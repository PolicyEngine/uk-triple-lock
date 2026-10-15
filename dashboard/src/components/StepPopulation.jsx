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
import { formatBn, formatCurrency, formatPct, formatWeekly } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import { recordNotes, SavingChart } from "./PathCharts";
import { AXIS_STYLE, CardBox, CustomTooltip, Expandable, Panel, Section, Select, ShareGrid, Unavailable } from "./ui";

const METRIC_OPTIONS = [
  { id: "pct", label: "% of income" },
  { id: "gbp", label: "£ a year" },
];
const ORDERED = new Set(["by_decile"]);

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

/** The card's line on poverty: "no noticeable change" when every measure moves by under 0.15 points. */
function povertyDetail(poverty) {
  const moves = POVERTY_MEASURES.map((m) => poverty.burnham_2030[m.id] - poverty.triple_lock[m.id]);
  if (moves.every((d) => Number.isFinite(d) && Math.abs(d) < 0.15)) {
    return `${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under both rules: no noticeable change in poverty`;
  }
  return `${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under the triple lock`;
}

export default function StepPopulation({ data, records, trajectories, labels: policyLabels, pathId, onPath }) {
  const years = Array.isArray(data?.distribution_years) ? data.distribution_years : [];
  const [year, setYear] = useState(years.at(-1));
  const [breakdownId, setBreakdownId] = useState("by_decile");
  const [metric, setMetric] = useState("pct");
  const labels = policyLabels ?? { triple_lock: getPolicyLabel(data, "triple_lock"), burnham_2030: getPolicyLabel(data, "burnham_2030") };
  if (!records?.length || !years.length || !labels.triple_lock || !labels.burnham_2030) {
    return <Unavailable what="The household results" plural />;
  }
  const record = records.find((r) => r.id === pathId) ?? records[0];
  const run = record.run;
  const traj = trajectories?.find((t) => t.id === record.id);
  const notes = traj ? recordNotes(traj) : [];
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
        title="What the Burnham plan means for households"
        lead="One path, run for the whole survey: what the government saves against the triple lock and how many households lose."
        boxed={false}
      >
        <Panel footerTitle="How the population runs work" footer={<>
              <p>
                Each rule run through PolicyEngine UK for every survey household, recalculating State Pension, income
                tax and Pension Credit. Housing Benefit and council tax reduction respond only for existing claimants,
                which understates those offsets. Gross: the fall in State Pension spending. Net: what the government
                keeps after taxes and benefits respond.
              </p>
              {evLosing ? (
                <p data-testid="expected-losing">
                  Across all paths, {formatPct(evLosing.mean)} of households are worse off in {fyLabel(year)}.
                </p>
              ) : null}
          </>}>
        <div className="flex flex-wrap gap-6">
          <Select label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
          <Select label="Year" options={years.map((y) => ({ id: y, label: fyLabel(y) }))} value={year} onChange={setYear} />
        </div>
        </Panel>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <CardBox label={`Saving in ${fyLabel(year)}`} testId="card-pop-saving">
            {account ? (
              <>
                <div className="mt-3 space-y-3">
                  {[
                    { key: "gross", label: "Gross", note: "State Pension spending", value: account.gross, color: colors.primary[800], testId: "card-pop-gross" },
                    { key: "net", label: "Net", note: "after tax and benefits respond", value: account.net, color: colors.primary[300], testId: "card-pop-net" },
                  ].map((r) => (
                    <div key={r.key} data-testid={r.testId} title={`${r.label} (${r.note}): ${formatBn(r.value, 2)}`}>
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-slate-600">{r.label} <span className="text-xs text-slate-400">{r.note}</span></span>
                        <span className="font-semibold tabular-nums text-slate-900">{formatBn(r.value, 2)}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full" style={{ width: `${Math.max(0, (100 * r.value) / Math.max(account.gross, account.net, 1e-9))}%`, background: r.color }} />
                      </div>
                    </div>
                  ))}
                </div>
                {account.gross > 0 ? (
                  <span className="mt-auto self-start pt-3">
                    <span className="inline-block rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-900" data-testid="card-pop-share">
                      Net is {Math.round((100 * account.net) / account.gross)}% of gross
                    </span>
                  </span>
                ) : null}
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-500">unavailable</p>
            )}
          </CardBox>
          <CardBox label="Households worse off" testId="card-losing">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{affected ? formatPct(affected.losing) : "unavailable"}</p>
            {affected ? (
              <p className="mt-1 text-sm text-slate-600">
                Losing {formatCurrency(affected.meanLoss)} a year on average ({formatWeekly(affected.meanLoss / 52)} a week)
              </p>
            ) : null}
            {affected ? <ShareGrid pct={affected.losing} /> : null}
          </CardBox>
          <CardBox label="Pensioners in absolute poverty, after housing costs" testId="card-poverty">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
              {poverty ? formatPct(poverty.burnham_2030.pensioners_absolute_ahc) : "unavailable"}
            </p>
            {poverty ? <p className="mt-1 text-sm text-slate-600">{povertyDetail(poverty)}</p> : null}
          </CardBox>
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <Panel
            className="flex flex-col"
            footerTitle={notes.length === 1 ? `⚠ ${notes[0].title}` : "⚠ Single survey households drive some net figures"}
            footer={
              notes.length ? (
                <>
                  {notes.map((n) => (
                    <div key={n.key}>
                      {notes.length > 1 ? <p className="font-semibold text-slate-700">{n.title}</p> : null}
                      {n.body}
                    </div>
                  ))}
                </>
              ) : null
            }
          >
            <h3 className="mb-2 font-semibold text-slate-800">Saving each year on this path</h3>
            {traj ? <SavingChart traj={traj} grow /> : <Unavailable what="The yearly savings" plural />}
          </Panel>
          <Panel>
            <h3 className="mb-2 font-semibold text-slate-800">From gross to net</h3>
            {account ? <NetAccountTable account={account} year={year} /> : <Unavailable what="The net account" />}
          </Panel>
        </div>
      </Section>

      <Section id="groups" title="Change in household income by group" lead="Who loses most on this path, by income decile, household type, age, tenure and region.">
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

    </div>
  );
}
