from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher


class GroupMatcher:
    def __init__(
        self,
        expected: Sequence[Matcher],
        *,
        flatten: bool = False,
        allow_unwrapped: bool = False,
    ) -> None:
        self.expected = tuple(expected)
        self.flatten = flatten
        self.allow_unwrapped = allow_unwrapped

    def match(self, actual: BaseException) -> MatchResult:
        # EG-B3: allow_unwrapped=True delegation
        if isinstance(actual, BaseExceptionGroup):
            pass  # Will be handled by normal group matching
        elif self.allow_unwrapped and len(self.expected) == 1:
            # Delegate to the single expected matcher if allow_unwrapped is true
            # and there's exactly one expected matcher.
            return self.expected[0].match(actual)
        else:
            # If not a group, and allow_unwrapped is false or there's more than one matcher,
            # it's a mismatch unless it's a single matcher that *can* handle non-groups.
            # For now, we'll assume it's an unexpected group if we reach here and it's not a group.
            # The leaf matcher handles the case where it *should* be a leaf.
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.EXPECTED_GROUP,
                    "expected an exception group",
                    actual_index=0,
                    actual_path=(),
                )
            )

        # If we reach here, `actual` is a BaseExceptionGroup.
        actual_group = cast(BaseExceptionGroup, actual)

        # EG-B1: Preserve nested group boundaries by default.
        # EG-B2: If flatten=True, recursively expose leaves.
        # EG-B4: Pair matchers in expected order.

        # Determine the actual items to match against.
        actual_items_to_match: list[tuple[tuple[int, ...], BaseException]] | list[BaseException]
        if self.flatten:
            flattened_items: list[tuple[tuple[int, ...], BaseException]] = []
            self._flatten_group(actual_group, (), flattened_items)
            actual_items_to_match = flattened_items
        else:
            actual_items_to_match = actual_group.exceptions

        expected_matchers = list(self.expected)
        matched_actual_indices = set()
        evidence_list: list[MatchEvidence] = []

        # EG-B4: Pair matchers in expected order
        for i, expected_matcher in enumerate(expected_matchers):
            found_match_for_expected = False
            # Iterate over actual items with their original indices if not flattened,
            # or with their flattened paths and exceptions if flattened.
            for j, actual_item_data in enumerate(actual_items_to_match):
                if j in matched_actual_indices:
                    continue

                actual_path: tuple[int, ...]
                actual_exception: BaseException

                # Unpack actual_item_data correctly based on whether flatten is True
                if self.flatten and isinstance(actual_item_data, tuple):
                    actual_path, actual_exception = actual_item_data
                else:
                    # If not flattened, actual_item_data is just the exception
                    actual_path = ()
                    actual_exception = actual_item_data

                match_result = expected_matcher.match(actual_exception)

                if match_result.matched:
                    # EG-I1: Preserve leaf failure codes and actual paths
                    for ev in match_result.evidence:
                        evidence_list.append(
                            ev.located(
                                expected_index=i,
                                actual_index=j,
                                prefix=actual_path,
                            )
                        )
                    matched_actual_indices.add(j)
                    found_match_for_expected = True
                    break  # Move to the next expected matcher

            if not found_match_for_expected:
                # EG-B4: Report unmatched expected
                evidence_list.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"no actual item matched expected matcher {i}",
                        expected_index=i,
                    )
                )

        # EG-B4: Report unexpected actual items
        for j, actual_item_data in enumerate(actual_items_to_match):
            if j not in matched_actual_indices:
                actual_path: tuple[int, ...]
                actual_exception: BaseException

                if self.flatten and isinstance(actual_item_data, tuple):
                    actual_path, actual_exception = actual_item_data
                else:
                    actual_path = ()
                    actual_exception = actual_item_data

                evidence_list.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        f"actual item {j} was not matched by any expected matcher",
                        actual_index=j,
                        actual_path=actual_path,
                    )
                )

        # EG-B4: Flag when another complete pairing exists.
        # This is a heuristic: if all expected items were matched, and all actual items were consumed,
        # and there were failures, it's possible a different pairing would have succeeded.
        # A more robust check would require exploring alternative pairings.
        all_expected_matched = len(matched_actual_indices) == len(expected_matchers)
        all_actual_consumed = len(matched_actual_indices) == len(actual_items_to_match)
        
        # If there are failures AND we have a situation where all expected were matched and all actual were consumed,
        # it's a strong indicator that a different ordering could have worked.
        # Also, if the number of expected and actual items are equal, and there are failures,
        # it's a potential indicator.
        potential_alternative = (
            (all_expected_matched and all_actual_consumed and bool(evidence_list)) or
            (len(expected_matchers) == len(actual_items_to_match) and bool(evidence_list))
        )


        if not evidence_list and len(expected_matchers) == len(actual_items_to_match):
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence_list, possible_alternative_pairing=potential_alternative
            )

    def _flatten_group(
        self,
        group: BaseExceptionGroup,
        current_path: tuple[int, ...],
        flattened_list: list[tuple[tuple[int, ...], BaseException]],
    ) -> None:
        """Recursively flatten an ExceptionGroup, keeping track of the path."""
        for i, exc in enumerate(group.exceptions):
            new_path = current_path + (i,)
            if isinstance(exc, BaseExceptionGroup):
                self._flatten_group(exc, new_path, flattened_list)
            else:
                flattened_list.append((new_path, exc))
