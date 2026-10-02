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
        # EG-B1: Preserve nested group boundaries by default
        # Actual must be an exception group
        if not isinstance(actual, BaseExceptionGroup):
            # EG-B3: allow_unwrapped mode - delegate non-group only with exactly one matcher
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                result = self.expected[0].match(actual)
                return result
            else:
                # Either not allow_unwrapped, or multiple matchers require a group
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.EXPECTED_GROUP,
                        message="expected an exception group",
                    )
                )
        
        # EG-B2: Flatten mode - recursively expose leaves with index paths
        if self.flatten:
            return self._match_flattened(actual)
        
        # B1: Default mode - preserve nested group boundaries
        return self._match_nested(actual)
    
    def _flatten_exceptions(self, exceptions: tuple[BaseException, ...], prefix: tuple[int, ...] = ()) -> list[tuple[BaseException, tuple[int, ...]]]:
        """EG-B2: Recursively flatten exceptions, retaining their index paths."""
        flattened = []
        for idx, exc in enumerate(exceptions):
            current_path = prefix + (idx,)
            if isinstance(exc, BaseExceptionGroup):
                # Recursively flatten nested groups
                flattened.extend(self._flatten_exceptions(exc.exceptions, current_path))
            else:
                # Leaf exception - add with its path
                flattened.append((exc, current_path))
        return flattened
    
    def _match_flattened(self, actual: BaseExceptionGroup) -> MatchResult:
        """EG-B2: Match against flattened leaves with retained paths."""
        flattened = self._flatten_exceptions(actual.exceptions)
        expected_matchers = self.expected
        
        evidence = []
        matched_actual_indices = set()
        
        # Try to match each expected matcher in order
        for expected_idx, expected_matcher in enumerate(expected_matchers):
            matched = False
            
            # Find the first unmatched actual exception that matches
            for flat_idx, (actual_exception, actual_path) in enumerate(flattened):
                if flat_idx in matched_actual_indices:
                    continue
                
                # Try to match
                result = expected_matcher.match(actual_exception)
                if result.matched:
                    matched_actual_indices.add(flat_idx)
                    matched = True
                    break
                else:
                    # Preserve failure evidence with path information
                    for ev in result.evidence:
                        evidence.append(
                            ev.located(
                                expected_index=expected_idx,
                                actual_index=flat_idx,
                                prefix=actual_path,
                            )
                        )
            
            if not matched:
                # This expected matcher couldn't be matched
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"no matching exception for expected matcher {expected_idx}",
                        expected_index=expected_idx,
                    )
                )
        
        # Check for unexpected actual exceptions
        for flat_idx, (actual_exception, actual_path) in enumerate(flattened):
            if flat_idx not in matched_actual_indices:
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"unexpected exception at index {flat_idx}",
                        actual_index=flat_idx,
                        actual_path=actual_path,
                    )
                )
        
        if evidence:
            # EG-B4: Check if a complete pairing exists with different ordering
            possible_alternative = self._check_alternative_pairing(flattened)
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative)
        
        return MatchResult.success()
    
    def _match_nested(self, actual: BaseExceptionGroup) -> MatchResult:
        """B1: Match with nested group boundaries preserved."""
        actual_exceptions = actual.exceptions
        expected_matchers = self.expected
        
        evidence = []
        matched_actual_indices = set()
        
        # Try to match each expected matcher in order
        for expected_idx, expected_matcher in enumerate(expected_matchers):
            matched = False
            
            # Find the first unmatched actual exception that matches
            for actual_idx, actual_exception in enumerate(actual_exceptions):
                if actual_idx in matched_actual_indices:
                    continue
                
                # Try to match
                result = expected_matcher.match(actual_exception)
                if result.matched:
                    matched_actual_indices.add(actual_idx)
                    matched = True
                    break
            
            if not matched:
                # This expected matcher couldn't be matched
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"no matching exception for expected matcher {expected_idx}",
                        expected_index=expected_idx,
                    )
                )
        
        # Check for unexpected actual exceptions
        for actual_idx, actual_exception in enumerate(actual_exceptions):
            if actual_idx not in matched_actual_indices:
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"unexpected exception at index {actual_idx}",
                        actual_index=actual_idx,
                    )
                )
        
        if evidence:
            # EG-B4: Check if a complete pairing exists with different ordering
            possible_alternative = self._check_alternative_pairing(actual_exceptions)
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative)
        
        return MatchResult.success()
    
    def _check_alternative_pairing(self, actual_items) -> bool:
        """EG-B4: Check if a complete pairing exists with different ordering."""
        # Try all permutations to see if there's a valid complete pairing
        from itertools import permutations
        
        expected_matchers = self.expected
        
        # If counts don't match, no complete pairing possible
        if len(actual_items) != len(expected_matchers):
            return False
        
        # Try each permutation of actual items
        for perm in permutations(range(len(actual_items))):
            all_matched = True
            for expected_idx, expected_matcher in enumerate(expected_matchers):
                actual_idx = perm[expected_idx]
                actual_item = actual_items[actual_idx]
                
                # Extract the actual exception if it's a tuple (from flattened)
                if isinstance(actual_item, tuple):
                    actual_exception = actual_item[0]
                else:
                    actual_exception = actual_item
                
                result = expected_matcher.match(actual_exception)
                if not result.matched:
                    all_matched = False
                    break
            
            if all_matched:
                return True
        
        return False
