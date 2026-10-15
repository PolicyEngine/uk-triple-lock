"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import { POLICIES, fyLabel, getFinalYear, isNum } from "../lib/dataHelpers";
import { formatCurrency } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { Card, ChartFrame } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Panel, Section, Select, Unavailable } from "./ui";

// Rows of the example's account; income tax is paid, so a fall in it adds to income.
export const ACCOUNT = [
  { key: "state_pension", label: "State Pension", sign: 1 },
  { key: "income_tax", label: "Income tax paid", sign: -1 },
  { key: "pension_credit", label: "Pension Credit", sign: 1 },
  { key: "housing_benefit", label: "Housing Benefit", sign: 1 },
  { key: "council_tax_reduction", label: "Council tax reduction", sign: 1 },
  { key: "winter_fuel_payment", label: "Winter Fuel Payment", sign: 1 },
];

/** The example households on one path's run, validated, or null. */
export function getExamples(run, years) {
  const h = run?.households;
  if (!h?.examples || !h?.results || !Array.isArray(years)) return null;
  const out = [];
  for (const [id, meta] of Object.entries(h.examples)) {
    const r = h.results[id];
    const ok = r && POLICIES.every((p) => [...ACCOUNT.map((a) => a.key), "net_income"].every((k) => years.every((y) => isNum(r[p]?.[k]?.[String(y)]))));
    if (!ok || typeof meta.label !== "string") return null;
    out.push({ id, label: meta.label, meta, value: (p, k, y) => r[p][k][String(y)] });
  }
  return out.length ? out : null;
}

function YearChart({ ex, years }) {
  const rows = years.map((y) => ({
    year: fyLabel(y),
    sp: ex.value("burnham_2030", "state_pension", y) - ex.value("triple_lock", "state_pension", y),
    net: ex.value("burnham_2030", "net_income", y) - ex.value("triple_lock", "net_income", y),
  }));
  return (
    <ChartFrame
      grow
      legend={[
        { label: "Change in State Pension", color: colorFor("burnham_2030") },
        { label: "Change in income after tax and benefits", color: colors.gray[700] },
      ]}
    >
      <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={formatCurrency} {...niceAxis(rows.flatMap((r) => [r.sp, r.net]))} />
        <ReferenceLine y={0} stroke={colors.gray[400]} />
        <Tooltip content={<CustomTooltip formatter={(v) => `${formatCurrency(v)} a year`} />} />
        <Bar dataKey="sp" name="Change in State Pension" fill={colorFor("burnham_2030")} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Line dataKey="net" name="Change in income after tax and benefits" stroke={colors.gray[700]} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
      </ComposedChart>
    </ChartFrame>
  );
}

function AccountTable({ ex, year, labels }) {
  const rows = [...ACCOUNT, { key: "net_income", label: "Income after tax and benefits", sign: 1 }];
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="account-table">
        <thead>
          <tr>
            <th>{fyLabel(year)}, £ a year</th>
            <th>{labels.triple_lock}</th>
            <th>{labels.burnham_2030}</th>
            <th>Effect on income</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const tl = ex.value("triple_lock", a.key, year);
            const bp = ex.value("burnham_2030", a.key, year);
            return (
              <tr key={a.key} className={a.key === "net_income" ? "font-semibold" : undefined}>
                <td>{a.label}</td>
                <td className="tabular-nums">{formatCurrency(tl)}</td>
                <td className="tabular-nums">{formatCurrency(bp)}</td>
                <td className="tabular-nums">{formatCurrency(a.sign * (bp - tl))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function StepPensioner({ data, records, labels, pathId, onPath }) {
  const years = data?.horizon;
  const final = getFinalYear(data);
  const record = records.find((r) => r.id === pathId) ?? records[0];
  const examples = getExamples(record?.run, years);
  const [exampleId, setExampleId] = useState(null);
  const [year, setYear] = useState(final);
  if (!examples || !final) return <Unavailable what="The example pensioners" plural />;
  const ex = examples.find((e) => e.id === exampleId) ?? examples[0];
  const sp = ex.value("burnham_2030", "state_pension", year) - ex.value("triple_lock", "state_pension", year);
  const net = ex.value("burnham_2030", "net_income", year) - ex.value("triple_lock", "net_income", year);
  const kept = sp < -0.5 ? net / sp : null;
  const yearOptions = [years.find((y) => y === 2034), final].filter(Boolean).map((y) => ({ id: y, label: fyLabel(y) }));
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-pensioner">
      <Section
        id="pensioner"
        title="What the Burnham plan means for one pensioner"
        lead="Four example pensioners on the chosen path: how much of the pension cut each one bears."
        boxed={false}
      >
      <Panel>
        <div className="flex flex-wrap gap-6">
          <Select label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
          <Select label="Year" options={yearOptions} value={year} onChange={setYear} />
          <Select label="Pensioner" options={examples.map((e) => ({ id: e.id, label: e.label }))} value={ex.id} onChange={setExampleId} />
        </div>
      </Panel>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <Card label="State Pension" value={`${formatCurrency(sp)} a year`} detail={`Under the Burnham plan, ${fyLabel(year)}`} testId="card-pensioner-sp" />
        <Card label="Income after tax and benefits" value={`${formatCurrency(net)} a year`} detail="The change the pensioner feels" testId="card-pensioner-net" />
        <Card
          label="Share of the pension loss the pensioner bears"
          value={kept === null ? "No loss" : kept <= 0 ? "None" : `${Math.round(100 * kept)}%`}
          detail={
            kept === null
              ? "The rules pay the same this year"
              : kept <= 0
                ? "Lower tax and more benefits more than replace the lost pension this year"
                : "The rest comes back through tax and benefits"
          }
          testId="card-pensioner-kept"
        />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Panel footerTitle="How tax and benefits soften the cut" footer={<>
            <p>
              A lower State Pension means less income tax, more Pension Credit, Housing Benefit or council tax reduction
              where entitled, and can restore the Winter Fuel Payment, so income falls by less than the pension. On the
              Pension Credit guarantee, extra credit and lower tax replace the whole cut; council tax reduction ignores
              their income (England: SI 2012/2885, Sch. 1, para. 13).
            </p>
            <p>
              The savings credit (60% of income above a threshold) falls with the pension, so the 90-year-old on the
              basic State Pension can still lose a little.
            </p>
            <p className="text-xs text-slate-500">
              Each example has the full flat-rate State Pension and claims everything it is entitled to, renters
              included. Private pensions, rents and council tax are in 2026-27 terms, growing with CPI. Ages are fixed:
              a pensioner of that age each year, not one person ageing.
            </p>
          </>}>
          <h3 className="mb-2 font-semibold text-slate-800">{ex.label}</h3>
          <AccountTable ex={ex} year={year} labels={labels} />
        </Panel>
        <Panel className="flex flex-col">
          <h3 className="mb-2 font-semibold text-slate-800">Each year on this path</h3>
          <YearChart ex={ex} years={years} />
        </Panel>
      </div>
      </Section>
    </div>
  );
}
