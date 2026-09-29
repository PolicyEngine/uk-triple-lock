/**
 * Render-level contract for the Cost tab. Expected values are derived from
 * the results file, not hard-coded, so the real pipeline output can replace
 * the sample fixture without editing these tests.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CostTab, { HEADLINE_YEARS } from "./CostTab";
import { BAD_TEXT_VALUES, BAD_VALUES, BROKEN_TEXT, bn1, fixture, fy, mutate, textOf } from "../lib/testUtils";

const ALTS = Object.keys(fixture.policies).filter((id) => id !== "triple_lock");
const cost = fixture.central.cost_vs_triple_lock_bn;

function expectedPhrase(value) {
  if (Number(Math.abs(value).toFixed(1)) === 0) return "No difference";
  return value < 0 ? `${bn1(value)} saving` : `${bn1(value)} extra cost`;
}

const TEXT_PATHS = [".label"];

describe("CostTab with the results file", () => {
  it("renders a gross headline for every alternative and headline year", () => {
    render(<CostTab data={fixture} />);
    for (const id of ALTS) {
      const card = screen.getByTestId(`headline-${id}`).textContent;
      expect(card).toContain(fixture.policies[id].label);
      for (const year of HEADLINE_YEARS) {
        expect(card).toContain(fy(year));
        expect(card).toContain(expectedPhrase(cost[id].gross[String(year)]));
      }
    }
  });

  it("switches the headlines to the net basis", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    for (const id of ALTS) {
      const card = screen.getByTestId(`headline-${id}`).textContent;
      for (const year of HEADLINE_YEARS) {
        expect(card).toContain(expectedPhrase(cost[id].net[String(year)]));
      }
    }
  });

  it("renders the weekly State Pension for every rule and year", () => {
    const text = textOf(<CostTab data={fixture} />);
    for (const [id, series] of Object.entries(fixture.central.full_state_pension_weekly)) {
      expect(text).toContain(fixture.policies[id].label);
      for (const value of Object.values(series)) {
        expect(text).toContain(`£${value.toFixed(2)}`);
      }
    }
    expect(text).not.toMatch(BROKEN_TEXT);
    expect(text).not.toContain("unavailable");
  });

  it("labels the triple lock as current policy from the data", () => {
    expect(textOf(<CostTab data={fixture} />)).toContain(fixture.policies.triple_lock.label);
  });

  it("moves with the data, so no headline is a literal", () => {
    const id = ALTS[0];
    const year = String(HEADLINE_YEARS[1]);
    const moved = mutate(`central.cost_vs_triple_lock_bn.${id}.gross.${year}`, -98.76);
    const card = (() => {
      render(<CostTab data={moved} />);
      return screen.getByTestId(`headline-${id}`).textContent;
    })();
    expect(card).toContain("£98.8bn saving");
  });

  it("says extra cost when a rule costs more than the triple lock", () => {
    const id = ALTS[0];
    const moved = mutate(`central.cost_vs_triple_lock_bn.${id}.gross.${HEADLINE_YEARS[0]}`, 1.23);
    render(<CostTab data={moved} />);
    expect(screen.getByTestId(`headline-${id}`).textContent).toContain("£1.2bn extra cost");
  });
});

describe("CostTab fails closed", () => {
  const cases = [
    [`central.cost_vs_triple_lock_bn.${ALTS[0]}.gross.${HEADLINE_YEARS[0]}`, "The annual cost chart is unavailable"],
    [`central.cost_vs_triple_lock_bn.${ALTS[1]}.gross.2031`, "The annual cost chart is unavailable"],
    [`central.full_state_pension_weekly.${ALTS[2]}.2030`, "The weekly State Pension table is unavailable"],
    ["central.full_state_pension_weekly.triple_lock.2034", "The weekly State Pension table is unavailable"],
    ["central.uprating.triple_lock.2027", "The uprating table is unavailable"],
    ["horizon", "The annual cost chart is unavailable"],
    ["policies.triple_lock.label", "The list of uprating rules is unavailable"],
  ];

  it.each(cases)("%s missing or invalid", (path, message) => {
    const values = TEXT_PATHS.some((t) => path.endsWith(t)) ? BAD_TEXT_VALUES : BAD_VALUES;
    for (const value of values) {
      const text = textOf(<CostTab data={mutate(path, value)} />);
      expect(text, `${path}=${String(value)}`).toContain(message);
      expect(text).not.toMatch(BROKEN_TEXT);
    }
  });

  it("shows unavailable in the headline card rather than a blank", () => {
    const path = `central.cost_vs_triple_lock_bn.${ALTS[0]}.gross.${HEADLINE_YEARS[0]}`;
    render(<CostTab data={mutate(path, undefined)} />);
    expect(screen.getByTestId(`headline-${ALTS[0]}`).textContent).toContain("unavailable");
  });

  it("rejects an uprating rate given as a percentage", () => {
    const text = textOf(<CostTab data={mutate("central.uprating.double_lock.2028", 3.1)} />);
    expect(text).toContain("The uprating table is unavailable");
  });

  it("rejects a missing triple lock", () => {
    const text = textOf(<CostTab data={mutate("policies.triple_lock", null, { remove: true })} />);
    expect(text).toContain("The list of uprating rules is unavailable");
  });
});

describe("CostTab explainers", () => {
  it("renders an explainer in every section", () => {
    const { container } = render(<CostTab data={fixture} />);
    const sections = container.querySelectorAll("section");
    expect(sections.length).toBe(6);
    for (const section of sections) {
      expect(within(section).getByTestId("explainer").textContent.length).toBeGreaterThan(40);
    }
    const text = container.textContent;
    expect(text).toContain("Gross counts State Pension spending only");
    expect(text).toContain("Pension Credit");
    expect(text).toContain("Below zero means the rule is cheaper");
  });

  it("derives the starting weekly rate from the file", () => {
    const b = fixture.central.base_year_weekly;
    const moved = mutate("central.base_year_weekly.new_state_pension", 199.99);
    expect(textOf(<CostTab data={fixture} />)).toContain(`starting from £${b.new_state_pension.toFixed(2)}`);
    expect(textOf(<CostTab data={moved} />)).toContain("starting from £199.99");
  });

  it("explains why the double lock and earnings link match only when they do", () => {
    const same = structuredClone(fixture);
    same.central.uprating.double_lock = structuredClone(same.central.uprating.earnings_link);
    for (const y of Object.keys(same.central.forecast.cpi)) {
      same.central.forecast.earnings[y] = same.central.forecast.cpi[y] + 0.01;
    }
    expect(textOf(<CostTab data={same} />)).toContain("give the same result");
    // The sample fixture's rules differ in one year, so the note is absent.
    expect(textOf(<CostTab data={fixture} />)).not.toContain("give the same result");
  });

  it("shows the lumpy-household caveat on the net basis", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    expect(document.body.textContent).toContain("one survey household");
  });
});

describe("CostTab benchmarks", () => {
  const central = fixture.metadata.benchmarks.filter((b) => b.verified && b.our_metric.startsWith("central."));
  const other = fixture.metadata.benchmarks.filter((b) => !b.verified || !b.our_metric.startsWith("central."));

  it("shows only central.* benchmarks, linked, with a like-for-like badge", () => {
    render(<CostTab data={fixture} />);
    const table = screen.getByTestId("benchmarks-central");
    for (const b of central) {
      const link = within(table).getByRole("link", { name: b.title });
      expect(link.getAttribute("href")).toBe(b.url);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noreferrer");
      expect(table.textContent).toContain(b.figure_text);
      expect(table.textContent).toContain(b.publisher);
    }
    for (const b of other) expect(table.textContent).not.toContain(b.title);
  });

  it("links the benchmark inline in the explainer", () => {
    const { container } = render(<CostTab data={fixture} />);
    const explainers = container.querySelectorAll("[data-testid=explainer]");
    const last = explainers[explainers.length - 1];
    expect(within(last).getByRole("link", { name: central[0].title })).toBeTruthy();
  });

  it("fails closed when the array is missing or a row is invalid", () => {
    for (const [path, value] of [
      ["metadata.benchmarks", undefined],
      ["metadata.benchmarks.0.url", "not a url"],
      ["metadata.benchmarks.0.like_for_like", "maybe"],
      ["metadata.benchmarks.1.publisher", ""],
      ["metadata.benchmarks.0.our_value", Number.NaN],
    ]) {
      const text = textOf(<CostTab data={mutate(path, value)} />);
      expect(text, path).toContain("The comparison with other analyses is unavailable");
      expect(text).not.toMatch(BROKEN_TEXT);
    }
  });
});

describe("CostTab net excluding the largest household", () => {
  it("charts the largest household's contribution for every rule at once", () => {
    render(<CostTab data={fixture} />);
    const box = screen.getByTestId("net-adjusted");
    expect(within(box).queryByRole("group")).toBeNull();
    for (const id of ALTS) expect(box.textContent).toContain(fixture.policies[id].label);
    expect(box.textContent).not.toContain("without the survey household");
  });

  it("keeps the headline cards to one figure each", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    expect(screen.queryByTestId(`net-excl-${ALTS[0]}-${HEADLINE_YEARS[0]}`)).toBeNull();
  });

  it("derives the example household contribution from the file", () => {
    render(<CostTab data={fixture} />);
    const year = String(HEADLINE_YEARS[0]);
    const top = Math.max(
      ...ALTS.map((id) => Math.abs(fixture.central.cost_vs_triple_lock_bn[id].largest_single_household[year].contribution_bn)),
    );
    expect(screen.getByTestId("largest-note").textContent).toContain(`£${top.toFixed(1)}bn`);
  });

  it("fails closed on a missing adjusted figure", () => {
    const last = ALTS[ALTS.length - 1];
    const path = `central.cost_vs_triple_lock_bn.${last}.largest_single_household.${HEADLINE_YEARS[0]}.contribution_bn`;
    for (const value of BAD_VALUES) {
      const text = textOf(<CostTab data={mutate(path, value)} />);
      expect(text).toContain("The net cost chart is unavailable");
      expect(text).not.toMatch(BROKEN_TEXT);
    }
  });
});

describe("CostTab composition caveat and verified badge", () => {
  it("shows the fixed-composition scenario from the file, not an overstatement", () => {
    render(<CostTab data={fixture} />);
    const c = fixture.central.composition_effect;
    const text = screen.getByTestId("composition-caveat").textContent;
    expect(text).toContain(`${c.difference_pct.toFixed(0)}%`);
    expect(text).not.toMatch(/overstat/i);
  });

  it("fails closed without a composition effect", () => {
    for (const value of BAD_VALUES) {
      const text = textOf(<CostTab data={mutate("central.composition_effect.difference_pct", value)} />);
      expect(text).toContain("The ageing caveat (composition effect) is unavailable");
    }
  });

  it("shows only benchmarks checked against their source", () => {
    render(<CostTab data={fixture} />);
    const table = screen.getByTestId("benchmarks-central");
    for (const b of fixture.metadata.benchmarks.filter((x) => x.our_metric.startsWith("central."))) {
      if (b.verified) expect(table.textContent).toContain(b.title);
      else expect(table.textContent).not.toContain(b.title);
    }
    expect(table.textContent).not.toMatch(/verified/i);
  });

  it("fails closed when verified is not a boolean", () => {
    for (const value of [undefined, "yes", 1]) {
      const text = textOf(<CostTab data={mutate("metadata.benchmarks.0.verified", value)} />);
      expect(text).toContain("The comparison with other analyses is unavailable");
    }
  });
});

describe("CostTab chart when the double lock equals the earnings link", () => {
  it("draws one merged line and labels it", () => {
    const d = structuredClone(fixture);
    d.central.uprating.double_lock = { ...d.central.uprating.earnings_link };
    d.central.cost_vs_triple_lock_bn.double_lock = structuredClone(d.central.cost_vs_triple_lock_bn.earnings_link);
    const text = textOf(<CostTab data={d} />);
    expect(text).toContain("Double lock = Earnings link (same on this forecast)");
  });
});

describe("CostTab weekly State Pension chart", () => {
  it("compares two chosen rules and states the final-year gap", () => {
    render(<CostTab data={fixture} />);
    const last = String(fixture.horizon[fixture.horizon.length - 1]);
    const w = fixture.central.full_state_pension_weekly;
    const gap = Math.abs(w.triple_lock[last] - w.cpi_link[last]).toFixed(2);
    expect(screen.getByTestId("weekly-gap").textContent).toContain(`£${gap}`);
    fireEvent.click(within(screen.getByTestId("weekly-rule-1")).getByRole("button", { name: /Earnings link/ }));
    const gap2 = Math.abs(w.triple_lock[last] - w.earnings_link[last]).toFixed(2);
    expect(screen.getByTestId("weekly-gap").textContent).toContain(`£${gap2}`);
    expect(screen.getByTestId("weekly-gap").textContent).toContain("Earnings link");
  });
});
