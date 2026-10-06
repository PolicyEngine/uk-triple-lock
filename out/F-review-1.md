**REQUEST CHANGES.** One Medium finding: the runbook and results schema don't match what a C2 build will produce. Everything else holds up: the pre-registration, rule freeze, scoring, routing, binding gates and disclosures meet checks 1–8 as specified. Once the Medium is fixed, I'd expect to approve.

I reviewed the worktree at local `model-v2-e` head `b515ac2` (implementation head `e8f19a6`). I made no edits, ran nothing, posted nothing and read no survey data.

## Findings

### M1 (Medium) — Results schema and post-build checks don't match what a C2 build produces
- **Pass outcome:** under ruling c, `expected_value.build` leaves out `backtest`, `past_years_check` and `method` (`src/triple_lock/expected_value.py:1078-1082`).
  - `docs/RESULTS_SCHEMA.md:20-37` documents a C2-pass `expected_value` that includes `backtest` and `past_years_check`.
  - `tests/test_results.py:418` and `tests/test_results.py:473-476` read those keys.
  - The dashboard test `dashboard/src components/Steps.test.jsx:142` reads `data.expected_value.past_years_check`.
- **Fail outcome (automatic a):** `expected_value` is absent from the results altogether. Every `results["expected_value"]` test in `tests/test_results.py` (lines 338–637) would raise a KeyError. Ruling (a) already had this problem, but it is now the automatic C2 route.
- **Consequence:** `docs/REBUILD.md:80-81` says "now nothing may fail" after the rebuild, then runs the dashboard tests. That can't be true under either outcome. Check 6 (runbook covers pass and fail) is therefore only partly met.
- **Fix (small):**
  - Either keep the legacy diagnostics under c, or correct the schema to the actual C2 shape.
  - Then either make `test_results.py` and the dashboard test handle both outcomes, or say plainly in REBUILD.md which checks change under each outcome.

### Low
- **L1 — A dry-run artifact reads like an authorization.** `adequacy()` sets `effective_ruling: "c"` and `expected_value_label: "model-conditional"` whatever the `run_kind` (`src/triple_lock/ts_uncertainty.py:130-135`). Both `out/uncertainty-c2-dry-run/selection.json:45-46` and the handoff's `c2_outcome` therefore say this.
  - It isn't a functional hole: every form has `fiscal_eligible=false`, and `validate_c2_handoff` refuses dry runs (`ts_uncertainty.py:443-444`).
  - It does contradict "no expected value authorized". Suggest making these fields depend on a binding run, or adding a "dry run — not authorized" marker.
- **L2 — The handoff's score check is self-referential.** `score_table_sha256` is a hash of the table carried inside the same manifest (`ts_uncertainty.py:433-438`). If the table, its hash and `c2_outcome` were all edited together, validation would still pass. The clean-tree requirement and deterministic re-scoring limit the risk. Consider recording the scoring HEAD, or cross-checking against a committed `scores.json` or receipt hash.
- **L3 — Fallback wording is misleading.** `pipeline.assumptions` prints "The recorded d955 ruling omits an expected value" (`src/triple_lock/pipeline.py:533`). Under C2 the omission is automatic because the primary failed. The facts block carries the right reason; the text should match.

### Info
- After 28 October, `validate_c2_handoff(require_binding=False)` recomputes the input provenance using today's date. The committed dry-run handoff will then stop validating for standalone scenarios. That is harmless, but worth knowing.
- `out/F-history.txt` stops at `7097e89` and doesn't list `e8f19a6` or `b515ac2`. The local reflog does list them.
- The public PR #24 page shows a newer head, `a531277` ("Export private Git history…"), which isn't in this worktree. I reviewed the local state.

## Required checks

