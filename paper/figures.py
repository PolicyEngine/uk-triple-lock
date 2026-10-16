"""Figures for the working paper, drawn from paperdata (data/results.json).

Each function draws one figure and returns it; the manuscript's code cells call
them. One colour per thing, the same in every figure: the triple lock darkest
teal, the Burnham plan light teal; CPI, earnings and 2.5% a year as greys when
they are references, and CPI grey and earnings mid teal when they are inputs;
gross saving dark teal and net saving light teal.
"""

import sys

import matplotlib

if "ipykernel" not in sys.modules:  # outside the manuscript's kernel: draw off screen
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

import paperdata as D  # noqa: E402

# The dashboard's palette (dashboard/src/lib/colors.js, SERIES): one colour per concept on every tab and figure.
TL = "#1D4044"  # the triple lock (current law): primary-900, darkest teal
BP = "#2C7A7B"  # the Burnham plan: primary-600, mid teal
IN_CPI = "#D97706"  # CPI: amber
IN_EARN = "#285E61"  # earnings: primary-700, dark teal
REF_EARN = IN_EARN  # earnings alone, as a reference level
REF_CPI = IN_CPI  # CPI alone
REF_FLOOR = "#9CA3AF"  # the 2.5% floor: gray-400, pale grey
GROSS = "#234E52"  # gross saving: primary-800
NET = "#4FD1C5"  # net saving: primary-300
BAND_OUTER = "#81E6D9"  # middle 80% of paths: primary-200
BAND_INNER = "#38B2AC"  # middle 50% of paths: primary-400
CENTRAL = "#6B7280"  # the OBR central forecast: gray-500, dashed
OFFSET = "#C9A9A6"  # what shrinks a saving: muted warm
ERROR = "#1F2937"  # Monte Carlo error whiskers: gray-800
ZERO = "#9CA3AF"
GRID = "#E2E8F0"
TEXT = "#344054"
BINDING = {"cpi": IN_CPI, "earnings": IN_EARN, "floor": REF_FLOOR}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8.5,
    "axes.edgecolor": "#CBD5E1",
    "axes.labelcolor": TEXT,
    "axes.titlesize": 9,
    "axes.titleweight": "bold",
    "axes.titlecolor": "#101828",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "legend.frameon": False,
    "legend.fontsize": 7.5,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
})

PCT = FuncFormatter(lambda v, _: f"{'−' if v < 0 else ''}{abs(v):g}%")
BN = FuncFormatter(lambda v, _: f"{'−' if v < 0 else ''}£{abs(v):g}bn")
GBP = FuncFormatter(lambda v, _: f"{'−' if v < 0 else ''}£{abs(v):,.0f}")
WEEK = FuncFormatter(lambda v, _: f"£{v:g}")


def _below(ax, ncol=2):
    """A legend under the axis, so it never covers the data."""
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.13), ncol=ncol, handlelength=1.6, columnspacing=1.0)


def _april_axis(ax, years, every=3, base=False):
    """Categorical x axis of April rises at 0..n-1 (and the level before the first at -1 when ``base``)."""
    ticks = list(range(len(years)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(y) if i % every == 0 or i == len(years) - 1 else "" for i, y in enumerate(years)])
    ax.set_xlim(-1.6 if base else -0.7, len(years) - 0.3)


def _inputs(ax, years, cpi, earnings):
    x = range(len(years))
    ax.plot(x, [100 * v for v in cpi], color=IN_CPI, lw=1.8, marker="o", ms=2.5, label="September CPI")
    ax.plot(x, [100 * v for v in earnings], color=IN_EARN, lw=1.8, marker="s", ms=2.5, label="May–July earnings")
    ax.axhline(100 * D.FLOOR, color=ZERO, ls="--", lw=1, label=D.FLOOR_TEXT)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The inputs, the year before")
    _april_axis(ax, years)
    _below(ax, 1)


def _levels(ax, years, series, title):
    """Cumulative levels from rates: series = [(label, rates, colour, width, style)], level before the first = 100."""
    xs = list(range(-1, len(years)))
    for label, rates, color, lw, ls in series:
        level = [100.0]
        for r in rates:
            level.append(level[-1] * (1 + r))
        ax.plot(xs, level, color=color, lw=lw, ls=ls, label=label)
    ax.set_title(title)
    _april_axis(ax, years, base=True)
    _below(ax, 2)


