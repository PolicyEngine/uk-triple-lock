"use client";

import { fyLabel, getCoverage, getEvBacktest, getExpectedValue, getLimitations, getProvenance, isNum } from "../lib/dataHelpers";
import { formatBn, formatCount, formatRate } from "../lib/formatters";
import { getHistory } from "../lib/trajectoryHelpers";
import { ReplicationLine } from "./Benchmarks";
import SectionHeading from "./SectionHeading";
import { BacktestNote } from "./PathCharts";
import { Expandable, Explainer, Unavailable } from "./ui";

const CALENDAR_SOURCE = {
  efo_calendar: "OBR March 2026 forecast",
  lted_converted: "OBR long-term determinants (converted to calendar years)",
};
const STATUTORY_SOURCE = {
  published: "Published (May–July 2026 earnings; August 2026 CPI)",
  efo_quarterly: "OBR forecast: September-quarter CPI, April–June earnings",
  calendar: "The calendar-year path",
};

function CentralPathTable({ data }) {
  const path = data?.central?.path;
  const years = data?.horizon;
  if (!path || !Array.isArray(years)) return <Unavailable what="The central path" />;
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="central-path-table">
        <thead>
          <tr>
            <th>April rise</th>
            <th>Set by: CPI</th>
            <th>Earnings</th>
            <th>Source</th>
            <th>Calendar year for the rest of the model: CPI</th>
            <th>Earnings</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const s = String(y - 1);
            const c = String(y);
            return (
              <tr key={y}>
                <td>{y}</td>
                <td className="tabular-nums">{formatRate(path.statutory?.cpi?.[s], 2)}</td>
                <td className="tabular-nums">{formatRate(path.statutory?.earnings?.[s], 2)}</td>
                <td>{STATUTORY_SOURCE[path.statutory_source?.[s]] ?? "unavailable"}</td>
                <td className="tabular-nums">{formatRate(path.calendar?.cpi?.[c], 2)}</td>
                <td className="tabular-nums">{formatRate(path.calendar?.earnings?.[c], 2)}</td>
                <td>{CALENDAR_SOURCE[path.calendar_source?.[c]] ?? "unavailable"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StrataTable({ ev }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="strata-table">
        <thead>
          <tr>
            <th>Stratum</th>
            <th>Share of paths</th>
            <th>Gap in {fyLabel(ev.years.at(-1))}, £ a week</th>
            <th>Full runs</th>
            <th>Of which also on Microcosm</th>
          </tr>
        </thead>
        <tbody>
          {ev.strata.map((s) => (
            <tr key={s.stratum}>
              <td>{s.stratum}</td>
              <td className="tabular-nums">{(100 * s.probability).toFixed(1)}%</td>
              <td className="tabular-nums">
                £{s.gap_range_gbp_week[0].toFixed(2)} to £{s.gap_range_gbp_week[1].toFixed(2)}
              </td>
              <td className="tabular-nums">{s.paths}</td>
              <td className="tabular-nums">{s.sensitivity_paths}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvBacktestTable({ bt }) {
  const law = Object.fromEntries(bt.suspended.map((r) => [r.id, r]));
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="ev-backtest-table">
        <thead>
          <tr>
            <th>Method</th>
            <th>Expected gap, % of the pension</th>
            <th>Bias, as in law (± SE)</th>
            <th>Bias, April 2022 as published (± SE)</th>
            <th>Switches in four years, predicted minus actual (as in law)</th>
          </tr>
        </thead>
        <tbody>
          {bt.published.map((r) => {
            const l = law[r.id];
            return (
              <tr key={r.id}>
                <td>{r.label}</td>
                <td className="tabular-nums">{r.mean_predicted_gap_pct.toFixed(2)}</td>
                <td className="tabular-nums">{l ? `${l.bias_pct_points.toFixed(2)} ± ${l.bias_se_independent.toFixed(2)}` : "n/a"}</td>
                <td className="tabular-nums">{`${r.bias_pct_points.toFixed(2)} ± ${r.bias_se_independent.toFixed(2)}`}</td>
                <td className="tabular-nums">{l && isNum(l.switch_bias) ? l.switch_bias.toFixed(2) : "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        Realised gap, averaged over the {bt.origins.length} forecasts: {bt.suspended[0].mean_realised_gap_pct.toFixed(2)}% as
        in law, {bt.published[0].mean_realised_gap_pct.toFixed(2)}% with April 2022 as published.
      </p>
    </div>
  );
}

function CoverageTable({ cov }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="coverage-table">
        <thead>
          <tr>
            <th>{fyLabel(cov.year)}</th>
            <th>DWP forecast</th>
            <th>Enhanced FRS</th>
            <th>Microcosm</th>
          </tr>
        </thead>
        <tbody>
          {cov.rows.map((r) => {
            const fmt = r.key.endsWith("_m") ? (v) => `${v.toFixed(2)}m` : (v) => formatBn(v, 1);
            return (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td className="tabular-nums">{fmt(r.dwp)}</td>
                <td className="tabular-nums">{fmt(r.primary)}</td>
                <td className="tabular-nums">{fmt(r.sensitivity)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        DWP: <a href={cov.dwp.source} target="_blank" rel="noreferrer">benefit expenditure and caseload tables</a>,
        Spring Forecast 2026, {cov.dwp.geography}. {cov.model_note}
      </p>
    </div>
  );
}

export default function MethodTab({ data }) {
  const ev = getExpectedValue(data);
  const bt = getEvBacktest(data);
  const cov = getCoverage(data);
  const limitations = getLimitations(data);
  const provenance = getProvenance(data);
  const history = getHistory(data);
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="method-tab">
      <section className="mb-12">
        <SectionHeading title="Every figure is a full model run" />
        <Explainer>
          <p>
            Each fiscal and household figure on this page comes from PolicyEngine UK run on the whole survey, once
            under each rule, for every path; none is scaled from another run. A path&apos;s CPI and earnings growth
            replace the model&apos;s economic assumptions before the data load, so benefit rates, tax thresholds,
            earnings and the model&apos;s own triple lock all follow it, and every run checks, year by year, that they
            did. The State Pension flat rates are then set from each rule applied to the path&apos;s September CPI and
            May–July earnings, rounded to 0.1 point as the model does. The additional State Pension is held at the
            unreformed run&apos;s amounts, so only the basic and new State Pension differ between the two runs.
          </p>
        </Explainer>
        <Expandable title="The central path, year by year" testId="central-path-box">
          <CentralPathTable data={data} />
        </Expandable>
      </section>

      <section className="mb-12">
        <SectionHeading title="How the expected saving is estimated" />
        {ev ? (
          <Explainer>
            <p data-testid="ev-method">
              A monthly model of the CPI index and average weekly earnings, fitted to 2000–2026 (leaving out the
              furlough months), simulates {formatCount(ev.nDraws)} paths from August 2026 to December{" "}
              {ev.years.at(-1)}. Both the statutory inputs and the calendar-year figures come from the same simulated
              months. Each path is then shifted by the same smooth monthly drift, so that the average across paths equals
              the OBR&apos;s calendar-year CPI and earnings forecast in every year while each path&apos;s ups and downs
              stay the model&apos;s own.
            </p>
            <p>
              Paths on which the two rules pay the same every year save exactly nothing (
              {isNum(ev.identical) ? `${(100 * ev.identical).toFixed(2)}% of them` : "a small share"}; one was run to
              confirm it). The rest are split into ten equally likely groups by how far the plan&apos;s full new State
              Pension falls behind the triple lock&apos;s by {fyLabel(ev.years.at(-1))}. {formatCount(ev.nRuns)} paths are
              drawn across the groups, more where the gap varies most, and each is a full run. The expected saving is
              the probability-weighted average of the groups&apos; mean savings, and its standard error comes from the
              spread within each group.
            </p>
          </Explainer>
        ) : (
          <Unavailable what="The expected saving" />
        )}
        {ev ? (
          <Expandable title="The groups of paths" testId="strata-box">
            <StrataTable ev={ev} />
          </Expandable>
        ) : null}
      </section>

      <section className="mb-12">
        <SectionHeading title="Testing the expected value on past forecasts" />
        {bt ? (
          <>
            <Explainer>
              <p>
                For each of {bt.origins.length} past OBR forecasts we fitted the monthly model only on data dated before
                it, simulated the September CPI and May–July earnings that set the next {bt.horizon} April rises, and
                compared the expected gap between the triple lock and the Burnham plan (the plan starting at the first of
                those rises) with what happened. The OBR forecast used as a single path predicts almost no gap and
                misses it by the most. The model shifted to the OBR&apos;s means, the method used here, has a bias within
                its standard error. Tilting the paths towards the past variance of the earnings–CPI gap and the past
                rate of lead changes made the bias larger.
              </p>
              {bt.note ? <p className="text-xs text-slate-500">{bt.note}</p> : null}
            </Explainer>
            <EvBacktestTable bt={bt} />
          </>
        ) : (
          <Unavailable what="The expected-value backtest" />
        )}
        <div className="mt-6">
          <BacktestNote tdata={data} history={history} />
        </div>
      </section>

      <section className="mb-12">
        <SectionHeading title="The survey data against DWP" />
        <Explainer>
          <p>
            The gross saving scales with State Pension spending; the net saving also runs through Pension Credit,
            Housing Benefit and income tax. Each dataset is set against DWP&apos;s forecast for the same year.
          </p>
        </Explainer>
        {cov ? <CoverageTable cov={cov} /> : <Unavailable what="The dataset comparison" />}
      </section>

      <section className="mb-12">
        <SectionHeading title="Limitations" />
        {limitations ? (
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700" data-testid="limitations">
            {limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        ) : (
          <Unavailable what="The list of limitations" />
        )}
      </section>

      <section className="mb-4 text-sm text-slate-600">
        {provenance ? <ReplicationLine data={data} /> : <Unavailable what="The provenance" />}
      </section>
    </div>
  );
}
