import { getBenchmarks, getBenchmarksOmitted, getProvenance, isNum } from "../lib/dataHelpers";
import { formatBn } from "../lib/formatters";
import { Unavailable } from "./ui";

const BADGE = {
  yes: { text: "Yes", className: "bg-primary-100 text-primary-800" },
  partial: { text: "Partial", className: "bg-amber-50 text-amber-700" },
  no: { text: "No", className: "bg-slate-100 text-slate-600" },
};

/** Our figure, formatted by what the metric's path in the results file measures. */
export function formatOurValue(metric, value) {
  if (!isNum(value)) return value;
  if (/rate_minus_earnings/.test(metric)) return `${(value * 100).toFixed(2)} points a year`;
  if (/\.rates\./.test(metric)) return `${(value * 100).toFixed(1)}%`;
  if (/level_ratio/.test(metric)) {
    const gap = (1 - value) * 100;
    if (Math.abs(gap) < 0.05) return "the same as the triple lock";
    return `${Math.abs(gap).toFixed(1)}% ${gap > 0 ? "below" : "above"} the triple lock`;
  }
  if (/estimates|saving_bn|_bn\b/.test(metric)) return formatBn(value, 1);
  return value.toLocaleString("en-GB");
}

export function ExternalLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

/**
 * The main point of each published costing in a few words, by benchmark id; the verbatim quote, what it compares and
 * the full note stay one click away. A benchmark without an entry here shows its own text.
 */
const SHORT = {
  dwp_uprating_2026: { theirs: "£15bn annual nominal direct AME saving in 2039-40", what: "Adjusted Triple Lock vs triple lock, Great Britain, using Pensim3" },
  budget_2026_long_term: { theirs: "£15bn a year by the late 2030s, £50bn by the late 2040s", what: "The Budget's figure, from DWP's analysis" },
  obr_efo_2026_medium_term: { theirs: "2.5% under both rules in 2030-31 and 2031-32", what: "OBR forecast, October 2026" },
  obr_lted_triple_lock_premium: { theirs: "Triple lock rises 0.6 points a year faster than earnings", what: "OBR long-term assumption" },
  obr_efo_2026_historical_replay: { theirs: "Payments 1.4% a year below the triple lock, 1990-2025", what: "OBR replay on outturn earnings and prices" },
  obr_frs_2025: { theirs: "£15.5bn extra in 2029-30", what: "Triple lock vs earnings uprating since 2012" },
  rf_ratchet_2026_cumulative: { theirs: "£12.6bn gross, £9bn net, in 2026-27", what: "Triple lock vs earnings uprating since 2012" },
  obr_frs_2026: { theirs: "9% of GDP by 2075-76, vs 7% with earnings uprating", what: "50-year projection with ageing" },
};

/** What our figure is, by the results path it reads: a file with an expected value compares that, one without a
 * scenario. */
export function ourFigure(metric) {
  if (/^expected_value\.estimates\./.test(metric)) return "probability-weighted estimate, UK";
  if (/^expected_value\.gap_by_calibration\./.test(metric)) return "on our paths, 2034-2039";
  if (/^central\.run\.saving_bn\.\d+\.gb\./.test(metric)) return "on the OBR's central path (one scenario), Great Britain";
  if (/^central\.run\.rates\./.test(metric)) return "April 2030 rise on our central path";
  if (/level_ratio/.test(metric)) return "flat rate after the April 2026 rise, replayed from April 2017";
  if (/^scenario_envelope\.obr_wedge\./.test(metric)) return "2039-40, £bn, ages held fixed, OBR-wedge scenario";
  if (/^trajectories\.history\..*\.gross$/.test(metric)) return "had the adjusted Triple Lock started in 2012, in 2026-27";
  if (/^trajectories\.history\..*\.net$/.test(metric)) return "net, had the adjusted Triple Lock started in 2012";
  return null;
}

