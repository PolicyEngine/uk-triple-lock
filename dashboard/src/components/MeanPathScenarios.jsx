import { fyLabel, getCentral, getFinalYear } from "../lib/dataHelpers";
import { formatBn } from "../lib/formatters";
import { Section } from "./ui";

/** A recorded scenario-envelope ruling can be displayed without an expected value. */
export default function MeanPathScenarios({ data }) {
  const final = getFinalYear(data);
  const central = getCentral(data);
  const scenarios = Object.entries(data?.mean_path_scenarios?.scenarios ?? {});
  const index = central?.years?.indexOf(final);
  return (
    <Section id="mean-path-scenarios" title="Scenario envelope" boxed={false}>
      <p>The recorded method ruling omits an expected value. Earnings variants are scenarios, not probability claims. Their Monte Carlo errors describe precision of each path set.</p>
      {central && index >= 0 ? <p>On the central path in {fyLabel(final)}: {formatBn(central.gross[index], 1)} gross and {formatBn(central.net[index], 1)} net.</p> : null}
      <table>
        <thead><tr><th>Earnings scenario from 2031</th><th>Gross path-set average</th><th>Net path-set average</th></tr></thead>
        <tbody>{scenarios.map(([name, scenario]) => (
          <tr key={name}>
            <td>{scenario.calendar_earnings_delta > 0 ? "+0.5pp" : "−0.5pp"}</td>
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
