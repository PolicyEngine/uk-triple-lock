import {
  fyLabel,
  getAlternatives,
  getBenchmarks,
  getBlockHorizon,
  getCentralForecastSource,
  getCentralNotes,
  getDraws,
  getErrorSource,
  getHorizon,
  getLargestHousehold,
  getLimitations,
  getPolicies,
  getProvenance,
  getSources,
  getVarCrossCheck,
  hasLargestHousehold,
} from "../lib/dataHelpers";
import { formatBn, formatCount } from "../lib/formatters";
import { ExternalLink, ReplicationLine } from "./Benchmarks";
import SectionHeading from "./SectionHeading";
import { Explainer, Unavailable } from "./ui";

const UNAVAILABLE_TEXT = "unavailable";

function Tile({ label, value, detail }) {
  return (
    <div className="metric-card" data-testid="glance-tile">
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-lg font-semibold text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  );
}

function AtAGlance({ data }) {
  const horizon = getHorizon(data);
  const policies = getPolicies(data);
  const draws = getDraws(data);
  const p = getProvenance(data);
  return (
    <section className="section-card">
      <SectionHeading title="At a glance" />
      <Explainer>
        <p>The key facts about this analysis, read from the results file.</p>
      </Explainer>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Years covered"
          value={horizon ? `${fyLabel(horizon[0])} to ${fyLabel(horizon[horizon.length - 1])}` : UNAVAILABLE_TEXT}
          detail={horizon ? `${horizon.length} fiscal years` : null}
        />
        <Tile
          label="Rules compared"
          value={policies ? String(policies.length) : UNAVAILABLE_TEXT}
          detail={policies ? policies.map((x) => x.label).join(", ") : null}
        />
        <Tile
          label="Simulated paths"
          value={draws ? formatCount(draws) : UNAVAILABLE_TEXT}
          detail="Monte Carlo draws of forecast errors"
        />
        <Tile
          label="Model and data"
          value={p.policyengineUk ? `policyengine-uk ${p.policyengineUk}` : UNAVAILABLE_TEXT}
          detail={p.datasetName ? `${p.datasetName}${p.dataBuild ? `, ${p.dataBuild}` : ""}` : null}
        />
      </div>
    </section>
  );
}

const STEPS = [
  {
    title: "Forecast",
    text: "Start from the OBR's central forecast of CPI inflation and earnings growth.",
  },
  {
    title: "Uprate each rule",
    text: "Work out each April's rise under each rule, and compound it from the current rates.",
  },
  {
    title: "Run PolicyEngine UK",
    text: "Apply the new pension rates to every household in the survey data, with all taxes and benefits.",
  },
  {
    title: "Gross and net cost",
    text: "Gross is the change in State Pension spending. Net adds the knock-on changes to other benefits and tax.",
  },
  {
    title: "Distribution",
    text: "Compare each household's net income with the triple lock, and average by group.",
  },
];

