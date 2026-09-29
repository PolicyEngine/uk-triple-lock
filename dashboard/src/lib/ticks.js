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

/** Ticks and domain props for a Recharts YAxis over the given values. */
export function niceAxis(values, options) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return {};
  const ticks = niceTicks(Math.min(...finite), Math.max(...finite), options);
  return { ticks, domain: [ticks[0], ticks[ticks.length - 1]], interval: 0 };
}
