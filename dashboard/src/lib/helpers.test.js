import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { netAccount, NET_ACCOUNT } from "../components/StepPopulation";
import { pathIndex } from "../components/StepPath";
import { fyLabel, getC2Screen, getPastYearsCheck, getCoverage, getCoverageRow, getExpectedValue, getHorizon, getSensitivityRange } from "./dataHelpers";
import { c2Fixture } from "./c2TestFixtures";
import { mutate, realData } from "./testUtils";
import { describeSource } from "./trajectoryHelpers";

describe("fyLabel", () => {
  it("names fiscal years by start year", () => {
    expect(fyLabel(2039)).toBe("2039-40");
    expect(fyLabel(2099)).toBe("2099-00");
    expect(fyLabel("2039")).toBe("unavailable");
  });
});

describe("getHorizon", () => {
  it("refuses a horizon that is not increasing integers", () => {
    expect(getHorizon({ horizon: [2027, 2027] })).toBeNull();
    expect(getHorizon({ horizon: [2027, "2028"] })).toBeNull();
    expect(getHorizon(realData)).toEqual(realData.horizon);
  });
});

describe("getExpectedValue", () => {
  it("reads the real file", () => {
    const ev = getExpectedValue(realData);
    if (realData.expected_value) {
      expect(ev.primary.gross).toHaveLength(realData.horizon.length);
      expect(ev.nUniquePaths).toBe(realData.expected_value.paths.length);
    } else expect(ev).toBeNull();
  });

  it.skipIf(!realData.expected_value).each(["mean", "se"])("is null when any year's %s is missing or negative", (k) => {
    const y = realData.horizon[3];
    expect(getExpectedValue(mutate(`expected_value.estimates.primary.net.${y}.${k}`, null))).toBeNull();
    if (k === "se") expect(getExpectedValue(mutate(`expected_value.estimates.primary.net.${y}.se`, -1))).toBeNull();
  });
});

describe("getCoverage", () => {
  it("is null when a row lacks a number", () => {
    expect(getCoverage(mutate("coverage.rows.0.dwp", "x"))).toBeNull();
    expect(getCoverage(realData).rows).toHaveLength(realData.coverage.rows.length);
  });
});

describe("getCoverageRow", () => {
  it("needs only the DWP and survey figures, and fails closed on a malformed table", () => {
    const i = realData.coverage.rows.findIndex((r) => r.key === "pension_credit_claims_m");
    expect(getCoverageRow(mutate(`coverage.rows.${i}.sensitivity`, null), "pension_credit_claims_m")).not.toBeNull();
    expect(getCoverageRow(mutate(`coverage.rows.${i}.dwp`, null), "pension_credit_claims_m")).toBeNull();
    expect(getCoverageRow(mutate("coverage.rows", { key: "pension_credit_claims_m" }), "pension_credit_claims_m")).toBeNull();
  });
});

describe("getSensitivityRange", () => {
  it.skipIf(!Object.keys(realData.expected_value?.sensitivities ?? {}).length)("gives the highest row's effective runs and standard error, or null for them when missing", () => {
    const year = realData.final_year;
    const r = getSensitivityRange(realData, "gross", year);
    const [name, top] = Object.entries(realData.expected_value.sensitivities).reduce((a, b) => (b[1].gross[year].mean > a[1].gross[year].mean ? b : a));
    expect(r.hi).toBe(top.gross[year].mean);
    expect(r.max).toEqual({ se: top.gross[year].se, effectiveRuns: top.effective_runs });
    const copy = structuredClone(realData); // sensitivity names contain dots, so not mutate()
    copy.expected_value.sensitivities[name].effective_runs = null;
    const noRuns = getSensitivityRange(copy, "gross", year);
    expect(noRuns.max).toBeNull();
    expect(noRuns.hi).toBe(r.hi);
  });
});

describe("netAccount", () => {
  it("always accounts from gross to net (property)", () => {
    const money = fc.double({ min: -50, max: 50, noNaN: true });
    fc.assert(
      fc.property(money, money, fc.array(money, { minLength: NET_ACCOUNT.length, maxLength: NET_ACCOUNT.length }), (gross, net, comps) => {
        const components = Object.fromEntries(NET_ACCOUNT.map((a, i) => [a.key, comps[i]]));
        const a = netAccount({ saving_bn: { 2039: { gross, net, components } } }, 2039);
        return Math.abs(a.gross + a.rows.reduce((t, r) => t + r.value, 0) + a.other - a.net) < 1e-9;
      }),
    );
  });

  it("is null when a component is missing", () => {
    expect(netAccount({ saving_bn: { 2039: { gross: 1, net: 1, components: {} } } }, 2039)).toBeNull();
  });
});

describe("pathIndex", () => {
  it("is 100 times the product of (1 + rate) for every series (property)", () => {
    const rate = fc.double({ min: -0.05, max: 0.15, noNaN: true });
    fc.assert(
      fc.property(fc.array(fc.tuple(rate, rate, rate, rate), { minLength: 1, maxLength: 13 }), (rows) => {
        const traj = { rows: rows.map(([tl, bp, c, e], i) => ({ year: 2027 + i, tlRate: tl, bpRate: bp, cpi: c, earnings: e })) };
        const out = pathIndex(traj);
        if (out.length !== rows.length + 1 || out[0].triple_lock !== 100) return false;
        const prod = (k) => rows.reduce((p, r) => p * (1 + r[k]), 100);
        const last = out.at(-1);
        const close = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));
        return close(last.triple_lock, prod(0)) && close(last.burnham_2030, prod(1)) && close(last.cpi, prod(2)) && close(last.earnings, prod(3));
      }),
    );
  });
});