function CostingSteps({ data }) {
  const forecast = getCentralForecastSource(data);
  return (
    <section className="section-card">
      <SectionHeading title="How the costing works" />
      <Explainer>
        <p>
          Five steps, run once for each rule on the central forecast
          {forecast && forecast.url ? (
            <>
              {" "}
              (<ExternalLink href={forecast.url}>source</ExternalLink>)
            </>
          ) : null}
          .
        </p>
      </Explainer>
      <ol className="grid gap-3 md:grid-cols-5" data-testid="steps">
        {STEPS.map((step, i) => (
          <li key={step.title} className="metric-card relative">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-700 text-sm font-semibold text-white">
              {i + 1}
            </span>
            <p className="mt-3 font-semibold text-slate-900">{step.title}</p>
            <p className="mt-1 text-sm leading-6 text-slate-600">{step.text}</p>
            {i < STEPS.length - 1 ? (
              <span aria-hidden="true" className="absolute -right-3 top-1/2 hidden text-slate-400 md:block">
                →
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function UncertaintyMethods({ data }) {
  const source = getErrorSource(data);
  const draws = getDraws(data);
  const blockHorizon = getBlockHorizon(data);
  const varCheck = getVarCrossCheck(data);
  const showVar = varCheck !== null && varCheck.status === "ok";

  const rows = [
    {
      label: "Data",
      main: source ? (
        <>
          {source.url ? <ExternalLink href={source.url}>{source.title}</ExternalLink> : source.title}
          {source.years ? `; forecasts made in ${source.years}` : ""}
        </>
      ) : (
        UNAVAILABLE_TEXT
      ),
      var: showVar ? (varCheck.sources ? `ONS series ${varCheck.sources.join(", ")}` : UNAVAILABLE_TEXT) : null,
    },
    {
      label: "What it captures",
      main: "How wrong the OBR's forecasts of CPI and earnings have actually been, including any lasting bias.",
      var: "How CPI and earnings have moved together historically, centred on the OBR's forecast.",
    },
    {
      label: "Horizon",
      main: blockHorizon
        ? `Errors for the first ${blockHorizon} years come from one past forecast, so they move together`
        : UNAVAILABLE_TEXT,
      var: showVar ? (varCheck.lagOrder ? `Each year depends on the previous ${varCheck.lagOrder}` : UNAVAILABLE_TEXT) : null,
    },
    {
      label: "Draws",
      main: draws ? formatCount(draws) : UNAVAILABLE_TEXT,
      var: showVar ? (varCheck.draws ? formatCount(varCheck.draws) : UNAVAILABLE_TEXT) : null,
    },
  ];

  return (
    <section className="section-card">
      <SectionHeading title="How the uncertainty works" />
      <Explainer>
        <p>
          The main method resamples the OBR&apos;s past forecast errors.
          {showVar ? " A second, independent method checks it." : ""} Both apply each rule to every
          simulated path.
        </p>
      </Explainer>
      {varCheck === null ? <Unavailable what="The VAR cross-check description" /> : null}
      <div className="overflow-x-auto">
        <table className="data-table" data-testid="uncertainty-methods">
          <thead>
            <tr>
              <th />
              <th>Main: OBR forecast-error resampling</th>
              {showVar ? <th>Cross-check: VAR model</th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td className="font-semibold">{r.label}</td>
                <td>{r.main}</td>
                {showVar ? <td>{r.var}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ChangesTable() {
  return (
    <section className="section-card">
      <SectionHeading title="What changes and what doesn't" />
      <Explainer>
        <p>Only the rule for uprating the State Pension changes between scenarios.</p>
      </Explainer>
      <div className="grid gap-4 md:grid-cols-2" data-testid="changes">
        <div className="metric-card">
          <p className="eyebrow text-primary-700">Changes with the rule</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
            <li>Basic State Pension</li>
            <li>New State Pension</li>
            <li>
              As a knock-on: the Pension Credit, Housing Benefit and income tax people receive or
              pay
            </li>
          </ul>
        </div>
        <div className="metric-card">
          <p className="eyebrow text-slate-500">The same in every scenario</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
            <li>Additional State Pension and protected payments (in law, uprated by CPI)</li>
            <li>Rates of Pension Credit, Housing Benefit and other benefits</li>
            <li>Tax rates and thresholds</li>
          </ul>
        </div>
      </div>
    </section>
  );
}

// Limitations come from the results file as plain text. Each is placed in one
// group by keyword; anything unmatched goes under "Model".
const GROUPS = [
  { id: "forecast", label: "Forecast", test: /forecast|monte carlo|OBR|earnings growth|AWE/i },
  { id: "data", label: "Data", test: /survey|FRS|dataset|household weight|weighted/i },
  { id: "model", label: "Model", test: /.*/ },
];

function Limitations({ data }) {
  const limitations = getLimitations(data);
  const notes = getCentralNotes(data);
  if (!limitations) {
    return (
      <section className="section-card">
        <SectionHeading title="Limitations" />
        <Unavailable what="The list of limitations" />
      </section>
    );
  }
  const grouped = GROUPS.map((g) => ({ ...g, items: [] }));
  for (const item of limitations) {
    grouped.find((g) => g.test.test(item)).items.push(item);
  }
  return (
    <section className="section-card">
      <SectionHeading title="Limitations" />
      <Explainer>
        <p>What the analysis does not capture, grouped by where the limitation comes from.</p>
      </Explainer>
      <div className="grid gap-4 lg:grid-cols-3">
        {grouped
          .filter((g) => g.items.length > 0)
          .map((g) => (
            <div key={g.id} className="metric-card" data-testid={`limitations-${g.id}`}>
              <p className="eyebrow text-slate-500">{g.label}</p>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700">
                {g.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
      </div>
      {notes.length > 0 ? (
        <div className="mt-5" data-testid="central-notes">
          <p className="eyebrow text-slate-500">Notes from the results file</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <LargestHousehold data={data} />
    </section>
  );
}

function LargestHousehold({ data }) {
  if (!hasLargestHousehold(data)) return null;
  const alternatives = getAlternatives(data);
  const horizon = getHorizon(data);
  if (!alternatives || !horizon) return <Unavailable what="The largest-household table" />;
  const series = alternatives.map((a) => ({ ...a, rows: getLargestHousehold(data, a.id) }));
  if (series.some((s) => !s.rows)) return <Unavailable what="The largest-household table" />;
  return (
    <div className="mt-6">
      <p className="eyebrow text-slate-500">Lumpy survey households</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        How much the single most influential survey household adds to each rule&apos;s net cost
        each year, in £ billion. Large values mean one record, with a large weight, is moving the
        net figure.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="data-table" data-testid="largest-household">
          <thead>
            <tr>
              <th>Year</th>
              {series.map((s) => (
                <th key={s.id}>{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {horizon.map((year, i) => (
              <tr key={year}>
                <td>{fyLabel(year)}</td>
                {series.map((s) => (
                  <td key={s.id} className="tabular-nums">
                    {formatBn(s.rows[i].contribution_bn, 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SourcesAndBenchmarks({ data }) {
  const sources = getSources(data);
  const benchmarks = getBenchmarks(data);
  return (
    <section className="section-card">
      <SectionHeading title="Sources and benchmarks" />
      <Explainer>
        <p>The data and published analyses this dashboard draws on or compares with.</p>
      </Explainer>
      {sources ? (
        <div className="overflow-x-auto">
          <table className="data-table" data-testid="sources">
            <thead>
              <tr>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.title}>
                  <td>{s.url ? <ExternalLink href={s.url}>{s.title}</ExternalLink> : s.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Unavailable what="The list of sources" />
      )}
      <div className="mt-6">
        {benchmarks ? (
          <div className="overflow-x-auto">
            <table className="data-table" data-testid="benchmark-sources">
              <thead>
                <tr>
                  <th>Benchmark</th>
                  <th>Publisher</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {benchmarks.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <ExternalLink href={b.url}>{b.title}</ExternalLink>
                    </td>
                    <td>{b.publisher}</td>
                    <td>{b.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Unavailable what="The list of benchmarks" />
        )}
      </div>
      <div className="mt-6 text-sm text-slate-600">
        <ReplicationLine data={data} />
      </div>
    </section>
  );
}

export default function MethodologyTab({ data }) {
  return (
    <div className="space-y-8">
      <AtAGlance data={data} />
      <CostingSteps data={data} />
      <UncertaintyMethods data={data} />
      <ChangesTable />
      <Limitations data={data} />
      <SourcesAndBenchmarks data={data} />
    </div>
  );
}
