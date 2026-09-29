/**
 * Render-level contract for the Cost tab. Expected values are derived from
 * the results file, not hard-coded, so the real pipeline output can replace
 * the sample fixture without editing these tests.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CostTab, { HEADLINE_YEARS } from "./CostTab";
import { BAD_TEXT_VALUES, BAD_VALUES, BROKEN_TEXT, bn1, fixture, mutate, textOf } from "../lib/testUtils";

const ALTS = Object.keys(fixture.policies).filter((id) => id !== "triple_lock");
const cost = fixture.central.cost_vs_triple_lock_bn;

const TEXT_PATHS = [".label"];

describe("CostTab with the results file", () => {
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
    expect(sections.length).toBe(5);
    for (const section of sections) {
      expect(within(section).getByTestId("explainer").textContent.length).toBeGreaterThan(40);
    }
    const text = container.textContent;
    expect(text).toContain("Gross is State Pension spending");
    expect(text).toContain("other benefits");
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
    expect(textOf(<CostTab data={same} />)).toContain("match here");
    // The sample fixture's rules differ in one year, so the note is absent.
    expect(textOf(<CostTab data={fixture} />)).not.toContain("match here");
  });

  it("shows the lumpy-household caveat on the net basis", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    expect(document.body.textContent).toMatch(/one survey household/i);
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

describe("CostTab headline cards", () => {
  it("keeps the headline cards to one figure each", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    expect(screen.queryByTestId(`net-excl-${ALTS[0]}-${HEADLINE_YEARS[0]}`)).toBeNull();
  });
});


describe("CostTab composition caveat and verified badge", () => {
  it("shows the fixed-composition scenario from the file, not an overstatement", () => {
    render(<CostTab data={fixture} />);
    const text = screen.getByTestId("composition-caveat").textContent;
    expect(text).toContain("no uncertainty range");
    expect(text).not.toMatch(/overstat/i);
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

describe("CostTab headline cards show the range of savings", () => {
  const unc = fixture.uncertainty.cost_of_triple_lock_vs;
  const last = String(fixture.horizon[fixture.horizon.length - 1]);

  it("gives the median, the 10th and 90th percentiles and the forecast figure for each rule", () => {
    render(<CostTab data={fixture} />);
    for (const id of ALTS) {
      const card = screen.getByTestId(`headline-${id}`).textContent;
      expect(screen.getByTestId(`median-${id}`).textContent).toBe(bn1(unc[id].p50));
      expect(card).toContain(`1 in 10 chance below ${bn1(unc[id].p10)}, 1 in 10 above ${bn1(unc[id].p90)}`);
      expect(card).toContain(`On the forecast alone: ${bn1(-cost[id].gross[last])}`);
    }
  });

  it("scales the range to net with the full-model net-to-gross ratio", () => {
    render(<CostTab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Net" }));
    for (const id of ALTS) {
      const runs = Object.values(fixture.uncertainty.net_on_representative_paths.by_alternative[id]);
      const ratios = runs.filter((r) => r.gross_bn > 0.1).map((r) => r.net_bn / r.gross_bn).sort((a, b) => a - b);
      const mid = Math.floor(ratios.length / 2);
      const ratio = ratios.length % 2 ? ratios[mid] : (ratios[mid - 1] + ratios[mid]) / 2;
      expect(screen.getByTestId(`median-${id}`).textContent).toBe(bn1(unc[id].p50 * ratio));
    }
  });

  it("fails closed per card when a rule has no range", () => {
    const text = textOf(<CostTab data={mutate(`uncertainty.cost_of_triple_lock_vs.${ALTS[0]}.p50`, null)} />);
    expect(text).toContain(`The range of savings for ${fixture.policies[ALTS[0]].label} is unavailable`);
  });
});