describe("ordinal and formatters", () => {
  it("gives English ordinals", async () => {
    const { ordinal, formatPct, formatPoints } = await import("./formatters");
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 55, 93, 101, 111, 112].map(ordinal)).toEqual(
      ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "55th", "93rd", "101st", "111th", "112th"]);
    expect(formatPct(-0.001, 1)).toBe("0.0%");
    expect(formatPoints(-0.02)).toBe("0.0");
    expect(formatPoints(1.23)).toBe("+1.2");
  });
});

describe("axisDigits", () => {
  it("gives every tick of an axis enough decimals to print distinctly (property)", async () => {
    const { axisDigits, niceTicks } = await import("./ticks");
    fc.assert(
      fc.property(fc.double({ min: -1000, max: 1000, noNaN: true }), fc.double({ min: 0.01, max: 1000, noNaN: true }), (lo, span) => {
        const values = [lo, lo + span];
        const d = axisDigits(values);
        const labels = niceTicks(lo, lo + span).map((t) => t.toFixed(d));
        return new Set(labels).size === labels.length && labels.every((l, i) => Math.abs(Number(l) - niceTicks(lo, lo + span)[i]) < 1e-9);
      }),
    );
  });
});

describe("a drawn path's position", () => {
  const good = { gap_percentile_2039: 2.35, larger_gap_pct_2039: 97.65, draws_compared: 50000 };

  it("is read from the selection, and is null for the central path or a bad value", async () => {
    const { readPosition } = await import("./trajectoryHelpers");
    expect(readPosition(good)).toEqual({ percentile: 2.35, larger: 97.65, draws: 50000 });
    expect(readPosition(undefined)).toBeNull();
    const bad = [["gap_percentile_2039", -1], ["gap_percentile_2039", 101], ["larger_gap_pct_2039", "x"],
      ["larger_gap_pct_2039", null], ["draws_compared", 2.5], ["draws_compared", 0]];
    for (const [k, v] of bad) expect(readPosition({ ...good, [k]: v }), `${k}=${v}`).toBeNull();
  });

  it("is worded without a 0th percentile or a rounded-away share", async () => {
    const { positionText } = await import("./trajectoryHelpers");
    expect(positionText({ percentile: 2.35, larger: 97.65, draws: 50000 }, "2039-40")).toBe(
      "A draw at the 2nd percentile of the model's 50,000 paths: 98% of them open a bigger gap by 2039-40, and so save more on the State Pension.");
    expect(positionText({ percentile: 0.2, larger: 99.7, draws: 10 }, "2039-40")).toMatch(/below the 1st percentile .*: over 99% of them/);
    expect(positionText({ percentile: 99.8, larger: 0.1, draws: 10 }, "2039-40")).toMatch(/above the 99th percentile .*: under 1% of them/);
    expect(positionText({ percentile: 100, larger: 0, draws: 10 }, "2039-40")).toContain(": 0% of them");
  });

  it("never prints a 0th or 100th percentile or a broken number (property)", async () => {
    const { positionText } = await import("./trajectoryHelpers");
    const share = fc.double({ min: 0, max: 100, noNaN: true });
    fc.assert(
      fc.property(share, share, fc.integer({ min: 1, max: 1e6 }), (percentile, larger, draws) => {
        const text = positionText({ percentile, larger, draws }, "2039-40");
        return !/\b0th\b|100th|NaN|undefined|(^|\s)-\d/.test(text);
      }),
    );
  });
});

describe("trajectory readers fail closed", () => {
  it("reads every path in the real file, and drops (and counts) a malformed one", async () => {
    const { readTrajectories, getHistory } = await import("./trajectoryHelpers");
    const all = readTrajectories(realData);
    expect(all.trajectories).toHaveLength(realData.trajectories.paths.length);
    expect(all.dropped).toBe(0);
    const y = String(realData.horizon[4]);
    const broken = mutate(`trajectories.paths.1.saving_bn.${y}.gross`, "x");
    const read = readTrajectories(broken);
    expect(read.dropped).toBe(1);
    expect(read.trajectories).toHaveLength(realData.trajectories.paths.length - 1);
    expect(getHistory(realData)).not.toBeNull();
    expect(getHistory(mutate("trajectories.history.cpi", null))).toBeNull();
  });
});

describe("describeSource", () => {
  it("names every label a run's rate_sources can carry, a scenario's specified rates included", () => {
    for (const s of ["earnings", "cpi", "floor", "specified"]) expect(describeSource("triple_lock", s)).not.toBeNull();
    for (const s of ["triple_lock", "earnings_path", "cpi", "floor", "specified"]) {
      expect(describeSource("burnham_2030", s)).not.toBeNull();
    }
    expect(describeSource("triple_lock", "given")).toBeNull();
  });
});


describe("frozen C2 provenance", () => {
  it.each([true, false])("reads diagnostics whether the primary passes=%s", (passes) => {
    const data = c2Fixture(passes);
    const screen = getC2Screen(data);
    expect(screen.primaryPasses).toBe(passes);
    expect(screen.rows).toHaveLength(8);
    expect(getPastYearsCheck(data).realised_gap_pct).toBe(6.3);
    expect(getPastYearsCheck(data).published.realised_gap_pct).toBe(10.9);
    expect(Boolean(getExpectedValue(data))).toBe(passes);
  });

  it("fails closed on malformed C2 score tables", () => {
    const data = c2Fixture();
    data.uncertainty_screen.c2_scores.scores.A.suspended.monthly_var1_boot.annual_gap_coverage.mean = null;
    expect(getC2Screen(data)).toBeNull();
  });
});
