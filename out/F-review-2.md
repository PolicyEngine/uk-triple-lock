# Second independent STANDARD review of model-v2 part F: **APPROVE**

M1, L1, L2 and L3 are all fixed. I re-checked the eight required checks in `out/F-review-prompt.md` and none regress. I found no Medium or High issues. There are four new Low/Info notes; none blocks approval.

I reviewed the snapshot at reviewed head `0b4014a` (from `out/F-final.md`). I didn't edit anything, run git, pytest or PolicyEngine, post anything, or read survey or cache data.

## The fixes

**M1 (results contracts under both outcomes): fixed.**
- **Pass outcome:** under ruling c, `expected_value.build` gets the outcome from the frozen handoff. The legacy backtest and past-years scorers run only when the ruling isn't c (`src/triple_lock/expected_value.py:1083-1084`); the old call at line 995 is only in the non-c branch.
- **Fail outcome:** a failing primary returns `effective_ruling: "a"` with its reason and the scenarios (`F-source-diff.patch:1088-1096`). `pipeline.build` then writes `expected_value_omission` and `uncertainty_screen` (`src/triple_lock/pipeline.py:610-632`).
- **No historical re-scoring in the binding build.** Inside `src/triple_lock/`, the only calls to `ev_backtest`, `past_years_check` and `run_candidate_backtest` are in those non-c branches. The verifier's `TU.adequacy` call only re-applies thresholds to saved summaries.
- **Schema:** `docs/RESULTS_SCHEMA.md` (patch lines 818-911) now matches what the code produces: the optional expected value, the provenance, `uncertainty_screen` and `scenario_envelope` fields, and the absence of `backtest`, `past_years_check` and `history_targets` under C2.
- **Python post-build checks:** `_checked_expected_value` (`tests/test_results.py`, patch 3031-3083):
  - rebuilds the verdict from the saved summaries;
  - checks that the expected value is present exactly when the primary passes;
  - checks requested/effective ruling, provenance and envelope parity, and that the omission reason equals `fallback_reason`.

  The legacy EV tests return early when there is no expected value.
- **Synthetic tests:** `tests/c2_results_fixture.py` covers pass and fail, with the scorers replaced by `pytest.fail`. Negative cases cover:
  - a missing expected value, a promoted alternative, a changed verdict and a missing sensitivity (patch 3117-3131);
  - a changed fiscal estimate and a changed paired estimate (3134-3147).
- **Dashboard field names match the real score table.** `getC2Screen` (`dashboard/src/lib/dataHelpers.js`, patch 461-483) reads `annual_gap_cells`, `annual_gap_excluded_cells`, `terminal_coverage.hits`, `terminal_scored_origins`, `realised_gap_pct`, `mean_gap_pct` and `realised_percentile`. All of them appear with those names in `out/uncertainty-c2-dry-run/scores.json` (e.g. lines 12069, 12105-12107, 14046-14058).
- **Dashboard tests:** they render every tab under both outcomes (`Steps.test.jsx`, patch 182-221). `testUtils.js` can switch the whole suite to either synthetic outcome without touching the public results file.
- **Envelope assertion holds on real data.** The test that 2022 earnings equal CPI matches `trajectories.py:264`.

**L1 (dry run read like an authorization): fixed.** `c2_authorization` (`src/triple_lock/ts_uncertainty.py:413-422`) sets `expected_value_authorized` only for a binding run where the primary passes. The validator rejects a mismatch (lines 471-473). The dry-run `selection.json:52-53` and `scores.json:14730-14731` say false and "dry run: no expected value authorization". The standalone mean-path command is explicitly unauthorized (`expected_value.py:911-912`).

**L2 (self-referential score check): fixed within its stated limits.** `scoring_head` must be a 40-character SHA, a real commit and an ancestor of HEAD. It must also agree with the score table's own copy (`ts_uncertainty.py:449-463`). Tests cover a missing, bogus or all-zero head and a valid ancestor (`tests/test_c2_screen.py:381-394`).

