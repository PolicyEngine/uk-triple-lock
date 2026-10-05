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

/** "Replication code: PolicyEngine/uk-triple-lock. Built with policyengine-uk X (...) on D (B)." */
export function ReplicationLine({ data }) {
  const p = getProvenance(data);
  if (p?.model) return <ModelReplicationLine model={p.model} />;
  const b = p?.release_bundle ?? {};
  return (
    <p data-testid="replication">
      Replication code:{" "}
      <ExternalLink href="https://github.com/PolicyEngine/uk-triple-lock">PolicyEngine/uk-triple-lock</ExternalLink>
      . Built with{" "}
      <ExternalLink href="https://github.com/PolicyEngine/policyengine.py">policyengine.py</ExternalLink>
      {b.policyengine_version ? ` ${b.policyengine_version}` : ""}
      {b.runtime_dataset ? ` on ${b.runtime_dataset}` : ""}
      {b.runtime_dataset && b.certified_data_build_id ? ` (${b.certified_data_build_id})` : ""}.
    </p>
  );
}

/** The model-v2 provenance: policyengine-uk pinned directly, so no policyengine.py bundle certifies the pair. */
function ModelReplicationLine({ model: m }) {
  return (
    <p data-testid="replication">
      Replication code:{" "}
      <ExternalLink href="https://github.com/PolicyEngine/uk-triple-lock">PolicyEngine/uk-triple-lock</ExternalLink>
      . Built with{" "}
      <ExternalLink href="https://github.com/PolicyEngine/policyengine-uk">policyengine-uk</ExternalLink>
      {m.model_version ? ` ${m.model_version}` : ""}
      {m.runtime_dataset ? ` on ${m.runtime_dataset}` : ""}
      {m.runtime_dataset && m.data_package && m.data_version ? ` (${m.data_package} ${m.data_version})` : ""}
      {m.certified === false ? ", a pairing no policyengine.py release has certified yet" : ""}.
    </p>
  );
}
