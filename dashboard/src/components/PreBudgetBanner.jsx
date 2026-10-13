import { getProvisional, isPreBudget } from "../lib/dataHelpers";
import { formatPct } from "../lib/formatters";

/**
 * Shown whenever the results file carries `"release": {"stage": "pre-budget"}` (`triple-lock-build --pre-budget`):
 * an interim file on the OBR's March 2026 forecast, before the binding post-Budget score. Under ruling (a) it shows
 * scenarios only; under (b) a model-conditional expected value; under (c) a provisional one, from the C2 dry run's
 * scores in `release.c2_dry_run`. The binding rebuild writes no `release` block, so the
 * banner disappears when it is swapped in.
 */
export default function PreBudgetBanner({ data }) {
  if (!isPreBudget(data)) return null;
  const { forecast, april_2027_cpi_leg: cpiLeg } = data.release;
  const modelConditional = data.release.execution_ruling === "b" && Boolean(data.expected_value);
  const provisional = getProvisional(data);
  return (
    <div role="note" className="note-card mb-6 rounded-xl px-5 py-4" data-testid="pre-budget-banner">
      <p className="note-eyebrow eyebrow">Pre-Budget release</p>
      <p className="note-body mt-1 text-sm">
        Figures use the {forecast ? forecast.replace(/^OBR /, "OBR's ") : "OBR's March 2026"} forecast
        {cpiLeg ? `, and April 2027's CPI leg uses ${cpiLeg}` : ""}.{" "}
        {provisional
          ? `The expected saving is provisional. In a dry run on today's data, the forecast model passes its pre-registered test on past forecasts: the outcome fell inside its range in ${provisional.terminalHits} of ${provisional.terminalOrigins} final years and ${formatPct(100 * provisional.annualCoverage, 0)} of annual checks. The binding test runs on the 28 October Budget inputs; if the model fails it, the update removes the expected saving and says why.`
          : modelConditional
          ? "The expected saving is model-conditional: the forecast model failed its pre-registered backtest, and a binding test on the 28 October Budget inputs will follow, with a new release."
          : "The expected saving will be added after the 28 October Budget."}
      </p>
    </div>
  );
}
