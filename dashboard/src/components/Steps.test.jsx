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
import { ACCOUNT } from "./StepPensioner";
import StepPopulation, { netAccount } from "./StepPopulation";
import StepTripleLock from "./StepTripleLock";
import { StepPaths } from "./StepPath";
import SummaryTab from "./SummaryTab";
import LandingTab from "./LandingTab";
import MeanPathScenarios from "./MeanPathScenarios";
import BenchmarksTable, { ReplicationLine } from "./Benchmarks";
import { AllPathsTable, recordNotes, trajectoryLabels, YearTable } from "./PathCharts";
import { getC2Screen, getPastYearsCheck, getRunsWithTables, getSavingSpread, getScenarioHeadline, getSensitivityRange, inQuotedRange, isPreBudget, isScenariosOnly } from "../lib/dataHelpers";
import { c2Fixture } from "../lib/c2TestFixtures";
import { formatAnnualFromWeekly, ordinal } from "../lib/formatters";
import { readTrajectories, readTrajectory } from "../lib/trajectoryHelpers";
import { BROKEN_TEXT, fixture, fy, mutate, realData as data } from "../lib/testUtils";

const bn = (v, d = 1) => `${v < 0 && Number(Math.abs(v).toFixed(d)) !== 0 ? "-" : ""}£${Math.abs(v).toFixed(d)}bn`;
const final = data.final_year;
const hasEv = Boolean(data.expected_value);
const { trajectories } = readTrajectories(data);
const records = getRunsWithTables(data);
const labels = trajectoryLabels(data);

describe("DWP comparison", () => {
  it("quotes direct AME savings with the supported Pensim3 comparison and HL3774", () => {
    render(<BenchmarksTable data={data} />);
    const row = screen.getByText("Department for Work and Pensions").closest("tr");
    expect(row.textContent).toContain("£15bn annual nominal direct AME saving in 2039-40");
    expect(row.textContent).toContain("Great Britain, using Pensim3");
    expect(row.textContent).toContain("published assumptions do not allow a like-for-like comparison");
    expect(row.textContent).toContain("excludes tax and debt-interest effects");
    expect(row.textContent).not.toMatch(/one (?:unstated uprating |uprating )?path|single path/);
    expect(within(row).getByRole("link", { name: "HL3774 (15 October 2026)" }).getAttribute("href"))
      .toBe("https://questions-statements.parliament.uk/written-questions/detail/2026-10-05/hl3774");
  });
});

