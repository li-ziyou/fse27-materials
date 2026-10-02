from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, runtime_checkable


class FailureCode(str, Enum):
    TYPE_MISMATCH = "type_mismatch"
    MESSAGE_MISMATCH = "message_mismatch"
    PREDICATE_REJECTED = "predicate_rejected"
    UNEXPECTED_GROUP = "unexpected_group"
    EXPECTED_GROUP = "expected_group"
    UNMATCHED_EXPECTED = "unmatched_expected"
    UNEXPECTED_ACTUAL = "unexpected_actual"


@dataclass(frozen=True)
class MatchEvidence:
    code: FailureCode
    message: str
    expected_index: int | None = None
    actual_index: int | None = None
    actual_path: tuple[int, ...] = ()

    def located(
        self,
        *,
        expected_index: int | None = None,
        actual_index: int | None = None,
        prefix: tuple[int, ...] = (),
    ) -> MatchEvidence:
        return replace(
            self,
            expected_index=self.expected_index if expected_index is None else expected_index,
            actual_index=self.actual_index if actual_index is None else actual_index,
            actual_path=prefix + self.actual_path,
        )


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    evidence: tuple[MatchEvidence, ...] = ()
    possible_alternative_pairing: bool = False

    @classmethod
    def success(cls) -> MatchResult:
        return cls(True)

    @classmethod
    def failure(cls, *evidence: MatchEvidence, possible_alternative_pairing: bool = False) -> MatchResult:
        return cls(False, tuple(evidence), possible_alternative_pairing)


@runtime_checkable
class Matcher(Protocol):
    def match(self, actual: BaseException) -> MatchResult: ...
