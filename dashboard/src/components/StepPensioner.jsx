"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { colors, SERIES } from "../lib/colors";
import { POLICIES, fyLabel, getFinalYear, isNum } from "../lib/dataHelpers";
import { formatCurrency } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { ChartFrame } from "./PathCharts";
import { AXIS_STYLE, BoxTitle, CardBox, CustomTooltip, HoverTip, Panel, Section, Select, Unavailable, ViewSwitch } from "./ui";

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
        { label: "Change in State Pension", color: SERIES.gross },
        { label: "Change in income after tax and benefits", color: SERIES.net },
      ]}
    >
      <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={formatCurrency} {...niceAxis(rows.flatMap((r) => [r.sp, r.net]))} />
        <ReferenceLine y={0} stroke={SERIES.axis} />
        <Tooltip content={<CustomTooltip formatter={(v) => `${formatCurrency(v)} a year`} />} />
        <Bar dataKey="sp" name="Change in State Pension" fill={SERIES.gross} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Line dataKey="net" name="Change in income after tax and benefits" stroke={SERIES.net} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
      </ComposedChart>
    </ChartFrame>
  );
}

// Short button labels for the four examples (the file's own label is the hover text and the fallback).
const SHORT = {
  owner: "Aged 70, State Pension only, owns home",
  private_pension: "Aged 70, £15,000 private pension, owns home",
  social_renter: "Aged 70, State Pension only, council tenant",
  basic_renter: "Aged 90, old basic State Pension, council tenant",
};
const VIEWS = [
  { id: "item", label: "This year, item by item" },
  { id: "years", label: "Each year" },
];
// What each account row does to income, worded by direction ("Lower income tax", "More Pension Credit").
const MOVE = {
  income_tax: (v) => (v >= 0 ? "Lower income tax" : "Higher income tax"),
  pension_credit: (v) => (v >= 0 ? "More Pension Credit" : "Less Pension Credit"),
  housing_benefit: (v) => (v >= 0 ? "More Housing Benefit" : "Less Housing Benefit"),
  council_tax_reduction: (v) => (v >= 0 ? "More council tax reduction" : "Less council tax reduction"),
  winter_fuel_payment: (v) => (v >= 0 ? "Winter Fuel Payment restored" : "Less Winter Fuel Payment"),
};

/** Each row's effect on income this year (plan minus triple lock, income tax counted as a fall in tax paid). */
function effects(ex, year) {
  return ACCOUNT.map((a) => ({ ...a, value: a.sign * (ex.value("burnham_2030", a.key, year) - ex.value("triple_lock", a.key, year)) }));
}

/** How much of the lower State Pension tax and benefits make up, from unrounded figures. */
function offsetText(sp, net) {
  if (sp > -0.5) return { value: "No change", share: null, detail: "The two rules pay the same State Pension this year." };
  const share = 1 - net / sp; // 1 = all of the lower pension made up
  const pct = Math.round(100 * share);
  const words = share > 1.005 ? "More than all of it" : share >= 0.995 ? "All of it" : share >= 0.9 ? "Almost all of it" : `${pct}%`;
  return { value: words, share, detail: `Tax and benefits make up ${pct}% of the ${formatCurrency(-sp)} lower State Pension.` };
}

