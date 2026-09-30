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
import { formatBn, formatPct, formatRate, formatWeekly } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import {
  LARGEST_HOUSEHOLD_FLAG,
  bestCoverage,
  describeSource,
  flaggedRows,
  getBacktest,
  getPolicyLabel,
  isFlagged,
  isFlaggedAnyYear,
  replayDifferences,
} from "../lib/trajectoryHelpers";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, LegendSwatches, ToggleGroup, Unavailable } from "./ui";

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

export function ChartFrame({ children, legend, height = 280 }) {
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

export function SavingChart({ traj }) {
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
            <th className="py-2 font-medium">Largest household&apos;s share of net</th>
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
              <td className="py-2">{shareText(r.concentration)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function shareText(c) {
  if (!c) return "unavailable";
  const pct = formatPct(Math.abs(c.share) * 100, 0);
  return Math.abs(c.share) >= LARGEST_HOUSEHOLD_FLAG ? `${pct}, flagged` : pct;
}

function concentration(t) {
  const final = t.largest ? shareText({ share: t.largest.share }) : "unavailable";
  const earlier = flaggedRows(t).filter((r) => r.year !== t.rows.at(-1).year);
  return earlier.length ? `${final}; flagged in ${earlier.map((r) => fyLabel(r.year)).join(", ")}` : final;
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
            <th className="py-2 font-medium">Largest household&apos;s share of net</th>
          </tr>
        </thead>
        <tbody className="text-slate-700">
          {trajectories.map((t) => {
            const last = t.rows.at(-1);
            return (
              <tr
                key={t.id}
                data-flagged={isFlaggedAnyYear(t) ? "true" : "false"}
                className={`cursor-pointer border-t border-slate-100 ${t.id === selected ? "bg-teal-50 font-medium" : "hover:bg-slate-50"}`}
                onClick={() => onSelect(t.id)}
              >
                <td className="py-2 pr-3">{t.label}</td>
                <td className="py-2 pr-3">{formatBn(last.gross, 2)}</td>
                <td className="py-2 pr-3">{formatBn(last.net, 2)}</td>
                <td className="py-2 pr-3">{formatWeekly(last.tlWeekly)}</td>
                <td className="py-2 pr-3">{formatWeekly(last.bpWeekly)}</td>
                <td className="py-2">{concentration(t)}</td>
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
export function LargestHouseholdFlag({ traj, year }) {
  const lh = traj.largest;
  if (!lh) {
    return (
      <p className="mt-6 text-sm text-slate-600" data-testid="concentration-unavailable">
        The check for one household record driving this path&apos;s net figure is unavailable, so treat the net saving
        with caution.
      </p>
    );
  }
  if (!isFlagged(traj)) return null;
  const parts = [`its State Pension ${lh.sp < 0 ? "falls" : "rises"} ${gbpYear(lh.sp)}`];
  if (Math.abs(lh.hb) >= 1) parts.push(`its Housing Benefit ${lh.hb > 0 ? "rises" : "falls"} ${gbpYear(lh.hb)}`);
  if (Math.abs(lh.pc) >= 1) parts.push(`its Pension Credit ${lh.pc > 0 ? "rises" : "falls"} ${gbpYear(lh.pc)}`);
  return (
    <div className="note-card mt-6 rounded-r-xl px-4 py-3 text-sm leading-6" data-testid="largest-household-flag">
      <p className="note-eyebrow font-semibold">One survey household moves this path&apos;s net figure by {formatBn(Math.abs(lh.contribution), 2)}</p>
      <p>
        In {fyLabel(year)}, household record {lh.id} stands for {Math.round(lh.weight).toLocaleString("en-GB")} households (the
        median record stands for {Math.round(lh.medianWeight).toLocaleString("en-GB")}). Under the Burnham plan{" "}
        {parts.join(", ")}. Without that record, the net saving would be {formatBn(lh.netExcluding, 2)}. It accounts
        for {formatBn(lh.gross, 2)} of the gross saving.
      </p>
    </div>
  );
}

/** Years before the last whose net figure one household record carries a fifth or more of. */
export function ConcentrationYears({ traj }) {
  const rows = flaggedRows(traj).filter((r) => r.year !== traj.rows.at(-1).year);
  if (!rows.length) return null;
  return (
    <div className="note-card mt-4 rounded-r-xl px-4 py-3 text-sm leading-6" data-testid="concentration-years">
      <p className="note-eyebrow font-semibold">One survey household drives the net figure in {rows.length === 1 ? "one year" : `${rows.length} years`}</p>
      <p>
        {rows
          .map((r) => `In ${fyLabel(r.year)}, household record ${r.concentration.id} (standing for ${Math.round(r.concentration.weight).toLocaleString("en-GB")} households) moves the net saving by ${formatBn(Math.abs(r.concentration.contribution), 2)}, ${formatPct(Math.abs(r.concentration.share) * 100, 0)} of it`)
          .join(". ")}
        . Read those years&apos; net figures with that in mind. Gross figures have no such threshold effects: the gap in
        them comes only from the flat rates.
      </p>
    </div>
  );
}

function ReplayNote({ history }) {
  const diffs = replayDifferences(history);
  if (!diffs) return null;
  if (!diffs.length) {
    return <p className="mt-3 text-sm text-slate-500" data-testid="past-note">The triple lock replayed on the latest figures gives the rise actually paid every year.</p>;
  }
  const first = history.years[0];
  const firstDiff = diffs.find((d) => d.year === first);
  return (
    <p className="mt-3 text-sm text-slate-500" data-testid="past-note">
      The triple lock here is the rule replayed on the latest ONS figures. It differs from the rise actually paid in{" "}
      {diffs.length} of {history.years.length} years:{" "}
      {diffs.map((d) => `April ${d.year} (paid ${formatRate(d.paid)}, rule ${formatRate(d.rule)})`).join(", ")}. The rises
      paid used the figures first published
      {firstDiff ? `, and April ${first}'s followed September ${first - 1} RPI` : ""}.
    </p>
  );
}

export function PastYears({ history, labels }) {
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
      <ToggleGroup label="Plan starts in" options={history.groups.map((g) => ({ id: g.id, label: g.label }))} value={group.id} onChange={setSelected} />

      {group.changesAnything && group.model ? (
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
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
        <p className="mt-6 text-sm text-slate-700" data-testid="past-no-difference">
          Had it started in {group.label}, the plan would have paid the same as the triple lock every year to April{" "}
          {history.years.at(-1)}.
        </p>
      )}

      <div className="mt-8">
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
      <ReplayNote history={history} />
    </section>
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
          We scored {pub.ranges.length} ways of putting a range on the two inputs, and the OBR forecast alone, against
          what followed {n} past OBR forecasts ({shortOrigin(pub.origins[0])} to {shortOrigin(pub.origins.at(-1))}).
          Each method is fitted only on data dated before the forecast, using today&apos;s revised figures, and scored
          on the September CPI and May–July earnings that set the next four April rises. The score for the gap between
          the triple lock and the Burnham plan is CRPS in percentage points of the pension; lower is better.
        </p>
        <p>
          The triple lock costs more than the Burnham plan when the lead passes between earnings and the higher of
          CPI and 2.5%: that is when the ratchet pays out. How April 2022 is scored decides the result. Scored on the
          published May–July 2021 earnings growth of {formatRate(pub.april2022.earnings)},{" "}
          {allUnder ? "every method predicted fewer switches between CPI and earnings than happened, and " : ""}
          the best placed {cov.published.best} of {n} realised gaps in its middle 80%. Scored with earnings equal to
          CPI ({formatRate(sus.april2022.cpi)}) that April, as the law set it when the earnings link was suspended, the
          best placed {cov.suspended.best} of {n}
          {missedAll.length
            ? `; ${cov.suspended.leader.label.toLowerCase()} missed the ${yearsLabel(missedAll.map(shortOrigin))} forecasts${
                missedPeak ? `, whose four rises include April ${peak}, set by September CPI of ${formatRate(peakCpi)}` : ""
              }`
            : ""}
          . Neither is a reliable 80% range, so this page reports the expected saving and a few paths, not odds.
        </p>
        {small.length ? (
          <p data-testid="backtest-small-ensembles">
            {small.map((r) => r.label).join(" and ")} {small.length === 1 ? "has" : "have"} only {small[0].minDraws}–
            {small[0].maxDraws} paths at these forecasts, so {small.length === 1 ? "its" : "their"} &ldquo;middle
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
