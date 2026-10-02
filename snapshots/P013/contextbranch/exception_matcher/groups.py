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
        if not isinstance(actual, ExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                # If allow_unwrapped is True and there's exactly one expected matcher,
                # try to match the non-group exception with that single matcher.
                return self.expected[0].match(actual)
            else:
                # Otherwise, a group is required, and we received a non-group exception.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message=f"Expected an ExceptionGroup, but got {type(actual).__name__}",
                    )
                )

        # Handle nested groups (EG-B1)
        if not self.flatten:
            # Default behavior: preserve nested group boundaries.
            # We need to match the actual group against a nested GroupMatcher.
            # If there's only one expected matcher and it's a GroupMatcher, use it.
            # Otherwise, this scenario might need more complex handling or is an error.
            # For now, assuming a single nested GroupMatcher is the expected case.
            if len(self.expected) == 1 and isinstance(self.expected[0], GroupMatcher):
                return self.expected[0].match(actual)
            else:
                # If not flattening, and there are multiple expected matchers, or the single
                # expected matcher isn't a GroupMatcher, it's a mismatch for the group itself.
                # We'll report this as an unexpected group if there are actual items in the group.
                if actual.exceptions:
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_GROUP,
                            message=f"Expected a single GroupMatcher for nested group, but got {len(self.expected)} expected matchers.",
                        )
                    )
                else:
                    # Empty group, no expected matchers, considered a success for the group itself.
                    return MatchResult.success()

        # Handle flattening (EG-B2)
        # If flatten is True, we recursively expose leaves.
        # We need to iterate through actual exceptions and match them against expected matchers.

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        result_evidence: list[MatchEvidence] = []
        actual_idx = 0
        expected_idx = 0

        while expected_idx < len(expected_matchers) and actual_idx < len(actual_exceptions):
            expected_matcher = expected_matchers[expected_idx]
            actual_exc = actual_exceptions[actual_idx]

            # Recursively call match for nested GroupMatchers if flatten is True.
            # This ensures that nested groups are also flattened if encountered.
            if isinstance(actual_exc, ExceptionGroup) and isinstance(expected_matcher, GroupMatcher):
                nested_result = expected_matcher.match(actual_exc)
                if nested_result.matched:
                    # If the nested group matched, we need to incorporate its evidence,
                    # especially the actual path to the leaves within that group.
                    # The actual path preservation is handled by the nested match itself.
                    # We need to ensure that the evidence from the nested match is correctly
                    # attributed to the current level's indices and prefix.
                    for ev in nested_result.evidence:
                        result_evidence.append(
                            ev.located(
                                expected_index=expected_idx,
                                actual_index=actual_idx,
                                prefix=(actual_idx,) + ev.actual_path # Append current actual index to nested path
                            )
                        )
                else:
                    # If nested group failed, propagate the failure.
                    # We need to correctly map nested failures back to the current level's indices.
                    for ev in nested_result.evidence:
                        result_evidence.append(
                            ev.located(
                                expected_index=expected_idx,
                                actual_index=actual_idx,
                                prefix=(actual_idx,) # The prefix here should be based on the current actual index
                            )
                        )
                    # If a nested group fails, we might still have other items to match.
                    # However, EG-B4 states pairing in order, so a failure here breaks the sequence.
                    # We'll proceed to report failures.
                    # For now, let's break and report.
                    break
            else:
                # Try to match the actual exception with the current expected matcher.
                # If the actual exception is a group but the expected is not a GroupMatcher,
                # this is a type mismatch for the current level.
                if isinstance(actual_exc, ExceptionGroup) and not isinstance(expected_matcher, GroupMatcher):
                    result_evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_GROUP,
                            message=f"Expected a leaf exception, but got an ExceptionGroup at actual index {actual_idx}.",
                            expected_index=expected_idx,
                            actual_index=actual_idx,
                        )
                    )
                    break # Move to failure reporting

                match_result = expected_matcher.match(actual_exc)

                if match_result.matched:
                    # Successful match, advance both expected and actual indices.
                    expected_idx += 1
                    actual_idx += 1
                else:
                    # Mismatch. EG-B4: report unmatched expected and unexpected actual.
                    # If the actual exception is an ExceptionGroup and we are not flattening,
                    # this is a problem that should have been caught earlier or handled differently.
                    # But if flatten is True, we should have already tried to match it recursively.
                    # If we reach here with an actual ExceptionGroup, it means it wasn't
                    # matched by a GroupMatcher, so it's an unexpected group at this point.
                    if isinstance(actual_exc, ExceptionGroup):
                        result_evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNEXPECTED_GROUP,
                                message=f"Unexpected ExceptionGroup at actual index {actual_idx}.",
                                expected_index=expected_idx,
                                actual_index=actual_idx,
                            )
                        )
                    else:
                        # Propagate leaf failure evidence, adding context of current indices.
                        for ev in match_result.evidence:
                            result_evidence.append(
                                ev.located(
                                    expected_index=expected_idx,
                                    actual_index=actual_idx,
                                    prefix=(actual_idx,) # This prefix might need adjustment for deeper nesting
                                )
                            )

                    # EG-B4: flag when another complete pairing exists.
                    # This is complex: requires looking ahead. For now, we focus on basic matching.
                    # A simple approach is to check if the remaining expected and actual items could form a match.
                    # This is a significant implementation detail for EG-B4.
                    # For now, we'll set possible_alternative_pairing based on a simplified check.
                    # A more robust check would involve trying to match remaining items.
                    possible_alternative = False
                    # Check if the number of remaining expected matchers equals the number of remaining actual exceptions.
                    # This is a necessary but not sufficient condition for an alternative pairing to exist.
                    if (len(expected_matchers) - expected_idx == len(actual_exceptions) - actual_idx) and \
                       (len(expected_matchers) - expected_idx > 0): # Ensure there are items left to potentially pair
                        possible_alternative = True

                    return MatchResult.failure(
                        *result_evidence,
                        possible_alternative_pairing=possible_alternative,
                    )

        # After the loop, check for remaining unmatched items.
        if expected_idx < len(expected_matchers):
            # Unmatched expected matchers
            for i in range(expected_idx, len(expected_matchers)):
                result_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher at index {i}",
                        expected_index=i,
                    )
                )

        if actual_idx < len(actual_exceptions):
            # Unexpected actual exceptions
            for i in range(actual_idx, len(actual_exceptions)):
                actual_exc = actual_exceptions[i]
                code = FailureCode.UNEXPECTED_GROUP if isinstance(actual_exc, ExceptionGroup) else FailureCode.UNEXPECTED_ACTUAL
                message = f"Unexpected exception group at actual index {i}" if isinstance(actual_exc, ExceptionGroup) else f"Unexpected actual exception at index {i}"
                result_evidence.append(
                    MatchEvidence(
                        code=code,
                        message=message,
                        actual_index=i,
                        actual_path=(i,)
                    )
                )

        if result_evidence:
            # EG-B4: flag when another complete pairing exists.
            # This is a simplified check. A full implementation would require backtracking or lookahead.
            possible_alternative = False
            # Check if the number of remaining expected matchers equals the number of remaining actual exceptions.
            # This is a necessary but not sufficient condition for an alternative pairing to exist.
            if (len(expected_matchers) - expected_idx == len(actual_exceptions) - actual_idx) and \
               (len(expected_matchers) - expected_idx > 0): # Ensure there are items left to potentially pair
                possible_alternative = True

            return MatchResult.failure(
                *result_evidence,
                possible_alternative_pairing=possible_alternative,
            )

        # If no evidence was collected, the match was successful.
        return MatchResult.success()
