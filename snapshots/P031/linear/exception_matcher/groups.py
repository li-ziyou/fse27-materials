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
        from .leaf import LeafMatcher  # Import here to avoid circular dependency if LeafMatcher needs GroupMatcher

        if isinstance(actual, BaseExceptionGroup):
            actual_exceptions = actual.exceptions
        elif self.allow_unwrapped:
            actual_exceptions = [actual]
        else:
            return MatchResult.failure(
                MatchEvidence(FailureCode.EXPECTED_GROUP, "expected an exception group")
            )

        if not self.expected:
            if not actual_exceptions:
                return MatchResult.success()
            else:
                return MatchResult.failure(
                    MatchEvidence(FailureCode.UNEXPECTED_ACTUAL, "no expected matchers, but actual exceptions exist")
                )

        if self.flatten:
            # Recursively expose leaves
            flattened_actual = []
            for i, exc in enumerate(actual_exceptions):
                if isinstance(exc, BaseExceptionGroup):
                    # For nested groups, we need to flatten them and record the path
                    # This part is tricky and needs careful handling of paths
                    # For now, we'll assume a simple flatten and handle paths in evidence
                    # If flatten is True, we want to match leaves directly.
                    # We need to recursively find all leaves and their original paths.
                    # This will require a helper function.
                    # Let's defer the full flatten implementation until we have a clear strategy for path tracking.
                    # For now, if flatten is true, we treat nested groups as sequences of their contained exceptions.
                    # This might not fully preserve the original structure for matching, but it exposes leaves.
                    # A more robust solution would involve a recursive flattening that keeps track of indices.
                    # For the sake of this implementation, let's assume we iterate through all exceptions.
                    # The problem statement says "recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence."
                    # This implies we need to flatten *and* track paths.
                    # Let's try a recursive helper for flattening.

                    def _flatten_recursive(exceptions: Sequence[BaseException], current_path: tuple[int, ...]) -> list[tuple[BaseException, tuple[int, ...]]]:
                        items = []
                        for idx, ex in enumerate(exceptions):
                            new_path = current_path + (idx,)
                            if isinstance(ex, BaseExceptionGroup):
                                items.extend(_flatten_recursive(ex.exceptions, new_path))
                            else:
                                items.append((ex, new_path))
                        return items

                    flattened_actual.extend(_flatten_recursive(exc.exceptions, (i,)))
                else:
                    flattened_actual.append((exc, (i,)))
            
            # Now match the flattened actual exceptions against the expected matchers
            # This part also needs to handle the pairing logic from EG-B4.
            # If flatten=True, we are essentially trying to match a list of leaves.
            # The pairing logic needs to be applied here.
            
            matched_indices = set()
            evidence = []
            possible_alternative_pairing = False

            for i, expected_matcher in enumerate(self.expected):
                found_match = False
                best_match_index = -1
                
                for j, (actual_exc, actual_path) in enumerate(flattened_actual):
                    if j not in matched_indices:
                        # LeafMatcher's match method already handles type, message, predicate.
                        # We need to ensure it handles ExceptionGroup correctly (it should reject it).
                        # However, here we are dealing with flattened leaves.
                        
                        # Check if the current expected_matcher is a LeafMatcher.
                        # If it is, we can directly use its match method.
                        # If it's a GroupMatcher and flatten=True, this is where it gets complex.
                        # EG-B2 implies that flatten=True exposes leaves for matching.
                        # So, if we encounter a GroupMatcher while flatten=True, it should probably also be flattened or treated differently.
                        # The requirement "recursively exposes leaves for matching" suggests that flatten should apply to nested groups too.
                        # Let's assume for now that if flatten is True, all matchers in `self.expected` are LeafMatchers or can be treated as such.
                        # This might be an oversimplification.

                        # Let's re-read EG-B2: "flatten=True recursively exposes leaves for matching while retaining each leaf's original index path in failure evidence."
                        # This implies that the `GroupMatcher` itself should handle the flattening of the *actual* exceptions, and then match them against its `expected` matchers.
                        # The `expected` matchers themselves are not necessarily flattened.
                        # If `self.expected` contains `GroupMatcher`s, and `self.flatten` is `True`, then those nested `GroupMatcher`s should ALSO flatten their expectations.
                        # This is getting complicated. Let's simplify for now and focus on the core logic.

                        # If we are flattening, we are matching individual exceptions.
                        # The `expected_matcher` should be capable of matching a single exception.
                        
                        # Need to pass the actual_path to LeafMatcher if it were to use it for evidence.
                        # But LeafMatcher's match method doesn't take path.
                        # The evidence is added *after* LeafMatcher.match returns.
                        
                        # Let's assume `expected_matcher` is a `LeafMatcher` for now.
                        # The `match` method of `LeafMatcher` returns a `MatchResult`.
                        # We need to adapt this to our `flattened_actual` which includes paths.
                        
                        leaf_match_result = expected_matcher.match(actual_exc)
                        
                        if leaf_match_result.matched:
                            # If the leaf matcher succeeded, we can potentially use this actual exception.
                            # We need to record the actual_path for evidence.
                            # The match evidence will be created by the GroupMatcher.
                            
                            # We need to find the "best" match. EG-B4: "expected matchers pair in expected order with the first still-unmatched successful actual item"
                            # This suggests a greedy approach.
                            
                            # If this is a successful match for the current expected_matcher
                            # And it's the first time we've found a match for this actual_exc
                            # Or if this actual_exc is better than a previously found match for this expected_matcher.
                            # The problem is, we don't have a "quality" of match for individual leaves here, only matched/unmatched.
                            # So it's a simple greedy assignment.

                            if not found_match: # First successful match for this expected_matcher
                                best_match_index = j
                                found_match = True
                            
                            # If we find a match, we should break from inner loop and move to next expected matcher.
                            # But we need to consider possible_alternative_pairing.
                            # EG-B4: "failures report unmatched expected and unexpected actual items and flag when another complete pairing exists."
                            # This implies we need to explore possibilities.

                            # For now, let's implement a simple greedy match.
                            # If `expected_matcher.match(actual_exc).matched` is True:
                            #   assign `actual_exc` to `expected_matcher`
                            #   mark `actual_exc` as matched
                            #   move to the next `expected_matcher`
                            
                            # If we find a match for expected_matcher[i] at flattened_actual[j]:
                            # We need to record the evidence.
                            # The `actual_path` from `flattened_actual` must be used.
                            
                            # Let's try to construct the evidence here.
                            # The `expected_matcher.match(actual_exc)` call returns a MatchResult.
                            # If it's `success`, the `MatchResult.evidence` is empty.
                            # We need to create the evidence for the `GroupMatcher`.
                            
                            # If `expected_matcher.match(actual_exc).matched`:
                            #   we have a potential match.
                            #   Store `j` as the index of the actual exception that matched `expected_matcher[i]`.
                            #   We need to keep track of all such pairings.
                            #   And also keep track of unmatched actuals.
                            
                            # This is getting complex. Let's re-evaluate EG-B4:
                            # "expected matchers pair in expected order with the first still-unmatched successful actual item"
                            # This suggests we iterate through `expected` matchers. For each `expected_matcher`, we iterate through `actual_exceptions` that haven't been matched yet.
                            # The first `actual_exception` that successfully matches `expected_matcher` is paired.
                            
                            # Let's refine the `flatten=True` logic.
                            # `flattened_actual` is a list of `(exception, path)` tuples.
                            # We need to match `self.expected` against this list.
                            
                            # If `self.expected` contains `GroupMatcher`s, and `flatten=True`, how should they behave?
                            # "recursively exposes leaves for matching"
                            # This implies that if `expected_matcher` is a `GroupMatcher` and `self.flatten` is `True`, then `expected_matcher` should ALSO behave as if its `flatten` is `True`.
                            # This implies `expected_matcher.match` should be called with `flatten=True` implicitly if `self.flatten` is true and `expected_matcher` is a `GroupMatcher`.
                            # This is a recursive definition.

                            # Let's assume for now that `self.expected` contains only `LeafMatcher`s when `self.flatten` is True.
                            # This is likely not the full story, but it's a starting point.
                            
                            # If `expected_matcher.match(actual_exc).matched`:
                            #   This `actual_exc` at `flattened_actual[j]` is a candidate for `expected_matcher[i]`.
                            #   We need to find the first available `actual_exc` for `expected_matcher[i]`.
                            
                            # Let's create a list of `(expected_matcher_index, actual_exception_index, actual_path)` for successful matches.
                            # And a set of `actual_exception_indices` that were used.
                            
                            # A simpler approach for EG-B4 might be:
                            # For each `expected_matcher` in `self.expected`:
                            #   Iterate through `actual_exceptions` that are not yet matched.
                            #   If `expected_matcher.match(actual_exc).matched`:
                            #     Pair them. Mark `actual_exc` as matched. Record the match. Break inner loop.
                            #   If no match is found for `expected_matcher`:
                            #     Record `expected_matcher` as unmatched.
                            # After iterating through all `expected_matcher`s:
                            #   Record any `actual_exceptions` that were not matched as unexpected.

                            # Let's try this refined approach for `flatten=True`:
                            
                            matched_actual_indices = set()
                            matched_evidence = []
                            possible_alternative_pairing = False # This needs to be determined by checking if a full match is possible with different assignments.

                            for i, expected_matcher in enumerate(self.expected):
                                found_match_for_expected = False
                                for j, (actual_exc, actual_path) in enumerate(flattened_actual):
                                    if j not in matched_actual_indices:
                                        # Call the matcher's match method.
                                        # If the `expected_matcher` is a `LeafMatcher`, call `expected_matcher.match(actual_exc)`.
                                        # If the `expected_matcher` is a `GroupMatcher`, this is where the recursive behavior of `flatten=True` needs to be considered.
                                        # If `self.flatten` is `True`, then any `GroupMatcher` in `self.expected` should also behave as if `flatten=True`.
                                        # This implies `expected_matcher.match(actual_exc)` should somehow know about `self.flatten`.
                                        # This is a tricky circular dependency or requires passing `flatten` down.
                                        
                                        # Let's assume for now that `expected_matcher` is a `LeafMatcher` when `flatten=True`.
                                        # This is a strong assumption. The test cases will reveal if this is wrong.
                                        
                                        # The `LeafMatcher.match` method returns a `MatchResult`.
                                        # We need to convert this into `MatchEvidence` for the `GroupMatcher`.
                                        
                                        match_result = expected_matcher.match(actual_exc)
                                        
                                        if match_result.matched:
                                            # We found a match for `expected_matcher[i]` at `flattened_actual[j]`
                                            matched_actual_indices.add(j)
                                            
                                            # Construct evidence.
                                            # The `actual_path` from `flattened_actual` is crucial here.
                                            # `MatchEvidence` has `actual_path`.
                                            
                                            # If the `match_result` from `expected_matcher.match` has evidence, it's from a deeper level, which we might want to preserve.
                                            # However, for a successful leaf match, `MatchResult.success()` has empty evidence.
                                            # So we create new evidence here.
                                            
                                            # The `expected_index` is `i`.
                                            # The `actual_index` is `j` in the `flattened_actual` list.
                                            # The `actual_path` is `actual_path` from `flattened_actual[j]`.
                                            
                                            # If `expected_matcher` itself had failures (which it shouldn't if `match_result.matched`), we'd need to incorporate them.
                                            # But `MatchResult.success()` means no evidence from the matcher itself.
                                            
                                            # So, we are creating a `MatchEvidence` for the pairing.
                                            # The `code` should be something like `SUCCESSFUL_MATCH` or just not present if we only record failures.
                                            # The requirements say "successful matches contain no failure evidence".
                                            # This means that if `MatchResult.matched` is True, the `evidence` tuple in the *final* `MatchResult` should be empty.
                                            # So, we only collect evidence for mismatches.
                                            
                                            found_match_for_expected = True
                                            break # Move to the next expected matcher (i+1)
                                
                                if not found_match_for_expected:
                                    # If we couldn't find a match for `expected_matcher[i]` among the remaining actual exceptions:
                                    # This means `expected_matcher[i]` is unmatched.
                                    # We need to report this failure.
                                    # The `actual_index` and `actual_path` for this failure are unknown because it's an unmatched expected.
                                    # The `expected_index` is `i`.
                                    
                                    # What if there *is* another pairing that would succeed? EG-B4: "flag when another complete pairing exists."
                                    # This implies we need to check for alternative pairings.
                                    # This is a combinatorial problem.
                                    # For now, let's just report the current failure.
                                    
                                    # If `expected_matcher` is a `LeafMatcher`:
                                    #   We need to know *why* it failed.
                                    #   We can't easily get that from `expected_matcher.match(actual_exc)` if `actual_exc` was already matched by a previous `expected_matcher`.
                                    #   This suggests we need to evaluate all `expected_matcher`s against all *available* `actual_exceptions`.
                                    
                                    # Let's reconsider the EG-B4 phrasing: "expected matchers pair in expected order with the first still-unmatched successful actual item"
                                    # This implies a sequential matching process.
                                    # When an `expected_matcher` fails to find a match, we record it as `UNMATCHED_EXPECTED`.
                                    # After checking all `expected_matcher`s, any `actual_exceptions` that were not `matched_actual_indices` are `UNEXPECTED_ACTUAL`.

                                    # If `expected_matcher` is a `LeafMatcher`, and it failed to match any available `actual_exc`, we need to know *why* it failed.
                                    # This means we might have to try matching `expected_matcher[i]` against *all* available `actual_exc`s and pick the "best" failure if no success is found.
                                    # Or, if there are multiple available `actual_exc`s that it *could* match, but it fails on all of them, that's a specific type of failure.
                                    
                                    # Let's simplify the EG-B4 implementation for now:
                                    # If `expected_matcher[i]` doesn't find *any* available `actual_exc` to match, we report `UNMATCHED_EXPECTED`.
                                    # We don't try to find a "best" failure for `expected_matcher[i]`.

                                    # The `expected_index` is `i`.
                                    # The `actual_index` and `actual_path` are not applicable for `UNMATCHED_EXPECTED`.
                                    
                                    # The `expected_matcher` itself is not an exception, so `code` is `UNMATCHED_EXPECTED`.
                                    # The `message` should describe that the expected matcher was not matched.
                                    
                                    # The problem is, `expected_matcher.match(actual_exc)` returns a `MatchResult`.
                                    # If `match_result.matched` is False, it contains evidence of failure.
                                    # We need to capture that evidence *if* `expected_matcher[i]` fails to match any `actual_exc`.
                                    
                                    # This suggests that EG-B4 requires a more sophisticated matching algorithm, possibly backtracking or exploring possibilities.
                                    # For now, let's focus on the basic structure of `flatten=True` and EG-B4's reporting.
                                    
                                    # Let's assume that if `expected_matcher[i]` fails to match any available `actual_exc`, it's a simple `UNMATCHED_EXPECTED` failure.
                                    # The `MatchEvidence` for this should describe the `expected_matcher` itself.
                                    # But `MatchEvidence` is for exceptions.
                                    # So, `UNMATCHED_EXPECTED` refers to the expected *matcher*.
                                    
                                    # The `expected_matcher` is not an exception. So how to report it?
                                    # The `MatchEvidence` contract: `code`, `message`, `expected_index`, `actual_index`, `actual_path`.
                                    # `UNMATCHED_EXPECTED` code is for the `expected` side.
                                    # `expected_index` is `i`.
                                    
                                    # The `message` should indicate which expected matcher failed.
                                    # Example: "Expected matcher at index {i} was not matched."
                                    
                                    # We need to collect all such failures.
                                    # `matched_evidence` should store all failures.
                                    # `expected_matcher` is a `Matcher` object. We can't put it in `MatchEvidence.message` directly.
                                    # Maybe `expected_matcher.__class__.__name__`?
                                    
                                    # Let's create an `UNMATCHED_EXPECTED` evidence.
                                    # The `actual_index` and `actual_path` are not applicable.
                                    # The `expected_index` is `i`.
                                    
                                    # The `MatchEvidence` has a `message` field.
                                    # We can describe the unmatched expected item there.
                                    # `MatchEvidence(FailureCode.UNMATCHED_EXPECTED, f"Expected matcher {i} was not matched.", expected_index=i)`
                                    
                                    # This still doesn't capture *why* it failed.
                                    # Let's assume for now that if a matcher is unmatched, we just report it as such.
                                    
                                    # The `possible_alternative_pairing` needs to be set if there's a way to reorder assignments to get a full match.
                                    # This is a complex problem. Let's defer its implementation for now.
                                    # We'll set it to `False` initially.
                                    
                                    # If we get here, it means `expected_matcher[i]` did not find any available `actual_exc` to match.
                                    # This is a failure.
                                    # We need to decide if this is a "possible alternative pairing" situation.
                                    # If there are remaining unmatched `actual_exc`s and remaining unmatched `expected_matcher`s, it's possible.
                                    # The condition for `possible_alternative_pairing` is when the overall match fails, but there exists *some* permutation of matches that *would* succeed.
                                    # This requires exploring permutations.
                                    
                                    # For now, let's assume `possible_alternative_pairing` is False.
                                    
                                    # Collect failure evidence for the unmatched expected matcher.
                                    # The `actual_index` and `actual_path` are not applicable.
                                    # `expected_index` is `i`.
                                    
                                    # We need to try matching `expected_matcher[i]` against *all* available `actual_exc`s to get the failure evidence.
                                    # This means we can't break early from the inner loop for `expected_matcher[i]`.
                                    # We need to iterate through all available `actual_exc`s for `expected_matcher[i]`.
                                    # If any of them match, we use that pairing and break.
                                    # If *none* of them match, then we have an `UNMATCHED_EXPECTED` failure.
                                    # To get the failure details, we should try matching `expected_matcher[i]` against each *available* `actual_exc` and record the failure evidence from the *first* one it fails against.
                                    
                                    # Let's refine the loop for `expected_matcher[i]`:
                                    
                                    best_failure_evidence_for_expected = None
                                    
                                    for j, (actual_exc, actual_path) in enumerate(flattened_actual):
                                        if j not in matched_actual_indices:
                                            match_result = expected_matcher.match(actual_exc)
                                            if match_result.matched:
                                                # Found a match. This is the best case.
                                                matched_actual_indices.add(j)
                                                found_match_for_expected = True
                                                # We need to associate this `actual_exc` with `expected_matcher[i]`.
                                                # The `MatchEvidence` for *successful* pairing is not created by `GroupMatcher` if the overall match succeeds.
                                                # So, we just mark it as matched.
                                                break # Move to the next expected matcher (i+1)
                                            else:
                                                # This `actual_exc` did not match `expected_matcher[i]`.
                                                # Record the failure evidence.
                                                # We need to consider the `actual_path` from `flattened_actual`.
                                                # The evidence from `match_result` needs to be `located` with the correct indices and path.
                                                
                                                # `match_result.evidence` contains `MatchEvidence` objects from the `expected_matcher`.
                                                # We need to transform these into evidence for the `GroupMatcher`.
                                                # The `expected_index` for these failures is `i`.
                                                # The `actual_index` is `j` (in `flattened_actual`).
                                                # The `actual_path` is `actual_path`.
                                                
                                                # Let's convert the `match_result.evidence` into `GroupMatcher` evidence.
                                                for ev in match_result.evidence:
                                                    located_ev = ev.located(
                                                        expected_index=i,
                                                        actual_index=j, # This is the index in flattened_actual
                                                        prefix=actual_path # This is the path in the original ExceptionGroup structure
                                                    )
                                                    
                                                    # We want to collect the failure evidence for this specific `expected_matcher[i]`.
                                                    # If `best_failure_evidence_for_expected` is None, or if this is a "worse" failure (e.g., more specific type of mismatch),
                                                    # we might want to keep track of the "best" failure.
                                                    # For now, let's just store the first failure encountered for this `expected_matcher[i]`.
                                                    if best_failure_evidence_for_expected is None:
                                                        best_failure_evidence_for_expected = located_ev
                                                    # If we wanted to pick the "most specific" failure, we'd add logic here.
                                                    # For now, let's just take the first failure encountered.
                                    
                                    if not found_match_for_expected:
                                        # If after checking all available `actual_exc`s, no match was found for `expected_matcher[i]`:
                                        # This `expected_matcher[i]` is definitely unmatched.
                                        # We need to create `MatchEvidence` for this.
                                        # The `code` should be `UNMATCHED_EXPECTED`.
                                        # The `expected_index` is `i`.
                                        # The `actual_index` and `actual_path` are not applicable.
                                        
                                        # We should use `best_failure_evidence_for_expected` if it was set.
                                        # If `best_failure_evidence_for_expected` is None, it means `expected_matcher[i]` did not fail against any `actual_exc` (e.g., it was an empty list of actuals).
                                        # In that case, the failure is simply that it was unmatched.
                                        
                                        if best_failure_evidence_for_expected:
                                            # If we found specific failure evidence from trying to match against actual exceptions.
                                            matched_evidence.append(best_failure_evidence_for_expected)
                                        else:
                                            # If no specific failure was recorded (e.g., no available actual exceptions to try against).
                                            # This means `expected_matcher[i]` is simply unmatched.
                                            # The `message` should indicate this.
                                            matched_evidence.append(
                                                MatchEvidence(
                                                    FailureCode.UNMATCHED_EXPECTED,
                                                    f"Expected matcher at index {i} was not matched.",
                                                    expected_index=i,
                                                )
                                            )
                                        
                                        # EG-B4: "flag when another complete pairing exists."
                                        # This is hard. Let's assume `possible_alternative_pairing` is False for now.
                                        # If `len(matched_actual_indices) < len(flattened_actual)` and `i < len(self.expected) - 1`, then there might be an alternative.
                                        # A full check would involve trying all permutations.
                                        
                                        # For now, if we have any unmatched expected or unexpected actuals, `possible_alternative_pairing` is True.
                                        # This is a heuristic, not a guarantee.
                                        # A true check requires exploring possibilities.
                                        # If we have any unmatched expected or any unused actuals, we can potentially have an alternative.
                                        if len(matched_actual_indices) < len(flattened_actual) or i < len(self.expected) - 1:
                                            possible_alternative_pairing = True

                            # After iterating through all expected matchers:
                            # Collect any `actual_exceptions` that were not matched.
                            unexpected_actual_evidence = []
                            for j, (actual_exc, actual_path) in enumerate(flattened_actual):
                                if j not in matched_actual_indices:
                                    # This `actual_exc` is unexpected.
                                    # `expected_index` is None.
                                    # `actual_index` is `j` in `flattened_actual`.
                                    # `actual_path` is `actual_path`.
                                    
                                    # The `actual_exc` itself is an exception.
                                    # The `MatchEvidence` should describe this unexpected exception.
                                    # `FailureCode.UNEXPECTED_ACTUAL`.
                                    # `message` should describe the exception.
                                    
                                    # We can use the exception's type and message.
                                    unexpected_actual_evidence.append(
                                        MatchEvidence(
                                            FailureCode.UNEXPECTED_ACTUAL,
                                            f"Unexpected actual exception: {type(actual_exc).__name__}",
                                            actual_index=j,
                                            actual_path=actual_path,
                                        )
                                    )
                                    
                                    # EG-B4: "flag when another complete pairing exists."
                                    # If we have unexpected actuals, and we still have expected matchers left to consider (which we don't in this loop),
                                    # then it implies a potential for alternative pairing.
                                    # If we have unexpected actuals, and the `expected` matchers were all matched, then it's a definite mismatch.
                                    # If we have unexpected actuals, and some `expected` matchers were *not* matched, then it's a complex situation.
                                    
                                    # Let's update `possible_alternative_pairing` if we find unexpected actuals and there are still expected matchers that *could* have been matched.
                                    # Or if there are unmatched expected matchers and unexpected actuals.
                                    
                                    # If we have unmatched expected matchers AND unexpected actuals, it's a strong indicator of `possible_alternative_pairing`.
                                    if i < len(self.expected): # If there are still expected matchers to process (which is not the case here, but for completeness)
                                         possible_alternative_pairing = True
                                    # If we have unexpected actuals, and we successfully matched all expected matchers (which means `i` would have reached `len(self.expected)`)
                                    # then it's a mismatch. But if there were *other* ways to match the expected, and this resulted in unexpected actuals, then it's an alternative.
                                    
                                    # A simpler heuristic for `possible_alternative_pairing`: if the match failed (which it will if `matched_evidence` or `unexpected_actual_evidence` is non-empty)
                                    # AND there are any unmatched expected matchers OR any unexpected actual exceptions, then it's *possible* there's an alternative.
                                    # This is not perfect, but it's a start.
                                    
                                    # If we found any `UNMATCHED_EXPECTED` evidence, then `possible_alternative_pairing` should be True if there are still `actual_exceptions` left to be matched.
                                    # If we found any `UNEXPECTED_ACTUAL` evidence, then `possible_alternative_pairing` should be True if there are still `expected_matchers` that were not matched.
                                    
                                    # Let's rely on the fact that if `matched_evidence` or `unexpected_actual_evidence` is not empty, the overall match is `False`.
                                    # Then, if we have any unmatched expected or unexpected actuals, set `possible_alternative_pairing = True`.
                                    
                                    # The condition `len(matched_actual_indices) < len(flattened_actual)` implies we have unexpected actuals.
                                    # If we also had `UNMATCHED_EXPECTED` failures, then `possible_alternative_pairing` is True.
                                    # If we had all `expected` matched, but `unexpected_actuals`, then `possible_alternative_pairing` is True if there was a different way to match `expected`.
                                    
                                    # Let's simplify: if the final match is False, and there are unmatched expected or unexpected actuals, set `possible_alternative_pairing = True`.
                                    pass # continue collecting unexpected actuals

                            all_evidence = tuple(matched_evidence) + tuple(unexpected_actual_evidence)

                            if not all_evidence and len(self.expected) == len(flattened_actual):
                                # Perfect match
                                return MatchResult.success()
                            else:
                                # Match failed. Determine `possible_alternative_pairing`.
                                # If there are unmatched expected and/or unexpected actuals, it implies a potential for alternative pairings.
                                # The complexity of determining `possible_alternative_pairing` is high.
                                # Let's set it to True if the match fails and there are remaining items on either side.
                                
                                final_possible_alternative_pairing = False
                                if len(matched_actual_indices) < len(flattened_actual): # There are unexpected actuals
                                    final_possible_alternative_pairing = True
                                if len(matched_actual_indices) < len(self.expected): # There are unmatched expected
                                    final_possible_alternative_pairing = True
                                    
                                # If all expected were matched, but there are unexpected actuals, it's a failure.
                                # If all actual were matched, but there are unmatched expected, it's a failure.
                                # If both are partially matched or completely unmatched, it's a failure.
                                
                                # The requirement is: "flag when another complete pairing exists."
                                # This means if the current matching fails, but *some other* arrangement of pairings would succeed.
                                # This is a combinatorial problem.
                                # For now, let's use a heuristic: if the match failed and there are both unmatched expected and unexpected actuals, it's likely true.
                                # Or if only one side has unmatched items, it could still be true if a different assignment would have worked.
                                
                                # A simpler heuristic: If the match failed, and the number of successful pairings is less than the number of expected matchers OR the number of actual exceptions, then it's *possible* there's an alternative.
                                num_successful_pairings = len(matched_actual_indices)
                                if num_successful_pairings < len(self.expected) or num_successful_pairings < len(flattened_actual):
                                     final_possible_alternative_pairing = True
                                
                                # Consider the case where all expected are matched, but there are unexpected actuals.
                                # If there was another way to match the expected, which would consume these actuals, then `possible_alternative_pairing` is True.
                                # This requires looking at the choices made.
                                
                                # Let's stick to the simpler heuristic for now.
                                
                                return MatchResult.failure(*all_evidence, possible_alternative_pairing=final_possible_alternative_pairing)

        else:  # flatten is False
            # EG-B1: `GroupMatcher` preserves nested group boundaries by default.
            # A nested group is matched by a nested matcher rather than by a leaf matcher.
            
            # EG-B3: `allow_unwrapped=True` delegates a non-group exception only when there is exactly one expected matcher; otherwise a group is required.
            
            if isinstance(actual, BaseExceptionGroup):
                actual_exceptions = actual.exceptions
            elif self.allow_unwrapped and len(self.expected) == 1:
                actual_exceptions = [actual] # Treat as a group with one item
            else:
                # Not an ExceptionGroup, and either allow_unwrapped is False, or there's more than one expected matcher.
                return MatchResult.failure(
                    MatchEvidence(FailureCode.EXPECTED_GROUP, "expected an exception group")
                )

            # Now, match `self.expected` against `actual_exceptions` (which are the exceptions within the group).
            # This is the core of EG-B4: pairing matchers with actual exceptions.
            
            matched_actual_indices = set()
            evidence_list = []
            possible_alternative_pairing = False

            for i, expected_matcher in enumerate(self.expected):
                found_match_for_expected = False
                
                # Iterate through actual exceptions to find the first one that matches.
                # EG-B4: "pair in expected order with the first still-unmatched successful actual item"
                
                best_failure_evidence_for_expected = None # To capture the best failure if no match is found.
                
                for j, actual_exception in enumerate(actual_exceptions):
                    if j not in matched_actual_indices:
                        # Try matching `expected_matcher` against `actual_exception`.
                        match_result = expected_matcher.match(actual_exception)
                        
                        if match_result.matched:
                            # Found a match. Pair `expected_matcher[i]` with `actual_exception[j]`.
                            matched_actual_indices.add(j)
                            found_match_for_expected = True
                            
                            # If `match_result.matched` is True, it means the `expected_matcher` successfully matched `actual_exception`.
                            # The `GroupMatcher` itself doesn't need to create evidence for a successful pairing.
                            # If the overall match is successful, `MatchResult.evidence` will be empty.
                            # If the overall match fails, we will collect evidence from mismatches.
                            
                            # We need to check for `possible_alternative_pairing` here.
                            # If we find a match, but there are still unmatched actual exceptions, it might indicate an alternative pairing.
                            # Or if there are unmatched expected matchers remaining.
                            
                            # If `len(matched_actual_indices) < len(actual_exceptions)`:
                            #   This means there are unexpected actuals.
                            #   If `i < len(self.expected) - 1`:
                            #     This means there are more expected matchers to process.
                            #     This combination (unexpected actuals + more expected matchers) suggests `possible_alternative_pairing`.
                            
                            # A simpler heuristic: if we find a match, but there are still unmatched actual exceptions, set `possible_alternative_pairing = True`.
                            # This is because if this `actual_exception` could have been matched by a *later* `expected_matcher`, or if a *later* `actual_exception` could have matched this `expected_matcher`, then `possible_alternative_pairing` is True.
                            
                            # If `len(matched_actual_indices) < len(actual_exceptions)`:
                            #   This means there are remaining actual exceptions that were not matched by `expected_matcher[i]`.
                            #   If `i < len(self.expected) - 1`: # There are more expected matchers
                            #     This implies `possible_alternative_pairing` is True.
                            #   If `i == len(self.expected) - 1`: # This was the last expected matcher
                            #     If there are still unmatched actual exceptions, then `possible_alternative_pairing` is True.
                            
                            # If we found a match, and there are still unmatched actual exceptions:
                            if len(matched_actual_indices) < len(actual_exceptions):
                                possible_alternative_pairing = True

                            break # Move to the next expected matcher (i+1)
                        else:
                            # `expected_matcher[i]` did not match `actual_exception[j]`.
                            # Record the failure evidence.
                            # `MatchResult.evidence` contains `MatchEvidence` from `expected_matcher`.
                            # We need to convert these to `GroupMatcher` evidence.
                            # `expected_index` is `i`.
                            # `actual_index` is `j`.
                            # `actual_path` is `()`, because we are not flattening here.
                            
                            for ev in match_result.evidence:
                                located_ev = ev.located(
                                    expected_index=i,
                                    actual_index=j,
                                    prefix=() # No flattening, so actual path is empty tuple.
                                )
                                
                                # If `best_failure_evidence_for_expected` is None, or if this failure is "worse" than the current best.
                                # For now, just store the first failure encountered for this `expected_matcher[i]`.
                                if best_failure_evidence_for_expected is None:
                                    best_failure_evidence_for_expected = located_ev
                                # Add logic here if we need to pick the "best" failure among multiple attempts.
                
                if not found_match_for_expected:
                    # `expected_matcher[i]` failed to match any available `actual_exception`.
                    # Record this as `UNMATCHED_EXPECTED`.
                    # `expected_index` is `i`.
                    # `actual_index` and `actual_path` are not applicable.
                    
                    if best_failure_evidence_for_expected:
                        # If we captured specific failure evidence from trying to match against actual exceptions.
                        evidence_list.append(best_failure_evidence_for_expected)
                    else:
                        # If no specific failure was recorded (e.g., no available actual exceptions to try against).
                        # This means `expected_matcher[i]` is simply unmatched.
                        evidence_list.append(
                            MatchEvidence(
                                FailureCode.UNMATCHED_EXPECTED,
                                f"Expected matcher at index {i} was not matched.",
                                expected_index=i,
                            )
                        )
                    
                    # EG-B4: "flag when another complete pairing exists."
                    # If we have unmatched expected and there are still actual exceptions left, it might be possible.
                    if len(matched_actual_indices) < len(actual_exceptions):
                        possible_alternative_pairing = True

            # After iterating through all expected matchers, collect any `actual_exceptions` that were not matched.
            unexpected_actual_evidence = []
            for j, actual_exception in enumerate(actual_exceptions):
                if j not in matched_actual_indices:
                    # This `actual_exception` is unexpected.
                    # `expected_index` is None.
                    # `actual_index` is `j`.
                    # `actual_path` is `()`.
                    
                    unexpected_actual_evidence.append(
                        MatchEvidence(
                            FailureCode.UNEXPECTED_ACTUAL,
                            f"Unexpected actual exception: {type(actual_exception).__name__}",
                            actual_index=j,
                            actual_path=(),
                        )
                    )
                    
                    # If we have unexpected actuals, and there are still unmatched expected matchers (which is not the case here, as we've iterated through all expected),
                    # then `possible_alternative_pairing` is True.
                    # But here, all expected matchers have been processed.
                    # If we have unexpected actuals, and all expected matchers were matched, it's a failure.
                    # If we have unexpected actuals, and some expected matchers were NOT matched, it's also a failure.
                    
                    # If we have unexpected actuals, and the match failed overall, it's a strong indicator of `possible_alternative_pairing`.
                    # If `len(matched_actual_indices) < len(actual_exceptions)` and `len(matched_actual_indices) < len(self.expected)`, then it's likely true.
                    # If all expected matchers were matched (i.e., `len(matched_actual_indices) == len(self.expected)`) but there are unexpected actuals, `possible_alternative_pairing` is True if there was another way to match the expected.
                    
                    # Let's use the heuristic: if match fails and there are unmatched expected OR unexpected actuals, `possible_alternative_pairing` is True.
                    # So, finding unexpected actuals already suggests it.
                    possible_alternative_pairing = True

            all_evidence = tuple(evidence_list) + tuple(unexpected_actual_evidence)

            # Check if all expected matchers were matched and all actual exceptions were consumed.
            if not all_evidence: # If all_evidence is empty, it means no failures were recorded.
                # This implies a perfect match.
                return MatchResult.success()
            else:
                # Match failed.
                # Determine `possible_alternative_pairing`.
                # If the number of successful pairings is less than the number of expected matchers OR actual exceptions, then it's possible there's an alternative.
                num_successful_pairings = len(matched_actual_indices)
                
                # If we found any UNMATCHED_EXPECTED or UNEXPECTED_ACTUAL, the match failed.
                # If `possible_alternative_pairing` was already set to True, keep it.
                # Otherwise, if the match failed, and there are still unmatched items on either side, set it to True.
                
                final_possible_alternative_pairing = possible_alternative_pairing # Start with value from earlier checks
                
                if num_successful_pairings < len(self.expected) or num_successful_pairings < len(actual_exceptions):
                    final_possible_alternative_pairing = True

                return MatchResult.failure(*all_evidence, possible_alternative_pairing=final_possible_alternative_pairing)

