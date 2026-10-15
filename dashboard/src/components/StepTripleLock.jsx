"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { colors, SERIES } from "../lib/colors";
import { getPastYearsCheck, isNum } from "../lib/dataHelpers";
import { formatPct, ordinal } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { getHistory } from "../lib/trajectoryHelpers";
import { ChartFrame, PastYears, PastYearsNote, trajectoryLabels } from "./PathCharts";
import { AXIS_STYLE, CollapsibleSection, CustomTooltip, Panel, Section, Unavailable, ViewSwitch } from "./ui";

export const INPUT_COLORS = { cpi: SERIES.cpi, earnings: SERIES.earnings, floor: SERIES.floor };
export const BINDING_COLORS = { cpi: SERIES.cpi, earnings: SERIES.earnings, floor: SERIES.floor };
export const BINDING_WORDS = { cpi: "CPI", earnings: "Earnings", floor: "2.5% floor" };

/** The triple lock's own record from the results file, validated, or null. */
export function getTripleLockRecord(data) {
  const t = data?.trajectories?.history?.triple_lock;
  const h = data?.trajectories?.history;
  const years = t?.years;
  if (!Array.isArray(years) || !years.length || !h) return null;
  const rows = years.map((y) => ({
    year: y,
    cpi: h.cpi?.[String(y)],
    earnings: t.earnings_published?.[String(y)],
    rate: t.rate?.[String(y)],
    paid: h.actual_rise?.[String(y)],
    binding: t.binding?.[String(y)],
    idx: Object.fromEntries(["triple_lock", "cpi", "earnings", "floor"].map((k) => [k, t.index?.[k]?.[String(y)]])),
  }));
  const ok = rows.every((r) => [r.cpi, r.earnings, r.rate].every(isNum) && BINDING_WORDS[r.binding] && Object.values(r.idx).every(isNum));
  return ok ? { rows, note: t.note } : null;
}

function InputsHistory({ rows }) {
  const data = rows.map((r) => ({ april: String(r.year), cpi: r.cpi * 100, earnings: r.earnings * 100 }));
  return (
    <ChartFrame
      legend={[
        { label: "September CPI, the year before", color: INPUT_COLORS.cpi },
        { label: "May–July earnings growth, the year before", color: INPUT_COLORS.earnings },
        { label: "2.5%", color: SERIES.floor, dashed: true },
      ]}
    >
      <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => `${v}%`} {...niceAxis(data.flatMap((r) => [r.cpi, r.earnings, 2.5]))} />
        <ReferenceLine y={2.5} stroke={SERIES.floor} strokeDasharray="4 4" />
        <Tooltip content={<CustomTooltip formatter={(v) => `${v.toFixed(1)}%`} />} />
        <Line dataKey="cpi" name="September CPI" stroke={INPUT_COLORS.cpi} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
        <Line dataKey="earnings" name="May–July earnings" stroke={INPUT_COLORS.earnings} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
      </LineChart>
    </ChartFrame>
  );
}

const RULE_VIEWS = [
  { id: "inputs", label: "The three figures" },
  { id: "rises", label: "The rise and what set it" },
];

/** The rule's record as one chart: the three figures behind each April's rise, or the rise and which figure set it. */
function RuleHistory({ rows }) {
  const [view, setView] = useState("inputs");
  return (
    <div data-testid="rule-history">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold text-slate-800">
          {view === "inputs" ? "The three figures behind each April\u2019s rise" : "Each April\u2019s rise, and which figure set it"}
        </h3>
        <ViewSwitch options={RULE_VIEWS} value={view} onChange={setView} />
      </div>
      {view === "inputs" ? <InputsHistory rows={rows} /> : <RisesHistory rows={rows} />}
    </div>
  );
}

