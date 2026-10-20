import { getBenchmarks, getProvenance, isNum } from "../lib/dataHelpers";
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
  dwp_uprating_2026: { theirs: "£15bn annual nominal direct AME saving in 2039-40", what: "Burnham plan vs triple lock, Great Britain, using Pensim3", ours: "probability-weighted estimate, UK" },
  obr_lted_triple_lock_premium: { theirs: "Triple lock rises 0.6 points a year faster than earnings", what: "OBR long-term assumption", ours: "on our paths, 2034-2039" },
  obr_frs_2025: { theirs: "£15.5bn extra in 2029-30", what: "Triple lock vs earnings uprating since 2012", ours: "had the Burnham plan started in 2012, in 2026-27" },
  rf_ratchet_2026_cumulative: { theirs: "£12.6bn gross, £9bn net, in 2026-27", what: "Triple lock vs earnings uprating since 2012", ours: "net, had the Burnham plan started in 2012" },
  obr_frs_2026: { theirs: "9% of GDP by 2075-76, vs 7% with earnings uprating", what: "50-year projection with ageing", ours: "2039-40, £bn, ages held fixed" },
};

export default function BenchmarksTable({ data }) {
  const rows = getBenchmarks(data);
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
                    {b.id === "dwp_uprating_2026" ? <p className="mt-1">DWP&apos;s published assumptions do not allow a like-for-like comparison with our probability-weighted estimate. Its direct AME saving excludes tax and debt-interest effects. See <ExternalLink href="https://questions-statements.parliament.uk/written-questions/detail/2026-10-05/hl3774">HL3774 (15 October 2026)</ExternalLink>.</p> : <p className="mt-1">{b.note}</p>}
                  </details>
                </td>
                <td className="tabular-nums">
                  <span className="font-medium text-slate-900">{formatOurValue(b.our_metric, b.our_value)}</span>
                  {short?.ours ? <span className="block text-xs text-slate-500">{short.ours}</span> : null}
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
