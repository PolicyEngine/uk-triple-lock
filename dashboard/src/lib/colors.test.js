import { describe, expect, it } from "vitest";

import { colorFor, policyColors } from "./colors";

describe("colorFor", () => {
  it("returns the assigned colour for each known policy", () => {
    for (const [id, colour] of Object.entries(policyColors)) expect(colorFor(id)).toBe(colour);
  });

  it("throws on an unknown policy id instead of guessing", () => {
    expect(() => colorFor("mystery_rule")).toThrow(/No colour assigned/);
  });
});
