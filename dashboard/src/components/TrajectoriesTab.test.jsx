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
import { fyLabel } from "../lib/dataHelpers";
import { formatBn, formatRate, formatWeekly } from "../lib/formatters";
import {
  bestCoverage,
  differenceNotes,
  getBacktest,
  getHistory,
  getTrajectories,
  flaggedRows,
  isFlagged,
  isFlaggedAnyYear,
  readTrajectory,
  replayDifferences,
  startYearsLabel,
} from "../lib/trajectoryHelpers";

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

function pick(label) {
  fireEvent.click(within(screen.getByRole("group", { name: "Path" })).getByRole("button", { name: label }));
}

describe("the results file", () => {
  it("has every trajectory valid for display, to 2039-40", () => {
    expect(getTrajectories(tdata)).toHaveLength(tdata.trajectories.length);
    expect(tdata.horizon.at(-1)).toBe(2039);
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
    expect(screen.getByTestId("card-gross").textContent).toContain(formatBn(tdata.trajectories[0].saving_bn[FINAL].gross, 2));
    expect(screen.getByTestId("card-gross").textContent).toContain(fyLabel(Number(FINAL)));
  });

  it.each(tdata.trajectories.map((t) => [t.id, t]))("shows %s's own figures when picked", (_, t) => {
    render(<TrajectoriesTab tdata={tdata} />);
    pick(t.label);
    expect(screen.getByTestId("card-gross").textContent).toContain(formatBn(t.saving_bn[FINAL].gross, 2));
    expect(screen.getByTestId("card-net").textContent).toContain(formatBn(t.saving_bn[FINAL].net, 2));
    expect(screen.getByTestId("card-weekly").textContent).toContain(formatWeekly(t.weekly.burnham_2030.new_state_pension[FINAL]));
    expect(screen.getByTestId("card-weekly").textContent).toContain(formatWeekly(t.weekly.triple_lock.new_state_pension[FINAL]));
    const notes = screen.getByTestId("trajectory-notes").textContent;
    const traj = readTrajectory(tdata, t);
    for (const n of differenceNotes(traj)) expect(notes).toContain(`April ${n.year}`);
    expect(screen.queryByTestId("largest-household-flag") !== null).toBe(isFlagged(traj));
    const earlier = flaggedRows(traj).filter((r) => r.year !== traj.rows.at(-1).year);
    expect(screen.queryByTestId("concentration-years") !== null).toBe(earlier.length > 0);
    for (const r of earlier) {
      expect(screen.getByTestId("concentration-years").textContent).toContain(`household record ${r.concentration.id}`);
    }
    expect(screen.getByTestId("trajectory-source").textContent).toContain(t.source);
  });

  it("says what moves with a path and what does not", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const text = screen.getByTestId("paths-explainer").textContent.replace(/\s+/g, " ");
    expect(text).toContain(`run to ${fyLabel(Number(FINAL))}`);
    expect(text).toContain("benefit rates, CPI-linked tax thresholds, earnings and the model's own triple lock follow the path");
    expect(text).toContain("rents and council tax do not follow it");
    expect(text).toContain("additional State Pension follows the model's own triple lock");
    expect(text).not.toContain("every benefit rate, threshold and income");
  });

  it("marks flagged paths in the table of all paths", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const rows = within(screen.getByTestId("all-paths-table")).getAllByRole("row").slice(1);
    const trajs = getTrajectories(tdata);
    rows.forEach((row, i) => {
      expect(row.getAttribute("data-flagged")).toBe(String(isFlaggedAnyYear(trajs[i])));
      expect(row.textContent.includes("flagged")).toBe(isFlaggedAnyYear(trajs[i]));
    });
  });

  it("explains a flagged household, including its share of the gross saving", () => {
    const i = 1;
    const bad = copyWith(`trajectories.${i}.largest_household.share_of_income_change`, 0.5);
    const lh = bad.trajectories[i].largest_household;
    render(<TrajectoriesTab tdata={bad} />);
    pick(bad.trajectories[i].label);
    const flag = screen.getByTestId("largest-household-flag").textContent.replace(/\s+/g, " ");
    expect(flag).toContain(`household record ${lh.household_id}`);
    expect(flag).toContain(`It accounts for ${formatBn(lh.gross_contribution_bn, 2)} of the gross saving`);
    expect(flag).toContain(`net saving would be ${formatBn(-lh.income_change_excluding_bn, 2)}`);
    expect(flag).not.toContain("does not depend on it");
    expect(within(screen.getByTestId("all-paths-table")).getAllByRole("row")[i + 1].textContent).toContain("flagged");
  });

  it("says the concentration check is unavailable when the record is missing", () => {
    const bad = copyWith("trajectories.1.largest_household", null, { remove: true });
    render(<TrajectoriesTab tdata={bad} />);
    pick(bad.trajectories[1].label);
    expect(screen.getByTestId("concentration-unavailable").textContent).toContain("unavailable");
    expect(screen.queryByTestId("largest-household-flag")).toBeNull();
    expect(within(screen.getByTestId("all-paths-table")).getAllByRole("row")[2].textContent).toContain("unavailable");
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
    expect(text).not.toContain("failed validation");
  });
});

