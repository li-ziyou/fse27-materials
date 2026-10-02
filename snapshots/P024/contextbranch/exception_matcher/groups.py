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
        if isinstance(actual, BaseExceptionGroup):
            return self._match_group(actual)
        else:
            return self._match_unwrapped(actual)

    def _match_group(self, actual: BaseExceptionGroup) -> MatchResult:
        if self.flatten:
            return self._match_flattened(actual)
        else:
            return self._match_nested(actual)

    def _match_unwrapped(self, actual: BaseException) -> MatchResult:
        if self.allow_unwrapped and len(self.expected) == 1:
            return self.expected[0].match(actual)
        else:
            return MatchResult.failure(
                MatchEvidence(FailureCode.UNEXPECTED_GROUP, "expected a group")
            )

    def _match_nested(self, actual: BaseExceptionGroup) -> MatchResult:
        expected_matchers = list(self.expected)
        actual_exceptions = list(actual.exceptions)
        evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        actual_idx = 0
        while expected_matchers and actual_idx < len(actual_exceptions):
            expected_matcher = expected_matchers[0]
            actual_exception = actual_exceptions[actual_idx]

            if isinstance(expected_matcher, GroupMatcher):
                if isinstance(actual_exception, BaseExceptionGroup):
                    # Preserve nested group boundaries
                    result = expected_matcher.match(actual_exception)
                    if result.matched:
                        expected_matchers.pop(0)
                        actual_exceptions.pop(actual_idx)
                        if result.possible_alternative_pairing:
                            possible_alternative_pairing = True
                        continue
                    else:
                        # If a nested group matcher fails, it's a failure for the current level
                        evidence.extend(
                            e.located(
                                expected_index=self.expected.index(expected_matcher),
                                actual_index=actual_idx,
                                prefix=(actual_idx,),
                            )
                            for e in result.evidence
                        )
                        # Move to the next actual exception if the nested group didn't match
                        actual_idx += 1
                        continue
                else:
                    # Expected a group but got a leaf
                    evidence.append(
                        MatchEvidence(
                            FailureCode.EXPECTED_GROUP,
                            "expected a group",
                            expected_index=self.expected.index(expected_matcher),
                            actual_index=actual_idx,
                            actual_path=(actual_idx,),
                        )
                    )
                    actual_idx += 1
                    continue
            else:
                # Expected a leaf matcher
                result = expected_matcher.match(actual_exception)
                if result.matched:
                    expected_matchers.pop(0)
                    actual_exceptions.pop(actual_idx)
                    if result.possible_alternative_pairing:
                        possible_alternative_pairing = True
                    continue
                else:
                    # If a leaf matcher fails, add its evidence and move to the next actual exception
                    evidence.extend(
                        e.located(
                            expected_index=self.expected.index(expected_matcher),
                            actual_index=actual_idx,
                        )
                        for e in result.evidence
                    )
                    actual_idx += 1
                    continue

        # Handle remaining expected or actual items
        if expected_matchers:
            for i, exp in enumerate(expected_matchers):
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        "unmatched expected",
                        expected_index=self.expected.index(exp),
                    )
                )
        if actual_idx < len(actual_exceptions):
            for i in range(actual_idx, len(actual_exceptions)):
                # In _match_nested, we don't have the direct `actual_path` like in _match_flattened.
                # We need to reconstruct it or pass it down. For now, we'll use a simplified path.
                # A more complete solution would involve a recursive call to get the actual path.
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        "unexpected actual",
                        actual_index=i,
                        actual_path=(i,),  # Placeholder: actual path might be more complex
                    )
                )

        # Check for alternative pairing
        # A more robust check for alternative pairing would involve trying all permutations.
        # For now, we flag it if there are unmatched items on both sides.
        if expected_matchers and actual_idx < len(actual_exceptions):
            possible_alternative_pairing = True

        return MatchResult.failure(
            tuple(evidence), possible_alternative_pairing=possible_alternative_pairing
        )

    def _match_flattened(self, actual: BaseExceptionGroup) -> MatchResult:
        # This is a placeholder for flatten=True logic.
        # It needs to recursively find leaf exceptions and match them.
        # The actual path needs to be preserved.
        # For now, we'll assume a simple case where we can match against leaves directly.
        # A full implementation would involve traversing the group structure.

        # Collect all leaf exceptions with their paths
        leaf_exceptions: list[tuple[BaseException, tuple[int, ...]]] = []

        def collect_leaves(exc: BaseException, path: tuple[int, ...]):
            if isinstance(exc, BaseExceptionGroup):
                for i, sub_exc in enumerate(exc.exceptions):
                    collect_leaves(sub_exc, path + (i,))
            else:
                leaf_exceptions.append((exc, path))

        collect_leaves(actual, ())

        # Now try to match the expected matchers against these leaves
        expected_matchers = list(self.expected)
        evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        leaf_idx = 0
        while expected_matchers and leaf_idx < len(leaf_exceptions):
            expected_matcher = expected_matchers[0]
            actual_leaf, actual_path = leaf_exceptions[leaf_idx]

            # In flattened mode, we expect only LeafMatchers or GroupMatchers that can be flattened
            if isinstance(expected_matcher, GroupMatcher):
                # If flatten is True on the outer matcher, and we encounter a nested GroupMatcher,
                # it means that nested group should also be flattened.
                # For now, we'll treat it as a leaf matcher if it can be flattened.
                # A more complex scenario might involve nested GroupMatchers with flatten=False.
                if expected_matcher.flatten:
                    result = expected_matcher.match(actual_leaf)  # Match against the leaf
                    if result.matched:
                        expected_matchers.pop(0)
                        leaf_idx += 1
                        if result.possible_alternative_pairing:
                            possible_alternative_pairing = True
                        continue
                    else:
                        evidence.extend(
                            e.located(
                                expected_index=self.expected.index(expected_matcher),
                                actual_index=leaf_idx,
                                prefix=actual_path,
                            )
                            for e in result.evidence
                        )
                        leaf_idx += 1
                        continue
                else:
                    # If nested GroupMatcher has flatten=False, it's an error in flattened mode.
                    evidence.append(
                        MatchEvidence(
                            FailureCode.UNEXPECTED_GROUP,
                            "cannot match nested group in flattened mode",
                            expected_index=self.expected.index(expected_matcher),
                            actual_index=leaf_idx,
                            actual_path=actual_path,
                        )
                    )
                    leaf_idx += 1
                    continue
            else:
                # Expected a leaf matcher
                result = expected_matcher.match(actual_leaf)
                if result.matched:
                    expected_matchers.pop(0)
                    leaf_idx += 1
                    if result.possible_alternative_pairing:
                        possible_alternative_pairing = True
                    continue
                else:
                    evidence.extend(
                        e.located(
                            expected_index=self.expected.index(expected_matcher),
                            actual_index=leaf_idx,
                            prefix=actual_path,
                        )
                        for e in result.evidence
                    )
                    leaf_idx += 1
                    continue

        # Handle remaining expected or actual items
        if expected_matchers:
            for i, exp in enumerate(expected_matchers):
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        "unmatched expected",
                        expected_index=self.expected.index(exp),
                    )
                )
        if leaf_idx < len(leaf_exceptions):
            for i in range(leaf_idx, len(leaf_exceptions)):
                _, actual_path = leaf_exceptions[i]
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        "unexpected actual",
                        actual_index=i,
                        actual_path=actual_path,
                    )
                )

        # Check for alternative pairing
        if expected_matchers and leaf_idx < len(leaf_exceptions):
            possible_alternative_pairing = True

        return MatchResult.failure(
            tuple(evidence), possible_alternative_pairing=possible_alternative_pairing
        )
