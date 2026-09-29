# Results file contract: `data/triple_lock_results.json`

The pipeline writes this file; the dashboard reads it (synced to
`dashboard/public/data/`). Every figure the dashboard shows comes from here.
Money in £bn (2 dp) or £ per year; years are fiscal years named by start
year ("2027" = 2027-28).

```jsonc
{
  "provenance": { "generated_at", "git_revision", "git_dirty", "packages": {...}, "dataset" },
  "horizon": [2027, 2028, ..., 2034],
  "policies": {                          // keyed by policy id
    "triple_lock":   { "label": "Triple lock (current policy)", "rule": "max(CPI, earnings, 2.5%)" },
    "double_lock":   { "label": "Double lock", "rule": "max(CPI, earnings)" },
    "earnings_link": { "label": "Earnings link", "rule": "earnings" },
    "cpi_link":      { "label": "CPI link", "rule": "CPI" }
  },
  "central": {                           // deterministic run on the OBR central forecast
    "forecast": { "source", "source_url", "cpi": {year: rate}, "earnings": {year: rate} },
    "uprating": { policy_id: {year: rate} },
    "cost_vs_triple_lock_bn": {          // negative = saving relative to the triple lock
      policy_id: { "gross": {year: bn}, "net": {year: bn} }   // net = after Pension Credit, HB, tax interactions
    },
    "full_state_pension_weekly": { policy_id: {year: £/wk} },
    "by_decile":   { policy_id: [ {decile, mean_change_gbp, pct_income_change} ] },  // final horizon year
    "by_region":   { policy_id: [ {region, mean_change_gbp, total_bn} ] },
    "households_affected": { policy_id: { "losing_pct", "mean_loss_gbp" } }
  },
  "uncertainty": {                       // Monte Carlo over OBR forecast errors
    "n_draws": int,
    "error_source": { "title", "url", "years_used", "method" },
    "cost_of_triple_lock_vs": {          // triple lock minus alternative, £bn in the final year
      policy_id: { "p5", "p10", "p25", "p50", "p75", "p90", "p95", "mean" }
    },
    "fan": {                             // cumulative uprating index (2026 = 1.0) by year
      policy_id: { year: { "p10", "p50", "p90" } }
    },
    "prob_triple_lock_binds_on_floor": {year: share},   // share of draws where 2.5% is the max
    "representative_paths": { "p10", "p50", "p90" }     // paths run through full PolicyEngine for distributional outputs
  },
  "metadata": { "method_limitations": [...], "sources": [...] }
}
```

## Clarifications (pipeline as built)

- Top-level `"sample": false` marks real model output (a dashboard sample file sets it to `true`).
- Rates (`central.forecast`, `central.uprating`, `representative_paths`) are decimals (0.025 = 2.5%).
  `central.forecast` and `representative_paths[*].cpi/earnings` are keyed by the **calendar growth
  year**; the uprating in fiscal year `y` uses growth in `y - 1` (as in policyengine-uk's
  `create_triple_lock.py`). `central.uprating` is keyed by the fiscal year the rate takes effect.
- `central.households_affected[policy].losing_pct` is a percent 0–100 of households losing more than
  £1 a year relative to the triple lock; `mean_loss_gbp` is their mean loss as a positive number.
- Distribution rows (`by_decile`, `by_quintile`, `by_region`, `by_hh_type`, `by_tenure`,
  `by_age_band`, `households_affected`) are given for the alternatives only (change vs the triple
  lock). `central.distribution_2029` repeats the tables for 2029-30.
- Every breakdown row has the shape `{<group_key>, label, mean_change_gbp, pct_income_change,
  total_bn, share_of_households_pct}`, where `<group_key>` is `decile` (1-10), `quintile` (1-5),
  `region` (PolicyEngine region code), `hh_type` (`single_pensioner`, `pensioner_couple`,
  `mixed_age`, `working_age_with_children`, `working_age_no_children`), `tenure` (`owner_outright`,
  `mortgage`, `social_rent`, `private_rent`) or `age_band` (`under_66`, `66_74`, `75_plus`; age of
  the household head as recorded in the FRS, which top-codes age at 80). `mean_change_gbp` is £ a
  year per household; `pct_income_change` the group's total change as % of its baseline net
  income; `total_bn` the group's total change in household net income, £bn; `share_of_households_pct`
  the group's share of all households. Within each breakdown `total_bn` sums (to rounding) to the
  **net** cost, `cost_vs_triple_lock_bn[policy].net` (equal to the change in household net income).
  Definitions are in `central.breakdown_notes`.
