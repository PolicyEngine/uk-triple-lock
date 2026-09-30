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
    "models": { "boot" | "tcop" | "gauss": { gap quantiles, deflation shares, switches per year, ... } },
    "gap_statistics": {...},
    "history": { "years", "cpi", "earnings", "actual_rise", "actual_weekly", "groups": [ past-years counterfactuals ],
                 "triple_lock": { "rate", "binding", "earnings_published", "index": {"triple_lock", "cpi", "earnings", "floor"} } },
    "backtest": { "statutory": {...}, "calendar": {...} }
  },

  "coverage": { "year": 2026, "dwp": {...}, "rows": [ { "key", "label", "dwp", "primary", "sensitivity" } ], "datasets": {...} },
  "dwp_uprating_analysis": { "saving_bn": { "2039": { "nominal": 15, "real_2025_26_prices": 11 }, ... }, "url", ... },
  "benchmarks": [ { "id", "publisher", "title", "date", "url", "figure_text", "comparison", "our_metric", "our_value",
                    "like_for_like", "note", "verified" } ],
  "method_limitations": [ ... ],
  "provenance": { "git_revision", "git_dirty", "source_hashes", "input_hashes", "engine_hashes", "packages",
                  "release_bundle", "datasets", "generated_at" }
}
```

`PATH_RUN` (engine.run_path):
- the inputs: `statutory`, `calendar`, `applied_growth`;
- the checks: `path_following`, `not_moving`, `also_moving`, `checks`;
- the rules on the path: `rates`, `rate_sources`, `weekly`, `applied_new_state_pension`;
- the money: `saving_bn` {year: {gross, net, household_income_change, components}} and `totals_bn` {policy: {year: {...}}};
- the people: `poverty_pct` {policy: {year: {...}}}, `households_affected` {year: {losing_pct, mean_loss_gbp}}, `distribution` {2034 | 2039: {by_decile, by_quintile, by_region, by_hh_type, by_tenure, by_age_band, households_affected}};
- the single household: `largest_household` {contribution_bn, share_of_income_change, income_change_excluding_bn} for the final year and `concentration_by_year` {year: {contribution_bn, share_of_income_change}}. FRS records are licensed data, so the file gives only a record's contribution to the totals, never its identifier, weight or amounts (`pipeline.redact_records`; `test_no_survey_record_is_published`);
- `dataset`.

Signs:
- `saving_bn.gross` is triple-lock minus plan State Pension spending;
- `saving_bn.net` is plan minus triple-lock `gov_balance`;
- `components` are plan minus triple lock.
