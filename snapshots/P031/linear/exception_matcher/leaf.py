from __future__ import annotations

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
        # EG-A1: rejects exception groups as leaves.
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.UNEXPECTED_GROUP,
                    "expected a leaf exception, got an exception group",
                )
            )

        # EG-A1: matches a leaf exception by isinstance against one type or a tuple of types
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.TYPE_MISMATCH,
                    f"expected type {self.exception_type}, got {type(actual)}",
                )
            )

        # EG-A2: optional string requires an exact exception message
        if self.message is not None and str(actual) != self.message:
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.MESSAGE_MISMATCH,
                    f"expected message '{self.message}', got '{str(actual)}'",
                )
            )

        # EG-A2: optional compiled regular expression uses search
        if isinstance(self.message, Pattern) and not self.message.search(str(actual)):
            return MatchResult.failure(
                MatchEvidence(
                    FailureCode.MESSAGE_MISMATCH,
                    f"message '{str(actual)}' does not match regex '{self.message.pattern}'",
                )
            )

        # EG-A2: optional predicate must return true
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(FailureCode.PREDICATE_REJECTED, "predicate rejected")
            )

        # EG-A3: successful matches contain no failure evidence
        return MatchResult.success()
