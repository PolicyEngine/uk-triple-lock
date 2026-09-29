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
  getCostSeries,
  getHorizon,
  getBaseYearWeekly,
  getCompositionEffect,
  getLargestContribution,
  getLateHorizon,
  getPolicies,
  getUprating,
  getWeeklyPension,
  earningsAtLeastCpi,
  hasLargestHousehold,
  upratingMatches,
} from "../lib/dataHelpers";
import { describeCostVsTripleLock, formatBn, formatPct, formatRate, formatWeekly } from "../lib/formatters";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import BenchmarksTable, { BenchmarkLinks } from "./Benchmarks";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

export const HEADLINE_YEARS = [2029, 2034];

const BASIS_OPTIONS = [
  { id: "gross", label: "Gross" },
  { id: "net", label: "Net" },
];


function HeadlineCards({ data, alternatives, basis }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {alternatives.map((alt) => (
        <div className="metric-card" key={alt.id} data-testid={`headline-${alt.id}`}>
          <p className="eyebrow text-slate-500">{alt.label}</p>
          {alt.rule ? <p className="mt-1 text-xs text-slate-500">Uprating: {alt.rule}</p> : null}
          <dl className="mt-4 space-y-3">
            {HEADLINE_YEARS.map((year) => (
              <div key={year}>
                <dt className="text-sm text-slate-500">{fyLabel(year)}</dt>
                <dd className="text-2xl font-semibold tracking-tight text-slate-900">
                  {describeCostVsTripleLock(getCostInYear(data, alt.id, basis, year))}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function CostChart({ data, baseline, alternatives, basis }) {
  const horizon = getHorizon(data);
  let series = alternatives.map((alt) => ({ ...alt, values: getCostSeries(data, alt.id, basis) }));
  if (!horizon || series.some((s) => !s.values)) {
    return <Unavailable what="The annual cost chart" />;
  }
  // When the double lock and earnings link uprate identically, their lines would sit exactly on
  // top of each other; draw one line and say so in its label.
  const double = series.find((s) => s.id === "double_lock");
  const earnings = series.find((s) => s.id === "earnings_link");
  if (
    double &&
    earnings &&
    upratingMatches(data, "double_lock", "earnings_link") === true &&
    double.values.every((v, i) => v === earnings.values[i])
  ) {
    series = series
      .filter((s) => s.id !== "double_lock")
      .map((s) =>
        s.id === "earnings_link"
          ? { ...s, label: `${double.label} = ${earnings.label} (same on this forecast)` }
          : s,
      );
  }
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
  const [pair, setPair] = useState(["triple_lock", "cpi_link"]);
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
      <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3" data-testid={`${testPrefix}-chooser`}>
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
              domain={["auto", "auto"]}
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

function NetAdjustedChart({ data, alternatives }) {
  const horizon = getHorizon(data);
  if (!horizon) return <Unavailable what="The net cost chart" />;
  const series = alternatives.map((alt) => ({
    ...alt,
    values: horizon.map((y) => getLargestContribution(data, alt.id, y)),
  }));
  if (series.some((s) => s.values.some((v) => v === null))) return <Unavailable what="The net cost chart" />;
  const rows = horizon.map((y, i) => {
    const row = { year: fyLabel(y) };
    for (const s of series) row[s.id] = s.values[i];
    return row;
  });
  return (
    <div data-testid="net-adjusted">
      <div className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="year" tick={AXIS_STYLE} />
            <YAxis
              tick={AXIS_STYLE}
              tickFormatter={(v) => formatBn(v, 1)}
              label={{ value: "£ billion added to net", angle: -90, position: "insideLeft", style: AXIS_STYLE }}
            />
            <ReferenceLine y={0} stroke={colors.gray[400]} />
            <Tooltip content={<CustomTooltip formatter={(v) => formatBn(v, 2)} />} />
            {series.map((s) => (
              <Line key={s.id} type="monotone" dataKey={s.id} name={s.label} stroke={colorFor(s.id)} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches items={series.map((s) => ({ label: s.label, color: colorFor(s.id) }))} />
      <ChartLogo />
    </div>
  );
}

function LargestNote({ data, alternatives }) {
  const year = HEADLINE_YEARS[0];
  const found = alternatives
    .map((alt) => ({ alt, v: getLargestContribution(data, alt.id, year) }))
    .filter((x) => x.v !== null);
  if (found.length === 0) return null;
  const top = found.reduce((a, b) => (Math.abs(b.v) > Math.abs(a.v) ? b : a));
  return (
    <p data-testid="largest-note">
      For example, one survey household adds {formatBn(top.v, 1)} to the {top.alt.label} net figure
      in {fyLabel(year)}.
    </p>
  );
}

function CompositionCaveat({ data }) {
  const effect = getCompositionEffect(data);
  if (!effect) return <Unavailable what="The ageing caveat (composition effect)" />;
  const late = getLateHorizon(data, "cpi_link");
  return (
    <p className="caveat-card px-4 py-2 text-sm" data-testid="composition-caveat">
      <strong>Caveats:</strong> survey ages are held fixed, so from 2033-34 every pensioner is on the
      new State Pension, and each 2034-35 cost is about {formatPct(effect.pct, 0)} above a scenario
      that holds the 2027-28 pensioner mix fixed.
      {late ? (
        <>
          {" "}
          Growth for 2031–33 is PolicyEngine&apos;s long-run path; with the OBR&apos;s long-term
          earnings growth instead, the 2034-35 gross saving from a CPI link is {formatBn(-late.obr, 1)}{" "}
          instead of {formatBn(-late.central, 1)}.
        </>
      ) : null}{" "}
      The Methodology tab explains both.
    </p>
  );
}

function MatchNote({ data }) {
  const same = upratingMatches(data, "double_lock", "earnings_link");
  const earningsHigher = earningsAtLeastCpi(data);
  if (same !== true || earningsHigher !== true) return null;
  return (
    <p>
      On the central forecast the double lock and the earnings link give the same result. Forecast
      earnings growth is at least as high as CPI inflation in every year, so the double lock always
      picks earnings. They differ only if inflation turns out higher than earnings growth.
    </p>
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
            Each card shows how much less a rule would cost the government than the triple lock,
            which is current policy, in two years. Figures are £ billion a year. Growth to 2030 is
            the OBR&apos;s March 2026 forecast; growth for 2031–33, which sets the last three
            upratings, is PolicyEngine&apos;s long-run path.
          </p>
          <p>
            <strong>Gross</strong> counts State Pension spending only. <strong>Net</strong> also
            counts knock-on effects: when pensions are lower, more people get Pension Credit and
            Housing Benefit, and pensioners pay less income tax. So the net saving is smaller.
          </p>
          <MatchNote data={data} />
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
        <SectionHeading title="Net cost and single survey households" />
        <Explainer>
          <p>
            Net costs rely on survey households, each standing for many homes. When a pension
            changes by a few pounds, one survey household can become eligible for Housing Benefit
            and move the net figure by hundreds of millions. The chart shows how much the survey
            household with the most effect adds to each rule&apos;s net figure each year, in £
            billion.
          </p>
          <LargestNote data={data} alternatives={alternatives} />
        </Explainer>
        <NetAdjustedChart data={data} alternatives={alternatives} />
      </section>

      <section className="section-card">
        <SectionHeading title="Annual cost compared with the triple lock" />
        <Explainer>
          <p>
            Each line shows one rule&apos;s {basis} cost minus the triple lock&apos;s, each year, in
            £ billion. Below zero means the rule is cheaper. The dashed line at zero is the triple
            lock. Use the Gross/Net buttons above to switch.
          </p>
          {basis === "net" ? <LumpyNote data={data} /> : null}
        </Explainer>
        <CostChart data={data} baseline={baseline} alternatives={alternatives} basis={basis} />
      </section>

      <section className="section-card">
        <SectionHeading title="Full new State Pension, £ a week" />
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
      </section>

      <section className="section-card">
        <SectionHeading title="Uprating each year" />
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
