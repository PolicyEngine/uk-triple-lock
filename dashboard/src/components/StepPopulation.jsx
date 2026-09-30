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
  isNum,
} from "../lib/dataHelpers";
import { formatBn, formatCurrency, formatPct, formatPoints } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import { Card, ConcentrationYears, LargestHouseholdFlag, SavingChart } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Expandable, Panel, Section, Select, Unavailable } from "./ui";

const METRIC_OPTIONS = [
  { id: "pct", label: "% of income" },
  { id: "gbp", label: "£ a year" },
];
const ORDERED = new Set(["by_decile", "by_quintile"]);

function shortLabel(label) {
  return label.length > 28 ? `${label.slice(0, 26)}…` : label;
}

// Where the gross saving goes: each component is (plan - triple lock), so extra benefit spending reduces the
// saving and lower income tax reduces it too.
export const NET_ACCOUNT = [
  { key: "pension_credit", label: "Extra Pension Credit" },
  { key: "housing_benefit", label: "Extra Housing Benefit" },
  { key: "council_tax_reduction", label: "Extra council tax reduction" },
  { key: "universal_credit", label: "Extra Universal Credit" },
  { key: "winter_fuel_payment", label: "Extra Winter Fuel Payment" },
  { key: "income_tax", label: "Less income tax", tax: true },
];

export function netAccount(run, year) {
  const s = run?.saving_bn?.[String(year)];
  if (!s || !isNum(s.gross) || !isNum(s.net) || !s.components) return null;
  const rows = NET_ACCOUNT.map((a) => ({ ...a, value: a.tax ? s.components[a.key] : -s.components[a.key] }));
  if (!rows.every((r) => isNum(r.value))) return null;
  const other = s.net - s.gross - rows.reduce((t, r) => t + r.value, 0);
  return { gross: s.gross, net: s.net, rows, other };
}

