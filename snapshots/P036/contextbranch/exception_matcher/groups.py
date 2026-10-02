from __future__ import annotations

from collections.abc import Sequence

from .contracts import MatchResult, Matcher, MatchEvidence, FailureCode


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
        elif self.allow_unwrapped:
            return self._match_unwrapped(actual)
        else:
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.UNEXPECTED_GROUP,
                    f"Expected group, got {type(actual).__name__}",
                )
            )

    def _match_group(self, actual_group: BaseExceptionGroup) -> MatchResult:
        if self.flatten:
            return self._match_flattened(actual_group)
        else:
            return self._match_nested(actual_group)

    def _match_nested(self, actual_group: BaseExceptionGroup) -> MatchResult:
        if len(self.expected) != len(actual_group.exceptions):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.UNMATCHED_EXPECTED,
                    f"Expected {len(self.expected)} matchers, got {len(actual_group.exceptions)} exceptions",
                )
            )
        
        matched_results = []
        for i, (expected_matcher, actual_exception) in enumerate(zip(self.expected, actual_group.exceptions)):
            result = expected_matcher.match(actual_exception)
            if not result.matched:
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"Matcher {i} failed",
                        expected_index=i,
                        actual_index=i,
                    ).located(prefix=(i,))
                )
            matched_results.append(result)

        return MatchResult.success()

    def _match_nested(self, actual_group: BaseExceptionGroup) -> MatchResult:
        actuals = actual_group.exceptions

        results = [
            [matcher.match(exc) for exc in actuals]
            for matcher in self.expected
        ]

        used = set()
        evidence = []

        for exp_idx, row in enumerate(results):
            act_idx = next(
                (
                    index
                    for index, result in enumerate(row)
                    if index not in used and result.matched
                ),
                None,
            )

            if act_idx is None:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"No exception matched matcher {exp_idx}",
                        expected_index=exp_idx,
                    )
                )
            else:
                used.add(act_idx)

        for act_idx in range(len(actuals)):
            if act_idx not in used:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        f"Exception {act_idx} was not matched",
                        actual_index=act_idx,
                        actual_path=(act_idx,),
                    )
                )

        if not evidence:
            return MatchResult.success()

        return MatchResult.failure(
            *evidence,
            possible_alternative_pairing=self._has_complete_pairing(
                results, len(actuals)
            ),
        )

    @staticmethod
    def _has_complete_pairing(
        results: Sequence[Sequence[MatchResult]],
        actual_count: int,
    ) -> bool:
        if len(results) != actual_count:
            return False

        owner = [-1] * actual_count

        def assign(exp_idx: int, visited: set[int]) -> bool:
            for act_idx, result in enumerate(results[exp_idx]):
                if not result.matched or act_idx in visited:
                    continue

                visited.add(act_idx)
                previous = owner[act_idx]

                if previous == -1 or assign(previous, visited):
                    owner[act_idx] = exp_idx
                    return True

            return False

        return all(assign(exp_idx, set()) for exp_idx in range(len(results)))
    
    def _match_unwrapped(self, actual: BaseException) -> MatchResult:
        if len(self.expected) == 1:
            return self.expected[0].match(actual)
        else:
            # If allow_unwrapped is True but there's more than one expected matcher,
            # it should still require a group.
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.EXPECTED_GROUP,
                    f"Cannot unwrap non-group exception with {len(self.expected)} matchers",
                )
            )
    def _match_flattened(
        self, actual_group: BaseExceptionGroup
    ) -> MatchResult:
        leaves: list[tuple[BaseException, tuple[int, ...]]] = []

        def collect(
            exc: BaseException, path: tuple[int, ...]
        ) -> None:
            if isinstance(exc, BaseExceptionGroup):
                for index, child in enumerate(exc.exceptions):
                    collect(child, path + (index,))
            else:
                leaves.append((exc, path))

        collect(actual_group, ())

        results = [
            [matcher.match(exc) for exc, _ in leaves]
            for matcher in self.expected
        ]

        used: set[int] = set()
        evidence: list[MatchEvidence] = []

        for exp_idx, row in enumerate(results):
            act_idx = next(
                (
                    index
                    for index, result in enumerate(row)
                    if index not in used and result.matched
                ),
                None,
            )

            if act_idx is None:
                for candidate_idx, result in enumerate(row):
                    if candidate_idx in used or result.matched:
                        continue

                    _, path = leaves[candidate_idx]
                    evidence.extend(
                        item.located(
                            expected_index=exp_idx,
                            actual_index=candidate_idx,
                            prefix=path,
                        )
                        for item in result.evidence
                    )

                evidence.append(
                    MatchEvidence(
                        FailureCode.UNMATCHED_EXPECTED,
                        f"No leaf matched matcher {exp_idx}",
                        expected_index=exp_idx,
                    )
                )
            else:
                used.add(act_idx)

        for act_idx, (_, path) in enumerate(leaves):
            if act_idx not in used:
                evidence.append(
                    MatchEvidence(
                        FailureCode.UNEXPECTED_ACTUAL,
                        f"Leaf {act_idx} was not matched",
                        actual_index=act_idx,
                        actual_path=path,
                    )
                )

        if not evidence:
            return MatchResult.success()

        return MatchResult.failure(
            *evidence,
            possible_alternative_pairing=self._has_complete_pairing(
                results, len(leaves)
            ),
        )