describe("recorded uncertainty rulings", () => {
  it("omits single-record outputs from the summary and path notes for cached legacy results", () => {
    const copy = c2Fixture();
    copy.expected_value.estimates.primary.net_excluding_largest_record = Object.fromEntries(
      copy.horizon.map((year) => [year, { mean: 9876.54321, se: 0.12345 }]),
    );
    const path = copy.trajectories.paths[0];
    path.largest_household = { contribution_bn: 9876.54321, share_of_income_change: 0.87654321,
                              income_change_excluding_bn: -1234.56789 };
    path.concentration_by_year = Object.fromEntries(copy.horizon.map((year) => [year, {
      contribution_bn: 8765.4321, share_of_income_change: 0.7654321,
    }]));
    const { container } = render(<SummaryTab data={copy} />);
    expect(container.textContent).toContain("Model-conditional expected value");
    // The earnings scenarios are shown once on the Budget impact tab, by its landing part, not again here.
    expect(container.textContent).not.toContain("Earnings scenarios");
    expect(container.textContent).not.toContain("One survey record.");
    expect(container.textContent).not.toContain("9876.5");
    const traj = readTrajectory(copy, path);
    expect(recordNotes(traj)).toEqual([]);
    const tables = render(<>
      <YearTable traj={traj} labels={trajectoryLabels(copy)} />
      <AllPathsTable trajectories={[traj]} selected={traj.id} onSelect={() => {}} />
    </>);
    expect(tables.container.textContent).not.toContain("Largest household");
    expect(tables.container.textContent).not.toContain("9876.5");
    expect(tables.container.textContent).toContain(bn(traj.rows.at(-1).gross, 2));
    expect(container.textContent).not.toMatch(BROKEN_TEXT);
  });

  it.each([true, false])("renders every tab for a synthetic C2 primary pass=%s without legacy diagnostics", (passes) => {
    const copy = c2Fixture(passes);
    expect(copy.expected_value?.backtest).toBeUndefined();
    expect(copy.expected_value?.past_years_check).toBeUndefined();
    const { container } = render(<Dashboard data={copy} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      expect(container.textContent, tab.label).not.toMatch(BROKEN_TEXT);
    }
    fireEvent.click(screen.getByRole("tab", { name: "Methodology" }));
    const table = screen.getByTestId("c2-screen-table");
    expect(table.textContent).toContain("80.0%");
    expect(table.textContent).toContain("20 / 4");
    expect(table.textContent).toContain("4/6");
    expect(table.textContent).toContain("As published");
    expect(table.textContent).toContain("1/6");
    expect(screen.queryByTestId("ev-backtest-table")).toBeNull();
    if (!passes) expect(screen.getByTestId("expected-value-omission").textContent).toContain("only scenarios are shown");
  });

  it("shows the automatic C2 fallback and scenarios once on the Budget impact tab", () => {
    const copy = c2Fixture(false);
    const { container } = render(<Dashboard data={copy} />);
    expect(screen.getAllByRole("heading", { name: /scenario envelope/i })).toHaveLength(1);
    expect(screen.getAllByTestId("scenario-interpretation")).toHaveLength(1);
    expect(screen.getByTestId("scenario-interpretation").textContent).toContain("primary failed C2");
    expect(screen.getByTestId("scenario-fallback-reason").textContent).toContain("terminal coverage below the threshold");
    expect(screen.getByTestId("scenario-earnings-upper").textContent).toContain("Earnings +0.5 points from 2031");
    expect(screen.getByTestId("scenario-earnings-lower").textContent).toContain("Earnings −0.5 points from 2031");
    expect(screen.queryByTestId("landing-expected")).toBeNull();
    expect(screen.getByTestId("dwp-box")).toBeTruthy();
    expect(container.textContent).not.toContain("Model-conditional expected value");
    expect(container.textContent).not.toMatch(BROKEN_TEXT);
    expect(container.textContent).not.toMatch(/\bunavailable\b/);
  });

  it.each([true, false])("keeps the C2 past-years check, in plain words, when pass=%s", (passes) => {
    const file = c2Fixture(passes);
    render(<StepTripleLock data={file} />);
    const c = getPastYearsCheck(file);
    const text = screen.getByTestId("past-years-check").textContent;
    expect(text).toContain(`${c.model.mean_gap_pct.toFixed(1)}%`);
    expect(text).toContain("percentile");
    expect(text).not.toMatch(/sensitivity only/);
  });

  it("renders scenario-envelope results without an expected-value section", () => {
    const copy = structuredClone(data);
    delete copy.expected_value;
    copy.uncertainty_ruling = { ruling: "a" };
    copy.mean_path_scenarios = { scenarios: { lower: {
      calendar_earnings_delta: -0.005,
      scenario_path_set: { gross: { [final]: { mean: 2, se: 0.1 } }, net: { [final]: { mean: 1, se: 0.05 } } },
    } } };
    const { container } = render(<LandingTab data={copy} />);
    expect(screen.getAllByRole("heading", { name: /scenario envelope/i })).toHaveLength(1);
    expect(container.textContent).toContain("£2.0bn ± £0.2bn");
    expect(container.textContent).toContain("Earnings −0.5 points from 2031");
    expect(container.textContent).not.toMatch(BROKEN_TEXT);
    expect(container.textContent).not.toMatch(/\bunavailable\b/);
  });

  it("says a pre-Budget release withholds the expected value until the Budget, not that the ruling omits it", () => {
    render(<MeanPathScenarios data={preBudgetCopy()} />);
    const text = screen.getByTestId("scenario-interpretation").textContent;
    expect(text).toContain("this pre-Budget release shows scenarios only");
    expect(text).toContain("28 October Budget inputs");
    expect(text).not.toContain("The recorded method ruling omits an expected value.");
  });

  it("renders a changed release Budget date in the mean-path wording", () => {
    const copy = preBudgetCopy();
    copy.release.budget_date = "2026-11-04";
    render(<MeanPathScenarios data={copy} />);
    expect(screen.getByTestId("scenario-interpretation").textContent).toContain("4 November Budget inputs");
  });

  it("reads each earnings scenario's recorded start year", () => {
    const copy = structuredClone(data);
    copy.mean_path_scenarios = { scenarios: {
      upper: { calendar_earnings_delta: 0.005, from_year: 2032 },
      lower: { calendar_earnings_delta: -0.005, from_year: 2034 },
    } };
    render(<MeanPathScenarios data={copy} />);
    expect(screen.getByText("+0.5 points from 2032")).toBeTruthy();
    expect(screen.getByText("−0.5 points from 2034")).toBeTruthy();
    expect(screen.queryByText(/from 2031/)).toBeNull();
  });

  it("labels the original-primary expected value as model conditional", () => {
    const copy = c2Fixture();
    copy.expected_value.provenance = { ruling: "b" };
    render(<SummaryTab data={copy} />);
    expect(screen.getByText(/Model-conditional expected value/)).toBeTruthy();
  });

  it.each([["landing", LandingTab], ["summary", SummaryTab]])("shows ruling c's conditional expected value beside recorded scenarios on the %s tab", (tab, Component) => {
    const copy = c2Fixture();
    copy.uncertainty_ruling = { ruling: "c" };
    copy.expected_value.provenance = { ruling: "c" };
    copy.mean_path_scenarios = { scenarios: {
      upper: { calendar_earnings_delta: 0.005, from_year: 2032,
        scenario_path_set: { gross: { [final]: { mean: 8, se: 0.2 } }, net: { [final]: { mean: 6, se: 0.15 } } } },
      lower: { calendar_earnings_delta: -0.005, from_year: 2034,
        scenario_path_set: { gross: { [final]: { mean: 2, se: 0.1 } }, net: { [final]: { mean: 1, se: 0.05 } } } },
    } };
    const { container } = render(<Component data={copy} />);
    if (tab === "landing") {
      // The earnings scenarios sit beside the expected value once, on the landing part of the tab.
      expect(screen.getAllByRole("heading", { name: "Earnings scenarios" })).toHaveLength(1);
      expect(screen.getByText("+0.5 points from 2032")).toBeTruthy();
      expect(screen.getByText("−0.5 points from 2034")).toBeTruthy();
      for (const value of ["£8.0bn ± £0.4bn", "£6.0bn ± £0.3bn", "£2.0bn ± £0.2bn", "£1.0bn ± £0.1bn"]) {
        expect(screen.getByText(value)).toBeTruthy();
      }
      expect(container.textContent).toContain("shown beside the model-conditional expected value");
    } else {
      expect(screen.queryByRole("heading", { name: "Earnings scenarios" })).toBeNull();
    }
    expect(container.textContent).not.toContain("omits an expected value");
    expect(container.textContent).not.toContain("fails its frozen adequacy backtest");
    if (tab === "landing") {
      const card = screen.getByTestId("landing-expected");
      expect(card.textContent).toContain("Model-conditional saving");
      expect(card.textContent).toContain(bn(copy.expected_value.estimates.primary.net[final].mean));
    } else {
      fireEvent.click(screen.getByRole("tab", { name: /Weighting paths to past volatility/ }));
      expect(screen.getByTestId("calibration-table").textContent).toContain("Model-conditional saving");
      expect(screen.getByTestId("calibration-table").textContent).toContain(bn(copy.expected_value.estimates.primary.gross[final].mean));
    }
    expect(container.textContent).not.toContain("Expected saving");
    expect(container.textContent).not.toMatch(BROKEN_TEXT);
  });
});

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

  it("never reports a single survey record, even if a file carries one", () => {
    // FRS records are licensed: no figure for one record, its contribution included. Made-up values, not results.
    const withRecord = structuredClone(data);
    const fake = { contribution_bn: 1, share_of_income_change: -0.5, income_change_excluding_bn: -2 };
    for (const run of [withRecord.central.run, ...withRecord.trajectories.paths]) {
      run.largest_household = fake;
      run.concentration_by_year = Object.fromEntries(withRecord.horizon.map((y) => [String(y), fake]));
    }
    withRecord.expected_value.estimates.primary.net_excluding_largest_record = withRecord.expected_value.estimates.primary.net;
    const { container } = render(<Dashboard data={withRecord} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(/largest household|survey household record|one survey (household|record)|single-record/i);
    }
  });

  it("has no sample banner on the real file", () => {
    render(<Dashboard data={data} />);
    expect(screen.queryByTestId("sample-banner")).toBeNull();
  });

  it("keeps the pre-Budget release block in the file, off the page", () => {
    render(<Dashboard data={preBudgetCopy()} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      expect(screen.queryByTestId("pre-budget-banner"), tab.label).toBeNull();
    }
  });

  it("has no pre-Budget banner without a pre-Budget release block", () => {
    const copy = structuredClone(data);
    delete copy.release;
    render(<Dashboard data={copy} />);
    expect(screen.queryByTestId("pre-budget-banner")).toBeNull();
  });
});

