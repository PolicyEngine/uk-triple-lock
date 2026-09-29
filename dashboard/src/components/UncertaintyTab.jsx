"use client";

import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
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
  getBootstrapSupport,
  getCostInYear,
  getCostQuantiles,
  getDraws,
  getErrorSource,
  getFan,
  getFinalYear,
  getCentralPosition,
  getNetOnPaths,
  getHorizon,
  getFloorProbabilities,
  getPolicies,
  getRobustness,
  getSensitivityDescription,
  getUncertaintyBasis,
  getUncertaintyText,
  getVarCrossCheck,
} from "../lib/dataHelpers";
import { formatBn, formatCount, formatIndex, formatPct } from "../lib/formatters";
import BenchmarksTable from "./Benchmarks";
import { niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

function FanChart({ data, policies }) {
  // Open on the announced policy when the file has it, with the triple lock's median alongside.
  const [selectedId, setSelectedId] = useState(
    policies.some((p) => p.id === "burnham_2030") ? "burnham_2030" : BASELINE_POLICY,
  );
  const baseline = policies[0];
  const policy = policies.find((p) => p.id === selectedId);
  if (!policy) return <Unavailable what="The selected rule" />;
  const fan = getFan(data, policy.id);
  const baselineFan = policy.id === BASELINE_POLICY ? null : getFan(data, BASELINE_POLICY);
  const color = colorFor(policy.id);

  const selector = (
    <div className="mb-5">
      <ToggleGroup
        options={policies.map((p) => ({ id: p.id, label: p.label }))}
        value={policy.id}
        onChange={setSelectedId}
        label="Rule shown in fan chart"
      />
    </div>
  );

  if (!fan) {
    return (
      <>
        {selector}
        <Unavailable what={`The fan chart for ${policy.label}`} />
      </>
    );
  }

  const rows = fan.map((r) => {
    const tl = baselineFan ? baselineFan.find((b) => b.year === r.year) : null;
    return {
      year: fyLabel(r.year),
      range: [r.p10, r.p90],
      p10: r.p10,
      p50: r.p50,
      p90: r.p90,
      tl50: tl ? tl.p50 : undefined,
    };
  });
  const lows = fan.map((r) => r.p10);
  const highs = [...fan.map((r) => r.p90), ...(baselineFan ? baselineFan.map((r) => r.p50) : [])];
  const min = Math.min(...lows);
  const max = Math.max(...highs);

  return (
    <>
      {selector}
      <div className="h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="year" tick={AXIS_STYLE} />
            <YAxis
              tick={AXIS_STYLE}
              {...niceAxis([min, max], { includeZero: false })}
              allowDataOverflow
              tickFormatter={(v) => v.toFixed(2)}
            />
            <Tooltip
              content={
                <CustomTooltip
                  formatter={(v, name, entry) =>
                    name === "Range"
                      ? `${formatIndex(entry.payload.p10)} to ${formatIndex(entry.payload.p90)}`
                      : formatIndex(v)
                  }
                />
              }
            />
            <Area dataKey="range" name="Range" stroke="none" fill={color} fillOpacity={0.2} isAnimationActive={false} />
            <Line dataKey="p50" name={`${policy.label} (median)`} stroke={color} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            {baselineFan ? (
              <Line
                dataKey="tl50"
                name={`${baseline.label} (median)`}
                stroke={colorFor(BASELINE_POLICY)}
                strokeDasharray="5 4"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches
        items={[
          { label: `${policy.label}: median`, color },
          { label: `${policy.label}: 10th to 90th percentile`, color: `${color}55` },
          ...(baselineFan ? [{ label: `${baseline.label}: median`, color: colorFor(BASELINE_POLICY), dashed: true }] : []),
        ]}
      />
      <ChartLogo />
      <div className="mt-4">
      <Expandable title={`Pension index for ${policy.label}: table`} testId="fan-table">
      <table className="data-table">
        <caption className="sr-only">Pension index for {policy.label}</caption>
        <thead>
          <tr>
            <th>Year</th>
            <th>10th percentile</th>
            <th>Median</th>
            <th>90th percentile</th>
          </tr>
        </thead>
        <tbody>
          {fan.map((r) => (
            <tr key={r.year}>
              <td>{fyLabel(r.year)}</td>
              <td>{formatIndex(r.p10)}</td>
              <td>{formatIndex(r.p50)}</td>
              <td>{formatIndex(r.p90)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </Expandable>
      </div>
    </>
  );
}

function CostRanges({ data, alternatives, basis, finalYear }) {
  const blocks = alternatives.map((alt) => ({
    ...alt,
    q: getCostQuantiles(data, alt.id),
    // Central-forecast cost of the triple lock over this rule, on the same
    // basis as the Monte Carlo, when the file states that basis.
    central: basis && finalYear ? getCostInYear(data, alt.id, basis, finalYear) : null,
  }));
  const valid = blocks.filter((b) => b.q);
  if (valid.length === 0) return <Unavailable what="The cost distribution" />;
  const lo = Math.min(0, ...valid.map((b) => b.q.p5));
  const hi = Math.max(0, ...valid.map((b) => b.q.p95));
  const span = hi - lo;
  if (!(span > 0)) return <Unavailable what="The cost distribution" />;
  const pos = (v) => `${((v - lo) / span) * 100}%`;

  return (
    <div className="space-y-6">
      {blocks.map((b) => (
        <div key={b.id} data-testid={`range-${b.id}`}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-semibold text-slate-800">Triple lock vs {b.label}</p>
            {b.q ? (
              <p className="text-sm text-slate-600">
                Median <strong>{formatBn(b.q.p50)}</strong>; 90% range{" "}
                <strong>
                  {formatBn(b.q.p5)} to {formatBn(b.q.p95)}
                </strong>
              </p>
            ) : null}
          </div>
          {b.q ? (
            <>
              <div className="relative h-7 rounded bg-slate-100" aria-hidden="true">
                <div className="absolute top-0 h-full w-px bg-slate-400" style={{ left: pos(0) }} />
                <div
                  className="absolute top-2 h-3 rounded"
                  style={{ left: pos(b.q.p5), width: `calc(${pos(b.q.p95)} - ${pos(b.q.p5)})`, backgroundColor: colorFor(b.id), opacity: 0.3 }}
                />
                <div
                  className="absolute top-1 h-5 rounded"
                  style={{ left: pos(b.q.p25), width: `calc(${pos(b.q.p75)} - ${pos(b.q.p25)})`, backgroundColor: colorFor(b.id), opacity: 0.6 }}
                />
                <div className="absolute top-0 h-full w-[3px] bg-slate-900" style={{ left: pos(b.q.p50) }} />
              </div>
              <p className="mt-2 text-sm text-slate-600" data-testid={`words-${b.id}`}>
                The middle 80% of draws runs from {formatBn(b.q.p10)} to {formatBn(b.q.p90)}, with a
                median of {formatBn(b.q.p50)}.
                {b.central !== null
                  ? ` On the central forecast alone it is ${formatBn(-b.central)}.`
                  : ""}
              </p>
            </>
          ) : (
            <Unavailable what={`The cost distribution against ${b.label}`} />
          )}
        </div>
      ))}
      <div className="flex justify-between text-xs text-slate-500">
        <span>{formatBn(lo)}</span>
        <span>{formatBn(hi)}</span>
      </div>
      <p className="text-sm text-slate-600">
        Light bar: 5th to 95th percentile. Dark bar: 25th to 75th percentile. Black line: median.
        Grey line: zero.
      </p>
    </div>
  );
}

function SpreadNote({ data, alternatives, basis, finalYear }) {
  if (!basis || !finalYear) return null;
  const known = alternatives.some((alt) => getCentralPosition(data, alt.id));
  if (!known) return null;
  return (
    <span data-testid="spread-note">
      {" "}
      The central-forecast cost sits low in every range: the triple lock takes the highest of three
      rates, so forecast misses raise its cost more than they lower it.
    </span>
  );
}

function FloorProbability({ data }) {
  const rows = getFloorProbabilities(data);
  if (!rows) return <Unavailable what="The probability that the 2.5% floor applies" />;
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.year} className="flex items-center gap-3 text-sm">
          <span className="w-16 shrink-0 text-slate-600">{fyLabel(r.year)}</span>
          <div className="relative h-4 flex-1 rounded bg-slate-100" aria-hidden="true">
            <div
              className="absolute left-0 top-0 h-full rounded"
              style={{ width: `${r.share * 100}%`, backgroundColor: colorFor(BASELINE_POLICY) }}
            />
          </div>
          <span className="w-14 shrink-0 text-right font-medium tabular-nums text-slate-800">
            {formatPct(r.share * 100, 0)}
          </span>
        </div>
      ))}
    </div>
  );
}

export const METHOD_CITATIONS = [
  {
    label: "Künsch (1989), block bootstrap",
    url: "https://doi.org/10.1214/aos/1176347265",
  },
  {
    label: "Knüppel (2014), forecast uncertainty from past forecast errors",
    url: "https://doi.org/10.1016/j.ijforecast.2013.08.004",
  },
  {
    label: "IFS (2023), R272, a stochastic simulation of the triple lock",
    url: "https://ifs.org.uk/sites/default/files/2023-09/R272-The-triple-lock-costs-and-uncertainty.pdf",
  },
];

export function Citations() {
  return (
    <>
      {METHOD_CITATIONS.map((c, i) => (
        <span key={c.url}>
          {i > 0 ? (i === METHOD_CITATIONS.length - 1 ? " and " : ", ") : ""}
          <a href={c.url} target="_blank" rel="noreferrer">
            {c.label}
          </a>
        </span>
      ))}
    </>
  );
}

function MethodNote({ data }) {
  const draws = getDraws(data);
  const support = getBootstrapSupport(data);
  const source = getErrorSource(data);
  const varCheck = getVarCrossCheck(data);
  const finalYear = getFinalYear(data);
  if (!draws || !support || !source || !finalYear) return <Unavailable what="The uncertainty method" />;
  const showVar = varCheck && varCheck.status === "ok";
  return (
    <Explainer>
      <ul className="list-disc space-y-2 pl-5">
        <li>
          <strong>What is uncertain:</strong> CPI inflation and earnings growth in each year, which
          set every April rise. Everything else (the population, other benefits, taxes) stays on
          the central path. The ranges cover gross State Pension spending only:{" "}
          <strong>
            net costs and household impacts on the other tabs have no uncertainty range
          </strong>
          ; five full-model runs below show how net relates to gross for the Burnham plan.
        </li>
        <li>
          <strong>Main model: a block bootstrap of the OBR&apos;s past forecast errors.</strong> Each
          simulated path takes how far a past OBR forecast (made in {source.years}) missed CPI and
          earnings, adds those misses to today&apos;s forecast, and adds the historical gaps between
          the measures the OBR forecasts and the ones the law uses. CPI and earnings misses are
          drawn together, four years at a time, so their joint pattern is kept. The approach
          follows <Citations />.
        </li>
        {showVar ? (
          <li>
            <strong>Cross-check: a vector autoregression (VAR).</strong> A statistical time-series
            model of CPI and earnings
            {varCheck.sampleYears ? ` fitted to ${varCheck.sampleYears[0]}–${varCheck.sampleYears[1]}` : ""}
            {varCheck.lagOrder ? `, where each year depends on the previous ${varCheck.lagOrder}` : ""},
            centred on the same path. It uses the OBR&apos;s measures, not the ones the law uses.
          </li>
        ) : null}
        <li>
          <strong>What comes out:</strong> for each path, the rise under every rule and how much
          more the triple lock costs than each alternative in {fyLabel(finalYear)}, in gross State
          Pension spending. There are <strong>{formatCount(draws)}</strong> draws over{" "}
          <strong>{formatCount(support.paths)}</strong> distinct paths ({formatCount(support.pairs)}{" "}
          pairs of the {formatCount(support.vintages)} past forecasts times{" "}
          {formatCount(support.firstYear)} first-year CPI changes), so read the percentiles as
          ranges, not probabilities.
        </li>
        <li>The Methodology tab gives the equations and a backtest on past forecasts.</li>
      </ul>
    </Explainer>
  );
}

function NetOnPaths({ data }) {
  const rows = getNetOnPaths(data, "burnham_2030");
  if (!rows) return null;
  return (
    <div className="mt-5">
      <Expandable title="Burnham plan: net cost on five simulated paths" testId="net-on-paths">
        <p className="mb-3 text-sm leading-6 text-slate-600">
          Five draws, at the 10th to 90th percentiles of the Burnham plan&apos;s gross saving, run
          through the full PolicyEngine model. Only the State Pension changes in these runs, so they
          show how the net saving relates to the gross one; they are not a range for the net cost.
        </p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Gross saving</th>
                <th>Net saving</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.q}>
                  <td>{r.q}th percentile</td>
                  <td className="tabular-nums">{formatBn(r.gross, 2)}</td>
                  <td className="tabular-nums">{formatBn(r.net, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Expandable>
    </div>
  );
}

function RobustnessTable({ data, alternatives }) {
  const rows = getRobustness(data, alternatives);
  if (rows.length === 0) return <Unavailable what="The robustness comparison" />;
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="robustness">
        <caption className="sr-only">Robustness of the extra cost of the triple lock</caption>
        <thead>
          <tr>
            <th>Method</th>
            {alternatives.map((a) => (
              <th key={a.id}>vs {a.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} data-testid={`robustness-${row.id}`}>
              <td>{row.label}</td>
              {alternatives.map((a) => {
                const q = row.byAlt[a.id];
                return (
                  <td key={a.id} className="tabular-nums">
                    {q ? (
                      <>
                        <strong>{formatBn(q.p50)}</strong>{" "}
                        <span className="text-slate-500">
                          ({formatBn(q.p10)} to {formatBn(q.p90)})
                        </span>
                      </>
                    ) : (
                      "unavailable"
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function UncertaintyTab({ data }) {
  const policies = getPolicies(data);
  const alternatives = getAlternatives(data);
  if (!policies || !alternatives) return <Unavailable what="The list of uprating rules" />;
  const finalYear = getFinalYear(data);
  const yearText = fyLabel(finalYear);
  const horizon = getHorizon(data);
  // The schema fixes the fan's index at 1.0 in the year before the horizon.
  const baseYearText = fyLabel(horizon ? horizon[0] - 1 : null);
  const basis = getUncertaintyBasis(data, alternatives);
  const status = getUncertaintyText(data, "status");
  const rawDesc = getSensitivityDescription(data, "sensitivity_raw_errors");
  const exShockDesc = getSensitivityDescription(data, "sensitivity_ex_2022_23");
  const proxyDesc = getSensitivityDescription(data, "sensitivity_proxy_only");
  const medianDesc = getSensitivityDescription(data, "sensitivity_median_centred");
  const hasAverage = Boolean(data?.uncertainty?.model_average);
  const varCheck = getVarCrossCheck(data);

  return (
    <div className="space-y-8">
      {status && status !== "complete" ? (
        <p className="note-card rounded-xl px-5 py-3 text-sm" data-testid="uncertainty-status">
          The uncertainty results in this file are marked &quot;{status}&quot;.
        </p>
      ) : null}

      <section className="section-card">
        <Expandable title="How we model uncertainty" testId="section-method">
        <MethodNote data={data} />
              </Expandable>
      </section>

      <section className="section-card">
        <SectionHeading title="Extra cost of the triple lock" />
        <Explainer>
          <p>
            Extra gross State Pension cost of the triple lock over each rule in {yearText}, across
            the simulated paths.
            <SpreadNote data={data} alternatives={alternatives} basis={basis} finalYear={finalYear} />
          </p>
        </Explainer>
        <CostRanges data={data} alternatives={alternatives} basis={basis} finalYear={finalYear} />
        <NetOnPaths data={data} />
      </section>

      <section className="section-card">
        <Expandable title="Is the range robust?" testId="section-robust">
        <Explainer>
          <p>
            The same extra cost in {yearText} under other ways of modelling forecast errors. Each
            cell shows the median, with the 10th to 90th percentile in brackets.
          </p>
          <ul className="list-disc pl-5">
            <li>
              <strong>Main</strong>: past OBR forecast errors with their average bias removed, plus
              the historical gaps between the OBR&apos;s measures and the September CPI and May–July
              earnings the law uses.
            </li>
            {rawDesc ? (
              <li>
                <strong>Raw OBR errors</strong>: {rawDesc}.
              </li>
            ) : null}
            {exShockDesc ? (
              <li>
                <strong>Excluding the 2022–23 shocks</strong>: {exShockDesc}.
              </li>
            ) : null}
            {proxyDesc ? (
              <li>
                <strong>OBR measures only</strong>: {proxyDesc}.
              </li>
            ) : null}
            {medianDesc ? (
              <li>
                <strong>Median-centred</strong>: {medianDesc}.
              </li>
            ) : null}
            {hasAverage ? (
              <li>
                <strong>Illustrative pool</strong>: the main run, the run without 2022–23 and the
                VAR pooled with equal weights. These are unlike methods with no basis for the
                weights, so this row is illustrative, not a cost distribution.
              </li>
            ) : null}
            {varCheck && varCheck.status === "ok" ? (
              <li>
                <strong>VAR cross-check</strong>: a statistical time-series model of CPI and
                earnings, fitted to past data, instead of the OBR&apos;s past errors. It models the
                OBR&apos;s measures, not the September CPI and May–July earnings the law uses.
              </li>
            ) : null}
          </ul>
          <p>
            The result depends on whether shocks on the scale of 2021–23 happen again, on the
            OBR&apos;s past forecast bias, and on how the errors are centred. Read the range across
            rows, not any single row, as the uncertainty.
          </p>
        </Explainer>
        <RobustnessTable data={data} alternatives={alternatives} />
              </Expandable>
      </section>

      <section className="section-card">
        <SectionHeading title="State Pension level over time" />
        <Explainer>
          <p>
            A fan chart. The line is the median path of the State Pension level, with {baseYearText}{" "}
            set to 1 (so 1.20 means 20% higher). The shaded band covers the middle 80% of draws. The dashed line is the
            triple lock&apos;s median, for comparison.
          </p>
        </Explainer>
        <FanChart data={data} policies={policies} />
      </section>

      <section className="section-card">
        <Expandable title="How often the 2.5% floor applies" testId="section-floor">
        <Explainer>
          <p>
            The floor &quot;binds&quot; when both CPI inflation and earnings growth come in below
            2.5%, so the triple lock pays 2.5%. Each bar is the share of simulated paths where that
            happens in that year. The Burnham plan keeps the same floor, so it also pays at least
            2.5% in those years; the earnings and CPI links do not.
          </p>
        </Explainer>
        <FloorProbability data={data} />
              </Expandable>
      </section>

      <section className="section-card">
        <Expandable title="How this compares" testId="compare-uncertainty">
          <Explainer>
            <p>
              Other estimates of how uncertain the triple lock&apos;s cost is. They look at other
              years than ours ({yearText}), so compare the width of the ranges, not the figures.
            </p>
          </Explainer>
          <BenchmarksTable data={data} scope="uncertainty" />
        </Expandable>
      </section>
    </div>
  );
}
