/**
 * Data helpers for the triple lock dashboard.
 *
 * Every figure the dashboard shows is read from the results file
 * (docs/RESULTS_SCHEMA.md). Each helper validates the block it returns and
 * gives back `null` when any field is missing or invalid, so the component
 * renders "unavailable" instead of "NaN", "£bn" or a blank. This is the same
 * fail-closed rule as getUpratingInputs in impact-iran-war-living-standards.
 */

export const BASELINE_POLICY = "triple_lock";
export const UNAVAILABLE = "unavailable";

export function isNum(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/** Fiscal year named by start year: 2027 -> "2027-28". */
export function fyLabel(year) {
  if (!Number.isInteger(year)) return UNAVAILABLE;
  return `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
}

/** True only for an explicit `"sample": true`. Real output omits the key. */
export function isSample(data) {
  return data?.sample === true;
}

/** Horizon years as integers, or null. */
export function getHorizon(data) {
  const horizon = data?.horizon;
  if (!Array.isArray(horizon) || horizon.length === 0) return null;
  if (!horizon.every((y) => Number.isInteger(y))) return null;
  for (let i = 1; i < horizon.length; i += 1) {
    if (horizon[i] <= horizon[i - 1]) return null;
  }
  return horizon;
}

export function getFinalYear(data) {
  const horizon = getHorizon(data);
  return horizon ? horizon[horizon.length - 1] : null;
}

/**
 * Policies in file order, triple lock first. Null unless the triple lock and
 * at least one alternative are present with a label.
 */
export function getPolicies(data) {
  const raw = data?.policies;
  if (!raw || typeof raw !== "object") return null;
  const entries = Object.entries(raw);
  if (!entries.every(([, p]) => isNonEmptyString(p?.label))) return null;
  const list = entries.map(([id, p]) => ({
    id,
    label: p.label,
    rule: isNonEmptyString(p.rule) ? p.rule : null,
  }));
  const baseline = list.find((p) => p.id === BASELINE_POLICY);
  const alternatives = list.filter((p) => p.id !== BASELINE_POLICY);
  if (!baseline || alternatives.length === 0) return null;
  return [baseline, ...alternatives];
}

export function getAlternatives(data) {
  const policies = getPolicies(data);
  return policies ? policies.filter((p) => p.id !== BASELINE_POLICY) : null;
}

export function getPolicyLabel(data, id) {
  const label = data?.policies?.[id]?.label;
  return isNonEmptyString(label) ? label : null;
}

/** {year: value} -> [values in horizon order], or null if any is invalid. */
function yearSeries(obj, horizon, valid = isNum) {
  if (!obj || typeof obj !== "object" || !horizon) return null;
  const values = horizon.map((y) => obj[String(y)]);
  return values.every(valid) ? values : null;
}

/**
 * Cost of a rule relative to the triple lock, £bn, one value per horizon year.
 * Negative = saving. `basis` is "gross" or "net".
 */
export function getCostSeries(data, policyId, basis) {
  return yearSeries(
    data?.central?.cost_vs_triple_lock_bn?.[policyId]?.[basis],
    getHorizon(data),
  );
}

/** One year's cost vs the triple lock, or null. */
export function getCostInYear(data, policyId, basis, year) {
  const value = data?.central?.cost_vs_triple_lock_bn?.[policyId]?.[basis]?.[String(year)];
  return isNum(value) ? value : null;
}

/** Full new State Pension £/week per horizon year, or null. */
export function getWeeklyPension(data, policyId) {
  return yearSeries(
    data?.central?.full_state_pension_weekly?.[policyId],
    getHorizon(data),
    (v) => isNum(v) && v > 0,
  );
}

/**
 * Uprating rate per horizon year, as a fraction (0.025 = 2.5%). The schema
 * does not say fraction or percent; fraction is assumed, consistent with the
 * `share` fields, and anything with |rate| >= 1 is rejected.
 */
export function getUprating(data, policyId) {
  return yearSeries(
    data?.central?.uprating?.[policyId],
    getHorizon(data),
    (v) => isNum(v) && Math.abs(v) < 1,
  );
}

/** Year the distributional results refer to (central.distribution_year), or null. */
export function getDistributionYear(data) {
  const year = data?.central?.distribution_year;
  return Number.isInteger(year) ? year : null;
}

const QUINTILE_LABELS = ["Bottom fifth by income", "2nd", "3rd", "4th", "Top fifth by income"];

/**
 * The "Change by group" breakdowns, in toggle order. `key` is the field in
 * central.*; `groupKey` is the field naming the group in each row.
 */
export const BREAKDOWNS = [
  { id: "quintile", label: "Income quintile", key: "by_quintile", groupKey: "quintile" },
  { id: "region", label: "Region", key: "by_region", groupKey: "region" },
  { id: "hh_type", label: "Household type", key: "by_hh_type", groupKey: "hh_type" },
  { id: "tenure", label: "Tenure", key: "by_tenure", groupKey: "tenure" },
  { id: "age", label: "Age", key: "by_age_band", groupKey: "age_band" },
];

/** Breakdowns the file includes (a non-empty object). */
export function getAvailableBreakdowns(data) {
  return BREAKDOWNS.filter((b) => {
    const block = data?.central?.[b.key];
    return block && typeof block === "object" && !Array.isArray(block) && Object.keys(block).length > 0;
  });
}

function groupLabel(breakdown, row) {
  if (breakdown.id === "quintile") {
    const q = row?.quintile;
    return Number.isInteger(q) && q >= 1 && q <= 5 ? QUINTILE_LABELS[q - 1] : null;
  }
  return isNonEmptyString(row?.label) ? row.label : null;
}

const OPTIONAL_COLUMNS = ["total_bn", "share_of_households_pct"];

/**
 * Rows of one breakdown for one rule, or null if any row is invalid.
 * mean_change_gbp, pct_income_change and a label are required (quintiles are
 * labelled from their number, "Bottom fifth by income" to "Top fifth by income"). total_bn and
 * share_of_households_pct are shown only when every row has a finite value;
 * a column present in some rows but missing or non-finite in others fails
 * the whole breakdown closed. Quintiles must be exactly 1 to 5.
 */
const HIDDEN_GROUPS = new Set(["under_66", "working_age_with_children", "working_age_no_children"]);

export function getBreakdown(data, breakdownId, policyId) {
  const breakdown = BREAKDOWNS.find((b) => b.id === breakdownId);
  const raw = breakdown ? data?.central?.[breakdown.key]?.[policyId] : null;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const columns = {};
  for (const col of OPTIONAL_COLUMNS) {
    const present = raw.filter((row) => row?.[col] !== undefined).length;
    if (present === 0) columns[col] = false;
    else if (present === raw.length && raw.every((row) => isNum(row[col]))) columns[col] = true;
    else return null;
  }
  const rows = [];
  const omitted = [];
  for (const row of raw) {
    const label = groupLabel(breakdown, row);
    // Groups the State Pension may not reach (under State Pension age, working-age
    // households) are left out only when the file shows no change for them.
    if (
      HIDDEN_GROUPS.has(row?.[breakdown.groupKey]) &&
      row.mean_change_gbp === 0 &&
      (row.total_bn === undefined || row.total_bn === 0)
    ) {
      if (label) omitted.push(label);
      continue;
    }
    if (!label || !isNum(row.mean_change_gbp) || !isNum(row.pct_income_change)) return null;
    rows.push({
      label,
      order: breakdown.id === "quintile" ? row.quintile : rows.length,
      mean_change_gbp: row.mean_change_gbp,
      pct_income_change: row.pct_income_change,
      total_bn: columns.total_bn ? row.total_bn : null,
      share_of_households_pct: columns.share_of_households_pct ? row.share_of_households_pct : null,
    });
  }
  if (breakdown.id === "quintile") {
    rows.sort((a, b) => a.order - b.order);
    if (rows.length !== 5 || !rows.every((r, i) => r.order === i + 1)) return null;
  }
  return {
    rows,
    omitted,
    hasTotal: columns.total_bn,
    hasShare: columns.share_of_households_pct,
  };
}

/** Sentence fragment naming the breakdowns present: "income, region and age". */
export function describeBreakdowns(data) {
  const words = {
    quintile: "income",
    region: "region",
    hh_type: "household type",
    tenure: "tenure",
    age: "age",
  };
  const list = getAvailableBreakdowns(data).map((b) => words[b.id]);
  if (list.length === 0) return null;
  if (list.length === 1) return list[0];
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

/** { losing_pct (0-100), mean_loss_gbp } or null. */
export function getHouseholdsAffected(data, policyId) {
  const block = data?.central?.households_affected?.[policyId];
  const pct = block?.losing_pct;
  const loss = block?.mean_loss_gbp;
  const ok = isNum(pct) && pct >= 0 && pct <= 100 && isNum(loss);
  return ok ? { losing_pct: pct, mean_loss_gbp: loss } : null;
}

export const QUANTILE_KEYS = ["p5", "p10", "p25", "p50", "p75", "p90", "p95"];

/**
 * Triple lock minus alternative, £bn in the final year (positive = the triple
 * lock costs more). All quantiles and the mean must be finite and the
 * quantiles must be in order, else null.
 */
export function getCostQuantiles(data, policyId) {
  const q = data?.uncertainty?.cost_of_triple_lock_vs?.[policyId];
  if (!q || !isNum(q.mean)) return null;
  const values = QUANTILE_KEYS.map((k) => q[k]);
  if (!values.every(isNum)) return null;
  for (let i = 1; i < values.length; i += 1) {
    if (values[i] < values[i - 1]) return null;
  }
  return Object.fromEntries([...QUANTILE_KEYS.map((k) => [k, q[k]]), ["mean", q.mean]]);
}

/**
 * Fan rows for a rule: every horizon year (plus the 2026 base year when the
 * file includes it) with ordered, positive p10/p50/p90. Null otherwise.
 */
export function getFan(data, policyId) {
  const horizon = getHorizon(data);
  const fan = data?.uncertainty?.fan?.[policyId];
  if (!horizon || !fan || typeof fan !== "object") return null;
  const base = horizon[0] - 1;
  const years = fan[String(base)] !== undefined ? [base, ...horizon] : horizon;
  const rows = [];
  for (const year of years) {
    const point = fan[String(year)];
    const [p10, p50, p90] = [point?.p10, point?.p50, point?.p90];
    if (![p10, p50, p90].every((v) => isNum(v) && v > 0)) return null;
    if (!(p10 <= p50 && p50 <= p90)) return null;
    rows.push({ year, p10, p50, p90 });
  }
  return rows;
}

/** Share of draws in which 2.5% is the binding leg, per horizon year. */
export function getFloorProbabilities(data) {
  const horizon = getHorizon(data);
  const values = yearSeries(
    data?.uncertainty?.prob_triple_lock_binds_on_floor,
    horizon,
    (v) => isNum(v) && v >= 0 && v <= 1,
  );
  return values ? horizon.map((year, i) => ({ year, share: values[i] })) : null;
}

export function getDraws(data) {
  const n = data?.uncertainty?.n_draws;
  return Number.isInteger(n) && n > 0 ? n : null;
}

/** Published inputs for the first uprating and the Aug-Sep CPI years, or null. */
export function getFirstYearInputs(data) {
  const s = data?.central?.forecast?.statutory_2027_inputs;
  const years = s?.aug_to_sep_years;
  if (!isNum(s?.earnings) || !isNum(s?.cpi) || !Array.isArray(years) || years.length !== 2) return null;
  if (!years.every(Number.isInteger)) return null;
  return { earnings: s.earnings, cpi: s.cpi, years };
}

/** How many forecast vintages and distinct macro paths the draws resample; null if absent. */
export function getBootstrapSupport(data) {
  const src = data?.uncertainty?.error_source;
  const vintages = src?.n_vintages;
  const paths = src?.n_distinct_paths;
  const pairs = src?.n_vintage_combinations;
  const firstYear = Number.isInteger(paths) && Number.isInteger(pairs) && pairs > 0 ? paths / pairs : null;
  const ok = [vintages, paths, pairs, firstYear].every((v) => Number.isInteger(v) && v > 0);
  return ok ? { vintages, paths, pairs, firstYear } : null;
}

/** Where the central-forecast cost sits in the exact distribution; null if absent. */
export function getCentralPosition(data, policyId) {
  const p = data?.uncertainty?.central_position?.by_alternative?.[policyId];
  if (!isNum(p?.central_bn) || !isNum(p?.share_below_central) || !isNum(p?.minimum_bn)) return null;
  if (p.share_below_central < 0 || p.share_below_central > 1) return null;
  return { central: p.central_bn, share: p.share_below_central, minimum: p.minimum_bn };
}

/** The leave-one-out backtest; null if absent or malformed. */
export function getBacktest(data) {
  const b = data?.uncertainty?.backtest;
  const ok = (p) => Array.isArray(p?.vintages) && p.vintages.length > 0 && p.n_within_p10_p90 && Number.isInteger(p.n_tested);
  return ok(b?.retrospective) && ok(b?.rolling_origin) ? b : null;
}

function textOrList(value) {
  if (isNonEmptyString(value)) return value;
  if (isNum(value)) return String(value);
  if (Array.isArray(value) && value.length > 0 && value.every((v) => isNonEmptyString(v) || isNum(v))) {
    return value.length > 2 && value.every(Number.isInteger)
      ? `${value[0]}–${value[value.length - 1]}`
      : value.join(", ");
  }
  return null;
}

/** Forecast error source: title and method required; url and years optional. */
export function getErrorSource(data) {
  const src = data?.uncertainty?.error_source;
  if (!isNonEmptyString(src?.title) || !isNonEmptyString(src?.method)) return null;
  return {
    title: src.title,
    url: isNonEmptyString(src.url) ? src.url : null,
    years: textOrList(src.years_used),
    method: src.method,
  };
}

export function getLimitations(data) {
  const list = data?.metadata?.method_limitations;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.every(isNonEmptyString) ? list : null;
}

/** Sources may be plain strings or { title, url }. */
export function getSources(data) {
  const list = data?.metadata?.sources;
  if (!Array.isArray(list) || list.length === 0) return null;
  const out = list.map((s) => {
    if (isNonEmptyString(s)) return { title: s, url: null };
    if (isNonEmptyString(s?.title)) {
      return { title: s.title, url: isNonEmptyString(s.url) ? s.url : null };
    }
    return null;
  });
  return out.every(Boolean) ? out : null;
}

export function getCentralForecastSource(data) {
  const f = data?.central?.forecast;
  if (!isNonEmptyString(f?.source)) return null;
  return { title: f.source, url: isNonEmptyString(f.source_url) ? f.source_url : null };
}

/**
 * Robustness rows: the main method, the raw-error and ex-2022-23
 * sensitivities and the VAR cross-check. A row appears only when its block is in the file. Its
 * quantiles are null (rendered "unavailable") when any p10/p50/p90 is
 * missing, non-finite or out of order.
 */
export const ROBUSTNESS_METHODS = [
  { id: "main", label: "Main (statutory inputs)", path: null },
  { id: "proxy", label: "OBR measures only (no statutory gaps)", path: "sensitivity_proxy_only" },
  { id: "raw", label: "Raw OBR errors (includes the OBR's past bias)", path: "sensitivity_raw_errors" },
  { id: "ex_2022_23", label: "Excluding the 2022–23 shocks", path: "sensitivity_ex_2022_23" },
  { id: "median", label: "Median-centred errors", path: "sensitivity_median_centred" },
  { id: "var", label: "VAR cross-check (OBR measures, not statutory)", path: "var_cross_check" },
  { id: "average", label: "Illustrative pool of the rows above (equal weights)", path: "model_average" },
];

export function getRobustness(data, alternatives) {
  const unc = data?.uncertainty;
  if (!unc || !Array.isArray(alternatives)) return [];
  const rows = [];
  for (const method of ROBUSTNESS_METHODS) {
    const block = method.path ? unc[method.path] : unc;
    if (block === undefined || block === null) continue;
    const byAlt = {};
    for (const alt of alternatives) {
      const q = block?.cost_of_triple_lock_vs?.[alt.id];
      const [p10, p50, p90] = [q?.p10, q?.p50, q?.p90];
      const ok = [p10, p50, p90].every(isNum) && p10 <= p50 && p50 <= p90;
      byAlt[alt.id] = ok ? { p10, p50, p90 } : null;
    }
    rows.push({ id: method.id, label: method.label, byAlt });
  }
  return rows;
}

/** A short string from the uncertainty block, or null. */
export function getUncertaintyText(data, key) {
  const value = data?.uncertainty?.[key];
  return isNonEmptyString(value) ? value : null;
}

// Notes about sections the dashboard does not show are skipped.
const SKIPPED_NOTES = new Set(["by_constituency_note"]);

/**
 * Plain-text notes the pipeline attaches under central (keys containing
 * "note" or "caveat"), searched recursively. Returns [] when there are none.
 */
export function getCentralNotes(data) {
  const out = [];
  const walk = (node, depth) => {
    if (!node || typeof node !== "object" || depth > 4) return;
    for (const [key, value] of Object.entries(node)) {
      if (/note|caveat/i.test(key) && !SKIPPED_NOTES.has(key)) {
        if (isNonEmptyString(value)) out.push(value);
        else if (Array.isArray(value)) value.filter(isNonEmptyString).forEach((v) => out.push(v));
      } else if (typeof value === "object") {
        walk(value, depth + 1);
      }
    }
  };
  walk(data?.central, 0);
  return out;
}

/** True when any rule reports largest_single_household. */
export function hasLargestHousehold(data) {
  const block = data?.central?.cost_vs_triple_lock_bn;
  return Boolean(block) && Object.values(block).some((v) => v?.largest_single_household !== undefined);
}

/**
 * Contribution of the single most influential survey household to a rule's
 * net cost, £bn, per horizon year; null if any year is invalid.
 */
export function getLargestHousehold(data, policyId) {
  const horizon = getHorizon(data);
  const block = data?.central?.cost_vs_triple_lock_bn?.[policyId]?.largest_single_household;
  if (!horizon || !block || typeof block !== "object") return null;
  const rows = horizon.map((year) => {
    const r = block[String(year)];
    return isNum(r?.contribution_bn) && isNum(r?.household_weight) && r.household_weight > 0
      ? { year, contribution_bn: r.contribution_bn, household_weight: r.household_weight }
      : null;
  });
  return rows.every(Boolean) ? rows : null;
}

/**
 * Versions for the footer. Each field is a string or null; the footer omits
 * any clause whose value is null.
 */
export function getProvenance(data) {
  const prov = data?.provenance;
  const pick = (v) => (isNonEmptyString(v) ? v : null);
  const dataset = prov?.dataset;
  return {
    policyengine: pick(prov?.packages?.policyengine),
    policyengineUk: pick(prov?.packages?.["policyengine-uk"]),
    datasetName: pick(dataset?.name),
    dataBuild: pick(dataset?.data_build),
  };
}

const LIKE_FOR_LIKE = new Set(["yes", "partial", "no"]);
/** Median (p50) of a sensitivity's cost for one alternative, or null. */
export function getSensitivityMedian(data, key, policyId) {
  const v = data?.uncertainty?.[key]?.cost_of_triple_lock_vs?.[policyId]?.p50;
  return isNum(v) ? v : null;
}

/**
 * Net cost excluding the single most influential survey household, £bn, for
 * one rule and year (negative = saving), or null.
 */
/** central.late_horizon_sensitivity, validated; null if absent or malformed. */
export function getLateHorizon(data, policyId) {
  const s = data?.central?.late_horizon_sensitivity;
  const g = s?.gross_bn?.[policyId];
  if (!isNum(g?.central) || !isNum(g?.obr_long_term)) return null;
  return { central: g.central, obr: g.obr_long_term };
}

export function getNetExcludingLargest(data, policyId, year) {
  const v = data?.central?.cost_vs_triple_lock_bn?.[policyId]?.net_excluding_largest_household?.[String(year)];
  return isNum(v) ? v : null;
}

/** That household's contribution to the net cost, £bn, or null. */
export function getLargestContribution(data, policyId, year) {
  const v = data?.central?.cost_vs_triple_lock_bn?.[policyId]?.largest_single_household?.[String(year)]?.contribution_bn;
  return isNum(v) ? v : null;
}

/**
 * central.composition_effect: gross costs under a scenario holding the 2027-28
 * pensioner composition fixed. Expected shape { difference_pct: number, description: string };
 * null if missing or invalid.
 */
export function getCompositionEffect(data) {
  const c = data?.central?.composition_effect;
  return isNum(c?.difference_pct) && isNonEmptyString(c?.description)
    ? { pct: c.difference_pct, description: c.description }
    : null;
}

/** Horizon years in which the central triple lock uprating equals the 2.5% floor. */
export function getCentralFloorYears(data) {
  const horizon = getHorizon(data);
  const tl = getUprating(data, "triple_lock");
  const floor = data?.metadata?.triple_lock_floor;
  if (!horizon || !tl || !isNum(floor)) return null;
  return horizon.filter((_, i) => Math.abs(tl[i] - floor) < 1e-9);
}

const BENCHMARK_TEXT_FIELDS = [
  "id",
  "publisher",
  "title",
  "date",
  "url",
  "figure_text",
  "comparison",
  "our_metric",
];

/**
 * metadata.benchmarks, validated. Null when the array is missing or any row
 * is invalid: every text field non-empty, our_value a finite number or a
 * non-empty string, like_for_like one of yes/partial/no, verified a boolean,
 * note a string.
 */
export function getBenchmarks(data) {
  const list = data?.metadata?.benchmarks;
  if (!Array.isArray(list) || list.length === 0) return null;
  const ok = list.every(
    (b) =>
      BENCHMARK_TEXT_FIELDS.every((f) => isNonEmptyString(b?.[f])) &&
      /^https?:\/\//.test(b.url) &&
      (isNum(b.our_value) || isNonEmptyString(b.our_value)) &&
      LIKE_FOR_LIKE.has(b.like_for_like) &&
      typeof b.verified === "boolean" &&
      typeof b.note === "string",
  );
  // Only benchmarks checked against their source are shown.
  const checked = ok ? list.filter((b) => b.verified) : [];
  return checked.length > 0 ? checked : null;
}

/** Benchmarks whose our_metric sits under `scope` ("central" or "uncertainty"). */
export function getBenchmarksFor(data, scope) {
  const list = getBenchmarks(data);
  return list ? list.filter((b) => b.our_metric.startsWith(`${scope}.`)) : null;
}

/** The VAR cross-check block, validated for the methodology comparison. */
export function getVarCrossCheck(data) {
  const v = data?.uncertainty?.var_cross_check;
  if (v === undefined) return { status: "absent" };
  if (!isNonEmptyString(v?.method)) return null;
  return {
    status: "ok",
    method: v.method,
    lagOrder: Number.isInteger(v.lag_order) ? v.lag_order : null,
    residualCorrelation: isNum(v.residual_correlation) ? v.residual_correlation : null,
    draws: Number.isInteger(v.n_draws) && v.n_draws > 0 ? v.n_draws : null,
    sources: Array.isArray(v.sources) && v.sources.every(isNonEmptyString) ? v.sources : null,
  };
}

/** Sensitivity description (e.g. ex-COVID), or null. */
export function getSensitivityDescription(data, key) {
  const d = data?.uncertainty?.[key]?.description;
  return isNonEmptyString(d) ? d : null;
}

export function getBlockHorizon(data) {
  const h = data?.uncertainty?.error_source?.block_horizon;
  return Number.isInteger(h) && h > 0 ? h : null;
}

/** Base-year (2026-27) full new State Pension £/week, or null. */
export function getBaseYearWeekly(data) {
  const b = data?.central?.base_year_weekly;
  return Number.isInteger(b?.year) && isNum(b?.new_state_pension) && b.new_state_pension > 0
    ? { year: b.year, amount: b.new_state_pension }
    : null;
}

/**
 * True when two rules give identical uprating in every horizon year on the
 * central forecast (null if either series is unavailable).
 */
export function upratingMatches(data, a, b) {
  const x = getUprating(data, a);
  const y = getUprating(data, b);
  if (!x || !y) return null;
  return x.every((v, i) => v === y[i]);
}

/** Forecast earnings growth >= CPI in every year the forecast lists, or null. */
export function earningsAtLeastCpi(data) {
  const f = data?.central?.forecast;
  if (!f?.cpi || !f?.earnings) return null;
  const years = Object.keys(f.cpi);
  if (years.length === 0 || !years.every((y) => isNum(f.cpi[y]) && isNum(f.earnings[y]))) return null;
  return years.every((y) => f.earnings[y] >= f.cpi[y]);
}

/** Basis of the Monte Carlo cost quantiles if every alternative states the same one. */
export function getUncertaintyBasis(data, alternatives) {
  const bases = alternatives.map((a) => data?.uncertainty?.cost_of_triple_lock_vs?.[a.id]?.basis);
  return bases.every((b) => b === bases[0]) && (bases[0] === "gross" || bases[0] === "net")
    ? bases[0]
    : null;
}
