"use client";

import { useState } from "react";

import { fyLabel, getAssumptions, getDwp, getExpectedValue, getFinalYear, getSwitchYear, isNum, isPreBudget, isScenariosOnly } from "../lib/dataHelpers";
import { formatBn, formatCount } from "../lib/formatters";
import BenchmarksTable from "./Benchmarks";
import { Section, TopicPanel, Unavailable } from "./ui";

const Z = 1.96;

export function pm(estimate, digits = 1) {
  if (!estimate || !isNum(estimate.mean) || !isNum(estimate.se)) return "unavailable";
  return `${formatBn(estimate.mean, digits)} ± ${formatBn(Z * estimate.se, digits)}`;
}

/**
 * The expected saving under each weighting of the same full runs, as points with 95% whiskers on one £bn axis: gross
 * as the point, the rest (net, effective paths and runs) on hover. The weighting used here is highlighted.
 */
function CalibrationTable({ ev }) {
  const [hover, setHover] = useState(null);
  const i = ev.years.length - 1;
  const rows = [
    { name: ev.primaryName, label: "OBR means, the model's own dynamics", used: true, gross: ev.primary.gross[i], net: ev.primary.net[i], ess: ev.nDraws, runs: ev.nRuns },
    ...ev.sensitivities.map((s) => ({ name: s.name, label: s.label.replace(/^Tilted to /, ""), gross: s.gross[i], net: s.net[i], ess: s.ess, runs: s.effectiveRuns })),
  ].filter((r) => isNum(r.gross?.mean) && isNum(r.gross?.se));
  const hi = Math.max(...rows.map((r) => r.gross.mean + Z * r.gross.se));
  const top = Math.ceil(hi / 5) * 5 || 5;
  const x = (v) => `${(100 * Math.max(0, v)) / top}%`;
  const ticks = Array.from({ length: top / 5 + 1 }, (_, k) => k * 5);
  return (
    <figure className="rounded-xl border border-slate-200 bg-white px-5 py-4" data-testid="calibration-table">
      <figcaption className="text-sm font-medium text-slate-900">
        {ev.modelConditional ? "Model-conditional saving" : "Expected saving"}, {fyLabel(ev.years[i])}, gross, by weighting
      </figcaption>
      <div className="mt-3 space-y-1">
        {rows.map((r, k) => (
          <div
            key={r.name}
            className={`relative grid grid-cols-[minmax(0,15rem)_1fr_6.5rem] items-center gap-3 rounded-md px-2 py-1.5 ${hover === k ? "bg-slate-50" : ""}`}
            onMouseEnter={() => setHover(k)}
            onMouseLeave={() => setHover(null)}
          >
            <span className={`text-xs leading-4 ${r.used ? "font-semibold text-teal-800" : "text-slate-600"}`}>{r.label}{r.used ? " (used here)" : ""}</span>
            <div className="relative h-5">
              <div className="absolute inset-x-0 top-1/2 h-px bg-slate-100" />
              <span className="absolute top-1/2 h-px -translate-y-1/2 bg-slate-500" style={{ left: x(r.gross.mean - Z * r.gross.se), width: x(2 * Z * r.gross.se) }} />
              <span className="absolute top-1/2 h-2.5 w-px -translate-y-1/2 bg-slate-500" style={{ left: x(r.gross.mean - Z * r.gross.se) }} />
              <span className="absolute top-1/2 h-2.5 w-px -translate-y-1/2 bg-slate-500" style={{ left: x(r.gross.mean + Z * r.gross.se) }} />
              <span
                className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ${r.used ? "h-3.5 w-3.5 bg-teal-700" : "h-3 w-3 bg-teal-400"}`}
                style={{ left: x(r.gross.mean) }}
              />
            </div>
            <span className="text-right text-xs tabular-nums text-slate-700">{pm(r.gross)}</span>
            {hover === k ? (
              <div className="pointer-events-none absolute right-28 top-full z-10 mt-1 w-64 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-lg">
                <div className="mb-1 font-semibold text-slate-800">{r.label}</div>
                <div>Gross: <span className="font-medium text-slate-900">{pm(r.gross)}</span></div>
                <div>Net: <span className="font-medium text-slate-900">{pm(r.net)}</span></div>
                <div>Effective paths: {formatCount(Math.round(r.ess))} of {formatCount(ev.nDraws)}</div>
                <div>Effective full runs: {formatCount(Math.round(r.runs))} of {formatCount(ev.nRuns)}</div>
              </div>
            ) : null}
          </div>
        ))}
        <div className="grid grid-cols-[minmax(0,15rem)_1fr_6.5rem] gap-3 px-2">
          <span />
          <div className="relative h-4 text-[11px] text-slate-500">
            {ticks.map((t, k) => (
              <span key={t} className={`absolute ${k === 0 ? "" : k === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2"}`} style={{ left: x(t) }}>
                {formatBn(t, 0)}
              </span>
            ))}
          </div>
          <span />
        </div>
      </div>
      <p className="mt-3 text-[11px] text-slate-500">Whiskers: 95% Monte Carlo error. Hover a row for net and how many runs it rests on.</p>
    </figure>
  );
}

/** The explanation of the expected saving and its spread, for the chart's closed "How to read" box. */
export function ExpectedDetails({ data }) {
  const ev = getExpectedValue(data);
  const final = getFinalYear(data);
  const switchYear = getSwitchYear(data);
  if (!ev || !final) return null;
  const i = ev.years.indexOf(final);
  return (
    <ul className="list-disc space-y-2 pl-5">
      <li data-testid="summary-explainer">
        <strong>The rule.</strong>{" "}Triple lock until April {switchYear ? switchYear - 1 : "2029"}; from April{" "}
        {switchYear ?? 2030}, at least the higher of CPI and 2.5%, topped up to keep the 2029-30 value relative to
        earnings.
      </li>
      <li>
        <strong>Where the saving comes from.</strong>{" "}Years when CPI or 2.5% beats earnings: the triple lock keeps
        the extra for good, the plan waits for earnings to catch up.
      </li>
      <li>
        <strong>How we average.</strong>{" "}{formatCount(ev.nDraws)}{" "}paths of CPI and earnings centred on the
        OBR&apos;s forecast; {formatCount(ev.nUniquePaths)}{" "}run in full, oversampling paths with large savings.
      </li>
      {ev.netExcludingLargest ? (
        <li>
          <strong>One survey record.</strong>{" "}Without the record that moves net figures most, the{" "}
          {fyLabel(final)}{" "}net saving would be {formatBn(ev.netExcludingLargest[i].mean, 1)}.
        </li>
      ) : null}
      {ev.gap ? (
        <li data-testid="uncertain-note">
          <strong>How far the pension falls.</strong>{" "}In {fyLabel(final)} the full new State Pension is £
          {ev.gap.mean_gap_gbp_week.toFixed(2)}{" "}a week lower on average; £{ev.gap.gap_gbp_week.p10.toFixed(2)} to £
          {ev.gap.gap_gbp_week.p90.toFixed(2)}{" "}on the middle 80% of paths.
        </li>
      ) : null}
    </ul>
  );
}

/** Why the figures differ from DWP's: the population bullet comes from the file's own assumptions block when it has one. */
function DwpDifferences({ data, premium, scenariosOnly }) {
  const population = (getAssumptions(data) ?? []).find((it) => it.key === "population");
  return (
    <div className="text-sm leading-6 text-slate-700">
      <ul className="list-disc space-y-1 pl-5" data-testid="dwp-differences">
        <li>
          DWP runs one unstated uprating path;{" "}
          {scenariosOnly ? "this page shows the scenarios above." : "ours averages over paths."}
        </li>
        {population ? (
          <li>
            DWP&apos;s Pensim3 projects the population and each pension; ours reweights today&apos;s survey.
          </li>
        ) : (
          <li>
            DWP&apos;s Pensim3 projects the population; here the survey is not aged (ages top-coded at 80, pension
            types fixed), so pensioner numbers change only through the weights and the State Pension age rising to 67.
          </li>
        )}
        <li>DWP counts direct spending only; we show gross spending and the net figure.</li>
        <li>DWP covers Great Britain, the model the UK; both in cash terms.</li>
        {premium && isNum(premium.triple_lock) && isNum(premium.burnham_2030) ? (
          <li data-testid="premium-note">
            The OBR assumes the triple lock beats earnings by 0.6 points a year. On our paths it beats May–July
            earnings by {(premium.triple_lock * 100).toFixed(2)}{" "}points a year in Aprils 2034 to 2039 (Burnham plan:{" "}
            {(premium.burnham_2030 * 100).toFixed(2)}).
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function dwpTopic(data, dwp, premium, scenariosOnly) {
  return {
    id: "dwp",
    testId: "dwp-box",
    title: dwp ? `Against DWP's £${dwp.nominal2039}bn` : "Against DWP's figure",
    summary: scenariosOnly ? "DWP projects the population and covers Great Britain only." : "DWP uses one path, projects the population and covers Great Britain only.",
    content: <DwpDifferences data={data} premium={premium} scenariosOnly={scenariosOnly} />,
  };
}

function benchmarksTopic(data) {
  return {
    id: "benchmarks",
    testId: "benchmarks-box",
    title: "Other published costings",
    summary: "OBR, Resolution Foundation and DWP figures beside ours.",
    content: <BenchmarksTable data={data} />,
  };
}

const CHOICES_TITLE = "How our costing compares";

export default function SummaryTab({ data }) {
  const ev = getExpectedValue(data);
  const dwp = getDwp(data);
  const final = getFinalYear(data);
  if (isScenariosOnly(data)) {
    // No expected value: only the comparisons that do not rest on one.
    return (
      <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="summary-tab">
        <Section id="choices" title="How the answer compares" lead="Against DWP and other costings." boxed={false}>
          <TopicPanel testId="choices-panel" topics={[dwpTopic(data, dwp, null, true), benchmarksTopic(data)]} />
        </Section>
      </div>
    );
  }
  if (!ev || !final) return <Unavailable what="The expected saving" />;
  const premium = ev.gap?.mean_rate_minus_earnings_2034_2039;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="summary-tab">
      {ev.modelConditional && !isPreBudget(data) ? <p>{ev.ruling === "b" ? "Model-conditional expected value. The original macro model fails its frozen adequacy backtest; Monte Carlo errors measure precision of this model path set." : "Model-conditional expected value. Monte Carlo errors measure precision of the recorded model path set."}</p> : null}
      <Section
        id="choices"
        title={CHOICES_TITLE}
        lead="Against DWP, other weightings and other costings."
        boxed={false}
      >
        <TopicPanel
          testId="choices-panel"
          topics={[
            dwpTopic(data, dwp, premium, false),
            {
              id: "weighting",
              testId: "calibration-box",
              title: "Other path weightings",
              summary: "The saving if paths are weighted to past volatility.",
              content: (
                <>
                    <p className="mb-3 text-sm leading-6 text-slate-600">
                          Each row reweights the same full runs; with fewer effective runs its ± is approximate. Rows
                          matched to past volatility were more biased in our backtest (Methodology tab), so they are
                          sensitivities only.
                        </p>
                        <CalibrationTable ev={ev} />
                </>
              ),
            },
            benchmarksTopic(data),
          ].filter(Boolean)}
        />
      </Section>
    </div>
  );
}
