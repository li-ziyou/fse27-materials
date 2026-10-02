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
        # EG-A1: Reject ExceptionGroup as leaves
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.UNEXPECTED_GROUP, "LeafMatcher cannot match ExceptionGroup"
                )
            )

        # EG-A1: Type matching
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.TYPE_MISMATCH,
                    f"Expected {self.exception_type}, got {type(actual).__name__}",
                )
            )

        # EG-A2: Message matching (string)
        if isinstance(self.message, str):
            if str(actual) != self.message:
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.MESSAGE_MISMATCH,
                        f"Expected message '{self.message}', got '{str(actual)}'",
                    )
                )

        # EG-A2: Message matching (regex)
        elif isinstance(self.message, re.Pattern):
            if not self.message.search(str(actual)):
                return MatchResult.failure(
                    MatchEvidence(
                        FailureCode.MESSAGE_MISMATCH,
                        f"Message did not match regex '{self.message.pattern}'",
                    )
                )

        # EG-A2: Predicate matching
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(FailureCode.PREDICATE_REJECTED, "Predicate did not return true")
            )

        # EG-A3: Successful match
        return MatchResult.success()
