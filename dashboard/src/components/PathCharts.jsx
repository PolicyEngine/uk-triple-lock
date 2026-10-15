"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors, SERIES, colorFor } from "../lib/colors";
import { fyLabel } from "../lib/dataHelpers";
import { formatAnnualFromWeekly, formatBn, formatRate } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import { describeSource, getPolicyLabel, replayDifferences } from "../lib/trajectoryHelpers";
import ChartLogo from "./ChartLogo";
import { AXIS_STYLE, CustomTooltip, LegendSwatches, Panel, PensionCompareCard, Select } from "./ui";

const INPUT_COLORS = { cpi: SERIES.cpi, earnings: SERIES.earnings };

export function policyLegend(labels) {
  return ["triple_lock", "burnham_2030"].map((p) => ({ label: labels[p], color: colorFor(p) }));
}

export function Card({ label, value, detail, testId }) {
  return (
    <div className="metric-card" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-600">{detail}</p> : null}
    </div>
  );
}

/** A chart with its legend and logo. With `grow`, it stretches to fill a flex-column box (at least `height` tall). */
export function ChartFrame({ children, legend, height = 280, grow = false }) {
  return (
    <>
      <div className={grow ? "min-h-0 flex-1" : undefined} style={grow ? { minHeight: height } : { height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
      {legend ? <LegendSwatches items={legend} /> : null}
      <ChartLogo />
    </>
  );
}

export function InputsChart({ traj }) {
  const rows = traj.rows.map((r) => ({ april: `Apr ${r.year}`, cpi: r.cpi * 100, earnings: r.earnings * 100 }));
  return (
    <ChartFrame legend={[{ label: "September CPI", color: INPUT_COLORS.cpi }, { label: "May–July earnings", color: INPUT_COLORS.earnings }, { label: "2.5% floor", color: SERIES.floor, dashed: true }]}>
      <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis
          tick={AXIS_STYLE}
          tickFormatter={(v) => `${v}%`}
          {...niceAxis(rows.flatMap((r) => [r.cpi, r.earnings, 2.5]))}
        />
        <ReferenceLine y={2.5} stroke={SERIES.floor} strokeDasharray="4 4" />
        <Tooltip content={<CustomTooltip formatter={(v) => `${v.toFixed(1)}%`} />} />
        <Line type="linear" dataKey="cpi" name="September CPI" stroke={INPUT_COLORS.cpi} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
        <Line type="linear" dataKey="earnings" name="May–July earnings" stroke={INPUT_COLORS.earnings} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
      </LineChart>
    </ChartFrame>
  );
}

export function RisesChart({ traj, labels }) {
  const rows = traj.rows.map((r) => ({ april: `Apr ${r.year}`, triple_lock: r.tlRate * 100, burnham_2030: r.bpRate * 100 }));
  return (
    <ChartFrame legend={policyLegend(labels)}>
      <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => `${v}%`} {...niceAxis(rows.flatMap((r) => [r.triple_lock, r.burnham_2030]))} />
        <Tooltip content={<CustomTooltip formatter={(v) => `${v.toFixed(1)}%`} />} />
        {["triple_lock", "burnham_2030"].map((p) => (
          <Bar key={p} dataKey={p} name={labels[p]} fill={colorFor(p)} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function SavingChart({ traj, grow = false }) {
  const rows = traj.rows.map((r) => ({ year: fyLabel(r.year), gross: r.gross, net: r.net }));
  return (
    <ChartFrame grow={grow} legend={[{ label: "Gross (State Pension spending)", color: SERIES.gross }, { label: "Net of tax and other benefits", color: SERIES.net }]}>
      <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, axisDigits(rows.flatMap((r) => [r.gross, r.net])))} {...niceAxis(rows.flatMap((r) => [r.gross, r.net]))} />
        <ReferenceLine y={0} stroke={SERIES.axis} />
        <Tooltip content={<CustomTooltip formatter={(v) => formatBn(v, 2)} />} />
        <Bar dataKey="gross" name="Gross (State Pension spending)" fill={SERIES.gross} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="net" name="Net of tax and other benefits" fill={SERIES.net} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartFrame>
  );
}

export function YearTable({ traj, labels }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] text-sm" data-testid="trajectory-table">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-2 pr-3 font-medium">April</th>
            <th className="py-2 pr-3 font-medium">Sep CPI</th>
            <th className="py-2 pr-3 font-medium">May–Jul earnings</th>
            <th className="py-2 pr-3 font-medium">{labels.triple_lock}</th>
            <th className="py-2 pr-3 font-medium">{labels.burnham_2030}</th>
            <th className="py-2 pr-3 font-medium">Pension a year, triple lock</th>
            <th className="py-2 pr-3 font-medium">Pension a year, Burnham plan</th>
            <th className="py-2 pr-3 font-medium">Saving, gross</th>
            <th className="py-2 pr-3 font-medium">Saving, net</th>
          </tr>
        </thead>
        <tbody className="text-slate-700">
          {traj.rows.map((r) => (
            <tr key={r.year} className="border-t border-slate-100">
              <td className="py-2 pr-3">{r.year}</td>
              <td className="py-2 pr-3">{formatRate(r.cpi)}</td>
              <td className="py-2 pr-3">{formatRate(r.earnings)}</td>
              <td className="py-2 pr-3">{formatRate(r.tlRate)} <span className="text-slate-400">({describeSource("triple_lock", r.tlSource)})</span></td>
              <td className="py-2 pr-3">{formatRate(r.bpRate)} <span className="text-slate-400">({describeSource("burnham_2030", r.bpSource)})</span></td>
              <td className="py-2 pr-3" title={`£${r.tlWeekly?.toFixed(2)} a week`}>{formatAnnualFromWeekly(r.tlWeekly)}</td>
              <td className="py-2 pr-3" title={`£${r.bpWeekly?.toFixed(2)} a week`}>{formatAnnualFromWeekly(r.bpWeekly)}</td>
              <td className="py-2 pr-3">{formatBn(r.gross, 2)}</td>
              <td className="py-2 pr-3">{formatBn(r.net, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AllPathsTable({ trajectories, selected, onSelect }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm" data-testid="all-paths-table">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-2 pr-3 font-medium">Path</th>
            <th className="py-2 pr-3 font-medium">Saving {fyLabel(trajectories[0].horizon.at(-1))}, gross</th>
            <th className="py-2 pr-3 font-medium">Net</th>
            <th className="py-2 pr-3 font-medium">Full new State Pension, triple lock</th>
            <th className="py-2 pr-3 font-medium">Burnham plan</th>
          </tr>
        </thead>
        <tbody className="text-slate-700">
          {trajectories.map((t) => {
            const last = t.rows.at(-1);
            return (
              <tr
                key={t.id}
                className={`cursor-pointer border-t border-slate-100 ${t.id === selected ? "bg-teal-50 font-medium" : "hover:bg-slate-50"}`}
                onClick={() => onSelect(t.id)}
              >
                <td className="py-2 pr-3">{t.label}</td>
                <td className="py-2 pr-3">{formatBn(last.gross, 2)}</td>
                <td className="py-2 pr-3">{formatBn(last.net, 2)}</td>
                <td className="py-2 pr-3">{formatAnnualFromWeekly(last.tlWeekly)}</td>
                <td className="py-2 pr-3">{formatAnnualFromWeekly(last.bpWeekly)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Individual-record notes are withheld even for cached legacy inputs. */
export function recordNotes() {
  return [];
}

function ReplayNote({ history }) {
  const diffs = replayDifferences(history);
  if (!diffs) return null;
  if (!diffs.length) {
    return <p data-testid="past-note">The triple lock replayed on the latest figures gives the rise actually paid every year.</p>;
  }
  const first = history.years[0];
  const firstDiff = diffs.find((d) => d.year === first);
  return (
    <p data-testid="past-note">
      The rule replayed on the latest ONS figures differs from the rise paid in{" "}
      {diffs.length} of {history.years.length} years:{" "}
      {diffs.map((d) => `April ${d.year} (paid ${formatRate(d.paid)}, rule ${formatRate(d.rule)})`).join(", ")}. The rises
      paid used the figures first published
      {firstDiff ? `, and April ${first}'s followed September ${first - 1} RPI` : ""}.
    </p>
  );
}

/** What the past-years comparison is, for the section's closed explanation. */
export function PastYearsNote({ history }) {
  return (
    <p>
      The rule applied to published September CPI and May–July earnings from an earlier April; savings for{" "}
      {fyLabel(history.modelYears[0])} to {fyLabel(history.modelYears.at(-1))}{" "}are full PolicyEngine UK runs.
      {history.suspendedYear ? ` In April ${history.suspendedYear} the earnings link was suspended in law, so both rules use CPI that year.` : ""}
    </p>
  );
}

export function PastYears({ history, labels, footer, footerTitle }) {
  const [selected, setSelected] = useState(history.groups[0].id);
  const group = history.groups.find((g) => g.id === selected) ?? history.groups[0];
  const rows = history.years.map((y, i) => ({
    april: String(y),
    triple_lock: group.tlRate[i] * 100,
    burnham_2030: group.bpRate[i] * 100,
  }));
  const lastYear = history.modelYears.at(-1);
  const pastLabels = { triple_lock: `${labels.triple_lock}, on the latest figures`, burnham_2030: labels.burnham_2030 };
  return (
    <Panel
      footerTitle={footerTitle}
      footer={
        <>
          {footer}
          <ReplayNote history={history} />
        </>
      }
    >
      <div data-testid="past-years">
        <Select label="Plan starts in" options={history.groups.map((g) => ({ id: g.id, label: g.label }))} value={group.id} onChange={setSelected} />

      {group.changesAnything && group.model ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <PensionCompareCard
            label={`Full new State Pension, ${fyLabel(lastYear)}`}
            fy={fyLabel(lastYear)}
            testId="past-weekly"
            gapTestId="past-gap"
            rows={[
              { key: "actual", label: "Triple lock (actual)", weekly: group.model.actual.at(-1), color: SERIES.tripleLock, testId: "past-actual" },
              { key: "plan", label: "Burnham plan, had it started then", weekly: group.model.counterfactual.at(-1), color: SERIES.burnham, testId: "past-plan" },
            ]}
          />
          {history.modelYears.slice(-2).map((y) => {
            const i = history.modelYears.indexOf(y);
            return (
              <Card
                key={y}
                label={`Saving in ${fyLabel(y)}`}
                value={formatBn(group.model.gross[i], 2)}
                detail={`${formatBn(group.model.net[i], 2)} net`}
                testId={`past-saving-${y}`}
              />
            );
          })}
        </div>
      ) : (
        <p className="mt-5 text-sm text-slate-700" data-testid="past-no-difference">
          Had it started in {group.label}, the plan would have paid the same as the triple lock every year to April{" "}
          {history.years.at(-1)}.
        </p>
      )}

      <div className="mt-6 border-t border-slate-100 pt-5">
        <h3 className="mb-2 font-semibold text-slate-800">April rises, {history.years[0]} to {history.years.at(-1)}</h3>
        <ChartFrame legend={policyLegend(pastLabels)}>
          <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="april" tick={AXIS_STYLE} />
            <YAxis tick={AXIS_STYLE} tickFormatter={(v) => `${v}%`} {...niceAxis(rows.flatMap((r) => [r.triple_lock, r.burnham_2030]))} />
            <Tooltip content={<CustomTooltip formatter={(v) => `${v.toFixed(1)}%`} />} />
            {["triple_lock", "burnham_2030"].map((p) => (
              <Bar key={p} dataKey={p} name={pastLabels[p]} fill={colorFor(p)} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            ))}
          </BarChart>
        </ChartFrame>
      </div>
      </div>
    </Panel>
  );
}

export function trajectoryLabels(tdata) {
  return { triple_lock: getPolicyLabel(tdata, "triple_lock"), burnham_2030: getPolicyLabel(tdata, "burnham_2030") };
}