function NetAccountTable({ account, year }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="net-account">
        <thead>
          <tr>
            <th>{fyLabel(year)}</th>
            <th>£ billion</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Saving on the basic and new State Pension (gross)</td>
            <td className="tabular-nums">{formatBn(account.gross, 2)}</td>
          </tr>
          {account.rows.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td className="tabular-nums">{formatBn(r.value, 2)}</td>
            </tr>
          ))}
          <tr>
            <td>Everything else (other taxes and benefits)</td>
            <td className="tabular-nums">{formatBn(account.other, 2)}</td>
          </tr>
          <tr className="font-semibold">
            <td>Saving to the government (net)</td>
            <td className="tabular-nums">{formatBn(account.net, 2)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function GroupChart({ rows, breakdownId, metric, label }) {
  const data = rows.map((r) => ({ label: r.label, value: metric === "gbp" ? r.mean : r.pct }));
  const digits = axisDigits(data.map((r) => r.value));
  const format = metric === "gbp" ? formatCurrency : (v) => formatPct(v, 2);
  const tickFormat = metric === "gbp" ? formatCurrency : (v) => formatPct(v, digits);
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
            <YAxis tick={AXIS_STYLE} tickFormatter={tickFormat} {...niceAxis(data.map((r) => r.value))} />
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
              <td className="tabular-nums">{formatPoints(poverty.burnham_2030[m.id] - poverty.triple_lock[m.id])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function StepPopulation({ data, records, trajectories, labels: policyLabels, pathId, onPath }) {
  const years = Array.isArray(data?.distribution_years) ? data.distribution_years : [];
  const [year, setYear] = useState(years.at(-1));
  const [breakdownId, setBreakdownId] = useState("by_quintile");
  const [metric, setMetric] = useState("pct");
  const labels = policyLabels ?? { triple_lock: getPolicyLabel(data, "triple_lock"), burnham_2030: getPolicyLabel(data, "burnham_2030") };
  if (!records?.length || !years.length || !labels.triple_lock || !labels.burnham_2030) {
    return <Unavailable what="The household results" plural />;
  }
  const record = records.find((r) => r.id === pathId) ?? records[0];
  const run = record.run;
  const traj = trajectories?.find((t) => t.id === record.id);
  const affected = getHouseholdsAffected(run, year);
  const poverty = getPoverty(run, year);
  const account = netAccount(run, year);
  const available = BREAKDOWNS.filter((b) => getBreakdown(run, year, b.id));
  const breakdown = available.find((b) => b.id === breakdownId) ?? available[0];
  const rows = breakdown ? getBreakdown(run, year, breakdown.id) : null;
  const ev = getExpectedValue(data);
  const evLosing = ev?.losing ? ev.losing[ev.years.indexOf(year)] : null;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-population">
      <Section
        id="everyone"
        title="What it means for households"
        lead="Who loses under the plan. The chosen path run for the whole survey population: what the government saves and how many households lose."
        boxed={false}
      >
        <Panel footerTitle="How the population runs work" footer={<>
              <p>
                The same path run through PolicyEngine UK for the whole survey population, once under each rule: every
                pensioner&apos;s State Pension recalculated, and with it their income tax and Pension Credit. Housing
                Benefit and council tax reduction respond only for households already receiving them in the survey; nobody
                newly entitled starts claiming, which understates those offsets. The gross saving is the fall in spending
                on the basic and new State Pension; the net saving is what the government keeps once taxes and other
                benefits respond.
              </p>
              {evLosing ? (
                <p data-testid="expected-losing">
                  Averaged over all the paths behind the expected saving, {formatPct(evLosing.mean)} of households
                  have a lower income under the plan in {fyLabel(year)}.
                </p>
              ) : null}
          </>}>
        <div className="flex flex-wrap gap-6">
          <Select label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
          <Select label="Year" options={years.map((y) => ({ id: y, label: fyLabel(y) }))} value={year} onChange={setYear} />
        </div>
        </Panel>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card label={`Gross saving, ${fyLabel(year)}`} value={account ? formatBn(account.gross, 2) : "unavailable"} detail="State Pension spending" testId="card-pop-gross" />
          <Card label="Net saving" value={account ? formatBn(account.net, 2) : "unavailable"} detail="After taxes and other benefits respond" testId="card-pop-net" />
          <Card
            label="Households with lower income"
            value={affected ? formatPct(affected.losing) : "unavailable"}
            detail={affected ? `Losing ${formatCurrency(affected.meanLoss)} a year on average` : null}
            testId="card-losing"
          />
          <Card
            label="Pensioners in absolute poverty, after housing costs"
            value={poverty ? formatPct(poverty.burnham_2030.pensioners_absolute_ahc) : "unavailable"}
            detail={poverty ? `${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under the triple lock` : null}
            testId="card-poverty"
          />
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <Panel>
            <h3 className="mb-2 font-semibold text-slate-800">Saving each year on this path</h3>
            {traj ? <SavingChart traj={traj} /> : <Unavailable what="The yearly savings" plural />}
          </Panel>
          <Panel>
            <h3 className="mb-2 font-semibold text-slate-800">From gross to net</h3>
            {account ? <NetAccountTable account={account} year={year} /> : <Unavailable what="The net account" />}
          </Panel>
        </div>
        {traj ? (
          <>
            <LargestHouseholdFlag traj={traj} year={traj.rows.at(-1).year} />
            <ConcentrationYears traj={traj} />
          </>
        ) : null}
      </Section>

      <Section id="groups" title="Change in household income by group" lead="Which households lose most on the chosen path, by income, type, age, tenure and region.">
        {breakdown && rows ? (
          <>
            <div className="flex flex-wrap gap-6">
              <Select label="Group by" options={available.map((b) => ({ id: b.id, label: b.label }))} value={breakdown.id} onChange={setBreakdownId} />
              <Select label="Show" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
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
      </Section>

      <Section
        id="poverty"
        title="Poverty"
        lead="Share of people below the poverty line after housing costs, under each rule."
        detailsTitle="How the poverty lines work"
        details={
          <>
              <p>
                Share of people in households below the poverty line after housing costs. The absolute line rises with
                CPI; the relative line is 60% of the median household income in the same run, so when pensions fall
                the line falls too, and relative pensioner poverty can fall even as pensioners lose. PolicyEngine weights
                that median by household, where the official statistics weight it by person.
              </p>
          </>
        }
      >
        {poverty ? <PovertyTable poverty={poverty} labels={labels} /> : <Unavailable what="The poverty figures" plural />}
      </Section>
    </div>
  );
}
