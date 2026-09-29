"use client";

import { colors } from "../lib/colors";

export const AXIS_STYLE = {
  fontSize: 12,
  fill: colors.gray[500],
};

/** Shown in place of any block whose inputs fail validation. */
export function Unavailable({ what, plural = false }) {
  return (
    <p
      className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600"
      data-testid="unavailable"
    >
      {what} {plural ? "are" : "is"} unavailable in this results file.
    </p>
  );
}

export function CustomTooltip({ active, payload, label, formatter, labelFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg">
      {label !== undefined ? (
        <div className="mb-2 font-semibold text-slate-800">
          {labelFormatter ? labelFormatter(label) : label}
        </div>
      ) : null}
      {payload
        .filter((entry) => !entry.hide && entry.name)
        .map((entry) => (
          <div className="flex items-center justify-between gap-4" key={entry.name}>
            <span className="flex items-center gap-2 text-slate-600">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              {entry.name}
            </span>
            <span className="font-medium text-slate-800">
              {formatter ? formatter(entry.value, entry.name, entry) : entry.value}
            </span>
          </div>
        ))}
    </div>
  );
}

/** Pill toggle group, styled with the template's .toggle-button. */
export function ToggleGroup({ options, value, onChange, label }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          aria-pressed={value === opt.id}
          className={`toggle-button ${value === opt.id ? "active" : ""}`}
          onClick={() => onChange(opt.id)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function LegendSwatches({ items }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-2">
          <span
            className="inline-block h-[3px] w-5 rounded"
            style={{
              backgroundColor: item.dashed ? "transparent" : item.color,
              borderTop: item.dashed ? `2px dashed ${item.color}` : undefined,
            }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}

/** Short plain-English explainer under a section heading. */
export function Explainer({ children }) {
  return (
    <div className="mb-5 space-y-2 text-sm leading-6 text-slate-600" data-testid="explainer">
      {children}
    </div>
  );
}
