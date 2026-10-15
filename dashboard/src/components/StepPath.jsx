"use client";

import { useState } from "react";
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import { fyLabel, getExpectedValue, getSwitchYear } from "../lib/dataHelpers";
import { formatWeekly, ordinal } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { differenceNotes, pickText } from "../lib/trajectoryHelpers";
import { AllPathsTable, ChartFrame, InputsChart, RisesChart, YearTable } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Panel, Section, Select, Unavailable, ViewSwitch } from "./ui";

const INDEX_SERIES = (labels) => [
  { key: "triple_lock", label: labels.triple_lock, color: colorFor("triple_lock"), width: 3 },
  { key: "burnham_2030", label: labels.burnham_2030, color: colorFor("burnham_2030"), width: 3 },
  { key: "earnings", label: "Earnings alone", color: colors.primary[300], width: 2, dashed: true },
  { key: "cpi", label: "CPI alone", color: colors.gray[400], width: 2, dashed: true },
];

/** Cumulative levels from the path's rows, 2026-27 = 100. */
export function pathIndex(traj) {
  let tl = 100;
  let bp = 100;
  let e = 100;
  let c = 100;
  const rows = [{ year: fyLabel(traj.rows[0].year - 1), triple_lock: 100, burnham_2030: 100, earnings: 100, cpi: 100 }];
  for (const r of traj.rows) {
    tl *= 1 + r.tlRate;
    bp *= 1 + r.bpRate;
    e *= 1 + r.earnings;
    c *= 1 + r.cpi;
    rows.push({ year: fyLabel(r.year), triple_lock: tl, burnham_2030: bp, earnings: e, cpi: c });
  }
  return rows;
}

function IndexChart({ traj, labels }) {
  const rows = pathIndex(traj);
  const series = INDEX_SERIES(labels);
  return (
    <ChartFrame legend={series.map((s) => ({ label: s.label, color: s.color, dashed: s.dashed }))}>
      <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} {...niceAxis(rows.flatMap((r) => series.map((s) => r[s.key])), { includeZero: false })} />
        <Tooltip content={<CustomTooltip formatter={(v) => v.toFixed(1)} />} />
        {series.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={s.width} strokeDasharray={s.dashed ? "5 4" : undefined} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

/** One path through the rules: what sets each rise, the rises, and where the levels end up. */
const RISE_VIEWS = [
  { id: "inputs", label: "What sets each rise" },
  { id: "rises", label: "The rise under each rule" },
];

/** The path's April rises in one chart: the three figures the triple lock reads, or the rise each rule gives. */
function RisesPanel({ traj, labels }) {
  const [view, setView] = useState("inputs");
  return (
    <div data-testid="path-rises-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-800">{view === "inputs" ? "What sets each April\u2019s rise" : "The April rise under each rule"}</h3>
          <p className="mb-3 mt-1 text-sm text-slate-500">
            {view === "inputs"
              ? "The triple lock takes the highest of September CPI, May–July earnings growth and 2.5%."
              : "The rules part in years when the plan waits for earnings to catch up."}
          </p>
        </div>
        <ViewSwitch options={RISE_VIEWS} value={view} onChange={setView} />
      </div>
      {view === "inputs" ? <InputsChart traj={traj} /> : <RisesChart traj={traj} labels={labels} />}
    </div>
  );
}

const SOURCE_STYLE = {
  earnings: { label: "earnings", color: colors.primary[600] },
  cpi: { label: "CPI", color: colors.gray[500] },
  floor: { label: "2.5% floor", color: colors.primary[200] },
};

function CardBox({ label, testId, children }) {
  return (
    <div className="metric-card flex flex-col" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      {children}
    </div>
  );
}

/** The full new State Pension in the final year under each rule, as two bars on one scale, and the gap. */
function PensionCard({ last, labels }) {
  const rows = [
    { key: "tl", label: "Triple lock (current law)", value: last.tlWeekly, color: colors.primary[800], testId: "card-tl-weekly" },
    { key: "bp", label: labels.burnham_2030 ?? "Burnham plan", value: last.bpWeekly, color: colors.primary[300], testId: "card-bp-weekly" },
  ];
  const max = Math.max(...rows.map((r) => r.value));
  const diff = last.bpWeekly - last.tlWeekly;
  const pct = (100 * diff) / last.tlWeekly;
  const same = Math.abs(diff) < 0.005;
  return (
    <CardBox label={`Full new State Pension, ${fyLabel(last.year)}`} testId="card-pension">
      <div className="mt-3 space-y-3">
        {rows.map((r) => (
          <div key={r.key} data-testid={r.testId} title={`${r.label}: ${formatWeekly(r.value)} a week`}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-slate-600">{r.label}</span>
              <span className="font-semibold tabular-nums text-slate-900">{formatWeekly(r.value)} a week</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full" style={{ width: `${(100 * r.value) / max}%`, background: r.color }} />
            </div>
          </div>
        ))}
      </div>
      <span className="mt-auto self-start pt-3">
        <span className="inline-block rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-900" data-testid="card-gap">
          {same ? "The same" : `${diff < 0 ? "−" : "+"}${formatWeekly(Math.abs(diff))} a week (${diff < 0 ? "−" : "+"}${Math.abs(pct).toFixed(1)}%)`}
        </span>
      </span>
    </CardBox>
  );
}

/** Which figure set the triple lock's rise each April from the switch: one stacked bar of the Aprils. */
function BindingCard({ after, counts, switchYear }) {
  const order = ["earnings", "floor", "cpi"].sort((a, b) => counts[b] - counts[a]);
  return (
    <CardBox label={`What set each rise from April ${switchYear} (triple lock)`} testId="card-binding">
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {counts[order[0]]} of {after.length} <span className="text-base font-medium text-slate-600">by {SOURCE_STYLE[order[0]].label}</span>
      </p>
      <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-slate-100">
        {after.map((r) => (
          <span
            key={r.year}
            className="h-full flex-1 border-r border-white last:border-r-0"
            style={{ background: SOURCE_STYLE[r.tlSource]?.color }}
            title={`April ${r.year}: ${SOURCE_STYLE[r.tlSource]?.label}`}
          />
        ))}
      </div>
      <div className="mt-auto flex flex-wrap gap-x-3 gap-y-1 pt-3 text-xs text-slate-600">
        {order.map((k) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SOURCE_STYLE[k].color }} />
            {SOURCE_STYLE[k].label[0].toUpperCase() + SOURCE_STYLE[k].label.slice(1)} {counts[k]}
          </span>
        ))}
      </div>
    </CardBox>
  );
}

