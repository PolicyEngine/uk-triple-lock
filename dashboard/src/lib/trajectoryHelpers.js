/**
 * Readers for trajectory_results.json. Every getter validates what it returns
 * and gives null on a missing or malformed value, so components fail closed
 * (show "unavailable") instead of printing NaN.
 */
import { isNum } from "./dataHelpers";

export const TRAJECTORY_POLICIES = ["triple_lock", "burnham_2030"];

const isText = (v) => typeof v === "string" && v.trim() !== "";
const isRate = (v) => isNum(v) && Math.abs(v) < 1;

function numbersFor(obj, keys, check = isNum) {
  if (!obj || typeof obj !== "object") return null;
  const out = keys.map((k) => obj[String(k)]);
  return out.every(check) ? out : null;
}

export function getTrajectoryHorizon(tdata) {
  const h = tdata?.horizon;
  return Array.isArray(h) && h.length > 1 && h.every(Number.isInteger) ? h : null;
}

export function getSwitchYear(tdata) {
  return Number.isInteger(tdata?.switch_year) ? tdata.switch_year : null;
}

export function getPolicyLabel(tdata, id) {
  const label = tdata?.policies?.[id]?.label;
  return isText(label) ? label : null;
}

/** Share of the final-year net figure above which one household record is flagged. */
export const LARGEST_HOUSEHOLD_FLAG = 0.2;

/** The largest single household record's contribution, validated, or null (concentration check unavailable). */
export function readLargestHousehold(lh) {
  if (!lh || typeof lh !== "object") return null;
  const numbers = [
    lh.weight,
    lh.median_weight,
    lh.contribution_bn,
    lh.share_of_income_change,
    lh.income_change_excluding_bn,
    lh.gross_contribution_bn,
  ];
  if (!numbers.every(isNum) || !Number.isInteger(lh.household_id) || lh.weight <= 0) return null;
  const change = lh.change_gbp;
  if (!change || !["housing_benefit", "pension_credit", "state_pension"].every((k) => isNum(change[k]))) return null;
  return {
    id: lh.household_id,
    weight: lh.weight,
    medianWeight: lh.median_weight,
    contribution: lh.contribution_bn,
    share: lh.share_of_income_change,
    netExcluding: -lh.income_change_excluding_bn,
    gross: lh.gross_contribution_bn,
    hb: change.housing_benefit,
    pc: change.pension_credit,
    sp: change.state_pension,
  };
}

/** Whether one household record carries at least LARGEST_HOUSEHOLD_FLAG of the path's final-year net figure. */
export function isFlagged(traj) {
  return Boolean(traj?.largest) && Math.abs(traj.largest.share) >= LARGEST_HOUSEHOLD_FLAG;
}

function readConcentration(c) {
  if (!c || typeof c !== "object") return null;
  const ok = Number.isInteger(c.household_id) && [c.share_of_income_change, c.contribution_bn, c.weight].every(isNum);
  return ok ? { id: c.household_id, share: c.share_of_income_change, contribution: c.contribution_bn, weight: c.weight } : null;
}

/** Rows (years) whose net figure one household record carries at least LARGEST_HOUSEHOLD_FLAG of. */
export function flaggedRows(traj) {
  return traj.rows.filter((r) => r.concentration && Math.abs(r.concentration.share) >= LARGEST_HOUSEHOLD_FLAG);
}

/** Whether any year's net figure, or the final year's, hangs on one household record. */
export function isFlaggedAnyYear(traj) {
  return isFlagged(traj) || flaggedRows(traj).length > 0;
}

/** One trajectory, validated and flattened for display, or null. */
export function readTrajectory(tdata, t) {
  const horizon = getTrajectoryHorizon(tdata);
  if (!horizon || !t || !isText(t.id) || !isText(t.label)) return null;
  const growthYears = horizon.map((y) => y - 1);
  const cpi = numbersFor(t.statutory?.cpi, growthYears, isRate);
  const earnings = numbersFor(t.statutory?.earnings, growthYears, isRate);
  const rates = {};
  const weekly = {};
  const sources = {};
  for (const p of TRAJECTORY_POLICIES) {
    rates[p] = numbersFor(t.rates?.[p], horizon, isRate);
    weekly[p] = numbersFor(t.weekly?.[p]?.new_state_pension, horizon, (v) => isNum(v) && v > 0);
    sources[p] = numbersFor(t.rate_sources?.[p], horizon, isText);
  }
  const gross = horizon.map((y) => t.saving_bn?.[String(y)]?.gross);
  const net = horizon.map((y) => t.saving_bn?.[String(y)]?.net);
  const losing = t.households_affected?.losing_pct;
  const meanLoss = t.households_affected?.mean_loss_gbp;
  const ok =
    cpi && earnings &&
    TRAJECTORY_POLICIES.every((p) => rates[p] && weekly[p] && sources[p]) &&
    gross.every(isNum) && net.every(isNum) && isNum(losing) && isNum(meanLoss);
  if (!ok) return null;
  return {
    id: t.id,
    label: t.label,
    source: isText(t.source) ? t.source : null,
    rateDecimals: Number.isInteger(t.rate_decimals) ? t.rate_decimals : null,
    horizon,
    rows: horizon.map((year, i) => ({
      year,
      cpi: cpi[i],
      earnings: earnings[i],
      tlRate: rates.triple_lock[i],
      bpRate: rates.burnham_2030[i],
      tlSource: sources.triple_lock[i],
      bpSource: sources.burnham_2030[i],
      tlWeekly: weekly.triple_lock[i],
      bpWeekly: weekly.burnham_2030[i],
      gross: gross[i],
      net: net[i],
      concentration: readConcentration(t.concentration_by_year?.[String(year)]),
    })),
    losingPct: losing,
    meanLoss,
    largest: readLargestHousehold(t.largest_household),
  };
}

