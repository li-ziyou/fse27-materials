from __future__ import annotations

from collections.abc import Sequence

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher


def _actual_items(group: BaseExceptionGroup, flatten: bool) -> tuple[tuple[BaseException, tuple[int, ...]], ...]:
    items: list[tuple[BaseException, tuple[int, ...]]] = []

    def visit(current: BaseExceptionGroup, prefix: tuple[int, ...]) -> None:
        for index, exception in enumerate(current.exceptions):
            path = prefix + (index,)
            if flatten and isinstance(exception, BaseExceptionGroup):
                visit(exception, path)
            else:
                items.append((exception, path))

    visit(group, ())
    return tuple(items)


def _has_complete_pairing(matrix: tuple[tuple[bool, ...], ...]) -> bool:
    def search(expected_index: int, used: frozenset[int]) -> bool:
        if expected_index == len(matrix):
            return True
        return any(
            matched and actual_index not in used and search(expected_index + 1, used | {actual_index})
            for actual_index, matched in enumerate(matrix[expected_index])
        )

    return search(0, frozenset())


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
            return MatchResult.failure(MatchEvidence(FailureCode.EXPECTED_GROUP, "Expected an exception group"))

        actual_items = _actual_items(actual, self.flatten)
        results = tuple(
            tuple(matcher.match(exception) for exception, _ in actual_items)
            for matcher in self.expected
        )
        matrix = tuple(tuple(result.matched for result in row) for row in results)
        used: set[int] = set()
        unmatched_expected: list[int] = []
        for expected_index, row in enumerate(results):
            selected = next((index for index, result in enumerate(row) if result.matched and index not in used), None)
            if selected is None:
                unmatched_expected.append(expected_index)
            else:
                used.add(selected)

        if not unmatched_expected and len(used) == len(actual_items):
            return MatchResult.success()

        evidence: list[MatchEvidence] = []
        for expected_index in unmatched_expected:
            evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, "No remaining actual exception matched", expected_index=expected_index))
            for actual_index, child_result in enumerate(results[expected_index]):
                for item in child_result.evidence:
                    evidence.append(item.located(expected_index=expected_index, actual_index=actual_index, prefix=actual_items[actual_index][1]))
        for actual_index, (_, path) in enumerate(actual_items):
            if actual_index not in used:
                evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, "Actual exception was not paired", actual_index=actual_index, actual_path=path))

        alternative = len(self.expected) == len(actual_items) and _has_complete_pairing(matrix)
        return MatchResult.failure(*evidence, possible_alternative_pairing=alternative)
