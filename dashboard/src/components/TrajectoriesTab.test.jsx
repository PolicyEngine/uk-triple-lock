/**
 * Render contract for the Trajectories tab. Expected values come from the
 * committed trajectory_results.json, so a regenerated file needs no test edits.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => searchParams,
}));

import TrajectoriesTab from "./TrajectoriesTab";
import Dashboard from "./Dashboard";
import tdata from "../../public/data/trajectory_results.json";
import { BROKEN_TEXT, realData, textOf } from "../lib/testUtils";
import { formatBn, formatWeekly } from "../lib/formatters";
import { LARGEST_HOUSEHOLD_FLAG, differenceNotes, getTrajectories, readTrajectory } from "../lib/trajectoryHelpers";

const FINAL = String(tdata.horizon.at(-1));

function copyWith(path, value, { remove = false } = {}) {
  const copy = structuredClone(tdata);
  const parts = path.split(".");
  let node = copy;
  for (const part of parts.slice(0, -1)) node = node[part];
  if (remove) delete node[parts.at(-1)];
  else node[parts.at(-1)] = value;
  return copy;
}

describe("the results file", () => {
  it("has every trajectory valid for display", () => {
    expect(getTrajectories(tdata)).toHaveLength(tdata.trajectories.length);
  });

  it("records the central path first and the Uncertainty tab's paths", () => {
    const ids = tdata.trajectories.map((t) => t.id);
    expect(ids[0]).toBe("central");
    expect(ids).toEqual(expect.arrayContaining(["uncertainty_tab_p50", "uncertainty_tab_p90"]));
  });
});

describe("TrajectoriesTab: future paths", () => {
  it("offers every path and opens on the first", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const picker = screen.getByRole("group", { name: "Path" });
    for (const t of tdata.trajectories) expect(within(picker).getByRole("button", { name: t.label })).toBeTruthy();
    const first = tdata.trajectories[0];
    expect(screen.getByTestId("card-gross").textContent).toContain(formatBn(first.saving_bn[FINAL].gross, 2));
  });

  it.each(tdata.trajectories.map((t) => [t.id, t]))("shows %s's own figures when picked", (_, t) => {
    render(<TrajectoriesTab tdata={tdata} />);
    fireEvent.click(within(screen.getByRole("group", { name: "Path" })).getByRole("button", { name: t.label }));
    expect(screen.getByTestId("card-gross").textContent).toContain(formatBn(t.saving_bn[FINAL].gross, 2));
    expect(screen.getByTestId("card-net").textContent).toContain(formatBn(t.saving_bn[FINAL].net, 2));
    expect(screen.getByTestId("card-weekly").textContent).toContain(formatWeekly(t.weekly.burnham_2030.new_state_pension[FINAL]));
    expect(screen.getByTestId("card-weekly").textContent).toContain(formatWeekly(t.weekly.triple_lock.new_state_pension[FINAL]));
    const notes = screen.getByTestId("trajectory-notes").textContent;
    const traj = readTrajectory(tdata, t);
    for (const n of differenceNotes(traj)) expect(notes).toContain(`April ${n.year}`);
    const flagged = Math.abs(t.largest_household.share_of_income_change) >= LARGEST_HOUSEHOLD_FLAG;
    expect(screen.queryByTestId("largest-household-flag") !== null).toBe(flagged);
  });

  it("explains the central path's single difference as the earnings-path catch-up", () => {
    const central = readTrajectory(tdata, tdata.trajectories[0]);
    const notes = differenceNotes(central);
    expect(notes.length).toBeGreaterThan(0);
    expect(notes.some((n) => n.text.includes("catching up to its earnings path"))).toBe(true);
  });

  it("never prints broken values", () => {
    const text = textOf(<TrajectoriesTab tdata={tdata} />);
    expect(text).not.toMatch(BROKEN_TEXT);
    expect(text).not.toContain("unavailable");
  });
});

describe("TrajectoriesTab: past years", () => {
  it("shows each start year's own 2026-27 pension, or says nothing changes", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const picker = screen.getByRole("group", { name: "Plan starts" });
    for (const g of tdata.history.groups) {
      const sy = g.switch_years;
      const label = sy.length > 1 ? `From April ${sy[0]} to ${sy.at(-1)}` : `From April ${sy[0]}`;
      fireEvent.click(within(picker).getByRole("button", { name: label }));
      if (g.changes_anything) {
        const y = String(tdata.history.model_years.at(-1));
        expect(screen.getByTestId("past-weekly").textContent).toContain(
          formatWeekly(g.model_years.counterfactual_weekly.new_state_pension[y]),
        );
      } else {
        expect(screen.getByTestId("past-no-difference")).toBeTruthy();
      }
    }
  });
});

describe("TrajectoriesTab: backtest", () => {
  it("lists every labelled method with its score", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const rows = within(screen.getByTestId("backtest-table")).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(3);
  });
});

describe("TrajectoriesTab fails closed", () => {
  it.each([
    ["trajectories", "The future paths are unavailable"],
    ["history", "The past-years comparison is unavailable"],
    ["backtest", "The backtest is unavailable"],
    ["policies", "The trajectory viewer is unavailable"],
  ])("without %s", (key, message) => {
    const text = textOf(<TrajectoriesTab tdata={copyWith(key, null, { remove: true })} />);
    expect(text).toContain(message);
    expect(text).not.toMatch(BROKEN_TEXT);
  });

  it("drops a path whose rate is written as a percentage", () => {
    const bad = copyWith(`trajectories.0.rates.burnham_2030.${FINAL}`, 3.7);
    expect(getTrajectories(bad).map((t) => t.id)).not.toContain(tdata.trajectories[0].id);
    expect(textOf(<TrajectoriesTab tdata={bad} />)).not.toMatch(BROKEN_TEXT);
  });

  it("drops a path with a missing saving", () => {
    const bad = copyWith(`trajectories.1.saving_bn.${FINAL}.net`, null, { remove: true });
    expect(getTrajectories(bad)).toHaveLength(tdata.trajectories.length - 1);
  });

  it("is unavailable when no data file is passed", () => {
    expect(textOf(<TrajectoriesTab tdata={null} />)).toContain("unavailable");
  });
});

describe("Dashboard wiring", () => {
  it("adds a Trajectories tab that renders the viewer", () => {
    render(<Dashboard data={realData} trajectories={tdata} />);
    fireEvent.click(screen.getByRole("tab", { name: "Trajectories" }));
    expect(screen.getByTestId("trajectories-tab")).toBeTruthy();
  });
});