/** Every trajectory that validates, in file order, and how many the file had that did not. */
export function readTrajectories(tdata) {
  if (!Array.isArray(tdata?.trajectories)) return { trajectories: null, dropped: 0 };
  const read = tdata.trajectories.map((t) => readTrajectory(tdata, t));
  const trajectories = read.filter(Boolean);
  return { trajectories: trajectories.length ? trajectories : null, dropped: read.length - trajectories.length };
}

export function getTrajectories(tdata) {
  return readTrajectories(tdata).trajectories;
}

const TL_SOURCE_WORDS = { earnings: "earnings growth", cpi: "CPI", floor: "the 2.5% floor" };
const BP_SOURCE_WORDS = {
  triple_lock: "the triple lock",
  earnings_path: "catching up to its earnings path",
  cpi: "CPI",
  floor: "the 2.5% floor",
};

export function describeSource(policy, source) {
  const words = policy === "triple_lock" ? TL_SOURCE_WORDS : BP_SOURCE_WORDS;
  return words[source] ?? null;
}

/**
 * Plain-language notes on the years the two rules differ, generated from the
 * rates and what set them. Rates are compared to 0.1 point.
 */
export function differenceNotes(traj) {
  const notes = [];
  for (const r of traj.rows) {
    const diff = Math.round((r.bpRate - r.tlRate) * 1000);
    if (diff === 0) continue;
    const tl = `the triple lock rises ${(r.tlRate * 100).toFixed(1)}% (${describeSource("triple_lock", r.tlSource)})`;
    const bp = `the Burnham plan ${(r.bpRate * 100).toFixed(1)}% (${describeSource("burnham_2030", r.bpSource)})`;
    const extra =
      diff > 0
        ? ": more than the triple lock, because the catch-up is rounded up while the triple lock's rate is rounded to the nearest 0.1 point"
        : "";
    notes.push({ year: r.year, text: `April ${r.year}: ${tl}; ${bp}${extra}.`, higher: diff > 0 });
  }
  return notes;
}

/** "April 2016", "April 2012 or 2013", "April 2012, 2013, 2014 or 2015". */
export function startYearsLabel(years) {
  if (years.length === 1) return `April ${years[0]}`;
  return `April ${years.slice(0, -1).join(", ")} or ${years.at(-1)}`;
}

/** Past-years block: inputs, groups and each group's full-model results, validated. */
export function getHistory(tdata) {
  const h = tdata?.history;
  const years = h?.years;
  const modelYears = h?.model_years;
  if (!Array.isArray(years) || !years.length || !years.every(Number.isInteger)) return null;
  if (!Array.isArray(modelYears) || !modelYears.length || !modelYears.every((y) => years.includes(y))) return null;
  const cpi = numbersFor(h.cpi, years, isRate);
  const earnings = numbersFor(h.earnings, years, isRate);
  if (!cpi || !earnings || !Array.isArray(h.groups) || !h.groups.length) return null;
  const groups = [];
  for (const g of h.groups) {
    const sy = g?.switch_years;
    if (!Array.isArray(sy) || !sy.length || !sy.every(Number.isInteger)) return null;
    const tl = numbersFor(g.triple_lock_rate, years, isRate);
    const bp = numbersFor(g.burnham_rate, years, isRate);
    const ratio = numbersFor(g.level_ratio, years, (v) => isNum(v) && v > 0);
    if (!tl || !bp || !ratio || typeof g.changes_anything !== "boolean") return null;
    let model = null;
    if (g.changes_anything) {
      const m = g.model_years;
      const gross = modelYears.map((y) => m?.saving_bn?.[String(y)]?.gross);
      const net = modelYears.map((y) => m?.saving_bn?.[String(y)]?.net);
      const actual = modelYears.map((y) => m?.actual_weekly?.new_state_pension?.[String(y)]);
      const cf = modelYears.map((y) => m?.counterfactual_weekly?.new_state_pension?.[String(y)]);
      if (![gross, net, actual, cf].every((a) => a.every(isNum))) return null;
      model = { gross, net, actual, counterfactual: cf };
    }
    groups.push({
      id: `from-${sy[0]}`,
      switchYears: sy,
      label: startYearsLabel(sy),
      tlRate: tl,
      bpRate: bp,
      ratio,
      finalRatio: ratio[years.indexOf(modelYears.at(-1))],
      changesAnything: g.changes_anything,
      model,
    });
  }
  const actualRise = numbersFor(h.actual_rise, years, isRate);
  return {
    years,
    modelYears,
    cpi,
    earnings,
    actualRise,
    suspendedYear: Number.isInteger(h.suspended_earnings_year) ? h.suspended_earnings_year : null,
    note: isText(h.note) ? h.note : null,
    groups,
  };
}

