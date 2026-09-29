"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors, colorFor } from "../lib/colors";
import {
  BASELINE_POLICY,
  fyLabel,
  getAlternatives,
  getCostInYear,
  getNetRatio,
  getCostQuantiles,
  getFinalYear,
  getCostSeries,
  getHorizon,
  getBaseYearWeekly,
  getPolicyDefinition,
  getPolicies,
  getUprating,
  getWeeklyPension,
  earningsAtLeastCpi,
  hasLargestHousehold,
  upratingMatches,
} from "../lib/dataHelpers";
import { formatBn, formatRate, formatWeekly } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import BenchmarksTable, { BenchmarkLinks } from "./Benchmarks";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

export const HEADLINE_YEARS = [2030, 2034];

const BASIS_OPTIONS = [
  { id: "gross", label: "Gross" },
  { id: "net", label: "Net" },
];


function HeadlineCards({ data, alternatives, basis }) {
  const year = getFinalYear(data);
  const cards = alternatives.map((alt) => {
    const q = getCostQuantiles(data, alt.id);
    const central = getCostInYear(data, alt.id, basis, year);
    const scale = basis === "net" ? getNetRatio(data, alt.id) : 1;
    return { alt, q, central, scale };
  });
  const usable = cards.filter((c) => c.q && c.scale !== null);
  if (!year || usable.length === 0) return <Unavailable what="The range of savings" />;
  const max = Math.max(...usable.map((c) => c.q.p90 * c.scale), ...usable.map((c) => (c.central !== null ? -c.central : 0)));
  const pos = (v) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ alt, q, central, scale }) => (
        <div className="metric-card" key={alt.id} data-testid={`headline-${alt.id}`}>
          <p className="eyebrow text-slate-500">{alt.label}</p>
          {alt.rule ? <p className="mt-1 text-xs text-slate-500">Uprating: {alt.rule}</p> : null}
          {q && scale !== null ? (
            <>
              <p className="mt-4 text-sm text-slate-500">Most likely saving, {fyLabel(year)}</p>
              <p className="text-3xl font-semibold tracking-tight text-slate-900" data-testid={`median-${alt.id}`}>
                {formatBn(q.p50 * scale)}
              </p>
              <div className="relative mt-3 h-3 rounded bg-slate-100" aria-hidden="true">
                <div
                  className="absolute top-0 h-full rounded"
                  style={{
                    left: pos(q.p10 * scale),
                    width: `calc(${pos(q.p90 * scale)} - ${pos(q.p10 * scale)})`,
                    backgroundColor: colorFor(alt.id),
                    opacity: 0.45,
                  }}
                />
                <div className="absolute -top-0.5 h-4 w-[3px] bg-slate-900" style={{ left: pos(q.p50 * scale) }} />
                {central !== null ? (
                  <div
                    className="absolute top-0 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-slate-900 bg-white"
                    style={{ left: pos(-central) }}
                  />
                ) : null}
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600" data-testid={`range-words-${alt.id}`}>
                1 in 10 chance below {formatBn(q.p10 * scale)}, 1 in 10 above {formatBn(q.p90 * scale)}. On
                the forecast alone: {central !== null ? formatBn(-central) : "unavailable"}.
              </p>
            </>
          ) : (
            <Unavailable what={`The range of savings for ${alt.label}`} />
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * When the double lock and earnings link uprate identically their lines would sit exactly on
 * top of each other; keep one line and say so in its label.
 */
function mergeIdentical(data, series) {
  const double = series.find((s) => s.id === "double_lock");
  const earnings = series.find((s) => s.id === "earnings_link");
  if (
    !double ||
    !earnings ||
    upratingMatches(data, "double_lock", "earnings_link") !== true ||
    !double.values.every((v, i) => v === earnings.values[i])
  ) {
    return series;
  }
  return series
    .filter((s) => s.id !== "double_lock")
    .map((s) => (s.id === "earnings_link" ? { ...s, label: `${double.label} = ${earnings.label} (same on this forecast)` } : s));
}

function CostChart({ data, baseline, alternatives, basis }) {
  const horizon = getHorizon(data);
  let series = alternatives.map((alt) => ({ ...alt, values: getCostSeries(data, alt.id, basis) }));
  if (!horizon || series.some((s) => !s.values)) {
    return <Unavailable what="The annual cost chart" />;
  }
  series = mergeIdentical(data, series);
  const rows = horizon.map((year, i) => {
    const row = { year: fyLabel(year) };
    for (const s of series) row[s.id] = s.values[i];
    return row;
  });
  return (
    <>
      <div className="h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="year" tick={AXIS_STYLE} />
            <YAxis
              tick={AXIS_STYLE}
              tickFormatter={(v) => formatBn(v, 0)}
              {...niceAxis(series.flatMap((s) => s.values))}
              label={{ value: "£ billion vs triple lock", angle: -90, position: "insideLeft", style: AXIS_STYLE }}
            />
            <ReferenceLine y={0} stroke={colorFor(BASELINE_POLICY)} strokeDasharray="4 4" />
            <Tooltip content={<CustomTooltip formatter={(v) => formatBn(v, 2)} />} />
            {series.map((s) => (
              <Line
                key={s.id}
                type="monotone"
                dataKey={s.id}
                name={s.label}
                stroke={colorFor(s.id)}
                strokeWidth={2.5}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches
        items={[
          { label: `${baseline.label} (zero line)`, color: colorFor(BASELINE_POLICY), dashed: true },
          ...series.map((s) => ({ label: s.label, color: colorFor(s.id) })),
        ]}
      />
      <ChartLogo />
    </>
  );
}

function RulePicker({ label, value, other, series, onChange, testId }) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label} data-testid={testId}>
      <span className="w-16 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {series.map((s) => {
        const active = s.id === value;
        return (
          <button
            key={s.id}
            type="button"
            aria-pressed={active}
            disabled={s.id === other}
            onClick={() => onChange(s.id)}
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition ${
              active
                ? "border-slate-800 bg-slate-800 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:border-slate-500"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colorFor(s.id) }} />
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

/** Line chart of one per-year series for two rules the reader picks. */
function CompareChart({ data, policies, getter, format, tickFormat, yLabel, what, gapText, testPrefix }) {
  const horizon = getHorizon(data);
  // Open on the announced plan against current policy, when the file has it.
  const [pair, setPair] = useState([
    "triple_lock",
    policies.some((p) => p.id === "burnham_2030") ? "burnham_2030" : policies[policies.length - 1].id,
  ]);
  const series = policies.map((p) => ({ ...p, values: getter(data, p.id) }));
  if (!horizon || series.some((s) => !s.values)) {
    return <Unavailable what={what} />;
  }
  const shown = pair.map((id) => series.find((s) => s.id === id)).filter(Boolean);
  const rows = horizon.map((year, i) => {
    const row = { year: fyLabel(year) };
    for (const s of shown) row[s.id] = s.values[i];
    return row;
  });
  return (
    <>
      <div className="space-y-2" data-testid={`${testPrefix}-chooser`}>
        <RulePicker
          label="Compare"
          value={pair[0]}
          other={pair[1]}
          series={series}
          onChange={(v) => setPair((p) => [v, p[1]])}
          testId={`${testPrefix}-rule-0`}
        />
        <RulePicker
          label="With"
          value={pair[1]}
          other={pair[0]}
          series={series}
          onChange={(v) => setPair((p) => [p[0], v])}
          testId={`${testPrefix}-rule-1`}
        />
      </div>
      <div className="mt-4 h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="year" tick={AXIS_STYLE} />
            <YAxis
              tick={AXIS_STYLE}
              tickFormatter={tickFormat}
              {...niceAxis(shown.flatMap((s) => s.values), { includeZero: false })}
              label={{ value: yLabel, angle: -90, position: "insideLeft", style: AXIS_STYLE }}
            />
            <Tooltip content={<CustomTooltip formatter={format} />} />
            {shown.map((s, i) => (
              <Line
                key={s.id}
                type="monotone"
                dataKey={s.id}
                name={s.label}
                stroke={colorFor(s.id)}
                strokeWidth={2.5}
                strokeDasharray={i === 1 ? "6 4" : undefined}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches items={shown.map((s, i) => ({ label: s.label, color: colorFor(s.id), dashed: i === 1 }))} />
      {gapText && shown.length === 2 ? (
        <p className="mt-2 text-sm text-slate-600" data-testid={`${testPrefix}-gap`}>
          {gapText(shown[0], shown[1], horizon)}
        </p>
      ) : null}
      <ChartLogo />
    </>
  );
}

function weeklyGap(a, b, horizon) {
  const last = horizon.length - 1;
  const gap = a.values[last] - b.values[last];
  return `In ${fyLabel(horizon[last])}, ${a.label} pays ${formatWeekly(Math.abs(gap))} a week ${
    gap >= 0 ? "more" : "less"
  } than ${b.label}.`;
}

function RuleTable({ data, policies, getter, format, caption }) {
  const horizon = getHorizon(data);
  const series = policies.map((p) => ({ ...p, values: getter(data, p.id) }));
  if (!horizon || series.some((s) => !s.values)) {
    return <Unavailable what={caption} />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>Year</th>
            {series.map((s) => (
              <th key={s.id}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {horizon.map((year, i) => (
            <tr key={year}>
              <td>{fyLabel(year)}</td>
              {series.map((s) => (
                <td key={s.id}>{format(s.values[i])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompositionCaveat({ data }) {
  const def = getPolicyDefinition(data);
  return (
    <p className="caveat-card px-4 py-2 text-sm" data-testid="composition-caveat">
      <strong>Caveats:</strong> central-forecast figures, with no uncertainty range (see
      Uncertainty).
      {def ? (
        <>
          {" "}
          The speech gave no formula: if the pension were restored to the earnings path only every
          five years, the Burnham plan would save {formatBn(-def.review, 1)} in 2034-35, not{" "}
          {formatBn(-def.annual, 1)}.
        </>
      ) : null}{" "}
      Frozen survey ages and PolicyEngine&apos;s growth path for 2031–33 are covered in
      Methodology.
    </p>
  );
}

function MatchNote({ data }) {
  const same = upratingMatches(data, "double_lock", "earnings_link");
  const earningsHigher = earningsAtLeastCpi(data);
  if (same !== true || earningsHigher !== true) return null;
  return (
    <>
      {" "}
      The double lock and earnings link match here, as forecast earnings growth never falls below
      CPI.
    </>
  );
}

function LumpyNote({ data }) {
  if (!hasLargestHousehold(data)) return null;
  return (
    <p>
      Net figures can change in steps from one year to the next. One survey household stands for
      many homes, and it can become eligible for Housing Benefit when its pension changes by a few
      pounds. The Methodology tab shows how much the household with the most effect adds each year.
    </p>
  );
}

export default function CostTab({ data }) {
  const [basis, setBasis] = useState("gross");
  const policies = getPolicies(data);
  const alternatives = getAlternatives(data);
  const baseYear = getBaseYearWeekly(data);

  if (!policies || !alternatives) {
    return <Unavailable what="The list of uprating rules" />;
  }
  const baseline = policies[0];

  return (
    <div className="space-y-8">
      <section className="section-card">
        <SectionHeading title="Saving compared with the triple lock" />
        <Explainer>
          <p>
            How much each rule would save the government compared with the triple lock in{" "}
            {fyLabel(getFinalYear(data))}, across 20,000 simulated paths of inflation and earnings. The
            bar covers the middle 80% of outcomes, the line is the most likely saving and the dot is the
            figure on the OBR forecast alone. <strong>Gross</strong>{" "}is State Pension spending;{" "}
            <strong>net</strong>{" "}also counts knock-on changes to other benefits and tax, scaled from
            full-model runs (about 70% of gross).
            <MatchNote data={data} />
          </p>
        </Explainer>
        <div className="mb-5">
          <ToggleGroup options={BASIS_OPTIONS} value={basis} onChange={setBasis} label="Cost basis" />
        </div>
        <HeadlineCards data={data} alternatives={alternatives} basis={basis} />
        <div className="mt-5">
          <CompositionCaveat data={data} />
        </div>
      </section>

      <section className="section-card">
        <SectionHeading title="Annual cost compared with the triple lock" />
        <Explainer>
          <p>
            Each line shows one rule&apos;s {basis}{" "}cost minus the triple lock&apos;s, each year, in
            £ billion. Below zero means the rule is cheaper. The dashed line at zero is the triple
            lock. Use the Gross/Net buttons above to switch.
          </p>
          {basis === "net" ? <LumpyNote data={data} /> : null}
        </Explainer>
        <CostChart data={data} baseline={baseline} alternatives={alternatives} basis={basis} />
      </section>

      <section className="section-card">
        <Expandable title="Full new State Pension, £ a week" testId="section-weekly">
        <Explainer>
          <p>
            The full weekly rate of the new State Pension in each year under each rule
            {baseYear ? `, starting from £${baseYear.amount.toFixed(2)} in ${fyLabel(baseYear.year)}` : ""}.
            People on the older basic State Pension, or with fewer qualifying years, get less, but
            their pension rises by the same percentage.
          </p>
        </Explainer>
        <CompareChart
          data={data}
          policies={policies}
          getter={getWeeklyPension}
          format={formatWeekly}
          tickFormat={(v) => `£${Math.round(v)}`}
          yLabel="£ a week"
          what="The weekly State Pension chart"
          gapText={weeklyGap}
          testPrefix="weekly"
        />
        <div className="mt-4">
          <Expandable title="Table: full new State Pension by year" testId="weekly-table">
            <RuleTable
              data={data}
              policies={policies}
              getter={getWeeklyPension}
              format={formatWeekly}
              caption="The weekly State Pension table"
            />
          </Expandable>
        </div>
              </Expandable>
      </section>

      <section className="section-card">
        <Expandable title="Uprating each year" testId="section-uprating">
        <Explainer>
          <p>
            The percentage rise each April under each rule (OBR forecast to 2030, PolicyEngine&apos;s
            long-run path after). The row for
            a year is the rise that takes effect in April of that year. The triple lock takes the
            highest of CPI inflation, earnings growth and 2.5%.
          </p>
        </Explainer>
        <CompareChart
          data={data}
          policies={policies}
          getter={getUprating}
          format={(v) => formatRate(v)}
          tickFormat={(v) => formatRate(v)}
          yLabel="Rise each April"
          what="The uprating chart"
          testPrefix="uprating"
        />
        <div className="mt-4">
          <Expandable title="Table: uprating by year" testId="uprating-table">
            <RuleTable
              data={data}
              policies={policies}
              getter={getUprating}
              format={(v) => formatRate(v)}
              caption="The uprating table"
            />
          </Expandable>
        </div>
              </Expandable>
      </section>

      <section className="section-card">
        <Expandable title="How this compares" testId="compare-central">
          <Explainer>
            <p>
              Other published estimates of the same costs, with our closest figure. They often use
              a different forecast, year or definition, so the last columns say how close the
              comparison is.
              <BenchmarkPrefix data={data} />
            </p>
          </Explainer>
          <BenchmarksTable data={data} scope="central" />
        </Expandable>
      </section>
    </div>
  );
}

function BenchmarkPrefix({ data }) {
  const links = BenchmarkLinks({ data, scope: "central" });
  if (!links) return null;
  return <> Sources compared: {links}.</>;
}
