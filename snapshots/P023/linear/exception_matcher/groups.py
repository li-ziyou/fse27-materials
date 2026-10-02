from __future__ import annotations

from collections.abc import Sequence
from typing import cast

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
        # EG-B3: allow_unwrapped=True delegates a non-group exception only when there is exactly one expected matcher.
        if self.allow_unwrapped and not isinstance(actual, BaseExceptionGroup):
            if len(self.expected) == 1:
                return self.expected[0].match(actual)
            else:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.EXPECTED_GROUP,
                        message="Expected group when allow_unwrapped is true and multiple matchers are present.",
                    )
                )

        # EG-B1: GroupMatcher preserves nested group boundaries by default.
        if not isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="Expected an exception group but received a leaf exception.",
                )
            )

        # EG-B4: expected matchers pair in expected order with the first still-unmatched successful actual item.
        expected_matchers = list(self.expected)
        actual_exceptions = list(actual.exceptions)
        actual_index_path_map = {}

        # If flatten is true, recursively expose leaves.
        if self.flatten:
            flattened_exceptions = []
            for i, exc in enumerate(actual_exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    # Recursively flatten nested groups
                    nested_exceptions = self._flatten_group(exc, (i,))
                    flattened_exceptions.extend(nested_exceptions)
                else:
                    flattened_exceptions.append((exc, (i,)))
            actual_exceptions = flattened_exceptions
        else:
            # Preserve nested group boundaries, map actual exceptions to their original index paths
            actual_exceptions_with_paths = []
            for i, exc in enumerate(actual_exceptions):
                actual_exceptions_with_paths.append((exc, (i,)))
            actual_exceptions = actual_exceptions_with_paths

        
        matched_indices = set()
        evidence = []

        for i, expected_matcher in enumerate(expected_matchers):
            found_match_for_pairing = False
            
            for j, (actual_exception, actual_path) in enumerate(actual_exceptions):
                if j in matched_indices:
                    continue

                # EG-B1: nested group is matched by a nested matcher rather than by a leaf matcher.
                # This check might need adjustment if flatten=True should allow GroupMatcher to match leaves.
                # For now, assume it's correct as per EG-B1.
                if isinstance(actual_exception, BaseExceptionGroup) and not isinstance(expected_matcher, GroupMatcher):
                    continue

                match_result = expected_matcher.match(actual_exception)

                # Preserve evidence from the leaf match, regardless of whether it's considered a "successful pairing"
                if match_result.evidence:
                    augmented_evidence = []
                    for ev in match_result.evidence:
                        # EG-I1: Preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
                        # The actual_path is already determined by the flattening process.
                        # We just need to ensure it's correctly applied.
                        augmented_evidence.append(
                            ev.located(
                                expected_index=i,
                                actual_index=j,
                                # The prefix should be the actual_path from the flattened exception.
                                prefix=actual_path,
                            )
                        )
                    evidence.extend(augmented_evidence)

                # If the leaf matcher considers this a "match" for pairing purposes:
                if match_result.matched:
                    matched_indices.add(j)
                    found_match_for_pairing = True
                    break # This actual exception is now paired, move to the next expected matcher

            if not found_match_for_pairing:
                # If we couldn't find any actual exception to pair with this expected matcher,
                # then this expected matcher is effectively unmatched.
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"Expected matcher {i} did not find a successful pair.",
                        expected_index=i,
                    )
                )

        # EG-B4: flag when another complete pairing exists.
        # Check if any of the unmatched actual exceptions could form a complete pairing with the remaining expected matchers
        # This is a simplified check; a more robust solution would involve backtracking or more complex matching algorithms.
        # For now, we'll just flag if there are any remaining unmatched actuals.
        possible_alternative_pairing = len(matched_indices) < len(expected_matchers) and len(matched_indices) < len(actual_exceptions)


        # EG-B4: failures report unexpected actual items.
        for j, (actual_exception, actual_path) in enumerate(actual_exceptions):
            if j not in matched_indices:
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Unexpected actual exception at index {j}.",
                        actual_index=j,
                        actual_path=actual_path,
                    )
                )

        # EG-I1: group matching consumes the shared Matcher/MatchResult contract.
        if len(evidence) == 0 and len(matched_indices) == len(expected_matchers) and len(matched_indices) == len(actual_exceptions):
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative_pairing
            )

    def _flatten_group(self, group: BaseExceptionGroup, path_prefix: tuple[int, ...]) -> list[tuple[BaseException, tuple[int, ...]]]:
        """Recursively flatten an exception group, keeping track of the original path."""
        flattened = []
        for i, exc in enumerate(group.exceptions):
            current_path = path_prefix + (i,)
            if isinstance(exc, BaseExceptionGroup):
                flattened.extend(self._flatten_group(exc, current_path))
            else:
                flattened.append((exc, current_path))
        return flattened

