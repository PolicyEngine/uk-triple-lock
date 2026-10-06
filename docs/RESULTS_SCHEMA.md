# Results file: `data/results.json`

`triple-lock-build` writes this file and the dashboard's copy (`dashboard/public/data/results.json`). Every figure the dashboard shows comes from it. Money is £bn a year (nominal) unless a key says otherwise; years are fiscal years named by start year ("2039" = 2039-40); rates are decimals. JSON object keys are strings.

```jsonc
{
  "sample": false,
  "horizon": [2027, ..., 2039], "final_year": 2039, "switch_year": 2030, "distribution_years": [2034, 2039],
  "policies": { "triple_lock": {"label", "rule"}, "burnham_2030": {"label", "rule"} },
  "base_year_weekly": { "year": 2026, "new_state_pension": 241.3, "basic_state_pension": 184.9 },

  "central": {
    "path": { "calendar": {"cpi": {year: rate}, "earnings": {...}}, "statutory": {...},
              "calendar_source": {year: "efo_calendar" | "lted_converted"},
              "statutory_source": {year: "published" | "efo_quarterly" | "calendar"},
              "april_2027_inputs": {...}, "obr_triple_lock_uprating": {year: rate}, "sources": {...} },
    "run": PATH_RUN
  },

  "expected_value": {
    "label": "model-conditional",
    "interpretation": "Model-conditional expected value; original monthly VAR(1) bootstrap passes the frozen C2 statutory screen",
    "method": "C1 160-slot own-form Neyman handoff; full paired PolicyEngine rule runs",
    "provenance": { "decision": "d955", "requested_ruling": "c", "effective_ruling": "c",
                    "ruling": "c", "screen": "c2", "rule_sha", "run_kind": "binding",
                    "scoring_head", "expected_value_authorized": true, "authorization",
                    "c1_failure", "c2_outcome", "c2_scores", "score_table_sha256" },
    "form": "monthly_var1_boot", "adequacy": { ...C2 outcome... },
    "sample_slots": 160, "unique_full_runs",
    "draws": { "n", "seed", "shocks", "form", "model": { lag order, drift by year, ... } },
    "calibrations": { "means_shift": { "draws": "shifted", "ess" },
                      "shift_dynamics[...].window.treatment": { "draws": "shifted", "ess", "targeted", "window", "treatment" }
                                                          | { "draws": "shifted", "error" } },
                      // Optional historical tilts that fail are recorded here, without a sensitivity estimate.
    "gap_by_calibration": { name: { "mean_gap_gbp_week", "gap_gbp_week": {p10..p90}, "identical_share",
                                    "mean_rate_minus_earnings_2034_2039": {"triple_lock", "burnham_2030"} } },
    "primary": "means_shift",
    "strata": [ { "stratum", "probability", "paths", "unique_paths", "sensitivity_paths" } ],
    "identical_rates": { "probability", "included_in_strata", "check_run": null | { "draw", "largest_abs_saving_bn" } },
    "datasets": { "primary": "enhanced_frs_2024_25", "sensitivity": "populace_uk_2023" },
    "estimates": { "primary" | "sensitivity": { output: { year: MONTE_CARLO_ESTIMATE } } },
                 // output: "gross", "net", "component.<name>", "households_losing_pct", "largest_record_bn",
                 // "net_excluding_largest_record"
    "paired_difference": { "gross" | "net": { year: MONTE_CARLO_ESTIMATE } },   // Microcosm minus Enhanced FRS
    "sensitivities": { calibration: { "ess", "effective_runs", "gross": {year: MONTE_CARLO_ESTIMATE}, "net": {...}, ... } },
    "paths": [ { "draw", "stratum", "times_drawn", "times_drawn_sensitivity", "gap_2039_gbp_week", "statutory", "rates",
                 "outputs": { "primary" | "sensitivity": { output: { year: value } } }, "weight_ratio" } ],
    "uncertainty_reporting": { "monte_carlo": "precision of this model path set only",
                               "model_and_mean_path": "scenario envelope; not a probability interval" }
  },

  "uncertainty_ruling": { "decision": "d955", "requested_ruling": "c",
                          "effective_ruling": "c" | "a", "ruling": "c" | "a",
                          "screen": "c2", "rule_sha", "run_kind": "binding",
                          "scoring_head", "expected_value_authorized": true | false, "authorization",
                          "c1_failure", "c2_outcome", "c2_scores", "score_table_sha256", "fallback_reason"? },
  "uncertainty_screen": { "screen": "c2", "rule_sha", "run_kind": "binding",
                          "scoring_head", "expected_value_authorized": true | false, "authorization",
                          "c1_failure", "c2_outcome", "c2_scores", "score_table_sha256" },
  "expected_value_omission": { "requested_ruling": "c", "effective_ruling": "a", "reason" },
                          // present only when expected value is omitted
  "mean_path_scenarios": { "interpretation": "paired mean-path scenarios; not a probability interval",
                           "adequacy_gate_applies": false, "provenance", "sample_slots", "baseline_full_runs",
                           "scenarios": { "earnings_minus_0_5pp" | "earnings_plus_0_5pp": {
                             "calendar_earnings_delta", "from_year": 2031, "unique_full_runs",
                             "paired_difference", "scenario_path_set" } } },
  "scenario_envelope": { "interpretation": "scenario envelope; not a probability interval",
                         "central": { "label", "path", "run": PATH_RUN },
                         "obr_wedge": { "label", "path", "run": PATH_RUN },
                         "last_decade_replay": {
                           "label": "Historical replay, April 2017–2026",
                           "interpretation": "historical legal replay; not a future forecast",
                           "years": [2017, ..., 2026], "switch_year": 2017,
                           "statutory": { "cpi", "earnings" }, "suspended_earnings_year": 2022,
                           "model_years": [2024, 2025, 2026], "counterfactual" },
                         "paired_earnings_mean_paths": { ...mean_path_scenarios... } },

  "trajectories": {
    "paths": [ { "id": "central" | "random" | "monthly_p50" | "monthly_p90", "label", "source", "selection"?,
                 ...PATH_RUN, "households": { "examples": {id: {...}}, "results": {id: {policy: {output: {year: £}}}} } } ],
                 // "selection" (the drawn paths, not "central"): "draw", "gap_gbp_week", "cdf_position", the random
                 // path's "seed" or a quantile path's "quantile", "quantile_gap_gbp_week", "band", "n_candidates",
                 // "candidates_effective_sample"; and where the path's 2039-40 gap in the full new State Pension sits
                 // among the primary calibration's weighted draws ("draws_compared" of them):
                 // "gap_percentile_2039" (% of the weight below it plus half the weight tied with it) and
                 // "larger_gap_pct_2039" (% of the weight on draws with a larger gap)
    "models": { "boot" | "tcop" | "gauss": { gap quantiles, deflation shares, switches per year, ... } },
    "gap_statistics": {...},
    "history": { "years", "cpi", "earnings", "actual_rise", "actual_weekly", "groups": [ past-years counterfactuals ],
                 "triple_lock": { "rate", "binding", "earnings_published", "index": {"triple_lock", "cpi", "earnings", "floor"} } },
    "backtest": { "statutory": {...}, "calendar": {...} }
  },

  "coverage": { "year": 2026, "dwp": { ..., "years": ["2026/27", ..., "2030/31"] },
                "rows": [ { "key", "label", "dwp", "primary", "primary_gb", "primary_gb_over_dwp",
                            "sensitivity", "sensitivity_gb", "sensitivity_gb_over_dwp" } ],   // 2026-27
                "by_year": { year: { "dwp_year": "2027/28" | null, "rows": [ ...as above... ] } },
                // 2026-2030, 2034 and 2039 on the central path under the triple lock; "dwp" is null (and no
                // *_over_dwp) past 2030-31, where DWP's tables stop. "<dataset>" is the UK; "<dataset>_gb" Great
                // Britain (households in England, Scotland and Wales), like for like with DWP
                "model_note", "datasets": { name: { "dataset", "model", "max_age", "records", "people",
                                                    "pension_type_people", "state_pension_age_people" } } },
  "dwp_uprating_analysis": { "saving_bn": { "2039": { "nominal": 15, "real_2025_26_prices": 11 }, ... }, "url", ... },
  "benchmarks": [ { "id", "publisher", "title", "date", "url", "figure_text", "comparison", "our_metric", "our_value",
                    "like_for_like", "note", "verified" } ],
  "method_limitations": [ ... ],
  "assumptions": [ { "key": "population" | "paths" | "benefits", "title", "text", "facts": {...} } ],
  "provenance": { "git_revision", "git_dirty", "source_hashes", "input_hashes", "engine_hashes", "packages",
                  "model", "datasets", "generated_at", "uncertainty_ruling", "uncertainty_screen" }
}
```

