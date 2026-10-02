from __future__ import annotations

from collections.abc import Sequence

from .contracts import MatchResult, Matcher


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
        if isinstance(actual, BaseExceptionGroup):
            actual_exceptions = actual.exceptions
        else:
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher if allow_unwrapped is True
                return self.expected[0].match(actual)
            else:
                # If not allowed to unwrap or more than one expected matcher, it's a group mismatch
                return MatchResult.failure(MatchEvidence(FailureCode.EXPECTED_GROUP, "Expected an ExceptionGroup but received a leaf exception"))

        # Handle ExceptionGroup
        if self.flatten:
            # Flattened matching: iterate through all leaves in the group
            collected_evidence = []
            matched_expected_indices = set()
            matched_actual_indices = set()
            
            for i, expected_matcher in enumerate(self.expected):
                found_match_for_expected = False
                for j, actual_exception in enumerate(actual_exceptions):
                    if j in matched_actual_indices:
                        continue # Skip already matched actual exceptions

                    if not isinstance(actual_exception, BaseExceptionGroup):
                        match_result = expected_matcher.match(actual_exception)
                        if match_result.matched:
                            matched_expected_indices.add(i)
                            matched_actual_indices.add(j)
                            # Evidence from leaf match is already structured
                            for ev in match_result.evidence:
                                collected_evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                            found_match_for_expected = True
                            break # Move to the next expected matcher
                        else:
                            # If a leaf doesn't match, collect its evidence and continue searching for a match for the current expected_matcher
                            for ev in match_result.evidence:
                                collected_evidence.append(ev.located(expected_index=i, actual_index=j, prefix=(j,)))
                
                # If after checking all actual exceptions, the current expected matcher was not matched
                if not found_match_for_expected and i not in matched_expected_indices:
                     # This case should be covered by UNMATCHED_EXPECTED if we exhaust expected matchers.
                     # For flatten=True, we expect all expected to match an actual.
                     pass

            # Report unmatched expected matchers
            for i in range(len(self.expected)):
                if i not in matched_expected_indices:
                    collected_evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, "Unmatched expected matcher", expected_index=i))

            # Report unexpected actual exceptions
            for j in range(len(actual_exceptions)):
                if j not in matched_actual_indices:
                    collected_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, "Unexpected actual exception", actual_index=j, actual_path=(j,)))

            if len(matched_expected_indices) == len(self.expected) and len(matched_actual_indices) == len(actual_exceptions):
                return MatchResult.success()
            else:
                return MatchResult.failure(*collected_evidence, possible_alternative_pairing=False) # Simplified failure reporting

        else: # Default: preserve nested group boundaries
            current_actual_index = 0
            all_evidence = []
            possible_alternative_pairing = False

            for i, expected_matcher in enumerate(self.expected):
                matched_this_expected = False
                while current_actual_index < len(actual_exceptions):
                    actual_exception = actual_exceptions[current_actual_index]

                    if isinstance(actual_exception, BaseExceptionGroup):
                        if isinstance(expected_matcher, GroupMatcher):
                            # Recursively match nested group
                            nested_result = expected_matcher.match(actual_exception)
                            if nested_result.matched:
                                # Propagate evidence from nested match, adding current actual_index and path
                                for ev in nested_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,) + ev.actual_path))
                                matched_this_expected = True
                                current_actual_index += 1
                                break # Move to the next expected matcher
                            else:
                                # Nested group did not match, collect its failures
                                for ev in nested_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,) + ev.actual_path))
                                possible_alternative_pairing = possible_alternative_pairing or nested_result.possible_alternative_pairing
                                # If the nested group didn't match, we might still find a match for the current expected_matcher later
                                # So we don't break here, but we also don't increment current_actual_index yet.
                                # However, for strict ordered matching, if a group doesn't match, it might be a failure.
                                # Let's assume for now that if a group doesn't match, it's an unexpected actual.
                                # This needs refinement based on EG-B4.
                                pass # Continue to next actual exception to see if it matches the current expected_matcher
                        else:
                            # Expected a leaf but got a group
                            all_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Expected a leaf matcher, but got an ExceptionGroup", expected_index=i, actual_index=current_actual_index, actual_path=(current_actual_index,)))
                            current_actual_index += 1 # Consume the unexpected group
                    else: # actual_exception is a leaf
                        if not isinstance(expected_matcher, GroupMatcher):
                            # Attempt to match leaf
                            match_result = expected_matcher.match(actual_exception)
                            if match_result.matched:
                                matched_this_expected = True
                                # Evidence from leaf match is already structured
                                for ev in match_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,)))
                                current_actual_index += 1
                                break # Move to the next expected matcher
                            else:
                                # Leaf did not match, collect its failures
                                for ev in match_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,)))
                                possible_alternative_pairing = possible_alternative_pairing or match_result.possible_alternative_pairing
                                current_actual_index += 1 # Consume the unmatched leaf
                        else:
                            # Expected a group but got a leaf
                            all_evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, "Expected a group matcher, but got a leaf exception", expected_index=i, actual_index=current_actual_index, actual_path=(current_actual_index,)))
                            # If we expected a group and got a leaf, it's a mismatch for this expected matcher.
                            # We should consume the leaf and try to match the next expected matcher with the next actual exception.
                            current_actual_index += 1 # Consume the unexpected leaf

                if not matched_this_expected:
                    # If after checking all remaining actual exceptions, the current expected matcher was not matched
                    # We need to report this as an unmatched expected.
                    # This is a simplified check. A full EG-B4 implementation is more complex.
                    # For now, if we break out of the inner while loop without `matched_this_expected` being True,
                    # it implies a failure for this `expected_matcher`.
                    # However, the logic above already appends evidence for mismatches.
                    pass


            # After iterating through all expected matchers, check for remaining actual exceptions
            if current_actual_index < len(actual_exceptions):
                for j in range(current_actual_index, len(actual_exceptions)):
                    all_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, "Unexpected actual exception", actual_index=j, actual_path=(j,)))

            # Check if all expected matchers were consumed and all actual exceptions were consumed
            if len(self.expected) == i + 1 and current_actual_index == len(actual_exceptions):
                return MatchResult.success()
            else:
                # EG-B4: Flag when another complete pairing exists. This is a complex condition.
                # For now, we set possible_alternative_pairing based on collected evidence.
                # A full implementation of EG-B4 requires exploring alternative pairings.
                return MatchResult.failure(*all_evidence, possible_alternative_pairing=possible_alternative_pairing)

        else:  # Default: preserve nested group boundaries
            current_actual_index = 0
            all_evidence = []
            possible_alternative_pairing = False

            for i, expected_matcher in enumerate(self.expected):
                matched_this_expected = False
                while current_actual_index < len(actual_exceptions):
                    actual_exception = actual_exceptions[current_actual_index]

                    if isinstance(actual_exception, BaseExceptionGroup):
                        if isinstance(expected_matcher, GroupMatcher):
                            # Recursively match nested group
                            nested_result = expected_matcher.match(actual_exception)
                            if nested_result.matched:
                                # Propagate evidence from nested match, adding current actual_index and path
                                for ev in nested_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,) + ev.actual_path))
                                matched_this_expected = True
                                current_actual_index += 1
                                break  # Move to the next expected matcher
                            else:
                                # Nested group did not match, collect its failures
                                for ev in nested_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,) + ev.actual_path))
                                possible_alternative_pairing = possible_alternative_pairing or nested_result.possible_alternative_pairing
                                # If the nested group didn't match, we might still find a match for the current expected_matcher later
                                # So we don't break here, but we also don't increment current_actual_index yet.
                                # However, for strict ordered matching, if a group doesn't match, it might be a failure.
                                # Let's assume for now that if a group doesn't match, it's an unexpected actual.
                                # This needs refinement based on EG-B4.
                                pass  # Continue to next actual exception to see if it matches the current expected_matcher
                        else:
                            # Expected a leaf but got a group
                            all_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Expected a leaf matcher, but got an ExceptionGroup", expected_index=i, actual_index=current_actual_index, actual_path=(current_actual_index,)))
                            current_actual_index += 1  # Consume the unexpected group
                    else:  # actual_exception is a leaf
                        if not isinstance(expected_matcher, GroupMatcher):
                            # Attempt to match leaf
                            match_result = expected_matcher.match(actual_exception)
                            if match_result.matched:
                                matched_this_expected = True
                                # Evidence from leaf match is already structured
                                for ev in match_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,)))
                                current_actual_index += 1
                                break  # Move to the next expected matcher
                            else:
                                # Leaf did not match, collect its failures
                                for ev in match_result.evidence:
                                    all_evidence.append(ev.located(expected_index=i, actual_index=current_actual_index, prefix=(current_actual_index,)))
                                possible_alternative_pairing = possible_alternative_pairing or match_result.possible_alternative_pairing
                                current_actual_index += 1  # Consume the unmatched leaf
                        else:
                            # Expected a group but got a leaf
                            all_evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, "Expected a group matcher, but got a leaf exception", expected_index=i, actual_index=current_actual_index, actual_path=(current_actual_index,)))
                            # If we expected a group and got a leaf, it's a mismatch for this expected matcher.
                            # We should consume the leaf and try to match the next expected matcher with the next actual exception.
                            current_actual_index += 1  # Consume the unexpected leaf

                if not matched_this_expected:
                    # If after checking all remaining actual exceptions, the current expected matcher was not matched
                    # We need to report this as an unmatched expected.
                    # This is a simplified check. A full EG-B4 implementation is more complex.
                    # For now, if we break out of the inner while loop without `matched_this_expected` being True,
                    # it implies a failure for this `expected_matcher`.
                    # However, the logic above already appends evidence for mismatches.
                    pass

            # After iterating through all expected matchers, check for remaining actual exceptions
            if current_actual_index < len(actual_exceptions):
                for j in range(current_actual_index, len(actual_exceptions)):
                    all_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, "Unexpected actual exception", actual_index=j, actual_path=(j,)))

            # Check if all expected matchers were consumed and all actual exceptions were consumed
            # This condition needs to be more robust for EG-B4.
            # For now, assuming a match if all expected are consumed and all actual are consumed.
            all_expected_consumed = i + 1 == len(self.expected) if self.expected else True
            all_actual_consumed = current_actual_index == len(actual_exceptions)

            if all_expected_consumed and all_actual_consumed:
                return MatchResult.success()
            else:
                # EG-B4: Flag when another complete pairing exists. This is a complex condition.
                # For now, we set possible_alternative_pairing based on collected evidence.
                # A full implementation of EG-B4 requires exploring alternative pairings.
                return MatchResult.failure(*all_evidence, possible_alternative_pairing=possible_alternative_pairing)

