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
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped:
                if len(self.expected) == 1:
                    return self.expected[0].match(actual)
                else:
                    return MatchResult.failure(
                        MatchEvidence(
                            FailureCode.EXPECTED_GROUP,
                            "expected group",
                            actual_index=0,
                        )
                    )
            else:
                return MatchResult.failure(
                    MatchEvidence(FailureCode.EXPECTED_GROUP, "expected group")
                )

        actual_exceptions = list(actual.exceptions)
        expected_matchers = list(self.expected)
        evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        if not self.flatten:
            matched_indices = set()
            for i, expected_matcher in enumerate(expected_matchers):
                found_match = False
                for j, actual_exception in enumerate(actual_exceptions):
                    if j in matched_indices:
                        continue

                    if isinstance(expected_matcher, LeafMatcher) and isinstance(
                        actual_exception, BaseExceptionGroup
                    ):
                        continue

                    if isinstance(expected_matcher, GroupMatcher) and isinstance(
                        actual_exception, BaseException
                    ):
                        if not isinstance(actual_exception, BaseExceptionGroup):
                            continue

                    result = expected_matcher.match(actual_exception)
                    if result.matched:
                        evidence.extend(
                            result.evidence[0].located(
                                expected_index=i, actual_index=j, prefix=(j,)
                            )
                            if result.evidence
                            else []
                        )
                        matched_indices.add(j)
                        found_match = True
                        break

                if not found_match:
                    evidence.append(
                        MatchEvidence(
                            FailureCode.UNMATCHED_EXPECTED,
                            "unmatched expected",
                            expected_index=i,
                        )
                    )

            unmatched_actual_indices = [
                j for j in range(len(actual_exceptions)) if j not in matched_indices
            ]
            if unmatched_actual_indices:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        "unexpected actual",
                        actual_index=unmatched_actual_indices[0],
                    )
                )

            if len(evidence) > 0 and len(expected_matchers) == len(actual_exceptions):
                possible_alternative_pairing = True

            return MatchResult(
                matched=not evidence, evidence=tuple(evidence), possible_alternative_pairing=possible_alternative_pairing
            )

        else:  # flatten is True
            all_leaves: list[tuple[BaseException, tuple[int, ...]]] = []
            for i, exc in enumerate(actual_exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    for leaf, path in self._flatten_group(exc):
                        all_leaves.append((leaf, (i,) + path))
                else:
                    all_leaves.append((exc, (i,)))

            matched_leaf_indices = set()
            for i, expected_matcher in enumerate(expected_matchers):
                found_match = False
                for j, (actual_leaf, actual_path) in enumerate(all_leaves):
                    if j in matched_leaf_indices:
                        continue

                    result = expected_matcher.match(actual_leaf)
                    # Collect evidence from failures, preserving the failure code and path
                    if result.evidence:
                        for ev in result.evidence:
                            evidence.append(
                                ev.located(expected_index=i, actual_index=j, prefix=actual_path)
                            )
                    
                    if result.matched:
                        matched_leaf_indices.add(j)
                        found_match = True
                        break

                if not found_match:
                    evidence.append(
                        MatchEvidence(
                            FailureCode.UNMATCHED_EXPECTED,
                            "unmatched expected",
                            expected_index=i,
                        )
                    )

            unmatched_actual_indices = [
                j for j in range(len(all_leaves)) if j not in matched_leaf_indices
            ]
            if unmatched_actual_indices:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        "unexpected actual",
                        actual_index=unmatched_actual_indices[0],
                    )
                )

            if len(evidence) > 0 and len(expected_matchers) == len(all_leaves):
                possible_alternative_pairing = True

            return MatchResult(
                matched=not evidence, evidence=tuple(evidence), possible_alternative_pairing=possible_alternative_pairing
            )

    def _flatten_group(self, group: BaseExceptionGroup) -> list[tuple[BaseException, tuple[int, ...]]]:
        leaves = []
        for i, exc in enumerate(group.exceptions):
            if isinstance(exc, BaseExceptionGroup):
                leaves.extend([(leaf, (i,) + path) for leaf, path in self._flatten_group(exc)])
            else:
                leaves.append((exc, (i,)))
        return leaves
