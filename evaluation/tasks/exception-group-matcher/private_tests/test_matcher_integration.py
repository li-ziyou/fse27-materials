from dataclasses import dataclass

from exception_matcher import FailureCode, GroupMatcher, MatchEvidence, MatchResult, matches


@dataclass
class RecordingMatcher:
    accepted: str
    seen: list[BaseException]

    def match(self, actual: BaseException) -> MatchResult:
        self.seen.append(actual)
        if str(actual) == self.accepted:
            return MatchResult.success()
        return MatchResult.failure(MatchEvidence(FailureCode.PREDICATE_REJECTED, "recorded mismatch"))


def test_group_consumes_any_shared_matcher_without_leaf_duplication(form_value):
    # EG-I1
    accepted = form_value("second", "accepted")
    seen = []
    matcher = GroupMatcher([RecordingMatcher(accepted, seen)])
    assert matches(matcher, ExceptionGroup("g", [ValueError(accepted)])).matched
    assert len(seen) == 1 and str(seen[0]) == accepted


def test_nested_matcher_evidence_accumulates_actual_path_prefixes():
    # EG-I1, EG-B1
    matcher = GroupMatcher([GroupMatcher([RecordingMatcher("wanted", [])])])
    actual = ExceptionGroup("outer", [ExceptionGroup("inner", [ValueError("actual")])])
    result = matcher.match(actual)
    failure = next(item for item in result.evidence if item.code is FailureCode.PREDICATE_REJECTED)
    assert failure.expected_index == 0
    assert failure.actual_index == 0
    assert failure.actual_path == (0, 0)


def test_flattened_pairing_uses_leaf_results_and_original_paths():
    # EG-I1, EG-B2, EG-B4
    left_seen, right_seen = [], []
    matcher = GroupMatcher([RecordingMatcher("left", left_seen), RecordingMatcher("right", right_seen)], flatten=True)
    actual = ExceptionGroup("outer", [ExceptionGroup("nested", [ValueError("right")]), ValueError("left")])
    assert matcher.match(actual).matched
    assert [str(item) for item in left_seen] == ["right", "left"]
    assert [str(item) for item in right_seen] == ["right", "left"]


def test_unwrapped_path_preserves_custom_matcher_failure_unchanged():
    # EG-I1, EG-B3
    matcher = GroupMatcher([RecordingMatcher("wanted", [])], allow_unwrapped=True)
    result = matcher.match(ValueError("actual"))
    assert result.evidence == (MatchEvidence(FailureCode.PREDICATE_REJECTED, "recorded mismatch"),)
