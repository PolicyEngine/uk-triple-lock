/**
 * Render contract against the real results file: every number checked here is read from the file, so a new
 * build updates the contract, and a missing or broken block must fail closed ("unavailable"), never NaN.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = new URLSearchParams();
const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, useSearchParams: () => searchParams }));

import Dashboard, { TAB_OPTIONS } from "./Dashboard";
import MethodTab from "./MethodTab";
import StepPensioner, { ACCOUNT } from "./StepPensioner";
import StepPopulation, { netAccount } from "./StepPopulation";
import StepTripleLock from "./StepTripleLock";
import { StepAnother, StepCentral } from "./StepPath";
import SummaryTab from "./SummaryTab";
import LandingTab from "./LandingTab";
import { trajectoryLabels } from "./PathCharts";
import { getRunsWithTables, getSavingSpread } from "../lib/dataHelpers";
import { ordinal } from "../lib/formatters";
import { readTrajectories } from "../lib/trajectoryHelpers";
import { BROKEN_TEXT, fixture, fy, mutate, realData as data } from "../lib/testUtils";

const bn = (v, d = 1) => `${v < 0 && Number(Math.abs(v).toFixed(d)) !== 0 ? "-" : ""}£${Math.abs(v).toFixed(d)}bn`;
const gbp = (v) => `${Math.round(v) < 0 ? "-" : ""}£${Math.abs(Math.round(v)).toLocaleString("en-GB")}`;
const final = data.final_year;
const { trajectories } = readTrajectories(data);
const records = getRunsWithTables(data);
const labels = trajectoryLabels(data);

describe("the page", () => {
  it("renders every step without broken text", () => {
    const { container } = render(<Dashboard data={data} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      // Formatter and inline fallbacks print a bare "unavailable"; nothing on the real file may fail validation.
      expect(text, tab.label).not.toMatch(/\bunavailable\b|\bnull\b|\bunknown\b/);
      expect(screen.queryAllByTestId("unavailable"), tab.label).toHaveLength(0);
    }
  });

  it("shows the sample banner on every step only when the file says so", () => {
    render(<Dashboard data={fixture} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      expect(screen.getByTestId("sample-banner")).toBeTruthy();
    }
  });

  it("has no sample banner on the real file", () => {
    render(<Dashboard data={data} />);
    expect(screen.queryByTestId("sample-banner")).toBeNull();
  });
});

describe("the triple lock", () => {
  it("counts which figure set each rise from the file", () => {
    render(<StepTripleLock data={data} />);
    const binding = Object.values(data.trajectories.history.triple_lock.binding);
    const n = (k) => binding.filter((b) => b === k).length;
    const text = screen.getByTestId("binding-counts").textContent.replace(/\s+/g, " ");
    expect(text).toContain(`CPI sets the rise ${n("cpi")} times, earnings ${n("earnings")} times and the 2.5% floor ${n("floor")} times`);
  });

  it("states the past-years check from the file", () => {
    render(<StepTripleLock data={data} />);
    const c = data.expected_value.past_years_check;
    expect(screen.getByTestId("past-years-check").textContent).toContain(`${c.realised_gap_pct.toFixed(1)}%`);
  });
});

describe("paths", () => {
  it("shows the central path's weekly amounts in the final year", () => {
    render(<StepCentral data={data} trajectories={trajectories} labels={labels} />);
    const w = data.central.run.weekly;
    expect(screen.getByTestId("card-tl-weekly").textContent).toContain(`£${w.triple_lock.new_state_pension[final].toFixed(2)}`);
    expect(screen.getByTestId("card-bp-weekly").textContent).toContain(`£${w.burnham_2030.new_state_pension[final].toFixed(2)}`);
  });

  it("says where each drawn path sits among the model's paths, from the file", () => {
    const drawn = data.trajectories.paths.filter((t) => t.selection);
    expect(drawn.map((t) => t.id)).toEqual(["random", "monthly_p50", "monthly_p90"]);
    for (const t of drawn) {
      const s = t.selection;
      const { unmount } = render(<StepAnother data={data} trajectories={trajectories} labels={labels} pathId={t.id} onPath={() => {}} />);
      expect(screen.getByTestId("path-position").textContent).toBe(
        `A draw at the ${ordinal(Math.round(s.gap_percentile_2039))} percentile of the model's ` +
          `${s.draws_compared.toLocaleString("en-GB")} paths: ${Math.round(s.larger_gap_pct_2039)}% of them open a ` +
          `bigger gap by ${fy(final)}, and so save more on the State Pension.`,
      );
      unmount();
    }
  });

  it("drops the position line, not the path, when the file lacks it", () => {
    const i = data.trajectories.paths.findIndex((t) => t.id === "random");
    const broken = readTrajectories(mutate(`trajectories.paths.${i}.selection.larger_gap_pct_2039`, null)).trajectories;
    render(<StepAnother data={data} trajectories={broken} labels={labels} pathId="random" onPath={() => {}} />);
    expect(screen.queryByTestId("path-position")).toBeNull();
    expect(screen.getByTestId("path-source").textContent).toContain("picked at random");
  });

  it("switches between the other paths", () => {
    const onPath = vi.fn();
    render(<StepAnother data={data} trajectories={trajectories} labels={labels} pathId="random" onPath={onPath} />);
    const other = trajectories.find((t) => t.id === "monthly_p90");
    fireEvent.change(screen.getByLabelText("Path"), { target: { value: other.id } });
    expect(onPath).toHaveBeenCalledWith("monthly_p90");
  });
});

describe("one pensioner", () => {
  it("shows each account row's effect on income from the file, and the rows sum to the net change", () => {
    const record = records.find((r) => r.id === "random");
    render(<StepPensioner data={data} records={records} labels={labels} pathId="random" onPath={() => {}} />);
    const ex = Object.keys(record.run.households.results)[0];
    const r = record.run.households.results[ex];
    const rows = within(screen.getByTestId("account-table")).getAllByRole("row").slice(1);
    let sum = 0;
    ACCOUNT.forEach((a, i) => {
      const effect = a.sign * (r.burnham_2030[a.key][final] - r.triple_lock[a.key][final]);
      sum += effect;
      expect(rows[i].textContent).toContain(gbp(effect));
    });
    const net = r.burnham_2030.net_income[final] - r.triple_lock.net_income[final];
    expect(rows.at(-1).textContent).toContain(gbp(net));
    expect(Math.abs(sum - net)).toBeLessThan(1.5);
  });
});

describe("everyone", () => {
  it("leaves little unexplained between gross and net on every path and year", () => {
    // "Everything else" is the residual: other taxes and benefits. A sign error or a missing channel would show here.
    for (const rec of records) {
      for (const y of data.distribution_years) {
        const a = netAccount(rec.run, y);
        expect(Math.abs(a.other), `${rec.id} ${y}`).toBeLessThanOrEqual(0.05 + 0.05 * Math.abs(a.gross));
      }
    }
  });

  it("signs the account as the government sees it", () => {
    const components = { pension_credit: 1, housing_benefit: 0.5, council_tax_reduction: 0, universal_credit: 0, winter_fuel_payment: 0, income_tax: -2 };
    const a = netAccount({ saving_bn: { 2039: { gross: 10, net: 6.5, components } } }, 2039);
    const row = (k) => a.rows.find((r) => r.key === k).value;
    expect(row("pension_credit")).toBe(-1); // more Pension Credit paid cuts the saving
    expect(row("housing_benefit")).toBe(-0.5);
    expect(row("income_tax")).toBe(-2); // less income tax collected cuts it too
    expect(a.other).toBeCloseTo(0, 12);
  });

  it("shows the path's gross and net saving", () => {
    render(<StepPopulation data={data} records={records} trajectories={trajectories} labels={labels} pathId="monthly_p90" onPath={() => {}} />);
    const s = records.find((r) => r.id === "monthly_p90").run.saving_bn[final];
    expect(screen.getByTestId("card-pop-gross").textContent).toContain(bn(s.gross, 2));
    expect(screen.getByTestId("card-pop-net").textContent).toContain(bn(s.net, 2));
  });
});

describe("summary", () => {
  it("shows the expected net saving, the spread across paths, the central figure and households losing", () => {
    render(<LandingTab data={data} />);
    const n = data.expected_value.estimates.primary.net[final];
    const g = data.expected_value.estimates.primary.gross[final];
    expect(screen.getByTestId("landing-expected").textContent).toContain(bn(n.mean));
    expect(screen.getByTestId("landing-expected").textContent).toContain(bn(g.mean));
    const spread = getSavingSpread(data);
    const last = spread.net.find((r) => r.year === final);
    expect(screen.getByTestId("landing-range").textContent).toContain(`${bn(last.p10)} to ${bn(last.p90)}`);
    expect(screen.getByTestId("landing-central").textContent).toContain(bn(data.central.run.saving_bn[final].net));
    expect(screen.getByTestId("spread-caveat").textContent).toMatch(/not forecast probabilities/);
  });

  it("states what the headline assumes, with the numbers from the file", () => {
    render(<LandingTab data={data} />);
    const sens = Object.values(data.expected_value.sensitivities).map((s) => s.gross[final].mean);
    expect(screen.getByTestId("assumption-paths").textContent).toContain(`${bn(Math.min(...sens))} to ${bn(Math.max(...sens))}`);
    const claims = data.coverage.rows.find((r) => r.key === "pension_credit_claims_m");
    expect(screen.getByTestId("assumption-benefits").textContent).toContain(`${claims.dwp.toFixed(2)}m`);
    expect(screen.getByTestId("assumption-benefits").textContent).toContain(bn(data.expected_value.estimates.sensitivity.net[final].mean));
    expect(screen.getByTestId("assumption-population").textContent).toContain(fy(final));
  });

  it("weights the full runs so their mean is the expected saving", () => {
    // Percentiles are ordered, and the runs' weighted mean (with the never-differing paths at zero) is the estimate.
    const spread = getSavingSpread(data);
    const S = new Map(data.expected_value.strata.map((s) => [s.stratum, s]));
    const w = data.expected_value.paths.map((p) => (S.get(p.stratum).probability * p.times_drawn) / S.get(p.stratum).paths);
    for (const key of ["gross", "net"]) {
      for (const r of spread[key]) {
        expect(r.p10 <= r.p25 && r.p25 <= r.p50 && r.p50 <= r.p75 && r.p75 <= r.p90, `${key} ${r.year}`).toBe(true);
      }
      const mean = data.expected_value.paths.reduce((a, p, i) => a + w[i] * p.outputs.primary[key][final], 0);
      const est = data.expected_value.estimates.primary[key][final];
      expect(Math.abs(mean - est.mean), key).toBeLessThan(3 * est.se + 0.05);
    }
  });

  it("fails closed when the runs lack their weights", () => {
    render(<LandingTab data={mutate("expected_value.strata", [])} />);
    expect(screen.getByTestId("unavailable")).toBeTruthy();
  });
});

describe("cost and uncertainty", () => {
  it("shows the expected saving's note", () => {
    render(<LandingTab data={data} />);
    expect(screen.getByTestId("uncertain-note").textContent).toContain(fy(final));
  });

  it("fails closed when an estimate is missing", () => {
    render(<SummaryTab data={mutate(`expected_value.estimates.primary.gross.${final}.se`, null)} />);
    expect(screen.getByTestId("unavailable")).toBeTruthy();
  });
});

describe("method", () => {
  it("shows the expected-value backtest and every coverage row from the file", () => {
    render(<MethodTab data={data} />);
    expect(screen.getByTestId("ev-backtest-table")).toBeTruthy();
    const rows = within(screen.getByTestId("coverage-table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(data.coverage.rows.length);
  });
});
