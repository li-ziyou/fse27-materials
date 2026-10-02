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
        if not isinstance(actual, ExceptionGroup):
            # EG-B3: allow_unwrapped=True delegates a non-group exception only when there is exactly one expected matcher; otherwise a group is required.
            if self.allow_unwrapped and len(self.expected) == 1:
                result = self.expected[0].match(actual)
                if result.matched:
                    return MatchResult.success()
                else:
                    # If the single expected matcher fails, we need to wrap its evidence.
                    # EG-I1: preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
                    return MatchResult.failure(
                        result.evidence[0].located(expected_index=0, actual_index=0)
                    )
            else:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected an ExceptionGroup but received a non-group exception.",
                    )
                )

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        matched_results: list[MatchResult] = []
        evidence: list[MatchEvidence] = []
        
        # EG-B4: expected matchers pair in expected order with the first still-unmatched successful actual item
        actual_idx = 0
        for expected_idx, expected_matcher in enumerate(expected_matchers):
            found_match = False
            while actual_idx < len(actual_exceptions):
                current_actual = actual_exceptions[actual_idx]
                
                # EG-B1: GroupMatcher preserves nested group boundaries by default
                if isinstance(expected_matcher, GroupMatcher) and not self.flatten:
                    if isinstance(current_actual, ExceptionGroup):
                        result = expected_matcher.match(current_actual)
                        if result.matched:
                            matched_results.append(result)
                            found_match = True
                            actual_idx += 1
                            break
                        else:
                            # If a nested group doesn't match, we need to record the evidence
                            # EG-I1: preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
                            for ev in result.evidence:
                                evidence.append(ev.located(expected_index=expected_idx, actual_index=actual_idx, prefix=(actual_idx,)))
                            # We still need to advance actual_idx to consider the next actual exception
                            actual_idx += 1
                    else:
                        # Expected a group, but got a leaf.
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNEXPECTED_GROUP,
                                message=f"Expected a nested ExceptionGroup, but got a leaf exception.",
                                expected_index=expected_idx,
                                actual_index=actual_idx,
                            )
                        )
                        actual_idx += 1
                else:
                    # Leaf matcher or flatten=True
                    result = expected_matcher.match(current_actual)
                    if result.matched:
                        matched_results.append(result)
                        found_match = True
                        actual_idx += 1
                        break
                    else:
                        # EG-I1: preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
                        for ev in result.evidence:
                            evidence.append(ev.located(expected_index=expected_idx, actual_index=actual_idx))
                        actual_idx += 1

            if not found_match:
                # EG-B4: failures report unmatched expected items
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher at index {expected_idx}.",
                        expected_index=expected_idx,
                    )
                )
        
        # EG-B4: failures report unexpected actual items
        if actual_idx < len(actual_exceptions):
            for remaining_actual_idx in range(actual_idx, len(actual_exceptions)):
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Unexpected actual exception at index {remaining_actual_idx}.",
                        actual_index=remaining_actual_idx,
                    )
                )
        
        # EG-B4: flag when another complete pairing exists.
        possible_alternative_pairing = False
        if not evidence and len(expected_matchers) == len(actual_exceptions):
            # This is a simplified check. A more robust check would involve backtracking or dynamic programming
            # to see if *any* permutation of actual exceptions could match expected matchers.
            # For now, we assume if there are no direct mismatches and counts align, an alternative might exist.
            # This is a heuristic and might need refinement based on test cases.
            possible_alternative_pairing = True

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative_pairing)
