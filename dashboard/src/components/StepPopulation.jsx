"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { colors, SERIES } from "../lib/colors";
import {
  BREAKDOWNS,
  POVERTY_MEASURES,
  fyLabel,
  getBreakdown,
  getHouseholdsAffected,
  getPolicyLabel,
  getPoverty,
  isNum,
  pathsAreScenarios,
} from "../lib/dataHelpers";
import { formatBn, formatCurrency, formatPct } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import { recordNotes, SavingChart } from "./PathCharts";
import { AXIS_STYLE, BoxTitle, CardBox, CustomTooltip, HoverTip, Panel, Section, Select, ShareGrid, Unavailable, ViewSwitch } from "./ui";

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

/**
 * From gross to net for one year as a horizontal waterfall: the gross saving, each offset as a step (components that
 * round to zero are left to the table), and the net saving. Each bar is an invisible base plus a visible length.
 */
function NetWaterfall({ account }) {
  const steps = [
    ...account.rows.map((r) => ({ label: r.label, value: r.value })),
    { label: "Everything else", value: account.other },
  ].filter((r) => Math.abs(r.value) >= 0.005);
  let run = account.gross;
  const data = [
    { label: "Gross saving", base: 0, len: account.gross, value: account.gross, kind: "gross" },
    ...steps.map((r) => {
      const from = run;
      run += r.value;
      return { label: r.label, base: Math.min(from, run), len: Math.abs(r.value), value: r.value, kind: r.value < 0 ? "down" : "up" };
    }),
    { label: "Net saving", base: 0, len: account.net, value: account.net, kind: "net" },
  ];
  const fill = { gross: SERIES.gross, net: SERIES.net, down: SERIES.offset, up: SERIES.gain };
  const top = Math.max(...data.map((d) => d.base + d.len)) * 1.18;
  for (const d of data) {
    d.text = d.kind === "down" || d.kind === "up" ? `${d.value < 0 ? "−" : "+"}${formatBn(Math.abs(d.value), 2)}` : formatBn(d.value, 2);
  }
  return (
    <div style={{ width: "100%", height: 70 + 44 * data.length }} data-testid="net-waterfall">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 10, right: 70, left: 10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} horizontal={false} />
          <XAxis type="number" domain={[0, top]} tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, axisDigits([top]))} />
          <YAxis type="category" dataKey="label" width={190} tick={AXIS_STYLE} interval={0} />
          <Tooltip
            cursor={{ fill: colors.gray[100] }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload;
              return (
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg">
                  <div className="font-semibold text-slate-800">{d.label}</div>
                  <div className="text-slate-600">{formatBn(d.value, 2)}</div>
                </div>
              );
            }}
          />
          <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="len" stackId="w" isAnimationActive={false} radius={[0, 3, 3, 0]}>
            {data.map((d) => <Cell key={d.label} fill={fill[d.kind]} />)}
            <LabelList dataKey="text" position="right" fontSize={12} fill={colors.gray[700]} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const SAVING_VIEWS = [
  { id: "years", label: "Each year" },
  { id: "net", label: "From gross to net" },
];

