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

// Uprating rule colours — the triple lock (current policy) darkest, then
// lighter teal shades and a grey for the CPI link.
export const policyColors = {
  triple_lock: "#1D4044",   // primary-900
  double_lock: "#2C7A7B",   // primary-600
  earnings_link: "#38B2AC", // primary-400
  cpi_link: "#6B7280",      // gray-500
};

const FALLBACK_COLORS = ["#285E61", "#4FD1C5", "#9CA3AF", "#344054"];

export function colorFor(policyId, index = 0) {
  return policyColors[policyId] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}
