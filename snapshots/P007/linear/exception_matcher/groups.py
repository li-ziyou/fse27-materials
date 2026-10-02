import sys
from __future__ import annotations

from collections.abc import Sequence
from typing import Tuple

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
        from .leaf import LeafMatcher

        all_evidence: list[MatchEvidence] = []
        possible_alternative = False

        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                result = self.expected[0].match(actual)
                # If the single matcher fails, propagate its evidence
                if not result.matched:
                    # Add original context if it's a leaf failure
                    # EG-I1: the evidence needs to be located with the correct expected_index and actual_index.
                    # Since we are delegating to a single matcher, its index is 0.
                    # The actual item is also the first (and only) actual item.
                    for ev in result.evidence:
                        all_evidence.append(ev.located(expected_index=0, actual_index=0, prefix=()))
                    return MatchResult.failure(tuple(all_evidence), possible_alternative_pairing=result.possible_alternative_pairing)
                return result # Success
            else:
                # Expected a group, but got a leaf.
                # EG-B3: If allow_unwrapped is False or there are multiple expected matchers, a group is required.
                # EG-A1: LeafMatcher rejects groups, GroupMatcher requires groups unless allow_unwrapped.
                # If we are here, it means we got a leaf but expected a group (or multiple matchers for unwrapped).
                if not self.allow_unwrapped or len(self.expected) > 1:
                    # If we are not allowed to unwrap or there are multiple expected matchers, a group is required.
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.EXPECTED_GROUP,
                            message="Expected an exception group, but received a leaf exception.",
                        )
                    )
                # This case should theoretically be covered by the allow_unwrapped logic above,
                # but as a fallback, if we reach here, it means we got a leaf and expected a group.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected an exception group, but received a leaf exception.",
                    )
                )

        # Handle ExceptionGroup
        actual_exceptions = actual.exceptions
        num_expected = len(self.expected)
        num_actual = len(actual_exceptions)

        # EG-B2: flatten=True recursively exposes leaves for matching
        if self.flatten:
            flat_actual_exceptions_with_paths: list[tuple[BaseException, tuple[int, ...]]] = []
            
            def collect_leaves(excs: Sequence[BaseException], current_path: tuple[int, ...]):
                for i, exc in enumerate(excs):
                    if isinstance(exc, BaseExceptionGroup):
                        # If flatten is True, we recurse into nested groups.
                        collect_leaves(exc.exceptions, current_path + (i,))
                    else:
                        # Found a leaf exception. Store it with its path.
                        flat_actual_exceptions_with_paths.append((exc, current_path + (i,)))
            
            collect_leaves(actual.exceptions, ())

            # Now match the expected matchers against these flattened actual leaves
            actual_items_to_match = [item[0] for item in flat_actual_exceptions_with_paths]
            actual_paths = [item[1] for item in flat_actual_exceptions_with_paths]

            matched_actual_indices = set()
            for i, expected_matcher in enumerate(self.expected):
                found_match = False
                for j, actual_item in enumerate(actual_items_to_match):
                    if j in matched_actual_indices:
                        continue

                    # If flatten is True, we expect to match leaves. A GroupMatcher as an expected matcher
                    # cannot directly match a leaf exception. This will result in an UNMATCHED_EXPECTED
                    # for this expected_matcher if no other actual item can match it.
                    if isinstance(expected_matcher, GroupMatcher):
                        # A GroupMatcher cannot match a leaf directly. We will consider this expected_matcher
                        # as not matching this actual_item. It will be handled as UNMATCHED_EXPECTED later.
                        continue 

                    # Match actual_item against expected_matcher (expected to be a LeafMatcher)
                    match_result = expected_matcher.match(actual_item)
                    if match_result.matched:
                        # If the leaf match was successful, we don't add evidence.
                        # If it failed, we add its evidence, and importantly, we add the path.
                        if not match_result.matched:
                            for ev in match_result.evidence:
                                # EG-I1: Preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
                                all_evidence.append(ev.located(expected_index=i, actual_index=j, prefix=actual_paths[j]))
                            possible_alternative = possible_alternative or match_result.possible_alternative_pairing
                        
                        matched_actual_indices.add(j)
                        found_match = True
                        break # Move to the next expected matcher

                if not found_match:
                    # EG-B4: Failures report unmatched expected items
                    all_evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message=f"Expected matcher {i} did not match any actual item.",
                            expected_index=i,
                            actual_index=None,
                        )
                    )
            
            # EG-B4: Failures report unexpected actual items
            for j in range(num_actual):
                if j not in matched_actual_indices:
                    # This actual item was not matched by any expected matcher
                    all_evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message=f"Actual item {j} was not matched by any expected matcher.",
                            actual_index=j,
                            actual_path=actual_paths[j],
                            expected_index=None,
                        )
                    )
            
            # EG-B4: flag when another complete pairing exists.
            if all_evidence:
                return MatchResult.failure(tuple(all_evidence), possible_alternative_pairing=possible_alternative)
            else:
                # If no evidence was collected, it means all expected items were matched and all actual items were consumed.
                return MatchResult.success()

        else: # Not flattening, preserve group boundaries (EG-B1)
            matched_actual_indices = set()
            
            # Iterate through expected matchers
            for i, expected_matcher in enumerate(self.expected):
                found_match_for_expected = False
                
                # Iterate through actual exceptions to find a match for the current expected_matcher
                for j, actual_exception in enumerate(actual_exceptions):
                    if j in matched_actual_indices:
                        continue # This actual exception has already been matched

                    is_actual_group = isinstance(actual_exception, BaseExceptionGroup)
                    is_expected_group_matcher = isinstance(expected_matcher, GroupMatcher)

                    # Rule EG-B1: Preserve nested group boundaries.
                    # If the actual exception is a group, the expected matcher MUST be a GroupMatcher.
                    if is_actual_group and not is_expected_group_matcher:
                        continue # Cannot match a group with a non-GroupMatcher
                    
                    # Rule EG-B1: If actual is a leaf, expected can be a LeafMatcher or GroupMatcher (with allow_unwrapped).
                    # If actual is a group, expected must be a GroupMatcher.
                    # If actual is a leaf and expected is a GroupMatcher: this is only allowed if allow_unwrapped is True
                    # and it's the only expected matcher. This case is handled by the initial check for non-group actuals.
                    # If we are here, it means a GroupMatcher is trying to match a leaf, which is not allowed in this context.
                    if not is_actual_group and is_expected_group_matcher:
                         continue # GroupMatcher cannot match a leaf directly here

                    # Perform the match
                    sub_result = expected_matcher.match(actual_exception)

                    if sub_result.matched:
                        # Successfully matched.
                        # EG-I1: Preserve evidence from sub-matches.
                        current_actual_path: tuple[int, ...] = ()
                        if isinstance(actual_exception, BaseExceptionGroup):
                            current_actual_path = (j,)
                        else: # It's a leaf exception
                            current_actual_path = (j,)
                        
                        for ev in sub_result.evidence:
                            all_evidence.append(ev.located(expected_index=i, actual_index=j, prefix=current_actual_path))
                        
                        possible_alternative = possible_alternative or sub_result.possible_alternative_pairing
                        
                        matched_actual_indices.add(j)
                        found_match_for_expected = True
                        break # Move to the next expected matcher

                if not found_match_for_expected:
                    # EG-B4: Failures report unmatched expected items
                    all_evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message=f"Expected matcher {i} did not match any actual exception.",
                            expected_index=i,
                            actual_index=None,
                        )
                    )
            
            # EG-B4: Failures report unexpected actual items
            for j in range(num_actual):
                if j not in matched_actual_indices:
                    # This actual exception was not matched by any expected matcher
                    current_actual_path = (j,)
                    all_evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message=f"Actual exception {j} was not matched by any expected matcher.",
                            actual_index=j,
                            actual_path=current_actual_path,
                            expected_index=None,
                        )
                    )
            
            # EG-B4: flag when another complete pairing exists.
            if all_evidence:
                return MatchResult.failure(tuple(all_evidence), possible_alternative_pairing=possible_alternative)
            else:
                # If no evidence was collected, it means all expected items were matched against actual items.
                return MatchResult.success()

        # This part should ideally not be reached if all cases are covered.
        return MatchResult.failure(
            MatchEvidence(
                code=FailureCode.UNEXPECTED_GROUP,
                message="Unexpected state during group matching.",
            )
        )