1. **d955(c) treatment — pass.**
   - Earnings is set equal to CPI in both draws and outturns, driven by the legal-regime year list (`ts_backtest.py:536-544`, `401-405`), not by zero values.
   - Annual cells are pooled with equal cell weight (`ts_backtest.py:486-500`, `573-576`).
   - Suspended years stay in terminal compounding, switch counts and floor fractions.
   - The whole-statistic exclusions are correct. With every year suspended, the Burnham plan equals the triple lock exactly. With one or fewer unsuspended years, no lead switch is possible.
   - Tests cover the legal years 1995, 2020 and 2031, an accidental zero, and a wholly suspended window.
   - The dry run reproduces primary A at 4/6 terminal and 80.0% annual coverage on 20 cells with 4 excluded. Published A terminal coverage of 1/6 is disclosed.
2. **Thresholds unchanged — pass.** The `C2_RULE` thresholds are a deepcopy of C1's, and only `treatments` and `exclusion` differ (`ts_uncertainty.py:39-51`, `out/F-rule-diff.json`).
   - A Hypothesis property test shows that published-earnings tables never change the C2 verdict.
   - The C1 verdict still reproduces from the retained artifacts (`tests/test_uncertainty.py:307-312`).
   - The C1 failures and the rule change made after scores were seen are disclosed in the frozen text and in `c1_failure_provenance`.
3. **Routing — pass.**
   - Under C2 the selected form is the primary or nothing (`ts_uncertainty.py:125-126`); no alternative is promoted or averaged in.
   - Ruling c reads the frozen handoff, validates it and never re-scores (adapter tests stub out scoring with `pytest.fail`).
   - A failing primary takes effective ruling (a) with an explicit reason, no expected value, and the paired scenarios kept.
4. **Binding gates — pass.**
   - Before any fiscal job, the handoff is checked for rule SHA, the frozen section matching `git show 65343e2:docs/METHOD.md` byte for byte, input/code hashes, a verdict that reproduces from the scores, binding status and complete origins (`pipeline.py:582-583`).
   - The binding inputs require September 2026 CPI and May–July 2026 AWE (checked against the raw monthly data), dated 28 October OBR means on `obr.uk`, committed bytes, and newly complete origins. A missing March 2022 H4 forecast is caught.
5. **Results — pass, apart from M1.**
   - The scenario envelope carries the central path, the OBR wedge, the dated "Historical replay, April 2017–2026" labelled "not a future forecast", and the paired ±0.5pt paths.
   - `c2_scores` (both treatments plus past-years) and the C1 failure stay in both `results` and `provenance` when the expected value is omitted.
6. **Runbook — partial (see M1).**
   - The commands and job counts check out. The build runs 494 Enhanced FRS jobs under either outcome, i.e. `3U+11` with U = 161 unique full runs. It runs 41 Microcosm jobs if the primary passes and 1 if it fails. The post-build ageing check (validation step 3) adds 211 Enhanced FRS jobs after a pass and 11 after a fail.
   - The d778 bundle comes after the d833 data release.
   - Only `origin/model-v2` was pushed, and PR #24 is open and still a draft.
7. **Forecast-only rows — pass.**
   - Rows with both outturn and error blank are skipped by the calendar-error loader. Partial rows and non-finite forecasts are still refused (`history_data.py:68-75`).
   - Every module outside `load_forecast_errors` keeps an identical syntax tree, so the historical E receipts aren't affected. No new cold run is claimed.
8. **Validation — pass.**
   - The guarded full collection is disclosed honestly: 931 collected, 869 passed, 3 known stale-result failures, 59 skipped (58 of those by the no-simulation guard). It is not described as an unguarded full pass.
   - The guard can't reach PolicyEngine through worker subprocesses: every `run_jobs` test uses a fake runner.

## Verification limits
I had no shell, so I couldn't run `git show` or `git diff`. Commit order comes from the private reflogs:
- `65343e2` was committed at 1791270847 and pushed at 1791270850.
- The first C2 code commit, `67b10d3`, came at 1791271642.
- The first dry-run commit, `25ef918`, came at 1791272034.

That `65343e2` changes `METHOD.md` alone rests on `out/F-history.txt` and the registration receipt. The byte-for-byte match of the frozen rule rests on `committed_c2_rule_hash()` running successfully in the committed dry run. A visual comparison of `METHOD.md:400-474` against `out/F-rule.md` also matches.