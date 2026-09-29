import { render } from "@testing-library/react";

import fixture from "../test/fixtures/sample_results.json";
import realData from "../../public/data/triple_lock_results.json";

export { fixture, realData };

/** Text a user would see, whitespace collapsed. */
export function textOf(element) {
  const { container, unmount } = render(element);
  const text = container.textContent.replace(/\s+/g, " ");
  unmount();
  return text;
}

/** Deep copy of the fixture with one dotted path set (or deleted). */
export function mutate(path, value, { remove = false } = {}) {
  const copy = structuredClone(fixture);
  const parts = path.split(".");
  let node = copy;
  for (const part of parts.slice(0, -1)) node = node[part];
  const last = parts[parts.length - 1];
  if (remove) delete node[last];
  else node[last] = value;
  return copy;
}

// Values a stale or partial results file could carry in place of a number.
export const BAD_VALUES = [undefined, null, "x", Number.NaN];

// Text that must never reach the page, whatever the data.
// "£bn" alone is a legitimate unit label (e.g. the pipeline's basis note), so
// it is flagged only where a formatter would have printed a number.
export const BROKEN_TEXT =
  /NaN|undefined|Infinity|\[object|£-?\.|£bn (saving|extra)|(Median|to|range|is|below|above) £bn/;

export const fy = (year) => `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
export const bn1 = (v) => `£${Math.abs(v).toFixed(1)}bn`;

// Bad values for text fields ("x" is a valid string).
export const BAD_TEXT_VALUES = [undefined, null, "", "   ", 42];
