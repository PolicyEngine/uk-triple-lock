"use client";

import { fyLabel, getC2Screen, getCoverage, getEvBacktest, getExpectedValue, getLimitations, getProvisional, isNum, isPreBudget, isText, withoutCrossCheck } from "../lib/dataHelpers";
import { formatBn, formatCount, formatRate } from "../lib/formatters";
import { getHistory } from "../lib/trajectoryHelpers";
import { BacktestNote } from "./PathCharts";
import { Expandable, Section, Unavailable } from "./ui";

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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The test's headline for the form used (test A, April 2022 as in law), then every score one click away. */
function C2ScreenTable({ screen, provisional }) {
  const used = screen.rows.find((r) => r.test === "A" && r.form === "monthly_var1_boot" && r.treatment === "suspended");
  return <div className="space-y-3" data-testid="c2-screen">
    <p className="text-sm leading-6 text-slate-700" data-testid="c2-headline">
      {screen.primaryPasses
        ? <>The forecast model used <strong>passes</strong>{used ? `: the outcome fell inside its range in ${used.terminal_coverage.hits} of ${used.terminal_scored_origins} final years and ${(100 * used.annual_gap_coverage.mean).toFixed(0)}% of annual checks` : ""}.</>
        : <>The forecast model used <strong>fails</strong>, so only scenarios are shown.</>}
    </p>
    <Expandable title="All test results" testId="c2-details">
      <div className="space-y-2 text-sm leading-6 text-slate-600">
        <p>April 2022 is scored as in law, with the earnings leg suspended, and cells fixed by law are skipped; published earnings are a sensitivity only.</p>
        <p>With published earnings, every model form failed an earlier version of the test (1/6 final years, after the 2021 furlough effect); that record is kept.</p>
        <p>{screen.run_kind === "binding" ? "Binding post-Budget score." : provisional ? "Dry run on today's inputs: the expected saving on this page is provisional; the binding score uses the Budget inputs." : "Dry run; no expected value authorized."}</p>
        <p className="text-xs text-slate-500">Rule fingerprint: <code>{screen.rule_sha}</code></p>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="data-table" data-testid="c2-screen-table">
          <thead><tr><th>Test</th><th>Form</th><th>April 2022</th><th>Verdict</th><th>Annual coverage</th><th>Scored / excluded cells</th><th>Final-year coverage</th><th>Gap bias, pp</th><th>Switch bias</th><th>Floor bias</th></tr></thead>
          <tbody>{screen.rows.map((r) => <tr key={`${r.test}.${r.form}.${r.treatment}`}>
            <td>{r.test}</td><td>{r.form}</td><td>{r.treatment === "suspended" ? "As in law" : "Published sensitivity"}</td>
            <td>{r.treatment === "suspended" ? (r.passes ? "Pass" : "Fail") : "Sensitivity only"}</td>
            <td>{(100 * r.annual_gap_coverage.mean).toFixed(1)}%</td><td>{r.annual_gap_cells} / {r.annual_gap_excluded_cells}</td>
            <td>{r.terminal_coverage.hits}/{r.terminal_scored_origins}</td><td>{r.gap_bias_pp.mean.toFixed(2)}</td><td>{r.switch_bias.mean.toFixed(2)}</td><td>{r.floor_bias.mean.toFixed(2)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </Expandable>
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
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">
        DWP: <a href={cov.dwp.source} target="_blank" rel="noreferrer">benefit expenditure and caseload tables</a>,
        Spring Forecast 2026, {cov.dwp.geography}. {withoutCrossCheck(cov.model_note?.replace(/``([^`]+)``/g, "$1"))}
      </p>
    </div>
  );
}

/** One sentence on the survey against DWP: State Pension spending, recipients and Pension Credit claims. */
function coverageHeadline(cov) {
  const row = Object.fromEntries(cov.rows.map((r) => [r.key, { dwp: r.dwp, ours: cov.gb ? r.primary_gb : r.primary }]));
  const parts = [
    row.state_pension_bn && `${formatBn(row.state_pension_bn.ours, 1)} of State Pension spending against DWP's ${formatBn(row.state_pension_bn.dwp, 1)}`,
    row.state_pension_recipients_m && `${row.state_pension_recipients_m.ours.toFixed(2)}m recipients against ${row.state_pension_recipients_m.dwp.toFixed(2)}m`,
    row.pension_credit_claims_m && `${row.pension_credit_claims_m.ours.toFixed(2)}m Pension Credit claims against ${row.pension_credit_claims_m.dwp.toFixed(2)}m`,
  ].filter(Boolean);
  if (!parts.length) return null;
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0];
  return `In ${fyLabel(cov.year)} the survey has ${list}${cov.gb ? ", for Great Britain" : ""}.`;
}

const RUN_STEPS = [
  {
    title: "The path replaces the model's economy",
    text: "A path's CPI and earnings replace PolicyEngine UK's economic assumptions, so benefit rates, tax thresholds and earnings follow it; each run checks this.",
  },
  {
    title: "Each rule sets the State Pension",
    text: "Basic and new State Pension rates follow each rule on the path's September CPI and May–July earnings, to 0.1 point.",
  },
  {
    title: "Everything else is held the same",
    text: "Additional State Pension grows with CPI and the Pension Credit guarantee with earnings; each person keeps their survey-year State Pension type; State Pension age is 67 from 2028-29.",
  },
  {
    title: "The difference is the plan's effect",
    text: "Only the basic and new State Pension differ, so every other change follows from the plan.",
  },
];

/** "28 October" from the release's ISO Budget date, or null. */
function budgetDay(release) {
  const m = isText(release?.budget_date) ? /^\d{4}-(\d{2})-(\d{2})$/.exec(release.budget_date) : null;
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return m && months[Number(m[1]) - 1] ? `${Number(m[2])} ${months[Number(m[1]) - 1]}` : null;
}

/** Without an expected value, the method of one is future work: what happens at the Budget, from the release block. */
function PendingExpectedValue({ data }) {
  const day = budgetDay(data?.release);
  return (
    <p className="text-sm leading-6 text-slate-700" data-testid="expected-value-pending">
      The expected saving is scored on the {day ? `${day} ` : ""}Budget&apos;s inputs: if the forecast model passes
      its test on past forecasts, it is added, labelled model-conditional; if not, only the scenarios stay.
    </p>
  );
}

/**
 * The limitations come from the results file. Each is placed in a group and shortened by matching its text; a short
 * version is used only when the file's wording still contains every figure it quotes (`needs`), otherwise the file's
 * own text is shown, and anything unmatched goes under "Other", so nothing is dropped.
 */
const LIMIT_GROUPS = [
  { title: "Prices and earnings", items: [
    { match: /convention of September CPI/, needs: ["2028-2031"], short: "Rises use September CPI and May–July earnings; the central path uses the OBR's quarterly figures for April 2028–2031, then its calendar-year path." },
    { match: /long-term projection/, needs: ["2030"], short: "After 2030 the central path is the OBR's long-term projection, which the OBR says is not a forecast." },
    { match: /rests on one statistical model/, needs: ["2000-2026", "twelve"], short: "The expected saving rests on one model of CPI and earnings, fitted to 2000–2026 and backtested on twelve overlapping four-year windows." },
    { match: /April 2027's benefit uprating/, needs: ["(2.3%)", "21 October 2026"], short: "April 2027's benefit uprating uses the model's 2026 CPI forecast (2.3%), not September 2026 CPI (published 21 October 2026)." },
  ] },
  { title: "Population", items: [
    { match: /aged statically/, needs: ["80 to 105"], short: "The population is reweighted, not aged: weights follow the ONS projection by age and sex, ages above the top code of 80 are spread to 105 using ONS shares, and State Pension type follows birth cohort. Deaths, migration and pensioners abroad are not modelled." },
    { match: /policyengine-uk-data#538/, needs: ["0.44%"], short: "Household weights sit 0.44% below their calibrated levels in every year (policyengine-uk-data#538)." },
  ] },
  { title: "What the model leaves out", items: [
    { match: /Rents and council tax/, needs: ["2030"], short: "Rents and council tax stay at 2030 levels; dividend, property, savings and self-employment income do not follow the path." },
    { match: /respond only for households already receiving/, needs: [], short: "Housing Benefit and council tax reduction respond only for existing claimants, which overstates the net saving." },
    { match: /Only the basic and new State Pension change/, needs: ["no behavioural response"], short: "Only the basic and new State Pension differ between the rules, and there is no behavioural response." },
    { match: /Pension Age Winter Heating Payment/, needs: ["£100", "£203.40", "#2138", "#2139"], short: "policyengine-uk pays Scotland's Pension Age Winter Heating Payment at £100 a household where the regulations pay £203.40 a person living alone (policyengine-uk#2138), and has no 25p addition at 80 (policyengine-uk#2139)." },
  ] },
  { title: "Rules, data and software", items: [
    { match: /Every rule follows the triple lock to April 2029/, needs: ["April 2030", "2029-30"], short: "Both rules follow the triple lock to April 2029; from April 2030 the plan rises by at least the higher of CPI and 2.5%, topped up to hold its 2029-30 ratio to earnings, as DWP defines it." },
    { match: /below State Pension age is not counted/, needs: [], short: "State Pension reported below State Pension age is not counted." },
    { match: /certified UK bundle/, needs: ["6.2.6", "2.125.1", "1.58.0"], short: "Model and data: the certified policyengine 6.2.6 UK bundle (policyengine-uk 2.125.1, Enhanced FRS 1.58.0)." },
    { match: /cash terms/, needs: ["Great Britain"], short: "Costs are in cash terms for the UK; DWP's figures are for Great Britain." },
    { match: /Concentration diagnostics/, needs: ["ten"], short: "Concentration diagnostics stay private until each total rests on at least ten contributing records." },
  ] },
];

function groupLimitations(limitations) {
  const used = new Set();
  const groups = LIMIT_GROUPS.map((g) => ({
    title: g.title,
    items: g.items.flatMap((it) => {
      const text = limitations.find((l) => !used.has(l) && it.match.test(l));
      if (!text) return [];
      used.add(text);
      return [it.needs.every((n) => text.includes(n)) ? it.short : text];
    }),
  }));
  const other = limitations.filter((l) => !used.has(l));
  return [...groups, { title: "Other", items: other }].filter((g) => g.items.length);
}

/** The limitations, grouped, with those about an expected value (which this file does not have) set apart. */
function Limitations({ limitations, scenariosOnly, preBudget }) {
  const later = scenariosOnly ? limitations.filter((l) => /expected value/i.test(l)) : [];
  const now = limitations.filter((l) => !later.includes(l));
  return (
    <>
      <div data-testid="limitations">
        <div className="grid gap-4 md:grid-cols-2">
          {groupLimitations(now).map((g) => (
            <div key={g.title} className="rounded-xl border border-slate-200 bg-white px-5 py-4">
              <p className="text-sm font-semibold text-slate-900">{g.title}</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-6 text-slate-700">
                {g.items.map((l) => <li key={l}>{l}</li>)}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <Expandable title="Full wording" testId="limitations-full">
            <ol className="list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-600">
              {now.map((l) => <li key={l}>{l}</li>)}
            </ol>
          </Expandable>
        </div>
      </div>
      {later.length ? (
        <div className="mt-4">
          <Expandable title={preBudget ? "For the expected saving, after the Budget" : "For an expected saving, which this file omits"} testId="limitations-later">
            <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
              {later.map((l) => <li key={l}>{l}</li>)}
            </ul>
          </Expandable>
        </div>
      ) : null}
    </>
  );
}

/** The run steps, with step 3's population wording following the treatment the file's assumptions block records. */
function runSteps(data) {
  const facts = (Array.isArray(data?.assumptions) ? data.assumptions : []).find((it) => it?.key === "population")?.facts;
  if (facts?.pension_types !== "cohort") return RUN_STEPS;
  return RUN_STEPS.map((step, k) => (k === 2 ? {
    ...step,
    text: step.text.replace("each person keeps their survey-year State Pension type", "each person's State Pension type follows their cohort"),
  } : step));
}

export default function MethodTab({ data }) {
  const ev = getExpectedValue(data);
  const bt = getEvBacktest(data);
  const c2 = getC2Screen(data);
  const cov = getCoverage(data);
  const limitations = getLimitations(data);
  const history = getHistory(data);
  const preBudget = isPreBudget(data);
  const scenariosOnly = !ev && data?.uncertainty_ruling?.ruling === "a";
  const pending = scenariosOnly && preBudget && !c2;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="method-tab">
      <Section
        id="full-runs"
        title="Every figure is a full model run"
        lead="Each fiscal and household figure is a PolicyEngine UK run on the whole survey, once per rule and path; none is scaled from another."
        detailsTitle="The central path, year by year"
        details={<CentralPathTable data={data} />}
      >
        <ol className="space-y-3 text-sm leading-6 text-slate-700" data-testid="run-steps">
          {runSteps(data).map((step, k) => (
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
        title={pending ? "The expected saving, after the Budget" : "How the expected saving is estimated"}
        lead={ev ? `${formatCount(ev.nDraws)} simulated paths of prices and earnings, grouped by the gap they open, with ${formatCount(ev.nRuns)} run in full.` : null}
        detailsTitle="The groups of paths"
        details={ev ? <StrataTable ev={ev} /> : null}
      >
        {ev ? (
          <div className="space-y-3 text-sm leading-6 text-slate-700">
            <p data-testid="ev-method">
              A monthly model of CPI and earnings, fitted to 2000–2026 without the furlough months, simulates{" "}
              {formatCount(ev.nDraws)}{" "}paths from August 2026 to December {ev.years.at(-1)}. Each is shifted so the
              average matches the OBR&apos;s forecast every year, keeping its own ups and downs.
            </p>
            <p>
              Paths where the rules pay the same every year save nothing (
              {isNum(ev.identical) ? `${(100 * ev.identical).toFixed(2)}%` : "a small share"}). The rest form ten equally
              likely groups by the {fyLabel(ev.years.at(-1))}{" "}pension gap; {formatCount(ev.nRuns)}{" "}paths drawn
              across them, more where the gap varies most, run in full. The expected saving weights each group&apos;s
              mean; its standard error comes from the spread within groups.
            </p>
          </div>
        ) : (
          c2 && !c2.primaryPasses ? <p data-testid="expected-value-omission">The forecast model failed its test on past forecasts, so only scenarios are shown. {data?.expected_value_omission?.reason}</p> : pending ? <PendingExpectedValue data={data} /> : <Unavailable what="The expected saving" />
        )}
      </Section>

      <Section
        id="backtest"
        title="Testing on past forecasts"
        lead="Had the model been fitted before each past OBR forecast, would what then happened have fallen inside its range?"
        detailsTitle="How the test works"
        details={bt ? <>
          <p>
            For each of {bt.origins.length} past OBR forecasts we fitted the model on earlier data only, simulated the
            next four years of September CPI and May–July earnings, and compared the expected gap between the two rules
            with what happened.
          </p>
          <p data-testid="ev-backtest-prose">{backtestProse(bt)}
          </p>
          {bt.note ? <p className="text-xs text-slate-500">{bt.note}</p> : null}
        </> : null}
      >
        {c2 ? <C2ScreenTable screen={c2} provisional={Boolean(getProvisional(data))} /> : bt ? <EvBacktestTable bt={bt} /> : pending ? null : <Unavailable what="The expected-value backtest" />}
        <div className={pending ? "" : "mt-6"}>
          <BacktestNote tdata={data} history={history} />
        </div>
      </Section>

      <Section
        id="survey"
        title="The survey data against DWP"
        lead="Gross saving scales with State Pension spending; net also runs through Pension Credit, Housing Benefit and income tax."
      >
        {cov ? (
          <div className="space-y-3">
            {coverageHeadline(cov) ? <p className="text-sm leading-6 text-slate-700" data-testid="coverage-headline">{coverageHeadline(cov)}</p> : null}
            <Expandable title="All rows and sources" testId="coverage-details">
              <CoverageTable cov={cov} />
            </Expandable>
          </div>
        ) : <Unavailable what="The dataset comparison" />}
      </Section>

      <Section id="limitations" title="Limitations" lead="What the model leaves out or simplifies.">
        {limitations ? (
          <Limitations limitations={limitations} scenariosOnly={scenariosOnly} preBudget={preBudget} />
        ) : (
          <Unavailable what="The list of limitations" />
        )}
      </Section>
    </div>
  );
}
