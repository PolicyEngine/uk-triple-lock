"use client";

import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import { fyLabel, getSwitchYear } from "../lib/dataHelpers";
import { formatWeekly } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { describeSource, differenceNotes } from "../lib/trajectoryHelpers";
import SectionHeading from "./SectionHeading";
import { AllPathsTable, Card, ChartFrame, InputsChart, RisesChart, YearTable } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, ToggleGroup, Unavailable } from "./ui";

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
export function PathView({ traj, labels, switchYear }) {
  const last = traj.rows.at(-1);
  const notes = differenceNotes(traj);
  const after = traj.rows.filter((r) => r.year >= (switchYear ?? 2030));
  const counts = { earnings: 0, cpi: 0, floor: 0 };
  for (const r of after) counts[r.tlSource] += 1;
  // How far the plan's pension is below the triple lock's, as a share of the triple lock's.
  const gapPct = (1 - last.bpWeekly / last.tlWeekly) * 100;
  const gapText = Math.abs(gapPct) < 0.05 ? "The same" : `${Math.abs(gapPct).toFixed(1)}% ${gapPct > 0 ? "lower" : "higher"}`;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label={`Full new State Pension, ${fyLabel(last.year)}`} value={`${formatWeekly(last.tlWeekly)} a week`} detail={labels.triple_lock} testId="card-tl-weekly" />
        <Card label="Under the Burnham plan" value={`${formatWeekly(last.bpWeekly)} a week`} detail={gapText} testId="card-bp-weekly" />
        <Card label={`Rises from April ${switchYear ?? 2030} set by`} value={`${counts.earnings} earnings`} detail={`${counts.cpi} CPI, ${counts.floor} the 2.5% floor (triple lock)`} testId="card-binding" />
        <Card label="Years the rules differ" value={String(notes.length)} detail={notes.length ? `First in April ${notes[0].year}` : "The same rise every year"} testId="card-differ" />
      </div>
      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 font-semibold text-slate-800">What sets each April&apos;s rise</h3>
          <InputsChart traj={traj} />
        </div>
        <div>
          <h3 className="mb-2 font-semibold text-slate-800">The April rise under each rule</h3>
          <RisesChart traj={traj} labels={labels} />
        </div>
      </div>
      <div className="mt-8">
        <h3 className="mb-2 font-semibold text-slate-800">The pension&apos;s level (2026-27 = 100)</h3>
        <IndexChart traj={traj} labels={labels} />
      </div>
      <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3" data-testid="path-notes">
        <p className="mb-2 font-semibold text-slate-800">Where the rules differ</p>
        {notes.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
            {notes.map((n) => (
              <li key={n.year}>{n.text}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-700">The two rules give the same rise every year on this path.</p>
        )}
      </div>
      <div className="mt-6">
        <Expandable title="Year by year" testId="path-table-box">
          <YearTable traj={traj} labels={labels} />
        </Expandable>
      </div>
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
  const firstEarnings = traj.rows.find((r) => r.year >= sw && r.tlSource === "earnings");
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-central">
      <SectionHeading title="2. The OBR's central forecast" />
      <Explainer>
        <p>
          The OBR&apos;s March 2026 forecast to 2030, and its long-term assumptions after (CPI at 2%, earnings growth
          rising to about 3.7%). April 2027&apos;s rise uses the published May–July 2026 earnings and August 2026 CPI.
          {floorYears.length
            ? ` On this path earnings grow by less than 2.5% for a few years, so the floor sets the triple lock in April ${floorYears.join(", ")}.`
            : ""}
          {firstEarnings ? ` From April ${firstEarnings.year} earnings lead every year.` : ""}
          {floorAfter.length
            ? ` The plan's earnings path starts from the 2029-30 level, so the floor years that matter are those from April ${sw} (${floorAfter.join(", ")}): the plan pays the floor then too, which leaves its pension above that earnings path. So when earnings pick up, the plan rises by only the higher of CPI and 2.5% until earnings catch up, while the triple lock rises with earnings from the higher level. Apart from the plan's rounding up to 0.1 point when it catches up, that is the whole difference on this path.`
            : " With no floor or CPI years after the switch, the two rules differ only through rounding on this path."}
        </p>
      </Explainer>
      <PathView traj={traj} labels={labels} switchYear={switchYear} />
    </div>
  );
}

export function StepAnother({ data, trajectories, labels, pathId, onPath }) {
  const others = (trajectories ?? []).filter((t) => t.id !== "central");
  const traj = others.find((t) => t.id === pathId) ?? others[0];
  const switchYear = getSwitchYear(data);
  if (!traj) return <Unavailable what="The other paths" plural />;
  const reversals = traj.rows.filter((r, i) => i > 0 && r.year > (switchYear ?? 2030) && r.tlSource !== traj.rows[i - 1].tlSource).length;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-another">
      <SectionHeading title="3. Another possible path" />
      <Explainer>
        <p>
          The central forecast is one path of many. These come from a monthly model of prices and earnings whose
          calendar-year averages equal the OBR&apos;s forecast every year: a path picked at random, and the paths at the middle
          and the 90th percentile of the gap the plan opens up by 2039-40. In a year when CPI or the floor runs ahead of
          earnings both rules pay it, but afterwards the plan rises more slowly until earnings catch up, while the triple
          lock keeps the gain.
        </p>
      </Explainer>
      <ToggleGroup label="Path" options={others.map((t) => ({ id: t.id, label: t.label }))} value={traj.id} onChange={onPath} />
      {traj.source ? <p className="mt-3 text-sm text-slate-500" data-testid="path-source">{traj.source}.</p> : null}
      <p className="mt-2 text-sm text-slate-600" data-testid="lead-changes">
        From April {switchYear ?? 2030}, the figure setting the triple lock changes {reversals} times on this path (
        {traj.rows.filter((r) => r.year >= (switchYear ?? 2030)).map((r) => describeSource("triple_lock", r.tlSource) ?? "unknown").join(", ")}).
      </p>
      <div className="mt-6">
        <PathView traj={traj} labels={labels} switchYear={switchYear} />
      </div>
      <div className="mt-8">
        <h3 className="mb-2 font-semibold text-slate-800">Every path shown here, at a glance</h3>
        <AllPathsTable trajectories={trajectories} selected={traj.id} onSelect={(id) => id !== "central" && onPath(id)} />
      </div>
    </div>
  );
}
