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
import { ReplicationLine } from "./Benchmarks";
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

  it("explains how the middle and 90th-percentile paths were picked, from the file", () => {
    const nRuns = data.expected_value.paths.length; // distinct full runs, as the Budget impact tab counts them
    const n = (v) => v.toLocaleString("en-GB");
    for (const id of ["monthly_p50", "monthly_p90"]) {
      const s = data.trajectories.paths.find((t) => t.id === id).selection;
      const { unmount } = render(<StepAnother data={data} trajectories={trajectories} labels={labels} pathId={id} onPath={() => {}} />);
      const text = screen.getByTestId("path-source").textContent;
      expect(text).toContain(`The model simulates ${n(s.draws_compared)} paths of prices and earnings.`);
      expect(text).toContain(`takes the ${n(s.n_candidates)} whose gap the plan opens up by ${fy(final)}`);
      expect(text).toContain(`the ${ordinal(Math.round(100 * s.quantile))} is £${s.quantile_gap_gbp_week.toFixed(2)} a week`);
      expect(text).toContain("closest to those paths' average");
      expect(text).toContain(`path ${n(s.draw)}, with a gap of £${s.gap_gbp_week.toFixed(2)} a week`);
      expect(text).toContain(`use all ${n(s.draws_compared)} paths, through ${n(nRuns)} full runs sampled across them`);
      unmount();
    }
  });

  it("falls back to the file's own sentence when the pick fields are missing", () => {
    const i = data.trajectories.paths.findIndex((t) => t.id === "monthly_p50");
    const broken = readTrajectories(mutate(`trajectories.paths.${i}.selection.n_candidates`, null)).trajectories;
    render(<StepAnother data={data} trajectories={broken} labels={labels} pathId="monthly_p50" onPath={() => {}} />);
    expect(screen.getByTestId("path-source").textContent).toBe(`${data.trajectories.paths[i].source}.`);
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

  it("breaks households down by income decile only, deciles first", () => {
    render(<StepPopulation data={data} records={records} trajectories={trajectories} labels={labels} pathId="monthly_p90" onPath={() => {}} />);
    const select = screen.getByLabelText("Group by");
    expect(select.value).toBe("by_decile");
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options[0]).toBe("Income decile");
    expect(options.some((o) => /quintile|fifth/i.test(o))).toBe(false);
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
    const rows = Object.values(data.expected_value.sensitivities);
    const sens = rows.map((s) => s.gross[final].mean);
    const top = rows.reduce((a, b) => (b.gross[final].mean > a.gross[final].mean ? b : a));
    const paths = screen.getByTestId("assumption-paths").textContent;
    expect(paths).toContain(`the lowest ${bn(Math.min(...sens))} gross`);
    // Other shock models are backtested but not run through the fiscal model (María, PR #12 re-review).
    expect(paths).toContain("does not include another model of prices and earnings");
    expect(paths).toContain(`about ${Math.round(top.effective_runs)} effective runs (standard error ${bn(top.gross[final].se)})`);
    const benefits = screen.getByTestId("assumption-benefits").textContent;
    const claims = data.coverage.rows.find((r) => r.key === "pension_credit_claims_m");
    expect(benefits).toContain(`In ${fy(data.coverage.year)} the survey has`);
    expect(benefits).toContain(`${claims.dwp.toFixed(2)}m`);
    expect(benefits).toContain("Great Britain");
    const diff = data.expected_value.paired_difference.net[final];
    const nPaired = data.expected_value.strata.reduce((a, s) => a + s.sensitivity_paths, 0);
    expect(benefits).toContain(
      `On the same ${nPaired} paths, the Microcosm dataset gives a net saving ${bn(Math.abs(diff.mean))} ${diff.mean >= 0 ? "higher" : "lower"} (standard error ${bn(diff.se)}).`,
    );
    expect(screen.getByTestId("assumption-population").textContent).toContain(fy(final));
    expect(screen.getByTestId("assumption-population").textContent).toContain("survey weights and the State Pension age");
  });

  // The pipeline writes the strip's wording from the model's configuration (#14 §5), so model-v2's ageing changes it.
  const BLOCK = [
    { key: "population", title: "Pensioners aged forward", text: "Survey ages are aged forward to 2039-40.", facts: { ages_aged_forward: true } },
    { key: "paths", title: "Paths title from the file", text: "Paths text from the file.", facts: {} },
    { key: "benefits", title: "Benefits title from the file", text: "Benefits text from the file.", facts: {} },
  ];

  it("reads the strip from the file's assumptions block when it has one", () => {
    render(<LandingTab data={mutate("assumptions", BLOCK)} />);
    for (const item of BLOCK) {
      const text = screen.getByTestId(`assumption-${item.key}`).textContent;
      expect(text).toContain(item.title);
      expect(text).toContain(item.text);
    }
    expect(screen.getByTestId("assumptions").textContent).not.toContain("survey weights and the State Pension age");
  });

  it("computes the strip from the file's figures only for a file without the block", () => {
    render(<LandingTab data={mutate("assumptions", null, { remove: true })} />);
    const strip = screen.getByTestId("assumptions").textContent;
    expect(screen.getByTestId("assumption-population").textContent).toContain("survey weights and the State Pension age");
    expect(screen.getByTestId("assumption-paths").textContent).toContain("does not include another model of prices and earnings");
    expect(screen.getByTestId("assumption-benefits").textContent).toContain("Great Britain");
    expect(strip).not.toContain("from the file");
    expect(strip).not.toMatch(BROKEN_TEXT);
  });

  // A block that is present but damaged never brings back the computed strip's "held fixed" wording.
  it.each([
    ["an item without text", [BLOCK[0], { ...BLOCK[1], text: "" }, BLOCK[2]], ["population", "benefits"]],
    ["a repeated key", [BLOCK[0], { ...BLOCK[1], key: "population" }, BLOCK[2]], ["population", "benefits"]],
    ["an item that is not an object", [BLOCK[0], "x", BLOCK[2]], ["population", "benefits"]],
  ])("shows only the valid items given %s", (_, block, keys) => {
    render(<LandingTab data={mutate("assumptions", block)} />);
    const strip = screen.getByTestId("assumptions").textContent;
    for (const key of ["population", "paths", "benefits"]) {
      if (keys.includes(key)) expect(screen.getByTestId(`assumption-${key}`).textContent).toContain(BLOCK.find((b) => b.key === key).text);
      else expect(screen.queryByTestId(`assumption-${key}`)).toBeNull();
    }
    expect(strip).not.toContain("held fixed");
    expect(strip).not.toContain("survey weights and the State Pension age");
  });

  it.each([
    ["an empty block", []],
    ["a block that is not a list", "x"],
    ["null", null],
    ["no valid item", [{ key: "population", title: "", text: "x" }]],
  ])("shows no strip given %s", (_, block) => {
    render(<LandingTab data={mutate("assumptions", block)} />);
    expect(screen.queryByTestId("assumptions")).toBeNull();
    expect(screen.getByTestId("landing-expected")).toBeTruthy();
  });

  it("says what the households-losing card's numbers are", () => {
    render(<LandingTab data={data} />);
    const text = screen.getByTestId("landing-losing").textContent;
    expect(text).toContain(`Expected share of households in ${fy(final).replace("-", "\u2011")}.`);
    expect(text).toMatch(/On 80% of paths it is between \d+% and \d+%\./);
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

  it("sets Great Britain against DWP's figures where the file gives it (model-v2)", () => {
    const rows = data.coverage.rows.map((r) => ({ ...r, primary_gb: 0.5, sensitivity_gb: 0.25 }));
    render(<MethodTab data={{ ...data, coverage: { ...data.coverage, rows } }} />);
    const table = screen.getByTestId("coverage-table");
    expect(table.textContent).toContain("Enhanced FRS, GB");
    const first = within(table).getAllByRole("row")[1];
    expect(first.textContent).toMatch(/0\.5|0\.50/);
  });
});

describe("replication line", () => {
  it("names the policyengine.py bundle in a file built before model-v2", () => {
    render(<ReplicationLine data={data} />);
    const text = screen.getByTestId("replication").textContent;
    if (data.provenance.release_bundle) expect(text).toContain(data.provenance.release_bundle.policyengine_version);
  });

  it("names the pinned policyengine-uk, the data release and that no bundle certifies them (model-v2)", () => {
    const model = {
      model_version: "2.118.0", runtime_dataset: "enhanced_frs_2024_25", data_package: "policyengine-uk-data",
      data_version: "1.56.16", certified: false,
    };
    const { release_bundle: _bundle, ...rest } = data.provenance;
    render(<ReplicationLine data={{ ...data, provenance: { ...rest, model } }} />);
    const text = screen.getByTestId("replication").textContent;
    expect(text).toContain("policyengine-uk 2.118.0 on enhanced_frs_2024_25 (policyengine-uk-data 1.56.16)");
    expect(text).toContain("no policyengine.py release has certified");
  });

  it("shows nothing it cannot source", () => {
    const { release_bundle: _bundle, ...rest } = data.provenance;
    render(<ReplicationLine data={{ ...data, provenance: rest }} />);
    expect(screen.getByTestId("replication").textContent).not.toContain("undefined");
  });
});
