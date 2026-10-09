"use client";

import { fyLabel, getC2Screen, getCoverage, getEvBacktest, getExpectedValue, getLimitations, isNum } from "../lib/dataHelpers";
import { formatBn, formatCount, formatRate } from "../lib/formatters";
import { getHistory } from "../lib/trajectoryHelpers";
import { BacktestNote } from "./PathCharts";
import { Section, Unavailable } from "./ui";

const CALENDAR_SOURCE = {
  efo_calendar: "OBR calendar-year forecast",
  lted_converted: "OBR long-term determinants (converted to calendar years)",
};
const STATUTORY_SOURCE = {
  published: "Published statutory CPI and earnings",
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
  const showGap = ev.strata.every((s) => Array.isArray(s.gap_range_gbp_week) && s.gap_range_gbp_week.length === 2 && s.gap_range_gbp_week.every(isNum));
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="strata-table">
        <thead>
          <tr>
            <th>Stratum</th>
            <th>Share of paths</th>
            {showGap ? <th>Gap in {fyLabel(ev.years.at(-1))}, £ a week</th> : null}
            <th>Full runs</th>
            <th>Of which also on Microcosm</th>
          </tr>
        </thead>
        <tbody>
          {ev.strata.map((s) => (
            <tr key={s.stratum}>
              <td>{s.stratum}</td>
              <td className="tabular-nums">{(100 * s.probability).toFixed(1)}%</td>
              {showGap ? <td className="tabular-nums">
                £{s.gap_range_gbp_week[0].toFixed(2)} to £{s.gap_range_gbp_week[1].toFixed(2)}
              </td> : null}
              <td className="tabular-nums">{s.paths}</td>
              <td className="tabular-nums">{s.sensitivity_paths}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function C2ScreenTable({ screen }) {
  return <div className="space-y-3" data-testid="c2-screen">
    <p>The C2 statutory screen scores April 2022 with the earnings leg suspended and excludes cells fixed by law. Published earnings are a sensitivity only. The original monthly VAR(1) bootstrap {screen.primaryPasses ? "passes; its expected value remains model-conditional" : "fails; the build automatically takes (a), scenarios only"}. Alternatives are reported separately.</p>
    <p>All five forms failed C1 on test A with published earnings (1/6 terminal coverage, following the 2021 furlough base effect). The rule changed after those scores were seen because Parliament suspended the earnings leg for April 2022. The C1 record is retained.</p>
    <p>Pre-registration: <code>{screen.rule_sha}</code>. {screen.run_kind === "binding" ? "Binding post-Budget score." : "Dry run; no expected value authorized."}</p>
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="c2-screen-table">
        <thead><tr><th>Test</th><th>Form</th><th>Treatment</th><th>C2 verdict</th><th>Annual coverage</th><th>Scored / excluded cells</th><th>Terminal coverage</th><th>Gap bias, pp</th><th>Switch bias</th><th>Floor bias</th></tr></thead>
        <tbody>{screen.rows.map((r) => <tr key={`${r.test}.${r.form}.${r.treatment}`}>
          <td>{r.test}</td><td>{r.form}</td><td>{r.treatment === "suspended" ? "As in law" : "Published sensitivity"}</td>
          <td>{r.treatment === "suspended" ? (r.passes ? "Pass" : "Fail") : "Sensitivity only"}</td>
          <td>{(100 * r.annual_gap_coverage.mean).toFixed(1)}%</td><td>{r.annual_gap_cells} / {r.annual_gap_excluded_cells}</td>
          <td>{r.terminal_coverage.hits}/{r.terminal_scored_origins}</td><td>{r.gap_bias_pp.mean.toFixed(2)}</td><td>{r.switch_bias.mean.toFixed(2)}</td><td>{r.floor_bias.mean.toFixed(2)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
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
            <th>Mean absolute error, as in law</th>
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
                <td className="tabular-nums">{l && isNum(l.mean_abs_error) ? l.mean_abs_error.toFixed(2) : "n/a"}</td>
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

/** The backtest findings, read from the file so the text cannot contradict the table. */
export function backtestProse(bt) {
  const law = Object.fromEntries(bt.suspended.map((r) => [r.id, r]));
  const pub = Object.fromEntries(bt.published.map((r) => [r.id, r]));
  const f = (r) => `${r.bias_pct_points >= 0 ? "+" : ""}${r.bias_pct_points.toFixed(2)} ± ${r.bias_se_independent.toFixed(2)}`;
  const parts = [];
  const worst = (rows) => rows.reduce((a, b) => (Math.abs(b.bias_pct_points) > Math.abs(a.bias_pct_points) ? b : a));
  if (law.obr_point && worst(bt.suspended).id === "obr_point" && worst(bt.published).id === "obr_point") {
    parts.push(`The OBR forecast used as a single path has the largest bias under both treatments of April 2022 (${f(law.obr_point)} points as in law, ${f(pub.obr_point)} as published).`);
  }
  if (law.means_shift && pub.means_shift) {
    const within = (r) => Math.abs(r.bias_pct_points) <= r.bias_se_independent;
    parts.push(`The model shifted to the OBR's means, the method used here, has a bias of ${f(law.means_shift)} points as in law${within(law.means_shift) ? ", within its standard error" : ""}, and ${f(pub.means_shift)} as published${within(pub.means_shift) ? ", also within it" : ""}.`);
  }
  if (law.shift_dynamics && law.means_shift) {
    const larger = Math.abs(law.shift_dynamics.bias_pct_points) > Math.abs(law.means_shift.bias_pct_points)
      && Math.abs(pub.shift_dynamics.bias_pct_points) > Math.abs(pub.means_shift.bias_pct_points);
    const lowerMae = law.shift_dynamics.mean_abs_error < law.means_shift.mean_abs_error;
    parts.push(`Tilting the paths towards the past variance of the earnings–CPI gap and the past rate of lead changes gives a bias of ${f(law.shift_dynamics)} as in law${larger ? ", larger under both treatments" : ""}${lowerMae ? ", though a lower mean absolute error" : ""}; we chose on bias because the expected value is a mean.`);
  }
  return parts.join(" ");
}

function CoverageTable({ cov }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="coverage-table">
        <thead>
          <tr>
            <th>{fyLabel(cov.year)}</th>
            <th>DWP forecast</th>
            <th>{cov.gb ? "Enhanced FRS, GB" : "Enhanced FRS"}</th>
            <th>{cov.gb ? "Microcosm, GB" : "Microcosm"}</th>
          </tr>
        </thead>
        <tbody>
          {cov.rows.map((r) => {
            const fmt = r.key.endsWith("_m") ? (v) => `${v.toFixed(2)}m` : (v) => formatBn(v, 1);
            // Great Britain against DWP's Great Britain where the file gives it (from model-v2); the UK before.
            return (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td className="tabular-nums">{fmt(r.dwp)}</td>
                <td className="tabular-nums">{fmt(cov.gb ? r.primary_gb : r.primary)}</td>
                <td className="tabular-nums">{fmt(cov.gb ? r.sensitivity_gb : r.sensitivity)}</td>
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

const RUN_STEPS = [
  {
    title: "The path replaces the model's economy",
    text: "A path's CPI and earnings growth replace PolicyEngine UK's economic assumptions before the data load, so benefit rates, tax thresholds, earnings and the model's own triple lock all follow it. Every run checks, year by year, that they did.",
  },
  {
    title: "Each rule sets the State Pension",
    text: "The basic and new State Pension flat rates come from each rule applied to the path's September CPI and May–July earnings, taken to 0.1 point as ONS publishes them.",
  },
  {
    title: "Everything else is held the same",
    text: "Under both rules the additional State Pension grows by September CPI, the Pension Credit guarantee rises with May–July earnings, each person keeps their survey-year State Pension type, and the State Pension age follows the law's timetable by date of birth, so from 2028-29 everyone aged 67 or over is above it and nobody younger.",
  },
  {
    title: "The difference is the plan's effect",
    text: "Only the basic and new State Pension differ between the two runs, so every change in tax, benefits and household income follows from the plan.",
  },
];

export default function MethodTab({ data }) {
  const ev = getExpectedValue(data);
  const bt = getEvBacktest(data);
  const c2 = getC2Screen(data);
  const cov = getCoverage(data);
  const limitations = getLimitations(data);
  const history = getHistory(data);
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="method-tab">
      <Section
        id="full-runs"
        title="Every figure is a full model run"
        lead="How the figures are made, tested and limited. Each fiscal and household figure comes from PolicyEngine UK run on the whole survey, once under each rule, for every path; none is scaled from another run."
        detailsTitle="The central path, year by year"
        details={<CentralPathTable data={data} />}
      >
        <ol className="space-y-3 text-sm leading-6 text-slate-700" data-testid="run-steps">
          {RUN_STEPS.map((step, k) => (
            <li key={step.title} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">{k + 1}</span>
              <span>
                <strong className="text-slate-900">{step.title}.</strong>{" "}{step.text}
              </span>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="estimate"
        title="How the expected saving is estimated"
        lead={ev ? `${formatCount(ev.nDraws)} simulated paths of prices and earnings, grouped by the gap they open, with ${formatCount(ev.nRuns)} run in full.` : null}
        detailsTitle="The groups of paths"
        details={ev ? <StrataTable ev={ev} /> : null}
      >
        {ev ? (
          <div className="space-y-3 text-sm leading-6 text-slate-700">
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
              Pension falls behind the triple lock&apos;s by {fyLabel(ev.years.at(-1))}. {formatCount(ev.nRuns)}{" "}paths are
              drawn across the groups, more where the gap varies most, and each is a full run. The expected saving is
              the probability-weighted average of the groups&apos; mean savings, and its standard error comes from the
              spread within each group.
            </p>
          </div>
        ) : (
          c2 && !c2.primaryPasses ? <p data-testid="expected-value-omission">The original primary failed C2, so the build automatically takes (a): scenarios only. {data?.expected_value_omission?.reason}</p> : <Unavailable what="The expected saving" />
        )}
      </Section>

      <Section
        id="backtest"
        title="Testing on past forecasts"
        lead="The model fitted only on data before each past OBR forecast, compared with what then happened."
        detailsTitle="How the test works"
        details={bt ? <>
          <p>
            For each of {bt.origins.length} past OBR forecasts we fitted the monthly model only on data dated before
            it, simulated the September CPI and May–July earnings for the four years after the forecast year (which
            set the April rises two to five years after the forecast), and compared the expected gap between the
            triple lock and the Burnham plan (the plan starting at the first of those rises) with what happened.
          </p>
          <p data-testid="ev-backtest-prose">{backtestProse(bt)}
          </p>
          {bt.note ? <p className="text-xs text-slate-500">{bt.note}</p> : null}
        </> : null}
      >
        {c2 ? <C2ScreenTable screen={c2} /> : bt ? <EvBacktestTable bt={bt} /> : <Unavailable what="The expected-value backtest" />}
        <div className="mt-6">
          <BacktestNote tdata={data} history={history} />
        </div>
      </Section>

      <Section
        id="survey"
        title="The survey data against DWP"
        lead="The gross saving scales with State Pension spending; the net saving also runs through Pension Credit, Housing Benefit and income tax."
      >
        {cov ? <CoverageTable cov={cov} /> : <Unavailable what="The dataset comparison" />}
      </Section>

      <Section id="limitations" title="Limitations" lead="What the model leaves out, and which way that may push the results.">
        {limitations ? (
          <ol className="divide-y divide-slate-100 text-sm leading-6 text-slate-700" data-testid="limitations">
            {limitations.map((l, k) => (
              <li key={l} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                <span className="w-5 shrink-0 text-right font-semibold tabular-nums text-slate-400">{k + 1}</span>
                <span>{l}</span>
              </li>
            ))}
          </ol>
        ) : (
          <Unavailable what="The list of limitations" />
        )}
      </Section>
    </div>
  );
}
