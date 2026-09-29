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
  getNetExcludingLargest,
  getPolicies,
  getUprating,
  getWeeklyPension,
  earningsAtLeastCpi,
  hasLargestHousehold,
  upratingMatches,
} from "../lib/dataHelpers";
import { describeCostVsTripleLock, formatBn, formatRate, formatWeekly } from "../lib/formatters";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import BenchmarksTable, { BenchmarkLinks } from "./Benchmarks";
import { AXIS_STYLE, CustomTooltip, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

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
                {basis === "net" ? (
                  <dd className="text-xs text-slate-500" data-testid={`net-excl-${alt.id}-${year}`}>
                    Excluding one heavily weighted survey household:{" "}
                    {describeCostVsTripleLock(getNetExcludingLargest(data, alt.id, year))}
                  </dd>
                ) : null}
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

function NetAdjustedTable({ data, alternatives }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="net-adjusted">
        <caption className="sr-only">Net cost with and without the largest survey household</caption>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Year</th>
            <th>Net</th>
            <th>Net excluding that household</th>
            <th>That household adds</th>
          </tr>
        </thead>
        <tbody>
          {alternatives.flatMap((alt) =>
            HEADLINE_YEARS.map((year) => (
              <tr key={`${alt.id}-${year}`}>
                <td>{alt.label}</td>
                <td>{fyLabel(year)}</td>
                <td>{describeCostVsTripleLock(getCostInYear(data, alt.id, "net", year))}</td>
                <td>{describeCostVsTripleLock(getNetExcludingLargest(data, alt.id, year))}</td>
                <td className="tabular-nums">{formatBn(getLargestContribution(data, alt.id, year), 2)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
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
  return (
    <p className="note-card rounded-xl px-4 py-3 text-sm" data-testid="composition-caveat">
      <strong>Caveat:</strong> survey ages are held fixed. {effect.description}
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
      Net figures can jump from one year to the next. A single survey household with a large weight
      can move onto Housing Benefit when its pension changes slightly. The Methodology tab shows how
      much the largest such household adds each year.
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
            which is current policy, in two years. Figures are £ billion a year on the OBR central
            forecast.
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
        <SectionHeading title="Net cost and one lumpy survey household" />
        <Explainer>
          <p>
            Net costs rely on survey households, each standing for many real ones. When a pension
            changes slightly, a single heavily weighted household can move onto Housing Benefit and
            shift the net figure by hundreds of millions. This table shows the net figure with and
            without the most influential household, in £ billion.
          </p>
          <LargestNote data={data} alternatives={alternatives} />
        </Explainer>
        <NetAdjustedTable data={data} alternatives={alternatives} />
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
        <RuleTable
          data={data}
          policies={policies}
          getter={getWeeklyPension}
          format={formatWeekly}
          caption="The weekly State Pension table"
        />
      </section>

      <section className="section-card">
        <SectionHeading title="Uprating each year" />
        <Explainer>
          <p>
            The percentage rise each April under each rule, on the OBR central forecast. The row for
            a year is the rise that takes effect in April of that year. The triple lock takes the
            highest of CPI inflation, earnings growth and 2.5%.
          </p>
        </Explainer>
        <RuleTable
          data={data}
          policies={policies}
          getter={getUprating}
          format={(v) => formatRate(v)}
          caption="The uprating table"
        />
      </section>

      <section className="section-card">
        <SectionHeading title="How this compares" />
        <Explainer>
          <p>
            Other published estimates of the same costs, with our closest figure. They often use a
            different forecast, year or definition, so the last columns say how close the
            comparison is.
            <BenchmarkPrefix data={data} />
          </p>
        </Explainer>
        <BenchmarksTable data={data} scope="central" />
      </section>
    </div>
  );
}

function BenchmarkPrefix({ data }) {
  const links = BenchmarkLinks({ data, scope: "central" });
  if (!links) return null;
  return <> Sources compared: {links}.</>;
}