describe("TrajectoriesTab: past years", () => {
  it("shows each start year's own pension, or says nothing changes", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const picker = screen.getByRole("group", { name: "Plan starts in" });
    const history = getHistory(tdata);
    for (const [k, g] of tdata.history.groups.entries()) {
      fireEvent.click(within(picker).getByRole("button", { name: startYearsLabel(g.switch_years) }));
      if (g.changes_anything) {
        const y = String(tdata.history.model_years.at(-1));
        const card = screen.getByTestId("past-weekly").textContent;
        expect(card).toContain(formatWeekly(g.model_years.counterfactual_weekly.new_state_pension[y]));
        expect(card).toContain(`Actual ${formatWeekly(g.model_years.actual_weekly.new_state_pension[y])}`);
        const ratio = history.groups[k].finalRatio;
        expect(ratio).toBe(g.level_ratio[y]);
        expect(card).toContain(ratio < 1 ? "lower" : "higher");
      } else {
        const text = screen.getByTestId("past-no-difference").textContent.replace(/\s+/g, " ");
        expect(text).toContain(`Had it started in ${startYearsLabel(g.switch_years)}`);
      }
    }
  });

  it("lists, from the file, the years the replayed triple lock differs from the rise paid", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const note = screen.getByTestId("past-note").textContent.replace(/\s+/g, " ");
    const diffs = replayDifferences(getHistory(tdata));
    expect(diffs).not.toBeNull();
    for (const d of diffs) expect(note).toContain(`April ${d.year} (paid ${formatRate(d.paid)}, rule ${formatRate(d.rule)})`);
    expect(note).toContain(`${diffs.length} of ${tdata.history.years.length} years`);
  });
});

describe("TrajectoriesTab: backtest", () => {
  it("reports both treatments of April 2022 from the file", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const text = screen.getByTestId("backtest-text").textContent.replace(/\s+/g, " ");
    const bt = getBacktest(tdata);
    expect(text).toContain(`We scored ${bt.published.ranges.length} ways of putting a range`);
    expect(text).toContain(`the best placed ${bestCoverage(bt.published).best} of ${bt.published.nOrigins}`);
    expect(text).toContain(`best placed ${bestCoverage(bt.suspended).best} of ${bt.suspended.nOrigins}`);
    expect(text).toContain(formatRate(bt.published.april2022.earnings));
    expect(text).toContain("this tab shows paths rather than odds");
    expect(text).not.toContain("the dashboard shows");
    expect(text).not.toContain("only information available at the time");
    for (const o of bestCoverage(bt.suspended).missed) expect(text).toContain(o.replace(/ EFO$/, ""));
  });

  it("labels small ensembles' coverage as their min-max range", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const small = getBacktest(tdata).published.ranges.filter((r) => r.smallEnsemble);
    expect(small.length).toBeGreaterThan(0);
    expect(screen.getByTestId("backtest-small-ensembles").textContent).toContain("full range of those paths");
    const table = screen.getByTestId("backtest-table").textContent;
    for (const r of small) expect(table).toContain(`${r.minDraws}–${r.maxDraws} paths: min–max range`);
  });

  it("lists every labelled method, the point forecast as n/a", () => {
    render(<TrajectoriesTab tdata={tdata} />);
    const rows = within(screen.getByTestId("backtest-table")).getAllByRole("row").slice(1);
    const bt = getBacktest(tdata);
    expect(rows).toHaveLength(bt.published.rows.length);
    const point = rows.find((r) => r.textContent.includes("OBR forecast alone"));
    expect(point.textContent).toContain("n/a");
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

  it("drops a path whose rate is written as a percentage, and says so", () => {
    const bad = copyWith(`trajectories.0.rates.burnham_2030.${FINAL}`, 3.7);
    expect(getTrajectories(bad).map((t) => t.id)).not.toContain(tdata.trajectories[0].id);
    const text = textOf(<TrajectoriesTab tdata={bad} />);
    expect(text).not.toMatch(BROKEN_TEXT);
    expect(text).toContain("One path in the results file failed validation and is not shown");
  });

  it("drops a path with a missing saving", () => {
    const bad = copyWith(`trajectories.1.saving_bn.${FINAL}.net`, null, { remove: true });
    expect(getTrajectories(bad)).toHaveLength(tdata.trajectories.length - 1);
  });

  it("is unavailable with only the point forecast in the backtest", () => {
    const bad = structuredClone(tdata);
    for (const block of Object.values(bad.backtest.statutory.treatments)) {
      block.chronological.methods = { obr_point: block.chronological.methods.obr_point };
    }
    const text = textOf(<TrajectoriesTab tdata={bad} />);
    expect(text).toContain("The backtest is unavailable");
    expect(text).not.toMatch(/-?Infinity/);
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
