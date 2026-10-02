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
        from .leaf import LeafMatcher

        # Handle cases where the actual exception is not an ExceptionGroup
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher if allow_unwrapped is True
                return self.expected[0].match(actual)
            else:
                # Otherwise, it's a mismatch because a group was expected
                return MatchResult.failure(
                    MatchEvidence(FailureCode.EXPECTED_GROUP, "An ExceptionGroup was expected but a leaf exception was provided.")
                )

        # Handle cases where the actual exception is an ExceptionGroup
        actual_exceptions = list(actual.exceptions)
        
        # If flatten is True, recursively extract all leaf exceptions and their paths
        flattened_actual: list[tuple[BaseException, tuple[int, ...]]] = []
        if self.flatten:
            def _flatten(exceptions: Sequence[BaseException], current_path: tuple[int, ...]):
                for i, exc in enumerate(exceptions):
                    if isinstance(exc, BaseExceptionGroup):
                        _flatten(exc.exceptions, current_path + (i,))
                    else:
                        flattened_actual.append((exc, current_path + (i,)))
            _flatten(actual_exceptions, ())
        else:
            # If not flattening, we'll work with the group structure directly,
            # but need to pair matchers with exceptions in order.
            # We'll represent actual exceptions with their index for easier pairing.
            # The actual_path will be handled during recursive calls.
            flattened_actual = [(exc, ()) for exc in actual_exceptions]


        # Attempt to match expected matchers against actual exceptions
        matched_indices = [False] * len(flattened_actual)
        collected_evidence: list[MatchEvidence] = []
        possible_alternative = False

        current_expected_idx = 0
        current_actual_idx_in_flattened = 0

        while current_expected_idx < len(self.expected) and current_actual_idx_in_flattened < len(flattened_actual):
            expected_matcher = self.expected[current_expected_idx]
            actual_exc, actual_path_prefix = flattened_actual[current_actual_idx_in_flattened]

            # Check for nested group matching when not flattening
            if not self.flatten and isinstance(actual_exc, BaseExceptionGroup):
                if not isinstance(expected_matcher, GroupMatcher):
                    # EG-B1: Nested group must be matched by a GroupMatcher
                    collected_evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message=f"Expected a GroupMatcher for nested ExceptionGroup at actual index {current_actual_idx_in_flattened}.",
                        expected_index=current_expected_idx,
                        actual_index=current_actual_idx_in_flattened,
                        actual_path=actual_path_prefix # This will be () if not flattened
                    ).located(prefix=actual_path_prefix))
                    # Try to match the current expected matcher with the next actual item if possible
                    # This is part of EG-B4's alternative pairing logic
                    # For now, we'll just advance to see if next actual item matches
                    current_actual_idx_in_flattened += 1
                    continue # Try next actual item with the same expected matcher
                
                # Delegate to nested GroupMatcher
                nested_result = expected_matcher.match(actual_exc)
                
                # EG-I1: Preserve nested evidence and update path
                located_evidences = [
                    evidence.located(
                        expected_index=current_expected_idx,
                        actual_index=current_actual_idx_in_flattened,
                        prefix=actual_path_prefix
                    ) for evidence in nested_result.evidence
                ]
                collected_evidence.extend(located_evidences)
                
                if nested_result.matched:
                    matched_indices[current_actual_idx_in_flattened] = True
                    current_expected_idx += 1
                    current_actual_idx_in_flattened += 1
                else:
                    if nested_result.possible_alternative_pairing:
                        possible_alternative = True
                    # If nested match failed, try to match the current expected with the next actual.
                    # This is essential for EG-B4's alternative pairing logic.
                    current_actual_idx_in_flattened += 1
            
            else: # Actual item is a leaf exception (or we are in flatten mode)
                if isinstance(expected_matcher, GroupMatcher) and not self.flatten:
                    collected_evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Expected a GroupMatcher for an ExceptionGroup, but found a leaf exception at actual index {current_actual_idx_in_flattened}.",
                        expected_index=current_expected_idx,
                        actual_index=current_actual_idx_in_flattened,
                        actual_path=actual_path_prefix
                    ).located(prefix=actual_path_prefix))
                    current_actual_idx_in_flattened += 1
                    continue 

                leaf_result = expected_matcher.match(actual_exc)
                if leaf_result.matched:
                    matched_indices[current_actual_idx_in_flattened] = True
                    for evidence in leaf_result.evidence:
                        collected_evidence.append(evidence.located(
                            expected_index=current_expected_idx,
                            actual_index=current_actual_idx_in_flattened,
                            prefix=actual_path_prefix
                        ))
                    current_expected_idx += 1
                    current_actual_idx_in_flattened += 1
                else:
                    for evidence in leaf_result.evidence:
                        collected_evidence.append(evidence.located(
                            expected_index=current_expected_idx,
                            actual_index=current_actual_idx_in_flattened,
                            prefix=actual_path_prefix
                        ))
                    if leaf_result.possible_alternative_pairing:
                        possible_alternative = True
                    current_actual_idx_in_flattened += 1
    
        else: # Actual item is a leaf exception (or we are in flatten mode)
            if isinstance(expected_matcher, GroupMatcher) and not self.flatten:
                collected_evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Expected a GroupMatcher for an ExceptionGroup, but found a leaf exception at actual index {current_actual_idx_in_flattened}.",
                    expected_index=current_expected_idx,
                    actual_index=current_actual_idx_in_flattened,
                    actual_path=actual_path_prefix
                ).located(prefix=actual_path_prefix))
                current_actual_idx_in_flattened += 1
    
            leaf_result = expected_matcher.match(actual_exc)
            if leaf_result.matched:
                matched_indices[current_actual_idx_in_flattened] = True
                for evidence in leaf_result.evidence:
                    collected_evidence.append(evidence.located(
                        expected_index=current_expected_idx,
                        actual_index=current_actual_idx_in_flattened,
                        prefix=actual_path_prefix
                    ))
                current_expected_idx += 1
                current_actual_idx_in_flattened += 1
            else:
                for evidence in leaf_result.evidence:
                    collected_evidence.append(evidence.located(
                        expected_index=current_expected_idx,
                        actual_index=current_actual_idx_in_flattened,
                        prefix=actual_path_prefix
                    ))
                if leaf_result.possible_alternative_pairing:
                    possible_alternative = True
                current_actual_idx_in_flattened += 1


        if current_expected_idx < len(self.expected):
            for i in range(current_expected_idx, len(self.expected)):
                collected_evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher at index {i} was not used.",
                    expected_index=i,
                    actual_index=None,
                    actual_path=()
                ))

        if not all(matched_indices):
            for i in range(len(flattened_actual)):
                if not matched_indices[i]:
                    exc, path = flattened_actual[i]
                    collected_evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Actual exception at index {i} (path: {path}) was not matched.",
                        expected_index=None,
                        actual_index=i,
                        actual_path=path
                    ))

        is_successful_match = (
            current_expected_idx == len(self.expected) and
            all(matched_indices) and
            not collected_evidence
        )

        if is_successful_match:
            return MatchResult.success()
        else:
            if not possible_alternative and (current_expected_idx < len(self.expected) or not all(matched_indices)):
                possible_alternative = True
            
            return MatchResult.failure(
                tuple(collected_evidence),
                possible_alternative_pairing=possible_alternative
            )


        if current_expected_idx < len(self.expected):
            for i in range(current_expected_idx, len(self.expected)):
                collected_evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher at index {i} was not used.",
                    expected_index=i,
                    actual_index=None,
                    actual_path=()
                ))

        if not all(matched_indices):
            for i in range(len(flattened_actual)):
                if not matched_indices[i]:
                    exc, path = flattened_actual[i]
                    collected_evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Actual exception at index {i} (path: {path}) was not matched.",
                        expected_index=None,
                        actual_index=i,
                        actual_path=path
                    ))

        is_successful_match = (
            current_expected_idx == len(self.expected) and
            all(matched_indices) and
            not collected_evidence
        )

        if is_successful_match:
            return MatchResult.success()
        else:
            if not possible_alternative and (current_expected_idx < len(self.expected) or not all(matched_indices)):
                possible_alternative = True
            
            return MatchResult.failure(
                tuple(collected_evidence),
                possible_alternative_pairing=possible_alternative
            )
