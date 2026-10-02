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
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="Leaf matcher received an exception group.",
                )
            )

        # EG-A1: Match a leaf exception by isinstance against one type or a tuple of types.
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type} but got {type(actual)}.",
                )
            )

        # EG-A2: Optional string requires an exact exception message.
        if self.message is not None and isinstance(self.message, str):
            if actual.args != (self.message,):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Expected message '{self.message}' but got '{actual.args[0] if actual.args else ''}'.",
                    )
                )

        # EG-A2: Optional compiled regular expression uses search.
        if self.message is not None and isinstance(self.message, Pattern):
            if not self.message.search(actual.args[0] if actual.args else ""):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Message '{actual.args[0] if actual.args else ''}' did not match regex '{self.message.pattern}'.",
                    )
                )

        # EG-A2: Optional predicate must return true.
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="Predicate returned false.",
                )
            )

        # EG-A3: Successful matches contain no failure evidence.
        return MatchResult.success()
