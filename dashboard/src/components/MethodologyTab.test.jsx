import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MethodologyTab from "./MethodologyTab";
import { BAD_TEXT_VALUES, BAD_VALUES, BROKEN_TEXT, fixture, mutate, textOf } from "../lib/testUtils";

describe("MethodologyTab with the sample fixture", () => {
  it("renders every limitation, source and benchmark from metadata", () => {
    const text = textOf(<MethodologyTab data={fixture} />);
    for (const item of fixture.metadata.method_limitations) expect(text).toContain(item);
    for (const s of fixture.metadata.sources) expect(text).toContain(typeof s === "string" ? s : s.title);
    for (const b of fixture.metadata.benchmarks.filter((x) => x.verified)) {
      expect(text).toContain(b.title);
      expect(text).toContain(b.publisher);
      expect(text).toContain(b.date);
    }
    expect(text).not.toMatch(BROKEN_TEXT);
    expect(text).not.toContain("unavailable");
  });

  it("shows at-a-glance tiles from the file", () => {
    render(<MethodologyTab data={fixture} />);
    const tiles = screen.getAllByTestId("glance-tile").map((t) => t.textContent).join(" | ");
    expect(tiles).toContain(`${fixture.horizon.length} fiscal years`);
    expect(tiles).toContain(fixture.uncertainty.n_draws.toLocaleString("en-GB"));
    expect(tiles).toContain(fixture.provenance.packages["policyengine-uk"]);
    expect(tiles).toContain(fixture.provenance.dataset.name);
    expect(tiles).toContain(String(Object.keys(fixture.policies).length));
  });

  it("renders five numbered costing steps and an explainer in every section", () => {
    const { container } = render(<MethodologyTab data={fixture} />);
    expect(within(screen.getByTestId("steps")).getAllByRole("listitem").length).toBe(5);
    for (const section of container.querySelectorAll("section")) {
      expect(within(section).getByTestId("explainer").textContent.length).toBeGreaterThan(20);
    }
  });

  it("compares the main method with the VAR cross-check", () => {
    render(<MethodologyTab data={fixture} />);
    const table = screen.getByTestId("uncertainty-methods").textContent;
    expect(table).toContain("Cross-check: VAR model");
    expect(table).toContain(fixture.uncertainty.var_cross_check.n_draws.toLocaleString("en-GB"));
    expect(table).toContain(`first ${fixture.uncertainty.error_source.block_horizon} years`);
    expect(table).toContain(`previous ${fixture.uncertainty.var_cross_check.lag_order}`);
  });

  it("drops the VAR column when the file has no cross-check", () => {
    render(<MethodologyTab data={mutate("uncertainty.var_cross_check", null, { remove: true })} />);
    expect(screen.getByTestId("uncertainty-methods").textContent).not.toContain("VAR");
  });

  it("groups limitations in one card, with the largest-household table under Data", () => {
    render(<MethodologyTab data={fixture} />);
    expect(screen.queryByTestId("central-notes")).toBeNull();
    expect(within(screen.getByTestId("limitations-data")).getByTestId("largest-household")).toBeTruthy();
    const table = screen.getByTestId("largest-household").textContent;
    const first = fixture.central.cost_vs_triple_lock_bn.double_lock.largest_single_household;
    expect(table).toContain(`£${first[String(fixture.horizon[0])].contribution_bn.toFixed(2)}bn`);
  });

  it("lists the frozen-ages caveat and only benchmarks checked against their source", () => {
    render(<MethodologyTab data={fixture} />);
    expect(screen.getByTestId("composition-limitation").textContent).toContain(
      `${fixture.central.composition_effect.difference_pct.toFixed(0)}% above a scenario`,
    );
    const table = screen.getByTestId("sources");
    for (const b of fixture.metadata.benchmarks.filter((x) => x.verified)) {
      expect(table.textContent).toContain(b.title);
    }
    for (const b of fixture.metadata.benchmarks.filter((x) => !x.verified)) {
      expect(table.textContent).not.toContain(b.title);
    }
    expect(table.textContent).not.toContain("Checked");
  });

  it("pins versions in the replication line", () => {
    render(<MethodologyTab data={fixture} />);
    const line = screen.getByTestId("replication").textContent;
    const p = fixture.provenance;
    expect(line).toContain(
      `Built with policyengine.py ${p.packages.policyengine} on ${p.dataset.name} (${p.dataset.data_build}).`,
    );
  });

  it("never mentions constituencies in its own copy", () => {
    const noConst = structuredClone(fixture);
    expect(textOf(<MethodologyTab data={noConst} />).toLowerCase()).not.toContain("constituenc");
  });
});

describe("MethodologyTab fails closed", () => {
  const TEXT_PATHS = ["method_limitations.0", "sources.0"];
  it.each([
    ["metadata.method_limitations", "The list of limitations is unavailable"],
    ["metadata.method_limitations.0", "The list of limitations is unavailable"],
    ["metadata.sources", "The list of sources is unavailable"],
    ["metadata.sources.0", "The list of sources is unavailable"],
    ["metadata.benchmarks", "The list of benchmarks is unavailable"],
    ["central.cost_vs_triple_lock_bn.cpi_link.largest_single_household.2030.contribution_bn", "The largest-household table is unavailable"],
  ])("%s missing or invalid", (path, message) => {
    const values = TEXT_PATHS.some((t) => path.endsWith(t)) ? BAD_TEXT_VALUES : BAD_VALUES;
    for (const value of values) {
      const text = textOf(<MethodologyTab data={mutate(path, value)} />);
      expect(text, `${path}=${String(value)}`).toContain(message);
      expect(text).not.toMatch(BROKEN_TEXT);
    }
  });

  it("shows unavailable in a tile rather than 0 or blank", () => {
    render(<MethodologyTab data={mutate("uncertainty.n_draws", null, { remove: true })} />);
    const tile = screen.getAllByTestId("glance-tile").find((t) => t.textContent.includes("Simulated paths"));
    expect(tile.textContent).toContain("unavailable");
    expect(tile.textContent).not.toMatch(/\b0\b/);
  });

  it("omits version clauses that are missing instead of printing undefined", () => {
    const moved = mutate("provenance.packages", {});
    delete moved.provenance.dataset;
    render(<MethodologyTab data={moved} />);
    const line = screen.getByTestId("replication").textContent;
    expect(line).toContain("Built with policyengine.py.");
    expect(line).not.toMatch(BROKEN_TEXT);
    expect(line).not.toContain("null");
  });
});
