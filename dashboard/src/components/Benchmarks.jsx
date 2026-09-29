import { getBenchmarksFor, getProvenance, isNum } from "../lib/dataHelpers";
import { formatBn, formatPct, formatWeekly } from "../lib/formatters";
import { Unavailable } from "./ui";

const BADGE = {
  yes: { text: "Yes", className: "bg-primary-100 text-primary-800" },
  partial: { text: "Partial", className: "bg-amber-50 text-amber-700" },
  no: { text: "No", className: "bg-slate-100 text-slate-600" },
};

/** Our figure, formatted by the units the schema gives the metric's path. */
export function formatOurValue(metric, value) {
  if (!isNum(value)) return value;
  if (/_bn\b|_bn\.|cost_of_triple_lock_vs/.test(metric)) return formatBn(value, 1);
  if (/weekly/.test(metric)) return formatWeekly(value);
  if (/prob_/.test(metric)) return formatPct(value * 100, 0);
  if (/pct/.test(metric)) return formatPct(value, 1);
  return value.toLocaleString("en-GB");
}

/** "Verified" when the benchmark figure has been checked against its source. */
export function ExternalLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

/** Inline list of linked benchmark titles for an explainer sentence. */
export function BenchmarkLinks({ data, scope }) {
  const rows = getBenchmarksFor(data, scope);
  if (!rows || rows.length === 0) return null;
  return rows.map((b, i) => (
    <span key={b.id}>
      {i > 0 ? (i === rows.length - 1 ? " and " : ", ") : ""}
      {b.publisher} (<ExternalLink href={b.url}>{b.title}</ExternalLink>)
    </span>
  ));
}

export default function BenchmarksTable({ data, scope }) {
  const rows = getBenchmarksFor(data, scope);
  if (!rows) return <Unavailable what="The comparison with other analyses" />;
  if (rows.length === 0) {
    return <p className="text-sm text-slate-600">The results file lists no comparisons for this section.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table" data-testid={`benchmarks-${scope}`}>
        <caption className="sr-only">Comparison with other analyses</caption>
        <thead>
          <tr>
            <th>Source</th>
            <th>Their figure</th>
            <th>What it compares</th>
            <th>Our closest figure</th>
            <th>Like for like?</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id}>
              <td>
                <span className="font-medium">{b.publisher}</span>
                <br />
                <ExternalLink href={b.url}>{b.title}</ExternalLink>
                <br />
                <span className="text-xs text-slate-500">{b.date}</span>
              </td>
              <td>{b.figure_text}</td>
              <td>{b.comparison}</td>
              <td className="tabular-nums">{formatOurValue(b.our_metric, b.our_value)}</td>
              <td>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${BADGE[b.like_for_like].className}`}>
                  {BADGE[b.like_for_like].text}
                </span>
              </td>
              <td className="text-slate-600">{b.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * "Replication code: PolicyEngine/uk-triple-lock. Built with policyengine.py
 * X on D (B)." Each version clause is omitted when the
 * results file does not give it.
 */
export function ReplicationLine({ data }) {
  const p = getProvenance(data);
  return (
    <p data-testid="replication">
      Replication code:{" "}
      <ExternalLink href="https://github.com/PolicyEngine/uk-triple-lock">PolicyEngine/uk-triple-lock</ExternalLink>
      . Built with{" "}
      <ExternalLink href="https://github.com/PolicyEngine/policyengine.py">policyengine.py</ExternalLink>
      {p.policyengine ? ` ${p.policyengine}` : ""}
      {p.datasetName ? ` on ${p.datasetName}` : ""}
      {p.datasetName && p.dataBuild ? ` (${p.dataBuild})` : ""}.
    </p>
  );
}
