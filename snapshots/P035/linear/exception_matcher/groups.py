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
        from .leaf import LeafMatcher  # Import here to avoid circular dependency if LeafMatcher is used within GroupMatcher logic

        # EG-B3: Handle allow_unwrapped
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped:
                if len(self.expected) == 1:
                    # Delegate to the single expected matcher
                    return self.expected[0].match(actual)
                else:
                    # More than one expected matcher, but actual is not a group
                    return MatchResult.failure(
                        MatchEvidence(
                            FailureCode.EXPECTED_GROUP,
                            f"Expected a group with {len(self.expected)} matchers, but got a leaf exception.",
                        )
                    )
            else:
                # allow_unwrapped is False, and actual is not a group
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_GROUP,
                        "Expected an ExceptionGroup, but got a leaf exception.",
                    )
                )

        # Actual is an ExceptionGroup
        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        evidence: list[MatchEvidence] = []
        matched_actual_indices = [False] * len(actual_exceptions)
        possible_alternative_pairing = False

        # EG-B1 & EG-B2: Handle flatten
        if self.flatten:
            # Flatten the actual exceptions to process leaf exceptions recursively
            def flatten_exceptions(exceptions, current_path=()):
                flat_list = []
                for i, exc in enumerate(exceptions):
                    path = current_path + (i,)
                    if isinstance(exc, BaseExceptionGroup):
                        flat_list.extend(flatten_exceptions(exc.exceptions, path))
                    else:
                        flat_list.append((exc, path))
                return flat_list

            flattened_actual = flatten_exceptions(actual_exceptions)
            actual_exceptions = [exc for exc, path in flattened_actual]
            # Store paths to reconstruct evidence later
            actual_paths = {i: path for i, (exc, path) in enumerate(flattened_actual)}
        else:
            actual_paths = {i: (i,) for i in range(len(actual_exceptions))}


        # EG-B4: Pair expected matchers with actual exceptions
        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exc in enumerate(actual_exceptions):
                if not matched_actual_indices[j]:
                    # If flatten is True, we need to pass the actual_exc and its path
                    # If flatten is False, LeafMatcher.match will handle the ExceptionGroup check
                    match_result = expected_matcher.match(actual_exc)

                    if match_result.matched:
                        # Preserve original index and path for evidence
                        evidence.append(
                            MatchEvidence(
                                code=FailureCode.UNEXPECTED_ACTUAL, # This will be overwritten if actual is consumed
                                message="Placeholder",
                                expected_index=i,
                                actual_index=j,
                                actual_path=actual_paths.get(j, (j,)),
                            )
                        )
                        matched_actual_indices[j] = True
                        found_match = True
                        break  # Move to the next expected matcher

            if not found_match:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"Expected matcher {i} did not match any remaining actual exceptions.",
                        expected_index=i,
                    )
                )

        # Collect unexpected actual exceptions
        for j, actual_exc in enumerate(actual_exceptions):
            if not matched_actual_indices[j]:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        f"Actual exception {j} was not matched by any expected matcher.",
                        actual_index=j,
                        actual_path=actual_paths.get(j, (j,)),
                    )
                )

        # EG-I1: Preserve leaf failure codes together with expected indexes, actual indexes, and nested actual paths.
        # Rerun matches to get detailed failure evidence for all unmatched expected and actual items.
        final_evidence: list[MatchEvidence] = []
        if not all(matched_actual_indices) or len(expected_matchers) != sum(matched_actual_indices):
            # Track which actual exceptions have been matched for this detailed evidence collection pass.
            temp_matched_actual_indices = [False] * len(actual_exceptions)

            # First, try to match expected to actual to identify unmatched expected.
            for i, expected_matcher in enumerate(expected_matchers):
                matched_this_expected = False
                for j, actual_exc in enumerate(actual_exceptions):
                    if not temp_matched_actual_indices[j]:
                        match_result = expected_matcher.match(actual_exc)
                        if match_result.matched:
                            temp_matched_actual_indices[j] = True
                            matched_this_expected = True
                            break # Found a match for this expected matcher, move to the next one.

                if not matched_this_expected:
                    # This expected matcher did not find a match. Record it as UNMATCHED_EXPECTED.
                    # We don't need to re-match here to get its specific failure, as the test is about pairing.
                    final_evidence.append(
                        MatchEvidence(
                            FailureCode.UNMATCHED_EXPECTED,
                            f"Expected matcher {i} did not match any remaining actual exceptions.",
                            expected_index=i,
                        )
                    )

            # Then, collect detailed evidence for any actual exceptions that were not matched.
            for j, actual_exc in enumerate(actual_exceptions):
                if not temp_matched_actual_indices[j]:
                    # This actual exception was not matched by any expected matcher.
                    # We need to determine *why* it failed to match. This is complex as it could fail
                    # against multiple expected matchers for different reasons.
                    # For now, we'll try to find *a* reason by attempting to match it against all
                    # expected matchers that were not themselves marked as UNMATCHED_EXPECTED.
                    failure_reason_found = False
                    for k, expected_matcher in enumerate(expected_matchers):
                        # Only consider expected matchers that are not already marked as unmatched.
                        if not any(e.code == FailureCode.UNMATCHED_EXPECTED and e.expected_index == k for e in final_evidence):
                            match_result = expected_matcher.match(actual_exc)
                            if not match_result.matched:
                                # This expected matcher failed to match this actual exception.
                                # We'll use the *first* failure evidence from this failed match.
                                # EG-I1: Ensure actual_path is correctly set.
                                if match_result.evidence:
                                    # The evidence from the leaf/group matcher might not have the correct indices/paths.
                                    # We need to locate it with the current context.
                                    original_evidence = match_result.evidence[0]
                                    # When a message mismatch occurs, ensure the actual_path is correctly set.
                                    # The prefix should be the path to the current actual exception.
                                    current_actual_path = actual_paths.get(j, (j,))
                                    located_evidence = original_evidence.located(
                                        expected_index=k,
                                        actual_index=j,
                                        prefix=current_actual_path,
                                    )
                                    final_evidence.append(located_evidence)
                                    failure_reason_found = True
                                    break # Found a reason, move to the next unmatched actual.

                    if not failure_reason_found:
                        # If no specific reason was found, mark it as UNEXPECTED_ACTUAL.
                        final_evidence.append(
                            MatchEvidence(
                                FailureCode.UNEXPECTED_ACTUAL,
                                f"Actual exception at index {j} was not matched by any expected matcher.",
                                actual_index=j,
                                actual_path=actual_paths.get(j, (j,)),
                            )
                        )

            # EG-B4: possible_alternative_pairing logic.
            # This is true if there are both unmatched expected items and unmatched actual items,
            # suggesting that a different pairing might have worked.
            if any(e.code == FailureCode.UNMATCHED_EXPECTED for e in final_evidence) and \
               any(e.code == FailureCode.UNEXPECTED_ACTUAL for e in final_evidence):
                possible_alternative_pairing = True

        # If no failures were recorded and all actuals were matched, it's a success.
        # We also check that the number of expected matchers matches the number of successfully matched actual exceptions.
        if not final_evidence and all(matched_actual_indices) and len(expected_matchers) == sum(matched_actual_indices):
            return MatchResult.success()
        else:
            # Return a failure result with all collected evidence.
            return MatchResult.failure(*final_evidence, possible_alternative_pairing=possible_alternative_pairing)