function GroupChart({ rows, breakdownId, metric, label }) {
  const data = rows.map((r) => ({ label: r.label, value: metric === "gbp" ? r.mean : r.pct }));
  const digits = axisDigits(data.map((r) => r.value));
  const format = metric === "gbp" ? formatCurrency : (v) => formatPct(v, 2);
  const tickFormat = metric === "gbp" ? formatCurrency : (v) => formatPct(v, digits);
  if (!ORDERED.has(breakdownId)) data.sort((a, b) => a.value - b.value);
  const decile = breakdownId === "by_decile";
  const tickLabel = decile ? (l) => l.replace(/^Decile\s+/i, "") : shortLabel;
  const longest = Math.max(...data.map((r) => tickLabel(r.label).length));
  const tilt = !decile && (data.length > 6 || longest > 12);
  return (
    <>
      <div className={tilt ? "h-[420px]" : "h-[340px]"} data-testid="group-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: tilt ? 10 : 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
            <XAxis
              dataKey="label"
              tick={AXIS_STYLE}
              tickFormatter={tickLabel}
              interval={0}
              angle={tilt ? -35 : 0}
              textAnchor={tilt ? "end" : "middle"}
              height={tilt ? Math.min(150, 20 + longest * 5.5) : decile ? 46 : 30}
              label={decile ? { value: "Income decile (1 = lowest income)", position: "insideBottom", offset: 0, style: { ...AXIS_STYLE, fontSize: 12 } } : undefined}
            />
            <YAxis tick={AXIS_STYLE} tickFormatter={tickFormat} {...niceAxis(data.map((r) => r.value))} />
            <ReferenceLine y={0} stroke={SERIES.axis} />
            <Tooltip content={<CustomTooltip formatter={format} />} />
            <Bar dataKey="value" name={label} fill={SERIES.burnham} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartLogo />
    </>
  );
}

// The path whose poverty change puts any other path in context: the typical (median-saving) simulated path.
const TYPICAL_PATH = "monthly_p50";
const NOTICEABLE = 0.15; // points: a move smaller than this rounds to 0.1 or less

