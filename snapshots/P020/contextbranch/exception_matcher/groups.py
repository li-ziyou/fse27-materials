from __future__ import annotations

from collections.abc import Sequence

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher
from .leaf import LeafMatcher


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
        if not isinstance(actual, ExceptionGroup):
            if self.allow_unwrapped:
                if len(self.expected) == 1:
                    return self.expected[0].match(actual)
                else:
                    # EG-B3: If allow_unwrapped is True, but there's more than one expected matcher,
                    # a non-group exception is still a mismatch because a group is required.
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.EXPECTED_GROUP,
                            message="Expected an exception group, but received a leaf exception.",
                        )
                    )
            else:
                # EG-B3: If allow_unwrapped is False, a non-group exception is always a mismatch.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected an exception group, but received a leaf exception.",
                    )
                )

        actual_items_to_match: list[tuple[BaseException, tuple[int, ...]]] = []
        if self.flatten:
            # EG-B2: Flatten the actual exceptions for matching.
            # We need to recursively find all leaf exceptions and their original paths.
            
            def _flatten(exc: BaseException, path: tuple[int, ...] = ()):
                if isinstance(exc, ExceptionGroup):
                    for i, sub_exc in enumerate(exc.exceptions):
                        _flatten(sub_exc, path + (i,))
                else:
                    actual_items_to_match.append((exc, path))

            _flatten(actual)
        else:
            # EG-B1: Preserve nested group boundaries.
            # Actual items are the exceptions directly within the group.
            actual_items_to_match = [(exc, actual.indexpath if hasattr(actual, "indexpath") else ()) for exc in actual.exceptions]

        # EG-B4: Pair expected matchers with actual items in order.
        # We iterate through expected matchers and try to find a corresponding actual item.
        matched_actual_indices: set[int] = set()
        result_evidence: list[MatchEvidence] = []
        
        for i, expected_matcher in enumerate(self.expected):
            found_match_for_expected = False
            for j, (actual_exception, actual_path) in enumerate(actual_items_to_match):
                if j not in matched_actual_indices:
                    # If the actual item is a group and the expected matcher is a LeafMatcher, it's a mismatch for EG-A1.
                    # If flatten is False, and the actual item is a group, we need to ensure the expected matcher
                    # is also a GroupMatcher to handle nesting.
                    if isinstance(actual_exception, ExceptionGroup) and not isinstance(expected_matcher, GroupMatcher) and not self.flatten:
                        continue # Skip this actual item, it's a group and expected is not a group matcher

                    sub_match_result = expected_matcher.match(actual_exception)
                    if sub_match_result.matched:
                        # EG-I1: Preserve leaf failure codes and add context.
                        # When a leaf matches, we need to ensure its evidence is correctly localized.
                        # If the leaf match itself produced evidence (e.g., a predicate failure within a successful type match),
                        # that evidence needs to be associated with the correct expected/actual indices and the actual path.
                        if sub_match_result.evidence:
                            for evidence in sub_match_result.evidence:
                                result_evidence.append(
                                    evidence.located(
                                        expected_index=i,
                                        actual_index=j,
                                        prefix=actual_path,
                                    )
                                )
                        # Successful leaf match with no evidence is still a match.
                        matched_actual_indices.add(j)
                        found_match_for_expected = True
                        break  # Move to the next expected matcher
                    else:
                        # Mismatch found. Collect its evidence.
                        # This evidence should be localized with the current expected and actual indices, and the actual path.
                        if sub_match_result.evidence:
                            for evidence in sub_match_result.evidence:
                                result_evidence.append(
                                    evidence.located(
                                        expected_index=i,
                                        actual_index=j,
                                        prefix=actual_path,
                                    )
                                )
                        # Continue to the next actual item to see if it matches this expected_matcher.
                        # Do NOT set found_match_for_expected = True here.
                        # Do NOT break here; continue searching for a match for this expected_matcher.

            if not found_match_for_expected:
                # EG-B4: Report unmatched expected items.
                result_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"Expected matcher {i} did not find a match.",
                        expected_index=i,
                    )
                )

        # EG-B4: Report unexpected actual items.
        for j, (actual_exception, actual_path) in enumerate(actual_items_to_match):
            if j not in matched_actual_indices:
                result_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Actual exception at index {j} was not matched.",
                        actual_index=j,
                        actual_path=actual_path,
                    )
                )

        # EG-B4: Flag when another complete pairing exists.
        # This is a complex condition to check and might require a more involved algorithm
        # to determine if a different permutation of matches would have succeeded.
        # The current implementation uses a greedy approach. If the greedy approach fails
        # to match all expected matchers, we need to determine if an alternative ordering
        # of actual exceptions could have led to a successful match.

        possible_alternative_pairing = False
        
        # A heuristic for possible_alternative_pairing:
        # If the greedy matching failed (i.e., there's at least one UNMATCHED_EXPECTED or UNEXPECTED_ACTUAL),
        # AND if the number of successfully matched actual items is less than the total number of expected matchers,
        # AND if the number of successfully matched expected items is less than the total number of actual items,
        # then it suggests a possibility of an alternative pairing.
        
        # More specifically, if there are both UNMATCHED_EXPECTED and UNEXPECTED_ACTUAL items,
        # it's a strong indicator that reordering might have worked.
        has_unmatched_expected = any(e.code == FailureCode.UNMATCHED_EXPECTED for e in result_evidence)
        has_unexpected_actual = any(e.code == FailureCode.UNEXPECTED_ACTUAL for e in result_evidence)
        
        if has_unmatched_expected and has_unexpected_actual:
            possible_alternative_pairing = True
        # Consider the case where all expected matchers were matched, but there are leftover actual items.
        # This implies that the items were present, but perhaps in a different order or some were matched incorrectly.
        # If there are no UNMATCHED_EXPECTED, but there are UNEXPECTED_ACTUAL, and the number of matched actuals
        # is less than the total number of actuals, it suggests a possible reordering.
        elif not has_unmatched_expected and has_unexpected_actual and len(matched_actual_indices) < len(actual_items_to_match):
             possible_alternative_pairing = True
        # Consider the case where all expected matchers were matched, but there are leftover actual items.
        # This implies that the items were present, but perhaps in a different order or some were matched incorrectly.
        # If there are no UNMATCHED_EXPECTED, but there are UNEXPECTED_ACTUAL, and the number of matched actuals
        # is less than the total number of actuals, it suggests a possible reordering.
        elif not has_unmatched_expected and has_unexpected_actual and len(matched_actual_indices) < len(actual_items_to_match):
             possible_alternative_pairing = True

        if result_evidence:
            return MatchResult.failure(
                *result_evidence, possible_alternative_pairing=possible_alternative_pairing
            )
        else:
            # If there's no evidence, it means all matchers found a corresponding actual item.
            # If actual_items_to_match is empty and self.expected is empty, it's a success.
            if not actual_items_to_match and not self.expected:
                return MatchResult.success()
            # If we reached here, it means no evidence was generated, but there might be
            # unmatched items if the logic above missed something.
            # For now, assume if no evidence, it's a success.
            return MatchResult.success()

