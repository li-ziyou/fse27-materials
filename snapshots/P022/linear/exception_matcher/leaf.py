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
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Leaf matcher cannot match an exception group."))

        if not isinstance(actual, self.exception_type):
            # Ensure the failure evidence includes the actual exception's type for better debugging.
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"Expected type {self.exception_type}, got {type(actual).__name__}."))

        if self.message is not None:
            actual_message = str(actual)
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Expected message '{self.message}', got '{actual_message}'."))
            elif isinstance(self.message, Pattern):
                if not self.message.search(actual_message):
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Message '{actual_message}' did not match pattern '{self.message.pattern}'."))

        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "Predicate did not return true."))

        return MatchResult.success()
