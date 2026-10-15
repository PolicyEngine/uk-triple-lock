"use client";

import { useState } from "react";
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { colors, SERIES } from "../lib/colors";
import { fyLabel, getExpectedValue, getSwitchYear, PATH_NAMES } from "../lib/dataHelpers";
import { formatAnnualFromWeekly, formatBn, formatRate, ordinal } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { describeSource, differenceNotes } from "../lib/trajectoryHelpers";
import { ChartFrame, InputsChart, RisesChart } from "./PathCharts";
import { AXIS_STYLE, BoxTitle, CardBox, CustomTooltip, HoverTip, PensionCompareCard, Panel, Section, Unavailable, ViewSwitch } from "./ui";

const INDEX_SERIES = (labels) => [
  { key: "triple_lock", label: labels.triple_lock, color: SERIES.tripleLock, width: 3 },
  { key: "burnham_2030", label: labels.burnham_2030, color: SERIES.burnham, width: 3 },
  { key: "earnings", label: "Earnings alone", color: SERIES.earnings, width: 2, dashed: true },
  { key: "cpi", label: "CPI alone", color: SERIES.cpi, width: 2, dashed: true },
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
      <BoxTitle
        title={view === "inputs" ? "What sets each April\u2019s rise" : "The April rise under each rule"}
        description={view === "inputs"
          ? "The triple lock takes the highest of September CPI, May–July earnings growth and 2.5%."
          : "Each April's rise under the Burnham plan and the triple lock; they differ when the plan waits for earnings to catch up."}
      >
        <ViewSwitch options={RISE_VIEWS} value={view} onChange={setView} />
      </BoxTitle>
      {view === "inputs" ? <InputsChart traj={traj} /> : <RisesChart traj={traj} labels={labels} />}
    </div>
  );
}

const SOURCE_STYLE = {
  earnings: { label: "earnings", color: SERIES.earnings },
  cpi: { label: "CPI", color: SERIES.cpi },
  floor: { label: "2.5% floor", color: SERIES.floor },
};

/** The full new State Pension in the final year under each rule, per year, and the gap. */
function PensionCard({ last, labels }) {
  const fy = fyLabel(last.year);
  return (
    <PensionCompareCard
      label={`Full new State Pension, ${fy}`}
      fy={fy}
      rows={[
        { key: "tl", label: "Triple lock (current law)", weekly: last.tlWeekly, color: SERIES.tripleLock, testId: "card-tl-weekly" },
        { key: "bp", label: labels.burnham_2030 ?? "Burnham plan", weekly: last.bpWeekly, color: SERIES.burnham, testId: "card-bp-weekly" },
      ]}
    />
  );
}

/** Which figure set the triple lock's rise each April from the switch: one stacked bar of the Aprils. */
function BindingCard({ after, counts, switchYear }) {
  const [focus, setFocus] = useState(null);
  const order = ["earnings", "floor", "cpi"].sort((a, b) => counts[b] - counts[a]);
  const segmentTip = (r) =>
    r.tlSource === "earnings"
      ? `April ${r.year}: earnings growth ${formatRate(r.earnings)} (CPI ${formatRate(r.cpi)}, floor 2.5%)`
      : r.tlSource === "cpi"
        ? `April ${r.year}: CPI ${formatRate(r.cpi)} (earnings ${formatRate(r.earnings)}, floor 2.5%)`
        : `April ${r.year}: the 2.5% floor (CPI ${formatRate(r.cpi)}, earnings ${formatRate(r.earnings)})`;
  return (
    <CardBox label={`What set the triple lock's rise, April ${switchYear} on`} testId="card-binding">
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {counts[order[0]]} of {after.length} <span className="text-base font-medium text-slate-600">by {SOURCE_STYLE[order[0]].label}</span>
      </p>
      <div className="mt-3 flex h-3 rounded-full bg-slate-100">
        {after.map((r, k) => (
          <HoverTip key={r.year} className="h-full flex-1" tip={segmentTip(r)} testId={`binding-${r.year}`}>
            <span
              className={`h-full w-full border-r border-white transition-opacity hover:opacity-80 ${k === 0 ? "rounded-l-full" : ""} ${k === after.length - 1 ? "rounded-r-full border-r-0" : ""}`}
              style={{ background: SOURCE_STYLE[r.tlSource]?.color, opacity: focus && focus !== r.tlSource ? 0.25 : 1 }}
            />
          </HoverTip>
        ))}
      </div>
      <div className="mt-auto flex flex-wrap gap-x-3 gap-y-1 pt-3 text-xs text-slate-600">
        {order.map((k) => (
          <span
            key={k}
            className="flex cursor-default items-center gap-1.5 rounded px-1 hover:bg-slate-50"
            onMouseEnter={() => setFocus(k)}
            onMouseLeave={() => setFocus(null)}
          >
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SOURCE_STYLE[k].color }} />
            {SOURCE_STYLE[k].label[0].toUpperCase() + SOURCE_STYLE[k].label.slice(1)} {counts[k]}
          </span>
        ))}
      </div>
    </CardBox>
  );
}

