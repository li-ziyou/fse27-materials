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
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="LeafMatcher cannot match an ExceptionGroup",
                )
            )

        # EG-A1: LeafMatcher matches a leaf exception by isinstance against one type or a tuple of types
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type}, got {type(actual)}",
                )
            )

        # EG-A2: an optional string requires an exact exception message,
        # an optional compiled regular expression uses `search`,
        # and an optional predicate must return true.
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
                            message=f"Expected message matching regex '{self.message.pattern}', got '{actual_message}'",
                        )
                    )
            else:
                # This case should ideally not happen if message is always str or Pattern
                # but included for robustness.
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Unexpected message type: {type(self.message)}",
                    )
                )

        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(code=FailureCode.PREDICATE_REJECTED, message="Predicate rejected exception")
            )

        # EG-A3: every leaf mismatch returns an unmatched MatchResult with the corresponding FailureCode;
        # successful matches contain no failure evidence.
        return MatchResult.success()
