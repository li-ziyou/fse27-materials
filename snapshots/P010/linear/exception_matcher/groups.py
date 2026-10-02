from __future__ import annotations

from collections.abc import Sequence

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher


def _flatten_exceptions(
    group: ExceptionGroup, prefix: tuple[int, ...] = ()
) -> list[tuple[BaseException, tuple[int, ...]]]:
    """Recursively flatten an ExceptionGroup into a list of (exception, path) tuples."""
    flattened = []
    for i, exc in enumerate(group.exceptions):
        path = prefix + (i,)
        if isinstance(exc, ExceptionGroup):
            flattened.extend(_flatten_exceptions(exc, path))
        else:
            flattened.append((exc, path))
    return flattened


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
            # EG-B1: GroupMatcher preserves nested group boundaries by default
            # This will be handled by recursively calling match on nested GroupMatchers
            pass
        else:
            # Handle non-group exceptions based on allow_unwrapped flag (Responsibility B)
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                return self.expected[0].match(actual)
            else:
                # If not allowed to unwrap, or more than one expected matcher, it's a mismatch
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.EXPECTED_GROUP,
                        f"expected ExceptionGroup, got {type(actual).__name__}"
                    )
                )

        # If actual is an ExceptionGroup, proceed with group matching logic
        
        if self.flatten:
            actual_items = _flatten_exceptions(actual)
        else:
            actual_items = [(exc, (i,)) for i, exc in enumerate(actual.exceptions)]

        expected_matchers = list(self.expected)
        
        matched_indices = set()
        evidence = []
        
        possible_alternative_pairing = False

        # EG-B4: Pair expected matchers with actual items in order
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, (actual_exception, actual_path) in enumerate(actual_items):
                if j in matched_indices:
                    continue

                # Recursively match nested groups if not flattening
                if not self.flatten and isinstance(actual_exception, ExceptionGroup) and isinstance(expected_matcher, GroupMatcher):
                    nested_result = expected_matcher.match(actual_exception)
                    if nested_result.matched:
                        matched_indices.add(j)
                        # Preserve nested failure evidence, adjusting path
                        for ev in nested_result.evidence:
                             evidence.append(ev.located(actual_index=j, prefix=actual_path))
                        found_match = True
                        break
                else:
                    # Match leaf exceptions
                    leaf_result = expected_matcher.match(actual_exception)
                    if leaf_result.matched:
                        matched_indices.add(j)
                        # Preserve leaf failure evidence, adjusting path
                        for ev in leaf_result.evidence:
                            # When flattening, the actual_path from _flatten_exceptions should be used
                            evidence.append(ev.located(actual_index=j, prefix=actual_path))
                        found_match = True
                        break
            
            if not found_match:
                # EG-B4: Report unmatched expected
                evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"expected matcher {i} was not matched", expected_index=i))
                # Check for possible alternative pairings if there are remaining actual exceptions
                if len(actual_items) > len(matched_indices):
                    possible_alternative_pairing = True

        # EG-B4: Report unexpected actual items
        for j, (actual_exception, actual_path) in enumerate(actual_items):
            if j not in matched_indices:
                evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"unexpected actual item {j}", actual_index=j, actual_path=actual_path))

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative_pairing
            )
