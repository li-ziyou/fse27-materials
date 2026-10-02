from __future__ import annotations
import re
from collections.abc import Callable
from re import Pattern

from .contracts import MatchResult, MatchEvidence, FailureCode


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
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "actual exception is a group, not a leaf"))

        # Check exception type
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"expected type {self.exception_type}, got {type(actual)}"))

        # Check message
        if self.message is not None:
            actual_message = str(actual)
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"expected message '{self.message}', got '{actual_message}'"))
            elif isinstance(self.message, re.Pattern):
                if not self.message.search(actual_message):
                    return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"message '{actual_message}' did not match pattern '{self.message.pattern}'"))
            else:
                # This case should ideally not happen if the constructor is type-checked, but for safety:
                return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"invalid message matcher type: {type(self.message)}"))

        # Check predicate
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "predicate returned false"))

        # All checks passed
        return MatchResult.success()
