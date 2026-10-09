import { fyLabel, getCentral, getFinalYear } from "../lib/dataHelpers";
import { formatBn } from "../lib/formatters";
import { Section } from "./ui";

/** Recorded earnings scenarios, with or without a model-conditional expected value. */
export default function MeanPathScenarios({ data, withExpectedValue = false }) {
  const final = getFinalYear(data);
  const central = getCentral(data);
  const scenarios = Object.entries(data?.mean_path_scenarios?.scenarios ?? {});
  const index = central?.years?.indexOf(final);
  const fallback = data?.uncertainty_ruling?.requested_ruling === "c" && data?.uncertainty_ruling?.effective_ruling === "a";
  return (
    <Section id="mean-path-scenarios" title="Scenario envelope" boxed={false}>
      <p data-testid="scenario-interpretation">{withExpectedValue ? "The recorded earnings envelope is shown beside the model-conditional expected value." : fallback ? "The original primary failed C2, so the build automatically takes (a): scenarios only, with no expected value." : "The recorded method ruling omits an expected value."} Earnings variants are scenarios, not probability claims. Their Monte Carlo errors describe precision of each path set.</p>
      {fallback && data?.expected_value_omission?.reason ? <p data-testid="scenario-fallback-reason">{data.expected_value_omission.reason}</p> : null}
      {central && index >= 0 ? <p>On the central path in {fyLabel(final)}: {formatBn(central.gross[index], 1)} gross and {formatBn(central.net[index], 1)} net.</p> : null}
      <table>
        <thead><tr><th>Earnings scenario</th><th>Gross path-set average</th><th>Net path-set average</th></tr></thead>
        <tbody>{scenarios.map(([name, scenario]) => (
          <tr key={name}>
            <td>{scenario.calendar_earnings_delta > 0 ? "+0.5pp" : "−0.5pp"} from {scenario.from_year ?? 2031}</td>
            {["gross", "net"].map((key) => {
              const estimate = scenario.scenario_path_set?.[key]?.[final];
              return <td key={key}>{estimate ? `${formatBn(estimate.mean, 1)} ± ${formatBn(1.96 * estimate.se, 1)}` : "unavailable"}</td>;
            })}
          </tr>
        ))}</tbody>
      </table>
    </Section>
  );
}