describe("a pre-Budget, scenarios-only release", () => {
  it("renders a changed release Budget date in the pending expected value", () => {
    const copy = preBudgetCopy();
    copy.release.budget_date = "2026-11-04";
    render(<MethodTab data={copy} />);
    expect(screen.getByTestId("expected-value-pending").textContent).toContain("4 November Budget");
  });
  // The real file when it is a pre-Budget release, and always a synthetic pre-Budget copy of whatever file is committed.
  const cases = [
    ...(isPreBudget(data) && !data.expected_value ? [["the committed file", () => data]] : []),
    ["a synthetic copy", () => preBudgetCopy()],
  ];
  const headings = (container) => [...container.querySelectorAll("h1, h2, h3")].map((h) => h.textContent.trim());

  it.each(cases)("shows %s on every tab with no unavailable, NaN or repeated heading", (_, file) => {
    const { container } = render(<Dashboard data={file()} />);
    expect(screen.getByTestId("intro").textContent).not.toContain("thousands of");
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bunavailable\b/i);
      expect(screen.queryAllByTestId("unavailable"), tab.label).toHaveLength(0);
      const h = headings(container);
      expect(h.filter((x, i) => h.indexOf(x) !== i), tab.label).toEqual([]);
      expect(h.filter((x) => /scenario envelope|earnings scenarios/i.test(x)).length, tab.label).toBeLessThanOrEqual(1);
      expect((text.match(/not a probability interval/g) ?? []).length, tab.label).toBeLessThanOrEqual(1);
    }
  });

  it.each(cases)("keeps expected-value wording out of the Methodology tab's method and limitations for %s", (_, file) => {
    const copy = file();
    render(<MethodTab data={copy} />);
    expect(screen.getByTestId("expected-value-pending").textContent).toContain("28 October Budget");
    expect(screen.queryByTestId("ev-method")).toBeNull();
    const now = screen.getByTestId("limitations").textContent;
    expect(now).not.toMatch(/expected value/i);
    const later = copy.method_limitations.filter((l) => /expected value/i.test(l));
    if (later.length) {
      const box = screen.getByTestId("limitations-later");
      expect(box.textContent).toContain("For the expected saving, after the Budget");
      for (const l of later) expect(box.textContent).toContain(l);
    }
  });

  it.skipIf(!(isPreBudget(data) && !data.expected_value))("leads the Budget impact tab with the file's scenarios, each once", () => {
    const { container } = render(<Dashboard data={data} />);
    const h = getScenarioHeadline(data);
    const env = data.scenario_envelope;
    const pair = (s, y) => [bn(s[y].gross), bn(s[y].net)];
    const card = (id) => screen.getByTestId(`scenario-${id}`).textContent;
    expect(h.years).toEqual([final - 5, final]);
    for (const y of h.years) {
      for (const v of pair(data.central.run.saving_bn, y)) expect(card("central")).toContain(v);
      for (const v of pair(env.obr_wedge.run.saving_bn, y)) expect(card("wedge")).toContain(v);
    }
    for (const [id, sc] of Object.entries(data.mean_path_scenarios.scenarios)) {
      const text = card(`earnings-${id}`);
      expect(text).toContain(`${sc.calendar_earnings_delta > 0 ? "+" : "−"}0.5pp from ${sc.from_year}`);
      expect(text).toContain(`${sc.unique_full_runs} simulated paths`);
      const g = sc.scenario_path_set.gross[final];
      expect(text).toContain(`${bn(g.mean)} ± ${bn(1.96 * g.se)}`);
      expect(text).toContain(bn(sc.scenario_path_set.net[final].mean));
      for (const y of h.years.slice(0, -1)) expect(text).toContain(bn(sc.scenario_path_set.gross[y].mean));
      // The baseline path set's mean (scenario minus paired difference) is not printed.
      expect(container.textContent).not.toContain(bn(g.mean - sc.paired_difference.gross[final].mean, 2));
    }
    const replay = env.last_decade_replay;
    const last = replay.model_years.at(-1);
    const model = replay.counterfactual.model_years;
    const text = screen.getByTestId("scenario-replay").textContent.replace(/\s+/g, " ");
    expect(text).toContain(`Had the plan started in April ${replay.switch_year}`);
    expect(text).toContain(`saved ${bn(model.saving_bn[last].gross)} in State Pension spending in ${fy(last)}`);
    expect(text).toContain(`(${bn(model.saving_bn[last].net)} net)`);
    expect(text).toContain(`£${model.counterfactual_weekly.new_state_pension[last].toFixed(2)} a week instead of £${model.actual_weekly.new_state_pension[last].toFixed(2)}`);
    expect(screen.getByRole("heading", { name: /scenario envelope/i }).closest("section").textContent).toContain("not a probability interval");
    expect(screen.queryByTestId("assumption-paths")).toBeNull();
    expect(screen.getByTestId("assumption-population")).toBeTruthy();
    expect(screen.queryByTestId("mean-path-table")).toBeNull();
    // The side menu lists only the sections the tab has.
    for (const link of within(screen.getByTestId("on-this-tab")).getAllByRole("link")) {
      expect(container.querySelector(link.getAttribute("href"))).toBeTruthy();
    }
  });

  it.skipIf(!(isPreBudget(data) && !data.expected_value))("explains the earnings scenarios' asymmetry only as far as the file supports it", () => {
    render(<LandingTab data={data} />);
    const flags = Object.values(data.mean_path_scenarios.scenarios).map((sc) => {
      const d = sc.paired_difference.gross[final];
      return { up: sc.calendar_earnings_delta > 0, flat: Math.abs(d.mean) <= 1.96 * d.se };
    });
    const line = screen.queryByTestId("scenario-asymmetry");
    if (flags.some((f) => f.flat) && flags.some((f) => !f.flat)) {
      const flat = flags.find((f) => f.flat);
      expect(line.textContent).toContain(`change from ${flat.up ? "higher" : "lower"} growth is not distinguishable from zero`);
      expect(line.textContent).toContain(fy(final));
      expect(line.textContent).not.toMatch(/£|±|\d\.\d/); // no figures typed into the prose
    } else {
      expect(line).toBeNull();
    }
  });

  it("omits each headline part the file lacks rather than printing unavailable", () => {
    const copy = preBudgetCopy();
    delete copy.scenario_envelope;
    copy.mean_path_scenarios = { scenarios: {} };
    const { container } = render(<LandingTab data={copy} />);
    expect(screen.getByTestId("scenario-central")).toBeTruthy();
    expect(screen.queryByTestId("scenario-wedge")).toBeNull();
    expect(screen.queryByTestId("scenario-replay")).toBeNull();
    expect(screen.queryByTestId("scenario-asymmetry")).toBeNull();
    expect(container.textContent).not.toMatch(/\bunavailable\b|NaN/);
  });
});

