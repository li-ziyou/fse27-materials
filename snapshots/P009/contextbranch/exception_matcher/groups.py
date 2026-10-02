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
        from .leaf import LeafMatcher
        from .contracts import FailureCode, MatchEvidence

        # If allow_unwrapped is True, and we have exactly one expected matcher,
        # we can try to match a non-group exception directly.
        if self.allow_unwrapped and len(self.expected) == 1 and not isinstance(actual, ExceptionGroup):
            return self.expected[0].match(actual)

        # If the actual exception is not an ExceptionGroup, and we are not in allow_unwrapped mode
        # with a single matcher, it's a mismatch.
        if not isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.UNEXPECTED_GROUP,
                    f"Expected an ExceptionGroup, but got {type(actual).__name__}.",
                )
            )

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        
        # If flatten is True, we need to recursively find all leaf exceptions
        # and store their original path.
        processed_actual = []
        if self.flatten:
            def flatten_group(group: ExceptionGroup, path: tuple[int, ...] = ()):
                for i, exc in enumerate(group.exceptions):
                    if isinstance(exc, ExceptionGroup):
                        flatten_group(exc, path + (i,))
                    else:
                        processed_actual.append((exc, path + (i,)))
            flatten_group(actual)
        else:
            processed_actual = [(exc, ()) for exc in actual_exceptions]

        matched_indices = [False] * len(processed_actual)
        
        # EG-B4: Pair expected matchers with actual items in order.
        # EG-B1: Preserve nested group boundaries by default.
        # EG-I1: Preserve leaf failure codes and paths.
        
        final_evidence = []
        
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, (actual_exception, actual_path) in enumerate(processed_actual):
                if not matched_indices[j]:
                    # If flatten is True, we need to recursively search for leaf exceptions
                    if self.flatten:
                        if isinstance(expected_matcher, LeafMatcher):
                            # If the expected matcher is a LeafMatcher, we need to check if the actual exception is a leaf
                            # and if it matches. If it's a group, we can't match it with a LeafMatcher directly.
                            if not isinstance(actual_exception, ExceptionGroup):
                                sub_result = expected_matcher.match(actual_exception)
                                if sub_result.matched:
                                    # Preserve the original path of the actual exception
                                    if sub_result.evidence:
                                        evidence = sub_result.evidence[0].located(
                                            expected_index=i, actual_index=j, prefix=actual_path
                                        )
                                        final_evidence.append(evidence)
                                    matched_indices[j] = True
                                    found_match = True
                                    break
                        else: # expected_matcher is a GroupMatcher
                            # If flatten is True, and we encounter a GroupMatcher, we should recursively call match
                            # on the nested group, but we need to ensure we are passing the correct actual exceptions.
                            # This part is tricky because flatten=True means we are looking for leaves.
                            # For now, let's assume GroupMatcher with flatten=True will handle its own flattening.
                            sub_result = expected_matcher.match(actual_exception)
                            if sub_result.matched:
                                # Preserve the original path of the actual exception
                                if sub_result.evidence:
                                    evidence = sub_result.evidence[0].located(
                                        expected_index=i, actual_index=j, prefix=actual_path
                                    )
                                    final_evidence.append(evidence)
                                matched_indices[j] = True
                                found_match = True
                                break
                    else: # flatten is False (default behavior)
                        # If flatten is False, a GroupMatcher should match an ExceptionGroup, and a LeafMatcher should match a leaf exception.
                        if isinstance(expected_matcher, LeafMatcher) and not isinstance(actual_exception, ExceptionGroup):
                            sub_result = expected_matcher.match(actual_exception)
                            if sub_result.matched:
                                if sub_result.evidence:
                                    evidence = sub_result.evidence[0].located(
                                        expected_index=i, actual_index=j, prefix=actual_path
                                    )
                                    final_evidence.append(evidence)
                                matched_indices[j] = True
                                found_match = True
                                break
                        elif isinstance(expected_matcher, GroupMatcher) and isinstance(actual_exception, ExceptionGroup):
                            sub_result = expected_matcher.match(actual_exception)
                            if sub_result.matched:
                                if sub_result.evidence:
                                    evidence = sub_result.evidence[0].located(
                                        expected_index=i, actual_index=j, prefix=actual_path
                                    )
                                    final_evidence.append(evidence)
                                matched_indices[j] = True
                                found_match = True
                                break
                        else:
                            # If flatten is False, and the types don't match (LeafMatcher vs ExceptionGroup, or GroupMatcher vs leaf exception)
                            # this is a mismatch for this pair.
                            pass

            if not found_match:
                # EG-B4: Report unmatched expected items
                final_evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"No match found for expected matcher {i}",
                        expected_index=i,
                    )
                )

        # EG-B4: Report unexpected actual items
        unexpected_actual_indices = [j for j, matched in enumerate(matched_indices) if not matched]
        for j in unexpected_actual_indices:
            actual_exception, actual_path = processed_actual[j]
            final_evidence.append(
                MatchEvidence(
                    FailureCode.UNEXPECTED_ACTUAL,
                    f"Unexpected actual exception {j} ({type(actual_exception).__name__})",
                    actual_index=j,
                    actual_path=actual_path
                )
            )
        
        # EG-B4: Flag when another complete pairing exists.
        possible_alternative = False
        # If there are no failures, and more actual exceptions than expected matchers,
        # it implies an alternative pairing could exist if we ignored some actual items.
        if not final_evidence and len(processed_actual) > len(expected_matchers):
            possible_alternative = True
        # If there are failures, but none are due to unmatched expected or unexpected actual items,
        # and there are more actual exceptions than expected matchers, it might indicate an alternative pairing.
        # This condition specifically checks if the failures are not of the "unmatched expected" or "unexpected actual" type,
        # and if there are more actual items than expected matchers. This scenario suggests that if the current
        # pairing were slightly different (e.g., different order or different choices for ambiguous matches),
        # a complete pairing might have been possible.
        elif final_evidence and len(processed_actual) > len(expected_matchers) and \
             all(e.code not in (FailureCode.UNMATCHED_EXPECTED, FailureCode.UNEXPECTED_ACTUAL) for e in final_evidence):
             possible_alternative = True
        # Also consider the case where there are exactly as many expected matchers as actual items,
        # but a failure occurred that wasn't an unmatched expected or unexpected actual. This could also
        # indicate an alternative pairing if the failures were due to, e.g., message mismatches,
        # and a different pairing might have succeeded.
        elif final_evidence and len(processed_actual) == len(expected_matchers) and \
             all(e.code not in (FailureCode.UNMATCHED_EXPECTED, FailureCode.UNEXPECTED_ACTUAL) for e in final_evidence):
             possible_alternative = True

        if final_evidence:
            return MatchResult.failure(
                *final_evidence,
                possible_alternative_pairing=possible_alternative
            )
        else:
            return MatchResult.success()
