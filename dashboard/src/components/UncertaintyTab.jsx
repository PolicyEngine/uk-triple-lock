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
  getCostInYear,
  getCostQuantiles,
  getDraws,
  getErrorSource,
  getFan,
  getFinalYear,
  getHorizon,
  getFloorProbabilities,
  getPolicies,
  getRobustness,
  getCentralFloorYears,
  getSensitivityDescription,
  getSensitivityMedian,
  getUncertaintyBasis,
  getUncertaintyText,
  getVarCrossCheck,
} from "../lib/dataHelpers";
import { formatBn, formatCount, formatIndex, formatPct } from "../lib/formatters";
import BenchmarksTable, { BenchmarkLinks } from "./Benchmarks";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

function FanChart({ data, policies }) {
  const [selectedId, setSelectedId] = useState(BASELINE_POLICY);
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
      base: r.p10,
      band: r.p90 - r.p10,
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
              domain={[Math.floor(min * 20) / 20, Math.ceil(max * 20) / 20]}
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
            <Area dataKey="base" stackId="fan" stroke="none" fill="transparent" tooltipType="none" legendType="none" isAnimationActive={false} />
            <Area dataKey="band" name="Range" stackId="fan" stroke="none" fill={color} fillOpacity={0.2} isAnimationActive={false} />
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
      <table className="data-table mt-4">
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
                In 1 path in 10 the extra cost is below {formatBn(b.q.p10)}; in half it is below{" "}
                {formatBn(b.q.p50)}; in 1 in 10 it is above {formatBn(b.q.p90)}.
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
  const rows = alternatives
    .map((alt) => ({
      alt,
      q: getCostQuantiles(data, alt.id),
      central: getCostInYear(data, alt.id, basis, finalYear),
      exShock: getSensitivityMedian(data, "sensitivity_ex_2022_23", alt.id),
    }))
    .filter((r) => r.q && r.central !== null);
  const low = rows.filter((r) => -r.central < r.q.p25);
  if (low.length === 0) return null;
  const floorYears = getCentralFloorYears(data);
  const withEx = rows.filter((r) => r.exShock !== null);
  return (
    <div data-testid="spread-note" className="space-y-2">
      <p>
        The central-forecast cost sits near the bottom of the simulated range: below the 25th
        percentile against {low.map((r) => r.alt.label).join(", ")}.
        {floorYears && floorYears.length > 0
          ? ` On the central forecast the 2.5% floor already applies in ${floorYears.map(fyLabel).join(", ")}, so there is little room for the triple lock to pay less, but plenty for it to pay more.`
          : ""}
      </p>
      <p>
        The triple lock pays the highest of three rates each year, so when inflation or earnings
        come in above forecast it pays the higher figure, while the floor limits how far it can
        fall. Every rule compounds, but these misses raise the triple lock more than the
        alternatives.
      </p>
      {withEx.length > 0 ? (
        <p>
          Much of the spread comes from shocks like those of 2021–23. Excluding the 2022–23
          forecast errors, the median extra cost is{" "}
          {withEx.map((r, i) => (
            <span key={r.alt.id}>
              {i > 0 ? (i === withEx.length - 1 ? " and " : ", ") : ""}
              {formatBn(r.exShock)} against the {r.alt.label}
            </span>
          ))}
          .
        </p>
      ) : null}
    </div>
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

function MethodNote({ data }) {
  const draws = getDraws(data);
  const source = getErrorSource(data);
  return (
    <Explainer>
      <p>
        A single costing uses one forecast of inflation and earnings. Forecasts are often wrong, and
        the triple lock pays whichever of CPI, earnings or 2.5% is highest. So its cost depends on
        how far outturns differ from the forecast.
      </p>
      <p>
        To show this, we re-run the costing many times. Each time, we add errors of the size the OBR
        has actually made in past forecasts of CPI and earnings to its central forecast, with their
        average bias removed so the paths centre on the OBR forecast
        {source && source.years ? ` (forecasts made in ${source.years})` : ""}. We then apply each
        uprating rule to every simulated path.
      </p>
      <OthersNote data={data} />
      {draws ? (
        <p>
          This file uses <strong>{formatCount(draws)}</strong> simulated paths.
        </p>
      ) : (
        <Unavailable what="The number of simulated paths" />
      )}
      {source ? (
        <>
          <p>
            Forecast errors:{" "}
            {source.url ? (
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.title}
              </a>
            ) : (
              source.title
            )}
            .
          </p>
          <p>{source.method}</p>
        </>
      ) : (
        <Unavailable what="The forecast error source" />
      )}
    </Explainer>
  );
}

function OthersNote({ data }) {
  const links = BenchmarkLinks({ data, scope: "uncertainty" });
  if (!links) return null;
  return <p>Others have also simulated this uncertainty: {links}.</p>;
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
  const basisNote = getUncertaintyText(data, "basis_note");
  const status = getUncertaintyText(data, "status");
  const rawDesc = getSensitivityDescription(data, "sensitivity_raw_errors");
  const exShockDesc = getSensitivityDescription(data, "sensitivity_ex_2022_23");
  const varCheck = getVarCrossCheck(data);

  return (
    <div className="space-y-8">
      {status && status !== "complete" ? (
        <p className="note-card rounded-xl px-5 py-3 text-sm" data-testid="uncertainty-status">
          The uncertainty results in this file are marked &quot;{status}&quot;.
        </p>
      ) : null}

      <section className="section-card">
        <SectionHeading title="How we model uncertainty" />
        <MethodNote data={data} />
      </section>

      <section className="section-card">
        <SectionHeading title="Extra cost of the triple lock" />
        <Explainer>
          <p>
            How much more the triple lock costs than each alternative in {yearText}, in £ billion,
            across all simulated paths{basis ? ` (${basis} cost)` : ""}. Above zero means the triple
            lock costs more.
          </p>
          {basisNote ? <p className="text-slate-500">Basis: {basisNote}</p> : null}
          <SpreadNote data={data} alternatives={alternatives} basis={basis} finalYear={finalYear} />
        </Explainer>
        <CostRanges data={data} alternatives={alternatives} basis={basis} finalYear={finalYear} />
      </section>

      <section className="section-card">
        <SectionHeading title="Is the range robust?" />
        <Explainer>
          <p>
            The same extra cost in {yearText} under other ways of modelling forecast errors. Each
            cell shows the median, with the 10th to 90th percentile in brackets.
          </p>
          <ul className="list-disc pl-5">
            <li>
              <strong>Main</strong>: past OBR forecast errors, with their average bias removed so
              the paths centre on the OBR forecast.
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
            {varCheck && varCheck.status === "ok" ? (
              <li>
                <strong>VAR cross-check</strong>: a statistical time-series model of CPI and
                earnings, fitted to past data, instead of the OBR&apos;s past errors.
              </li>
            ) : null}
          </ul>
          <p>
            The result is sensitive to two things: whether shocks on the scale of 2021–23 happen
            again, and whether the OBR&apos;s past forecast bias carries on. The rows show how far
            the cost moves under each assumption, so read the range across rows, not any single
            row, as the uncertainty.
          </p>
        </Explainer>
        <RobustnessTable data={data} alternatives={alternatives} />
      </section>

      <section className="section-card">
        <SectionHeading title="State Pension level over time" />
        <Explainer>
          <p>
            A fan chart. The line is the median path of the State Pension level, with {baseYearText}{" "}
            set to 1 (so 1.20 means 20% higher). The shaded band covers the middle 80% of paths: in 1 path
            in 10 the level is below the band, and in 1 in 10 it is above it. The dashed line is the
            triple lock&apos;s median, for comparison.
          </p>
        </Explainer>
        <FanChart data={data} policies={policies} />
      </section>

      <section className="section-card">
        <SectionHeading title="How often the 2.5% floor applies" />
        <Explainer>
          <p>
            The floor &quot;binds&quot; when both CPI inflation and earnings growth come in below
            2.5%, so the triple lock pays 2.5%. Each bar is the share of simulated paths where that
            happens in that year.
          </p>
        </Explainer>
        <FloorProbability data={data} />
      </section>

      <section className="section-card">
        <SectionHeading title="How this compares" />
        <Explainer>
          <p>
            Other estimates of how uncertain the triple lock&apos;s cost is. They often look at
            different years, so their horizons differ from ours ({yearText}); compare the width of
            the ranges rather than the exact figures.
          </p>
        </Explainer>
        <BenchmarksTable data={data} scope="uncertainty" />
      </section>
    </div>
  );
}
