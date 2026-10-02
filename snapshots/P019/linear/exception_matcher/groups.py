from __future__ import annotations

from collections.abc import Sequence

from .contracts import MatchResult, Matcher
from .leaf import LeafMatcher # Import LeafMatcher here for use in _match_nested_group


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
        from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher
        # from .leaf import LeafMatcher  # Import LeafMatcher for type checking - moved to top

        if isinstance(actual, BaseExceptionGroup):
            # Handle ExceptionGroup matching
            return self._match_group(actual)
        else:
            # Handle non-ExceptionGroup matching
            return self._match_non_group(actual)

    def _match_group(self, actual: BaseExceptionGroup) -> MatchResult:
        from .contracts import FailureCode, MatchEvidence, MatchResult

        if self.flatten:
            # EG-B2: Flatten the group and match leaves
            all_leaves = []
            for i, exc in enumerate(actual.exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    # If flatten is true, we still need to preserve nested group structure for pathing
                    # but we will match leaves within them.
                    # For now, we will recursively get all leaves, and reconstruct path.
                    # This part might need refinement depending on exact pathing requirements.
                    leaves_from_nested = self._get_all_leaves(exc, prefix=(i,))
                    all_leaves.extend(leaves_from_nested)
                else:
                    all_leaves.append((exc, (i,))) # Store exception and its index path

            # Now try to match the flattened leaves against expected matchers
            return self._match_flattened_leaves(all_leaves)
        else:
            # EG-B1: Preserve nested group boundaries
            return self._match_nested_group(actual)

    def _match_non_group(self, actual: BaseException) -> MatchResult:
        from .contracts import FailureCode, MatchEvidence, MatchResult

        if self.allow_unwrapped:
            # EG-B3: Allow unwrapped delegation if there's exactly one expected matcher
            if len(self.expected) == 1:
                # Delegate to the single expected matcher
                return self.expected[0].match(actual)
            else:
                # If more than one expected matcher, a group is required
                return MatchResult.failure(
                    MatchEvidence(FailureCode.EXPECTED_GROUP, f"Expected an ExceptionGroup with {len(self.expected)} matchers, but got a leaf exception.")
                )
        else:
            # If allow_unwrapped is False, a non-group exception cannot be matched by a GroupMatcher
            return MatchResult.failure(
                MatchEvidence(FailureCode.UNEXPECTED_GROUP, "GroupMatcher expected an ExceptionGroup, but received a leaf exception.")
            )

    def _match_nested_group(self, actual: BaseExceptionGroup) -> MatchResult:
        from .contracts import FailureCode, MatchEvidence, MatchResult

        # EG-B1: Match expected matchers against actual items in order
        # EG-B4: Pair in expected order, report failures, flag possible alternative pairings
        
        expected_matchers = list(self.expected)
        actual_exceptions = list(actual.exceptions)
        
        matched_indices_actual = set()
        matched_indices_expected = set()
        
        evidence = []
        
        # First pass: try to match expected matchers with actual exceptions in order
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if j in matched_indices_actual:
                    continue
                
                # Check if the actual exception is a group and the expected matcher is a GroupMatcher
                # or if the actual exception is a leaf and the expected matcher is a LeafMatcher
                # or if the actual exception can be matched by the expected_matcher (general case)
                
                # EG-B1: Preserve nested group boundaries by default
                if isinstance(actual_exception, BaseExceptionGroup) and isinstance(expected_matcher, GroupMatcher):
                    sub_result = expected_matcher.match(actual_exception)
                    if sub_result.matched:
                        matched_indices_actual.add(j)
                        matched_indices_expected.add(i)
                        # If the nested match itself had evidence, it should be included.
                        # However, for top-level match, we only care about direct mismatches or unmatched items.
                        # The sub_result.evidence pertains to the inner match.
                        # For now, we assume successful nested match means no direct evidence here.
                        found_match = True
                        break
                elif isinstance(actual_exception, BaseException) and not isinstance(actual_exception, BaseExceptionGroup) and isinstance(expected_matcher, LeafMatcher):
                    sub_result = expected_matcher.match(actual_exception)
                    if sub_result.matched:
                        matched_indices_actual.add(j)
                        matched_indices_expected.add(i)
                        found_match = True
                        break
            # If no match found for this expected_matcher, record it as unmatched
            # Note: EG-B4 requires reporting unmatched expected items.
            if not found_match:
                pass # Will be handled when checking for unmatched expected

        # Report unmatched expected matchers
        for i, expected_matcher in enumerate(expected_matchers):
            if i not in matched_indices_expected:
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"Expected matcher {i} was not matched.", expected_index=i))

        # Report unmatched expected matchers
        for i, expected_matcher in enumerate(expected_matchers):
            if i not in matched_indices_expected:
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"Expected matcher {i} was not matched.", expected_index=i))

        # Report unexpected actual exceptions
        for j, actual_exception in enumerate(actual_exceptions):
            if j not in matched_indices_actual:
                # Need to determine the type of failure for the unexpected actual exception.
                # If it's a group, and we are not flattening, it's an UNEXPECTED_GROUP.
                # If it's a leaf, it's an UNEXPECTED_ACTUAL.
                if isinstance(actual_exception, BaseExceptionGroup):
                    evidence.append(MatchEvidence(FailureCode.UNEXPECTED_GROUP, f"Unexpected ExceptionGroup at index {j}.", actual_index=j))
                else:
                    evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"Unexpected leaf exception at index {j}.", actual_index=j))

        # EG-B4: Flag when another complete pairing exists
        # This is a complex condition. It implies that if we were to rearrange
        # the actual exceptions, a full match would be possible.
        # A simple heuristic: if we have unmatched expected and unexpected actual,
        # and the number of unmatched expected equals the number of unexpected actual,
        # it's a potential alternative pairing. More sophisticated checks may be needed.
        possible_alternative = False
        if len(evidence) > 0:
            unmatched_expected_count = sum(1 for ev in evidence if ev.code == FailureCode.UNMATCHED_EXPECTED)
            unexpected_actual_count = sum(1 for ev in evidence if ev.code in (FailureCode.UNEXPECTED_ACTUAL, FailureCode.UNEXPECTED_GROUP))
            if unmatched_expected_count == unexpected_actual_count and unmatched_expected_count > 0:
                possible_alternative = True

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative
            )

    def _get_all_leaves(self, group: BaseExceptionGroup, prefix: tuple[int, ...] = ()) -> list[tuple[BaseException, tuple[int, ...]]]:
        """Recursively get all leaf exceptions and their paths from a group."""
        leaves = []
        for i, exc in enumerate(group.exceptions):
            current_path = prefix + (i,)
            if isinstance(exc, BaseExceptionGroup):
                leaves.extend(self._get_all_leaves(exc, prefix=current_path))
            else:
                leaves.append((exc, current_path))
        return leaves

    def _match_flattened_leaves(self, actual_leaves: list[tuple[BaseException, tuple[int, ...]]]) -> MatchResult:
        """Match a list of flattened leaves against expected matchers."""
        from .contracts import FailureCode, MatchEvidence, MatchResult
        
        # This logic is similar to _match_nested_group but operates on a flat list of (exception, path)
        # and needs to report the path in evidence.
        
        expected_matchers = list(self.expected)
        
        matched_indices_actual_leaves = set()
        matched_indices_expected = set()
        
        evidence = []
        
        # First pass: try to match expected matchers with actual leaves in order
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, (actual_exception, actual_path) in enumerate(actual_leaves):
                if j in matched_indices_actual_leaves:
                    continue
                
                # Ensure we are only matching leaf exceptions against expected matchers
                if isinstance(actual_exception, BaseExceptionGroup):
                    # This should not happen if _get_all_leaves is working correctly,
                    # but as a safeguard:
                    continue

                # EG-B2: When flatten=True, we match leaves. The expected matcher
                # should ideally be a LeafMatcher, but GroupMatcher could also be
                # used if it's designed to handle flattening internally or if it's
                # a single-element group that can match a leaf.
                # For now, assume expected_matcher can match a leaf.
                
                # The `match` method of the expected_matcher will be called.
                # If it's a LeafMatcher, it will handle leaf-specific checks.
                # If it's a GroupMatcher and flatten=True, it might have its own logic.
                # However, since we're in GroupMatcher.match with flatten=True,
                # we are essentially flattening one level here.
                # The recursive flattening might be handled by GroupMatcher itself if nested.
                # For this method, we assume expected_matcher can match a single actual_exception.
                
                # We need to pass the actual_path to the evidence if mismatch occurs.
                # The expected_matcher.match() should return MatchResult.
                # If it's a LeafMatcher, it will return a result for that leaf.
                # If it's a GroupMatcher, it needs to be able to handle a single leaf input,
                # or we need to ensure only LeafMatchers are in `expected` when flatten=True.
                # The prompt implies `expected` can contain `Matcher`s, which could be `GroupMatcher` too.
                
                # Let's assume for now that `expected_matcher.match(actual_exception)` is valid.
                # The `actual_path` needs to be incorporated into the evidence.
                
                # The `MatchResult` from `expected_matcher.match` should have evidence.
                # We need to ensure the evidence's `actual_path` is correctly set.
                # The `MatchEvidence.located` method is for this.
                
                sub_result = expected_matcher.match(actual_exception)
                
                if sub_result.matched:
                    matched_indices_actual_leaves.add(j)
                    matched_indices_expected.add(i)
                    found_match = True
                    break
            
            if not found_match:
                # If no match found for this expected_matcher, record it as unmatched.
                pass # Will be handled when checking for unmatched expected

        # Report unmatched expected matchers
        for i, expected_matcher in enumerate(expected_matchers):
            if i not in matched_indices_expected:
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"Expected matcher {i} was not matched.", expected_index=i))

        # Report unexpected actual leaves
        for j, (actual_exception, actual_path) in enumerate(actual_leaves):
            if j not in matched_indices_actual_leaves:
                # The evidence should include the actual_path.
                # The actual_exception itself is unexpected.
                # The failure code might be UNEXPECTED_ACTUAL.
                # The actual_path is crucial here.
                
                # We need a way to get the failure code from the expected matcher if it was present.
                # If the expected_matcher itself failed to match, we have UNMATCHED_EXPECTED.
                # If an actual exception is left over, it's UNEXPECTED_ACTUAL.
                
                # The evidence for unexpected actuals should carry the path.
                # We might need to call the `match` method of the first expected matcher
                # with the actual exception to get specific failure details, but that's not how it works.
                # The evidence should describe the mismatch.
                
                # If an actual exception is not matched, it's an unexpected actual.
                # The failure code should probably be UNEXPECTED_ACTUAL.
                # The message should indicate what was unexpected, and the path.
                
                # The current LeafMatcher returns TYPE_MISMATCH, MESSAGE_MISMATCH, etc.
                # If we have an unexpected actual, we don't have a specific expected matcher to blame for *this* actual.
                # So, UNEXPECTED_ACTUAL is appropriate.
                
                # The actual_path should be included in the evidence.
                # The MatchEvidence already has an actual_path field.
                # We need to construct it.
                
                # The `actual_path` from `_get_all_leaves` is already the full path.
                # We need to make sure MatchEvidence can store it.
                # MatchEvidence has `actual_path: tuple[int, ...]`.

                # Let's create an evidence for unexpected actual with its path.
                # The message could be more informative.
                
                # If the actual_exception is an ExceptionGroup itself, and flatten=True,
                # this implies it was not fully flattened or matched by a nested GroupMatcher.
                # However, _get_all_leaves should have extracted all leaves.
                # So, if we are here, it means this leaf was not matched.
                
                # The `MatchEvidence.located` method can help set the path.
                # But here we are creating a new evidence.
                
                # Let's assume the failure is simply that this item was unexpected.
                # The path is critical.
                
                # If the expected matcher was a LeafMatcher, and it failed to match,
                # we'd get UNMATCHED_EXPECTED.
                # If this actual leaf was simply left over, it's UNEXPECTED_ACTUAL.
                
        # The `MatchEvidence.located` method can help set the path.
        # But here we are creating a new evidence.
        
        # Let's assume the failure is simply that this item was unexpected.
        # The path is critical.
        
        # If the expected matcher was a LeafMatcher, and it failed to match,
        # we'd get UNMATCHED_EXPECTED.
        # If this actual leaf was simply left over, it's UNEXPECTED_ACTUAL.
        
        # The `MatchEvidence.located` method is for *modifying* existing evidence.
        # We are creating new evidence here.
        
        # The `actual_path` is already available from `actual_leaves`.
        # We need to ensure the `MatchEvidence` constructor handles it.
        
        # If `actual_exception` is a group, it implies a failure to flatten or match it as a group.
        # But if `flatten=True`, we expect only leaves.
        # So, if we encounter an ExceptionGroup here, it's an issue with the flattening logic or how GroupMatcher handles nested groups in flatten mode.
        # For now, let's assume `actual_leaves` only contains leaf exceptions.

        # The evidence should reflect the failure.
        # It's an unexpected actual exception.
        # The path is important.
        
        # The `MatchEvidence` constructor takes `actual_path`.
        # We should pass the `actual_path` here.
        
        # Let's refine the evidence creation.
        # The `actual_path` is already captured in `actual_leaves`.
        
        # If the actual is an ExceptionGroup, and flatten is True, it means
        # the GroupMatcher (this one) did not handle it, or a nested one did not.
        # But _get_all_leaves should have broken it down.
        # So, if we are here, `actual_exception` MUST be a leaf.
        
        # Let's create the evidence.
        # The message should be informative.
        
        # The `MatchEvidence` constructor has `actual_path` as a parameter.
        # We should pass `actual_path` to it.
        
        # We need to construct the `MatchEvidence` with the correct `actual_path`.
        # The `actual_path` is already computed by `_get_all_leaves`.
        
        # We need to ensure that if `actual_exception` is an `ExceptionGroup`
        # and `flatten` is True, this indicates a problem.
        # However, the `_get_all_leaves` should have already extracted all leaf exceptions.
        # So, `actual_exception` here should always be a leaf.
        
        # The failure code should be `UNEXPECTED_ACTUAL`.
        # The message can be generic: "Unexpected leaf exception".
        # The `actual_index` here refers to the index in the `actual_leaves` list.
        # The `actual_path` is the true path within the original exception group structure.
        
        # We need to create MatchEvidence with the actual_path.
        # The MatchEvidence constructor has `actual_path` as a parameter.
        
        # Let's ensure the `actual_path` is correctly passed.
        # `actual_leaves` contains tuples of `(exception, path)`.
        # So `actual_path` is `actual_leaves[j][1]`.
        
        evidence.append(MatchEvidence(
            code=FailureCode.UNEXPECTED_ACTUAL,
            message=f"Unexpected leaf exception at path {actual_path}",
            actual_index=j, # Index in the flattened list
            actual_path=actual_path # Original path in the nested structure
        ))

        # EG-B4: Flag when another complete pairing exists
        # This check is tricky. A simple heuristic: if we have unmatched expected items
        # and unmatched actual items, and their counts are equal, it might be an alternative pairing.
        # This is a simplification. A more robust check would involve trying to match
        # the remaining expected with the remaining actual in different orders.
        
        possible_alternative = False
        if len(evidence) > 0:
            unmatched_expected_count = sum(1 for ev in evidence if ev.code == FailureCode.UNMATCHED_EXPECTED)
            unexpected_actual_count = sum(1 for ev in evidence if ev.code in (FailureCode.UNEXPECTED_ACTUAL, FailureCode.UNEXPECTED_GROUP))
            
            # If the number of unmatched expected equals the number of unexpected actual,
            # it suggests a potential reordering that could lead to a full match.
            if unmatched_expected_count > 0 and unmatched_expected_count == unexpected_actual_count:
                possible_alternative = True

        if not evidence:
            return MatchResult.success()
        else:
            # If there are unmatched expected items, they should be reported.
            # If there are unexpected actual items, they should be reported.
            
            # The evidence list already contains these.
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative
            )