/** A scenarios-only file as `triple-lock-build --pre-budget --uncertainty-ruling a` writes it. */
describe("a pre-Budget release with a model-conditional expected value (ruling b)", () => {
  // The committed file when it is one, and always a synthetic (b) copy of a file with an expected value.
  const synthetic = () => {
    const copy = structuredClone(data);
    copy.release = { stage: "pre-budget", interim: true, execution_ruling: "b", forecast: "OBR March 2026",
      april_2027_cpi_leg: "August 2026 CPI (provisional; September published 21 Oct)", recorded_ruling: "c",
      budget_date: "2026-10-28" };
    copy.expected_value.paired_sensitivity = { status: "omitted", dataset: "microcosm_uk_2024_25", reason: "x" };
    delete copy.expected_value.estimates.sensitivity;
    copy.expected_value.paired_difference = {};
    return copy;
  };
  const cases = [
    ...(isPreBudget(data) && hasEv && data.release.execution_ruling === "b" ? [["the committed file", () => data]] : []),
    ...(hasEv ? [["a synthetic copy", synthetic]] : []),
  ];
  const headings = (container) => [...container.querySelectorAll("h1, h2, h3")].map((h) => h.textContent.trim());

  it.each(cases)("shows %s on every tab with no unavailable, NaN or repeated heading", (_, file) => {
    const { container } = render(<Dashboard data={file()} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bunavailable\b/i);
      expect(screen.queryAllByTestId("unavailable"), tab.label).toHaveLength(0);
      const h = headings(container);
      expect(h.filter((x, i) => h.indexOf(x) !== i), tab.label).toEqual([]);
      expect((text.match(/not a probability interval/g) ?? []).length, tab.label).toBeLessThanOrEqual(1);
      expect((text.match(/Microcosm dataset cross-check/g) ?? []).length, tab.label).toBeLessThanOrEqual(1);
    }
  });

  it.each(cases)("leads %s with the distribution across paths, then the scenarios, each figure once", (_, file) => {
    const copy = file();
    render(<Dashboard data={copy} />);
    const est = copy.expected_value.estimates.primary;
    const expected = screen.getByTestId("landing-expected").textContent;
    expect(expected).toContain("Model-conditional saving");
    for (const k of ["gross", "net"]) expect(expected).toContain(bn(est[k][final].mean));
    fireEvent.mouseEnter(screen.getByTestId("landing-expected-error"));
    expect(screen.getByRole("tooltip").textContent).toContain(`±${bn(1.96 * est.gross[final].se)} gross`);
    for (const k of ["gross", "net"]) expect(expected).toContain(`${bn(est[k][final - 5].mean)} ${k}`);
    const spread = getSavingSpread(copy);
    for (const k of ["gross", "net"]) {
      const last = spread[k].find((r) => r.year === final);
      expect(screen.getByTestId("landing-range").textContent).toContain(`${bn(last.p10)} to ${bn(last.p90)}`);
    }
    expect(screen.getAllByTestId("spread-strip").length).toBeGreaterThan(0);
    expect(screen.getByTestId("spread-chart")).toBeTruthy();
    // The central forecast is one scenario in the chart, not also an expected-value card.
    expect(screen.queryByTestId("landing-central")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: /Single scenarios/ }));
    expect(screen.getByTestId("scenario-bars")).toBeTruthy();
    // No Microcosm comparison box: the strip says when it comes.
    expect(screen.queryByTestId("dataset-box")).toBeNull();
  });
});

/** A provisional (c) file as `triple-lock-build --pre-budget --uncertainty-ruling c` writes it: the C2 dry run's
 * scores, with or without the paired Microcosm cross-check. */
describe("a provisional pre-Budget release under ruling (c)", () => {
  const synthetic = (withMicrocosm) => () => {
    const copy = structuredClone(data);
    const fixture = c2Fixture(true);
    const screen = { ...fixture.uncertainty_screen, run_kind: "dry_run", expected_value_authorized: false };
    copy.uncertainty_screen = screen;
    copy.provenance.uncertainty_screen = structuredClone(screen);
    copy.uncertainty_ruling = { ...structuredClone(screen), decision: "d955", ruling: "c", requested_ruling: "c",
      effective_ruling: "c", provisional: true, release_stage: "pre-budget", interim: true, recorded_ruling: "c" };
    copy.expected_value.provenance = structuredClone(copy.uncertainty_ruling);
    copy.release = { stage: "pre-budget", interim: true, execution_ruling: "c", provisional: true,
      c2_dry_run: { terminal_hits: 4, terminal_origins: 6, annual_coverage: 0.8, annual_cells: 20 },
      forecast: "OBR March 2026", april_2027_cpi_leg: "August 2026 CPI (provisional; September published 21 Oct)",
      recorded_ruling: "c", budget_date: "2026-10-28" };
    if (withMicrocosm) {
      delete copy.expected_value.paired_sensitivity;
      copy.expected_value.estimates.sensitivity = fixture.expected_value.estimates.sensitivity;
      copy.expected_value.paired_difference = fixture.expected_value.paired_difference;
    } else {
      copy.expected_value.paired_sensitivity = { status: "omitted", dataset: "microcosm_uk_2024_25", reason: "x" };
      delete copy.expected_value.estimates.sensitivity;
      copy.expected_value.paired_difference = {};
    }
    return copy;
  };
  const cases = [
    ...(isPreBudget(data) && hasEv && data.release.execution_ruling === "c" ? [["the committed file", () => data]] : []),
    ...(hasEv ? [["a copy with the Microcosm cross-check", synthetic(true)], ["a copy without it", synthetic(false)]] : []),
  ];
  const headings = (container) => [...container.querySelectorAll("h1, h2, h3")].map((h) => h.textContent.trim());

  it.skipIf(!hasEv)("renders a changed release Budget date in the provisional card", () => {
    const copy = synthetic(true)();
    copy.release.budget_date = "2026-11-04";
    render(<LandingTab data={copy} />);
    expect(screen.getByTestId("landing-expected").textContent).toContain("Provisional until the 4 November Budget.");
  });

  it.each(cases)("shows %s on every tab, labelled provisional, with nothing broken", (_, file) => {
    const copy = file();
    const { container } = render(<Dashboard data={copy} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(/failed its pre-registered backtest|fails its frozen adequacy/);
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bunavailable\b/i);
      const h = headings(container);
      expect(h.filter((x, i) => h.indexOf(x) !== i), tab.label).toEqual([]);
    }
  });

  it.each(cases)("leads %s with the provisional distribution, then the scenarios once", (_, file) => {
    const copy = file();
    render(<Dashboard data={copy} />);
    expect(screen.getByTestId("landing-expected").textContent).toContain("Provisional until the 28 October Budget.");
    fireEvent.click(screen.getByRole("tab", { name: /Single scenarios/ }));
    expect(screen.getByTestId("scenario-bars")).toBeTruthy();
    expect(screen.queryByTestId("landing-central")).toBeNull();
    // The earnings scenarios appear once, in the envelope beside the distribution.
    expect(screen.queryByTestId("scenario-interpretation")).toBeNull();
    // The dashboard publishes the Enhanced FRS only: the Microcosm cross-check stays in the file, not on the page.
    expect(screen.queryByRole("tab", { name: /The survey data/ })).toBeNull();
    expect(document.body.textContent).not.toMatch(/Microcosm/);
  });

  it.each(cases)("says on the Methodology tab that %s rests on the C2 dry run", (_, file) => {
    render(<MethodTab data={file()} />);
    const c2 = screen.getByTestId("c2-screen").textContent.replace(/\s+/g, " ");
    expect(c2).toContain("the expected saving on this page is provisional until it is scored again on the Budget's figures");
    expect(c2).not.toContain("no expected value authorized");
  });
});

