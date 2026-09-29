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
import { fyLabel } from "../lib/dataHelpers";
import { formatBn, formatCurrency, formatPct, formatRate, formatWeekly } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import {
  LARGEST_HOUSEHOLD_FLAG,
  describeSource,
  differenceNotes,
  getBacktestRows,
  getHistory,
  getPolicyLabel,
  getSwitchYear,
  getTrajectories,
} from "../lib/trajectoryHelpers";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

const INPUT_COLORS = { cpi: colors.gray[500], earnings: colors.primary[400] };

function policyLegend(labels) {
  return ["triple_lock", "burnham_2030"].map((p) => ({ label: labels[p], color: colorFor(p) }));
}

function Card({ label, value, detail, testId }) {
  return (
    <div className="metric-card" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-600">{detail}</p> : null}
    </div>
  );
}

function ChartFrame({ children, legend, height = 280 }) {
  return (
    <>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
      {legend ? <LegendSwatches items={legend} /> : null}
      <ChartLogo />
    </>
  );
}

function InputsChart({ traj }) {
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

function RisesChart({ traj, labels }) {
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

function SavingChart({ traj }) {
  const rows = traj.rows.map((r) => ({ year: fyLabel(r.year), gross: r.gross, net: r.net }));
  return (
    <ChartFrame legend={[{ label: "Gross (State Pension spending)", color: colors.primary[600] }, { label: "Net of tax and other benefits", color: colors.primary[300] }]}>
      <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="year" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, 1)} {...niceAxis(rows.flatMap((r) => [r.gross, r.net]))} />
        <ReferenceLine y={0} stroke={colors.gray[400]} />
        <Tooltip content={<CustomTooltip formatter={(v) => formatBn(v, 2)} />} />
        <Bar dataKey="gross" name="Gross (State Pension spending)" fill={colors.primary[600]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="net" name="Net of tax and other benefits" fill={colors.primary[300]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartFrame>
  );
}

function YearTable({ traj, labels }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm" data-testid="trajectory-table">
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
            <th className="py-2 font-medium">Saving, net</th>
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
              <td className="py-2">{formatBn(r.net, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AllPathsTable({ trajectories, selected, onSelect }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm" data-testid="all-paths-table">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-2 pr-3 font-medium">Path</th>
            <th className="py-2 pr-3 font-medium">Saving {fyLabel(trajectories[0].horizon.at(-1))}, gross</th>
            <th className="py-2 pr-3 font-medium">Net</th>
            <th className="py-2 pr-3 font-medium">Full new State Pension, triple lock</th>
            <th className="py-2 font-medium">Burnham plan</th>
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
                <td className="py-2">{formatWeekly(last.bpWeekly)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function gbpYear(v) {
  return `£${Math.round(Math.abs(v)).toLocaleString("en-GB")} a year`;
}

/** Flags a path whose final-year net figure hangs on one survey household record. */
function LargestHouseholdFlag({ traj, year }) {
  const lh = traj.largest;
  if (!lh || Math.abs(lh.share) < LARGEST_HOUSEHOLD_FLAG) return null;
  const parts = [`its State Pension ${lh.sp < 0 ? "falls" : "rises"} ${gbpYear(lh.sp)}`];
  if (Math.abs(lh.hb) >= 1) parts.push(`its Housing Benefit ${lh.hb > 0 ? "rises" : "falls"} ${gbpYear(lh.hb)}`);
  if (Math.abs(lh.pc) >= 1) parts.push(`its Pension Credit ${lh.pc > 0 ? "rises" : "falls"} ${gbpYear(lh.pc)}`);
  return (
    <div className="note-card mt-6 rounded-r-xl px-4 py-3 text-sm leading-6" data-testid="largest-household-flag">
      <p className="note-eyebrow font-semibold">One survey household moves this path&apos;s net figure by {formatBn(Math.abs(lh.contribution), 2)}</p>
      <p>
        In {fyLabel(year)}, household record {lh.id} stands for {Math.round(lh.weight).toLocaleString("en-GB")} households (the
        median record stands for {Math.round(lh.medianWeight).toLocaleString("en-GB")}). Under the Burnham plan{" "}
        {parts.join(", ")}. Without that record, the net saving would be {formatBn(lh.netExcluding, 2)}. The gross saving
        does not depend on it.
      </p>
    </div>
  );
}

function FuturePaths({ tdata, trajectories, labels }) {
  const [selected, setSelected] = useState(trajectories[0].id);
  const traj = trajectories.find((t) => t.id === selected) ?? trajectories[0];
  const last = traj.rows.at(-1);
  const notes = differenceNotes(traj);
  const switchYear = getSwitchYear(tdata);
  return (
    <section className="mb-12" data-testid="future-paths">
      <SectionHeading title="A few paths through the full model" />
      <Explainer>
        <p>
          Each path is a full PolicyEngine UK run. Its CPI and earnings growth replace the model&apos;s economic
          assumptions, so every benefit rate, threshold and income that the model uprates moves with it, and the
          State Pension rises each April under each rule. Both rules follow the triple lock until April{" "}
          {switchYear ? switchYear - 1 : "the switch"}. The paths are chosen to be understood, one at a time, not to
          form a probability range.
        </p>
      </Explainer>
      <ToggleGroup
        label="Path"
        options={trajectories.map((t) => ({ id: t.id, label: t.label }))}
        value={traj.id}
        onChange={setSelected}
      />
      {traj.source ? <p className="mt-3 text-sm text-slate-500" data-testid="trajectory-source">{traj.source}.</p> : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label={`Saving in ${fyLabel(last.year)}`} value={formatBn(last.gross, 2)} detail="Gross: State Pension spending" testId="card-gross" />
        <Card label="Net saving" value={formatBn(last.net, 2)} detail="After income tax, Pension Credit and other benefits" testId="card-net" />
        <Card
          label="Full new State Pension"
          value={`${formatWeekly(last.bpWeekly)} a week`}
          detail={`${formatWeekly(last.tlWeekly)} under the triple lock`}
          testId="card-weekly"
        />
        <Card
          label="Households with lower income"
          value={formatPct(traj.losingPct)}
          detail={`Losing ${formatCurrency(traj.meanLoss)} a year on average, ${fyLabel(last.year)}`}
          testId="card-losing"
        />
      </div>

      <LargestHouseholdFlag traj={traj} year={last.year} />

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
        <h3 className="mb-2 font-semibold text-slate-800">Saving each year from the Burnham plan</h3>
        <SavingChart traj={traj} />
      </div>

      <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3" data-testid="trajectory-notes">
        <p className="mb-2 font-semibold text-slate-800">Where the rules differ on this path</p>
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
        <Expandable title="Year by year" testId="trajectory-table-box">
          <YearTable traj={traj} labels={labels} />
        </Expandable>
      </div>

      <div className="mt-8">
        <h3 className="mb-2 font-semibold text-slate-800">All paths at a glance</h3>
        <AllPathsTable trajectories={trajectories} selected={traj.id} onSelect={setSelected} />
      </div>
    </section>
  );
}

function PastYears({ history, labels }) {
  const [selected, setSelected] = useState(history.groups[0].id);
  const group = history.groups.find((g) => g.id === selected) ?? history.groups[0];
  const rows = history.years.map((y, i) => ({
    april: String(y),
    triple_lock: group.tlRate[i] * 100,
    burnham_2030: group.bpRate[i] * 100,
  }));
  const lastRatio = group.ratio.at(-1);
  return (
    <section className="mb-12" data-testid="past-years">
      <SectionHeading title="Past years: if the plan had started earlier" />
      <Explainer>
        <p>
          The same rule applied to the published September CPI and May–July earnings from an earlier April. The
          weekly amounts come from the rule; the savings for {fyLabel(history.modelYears[0])} to{" "}
          {fyLabel(history.modelYears.at(-1))}, the years the survey data cover, are full PolicyEngine UK runs.
          {history.suspendedYear ? ` In April ${history.suspendedYear} the earnings link was suspended in law, so both rules use CPI that year.` : ""}
        </p>
      </Explainer>
      <ToggleGroup label="Plan starts" options={history.groups.map((g) => ({ id: g.id, label: `From ${g.label}` }))} value={group.id} onChange={setSelected} />

      {group.changesAnything && group.model ? (
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <Card
            label={`Full new State Pension, ${fyLabel(history.modelYears.at(-1))}`}
            value={`${formatWeekly(group.model.counterfactual.at(-1))} a week`}
            detail={`${formatWeekly(group.model.actual.at(-1))} actual (${formatPct((lastRatio - 1) * 100)})`}
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
        <p className="mt-6 text-sm text-slate-700" data-testid="past-no-difference">
          Starting in {group.label}, the plan would have paid the same as the triple lock every year to{" "}
          {history.years.at(-1)}.
        </p>
      )}

      <div className="mt-8">
        <h3 className="mb-2 font-semibold text-slate-800">April rises, {history.years[0]} to {history.years.at(-1)}</h3>
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
      </div>
      <p className="mt-3 text-sm text-slate-500" data-testid="past-note">
        The inputs are the latest ONS figures, which can differ slightly from those first published and used at the
        time. April 2011 shows the CPI and earnings rule; the actual rise that year, 4.6%, followed September 2010 RPI.
      </p>
    </section>
  );
}

function BacktestNote({ tdata }) {
  const bt = getBacktestRows(tdata);
  if (!bt) return <Unavailable what="The backtest" />;
  const probabilistic = bt.rows.filter((r) => r.id !== "obr_point");
  const allUnder = probabilistic.every((r) => r.switchesExpected < r.switchesRealised);
  const bestInside = Math.max(...probabilistic.map((r) => r.burnhamInside));
  return (
    <Expandable title="Why a few paths, not a probability range" testId="backtest-box">
      <div className="space-y-3 text-sm leading-6 text-slate-600">
        <p>
          We tested {bt.rows.length} ways of putting a range on the two inputs against what happened, from the {bt.nOrigins} past
          OBR forecasts for which the test uses only information available at the time. Each method is scored on the
          realised September CPI and May–July earnings over the next four years. The score for the gap between the
          triple lock and the Burnham plan is CRPS in percentage points of the pension; lower is better.
        </p>
        <p>
          The triple lock&apos;s cost comes from the two inputs taking turns to lead: that is when the ratchet pays out.{" "}
          {allUnder ? "Every method predicted fewer of those reversals than happened, and " : ""}
          {`the best placed ${bestInside} of ${bt.nOrigins} realised gaps in its middle 80%.`} That is why the dashboard
          shows paths rather than odds.
        </p>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm" data-testid="backtest-table">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Method</th>
              <th className="py-2 pr-3 font-medium">Burnham gap score</th>
              <th className="py-2 pr-3 font-medium">Realised gap inside middle 80%</th>
              <th className="py-2 font-medium">Reversals in four years: predicted / actual</th>
            </tr>
          </thead>
          <tbody className="text-slate-700">
            {bt.rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="py-2 pr-3">{r.label}</td>
                <td className="py-2 pr-3">{r.burnhamCrps.toFixed(2)}</td>
                <td className="py-2 pr-3">{r.burnhamInside} of {bt.nOrigins}</td>
                <td className="py-2">{r.switchesExpected.toFixed(1)} / {r.switchesRealised.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Expandable>
  );
}

export default function TrajectoriesTab({ tdata }) {
  const trajectories = getTrajectories(tdata);
  const history = getHistory(tdata);
  const labels = { triple_lock: getPolicyLabel(tdata, "triple_lock"), burnham_2030: getPolicyLabel(tdata, "burnham_2030") };
  if (!labels.triple_lock || !labels.burnham_2030) return <Unavailable what="The trajectory viewer" />;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="trajectories-tab">
      {trajectories ? <FuturePaths tdata={tdata} trajectories={trajectories} labels={labels} /> : <Unavailable what="The future paths" plural />}
      {history ? <PastYears history={history} labels={labels} /> : <Unavailable what="The past-years comparison" />}
      <BacktestNote tdata={tdata} />
    </div>
  );
}
