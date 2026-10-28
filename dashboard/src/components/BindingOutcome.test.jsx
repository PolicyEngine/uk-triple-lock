/**
 * The binding C2 outcome on the provisional pre-Budget file: the expected value is withdrawn and the page shows the
 * scenarios-only release, with a dated notice. Every other figure is the file's own.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = new URLSearchParams();
const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, useSearchParams: () => searchParams }));

import Dashboard, { TAB_OPTIONS } from "./Dashboard";
import { BINDING_C2_OUTCOME, getExpectedValue, getProvisional, getRunsWithTables, isScenariosOnly, pathNames, PATH_NAMES, SCENARIO_PATH_NAMES, withBindingOutcome } from "../lib/dataHelpers";
import { c2Fixture } from "../lib/c2TestFixtures";
import { readTrajectories } from "../lib/trajectoryHelpers";
import { BROKEN_TEXT, fixture, realData } from "../lib/testUtils";

const CHANGED = ["expected_value", "release", "uncertainty_ruling", "expected_value_omission", "binding_outcome"];

describe("other files are shown as they are", () => {
  it.each([
    ["a passing binding file", () => c2Fixture(true)],
    ["a failing binding file", () => c2Fixture(false)],
    ["a file without an expected value", () => { const d = structuredClone(realData); delete d.expected_value; return d; }],
  ])("returns %s unchanged", (_, file) => {
    const d = file();
    expect(withBindingOutcome(d)).toBe(d);
  });

  it("keeps the expected-value path names for a file with an expected value", () => {
    expect(pathNames(c2Fixture(true))).toBe(PATH_NAMES);
    expect(pathNames(c2Fixture(false))).toBe(SCENARIO_PATH_NAMES);
  });
});

describe.runIf(Boolean(getProvisional(realData)))("the provisional pre-Budget file after the binding score", () => {
  const shown = withBindingOutcome(realData);

  it("drops the expected value and records the fallback to (a), leaving every other block the file's own", () => {
    expect(realData.expected_value).toBeTruthy();
    expect(shown.expected_value).toBeUndefined();
    expect(getExpectedValue(shown)).toBeNull();
    expect(getProvisional(shown)).toBeNull();
    expect(isScenariosOnly(shown)).toBe(true);
    expect(shown.uncertainty_ruling).toMatchObject({ ruling: "a", requested_ruling: "c", effective_ruling: "a" });
    expect(shown.expected_value_omission).toEqual({ requested_ruling: "c", effective_ruling: "a", reason: BINDING_C2_OUTCOME.reason });
    expect(shown.binding_outcome).toMatchObject({ date: "2026-10-28", draws: realData.expected_value.draws.n, built: realData.provenance.generated_at });
    for (const key of Object.keys(realData).filter((k) => !CHANGED.includes(k))) expect(shown[key], key).toBe(realData[key]);
    const { provisional, ...release } = shown.release;
    expect(provisional).toBe(false);
    const { provisional: was, ...before } = realData.release;
    expect(was).toBe(true);
    expect(release).toEqual(before);
  });

  it("is idempotent and leaves the committed object alone", () => {
    expect(withBindingOutcome(shown)).toBe(shown);
    expect(getProvisional(realData)).not.toBeNull();
  });

  it("names the model's paths as scenarios, never typical or by percentile", () => {
    const names = [...readTrajectories(shown).trajectories, ...getRunsWithTables(shown)].map((t) => t.label);
    expect(names.join(" | ")).not.toMatch(/typical|high-saving|percentile|median/i);
    expect(names).toContain("Model path: a large gap");
  });

  it("states the outcome in a dated notice and shows no withdrawn figure on any tab", () => {
    const { container } = render(<Dashboard data={shown} />);
    const notice = screen.getByTestId("binding-outcome-notice").textContent.replace(/\s+/g, " ");
    expect(notice).toContain("Updated 28 October 2026");
    expect(notice).toContain(`built on ${new Date(realData.provenance.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })}`);
    expect(notice).toContain(`${realData.expected_value.draws.n.toLocaleString("en-GB")} simulated paths`);
    expect(notice).toContain("failed that test");
    expect(notice).toContain(`on the ${realData.release.forecast} forecast`);
    expect(screen.getByRole("link", { name: "uk-triple-lock#45" }).getAttribute("href")).toBe(BINDING_C2_OUTCOME.url);
    for (const tab of TAB_OPTIONS) {
      fireEvent.click(screen.getByRole("tab", { name: tab.label }));
      // The notice says what was withdrawn; the rest of the page must not show it.
      const text = container.textContent.replace(/\s+/g, " ").replace(notice, "");
      expect(text, tab.label).not.toMatch(BROKEN_TEXT);
      expect(text, tab.label).not.toMatch(/\bunavailable\b/i);
      expect(text, tab.label).not.toMatch(/expected saving (is|on this page is) provisional|provisional until/i);
      expect(text, tab.label).not.toMatch(/Expected saving,|middle 80%/);
      expect(screen.queryAllByTestId("binding-outcome-notice"), tab.label).toHaveLength(1);
      for (const radio of screen.queryAllByRole("radio")) expect(radio.textContent, tab.label).not.toMatch(/typical|high-saving|percentile/i);
    }
  });

  it("explains the failure in the method, and labels the scores shown as the dry run's", () => {
    render(<Dashboard data={shown} />);
    fireEvent.click(screen.getByRole("tab", { name: TAB_OPTIONS.find((t) => t.id === "method").label }));
    expect(screen.getByTestId("expected-value-omission").textContent).toContain(BINDING_C2_OUTCOME.reason);
    const headline = screen.queryByTestId("c2-headline");
    if (headline) expect(headline.textContent).toContain("In the dry run before the Budget");
    expect(screen.getByTestId("c2-screen").textContent).toContain("These are the dry run's scores");
  });

  it("is not shown on the committed file itself or a sample", () => {
    render(<Dashboard data={realData} />);
    expect(screen.queryByTestId("binding-outcome-notice")).toBeNull();
    render(<Dashboard data={fixture} />);
    expect(screen.queryByTestId("binding-outcome-notice")).toBeNull();
  });
});
