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
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                return self.expected[0].match(actual)
            return MatchResult.failure(
                MatchEvidence(FailureCode.EXPECTED_GROUP, "expected an exception group")
            )
        
        return self._match_flattened(actual) if self.flatten else self._match_nested(actual)
    
    def _match_nested(self, actual: BaseExceptionGroup) -> MatchResult:
        used_actual_indices = self._pair_matchers(actual.exceptions)
        evidence = self._build_evidence(self.expected, actual.exceptions, used_actual_indices)
        
        if evidence:
            alt_pairing_exists = self._has_alternative_pairing(self.expected, actual.exceptions)
            return MatchResult.failure(*evidence, possible_alternative_pairing=alt_pairing_exists)
        return MatchResult.success()
    
    def _match_flattened(self, actual: BaseExceptionGroup) -> MatchResult:
        leaves_with_paths = self._flatten_exceptions(actual)
        leaf_exceptions = [exc for exc, _ in leaves_with_paths]
        used_leaf_indices = self._pair_matchers(leaf_exceptions)
        evidence = self._build_flattened_evidence(self.expected, leaves_with_paths, used_leaf_indices)
        
        if evidence:
            alt_pairing_exists = self._has_alternative_pairing(self.expected, leaf_exceptions)
            return MatchResult.failure(*evidence, possible_alternative_pairing=alt_pairing_exists)
        return MatchResult.success()
    
    def _pair_matchers(self, actual_excs: list[BaseException]) -> list[bool]:
        used = [False] * len(actual_excs)
        for expected_matcher in self.expected:
            for act_idx, actual_exc in enumerate(actual_excs):
                if not used[act_idx] and expected_matcher.match(actual_exc).matched:
                    used[act_idx] = True
                    break
        return used
    
    def _build_evidence(self, expected: tuple[Matcher, ...], actual: tuple[BaseException, ...], used: list[bool]) -> list[MatchEvidence]:
        evidence = []
        
        for exp_idx, expected_matcher in enumerate(expected):
            matched_actual = False
            for act_idx, actual_exc in enumerate(actual):
                if used[act_idx] and expected_matcher.match(actual_exc).matched:
                    matched_actual = True
                    break
            
            if not matched_actual:
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"expected {expected_matcher}", expected_index=exp_idx))
        
        for act_idx, actual_exc in enumerate(actual):
            if not used[act_idx]:
                evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"unexpected {actual_exc}", actual_index=act_idx))
        
        return evidence
    
    def _build_flattened_evidence(self, expected: tuple[Matcher, ...], leaves_with_paths: list[tuple[BaseException, tuple[int, ...]]], used: list[bool]) -> list[MatchEvidence]:
        evidence = []
        leaf_exceptions = [exc for exc, _ in leaves_with_paths]
        
        for exp_idx, expected_matcher in enumerate(expected):
            matched_leaf_idx = -1
            for leaf_idx, (leaf_exc, leaf_path) in enumerate(leaves_with_paths):
                if not used[leaf_idx] and expected_matcher.match(leaf_exc).matched:
                    matched_leaf_idx = leaf_idx
                    break
            
            if matched_leaf_idx != -1:
                used[matched_leaf_idx] = True
            else:
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"expected {expected_matcher}", expected_index=exp_idx))
        
        for leaf_idx, (leaf_exc, leaf_path) in enumerate(leaves_with_paths):
            if not used[leaf_idx]:
                evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"unexpected {leaf_exc}", actual_index=leaf_idx, actual_path=leaf_path))
        
        return evidence

    def _flatten_exceptions(self, actual: BaseExceptionGroup) -> list[tuple[BaseException, tuple[int, ...]]]:
        leaves = []
        for i, exc in enumerate(actual.exceptions):
            if isinstance(exc, BaseExceptionGroup):
                nested_leaves = self._flatten_exceptions(exc)
                for leaf, path in nested_leaves:
                    leaves.append((leaf, (i,) + path))
            else:
                leaves.append((exc, (i,)))
        return leaves

    def _has_alternative_pairing(self, expected: tuple[Matcher, ...], actual: list[BaseException]) -> bool:
        # This is a simplified check for alternative pairings. A more robust solution would involve a bipartite matching algorithm.
        # For now, we check if there are any unused actual exceptions that could potentially match an unused expected matcher.
        
        # Create copies to avoid modifying original lists during the check
        remaining_expected = list(expected)
        remaining_actual = list(actual)
        
        used_actual_indices_for_alt_check = [False] * len(remaining_actual)
        
        for exp_idx, exp_matcher in enumerate(remaining_expected):
            found_match = False
            for act_idx, act_exc in enumerate(remaining_actual):
                if not used_actual_indices_for_alt_check[act_idx]:
                    if exp_matcher.match(act_exc).matched:
                        used_actual_indices_for_alt_check[act_idx] = True
                        found_match = True
                        break
            if not found_match:
                # If an expected matcher cannot find any match, then no alternative pairing is possible with this set of remaining items
                return False
        
        # If all expected matchers found a match, it means the original pairing was successful,
        # but we are here to check for *alternative* pairings. If all items were consumed,
        # and there were no other possibilities, then there isn't an alternative.
        # This is a heuristic, not a definitive check for all cases.
        return not all(used_actual_indices_for_alt_check)
