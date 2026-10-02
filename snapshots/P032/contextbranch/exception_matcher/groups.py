from __future__ import annotations

from collections.abc import Sequence

from .contracts import MatchResult, Matcher


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
        from .contracts import FailureCode, MatchEvidence, MatchResult

        def _flatten_group(exc_group: BaseExceptionGroup, current_path: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], BaseException]]:
            leaves = []
            for i, exc in enumerate(exc_group.exceptions):
                new_path = current_path + (i,)
                if isinstance(exc, BaseExceptionGroup):
                    leaves.extend(_flatten_group(exc, new_path))
                else:
                    leaves.append((new_path, exc))
            return leaves

        if self.allow_unwrapped:
            if len(self.expected) == 1 and not isinstance(actual, BaseExceptionGroup):
                return self.expected[0].match(actual)
            elif len(self.expected) > 1 and not isinstance(actual, BaseExceptionGroup):
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.EXPECTED_GROUP,
                        f"Expected a group with {len(self.expected)} matchers, but got a single exception",
                    )
                )

        actual_items_with_paths: list[tuple[tuple[int, ...], BaseException]] = []
        if isinstance(actual, BaseExceptionGroup):
            if self.flatten:
                actual_items_with_paths = _flatten_group(actual)
            else:
                for i, exc in enumerate(actual.exceptions):
                    actual_items_with_paths.append(((i,), exc))
        else:
            if not self.allow_unwrapped or len(self.expected) != 1:
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.EXPECTED_GROUP,
                        "Expected an exception group",
                    )
                )

        expected_matchers = list(self.expected)
        
        matched_actual_indices = set()
        evidence = []
        possible_alternative_pairing = False

        for i, expected_matcher in enumerate(expected_matchers):
            found_match_for_expected = False
            
            for j, (actual_path, actual_item) in enumerate(actual_items_with_paths):
                if j in matched_actual_indices:
                    continue

                actual_is_group = isinstance(actual_item, BaseExceptionGroup)
                expected_is_group_matcher = hasattr(expected_matcher, "expected")

                if not self.flatten:
                    if actual_is_group and not expected_is_group_matcher:
                        evidence.append(
                            MatchEvidence(
                                FailureCode.UNEXPECTED_GROUP,
                                "Expected a leaf exception, but got a group",
                                expected_index=i,
                                actual_index=j,
                                actual_path=actual_path,
                            )
                        )
                        continue # Try next actual item

                    if not actual_is_group and expected_is_group_matcher:
                        if not (self.allow_unwrapped and len(self.expected) == 1): # Re-check allow_unwrapped condition
                            evidence.append(
                                MatchEvidence(
                                    FailureCode.EXPECTED_GROUP,
                                    "Expected a group matcher for a nested group",
                                    expected_index=i,
                                    actual_index=j,
                                    actual_path=actual_path,
                                )
                            )
                            continue # Try next actual item
                
                sub_result = expected_matcher.match(actual_item)

                if sub_result.matched:
                    for ev in sub_result.evidence:
                        evidence.append(
                            ev.located(
                                expected_index=i,
                                actual_index=j,
                                prefix=actual_path,
                            )
                        )
                    matched_actual_indices.add(j)
                    found_match_for_expected = True
                    break

            

            if not found_match_for_expected:
                # EG-B4: Report unmatched expected.
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        "No actual item matched this expected matcher",
                        expected_index=i,
                    )
                )

        all_available_actual_indices = set(range(len(actual_items_with_paths)))
        unexpected_actual_indices = all_available_actual_indices - matched_actual_indices

        for j in unexpected_actual_indices:
            actual_path, _ = actual_items_with_paths[j]
            evidence.append(
                MatchEvidence(
                    FailureCode.UNEXPECTED_ACTUAL,
                    "Actual item was not matched by any expected matcher",
                    actual_index=j,
                    actual_path=actual_path,
                )
            )

        num_unmatched_expected = sum(1 for ev in evidence if ev.code == FailureCode.UNMATCHED_EXPECTED)
        num_unexpected_actual = sum(1 for ev in evidence if ev.code == FailureCode.UNEXPECTED_ACTUAL)

        if num_unmatched_expected > 0 and num_unexpected_actual > 0 and num_unmatched_expected == num_unexpected_actual:
            possible_alternative_pairing = True
        elif len(expected_matchers) == len(actual_items_with_paths) and len(evidence) > 0:
            possible_alternative_pairing = True

        if not evidence and len(expected_matchers) == len(actual_items_with_paths) and len(matched_actual_indices) == len(actual_items_with_paths):
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative_pairing,
            )
