/**
 * Design tokens — inlined from @policyengine/ui-kit/legacy/tokens/colors
 * to avoid ESM bundling issues with Next.js.
 *
 * Palette: grays + dark green/teal only.
 */
export const colors = {
  primary: {
    50: "#E6FFFA",
    100: "#B2F5EA",
    200: "#81E6D9",
    300: "#4FD1C5",
    400: "#38B2AC",
    500: "#319795",
    600: "#2C7A7B",
    700: "#285E61",
    800: "#234E52",
    900: "#1D4044",
  },
  gray: {
    50: "#F9FAFB",
    100: "#F2F4F7",
    200: "#E2E8F0",
    300: "#D1D5DB",
    400: "#9CA3AF",
    500: "#6B7280",
    600: "#4B5563",
    700: "#344054",
    800: "#1F2937",
    900: "#101828",
  },
  border: {
    light: "#E2E8F0",
    medium: "#CBD5E1",
    dark: "#94A3B8",
  },
};

/** White, for marks drawn on top of a filled colour. */
export const WHITE = "#FFFFFF";

/**
 * The one meaning-to-colour map every chart, card bar, dot, segment, legend swatch and tooltip swatch uses, so the
 * same thing has the same colour on every tab. Lines that the legend marks as dashed or dotted take their dash from
 * the chart; the colour comes from here.
 */
export const SERIES = {
  tripleLock: colors.primary[900], // triple lock (current law): darkest teal
  burnham: colors.primary[600], //    the Burnham plan: mid teal
  gross: colors.primary[800], //      gross saving (State Pension spending): dark teal
  net: colors.primary[300], //        net saving (after tax and benefits): light teal
  earnings: colors.primary[700], //   earnings growth, or a path that follows earnings alone: dark teal
  cpi: "#D97706", //                  CPI, or a path that follows prices alone: amber (distinct from teal in hue and for colour-blind readers)
  floor: colors.gray[400], //         the 2.5% floor: pale grey (dashed as a line)
  bandOuter: colors.primary[200], //  middle 80% of paths
  bandInner: colors.primary[400], //  middle 50% of paths
  average: colors.primary[900], //    average across paths (solid)
  median: colors.primary[700], //     median path (dotted)
  central: colors.gray[500], //       the OBR's central forecast (dashed)
  offset: "#C9A9A6", //               what shrinks a saving (extra benefits, less tax): muted warm
  gain: colors.primary[500], //       what adds to a saving
  highlight: colors.primary[700], //  the selected or hovered mark
  error: colors.gray[800], //         Monte Carlo error whiskers
  muted: colors.gray[200], //         empty cells (unfilled squares, unselected)
  axis: colors.gray[400], //          zero lines and reference lines
};

// Uprating rule colours, from SERIES: the triple lock (current law) darkest.
export const policyColors = {
  triple_lock: SERIES.tripleLock,
  burnham_2030: SERIES.burnham,
};

/** Colour for a policy id. Throws on an id with no assigned colour. */
export function colorFor(policyId) {
  if (!Object.hasOwn(policyColors, policyId)) {
    throw new Error(`No colour assigned for policy "${policyId}"`);
  }
  return policyColors[policyId];
}
