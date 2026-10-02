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
        # EG-A1: Reject exception groups as leaves.
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message=f"Expected a leaf exception, but got an ExceptionGroup.",
                )
            )

        # EG-A1: Match by isinstance against one type or a tuple of types.
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type}, but got {type(actual)}.",
                )
            )

        # EG-A2: Optional string requires an exact exception message.
        if self.message is not None and actual.args != self.message:
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.MESSAGE_MISMATCH,
                    message=f"Expected message '{self.message}', but got '{actual.args}'.",
                )
            )

        # EG-A2: Optional compiled regular expression uses search.
        if isinstance(self.message, Pattern) and not self.message.search(str(actual.args)):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.MESSAGE_MISMATCH,
                    message=f"Message '{actual.args}' did not match regex '{self.message.pattern}'.",
                )
            )

        # EG-A2: Optional predicate must return true.
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="Predicate did not return true.",
                )
            )

        # EG-A3: Successful matches contain no failure evidence.
        return MatchResult.success()
