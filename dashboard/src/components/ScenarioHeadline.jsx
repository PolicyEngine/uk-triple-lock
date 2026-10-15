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

/** A round axis maximum just above the largest value, divisible into four even ticks. */
function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.6, 2, 2.4, 3, 4, 6, 8, 10].map((m) => m * p).find((m) => m >= v) ?? 10 * p;
}

/**
 * The scenarios on one £bn axis for the final year: a filled dot for gross, a hollow one for net, and the 95% Monte
 * Carlo error as a whisker on the earnings scenarios. Points, not a distribution: no axis value is a probability.
 */
function ScenarioDots({ rows, fy }) {
  const top = niceMax(Math.max(...rows.flatMap((r) => [r.gross + (r.grossErr ?? 0), r.net + (r.netErr ?? 0)])));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const x = (v) => `${(100 * v) / top}%`;
  return (
    <figure className="mt-5 rounded-xl border border-slate-200 bg-white px-5 py-4" data-testid="scenario-dots">
      <figcaption className="text-sm font-medium text-slate-900">Each scenario&apos;s saving in {fy}, £bn</figcaption>
      <div className="mt-3 space-y-3">
        {rows.map((r) => (
          <div key={r.key} className="grid grid-cols-[minmax(0,11rem)_1fr] items-center gap-3 sm:grid-cols-[14rem_1fr]">
            <span className="text-xs text-slate-600">{r.label}</span>
            <div className="relative h-6">
              <div className="absolute inset-x-0 top-1/2 h-px bg-slate-200" />
              {[["net", "netErr"], ["gross", "grossErr"]].map(([k, e]) => (
                <span key={k}>
                  {r[e] ? (
                    <span
                      className="absolute top-1/2 h-px -translate-y-1/2 bg-slate-500"
                      style={{ left: x(r[k] - r[e]), width: x(2 * r[e]) }}
                    />
                  ) : null}
                  <span
                    className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-teal-700 ${k === "gross" ? "bg-teal-700" : "bg-white"}`}
                    style={{ left: x(r[k]) }}
                    title={`${r.label}: ${formatBn(r[k], 1)} ${k}`}
                  />
                </span>
              ))}
            </div>
          </div>
        ))}
        <div className="grid grid-cols-[minmax(0,11rem)_1fr] gap-3 sm:grid-cols-[14rem_1fr]">
          <span />
          <div className="relative h-4 text-[11px] text-slate-500">
            {ticks.map((t, i) => (
              <span
                key={t}
                className={`absolute ${i === 0 ? "" : i === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2"}`}
                style={{ left: x(t) }}
              >
                {formatBn(t, top < 4 ? 1 : 0)}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex justify-center gap-5 text-xs text-slate-600">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-teal-700 bg-teal-700" />Gross</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-teal-700 bg-white" />Net of tax and benefits</span>
        <span className="flex items-center gap-1.5"><span className="h-px w-4 bg-slate-500" />95% Monte Carlo error</span>
      </div>
    </figure>
  );
}

/** One line on why the paired earnings scenarios are not mirror images, only when the file shows they are not. */
function asymmetryLine(scenarios, fy) {
  const flat = scenarios.filter((s) => s.indistinguishable === true);
  const moved = scenarios.filter((s) => s.indistinguishable === false);
  if (!flat.length || !moved.length) return null;
  const word = (s) => (s.delta > 0 ? "higher" : "lower");
  return `Against the same paths without the shift, ${moved.map(word).join(" and ")} earnings growth ${moved.every((s) => s.lower) ? "cuts" : "changes"} the ${fy} saving, but the change from ${flat.map(word).join(" and ")} growth is not distinguishable from zero, so the two are not mirror images.`;
}

/** The scenarios in one box, for the pre-Budget layout: the final year's gross and net saving per scenario. */
function ScenarioTable({ rows, fy }) {
  const cell = (v, e) => (e ? `${formatBn(v, 1)} ± ${formatBn(e, 1)}` : formatBn(v, 1));
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="data-table" data-testid="scenario-table">
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Gross, {fy}</th>
            <th>Net</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} data-testid={`scenario-${r.key}`}>
              <td>{r.label}</td>
              <td className="tabular-nums">{cell(r.gross, r.grossErr)}</td>
              <td className="tabular-nums">{cell(r.net, r.netErr)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The Budget impact tab's headline for a scenarios-only file (no expected value): the central forecast, the OBR wedge,
 * the paired earnings mean-path scenarios and the last-decade replay, every figure read from the file. Shown once.
 * With a model-conditional expected value (a pre-Budget (b) file) it follows the distribution as its own section:
 * `beside` gives it its own id and title.
 */
export default function ScenarioHeadline({ data, beside = false }) {
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
  const dots = [
    h.central && { key: "central", label: "OBR's central forecast", ...h.central[h.final] },
    h.wedge && { key: "wedge", label: "Triple lock at the OBR's long-term rate", ...h.wedge.values[h.final] },
    ...h.scenarios.map((s) => ({
      key: s.id,
      label: `Earnings ${s.name}`,
      gross: s.values[h.final].gross,
      net: s.values[h.final].net,
      grossErr: Z * s.values[h.final].grossSe,
      netErr: Z * s.values[h.final].netSe,
    })),
  ].filter((r) => r && Number.isFinite(r.gross) && Number.isFinite(r.net));
  const asymmetry = asymmetryLine(h.scenarios, fy);
  const forecast = data?.release?.forecast;
  const onlyTripleLock = Object.keys(data?.scenario_envelope?.obr_wedge?.path?.specified_rates ?? {}).join() === "triple_lock";
  const runs = h.scenarios.find((s) => s.runs)?.runs;
  if (beside) {
    return (
      <Section
        id="scenarios"
        title="Scenarios and sensitivities"
        lead={`The ${fy} saving on single scenarios, each run on its own. On the OBR's smooth central path earnings lead almost every year, so the plan barely bites.`}
        boxed={false}
      >
        {dots.length ? <ScenarioTable rows={dots} fy={fy} /> : null}
      </Section>
    );
  }
  return (
    <Section
      id={beside ? "scenarios" : "at-a-glance"}
      title={beside ? "Beside it: the scenario envelope" : "What the plan saves: the scenario envelope"}
      lead={beside
        ? `The same saving in ${fy} on ${cards.length} scenarios, each run on its own.`
        : `What the Burnham plan saves against the triple lock in ${fy}${cards.length > 1 ? `, on ${cards.length} scenarios` : ""}.${h.interpretation ? ` ${sentence(`together they are a ${h.interpretation}`)}` : ""}`}
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
      {dots.length > 1 ? <ScenarioDots rows={dots} fy={fy} /> : null}
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