/**
 * The years the Burnham plan's pension sits below the triple lock's, one dot per April from the switch: once the rules
 * part, the gap carries on, so this counts years below rather than years the rises differ.
 */
function DifferCard({ after }) {
  const isBelow = (r) => r.bpWeekly < r.tlWeekly - 0.005;
  const below = after.filter(isBelow);
  const first = below[0]?.year;
  const continuous = first !== undefined && after.filter((r) => r.year >= first).every(isBelow);
  const rise = (v) => `${v >= 0 ? "+" : ""}${formatRate(v)}`;
  return (
    <CardBox label="Pension below the triple lock" testId="card-differ">
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {below.length} <span className="text-base font-medium text-slate-600">of {after.length} years</span>
      </p>
      <p className="mt-1 text-sm text-slate-600">
        {first === undefined ? "The same pension every year" : continuous ? `Every year from April ${first}` : `First in April ${first}`}
      </p>
      <div className="mt-auto flex justify-between gap-1 pt-3">
        {after.map((r) => (
          <HoverTip
            key={r.year}
            className="flex-col items-center gap-1 rounded px-0.5 hover:bg-slate-50"
            testId={`differ-${r.year}`}
            tip={isBelow(r)
              ? `From April ${r.year}: ${formatAnnualFromWeekly(r.tlWeekly - r.bpWeekly)} a year below the triple lock (rises: triple lock ${rise(r.tlRate)}, Burnham plan ${rise(r.bpRate)})`
              : `From April ${r.year}: the same pension (rise ${rise(r.tlRate)})`}
          >
            <span className={`h-3 w-3 rounded-full ${isBelow(r) ? "" : "border border-slate-300 bg-white"}`} style={isBelow(r) ? { background: SERIES.highlight } : undefined} />
            <span className="text-[10px] tabular-nums text-slate-400">{String(r.year).slice(2)}</span>
          </HoverTip>
        ))}
      </div>
    </CardBox>
  );
}

export function PathView({ traj, labels, switchYear, isCentral = false }) {
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
        <DifferCard after={after} />
      </div>
      <Panel id="path-rises" className="mt-5">
        <RisesPanel traj={traj} labels={labels} />
      </Panel>
      <Panel
        id="path-level"
        className="mt-5"
        footers={[
          { title: "How to read this chart", content: <PathNotes traj={traj} isCentral={isCentral} notes={notes} yearLabel={fyLabel(last.year)} /> },
        ]}
      >
        <BoxTitle
          title="The pension's level (2026-27 = 100)"
          description="The pension under the Burnham plan and the triple lock (current law), against earnings alone and prices alone."
        />
        <IndexChart traj={traj} labels={labels} />
      </Panel>
    </>
  );
}

const SOURCE_SHORT = { earnings: "earnings", cpi: "CPI", floor: "the 2.5% floor" };

/** "2028–2031" for consecutive years, "2028 and 2030" otherwise. */
function yearSpan(ys) {
  if (ys.length === 1) return String(ys[0]);
  const consecutive = ys.every((y, k) => k === 0 || y === ys[k - 1] + 1);
  return consecutive ? `${ys[0]}–${ys[ys.length - 1]}` : `${ys.slice(0, -1).join(", ")} and ${ys.at(-1)}`;
}

