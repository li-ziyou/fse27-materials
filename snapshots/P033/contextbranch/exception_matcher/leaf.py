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
        # EG-A1: Rejects exception groups as leaves.
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="LeafMatcher cannot match an ExceptionGroup",
                )
            )

        # EG-A1: Matches by isinstance against one type or a tuple of types.
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type}, got {type(actual).__name__}",
                )
            )

        # EG-A2: Optional string requires an exact exception message.
        if isinstance(self.message, str):
            if str(actual) != self.message:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Expected message '{self.message}', got '{str(actual)}'",
                    )
                )

        # EG-A2: Optional compiled regular expression uses search.
        if hasattr(self.message, "search"):  # Check if it's a compiled regex pattern
            if not self.message.search(str(actual)):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Message '{str(actual)}' did not match pattern '{self.message.pattern}'",
                    )
                )

        # EG-A2: Optional predicate must return true.
        if self.predicate:
            if not self.predicate(actual):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.PREDICATE_REJECTED,
                        message="Predicate returned False",
                    )
                )

        # EG-A3: Successful matches contain no failure evidence.
        return MatchResult.success()
