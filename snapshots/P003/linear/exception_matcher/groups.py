from __future__ import annotations  # noqa: I001

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias
from builtins import BaseExceptionGroup
from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher

# Define a type alias for exceptions that can be matched
MatchableException: TypeAlias = BaseException | BaseExceptionGroup


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

    def match(self, actual: MatchableException) -> MatchResult:
        # EG-B1: Preserve nested group boundaries by default
        # EG-B1: Preserve nested group boundaries by default
        if not self.flatten:
            # If not flattening, we expect an ExceptionGroup to match
            if not isinstance(actual, BaseExceptionGroup):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.EXPECTED_GROUP,
                        message="Expected an ExceptionGroup",
                    )
                )
            actual_exceptions = actual.exceptions
        else:
            # EG-B2: Recursively expose leaves for matching when flatten=True
            # We need to flatten the actual exception group to get all leaf exceptions
            # and their original paths.
            actual_exceptions_with_paths = self._flatten_exceptions(actual)
            actual_exceptions = [exc for _, exc in actual_exceptions_with_paths]
            # Store paths for later use in evidence
            self._actual_paths = {i: path for i, (path, _) in enumerate(actual_exceptions_with_paths)}

        return self._match_exceptions(actual_exceptions)

    def _flatten_exceptions(self, actual: MatchableException) -> list[tuple[tuple[int, ...], BaseException]]:
        """Recursively flatten an ExceptionGroup into a list of (path, exception) tuples."""
        exceptions_with_paths = []
        if isinstance(actual, BaseExceptionGroup):
            for i, exc in enumerate(actual.exceptions):
                nested_paths = self._flatten_exceptions(exc)
                for path, sub_exc in nested_paths:
                    exceptions_with_paths.append(((i,) + path, sub_exc))
        else:
            # For a non-group exception passed directly, its path is empty.
            # This case is relevant when allow_unwrapped=True.
            exceptions_with_paths.append(((), actual))
        return exceptions_with_paths

    def _match_exceptions(self, actual_exceptions: list[BaseException]) -> MatchResult:
        """Match a sequence of expected matchers against a sequence of actual exceptions."""
        expected_matchers = list(self.expected)
        actual_indices_used = [False] * len(actual_exceptions)
        evidence: list[MatchEvidence] = []
        
        # If flatten is True, we need to use the stored paths.
        actual_paths = getattr(self, '_actual_paths', {})

        # EG-B4: Pair expected matchers with actual items in order
        for i, expected_matcher in enumerate(expected_matchers):
            matched_for_expected = False
            for j, actual_exception in enumerate(actual_exceptions):
                if not actual_indices_used[j]:
                    
                    is_actual_group = isinstance(actual_exception, BaseExceptionGroup)
                    
                    # Rule EG-B3: allow_unwrapped=True delegates a non-group exception only when there is exactly one expected matcher.
                    # If allow_unwrapped is True and there's only one expected matcher, we can match a single non-group exception.
                    if self.allow_unwrapped and len(expected_matchers) == 1 and not is_actual_group:
                        pass # Proceed to match
                    # If the actual exception is a group and we are not flattening and we have multiple expected matchers,
                    # the actual exception must be matched by a GroupMatcher.
                    elif is_actual_group and not self.flatten and len(expected_matchers) > 1 and not isinstance(expected_matcher, GroupMatcher):
                        continue # Cannot match a group with a leaf matcher when multiple expected matchers exist.
                    # If the actual exception is not a group and we are not flattening and we have multiple expected matchers,
                    # it should be matched by a LeafMatcher.
                    elif not is_actual_group and not self.flatten and len(expected_matchers) > 1 and not isinstance(expected_matcher, LeafMatcher):
                        continue # Cannot match a leaf with a group matcher when multiple expected matchers exist.
                    # If the actual exception is a group and we are not flattening and we have only one expected matcher,
                    # it should be matched by a GroupMatcher.
                    elif is_actual_group and not self.flatten and len(expected_matchers) == 1 and not isinstance(expected_matcher, GroupMatcher):
                        continue # Cannot match a group with a leaf matcher when only one expected matcher exists.
                    # If the actual exception is not a group and we are not flattening and we have only one expected matcher,
                    # it should be matched by a LeafMatcher.
                    elif not is_actual_group and not self.flatten and len(expected_matchers) == 1 and not isinstance(expected_matcher, LeafMatcher):
                        continue # Cannot match a leaf with a group matcher when only one expected matcher exists.
                    # If the actual exception is a group and we are flattening, it should be matched by a GroupMatcher.
                    elif is_actual_group and self.flatten and not isinstance(expected_matcher, GroupMatcher):
                        continue # Cannot match a group with a leaf matcher when flattening.
                    # If the actual exception is not a group and we are flattening, it should be matched by a LeafMatcher.
                    elif not is_actual_group and self.flatten and not isinstance(expected_matcher, LeafMatcher):
                        continue # Cannot match a leaf with a group matcher when flattening.
                    # If actual is a group and allow_unwrapped is True and we have multiple expected matchers,
                    # this actual exception cannot be matched by a leaf matcher.
                    elif is_actual_group and self.allow_unwrapped and len(expected_matchers) > 1:
                        continue

                    # If none of the above continue conditions were met, attempt to match.
                    match_result = expected_matcher.match(actual_exception)

                    if match_result.matched:
                        # Preserve leaf failure codes and paths (EG-I1)
                        if match_result.evidence:
                            for ev in match_result.evidence:
                                # If flatten is True, we need to include the actual path.
                                current_actual_path = actual_paths.get(j, ())
                                evidence.append(
                                    ev.located(
                                        expected_index=i,
                                        actual_index=j,
                                        prefix=current_actual_path if self.flatten else (),
                                    )
                                )
                        
                        actual_indices_used[j] = True
                        matched_for_expected = True
                        break # Move to the next expected matcher

            if not matched_for_expected:
                # EG-B4: Report unmatched expected items
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher at index {i}",
                        expected_index=i,
                    )
                )

        # EG-B4: Report unexpected actual items
        for j, actual_exception in enumerate(actual_exceptions):
            if not actual_indices_used[j]:
                # EG-I1: Include actual path in unexpected actual exceptions if flattening.
                current_actual_path = actual_paths.get(j, ())
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Unexpected actual exception at index {j}",
                        actual_index=j,
                        actual_path=current_actual_path if self.flatten else (),
                    )
                )

        # EG-B4: Flag when another complete pairing exists.
        # This is a heuristic. A more robust check might be needed for complex cases.
        possible_alternative_pairing = False
        if len(expected_matchers) == len(actual_exceptions) and not evidence:
             # Perfect match, no alternative needed.
             pass
        elif len(expected_matchers) <= len(actual_exceptions) and not evidence:
            # No failures, but more actual exceptions than expected. Could be an alternative pairing.
            possible_alternative_pairing = True
        elif len(expected_matchers) == len(actual_exceptions) and evidence:
            # Failures exist, but counts match. Might be an alternative pairing if failures are minor.
            possible_alternative_pairing = True
        elif len(expected_matchers) > len(actual_exceptions) and not evidence:
            # No failures, but fewer actual exceptions than expected. Not a complete pairing.
            pass
        elif len(expected_matchers) > len(actual_exceptions) and evidence:
            # Failures and fewer actual exceptions than expected. Unlikely to be an alternative pairing.
            pass
        # If there are failures and the number of expected matchers is less than actual exceptions,
        # it's possible that the remaining actual exceptions could form a valid group if they were
        # matched differently. This is a complex scenario. For now, we'll consider it possible.
        elif evidence and len(expected_matchers) < len(actual_exceptions):
             possible_alternative_pairing = True

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(
                *evidence,
                possible_alternative_pairing=possible_alternative_pairing,
            )