/** Runs of the same source over consecutive Aprils: [{ source, years }]. */
function sourceRuns(rows) {
  const runs = [];
  for (const r of rows) {
    const last = runs.at(-1);
    if (last && last.source === r.tlSource) last.years.push(r.year);
    else runs.push({ source: r.tlSource, years: [r.year] });
  }
  return runs;
}

/** "How to read this chart" for one path: the path, what set each rise, where the rules differ, and why, from its rows. */
function PathNotes({ traj, isCentral, notes, yearLabel }) {
  const last = traj.rows.at(-1);
  const runs = sourceRuns(traj.rows);
  const sets = runs.map((r, k) => `${SOURCE_SHORT[r.source] ?? r.source} in April ${yearSpan(r.years)}${k === runs.length - 1 ? "" : ""}`);
  const gapYear = formatAnnualFromWeekly(last.tlWeekly - last.bpWeekly);
  const rise = (v) => `${v >= 0 ? "+" : ""}${formatRate(v)}`;
  return (
    <ul className="list-disc space-y-2 pl-5">
      <li>
        <strong>The path.</strong>{" "}
        {isCentral
          ? "The OBR's March 2026 forecast to 2030, then its long-term assumptions (CPI 2%, earnings about 3.7%). April 2027 uses May–July 2026 earnings and August 2026 CPI."
          : "One of the model's simulated paths of prices and earnings, centred on the OBR's forecast."}
      </li>
      <li>
        <strong>What sets each rise.</strong>{" "}The triple lock is set by {sets.length > 1 ? `${sets.slice(0, -1).join(", ")} and ${sets.at(-1)}` : sets[0]}.
      </li>
      <li data-testid="path-notes">
        <strong>Where the rules differ.</strong>{" "}
        {notes.length ? (
          <ul className="mt-1 list-none space-y-0.5 pl-0">
            {notes.map((n) => {
              const r = traj.rows.find((x) => x.year === n.year);
              return (
                <li key={n.year}>
                  April {n.year}: triple lock {rise(r.tlRate)} ({describeSource("triple_lock", r.tlSource)}); Burnham plan {rise(r.bpRate)} ({describeSource("burnham_2030", r.bpSource)}).
                </li>
              );
            })}
          </ul>
        ) : (
          "The two rules give the same rise every year on this path."
        )}
      </li>
      <li>
        <strong>Why.</strong>{" "}
        {notes.length
          ? `After years when CPI or the 2.5% floor beats earnings, the Burnham plan rises only by CPI or 2.5% until earnings catch up; the triple lock carries those higher rises forward. That, and rounding, is the whole gap: ${gapYear} a year by ${yearLabel}.`
          : "With the same rise every year, the two rules pay the same pension."}
      </li>
    </ul>
  );
}

const BUTTON_LABEL = PATH_NAMES;

/** Short bullets on where each path comes from; the selected simulated path's own pick on its own line. */
function PathSources({ ordered, traj, ev, yearLabel }) {
  const simulated = ordered.filter((t) => t.pick);
  const draws = simulated[0]?.pick.draws;
  const band = simulated.find((t) => t.pick.kind === "percentile")?.pick.band;
  const n = (v) => v.toLocaleString("en-GB");
  const runs = Number.isInteger(ev?.nUniquePaths) && ev.nUniquePaths > 0 ? ` (${n(ev.nUniquePaths)} run in full)` : "";
  return (
    <ul className="list-disc space-y-1 pl-5" data-testid="path-sources">
      <li><strong>OBR central forecast:</strong>{" "}the OBR&apos;s March 2026 forecast, then its long-term assumptions.</li>
      {draws ? <li><strong>Simulated paths:</strong>{" "}from a monthly model of prices and earnings centred on that forecast ({n(draws)} paths).</li> : null}
      {simulated.some((t) => t.pick.kind === "random") ? <li><strong>Example path (random):</strong>{" "}one simulated path picked at random.</li> : null}
      {band ? (
        <li>
          <strong>Typical and high-saving paths:</strong>{" "}a typical path at the median and at the 90th percentile of the {yearLabel} gap: among the paths
          within ±{Math.round(band * 100 * 10) / 10} percentiles, the one whose CPI and earnings are closest to their average.
        </li>
      ) : null}
      {traj.pick ? (
        <li data-testid="path-pick">
          <strong>Selected now:</strong>{" "}path {n(traj.pick.draw)}
          {traj.pick.kind === "random" ? ", picked at random" : ""}, gap {formatAnnualFromWeekly(traj.pick.gap)} a year by {yearLabel}.
        </li>
      ) : null}
      {draws ? (
        <li>
          {ev ? `The expected saving uses all ${n(draws)} paths${runs}, not these examples.` : "These are illustrative paths, not an average."}
        </li>
      ) : null}
    </ul>
  );
}

