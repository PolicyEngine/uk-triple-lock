/**
 * Render contract against the real pipeline output in public/data. Every
 * expectation is derived from that file, so a new pipeline run updates the
 * contract; a field the file does not (yet) carry must fail closed.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = new URLSearchParams();
const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

import AffectedTab from "./AffectedTab";
import CostTab from "./CostTab";
import Dashboard from "./Dashboard";
import MethodologyTab from "./MethodologyTab";
import UncertaintyTab from "./UncertaintyTab";
import { BROKEN_TEXT, realData as data, textOf } from "../lib/testUtils";

const ALTS = Object.keys(data.policies).filter((id) => id !== "triple_lock");
const TABS = ["Cost", "Who's affected", "Uncertainty", "Methodology"];
const bn1 = (v) => `£${Math.abs(v).toFixed(1)}bn`;
const gbp = (v) => `${v < 0 ? "-" : ""}£${Math.abs(Math.round(v)).toLocaleString("en-GB")}`;

describe("real results file", () => {
  it("renders every tab without broken text", () => {
    const { container } = render(<Dashboard data={data} />);
    for (const tab of TABS) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(container.textContent.replace(/\s+/g, " "), tab).not.toMatch(BROKEN_TEXT);
    }
  });

  it("renders the 2034-35 gross headline for every alternative", () => {
    render(<CostTab data={data} />);
    for (const id of ALTS) {
      const v = data.central.cost_vs_triple_lock_bn[id].gross["2034"];
      expect(screen.getByTestId(`headline-${id}`).textContent).toContain(`${bn1(v)} saving`);
    }
  });

  it("renders the weekly State Pension for every rule", () => {
    const text = textOf(<CostTab data={data} />);
    for (const series of Object.values(data.central.full_state_pension_weekly)) {
      for (const v of Object.values(series)) expect(text).toContain(`£${v.toFixed(2)}`);
    }
  });

  it("renders quintiles if the file has them, and fails closed if not", () => {
    const text = textOf(<AffectedTab data={data} />);
    const rows = data.central.by_quintile?.[ALTS[0]];
    if (rows) {
      expect(text).toContain("Poorest fifth");
      for (const r of rows) expect(text).toContain(gbp(r.mean_change_gbp));
    } else {
      expect(text).not.toContain("Poorest fifth");
    }
    expect(text).not.toMatch(/decile/i);
    expect(text.toLowerCase()).not.toContain("constituenc");
  });

  it("renders the Monte Carlo median and robustness rows present in the file", () => {
    render(<UncertaintyTab data={data} />);
    for (const id of ALTS) {
      const q = data.uncertainty.cost_of_triple_lock_vs[id];
      expect(screen.getByTestId(`range-${id}`).textContent).toContain(`Median ${bn1(q.p50)}`);
    }
    const table = screen.getByTestId("robustness");
    for (const [key, id] of [
      ["sensitivity_raw_errors", "raw"],
      ["sensitivity_ex_2022_23", "ex_2022_23"],
      ["sensitivity_statutory_gaps", "statutory"],
      ["var_cross_check", "var"],
    ]) {
      const row = within(table).queryByTestId(`robustness-${id}`);
      if (data.uncertainty[key]) {
        const q = data.uncertainty[key].cost_of_triple_lock_vs[ALTS[0]];
        expect(row.textContent).toContain(bn1(q.p50));
      } else {
        expect(row).toBeNull();
      }
    }
  });

  it("renders every limitation and pins versions from provenance", () => {
    render(<MethodologyTab data={data} />);
    const text = document.body.textContent;
    for (const item of data.metadata.method_limitations) expect(text).toContain(item);
    const p = data.provenance;
    expect(screen.getByTestId("replication").textContent).toContain(
      `policyengine.py ${p.packages.policyengine} (policyengine-uk ${p.packages["policyengine-uk"]}) on ${p.dataset.name} (${p.dataset.data_build})`,
    );
  });

  it("renders benchmarks if the file has them, and fails closed if not", () => {
    const text = textOf(<MethodologyTab data={data} />);
    const valid =
      Array.isArray(data.metadata.benchmarks) &&
      data.metadata.benchmarks.every((b) => typeof b.verified === "boolean");
    if (valid) {
      for (const b of data.metadata.benchmarks) expect(text).toContain(b.title);
    } else {
      expect(text).toContain("The list of benchmarks is unavailable");
    }
  });
});