**L3 (fallback wording): fixed.** The assumptions strip uses the recorded `fallback_reason` and refuses to publish if it is missing (`pipeline.py:530-537`, `tests/test_c2_assumptions.py`). The dashboard wording matches (`MeanPathScenarios.jsx`, `MethodTab.jsx`).

## Pre-registration and unchanged numbers
- **Pre-registration first.** `65343e2` has parent base `5fc1b19` and changes only `docs/METHOD.md` (`out/F-history.txt:1-7`, `F-registration.json`). Every implementation and scoring commit comes later (03:27 onward, vs 03:14:07 for the pre-registration). That includes `67b10d3`, `a99ac2e`, `4ffd465`, `2ccf381` and the review-fix re-score `c6202c8` (`F-registration-audit.json`).
- **Frozen rule unchanged.** The marked section in `docs/METHOD.md:400-474` matches `F-rule.md`. `committed_c2_rule_hash` compares it with `git show 65343e2:docs/METHOD.md`.
- **Thresholds unchanged.** `C2_RULE` is a deep copy of `C1_RULE`; only the treatment and exclusion differ (`ts_uncertainty.py:39-51`).
- **No numeric changes in the review fixes.** `2ccf381` doesn't touch `ts_backtest.py`. The receipt records `review_fix_numeric_scores_exact` and `future_draw_hashes_unchanged`. Spot checks of `scores.json` match the `F-dry-run.md` table (A/published primary: gap CRPS 1.895, energy 7.870, 66.7% annual coverage, 1/6 terminal hits; past-years percentiles 56.54/92.08).
- **Runbook.** `docs/REBUILD.md:62-77` and lines 105-114 state the job counts and the extra step for each outcome.
- **Validation is reported honestly.** The guarded run (953 collected, 891 passed, 3 known stale failures, 59 skipped) is not called an unguarded full pass (`F-validation.md:91`).

## New findings (none block approval)
- **L-a (Low): missing full stop in the published fallback text.** `fallback_reason` ends with the raw failure list and no full stop (`expected_value.py:795`). `pipeline.py:532-537` then appends " Mean-path variants…", giving e.g. "…exceeds 1.25 Mean-path variants are scenarios…". The test's reason ends in "." (`tests/test_c2_assumptions.py:355`), so it doesn't catch this. Fix: add a closing full stop.
- **L-b (Low): the ancestry check is a weak link.** Any ancestor passes, including `65343e2` itself (`test_c2_screen.py:393`). A score table without `scoring_head` is also accepted (`ts_uncertainty.py:462`, because it uses `.get` with a default). This matches the disclosed "audit link, not authentication" scope. Consider requiring the key.
- **Info: dry-run verdict fields.** In the dry-run `c2_outcome`, `effective_ruling` is still "c" and `expected_value_label` is still "model-conditional" (`selection.json:45-46`, kept on purpose per `test_c2_screen.py:375`). The new authorization fields are what decide.
- **Info: dashboard edge case.** If a terminal statistic were wholly excluded by law and lacked `hits`, `getC2Screen` would return null and fall back to "Unavailable". The current data doesn't hit this.
- **Info: runbook line 81 is now true.** "now nothing may fail" (`docs/REBUILD.md:81`) holds under both outcomes, given the early returns in `tests/test_results.py`.

## Verification limits
- I couldn't run commands, so I didn't re-run any tests. The pass counts come from `F-validation.md` and the `.cache` logs it cites.
- The exported history and registration audit stop at `f56d5b5`. The `.git-e` reflog shows `0b4014a` ("Record completed C2 review fixes and validation…") and `d3d5139` ("Checkpoint second independent C2 review dispatch") after it. I couldn't read those two commits' file lists. That they touch only evidence files rests on their commit subjects and `F-STATE.md`.