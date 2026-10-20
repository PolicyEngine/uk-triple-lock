"use client";

import { budgetDay, fyLabel, getC2Screen, getCoverage, getEvBacktest, getExpectedValue, getLimitations, getProvisional, isNum, isPreBudget, withoutCrossCheck } from "../lib/dataHelpers";
import { formatBn, formatCount, formatRate } from "../lib/formatters";
import { Expandable, Panel, Section, Unavailable } from "./ui";

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

/** Readable names for the forecast-model forms the test scores. */
const FORM_NAMES = {
  monthly_var1_boot: "Monthly model (used here)",
  monthly_var2_boot: "Monthly model, longer memory",
  annual_boot_gap: "Annual model",
  monthly_var1_tcop: "Monthly model, heavy-tailed shocks",
  monthly_var1_gauss: "Monthly model, normal shocks",
};
/** Which past OBR forecasts each test scores. */
const TEST_SETS = { A: "6 forecasts, 2016–2021", B: "12 forecasts, 2010–2021" };

/** The form used: test A, April 2022 as in law. */
function usedRow(screen) {
  return screen.rows.find((r) => r.test === "A" && r.form === "monthly_var1_boot" && r.treatment === "suspended");
}

/** Every score and the notes on how it was scored, for the dropdown under the reliability cards. */
function C2Details({ screen, provisional }) {
  return <div className="space-y-3" data-testid="c2-screen">
    <div className="space-y-2">
      <p>The pass mark uses the 6 OBR forecasts of March 2016 to March 2021; the 12 forecasts since June 2010 are a wider check. April 2022 is scored as the law set it, with the earnings link suspended, and years fixed by law are skipped. Scored with the earnings growth published for April 2022 instead, every model placed only 1 of 6 final years inside its range, after the 2021 furlough effect.</p>
      <p>{screen.run_kind === "binding" ? "Scored on the Budget's figures." : provisional ? "Scored on today's figures: the expected saving on this page is provisional until it is scored again on the Budget's figures." : "Scored on today's figures; no expected saving is shown."}</p>
    </div>
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="c2-screen-table">
        <thead><tr><th>Past forecasts</th><th>Model</th><th>April 2022</th><th>Verdict</th><th>Annual checks inside range</th><th>Years scored / skipped</th><th>Final years inside range</th><th>Bias in the gap, points</th><th>Bias in lead changes</th><th>Bias in floor years</th></tr></thead>
        <tbody>{screen.rows.map((r) => <tr key={`${r.test}.${r.form}.${r.treatment}`}>
          <td>{TEST_SETS[r.test] ?? r.test}</td><td>{FORM_NAMES[r.form] ?? r.form}</td><td>{r.treatment === "suspended" ? "As in law" : "As published"}</td>
          <td>{r.treatment === "suspended" ? (r.passes ? "Pass" : "Fail") : "Check only"}</td>
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

/** The survey against DWP for the reliability card: State Pension spending, recipients and Pension Credit claims. */
function coverageRows(cov) {
  const row = Object.fromEntries(cov.rows.map((r) => [r.key, { dwp: r.dwp, ours: cov.gb ? r.primary_gb : r.primary }]));
  const bn = (v) => formatBn(v, 1);
  const m = (v) => `${v.toFixed(2)}m`;
  return [
    row.state_pension_bn && { key: "sp", label: "State Pension spending", short: "of State Pension spending", ...row.state_pension_bn, fmt: bn },
    row.state_pension_recipients_m && { key: "recipients", label: "State Pension recipients", short: "recipients", ...row.state_pension_recipients_m, fmt: m },
    row.pension_credit_claims_m && { key: "pc", label: "Pension Credit claims", short: "Pension Credit claims", ...row.pension_credit_claims_m, fmt: m },
  ].filter((r) => r && isNum(r.ours) && isNum(r.dwp));
}

const RUN_STEPS = [
  { title: "The path drives the economy", text: "A path's CPI and earnings replace the model's own forecasts, so benefit rates, tax thresholds and earnings follow it." },
  { title: "Each rule sets the pension", text: "The basic and new State Pension rise under the triple lock in one run and under the Burnham plan in the other." },
  { title: "Everything else follows the law", text: "Every other tax and benefit is the same in both runs, uprated along the same path." },
  { title: "The difference is the plan", text: "Only the basic and new State Pension differ, so every other change follows from the plan." },
];

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
 * The limitations come from the results file. Each row is matched by its text and shown as a short name and one plain
 * line; the short line is used only while the file's wording still contains every figure it
 * quotes (`needs`), otherwise the file's own text is shown. Items the page states elsewhere, and internal accounting
 * notes, are not repeated (`drop`); anything unmatched is shown in full, so no limitation is lost.
 */
const ISSUE = (repo, n) => ({ label: `${repo}#${n}`, href: `https://github.com/PolicyEngine/${repo}/issues/${n}` });
const LIMIT_ROWS = [
  { group: "Economy", match: /long-term projection/, needs: ["2030"], name: "OBR long-term path",
    short: "After 2030 the central path is the OBR's long-term projection, which the OBR says is not a forecast." },
  { group: "Economy", match: /rests on one statistical model/, needs: ["2000-2026"], name: "One model of prices and earnings",
    short: "The average and range rest on one model of CPI and earnings, fitted to 2000–2026 and tested on past OBR forecasts." },
  { group: "Economy", match: /April 2027's benefit uprating/, needs: ["(2.3%)", "21 October 2026"], name: "April 2027 uprating",
    short: "Benefits rise in April 2027 by the model's CPI forecast (2.3%); September CPI is published on 21 October 2026." },
  { group: "Population", match: /aged statically/, needs: [], name: "No deaths or migration",
    short: "The survey is reweighted, not aged: deaths, migration and pensioners abroad are not modelled, and later retirees' pensions come from today's records." },
  { group: "Population", match: /policyengine-uk-data#538/, needs: ["0.44%"], name: "Weights slightly low",
    short: "Household weights sit 0.44% below their calibrated levels in every year.", issues: [ISSUE("policyengine-uk-data", 538)] },
  { group: "Model coverage", match: /respond only for households already receiving/, needs: [], name: "Benefits for existing claimants only",
    short: "Housing Benefit and council tax reduction respond only for households already claiming them, so the net saving is slightly overstated." },
  { group: "Model coverage", match: /Rents and council tax/, needs: ["2030"], name: "Rents and other income frozen",
    short: "Rents and council tax stay at 2030 levels; dividend, property, savings and self-employment income do not follow the path." },
  { group: "Model coverage", match: /Only the basic and new State Pension change/, needs: ["no behavioural response"], name: "No behavioural response",
    short: "Nobody changes how much they work, save or claim because of the plan." },
  { group: "Model coverage", match: /Pension Age Winter Heating Payment/, needs: ["£100", "£203.40"], name: "Scottish winter payment",
    short: "Scotland's Pension Age Winter Heating Payment is paid at £100 a household, not £203.40 a person living alone, with no 25p addition at 80.",
    issues: [ISSUE("policyengine-uk", 2138), ISSUE("policyengine-uk", 2139)] },
  { group: "Model coverage", match: /cash terms/, needs: ["Great Britain"], name: "UK costs, GB comparisons",
    short: "Costs are for the UK; DWP's figures cover Great Britain, so comparisons with DWP use our Great Britain figures." },
  // Stated under "Our assumptions" or the footer, or internal accounting notes: not repeated here.
  { match: /convention of September CPI/, drop: true },
  { match: /Every rule follows the triple lock to April 2029/, drop: true },
  { match: /certified UK bundle/, drop: true },
  { match: /below State Pension age is not counted/, drop: true },
  { match: /Concentration diagnostics/, drop: true },
];
const LIMIT_GROUP_ORDER = ["Economy", "Population", "Model coverage", "Other"];

function limitationRows(limitations) {
  const used = new Set();
  const rows = LIMIT_ROWS.flatMap((r) => {
    const text = limitations.find((l) => !used.has(l) && r.match.test(l));
    if (!text) return [];
    used.add(text);
    if (r.drop) return [];
    return [{ ...r, line: r.needs.every((n) => text.includes(n)) ? r.short : text }];
  });
  const other = limitations.filter((l) => !used.has(l)).map((l) => ({ group: "Other", name: "Other", line: l }));
  return [...rows, ...other];
}

/** The limitations as one scannable list: name, one line, issue links. */
function Limitations({ limitations, scenariosOnly, preBudget }) {
  const later = scenariosOnly ? limitations.filter((l) => /expected value/i.test(l)) : [];
  const rows = limitationRows(limitations.filter((l) => !later.includes(l)));
  return (
    <>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white" data-testid="limitations">
        {LIMIT_GROUP_ORDER.filter((g) => rows.some((r) => r.group === g)).map((g) => (
          <div key={g}>
            <p className="eyebrow border-b border-slate-100 bg-slate-50 px-4 py-2 text-slate-500">{g}</p>
            <ul className="divide-y divide-slate-100">
              {rows.filter((r) => r.group === g).map((r) => (
                <li key={r.line} className="grid gap-1 px-4 py-3 sm:grid-cols-[14rem_1fr] sm:items-baseline sm:gap-4">
                  <span className="text-sm font-semibold text-slate-900">{r.name}</span>
                  <span className="text-[13px] leading-5 text-slate-700">
                    {r.line}
                    {r.issues?.length ? (
                      <span className="text-slate-500">
                        {" "}(
                        {r.issues.map((iss, k) => (
                          <span key={iss.label}>{k ? ", " : ""}<a href={iss.href} target="_blank" rel="noreferrer">{iss.label}</a></span>
                        ))}
                        )
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
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

/** The run steps. */
function runSteps() {
  return RUN_STEPS;
}

/** One input row: what it is (linked where the file records a URL), and what we use it for. */
function InputRow({ name, href, use }) {
  return (
    <li className="grid gap-1 px-4 py-2.5 sm:grid-cols-[18rem_1fr] sm:gap-4">
      <span className="text-sm font-medium text-slate-900">{href ? <a href={href} target="_blank" rel="noreferrer">{name}</a> : name}</span>
      <span className="text-[13px] leading-5 text-slate-600">{use}</span>
    </li>
  );
}

/** The inputs, with URLs read from the results file; one without a recorded URL is left unlinked. */
function inputs(data) {
  const sources = data?.central?.path?.sources ?? {};
  const bundle = data?.provenance?.model?.certification_bundle?.bundle_version ?? data?.provenance?.release_bundle?.policyengine_version;
  const dataVersion = data?.provenance?.model?.data_version;
  return [
    { key: "model", name: `PolicyEngine UK${bundle ? `, policyengine.py ${bundle}` : ""}`, href: "https://github.com/PolicyEngine/policyengine.py",
      use: "The tax and benefit model every figure is run through." },
    { key: "survey", name: `Enhanced Family Resources Survey 2024-25${dataVersion ? ` (policyengine-uk-data ${dataVersion})` : ""}`,
      use: "The households, their incomes and their State Pensions." },
    { key: "obr", name: "OBR March 2026 Economic and fiscal outlook", href: sources.efo_quarterly?.url ?? sources.efo_calendar?.url,
      use: "The central path of CPI and earnings, and the average the simulated paths are centred on." },
    { key: "lted", name: "OBR long-term economic determinants", href: sources.lted_converted?.url ?? sources.calendar?.url,
      use: "The path after 2030." },
    { key: "ons", name: "ONS CPI and average weekly earnings", href: data?.central?.path?.april_2027_inputs?.cpi_url,
      use: "History the model of prices and earnings is fitted to, and the published inputs to April 2027's rise." },
    { key: "pop", name: "ONS 2024-based population projection", use: "The number of people by age and sex each year." },
    { key: "dwp", name: "DWP Spring Forecast 2026 benefit tables", href: data?.coverage?.dwp?.source,
      use: "A check of the survey's pension and benefit totals (below)." },
  ];
}

export default function MethodTab({ data }) {
  const ev = getExpectedValue(data);
  const bt = getEvBacktest(data);
  const c2 = getC2Screen(data);
  const cov = getCoverage(data);
  const limitations = getLimitations(data);
  const preBudget = isPreBudget(data);
  const scenariosOnly = !ev && data?.uncertainty_ruling?.ruling === "a";
  const pending = scenariosOnly && preBudget && !c2;
  const used = c2 ? usedRow(c2) : null;
  const covRows = cov ? coverageRows(cov) : [];
  const finalFy = ev ? fyLabel(ev.years.at(-1)) : null;
  const switchYear = 2030;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="method-tab">
      <Section
        id="how"
        title="How we model it"
        lead="Each figure is a full PolicyEngine UK run under both rules, on many possible paths of prices and earnings."
        boxed={false}
      >
        <Panel
          footers={[
            { title: "All test results", content: c2 ? <C2Details screen={c2} provisional={Boolean(getProvisional(data))} /> : bt ? <>
              <EvBacktestTable bt={bt} />
              <p className="mt-3" data-testid="ev-backtest-prose">{backtestProse(bt)}</p>
            </> : null },
            { title: "The central path, year by year", content: <CentralPathTable data={data} /> },
          ]}
        >
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="run-steps">
            {runSteps().map((step, k) => (
              <li key={step.title} className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-700 text-xs font-semibold text-white">{k + 1}</span>
                <p className="mt-2 text-sm font-semibold text-slate-900">{step.title}</p>
                <p className="mt-1 text-[13px] leading-5 text-slate-600">{step.text}</p>
              </li>
            ))}
          </ol>
          <div className="mt-4 rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm leading-6 text-slate-700">
            {ev ? (
              <div data-testid="ev-method">
                <p className="eyebrow text-slate-500">{formatCount(ev.nDraws)} paths, {formatCount(ev.nRuns)} run in full</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  <li>A monthly model of CPI and earnings, fitted to 2000–2026 without the furlough months, simulates {formatCount(ev.nDraws)} paths, each shifted so its average matches the OBR&apos;s forecast.</li>
                  <li>They are grouped by the {finalFy}{" "}pension gap, and {formatCount(ev.nRuns)} are run in full, more where the gap varies most; the average weights each group.</li>
                  {isNum(ev.identical) ? <li>{(100 * ev.identical).toFixed(2)}% of paths save nothing: the rules pay the same every year.</li> : null}
                </ul>
              </div>
            ) : c2 && !c2.primaryPasses ? (
              <p data-testid="expected-value-omission">The forecast model failed its test on past forecasts, so only scenarios are shown. {data?.expected_value_omission?.reason}</p>
            ) : pending ? <PendingExpectedValue data={data} /> : <Unavailable what="The expected saving" />}
            {c2 && used ? (
              <p className="mt-3 border-t border-slate-100 pt-3" data-testid="c2-headline">
                <strong>Tested on {used.terminal_scored_origins} past OBR forecasts:</strong>{" "}the outcome fell inside the model&apos;s range in{" "}
                {used.terminal_coverage.hits} of {used.terminal_scored_origins}{" "}final years and{" "}
                {(100 * used.annual_gap_coverage.mean).toFixed(0)}% of annual checks{c2.primaryPasses ? "" : ", short of the pass mark, so only scenarios are shown"}.
              </p>
            ) : bt ? <p className="mt-3 border-t border-slate-100 pt-3">{backtestProse(bt)}</p> : null}
          </div>
        </Panel>
      </Section>

      <Section
        id="inputs"
        title="What we use"
        lead="The model, the survey and the official forecasts and statistics behind every figure."
        boxed={false}
      >
        <Panel footers={cov ? [{ title: "All survey rows and sources", content: <CoverageTable cov={cov} />, testId: "coverage-details" }] : []}>
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200" data-testid="inputs">
            {inputs(data).map((r) => <InputRow key={r.key} {...r} />)}
          </ul>
          {covRows.length ? (
            <p className="mt-3 text-[13px] leading-5 text-slate-600" data-testid="coverage-headline">
              <strong className="text-slate-800">The survey against DWP, {fyLabel(cov.year)}{cov.gb ? ", Great Britain" : ""}:</strong>{" "}
              {covRows.map((r, k) => (
                <span key={r.key}>{k ? (k === covRows.length - 1 ? " and " : ", ") : ""}{r.fmt(r.ours)} {r.short}{" "}(DWP {r.fmt(r.dwp)})</span>
              ))}.
            </p>
          ) : null}
        </Panel>
      </Section>

      <Section
        id="assumptions"
        title="Our assumptions"
        lead="The rules as we read them, and how the population and everything else are held."
        boxed={false}
      >
        <Panel>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700" data-testid="assumptions-list">
            <li><strong>Triple lock (current law)</strong>{" "}to April 2029 under both rules: each April the pension rises by the highest of September CPI, May–July earnings growth and 2.5%.</li>
            <li><strong>Burnham plan</strong>{" "}from April {switchYear}, as DWP defines it: a rise of at least the higher of CPI and 2.5%, topped up to keep the pension at its 2029-30 ratio to earnings; the top-up is rounded up to 0.1 point.</li>
            <li><strong>Population:</strong>{" "}today&apos;s survey, reweighted each year to the ONS projection by age and sex; ages above the survey&apos;s top code of 80 are spread using ONS shares, and State Pension type follows birth cohort.</li>
            <li><strong>Everything else as in law:</strong>{" "}additional State Pension rises with CPI, the Pension Credit guarantee with earnings, and State Pension age is 67 from 2028-29.</li>
            <li><strong>Units:</strong>{" "}cash terms (nominal £), for the UK.</li>
          </ul>
        </Panel>
      </Section>

      <Section
        id="limitations"
        title="Limitations"
        lead="What the model simplifies or leaves out, and which way that could push the saving."
        boxed={false}
      >
        {limitations ? (
          <Limitations limitations={limitations} scenariosOnly={scenariosOnly} preBudget={preBudget} />
        ) : (
          <Unavailable what="The list of limitations" />
        )}
      </Section>
    </div>
  );
}