function preBudgetCopy() {
  const copy = structuredClone(data);
  delete copy.expected_value;
  delete copy.uncertainty_screen;
  delete copy.provenance?.uncertainty_screen;
  copy.uncertainty_ruling = { decision: "d955", ruling: "a", recorded_ruling: "c", release_stage: "pre-budget" };
  copy.expected_value_omission = { requested_ruling: "a", effective_ruling: "a",
    reason: "Withheld pending the post-Budget binding score." };
  copy.release = { stage: "pre-budget", forecast: "OBR March 2026",
    april_2027_cpi_leg: "August 2026 CPI (provisional; September published 21 Oct)",
    expected_value: "withheld until the binding C2 score on the 28 October 2026 Budget inputs", recorded_ruling: "c",
    budget_date: "2026-10-28" };
  copy.mean_path_scenarios = { scenarios: { lower: {
    calendar_earnings_delta: -0.005,
    scenario_path_set: { gross: { [final]: { mean: 2, se: 0.1 } }, net: { [final]: { mean: 1, se: 0.05 } } },
  } } };
  return copy;
}

describe("the triple lock", () => {
  it("counts which figure set each rise from the file", () => {
    render(<StepTripleLock data={data} />);
    const binding = Object.values(data.trajectories.history.triple_lock.binding);
    const n = (k) => binding.filter((b) => b === k).length;
    const text = screen.getByTestId("binding-counts").textContent.replace(/\s+/g, " ");
    expect(text).toContain(`CPI sets the rise ${n("cpi")} times, earnings ${n("earnings")} times and the 2.5% floor ${n("floor")} times`);
  });

  it("states the past-years check from the file, or nothing when the file has none", () => {
    render(<StepTripleLock data={data} />);
    const c = getPastYearsCheck(data);
    if (c) {
      expect(screen.getByTestId("past-years-check").textContent).toContain(`${(c.screen === "c2" ? c.model.mean_gap_pct : c.realised_gap_pct).toFixed(1)}%`);
    } else {
      // A scenarios-only file has no expected value, so no expected-value check of the past years either.
      expect(isScenariosOnly(data)).toBe(true);
      expect(screen.queryByTestId("past-years-check")).toBeNull();
      expect(screen.getByTestId("past-years")).toBeTruthy();
    }
  });
});

describe("paths", () => {
  it("shows the central path's pension per year in the final year", () => {
    render(<StepPaths data={data} trajectories={trajectories} labels={labels} />);
    const w = data.central.run.weekly;
    expect(screen.getByTestId("card-tl-weekly").textContent).toContain(`${formatAnnualFromWeekly(w.triple_lock.new_state_pension[final])} a year`);
    expect(screen.getByTestId("card-bp-weekly").textContent).toContain(`${formatAnnualFromWeekly(w.burnham_2030.new_state_pension[final])} a year`);
  });

  it("says where each drawn path sits among the model's paths, from the file", () => {
    const drawn = data.trajectories.paths.filter((t) => t.selection);
    expect(drawn.map((t) => t.id)).toEqual(["random", "monthly_p50", "monthly_p90"]);
    for (const t of drawn) {
      const s = t.selection;
      const { unmount } = render(<StepPaths data={data} trajectories={trajectories} labels={labels} pathId={t.id} onPath={() => {}} />);
      const line = screen.getByTestId("path-source").textContent;
      expect(line).toContain(`at the ${ordinal(Math.max(1, Math.min(99, Math.round(s.gap_percentile_2039))))} percentile`);
      expect(line).toContain(`${formatAnnualFromWeekly(s.gap_gbp_week)} a year below the triple lock's`);
      unmount();
    }
  });

  it("drops the percentile, not the path, when the file lacks it", () => {
    const i = data.trajectories.paths.findIndex((t) => t.id === "random");
    const broken = readTrajectories(mutate(`trajectories.paths.${i}.selection.larger_gap_pct_2039`, null)).trajectories;
    render(<StepPaths data={data} trajectories={broken} labels={labels} pathId="random" onPath={() => {}} />);
    const line = screen.getByTestId("path-source").textContent;
    expect(line).toContain("picked at random");
    expect(line).not.toContain("percentile");
  });

  it("lists where the paths come from as short points, with the selected path's pick from the file", () => {
    const n = (v) => v.toLocaleString("en-GB");
    for (const id of ["monthly_p50", "monthly_p90"]) {
      const s = data.trajectories.paths.find((t) => t.id === id).selection;
      const { unmount } = render(<StepPaths data={data} trajectories={trajectories} labels={labels} pathId={id} onPath={() => {}} />);
      const text = screen.getByTestId("path-sources").textContent;
      expect(text).toContain(`(${n(s.draws_compared)} paths)`);
      expect(text).toContain(`within ±${Math.round(s.band * 1000) / 10} percentiles`);
      expect(screen.getByTestId("path-source").textContent).toContain(`Path ${n(s.draw)}`);
      expect(text).toContain(hasEv ? `The expected saving uses all ${n(s.draws_compared)} paths` : "These are illustrative paths, not an average.");
      unmount();
    }
  });

  it("opens on the OBR central forecast and offers it first", () => {
    render(<StepPaths data={data} trajectories={trajectories} labels={labels} onPath={() => {}} />);
    const radios = screen.getAllByRole("radio");
    expect(radios[0].textContent).toContain("OBR central forecast");
    expect(radios[0].getAttribute("aria-checked")).toBe("true");
    expect(screen.getByTestId("path-source").textContent).toContain("Selected: OBR central forecast. Earnings beat prices almost every year");
  });

  it("switches paths with the buttons", () => {
    const onPath = vi.fn();
    render(<StepPaths data={data} trajectories={trajectories} labels={labels} pathId="random" onPath={onPath} />);
    fireEvent.click(screen.getByRole("radio", { name: /90th percentile/ }));
    expect(onPath).toHaveBeenCalledWith("monthly_p90");
  });

  it("shows a styled tooltip when a card element is hovered", () => {
    render(<StepPaths data={data} trajectories={trajectories} labels={labels} onPath={() => {}} />);
    const central = trajectories.find((t) => t.id === "central");
    const r = central.rows.find((x) => x.year >= 2030);
    fireEvent.mouseEnter(screen.getByTestId(`binding-${r.year}`));
    expect(screen.getByRole("tooltip").textContent).toContain(`April ${r.year}:`);
    fireEvent.mouseLeave(screen.getByTestId(`binding-${r.year}`));
    fireEvent.mouseEnter(screen.getByTestId(`differ-${r.year}`));
    expect(screen.getByRole("tooltip").textContent).toMatch(new RegExp(`April ${r.year}: (the same pension|.* below the triple lock)`));
  });
});

