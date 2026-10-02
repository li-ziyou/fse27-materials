from __future__ import annotations

from collections.abc import Sequence
from re import Pattern

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher, replace
from .leaf import LeafMatcher


class GroupMatcher:
    def __init__(
        self,
        expected: Sequence[Matcher],
        flatten: bool = False,
        allow_unwrapped: bool = False,
    ) -> None:
        self.expected = expected
        self.flatten = flatten
        self.allow_unwrapped = allow_unwrapped

    def match(self, actual: BaseException) -> MatchResult:
        # Import here to avoid circular dependency if LeafMatcher needs GroupMatcher
        # This import is necessary if LeafMatcher is used within GroupMatcher's logic.
        # However, if GroupMatcher only calls LeafMatcher.match, and LeafMatcher doesn't import GroupMatcher,
        # then this specific import might not be strictly needed here.
        # Given the test failures, it's safer to keep it or ensure the dependency is handled.
        # For now, let's assume it might be needed for internal logic or future expansion.
        from .leaf import LeafMatcher

        if not isinstance(actual, ExceptionGroup):
            # EG-B3: allow_unwrapped=True delegation
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                return self.expected[0].match(actual)
            else:
                # If not allowed to unwrap or more than one matcher expected, it's a failure.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.EXPECTED_GROUP,
                        message="Expected an ExceptionGroup",
                    )
                )

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        evidence: list[MatchEvidence] = []

        if self.flatten:
            # EG-B2: Flatten the actual exceptions
            flat_actual_exceptions: list[tuple[BaseException, tuple[int, ...]]] = []
            for i, exc in enumerate(actual_exceptions):
                if isinstance(exc, ExceptionGroup):
                    # Recursively flatten nested groups, preserving path
                    for sub_exc, sub_path in self._flatten_recursive(exc, (i,)):
                        flat_actual_exceptions.append((sub_exc, sub_path))
                else:
                    flat_actual_exceptions.append((exc, (i,)))
            actual_exceptions_for_matching = flat_actual_exceptions
        else:
            # EG-B1: Preserve nested group boundaries by default
            actual_exceptions_for_matching = [(exc, (i,)) for i, exc in enumerate(actual_exceptions)]

        # EG-B4: Pair expected matchers with actual items in order
        actual_idx = 0
        expected_idx = 0
        possible_alternative_pairing = False

        while expected_idx < len(expected_matchers) and actual_idx < len(actual_exceptions_for_matching):
            expected_matcher = expected_matchers[expected_idx]
            actual_exc, actual_path = actual_exceptions_for_matching[actual_idx]

            # Match the current expected matcher against the current actual exception
            match_result = expected_matcher.match(actual_exc)

            # If flatten is True, and the match resulted in evidence,
            # we need to update the evidence with the actual_path.
            if self.flatten and match_result.evidence:
                updated_evidence = []
                for ev in match_result.evidence:
                    # Only append path if it's a leaf failure.
                    # Group-related failures might have their own path context.
                    if ev.code not in (FailureCode.UNEXPECTED_GROUP, FailureCode.EXPECTED_GROUP):
                        # The .located() method does not take 'actual_path'.
                        # The actual_path should be part of the MatchEvidence itself if it's already there,
                        # or it's handled by the recursive calls and the flattening logic.
                        # We should only ensure that the evidence we are adding has the correct path context.
                        # If `ev` already has an `actual_path`, we should use it. If not, and we have
                        # `actual_path` from the flattening, we should combine them.
                        # For now, let's assume `ev` might already have a path, and we are not overwriting it here.
                        # If `ev` does not have a path, and we have `actual_path`, we should add it.
                        # The `located` method is for prefixing paths.
                        # Let's simplify: if `ev` has no path, and we have one, add it.
                        # If `ev` already has a path, it's likely from a deeper nesting.
                        # The test case failure suggests that the path isn't being preserved correctly.
                        # The `actual_path` here is the path *to* the current `actual_exc`.
                        # We need to ensure this path is associated with the evidence.
                        # A simpler approach is to just add the evidence with the correct path if it's missing.
                        # However, `ev.located` is intended for path manipulation.
                        # Let's re-examine the contract of `MatchEvidence.located`. It takes `prefix`.
                        # The goal is to ensure the `actual_path` is part of the final `MatchEvidence`.
                        # If `ev` has `actual_path`, it's already set. If not, and we have `actual_path`,
                        # we should use it.
                        # The issue might be that `ev.located` is not the right tool for this.
                        # Let's try to directly add the path if it's not present.
                        if not ev.actual_path and actual_path:
                            updated_evidence.append(ev.located(prefix=actual_path)) # Using prefix as it's the closest available
                        elif ev.actual_path:
                            updated_evidence.append(ev) # Keep existing path
                        else:
                            updated_evidence.append(ev) # No path to add
                    else:
                        updated_evidence.append(ev) # Keep original evidence for group mismatches
                match_result = replace(match_result, evidence=tuple(updated_evidence))

            if match_result.matched:
                # EG-B1: Preserve nested group boundaries by default.
                # If we are not flattening, and the actual exception is a group,
                # it must be matched by a GroupMatcher.
                if not self.flatten and isinstance(actual_exc, ExceptionGroup) and not isinstance(expected_matcher, GroupMatcher):
                    evidence.append(MatchEvidence(
                        code=FailureCode.UNEXPECTED_GROUP,
                        message="Expected a leaf exception, but got a group",
                        expected_index=expected_idx,
                        actual_index=actual_idx,
                        actual_path=actual_path # Path to the unexpected group
                    ))
                    # This is a mismatch, so we break and report.
                    # Consume the actual group and move to the next expected matcher.
                    actual_idx += 1
                    expected_idx += 1
                    # Break from the while loop as this pairing attempt failed.
                    break
                else:
                    # Successful match, move to the next expected and actual items.
                    evidence.extend(match_result.evidence)
                    expected_idx += 1
                    actual_idx += 1
            else:
                # Handle mismatches
                # EG-B4: Check for possible alternative pairings.
                # If the number of remaining expected matchers equals the number of remaining actual exceptions,
                # it suggests a potential alternative pairing exists if the current mismatch was resolved differently.
                if len(expected_matchers) - expected_idx == len(actual_exceptions_for_matching) - actual_idx:
                    possible_alternative_pairing = True

                # If there are remaining items on both sides, it implies a potential for a different arrangement.
                if expected_idx < len(expected_matchers) and actual_idx < len(actual_exceptions_for_matching):
                    possible_alternative_pairing = True

                # Report unmatched expected and unexpected actual items.
                # Unmatched expected: all expected matchers from the current expected_idx onwards.
                if len(expected_matchers) > expected_idx:
                    for i in range(expected_idx, len(expected_matchers)):
                        evidence.append(MatchEvidence(
                            code=FailureCode.UNMATCHED_EXPECTED,
                            message=f"Expected matcher {i} was not matched",
                            expected_index=i,
                            # actual_path is not directly applicable here as no specific actual item was matched for this expected matcher.
                        ))
                # Unexpected actual: all actual exceptions from the current actual_idx onwards.
                if len(actual_exceptions_for_matching) > actual_idx:
                    for i in range(actual_idx, len(actual_exceptions_for_matching)):
                        actual_exc, actual_path = actual_exceptions_for_matching[i]
                        evidence.append(MatchEvidence(
                            code=FailureCode.UNEXPECTED_ACTUAL,
                            message=f"Unexpected actual exception {i}",
                            actual_index=i,
                            actual_path=actual_path
                        ))
                # Once a mismatch occurs, the current pairing attempt fails. Break the loop.
                break

        # After the loop, check for any remaining unmatched expected matchers.
        if expected_idx < len(expected_matchers):
            for i in range(expected_idx, len(expected_matchers)):
                evidence.append(MatchEvidence(
                    code=FailureCode.UNMATCHED_EXPECTED,
                    message=f"Expected matcher {i} was not matched",
                    expected_index=i,
                ))

        # Check for any remaining unexpected actual exceptions.
        if actual_idx < len(actual_exceptions_for_matching):
            for i in range(actual_idx, len(actual_exceptions_for_matching)):
                actual_exc, actual_path = actual_exceptions_for_matching[i]
                evidence.append(MatchEvidence(
                    code=FailureCode.UNEXPECTED_ACTUAL,
                    message=f"Unexpected actual exception {i}",
                    actual_index=i,
                    actual_path=actual_path
                ))

        # Construct the final MatchResult.
        return MatchResult(
            matched=not evidence, # True if no evidence (no failures), False otherwise.
            evidence=tuple(evidence),
            possible_alternative_pairing=possible_alternative_pairing
        )

    def _flatten_recursive(self, exc: BaseException, current_path: tuple[int, ...]) -> list[tuple[BaseException, tuple[int, ...]]]:
        """Recursively flatten an ExceptionGroup, preserving the path."""
        if not isinstance(exc, ExceptionGroup):
            # If it's not an ExceptionGroup, return it with its current path.
            return [(exc, current_path)]

        flat_exceptions: list[tuple[BaseException, tuple[int, ...]]] = []
        # Iterate through exceptions within the current ExceptionGroup.
        for i, sub_exc in enumerate(exc.exceptions):
            # Recursively call _flatten_recursive for nested exceptions.
            # Append the current index 'i' to the path.
            flat_exceptions.extend(self._flatten_recursive(sub_exc, current_path + (i,)))
        return flat_exceptions
        