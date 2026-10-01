"use client";

import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { colors, colorFor } from "../lib/colors";
import { fyLabel, getExpectedValue, getSwitchYear } from "../lib/dataHelpers";
import { formatWeekly } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { describeSource, differenceNotes, pickText, positionText } from "../lib/trajectoryHelpers";
import { AllPathsTable, Card, ChartFrame, InputsChart, RisesChart, YearTable } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Expandable, Panel, Section, Select, Unavailable } from "./ui";

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
export function PathView({ traj, labels, switchYear, footer, footerTitle }) {
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
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Panel>
          <h3 className="font-semibold text-slate-800">What sets each April&apos;s rise</h3>
          <p className="mb-3 mt-1 text-sm text-slate-500">The three figures the triple lock takes the highest of: September CPI and May–July earnings growth from the year before, and 2.5%.</p>
          <InputsChart traj={traj} />
        </Panel>
        <Panel>
          <h3 className="font-semibold text-slate-800">The April rise under each rule</h3>
          <p className="mb-3 mt-1 text-sm text-slate-500">How much the pension rises each April. The rules part in years when the plan waits for earnings to catch up.</p>
          <RisesChart traj={traj} labels={labels} />
        </Panel>
      </div>
      <Panel className="mt-5" footer={footer} footerTitle={footerTitle}>
        <h3 className="font-semibold text-slate-800">The pension&apos;s level (2026-27 = 100)</h3>
        <p className="mb-3 mt-1 text-sm text-slate-500">Where those rises leave the pension under each rule, against earnings alone and prices alone.</p>
        <IndexChart traj={traj} labels={labels} />
        <div className="mt-5 border-t border-slate-100 pt-4" data-testid="path-notes">
        <h4 className="mb-2 text-sm font-semibold text-slate-800">Where the rules differ</h4>
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
      </Panel>
      <div className="mt-5">
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
  const cpiAfter = traj.rows.filter((r) => r.year >= sw && r.tlSource === "cpi").map((r) => r.year);
  const firstEarnings = traj.rows.find((r) => r.year >= sw && r.tlSource === "earnings");
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-central">
      <Section
        id="central"
        title="On the OBR's central forecast"
        lead="The OBR's forecast, followed year by year under both rules: earnings lead almost every year, so the rules barely differ."
        boxed={false}
      >
        <PathView traj={traj} labels={labels} switchYear={switchYear} footerTitle="Why the saving is small on this path" footer={<p>
            The OBR&apos;s March 2026 forecast to 2030, and its long-term assumptions after (CPI at 2%, earnings growth
            rising to about 3.7%). April 2027&apos;s rise uses the published May–July 2026 earnings and August 2026 CPI.
            {floorYears.length
              ? ` On this path earnings grow by less than 2.5% for a few years, so the floor sets the triple lock in April ${floorYears.join(", ")}.`
              : ""}
            {firstEarnings ? ` From April ${firstEarnings.year} earnings lead every year.` : ""}
            {floorAfter.length || cpiAfter.length
              ? ` The plan's earnings path starts from the 2029-30 level, so the years that matter are those from April ${sw} in which the floor or CPI, not earnings, sets the triple lock (${[...floorAfter, ...cpiAfter].sort().join(", ")}): the plan pays the same then, which leaves its pension above that earnings path. So when earnings pick up, the plan rises by only the higher of CPI and 2.5% until earnings catch up, while the triple lock rises with earnings from the higher level. Apart from the plan's rounding up to 0.1 point when it catches up, that is the whole difference on this path.`
              : " With no floor or CPI years after the switch, the two rules differ only through rounding on this path."}
          </p>} />
      </Section>
    </div>
  );
}

export function StepAnother({ data, trajectories, labels, pathId, onPath }) {
  const others = (trajectories ?? []).filter((t) => t.id !== "central");
  const traj = others.find((t) => t.id === pathId) ?? others[0];
  const switchYear = getSwitchYear(data);
  if (!traj) return <Unavailable what="The other paths" plural />;
  const yearLabel = fyLabel(traj.rows.at(-1).year);
  const sourceText = traj.pick ? pickText(traj.pick, yearLabel, getExpectedValue(data)?.nUniquePaths) : traj.source ? `${traj.source}.` : null;
  const reversals = traj.rows.filter((r, i) => i > 0 && r.year > (switchYear ?? 2030) && r.tlSource !== traj.rows[i - 1].tlSource).length;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-another">
      <Section
        id="paths"
        title="Other possible paths"
        lead="Pick a path from the monthly model to see how the two rules part when prices and earnings swap the lead."
        boxed={false}
      >
        <Panel footerTitle="Where these paths come from" footer={<p>
            The central forecast is one path of many. These come from a monthly model of prices and earnings whose
            calendar-year averages equal the OBR&apos;s forecast every year: a path picked at random, and typical paths near the middle
            and the 90th percentile of the gap the plan opens up by 2039-40. In a year when CPI or the floor runs ahead of
            earnings both rules pay it, but afterwards the plan rises more slowly until earnings catch up, while the triple
            lock keeps the gain.
          </p>}>
          <Select label="Path" options={others.map((t) => ({ id: t.id, label: t.label }))} value={traj.id} onChange={onPath} />
          {sourceText ? <p className="mt-3 text-sm leading-6 text-slate-600" data-testid="path-source">{sourceText}</p> : null}
          {traj.position ? (
            <p className="mt-2 text-sm font-medium text-slate-700" data-testid="path-position">
              {positionText(traj.position, yearLabel)}
            </p>
          ) : null}
          <p className="mt-2 text-sm text-slate-600" data-testid="lead-changes">
            From April {switchYear ?? 2030}, the figure setting the triple lock changes {reversals} times on this path (
            {traj.rows.filter((r) => r.year >= (switchYear ?? 2030)).map((r) => describeSource("triple_lock", r.tlSource) ?? "unknown").join(", ")}).
          </p>
        </Panel>
        <div className="mt-5">
          <PathView traj={traj} labels={labels} switchYear={switchYear} />
        </div>
        <Panel className="mt-5">
          <h3 className="mb-2 font-semibold text-slate-800">Every path shown here, at a glance</h3>
          <AllPathsTable trajectories={trajectories} selected={traj.id} onSelect={(id) => id !== "central" && onPath(id)} />
        </Panel>
      </Section>
    </div>
  );
}
