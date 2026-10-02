from __future__ import annotations

from collections.abc import Sequence

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
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                delegate_result = self.expected[0].match(actual)
                # If the delegate match was successful and had no evidence, return its result directly.
                if delegate_result.matched and not delegate_result.evidence:
                    return delegate_result
                # Augment evidence from the delegate match with the correct actual_index and prefix.
                augmented_evidence = tuple(
                    ev.located(actual_index=0, prefix=()) for ev in delegate_result.evidence
                )
                return MatchResult(delegate_result.matched, augmented_evidence, delegate_result.possible_alternative_pairing)
            else:
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_GROUP,
                        "Expected an exception group, but got a leaf exception.",
                    )
                )

        def get_all_leaves(exceptions: Sequence[BaseException], current_path: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], BaseException]]:
            leaves = []
            for i, exc in enumerate(exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    if not self.flatten:
                        leaves.append((current_path + (i,), exc))
                    else:
                        leaves.extend(get_all_leaves(exc.exceptions, current_path + (i,)))
                else:
                    leaves.append((current_path + (i,), exc))
            return leaves

        actual_items_with_paths = get_all_leaves(actual.exceptions)

        matched_indices = set()
        evidence = []
        
        current_actual_item_idx = 0
        for i, expected_matcher in enumerate(self.expected):
            found_match = False
            for j, (actual_path, actual_exception) in enumerate(actual_items_with_paths):
                if j not in matched_indices:
                    result = expected_matcher.match(actual_exception)
                    if result.matched:
                        augmented_evidence = tuple(
                            ev.located(actual_index=current_actual_item_idx, prefix=actual_path, expected_index=i) for ev in result.evidence
                        )
                        evidence.extend(augmented_evidence)
                        matched_indices.add(j)
                        found_match = True
                        current_actual_item_idx += 1
                        break
                    elif self.flatten:
                        augmented_evidence = tuple(
                            ev.located(actual_index=current_actual_item_idx, prefix=actual_path, expected_index=i) for ev in result.evidence
                        )
                        evidence.extend(augmented_evidence)

            if not found_match:
                if self.flatten:
                    evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"No actual leaf matched expected matcher {expected_matcher}.", expected_index=i))
                else:
                    evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"No actual item matched expected matcher {expected_matcher}.", expected_index=i))

        for i, (actual_path, actual_exception) in enumerate(actual_items_with_paths):
            if i not in matched_indices:
                evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"Unexpected actual item: {actual_exception}", actual_index=i, actual_path=actual_path))
        
        possible_alternative_pairing = False
        unmatched_expected_count = sum(1 for ev in evidence if ev.code == FailureCode.UNMATCHED_EXPECTED)
        unexpected_actual_count = sum(1 for ev in evidence if ev.code == FailureCode.UNEXPECTED_ACTUAL)

        if unmatched_expected_count > 0 and unexpected_actual_count > 0:
            if unexpected_actual_count >= unmatched_expected_count:
                 possible_alternative_pairing = True
        elif not evidence and len(self.expected) > 0 and len(actual_items_with_paths) > 0 and len(self.expected) != len(actual_items_with_paths):
             pass

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative_pairing
            )