function RisesHistory({ rows }) {
  const data = rows.map((r) => ({ april: String(r.year), rate: r.rate * 100, binding: r.binding }));
  return (
    <ChartFrame legend={Object.entries(BINDING_WORDS).map(([k, label]) => ({ label: `Set by ${label === "Earnings" ? "earnings" : label}`, color: BINDING_COLORS[k] }))}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => `${v}%`} {...niceAxis(data.map((r) => r.rate))} />
        <Tooltip content={<CustomTooltip formatter={(v, _n, e) => `${v.toFixed(1)}% (${BINDING_WORDS[e.payload.binding].toLowerCase()})`} />} />
        <Bar dataKey="rate" name="Triple lock rise" radius={[4, 4, 0, 0]} isAnimationActive={false}>
          {data.map((r) => (
            <Cell key={r.april} fill={BINDING_COLORS[r.binding]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

const INDEX_SERIES = [
  { key: "triple_lock", label: "Triple lock", color: SERIES.tripleLock },
  { key: "earnings", label: "Earnings alone", color: SERIES.earnings, dashed: true },
  { key: "cpi", label: "CPI alone", color: SERIES.cpi, dashed: true },
  { key: "floor", label: "2.5% a year", color: SERIES.floor, dashed: true },
];

function IndexHistory({ rows }) {
  const first = rows[0].year - 1;
  const data = [{ april: String(first), triple_lock: 100, earnings: 100, cpi: 100, floor: 100 },
    ...rows.map((r) => ({ april: String(r.year), ...Object.fromEntries(INDEX_SERIES.map((s) => [s.key, 100 * r.idx[s.key]])) }))];
  return (
    <ChartFrame legend={INDEX_SERIES.map((s) => ({ label: s.label, color: s.color, dashed: s.dashed }))}>
      <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} {...niceAxis(data.flatMap((r) => INDEX_SERIES.map((s) => r[s.key])), { includeZero: false })} />
        <Tooltip content={<CustomTooltip formatter={(v) => v.toFixed(1)} />} />
        {INDEX_SERIES.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={s.key === "triple_lock" ? 3 : 2} strokeDasharray={s.dashed ? "5 4" : undefined} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export default function StepTripleLock({ data }) {
  const record = getTripleLockRecord(data);
  const history = getHistory(data);
  // One line under the closed section's title: the first start year's effect on today's pension, from the replay.
  const first = history?.groups?.[0];
  const firstYear = first?.label?.match(/\d{4}/)?.[0];
  const preview = first?.changesAnything && isNum(first.finalRatio) && firstYear && first.finalRatio !== 1
    ? `Had it started in April ${firstYear}, today's full new State Pension would be ${formatPct(Math.abs(first.finalRatio - 1) * 100)} ${first.finalRatio < 1 ? "lower" : "higher"}.`
    : null;
  const labels = trajectoryLabels(data);
  const check = getPastYearsCheck(data);
  if (!record) return <Unavailable what="The triple lock's record" />;
  const { rows } = record;
  const counts = Object.fromEntries(Object.keys(BINDING_WORDS).map((k) => [k, rows.filter((r) => r.binding === k).length]));
  const last = rows.at(-1);
  const gap = (last.idx.triple_lock / last.idx.earnings - 1) * 100;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="step-triple-lock">
      <Section
        id="rule"
        title="How the triple lock works"
        lead="What has set each April's rise since 2011, and how the triple lock's ratchet adds up over time."
        boxed={false}
      >
        <Panel>
          <RuleHistory rows={rows} />
        </Panel>
        <Panel footerTitle="The rule and its record since 2011" footer={<>
              <p>
                CPI is the year to the previous September; earnings are average weekly total pay in the previous
                May–July. A year when CPI beats earnings raises the pension for good.
              </p>
              <p data-testid="binding-counts">
                April {rows[0].year} to April {last.year}: CPI sets the rise{" "}
                {counts.cpi} times, earnings {counts.earnings} times and the 2.5% floor {counts.floor} times. The pension
                rises {((last.idx.triple_lock - 1) * 100).toFixed(0)}%, against{" "}
                {((last.idx.earnings - 1) * 100).toFixed(0)}% for earnings and {((last.idx.cpi - 1) * 100).toFixed(0)}% for
                prices: {gap.toFixed(0)}% above an earnings link alone.
              </p>
          {record.note ? <p>{record.note}</p> : null}
</>} className="mt-5">
          <h3 className="mb-2 font-semibold text-slate-800">What the ratchet adds up to (before April {rows[0].year} = 100)</h3>
          <IndexHistory rows={rows} />
        </Panel>
      </Section>

      <CollapsibleSection
        id="earlier"
        title="If the Burnham plan had started earlier"
        lead="The plan keeps the 2.5% floor and price protection but drops the ratchet."
        preview={preview}
        showLabel="Pick a start year"
        testId="earlier-expandable"
      >
          <div>
        {history && labels.triple_lock ? <PastYears history={history} labels={labels} footerTitle="The plan, and how this comparison works" footer={<>
              <p>
                After a year when prices or the floor beat earnings, the plan waits for earnings to catch up; the triple
                lock carries the gain forward.
              </p>
            {history ? <PastYearsNote history={history} /> : null}
            {check?.screen === "c2" ? <p data-testid="past-years-check">
                Checked on the past, the model expects a gap of {check.model.mean_gap_pct.toFixed(1)}% of the pension; the actual gap was {check.realised_gap_pct.toFixed(1)}%, its {ordinal(Math.round(check.model.realised_percentile))} percentile. With published earnings (a sensitivity only): {check.published.mean_gap_pct.toFixed(1)}% expected, {check.published.realised_gap_pct.toFixed(1)}% actual, its {ordinal(Math.round(check.published.realised_percentile))} percentile.
              </p> : check ? (
              <p data-testid="past-years-check">
                Fitted on data to December {check.years[0] - 1}, our model expects a plan started in April{" "}
                {check.years[0] + 1} to open a gap of {check.model.mean_gap_pct.toFixed(1)}% by April {check.years[1] + 1};
                the actual gap was {check.realised_gap_pct.toFixed(1)}%, its{" "}
                {ordinal(Math.round(check.model.realised_percentile))} percentile.
              </p>
            ) : null}
          </>} /> : <Unavailable what="The past-years comparison" />}
          </div>
      </CollapsibleSection>
    </div>
  );
}