def history():
    """Step 1: the inputs, the rise and what set it, and the cumulative index, April 2011-2026."""
    rec = D.tl_record()
    years = [r["year"] for r in rec]
    x = range(len(years))
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 3.0))
    _inputs(axes[0], years, [r["cpi"] for r in rec], [r["earnings"] for r in rec])
    ax = axes[1]
    ax.bar(x, [100 * r["rate"] for r in rec], color=[BINDING[r["binding"]] for r in rec], width=0.75)
    for k, label in (("cpi", "Set by CPI"), ("earnings", "Set by earnings"), ("floor", "Set by the floor")):
        ax.bar([0], [0], color=BINDING[k], label=label)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The April rise")
    _april_axis(ax, years)
    _below(ax, 1)
    first = years[0]
    _levels(axes[2], years, [
        ("Triple lock", [r["rate"] for r in rec], TL, 2.2, "-"),
        ("Earnings alone", [r["earnings"] for r in rec], REF_EARN, 1.3, "--"),
        ("CPI alone", [r["cpi"] for r in rec], REF_CPI, 1.3, ":"),
        (f"{D.FLOOR_TEXT} a year", [D.FLOOR] * len(rec), REF_FLOOR, 1.3, "-."),
    ], f"Level (before April {first} = 100)")
    fig.tight_layout(w_pad=1.0)
    return fig


def past_years():
    """Step 1: the plan started earlier: the rises, and the ratio of its level to the triple lock's each April."""
    groups = [g for g in D.history_groups() if g["changes"]]
    years = D.HISTORY["years"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0))
    first = groups[0]
    x = list(range(len(years)))
    w = 0.4
    ax = axes[0]
    ax.bar([i - w / 2 for i in x], [100 * first["tl_rate"][str(y)] for y in years], width=w, color=TL,
           label="Triple lock (latest figures)")
    ax.bar([i + w / 2 for i in x], [100 * first["bp_rate"][str(y)] for y in years], width=w, color=BP,
           label=f"Burnham plan from {first['label']}")
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("April rises")
    _april_axis(ax, years)
    _below(ax, 1)
    ax = axes[1]
    shades = [TL, BP, NET, IN_CPI, REF_FLOOR]  # clearly separate steps, darkest for the earliest start
    for g, c in zip(groups, shades):
        ax.plot(x, [100 * (g["ratio"][str(y)] - 1) for y in years], color=c, lw=1.8, label=f"From {g['label']}")
    ax.axhline(0, color=ZERO, lw=0.8)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The plan's level against the triple lock's")
    _april_axis(ax, years)
    _below(ax, 1)
    fig.tight_layout(w_pad=1.2)
    return fig


def path_view(pid):
    """Steps 2 and 3: a path's inputs, the rise under each rule, and the levels."""
    p = D.path(pid)
    rows = D.path_rows(p)
    years = [r["year"] for r in rows]
    x = list(range(len(rows)))
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 3.0))
    _inputs(axes[0], years, [r["cpi"] for r in rows], [r["earnings"] for r in rows])
    ax = axes[1]
    w = 0.4
    ax.bar([i - w / 2 for i in x], [100 * r["tl_rate"] for r in rows], width=w, color=TL, label="Triple lock")
    ax.bar([i + w / 2 for i in x], [100 * r["bp_rate"] for r in rows], width=w, color=BP, label="Burnham plan")
    ax.axvline(years.index(D.SWITCH) - 0.5, color=ZERO, lw=0.8, ls=":")
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The April rise")
    _april_axis(ax, years)
    _below(ax, 1)
    _levels(axes[2], years, [
        ("Triple lock", [r["tl_rate"] for r in rows], TL, 2.2, "-"),
        ("Burnham plan", [r["bp_rate"] for r in rows], BP, 2.2, "-"),
        ("Earnings alone", [r["earnings"] for r in rows], REF_EARN, 1.2, "--"),
        ("CPI alone", [r["cpi"] for r in rows], REF_CPI, 1.2, ":"),
        (f"{D.FLOOR_TEXT} a year", [D.FLOOR] * len(rows), REF_FLOOR, 1.2, "-."),
    ], f"Level (before April {years[0]} = 100)")
    fig.tight_layout(w_pad=1.0)
    return fig


PATH_STYLE = {"central": (CENTRAL, "--"), "random": (BP, "-"), "monthly_p50": (IN_EARN, "-"),
              "monthly_p90": (TL, "-")}
PATH_SHORT = {"central": "OBR central forecast", "random": "Example path", "monthly_p50": "Typical path",
              "monthly_p90": "High-saving path"}


