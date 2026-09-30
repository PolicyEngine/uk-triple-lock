"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import {
  BREAKDOWNS,
  POVERTY_MEASURES,
  fyLabel,
  getBreakdown,
  getExpectedValue,
  getHouseholdsAffected,
  getPolicyLabel,
  getPoverty,
  getRunsWithTables,
} from "../lib/dataHelpers";
import { formatBn, formatCurrency, formatPct } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, ToggleGroup, Unavailable } from "./ui";

const METRIC_OPTIONS = [
  { id: "pct", label: "% of income" },
  { id: "gbp", label: "£ a year" },
];
const ORDERED = new Set(["by_decile", "by_quintile"]);

function shortLabel(label) {
  return label.length > 28 ? `${label.slice(0, 26)}…` : label;
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

function GroupChart({ rows, breakdownId, metric, label }) {
  const format = metric === "gbp" ? formatCurrency : (v) => formatPct(v, 2);
  const data = rows.map((r) => ({ label: r.label, value: metric === "gbp" ? r.mean : r.pct }));
  if (!ORDERED.has(breakdownId)) data.sort((a, b) => a.value - b.value);
  const longest = Math.max(...data.map((r) => shortLabel(r.label).length));
  const tilt = data.length > 6 || longest > 12;
  return (
    <>
      <div className={tilt ? "h-[420px]" : "h-[340px]"} data-testid="group-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: tilt ? 10 : 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
            <XAxis
              dataKey="label"
              tick={AXIS_STYLE}
              tickFormatter={shortLabel}
              interval={0}
              angle={tilt ? -35 : 0}
              textAnchor={tilt ? "end" : "middle"}
              height={tilt ? Math.min(150, 20 + longest * 5.5) : 30}
            />
            <YAxis tick={AXIS_STYLE} tickFormatter={format} {...niceAxis(data.map((r) => r.value))} />
            <ReferenceLine y={0} stroke={colors.gray[400]} />
            <Tooltip content={<CustomTooltip formatter={format} />} />
            <Bar dataKey="value" name={label} fill={colorFor("burnham_2030")} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartLogo />
    </>
  );
}

function GroupTable({ rows, label }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="group-table">
        <thead>
          <tr>
            <th>{label}</th>
            <th>Mean change, £ a year</th>
            <th>Change, % of income</th>
            <th>Total, £ billion</th>
            <th>Share of households</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="tabular-nums">{formatCurrency(r.mean)}</td>
              <td className="tabular-nums">{formatPct(r.pct, 2)}</td>
              <td className="tabular-nums">{formatBn(r.total, 2)}</td>
              <td className="tabular-nums">{formatPct(r.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PovertyTable({ poverty, labels }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="poverty-table">
        <thead>
          <tr>
            <th>Measure</th>
            <th>{labels.triple_lock}</th>
            <th>{labels.burnham_2030}</th>
            <th>Change, points</th>
          </tr>
        </thead>
        <tbody>
          {POVERTY_MEASURES.map((m) => (
            <tr key={m.id}>
              <td>{m.label}</td>
              <td className="tabular-nums">{formatPct(poverty.triple_lock[m.id])}</td>
              <td className="tabular-nums">{formatPct(poverty.burnham_2030[m.id])}</td>
              <td className="tabular-nums">{(poverty.burnham_2030[m.id] - poverty.triple_lock[m.id]).toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AffectedTab({ data }) {
  const runs = getRunsWithTables(data);
  const years = Array.isArray(data?.distribution_years) ? data.distribution_years : [];
  const [runId, setRunId] = useState(runs.find((r) => r.id !== "central")?.id ?? runs[0]?.id);
  const [year, setYear] = useState(years.at(-1));
  const [breakdownId, setBreakdownId] = useState("by_quintile");
  const [metric, setMetric] = useState("pct");
  const labels = { triple_lock: getPolicyLabel(data, "triple_lock"), burnham_2030: getPolicyLabel(data, "burnham_2030") };
  if (!runs.length || !years.length || !labels.triple_lock || !labels.burnham_2030) {
    return <Unavailable what="The household results" plural />;
  }
  const run = (runs.find((r) => r.id === runId) ?? runs[0]).run;
  const affected = getHouseholdsAffected(run, year);
  const poverty = getPoverty(run, year);
  const available = BREAKDOWNS.filter((b) => getBreakdown(run, year, b.id));
  const breakdown = available.find((b) => b.id === breakdownId) ?? available[0];
  const rows = breakdown ? getBreakdown(run, year, breakdown.id) : null;
  const ev = getExpectedValue(data);
  const evLosing = ev?.losing ? ev.losing[ev.years.indexOf(year)] : null;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="affected-tab">
      <section className="mb-12">
        <SectionHeading title="Who pays for the saving" />
        <Explainer>
          <p>
            Household results depend on the path CPI and earnings take, so they are shown for one path at a time,
            each a full PolicyEngine UK run. A household loses when its pensioners get less State Pension; Pension
            Credit, Housing Benefit and lower income tax make up part of the loss for some. Households are grouped as
            in the survey, whose members keep their survey-year ages.
          </p>
          {evLosing ? (
            <p data-testid="expected-losing">
              Averaged over all the paths behind the expected saving, {formatPct(evLosing.mean)} of households have a
              lower income under the plan in {fyLabel(year)}.
            </p>
          ) : null}
        </Explainer>
        <div className="flex flex-wrap gap-6">
          <ToggleGroup label="Path" options={runs.map((r) => ({ id: r.id, label: r.label }))} value={runId} onChange={setRunId} />
          <ToggleGroup label="Year" options={years.map((y) => ({ id: y, label: fyLabel(y) }))} value={year} onChange={setYear} />
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card
            label="Households with lower income"
            value={affected ? formatPct(affected.losing) : "unavailable"}
            detail={affected ? `Losing ${formatCurrency(affected.meanLoss)} a year on average` : null}
            testId="card-losing"
          />
          <Card
            label="Pensioners in absolute poverty, after housing costs"
            value={poverty ? `${formatPct(poverty.burnham_2030.pensioners_absolute_ahc)}` : "unavailable"}
            detail={poverty ? `${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under the triple lock` : null}
            testId="card-poverty"
          />
          <Card
            label="Everyone in absolute poverty, after housing costs"
            value={poverty ? `${formatPct(poverty.burnham_2030.everyone_absolute_ahc)}` : "unavailable"}
            detail={poverty ? `${formatPct(poverty.triple_lock.everyone_absolute_ahc)} under the triple lock` : null}
            testId="card-poverty-all"
          />
        </div>
      </section>

      <section className="mb-12">
        <SectionHeading title="Change in household income by group" />
        {breakdown && rows ? (
          <>
            <div className="flex flex-wrap gap-6">
              <ToggleGroup label="Group" options={available.map((b) => ({ id: b.id, label: b.label }))} value={breakdown.id} onChange={setBreakdownId} />
              <ToggleGroup label="Measure" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
            </div>
            <div className="mt-4">
              <GroupChart rows={rows} breakdownId={breakdown.id} metric={metric} label={labels.burnham_2030} />
            </div>
            <div className="mt-4">
              <Expandable title={`Table: change by ${breakdown.label.toLowerCase()}`} testId="group-table-box">
                <GroupTable rows={rows} label={breakdown.label} />
              </Expandable>
            </div>
          </>
        ) : (
          <Unavailable what="The breakdown by group" />
        )}
      </section>

      <section className="mb-12">
        <SectionHeading title="Poverty" />
        <Explainer>
          <p>
            Share of people in households below the poverty line after housing costs. The absolute line rises with
            CPI; the relative line is 60% of the median household income in the same run, so when pensions fall
            the line falls too, and relative pensioner poverty can fall even as pensioners lose. PolicyEngine weights
            that median by household, where the official statistics weight it by person.
          </p>
        </Explainer>
        {poverty ? <PovertyTable poverty={poverty} labels={labels} /> : <Unavailable what="The poverty figures" plural />}
      </section>
    </div>
  );
}
