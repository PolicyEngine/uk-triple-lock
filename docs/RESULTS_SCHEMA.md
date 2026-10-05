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
    "draws": { "n", "seed", "shocks", "model": { lag order, drift by year, ... } },
    "history_targets": { "window.treatment": { "gap_variance", "switch_rate", "floor_share", "years" } },
    "calibrations": { name: { "draws": "raw" | "shifted", "ess", "achieved", "targeted", "description", ... } },
    "gap_by_calibration": { name: { "mean_gap_gbp_week", "gap_gbp_week": {p10..p90}, "identical_share",
                                    "mean_rate_minus_earnings_2034_2039": {"triple_lock", "burnham_2030"} } },
    "primary": "means_shift",
    "backtest": { "origins", "horizon_years", "note", "rows", "summary": { "published" | "suspended": { method: {
                   "mean_predicted_gap_pct", "mean_realised_gap_pct", "bias_pct_points", "bias_se_independent",
                   "mean_abs_error", "switch_bias", "min_ess" } } } },
    "past_years_check": { "years", "realised_gap_pct", "model": {...}, "dynamics": {...} },
    "strata": [ { "stratum", "probability", "gap_range_gbp_week", "mean_gap_gbp_week", "paths", "unique_paths",
                  "sensitivity_paths" } ],
    "identical_rates": { "probability", "check_run": { "draw", "largest_abs_saving_bn" } },
    "datasets": { "primary": "enhanced_frs_2024_25", "sensitivity": "populace_uk_2023" },
    "estimates": { "primary" | "sensitivity": { output: { year: { "mean", "se" } } } },
                 // output: "gross", "net", "component.<name>", "households_losing_pct", "largest_record_bn",
                 // "net_excluding_largest_record"
    "paired_difference": { "gross" | "net": { year: { "mean", "se" } } },   // Microcosm minus Enhanced FRS
    "sensitivities": { calibration: { "ess", "effective_runs", "gross": {year: {mean, se}}, "net": {...} } },
    "paths": [ { "draw", "stratum", "times_drawn", "weight", "gap_2039_gbp_week", "statutory", "rates",
                 "outputs": { "primary" | "sensitivity": { output: { year: value } } }, "weight_ratio" } ]
                 // "weight" is the path's probability weight, not a survey weight
  },

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
                // Britain (households outside Northern Ireland), like for like with DWP
                "model_note", "datasets": { name: { "dataset", "model", "max_age", "records", "people",
                                                    "pension_type_people", "state_pension_age_people" } } },
  "dwp_uprating_analysis": { "saving_bn": { "2039": { "nominal": 15, "real_2025_26_prices": 11 }, ... }, "url", ... },
  "benchmarks": [ { "id", "publisher", "title", "date", "url", "figure_text", "comparison", "our_metric", "our_value",
                    "like_for_like", "note", "verified" } ],
  "method_limitations": [ ... ],
  "assumptions": [ { "key": "population" | "paths" | "benefits", "title", "text", "facts": {...} } ],
  "provenance": { "git_revision", "git_dirty", "source_hashes", "input_hashes", "engine_hashes", "packages",
                  "model", "datasets", "generated_at" }
}
```

`provenance.model` (from model-v2; a file built earlier has `release_bundle`, the policyengine.py bundle): what the runs ran on, as `datasets.provenance` records it: `model_package`, `model_version` (the installed policyengine-uk, which `packages` also gives), `core_version`, `certified` (false: no policyengine.py release certifies the pair) and `certification` (why), `runtime_dataset` (its logical name), `dataset` (the registry name, with its revision), `runtime_dataset_uri`, `runtime_dataset_sha256`, `data_package`, `data_version`, `data_built_with` and `data_certified_elsewhere`. `provenance.datasets.primary` is the registry name.

`assumptions` (`pipeline.assumptions`): what the headline figures are conditional on, in the order the dashboard's "What these figures assume" strip shows them. The pipeline writes the `title` and `text` from how the runs treated the population (each path run's `fixed_inputs.population`) and from the assembled results, so the strip changes when the model does; `facts` holds every number the text quotes, each equal to a figure elsewhere in the file (`test_assumptions_quote_the_results`). If a figure the block quotes is missing, or a value has no wording (a population treatment, calibration, shock model or dataset the pipeline has not been taught to describe), the build fails (`pipeline.MissingFigure`) rather than publish a strip that no longer describes the model. The dashboard renders the block's valid items (a non-empty `key`, `title` and `text`; the first item of each key), and nothing if none is valid; it computes the strip from the figures below only for a file with no `assumptions` key (built before the block existed). `scripts/check_assumptions.py` checks a results file (the #14 §5 pilot's, say) can carry the block, in seconds.
- `population`: `weights`, `ages` and `pension_types` as the path runs recorded them (see `fixed_inputs` below; the central run and every trajectory must record the same, or the build fails), `final_year`, `data_year`, `state_pension_age` (the ages in the final year) and `state_pension_age_settled_year` (from when it stops changing), and the primary dataset's `max_age`. With ages and types both from the survey year, the build also fails if the held type counts move after the State Pension age settles;
- `paths`: `year`, `measure` ("gross"), `calibration` (`expected_value.primary`), `reweightings` (how many `expected_value.sensitivities` named `shift_dynamics*`, the reweightings to past dynamics the text describes) and `reweightings_with_floor`, `floor`, `other_sensitivities` (every other sensitivity, left out of the range and counted in the text), `lowest` {calibration, mean, se} and `highest` {calibration, mean, se, effective_runs} of their final-year expected saving, and `shock_models_run` / `shock_models_not_run` (keys of `trajectories.models` by `runs_paths`; a model with no short name is named by its `label`);
- `benefits`: `coverage_year`, `pension_credit_claims_m` and `housing_benefit_pension_age_bn` {primary, dwp} (from `coverage.rows`), `model_geography`, `dwp_geography`, and `paired_difference_net` {year, mean, se, paths, dataset}: `expected_value.paired_difference.net` in the final year, the number of paired paths and the sensitivity dataset's name.

`PATH_RUN` (engine.run_path):
- the inputs: `statutory`, `calendar`, `applied_growth`;
- the checks: `path_following` (from model-v2 with `model_statutory_inputs`: the model's September CPI and May–July AWE read back, against the path's), `not_moving`, `also_moving`, `checks`;
- the rules on the path: `rates`, `rate_sources`, `weekly`, `applied_new_state_pension`. `rate_sources` names what set each rise: for the triple lock `floor` whenever neither input exceeds 2.5%, else `earnings` or `cpi` (CPI when they tie); for the Burnham plan `triple_lock` before the switch, then `earnings_path`, `cpi` (above 2.5%) or `floor`. A scenario run's specified years are `specified` for that policy (the plan stays `triple_lock` before the switch); no path in this file has any, and the dashboard reads the label as "a specified rate";
- the inputs held the same under both rules: `fixed_inputs` {data_year, population {weights: "survey" | "ons_projection" | "reweighted", ages: "survey_year" | "adjusted" | "aged_forward", pension_types: "survey_year" | "cohort" | "model"} (`engine.population_treatment`: weights and ages as the dataset load declares them (`engine.LOADED_POPULATION`), checked against what the run pins and the ages the model computes; pension types by the rule `pinned_inputs` follows (`engine.PENSION_TYPE_RULE`)), state_pension_age {year: [ages]} (from model-v2: the youngest survey age, in whole years, with anyone over State Pension age that year and the youngest from which everyone is, one value when they coincide, as policyengine-uk's timetable by date of birth puts them; a file built earlier gives the State Pension age itself), pension_credit_guarantee_single_weekly {year: £}, held_pension_type_records {year: {BASIC, NEW, NONE: records}}, held_pension_type_people {year: {BASIC, NEW, NONE: weighted people}}}; the type counts are read back from the model after pinning;
- the money: `saving_bn` {year: {gross, net, household_income_change, components, components_by_variable, decomposition_residual, net_model_float32, gb: {gross, net, components}}} and `totals_bn` {policy: {year: {<group>, gov_balance, gov_balance_model, household_net_income, basic_state_pension, new_state_pension, variables: {variable: £bn}, tax_variables: [...], gb: {<group>, gov_balance, household_net_income, basic_state_pension, new_state_pension}}}}. The groups (`config.FISCAL_GROUPS`, plus `other_spending` and `other_tax`) and `variables` cover every variable in policyengine-uk's `GOV_TAX_VARIABLES` and `GOV_SPENDING_VARIABLES` (State Pension in its three parts; `tax_variables` names the taxes). `gov_balance` is their float64 sum, taxes less spending, so taxes added and spending subtracted the components are `net` exactly (`decomposition_residual`, below 1e-6 £bn); `gov_balance_model` and `net_model_float32` are the model's own float32 figures, within 1e-5 £bn. `gb` is Great Britain (households outside Northern Ireland). A file built before model-v2 has the eight named groups only;
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
