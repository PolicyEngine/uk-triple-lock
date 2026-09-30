/**
 * Readers for results.json (docs/RESULTS_SCHEMA.md).
 *
 * Every figure the dashboard shows is read from the results file. Each reader
 * validates the block it returns and gives back `null` when any field is
 * missing or invalid, so the component renders "unavailable" instead of "NaN",
 * "£bn" or a blank.
 */

export const UNAVAILABLE = "unavailable";
export const POLICIES = ["triple_lock", "burnham_2030"];

export function isNum(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function isText(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/** Fiscal year named by start year: 2027 -> "2027-28". */
export function fyLabel(year) {
  if (!Number.isInteger(year)) return UNAVAILABLE;
  return `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
}

/** True only for an explicit `"sample": true`. */
export function isSample(data) {
  return data?.sample === true;
}

/** Horizon years as increasing integers, or null. */
export function getHorizon(data) {
  const horizon = data?.horizon;
  if (!Array.isArray(horizon) || horizon.length === 0 || !horizon.every(Number.isInteger)) return null;
  for (let i = 1; i < horizon.length; i += 1) if (horizon[i] <= horizon[i - 1]) return null;
  return horizon;
}

export function getFinalYear(data) {
  const h = getHorizon(data);
  return h && data.final_year === h.at(-1) ? data.final_year : null;
}

export function getSwitchYear(data) {
  return Number.isInteger(data?.switch_year) ? data.switch_year : null;
}

export function getPolicyLabel(data, id) {
  const label = data?.policies?.[id]?.label;
  return isText(label) ? label : null;
}

function byYear(obj, years, pick = (v) => v, check = isNum) {
  if (!obj || typeof obj !== "object") return null;
  const out = years.map((y) => pick(obj[String(y)]));
  return out.every(check) ? out : null;
}

// ── Central path ────────────────────────────────────────────────────────

/** The central path's full run: savings by year, weekly amounts and rates, or null. */
export function getCentral(data) {
  const years = getHorizon(data);
  const run = data?.central?.run;
  if (!years || !run) return null;
  const gross = byYear(run.saving_bn, years, (v) => v?.gross);
  const net = byYear(run.saving_bn, years, (v) => v?.net);
  const weekly = {};
  const rates = {};
  for (const p of POLICIES) {
    weekly[p] = byYear(run.weekly?.[p]?.new_state_pension, years, (v) => v, (v) => isNum(v) && v > 0);
    rates[p] = byYear(run.rates?.[p], years);
  }
  if (!gross || !net || POLICIES.some((p) => !weekly[p] || !rates[p])) return null;
  const path = data.central.path;
  const statYears = years.map((y) => y - 1);
  const cpi = byYear(path?.statutory?.cpi, statYears);
  const earnings = byYear(path?.statutory?.earnings, statYears);
  const obrTl = byYear(path?.obr_triple_lock_uprating, statYears);
  return { years, gross, net, weekly, rates, cpi, earnings, obrTripleLock: obrTl };
}

// ── Expected value ──────────────────────────────────────────────────────

function readEstimate(block, years) {
  const mean = byYear(block, years, (v) => v?.mean);
  const se = byYear(block, years, (v) => v?.se, (v) => isNum(v) && v >= 0);
  return mean && se ? years.map((y, i) => ({ year: y, mean: mean[i], se: se[i] })) : null;
}

const SENSITIVITY_LABELS = {
  "shift_dynamics.2001_2025.covid_excluded": "Tilted to 2001-2025's gap variance and switch rate (2020-21 left out)",
  "shift_dynamics.2001_2025.suspended": "Tilted to 2001-2025's dynamics (April 2022 as in law)",
  "shift_dynamics.2001_2025.published": "Tilted to 2001-2025's dynamics (as published)",
  "shift_dynamics.2010_2025.covid_excluded": "Tilted to 2010-2025's gap variance and switch rate (2020-21 left out)",
  "shift_dynamics.2010_2025.suspended": "Tilted to 2010-2025's dynamics (April 2022 as in law)",
  "shift_dynamics.2010_2025.published": "Tilted to 2010-2025's dynamics (as published)",
};

/** The expected-value block, validated, or null. */
export function getExpectedValue(data) {
  const years = getHorizon(data);
  const ev = data?.expected_value;
  if (!years || !ev || !isText(ev.primary)) return null;
  const primary = { gross: readEstimate(ev.estimates?.primary?.gross, years), net: readEstimate(ev.estimates?.primary?.net, years) };
  const sensitivity = {
    gross: readEstimate(ev.estimates?.sensitivity?.gross, years),
    net: readEstimate(ev.estimates?.sensitivity?.net, years),
  };
  const diff = { gross: readEstimate(ev.paired_difference?.gross, years), net: readEstimate(ev.paired_difference?.net, years) };
  const losing = readEstimate(ev.estimates?.primary?.households_losing_pct, years);
  const netExcludingLargest = readEstimate(ev.estimates?.primary?.net_excluding_largest_record, years);
  if (!primary.gross || !primary.net || !sensitivity.gross || !sensitivity.net || !diff.gross || !diff.net) return null;
  const paths = Array.isArray(ev.paths) ? ev.paths : [];
  const strata = Array.isArray(ev.strata) ? ev.strata : [];
  const nRuns = strata.reduce((a, s) => a + (Number.isInteger(s.paths) ? s.paths : 0), 0);
  const nSensitivity = strata.reduce((a, s) => a + (Number.isInteger(s.sensitivity_paths) ? s.sensitivity_paths : 0), 0);
  const gap = ev.gap_by_calibration?.[ev.primary];
  const sensitivities = Object.entries(ev.sensitivities ?? {})
    .filter(([name]) => SENSITIVITY_LABELS[name])
    .map(([name, s]) => ({
      name,
      label: SENSITIVITY_LABELS[name],
      ess: s.ess,
      effectiveRuns: s.effective_runs,
      gross: readEstimate(s.gross, years),
      net: readEstimate(s.net, years),
    }))
    .filter((s) => s.gross && s.net && isNum(s.ess) && isNum(s.effectiveRuns));
  return {
    years,
    primaryName: ev.primary,
    primary,
    sensitivity,
    diff,
    losing,
    netExcludingLargest,
    sensitivities,
    datasets: ev.datasets ?? {},
    nDraws: ev.draws?.n,
    nRuns,
    nUniquePaths: paths.length,
    nSensitivity,
    strata,
    identical: ev.identical_rates?.probability,
    gap: gap && isNum(gap.mean_gap_gbp_week) ? gap : null,
  };
}

/** The expected-value backtest summary for one treatment of April 2022, or null. */
export const EV_BACKTEST_LABELS = {
  obr_point: "OBR forecast as a single path",
  model: "Monthly model as fitted",
  means_tilt: "Tilted to the OBR means",
  means_shift: "Shifted to the OBR means (used here)",
  shift_dynamics: "Shifted, then tilted to past gap variance and switch rate",
};

export function getEvBacktest(data) {
  const bt = data?.expected_value?.backtest;
  if (!bt || !Array.isArray(bt.origins)) return null;
  const out = {};
  for (const t of ["published", "suspended"]) {
    const s = bt.summary?.[t];
    if (!s) return null;
    out[t] = Object.keys(EV_BACKTEST_LABELS)
      .filter((k) => s[k])
      .map((k) => ({ id: k, label: EV_BACKTEST_LABELS[k], ...s[k] }))
      .filter((r) => [r.mean_predicted_gap_pct, r.mean_realised_gap_pct, r.bias_pct_points, r.bias_se_independent].every(isNum));
    if (!out[t].length) return null;
  }
  return { ...out, origins: bt.origins, horizon: bt.horizon_years, note: isText(bt.note) ? bt.note : null };
}

export function getPastYearsCheck(data) {
  const pc = data?.expected_value?.past_years_check;
  if (!pc || !isNum(pc.realised_gap_pct) || !pc.model || !isNum(pc.model.mean_gap_pct)) return null;
  return pc;
}

// ── Household tables ────────────────────────────────────────────────────

const QUINTILE_LABELS = ["Bottom fifth by income", "2nd", "3rd", "4th", "Top fifth by income"];

export const BREAKDOWNS = [
  { id: "by_quintile", label: "Income", column: "quintile" },
  { id: "by_hh_type", label: "Household type", column: "hh_type" },
  { id: "by_age_band", label: "Age of head", column: "age_band" },
  { id: "by_tenure", label: "Tenure", column: "tenure" },
  { id: "by_region", label: "Region", column: "region" },
  { id: "by_decile", label: "Income decile", column: "decile" },
];

/** Rows of one household table for a path run and year, or null. */
export function getBreakdown(run, year, breakdownId) {
  const b = BREAKDOWNS.find((x) => x.id === breakdownId);
  const rows = run?.distribution?.[String(year)]?.[breakdownId];
  if (!b || !Array.isArray(rows) || !rows.length) return null;
  const out = rows.map((r) => ({
    group: r[b.column],
    label: b.id === "by_quintile" ? QUINTILE_LABELS[r.quintile - 1] : r.label,
    mean: r.mean_change_gbp,
    pct: r.pct_income_change,
    total: r.total_bn,
    share: r.share_of_households_pct,
  }));
  return out.every((r) => isText(r.label) && [r.mean, r.pct, r.total, r.share].every(isNum)) ? out : null;
}

export function getHouseholdsAffected(run, year) {
  const a = run?.households_affected?.[String(year)];
  return a && isNum(a.losing_pct) && isNum(a.mean_loss_gbp) ? { losing: a.losing_pct, meanLoss: a.mean_loss_gbp } : null;
}

export const POVERTY_MEASURES = [
  { id: "pensioners_absolute_ahc", label: "Pensioners, absolute poverty after housing costs" },
  { id: "pensioners_relative_ahc", label: "Pensioners, relative poverty after housing costs" },
  { id: "everyone_absolute_ahc", label: "Everyone, absolute poverty after housing costs" },
  { id: "everyone_relative_ahc", label: "Everyone, relative poverty after housing costs" },
];

export function getPoverty(run, year) {
  const out = {};
  for (const p of POLICIES) {
    const v = run?.poverty_pct?.[p]?.[String(year)];
    if (!v || !POVERTY_MEASURES.every((m) => isNum(v[m.id]))) return null;
    out[p] = v;
  }
  return out;
}

/** The full-run paths the steps offer: the central path first, then the others in file order. */
export function getRunsWithTables(data) {
  const runs = [];
  for (const t of data?.trajectories?.paths ?? []) {
    if (t?.distribution && isText(t.id) && isText(t.label)) runs.push({ id: t.id, label: t.label, run: t });
  }
  runs.sort((a, b) => (a.id === "central" ? -1 : b.id === "central" ? 1 : 0));
  return runs;
}

// ── Context ─────────────────────────────────────────────────────────────

export function getDwp(data) {
  const d = data?.dwp_uprating_analysis;
  const s = d?.saving_bn?.["2039"];
  return d && isText(d.url) && isNum(s?.nominal) && isNum(s?.real_2025_26_prices) ? { ...d, nominal2039: s.nominal, real2039: s.real_2025_26_prices } : null;
}

export function getCoverage(data) {
  const c = data?.coverage;
  if (!c || !Array.isArray(c.rows) || !c.rows.length) return null;
  const rows = c.rows.filter((r) => isText(r.label) && [r.dwp, r.primary, r.sensitivity].every(isNum));
  return rows.length === c.rows.length ? { ...c, rows } : null;
}

const LIKE_FOR_LIKE = new Set(["yes", "partial", "no"]);

export function getBenchmarks(data) {
  const b = data?.benchmarks;
  if (!Array.isArray(b)) return null;
  const rows = b.filter(
    (r) => r.verified === true && ["publisher", "title", "url", "figure_text", "comparison", "note"].every((k) => isText(r[k])) &&
      LIKE_FOR_LIKE.has(r.like_for_like) && isNum(r.our_value) && r.url.startsWith("https://"),
  );
  return rows.length ? rows : null;
}

export function getLimitations(data) {
  const l = data?.method_limitations;
  return Array.isArray(l) && l.length && l.every(isText) ? l : null;
}

export function getProvenance(data) {
  const p = data?.provenance;
  if (!p || !isText(p.git_revision) || !p.release_bundle) return null;
  return p;
}

export function getCoverageDatasets(data) {
  return data?.expected_value?.datasets ?? null;
}

// ── Spread of the saving across paths ───────────────────────────────────

function weightedQuantile(sorted, total, q) {
  let cum = 0;
  for (const [value, weight] of sorted) {
    cum += weight;
    if (cum >= q * total) return value;
  }
  return sorted.at(-1)?.[0] ?? null;
}

export const SPREAD_QUANTILES = { p10: 0.1, p25: 0.25, p50: 0.5, p75: 0.75, p90: 0.9 };

/**
 * Percentiles of the gross and net saving across the model's paths, by year, from the full runs.
 * Each run stands for its stratum's share of the paths (stratum probability / draws in the stratum, times the
 * times it was drawn); the paths on which the two rules never differ carry the remaining share at zero saving,
 * as in the expected-value estimator. Null when the file lacks the runs or their weights.
 */
export function getSavingSpread(data) {
  const years = getHorizon(data);
  const ev = data?.expected_value;
  const paths = Array.isArray(ev?.paths) ? ev.paths : [];
  const strata = new Map((Array.isArray(ev?.strata) ? ev.strata : []).map((s) => [s.stratum, s]));
  if (!years || paths.length === 0 || strata.size === 0) return null;
  const weights = paths.map((p) => {
    const s = strata.get(p.stratum);
    return s && isNum(s.probability) && s.paths > 0 && isNum(p.times_drawn) ? (s.probability * p.times_drawn) / s.paths : NaN;
  });
  if (weights.some((w) => !isNum(w))) return null;
  const zeroMass = Math.max(0, 1 - weights.reduce((a, w) => a + w, 0));
  const spread = {};
  for (const key of ["gross", "net"]) {
    const rows = [];
    for (const y of years) {
      const pairs = paths.map((p, i) => [p.outputs?.primary?.[key]?.[String(y)], weights[i]]);
      if (pairs.some(([v]) => !isNum(v))) return null;
      if (zeroMass > 0) pairs.push([0, zeroMass]);
      pairs.sort((a, b) => a[0] - b[0]);
      const total = pairs.reduce((a, [, w]) => a + w, 0);
      const row = { year: y };
      for (const [name, q] of Object.entries(SPREAD_QUANTILES)) row[name] = weightedQuantile(pairs, total, q);
      rows.push(row);
    }
    spread[key] = rows;
  }
  return { years, ...spread, nRuns: paths.length };
}

/**
 * The spread of one year's figure (gross, net or households_losing_pct) across the model's paths: a weighted
 * histogram, its 10th, 50th and 90th percentiles and mean, and a function giving the percentile of any value. Each
 * full run is weighted as in getSavingSpread, with the never-differing paths at zero. Null when the file lacks the
 * runs or their weights.
 */
export function getSavingHistogram(data, key, year, { nBins = 24, binZero = true } = {}) {
  const ev = data?.expected_value;
  const paths = Array.isArray(ev?.paths) ? ev.paths : [];
  const strata = new Map((Array.isArray(ev?.strata) ? ev.strata : []).map((s) => [s.stratum, s]));
  if (paths.length === 0 || strata.size === 0) return null;
  const pairs = paths.map((p) => {
    const s = strata.get(p.stratum);
    const w = s && isNum(s.probability) && s.paths > 0 && isNum(p.times_drawn) ? (s.probability * p.times_drawn) / s.paths : NaN;
    return [p.outputs?.primary?.[key]?.[String(year)], w];
  });
  if (pairs.some(([v, w]) => !isNum(v) || !isNum(w))) return null;
  const zeroMass = Math.max(0, 1 - pairs.reduce((a, [, w]) => a + w, 0));
  if (zeroMass > 0) pairs.push([0, zeroMass]);
  pairs.sort((a, b) => a[0] - b[0]);
  const total = pairs.reduce((a, [, w]) => a + w, 0);
  // binZero false leaves the never-differing paths out of the bars (not the mean or percentiles), so a figure that
  // clusters far from zero is not squashed against it.
  const barPairs = binZero || zeroMass === 0 ? pairs : pairs.filter(([v, w]) => !(v === 0 && w === zeroMass));
  const lo = binZero ? Math.min(0, pairs[0][0]) : barPairs[0][0];
  const hi = barPairs.at(-1)[0];
  const width = (hi - lo) / nBins || 1;
  const bins = Array.from({ length: nBins }, (_, i) => ({ x0: lo + i * width, x1: lo + (i + 1) * width, weight: 0 }));
  for (const [v, w] of barPairs) bins[Math.max(0, Math.min(nBins - 1, Math.floor((v - lo) / width)))].weight += w;
  const q = (p) => weightedQuantile(pairs, total, p);
  const mean = pairs.reduce((a, [v, w]) => a + v * w, 0) / total;
  const percentileOf = (v) => (100 * pairs.filter(([x]) => x < v).reduce((a, [, w]) => a + w, 0)) / total;
  return { lo, hi, bins, p10: q(0.1), p50: q(0.5), p90: q(0.9), mean, percentileOf };
}
