from __future__ import annotations

from collections.abc import Sequence
from typing import overload

from exception_matcher.contracts import FailureCode, MatchEvidence, MatchResult, Matcher
from exception_matcher.leaf import LeafMatcher

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
            else:
                return MatchResult.failure(MatchEvidence(FailureCode.EXPECTED_GROUP, "Expected an exception group but got a leaf exception."))

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        # If flatten is True, recursively extract leaf exceptions
        if self.flatten:
            flattened_actual = self._flatten_exceptions(actual, prefix=())
            actual_exceptions_for_flatten = [(exp, idx) for exp, idx in flattened_actual]
        else:
            actual_exceptions_for_flatten = [(exp, (idx,)) for idx, exp in enumerate(actual_exceptions)]


        matched_actual_indices = set()
        matched_expected_indices = set()

        for i, expected_matcher in enumerate(expected_matchers):
            found_match = False
            for j, (actual_exception, actual_path) in enumerate(actual_exceptions_for_flatten):
                if j in matched_actual_indices:
                    continue

                # If flatten is True, actual_path is already a tuple of indices
                # If flatten is False, we need to construct the path
                current_actual_path = actual_path if self.flatten else (j,)

                match_result = expected_matcher.match(actual_exception)

                if match_result.matched:
                    matched_expected_indices.add(i)
                    matched_actual_indices.add(j)
                    found_match = True
                # For a successful match, evidence should be empty per EG-A3.
                # No need to process match_result.evidence here.
                matched_expected_indices.add(i)
                matched_actual_indices.add(j)
                found_match = True
                break # Move to the next expected matcher
            else:
                # If the leaf match failed, capture its evidence and ensure it's located correctly.
                # This evidence should be added to the overall evidence list for the group match.
                for ev in match_result.evidence:
                    if isinstance(ev, MatchEvidence):
                        # Ensure the evidence is correctly located with the expected_index, actual_index, and actual_path prefix.
                        evidence.append(
                            ev.located(
                                expected_index=i,
                                actual_index=j,
                                prefix=actual_path
                            )
                        )
        # If after checking all actual exceptions, no *successful* match was found for this expected_matcher:
        if not found_match:
            # This case should ideally be covered by the loop above where `match_result.matched` is False,
            # and evidence is collected. However, if no actual exceptions were even considered,
            # we might end up here. The primary fix is ensuring evidence is collected in the loop.
            # The UNMATCHED_EXPECTED failure should be generated when an expected matcher
            # has no corresponding successful match in the actual exceptions.
            # The `expected_index` is `i`.
            # The `actual_path` for an unmatched expected item is tricky. If `flatten=True`,
            # `actual_path` in the loop above would have captured the nested path.
            # If no match was found, it means none of the actual exceptions matched this expected matcher.
            # We will rely on the evidence collected within the loop for mismatches.
            pass # The evidence collection in the loop should handle this.


        # Check for unexpected actual exceptions
        for j, (actual_exception, actual_path) in enumerate(actual_exceptions_for_flatten):
            if j not in matched_actual_indices:
                # If flatten is True, actual_path is already a tuple of indices.
                # If flatten is False, we use the index j.
                current_actual_path = actual_path if self.flatten else (j,)
                evidence.append(MatchEvidence(
                    FailureCode.UNEXPECTED_ACTUAL,
                    f"Unexpected actual exception at path {current_actual_path}.",
                    actual_index=j,
                    actual_path=current_actual_path
                ))

        # Check for possible alternative pairings (EG-B4)
        # This check is a simplification. A more robust check would involve backtracking.
        if len(matched_expected_indices) < len(expected_matchers) and len(matched_actual_indices) < len(actual_exceptions_for_flatten):
             possible_alternative_pairing = True

        if not evidence:
            return MatchResult.success()
        else:
            # Ensure that MatchResult.failure receives individual MatchEvidence objects
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative_pairing)

        # If after checking all actual exceptions, no *successful* match was found for this expected_matcher:
        if not found_match:
            # If flatten is True, actual_path is already available from _flatten_exceptions.
            # If flatten is False, we use the index j from the outer loop.
            # If j is not in locals(), it means actual_exceptions_for_flatten was empty, so default to empty tuple.
            # We need to ensure the actual_path is correctly determined for the UNMATCHED_EXPECTED failure.
            # If the inner loop didn't run at all (actual_exceptions_for_flatten is empty),
            # then `actual_path` won't be defined.
            # However, the test case has actual exceptions, so `actual_path` will be defined.
            # The issue is that `actual_path` refers to the *current* actual exception being checked in the inner loop.
            # If `found_match` is False, it means *none* of the actual exceptions matched.
            # So, we should report UNMATCHED_EXPECTED, and the `actual_path` for this failure
            # is not directly tied to a single actual exception that failed.
            # The original code's `current_actual_path_for_failure` logic seems to be trying
            # to get the path of the last checked actual exception, which might be misleading.
            # For a general UNMATCHED_EXPECTED, the actual_path might be better left empty,
            # or reflect the state of actual exceptions not consumed by other matchers.
            # Let's stick to the original logic for `current_actual_path_for_failure` for now,
            # but the primary fix is collecting the leaf failures.
            current_actual_path_for_failure = actual_path if self.flatten else (j,) if 'j' in locals() else ()
            evidence.append(MatchEvidence(
                FailureCode.UNMATCHED_EXPECTED,
                f"Expected matcher {i} did not find a match.",
                expected_index=i,
                actual_path=current_actual_path_for_failure
            ))


        # Check for unexpected actual exceptions
        for j, (actual_exception, actual_path) in enumerate(actual_exceptions_for_flatten):
            if j not in matched_actual_indices:
                # If flatten is True, actual_path is already a tuple of indices.
                # If flatten is False, we use the index j.
                current_actual_path = actual_path if self.flatten else (j,)
                evidence.append(MatchEvidence(
                    FailureCode.UNEXPECTED_ACTUAL,
                    f"Unexpected actual exception at path {current_actual_path}.",
                    actual_index=j,
                    actual_path=current_actual_path
                ))

        # Check for possible alternative pairings (EG-B4)
        # This check is a simplification. A more robust check would involve backtracking.
        if len(matched_expected_indices) < len(expected_matchers) and len(matched_actual_indices) < len(actual_exceptions_for_flatten):
             possible_alternative_pairing = True

        if not evidence:
            return MatchResult.success()
        else:
            # Ensure that MatchResult.failure receives individual MatchEvidence objects
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative_pairing)


    def _flatten_exceptions(self, exception: BaseException, prefix: tuple[int, ...]) -> list[tuple[BaseException, tuple[int, ...]]]:
        """Recursively flattens exception groups, preserving original paths."""
        items = []
        if isinstance(exception, BaseExceptionGroup):
            for i, exc in enumerate(exception.exceptions):
                items.extend(self._flatten_exceptions(exc, prefix + (i,)))
        else:
            items.append((exception, prefix))
        return items
