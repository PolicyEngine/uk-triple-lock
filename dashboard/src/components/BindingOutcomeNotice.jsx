import { formatCount } from "../lib/formatters";
import { getBindingOutcome, isText } from "../lib/dataHelpers";

function day(iso) {
  const date = isText(iso) ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    : null;
}

/**
 * Shown while the committed file is the provisional pre-Budget release and the binding C2 score has failed
 * (`withBindingOutcome`): what the page showed, why it was withdrawn and what it shows now. The rebuilt file
 * records the outcome itself, so this goes with it.
 */
export default function BindingOutcomeNotice({ data }) {
  const b = getBindingOutcome(data);
  if (!b) return null;
  const updated = day(b.date);
  const built = day(b.built);
  const forecast = data?.release?.forecast;
  return (
    <div role="status" className="note-card mb-6 rounded-xl px-5 py-4" data-testid="binding-outcome-notice">
      <p className="note-eyebrow eyebrow">Updated {updated}</p>
      <p className="note-body mt-1 text-sm">
        This dashboard&apos;s pre-Budget release{built ? `, built on ${built},` : ""} showed an expected saving: an estimated
        average across {Number.isInteger(b.draws) ? `${formatCount(b.draws)} ` : ""}simulated paths of prices and earnings, with a
        range around it, provisional until a test we registered before the Budget was run again on the Budget&apos;s figures.
        On {updated}, the model behind those paths failed that test (
        <a href={b.url} target="_blank" rel="noreferrer">uk-triple-lock#45</a>). As the registered rule requires, we have
        withdrawn the expected saving and its range, and this page now shows scenarios only.
      </p>
      <p className="note-body mt-2 text-sm">
        Every figure here still comes from the pre-Budget release{forecast ? `, on the ${forecast} forecast` : ""}. We are
        rebuilding the dashboard on the Budget&apos;s inputs, and its figures may change.
      </p>
    </div>
  );
}