/**
 * The Forecast paths tab: one path at a time under both rules. The OBR's central forecast is the default; the
 * model's simulated paths are the other options, picked with a row of buttons showing each one's saving.
 */
export function StepPaths({ data, trajectories, labels, pathId = "central", onPath }) {
  const all = trajectories ?? [];
  const central = all.find((t) => t.id === "central");
  const ordered = [...(central ? [central] : []), ...all.filter((t) => t.id !== "central")];
  const traj = ordered.find((t) => t.id === pathId) ?? ordered[0];
  const switchYear = getSwitchYear(data);
  if (!traj) return <Unavailable what="The forecast paths" plural />;
  const isCentral = traj.id === "central";
  const yearLabel = fyLabel(traj.rows.at(-1).year);
  const ev = getExpectedValue(data);
  const start = switchYear ?? 2030;
  const changes = traj.rows.filter((r, i) => i > 0 && r.year > start && r.tlSource !== traj.rows[i - 1].tlSource).length;
  const last = traj.rows.at(-1);
  const gap = last.tlWeekly - last.bpWeekly;
  const gapText = Math.abs(gap) < 0.005 ? "the same as the triple lock's" : `${formatAnnualFromWeekly(Math.abs(gap))} a year ${gap > 0 ? "below" : "above"} the triple lock's`;
  const where = traj.position ? ` at the ${ordinal(Math.max(1, Math.min(99, Math.round(traj.position.percentile))))} percentile` : "";
  const sourceText = isCentral
    ? `The OBR central forecast: earnings beat prices almost every year, so the Burnham plan's pension ends just ${gapText} by ${yearLabel}.`
    : `A simulated path${traj.pick?.kind === "random" ? " picked at random" : ""}${where}: the Burnham plan's pension ends ${gapText} by ${yearLabel}; the figure setting the triple lock changes ${changes} ${changes === 1 ? "time" : "times"} after ${start}.`;
  const pick = (id) => onPath?.(id);
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid={isCentral ? "step-central" : "step-another"}>
      <Section
        id="paths"
        title="Burnham plan vs triple lock (current law) on one path"
        lead="How the Burnham plan and the triple lock (current law) raise the pension on one path of prices and earnings: the OBR central forecast or a simulated path."
        boxed={false}
      >
        <Panel
          id="path-picker"
          footers={[{ title: "Where these paths come from", content: <PathSources ordered={ordered} traj={traj} ev={ev} yearLabel={yearLabel} /> }]}
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Path">
            {ordered.map((t) => {
              const on = t.id === traj.id;
              const g = t.rows.at(-1).gross;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => pick(t.id)}
                  className={`rounded-xl border px-3 py-2 text-left transition-colors ${on ? "border-teal-600 bg-teal-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"}`}
                >
                  <span className={`block text-sm font-semibold ${on ? "text-teal-900" : "text-slate-800"}`}>{BUTTON_LABEL[t.id] ?? t.label}</span>
                  <span className="block text-xs tabular-nums text-slate-500">
                    {Number.isFinite(g) ? `${formatBn(g, 1)} saved in ${yearLabel}` : t.label}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-sm text-slate-700" data-testid="path-source">{sourceText}</p>
        </Panel>
        <div className="mt-5">
          <PathView traj={traj} labels={labels} switchYear={switchYear} isCentral={isCentral} />
        </div>
      </Section>
    </div>
  );
}
