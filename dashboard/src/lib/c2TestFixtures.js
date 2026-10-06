import realData from "../../public/data/results.json";

/** Synthetic result contracts; no calculation or fiscal job is performed. */
export function c2Fixture(primaryPasses = true) {
  const data = structuredClone(realData);
  const estimate = (mean) => Object.fromEntries(data.horizon.map((y) => [y, { mean, se: 0.1 }]));
  const series = (value) => Object.fromEntries(data.horizon.map((y) => [y, value]));
  const reason = "Original monthly VAR(1) bootstrap failed the frozen C2 screen: terminal coverage below the threshold.";
  const metric = (treatment) => ({
    annual_gap_coverage: { mean: treatment === "suspended" ? 0.8 : 0.6 },
    annual_gap_cells: treatment === "suspended" ? 20 : 24,
    annual_gap_excluded_cells: treatment === "suspended" ? 4 : 0,
    terminal_coverage: { hits: treatment === "suspended" ? 4 : 1 },
    terminal_scored_origins: 6, gap_bias_pp: { mean: 1.3 }, switch_bias: { mean: -0.1 }, floor_bias: { mean: 0.2 },
  });
  const forms = { monthly_var1_boot: { passes: primaryPasses }, annual_var1_boot: { passes: true } };
  const screen = {
    screen: "c2", run_kind: "binding", rule_sha: "65343e2ee43a359f056ce5a027739509d32ab49f",
    c1_failure: { all_five_failed: true, rule_changed_after_scores_seen: true },
    c2_outcome: { forms, effective_ruling: primaryPasses ? "c" : "a", fallback_reason: primaryPasses ? null : reason },
    c2_scores: {
      scores: Object.fromEntries(["A", "B"].map((test) => [test, Object.fromEntries(["suspended", "published"].map((t) => [t,
        Object.fromEntries(Object.keys(forms).map((form) => [form, metric(t)]))]))])),
      past_years: { monthly_var1_boot: {
        suspended: { realised_gap_pct: 6.3, mean_gap_pct: 6.0, realised_percentile: 56.54 },
        published: { realised_gap_pct: 10.9, mean_gap_pct: 6.1, realised_percentile: 92.08 },
      } },
    },
  };
  data.uncertainty_screen = screen;
  data.provenance.uncertainty_screen = structuredClone(screen);
  data.uncertainty_ruling = { ruling: primaryPasses ? "c" : "a", requested_ruling: "c", effective_ruling: primaryPasses ? "c" : "a" };
  data.mean_path_scenarios = { scenarios: Object.fromEntries([["upper", 0.005, 8, 6], ["lower", -0.005, 2, 1]].map(([name, delta, gross, net]) => [name, {
    calendar_earnings_delta: delta, from_year: 2031, scenario_path_set: { gross: estimate(gross), net: estimate(net) },
  }])) };
  data.scenario_envelope = {
    interpretation: "scenario envelope; not a probability interval",
    central: data.central,
    obr_wedge: data.trajectories.paths.find((p) => p.id === "obr_premium"),
    last_decade_replay: { label: "Historical replay, April 2017–2026", interpretation: "historical legal replay; not a future forecast", years: [2017, 2026] },
    paired_earnings_mean_paths: data.mean_path_scenarios,
  };
  if (!primaryPasses) {
    delete data.expected_value;
    data.expected_value_omission = { requested_ruling: "c", effective_ruling: "a", reason };
  } else {
    data.expected_value = {
      primary: "monthly_var1_boot", interpretation: "model-conditional", draws: { n: 50000 },
      provenance: { ...structuredClone(screen), ruling: "c" },
      estimates: {
        primary: { gross: estimate(8), net: estimate(4), households_losing_pct: estimate(20) },
        sensitivity: { gross: estimate(8.5), net: estimate(4.5) },
      },
      paired_difference: { gross: estimate(0.5), net: estimate(0.5) }, sensitivities: {},
      strata: [{ stratum: 1, probability: 1, paths: 2, sensitivity_paths: 2 }],
      paths: [[4, 2, 10], [12, 6, 30]].map(([gross, net, losing], index) => ({ stratum: 1, draw: index, times_drawn: 1,
        outputs: { primary: { gross: series(gross), net: series(net), households_losing_pct: series(losing) } } })),
      gap_by_calibration: { monthly_var1_boot: { mean_gap_gbp_week: 10, gap_gbp_week: { p10: 5, p90: 15 }, mean_rate_minus_earnings_2034_2039: 0.001 } },
    };
  }
  return data;
}
