import { fyLabel, getScenarioHeadline } from "../lib/dataHelpers";
import { formatBn, formatWeekly } from "../lib/formatters";
import { Expandable, Section } from "./ui";

const Z = 1.96;

function sentence(text) {
  const t = text.replace(/;\s*/g, ", ");
  return `${t[0].toUpperCase()}${t.slice(1)}.`;
}

function Card({ label, value, detail, earlier, testId }) {
  return (
    <div className="metric-card flex flex-col" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail ? <p className="mt-1 text-sm text-slate-600">{detail}</p> : null}
      {earlier ? <p className="mt-auto pt-3 text-xs text-slate-500">{earlier}</p> : null}
    </div>
  );
}

/** "2034-35: £0.7bn gross, £0.5bn net", for every headline year before the final one the file gives. */
function earlierYears(values, years, final) {
  const parts = years.filter((y) => y !== final && values[y]).map((y) => `${fyLabel(y)}: ${formatBn(values[y].gross, 1)} gross, ${formatBn(values[y].net, 1)} net`);
  return parts.length ? parts.join("; ") : null;
}

/** One line on why the paired earnings scenarios are not mirror images, only when the file shows they are not. */
function asymmetryLine(scenarios, fy) {
  const flat = scenarios.filter((s) => s.indistinguishable === true);
  const moved = scenarios.filter((s) => s.indistinguishable === false);
  if (!flat.length || !moved.length) return null;
  const word = (s) => (s.delta > 0 ? "higher" : "lower");
  return `Against the same paths without the shift, ${moved.map(word).join(" and ")} earnings growth ${moved.every((s) => s.lower) ? "cuts" : "changes"} the ${fy} saving, but the change from ${flat.map(word).join(" and ")} growth is not distinguishable from zero, so the two are not mirror images.`;
}

/**
 * The Budget impact tab's headline for a scenarios-only file (no expected value): the central forecast, the OBR wedge,
 * the paired earnings mean-path scenarios and the last-decade replay, every figure read from the file. Shown once.
 */
export default function ScenarioHeadline({ data }) {
  const h = getScenarioHeadline(data);
  if (!h) return null;
  const fy = fyLabel(h.final);
  const fyTight = fy.replace("-", "‑"); // a non-breaking hyphen keeps "2039-40" on one line
  const fallback = data?.uncertainty_ruling?.requested_ruling === "c" && data?.uncertainty_ruling?.effective_ruling === "a";
  const cards = [
    h.central && {
      key: "central",
      label: "The OBR's central forecast",
      value: formatBn(h.central[h.final].gross, 1),
      detail: `Gross, ${fyTight}; ${formatBn(h.central[h.final].net, 1)} net of tax and benefits`,
      earlier: earlierYears(h.central, h.years, h.final),
    },
    h.wedge && {
      key: "wedge",
      label: "Triple lock at the OBR's long-term rate",
      value: formatBn(h.wedge.values[h.final].gross, 1),
      detail: `Gross, ${fyTight}; ${formatBn(h.wedge.values[h.final].net, 1)} net`,
      earlier: earlierYears(h.wedge.values, h.years, h.final),
    },
    ...h.scenarios.map((s) => ({
      key: `earnings-${s.id}`,
      label: `Earnings ${s.name}`,
      value: `${formatBn(s.values[h.final].gross, 1)} ± ${formatBn(Z * s.values[h.final].grossSe, 1)}`,
      detail: `Gross, ${fyTight}, average of ${s.runs ? `${s.runs} ` : ""}simulated paths; ${formatBn(s.values[h.final].net, 1)} ± ${formatBn(Z * s.values[h.final].netSe, 1)} net`,
      earlier: earlierYears(s.values, h.years, h.final),
    })),
  ].filter(Boolean);
  const asymmetry = asymmetryLine(h.scenarios, fy);
  const forecast = data?.release?.forecast;
  const onlyTripleLock = Object.keys(data?.scenario_envelope?.obr_wedge?.path?.specified_rates ?? {}).join() === "triple_lock";
  const runs = h.scenarios.find((s) => s.runs)?.runs;
  return (
    <Section
      id="at-a-glance"
      title="What the plan saves: the scenario envelope"
      lead={`What the Burnham plan saves against the triple lock in ${fy}${cards.length > 1 ? `, on ${cards.length} scenarios` : ""}.${h.interpretation ? ` ${sentence(`together they are a ${h.interpretation}`)}` : ""}`}
      boxed={false}
    >
      {fallback && data?.expected_value_omission?.reason ? (
        <p className="mb-4 text-sm leading-6 text-slate-700" data-testid="scenario-interpretation">
          The original primary failed C2, so the build automatically takes (a): scenarios only, with no expected value.{" "}
          <span data-testid="scenario-fallback-reason">{data.expected_value_omission.reason}</span>
        </p>
      ) : null}
      {cards.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="scenario-cards">
          {cards.map(({ key, ...card }) => <Card key={key} testId={`scenario-${key}`} {...card} />)}
        </div>
      ) : null}
      {h.replay ? (
        <p className="mt-5 rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm leading-6 text-slate-700" data-testid="scenario-replay">
          <strong className="text-slate-900">Looking back.</strong>{" "}Had the plan started in April {h.replay.switchYear}, it
          would have saved {formatBn(h.replay.gross, 1)} in State Pension spending in {fyLabel(h.replay.year)} (
          {formatBn(h.replay.net, 1)} net), with the full new State Pension at {formatWeekly(h.replay.plan)} a week instead
          of {formatWeekly(h.replay.actual)}.{h.replay.interpretation ? ` ${sentence(h.replay.interpretation)}` : ""}
        </p>
      ) : null}
      <div className="mt-4">
        <Expandable title="How to read these scenarios" testId="scenario-details">
          <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
            {h.central ? (
              <li>
                <strong>Central forecast.</strong>{" "}One smooth path{forecast ? `, the ${forecast} forecast and the OBR's long-term projection after it` : ""}.
                Earnings lead in almost every year, so the plan barely bites.
              </li>
            ) : null}
            {h.wedge ? (
              <li data-testid="scenario-wedge-note">
                <strong>OBR&apos;s long-term rate.</strong>{" "}{h.wedge.source ? sentence(h.wedge.source) : "The triple lock rises at the OBR's long-term rate."}
                {onlyTripleLock ? " The Burnham plan's rises are those of the central forecast." : ""}
              </li>
            ) : null}
            {h.scenarios.length ? (
              <li>
                <strong>Earnings scenarios.</strong>{" "}Each is the average over {runs ? `${runs} ` : ""}simulated paths of
                prices and earnings, with earnings growth shifted from the year shown. Prices and earnings swap the lead
                on these paths, which is when the plan saves, so they save far more than the smooth central path. The ±
                is the 95% Monte Carlo error: how precisely the paths pin down the average, not a range for the saving.
              </li>
            ) : null}
            {asymmetry ? <li data-testid="scenario-asymmetry">{asymmetry}</li> : null}
            {h.replay ? (
              <li>
                <strong>Other start years.</strong>{" "}The How the triple lock works tab replays the plan from other
                Aprils.
              </li>
            ) : null}
          </ul>
        </Expandable>
      </div>
    </Section>
  );
}
