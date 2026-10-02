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
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "Expected a leaf exception, but got an ExceptionGroup"))

        # EG-A1: Match a leaf exception by isinstance against one type or a tuple of types.
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, f"Expected type {self.exception_type}, but got {type(actual)}"))

        # EG-A2: Optional string requires an exact exception message.
        if self.message is not None and isinstance(self.message, str):
            if str(actual) != self.message:
                return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Expected message '{self.message}', but got '{str(actual)}'"))

        # EG-A2: Optional compiled regular expression uses search.
        if self.message is not None and hasattr(self.message, 'search'): # type: ignore
            if not self.message.search(str(actual)): # type: ignore
                return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, f"Message '{str(actual)}' did not match pattern '{self.message}'"))

        # EG-A2: Optional predicate must return true.
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "Predicate returned false"))

        # EG-A3: Successful matches contain no failure evidence.
        return MatchResult.success()
