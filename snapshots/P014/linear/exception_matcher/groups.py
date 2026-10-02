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
        from .contracts import FailureCode, MatchEvidence
        from .leaf import LeafMatcher

        if not isinstance(actual, ExceptionGroup):
            # EG-B3: allow_unwrapped=True delegates a non-group exception only when there is exactly one expected matcher; otherwise a group is required.
            if self.allow_unwrapped and len(self.expected) == 1:
                return self.expected[0].match(actual)
            else:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="non-group exception received but a group was expected",
                    )
                )

        actual_exceptions = actual.exceptions
        expected_matchers = list(self.expected)
        matched_results = []
        evidence: list[MatchEvidence] = []

        if self.flatten:
            # EG-B2: flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence.
            flattened_actual: list[tuple[BaseException, tuple[int, ...]]] = []

            def flatten_group(group: ExceptionGroup, path: tuple[int, ...] = ()):
                for i, exc in enumerate(group.exceptions):
                    if isinstance(exc, ExceptionGroup):
                        flatten_group(exc, path + (i,))
                    else:
                        flattened_actual.append((exc, path + (i,)))

            flatten_group(actual)

            # Match flattened leaves against expected matchers
            actual_idx = 0
            expected_idx = 0
            while expected_idx < len(expected_matchers) and actual_idx < len(flattened_actual):
                exc, path = flattened_actual[actual_idx]
                matcher = expected_matchers[expected_idx]

            # EG-B2: flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence.
            # We should allow any Matcher here, not just LeafMatcher, to match against the flattened leaf exceptions.
            # The actual matching is done by matcher.match(exc).
            match_result = matcher.match(exc)
            if match_result.matched:
                matched_results.append(match_result)
                # Remove the matched matcher and exception to proceed with the rest
                expected_matchers.pop(expected_idx)
                flattened_actual.pop(actual_idx)
            else:
                # EG-B4: failures report unmatched expected and unexpected actual items and flag when another complete pairing exists.
                # The evidence from the leaf match should be preserved and located.
                match_evidence = match_result.evidence[0].located(
                    expected_index=expected_idx,
                    actual_index=actual_idx,
                    prefix=path,
                )
                evidence.append(match_evidence)
                # Move to the next actual exception if the current one didn't match
                actual_idx += 1
            
            # Handle remaining expected or actual items
            if expected_matchers:
                for i, matcher in enumerate(expected_matchers):
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message="unmatched expected matcher",
                            expected_index=self.expected.index(matcher), # Use original index
                        )
                    )
            if flattened_actual:
                for i, (exc, path) in enumerate(flattened_actual):
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message="unexpected actual exception",
                            actual_index=actual_idx + i, # Use original index
                            actual_path=path,
                        )
                    )

        else:
            # EG-B1: GroupMatcher preserves nested group boundaries by default
            actual_exceptions_list = list(actual.exceptions)
            expected_matchers_list = list(self.expected)
            
            consumed_actual_indices = set()
            consumed_expected_indices = set()
            
            # First pass: try to match expected matchers in order with actual exceptions
            for i, expected_matcher in enumerate(expected_matchers_list):
                found_match = False
                for j, actual_exc in enumerate(actual_exceptions_list):
                    if j in consumed_actual_indices:
                        continue

                    # Determine if the actual exception is a group or leaf and if the expected matcher is compatible
                    is_actual_group = isinstance(actual_exc, ExceptionGroup)
                    is_expected_group_matcher = isinstance(expected_matcher, GroupMatcher)

                    if is_actual_group and is_expected_group_matcher:
                        # Nested group matching
                        nested_result = expected_matcher.match(actual_exc)
                        if nested_result.matched:
                            matched_results.append(nested_result)
                            consumed_actual_indices.add(j)
                            consumed_expected_indices.add(i)
                            found_match = True
                            break # Move to the next expected matcher
                    elif not is_actual_group and not is_expected_group_matcher:
                        # Leaf matching
                        match_result = expected_matcher.match(actual_exc)
                        if match_result.matched:
                            matched_results.append(match_result)
                            consumed_actual_indices.add(j)
                            consumed_expected_indices.add(i)
                            found_match = True
                            break # Move to the next expected matcher
                    # else: types are incompatible (e.g., expecting GroupMatcher for Leaf, or vice versa)
                        # This case will be handled by the evidence collection for unmatched/unexpected items

                if not found_match and i not in consumed_expected_indices:
                    # If no match was found for this expected_matcher, record it as unmatched
                    # (or potentially unexpected if it implies a different pairing)
                    pass # We'll collect all unmatched/unexpected at the end

            # Collect evidence for unmatched expected and unexpected actual items
            for i, expected_matcher in enumerate(expected_matchers_list):
                if i not in consumed_expected_indices:
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message="unmatched expected matcher",
                            expected_index=i,
                        )
                    )
            
            for j, actual_exc in enumerate(actual_exceptions_list):
                if j not in consumed_actual_indices:
                    evidence.append(
                        MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message="unexpected actual exception",
                            actual_index=j,
                        )
                    )

        # EG-B4: flag when another complete pairing exists.
        # This is a complex condition to check and might require more sophisticated logic
        # For now, we'll set it to False. A full implementation would need to explore permutations.
        possible_alternative_pairing = False

        if not evidence:
            return MatchResult.success()
        else:
            return MatchResult.failure(*evidence, possible_alternative_pairing=possible_alternative_pairing)
