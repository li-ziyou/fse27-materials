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
        from .contracts import FailureCode, MatchEvidence, MatchResult

        # EG-A1: Reject exception groups as leaves
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="LeafMatcher cannot match an ExceptionGroup",
                )
            )

        # EG-A1: Check exception type
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type}, got {type(actual)}",
                )
            )

        # EG-A2: Check message if provided
        if self.message is not None:
            actual_message = actual.args[0] if actual.args else ""
            if isinstance(self.message, str):
                if actual_message != self.message:
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.MESSAGE_MISMATCH,
                            message=f"Expected message '{self.message}', got '{actual_message}'",
                        )
                    )
            elif isinstance(self.message, Pattern):
                if not self.message.search(actual_message):
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.MESSAGE_MISMATCH,
                            message=f"Message '{actual_message}' did not match regex '{self.message.pattern}'",
                        )
                    )

        # EG-A2: Check predicate if provided
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="Predicate returned False",
                )
            )

        # EG-A3: Successful match
        return MatchResult.success()
