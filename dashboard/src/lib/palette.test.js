// @vitest-environment node
/**
 * Every data mark takes its colour from SERIES in colors.js, so the same thing has the same colour on every tab. A
 * raw hex colour in a component would bypass that; this fails on one. The PolicyEngine site header and footer carry
 * the site's own brand colours and are not data marks.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { SERIES, policyColors } from "./colors";

const DIR = path.resolve(__dirname, "../components");
const SITE_CHROME = new Set(["PolicyEngineHeader.jsx", "PolicyEngineFooter.jsx"]);
// A hex colour as a string literal: "#2C7A7B", '#fff', `#C9A9A6`. Issue numbers in text (#538) are not quoted alone.
const HEX = /["'`]#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})["'`]/g;

describe("the colour palette", () => {
  const files = readdirSync(DIR).filter((f) => f.endsWith(".jsx") && !f.includes(".test.") && !SITE_CHROME.has(f));

  it.each(files)("%s has no raw hex colour", (file) => {
    const found = readFileSync(path.join(DIR, file), "utf8").match(HEX) ?? [];
    expect(found, `${file}: use SERIES or colors from lib/colors.js`).toEqual([]);
  });

  it("gives each rule the SERIES colour", () => {
    expect(policyColors).toEqual({ triple_lock: SERIES.tripleLock, burnham_2030: SERIES.burnham });
  });

  it("keeps the rules, gross and net, and the three inputs distinguishable", () => {
    const sets = [["tripleLock", "burnham"], ["gross", "net"], ["cpi", "earnings", "floor"], ["bandOuter", "bandInner"]];
    for (const keys of sets) expect(new Set(keys.map((k) => SERIES[k])).size, keys.join("/")).toBe(keys.length);
  });
});
