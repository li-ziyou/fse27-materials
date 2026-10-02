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
        from .contracts import FailureCode, MatchEvidence

        # EG-A1: reject exception groups as leaves
        if isinstance(actual, ExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="leaf matcher cannot match an exception group",
                )
            )

        # EG-A1: match by isinstance against one type or a tuple of types
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"expected type {self.exception_type}, got {type(actual)}",
                )
            )

        # EG-A2: optional string requires an exact exception message
        if self.message is not None and actual.args and actual.args[0] != self.message:
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.MESSAGE_MISMATCH,
                    message=f"expected message '{self.message}', got '{actual.args[0]}'",
                )
            )

        # EG-A2: optional compiled regular expression uses search
        if isinstance(self.message, Pattern):
            actual_message_str = ""
            # EG-A2: an optional compiled regular expression uses `search`
            if actual.args:
                arg0 = actual.args[0]
                # Ensure arg0 is a string before passing to search
                if isinstance(arg0, str):
                    actual_message_str = arg0
                elif arg0 is not None: # Handle non-string, non-None arguments by converting to string
                    actual_message_str = str(arg0)
                else: # Handle None argument
                    actual_message_str = "None"
            
            if not self.message.search(actual_message_str):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"expected message matching regex '{self.message.pattern}', got '{actual_message_str}'",
                    )
                )

        # EG-A2: optional predicate must return true
        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="predicate returned false",
                )
            )

        # EG-A3: successful matches contain no failure evidence
        return MatchResult.success()
