from __future__ import annotations

from .contracts import MatchResult, Matcher


def matches(expected: Matcher, actual: BaseException) -> MatchResult:
    """Evaluate any matcher through the package's shared result contract."""
    return expected.match(actual)
