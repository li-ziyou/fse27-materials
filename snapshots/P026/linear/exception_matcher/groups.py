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
        from .leaf import LeafMatcher # Import LeafMatcher here

        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                delegate_result = self.expected[0].match(actual)
                if delegate_result.matched:
                    return MatchResult.success()
                else:
                    processed_evidence = []
                    for ev in delegate_result.evidence:
                        processed_evidence.append(
                            ev.located(actual_index=0, prefix=(0,))
                        )
                    return MatchResult.failure(*processed_evidence, possible_alternative_pairing=delegate_result.possible_alternative_pairing)
            else:
                return MatchResult.failure(
                    MatchEvidence(FailureCode.EXPECTED_GROUP, "expected group but got leaf")
                )

        actual_exceptions = actual.exceptions
        expected_matchers = list(self.expected)
        actual_matched_indices = [False] * len(actual_exceptions)
        expected_matched_indices = [False] * len(expected_matchers)
        evidence = []

        if self.flatten:
            # Flattened mode: recursively expose leaves
            flat_actual = []
            for i, exc in enumerate(actual_exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    # Recursively flatten and add original index path
                    for j, sub_exc in enumerate(exc.exceptions):
                        flat_actual.append((sub_exc, (i, j)))
                else:
                    flat_actual.append((exc, (i,)))

            for i, (expected_matcher, expected_idx) in enumerate(zip(expected_matchers, range(len(expected_matchers)))):
                found_match = False
                for j, (actual_exception, actual_path) in enumerate(flat_actual):
                    if not actual_matched_indices[j]:
                        result = expected_matcher.match(actual_exception)
                        if result.matched:
                            evidence.append(
                                MatchEvidence(
                                    code=FailureCode.TYPE_MISMATCH, # Placeholder, will be replaced if it's a real mismatch
                                    message="matched",
                                    expected_index=expected_idx,
                                    actual_index=actual_path[0], # Use the first index of the original path
                                    actual_path=actual_path,
                                ).located(prefix=actual_path) # Ensure actual_path is set correctly
                            )
                            actual_matched_indices[j] = True
                            expected_matched_indices[i] = True
                            found_match = True
                            break
                if not found_match:
                    # If an expected matcher didn't find a match, add evidence for it
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message=f"expected matcher {expected_idx} did not find a match",
                            expected_index=expected_idx,
                        )
                    )

            # Collect unexpected actual exceptions
            for j, (actual_exception, actual_path) in enumerate(flat_actual):
                if not actual_matched_indices[j]:
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message=f"unexpected actual exception at path {actual_path}",
                            actual_index=actual_path[0],
                            actual_path=actual_path,
                        )
                    )

        else:
            # Default mode: preserve nested group boundaries
            actual_indices_to_match = list(range(len(actual_exceptions)))
            expected_idx = 0
            actual_idx_ptr = 0

            while expected_idx < len(expected_matchers) and actual_idx_ptr < len(actual_exceptions):
                current_expected = expected_matchers[expected_idx]
                current_actual = actual_exceptions[actual_idx_ptr]
                current_actual_original_index = actual_indices_to_match[actual_idx_ptr]

                result = current_expected.match(current_actual)

                if result.matched:
                    expected_matched_indices[expected_idx] = True
                    actual_matched_indices[actual_idx_ptr] = True
                    if isinstance(current_expected, GroupMatcher) and isinstance(current_actual, BaseExceptionGroup):
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.TYPE_MISMATCH, # Placeholder, will be replaced if it's a real mismatch
                                message="matched group",
                                expected_index=expected_idx,
                                actual_index=current_actual_original_index,
                                actual_path=(current_actual_original_index,),
                            )
                        )
                    else:
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.TYPE_MISMATCH, # Placeholder, will be replaced if it's a real mismatch
                                message="matched leaf",
                                expected_index=expected_idx,
                                actual_index=current_actual_original_index,
                                actual_path=(current_actual_original_index,),
                            )
                        )
                    actual_idx_ptr += 1
                    expected_idx += 1
                else:
                    if isinstance(current_actual, BaseExceptionGroup) and isinstance(current_expected, LeafMatcher) and not self.allow_unwrapped:
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.EXPECTED_GROUP,
                                message=f"expected a group matcher for actual group at index {current_actual_original_index}",
                                expected_index=expected_idx,
                                actual_index=current_actual_original_index,
                                actual_path=(current_actual_original_index,),
                            )
                        )
                        expected_matched_indices[expected_idx] = True # Mark expected as "handled" even though it failed
                        actual_matched_indices[actual_idx_ptr] = True
                        actual_idx_ptr += 1
                        expected_idx += 1
                    elif isinstance(current_actual, BaseException) and isinstance(current_expected, GroupMatcher) and not self.allow_unwrapped:
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.EXPECTED_GROUP,
                                message=f"expected a group matcher for actual leaf at index {current_actual_original_index}",
                                expected_index=expected_idx,
                                actual_index=current_actual_original_index,
                                actual_path=(current_actual_original_index,),
                            )
                        )
                        expected_matched_indices[expected_idx] = True
                        actual_matched_indices[actual_idx_ptr] = True
                        actual_idx_ptr += 1
                        expected_idx += 1
                    else:
                        if expected_idx + 1 < len(expected_matchers) and actual_idx_ptr + 1 < len(actual_exceptions):
                            next_actual_result = current_expected.match(actual_exceptions[actual_idx_ptr + 1])
                            if next_actual_result.matched:
                                evidence.append(
                                    MatchEvidence(
                                        code=FailureCode.UNEXPECTED_ACTUAL,
                                        message=f"unexpected actual exception at index {current_actual_original_index}",
                                        actual_index=current_actual_original_index,
                                        actual_path=(current_actual_original_index,),
                                    )
                                )
                                actual_idx_ptr += 1
                                continue 

                            next_expected_result = expected_matchers[expected_idx + 1].match(current_actual)
                            if next_expected_result.matched:
                                evidence.append(
                                    MatchEvidence(
                                        code=FailureCode.UNMATCHED_EXPECTED,
                                        message=f"unexpected expected matcher at index {expected_idx}",
                                        expected_index=expected_idx,
                                    )
                                )
                                expected_idx += 1
                                continue 
                        
                        if isinstance(current_actual, BaseExceptionGroup) and isinstance(current_expected, LeafMatcher):
                            evidence.append(
                                MatchEvidence(
                                    code=FailureCode.UNEXPECTED_GROUP,
                                    message="leaf matcher received group",
                                    expected_index=expected_idx,
                                    actual_index=current_actual_original_index,
                                    actual_path=(current_actual_original_index,),
                                )
                            )
                        elif isinstance(current_actual, BaseException) and isinstance(current_expected, GroupMatcher):
                            evidence.append(
                                MatchEvidence(
                                    code=FailureCode.EXPECTED_GROUP,
                                    message="expected group matcher for actual leaf",
                                    expected_index=expected_idx,
                                    actual_index=current_actual_original_index,
                                    actual_path=(current_actual_original_index,),
                                )
                            )
                        else:
                            failed_match_result = result 
                            if failed_match_result.evidence:
                                for ev in failed_match_result.evidence:
                                    evidence.append(
                                        ev.located(
                                            expected_index=expected_idx,
                                            actual_index=current_actual_original_index,
                                            prefix=(current_actual_original_index,),
                                        )
                                    )
                            else: 
                                evidence.append(
                                    MatchEvidence(
                                        code=FailureCode.TYPE_MISMATCH, 
                                        message="mismatch",
                                        expected_index=expected_idx,
                                        actual_index=current_actual_original_index,
                                        actual_path=(current_actual_original_index,),
                                    )
                                )
                        
                        expected_matched_indices[expected_idx] = True
                        actual_idx_ptr += 1
                        expected_idx += 1

            for i, matched in enumerate(expected_matched_indices):
                if not matched:
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message=f"expected matcher {i} was not matched",
                            expected_index=i,
                        )
                    )

            for i, matched in enumerate(actual_matched_indices):
                if not matched:
                    current_actual = actual_exceptions[i]
                    actual_path_segment = (i,)
                    if isinstance(current_actual, BaseExceptionGroup):
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNEXPECTED_GROUP,
                                message=f"unexpected group exception at index {i}",
                                actual_index=i,
                                actual_path=actual_path_segment,
                            )
                        )
                    else:
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNEXPECTED_ACTUAL,
                                message=f"unexpected actual exception at index {i}",
                                actual_index=i,
                                actual_path=actual_path_segment,
                            )
                        )

        possible_alternative_pairing = False
        if any(e.code == FailureCode.UNMATCHED_EXPECTED for e in evidence) and \
           any(e.code == FailureCode.UNEXPECTED_ACTUAL for e in evidence):
            possible_alternative_pairing = True
        
        if not evidence:
            return MatchResult.success()
        else:
            filtered_evidence = [e for e in evidence if e.message != "matched"]
            return MatchResult.failure(*filtered_evidence, possible_alternative_pairing=possible_alternative_pairing)
