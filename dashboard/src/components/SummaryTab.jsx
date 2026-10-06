"use client";

import { fyLabel, getDwp, getExpectedValue, getFinalYear, getSwitchYear, isNum } from "../lib/dataHelpers";
import { formatBn, formatCount } from "../lib/formatters";
import BenchmarksTable from "./Benchmarks";
import MeanPathScenarios from "./MeanPathScenarios";
import { Section, TopicPanel, Unavailable } from "./ui";

const Z = 1.96;

export function pm(estimate, digits = 1) {
  if (!estimate || !isNum(estimate.mean) || !isNum(estimate.se)) return "unavailable";
  return `${formatBn(estimate.mean, digits)} ± ${formatBn(Z * estimate.se, digits)}`;
}

function DatasetTable({ ev }) {
  const show = ev.years.filter((y) => y >= 2031 && (y - 2031) % 4 === 0 || y === ev.years.at(-1));
  const years = [...new Set(show)];
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="dataset-table">
        <thead>
          <tr>
            <th>Year</th>
            <th>Enhanced FRS, gross</th>
            <th>Net</th>
            <th>Microcosm, gross</th>
            <th>Net</th>
            <th>Microcosm minus Enhanced FRS, gross (paired)</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const i = ev.years.indexOf(y);
            return (
              <tr key={y}>
                <td>{fyLabel(y)}</td>
                <td className="tabular-nums">{pm(ev.primary.gross[i])}</td>
                <td className="tabular-nums">{pm(ev.primary.net[i])}</td>
                <td className="tabular-nums">{pm(ev.sensitivity.gross[i])}</td>
                <td className="tabular-nums">{pm(ev.sensitivity.net[i])}</td>
                <td className="tabular-nums">{pm(ev.diff.gross[i], 2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
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
        <strong>The rule.</strong>{" "}The plan pays the triple lock until April {switchYear ? switchYear - 1 : "2029"}.
        From April {switchYear ?? 2030}{" "}the pension rises by at least the higher of CPI and 2.5%, plus whatever
        keeps it at its 2029-30 value relative to earnings (DWP&apos;s definition).
      </li>
      <li>
        <strong>Where the saving comes from.</strong>{" "}Years when CPI or the 2.5% floor runs ahead of earnings: the
        triple lock keeps that extra for good, while the plan waits for earnings to catch up. Otherwise the rules
        differ only by 0.1-point rounding.
      </li>
      <li>
        <strong>Why the central forecast shows little.</strong>{" "}On it earnings lead in almost every year from 2031,
        so what to expect depends on how often the lead changes hands.
      </li>
      <li>
        <strong>How we average.</strong>{" "}{formatCount(ev.nDraws)}{" "}paths of CPI and earnings from a monthly model,
        shifted so their calendar-year averages equal the OBR&apos;s forecast; {formatCount(ev.nUniquePaths)}{" "}of
        them run in full through PolicyEngine UK, sampled so that paths with large savings are well represented.
      </li>
      <li>
        <strong>The average line.</strong>{" "}Its 95% Monte Carlo uncertainty in {fyLabel(final)} is ±
        {formatBn(1.96 * ev.primary.gross[i].se, 1)}{" "}gross: how precisely the full runs pin down the average,
        not how much the saving could vary.
      </li>
      {ev.netExcludingLargest ? (
        <li>
          <strong>One survey record.</strong>{" "}Without the record that moves each path&apos;s net figure most, the
          expected net saving in {fyLabel(final)} would be {formatBn(ev.netExcludingLargest[i].mean, 1)}.
        </li>
      ) : null}
      {ev.gap ? (
        <li data-testid="uncertain-note">
          <strong>How far the pension falls.</strong>{" "}In {fyLabel(final)} the full new State Pension is £
          {ev.gap.mean_gap_gbp_week.toFixed(2)}{" "}a week lower under the plan on average; across the model&apos;s paths
          the gap runs from £{ev.gap.gap_gbp_week.p10.toFixed(2)} to £{ev.gap.gap_gbp_week.p90.toFixed(2)} a week
          (10th to 90th percentile: a spread of scenarios, not a forecast probability).
        </li>
      ) : null}
    </ul>
  );
}

export default function SummaryTab({ data }) {
  const ev = getExpectedValue(data);
  const dwp = getDwp(data);
  const final = getFinalYear(data);
  if (data?.uncertainty_ruling?.ruling === "a") return <MeanPathScenarios data={data} />;
  if (!ev || !final) return <Unavailable what="The expected saving" />;
  const premium = ev.gap?.mean_rate_minus_earnings_2034_2039;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="summary-tab">
      {ev.modelConditional ? <p>{ev.ruling === "b" ? "Model-conditional expected value. The original macro model fails its frozen adequacy backtest; Monte Carlo errors measure precision of this model path set." : "Model-conditional expected value. Monte Carlo errors measure precision of the recorded model path set."}</p> : null}
      {ev.ruling === "c" && Object.keys(data?.mean_path_scenarios?.scenarios ?? {}).length > 0 ? <MeanPathScenarios data={data} withExpectedValue /> : null}
      <Section
        id="choices"
        title="How the answer compares, and what it depends on"
        lead="Why it differs from DWP's costing, how it changes with our data and weighting, and other published costings."
        boxed={false}
      >
        <TopicPanel
          testId="choices-panel"
          topics={[
            {
              id: "dwp",
              testId: "dwp-box",
              title: dwp ? `Why it differs from DWP's £${dwp.nominal2039}bn` : "Why it differs from DWP's figure",
              summary: "One path, a dynamic population model, and Great Britain only.",
              content: (
                    <div className="text-sm leading-6 text-slate-700">
                          <ul className="list-disc space-y-1 pl-5" data-testid="dwp-differences">
                            <li>DWP runs one uprating path through its model and does not state it; ours averages over paths.</li>
                            <li>
                              DWP&apos;s Pensim3 is a dynamic model that projects the population and each person&apos;s pension. The
                              survey here is not aged: ages stay at their survey values, top-coded at 80, and each pensioner keeps the
                              State Pension type they had in the survey, so there are no new pensioners on the new State Pension, and
                              the number of pensioners changes only through the survey weights and the rise in State Pension age to 67.
                            </li>
                            <li>DWP&apos;s figure is direct spending only. Ours is gross State Pension spending too, with the net figure
                              beside it.</li>
                            <li>DWP covers Great Britain; the model covers the UK. Both figures here are in cash terms.</li>
                            {premium && isNum(premium.triple_lock) && isNum(premium.burnham_2030) ? (
                              <li data-testid="premium-note">
                                The OBR&apos;s long-term assumption is that the triple lock rises 0.6 points a year faster than
                                earnings. On our paths the triple lock rises {(premium.triple_lock * 100).toFixed(2)} points a year
                                faster than May–July earnings for the Aprils 2034 to 2039, on average, and the Burnham plan{" "}
                                {(premium.burnham_2030 * 100).toFixed(2)} points.
                              </li>
                            ) : null}
                          </ul>
                        </div>
              ),
            },
            {
              id: "dataset",
              testId: "dataset-box",
              title: "The survey data",
              summary: "The same paths on a second dataset, Microcosm, beside the Enhanced FRS.",
              content: (
                <>
                    <p className="mb-3 text-sm leading-6 text-slate-600">
                          The same {formatCount(ev.nSensitivity)}{" "}paths (a subsample of those above) run on both datasets, so the
                          difference is paired. With so few runs in some groups the ± figures here are approximate. The Enhanced FRS is PolicyEngine&apos;s certified dataset; Microcosm is not yet
                          certified. The Methodology tab sets both against DWP&apos;s spending and caseloads.
                        </p>
                        <DatasetTable ev={ev} />
                </>
              ),
            },
            {
              id: "weighting",
              testId: "calibration-box",
              title: "How the paths are weighted",
              summary: "The expected saving if paths are weighted to match past volatility instead.",
              content: (
                <>
                    <p className="mb-3 text-sm leading-6 text-slate-600">
                          Every row reuses the same full runs, reweighted; with fewer effective runs a row&apos;s ± figure is
                          approximate and too narrow. The dynamics rows also match the past variance of the gap
                          between May–July earnings and September CPI and how often the lead passed between them; in our backtest
                          (Methodology tab) that made the expected gap more biased, so they are shown as sensitivities.
                        </p>
                        <CalibrationTable ev={ev} />
                </>
              ),
            },
            {
              id: "benchmarks",
              testId: "benchmarks-box",
              title: "Other published costings",
              summary: "OBR, Resolution Foundation and DWP figures beside our closest equivalent.",
              content: (
                    <BenchmarksTable data={data} />
              ),
            },
          ]}
        />
      </Section>
    </div>
  );
}