const pts = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}`;

/** The pensioner (absolute, relative) changes after housing costs, in points, Burnham plan minus triple lock. */
function pensionerMoves(poverty) {
  return {
    abs: poverty.burnham_2030.pensioners_absolute_ahc - poverty.triple_lock.pensioners_absolute_ahc,
    rel: poverty.burnham_2030.pensioners_relative_ahc - poverty.triple_lock.pensioners_relative_ahc,
  };
}

/**
 * The card's line on poverty, for the selected path, put in context: where this path shows no noticeable change
 * (every measure moves by under 0.15 points), it gives the typical path's change too, so a flat path is not read as
 * the overall finding.
 */
export function povertyDetail(poverty, typical, isTypical) {
  const moves = POVERTY_MEASURES.map((m) => poverty.burnham_2030[m.id] - poverty.triple_lock[m.id]);
  const here = pensionerMoves(poverty);
  if (moves.some((d) => Math.abs(d) >= NOTICEABLE)) {
    return `${pts(here.abs)} points under the Burnham plan on this path (${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under the triple lock); relative poverty ${pts(here.rel)} points.`;
  }
  const base = `${formatPct(poverty.triple_lock.pensioners_absolute_ahc)} under both rules: no noticeable change on this path.`;
  if (!typical || isTypical) return base;
  const t = pensionerMoves(typical);
  if (Math.abs(t.abs) < NOTICEABLE && Math.abs(t.rel) < NOTICEABLE) return `${base} The typical path shows no noticeable change either.`;
  return `${base} On the typical path, pensioner poverty after housing costs is ${pts(t.abs)} points (absolute) and ${pts(t.rel)} (relative) under the Burnham plan.`;
}

/** Pensioner absolute poverty after housing costs under each rule, as two thin bars on one scale, at the card's foot. */
function PovertyBars({ poverty, labels }) {
  const rows = [
    { key: "triple_lock", label: labels?.triple_lock ?? "Triple lock (current law)", value: poverty.triple_lock.pensioners_absolute_ahc, color: SERIES.tripleLock },
    { key: "burnham_2030", label: labels?.burnham_2030 ?? "Burnham plan", value: poverty.burnham_2030.pensioners_absolute_ahc, color: SERIES.burnham },
  ];
  const top = Math.max(...rows.map((r) => r.value), 1e-9) * 1.15;
  return (
    <div className="mt-auto space-y-2 pt-3" data-testid="poverty-bars">
      {rows.map((r) => (
        <HoverTip key={r.key} block className="rounded-md px-1 py-1 hover:bg-slate-50" tip={`${r.label}: ${formatPct(r.value)} of pensioners in absolute poverty after housing costs`}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-slate-600">{r.label}</span>
            <span className="font-semibold tabular-nums text-slate-900">{formatPct(r.value)}</span>
          </div>
          <div className="mt-1 h-2 rounded-full" style={{ background: SERIES.muted }}>
            <div className="h-2 rounded-full" style={{ width: `${(100 * r.value) / top}%`, background: r.color }} />
          </div>
        </HoverTip>
      ))}
    </div>
  );
}

export default function StepPopulation({ data, records, trajectories, labels: policyLabels, pathId, onPath }) {
  const years = Array.isArray(data?.distribution_years) ? data.distribution_years : [];
  const [year, setYear] = useState(years.at(-1));
  const [view, setView] = useState("years");
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
  // Without an expected value no path is typical, so a flat path's line gets no typical path's context.
  const scenarios = pathsAreScenarios(data);
  const typicalRecord = scenarios ? null : records.find((r) => r.id === TYPICAL_PATH);
  const typicalPoverty = typicalRecord ? getPoverty(typicalRecord.run, year) : null;
  const account = netAccount(run, year);
  const available = BREAKDOWNS.filter((b) => getBreakdown(run, year, b.id));
  const breakdown = available.find((b) => b.id === breakdownId) ?? available[0];
  const rows = breakdown ? getBreakdown(run, year, breakdown.id) : null;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-population">
      <Section
        id="everyone"
        title="What the Burnham plan means for households"
        lead="What the Burnham plan means for the government and household incomes on one path, against the triple lock (current law)."
        boxed={false}
      >
        <Panel footerTitle="How these figures are calculated" footer={
              <ul className="list-disc space-y-1 pl-5">
                <li><strong>One path.</strong>{" "}Figures are for the chosen path; {scenarios ? "no average over paths is shown, and the Budget impact tab compares scenarios." : "the Budget impact tab gives the average over all paths."}</li>
                <li><strong>Full model runs.</strong>{" "}Each rule runs through PolicyEngine UK for every survey household, recalculating the State Pension, income tax and Pension Credit.</li>
                <li><strong>Gross.</strong>{" "}The fall in State Pension spending.</li>
                <li><strong>Net.</strong>{" "}What the government keeps after tax and benefits respond.</li>
                <li><strong>One caveat.</strong>{" "}Housing Benefit and council tax reduction respond only for existing claimants, so the net saving is slightly overstated.</li>
              </ul>
          }>
        <p className="mb-3 text-sm text-slate-500">Pick the path and year the figures below are for.</p>
        <div className="flex flex-wrap gap-6">
          <Select label="Path" options={records.map((r) => ({ id: r.id, label: r.label }))} value={record.id} onChange={onPath} />
          <Select label="Year" options={years.map((y) => ({ id: y, label: fyLabel(y) }))} value={year} onChange={setYear} />
        </div>
        </Panel>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <CardBox label={`Saving on this path, ${fyLabel(year)}`} testId="card-pop-saving">
            {account ? (
              <>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{formatBn(account.gross, 2)}</p>
                <p className="mt-1 text-sm text-slate-600">
                  Gross; {formatBn(account.net, 2)} net of tax and benefits
                  {account.gross > 0 ? <span data-testid="card-pop-share"> (net is {Math.round((100 * account.net) / account.gross)}% of gross)</span> : null}
                </p>
                <div className="mt-auto space-y-2 pt-3">
                  {[
                    { key: "gross", label: "Gross", note: "State Pension spending", value: account.gross, color: SERIES.gross, testId: "card-pop-gross" },
                    { key: "net", label: "Net", note: "after tax and benefits respond", value: account.net, color: SERIES.net, testId: "card-pop-net" },
                  ].map((r) => (
                    <HoverTip key={r.key} block className="rounded-md px-1 py-1 hover:bg-slate-50" tip={r.key === "gross" ? `Gross: ${formatBn(r.value, 2)} less spent on the State Pension in ${fyLabel(year)}` : `Net: ${formatBn(r.value, 2)} kept by the government in ${fyLabel(year)} after more Pension Credit and other benefits and less income tax`}>
                    <div data-testid={r.testId}>
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-slate-600">{r.label} <span className="text-xs text-slate-400">{r.note}</span></span>
                        <span className="font-semibold tabular-nums text-slate-900">{formatBn(r.value, 2)}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full" style={{ width: `${Math.max(0, (100 * r.value) / Math.max(account.gross, account.net, 1e-9))}%`, background: r.color }} />
                      </div>
                    </div>
                    </HoverTip>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-500">unavailable</p>
            )}
          </CardBox>
          <CardBox label="Households worse off on this path" testId="card-losing">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{affected ? formatPct(affected.losing) : "unavailable"}</p>
            {affected ? (
              <p className="mt-1 text-sm text-slate-600">
                {formatCurrency(affected.meanLoss)} a year less income than under the triple lock, on average, on this path
              </p>
            ) : null}
            {affected ? <ShareGrid pct={affected.losing} /> : null}
            {affected && isNum(affected.gaining) ? (
              <p className="mt-2 text-sm text-slate-600" data-testid="card-gaining">
                {affected.gaining > 0
                  ? `${formatPct(affected.gaining)} are better off, by ${formatCurrency(affected.meanGain)} a year on average.`
                  : "No household is better off."}{" "}
                Both groups count a change of more than £1 a year.
              </p>
            ) : null}
          </CardBox>
          <CardBox label="Pensioners in absolute poverty, after housing costs" testId="card-poverty">
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
              {poverty ? formatPct(poverty.burnham_2030.pensioners_absolute_ahc) : "unavailable"}
            </p>
            {poverty ? <p className="mt-1 text-sm text-slate-600">{povertyDetail(poverty, typicalPoverty, !scenarios && record.id === TYPICAL_PATH)}</p> : null}
            {poverty ? <PovertyBars poverty={poverty} labels={policyLabels} /> : null}
          </CardBox>
        </div>
        <Panel
          className="mt-5"
          footers={[
            {
              title: "How to read this chart",
              content: (
                <p>
                  Gross is the fall in State Pension spending. Net is what the government keeps after the rest of the
                  system responds: lower pensions mean more Pension Credit and other benefits, and less income tax, so
                  the net saving is smaller.
                </p>
              ),
            },
            ...notes.map((n) => ({ title: `⚠ ${n.title}`, content: n.body })),
          ]}
        >
          <BoxTitle
            title={view === "years" ? "Saving each year on this path" : `From gross to net on this path, ${fyLabel(year)}`}
            description={view === "years"
              ? "How much less the government spends each year under the Burnham plan than under the triple lock (current law), before and after tax and benefits respond."
              : "How the saving on the State Pension shrinks as income tax falls and benefits rise."}
          >
            <ViewSwitch options={SAVING_VIEWS} value={view} onChange={setView} />
          </BoxTitle>
          {view === "years" ? (
            traj ? <SavingChart traj={traj} /> : <Unavailable what="The yearly savings" plural />
          ) : account ? (
            <>
              <NetWaterfall account={account} />
              <div className="mt-2 flex flex-wrap justify-center gap-5 text-xs text-slate-600">
                <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.gross }} />Gross saving</span>
                <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.offset }} />Offsets: extra benefits, less tax</span>
                <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SERIES.net }} />Net saving</span>
              </div>
            </>
          ) : (
            <Unavailable what="The net account" />
          )}
        </Panel>
      </Section>

      <Section id="groups" title="Change in household income by group" lead="How the change in household income from the Burnham plan, against the triple lock, differs between groups on this path." boxed={false}>
        {breakdown && rows ? (
          <Panel>
            <div className="flex flex-wrap gap-6">
              <Select label="Group by" options={available.map((b) => ({ id: b.id, label: b.label }))} value={breakdown.id} onChange={setBreakdownId} />
              <Select label="Show" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
            </div>
            <div className="mt-4">
              <GroupChart rows={rows} breakdownId={breakdown.id} metric={metric} label={labels.burnham_2030} />
            </div>
          </Panel>
        ) : (
          <Unavailable what="The breakdown by group" />
        )}
      </Section>

    </div>
  );
}
