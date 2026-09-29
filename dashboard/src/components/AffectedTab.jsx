"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors, colorFor } from "../lib/colors";
import {
  fyLabel,
  getAlternatives,
  getAvailableBreakdowns,
  getBreakdown,
  getDistributionYear,
  getHouseholdsAffected,
  hasLargestHousehold,
} from "../lib/dataHelpers";
import { formatBn, formatCurrency, formatPct } from "../lib/formatters";
import ChartLogo from "./ChartLogo";
import SectionHeading from "./SectionHeading";
import { AXIS_STYLE, CustomTooltip, Expandable, Explainer, ToggleGroup, Unavailable } from "./ui";

const METRIC_OPTIONS = [
  { id: "pct", label: "% of income" },
  { id: "gbp", label: "£ a year" },
];

// Income groups keep their natural order; other groups are sorted by the change shown.
const ORDERED_GROUPS = new Set(["decile", "quintile"]);

function shortLabel(label) {
  return label.length > 28 ? `${label.slice(0, 26)}…` : label;
}

function GroupChart({ breakdown, groupId, policy, metric }) {
  const key = metric === "gbp" ? "mean_change_gbp" : "pct_income_change";
  const format = metric === "gbp" ? formatCurrency : (v) => formatPct(v, 2);
  const rows = breakdown.rows.map((r) => ({ label: r.label, value: r[key] }));
  if (!ORDERED_GROUPS.has(groupId)) rows.sort((a, b) => a.value - b.value);
  const longest = Math.max(...rows.map((r) => shortLabel(r.label).length));
  const tilt = rows.length > 6 || longest > 12;
  return (
    <>
      <div className={tilt ? "h-[420px]" : "h-[340px]"}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 10, right: 20, left: 10, bottom: tilt ? 10 : 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.border.light} vertical={false} />
            <XAxis
              dataKey="label"
              tick={AXIS_STYLE}
              tickFormatter={shortLabel}
              interval={0}
              angle={tilt ? -35 : 0}
              textAnchor={tilt ? "end" : "middle"}
              height={tilt ? Math.min(150, 20 + longest * 5.5) : 30}
            />
            <YAxis tick={AXIS_STYLE} tickFormatter={format} />
            <ReferenceLine y={0} stroke={colors.gray[400]} />
            <Tooltip content={<CustomTooltip formatter={format} />} />
            <Bar dataKey="value" name={policy.label} fill={colorFor(policy.id)} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartLogo />
    </>
  );
}

function GroupTable({ breakdown, groupLabel }) {
  return (
    <div className="mt-4">
    <Expandable title={`Table: change by ${groupLabel.toLowerCase()}`} testId="group-table-box">
    <div className="overflow-x-auto">
      <table className="data-table" data-testid="group-table">
        <caption className="sr-only">Change by {groupLabel.toLowerCase()}</caption>
        <thead>
          <tr>
            <th>{groupLabel}</th>
            <th>Mean change, £ a year</th>
            <th>Change, % of income</th>
            {breakdown.hasTotal ? <th>Total, £ billion</th> : null}
            {breakdown.hasShare ? <th>Share of households</th> : null}
          </tr>
        </thead>
        <tbody>
          {breakdown.rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="tabular-nums">{formatCurrency(r.mean_change_gbp)}</td>
              <td className="tabular-nums">{formatPct(r.pct_income_change, 2)}</td>
              {breakdown.hasTotal ? <td className="tabular-nums">{formatBn(r.total_bn, 2)}</td> : null}
              {breakdown.hasShare ? <td className="tabular-nums">{formatPct(r.share_of_households_pct)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </Expandable>
    </div>
  );
}

function ChangeByGroup({ data, policy, yearText }) {
  const available = getAvailableBreakdowns(data);
  const [groupId, setGroupId] = useState(available.length > 0 ? available[0].id : null);
  const [metric, setMetric] = useState("pct");

  if (available.length === 0) return <Unavailable what="The breakdown by group" />;
  const group = available.find((b) => b.id === groupId);
  if (!group) return <Unavailable what="The breakdown by group" />;
  const breakdown = getBreakdown(data, group.id, policy.id);

  return (
    <>
      <Explainer>
        <p>
          <strong>Mean change</strong> is the average change in household net income in {yearText},
          in £ a year, across every household in the group, and <strong>% of income</strong> is that
          change as a share of the group&apos;s net income; negative means less income than under
          the triple lock. Only the basic and new State Pension change, so the charts leave out
          groups the State Pension does not reach (people under State Pension age and working-age
          households).
          {hasLargestHousehold(data)
            ? " A group with few survey households can move with a single record, so treat differences of a few pounds with caution."
            : ""}
        </p>
      </Explainer>
      <div className="mb-3 flex flex-wrap items-center gap-4">
        <ToggleGroup
          options={available.map((b) => ({ id: b.id, label: b.label }))}
          value={group.id}
          onChange={setGroupId}
          label="Group"
        />
      </div>
      <div className="mb-5">
        <ToggleGroup options={METRIC_OPTIONS} value={metric} onChange={setMetric} label="Measure" />
      </div>
      {breakdown ? (
        <>
          <GroupChart breakdown={breakdown} groupId={group.id} policy={policy} metric={metric} />
          <GroupTable breakdown={breakdown} groupLabel={group.label} />
        </>
      ) : (
        <Unavailable what={`The breakdown by ${group.label.toLowerCase()}`} />
      )}
    </>
  );
}

function LosersCards({ data, alternatives }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {alternatives.map((alt) => {
        const block = getHouseholdsAffected(data, alt.id);
        return (
          <div className="metric-card" key={alt.id} data-testid={`losers-${alt.id}`}>
            <p className="eyebrow text-slate-500">{alt.label}</p>
            {block ? (
              <>
                <p className="mt-3 text-2xl font-semibold text-slate-900">{formatPct(block.losing_pct)}</p>
                <p className="text-sm text-slate-600">of households lose</p>
                <p className="mt-3 text-sm text-slate-600">
                  Average loss among them: <strong>{formatCurrency(block.mean_loss_gbp)}</strong> a year
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-600">Unavailable in this results file.</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function AffectedTab({ data }) {
  const alternatives = getAlternatives(data);
  const [selectedId, setSelectedId] = useState(alternatives ? alternatives[0].id : null);

  if (!alternatives) return <Unavailable what="The list of uprating rules" />;
  const policy = alternatives.find((a) => a.id === selectedId);
  if (!policy) return <Unavailable what="The selected rule" />;
  const yearText = fyLabel(getDistributionYear(data));

  return (
    <div className="space-y-8">
      <section className="section-card">
        <SectionHeading title="Households that lose compared with the triple lock" />
        <Explainer>
          <p>
            The share of all households whose net income in {yearText} is lower under each rule than
            under the triple lock, and the average loss a year among those households. Households
            with nobody on the State Pension are not affected directly.
          </p>
        </Explainer>
        <LosersCards data={data} alternatives={alternatives} />
      </section>

      <section className="section-card">
        <SectionHeading title="Change by group" />
        <div className="mb-6">
          <p className="mb-2 text-sm text-slate-600">
            Choose the rule to compare with the triple lock:
          </p>
          <ToggleGroup
            options={alternatives.map((a) => ({ id: a.id, label: a.label }))}
            value={policy.id}
            onChange={setSelectedId}
            label="Uprating rule"
          />
        </div>
        <ChangeByGroup data={data} policy={policy} yearText={yearText} />
      </section>
    </div>
  );
}
