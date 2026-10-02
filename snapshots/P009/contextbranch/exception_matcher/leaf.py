from __future__ import annotations

from collections.abc import Callable
from re import Pattern

from .contracts import MatchResult


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
        from .contracts import FailureCode, MatchEvidence, MatchResult
    
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Expected a leaf exception, but got an ExceptionGroup."))

        # EG-A1: Check exception type
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"Expected type {self.exception_type}, but got {type(actual)}."))

        # EG-A2: Check message
        if self.message is not None:
            actual_message = str(actual)
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Expected message '{self.message}', but got '{actual_message}'."))
            elif isinstance(self.message, Pattern):
                if not self.message.search(actual_message):
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Expected message matching regex '{self.message.pattern}', but got '{actual_message}'."))

        # EG-A2: Check predicate
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "Predicate rejected the exception."))

        # EG-A3: Successful match
        return MatchResult.success()
# This line below seems to be a stray comment or artifact that's causing the syntax error.
# Removing it to fix the unterminated string literal.
# n_matcher/leaf.py")
