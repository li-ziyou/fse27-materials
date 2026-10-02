from __future__ import annotations

from collections.abc import Callable
from re import Pattern
import sys

# Define dummy classes for BaseExceptionGroup and ExceptionGroup if not available (Python < 3.11)
# This allows isinstance checks to work without NameError, but they won't have actual group behavior.
# The task implies a modern Python environment, so this is a fallback for older runtimes.
if sys.version_info >= (3, 11):
    BaseExceptionGroup = BaseExceptionGroup
    ExceptionGroup = ExceptionGroup
else:
    # Create simple classes that inherit from BaseException.
    # This is sufficient for isinstance checks and to avoid NameErrors in the logic.
    class BaseExceptionGroup(BaseException):
        def __init__(self, message, exceptions):
            super().__init__(message)
            self.exceptions = exceptions

    class ExceptionGroup(BaseExceptionGroup):
        pass


import sys
from __future__ import annotations

from collections.abc import Callable
from re import Pattern

# Define dummy classes for BaseExceptionGroup and ExceptionGroup if not available (Python < 3.11)
# This allows isinstance checks to work without NameError, but they won't have actual group behavior.
# The task implies a modern Python environment, so this is a fallback for older runtimes.
if sys.version_info >= (3, 11):
    BaseExceptionGroup = BaseExceptionGroup
    ExceptionGroup = ExceptionGroup
else:
    # Create simple classes that inherit from BaseException.
    # This is sufficient for isinstance checks and to avoid NameErrors in the logic.
    class BaseExceptionGroup(BaseException):
        def __init__(self, message, exceptions):
            super().__init__(message)
            self.exceptions = exceptions

    class ExceptionGroup(BaseExceptionGroup):
        pass

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
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.UNEXPECTED_GROUP,
                    message="LeafMatcher cannot match an exception group.",
                )
            )

        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.TYPE_MISMATCH,
                    message=f"Expected type {self.exception_type}, but got {type(actual)}.",
                )
            )

        if isinstance(self.message, str):
            if str(actual) != self.message:
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Expected message '{self.message}', but got '{str(actual)}'.",
                    )
                )
        elif isinstance(self.message, Pattern):
            if not self.message.search(str(actual)):
                return MatchResult.failure(
                    MatchEvidence(
                        code=FailureCode.MESSAGE_MISMATCH,
                        message=f"Message '{str(actual)}' did not match pattern '{self.message.pattern}'.",
                    )
                )

        if self.predicate is not None and not self.predicate(actual):
            return MatchResult.failure(
                MatchEvidence(
                    code=FailureCode.PREDICATE_REJECTED,
                    message="Predicate rejected the exception.",
                )
            )

        return MatchResult.success()
