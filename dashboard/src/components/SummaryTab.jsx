"use client";

import { fyLabel, getAssumptions, getDwp, getExpectedValue, getFinalYear, getSwitchYear, isNum, isPreBudget, isScenariosOnly } from "../lib/dataHelpers";
import { formatBn, formatCount } from "../lib/formatters";
import BenchmarksTable from "./Benchmarks";
import { Section, TopicPanel, Unavailable } from "./ui";

const Z = 1.96;

export function pm(estimate, digits = 1) {
  if (!estimate || !isNum(estimate.mean) || !isNum(estimate.se)) return "unavailable";
  return `${formatBn(estimate.mean, digits)} ± ${formatBn(Z * estimate.se, digits)}`;
}

function CalibrationTable({ ev }) {
  const i = ev.years.length - 1;
  const rows = [
    { name: ev.primaryName, label: "The OBR's means, the model's own dynamics (used here)", gross: ev.primary.gross[i], net: ev.primary.net[i], ess: ev.nDraws, runs: ev.nRuns },
    ...ev.sensitivities.map((s) => ({ name: s.name, label: s.label, gross: s.gross[i], net: s.net[i], ess: s.ess, runs: s.effectiveRuns })),
  ];
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="calibration-table">
        <thead>
          <tr>
            <th>How the paths are weighted</th>
            <th>{ev.modelConditional ? "Model-conditional saving" : "Expected saving"} {fyLabel(ev.years[i])}, gross</th>
            <th>Net</th>
            <th>Effective paths (of {formatCount(ev.nDraws)})</th>
            <th>Effective full runs (of {formatCount(ev.nRuns)})</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>{r.label}</td>
              <td className="tabular-nums">{pm(r.gross)}</td>
              <td className="tabular-nums">{pm(r.net)}</td>
              <td className="tabular-nums">{formatCount(Math.round(r.ess))}</td>
              <td className="tabular-nums">{formatCount(Math.round(r.runs))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
    title: dwp ? `Why it differs from DWP's £${dwp.nominal2039}bn` : "Why it differs from DWP's figure",
    summary: scenariosOnly ? "A dynamic population model, and Great Britain only." : "One path, a dynamic population model, and Great Britain only.",
    content: <DwpDifferences data={data} premium={premium} scenariosOnly={scenariosOnly} />,
  };
}

function benchmarksTopic(data) {
  return {
    id: "benchmarks",
    testId: "benchmarks-box",
    title: "Other published costings",
    summary: "OBR, Resolution Foundation and DWP figures beside our closest equivalent.",
    content: <BenchmarksTable data={data} />,
  };
}

const CHOICES_TITLE = "How the answer compares, and what it depends on";

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
              title: "How the paths are weighted",
              summary: "The saving with paths weighted to past volatility.",
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
