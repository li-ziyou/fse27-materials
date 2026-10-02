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
            # If the actual exception is not a group, it can only be matched by GroupMatcher
            # if allow_unwrapped is True and there's exactly one expected matcher.
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher.
                return self.expected[0].match(actual)
            else:
                # Otherwise, it's a mismatch because a group was expected.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected an ExceptionGroup, but got a leaf exception.",
                    )
                )

        # EG-B1: GroupMatcher preserves nested group boundaries by default.
        # A nested group is matched by a nested matcher rather than by a leaf matcher.
        if not self.flatten:
            # Default behavior: nested groups must be matched by nested GroupMatchers.
            # We need to recursively match the actual group's exceptions against the expected matchers.
            # This part requires a more sophisticated matching logic that considers nested structure.
            # For now, let's focus on the core logic of matching a group against its expected matchers.
            # The actual implementation will involve iterating through actual.exceptions and matching them
            # against self.expected, respecting nested GroupMatchers.

            # Placeholder for now, will be implemented in subsequent steps.
            # The core idea is to pair expected matchers with actual exceptions,
            # and if an expected matcher is itself a GroupMatcher, it should try to match
            # an actual ExceptionGroup.
            pass # This will be fleshed out in more detailed implementations.

        # EG-B2: flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence.
        if self.flatten:
            actual_exceptions = list(actual.exceptions)
            matched_indices = [False] * len(actual_exceptions)
            evidence = []

            for i, expected_matcher in enumerate(self.expected):
                found_match = False
                for j, actual_exception in enumerate(actual_exceptions):
                    if not matched_indices[j]:
                        # Recursively call match on the actual exception.
                        # If the actual exception is a group and flatten is true,
                        # this will continue to expose leaves.
                        result = expected_matcher.match(actual_exception)

                        if result.matched:
                            matched_indices[j] = True
                            found_match = True
                            # If the nested match had evidence, it should be preserved and updated with the path.
                            if result.evidence:
                                for ev in result.evidence:
                                    evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                        break # Move to the next expected matcher

                if not found_match:
                    # If an expected matcher did not find a match, record the failure.
                    evidence.append(MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"Expected matcher {i} did not find a match.",
                        expected_index=i
                    ))

            # Check for any remaining unmatched actual exceptions
            for j, actual_exception in enumerate(actual_exceptions):
                if not matched_indices[j]:
                    evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Unexpected actual exception at index {j}.",
                        actual_index=j,
                        actual_path=(j,)
                    ))

        if not evidence:
            return MatchResult.success()
        else:
            # EG-B4: flag when another complete pairing exists.
            # This requires a more complex lookahead or backtracking logic.
            # For now, we'll assume no alternative pairing is found.
            return MatchResult.failure(tuple(evidence), possible_alternative_pairing=False)


# EG-B1: GroupMatcher preserves nested group boundaries by default, so a nested group is matched by a nested matcher rather than by a leaf matcher.
    if not self.flatten:
        # This is the default behavior. We need to match expected matchers against actual exceptions,
        # and if an expected matcher is a GroupMatcher, it should attempt to match an ExceptionGroup.
        # This requires a recursive matching approach.
        actual_exceptions = list(actual.exceptions)
        matched_indices = [False] * len(actual_exceptions)
        evidence = []

        for i, expected_matcher in enumerate(self.expected):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if not matched_indices[j]:
                    # If the expected matcher is a GroupMatcher and the actual is an ExceptionGroup,
                    # we should delegate to the GroupMatcher's match method.
                    if isinstance(expected_matcher, GroupMatcher) and isinstance(actual_exception, ExceptionGroup):
                        result = expected_matcher.match(actual_exception)
                        if result.matched:
                            matched_indices[j] = True
                            found_match = True
                            # Preserve evidence from nested matches, updating paths.
                            if result.evidence:
                                for ev in result.evidence:
                                    evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                            break
                    # Otherwise, try to match with the current expected_matcher
                    else:
                        result = expected_matcher.match(actual_exception)
                        if result.matched:
                            matched_indices[j] = True
                            found_match = True
                            if result.evidence:
                                for ev in result.evidence:
                                    evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                            break

            if not found_match:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher {i} did not find a match.",
                    expected_index=i
                ))

        # Check for any remaining unmatched actual exceptions
        for j, actual_exception in enumerate(actual_exceptions):
            if not matched_indices[j]:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Unexpected actual exception at index {j}.",
                    actual_index=j,
                    actual_path=(j,)
                ))

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(tuple(evidence), possible_alternative_pairing=False)

    # EG-B2: flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence.
    if self.flatten:
        actual_exceptions = list(actual.exceptions)
        matched_indices = [False] * len(actual_exceptions)
        evidence = []

        for i, expected_matcher in enumerate(self.expected):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if not matched_indices[j]:
                    # Recursively call match on the actual exception.
                    # If the actual exception is a group and flatten is true,
                    # this will continue to expose leaves.
                    result = expected_matcher.match(actual_exception)

                    if result.matched:
                        matched_indices[j] = True
                        found_match = True
                        # If the nested match had evidence, it should be preserved and updated with the path.
                        if result.evidence:
                            for ev in result.evidence:
                                evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                        break # Move to the next expected matcher

            if not found_match:
                # If an expected matcher did not find a match, record the failure.
                evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher {i} did not find a match.",
                    expected_index=i
                ))

        # Check for any remaining unmatched actual exceptions
        for j, actual_exception in enumerate(actual_exceptions):
            if not matched_indices[j]:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Unexpected actual exception at index {j}.",
                    actual_index=j,
                    actual_path=(j,)
                ))

        if not evidence:
            return MatchResult.success()
        else:
            # EG-B4: flag when another complete pairing exists.
            # This requires a more complex lookahead or backtracking logic.
            # For now, we'll assume no alternative pairing is found.
            return MatchResult.failure(tuple(evidence), possible_alternative_pairing=False)

    # If we reach here, it means flatten is False and the logic for non-flattened groups is above.
    # This part of the code should not be reached if flatten is True.
    # The original placeholder return statement is removed.
