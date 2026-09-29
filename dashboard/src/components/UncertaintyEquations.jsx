"use client";

import { fyLabel, getBacktest, getErrorSource, getFinalYear, getFirstYearInputs } from "../lib/dataHelpers";
import { formatPct } from "../lib/formatters";
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

/** Leave-one-out backtest on past OBR forecasts. */
export function Backtest({ data }) {
  const b = getBacktest(data);
  if (!b) return <Unavailable what="The backtest" />;
  return (
    <div className="space-y-3 text-sm leading-6 text-slate-600" data-testid="backtest">
      <p>
        For each past forecast, the other forecasts&apos; errors and gaps are added to it, and the
        realised September CPI and May–July earnings are placed among those paths. The measure is
        how far the triple lock ran ahead of each alternative over four upratings, as % of the
        triple lock. A method with calibrated ranges would put the realised value inside its 10th
        to 90th percentile about 8 times in 10.
      </p>
      <ul className="list-disc pl-5">
        {BACKTEST_ALTS.map(([id, label]) => (
          <li key={id}>
            {label}: inside the range for {formatPct(100 * b.share_within_p10_p90[id], 0)} of past
            forecasts.
          </li>
        ))}
      </ul>
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
            {b.vintages.map((v) => (
              <tr key={v.vintage}>
                <td>{v.vintage}</td>
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
