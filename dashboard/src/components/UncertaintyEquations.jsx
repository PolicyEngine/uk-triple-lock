"use client";

import { fyLabel, getBacktest, getErrorSource, getFinalYear, getFirstYearInputs } from "../lib/dataHelpers";
import TeX from "./TeX";
import { Expandable, Unavailable } from "./ui";
import { Citations } from "./UncertaintyTab";

/** The uncertainty method written as equations. */
export function MethodEquations({ data }) {
  const source = getErrorSource(data);
  const first = getFirstYearInputs(data);
  const finalYear = getFinalYear(data);
  if (!source || !first || !finalYear) return <Unavailable what="The uncertainty method" />;
  const pct = (v) => `${(v * 100).toFixed(1)}\\%`;
  return (
    <ul className="list-disc space-y-3 pl-5 text-sm leading-6 text-slate-600" data-testid="method-equations">
      <li>
        Each rule sets the April uprating in year <TeX tex="t" /> from growth in year{" "}
        <TeX tex="t-1" />, where <TeX tex="\pi" /> is September CPI and <TeX tex="w" /> is May–July
        average weekly earnings (total pay). No rule cuts the cash pension:
        <div className="my-2 overflow-x-auto">
          <TeX
            display
            tex={String.raw`\begin{aligned}
r^{\text{TL}}_t &= \max(\pi_{t-1},\ w_{t-1},\ 2.5\%) & r^{\text{DL}}_t &= \max(\pi_{t-1},\ w_{t-1},\ 0)\\
r^{\text{E}}_t &= \max(w_{t-1},\ 0) & r^{\text{CPI}}_t &= \max(\pi_{t-1},\ 0)
\end{aligned}`}
          />
        </div>
      </li>
      <li>
        Each draw <TeX tex="d" /> adds past OBR forecast errors to the OBR&apos;s central forecast{" "}
        <TeX tex="\hat{x}" />, for <TeX tex="x \in \{\pi, w\}" /> and horizon{" "}
        <TeX tex="h = g - 2026" />:
        <div className="my-2 overflow-x-auto">
          <TeX
            display
            tex={String.raw`x^{(d)}_g = \hat{x}_g + \big(e_{v,h} - \bar{e}_h\big) + \big(s_{v+h} - \bar{s}_h\big)`}
          />
        </div>
        <TeX tex="v" /> is a past OBR forecast drawn at random (forecasts made in {source.years}),{" "}
        <TeX tex="e_{v,h}" /> is its error <TeX tex="h" /> years ahead, and <TeX tex="s_{v+h}" /> is
        the gap in that year between the measure the law uses and the measure the OBR forecasts
        (calendar-year CPI; national-accounts earnings). The bars are averages across forecasts at
        each horizon, so the average path is the OBR forecast. Horizons 1–4 come from one forecast
        and later horizons from a second, following the block bootstrap.
      </li>
      <li>
        The first uprating (April 2027) uses published earnings,{" "}
        <TeX tex={`w_{2026} = ${pct(first.earnings)}`} />, and draws September CPI around the
        published August figure: <TeX tex={`\\pi^{(d)}_{2026} = ${pct(first.cpi)} + \\delta^{(d)}`} />,
        where <TeX tex="\delta" /> is an August-to-September change in CPI from {first.years[0]}–
        {first.years[1]}.
      </li>
      <li>
        Each rule compounds into an index, and the extra cost of the triple lock in{" "}
        {fyLabel(finalYear)} scales PolicyEngine&apos;s State Pension spending <TeX tex="S" /> on
        the central path:
        <div className="my-2 overflow-x-auto">
          <TeX
            display
            tex={String.raw`I^{p,(d)}_T = \prod_{t} \big(1 + r^{p,(d)}_t\big), \qquad C^{(d)}_{p} = S \times \frac{I^{\text{TL},(d)}_T - I^{p,(d)}_T}{\hat{I}^{\text{TL}}_T}`}
          />
        </div>
        Full PolicyEngine runs on three of the draws give the same result.
      </li>
      <li>
        Sources for the method: <Citations />.
      </li>
    </ul>
  );
}

const BACKTEST_ALTS = [
  ["earnings_link", "Earnings link"],
  ["cpi_link", "CPI link"],
];

function BacktestTable({ part }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <caption className="sr-only">Backtest of the uncertainty method</caption>
        <thead>
          <tr>
            <th>Forecast</th>
            {BACKTEST_ALTS.map(([id, label]) => (
              <th key={id}>{label}: realised (10th–90th percentile)</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {part.vintages.map((v) => (
            <tr key={v.vintage}>
              <td>
                {v.vintage}
                {Number.isInteger(v.n_training) ? ` (${v.n_training} earlier)` : ""}
              </td>
              {BACKTEST_ALTS.map(([id]) => {
                const x = v.by_alternative[id];
                return (
                  <td key={id} className="tabular-nums">
                    {x.realised_pct.toFixed(1)}% ({x.draws_p10_pct.toFixed(1)}% to {x.draws_p90_pct.toFixed(1)}%)
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Retrospective and real-time backtests on past OBR forecasts. */
export function Backtest({ data }) {
  const b = getBacktest(data);
  if (!b) return <Unavailable what="The backtest" />;
  const coverage = (part) =>
    BACKTEST_ALTS.map(([id, label]) => `${label} ${part.n_within_p10_p90[id]} of ${part.n_tested}`).join("; ");
  return (
    <div className="space-y-3 text-sm leading-6 text-slate-600" data-testid="backtest">
      <p>
        Each check places the realised September CPI and May–July earnings of a past forecast&apos;s
        target years among simulated paths, and measures how far the triple lock ran ahead of each
        alternative over four upratings, as % of the triple lock. A calibrated 10th–90th percentile
        range would contain the realised value about 8 times in 10. The realised inputs are the
        latest ONS revisions, and the 2022 rise applies the formula although the earnings leg was
        suspended that year.
      </p>
      <ul className="list-disc pl-5">
        <li>
          <strong>Retrospective</strong> (each forecast against all the others, including later
          ones whose outcomes overlap): inside the range for {coverage(b.retrospective)}.
        </li>
        <li>
          <strong>Real time</strong> (each forecast against only the forecasts fully published when
          it was made): inside the range for {coverage(b.rolling_origin)}.
        </li>
      </ul>
      <p>
        Both checks rest on 12 forecasts or fewer, so neither pins down how often the ranges
        will hold. They do show the ranges are too narrow to read as probabilities.
      </p>
      <Expandable title="Real-time check by forecast" testId="backtest-rolling">
        <BacktestTable part={b.rolling_origin} />
      </Expandable>
      <Expandable title="Retrospective check by forecast" testId="backtest-retro">
        <BacktestTable part={b.retrospective} />
      </Expandable>
    </div>
  );
}

export function UncertaintyDetail({ data }) {
  return (
    <div className="mt-5 space-y-3">
      <Expandable title="The method in equations" testId="method-equations-box">
        <MethodEquations data={data} />
      </Expandable>
      <Expandable title="Backtest on past forecasts" testId="backtest-box">
        <Backtest data={data} />
      </Expandable>
    </div>
  );
}
