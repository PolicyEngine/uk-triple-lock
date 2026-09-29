import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// A stable instance, as Next.js returns between navigations.
const searchParams = new URLSearchParams();
const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

import Dashboard from "./Dashboard";
import { BROKEN_TEXT, fixture, mutate, realData } from "../lib/testUtils";

const TABS = ["Budget impact", "Who's affected", "Uncertainty", "Methodology"];

describe("sample banner", () => {
  it("is shown on every tab when the file is marked sample", () => {
    expect(fixture.sample).toBe(true);
    render(<Dashboard data={fixture} />);
    for (const tab of TABS) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(screen.getByTestId("sample-banner").textContent).toContain("Sample data — not results");
    }
  });

  it("is hidden when sample is false", () => {
    render(<Dashboard data={mutate("sample", false)} />);
    expect(screen.queryByTestId("sample-banner")).toBeNull();
  });

  it("is hidden when the key is absent", () => {
    render(<Dashboard data={mutate("sample", null, { remove: true })} />);
    expect(screen.queryByTestId("sample-banner")).toBeNull();
  });

  it("is not triggered by a truthy non-boolean", () => {
    render(<Dashboard data={mutate("sample", "false")} />);
    expect(screen.queryByTestId("sample-banner")).toBeNull();
  });

  it("follows the real results file's own flag", () => {
    render(<Dashboard data={realData} />);
    expect(screen.queryByTestId("sample-banner") !== null).toBe(realData.sample === true);
  });
});

describe("Dashboard", () => {
  it("renders every tab without broken text", () => {
    const { container } = render(<Dashboard data={fixture} />);
    for (const tab of TABS) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(screen.getByRole("tab", { name: tab }).getAttribute("aria-selected")).toBe("true");
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab).not.toMatch(BROKEN_TEXT);
      expect(text, tab).not.toContain("unavailable");
    }
  });

  it("names only the breakdowns present in the intro", () => {
    const text = (d) => {
      const { container, unmount } = render(<Dashboard data={d} />);
      const t = container.textContent.replace(/\s+/g, " ");
      unmount();
      return t;
    };
    expect(text(fixture)).toContain("the change in household income by income, region, household type and tenure.");
    const onlyRegion = structuredClone(fixture);
    for (const k of ["by_quintile", "by_hh_type", "by_tenure"]) delete onlyRegion.central[k];
    expect(text(onlyRegion)).toContain("the change in household income by region.");
    expect(text(fixture).toLowerCase()).not.toContain("constituenc");
  });

  it("pins the versions from the file in the footer", () => {
    render(<Dashboard data={fixture} />);
    const lines = screen.getAllByTestId("replication").map((n) => n.textContent);
    const p = fixture.provenance;
    expect(lines[lines.length - 1]).toContain(
      `policyengine.py ${p.packages.policyengine} on ${p.dataset.name} (${p.dataset.data_build})`,
    );
  });

  it("renders every tab without broken text when the file is empty", () => {
    const { container } = render(<Dashboard data={{}} />);
    for (const tab of TABS) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      const text = container.textContent.replace(/\s+/g, " ");
      expect(text, tab).not.toMatch(BROKEN_TEXT);
      expect(text, tab).toContain("unavailable");
    }
  });
});
