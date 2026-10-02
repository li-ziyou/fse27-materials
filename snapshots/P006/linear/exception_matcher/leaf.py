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
        # EG-A1: Reject exception groups as leaves
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="exception group is not a leaf",
                )
            )
        
        # EG-A1: Check if actual matches the expected type(s)
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"expected {self.exception_type}, got {type(actual).__name__}",
                )
            )
        
        # EG-A2: Check message constraint if provided
        if self.message is not None:
            actual_message = str(actual)
            # Check if it's a compiled regex pattern or a string
            if isinstance(self.message, Pattern):
                # Use .search() for regex patterns
                if not self.message.search(actual_message):
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.MESSAGE_MISMATCH,
                            message=f"message does not match pattern",
                        )
                    )
            else:
                # Exact string match
                if actual_message != self.message:
                    return MatchResult.failure(
                        MatchEvidence(
                            code=FailureCode.MESSAGE_MISMATCH,
                            message=f"expected message '{self.message}', got '{actual_message}'",
                        )
                    )
        
        # EG-A2: Check predicate constraint if provided
        if self.predicate is not None:
            if not self.predicate(actual):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.PREDICATE_REJECTED,
                        message="predicate returned False",
                    )
                )
        
        # All constraints passed
        return MatchResult.success()
