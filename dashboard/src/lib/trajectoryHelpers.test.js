/**
 * Properties of the trajectory readers, for all inputs (fast-check), plus
 * fail-closed checks on the validators.
 */
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import {
  LARGEST_HOUSEHOLD_FLAG,
  bestCoverage,
  differenceNotes,
  getBacktest,
  getHistory,
  isFlagged,
  readLargestHousehold,
  readTrajectories,
  startYearsLabel,
} from "./trajectoryHelpers";
import tdata from "../../public/data/trajectory_results.json";

const rate3 = fc.integer({ min: 0, max: 120 }).map((k) => k / 1000);
const tlSource = fc.constantFrom("earnings", "cpi", "floor");
const bpSource = fc.constantFrom("triple_lock", "earnings_path", "cpi", "floor");
const row = fc.record({ tlRate: rate3, bpRate: rate3, tlSource, bpSource });

describe("differenceNotes", () => {
  it("notes exactly the years the rules differ at 0.1 point, in order, with both rates", () => {
    fc.assert(
      fc.property(fc.array(row, { minLength: 1, maxLength: 14 }), (rows) => {
        const traj = { rows: rows.map((r, i) => ({ ...r, year: 2027 + i })) };
        const notes = differenceNotes(traj);
        const differing = traj.rows.filter((r) => Math.round((r.bpRate - r.tlRate) * 1000) !== 0);
        expect(notes.map((n) => n.year)).toEqual(differing.map((r) => r.year));
        for (const [n, r] of notes.map((n, i) => [n, differing[i]])) {
          expect(n.text.startsWith(`April ${r.year}: `)).toBe(true);
          expect(n.text).toContain(`${(r.tlRate * 100).toFixed(1)}%`);
          expect(n.text).toContain(`${(r.bpRate * 100).toFixed(1)}%`);
          expect(n.higher).toBe(r.bpRate > r.tlRate);
          expect(n.text).not.toMatch(/NaN|undefined|null/);
        }
      }),
    );
  });
});

describe("startYearsLabel", () => {
  it("names every start year once and never reads as a period", () => {
    fc.assert(
      fc.property(fc.uniqueArray(fc.integer({ min: 2012, max: 2026 }), { minLength: 1, maxLength: 8 }), (ys) => {
        const years = [...ys].sort((a, b) => a - b);
        const label = startYearsLabel(years);
        expect(label.startsWith("April ")).toBe(true);
        for (const y of years) expect(label.split(String(y)).length - 1).toBe(1);
        expect(label).not.toMatch(/ to /);
        if (years.length > 1) expect(label).toContain(` or ${years.at(-1)}`);
      }),
    );
  });
});

/** A valid history block from a switch-year partition and rates. */
const historyArb = fc
  .record({
    n: fc.integer({ min: 4, max: 16 }),
    rates: fc.array(fc.tuple(rate3, rate3, fc.double({ min: 0.8, max: 1.2, noNaN: true })), { minLength: 16, maxLength: 16 }),
    cuts: fc.uniqueArray(fc.integer({ min: 1, max: 14 }), { maxLength: 4 }),
  })
  .map(({ n, rates, cuts }) => {
    const years = Array.from({ length: n }, (_, i) => 2011 + i);
    const byYear = (f) => Object.fromEntries(years.map((y, i) => [String(y), f(i)]));
    const starts = years.slice(1);
    const edges = [0, ...cuts.filter((c) => c < starts.length).sort((a, b) => a - b), starts.length];
    const groups = [];
    for (let k = 0; k + 1 < edges.length; k++) {
      const sy = starts.slice(edges[k], edges[k + 1]);
      if (!sy.length) continue;
      const changes = k % 2 === 0;
      groups.push({
        switch_years: sy,
        triple_lock_rate: byYear((i) => rates[i][0]),
        burnham_rate: byYear((i) => rates[i][1]),
        level_ratio: byYear((i) => rates[i][2]),
        changes_anything: changes,
        model_years: changes
          ? {
              saving_bn: Object.fromEntries(years.slice(-3).map((y) => [String(y), { gross: 1, net: 0.5 }])),
              actual_weekly: { new_state_pension: Object.fromEntries(years.slice(-3).map((y) => [String(y), 200])) },
              counterfactual_weekly: { new_state_pension: Object.fromEntries(years.slice(-3).map((y) => [String(y), 190])) },
            }
          : null,
      });
    }
    return {
      history: {
        years,
        model_years: years.slice(-3),
        cpi: byYear((i) => rates[i][0]),
        earnings: byYear((i) => rates[i][1]),
        actual_rise: byYear((i) => rates[i][0]),
        groups,
      },
    };
  });

