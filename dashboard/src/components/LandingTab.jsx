"use client";

import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors } from "../lib/colors";
import { fyLabel, getAssumptions, getCentral, getCoverageRow, getExpectedValue, getFinalYear, getSavingHistogram, getSavingSpread, getSensitivityRange, getSwitchYear, isNum } from "../lib/dataHelpers";
import { formatBn, formatPct } from "../lib/formatters";
import { axisDigits, niceAxis } from "../lib/ticks";
import ChartLogo from "./ChartLogo";
import { ExpectedDetails } from "./SummaryTab";
import { AXIS_STYLE, CustomTooltip, LegendSwatches, Section, Select, Unavailable } from "./ui";

const BAND_OUTER = colors.primary[200];
const BAND_INNER = colors.primary[400];
const AVERAGE = colors.primary[900];
const MEDIAN = colors.primary[700];
const CENTRAL = colors.gray[500];

const MEASURES = [
  { id: "net", label: "Net of tax and benefits" },
  { id: "gross", label: "Gross State Pension spending" },
];

const MARK = colors.primary[800];
const CENTRAL_MARK = colors.gray[500];

/**
 * A small histogram of one figure across the model's paths: the middle 80% shaded, the median and the average
 * marked, and optionally the central forecast. `show` picks which marks appear, and the legend lists only those.
 */
