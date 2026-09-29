import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AffectedTab from "./AffectedTab";
import { BAD_TEXT_VALUES, BAD_VALUES, BROKEN_TEXT, fixture, mutate, textOf } from "../lib/testUtils";

const ALTS = Object.keys(fixture.policies).filter((id) => id !== "triple_lock");
const first = ALTS[0];
const gbp = (v) => `${v < 0 ? "-" : ""}£${Math.abs(Math.round(v)).toLocaleString("en-GB")}`;
const QUINTILES = ["Poorest fifth", "2nd", "3rd", "4th", "Richest fifth"];

function groupButton(name) {
  return within(screen.getByRole("group", { name: "Group" })).queryByRole("button", { name });
}

function tableText() {
  return screen.getByTestId("group-table").textContent;
}

describe("AffectedTab with the sample fixture", () => {
  it("defaults to income quintiles with the fixed labels, not the file's", () => {
    render(<AffectedTab data={fixture} />);
    const text = tableText();
    for (const [i, row] of fixture.central.by_quintile[first].entries()) {
      expect(text).toContain(QUINTILES[i]);
      expect(text).toContain(gbp(row.mean_change_gbp));
      expect(text).toContain(`${row.pct_income_change.toFixed(2)}%`);
      expect(text).toContain(`${row.share_of_households_pct.toFixed(1)}%`);
    }
    expect(text).not.toContain("Quintile 1");
  });

  it("shows only the breakdowns present in the file", () => {
    render(<AffectedTab data={fixture} />);
    expect(groupButton("Income quintile")).not.toBeNull();
    expect(groupButton("Region")).not.toBeNull();
    expect(groupButton("Household type")).not.toBeNull();
    expect(groupButton("Tenure")).not.toBeNull();
    // The fixture has no by_age_band.
    expect(groupButton("Age")).toBeNull();
  });

  it("switches data with the group toggle", () => {
    render(<AffectedTab data={fixture} />);
    for (const [name, key] of [
      ["Region", "by_region"],
      ["Household type", "by_hh_type"],
      ["Tenure", "by_tenure"],
    ]) {
      fireEvent.click(groupButton(name));
      const text = tableText();
      for (const row of fixture.central[key][first]) {
        expect(text).toContain(row.label);
        expect(text).toContain(gbp(row.mean_change_gbp));
      }
    }
  });

  it("switches rule with the rule toggle", () => {
    const other = ALTS[ALTS.length - 1];
    render(<AffectedTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: fixture.policies[other].label }));
    for (const row of fixture.central.by_quintile[other]) {
      expect(tableText()).toContain(gbp(row.mean_change_gbp));
    }
  });

  it("renders the share of households losing for every alternative", () => {
    render(<AffectedTab data={fixture} />);
    for (const id of ALTS) {
      const card = screen.getByTestId(`losers-${id}`).textContent;
      const block = fixture.central.households_affected[id];
      expect(card).toContain(`${block.losing_pct.toFixed(1)}%`);
      expect(card).toContain(gbp(block.mean_loss_gbp));
    }
  });

  it("renders an explainer in every section, with the year from the file", () => {
    const { container } = render(<AffectedTab data={fixture} />);
    const sections = container.querySelectorAll("section");
    expect(sections.length).toBe(2);
    for (const section of sections) {
      expect(within(section).getByTestId("explainer").textContent.length).toBeGreaterThan(40);
    }
    const year = fixture.central.distribution_year;
    const fy = `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
    const text = container.textContent;
    expect(text).toContain(`in ${fy}`);
    expect(text).toContain("Mean change");
    expect(text).toContain("% of income");
    expect(text).toContain("additional State Pension is the same in every scenario");
  });

  it("has no constituency section", () => {
    expect(textOf(<AffectedTab data={fixture} />).toLowerCase()).not.toContain("constituenc");
  });
});

describe("AffectedTab fails closed", () => {
  const TEXT_PATHS = [".label"];
  const cases = [
    [`central.by_quintile.${first}.3.mean_change_gbp`, "The breakdown by income quintile is unavailable"],
    [`central.by_quintile.${first}.4.pct_income_change`, "The breakdown by income quintile is unavailable"],
    [`central.by_quintile.${first}.0.quintile`, "The breakdown by income quintile is unavailable"],
    [`central.by_quintile.${first}.1.total_bn`, "The breakdown by income quintile is unavailable"],
    [`central.by_quintile.${first}.2.share_of_households_pct`, "The breakdown by income quintile is unavailable"],
    [`central.by_quintile.${first}`, "The breakdown by income quintile is unavailable"],
  ];

  it.each(cases)("%s missing or invalid", (path, message) => {
    const values = TEXT_PATHS.some((t) => path.endsWith(t)) ? BAD_TEXT_VALUES : BAD_VALUES;
    for (const value of values) {
      const text = textOf(<AffectedTab data={mutate(path, value)} />);
      expect(text, `${path}=${String(value)}`).toContain(message);
      expect(text).not.toMatch(BROKEN_TEXT);
      expect(text).not.toMatch(/£0\b/);
    }
  });

  it("fails closed on a bad region label rather than showing the code", () => {
    for (const value of BAD_TEXT_VALUES) {
      render(<AffectedTab data={mutate(`central.by_region.${first}.0.label`, value)} />);
      fireEvent.click(groupButton("Region"));
      expect(screen.getByText(/The breakdown by region is unavailable/)).toBeTruthy();
      cleanup();
    }
  });

  it("rejects a quintile table without five rows", () => {
    const short = mutate(`central.by_quintile.${first}`, fixture.central.by_quintile[first].slice(0, 4));
    expect(textOf(<AffectedTab data={short} />)).toContain("The breakdown by income quintile is unavailable");
  });

  it("hides the button of a missing breakdown and never falls back to deciles", () => {
    const noQuintile = mutate("central.by_quintile", null, { remove: true });
    noQuintile.central.by_decile = { [first]: [] };
    render(<AffectedTab data={noQuintile} />);
    expect(groupButton("Income quintile")).toBeNull();
    expect(groupButton("Region")).not.toBeNull();
    expect(screen.queryByText(/decile/i)).toBeNull();
  });

  it("shows unavailable when no breakdown is present", () => {
    const none = structuredClone(fixture);
    for (const k of ["by_quintile", "by_region", "by_hh_type", "by_tenure"]) delete none.central[k];
    expect(textOf(<AffectedTab data={none} />)).toContain("The breakdown by group is unavailable");
  });

  it("shows unavailable in a losers card with a bad share", () => {
    for (const value of [...BAD_VALUES, -1, 150]) {
      render(<AffectedTab data={mutate(`central.households_affected.${first}.losing_pct`, value)} />);
      const card = screen.getByTestId(`losers-${first}`).textContent;
      expect(card, String(value)).toContain("Unavailable in this results file.");
      expect(card).not.toMatch(BROKEN_TEXT);
      cleanup();
    }
  });

  it("says the year is unavailable rather than guessing it", () => {
    const text = textOf(<AffectedTab data={mutate("central.distribution_year", null, { remove: true })} />);
    expect(text).toContain("in unavailable");
  });
});