describe("one pensioner", () => {
  it("has account items in the file that sum to the net change", () => {
    const record = records.find((r) => r.id === "random");
    const ex = Object.keys(record.run.households.results)[0];
    const r = record.run.households.results[ex];
    let sum = 0;
    ACCOUNT.forEach((a) => {
      sum += a.sign * (r.burnham_2030[a.key][final] - r.triple_lock[a.key][final]);
    });
    const net = r.burnham_2030.net_income[final] - r.triple_lock.net_income[final];
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

// The standard expected-value layout: the committed file without any pre-Budget release block.
const standard = () => {
  const copy = structuredClone(data);
  delete copy.release;
  return copy;
};

// The assumptions strip shows in the layout without a pre-Budget release; the pre-Budget layout points to Methodology.
const stripLayout = (d) => { const c = structuredClone(d); delete c.release; return c; };

describe("summary", () => {
  it.skipIf(!hasEv)("shows the expected net saving, the spread across paths, the central figure and households losing", () => {
    const data = standard();
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

  it.skipIf(!hasEv || data.assumptions !== undefined || !Object.keys(data.expected_value?.sensitivities ?? {}).length)("states what the headline assumes, with the numbers from the file", () => {
    render(<LandingTab data={data} />);
    const rows = Object.entries(data.expected_value.sensitivities)
      .filter(([name, s]) => name.startsWith("shift_dynamics") && inQuotedRange(s)).map(([, s]) => s);
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

  it.skipIf(!hasEv)("reads the strip from the file's assumptions block when it has one", () => {
    render(<LandingTab data={stripLayout(mutate("assumptions", BLOCK))} />);
    for (const item of BLOCK) {
      const text = screen.getByTestId(`assumption-${item.key}`).textContent;
      expect(text).toContain(item.title);
      expect(text).toContain(item.text);
    }
    expect(screen.getByTestId("assumptions").textContent).not.toContain("survey weights and the State Pension age");
  });

  it.skipIf(!hasEv || !Object.keys(data.expected_value?.sensitivities ?? {}).length)("computes the strip from the file's figures only for a file without the block", () => {
    render(<LandingTab data={stripLayout(mutate("assumptions", null, { remove: true }))} />);
    const strip = screen.getByTestId("assumptions").textContent;
    expect(screen.getByTestId("assumption-population").textContent).toContain("survey weights and the State Pension age");
    expect(screen.getByTestId("assumption-paths").textContent).toContain("does not include another model of prices and earnings");
    expect(screen.getByTestId("assumption-benefits").textContent).toContain("Great Britain");
    expect(strip).not.toContain("from the file");
    expect(strip).not.toMatch(BROKEN_TEXT);
  });

  it.skipIf(!hasEv || !Object.keys(data.expected_value?.sensitivities ?? {}).length)("corrects a stored paths range that includes an under-supported reweighting", () => {
    const copy = stripLayout(structuredClone(data));
    const range = getSensitivityRange(copy, "gross", final);
    copy.assumptions = [{ key: "paths", title: "Recorded path title", text: "Stale range: the lowest £0.0bn gross.",
      facts: { lowest: { mean: -999 }, highest: { mean: 999 }, reweightings: 999 } }];
    render(<LandingTab data={copy} />);
    const paths = screen.getByTestId("assumption-paths").textContent;
    expect(paths).toContain("Recorded path title");
    expect(paths).toContain(`the lowest ${bn(range.lo)} gross`);
    expect(paths).toContain(`the highest ${bn(range.hi)}`);
    expect(paths).not.toContain("Stale range");
    if (range.excluded === 6) expect(paths).toContain("Six more reweightings");
  });

  it.skipIf(!hasEv || !Object.keys(data.expected_value?.sensitivities ?? {}).length)("withholds a stored numeric range when no reweighting qualifies", () => {
    const copy = stripLayout(structuredClone(data));
    for (const row of Object.values(copy.expected_value.sensitivities)) row.included_in_quoted_range = false;
    copy.assumptions = [{ key: "paths", title: "Recorded path title", text: "Stale range: the lowest £0.0bn gross.",
      facts: { lowest: { mean: -999 }, highest: { mean: 999 }, reweightings: 999 } }];
    render(<LandingTab data={copy} />);
    expect(screen.queryByTestId("assumption-paths")).toBeNull();
  });

  // A block that is present but damaged never brings back the computed strip's "held fixed" wording.
  it.skipIf(!hasEv).each([
    ["an item without text", [BLOCK[0], { ...BLOCK[1], text: "" }, BLOCK[2]], ["population", "benefits"]],
    ["a repeated key", [BLOCK[0], { ...BLOCK[1], key: "population" }, BLOCK[2]], ["population", "benefits"]],
    ["an item that is not an object", [BLOCK[0], "x", BLOCK[2]], ["population", "benefits"]],
  ])("shows only the valid items given %s", (_, block, keys) => {
    render(<LandingTab data={stripLayout(mutate("assumptions", block))} />);
    const strip = screen.getByTestId("assumptions").textContent;
    for (const key of ["population", "paths", "benefits"]) {
      if (keys.includes(key)) expect(screen.getByTestId(`assumption-${key}`).textContent).toContain(BLOCK.find((b) => b.key === key).text);
      else expect(screen.queryByTestId(`assumption-${key}`)).toBeNull();
    }
    expect(strip).not.toContain("held fixed");
    expect(strip).not.toContain("survey weights and the State Pension age");
  });

  it.skipIf(!hasEv).each([
    ["an empty block", []],
    ["a block that is not a list", "x"],
    ["null", null],
    ["no valid item", [{ key: "population", title: "", text: "x" }]],
  ])("shows no strip given %s", (_, block) => {
    render(<LandingTab data={stripLayout(mutate("assumptions", block))} />);
    expect(screen.queryByTestId("assumptions")).toBeNull();
    expect(screen.getByTestId("landing-expected")).toBeTruthy();
  });

  it.skipIf(!hasEv)("says what the households-losing card's numbers are", () => {
    render(<LandingTab data={standard()} />);
    const text = screen.getByTestId("landing-losing").textContent;
    expect(text).toContain(`Expected share of households in ${fy(final).replace("-", "\u2011")}.`);
    expect(text).toMatch(/On 80% of paths it is between \d+% and \d+%\./);
  });

  it.skipIf(!hasEv)("weights the full runs so their mean is the expected saving", () => {
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

  it.skipIf(!hasEv)("fails closed when the runs lack their weights", () => {
    render(<LandingTab data={mutate("expected_value.strata", [])} />);
    expect(screen.getByTestId("unavailable")).toBeTruthy();
  });
});

describe("cost and uncertainty", () => {
  it.skipIf(!hasEv)("shows the expected saving's note", () => {
    render(<LandingTab data={data} />);
    expect(screen.getByTestId("uncertain-note").textContent).toContain(fy(final));
  });

  it.skipIf(!hasEv)("fails closed when an estimate is missing", () => {
    render(<SummaryTab data={mutate(`expected_value.estimates.primary.gross.${final}.se`, null)} />);
    expect(screen.getByTestId("unavailable")).toBeTruthy();
  });
});

describe("method", () => {
  it("shows the expected-value backtest, or what follows the Budget, and every coverage row from the file", () => {
    render(<MethodTab data={data} />);
    if (getC2Screen(data)) expect(screen.getByTestId("c2-screen-table")).toBeTruthy();
    else if (data.expected_value) expect(screen.getByTestId("ev-backtest-table")).toBeTruthy();
    else {
      expect(isPreBudget(data)).toBe(true);
      expect(screen.getByTestId("expected-value-pending")).toBeTruthy();
      expect(screen.queryAllByTestId("unavailable")).toHaveLength(0);
    }
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

  it("falls back to the pinned policyengine-uk and data release when no policyengine.py version is recorded", () => {
    const model = {
      model_version: "2.118.0", runtime_dataset: "enhanced_frs_2024_25", data_package: "policyengine-uk-data",
      data_version: "1.56.16", certified: false,
    };
    const { release_bundle: _bundle, ...rest } = data.provenance;
    render(<ReplicationLine data={{ ...data, provenance: { ...rest, model } }} />);
    const text = screen.getByTestId("replication").textContent;
    expect(text).toContain("policyengine-uk 2.118.0 on enhanced_frs_2024_25 (policyengine-uk-data 1.56.16)");
  });

  it("names only the policyengine.py version when the file records one", () => {
    const model = {
      model_version: "2.125.1", runtime_dataset: "enhanced_frs_2024_25", data_package: "policyengine-uk-data",
      data_version: "1.58.0", certified: true, certification: "policyengine.py 6.2.6 UK bundle certification (#555)",
      certification_bundle: { bundle_package: "policyengine", bundle_version: "6.2.6", bundle_id: "uk-6.2.6" },
    };
    const { release_bundle: _bundle, ...rest } = data.provenance;
    render(<ReplicationLine data={{ ...data, provenance: { ...rest, model } }} />);
    const text = screen.getByTestId("replication").textContent;
    expect(text).toContain("Built with policyengine.py 6.2.6.");
    expect(text).not.toContain("policyengine-uk 2.125.1");
    expect(text).not.toContain("enhanced_frs_2024_25");
  });

  it("shows nothing it cannot source", () => {
    const { release_bundle: _bundle, ...rest } = data.provenance;
    render(<ReplicationLine data={{ ...data, provenance: rest }} />);
    expect(screen.getByTestId("replication").textContent).not.toContain("undefined");
  });
});

describe("the published dashboard shows the Enhanced FRS only", () => {
  it("never names Microcosm on any tab, with every disclosure open", () => {
    const { container } = render(<Dashboard data={data} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      container.querySelectorAll("details").forEach((d) => { d.open = true; });
      expect(container.textContent, tab.label).not.toMatch(/Microcosm/);
    }
  });
});

describe("the triple lock tab", () => {
  it("shows the rule's record as one chart with a switch between its two views", () => {
    render(<StepTripleLock data={data} />);
    const box = screen.getByTestId("rule-history");
    expect(box.textContent).toContain("The three figures behind each April");
    fireEvent.click(within(box).getByRole("tab", { name: "The rise and what set it" }));
    expect(box.textContent).toContain("which figure set it");
  });

  it("keeps the earlier-start replay in one closed box", () => {
    render(<StepTripleLock data={data} />);
    const details = screen.getByTestId("earlier-expandable");
    expect(details.open).toBe(false);
    expect(within(details).getByTestId("past-years")).toBeTruthy();
  });
});

describe("every chart or table box says what it shows", () => {
  it("gives each titled box a one-line description, on every tab", () => {
    const { container } = render(<Dashboard data={data} />);
    let titled = 0;
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      container.querySelectorAll("details").forEach((d) => { d.open = true; });
      titled += container.querySelectorAll("[data-box-title]").length;
      // A heading inside a box must be a BoxTitle (or a captioned figure), which carries the description line.
      const bare = [...container.querySelectorAll(".panel h3")].filter((h) => !h.hasAttribute("data-box-title"));
      expect(bare.map((h) => h.textContent), tab.label).toEqual([]);
      for (const t of container.querySelectorAll("[data-box-title]")) {
        let box = t.parentElement;
        while (box && !box.querySelector("[data-box-description]")) box = box.parentElement;
        const desc = box?.querySelector("[data-box-description]");
        expect(desc?.textContent.trim().length ?? 0, `${tab.label}: ${t.textContent}`).toBeGreaterThan(20);
      }
    }
    expect(titled).toBeGreaterThan(3);
  });
});

describe("every switchable chart has room to draw", () => {
  it("gives each chart frame an explicit height in every view", () => {
    const { container } = render(<Dashboard data={data} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      // Click every view switch button, then check every chart frame on the tab.
      const subTabs = tab.id === "households" ? [null, screen.getByRole("tab", { name: /Example pensioners/ })] : [null];
      for (const sub of subTabs) {
        if (sub) fireEvent.click(sub);
        const switches = [...container.querySelectorAll('.panel [role="tab"]')];
        expect(switches.length > 0 || tab.id === "budget" || tab.id === "method", tab.label).toBe(true);
        for (const b of [null, ...switches]) {
          if (b) fireEvent.click(b);
          const frames = container.querySelectorAll('[data-testid="chart-frame"]');
          for (const f of frames) expect(parseFloat(f.style.height), `${tab.label}: ${b?.textContent ?? "default"}`).toBeGreaterThan(100);
        }
      }
    }
  });
});

describe("the poverty card puts the path in context", () => {
  const typical = records.find((r) => r.id === "monthly_p50");
  const year = data.horizon.at(-1);
  const pp = (run, k) => run.poverty_pct.burnham_2030[String(year)][k] - run.poverty_pct.triple_lock[String(year)][k];
  const pts = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}`;

  it.skipIf(!typical)("on the OBR central path, gives the typical path's change from the data", () => {
    render(<StepPopulation data={data} records={records} pathId="central" onPath={() => {}} />);
    const text = screen.getByTestId("card-poverty").textContent.replace(/\s+/g, " ");
    expect(text).toContain("no noticeable change on this path");
    expect(text).toContain(`On the typical path, pensioner poverty after housing costs is ${pts(pp(typical.run, "pensioners_absolute_ahc"))} points (absolute) and ${pts(pp(typical.run, "pensioners_relative_ahc"))} (relative)`);
  });

  it.skipIf(!typical)("on the typical path, states the change", () => {
    render(<StepPopulation data={data} records={records} pathId="monthly_p50" onPath={() => {}} />);
    const text = screen.getByTestId("card-poverty").textContent.replace(/\s+/g, " ");
    expect(text).toContain(`${pts(pp(typical.run, "pensioners_absolute_ahc"))} points under the Burnham plan on this path`);
    expect(text).not.toContain("no noticeable change");
  });
});

describe("the households card gives those better off beside those worse off", () => {
  const year = data.distribution_years.at(-1);
  const withAffected = (a) => records.map((r) => (r.id === "central"
    ? { ...r, run: { ...r.run, households_affected: { ...r.run.households_affected, [String(year)]: a } } }
    : r));
  const card = () => screen.getByTestId("card-losing").textContent.replace(/\s+/g, " ");

  it("states the share and mean gain at the same £1 threshold", () => {
    render(<StepPopulation data={data} records={withAffected({ losing_pct: 30.25, mean_loss_gbp: 410, gaining_pct: 1.5, mean_gain_gbp: 37 })} pathId="central" onPath={() => {}} />);
    expect(card()).toContain("1.5% are better off, by £37 a year on average. Both groups count a change of more than £1 a year.");
  });

  it("says none is better off when the group is empty", () => {
    render(<StepPopulation data={data} records={withAffected({ losing_pct: 30.25, mean_loss_gbp: 410, gaining_pct: 0, mean_gain_gbp: 0 })} pathId="central" onPath={() => {}} />);
    expect(card()).toContain("No household is better off.");
  });

  it("says nothing about gains for a file that records losers only", () => {
    render(<StepPopulation data={data} records={withAffected({ losing_pct: 30.25, mean_loss_gbp: 410 })} pathId="central" onPath={() => {}} />);
    expect(screen.queryByTestId("card-gaining")).toBeNull();
    expect(card()).not.toContain("better off");
  });
});

describe("benchmarks in a scenarios-only file", () => {
  const row = (id, our_metric, our_value, extra = {}) => ({
    id, publisher: `Publisher ${id}`, title: `Title ${id}`, date: "2026-10-28", url: `https://example.org/${id}`,
    figure_text: "Quoted", comparison: "Compared", our_metric, our_value, like_for_like: "partial", note: "Note",
    verified: true, ...extra,
  });
  const file = {
    ...data,
    benchmarks: [
      row("dwp_uprating_2026", "central.run.saving_bn.2039.gb.gross", 1.24),
      row("obr_efo_2026_medium_term", "central.run.rates.burnham_2030.2030", 0.025),
      row("obr_efo_2026_historical_replay", "scenario_envelope.last_decade_replay.counterfactual.level_ratio.2026", 0.9876),
    ],
    benchmarks_omitted: [{ id: "obr_lted_triple_lock_premium", publisher: "Office for Budget Responsibility",
                           title: "Long-term economic determinants, March 2026 EFO", url: "https://obr.uk/x.xlsx" }],
  };

  it("says what each figure of ours is and names what it cannot compare", () => {
    render(<BenchmarksTable data={file} />);
    const dwp = screen.getByText("Publisher dwp_uprating_2026").closest("tr").textContent;
    expect(dwp).toContain("£1.2bn");
    expect(dwp).toContain("on the OBR's central path (one scenario), Great Britain");
    expect(dwp).not.toContain("probability-weighted");
    expect(screen.getByText("Publisher obr_efo_2026_medium_term").closest("tr").textContent).toContain("2.5%");
    expect(screen.getByText("Publisher obr_efo_2026_historical_replay").closest("tr").textContent)
      .toContain("1.2% below the triple lock");
    const omitted = screen.getByTestId("benchmarks-omitted");
    expect(omitted.textContent).toContain("Office for Budget Responsibility, Long-term economic determinants, March 2026 EFO");
    expect(omitted.textContent).toContain("expected value this release does not have");
  });

  it("names no omitted benchmark when the file lists none", () => {
    render(<BenchmarksTable data={{ ...file, benchmarks_omitted: undefined }} />);
    expect(screen.queryByTestId("benchmarks-omitted")).toBeNull();
  });
});
