import re

from exception_matcher import FailureCode, LeafMatcher


def test_leaf_matches_type_exact_message_and_pattern_search(form_value):
    # EG-A1, EG-A2
    message = form_value("bad value", "invalid input")
    suffix = form_value(r"value$", r"input$")
    assert LeafMatcher(ValueError, message).match(ValueError(message)).matched
    assert LeafMatcher((TypeError, ValueError), re.compile(suffix), lambda error: bool(error.args)).match(ValueError(message)).matched


def test_leaf_failure_has_one_structured_reason():
    # EG-A3
    result = LeafMatcher(ValueError, "wanted").match(ValueError("actual"))
    assert not result.matched
    assert [item.code for item in result.evidence] == [FailureCode.MESSAGE_MISMATCH]


def test_exception_group_is_not_a_leaf():
    # EG-A1, EG-A3
    result = LeafMatcher(ValueError).match(ExceptionGroup("group", [ValueError()]))
    assert not result.matched
    assert result.evidence[0].code is FailureCode.UNEXPECTED_GROUP