- `central.cost_vs_triple_lock_bn[policy]`: `gross` = change in basic + new State Pension spend;
  `net` = minus the change in PolicyEngine `gov_balance` (equal, to rounding, to the change in
  household net income). Extra fields: `components` (Pension Credit, Housing Benefit, UC, Council Tax
  Reduction, Winter Fuel, income tax) and `largest_single_household` (eligibility-cliff diagnostic).
- `uncertainty.cost_of_triple_lock_vs[policy]` is **gross** State Pension spend, £bn, in the final
  horizon year (2034-35), positive = the triple lock costs more; each entry carries `"basis": "gross"`.
- `uncertainty.prob_triple_lock_binds_on_floor` values are shares 0–1, keyed by uprating year.
- `uncertainty.representative_paths` = `{"p10": {"cpi": {year: rate}, "earnings": {year: rate},
  "uprating": {policy: {year: rate}}, ...}, "p50": ..., "p90": ...}`, ranked on the final-year cost of
  the triple lock vs the CPI link. Full PolicyEngine results for them are in
  `uncertainty.representative_path_runs`.
- The main uncertainty run (`uncertainty.cost_of_triple_lock_vs`, `fan`,
  `prob_triple_lock_binds_on_floor`, `representative_paths`) is for the **statutory inputs**:
  de-meaned OBR forecast errors plus the same target years' historical gaps to September CPI and
  May–July AWE (de-meaned by horizon; `error_source.statutory_gaps`), and September 2026 CPI drawn
  as August plus a resampled historical August-to-September change. It is **gross only**.
  Sensitivities with the same fields: `sensitivity_proxy_only` (no statutory gaps),
  `sensitivity_raw_errors` (errors not de-meaned, with the gaps; its `description` and
  `mean_error_by_horizon` state the bias) and `sensitivity_ex_2022_23` (as main, dropping vintages
  whose horizon 1–4 targets include 2022 or 2023).
- No rule cuts the cash pension: every rule's annual uprating is floored at 0, in the central run and
  every draw. `uncertainty.zero_floor` gives `share_of_draws_any_rule` and `share_of_draws_by_rule`.
- `uncertainty.cost_of_triple_lock_vs_pct_of_spend[policy]`: the same percentiles as % of final-year
  basic + new State Pension spend under the central triple lock.
- `central.forecast.statutory_2027_inputs`: the April 2027 uprating uses published May–July 2026 AWE
  total pay growth (ONS KAC3) for earnings and August 2026 CPI (ONS D7G7) for CPI, instead of
  PolicyEngine's calendar-year 2026 growth; the triple-lock baseline is therefore a reform run too.
- `central.composition_effect`: flat-rate spend per index point by year, `difference_pct` and
  `difference_pct_by_year` (how much larger each gross cost is than under a scenario holding the
  2027-28 pensioner composition fixed; a scenario, not a measured bias) and
  `gross_fixed_composition[policy]` (gross cost under that scenario).
- `central.cost_vs_triple_lock_bn[policy].net_excluding_largest_household`: `net` minus the largest
  single survey household's contribution that year.
- The pipeline requires `data/obr_forecast_errors.csv` and fails without it (no placeholder output).
- `metadata.benchmarks`: rows of `data/benchmarks.csv` (`id, publisher, title, date, url,
  figure_text, comparison, our_metric, like_for_like, note, verified`; `verified` is a boolean, false
  where the source could not be re-read) plus `our_value`, the value at the
  dotted path `our_metric` in this file.
- `central.by_quintile`: quintiles pair PolicyEngine's `household_income_decile` (deciles of
  equivalised household net income with boundaries set so each holds a tenth of people, i.e.
  person-weighted; same concept as `by_decile`): 1-2, 3-4, …; households PolicyEngine marks -1
  (negative net income) are assigned to decile 1.
- `uncertainty.var_cross_check`: cross-check on the main (forecast-error bootstrap) method, with the
  same fields (`cost_of_triple_lock_vs` percentiles with `basis: "gross"`, `fan`,
  `prob_triple_lock_binds_on_floor`, `representative_paths`) plus `method`, `lag_order`,
  `residual_correlation` and `fit` (coefficients, AIC, sample). Bivariate VAR on ONS CPI (D7G7) and
  OBR-definition earnings growth, 1989-2025, mean-shifted each year to the OBR central path.