For d955(c), `expected_value` exists only if the **original monthly VAR(1) bootstrap primary** passes the binding [C2 screen](METHOD.md#model-v2-statutory-uncertainty-screen-pre-registration-c2). Its label is **model-conditional**. Passing alternatives are reported in `c2_outcome` individually; they never replace the primary or get averaged. If the primary fails, the build automatically records requested ruling `c`, effective ruling `a` and the failure reason, and omits `expected_value`. `scenario_envelope` remains beside the expected value after a pass and is the output after a failure: central path, OBR-wedge run, recorded historical last-decade replay (April 2017–2026, with its own model years) and paired ±0.5-point calendar-earnings mean paths from 2031. Each entry carries its saved full-run result or paired path-set estimate and recorded years, with no probability-interval claim. The historical replay is labelled with its period and is not combined into a future-year numerical range.

`uncertainty_screen.rule_sha` is the committed C2 pre-registration `65343e2ee43a359f056ce5a027739509d32ab49f`; the handoff must match it before execution. Its `run_kind` is `binding`; a handoff labelled `dry_run` records a diagnostic run on pre-Budget inputs and cannot authorize an expected value. `expected_value_authorized` is true only for a binding primary pass; `authorization` records a dry run, a binding pass or the automatic fallback. `scoring_head` records the source commit used for scoring, validated as an ancestor of the checked-out build. `c1_failure` discloses that all five forms failed the original frozen C1 screen on test A with published earnings (1/6 terminal coverage, from the 2021 furlough base effect), the post-scoring rule change and the retained C1 record. `c2_outcome` retains the original-primary pass/fail and each alternative's result and failures. `c2_scores` carries both suspended and published summary tables, past-years percentiles, origins and legal-regime metadata beside that outcome; `score_table_sha256` identifies the complete handoff table, which also retains per-origin rows. The tables record legal exclusions and denominators. The rule-section hash, source snapshot and binding inputs support validation of the outcome and detect accidental changes; these hashes are audit evidence, not protection against jointly rewriting scores and their hashes. Suspended scoring, including its 5th–95th percentile past-years check, determines C2. Published-earnings scores, including their past-years percentile, remain sensitivities. Screen, rule SHA, C1 disclosure, C2 outcome and its quantitative sensitivity are carried in both results and provenance even when expected value is absent.

C2 results consume the frozen handoff; the build does not run the legacy expected-value backtest or past-years scorer. Consequently `expected_value.backtest`, `expected_value.past_years_check` and `expected_value.history_targets` are absent under C2. Earlier results retain their legacy diagnostics and prose `method`. C2 results instead retain the adapter's `method` string shown above and the frozen summary tables and past-years percentiles in `uncertainty_screen.c2_scores`. Results verification reconstructs the C2 verdict from those saved summaries, checks the requested and effective rulings against expected-value presence, and recomputes every published fiscal estimate and paired difference from the saved path records when an expected value is present. An automatic fallback checks the omission reason and all scenario-envelope entries. Neither outcome requires a new historical re-score.

Every reported Monte Carlo SE describes precision of the model path set. Path-sampling and first-phase variance components are recorded separately from the model/mean-path scenario envelope; none is a measure of that envelope's uncertainty. The 160 estimator slots preserve replacement multiplicities. The exact 40-slot paired subsample is recorded through `times_drawn_sensitivity` and each stratum's `sensitivity_paths`, including zero-stratum probability once.

`MONTE_CARLO_ESTIMATE` contains `mean`, `se`, `se_path_sampling`, `se_first_phase`, `variance_path_sampling`, `variance_first_phase`, `plus_minus_95` and `mc_interval_95`. The last two describe Monte Carlo precision conditional on the model path set. The assumptions strip quotes only `mean` and `se`; the other precision fields remain in the results.

`provenance.model` (from model-v2; a file built earlier has `release_bundle`, the policyengine.py bundle): what the runs ran on, as `datasets.provenance` records it: `model_package`, `model_version` (the installed policyengine-uk, which `packages` also gives), `core_version`, `certified` (false: no policyengine.py release certifies the pair) and `certification` (why), `runtime_dataset` (its logical name), `dataset` (the registry name, with its revision), `runtime_dataset_uri`, `runtime_dataset_sha256`, `data_package`, `data_version`, `data_built_with` and `data_certified_elsewhere`. `provenance.datasets.primary` is the registry name.

`assumptions` (`pipeline.assumptions`): what the headline figures are conditional on, in the order the dashboard's "What these figures assume" strip shows them. The pipeline writes the `title` and `text` from how the runs treated the population (each path run's `fixed_inputs.population`) and from the assembled results, so the strip changes when the model does; `facts` holds every number the text quotes, each equal to a figure elsewhere in the file (`test_assumptions_quote_the_results`). If a figure the block quotes is missing, or a value has no wording (a population treatment, calibration, shock model or dataset the pipeline has not been taught to describe), the build fails (`pipeline.MissingFigure`) rather than publish a strip that no longer describes the model. The dashboard renders the block's valid items (a non-empty `key`, `title` and `text`; the first item of each key), and nothing if none is valid; it computes the strip from the figures below only for a file with no `assumptions` key (built before the block existed). `scripts/check_assumptions.py` checks a results file (the #14 §5 pilot's, say) can carry the block, in seconds.
- `population`: `weights`, `ages` and `pension_types` as the path runs recorded them (see `fixed_inputs` below; the central run and every trajectory must record the same, or the build fails), `final_year`, `data_year`, `state_pension_age` (the ages in the final year) and `state_pension_age_settled_year` (from when it stops changing), and the primary dataset's `max_age`. With ages and types both from the survey year, the build also fails if the held type counts move after the State Pension age settles;
- `paths`: `year`, `measure` ("gross"), `calibration` (`expected_value.primary`), `reweightings` (how many `expected_value.sensitivities` named `shift_dynamics*`, the reweightings to past dynamics the text describes) and `reweightings_with_floor`, `floor`, `other_sensitivities` (every other sensitivity, left out of the range and counted in the text), `lowest` {calibration, mean, se} and `highest` {calibration, mean, se, effective_runs} of their final-year expected saving, and `shock_models_run` / `shock_models_not_run` (keys of `trajectories.models` by `runs_paths`; a model with no short name is named by its `label`);
- `benefits`: `coverage_year`, `pension_credit_claims_m` and `housing_benefit_pension_age_bn` {primary, dwp} (from `coverage.rows`: `primary` is the row's `primary_gb` where `model_geography` is "Great Britain", as from model-v2, and its UK `primary` otherwise), `model_geography`, `dwp_geography`, and `paired_difference_net` {year, mean, se, paths, dataset}: `expected_value.paired_difference.net` in the final year, the number of paired paths and the sensitivity dataset's name.

`PATH_RUN` (engine.run_path):
- the inputs: `statutory`, `calendar`, `applied_growth`;
- the checks: `path_following` (from model-v2 with `model_statutory_inputs`: the model's September CPI and May–July AWE read back, against the path's), `not_moving`, `also_moving`, `checks`;
- the rules on the path: `rates`, `rate_sources`, `weekly`, `applied_new_state_pension`. `rate_sources` names what set each rise: for the triple lock `floor` whenever neither input exceeds 2.5%, else `earnings` or `cpi` (CPI when they tie); for the Burnham plan `triple_lock` before the switch, then `earnings_path`, `cpi` (above 2.5%) or `floor`. A scenario run's specified years are `specified` for that policy (the plan stays `triple_lock` before the switch); no path in this file has any, and the dashboard reads the label as "a specified rate";
- the inputs held the same under both rules: `fixed_inputs` {data_year, population {weights: "survey" | "ons_projection" | "reweighted", ages: "survey_year" | "adjusted" | "aged_forward", pension_types: "survey_year" | "cohort" | "model"} (`engine.population_treatment`: weights and ages as the dataset load declares them (`engine.LOADED_POPULATION`), checked against what the run pins and the ages the model computes; pension types by the rule `pinned_inputs` follows (`engine.PENSION_TYPE_RULE`)), state_pension_age {year: [ages]} (from model-v2: the youngest survey age, in whole years, with anyone over State Pension age that year and the youngest from which everyone is, one value when they coincide, as policyengine-uk's timetable by date of birth puts them; a file built earlier gives the State Pension age itself), pension_credit_guarantee_single_weekly {year: £}, held_pension_type_records {year: {BASIC, NEW, NONE: records}}, held_pension_type_people {year: {BASIC, NEW, NONE: weighted people}}}; the type counts are read back from the model after pinning;
- the money: `saving_bn` {year: {gross, net, household_income_change, components, components_by_variable, decomposition_residual, net_model_float32, gb: {gross, net, components}}} and `totals_bn` {policy: {year: {<group>, gov_balance, gov_balance_model, household_net_income, basic_state_pension, new_state_pension, variables: {variable: £bn}, tax_variables: [...], gb: {<group>, gov_balance, household_net_income, basic_state_pension, new_state_pension}}}}. The groups (`config.FISCAL_GROUPS`, plus `other_spending` and `other_tax`) and `variables` cover every variable in policyengine-uk's `GOV_TAX_VARIABLES` and `GOV_SPENDING_VARIABLES` (State Pension in its three parts; `tax_variables` names the taxes). `gov_balance` is their float64 sum, taxes less spending, so taxes added and spending subtracted the components are `net` by construction (`decomposition_residual` is float64 rounding); `gov_balance_model` and `net_model_float32` are the model's own float32 figures, which each run checks the sum against (a level to 1e-4 £bn, the change to 1e-5). `gb` is Great Britain (households in England, Scotland and Wales). A file built before model-v2 has the eight named groups only;
- the people: `poverty_pct` {policy: {year: {...}}}, `households_affected` {year: {losing_pct, mean_loss_gbp}}, `distribution` {2034 | 2039: {by_decile, by_quintile, by_region, by_hh_type, by_tenure, by_age_band, households_affected}};
- the single household: `largest_household` {contribution_bn, share_of_income_change, income_change_excluding_bn} for the final year and `concentration_by_year` {year: {contribution_bn, share_of_income_change}}. FRS records are licensed data, so the file gives only a record's contribution to the totals, never its identifier, weight or amounts (`pipeline.redact_records`; `test_no_survey_record_is_published`);
- `dataset` (the logical name) and, in a job's own output, `model` (the provenance above; the build moves the central run's to `provenance.model`).

Signs:
- `saving_bn.gross` is triple-lock minus plan State Pension spending;
- `saving_bn.net` is plan minus triple-lock `gov_balance`;
- `components` are plan minus triple lock.

## Scenario runs: `data/scenarios/NAME.json`

Every full build (`triple-lock-build`) writes one of these for each scenario, and `triple-lock-build --scenario NAME` rewrites one alone: a full run of the central path with a scenario's specified rates (docs/METHOD.md, Scenario runs), records redacted as above. The dashboard does not read these files.

```jsonc
{
  "id", "label", "source",
  "specified_rates": { policy: { year: rate } },   // as given, before rounding; the rates paid are in run.rates
  "run": PATH_RUN,                                  // without "model"; rate_sources says "specified" where a rate was given
  "provenance": { "git_revision", "git_dirty", "source_hashes", "input_hashes", "engine_hashes", "packages",
                  "model", "datasets", "generated_at", "snapshot" }   // "release_bundle" before model-v2
}
```

`git_revision` may be a commit on a branch that was later squashed or rebased away, so it need not be reachable from main. The source, input and engine hashes are what tie an output to the code: `tests/test_scenarios.py::test_not_stale` (and `tests/test_results.py::test_not_stale` for the results file) compares them with today's.
