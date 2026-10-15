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
import { colors, colorFor } from "../lib/colors";
import { fyLabel, getExpectedValue } from "../lib/dataHelpers";
import { formatBn, formatPct, formatRate, formatWeekly } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import {
  bestCoverage,
  describeSource,
  getBacktest,
  getPolicyLabel,
  replayDifferences,
} from "../lib/trajectoryHelpers";
import ChartLogo from "./ChartLogo";
import { AXIS_STYLE, CustomTooltip, Expandable, LegendSwatches, Panel, Select, Unavailable } from "./ui";

const INPUT_COLORS = { cpi: colors.gray[500], earnings: colors.primary[400] };

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
    <ChartFrame legend={[{ label: "September CPI", color: INPUT_COLORS.cpi }, { label: "May–July earnings", color: INPUT_COLORS.earnings }, { label: "2.5% floor", color: colors.gray[400], dashed: true }]}>
      <LineChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis
          tick={AXIS_STYLE}
          tickFormatter={(v) => `${v}%`}
          {...niceAxis(rows.flatMap((r) => [r.cpi, r.earnings, 2.5]))}
        />
        <ReferenceLine y={2.5} stroke={colors.gray[400]} strokeDasharray="4 4" />
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
    <ChartFrame grow={grow} legend={[{ label: "Gross (State Pension spending)", color: colors.primary[600] }, { label: "Net of tax and other benefits", color: colors.primary[300] }]}>
      <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, axisDigits(rows.flatMap((r) => [r.gross, r.net])))} {...niceAxis(rows.flatMap((r) => [r.gross, r.net]))} />
        <ReferenceLine y={0} stroke={colors.gray[400]} />
        <Tooltip content={<CustomTooltip formatter={(v) => formatBn(v, 2)} />} />
        <Bar dataKey="gross" name="Gross (State Pension spending)" fill={colors.primary[600]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="net" name="Net of tax and other benefits" fill={colors.primary[300]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
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
            <th className="py-2 pr-3 font-medium">Weekly, triple lock</th>
            <th className="py-2 pr-3 font-medium">Weekly, Burnham plan</th>
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
              <td className="py-2 pr-3">{formatWeekly(r.tlWeekly)}</td>
              <td className="py-2 pr-3">{formatWeekly(r.bpWeekly)}</td>
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
                <td className="py-2 pr-3">{formatWeekly(last.tlWeekly)}</td>
                <td className="py-2 pr-3">{formatWeekly(last.bpWeekly)}</td>
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
    <div data-testid="past-years">
      <Panel>
        <Select label="Plan starts in" options={history.groups.map((g) => ({ id: g.id, label: g.label }))} value={group.id} onChange={setSelected} />
      </Panel>

      {group.changesAnything && group.model ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Card
            label={`Full new State Pension, ${fyLabel(lastYear)}`}
            value={`${formatWeekly(group.model.counterfactual.at(-1))} a week`}
            detail={`Actual ${formatWeekly(group.model.actual.at(-1))}; the plan's is ${formatPct(Math.abs(group.finalRatio - 1) * 100)} ${group.finalRatio < 1 ? "lower" : "higher"}`}
            testId="past-weekly"
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

      <Panel
        className="mt-5"
        footerTitle={footerTitle}
        footer={
          <>
            {footer}
            <ReplayNote history={history} />
          </>
        }
      >
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
      </Panel>
    </div>
  );
}

function yearsLabel(years) {
  return years.length > 1 ? `${years.slice(0, -1).join(", ")} and ${years.at(-1)}` : String(years[0]);
}

function shortOrigin(origin) {
  return origin.replace(/ EFO$/, "").replace(/ forecast$/, "");
}

export function BacktestNote({ tdata, history }) {
  const bt = getBacktest(tdata);
  if (!bt) return <Unavailable what="The backtest" />;
  const pub = bt.published;
  const sus = bt.suspended;
  const n = pub.nOrigins;
  const allUnder = pub.ranges.every((r) => r.switchesExpected < r.switchesRealised);
  const cov = { published: bestCoverage(pub), suspended: bestCoverage(sus) };
  // The April with the highest September CPI behind it, from the past-years inputs.
  const peak = history ? history.years[history.cpi.indexOf(Math.max(...history.cpi))] : null;
  const peakCpi = peak ? history.cpi[history.years.indexOf(peak)] : null;
  const missedAll = cov.suspended.missed;
  const missedPeak = peak && missedAll.length && missedAll.every((o) => bt.windows[o].includes(peak));
  const small = pub.ranges.filter((r) => r.smallEnsemble);
  const lawById = Object.fromEntries(sus.rows.map((r) => [r.id, r]));
  return (
    <Expandable title="Which forecast distribution scores best" testId="backtest-box">
      <div className="space-y-3 text-sm leading-6 text-slate-600" data-testid="backtest-text">
        <p>
          We scored {pub.ranges.length} ways of putting a range on CPI and earnings, and the OBR forecast alone,
          against what followed {n} past OBR forecasts ({shortOrigin(pub.origins[0])} to{" "}
          {shortOrigin(pub.origins.at(-1))}), each fitted on earlier data only. The gap score (CRPS, points of the
          pension) is lower for better methods.
        </p>
        <p>
          How April 2022 is scored decides the result. On the published May–July 2021 earnings growth of{" "}
          {formatRate(pub.april2022.earnings)},{" "}
          {allUnder ? "every method predicted fewer switches between CPI and earnings than happened, and " : ""}
          the best placed {cov.published.best} of {n} actual gaps in its middle 80%. With earnings set to CPI (
          {formatRate(sus.april2022.cpi)}), as the law did that April, the best placed {cov.suspended.best} of {n}
          {missedAll.length
            ? `; ${cov.suspended.leader.label[0].toLowerCase()}${cov.suspended.leader.label.slice(1)} missed the ${yearsLabel(missedAll.map(shortOrigin))} forecasts${
                missedPeak ? `, whose four rises include April ${peak}, set by September CPI of ${formatRate(peakCpi)}` : ""
              }`
            : ""}
          . Neither is a reliable 80% range, so this page reports{" "}
          {getExpectedValue(tdata) ? "the expected saving and a few paths" : "scenarios and a few paths"}, not odds.
        </p>
        {small.length ? (
          <p data-testid="backtest-small-ensembles">
            {small.map((r) => r.label).join(" and ")} {small.length === 1 ? "has" : "have"} only {small[0].minDraws}–
            {small[0].maxDraws} paths at these forecasts, so {small.length === 1 ? "its" : "their"}{" "}&ldquo;middle
            80%&rdquo; is the full range of those paths.
          </p>
        ) : null}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm" data-testid="backtest-table">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Method</th>
              <th className="py-2 pr-3 font-medium">April 2022 as published: gap score</th>
              <th className="py-2 pr-3 font-medium">Inside middle 80%</th>
              <th className="py-2 pr-3 font-medium">As in law: gap score</th>
              <th className="py-2 pr-3 font-medium">Inside middle 80%</th>
              <th className="py-2 font-medium">Switches in four years, predicted / actual (as published)</th>
            </tr>
          </thead>
          <tbody className="text-slate-700">
            {pub.rows.map((r) => {
              const law = lawById[r.id];
              return (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="py-2 pr-3">
                    {r.label}
                    {r.smallEnsemble ? <span className="text-slate-400"> ({r.minDraws}–{r.maxDraws} paths: min–max range)</span> : null}
                  </td>
                  <td className="py-2 pr-3">{r.burnhamCrps.toFixed(2)}</td>
                  <td className="py-2 pr-3">{r.point ? "n/a" : `${r.burnhamInside} of ${n}`}</td>
                  <td className="py-2 pr-3">{law ? law.burnhamCrps.toFixed(2) : "n/a"}</td>
                  <td className="py-2 pr-3">{r.point || !law ? "n/a" : `${law.burnhamInside} of ${n}`}</td>
                  <td className="py-2">{r.switchesExpected.toFixed(1)} / {r.switchesRealised.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Expandable>
  );
}

export function trajectoryLabels(tdata) {
  return { triple_lock: getPolicyLabel(tdata, "triple_lock"), burnham_2030: getPolicyLabel(tdata, "burnham_2030") };
}