def gaps():
    """Step 3: the weekly gap in the full new State Pension on each path shown (rule arithmetic)."""
    fig, ax = plt.subplots(figsize=(7.4, 2.8))
    ends = []
    for pid in D.PATH_IDS:
        rows = D.path_rows(D.path(pid))
        color, ls = PATH_STYLE.get(pid, (REF_CPI, "-"))
        y = [52 * (r["tl_weekly"] - r["bp_weekly"]) for r in rows]
        ax.plot([r["year"] for r in rows], y, color=color, ls=ls, lw=1.8, marker="o", ms=2.5)
        ends.append((y[-1], PATH_SHORT.get(pid, pid), color, rows[-1]["year"]))
    # Direct labels at the right, nudged apart where lines end close together.
    ends.sort()
    placed = []
    span = max(e[0] for e in ends) - min(e[0] for e in ends)
    for value, label, color, year in ends:
        pos = value
        if placed and pos - placed[-1] < 0.07 * span:
            pos = placed[-1] + 0.07 * span
        placed.append(pos)
        ax.annotate(label, (year, value), xytext=(year + 0.3, pos), color=color, fontsize=7.5, va="center",
                    annotation_clip=False)
    ax.yaxis.set_major_formatter(GBP)
    ax.set_xlim(right=D.FINAL + 3.2)
    ax.set_title("Full new State Pension: triple lock minus Burnham plan, £ a year")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    fig.tight_layout()
    return fig


def short_label(meta):
    """A panel title from the example's own fields: 'Aged 70, owns their home, State Pension only'."""
    tenure = {"OWNED_OUTRIGHT": "owns their home", "RENT_FROM_COUNCIL": "council tenant"}.get(meta["tenure"],
                                                                                            meta["tenure"].lower())
    income = f"£{meta['private_pension']:,} private pension" if meta["private_pension"] else "State Pension only"
    return f"Aged {meta['age']}, {tenure}, {income}"


def pensioners(pid):
    """Step 4: each example pensioner's change in State Pension and in income, each year, on a path."""
    exs = D.examples(D.path(pid))
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 4.8), sharex=True)
    for ax, letter, (key, ex) in zip(axes.flat, "abcd", exs.items()):
        sp = [D.ex_change(ex, "state_pension", y) for y in D.YEARS]
        net = [D.ex_change(ex, "net_income", y) for y in D.YEARS]
        ax.bar(D.YEARS, sp, color=BP, width=0.7, label="Change in State Pension")
        ax.plot(D.YEARS, net, color=TL, lw=1.8, marker="o", ms=2.5, label="Change in income after tax and benefits")
        ax.axhline(0, color=ZERO, lw=0.8)
        ax.yaxis.set_major_formatter(GBP)
        ax.set_title(f"({letter}) {short_label(ex['meta'])}", fontsize=7.5)
        ax.xaxis.set_major_locator(MaxNLocator(5, integer=True))
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.05, 1, 1), h_pad=1.0)
    return fig


def savings(pid):
    """Step 5: gross and net saving each year on a path (full runs)."""
    p = D.path(pid)
    rows = D.path_rows(p)
    x = [r["year"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.4, 2.7))
    w = 0.4
    ax.bar([v - w / 2 for v in x], [r["gross"] for r in rows], width=w, color=GROSS, label="Gross (State Pension spending)")
    ax.bar([v + w / 2 for v in x], [r["net"] for r in rows], width=w, color=NET, label="Net of tax and benefits")
    ax.axhline(0, color=ZERO, lw=0.8)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Saving by fiscal year (named by its first year)")
    _below(ax, 2)
    fig.tight_layout()
    return fig


def expected():
    """Step 6: the expected saving, gross and net, with 1.96 Monte Carlo standard errors; the central path's gross."""
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ys = D.YEARS
    for out, color, label in (("gross", GROSS, "Expected saving, gross"), ("net", NET, "Expected saving, net")):
        m = [D.est(out, y)["mean"] for y in ys]
        s = [D.est(out, y)["se"] for y in ys]
        ax.fill_between(ys, [a - 1.96 * b for a, b in zip(m, s)], [a + 1.96 * b for a, b in zip(m, s)], color=color,
                        alpha=0.25, lw=0)
        ax.plot(ys, m, color=color, lw=2.2, label=label)
    central = D.path_rows(D.path("central"))
    ax.plot(ys, [r["gross"] for r in central], color=CENTRAL, lw=1.4, ls="--", label="OBR central forecast, gross")
    ax.axhline(0, color=ZERO, lw=0.8)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Saving by fiscal year (named by its first year)")
    _below(ax, 3)
    fig.tight_layout()
    return fig