describe("getHistory", () => {
  it("reads every valid block, one group per switch-year set, with the last model year's ratio", () => {
    fc.assert(
      fc.property(historyArb, (t) => {
        const h = getHistory(t);
        expect(h).not.toBeNull();
        expect(h.groups).toHaveLength(t.history.groups.length);
        const last = String(t.history.model_years.at(-1));
        h.groups.forEach((g, i) => {
          const raw = t.history.groups[i];
          expect(g.label).toBe(startYearsLabel(raw.switch_years));
          expect(g.finalRatio).toBe(raw.level_ratio[last]);
          expect(g.model === null).toBe(!raw.changes_anything);
        });
      }),
    );
  });

  it("fails closed on any rate written as a percentage or text", () => {
    fc.assert(
      fc.property(historyArb, fc.constantFrom(3.7, "x", null), fc.nat(), (t, bad, pick) => {
        const copy = structuredClone(t);
        const g = copy.history.groups[pick % copy.history.groups.length];
        const field = ["triple_lock_rate", "burnham_rate"][pick % 2];
        g[field][String(copy.history.years[pick % copy.history.years.length])] = bad;
        expect(getHistory(copy)).toBeNull();
      }),
    );
  });

  it("fails closed when a model year is outside the years", () => {
    const t = fc.sample(historyArb, 1)[0];
    t.history.model_years = [1999];
    expect(getHistory(t)).toBeNull();
  });
});

describe("largest household", () => {
  const valid = tdata.trajectories[0].largest_household;

  it("is unavailable when any field is missing or malformed", () => {
    for (const key of ["weight", "gross_contribution_bn", "share_of_income_change", "household_id", "change_gbp"]) {
      expect(readLargestHousehold({ ...valid, [key]: undefined })).toBeNull();
      expect(readLargestHousehold({ ...valid, [key]: "x" })).toBeNull();
    }
    expect(readLargestHousehold(null)).toBeNull();
  });

  it("is flagged exactly when its share of the net figure reaches the threshold", () => {
    fc.assert(
      fc.property(fc.double({ min: -3, max: 3, noNaN: true }), (share) => {
        const largest = readLargestHousehold({ ...valid, share_of_income_change: share });
        expect(isFlagged({ largest })).toBe(Math.abs(share) >= LARGEST_HOUSEHOLD_FLAG);
      }),
    );
  });

  it("counts paths that fail validation", () => {
    const copy = structuredClone(tdata);
    copy.trajectories[1].rates.burnham_2030[String(copy.horizon.at(-1))] = 3.7;
    const { trajectories, dropped } = readTrajectories(copy);
    expect(dropped).toBe(1);
    expect(trajectories).toHaveLength(tdata.trajectories.length - 1);
  });
});

describe("getBacktest", () => {
  const methods = (t) => tdata.backtest.statutory.treatments[t].chronological.methods;

  it("reads both treatments of April 2022 from the file", () => {
    const bt = getBacktest(tdata);
    expect(bt).not.toBeNull();
    for (const t of ["published", "suspended"]) {
      expect(bt[t].ranges.length).toBeGreaterThan(0);
      expect(bt[t].ranges.every((r) => r.id !== "obr_point")).toBe(true);
      const { best, missed } = bestCoverage(bt[t]);
      expect(best).toBe(Math.max(...bt[t].ranges.map((r) => methods(t)[r.id].burnham_2030_inside)));
      expect(missed.length).toBe(bt[t].nOrigins - best);
    }
  });

  it("needs at least one range method", () => {
    const copy = structuredClone(tdata);
    for (const t of ["published", "suspended"]) {
      const m = copy.backtest.statutory.treatments[t].chronological.methods;
      for (const id of Object.keys(m)) if (id !== "obr_point") delete m[id];
    }
    expect(getBacktest(copy)).toBeNull();
  });

  it("rejects a count inside the range that is impossible", () => {
    fc.assert(
      fc.property(fc.oneof(fc.integer({ min: 7, max: 50 }), fc.integer({ min: -50, max: -1 }), fc.constant(2.5)), (bad) => {
        const copy = structuredClone(tdata);
        copy.backtest.statutory.treatments.suspended.chronological.methods["iid_normal"].burnham_2030_inside = bad;
        expect(getBacktest(copy)).toBeNull();
      }),
    );
  });
});
