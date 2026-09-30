import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { netAccount, NET_ACCOUNT } from "../components/StepPopulation";
import { pathIndex } from "../components/StepPath";
import { fyLabel, getCoverage, getExpectedValue, getHorizon } from "./dataHelpers";
import { mutate, realData } from "./testUtils";

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
    expect(ev.primary.gross).toHaveLength(realData.horizon.length);
    expect(ev.nUniquePaths).toBe(realData.expected_value.paths.length);
  });

  it.each(["mean", "se"])("is null when any year's %s is missing or negative", (k) => {
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
