"use client";

import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { colors } from "../lib/colors";
import { getPastYearsCheck, isNum } from "../lib/dataHelpers";
import { ordinal } from "../lib/formatters";
import { niceAxis } from "../lib/ticks";
import { getHistory } from "../lib/trajectoryHelpers";
import { ChartFrame, PastYears, PastYearsNote, trajectoryLabels } from "./PathCharts";
import { AXIS_STYLE, CustomTooltip, Panel, Section, Unavailable } from "./ui";

export const INPUT_COLORS = { cpi: colors.gray[500], earnings: colors.primary[400], floor: colors.gray[300] };
export const BINDING_COLORS = { cpi: colors.gray[500], earnings: colors.primary[500], floor: colors.gray[300] };
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
        { label: "2.5%", color: colors.gray[400], dashed: true },
      ]}
    >
      <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} tickFormatter={(v) => `${v}%`} {...niceAxis(data.flatMap((r) => [r.cpi, r.earnings, 2.5]))} />
        <ReferenceLine y={2.5} stroke={colors.gray[400]} strokeDasharray="4 4" />
        <Tooltip content={<CustomTooltip formatter={(v) => `${v.toFixed(1)}%`} />} />
        <Line dataKey="cpi" name="September CPI" stroke={INPUT_COLORS.cpi} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
        <Line dataKey="earnings" name="May–July earnings" stroke={INPUT_COLORS.earnings} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
      </LineChart>
    </ChartFrame>
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
  { key: "triple_lock", label: "Triple lock", color: colors.primary[800] },
  { key: "earnings", label: "Earnings alone", color: colors.primary[400] },
  { key: "cpi", label: "CPI alone", color: colors.gray[500] },
  { key: "floor", label: "2.5% a year", color: colors.gray[300] },
];

function IndexHistory({ rows }) {
  const first = rows[0].year - 1;
  const data = [{ april: String(first), triple_lock: 100, earnings: 100, cpi: 100, floor: 100 },
    ...rows.map((r) => ({ april: String(r.year), ...Object.fromEntries(INDEX_SERIES.map((s) => [s.key, 100 * r.idx[s.key]])) }))];
  return (
    <ChartFrame legend={INDEX_SERIES.map((s) => ({ label: s.label, color: s.color }))}>
      <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
        <XAxis dataKey="april" tick={AXIS_STYLE} />
        <YAxis tick={AXIS_STYLE} {...niceAxis(data.flatMap((r) => INDEX_SERIES.map((s) => r[s.key])), { includeZero: false })} />
        <Tooltip content={<CustomTooltip formatter={(v) => v.toFixed(1)} />} />
        {INDEX_SERIES.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={s.key === "triple_lock" ? 3 : 2} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export default function StepTripleLock({ data }) {
  const record = getTripleLockRecord(data);
  const history = getHistory(data);
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
        lead="Each April the pension rises by the highest of CPI, earnings growth and 2.5%, and keeps every gain."
        boxed={false}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel>
            <h3 className="mb-2 font-semibold text-slate-800">The three figures behind each April&apos;s rise</h3>
            <InputsHistory rows={rows} />
          </Panel>
          <Panel>
            <h3 className="mb-2 font-semibold text-slate-800">The rise, and which figure set it</h3>
            <RisesHistory rows={rows} />
          </Panel>
        </div>
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

      <Section
        id="earlier"
        title="If the Burnham plan had started earlier"
        lead="The plan keeps the 2.5% floor and price protection but drops the ratchet. Pick a start year."
        boxed={false}
      >
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
      </Section>
    </div>
  );
}
