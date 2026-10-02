from dataclasses import dataclass

from exception_matcher import FailureCode, GroupMatcher, MatchEvidence, MatchResult


@dataclass(frozen=True)
class StubMatcher:
    exception_type: type[BaseException]
    message: str | None = None

    def match(self, actual: BaseException) -> MatchResult:
        if isinstance(actual, BaseExceptionGroup):
            return MatchResult.failure(MatchEvidence(FailureCode.UNEXPECTED_GROUP, "group"))
        if not isinstance(actual, self.exception_type):
            return MatchResult.failure(MatchEvidence(FailureCode.TYPE_MISMATCH, "type"))
        if self.message is not None and str(actual) != self.message:
            return MatchResult.failure(MatchEvidence(FailureCode.MESSAGE_MISMATCH, "message"))
        return MatchResult.success()


def test_nested_group_boundaries_are_matched_explicitly():
    # EG-B1
    matcher = GroupMatcher([GroupMatcher([StubMatcher(ValueError)])])
    actual = ExceptionGroup("outer", [ExceptionGroup("inner", [ValueError()])])
    assert matcher.match(actual).matched


def test_flatten_and_unwrapped_modes_are_explicit():
    # EG-B2, EG-B3
    nested = ExceptionGroup("outer", [ExceptionGroup("inner", [TypeError("x")])])
    assert GroupMatcher([StubMatcher(TypeError)], flatten=True).match(nested).matched
    assert GroupMatcher([StubMatcher(TypeError)], allow_unwrapped=True).match(TypeError("x")).matched
    result = GroupMatcher([StubMatcher(TypeError), StubMatcher(ValueError)], allow_unwrapped=True).match(TypeError("x"))
    assert result.evidence[0].code is FailureCode.EXPECTED_GROUP


def test_greedy_failure_reports_a_possible_complete_pairing(form_value):
    # EG-B4
    specific = form_value("x", "chosen")
    other = form_value("y", "other")
    matcher = GroupMatcher([StubMatcher(ValueError), StubMatcher(ValueError, specific)])
    actual = ExceptionGroup("values", [ValueError(specific), ValueError(other)])
    result = matcher.match(actual)
    assert not result.matched
    assert result.possible_alternative_pairing
