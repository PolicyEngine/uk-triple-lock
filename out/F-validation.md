# Part F validation — 6 October 2026

Pre-registration: `65343e2ee43a359f056ce5a027739509d32ab49f`, committed and pushed with only `docs/METHOD.md` changed before C2 implementation or scoring. [Registration receipt](F-registration.json), [frozen rule](F-rule.md), and [rule-object diff](F-rule-diff.json) retain that record. Threshold bytes are identical between C1 and C2; only treatment and legal exclusion differ.

## Checks completed

| Check | Result | Evidence |
|---|---|---|
| C2 scoring, rule, property and adapter tests, including the explicit unrounded terminal/past correction | **88 passed**, 34.06s, exit 0 | C2 agent's terminal receipt, session `7805`; no filesystem log was captured |
| Final C2, adapter and forecast-only-row parser integration suite | **102 passed**, 15.12s, exit 0 | `.cache/F-history-data-focused-final.log`; includes 14 new parser cases |
| Independent adapter subset | **22 passed**, 17.58s | `.cache/F-adapter-tests.log` |
| Final historical E correspondence and tamper regressions | **54 passed**, 13.77s | `.cache/F-E-correspondence-tests.log`, [correspondence proof](F-E-correspondence.json) |
| Dashboard `bun run test` | **83 passed**, four files, 38.18s | `.cache/F-dashboard-test.log` |
| Dashboard `bun run lint` | **Exit 0**, zero errors, two existing warnings | `.cache/F-dashboard-lint.log` |
| Dashboard `bun run build` | **Exit 0**, successful compile and three static pages | `.cache/F-dashboard-build.log` |

No dashboard source changes or PolicyEngine simulations were made for these checks. Adapter routing tests use a mocked fiscal runner. The Node `DEP0205` deprecation notice remains informational.

Exact combined C2/adapter command:

```sh
.venv313/bin/python -m pytest tests/test_c2_screen.py tests/test_uncertainty.py \
  tests/test_uncertainty_adapter.py -q
```

Final parser-inclusive command:

```sh
.venv313/bin/python -m pytest tests/test_history_data.py tests/test_c2_screen.py \
  tests/test_uncertainty.py tests/test_uncertainty_adapter.py -q \
  > .cache/F-history-data-focused-final.log 2>&1
```

The 14 parser cases confirm that forecast-only fourth-horizon rows remain available to C2 while the legacy calendar-error pool ignores them, that existing observed-error dictionaries retain identical encoding, and that partial observations and nonfinite forecasts are refused.

## Required routing and rule checks

| Requirement | Tests |
|---|---|
| Exclusions follow the legal regime, including a different suspended year; coincidental zeros remain scored | `tests/test_c2_screen.py::test_exclusions_follow_legal_year_and_apply_to_forecast_and_outturn`, `test_accidental_zero_is_scored_and_wholly_suspended_terminal_is_excluded` |
| Annual cells are pooled with equal cell weight after exclusion | `tests/test_c2_screen.py::test_cell_weighted_gap_statistics_do_not_average_origin_percentages`, `test_c2_backtest_pools_annual_exclusions_and_preserves_other_scores` |
| Published earnings never change C2's verdict, over random score tables | `tests/test_c2_screen.py::test_published_earnings_random_score_tables_never_change_c2_verdict` (Hypothesis property) |
| Original primary alone controls routing: passing executes expected value; failing takes (a), even if alternatives pass | `tests/test_c2_screen.py::test_c2_never_promotes_passing_alternative_and_routes_automatically`; `tests/test_uncertainty_adapter.py::test_ruling_c_reads_frozen_screen_and_executes_only_passing_original_primary`, `test_ruling_c_failing_primary_falls_back_even_if_every_alternative_passes`, `test_ruling_c_fallback_keeps_independent_paired_scenarios` |
| C1/C2 threshold bytes are identical | `tests/test_c2_screen.py::test_rule_threshold_objects_are_byte_identical`; [diff](F-rule-diff.json) |
| Handoff records the committed rule and rejects a different SHA, modified scores/inputs, or dry-run authorization | `tests/test_c2_screen.py::test_handoff_records_actual_preregistration_sha_and_frozen_section`, `test_handoff_rejects_rule_and_score_or_input_tampering`, `test_dry_run_handoff_cannot_authorize_a_binding_build`; `tests/test_uncertainty_adapter.py::test_ruling_c_refuses_handoff_with_different_committed_rule_sha`, `test_ruling_c_refuses_real_validated_dry_run_before_fiscal_jobs` |
| Results retain the scenario envelope, effective fallback, C1 failure and quantitative C2 sensitivity | `tests/test_uncertainty_adapter.py::test_results_envelope_carries_existing_runs_and_dated_historical_replay`, `test_pipeline_results_keep_c2_provenance_envelope_and_omission_reason` |
| Screen terminal and past arithmetic preserve the committed unrounded convention | `tests/test_c2_screen.py::test_frozen_candidate_terminal_gap_preserves_unrounded_rates`, `test_frozen_past_years_terminal_gap_preserves_unrounded_boundary` |

