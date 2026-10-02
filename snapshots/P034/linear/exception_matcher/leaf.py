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
            return MatchResult.failure(
                MatchEvidence(FailureCode.UNEXPECTED_GROUP, "exception group cannot be matched as a leaf")
            )

        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(FailureCode.TYPE_MISMATCH, f"expected {self.exception_type}, got {type(actual)}")
            )

        if isinstance(self.message, str):
            if str(actual) != self.message:
                return MatchResult.failure(
                    MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"expected message {self.message!r}, got {str(actual)!r}")
                )
        elif isinstance(self.message, Pattern):
            if not self.message.search(str(actual)):
                return MatchResult.failure(
                    MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"message {str(actual)!r} does not match pattern {self.message.pattern!r}")
                )

        if self.predicate is not None:
            if not self.predicate(actual):
                return MatchResult.failure(
                    MatchEvidence(FailureCode.PREDICATE_REJECTED, "predicate returned false")
                )

        return MatchResult.success()
