import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { colors } from "../lib/colors";
import { fyLabel, getScenarioHeadline } from "../lib/dataHelpers";
import { formatBn, formatWeekly } from "../lib/formatters";
import ChartLogo from "./ChartLogo";
import { AXIS_STYLE, Expandable, Panel, Section } from "./ui";

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

/**
 * The scenarios in one chart, for the pre-Budget layout: the final year's gross and net saving per scenario as bars,
 * with the 95% Monte Carlo error as a whisker on the earnings scenarios (the others are single runs).
 */
function ScenarioTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const line = (v, e) => (e ? `${formatBn(v, 1)} ± ${formatBn(e, 1)}` : formatBn(v, 1));
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg">
      <div className="mb-1 font-semibold text-slate-800">{label}</div>
      <div className="text-slate-600">Gross: <span className="font-medium text-slate-900">{line(r.gross, r.grossErr)}</span></div>
      <div className="text-slate-600">Net: <span className="font-medium text-slate-900">{line(r.net, r.netErr)}</span></div>
      {r.grossErr ? <div className="mt-1 text-xs text-slate-500">Average of simulated paths; ± is the 95% Monte Carlo error.</div> : <div className="mt-1 text-xs text-slate-500">One smooth path, run once.</div>}
    </div>
  );
}

function ScenarioBars({ rows, fy, footer }) {
  const data = rows.map((r) => ({
    label: r.label,
    gross: r.gross,
    net: r.net,
    grossErr: r.grossErr ?? 0,
    netErr: r.netErr ?? 0,
  }));
  const top = niceMax(Math.max(...data.flatMap((r) => [r.gross + r.grossErr, r.net + r.netErr])));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const label = (key, err) => function BarValue({ x, y, width, height, index }) {
    const r = data[index];
    const text = r[err] ? `${formatBn(r[key], 1)} ± ${formatBn(r[err], 1)}` : formatBn(r[key], 1);
    return (
      <text x={x + width + 8 + (r[err] ? (width / r[key]) * r[err] : 0)} y={y + height / 2} dy={4} fontSize={12} fill={colors.gray[700]}>
        {text}
        {r[err] ? null : <tspan fill={colors.gray[400]} fontSize={11}>{" "}· single run</tspan>}
      </text>
    );
  };
  return (
    <Panel footer={footer} footerTitle="How to read this chart">
    <figure data-testid="scenario-bars">
      <figcaption className="text-sm font-medium text-slate-900">Saving in {fy} by scenario, £bn</figcaption>
      <div style={{ width: "100%", height: 90 + 70 * data.length }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 10, right: 130, left: 10, bottom: 0 }} barGap={3}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} horizontal={false} />
            <XAxis type="number" domain={[0, top]} ticks={ticks} tick={AXIS_STYLE} tickFormatter={(v) => formatBn(v, top < 4 ? 1 : 0)} />
            <YAxis type="category" dataKey="label" width={210} tick={AXIS_STYLE} interval={0} />
            <Tooltip cursor={{ fill: colors.gray[100] }} content={<ScenarioTip />} />
            <Bar dataKey="gross" name="Gross" fill={colors.primary[700]} radius={[0, 3, 3, 0]} isAnimationActive={false} label={label("gross", "grossErr")}>
              <ErrorBar dataKey="grossErr" width={6} strokeWidth={1.5} stroke={colors.gray[800]} direction="x" isAnimationActive={false} />
            </Bar>
            <Bar dataKey="net" name="Net of tax and benefits" fill={colors.primary[300]} radius={[0, 3, 3, 0]} isAnimationActive={false} label={label("net", "netErr")}>
              <ErrorBar dataKey="netErr" width={6} strokeWidth={1.5} stroke={colors.gray[800]} direction="x" isAnimationActive={false} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-5 text-xs text-slate-600">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: colors.primary[700] }} />Gross</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: colors.primary[300] }} />Net of tax and benefits</span>
        <span className="flex items-center gap-1.5"><span className="h-px w-4 bg-slate-800" />95% Monte Carlo error (path averages)</span>
      </div>
      <ChartLogo />
    </figure>
    </Panel>
  );
}

/**
 * The Budget impact tab's headline for a scenarios-only file (no expected value): the central forecast, the OBR wedge,
 * the paired earnings mean-path scenarios and the last-decade replay, every figure read from the file. Shown once.
 * With a model-conditional expected value (a pre-Budget (b) file) it follows the distribution as its own section:
 * `beside` gives it its own id and title.
 */
/** The single scenarios as a topic of the Budget tab's comparison panel (pre-Budget layout), or null without them. */
export function singleScenariosTopic(data) {
  if (!getScenarioHeadline(data)) return null;
  return {
    id: "scenarios",
    testId: "scenarios-box",
    title: "Single scenarios",
    summary: "The saving on four fixed paths, each run once, beside the average.",
    content: <ScenarioHeadline data={data} beside />,
  };
}

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
      <div data-testid="single-scenarios">
        <p className="mb-3 text-sm leading-6 text-slate-600">
          The Burnham plan&apos;s saving against the triple lock (current law) in {fy} on four fixed scenarios, to show how much it depends on the path prices and earnings take.
        </p>
        {dots.length ? <ScenarioBars rows={dots} fy={fy} footer={
          <ul className="list-disc space-y-2 pl-5">
            <li><strong>Bars.</strong>{" "}Dark is the saving in State Pension spending; light is what is left after income tax and means-tested benefits respond.</li>
            <li><strong>OBR&apos;s central forecast.</strong>{" "}One smooth path on which earnings beat prices almost every year, so the two rules barely differ.</li>
            <li><strong>Triple lock at the OBR&apos;s long-term rate.</strong>{" "}The triple lock rises 0.6 points a year faster than earnings, as the OBR assumes in the long run.</li>
            <li><strong>Earnings ±0.5pp.</strong>{" "}The simulated paths with earnings growth 0.5 points lower or higher from 2031, averaged. The whisker is the 95% Monte Carlo error of that average.</li>
            <li><strong>Single runs.</strong>{" "}The first two are one fixed path each, run once, so they have no Monte Carlo error.</li>
          </ul>
        } /> : null}
      </div>
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
