import { isPreBudget } from "../lib/dataHelpers";

/**
 * Shown whenever the results file carries `"release": {"stage": "pre-budget"}` (`triple-lock-build --pre-budget`):
 * an interim, scenarios-only file on the OBR's March 2026 forecast, before the binding post-Budget score. The binding
 * rebuild writes no `release` block, so the banner disappears when it is swapped in.
 */
export default function PreBudgetBanner({ data }) {
  if (!isPreBudget(data)) return null;
  const { forecast, april_2027_cpi_leg: cpiLeg } = data.release;
  return (
    <div role="note" className="note-card mb-6 rounded-xl px-5 py-4" data-testid="pre-budget-banner">
      <p className="note-eyebrow eyebrow">Pre-Budget release</p>
      <p className="note-body mt-1 text-sm">
        Figures use the {forecast ?? "OBR March 2026"} forecast
        {cpiLeg ? `, and April 2027's CPI leg uses ${cpiLeg}` : ""}. The expected saving will be added after the
        28 October Budget.
      </p>
    </div>
  );
}