/** This year's change in income as a waterfall: the lower State Pension, then each offset, ending at the net change. */
function ItemWaterfall({ ex, year }) {
  const rows = effects(ex, year);
  const sp = rows[0].value;
  const net = ex.value("burnham_2030", "net_income", year) - ex.value("triple_lock", "net_income", year);
  const steps = [];
  for (const r of rows.slice(1).filter((x) => Math.abs(x.value) >= 0.5)) {
    const from = sp + steps.reduce((a, d) => a + d.value, 0);
    steps.push({ label: MOVE[r.key](r.value), value: r.value, range: [Math.min(from, from + r.value), Math.max(from, from + r.value)], kind: "offset" });
  }
  const data = [
    { label: "State Pension", value: sp, range: [Math.min(0, sp), Math.max(0, sp)], kind: "pension" },
    ...steps,
    { label: "Change in income", value: net, range: [Math.min(0, net), Math.max(0, net)], kind: "net" },
  ];
  for (const d of data) d.text = Math.round(Math.abs(d.value)) === 0 ? "£0" : `${d.value > 0 ? "+" : "−"}${formatCurrency(Math.abs(d.value))}`;
  const fill = { pension: SERIES.gross, offset: SERIES.offset, net: SERIES.net };
  const axis = niceAxis([0, ...data.flatMap((d) => d.range)]);
  // A change that rounds to nothing still gets a sliver, so its bar and label show.
  const sliver = (axis.domain[1] - axis.domain[0]) * 0.006;
  for (const d of data) if (d.range[1] - d.range[0] < sliver) d.range = [d.range[0] - sliver / 2, d.range[1] + sliver / 2];
  return (
    <>
      <div style={{ width: "100%", height: 70 + 44 * data.length }} data-testid="pensioner-waterfall">
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 10, right: 60, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} horizontal={false} />
            <XAxis type="number" {...axis} tick={AXIS_STYLE} tickFormatter={formatCurrency} />
            <YAxis type="category" dataKey="label" width={190} tick={AXIS_STYLE} interval={0} />
            <ReferenceLine x={0} stroke={SERIES.axis} />
            <Tooltip
              cursor={{ fill: colors.gray[100] }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg">
                    <div className="font-semibold text-slate-800">{d.label}</div>
                    <div className="text-slate-600">{d.text} a year in {fyLabel(year)}</div>
                  </div>
                );
              }}
            />
            <Bar dataKey="range" isAnimationActive={false} radius={3}>
              {data.map((d) => <Cell key={d.label} fill={fill[d.kind]} />)}
              <LabelList dataKey="text" position="right" fontSize={12} fill={colors.gray[700]} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-5 text-xs text-slate-600">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.gross }} />Lower State Pension</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.offset }} />Offsets: tax and benefits</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.net }} />Change in income</span>
      </div>
    </>
  );
}

