"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import { POLICIES, fyLabel, getFinalYear, isNum } from "../lib/dataHelpers";
import { formatCurrency } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import SectionHeading from "./SectionHeading";
import { Card, ChartFrame } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Explainer, ToggleGroup, Unavailable } from "./ui";

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
      <SectionHeading title="4. What it means for one pensioner" />
      <Explainer>
        <p>
          Example pensioners run through PolicyEngine UK under both rules on the chosen path. A lower State Pension
          means less income tax for a pensioner above the personal allowance, more Pension Credit, Housing Benefit or
          council tax reduction for one entitled to them, and can bring a pensioner back under the Winter Fuel
          Payment&apos;s income threshold, so income falls by less than the pension. For a pensioner on the Pension
          Credit guarantee, Pension Credit counts income after income tax, so the extra Pension Credit and the lower
          tax bill together replace the whole loss.
        </p>
        <p>
          PolicyEngine UK then also raises such a pensioner&apos;s council tax reduction, which it tapers on income
          after tax without counting Pension Credit, so their income rises. That is a gap in the model: in England the
          regulations disregard all the income of anyone receiving the guarantee credit (SI 2012/2885, Schedule 1,
          paragraph 13), so their council tax reduction should not change and their income should stay the same.
        </p>
        <p className="text-xs text-slate-500">
          Each example gets the full flat-rate State Pension and claims everything it is entitled to; the renters
          claim Housing Benefit, which pensioners can claim afresh. (In the survey runs of step 5, only households
          already receiving Housing Benefit or council tax reduction see them respond.) Private pensions, rents and council tax are stated in 2026-27 terms and
          grow with the path&apos;s CPI. Each example is the stated age in every year: a pensioner of that age in each
          year, not one person ageing.
        </p>
      </Explainer>
      <div className="flex flex-wrap gap-6">
        <ToggleGroup label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
        <ToggleGroup label="Year" options={yearOptions} value={year} onChange={setYear} />
      </div>
      <div className="mt-4">
        <ToggleGroup label="Pensioner" options={examples.map((e) => ({ id: e.id, label: e.label }))} value={ex.id} onChange={setExampleId} />
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
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
      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 font-semibold text-slate-800">{ex.label}</h3>
          <AccountTable ex={ex} year={year} labels={labels} />
        </div>
        <div>
          <h3 className="mb-2 font-semibold text-slate-800">Each year on this path</h3>
          <YearChart ex={ex} years={years} />
        </div>
      </div>
    </div>
  );
}
