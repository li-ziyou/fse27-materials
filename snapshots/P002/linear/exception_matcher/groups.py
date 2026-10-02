from __future__ import annotations

from collections.abc import Sequence

from .contracts import MatchResult, Matcher, MatchEvidence, FailureCode


class GroupMatcher:
    def __init__(
        self,
        expected: Sequence[Matcher],
        *,
        flatten: bool = False,
        allow_unwrapped: bool = False,
    ) -> None:
        self.expected = tuple(expected)
        self.flatten = flatten
        self.allow_unwrapped = allow_unwrapped

    def match(self, actual: BaseException) -> MatchResult:
        if not isinstance(actual, BaseExceptionGroup):
            if self.allow_unwrapped and len(self.expected) == 1:
                # Delegate to the single expected matcher
                return self.expected[0].match(actual)
            else:
                # If not allowing unwrapped exceptions and multiple expected matchers, it's an error
                return MatchResult.failure(MatchEvidence(FailureCode.EXPECTED_GROUP, "expected a group, got a leaf"))

        actual_exceptions = actual.exceptions
        expected_matchers = list(self.expected)
        match_evidence: list[MatchEvidence] = []
        possible_alternative_pairing = False

        if self.flatten:
            leaves_with_paths = []
            def collect_leaves(exc_group: BaseExceptionGroup, current_path: tuple[int, ...]):
                for i, exc in enumerate(exc_group.exceptions):
                    new_path = current_path + (i,)
                    if isinstance(exc, BaseExceptionGroup):
                        collect_leaves(exc, new_path)
                    else:
                        leaves_with_paths.append({"exception": exc, "path": new_path})

            collect_leaves(actual, ())

            matched_leaf_indices = set()
            for exp_idx, exp_matcher in enumerate(expected_matchers):
                found_match = False
                for leaf_idx, leaf_data in enumerate(leaves_with_paths):
                    if leaf_idx not in matched_leaf_indices:
                        leaf_exc = leaf_data["exception"]
                        leaf_path = leaf_data["path"]
                        sub_result = exp_matcher.match(leaf_exc)
                        if sub_result.matched:
                            # Propagate evidence from sub-match, adjusting indices and paths
                            for ev in sub_result.evidence:
                                match_evidence.append(ev.located(expected_index=exp_idx, actual_index=leaf_idx, prefix=leaf_path))
                            matched_leaf_indices.add(leaf_idx)
                            found_match = True
                            break # Move to the next expected matcher
                if not found_match:
                    match_evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"expected matcher {exp_idx} not matched", expected_index=exp_idx))

            # Check for unexpected actual leaves
            for leaf_idx, leaf_data in enumerate(leaves_with_paths):
                if leaf_idx not in matched_leaf_indices:
                    match_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"unexpected leaf at path {leaf_data['path']}", actual_index=leaf_idx, actual_path=leaf_data['path']))

            if any(ev.code == FailureCode.UNMATCHED_EXPECTED for ev in match_evidence) and \
               any(ev.code == FailureCode.UNEXPECTED_ACTUAL for ev in match_evidence):
                possible_alternative_pairing = True

            if not match_evidence:
                        return MatchResult.success()
            else:
                        # Pass the unpacked list of match_evidence objects to MatchResult.failure
                        return MatchResult.failure(*match_evidence, possible_alternative_pairing=possible_alternative_pairing)

        else: # Default behavior: preserve nested group boundaries
                matched_indices = set()
                for exp_idx, exp_matcher in enumerate(expected_matchers):
                    found_match = False
                    for act_idx, actual_exception in enumerate(actual_exceptions):
                        if act_idx not in matched_indices:
                            sub_result = exp_matcher.match(actual_exception)
                            if sub_result.matched:
                                for ev in sub_result.evidence:
                                    # Propagate evidence from sub-match, adjusting indices and paths
                                    match_evidence.append(ev.located(expected_index=exp_idx, actual_index=act_idx))
                                matched_indices.add(act_idx)
                                found_match = True
                                break
                    if not found_match:
                        match_evidence.append(MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"expected matcher {exp_idx} not matched", expected_index=exp_idx))

                for act_idx, actual_exception in enumerate(actual_exceptions):
                    if act_idx not in matched_indices:
                        match_evidence.append(MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, f"unexpected actual exception at index {act_idx}", actual_index=act_idx))

                if any(ev.code == FailureCode.UNMATCHED_EXPECTED for ev in match_evidence) and \
                    any(ev.code == FailureCode.UNEXPECTED_ACTUAL for ev in match_evidence):
                    possible_alternative_pairing = True

                if not match_evidence:
                    return MatchResult.success()
                else:
                    # Pass the unpacked list of match_evidence objects to MatchResult.failure
                    return MatchResult.failure(*match_evidence, possible_alternative_pairing=possible_alternative_pairing)
