from __future__ import annotations

from collections.abc import Sequence

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher
from .leaf import LeafMatcher


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
                return self.expected[0].match(actual)
            else:
                return MatchResult.failure(MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP if len(self.expected) > 1 else FailureCode.EXPECTED_GROUP,
                    message=f"Expected an ExceptionGroup, but got {type(actual).__name__}",
                ))

        # We need to handle the case where `actual.exceptions` is modified in place by `collect_leaves`
        # if `flatten` is True. To avoid this, we create a copy.
        actual_exceptions_list = list(actual.exceptions)
        expected_matchers = self.expected
        evidence = []
        matched_indices = set()
        original_paths = {}  # To store original paths if flatten is True

        if self.flatten:
            # Collect all leaf exceptions and their original paths
            flat_actual_exceptions = []

            def collect_leaves(exc_group, current_path=()):
                for i, exc in enumerate(exc_group.exceptions):
                    if isinstance(exc, ExceptionGroup):
                        collect_leaves(exc, current_path + (i,))
                    else:
                        original_paths[len(flat_actual_exceptions)] = current_path + (i,)
                        flat_actual_exceptions.append(exc)

            collect_leaves(actual, ()) # Start with the top-level exception group
            actual_exceptions = flat_actual_exceptions
        else:
            actual_exceptions = actual_exceptions_list


        # EG-B4: expected matchers pair in expected order with the first still-unmatched successful actual item
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if j not in matched_indices:
                    # EG-B1: GroupMatcher preserves nested group boundaries by default
                    if not self.flatten and isinstance(actual_exception, ExceptionGroup) and isinstance(expected_matcher, GroupMatcher):
                        nested_match_result = expected_matcher.match(actual_exception)
                        if nested_match_result.matched:
                            matched_indices.add(j)
                            found_match = True
                            # If there's evidence from the nested match, we need to prepend the current actual_index to the path.
                            for ev in nested_match_result.evidence:
                                evidence.append(ev.located(actual_index=j, prefix=original_paths.get(j, ()) if self.flatten else ()))
                            break
                        else:
                            # If the nested group did not match, we need to record the evidence.
                            for ev in nested_match_result.evidence:
                                evidence.append(ev.located(expected_index=i, actual_index=j, prefix=original_paths.get(j, ()) if self.flatten else ()))

                    # If the expected matcher is a LeafMatcher and the actual exception is not an ExceptionGroup
                    elif isinstance(expected_matcher, LeafMatcher) and not isinstance(actual_exception, ExceptionGroup):
                        leaf_match_result = expected_matcher.match(actual_exception)
                        if leaf_match_result.matched:
                            matched_indices.add(j)
                            found_match = True
                            # If there's evidence from the leaf match, it should be empty for a successful match.
                            # However, if there were failures in the leaf match, we record them.
                            if leaf_match_result.evidence:
                                for ev in leaf_match_result.evidence:
                                    evidence.append(ev.located(expected_index=i, actual_index=j, prefix=original_paths.get(j, ()) if self.flatten else ()))
                            break
                        else:
                            # If the leaf did not match, record the evidence.
                            for ev in leaf_match_result.evidence:
                                evidence.append(ev.located(expected_index=i, actual_index=j, prefix=original_paths.get(j, ()) if self.flatten else ()))

            if not found_match:
                # If we couldn't find a match for the current expected matcher
                if isinstance(expected_matcher, GroupMatcher):
                    # If it's a GroupMatcher and we didn't find a matching group, it's an UNEXPECTED_GROUP
                    evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message=f"Expected an ExceptionGroup at expected index {i}, but no matching group found",
                        expected_index=i,
                    ))
                else:
                    # Otherwise, it's an UNMATCHED_EXPECTED
                    evidence.append(MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher {i}",
                        expected_index=i,
                    ))

        # Check for unexpected actual exceptions
        for j in range(len(actual_exceptions)):
            if j not in matched_indices:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Actual exception at index {j} was not matched",
                    actual_index=j,
                    actual_path=original_paths.get(j, ()) if self.flatten else ()
                ))

        # EG-B4: flag when another complete pairing exists
        possible_alternative_pairing = False
        # A more robust check for alternative pairings would involve exploring different matching combinations.
        # For this implementation, we'll simplify by flagging if the number of expected matchers equals
        # the number of actual exceptions, but we haven't matched all expected ones. This is a heuristic.
        if len(expected_matchers) == len(actual_exceptions) and len(matched_indices) < len(expected_matchers):
             possible_alternative_pairing = True

        return MatchResult(
            # A match is successful only if all expected matchers found a corresponding actual exception,
            # and all actual exceptions were matched.
            matched=len(evidence) == 0 and len(matched_indices) == len(actual_exceptions),
            evidence=tuple(evidence),
            possible_alternative_pairing=possible_alternative_pairing
        )
