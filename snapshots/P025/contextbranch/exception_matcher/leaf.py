from __future__ import annotations

from collections.abc import Callable
import re
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
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Expected a leaf exception, received a group"))
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"Unexpected exception type: {type(actual).__name__}"))
        text = str(actual)
        if isinstance(self.message, str) and text != self.message:
            return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Exception message {text!r} did not equal {self.message!r}"))
        if hasattr(self.message, "search") and not self.message.search(text):
            return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Exception message {text!r} did not match the pattern"))
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "The leaf predicate rejected the exception"))
        return MatchResult.success()
