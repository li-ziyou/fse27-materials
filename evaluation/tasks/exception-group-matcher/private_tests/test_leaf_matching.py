import re

import pytest

from exception_matcher import FailureCode, LeafMatcher


@pytest.mark.parametrize("actual", [TypeError("x"), RuntimeError("x"), Exception("x")])
def test_wrong_types_return_type_mismatch(actual):
    # EG-A1, EG-A3
    result = LeafMatcher(ValueError).match(actual)
    assert not result.matched
    assert [item.code for item in result.evidence] == [FailureCode.TYPE_MISMATCH]


def test_subclasses_and_type_tuples_use_isinstance():
    # EG-A1
    class SpecialValue(ValueError):
        pass

    assert LeafMatcher(ValueError).match(SpecialValue()).matched
    assert LeafMatcher((KeyError, SpecialValue)).match(SpecialValue()).matched


def test_exact_message_and_regex_search_are_distinct(form_value):
    # EG-A2, EG-A3
    needle = form_value("needle", "token")
    actual = form_value("a needle here", "a token here")
    assert not LeafMatcher(ValueError, needle).match(ValueError(actual)).matched
    assert LeafMatcher(ValueError, re.compile(needle)).match(ValueError(actual)).matched
    failure = LeafMatcher(ValueError, re.compile(f"^{needle}$")).match(ValueError(actual))
    assert failure.evidence[0].code is FailureCode.MESSAGE_MISMATCH


def test_predicate_runs_after_type_and_message_and_has_structured_failure():
    # EG-A2, EG-A3
    seen = []
    matcher = LeafMatcher(ValueError, re.compile("ok"), lambda error: not seen.append(error) and error.args == ("ok",))
    assert matcher.match(ValueError("ok")).matched
    result = matcher.match(ValueError("not ok"))
    assert not result.matched
    assert result.evidence[0].code is FailureCode.PREDICATE_REJECTED
    assert len(seen) == 2


def test_groups_are_rejected_even_when_their_type_is_requested():
    # EG-A1, EG-A3
    group = ExceptionGroup("g", [ValueError()])
    result = LeafMatcher(ExceptionGroup).match(group)
    assert not result.matched
    assert result.evidence[0].code is FailureCode.UNEXPECTED_GROUP
