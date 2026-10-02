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


def test_default_mode_rejects_leaf_for_nested_group_position():
    # EG-B1
    matcher = GroupMatcher([StubMatcher(ValueError)])
    result = matcher.match(ExceptionGroup("g", [ExceptionGroup("nested", [ValueError()])]))
    assert not result.matched
    assert FailureCode.UNEXPECTED_GROUP in {item.code for item in result.evidence}


def test_flatten_retains_deep_original_path_on_failure():
    # EG-B2
    actual = ExceptionGroup("0", [TypeError(), ExceptionGroup("1", [KeyError(), ExceptionGroup("2", [ValueError("bad")])])])
    result = GroupMatcher([StubMatcher(ValueError, "wanted")], flatten=True).match(actual)
    mismatch = next(item for item in result.evidence if item.code is FailureCode.MESSAGE_MISMATCH)
    assert mismatch.actual_path == (1, 1, 0)


def test_unwrapped_requires_flag_and_exactly_one_matcher():
    # EG-B3
    assert GroupMatcher([StubMatcher(ValueError)], allow_unwrapped=True).match(ValueError()).matched
    for matcher in (GroupMatcher([StubMatcher(ValueError)]), GroupMatcher([], allow_unwrapped=True), GroupMatcher([StubMatcher(ValueError), StubMatcher(TypeError)], allow_unwrapped=True)):
        result = matcher.match(ValueError())
        assert not result.matched
        assert result.evidence[0].code is FailureCode.EXPECTED_GROUP


def test_pairing_is_expected_order_first_unmatched_actual(form_value):
    # EG-B4
    first = form_value("a", "alpha")
    second = form_value("b", "beta")
    matcher = GroupMatcher([StubMatcher(ValueError, second), StubMatcher(ValueError, first)])
    assert matcher.match(ExceptionGroup("g", [ValueError(first), ValueError(second)])).matched


def test_count_failures_report_expected_and_actual_indexes():
    # EG-B4
    too_few = GroupMatcher([StubMatcher(ValueError), StubMatcher(TypeError)]).match(ExceptionGroup("g", [ValueError()]))
    assert any(item.code is FailureCode.UNMATCHED_EXPECTED and item.expected_index == 1 for item in too_few.evidence)
    too_many = GroupMatcher([StubMatcher(ValueError)]).match(ExceptionGroup("g", [ValueError(), TypeError()]))
    assert any(item.code is FailureCode.UNEXPECTED_ACTUAL and item.actual_index == 1 for item in too_many.evidence)


def test_alternative_flag_is_only_set_when_complete_pairing_exists():
    # EG-B4
    recoverable = GroupMatcher([StubMatcher(ValueError), StubMatcher(ValueError, "specific")]).match(ExceptionGroup("g", [ValueError("specific"), ValueError("other")]))
    impossible = GroupMatcher([StubMatcher(ValueError), StubMatcher(TypeError)]).match(ExceptionGroup("g", [ValueError(), ValueError()]))
    assert recoverable.possible_alternative_pairing
    assert not impossible.possible_alternative_pairing
