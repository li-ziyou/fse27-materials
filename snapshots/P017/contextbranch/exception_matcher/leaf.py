from __future__ import annotations

from collections.abc import Callable
from re import Pattern
import inspect

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
        # EG-A1: Rejects ExceptionGroups as Leaves
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message=f"Expected a leaf exception, but got an ExceptionGroup.",
                )
            )

        # EG-A1: Type Matching
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected exception of type {self.exception_type}, but got {type(actual)}.",
                )
            )

        # EG-A2: Message Matching
        actual_message = str(actual)
        if isinstance(self.message, str):
            if actual_message != self.message:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Expected message '{self.message}', but got '{actual_message}'.",
                    )
                )
        elif isinstance(self.message, Pattern):
            if self.message.search(actual_message) is None:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Message '{actual_message}' did not match pattern '{self.message.pattern}'.",
                    )
                )

        # EG-A2: Predicate Matching
        if self.predicate is not None:
            if not self.predicate(actual):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.PREDICATE_REJECTED,
                        message="Predicate rejected the exception.",
                    )
                )

        # EG-A3: Successful Match
        return MatchResult.success()
