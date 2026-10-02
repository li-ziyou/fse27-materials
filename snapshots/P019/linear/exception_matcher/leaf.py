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
        from .contracts import FailureCode, MatchEvidence

        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(FailureCode.UNEXPECTED_GROUP, "LeafMatcher cannot match ExceptionGroup")
            )

        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(FailureCode.TYPE_MISMATCH, f"Expected {self.exception_type}, got {type(actual)}")
            )

        if self.message is not None:
            actual_message = str(actual)
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(
                        MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Expected message '{self.message}', got '{actual_message}'")
                    )
            elif not self.message.search(actual_message):
                return MatchResult.failure(
                    MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Message '{actual_message}' did not match pattern '{self.message.pattern}'")
                )

        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(FailureCode.PREDICATE_REJECTED, "Predicate rejected the exception")
            )

        return MatchResult.success()
