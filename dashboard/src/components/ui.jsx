"use client";

import { useEffect, useRef, useState } from "react";
import { colors, SERIES, WHITE } from "../lib/colors";
import { formatAnnualFromWeekly } from "../lib/formatters";

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
export function Panel({ id, children, className = "", footer, footerTitle = "More detail", footers }) {
  // One closed explanation (footer, footerTitle) or several stacked ones ({title, content, testId}), joined to the box.
  const rows = (footers ?? (footer ? [{ title: footerTitle, content: footer }] : [])).filter((f) => f && f.content);
  return (
    <div id={id} className={`panel scroll-mt-24 ${className}`} data-testid="panel">
      {children}
      {rows.length ? (
        <div className="-mx-6 -mb-6 mt-6">
          {rows.map((f, k) => (
            <details
              key={f.title}
              className={`group border-t border-slate-200 bg-slate-50/60 ${k === rows.length - 1 ? "rounded-b-[18px]" : ""}`}
              data-testid={f.testId}
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-3 text-sm font-semibold text-slate-700">
                <span>{f.title}</span>
                <span aria-hidden="true" className="text-slate-500 transition-transform group-open:rotate-90">
                  ›
                </span>
              </summary>
              <div className="space-y-2 px-6 pb-5 text-sm leading-6 text-slate-600">{f.content}</div>
            </details>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * One section of a tab: a title, a one-line takeaway, the content in a box, and the longer explanation closed
 * underneath. Sections are divided by a rule so a tab reads as a short list of separate parts.
 */
/**
 * A section closed by default, in one box: a clickable header row (title, one-line lead, an optional preview line and
 * a pill) and, once open, the content joined underneath it by a divider. Panels inside lose their own border so the
 * whole section reads as one box; their joined footers still sit at its bottom edge.
 */
export function CollapsibleSection({ id, title, lead, preview, showLabel = "Show", testId, children }) {
  const ref = useRef(null);
  // A link to the section (the "On this tab" menu) opens it.
  useEffect(() => {
    if (!id) return undefined;
    const open = () => {
      if (window.location.hash === `#${id}` && ref.current) ref.current.open = true;
    };
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, [id]);
  return (
    <section id={id} className="section-block scroll-mt-24" data-testid={id ? `section-${id}` : undefined}>
      <details
        ref={ref}
        className="collapsible group overflow-hidden rounded-[18px] border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
        data-testid={testId}
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 transition hover:bg-teal-50/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-xl font-semibold tracking-tight text-slate-900">{title}</span>
            {lead ? <span className="mt-1 block text-[0.95rem] leading-6 text-slate-600">{lead}</span> : null}
            {preview ? <span className="mt-1 block text-sm font-medium text-teal-800" data-testid={testId ? `${testId}-preview` : undefined}>{preview}</span> : null}
          </span>
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-3.5 py-1.5 text-sm font-medium text-teal-800 group-hover:bg-teal-100">
            <span className="group-open:hidden">{showLabel}</span>
            <span className="hidden group-open:inline">Hide</span>
            <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">›</span>
          </span>
        </summary>
        <div className="collapsible-body border-t border-slate-200">{children}</div>
      </details>
    </section>
  );
}

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
                        backgroundColor: state === "current" ? colors.primary[600] : state === "passed" ? colors.primary[100] : WHITE,
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
                  style={{ backgroundColor: on ? colors.primary[600] : colors.gray[200], color: on ? WHITE : colors.gray[500] }}
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

/** A two-or-more-way switch between views of one chart: rounded segmented buttons, the selected one raised. */
export function ViewSwitch({ options, value, onChange, label = "Chart view" }) {
  return (
    <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1 text-sm" role="tablist" aria-label={label}>
      {options.map((v) => (
        <button
          key={v.id}
          type="button"
          role="tab"
          aria-selected={v.id === value}
          onClick={() => onChange(v.id)}
          className={`rounded-full px-3 py-1 font-medium transition-colors ${v.id === value ? "bg-white text-teal-800 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

/** A share as 100 squares, one per 1% of households: the filled ones are the share. For a share the paths barely
 * move, where a spread strip would be a single spike. */
export function ShareGrid({ pct, unit = "households", verb = "are worse off under the plan" }) {
  const filled = Math.round(pct);
  const [hover, setHover] = useState(null);
  return (
    <div className="relative mt-auto pt-4" data-testid="share-grid" onMouseLeave={() => setHover(null)}>
      {hover !== null ? (
        <div className="pointer-events-none absolute -top-7 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-md">
          {hover < filled
            ? `${filled} in 100 ${unit} ${verb}`
            : `${100 - filled} in 100 ${unit} are not affected`}
        </div>
      ) : null}
      <div className="grid grid-cols-[repeat(20,minmax(0,1fr))] gap-[3px]" role="img" aria-label={`${filled} in 100 households`}>
        {Array.from({ length: 100 }, (_, k) => (
          <span
            key={k}
            className="aspect-square cursor-default rounded-[2px]"
            onMouseEnter={() => setHover(k)}
            style={{ background: k < filled ? (hover !== null && hover < filled ? SERIES.highlight : SERIES.burnham) : (hover !== null && hover >= filled ? colors.gray[300] : SERIES.muted) }}
          />
        ))}
      </div>
      <p className="mt-2 text-center text-[11px] text-slate-500">Each square: 1 in 100 {unit}</p>
    </div>
  );
}

/** A headline card: an eyebrow label over free content (the dashboard's metric-card style). */
/**
 * The full new State Pension under two rules as two bars on one scale, per year, with the gap as a chip. `rows` give
 * weekly amounts ({ key, label, weekly, color, testId }); the first row is the one the gap is measured against.
 */
export function PensionCompareCard({ label, rows, fy, against = "the Burnham plan", testId = "card-pension", gapTestId = "card-gap" }) {
  const max = Math.max(...rows.map((r) => r.weekly));
  const diff = rows[1].weekly - rows[0].weekly;
  const pct = (100 * diff) / rows[0].weekly;
  const same = Math.abs(diff) < 0.005;
  const sign = diff < 0 ? "−" : "+";
  return (
    <CardBox label={label} testId={testId}>
      <div className="mt-3 space-y-2">
        {rows.map((r) => (
          <HoverTip key={r.key} block className="rounded-md px-1 py-1 hover:bg-slate-50" tip={`${r.label}: ${formatAnnualFromWeekly(r.weekly, { withWeekly: true })}${fy ? ` in ${fy}` : ""}`}>
            <div data-testid={r.testId}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-slate-600">{r.label}</span>
                <span className="font-semibold tabular-nums text-slate-900">{formatAnnualFromWeekly(r.weekly)} a year</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-slate-100">
                <div className="h-2 rounded-full" style={{ width: `${(100 * r.weekly) / max}%`, background: r.color }} />
              </div>
            </div>
          </HoverTip>
        ))}
      </div>
      <span className="mt-auto self-start pt-3">
        <HoverTip tip={same ? "The two rules pay the same" : `${formatAnnualFromWeekly(Math.abs(diff), { withWeekly: true })} ${diff < 0 ? "less" : "more"} under ${against}`}>
          <span className="inline-block rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-900 hover:bg-teal-100" data-testid={gapTestId}>
            {same ? "The same" : `${sign}${formatAnnualFromWeekly(Math.abs(diff))} a year (${sign}${Math.abs(pct).toFixed(1)}%)`}
          </span>
        </HoverTip>
      </span>
    </CardBox>
  );
}

export function CardBox({ label, testId, children }) {
  return (
    <div className="metric-card flex flex-col" data-testid={testId}>
      <p className="eyebrow text-slate-500">{label}</p>
      {children}
    </div>
  );
}


/**
 * A styled hover (and keyboard focus) tooltip around any element: the dashboard's tooltip look, shown above the
 * element while it is hovered or focused. `tip` is the text; `block` makes the wrapper a block for full-width rows.
 */
export function HoverTip({ tip, children, block = false, className = "", testId, onHover }) {
  const [open, setOpen] = useState(false);
  const show = () => {
    setOpen(true);
    onHover?.(true);
  };
  const hide = () => {
    setOpen(false);
    onHover?.(false);
  };
  const Tag = block ? "div" : "span";
  return (
    <Tag
      className={`relative cursor-default ${block ? "block" : "inline-flex"} ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      tabIndex={0}
      data-testid={testId}
    >
      {children}
      {open && tip ? (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max max-w-[16rem] -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left text-xs font-normal leading-5 text-slate-700 shadow-md"
        >
          {tip}
        </span>
      ) : null}
    </Tag>
  );
}
