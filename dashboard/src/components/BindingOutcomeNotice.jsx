import { formatCount } from "../lib/formatters";
import { getBindingOutcome, isText } from "../lib/dataHelpers";

function day(iso) {
  const date = isText(iso) ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    : null;
}

/** What the release was built on, as the file records it: its forecast, model version and survey. */
function builtOn(data) {
  const forecast = data?.release?.forecast;
  const version = data?.provenance?.model?.model_version;
  const survey = data?.provenance?.datasets?.primary;
  const items = [
    isText(forecast) ? `the ${forecast} forecast` : null,
    isText(version) ? `PolicyEngine UK ${version}` : null,
    isText(survey) && survey.startsWith("enhanced_frs_2024_25") ? "the Enhanced Family Resources Survey 2024-25" : null,
  ].filter(Boolean);
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : items[0] ?? null;
}

/**
 * Shown while the committed file is the provisional pre-Budget release and the binding C2 score has failed
 * (`withBindingOutcome`): what the page showed, why it was withdrawn and what it shows now. The explainer post carries
 * the same note (policyengine-app-v2#1473). The rebuilt file records the outcome itself, so this goes with it.
 */
export default function BindingOutcomeNotice({ data }) {
  const b = getBindingOutcome(data);
  if (!b) return null;
  const updated = day(b.date);
  const built = day(b.built);
  const inputs = builtOn(data);
  return (
    <div role="status" className="note-card mb-6 rounded-xl px-5 py-4" data-testid="binding-outcome-notice">
      <p className="note-eyebrow eyebrow">Updated {updated}</p>
      <p className="note-body mt-1 text-sm">
        This dashboard&apos;s pre-Budget release{built ? `, built on ${built},` : ""} showed an expected saving: an estimated
        average across {Number.isInteger(b.draws) ? `${formatCount(b.draws)} ` : ""}simulated paths of prices and earnings, with a
        range around it. On {updated}, the model behind those paths failed a test we had registered before the Budget (
        <a href={b.url} target="_blank" rel="noreferrer">uk-triple-lock#45</a>). As the registered rule requires, we have
        withdrawn the expected saving and its range. This page now shows scenarios only, with the model&apos;s own paths
        labelled as illustrations.
      </p>
      <p className="note-body mt-2 text-sm">
        Every figure here still comes from the pre-Budget release{inputs ? `, which uses ${inputs}` : ""}. We are rebuilding
        the dashboard with {b.rebuild}, and its figures may change.
      </p>
    </div>
  );
}
