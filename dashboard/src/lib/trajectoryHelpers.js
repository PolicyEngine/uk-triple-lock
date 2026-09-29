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
  const lh = t.largest_household;
  const largest =
    lh && [lh.weight, lh.median_weight, lh.contribution_bn, lh.share_of_income_change, lh.income_change_excluding_bn].every(isNum) &&
    Number.isInteger(lh.household_id) && lh.change_gbp && ["housing_benefit", "pension_credit", "state_pension"].every((k) => isNum(lh.change_gbp[k]))
      ? {
          id: lh.household_id,
          weight: lh.weight,
          medianWeight: lh.median_weight,
          contribution: lh.contribution_bn,
          share: lh.share_of_income_change,
          netExcluding: -lh.income_change_excluding_bn,
          hb: lh.change_gbp.housing_benefit,
          pc: lh.change_gbp.pension_credit,
          sp: lh.change_gbp.state_pension,
        }
      : null;
  return {
    id: t.id,
    label: t.label,
    source: isText(t.source) ? t.source : null,
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
    })),
    losingPct: losing,
    meanLoss,
    largest,
  };
}

/** Share of the final-year net figure above which one household record is flagged. */
export const LARGEST_HOUSEHOLD_FLAG = 0.2;

/** Every trajectory that validates, in file order. */
export function getTrajectories(tdata) {
  if (!Array.isArray(tdata?.trajectories)) return null;
  const out = tdata.trajectories.map((t) => readTrajectory(tdata, t)).filter(Boolean);
  return out.length ? out : null;
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
 * rates and what set them. Rates are compared at the file's 3 dp.
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

/** Past-years block: inputs, groups and each group's full-model results, validated. */
export function getHistory(tdata) {
  const h = tdata?.history;
  const years = h?.years;
  const modelYears = h?.model_years;
  if (!Array.isArray(years) || !years.every(Number.isInteger)) return null;
  if (!Array.isArray(modelYears) || !modelYears.every(Number.isInteger)) return null;
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
      label: sy.length > 1 ? `April ${sy[0]} to ${sy[sy.length - 1]}` : `April ${sy[0]}`,
      tlRate: tl,
      bpRate: bp,
      ratio,
      changesAnything: g.changes_anything,
      model,
    });
  }
  return {
    years,
    modelYears,
    cpi,
    earnings,
    suspendedYear: Number.isInteger(h.suspended_earnings_year) ? h.suspended_earnings_year : null,
    note: isText(h.note) ? h.note : null,
    groups,
  };
}

export const BACKTEST_LABELS = {
  "monthly_tcop+tilt": "Monthly model, t-copula (used for the paths)",
  "monthly_gauss+tilt": "Monthly model, Gaussian",
  "annual_boot_var+tilt+gap_blocks": "Annual model plus historical statutory gaps",
  "annual_boot_var+tilt+no_gaps": "Annual model, calendar measures only",
  block_bootstrap_statutory: "Past OBR forecast errors (the Uncertainty tab's method)",
  iid_normal: "Independent normal errors",
  obr_point: "OBR forecast alone",
};

/** Rows of the chronological statutory backtest, in BACKTEST_LABELS order. */
export function getBacktestRows(tdata) {
  const methods = tdata?.backtest?.statutory?.chronological?.methods;
  const origins = tdata?.backtest?.statutory?.chronological?.origins;
  if (!methods || !Array.isArray(origins)) return null;
  const rows = Object.entries(BACKTEST_LABELS)
    .filter(([id]) => methods[id])
    .map(([id, label]) => {
      const m = methods[id];
      return {
        id,
        label,
        energy: m.energy,
        burnhamCrps: m.burnham_2030_crps_pp,
        burnhamInside: m.burnham_2030_inside,
        switchesExpected: m.switches_expected,
        switchesRealised: m.switches_realised,
      };
    });
  const ok = rows.length && rows.every((r) =>
    [r.energy, r.burnhamCrps, r.switchesExpected, r.switchesRealised].every(isNum) && Number.isInteger(r.burnhamInside));
  return ok ? { rows, nOrigins: origins.length } : null;
}
