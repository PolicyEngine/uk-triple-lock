"use client";

import { useEffect, useState } from "react";
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
    <div className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm text-slate-600">
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

/** A box closed by default; the title stays visible and opens the content. */
export function Expandable({ title, children, testId }) {
  return (
    <details className="expandable group" data-testid={testId}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-semibold text-slate-800">
        <span>{title}</span>
        <span aria-hidden="true" className="text-slate-500 transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <div className="border-t border-slate-200 px-4 py-4">{children}</div>
    </details>
  );
}

/**
 * A section's content (charts, tables, controls) in a box; its title and explanation stay outside. A footer is a
 * closed explanation joined to the bottom of the box, so it reads as part of what it explains.
 */
export function Panel({ children, className = "", footer, footerTitle = "More detail" }) {
  return (
    <div className={`panel ${className}`} data-testid="panel">
      {children}
      {footer ? (
        <details className="group -mx-6 -mb-6 mt-6 rounded-b-[18px] border-t border-slate-200 bg-slate-50/60">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-3 text-sm font-semibold text-slate-700">
            <span>{footerTitle}</span>
            <span aria-hidden="true" className="text-slate-500 transition-transform group-open:rotate-90">
              ›
            </span>
          </summary>
          <div className="space-y-2 px-6 pb-5 text-sm leading-6 text-slate-600">{footer}</div>
        </details>
      ) : null}
    </div>
  );
}

/**
 * One section of a tab: a title, a one-line takeaway, the content in a box, and the longer explanation closed
 * underneath. Sections are divided by a rule so a tab reads as a short list of separate parts.
 */
export function Section({ id, title, lead, details, detailsTitle = "More detail", children, boxed = true }) {
  return (
    <section id={id} className="section-block" data-testid={id ? `section-${id}` : undefined}>
      <h2 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h2>
      {lead ? <p className="mt-2 text-[0.95rem] leading-6 text-slate-600">{lead}</p> : null}
      {children && boxed ? (
        <Panel className="mt-5" footer={details} footerTitle={detailsTitle}>
          {children}
        </Panel>
      ) : null}
      {children && !boxed ? <div className="mt-5">{children}</div> : null}
      {details && !boxed ? (
        <div className="mt-4">
          <Expandable title={detailsTitle}>
            <div className="space-y-2 text-sm leading-6 text-slate-600">{details}</div>
          </Expandable>
        </div>
      ) : null}
    </section>
  );
}

/**
 * A tab's page with its sections listed down the right, the one in view highlighted as the reader scrolls. On narrow
 * screens the list sits above the content as links.
 */
export function TabLayout({ sections, children }) {
  const [active, setActive] = useState(sections[0]?.id);
  useEffect(() => {
    function onScroll() {
      // The last section whose top has passed a line near the top of the window is the one being read.
      let current = sections[0]?.id;
      for (const s of sections) {
        const el = document.getElementById(s.id);
        if (el && el.getBoundingClientRect().top <= 140) current = s.id;
      }
      // At the very bottom the last section is the one in view even if its top never reaches the line.
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) current = sections.at(-1)?.id;
      setActive(current);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [sections]);
  return (
    <div>
      <div className="min-w-0">
        {sections.length ? <nav className="mb-2 flex flex-wrap items-center gap-2 text-sm lg:hidden" aria-label="On this tab" data-testid="on-this-tab">
          <span className="mr-1 text-slate-500">On this tab:</span>
          {sections.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-700">
              {s.title}
            </a>
          ))}
        </nav> : null}
        <div className="tab-body">{children}</div>
      </div>
      {sections.length ? <aside className="hidden lg:block">
        <nav className="section-nav" aria-label="Sections on this tab" data-testid="section-nav">
          <p className="eyebrow mb-4 pl-7 text-slate-500">On this tab</p>
          <ol className="relative">
            <span aria-hidden="true" className="absolute bottom-[18px] left-[7px] top-[18px] w-[2px] rounded bg-slate-200" />
            {/* The line fills in teal down to the section being read. */}
            <span
              aria-hidden="true"
              className="absolute left-[7px] top-[18px] w-[2px] rounded transition-all duration-300"
              style={{
                backgroundColor: colors.primary[600],
                height: `calc((100% - 36px) * ${sections.length > 1 ? Math.max(0, sections.findIndex((x) => x.id === active)) / (sections.length - 1) : 0})`,
              }}
            />
            {sections.map((s, i) => {
              const at = sections.findIndex((x) => x.id === active);
              const state = i === at ? "current" : i < at ? "passed" : "ahead";
              return (
                <li key={s.id} className="relative">
                  <a
                    href={`#${s.id}`}
                    aria-current={state === "current" ? "true" : undefined}
                    className="group flex items-center gap-3 py-2.5 text-sm"
                  >
                    <span
                      aria-hidden="true"
                      className="relative z-[1] flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 bg-white transition-all"
                      style={{
                        borderColor: state === "ahead" ? colors.gray[300] : colors.primary[600],
                        backgroundColor: state === "current" ? colors.primary[600] : state === "passed" ? colors.primary[100] : "#fff",
                        boxShadow: state === "current" ? `0 0 0 4px ${colors.primary[50]}` : "none",
                      }}
                    />
                    <span
                      className={`whitespace-nowrap font-medium transition-colors ${
                        state === "current" ? "text-slate-900" : "text-slate-400 group-hover:text-slate-700"
                      }`}
                    >
                      {s.title}
                    </span>
                  </a>
                </li>
              );
            })}
          </ol>
        </nav>
      </aside> : null}
    </div>
  );
}

