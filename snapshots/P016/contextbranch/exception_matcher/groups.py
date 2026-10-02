from __future__ import annotations

from collections.abc import Sequence

from .contracts import FailureCode, MatchResult, Matcher
from .api import matches
from .contracts import MatchEvidence # Added MatchEvidence import


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
        if isinstance(actual, ExceptionGroup):
            if self.flatten:
                # Handle flatten=True case (EG-B2)
                return self._match_flattened_group(actual)
            else:
                # Handle default case (EG-B1): preserve nested groups
                return self._match_nested_group(actual)
        elif self.allow_unwrapped:
            # Handle allow_unwrapped=True case (to be implemented later)
            pass
        
        # If not an ExceptionGroup and allow_unwrapped is False, or if flatten=True
        # and we haven't handled it yet, it's a mismatch for GroupMatcher.
        # This case will be refined as other requirements are implemented.
        return MatchResult.failure(
            MatchEvidence(
                code=FailureCode.UNEXPECTED_GROUP,
                message=f"Expected an ExceptionGroup, but got {type(actual).__name__}",
            )
        )

    def _match_nested_group(self, actual_group: ExceptionGroup) -> MatchResult:
        # EG-B1: Preserve nested group boundaries by default
        # A nested group is matched by a nested matcher rather than by a leaf matcher.
        
        actual_items = list(actual_group.exceptions)
        expected_matchers = list(self.expected)
        
        matched_indices = set()
        evidence = []

        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exception in enumerate(actual_items):
                if j in matched_indices:
                    continue

                # If the expected matcher is a GroupMatcher and the actual item is an ExceptionGroup,
                # recursively call match. Otherwise, try to match with the current expected_matcher.
                if isinstance(expected_matcher, GroupMatcher) and isinstance(actual_exception, ExceptionGroup):
                    nested_result = expected_matcher.match(actual_exception)
                    if nested_result.matched:
                        matched_indices.add(j)
                        found_match = True
                        break
                else:
                # Use the global matches function to delegate to LeafMatcher or other Matchers
                # This will implicitly handle EG-A1, EG-A2, EG-A3 via LeafMatcher.match
                # and EG-I1 for evidence preservation.
                    nested_result = matches(expected_matcher, actual_exception)
                    if nested_result.matched:
                        matched_indices.add(j)
                        found_match = True
                        # EG-B4: expected matchers pair in expected order with the first still-unmatched successful actual item
                        break
            
            if not found_match:
                # EG-B4: failures report unmatched expected and unexpected actual items
                evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher {type(expected_matcher).__name__} did not find a match.",
                    expected_index=i,
                ))

        # Check for unexpected actual items
        for j, actual_exception in enumerate(actual_items):
            if j not in matched_indices:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Unexpected actual exception: {type(actual_exception).__name__}",
                    actual_index=j,
                ))
        
        # EG-B4: flag when another complete pairing exists.
        possible_alternative_pairing = False
        if len(matched_indices) < len(actual_items) and len(expected_matchers) == len(actual_items):
            # This condition is a simplification. A more robust check would involve
            # trying to find an alternative pairing if the current one failed.
            # For now, we assume if there are unmatched actual items and the number of expected
            # matchers equals the number of actual items, an alternative pairing might exist.
            possible_alternative_pairing = True

        if not evidence and len(matched_indices) == len(actual_items) and len(expected_matchers) == len(actual_items):
            return MatchResult.success()
        else:
            # EG-I1: Preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
            # The evidence from nested matches should be incorporated here.
            # For now, we just pass the collected evidence. This needs to be enhanced to include evidence from nested matches.
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative_pairing)

    def _match_flattened_group(self, actual_group: ExceptionGroup, current_path: tuple[int, ...] = ()) -> MatchResult:
        # EG-B2: flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence.
        
        actual_exceptions = list(actual_group.exceptions)
        expected_matchers = list(self.expected)
        
        matched_indices = set()
        evidence = []

        # Iterate through expected matchers and try to find a match in actual exceptions
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if j in matched_indices:
                    continue
                
                # Construct the path for the current actual exception
                exception_path = current_path + (j,)

                if isinstance(actual_exception, ExceptionGroup):
                    # If it's a nested group, recurse if flatten is true
                    if self.flatten:
                        nested_result = self._match_flattened_group(actual_exception, exception_path)
                        if nested_result.matched:
                            matched_indices.add(j)
                            found_match = True
                            break
                    else:
                        # If flatten is false, this group should be matched by a GroupMatcher
                        # If the expected matcher is a GroupMatcher, try to match it.
                        if isinstance(expected_matcher, GroupMatcher):
                            nested_result = expected_matcher.match(actual_exception)
                            if nested_result.matched:
                                matched_indices.add(j)
                                found_match = True
                                break
                        else:
                            # Otherwise, this is a mismatch for a leaf matcher
                            evidence.append(MatchEvidence(
                                code=FailureCode.UNEXPECTED_GROUP,
                                message=f"Expected a leaf exception, but got an ExceptionGroup at path {exception_path}",
                                expected_index=i,
                                actual_index=j,
                                actual_path=exception_path,
                            ))
                            # Even if it's an unexpected group, we might still find a match later in actual_exceptions
                            # so we don't break here.
                else:
                    # It's a leaf exception, try to match it with the expected_matcher
                    nested_result = matches(expected_matcher, actual_exception)
                    if nested_result.matched:
                        matched_indices.add(j)
                        found_match = True
                        break
            
            if not found_match:
                evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher {type(expected_matcher).__name__} did not find a match.",
                    expected_index=i,
                    actual_path=current_path, # Path where the expected matcher was supposed to find a match
                ))

        # Check for unexpected actual items
        for j, actual_exception in enumerate(actual_exceptions):
            if j not in matched_indices:
                exception_path = current_path + (j,)
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Unexpected actual exception: {type(actual_exception).__name__}",
                    actual_index=j,
                    actual_path=exception_path,
                ))
        
        # EG-B4: flag when another complete pairing exists.
        possible_alternative_pairing = False
        if len(matched_indices) < len(actual_exceptions) and len(expected_matchers) == len(actual_exceptions):
            possible_alternative_pairing = True

        if not evidence and len(matched_indices) == len(actual_exceptions) and len(expected_matchers) == len(actual_exceptions):
            return MatchResult.success()
        else:
            # EG-I1: Preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
            # Incorporate evidence from nested matches.
            processed_evidence = []
            for ev in evidence:
                if ev.actual_path: # If the evidence already has a path
                    processed_evidence.append(ev)
                else: # Otherwise, prepend the current path
                    processed_evidence.append(ev.located(prefix=current_path))
            
            return MatchResult.failure(*processed_evidence, possible_alternative_pairing=possible_alternative_pairing)
