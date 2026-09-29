import { describe, expect, it } from "vitest";

import { getBreakdown } from "./dataHelpers";

const row = (age_band, mean, total) => ({ age_band, label: age_band, mean_change_gbp: mean, pct_income_change: 0, total_bn: total });
const data = (rows) => ({ central: { by_age_band: { cpi_link: rows } } });

describe("getBreakdown hides only groups with no change", () => {
  it("drops a zero under-66 row and reports it", () => {
    const b = getBreakdown(data([row("under_66", 0, 0), row("66_74", -120, -0.4)]), "age", "cpi_link");
    expect(b.rows.map((r) => r.label)).not.toContain(b.omitted[0]);
    expect(b.omitted).toHaveLength(1);
    expect(b.rows).toHaveLength(1);
  });

  it("keeps an under-66 row that changes", () => {
    const b = getBreakdown(data([row("under_66", -5, -0.01), row("66_74", -120, -0.4)]), "age", "cpi_link");
    expect(b.omitted).toHaveLength(0);
    expect(b.rows).toHaveLength(2);
  });
});
