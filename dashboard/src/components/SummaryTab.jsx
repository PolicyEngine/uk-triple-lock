"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors } from "../lib/colors";
import { fyLabel, getCentral, getDwp, getExpectedValue, getFinalYear, getSwitchYear, isNum } from "../lib/dataHelpers";
import { formatBn, formatCount } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import BenchmarksTable from "./Benchmarks";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, Unavailable } from "./ui";

const Z = 1.96;
const GROSS = colors.primary[700];
const NET = colors.primary[400];
const CENTRAL = colors.gray[500];

export function pm(estimate, digits = 1) {
  if (!estimate || !isNum(estimate.mean) || !isNum(estimate.se)) return "unavailable";
  return `${formatBn(estimate.mean, digits)} ± ${formatBn(Z * estimate.se, digits)}`;
}

function Card({ label, value, detail, testId }) {
  return (
    <div className="metric-card" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-600">{detail}</p> : null}
    </div>
  );
}

function ExpectedChart({ ev, central }) {
  const rows = ev.years.map((y, i) => {
    const g = ev.primary.gross[i];
    const n = ev.primary.net[i];
    return {
      year: fyLabel(y),
      gross: g.mean,
      grossBand: [g.mean - Z * g.se, g.mean + Z * g.se],
      net: n.mean,
      netBand: [n.mean - Z * n.se, n.mean + Z * n.se],
      central: central ? central.gross[i] : null,
    };
  });
  const values = rows.flatMap((r) => [...r.grossBand, ...r.netBand, r.central]).filter(isNum);
  return (
    <>
      <div style={{ height: 340 }} data-testid="expected-chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="year" tick={AXIS_STYLE} />
            <YAxis tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, axisDigits(values))} {...niceAxis(values)} />
            <ReferenceLine y={0} stroke={colors.gray[400]} />
            <Tooltip
              content={
                <CustomTooltip
                  formatter={(v) => (Array.isArray(v) ? `${formatBn(v[0], 1)} to ${formatBn(v[1], 1)}` : formatBn(v, 2))}
                />
              }
            />
            <Area dataKey="grossBand" name="Gross, 95% Monte Carlo interval" stroke="none" fill={GROSS} fillOpacity={0.15} isAnimationActive={false} />
            <Area dataKey="netBand" name="Net, 95% Monte Carlo interval" stroke="none" fill={NET} fillOpacity={0.2} isAnimationActive={false} />
            <Line dataKey="gross" name="Expected saving, gross" stroke={GROSS} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Line dataKey="net" name="Expected saving, net" stroke={NET} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            {central ? (
              <Line dataKey="central" name="Central forecast, gross" stroke={CENTRAL} strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches
        items={[
          { label: "Expected saving, gross (State Pension spending)", color: GROSS },
          { label: "Expected saving, net of tax and other benefits", color: NET },
          { label: "On the central forecast alone, gross", color: CENTRAL, dashed: true },
        ]}
      />
      <p className="mt-2 text-xs text-slate-500">Shaded: 95% Monte Carlo interval of the expected value, not the range of outcomes.</p>
      <ChartLogo />
    </>
  );
}