def runs():
    """Step 6: every full run's final-year saving against its weekly gap (one point per run)."""
    fy = str(D.FINAL)
    pts = [(p["gap_2039_gbp_week"], p["outputs"]["primary"]["gross"][fy], p["outputs"]["primary"]["net"][fy])
           for p in D.EV["paths"]]
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ax.scatter([a for a, _, _ in pts], [b for _, b, _ in pts], s=10, color=GROSS, alpha=0.85, label="Gross saving", lw=0)
    ax.scatter([a for a, _, _ in pts], [c for _, _, c in pts], s=10, color=NET, alpha=0.9, label="Net saving", lw=0)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_formatter(WEEK)
    ax.set_xlabel(f"Gap in the full new State Pension, {D.fy(D.FINAL)}, £ a week")
    ax.set_title(f"Every full run on the Enhanced FRS: saving in {D.fy(D.FINAL)}")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def fan():
    """The saving each year across the paths, as on the dashboard: the average, the median, the middle 50% and 80% of
    paths (weighted full runs), and the OBR central forecast. Gross, in State Pension spending."""
    ys = [y for y in D.YEARS if y >= D.SWITCH]
    q = {k: [D.spread("gross", y, (k,))[0] for y in ys] for k in (0.1, 0.25, 0.5, 0.75, 0.9)}
    mean = [D.est("gross", y)["mean"] for y in ys]
    central = {r["year"]: r["gross"] for r in D.path_rows(D.path("central"))}
    fig, ax = plt.subplots(figsize=(7.4, 3.1))
    ax.fill_between(ys, q[0.1], q[0.9], color=BAND_OUTER, alpha=0.55, lw=0, label="Middle 80% of paths")
    ax.fill_between(ys, q[0.25], q[0.75], color=BAND_INNER, alpha=0.55, lw=0, label="Middle 50% of paths")
    ax.plot(ys, mean, color=TL, lw=2.2, label="Average across paths")
    ax.plot(ys, q[0.5], color=IN_EARN, lw=1.4, ls=":", label="Median path")
    ax.plot(ys, [central[y] for y in ys], color=CENTRAL, lw=1.4, ls="--", label="OBR central forecast")
    ax.axhline(0, color=ZERO, lw=0.8)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Gross saving by fiscal year (named by its first year)")
    _below(ax, 3)
    fig.tight_layout()
    return fig


def scenario_bars():
    """The single scenarios in the final year: gross and net, with 95% Monte Carlo error on the path averages."""
    rows = D.scenarios([D.FINAL])
    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    names = [r["name"] for r in rows][::-1]
    vals = [r["values"][D.FINAL] for r in rows][::-1]
    y = range(len(rows))
    h = 0.36
    ax.barh([i + h / 2 for i in y], [v[0] for v in vals], height=h, color=GROSS, label="Gross",
            xerr=[1.96 * v[2] if v[2] else 0 for v in vals], error_kw={"ecolor": ERROR, "lw": 1, "capsize": 3})
    ax.barh([i - h / 2 for i in y], [v[1] for v in vals], height=h, color=NET, label="Net of tax and benefits",
            xerr=[1.96 * v[3] if v[3] else 0 for v in vals], error_kw={"ecolor": ERROR, "lw": 1, "capsize": 3})
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.xaxis.set_major_formatter(BN)
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Saving in {D.fy(D.FINAL)} by scenario")
    _below(ax, 2)
    fig.tight_layout()
    return fig


def deciles(pid):
    """The change in household income by income decile on a path in the final year, % of income."""
    rows = D.path(pid)["distribution"][str(D.FINAL)]["by_decile"]
    fig, ax = plt.subplots(figsize=(7.4, 2.6))
    x = [r["decile"] for r in rows]
    ax.bar(x, [r["pct_income_change"] for r in rows], color=BP, width=0.7)
    ax.axhline(0, color=ZERO, lw=0.8)
    ax.set_xticks(x)
    ax.set_xlabel("Income decile (1 = lowest income)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{'−' if v < 0 else ''}{abs(v):.2f}%"))
    ax.set_title(f"Change in household income, {D.fy(D.FINAL)}, % of income")
    fig.tight_layout()
    return fig
