from __future__ import annotations

import re
from collections.abc import Callable
from re import Pattern

from .contracts import FailureCode, MatchEvidence, MatchResult


class LeafMatcher:
    def __init__(
        self,
        exception_type: type[BaseException] | tuple[type[BaseException], ...],
        message: str | Pattern[str] | None = None,
        predicate: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self.exception_type = exception_type
        self.message = message
        self.predicate = predicate

    def match(self, actual: BaseException) -> MatchResult:
        # EG-A1: Reject exception groups as leaves
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "actual is an exception group, not a leaf"))

        # EG-A1: Match by type
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"expected type {self.exception_type}, got {type(actual)}"))

        # EG-A2: Match by message (exact string or regex search)
        if self.message:
            actual_message = str(actual)
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"expected message '{self.message}', got '{actual_message}'"))
            elif isinstance(self.message, re.Pattern):
                if self.message.search(actual_message) is None:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"message '{actual_message}' did not match pattern '{self.message.pattern}'"))
            else:
                # Should not happen with current constructor, but good for robustness
                return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"invalid message matcher type: {type(self.message)}"))

        # EG-A2: Match by predicate
        if self.predicate:
            if not self.predicate(actual):
                return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "predicate returned False"))

        # EG-A3: Successful match
        return MatchResult.success()
