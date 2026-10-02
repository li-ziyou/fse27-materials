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
        raise NotImplementedError("Implement Responsibility B in exception_matcher/groups.py")
