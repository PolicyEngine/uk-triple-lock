"use client";

import { getPastYearsCheck } from "../lib/dataHelpers";
import { getHistory } from "../lib/trajectoryHelpers";
import SectionHeading from "./SectionHeading";
import { PastYears, trajectoryLabels } from "./TrajectoriesTab";
import { Explainer, Unavailable } from "./ui";

function ModelCheck({ check }) {
  const m = check.model;
  return (
    <section className="mb-12" data-testid="past-years-check">
      <SectionHeading title="Would the model have seen it coming?" />
      <Explainer>
        <p>
          Fitted only on data to December {check.years[0] - 1}, the monthly model behind the expected saving gives the
          plan, had it started in April {check.years[0] + 1}, an average gap of {m.mean_gap_pct.toFixed(1)}% of the
          pension by April {check.years[1] + 1} (10th to 90th percentile {m.p10_p50_p90[0].toFixed(1)}% to{" "}
          {m.p10_p50_p90[2].toFixed(1)}%). Replayed on what happened, the gap is {check.realised_gap_pct.toFixed(1)}%,
          at the model&apos;s {Math.round(m.realised_percentile)}th percentile.
          {check.dynamics && Number.isFinite(check.dynamics.realised_percentile)
            ? ` Tilted to the calmer ${check.dynamics_targets.years[0]}-${check.dynamics_targets.years[1]} history, the model would have put it at its ${Math.round(check.dynamics.realised_percentile)}th percentile, one reason the expected saving does not use that tilt.`
            : ""}
        </p>
      </Explainer>
    </section>
  );
}

export default function PastYearsTab({ data }) {
  const history = getHistory(data);
  const labels = trajectoryLabels(data);
  const check = getPastYearsCheck(data);
  if (!labels.triple_lock || !labels.burnham_2030) return <Unavailable what="The past-years comparison" />;
  return (
    <div className="animate-[fadeIn_0.4s_ease-out]" data-testid="past-years-tab">
      {history ? <PastYears history={history} labels={labels} /> : <Unavailable what="The past-years comparison" />}
      {check ? <ModelCheck check={check} /> : null}
    </div>
  );
}