/** How many Aprils the two rules give different rises, with one dot per April from the switch. */
function DifferCard({ after, notes }) {
  const differ = new Set(notes.map((n) => n.year));
  return (
    <CardBox label="Years the rules differ" testId="card-differ">
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {notes.length} <span className="text-base font-medium text-slate-600">of {after.length}</span>
      </p>
      <p className="mt-1 text-sm text-slate-600">{notes.length ? `First in April ${notes[0].year}` : "The same rise every year"}</p>
      <div className="mt-auto flex justify-between gap-1 pt-3">
        {after.map((r) => (
          <span key={r.year} className="flex flex-col items-center gap-1" title={`April ${r.year}: ${differ.has(r.year) ? "the rules differ" : "the same rise"}`}>
            <span className={`h-3 w-3 rounded-full ${differ.has(r.year) ? "bg-teal-700" : "border border-slate-300 bg-white"}`} />
            <span className="text-[10px] tabular-nums text-slate-400">{String(r.year).slice(2)}</span>
          </span>
        ))}
      </div>
    </CardBox>
  );
}

export function PathView({ traj, labels, switchYear, footer }) {
  const last = traj.rows.at(-1);
  const notes = differenceNotes(traj);
  const after = traj.rows.filter((r) => r.year >= (switchYear ?? 2030));
  const counts = { earnings: 0, cpi: 0, floor: 0 };
  for (const r of after) counts[r.tlSource] += 1;
  return (
    <>
      <div id="path-pension" className="grid scroll-mt-24 gap-4 lg:grid-cols-3">
        <PensionCard last={last} labels={labels} />
        <BindingCard after={after} counts={counts} switchYear={switchYear ?? 2030} />
        <DifferCard after={after} notes={notes} />
      </div>
      <Panel id="path-rises" className="mt-5">
        <RisesPanel traj={traj} labels={labels} />
      </Panel>
      <Panel
        id="path-level"
        className="mt-5"
        footers={[
          {
            title: "How to read this chart",
            content: (
              <>
                <div data-testid="path-notes">
                  <p className="font-semibold text-slate-800">Where the rules differ</p>
                  {notes.length ? (
                    <ul className="list-disc space-y-1 pl-5 text-slate-700">
                      {notes.map((n) => (
                        <li key={n.year}>{n.text}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-700">The two rules give the same rise every year on this path.</p>
                  )}
                </div>
                {footer}
              </>
            ),
          },
          { title: "Year by year", testId: "path-table-box", content: <YearTable traj={traj} labels={labels} /> },
        ]}
      >
        <h3 className="font-semibold text-slate-800">The pension&apos;s level (2026-27 = 100)</h3>
        <p className="mb-3 mt-1 text-sm text-slate-500">Where those rises leave the pension under each rule, against earnings alone and prices alone.</p>
        <IndexChart traj={traj} labels={labels} />
      </Panel>
    </>
  );
}

export function StepCentral({ data, trajectories, labels }) {
  const traj = trajectories?.find((t) => t.id === "central");
  const switchYear = getSwitchYear(data);
  if (!traj) return <Unavailable what="The central forecast path" />;
  const sw = switchYear ?? 2030;
  const floorYears = traj.rows.filter((r) => r.tlSource === "floor").map((r) => r.year);
  const floorAfter = floorYears.filter((y) => y >= sw);
  const cpiAfter = traj.rows.filter((r) => r.year >= sw && r.tlSource === "cpi").map((r) => r.year);
  const firstEarnings = traj.rows.find((r) => r.year >= sw && r.tlSource === "earnings");
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-central">
      <Section
        id="central"
        title="Burnham plan vs triple lock"
        lead="The OBR's forecast under both rules: earnings lead almost every year, so the rules barely differ."
        boxed={false}
      >
        <PathView traj={traj} labels={labels} switchYear={switchYear} footer={<p>
            The OBR&apos;s March 2026 forecast to 2030, then its long-term assumptions (CPI 2%, earnings about 3.7%);
            April 2027 uses May–July 2026 earnings and August 2026 CPI.
            {floorYears.length
              ? ` Earnings grow by less than 2.5% for a few years, so the floor sets the triple lock in April ${floorYears.join(", ")}.`
              : ""}
            {firstEarnings ? ` From April ${firstEarnings.year} earnings lead every year.` : ""}
            {floorAfter.length || cpiAfter.length
              ? ` After April ${sw} the floor or CPI sets the triple lock in ${[...floorAfter, ...cpiAfter].sort().join(", ")}; the plan then rises only by CPI or 2.5% until earnings catch up. That, and rounding, is the whole difference.`
              : " With no floor or CPI years after the switch, only rounding separates the rules."}
          </p>} />
      </Section>
    </div>
  );
}

function Chip({ children, title, testId }) {
  return (
    <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-700" title={title} data-testid={testId}>
      {children}
    </span>
  );
}

export function StepAnother({ data, trajectories, labels, pathId, onPath }) {
  const others = (trajectories ?? []).filter((t) => t.id !== "central");
  const traj = others.find((t) => t.id === pathId) ?? others[0];
  const switchYear = getSwitchYear(data);
  if (!traj) return <Unavailable what="The other paths" plural />;
  const yearLabel = fyLabel(traj.rows.at(-1).year);
  const ev = getExpectedValue(data);
  const pickLong = traj.pick ? pickText(traj.pick, yearLabel, ev?.nUniquePaths, Boolean(ev)) : null;
  const sourceText = traj.pick
    ? `One of ${traj.pick.draws.toLocaleString("en-GB")} simulated paths${traj.pick.kind === "random" ? ", picked at random" : ""}. ${ev ? "The expected saving uses all of them; this one" : "This one"} shows how the rules play out year by year.`
    : traj.source ? `${traj.source}.` : null;
  const start = switchYear ?? 2030;
  const reversals = traj.rows.filter((r, i) => i > 0 && r.year > start && r.tlSource !== traj.rows[i - 1].tlSource).length;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-another">
      <Section
        id="paths"
        title="Burnham plan vs triple lock"
        lead="Pick a path to see how the rules part when prices and earnings swap the lead."
        boxed={false}
      >
        <Panel
          footers={[
            {
              title: "Compare the four paths",
              content: <AllPathsTable trajectories={trajectories} selected={traj.id} onSelect={(id) => id !== "central" && onPath(id)} />,
            },
            {
              title: "Where these paths come from",
              content: (
                <>
                  <p>
                    A monthly model of prices and earnings centred on the OBR&apos;s forecast: one path at random, and
                    typical paths at the middle and 90th percentile of the {yearLabel} gap.
                  </p>
                  {pickLong ? <p data-testid="path-pick">{pickLong}</p> : null}
                </>
              ),
            },
          ]}
        >
          <div className="flex flex-wrap items-center gap-3">
            <Select label="Path" options={others.map((t) => ({ id: t.id, label: t.label }))} value={traj.id} onChange={onPath} />
            <div className="flex flex-wrap gap-2 text-xs">
              {traj.pick ? (
                <Chip testId="path-gap" title={`How far the Burnham plan's pension ends below the triple lock's in ${yearLabel}`}>
                  Gap by {yearLabel}: <strong>{formatWeekly(traj.pick.gap)} a week</strong>
                </Chip>
              ) : null}
              {traj.position ? (
                <Chip testId="path-position" title={`Where this path sits among the model's ${traj.position.draws.toLocaleString("en-GB")} paths, by its gap`}>
                  Percentile: <strong>{ordinal(Math.max(1, Math.min(99, Math.round(traj.position.percentile))))}</strong> of{" "}
                  {traj.position.draws.toLocaleString("en-GB")} ({Math.round(traj.position.larger)}% of paths save more)
                </Chip>
              ) : null}
              <Chip testId="lead-changes" title={`Times the figure setting the triple lock changes from April ${start}`}>
                Lead changes since {start}: <strong>{reversals}</strong>
              </Chip>
            </div>
          </div>
          <p className="mt-3 text-sm text-slate-600" data-testid="path-source">{sourceText}</p>
        </Panel>
        <div className="mt-5">
          <PathView traj={traj} labels={labels} switchYear={switchYear} />
        </div>
      </Section>
    </div>
  );
}