/** Years where the triple lock replayed on the latest figures differs from the rise actually paid (to 0.1 point). */
export function replayDifferences(history) {
  if (!history?.actualRise) return null;
  const tl = history.groups[0].tlRate;
  return history.years
    .map((year, i) => ({ year, paid: history.actualRise[i], rule: tl[i] }))
    .filter((d) => Math.round(d.paid * 1000) !== Math.round(d.rule * 1000));
}

export const BACKTEST_LABELS = {
  "monthly_boot+tilt": "Monthly model, resampled shocks (used for the paths)",
  "monthly_boot+raw": "Monthly model, resampled shocks, not calibrated",
  "monthly_tcop+tilt": "Monthly model, t-copula shocks",
  "monthly_gauss+tilt": "Monthly model, Gaussian shocks",
  "annual_boot_var+tilt+gap_blocks": "Annual model plus historical statutory gaps",
  "annual_boot_var+tilt+no_gaps": "Annual model, calendar measures only",
  block_bootstrap_statutory: "Past OBR forecast errors (the Uncertainty tab's method)",
  iid_normal: "Independent normal errors",
  obr_point: "OBR forecast alone (a point, not a range)",
};
export const POINT_METHODS = ["obr_point"];
export const BACKTEST_TREATMENTS = ["published", "suspended"];
const SMALL_ENSEMBLE = 10; // below this many paths a 10-90% interval is the paths' min-max range

function readBacktestTreatment(block) {
  const methods = block?.chronological?.methods;
  const origins = block?.chronological?.origins;
  if (!methods || typeof methods !== "object" || !Array.isArray(origins) || !origins.length) return null;
  const n = origins.length;
  const rows = [];
  for (const [id, label] of Object.entries(BACKTEST_LABELS)) {
    const m = methods[id];
    if (!m) continue;
    const row = {
      id,
      label,
      point: POINT_METHODS.includes(id),
      energy: m.energy,
      burnhamCrps: m.burnham_2030_crps_pp,
      burnhamInside: m.burnham_2030_inside,
      insideByOrigin: m.burnham_2030_inside_by_origin,
      switchesExpected: m.switches_expected,
      switchesRealised: m.switches_realised,
      minDraws: m.min_draws,
      maxDraws: m.max_draws,
    };
    const valid =
      [row.energy, row.burnhamCrps, row.switchesExpected, row.switchesRealised].every(isNum) &&
      Number.isInteger(row.burnhamInside) && row.burnhamInside >= 0 && row.burnhamInside <= n &&
      Number.isInteger(row.minDraws) && Number.isInteger(row.maxDraws) && row.minDraws >= 1 && row.minDraws <= row.maxDraws &&
      Array.isArray(row.insideByOrigin) && row.insideByOrigin.length === n &&
      row.insideByOrigin.filter((v) => v === true).length === row.burnhamInside;
    if (!valid) return null;
    row.smallEnsemble = !row.point && row.maxDraws < SMALL_ENSEMBLE;
    rows.push(row);
  }
  const ranges = rows.filter((r) => !r.point);
  const april2022 = block.april_2022_inputs;
  if (!ranges.length || !isRate(april2022?.cpi) || !isRate(april2022?.earnings)) return null;
  return { rows, ranges, origins, nOrigins: n, april2022, description: isText(block.description) ? block.description : null };
}

/** The chronological statutory backtest under both treatments of April 2022, or null. */
export function getBacktest(tdata) {
  const st = tdata?.backtest?.statutory;
  const out = {};
  for (const t of BACKTEST_TREATMENTS) {
    out[t] = readBacktestTreatment(st?.treatments?.[t]);
    if (!out[t]) return null;
  }
  const windows = st.origin_april_upratings;
  const ok = out.published.origins.every(
    (o) => Array.isArray(windows?.[o]) && windows[o].length && windows[o].every(Number.isInteger),
  );
  return ok ? { ...out, windows } : null;
}

/**
 * For one treatment: the most realised gaps any range method placed in its middle 80%, and the
 * forecasts missed by the best-scoring (lowest CRPS) of the methods that managed it.
 */
export function bestCoverage(treatment) {
  const best = Math.max(...treatment.ranges.map((r) => r.burnhamInside));
  const leader = treatment.ranges
    .filter((r) => r.burnhamInside === best)
    .reduce((a, b) => (b.burnhamCrps < a.burnhamCrps ? b : a));
  const missed = treatment.origins.filter((_, i) => !leader.insideByOrigin[i]);
  return { best, leader, missed };
}