export default function StepPensioner({ data, records, labels, pathId, onPath }) {
  const years = data?.horizon;
  const final = getFinalYear(data);
  const record = records.find((r) => r.id === pathId) ?? records[0];
  const examples = getExamples(record?.run, years);
  const [exampleId, setExampleId] = useState(null);
  const [year, setYear] = useState(final);
  const [view, setView] = useState("item");
  if (!examples || !final) return <Unavailable what="The example pensioners" plural />;
  const ex = examples.find((e) => e.id === exampleId) ?? examples[0];
  const tl = ex.value("triple_lock", "state_pension", year);
  const bp = ex.value("burnham_2030", "state_pension", year);
  const sp = bp - tl;
  const net = ex.value("burnham_2030", "net_income", year) - ex.value("triple_lock", "net_income", year);
  const offsets = effects(ex, year).slice(1).filter((r) => Math.abs(r.value) >= 0.5);
  const off = offsetText(sp, net);
  const max = Math.max(tl, bp) || 1;
  const fy = fyLabel(year);
  const yearOptions = [years.find((y) => y === 2034), final].filter(Boolean).map((y) => ({ id: y, label: fyLabel(y) }));
  // Under 50p rounds to £0, shown without a sign.
  const signed = (v) => (Math.abs(v) < 0.5 ? "£0" : `${v > 0 ? "+" : "−"}${formatCurrency(Math.abs(v))}`);
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-pensioner">
      <Section
        id="pensioner"
        title="What the Burnham plan means for one pensioner"
        lead="How the Burnham plan changes the income of four example pensioners on the chosen path, after tax and benefits respond."
        boxed={false}
      >
        <Panel>
          <div className="flex flex-wrap gap-6">
            <Select label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
            <Select label="Year" options={yearOptions} value={year} onChange={setYear} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label="Pensioner" data-testid="pensioner-buttons">
            {examples.map((e) => {
              const on = e.id === ex.id;
              return (
                <button
                  key={e.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  title={e.label}
                  onClick={() => setExampleId(e.id)}
                  className={`rounded-xl border px-3 py-2 text-left text-sm transition-colors ${on ? "border-teal-600 bg-teal-50 font-semibold text-teal-900 shadow-sm" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"}`}
                >
                  {SHORT[e.id] ?? e.label}
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-sm text-slate-700" data-testid="pensioner-label">{ex.label}.</p>
        </Panel>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <CardBox label={`State Pension, ${fy}`} testId="card-pensioner-sp">
            <div className="mt-3 space-y-2">
              {[
                { key: "tl", label: labels.triple_lock, v: tl, color: SERIES.tripleLock },
                { key: "bp", label: labels.burnham_2030, v: bp, color: SERIES.burnham },
              ].map((r) => (
                <HoverTip key={r.key} block className="rounded-md px-1 py-1 hover:bg-slate-50" tip={`${r.label}: ${formatCurrency(r.v)} a year in ${fy}`}>
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="text-slate-600">{r.label}</span>
                    <span className="font-semibold tabular-nums text-slate-900">{formatCurrency(r.v)} a year</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-slate-100">
                    <div className="h-2 rounded-full" style={{ width: `${(100 * r.v) / max}%`, background: r.color }} />
                  </div>
                </HoverTip>
              ))}
            </div>
            <span className="mt-auto self-start pt-3">
              <HoverTip tip={`${formatCurrency(Math.abs(sp))} a year ${sp < 0 ? "less" : "more"} under the Burnham plan`}>
                <span className="inline-block rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-900 hover:bg-teal-100">
                  {Math.abs(sp) < 0.5 ? "The same" : `${signed(sp)} a year`}
                </span>
              </HoverTip>
            </span>
          </CardBox>
          <CardBox label={`Change in income after tax and benefits, ${fy}`} testId="card-pensioner-net">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{signed(net)} a year</p>
            <p className="mt-1 text-sm text-slate-600">Change under the Burnham plan, {fy}</p>
            {offsets.length ? (
              <ul className="mt-3 space-y-1 text-sm">
                <li className="text-xs uppercase tracking-wide text-slate-500">Of which, making up the lower pension</li>
                {offsets.map((r) => (
                  <li key={r.key} className="flex justify-between gap-3">
                    <span className="text-slate-600">{MOVE[r.key](r.value)}</span>
                    <span className="tabular-nums font-medium text-slate-900">{signed(r.value)}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardBox>
          <CardBox label="Share of the lower pension made up" testId="card-pensioner-kept">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{off.value}</p>
            <p className="mt-1 text-sm text-slate-600">{off.detail}</p>
            {off.share !== null ? (
              <HoverTip block className="mt-auto pt-4" tip={`Made up by tax and benefits: ${Math.round(100 * off.share)}%. Borne by the pensioner: ${Math.max(0, 100 - Math.round(100 * off.share))}%.`}>
                <div className="h-2.5 rounded-full" style={{ background: SERIES.muted }}>
                  <div className="h-2.5 rounded-full" style={{ width: `${Math.min(100, Math.max(0, 100 * off.share))}%`, background: SERIES.gain }} />
                </div>
                <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>0%</span><span>100%</span></div>
              </HoverTip>
            ) : null}
          </CardBox>
        </div>

        <Panel
          className="mt-5"
          footers={[
            {
              title: "How to read this",
              content: (
                <>
                  <p>
                    A lower State Pension means less income tax and, where the pensioner is entitled, more Pension Credit,
                    Housing Benefit or council tax reduction, so income falls by less than the pension. On the Pension
                    Credit guarantee, extra credit and lower tax can make up all of it; council tax reduction then ignores
                    their income (England: SI 2012/2885, Sch. 1, para. 13).
                  </p>
                  <p>
                    The savings credit falls as income rises, so a pensioner on the old basic State Pension can still see
                    a small fall.
                  </p>
                  <p className="text-xs text-slate-500">
                    Each example has the full flat-rate State Pension and claims everything it is entitled to. Private
                    pensions, rents and council tax are in 2026-27 terms, growing with CPI. Ages are fixed: a pensioner of
                    that age each year, not one person ageing.
                  </p>
                </>
              ),
            },
          ]}
        >
          <BoxTitle
            title={view === "item" ? `How the change in income adds up, ${fy}` : "Change in income each year on this path"}
            description={view === "item"
              ? "How the lower State Pension, income tax and benefits add up to the change in this pensioner's income."
              : "This pensioner's change in State Pension and in income after tax and benefits, against the triple lock (current law)."}
          >
            <ViewSwitch options={VIEWS} value={view} onChange={setView} />
          </BoxTitle>
          {view === "item" ? <ItemWaterfall ex={ex} year={year} /> : <YearChart ex={ex} years={years} />}
        </Panel>
      </Section>
    </div>
  );
}
