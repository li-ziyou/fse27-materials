from __future__ import annotations

from collections.abc import Sequence
from typing import Type

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
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.EXPECTED_GROUP,
                            message=f"Expected an ExceptionGroup with {len(self.expected)} matchers, but got a leaf exception.",
                        )
                    )
            else:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected an ExceptionGroup, but got a leaf exception.",
                    )
                )

        actual_exceptions = actual.exceptions
        expected_matchers = self.expected
        num_expected = len(expected_matchers)
        num_actual = len(actual_exceptions)

        # For flatten=False, we need to match GroupMatcher with ExceptionGroup and LeafMatcher with leaf exceptions.
        # For flatten=True, we need to flatten the actual exceptions and match LeafMatcher against them.
        # GroupMatcher against a leaf is not allowed when flatten=True.

        if self.flatten:
            flattened_actuals: list[tuple[BaseException, tuple[int, ...]]] = []

            def _flatten_exceptions(exceptions: Sequence[BaseException], current_path: tuple[int, ...]):
                for idx, exc in enumerate(exceptions):
                    if isinstance(exc, ExceptionGroup):
                        _flatten_exceptions(exc.exceptions, current_path + (idx,))
                    else:
                        flattened_actuals.append((exc, current_path + (idx,)))

            _flatten_exceptions(actual_exceptions, ())

            matched_flattened_indices = [False] * len(flattened_actuals)
            all_evidence: list[MatchEvidence] = []
            possible_alternative_pairing = False

            for i, expected_matcher in enumerate(expected_matchers):
                found_match = False
                for j, (actual_exception, actual_path) in enumerate(flattened_actuals):
                    if not matched_flattened_indices[j]:
                        # When flatten is True, expected_matcher should ideally be a LeafMatcher.
                        # If it's a GroupMatcher, it implies a mismatch in expectation for this mode.
                        if isinstance(expected_matcher, LeafMatcher):
                            leaf_result = expected_matcher.match(actual_exception)
                            if leaf_result.matched:
                                matched_flattened_indices[j] = True
                                for evidence in leaf_result.evidence:
                                    prefixed_evidence = evidence.located(
                                        expected_index=i,
                                        actual_index=j,
                                        prefix=actual_path,
                                    )
                                    all_evidence.append(prefixed_evidence)
                                found_match = True
                                break
                            else:
                            for evidence in leaf_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=actual_path,
                                )
                                all_evidence.append(prefixed_evidence)
                                found_match = True
                                break
                            else:
                            for evidence in leaf_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                        prefix=actual_path,
                                    )
                                    all_evidence.append(prefixed_evidence)
                                found_match = True
                                break
                            else:
                                # Collect evidence even if it didn't match, to report the mismatch
                        # Collect evidence even if it didn't match, to report the mismatch
                        for evidence in leaf_result.evidence:
                            prefixed_evidence = evidence.located(
                                expected_index=i,
                                actual_index=j,
                                prefix=actual_path,
                            )
                            all_evidence.append(prefixed_evidence)
                        # If the leaf did not match, we should not mark it as found_match,
                        # and continue searching for a match for the current expected_matcher.
                        # However, we do collect its evidence.
                        # If no match is found for this expected_matcher after checking all actuals,
                        # it will be reported as UNMATCHED_EXPECTED.
                        continue # Continue to the next actual exception for this expected matcher

                    # If the leaf matched, mark it and break the inner loop
                    matched_flattened_indices[j] = True
                    for evidence in leaf_result.evidence:
                        prefixed_evidence = evidence.located(
                            expected_index=i,
                            actual_index=j,
                            prefix=actual_path,
                        )
                        all_evidence.append(prefixed_evidence)
                    found_match = True
                    break # Break the inner loop (over actuals) as we found a match for this expected_matcher

                # EG-B1 violation: A GroupMatcher cannot match a leaf directly when flatten=True.
                # This case should result in a failure for this expected_matcher.
                elif isinstance(expected_matcher, GroupMatcher):
                    # If the actual exception is a group, we should try to match it with the GroupMatcher.
                    # If it's a leaf, it's a type mismatch for the GroupMatcher.
                    if isinstance(actual_exception, ExceptionGroup):
                        # Recursively match the nested group.
                        nested_result = expected_matcher.match(actual_exception)
                        if nested_result.matched:
                            matched_flattened_indices[j] = True
                            for evidence in nested_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=actual_path,
                                )
                                all_evidence.append(prefixed_evidence)
                            found_match = True
                            break # Break the inner loop (over actuals) as we found a match for this expected_matcher
                        else:
                            # If the nested group didn't match, add its evidence, prefixed with current path
                            for evidence in nested_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=actual_path,
                                )
                                all_evidence.append(prefixed_evidence)
                            # If the nested group didn't match, we continue to the next actual exception
                            # to see if it can match the current expected_matcher.
                            continue
                    else:
                        # If expected a GroupMatcher but got a leaf, this is a mismatch.
                        # Collect evidence and continue searching for a match for the current expected_matcher.
                        all_evidence.append(MatchEvidence(
                            code=FailureCode.UNEXPECTED_GROUP,
                            message=f"Expected an ExceptionGroup, but got a leaf exception at flattened index {j} (path: {actual_path}).",
                            expected_index=i,
                            actual_index=j,
                            actual_path=actual_path,
                        ))
                        continue # Continue to the next actual exception for this expected matcher

            if not found_match:
                all_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher at index {i}.",
                        expected_index=i,
                    )
                )
                # EG-B4: Flag possible alternative pairing. This check needs to be more robust,
                # but for now, if there are remaining unmatched actuals, it's a potential alternative.
                if any(not matched for matched in matched_flattened_indices):
                    possible_alternative_pairing = True

        # Check for unexpected actuals in the flattened list
        for j, (actual_exception, actual_path) in enumerate(flattened_actuals):
            if not matched_flattened_indices[j]:
                all_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Actual exception at flattened index {j} (path: {actual_path}) was not matched.",
                        actual_index=j,
                        actual_path=actual_path,
                    )
                )
                if num_expected < len(flattened_actuals):
                    possible_alternative_pairing = True

        all_expected_matched = all(matched_flattened_indices)
        # This check is key: if all expected were matched AND there are no unexpected actuals, it's a success.
        no_unexpected_actuals = all(matched for matched in matched_flattened_indices)

        if all_expected_matched and no_unexpected_actuals:
            return MatchResult.success()
        else:
            return MatchResult.failure(*all_evidence, possible_alternative_pairing=possible_alternative_pairing)

    else: # flatten is False (default behavior)
        # EG-B1: Preserve nested group boundaries.
        # Match GroupMatcher against ExceptionGroup, and LeafMatcher against leaf exceptions.

        matched_actual_indices = [False] * num_actual
        all_evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, actual_exception in enumerate(actual_exceptions):
                if not matched_actual_indices[j]:
                    # Case 1: Expected GroupMatcher, Actual ExceptionGroup
                    if isinstance(expected_matcher, GroupMatcher) and isinstance(actual_exception, ExceptionGroup):
                        # Recursively match the nested group.
                        nested_result = expected_matcher.match(actual_exception)
                        if nested_result.matched:
                            matched_actual_indices[j] = True
                            for evidence in nested_result.evidence:
                                # Prepend the current actual index to the evidence's actual_path
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=(j,) + evidence.actual_path,
                                )
                                all_evidence.append(prefixed_evidence)
                            found_match = True
                            break
                        else:
                            # If the nested group didn't match, add its evidence, prefixed with current path
                            for evidence in nested_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=(j,) + evidence.actual_path,
                                )
                                all_evidence.append(prefixed_evidence)
                            # If the nested group didn't match, we continue to the next actual exception
                            # to see if it can match the current expected_matcher.
                            continue

                    # Case 2: Expected LeafMatcher, Actual Leaf Exception
                    elif isinstance(expected_matcher, LeafMatcher) and not isinstance(actual_exception, ExceptionGroup):
                        leaf_result = expected_matcher.match(actual_exception)
                        if leaf_result.matched:
                            matched_actual_indices[j] = True
                            for evidence in leaf_result.evidence:
                                # For leaf matches, the path is just the current index.
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=(j,),
                                )
                                all_evidence.append(prefixed_evidence)
                            found_match = True
                            break
                        else:
                            # If the leaf didn't match, add its evidence
                            for evidence in leaf_result.evidence:
                                prefixed_evidence = evidence.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=(j,),
                                )
                                all_evidence.append(prefixed_evidence)
                            # If the leaf didn't match, continue to the next actual exception
                            # to see if it can match the current expected_matcher.
                            continue

            if not found_match:
                all_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNMATCHED_EXPECTED,
                        message=f"No actual exception matched expected matcher at index {i}.",
                        expected_index=i,
                    )
                )
                # EG-B4: Flag possible alternative pairing
                if any(not matched for matched in matched_actual_indices):
                    possible_alternative_pairing = True

        # EG-B4: Unexpected actual exceptions
        for j, actual_exception in enumerate(actual_exceptions):
            if not matched_actual_indices[j]:
                all_evidence.append(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_ACTUAL,
                        message=f"Actual exception at index {j} was not matched.",
                        actual_index=j,
                        actual_path=(j,),  # Initial path for unexpected actual
                    )
                )
                # If we find an unexpected actual, it might mean there was an alternative pairing
                if num_expected < num_actual:
                    possible_alternative_pairing = True

        all_expected_matched = all(matched_actual_indices)
        # This check is key: if all expected were matched AND there are no unexpected actuals, it's a success.
        no_unexpected_actuals = all(matched for matched in matched_actual_indices)

        if all_expected_matched and no_unexpected_actuals:
            return MatchResult.success()
        else:
            return MatchResult.failure(*all_evidence, possible_alternative_pairing=possible_alternative_pairing)