/** A labelled drop-down for choosing one option, styled to match the page. */
export function Select({ label, options, value, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      <span className="font-medium">{label}</span>
      <span className="relative">
        <select
          className="cursor-pointer appearance-none rounded-full border border-slate-200 bg-white py-1.5 pl-4 pr-9 text-sm font-medium text-slate-800 shadow-sm hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-600/30"
          value={value}
          onChange={(e) => onChange(options.find((o) => String(o.id) === e.target.value)?.id ?? e.target.value)}
          aria-label={label}
        >
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        <span aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">
          ▾
        </span>
      </span>
    </label>
  );
}

/**
 * Several related topics in one box: the topics listed down the left, each with a one-line summary, and the chosen
 * one's content on the right. On narrow screens the list sits above the content.
 */
export function TopicPanel({ topics, testId }) {
  const [chosen, setChosen] = useState(topics[0]?.id);
  const topic = topics.find((t) => t.id === chosen) ?? topics[0];
  return (
    <div className="panel !p-0 overflow-hidden" data-testid={testId}>
      <div className="grid md:grid-cols-[300px_minmax(0,1fr)]">
        <div className="border-b border-slate-200 bg-slate-50/70 p-3 md:border-b-0 md:border-r" role="tablist" aria-orientation="vertical">
          {topics.map((t, k) => {
            const on = t.id === topic.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setChosen(t.id)}
                className={`mb-1 flex w-full gap-3 rounded-xl px-3 py-3 text-left transition-colors last:mb-0 ${on ? "bg-white shadow-sm ring-1 ring-slate-200" : "hover:bg-white/70"}`}
              >
                <span
                  className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                  style={{ backgroundColor: on ? colors.primary[600] : colors.gray[200], color: on ? "#fff" : colors.gray[500] }}
                >
                  {k + 1}
                </span>
                <span>
                  <span className={`block text-sm font-semibold ${on ? "text-slate-900" : "text-slate-700"}`}>{t.title}</span>
                  {t.summary ? <span className="mt-0.5 block text-xs leading-5 text-slate-500">{t.summary}</span> : null}
                </span>
              </button>
            );
          })}
        </div>
        <div className="min-w-0 p-6" role="tabpanel" data-testid={topic.testId}>
          {topic.content}
        </div>
      </div>
    </div>
  );
}

/** Sub-tabs inside a tab, styled like the main tabs but smaller. */
export function SubTabs({ options, value, onChange }) {
  return (
    <div className="mb-8 flex w-fit flex-wrap border-b-2 border-slate-200" role="tablist" aria-label="Views in this tab">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="tab"
          aria-selected={o.id === value}
          onClick={() => onChange(o.id)}
          className={`tab-button sub-tab-button ${o.id === value ? "active" : ""}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
