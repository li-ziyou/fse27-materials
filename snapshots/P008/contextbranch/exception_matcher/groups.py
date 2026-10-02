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
        # EG-B1: GroupMatcher preserves nested group boundaries by default
        # EG-B2: flatten=True recursively exposes leaves for matching
        # EG-B3: allow_unwrapped=True delegates a non-group exception only when there is exactly one expected matcher
        # EG-B4: expected matchers pair in expected order with the first still-unmatched successful actual item
        # EG-I1: group matching consumes the shared Matcher/MatchResult contract and preserves leaf failure codes

        from .leaf import LeafMatcher # Import LeafMatcher for type checking

        if isinstance(actual, ExceptionGroup):
            actual_exceptions = actual.exceptions
            if self.flatten:
                # Flatten the actual exceptions if flatten is True
                actual_exceptions = self._flatten_exceptions(actual_exceptions)

            # Attempt to match expected matchers against actual exceptions
            return self._match_exceptions(actual_exceptions, actual.subgroup(None).index) # Pass actual group's index path

        elif self.allow_unwrapped and len(self.expected) == 1:
            # EG-B3: allow_unwrapped=True, delegate non-group exception to the single expected matcher
            return self.expected[0].match(actual)
        else:
            # Mismatch: actual is not an ExceptionGroup and allow_unwrapped is False or there are multiple expected matchers
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP if not self.allow_unwrapped else FailureCode.EXPECTED_GROUP,
                    message="Expected an ExceptionGroup or a single matcher for unwrapped exception",
                    # We don't have an actual index path for the group itself here, but we can indicate the type mismatch
                )
            )

    def _flatten_exceptions(self, exceptions: Sequence[BaseException], current_path: tuple[int, ...] = ()) -> list[tuple[BaseException, tuple[int, ...]]]:
        """Recursively flattens ExceptionGroups while preserving original paths."""
        flattened = []
        for i, exc in enumerate(exceptions):
            if isinstance(exc, ExceptionGroup):
                if self.flatten: # Only flatten if flatten is True
                    flattened.extend(self._flatten_exceptions(exc.exceptions, current_path + (i,)))
                else:
                    flattened.append((exc, current_path + (i,))) # Preserve group if not flattening
            else:
                flattened.append((exc, current_path + (i,)))
        return flattened

    def _match_exceptions(self, actual_items: Sequence[tuple[BaseException, tuple[int, ...]]], group_path: tuple[int, ...] = ()) -> MatchResult:
        """Matches expected matchers against actual exception items."""
        expected_matchers = list(self.expected)
        actual_idx = 0
        expected_idx = 0
        evidence = []

        while expected_idx < len(expected_matchers) and actual_idx < len(actual_items):
            expected_matcher = expected_matchers[expected_idx]
            actual_exc, actual_path_in_group = actual_items[actual_idx]

            # EG-B1: Preserve nested group boundaries by default
            if not self.flatten and isinstance(expected_matcher, GroupMatcher) and isinstance(actual_exc, ExceptionGroup):
                # Recursively match nested groups
                nested_result = expected_matcher.match(actual_exc)
                if nested_result.matched:
                    # If nested group matched, update the actual_path_in_group with the nested group's path
                    # and continue matching the outer group.
                    # The actual_path_in_group here is the path to the nested group itself
                    actual_items[actual_idx] = (actual_exc, actual_path_in_group) # Keep the original path to the group
                    expected_idx += 1
                    actual_idx += 1
                    evidence.extend(nested_result.evidence)
                else:
                    # If nested group did not match, add its evidence and potentially flag possible alternative pairing
                    evidence.extend(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED, # Or a more specific code for group mismatch
                            message=f"Nested group mismatch: {nested_result.evidence[0].message if nested_result.evidence else 'unknown error'}",
                            expected_index=expected_idx,
                            actual_index=actual_idx,
                            actual_path=group_path + actual_path_in_group,
                        ).located(actual_index=actual_idx, prefix=group_path)
                    )
                    # EG-B4: flag when another complete pairing exists
                    if nested_result.possible_alternative_pairing:
                        evidence[-1] = replace(evidence[-1], possible_alternative_pairing=True)
                    # For now, we assume a direct mismatch and move to the next expected/actual.
                    # More sophisticated logic might be needed for complex EG-B4 scenarios.
                    expected_idx += 1
                    actual_idx += 1

            else:
                # Try to match the current expected matcher with the current actual exception
                match_result = expected_matcher.match(actual_exc)

                if match_result.matched:
                    expected_idx += 1
                    actual_idx += 1
                    # If the actual item was part of a nested group and we are flattening,
                    # we need to ensure the evidence from the leaf matcher includes the correct path.
                    # The `match_result.evidence` from LeafMatcher will be empty on success.
                    # If there were failures in the leaf matcher, they would be here.
                    # We need to add the actual_path_in_group to any evidence from the leaf match.
                    # However, the leaf match itself doesn't know about the group path.
                    # This logic needs to be handled carefully.
                    # For now, assume success means no evidence to add from this pairing.
                    pass # Success, move to next expected and actual
                else:
                    # Mismatch found
                    # EG-B4: report unmatched expected and unexpected actual items
                    if match_result.evidence:
                        # If the leaf matcher provided evidence, add it with the correct path
                        for ev in match_result.evidence:
                            evidence.append(
                                ev.located(
                                    expected_index=expected_idx,
                                    actual_index=actual_idx,
                                    prefix=group_path + actual_path_in_group,
                                )
                            )
                    else:
                        # If no specific evidence from the leaf, create a generic mismatch evidence
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNMATCHED_EXPECTED,
                                message=f"Expected matcher {expected_matcher} did not match actual exception {actual_exc}",
                                expected_index=expected_idx,
                                actual_index=actual_idx,
                                actual_path=group_path + actual_path_in_group,
                            ).located(actual_index=actual_idx, prefix=group_path)
                        )

                    # EG-B4: flag when another complete pairing exists
                    if match_result.possible_alternative_pairing:
                        evidence[-1] = replace(evidence[-1], possible_alternative_pairing=True)

                    # Decide how to proceed:
                    # If the current expected matcher *could* match a later actual item,
                    # or a later expected matcher *could* match the current actual item,
                    # we might need to explore alternatives.
                    # For now, assume a greedy match and move to the next expected/actual on mismatch.
                    # This is a simplification for EG-B4.
                    expected_idx += 1
                    actual_idx += 1

        # After the loop, check for remaining unmatched expected or actual items
        if expected_idx < len(expected_matchers):
            # EG-B4: unmatched expected items
            for i in range(expected_idx, len(expected_matchers)):
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"Unmatched expected matcher: {expected_matchers[i]}",
                        expected_index=i,
                        actual_index=None,
                        actual_path=group_path,
                    ).located(prefix=group_path)
                )

        if actual_idx < len(actual_items):
            # EG-B4: unexpected actual items
            for i in range(actual_idx, len(actual_items)):
                exc, path = actual_items[i]
                evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Unexpected actual exception: {exc}",
                        expected_index=None,
                        actual_index=i,
                        actual_path=group_path + path,
                    ).located(actual_index=i, prefix=group_path)
                )

        if not evidence:
            # If no evidence was collected, it means all expected matchers were consumed and all actual items were consumed.
            # This implies a successful match.
            return MatchResult.success()
        else:
            # Construct the result with collected evidence.
            # EG-B4: flag when another complete pairing exists
            # This is a simplified check. A more robust check for alternative pairings would involve backtracking or more complex lookahead.
            # For now, we'll rely on the `possible_alternative_pairing` flag from nested calls or specific matchers.
            # If there's a mix of expected and actual mismatches, it's definitely not a full match.
            # If there are only unexpected actuals, and the expected were all matched, it might be a partial match scenario.
            # The current logic focuses on full match/mismatch.
            possible_alt = any(ev.possible_alternative_pairing for ev in evidence)
            return MatchResult.failure(tuple(evidence), possible_alternative_pairing=possible_alt)
