import { budgetDay, C2_FALLBACK_TEXT, earningsScenarioName, fyLabel, getC2FailureText, getCentral, getFinalYear, isPreBudget } from "../lib/dataHelpers";
import { formatBn } from "../lib/formatters";
import { Section } from "./ui";

/** Recorded earnings scenarios, with or without a model-conditional expected value. */
export default function MeanPathScenarios({ data, withExpectedValue = false }) {
  const final = getFinalYear(data);
  const central = getCentral(data);
  const scenarios = Object.entries(data?.mean_path_scenarios?.scenarios ?? {});
  const index = central?.years?.indexOf(final);
  const fallback = data?.uncertainty_ruling?.requested_ruling === "c" && data?.uncertainty_ruling?.effective_ruling === "a";
  const failure = fallback ? getC2FailureText(data) : null;
  const preBudget = !withExpectedValue && !fallback && isPreBudget(data);
  const day = budgetDay(data?.release);
  return (
    <Section id="mean-path-scenarios" title="Earnings scenarios" boxed={false}>
      <p data-testid="scenario-interpretation">{withExpectedValue ? "The recorded earnings envelope is shown beside the model-conditional expected value." : fallback ? C2_FALLBACK_TEXT : preBudget ? `The recorded method ruling scores the expected value on the ${day ? `${day} ` : ""}Budget inputs, so this pre-Budget release shows scenarios only.` : "The recorded method ruling omits an expected value."} Earnings variants are scenarios, not probability claims. Their Monte Carlo errors describe precision of each path set.</p>
      {failure ? <p data-testid="scenario-fallback-reason">{failure}</p> : null}
      {central && index >= 0 ? <p>On the central path in {fyLabel(final)}: {formatBn(central.gross[index], 1)} gross and {formatBn(central.net[index], 1)} net.</p> : null}
      <div className="overflow-x-auto"><table className="data-table" data-testid="mean-path-table">
        <thead><tr><th>Earnings scenario</th><th>Gross path-set average</th><th>Net path-set average</th></tr></thead>
        <tbody>{scenarios.map(([name, scenario]) => (
          <tr key={name}>
            <td>{earningsScenarioName(scenario) ?? "unavailable"}</td>
            {["gross", "net"].map((key) => {
              const estimate = scenario.scenario_path_set?.[key]?.[final];
              return <td key={key}>{estimate ? `${formatBn(estimate.mean, 1)} ± ${formatBn(1.96 * estimate.se, 1)}` : "unavailable"}</td>;
            })}
          </tr>
        ))}</tbody>
      </table></div>
    </Section>
  );
}
