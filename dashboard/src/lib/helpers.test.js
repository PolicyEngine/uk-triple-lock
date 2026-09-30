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
  it("compounds the rates and never lets the plan exceed the triple lock by more than rounding (property)", () => {
    const rate = fc.double({ min: 0, max: 0.1, noNaN: true });
    fc.assert(
      fc.property(fc.array(fc.tuple(rate, rate), { minLength: 1, maxLength: 13 }), (pairs) => {
        const traj = { rows: pairs.map(([tl, extra], i) => ({ year: 2027 + i, tlRate: tl, bpRate: Math.max(0, tl - extra), cpi: 0.02, earnings: 0.03 })) };
        const rows = pathIndex(traj);
        return rows.length === pairs.length + 1 && rows.every((r) => r.burnham_2030 <= r.triple_lock + 1e-9);
      }),
    );
  });
});
