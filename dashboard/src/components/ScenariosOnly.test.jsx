/**
 * A file with no expected value: the model's paths are illustrations, no tab places a path in a distribution, and a
 * failed C2 test reads in the page's own words, from the file's own scores.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = new URLSearchParams();
const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, useSearchParams: () => searchParams }));

import Dashboard, { TAB_OPTIONS } from "./Dashboard";
import MeanPathScenarios from "./MeanPathScenarios";
import MethodTab from "./MethodTab";
import { C2_FALLBACK_TEXT, getC2FailureText, getC2Screen, getExpectedValue, getRunsWithTables, isScenariosOnly, pathNames, PATH_NAMES, SCENARIO_PATH_NAMES } from "../lib/dataHelpers";
import { c2Fixture } from "../lib/c2TestFixtures";
import { readTrajectories } from "../lib/trajectoryHelpers";
import { BROKEN_TEXT, realData } from "../lib/testUtils";
import resultsFile from "../../public/data/results.json";

// Wording that places a path within the model's distribution or points to an average over paths. Without an expected
// value none may survive, except these, which say so or describe something else: the registered (a) envelope's
// earnings scenarios, the past-years check's score, and the lines saying no path is typical and no average is shown.
const PLACING = /.{0,60}(\btypical\b|high-saving|percentile|\bmedian\b|average over|average across|all paths).{0,60}/gi;
const PLACING_ALLOWED = [
  /Each is the average over (?:[\d,]+ )?draws from the model's simulated paths/,
  /is at its \d+(st|nd|rd|th) percentile, well inside its range/,
  /not a typical or a likely path/,
  /no average over paths is shown/,
];
const placing = (text) => [...text.matchAll(PLACING)].map((m) => m[0]).filter((m) => !PLACING_ALLOWED.some((ok) => ok.test(m)));
// The rule's internals, as the file's own reason states them.
const INTERNALS = /d955\(a\)|floor_bias|A\/suspended|primary failed|the build automatically/;
const FAILURE = "Scored on 6 OBR forecasts, one a year from March 2016 to March 2021, it expected earnings growth below 2.5% in 44.6% of the years tested, against 17.9% in practice: a bias of 0.267, beyond the limit of 0.25. The registered rule then drops the expected value and keeps the scenarios.";

const failed = () => c2Fixture(false);
const screens = (copy) => [copy.uncertainty_screen, copy.provenance?.uncertainty_screen, copy.expected_value?.provenance].filter(Boolean);
const withFailures = (failures) => {
  const copy = failed();
  for (const block of screens(copy)) block.c2_outcome.forms.monthly_var1_boot.failures = failures;
  return copy;
};

describe("the path names", () => {
  it("keeps the expected-value path names only for a file with an expected value, whatever the ruling", () => {
    expect(pathNames(c2Fixture(true))).toBe(PATH_NAMES);
    expect(pathNames(failed())).toBe(SCENARIO_PATH_NAMES);
    const withoutEv = structuredClone(realData);
    delete withoutEv.expected_value;
    withoutEv.uncertainty_ruling = { ...withoutEv.uncertainty_ruling, ruling: "c" };
    expect(isScenariosOnly(withoutEv)).toBe(false);
    expect(pathNames(withoutEv)).toBe(SCENARIO_PATH_NAMES);
  });

  it("names the model's paths as scenarios, never typical or by percentile", () => {
    const data = failed();
    const names = [...readTrajectories(data).trajectories, ...getRunsWithTables(data)].map((t) => t.label);
    expect(names.join(" | ")).not.toMatch(/typical|high-saving|percentile|median/i);
    expect(names).toContain("Model path: a large gap");
  });
});

describe("a file whose primary failed C2", () => {
  it("reads the same on every tab: no expected value, no placed path and none of the rule's internals", () => {
    const { container } = render(<Dashboard data={failed()} />);
    let pathSources = 0;
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bunavailable\b/i);
      expect(text, tab.label).not.toMatch(/expected saving (is|on this page is) provisional|provisional until/i);
      expect(text, tab.label).not.toMatch(/Expected saving,|middle 80%/);
      expect(text, tab.label).not.toMatch(INTERNALS);
      for (const radio of screen.queryAllByRole("radio")) expect(radio.textContent, tab.label).not.toMatch(/typical|high-saving|percentile/i);
      // Collapsed footers are <details>, so their text is in the page too.
      expect(placing(text), tab.label).toEqual([]);
      for (const list of screen.queryAllByTestId("path-sources")) {
        pathSources += 1;
        expect(list.textContent, tab.label).not.toMatch(/Example path|typical path|high-saving path/i);
        expect(list.textContent, tab.label).toContain(`${SCENARIO_PATH_NAMES.random}:`);
      }
    }
    expect(pathSources).toBeGreaterThan(0);
  });

  it("words the failure from the file's scores, in the same words wherever it appears", () => {
    expect(getC2FailureText(failed())).toBe(FAILURE);
    render(<Dashboard data={failed()} />);
    expect(screen.getByTestId("scenario-fallback-reason").textContent).toBe(FAILURE);
    fireEvent.click(screen.getByRole("tab", { name: TAB_OPTIONS.find((t) => t.id === "method").label }));
    expect(screen.getByTestId("expected-value-omission").textContent).toBe(`${C2_FALLBACK_TEXT} ${FAILURE}`);
  });

  it("reads each number from the row and limit the failure names", () => {
    const copy = withFailures(["B/suspended: |floor_bias| 0.300 exceeds 0.29"]);
    for (const block of screens(copy)) {
      Object.assign(block.c2_scores.scores.B.suspended.monthly_var1_boot, {
        floor_bias: { mean: 0.3 }, predicted_floor_frequency: { mean: 0.5 }, realised_floor_frequency: { mean: 0.2 },
      });
    }
    expect(getC2FailureText(copy)).toBe("Scored on 12 OBR forecasts, one a year from June 2010 to March 2021, it expected earnings growth below 2.5% in 50.0% of the years tested, against 20.0% in practice: a bias of 0.300, beyond the limit of 0.29. The registered rule then drops the expected value and keeps the scenarios.");
  });

  it("keeps every tab when an alternative form has no verdict", () => {
    const copy = failed();
    for (const block of screens(copy)) block.c2_outcome.forms.annual_var1_boot = null;
    expect(getC2Screen(copy)).toBeNull();
    render(<Dashboard data={copy} />);
    expect(screen.getByTestId("scenario-interpretation").textContent).toBe(C2_FALLBACK_TEXT);
    fireEvent.click(screen.getByRole("tab", { name: TAB_OPTIONS.find((t) => t.id === "method").label }));
    expect(screen.queryByTestId("c2-headline")).toBeNull();
  });

  it("leaves the coverage counts unjudged, as the failure may lie elsewhere", () => {
    render(<MethodTab data={failed()} />);
    const headline = screen.getByTestId("c2-headline").textContent.replace(/\s+/g, " ");
    expect(headline).toBe("Tested on 6 past OBR forecasts: the outcome fell inside the model's range in 4 of 6 final years and 80% of annual checks.");
  });

  it.each([
    ["names a check the page does not word", ["A/suspended: terminal_coverage 0.333 outside [0.50, 1.00]"]],
    ["names a treatment C2 does not score", ["B/published: |floor_bias| 0.300 exceeds 0.29"]],
    ["has more than one failure", ["A/suspended: |floor_bias| 0.267 exceeds 0.25", "A/suspended: |gap_bias_pp| 1.600 exceeds 1.5"]],
    ["has none listed", []],
    ["lists no failures", undefined],
  ])("says only that the model failed when the file %s", (_, failures) => {
    const copy = withFailures(failures);
    expect(getC2FailureText(copy)).toBeNull();
    render(<Dashboard data={copy} />);
    expect(screen.getByTestId("scenario-interpretation").textContent).toBe(C2_FALLBACK_TEXT);
    expect(screen.queryByTestId("scenario-fallback-reason")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: TAB_OPTIONS.find((t) => t.id === "method").label }));
    expect(screen.getByTestId("expected-value-omission").textContent.trim()).toBe(C2_FALLBACK_TEXT);
  });

  it.each([
    ["its forecast list", (block) => { delete block.c2_scores.origins; }],
    ["the predicted frequency", (block) => { delete block.c2_scores.scores.A.suspended.monthly_var1_boot.predicted_floor_frequency; }],
    ["the realised frequency", (block) => { delete block.c2_scores.scores.A.suspended.monthly_var1_boot.realised_floor_frequency; }],
  ])("says only that the model failed when the file lacks %s", (_, remove) => {
    const copy = failed();
    screens(copy).forEach(remove);
    expect(getC2FailureText(copy)).toBeNull();
  });

  it("states the earnings scenarios' failure once, in the same words", () => {
    render(<MeanPathScenarios data={failed()} />);
    expect(screen.getByTestId("scenario-interpretation").textContent).toContain(C2_FALLBACK_TEXT);
    expect(screen.getByTestId("scenario-fallback-reason").textContent).toBe(FAILURE);
    expect(screen.getByTestId("scenario-interpretation").textContent).not.toMatch(INTERNALS);
  });
});

describe("a file with no failure to word", () => {
  it("gives no failure text for a passing file or one with no C2 screen", () => {
    expect(getC2FailureText(c2Fixture(true))).toBeNull();
    expect(getC2FailureText(null)).toBeNull();
    expect(getC2FailureText({})).toBeNull();
  });
});

// The binding results file, once it is committed, in any fixture mode: docs/C2_BINDING.md's score, in the page's words.
describe.runIf(!getExpectedValue(resultsFile) && getC2Screen(resultsFile)?.primaryPasses === false)("the binding file", () => {
  it("words the registered failure", () => {
    expect(getC2FailureText(resultsFile)).toBe("Scored on 7 OBR forecasts, one a year from March 2016 to March 2022, it expected earnings growth below 2.5% in 44.6% of the years tested, against 17.9% in practice: a bias of 0.267, beyond the limit of 0.25. The registered rule then drops the expected value and keeps the scenarios.");
  });

  it("calls the score final, and says the Budget's inputs were in rather than that it scored them", () => {
    render(<MethodTab data={resultsFile} />);
    expect(screen.getByTestId("c2-screen").textContent).toContain("This is the final score, run once the Budget's inputs were in.");
  });

  it("shows no decision id or broken text on any tab, and leaves no limitation unnamed", () => {
    const { container } = render(<Dashboard data={resultsFile} />);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bd\d{3,4}\b|Vahid|bridge step|paired sensitivity|housing_benefit_|coverage job/);
    }
    expect(within(screen.getByTestId("limitations")).queryByText("Other")).toBeNull();
  });
});