## Dry-run verification

[Definitive dry-run receipt](F-dry-run-receipt.json) and [full tables](F-dry-run.md): primary suspended test A reproduces **4/6 terminal hits** and **80.0% annual coverage over 20 non-excluded cells**, with four legal exclusions. All 340 compared C1 means reproduce within `1e-12` after the specified annual exclusion/pooling (maximum roundoff `4.44e-16`); every past-years record is exact. Future baseline and paired draw hashes are unchanged.

The primary, VAR(2), Student-t and Gaussian pass this **dry run**; the annual form fails its suspended switch-CRPS ratio. Published earnings are sensitivities and retain 1/6 test-A terminal coverage. The [first dry run](F-first-dry-run.md) is preserved because it exposed inherited rounding in the shared helper; correction `a99ac2e` restores the already-frozen unrounded convention. A final provenance refresh after the parser fix leaves the **entire `scores.json` byte-identical**, refreshes the handoff's code hashes and regenerates the tables/receipt (root session `27983`, exit 0). All current-input runs remain diagnostics, every form is fiscally ineligible, and the binding C2 score still waits for the post-Budget inputs. No expected value is authorized by these results.

## Full pytest collection with the no-simulation guard

The task requests full pytest and also prohibits PolicyEngine microsimulation runs. The temporary plugin `.cache/f_no_policyengine_runs.py` preserves full collection but skips any test whose fixture tries to instantiate `policyengine_uk.Simulation` or `Microsimulation`. Pure, parameter-only, artifact and mocked-runner checks remain enabled. The simulation skips are disclosed; they are not counted as passes.

Initial guarded run: **908 collected; 844 passed, five failed, 59 skipped**, 285.17s (`.cache/F-pytest.log`). Of the skips, **58** are the explicit no-PolicyEngine-constructor guard and **one** is the existing historical result built before the assumptions block. Two additional failures were E tests that incorrectly required today's broad source fingerprint to equal the retained E calculation's historical fingerprint. Their test-only correction verifies immutable recorded commits and the unchanged fixed-spec execution closure; the 53-test correspondence suite passes. The other three failures are the documented stale results:

- `tests/test_results.py::test_not_stale`
- `tests/test_results.py::test_method_text_percentiles_match_the_past_years_check`
- `tests/test_scenarios.py::test_not_stale`

Guarded run after the E test-only fixes: **916 collected; 854 passed, three documented stale failures, 59 skipped**, 147.68s, exit 1 (root session `43946`, `.cache/F-pytest-final.log`). The skips remain **58** no-PolicyEngine-constructor cases plus **one** historical assumptions-block case. No other failures remained in that run.

Final guarded run after the forecast-only-row parser integration fix and its additional source-correspondence protection: **931 collected; 869 passed, three documented stale failures, 59 skipped**, 176.93s, exit 1 (root session `68692`, `.cache/F-pytest-post-parser.log`). The skips are again **58** explicit no-PolicyEngine-constructor cases plus **one** historical assumptions-block case. The only failures are the three stale nodes listed above. Exact final command:

```sh
GIT_DIR="$PWD/.git-e" TMPDIR="$PWD/.cache/tmp" PYTHONPATH="$PWD/.cache:$PWD/src" \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
.venv313/bin/python -u -m pytest -p f_no_policyengine_runs -ra --durations=20 \
  > .cache/F-pytest-post-parser.log 2>&1
```

## Retained E evidence

Part F makes **no new cold-run proof**. The Microcosm and Enhanced FRS receipts retain their actual calculation head `5d8b53c632fa4d8e69c2624738afd8cf823a9a52`, original source hash, quantities and bytes. [F's correspondence proof](F-E-correspondence.json) checks each recorded full-source hash against immutable Git blobs, recipe hashes against the workers actually recorded, and unchanged engine/dependency/ONS/saved-macro inputs against the current fixed-spec fiscal path. It separately protects redaction and rule/draw helpers through exact AST checks, and protects `history_data.py`'s whole AST except its changed CSV loader. Tamper tests reject changed recorded hashes, engine or projection/spec inputs, rule arithmetic and other historical-data code.

The broad current source fingerprint differs because F changes five modules: `expected_value.py`, `pipeline.py`, `ts_backtest.py`, `ts_uncertainty.py` and `history_data.py`; the proof explicitly records that difference. It does not relabel historical E execution as a run at the F head or certify a new model/data bundle. Validation is complete within the no-simulation constraint. Independent standard Subfleet review remains pending and will be recorded separately.