export default function BenchmarksTable({ data }) {
  const rows = getBenchmarks(data);
  const omitted = getBenchmarksOmitted(data);
  if (!rows) return <Unavailable what="The comparison with other analyses" />;
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="benchmarks">
        <caption className="sr-only">Comparison with other analyses</caption>
        <thead>
          <tr>
            <th>Source</th>
            <th>Their figure</th>
            <th>Ours</th>
            <th>Like for like?</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => {
            const short = SHORT[b.id];
            return (
              <tr key={b.id} className="align-top">
                <td className="min-w-[11rem]">
                  <ExternalLink href={b.url}>{b.publisher}</ExternalLink>
                  <span className="block text-xs text-slate-500">{b.date.slice(0, 4)}</span>
                </td>
                <td>
                  <span className="font-medium text-slate-900">{short?.theirs ?? b.figure_text}</span>
                  <span className="block text-xs text-slate-500">{short?.what ?? b.comparison}</span>
                  <details className="mt-1 text-xs text-slate-500">
                    <summary className="cursor-pointer text-teal-700">Source and notes</summary>
                    <p className="mt-1"><ExternalLink href={b.url}>{b.title}</ExternalLink>: {b.figure_text}</p>
                    <p className="mt-1">{b.comparison}.</p>
                    {b.id === "dwp_uprating_2026" ? <p className="mt-1">DWP&apos;s published assumptions do not allow a like-for-like comparison with our figures. Its direct AME saving excludes tax and debt-interest effects. See <ExternalLink href="https://questions-statements.parliament.uk/written-questions/detail/2026-10-05/hl3774">HL3774 (15 October 2026)</ExternalLink>.</p> : <p className="mt-1">{b.note}</p>}
                  </details>
                </td>
                <td className="tabular-nums">
                  <span className="font-medium text-slate-900">{formatOurValue(b.our_metric, b.our_value)}</span>
                  {ourFigure(b.our_metric) ? <span className="block text-xs text-slate-500">{ourFigure(b.our_metric)}</span> : null}
                </td>
                <td>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${BADGE[b.like_for_like].className}`}>
                    {BADGE[b.like_for_like].text}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {omitted ? (
        <p className="mt-2 text-xs text-slate-500" data-testid="benchmarks-omitted">
          Not compared here, because each compares an expected value this release does not have:{" "}
          {omitted.map((b, i) => (
            <span key={b.id}>
              {i ? "; " : ""}
              <ExternalLink href={b.url}>{b.publisher}, {b.title}</ExternalLink>
            </span>
          ))}
          .
        </p>
      ) : null}
    </div>
  );
}

/** "Replication code: PolicyEngine/uk-triple-lock. Built with policyengine.py X." The policyengine.py version pins the
 * model and data; without one the file's own model and dataset are named instead. */
export function ReplicationLine({ data }) {
  const p = getProvenance(data);
  const version = p?.model?.certification_bundle?.bundle_version ?? p?.release_bundle?.policyengine_version;
  if (!version && p?.model) return <ModelReplicationLine model={p.model} />;
  return (
    <p data-testid="replication">
      Replication code:{" "}
      <ExternalLink href="https://github.com/PolicyEngine/uk-triple-lock">PolicyEngine/uk-triple-lock</ExternalLink>
      . Built with{" "}
      <ExternalLink href="https://github.com/PolicyEngine/policyengine.py">policyengine.py</ExternalLink>
      {version ? ` ${version}` : ""}.
    </p>
  );
}

/** Fallback without a policyengine.py version: the policyengine-uk version and dataset the file records. */
function ModelReplicationLine({ model: m }) {
  return (
    <p data-testid="replication">
      Replication code:{" "}
      <ExternalLink href="https://github.com/PolicyEngine/uk-triple-lock">PolicyEngine/uk-triple-lock</ExternalLink>
      . Built with{" "}
      <ExternalLink href="https://github.com/PolicyEngine/policyengine-uk">policyengine-uk</ExternalLink>
      {m.model_version ? ` ${m.model_version}` : ""}
      {m.runtime_dataset ? ` on ${m.runtime_dataset}` : ""}
      {m.runtime_dataset && m.data_package && m.data_version ? ` (${m.data_package} ${m.data_version})` : ""}.
    </p>
  );
}
