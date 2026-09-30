/**
 * Round axis ticks (steps of 1, 2, 2.5 or 5 times a power of ten) spanning min..max,
 * with at least a tenth of a step of room so no bar or line touches the axis edge.
 * `includeZero` keeps 0 in range (bars and cost differences); leave it off for levels.
 */
export function niceTicks(min, max, { includeZero = true, target = 5 } = {}) {
  let lo = includeZero ? Math.min(0, min) : min;
  let hi = includeZero ? Math.max(0, max) : max;
  if (lo === hi) {
    lo -= Math.abs(lo) * 0.1 || 1;
    hi += Math.abs(hi) * 0.1 || 1;
  }
  const raw = (hi - lo) / target;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((m) => m >= raw);
  let start = Math.floor(lo / step) * step;
  let end = Math.ceil(hi / step) * step;
  // Room at an edge the data reaches (zero is a baseline, not an edge to pad).
  if (lo !== 0 && lo - start < step * 0.1) start -= step;
  if (hi !== 0 && end - hi < step * 0.1) end += step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toFixed(10)) + 0);
  return ticks;
}

/**
 * Decimal places a tick formatter needs so every tick of the axis over these values prints distinctly and exactly
 * (a 2.5 step needs 1, a 0.25 step 2). `scale` converts axis units to printed units (e.g. 100 for a rate shown
 * as a percentage).
 */
export function axisDigits(values, options, scale = 1) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return 0;
  const ticks = niceTicks(Math.min(...finite), Math.max(...finite), options);
  const step = Math.abs((ticks[1] - ticks[0]) * scale);
  for (let d = 0; d <= 6; d += 1) {
    const scaled = step * 10 ** d;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-6) return d;
  }
  return 6;
}

/** Ticks and domain props for a Recharts YAxis over the given values. */
export function niceAxis(values, options) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return {};
  const ticks = niceTicks(Math.min(...finite), Math.max(...finite), options);
  return { ticks, domain: [ticks[0], ticks[ticks.length - 1]], interval: 0 };
}
