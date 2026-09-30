import { isNum, UNAVAILABLE } from "./dataHelpers";

// Every formatter returns "unavailable" for a missing or non-finite value, so
// no chart label, card or table cell can print "NaN" or "£bn".

export function formatCurrency(value) {
  if (!isNum(value)) return UNAVAILABLE;
  const rounded = Math.round(value);
  const sign = rounded < 0 ? "-" : "";
  return `${sign}£${Math.abs(rounded).toLocaleString("en-GB")}`;
}

export function formatBn(value, digits = 1) {
  if (!isNum(value)) return UNAVAILABLE;
  const fixed = Math.abs(value).toFixed(digits);
  const sign = value < 0 && Number(fixed) !== 0 ? "-" : "";
  return `${sign}£${fixed}bn`;
}

export function formatPct(value, digits = 1) {
  if (!isNum(value)) return UNAVAILABLE;
  // No "-0.0%": a small negative that rounds to zero prints as zero.
  const v = Number(Math.abs(value).toFixed(digits)) === 0 ? 0 : value;
  return `${v.toFixed(digits)}%`;
}

/** A change in percentage points, signed, with no "-0.0". */
export function formatPoints(value, digits = 1) {
  if (!isNum(value)) return UNAVAILABLE;
  const v = Number(Math.abs(value).toFixed(digits)) === 0 ? 0 : value;
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

/** 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st... */
export function ordinal(n) {
  if (!Number.isInteger(n)) return UNAVAILABLE;
  const mod100 = n % 100;
  const suffix = mod100 >= 10 && mod100 <= 20 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th";
  return `${n}${suffix}`;
}

/** A fraction (0.025) as a percentage ("2.5%"). */
export function formatRate(value, digits = 1) {
  if (!isNum(value)) return UNAVAILABLE;
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatWeekly(value) {
  if (!isNum(value)) return UNAVAILABLE;
  return `£${value.toFixed(2)}`;
}

export function formatIndex(value) {
  if (!isNum(value)) return UNAVAILABLE;
  return value.toFixed(3);
}

export function formatCount(value) {
  if (!isNum(value)) return UNAVAILABLE;
  return value.toLocaleString("en-GB");
}

/**
 * A cost relative to the triple lock (negative = saving) as a phrase:
 * "£0.6bn saving", "£0.6bn extra cost" or "No difference".
 */
export function describeCostVsTripleLock(value, digits = 1) {
  if (!isNum(value)) return UNAVAILABLE;
  if (Number(Math.abs(value).toFixed(digits)) === 0) return "No difference";
  return value < 0
    ? `${formatBn(-value, digits)} saving`
    : `${formatBn(value, digits)} extra cost`;
}
