from __future__ import annotations

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
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "expected leaf, got group"))

        # EG-A1: LeafMatcher matches a leaf exception by isinstance against one type or a tuple of types
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"expected {self.exception_type}, got {type(actual)}"))

        # EG-A2: optional string requires an exact exception message, optional compiled regular expression uses search, optional predicate must return true.
        if self.message is not None:
            actual_message = actual.args[0] if actual.args else ""
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"expected message '{self.message}', got '{actual_message}'"))
            elif not self.message.search(actual_message):
                return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"expected message matching regex '{self.message.pattern}', got '{actual_message}'"))

        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "predicate returned false"))

        # EG-A3: successful matches contain no failure evidence.
        return MatchResult.success()