function SpreadStrip({ hist, central, show = ["band", "median", "average"] }) {
  const W = 240;
  const H = 46;
  const T = 6; // room above the bars for the average's dot
  const x = (v) => Math.min(W, Math.max(0, ((v - hist.lo) / (hist.hi - hist.lo || 1)) * W));
  const maxW = Math.max(...hist.bins.map((b) => b.weight)) || 1;
  const bw = W / hist.bins.length;
  const band = show.includes("band");
  const legend = [
    band && { key: "band", label: "Middle 80%", swatch: <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: colors.primary[400] }} /> },
    show.includes("median") && { key: "median", label: "Median", swatch: <span className="inline-block h-3 w-[2px]" style={{ backgroundColor: MARK }} /> },
    show.includes("average") && { key: "average", label: "Average", swatch: <span className="inline-block h-3 w-[2px]" style={{ backgroundColor: MARK }} /> },
    isNum(central) && { key: "central", label: "OBR central", swatch: <span className="inline-block h-3 border-l-2 border-dashed" style={{ borderColor: CENTRAL_MARK }} /> },
  ].filter(Boolean);
  return (
    <div className="mt-auto pt-4" data-testid="spread-strip">
      <svg viewBox={`0 ${-T} ${W} ${H + T + 4}`} className="h-auto w-full" role="img" aria-label="Spread across the model's paths">
        {hist.bins.map((b, i) => {
          const h = (b.weight / maxW) * H;
          const mid = (b.x0 + b.x1) / 2;
          const inside = !band || (mid >= hist.p10 && mid <= hist.p90);
          return <rect key={i} x={i * bw + 0.5} y={H - h} width={Math.max(0, bw - 1)} height={h} rx={1} fill={inside ? colors.primary[400] : colors.primary[100]} />;
        })}
        <line x1={0} x2={W} y1={H + 0.5} y2={H + 0.5} stroke={colors.gray[300]} />
        {show.includes("median") ? <line x1={x(hist.p50)} x2={x(hist.p50)} y1={0} y2={H} stroke={MARK} strokeWidth={2} /> : null}
        {isNum(central) ? <line x1={x(central)} x2={x(central)} y1={0} y2={H} stroke={CENTRAL_MARK} strokeWidth={2} strokeDasharray="3 2" /> : null}
        {show.includes("average") ? (
          <>
            <line x1={x(hist.mean)} x2={x(hist.mean)} y1={-2} y2={H} stroke={MARK} strokeWidth={2} />
            <circle cx={x(hist.mean)} cy={-2} r={3} fill={MARK} />
          </>
        ) : null}
      </svg>
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {legend.map((l) => (
          <span key={l.key} className="flex items-center gap-1">
            {l.swatch}
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * What the headline figures are conditional on, computed from the file's figures: the strip for a results file
 * built before the pipeline wrote its own assumptions block.
 */
function computedAssumptions(data, final) {
  const ev = getExpectedValue(data);
  const i = ev ? ev.years.indexOf(final) : -1;
  const range = getSensitivityRange(data, "gross", final);
  const claims = getCoverageRow(data, "pension_credit_claims_m");
  const hb = getCoverageRow(data, "housing_benefit_pension_age_bn");
  // Microcosm minus the Enhanced FRS on the same paths (paired), and how many paths that rests on.
  const paired = ev?.diff?.net?.[i];
  const nPaired = ev?.nSensitivity;
  const coverageYear = Number.isInteger(data?.coverage?.year) ? fyLabel(data.coverage.year) : null;
  const top = range?.max
    ? `, which rests on about ${Math.round(range.max.effectiveRuns)} effective runs (standard error ${formatBn(range.max.se, 1)})`
    : "";
  const dataset = paired && nPaired > 0
    ? ` On the same ${nPaired} paths, the Microcosm dataset gives a net saving ${formatBn(Math.abs(paired.mean), 1)} ${paired.mean >= 0 ? "higher" : "lower"} (standard error ${formatBn(paired.se, 1)}).`
    : "";
  return [
    {
      key: "population",
      title: "Today's pensioners, held fixed",
      text: `Survey ages and State Pension types are fixed to ${fyLabel(final)}, so nobody new joins on the new State Pension; the number of pensioners changes only through the survey weights and the State Pension age. DWP's costing projects the population; ours does not.`,
    },
    range && {
      key: "paths",
      title: "One model of prices and earnings",
      text: `Its paths are shifted to the OBR's average forecast. Reweighting the same full runs to match how much the gap between earnings growth and CPI varied in the past and how often the lead switched (in some versions also how often the 2.5% floor binds) gives separate point estimates, the lowest ${formatBn(range.lo, 1)} gross${range.min ? ` (standard error ${formatBn(range.min.se, 1)})` : ""} and the highest ${formatBn(range.hi, 1)}${top}. This range does not include another model of prices and earnings: Student-t and Gaussian versions are tested against past forecasts (Methodology tab) but not run through the full fiscal model.`,
    },
    claims && hb && coverageYear && {
      key: "benefits",
      title: "Survey benefit baselines above DWP's",
      text: `In ${coverageYear} the survey has ${claims.primary.toFixed(2)}m Pension Credit claims against DWP's ${claims.dwp.toFixed(2)}m, and ${formatBn(hb.primary, 1)} of pension-age Housing Benefit against ${formatBn(hb.dwp, 1)}, a UK model against DWP's Great Britain figures.${dataset}`,
    },
  ].filter(Boolean);
}

/**
 * What the headline figures are conditional on, each with its number from the file: a strip under the cards, so no
 * one reads the net figure or the expected value as an unconditional forecast. The results file's own assumptions
 * block (written by the pipeline from the model's configuration) when it has a valid one; otherwise computed here.
 */
function Assumptions({ data, final }) {
  const items = getAssumptions(data) ?? computedAssumptions(data, final);
  return (
    <div className="mt-5" data-testid="assumptions">
      <p className="eyebrow mb-3 text-slate-500">What these figures assume</p>
      <div className="grid gap-4 md:grid-cols-3">
        {items.map((it) => (
          <div key={it.key} className="border-l-2 pl-4" style={{ borderColor: colors.gray[300] }} data-testid={`assumption-${it.key}`}>
            <p className="text-sm font-semibold text-slate-800">{it.title}</p>
            <p className="mt-1 text-sm leading-6 text-slate-600">{it.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Card({ label, value, detail, testId, children }) {
  return (
    <div className="metric-card flex flex-col" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-600">{detail}</p> : null}
      {children}
    </div>
  );
}

function SpreadChart({ rows }) {
  const values = rows.flatMap((r) => [r.p10, r.p90, r.central]).filter(isNum);
  const range = (a, b) => `${formatBn(a, 1)} to ${formatBn(b, 1)}`;
  return (
    <>
      <div style={{ height: 360 }} data-testid="spread-chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} />
            <XAxis dataKey="label" tick={AXIS_STYLE} />
            <YAxis tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, axisDigits(values))} {...niceAxis(values)} />
            <ReferenceLine y={0} stroke={colors.gray[400]} />
            <Tooltip
              content={
                <CustomTooltip formatter={(v) => (Array.isArray(v) ? range(v[0], v[1]) : formatBn(v, 1))} />
              }
            />
            <Area dataKey="outer" name="Middle 80% of paths" stroke="none" fill={BAND_OUTER} fillOpacity={0.45} isAnimationActive={false} />
            <Area dataKey="inner" name="Middle 50% of paths" stroke="none" fill={BAND_INNER} fillOpacity={0.45} isAnimationActive={false} />
            <Line dataKey="mean" name="Average across paths" stroke={AVERAGE} strokeWidth={3} dot={false} isAnimationActive={false} />
            <Line dataKey="p50" name="Median path" stroke={MEDIAN} strokeDasharray="2 3" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="central" name="OBR central forecast" stroke={CENTRAL} strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <LegendSwatches
        items={[
          { label: "Average across paths", color: AVERAGE },
          { label: "Median path", color: MEDIAN, dashed: true },
          { label: "Middle 50% of paths", color: BAND_INNER },
          { label: "Middle 80% of paths", color: BAND_OUTER },
          { label: "On the OBR's central forecast", color: CENTRAL, dashed: true },
        ]}
      />
      <ChartLogo />
    </>
  );
}

export default function LandingTab({ data }) {
  const [measure, setMeasure] = useState("net");
  const spread = getSavingSpread(data);
  const ev = getExpectedValue(data);
  const central = getCentral(data);
  const final = getFinalYear(data);
  const switchYear = getSwitchYear(data);
  if (!spread || !ev || !central || !final) return <Unavailable what="The summary" />;

  const i = ev.years.indexOf(final);
  const from = switchYear ?? ev.years[0];
  const rows = spread[measure]
    .map((r, k) => ({ ...r, central: central[measure][k], mean: ev.primary[measure][k].mean }))
    .filter((r) => r.year >= from)
    .map((r) => ({ ...r, label: fyLabel(r.year), outer: [r.p10, r.p90], inner: [r.p25, r.p75] }));
  const last = (key) => spread[key].find((r) => r.year === final);
  const netLast = last("net");
  const grossLast = last("gross");
  const losing = ev.losing?.[i]?.mean;
  const netHist = getSavingHistogram(data, "net", final);
  const losingHist = getSavingHistogram(data, "households_losing_pct", final, { binZero: false });
  const fy = fyLabel(final).replace("-", "\u2011"); // a non-breaking hyphen keeps "2039-40" on one line
  const losingDetail = losingHist
    ? `Expected share of households in ${fy}. On 80% of paths it is between ${formatPct(losingHist.p10, 0)} and ${formatPct(losingHist.p90, 0)}.`
    : `Expected share of households in ${fy}.`;
  const centralPct = netHist ? Math.round(netHist.percentileOf(central.net[i])) : null;

  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="landing-tab">
      <Section id="at-a-glance" title="The plan at a glance" lead={`From April ${switchYear ?? 2030} the Burnham plan raises the pension by at least the higher of CPI and 2.5%, and never lets it fall behind earnings from its 2029-30 level, but drops the triple lock's ratchet. What it saves in ${fyLabel(final)}, and who pays:`} boxed={false}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card
            label={`Expected saving, ${fy}`}
            value={formatBn(ev.primary.net[i].mean, 1)}
            detail={`Net of tax and benefits; ${formatBn(ev.primary.gross[i].mean, 1)} in State Pension spending`}
            testId="landing-expected"
          >
            {netHist ? <SpreadStrip hist={netHist} show={["average"]} /> : null}
          </Card>
          <Card
            label="Middle 80% of paths"
            value={`${formatBn(netLast.p10, 1)} to ${formatBn(netLast.p90, 1)}`}
            detail={`Net, ${fy}; ${formatBn(grossLast.p10, 1)} to ${formatBn(grossLast.p90, 1)} gross`}
            testId="landing-range"
          >
            {netHist ? <SpreadStrip hist={netHist} show={["band", "median"]} /> : null}
          </Card>
          <Card
            label="On the OBR's central forecast"
            value={formatBn(central.net[i], 1)}
            detail={centralPct !== null ? `Net; ${100 - centralPct}% of the model's paths save more` : "Net, on one smooth path that misses most of the saving"}
            testId="landing-central"
          >
            {netHist ? <SpreadStrip hist={netHist} central={central.net[i]} show={[]} /> : null}
          </Card>
          <Card
            label="Households with lower income"
            value={isNum(losing) ? formatPct(losing, 0) : "unavailable"}
            detail={losingDetail}
            testId="landing-losing"
          >
            {losingHist ? <SpreadStrip hist={losingHist} show={["band", "average"]} /> : null}
          </Card>
        </div>
        <Assumptions data={data} final={final} />
      </Section>

      <Section
        id="each-year"
        title="The saving each year"
        lead="The average saving across every simulated path, the range around it, and the OBR's central forecast alone."
        detailsTitle="How to read this chart"
        details={
          <>
            <p>
              Each band shows the spread of the saving across {spread.nRuns}{" "}full PolicyEngine UK runs, standing for
              thousands of simulated paths of prices and earnings calibrated to the OBR&apos;s forecast. The dashed line
              is the OBR&apos;s own central forecast, which sits near the bottom: on that one smooth path earnings lead
              almost every year, so the plan barely bites.
            </p>
            <p data-testid="spread-caveat">
              The bands are a spread of scenarios, not forecast probabilities: testing the model on past forecasts shows its
              ranges are too narrow to read as probabilities (see the Methodology tab).
            </p>
            <ExpectedDetails data={data} />
          </>
        }
      >
        <div className="mb-4">
          <Select label="Show" options={MEASURES} value={measure} onChange={setMeasure} />
        </div>
        <SpreadChart rows={rows} />
      </Section>
    </div>
  );
}
