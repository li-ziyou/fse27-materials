from __future__ import annotations

from collections.abc import Callable, Sequence
from re import Pattern

from .contracts import FailureCode, MatchEvidence, MatchResult, Matcher, replace


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

        # EG-A2: Check message
        if self.message is not None:
            # Ensure actual.args is not empty before accessing actual.args[0]
            if not actual.args:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message="Exception has no arguments for message matching",
                    )
                )
            # EG-A2: Check message string exactly
            if isinstance(self.message, str):
                if actual.args[0] != self.message:
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.MESSAGE_MISMATCH,
                            message=f"Expected message '{self.message}', got '{actual.args[0]}'",
                        )
                    )
            # EG-A2: Check message with regex search
            elif not self.message.search(actual.args[0]):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Message '{actual.args[0]}' did not match regex '{self.message.pattern}'",
                    )
                )

        # EG-A2: Check predicate
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="Predicate did not return true",
                )
            )

        # EG-A3: Successful match
        return MatchResult.success()
