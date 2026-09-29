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
    "by_constituency": { policy_id: [ {code, name, mean_change_gbp} ] },            // optional if data allows
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
