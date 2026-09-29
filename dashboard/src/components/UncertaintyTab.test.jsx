import { cleanup, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import UncertaintyTab from "./UncertaintyTab";
import { BAD_TEXT_VALUES, BAD_VALUES, BROKEN_TEXT, bn1, fixture, fy, mutate, textOf } from "../lib/testUtils";

const ALTS = Object.keys(fixture.policies).filter((id) => id !== "triple_lock");
const unc = fixture.uncertainty;

const TEXT_PATHS = [".method"];

describe("UncertaintyTab with the results file", () => {
  it("renders the median and 90% range for every alternative", () => {
    render(<UncertaintyTab data={fixture} />);
    for (const id of ALTS) {
      const q = unc.cost_of_triple_lock_vs[id];
      const block = screen.getByTestId(`range-${id}`).textContent.replace(/\s+/g, " ");
      expect(block).toContain(fixture.policies[id].label);
      expect(block).toContain(`Median ${bn1(q.p50)}`);
      // One ordered phrase, so a p5/p95 swap cannot pass.
      expect(block).toContain(`90% range ${bn1(q.p5)} to ${bn1(q.p95)}`);
    }
  });

  it("renders the probability the floor binds for every year", () => {
    const text = textOf(<UncertaintyTab data={fixture} />);
    for (const [year, share] of Object.entries(unc.prob_triple_lock_binds_on_floor)) {
      expect(text).toContain(`${fy(Number(year))}${(share * 100).toFixed(0)}%`);
    }
  });

  it("renders the triple lock fan table and the method", () => {
    const text = textOf(<UncertaintyTab data={fixture} />);
    const last = String(fixture.horizon[fixture.horizon.length - 1]);
    const point = unc.fan.triple_lock[last];
    expect(text).toContain(`${fy(Number(last))}${point.p10.toFixed(3)}${point.p50.toFixed(3)}${point.p90.toFixed(3)}`);
    expect(text).toContain(unc.n_draws.toLocaleString("en-GB"));
    expect(text).toContain(unc.error_source.title);
    expect(text).toContain("distinct paths");
    expect(text).not.toMatch(BROKEN_TEXT);
    expect(text).not.toContain("unavailable");
  });
});

describe("UncertaintyTab fails closed", () => {
  const last = String(fixture.horizon[fixture.horizon.length - 1]);
  const cases = [
    ["uncertainty.fan.triple_lock.2030.p50", "The fan chart for"],
    [`uncertainty.fan.triple_lock.${last}`, "The fan chart for"],
    ["uncertainty.prob_triple_lock_binds_on_floor.2031", "The probability that the 2.5% floor applies is unavailable"],
    ["uncertainty.n_draws", "The uncertainty method is unavailable"],
    ["uncertainty.error_source.method", "The uncertainty method is unavailable"],
    ["uncertainty.cost_of_triple_lock_vs", "The cost distribution is unavailable"],
  ];

  it.each(cases)("%s missing or invalid", (path, message) => {
    const values = TEXT_PATHS.some((t) => path.endsWith(t)) ? BAD_TEXT_VALUES : BAD_VALUES;
    for (const value of values) {
      const text = textOf(<UncertaintyTab data={mutate(path, value)} />);
      expect(text, `${path}=${String(value)}`).toContain(message);
      expect(text).not.toMatch(BROKEN_TEXT);
    }
  });

  it("drops only the alternative whose quantiles are broken", () => {
    const [broken, ...rest] = ALTS;
    for (const key of ["p5", "p50", "p95", "mean"]) {
      for (const value of BAD_VALUES) {
        render(<UncertaintyTab data={mutate(`uncertainty.cost_of_triple_lock_vs.${broken}.${key}`, value)} />);
        expect(screen.getByTestId(`range-${broken}`).textContent).toContain("is unavailable");
        for (const id of rest) {
          expect(screen.getByTestId(`range-${id}`).textContent).toContain("Median");
        }
        cleanup();
      }
    }
  });

  it("rejects quantiles out of order", () => {
    const id = ALTS[0];
    const q = unc.cost_of_triple_lock_vs[id];
    render(<UncertaintyTab data={mutate(`uncertainty.cost_of_triple_lock_vs.${id}.p75`, q.p25 - 1)} />);
    expect(screen.getByTestId(`range-${id}`).textContent).toContain("is unavailable");
  });

  it("rejects a floor probability given as a percentage", () => {
    const text = textOf(<UncertaintyTab data={mutate("uncertainty.prob_triple_lock_binds_on_floor.2029", 31)} />);
    expect(text).toContain("The probability that the 2.5% floor applies is unavailable");
  });
});

const bnq = (v) => `£${Math.abs(v).toFixed(1)}bn`;

describe("UncertaintyTab robustness table", () => {
  const rows = [
    ["main", unc],
    ["proxy", unc.sensitivity_proxy_only],
    ["raw", unc.sensitivity_raw_errors],
    ["ex_2022_23", unc.sensitivity_ex_2022_23],
    ["var", unc.var_cross_check],
  ];

  it("labels the rows in the agreed order", () => {
    render(<UncertaintyTab data={fixture} />);
    const labels = [...screen.getByTestId("robustness").querySelectorAll("tbody tr td:first-child")].map((td) => td.textContent);
    expect(labels).toEqual([
      "Main (statutory inputs)",
      "OBR measures only (no statutory gaps)",
      "Raw OBR errors (includes the OBR's past bias)",
      "Excluding the 2022–23 shocks",
      "VAR cross-check",
    ]);
  });

  it("says the result is sensitive rather than that close rows settle it", () => {
    const text = textOf(<UncertaintyTab data={fixture} />);
    expect(text).toContain("sensitive to two things");
    expect(text).not.toContain("does not depend much");
  });

  it("renders p10/p50/p90 for each method and alternative", () => {
    render(<UncertaintyTab data={fixture} />);
    for (const [id, block] of rows) {
      const row = screen.getByTestId(`robustness-${id}`).textContent.replace(/\s+/g, " ");
      for (const alt of ALTS) {
        const q = block.cost_of_triple_lock_vs[alt];
        expect(row, `${id} ${alt}`).toContain(`${bnq(q.p50)} (${bnq(q.p10)} to ${bnq(q.p90)})`);
      }
    }
  });

  it("omits a method row whose block is absent", () => {
    render(<UncertaintyTab data={mutate("uncertainty.var_cross_check", null, { remove: true })} />);
    expect(screen.queryByTestId("robustness-var")).toBeNull();
    expect(screen.getByTestId("robustness-ex_2022_23")).toBeTruthy();
    expect(screen.queryByTestId("robustness-ex_covid")).toBeNull();
  });

  it("fails closed on a bad value in a present row", () => {
    for (const key of ["p10", "p50", "p90"]) {
      for (const value of BAD_VALUES) {
        render(<UncertaintyTab data={mutate(`uncertainty.var_cross_check.cost_of_triple_lock_vs.${ALTS[0]}.${key}`, value)} />);
        const row = screen.getByTestId("robustness-var").textContent;
        expect(row, `${key}=${String(value)}`).toContain("unavailable");
        expect(row).not.toMatch(BROKEN_TEXT);
        cleanup();
      }
    }
  });
});

describe("UncertaintyTab explainers", () => {
  it("renders an explainer in every section", () => {
    const { container } = render(<UncertaintyTab data={fixture} />);
    const sections = container.querySelectorAll("section");
    expect(sections.length).toBe(6);
    for (const section of sections) {
      expect(within(section).getByTestId("explainer").textContent.length).toBeGreaterThan(40);
    }
    const text = container.textContent;
    expect(text).toContain("middle 80% of draws");
    expect(text).not.toContain("1 path in 10");
    expect(text).toContain("binds");
    expect(text).toContain("fan chart");
    expect(text).toContain("forecasts made in 2010–2024");
    expect(text).toContain("144 distinct paths");
  });

  it("puts each range into words and compares it with the central forecast", () => {
    render(<UncertaintyTab data={fixture} />);
    const last = String(fixture.horizon[fixture.horizon.length - 1]);
    for (const id of ALTS) {
      const q = unc.cost_of_triple_lock_vs[id];
      const central = -fixture.central.cost_vs_triple_lock_bn[id].gross[last];
      const words = screen.getByTestId(`words-${id}`).textContent;
      expect(words).toContain(`runs from ${bnq(q.p10)} to ${bnq(q.p90)}`);
      expect(words).toContain(`median of ${bnq(q.p50)}`);
      expect(words).toContain(`central forecast alone it is ${bnq(central)}`);
    }
  });

  it("explains the spread without blaming a triple-lock-only ratchet", () => {
    render(<UncertaintyTab data={fixture} />);
    const note = screen.getByTestId("spread-note").textContent.replace(/\s+/g, " ");
    expect(note).toContain("near the bottom of the simulated range");
    expect(note).toContain("highest of three rates");
    expect(note).toContain("Every rule compounds");
    expect(note).not.toContain("never back down");
    for (const id of ALTS) {
      const m = unc.sensitivity_ex_2022_23.cost_of_triple_lock_vs[id].p50;
      expect(note).toContain(`${bnq(m)} against the ${fixture.policies[id].label}`);
    }
  });

  it("names the central-forecast years where the floor applies, from the file", () => {
    const floorYears = fixture.horizon.filter(
      (y) => Math.abs(fixture.central.uprating.triple_lock[String(y)] - fixture.metadata.triple_lock_floor) < 1e-9,
    );
    const note = (() => {
      render(<UncertaintyTab data={fixture} />);
      return screen.getByTestId("spread-note").textContent;
    })();
    for (const y of floorYears) expect(note).toContain(fy(y));
  });

  it("omits the spread note when the central cost is not low in the range", () => {
    const low = structuredClone(fixture);
    for (const id of ALTS) {
      for (const k of ["p5", "p10", "p25", "p50", "p75", "p90", "p95", "mean"]) {
        low.uncertainty.cost_of_triple_lock_vs[id][k] = 0;
      }
    }
    render(<UncertaintyTab data={low} />);
    expect(screen.queryByTestId("spread-note")).toBeNull();
  });

  it("does not compare with the central cost when the basis is not stated", () => {
    const noBasis = mutate(`uncertainty.cost_of_triple_lock_vs.${ALTS[0]}.basis`, null, { remove: true });
    render(<UncertaintyTab data={noBasis} />);
    expect(screen.getByTestId(`words-${ALTS[0]}`).textContent).not.toContain("central forecast alone");
  });

  it("shows uncertainty benchmarks with a horizon warning and inline links", () => {
    const { container } = render(<UncertaintyTab data={fixture} />);
    const table = screen.getByTestId("benchmarks-uncertainty");
    for (const b of fixture.metadata.benchmarks) {
      if (b.verified && b.our_metric.startsWith("uncertainty.")) {
        expect(within(table).getByRole("link", { name: b.title }).getAttribute("href")).toBe(b.url);
      } else {
        expect(table.textContent).not.toContain(b.title);
      }
    }
    expect(container.textContent).toContain("compare the width of the ranges");
  });
});
