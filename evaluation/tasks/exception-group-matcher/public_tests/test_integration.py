from exception_matcher import FailureCode, GroupMatcher, LeafMatcher, matches


def test_group_preserves_leaf_failure_code_and_nested_location():
    # EG-I1, EG-A3, EG-B2
    matcher = GroupMatcher([LeafMatcher(ValueError, "wanted")], flatten=True)
    actual = ExceptionGroup("outer", [ExceptionGroup("inner", [ValueError("other")])])
    result = matches(matcher, actual)
    message_failures = [item for item in result.evidence if item.code is FailureCode.MESSAGE_MISMATCH]
    assert len(message_failures) == 1
    assert message_failures[0].expected_index == 0
    assert message_failures[0].actual_index == 0
    assert message_failures[0].actual_path == (0, 0)


def test_unwrapped_delegation_does_not_skip_leaf_predicate():
    # EG-I1, EG-A2, EG-B3
    matcher = GroupMatcher([LeafMatcher(ValueError, predicate=lambda error: error.args == ("ok",))], allow_unwrapped=True)
    result = matcher.match(ValueError("no"))
    assert not result.matched
    assert result.evidence[0].code is FailureCode.PREDICATE_REJECTED


def test_repeated_types_can_be_disambiguated_by_leaf_contracts(form_value):
    # EG-I1, EG-A2, EG-B4
    left = form_value("left", "alpha")
    right = form_value("right", "beta")
    matcher = GroupMatcher([LeafMatcher(ValueError, left), LeafMatcher(ValueError, right)])
    actual = ExceptionGroup("values", [ValueError(right), ValueError(left)])
    assert matcher.match(actual).matched