function DatasetTable({ ev }) {
  const show = ev.years.filter((y) => y >= 2031 && (y - 2031) % 4 === 0 || y === ev.years.at(-1));
  const years = [...new Set(show)];
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="dataset-table">
        <thead>
          <tr>
            <th>Year</th>
            <th>Enhanced FRS, gross</th>
            <th>Net</th>
            <th>Microcosm, gross</th>
            <th>Net</th>
            <th>Microcosm minus Enhanced FRS, gross (paired)</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const i = ev.years.indexOf(y);
            return (
              <tr key={y}>
                <td>{fyLabel(y)}</td>
                <td className="tabular-nums">{pm(ev.primary.gross[i])}</td>
                <td className="tabular-nums">{pm(ev.primary.net[i])}</td>
                <td className="tabular-nums">{pm(ev.sensitivity.gross[i])}</td>
                <td className="tabular-nums">{pm(ev.sensitivity.net[i])}</td>
                <td className="tabular-nums">{pm(ev.diff.gross[i], 2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CalibrationTable({ ev }) {
  const i = ev.years.length - 1;
  const rows = [
    { name: ev.primaryName, label: "The OBR's means, the model's own dynamics (used here)", gross: ev.primary.gross[i], net: ev.primary.net[i], ess: ev.nDraws, runs: ev.nRuns },
    ...ev.sensitivities.map((s) => ({ name: s.name, label: s.label, gross: s.gross[i], net: s.net[i], ess: s.ess, runs: s.effectiveRuns })),
  ];
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="calibration-table">
        <thead>
          <tr>
            <th>How the paths are weighted</th>
            <th>Expected saving {fyLabel(ev.years[i])}, gross</th>
            <th>Net</th>
            <th>Effective paths (of {formatCount(ev.nDraws)})</th>
            <th>Effective full runs (of {formatCount(ev.nRuns)})</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>{r.label}</td>
              <td className="tabular-nums">{pm(r.gross)}</td>
              <td className="tabular-nums">{pm(r.net)}</td>
              <td className="tabular-nums">{formatCount(Math.round(r.ess))}</td>
              <td className="tabular-nums">{formatCount(Math.round(r.runs))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SummaryTab({ data }) {
  const ev = getExpectedValue(data);
  const central = getCentral(data);
  const dwp = getDwp(data);
  const final = getFinalYear(data);
  const switchYear = getSwitchYear(data);
  if (!ev || !final) return <Unavailable what="The expected saving" />;
  const i = ev.years.indexOf(final);
  const g = ev.primary.gross[i];
  const n = ev.primary.net[i];
  const premium = ev.gap?.mean_rate_minus_earnings_2034_2039;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="summary-tab">
      <section className="mb-12">
        <SectionHeading title="6. The saving to expect, across every path" />
        <Explainer>
          <p data-testid="summary-explainer">
            The Burnham plan pays the triple lock until April {switchYear ? switchYear - 1 : "2029"}. From April{" "}
            {switchYear ?? 2030} the pension rises by at least the higher of CPI and 2.5%, plus whatever keeps it at
            its 2029-30 value relative to earnings, as DWP defines the plan. Apart from 0.1-point rounding, it saves
            money only after years in which CPI or the 2.5% floor runs ahead of earnings: the triple lock keeps that
            extra for good, while the plan&apos;s pension waits for earnings to catch up. On the OBR&apos;s central forecast earnings lead in almost every
            year from 2031, so the plan saves little; what to expect depends on how often the lead changes hands.
          </p>
          <p>
            We average over {formatCount(ev.nDraws)} paths of CPI and earnings from a monthly model of both, shifted
            so their calendar-year averages equal the OBR&apos;s forecast in every year, and run {formatCount(ev.nUniquePaths)} of
            them through PolicyEngine UK in full, sampled so that paths with large savings are well represented. The ±
            figures are the 95% Monte Carlo uncertainty of that average, not the range of outcomes.
          </p>
        </Explainer>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card label={`Expected saving, ${fyLabel(final)}`} value={formatBn(g.mean, 1)} detail={`± ${formatBn(Z * g.se, 1)}; gross State Pension spending, UK`} testId="card-expected-gross" />
          <Card label="Net of tax and other benefits" value={formatBn(n.mean, 1)} detail={`± ${formatBn(Z * n.se, 1)}; after income tax, Pension Credit and Housing Benefit${ev.netExcludingLargest ? `. ${formatBn(ev.netExcludingLargest[i].mean, 1)} without the single survey record that moves each path's net figure most` : ""}`} testId="card-expected-net" />
          <Card label="On the central forecast" value={central ? formatBn(central.gross[i], 1) : "unavailable"} detail="Gross, on the OBR's path alone" testId="card-central" />
          <Card label="DWP's costing" value={dwp ? `£${dwp.nominal2039}bn` : "unavailable"} detail="Gross, Great Britain, one path through its Pensim3 model" testId="card-dwp" />
        </div>
        <p className="mt-4 text-sm text-slate-600" data-testid="uncertain-note">
          The cost is highly uncertain.
          {ev.gap
            ? ` In ${fyLabel(final)} the full new State Pension is £${ev.gap.mean_gap_gbp_week.toFixed(2)} a week lower under the plan on average, but across the model's paths the gap runs from £${ev.gap.gap_gbp_week.p10.toFixed(2)} to £${ev.gap.gap_gbp_week.p90.toFixed(2)} a week (10th to 90th percentile: a spread of scenarios, not a forecast probability).`
            : ""}{" "}
          Steps 2 to 5 follow single paths through the full model year by year.
        </p>
        <div className="mt-8">
          <h3 className="mb-2 font-semibold text-slate-800">Expected saving each year</h3>
          <ExpectedChart ev={ev} central={central} />
        </div>
      </section>

      <section className="mb-12">
        <SectionHeading title={dwp ? `Why it differs from DWP's £${dwp.nominal2039}bn` : "Why it differs from DWP's figure"} />
        <Explainer>
          <ul className="list-disc space-y-1 pl-5" data-testid="dwp-differences">
            <li>DWP runs one uprating path through its model and does not state it; ours averages over paths.</li>
            <li>
              DWP&apos;s Pensim3 is a dynamic model that projects the population and each person&apos;s pension. The
              survey here is not aged: ages stay at their survey values, top-coded at 80, and each pensioner keeps the
              State Pension type they had in the survey, so there are no new pensioners on the new State Pension, and
              the number of pensioners changes only through the survey weights and the rise in State Pension age to 67.
            </li>
            <li>DWP&apos;s figure is direct spending only. Ours is gross State Pension spending too, with the net figure
              beside it.</li>
            <li>DWP covers Great Britain; the model covers the UK. Both figures here are in cash terms.</li>
            {premium && isNum(premium.triple_lock) && isNum(premium.burnham_2030) ? (
              <li data-testid="premium-note">
                The OBR&apos;s long-term assumption is that the triple lock rises 0.6 points a year faster than
                earnings. On our paths the triple lock rises {(premium.triple_lock * 100).toFixed(2)} points a year
                faster than May–July earnings for the Aprils 2034 to 2039, on average, and the Burnham plan{" "}
                {(premium.burnham_2030 * 100).toFixed(2)} points.
              </li>
            ) : null}
          </ul>
        </Explainer>
      </section>

      <section className="mb-12">
        <SectionHeading title="How much the answer depends on our choices" />
        <div className="space-y-4">
          <Expandable title="The survey data: Enhanced FRS and Microcosm" testId="dataset-box">
            <p className="mb-3 text-sm leading-6 text-slate-600">
              The same {formatCount(ev.nSensitivity)} paths (a subsample of those above) run on both datasets, so the
              difference is paired. With so few runs in some groups the ± figures here are approximate. The Enhanced FRS is PolicyEngine&apos;s certified dataset; Microcosm is not yet
              certified. The Method tab sets both against DWP&apos;s spending and caseloads.
            </p>
            <DatasetTable ev={ev} />
          </Expandable>
          <Expandable title="How the paths are weighted" testId="calibration-box">
            <p className="mb-3 text-sm leading-6 text-slate-600">
              Every row reuses the same full runs, reweighted; with fewer effective runs a row&apos;s ± figure is
              approximate and too narrow. The dynamics rows also match the past variance of the gap
              between May–July earnings and September CPI and how often the lead passed between them; in our backtest
              (Method tab) that made the expected gap more biased, so they are shown as sensitivities.
            </p>
            <CalibrationTable ev={ev} />
          </Expandable>
          <Expandable title="Other published costings" testId="benchmarks-box">
            <BenchmarksTable data={data} />
          </Expandable>
        </div>
      </section>
    </div>
  );
}
