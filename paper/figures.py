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

TL = "#1D4044"  # the triple lock (primary-900)
BP = "#38B2AC"  # the Burnham plan (primary-400)
IN_CPI = "#6B7280"  # CPI as an input (gray-500)
IN_EARN = "#285E61"  # earnings as an input (primary-700)
REF_EARN = "#6B7280"  # earnings alone, as a reference level
REF_CPI = "#9CA3AF"  # CPI alone
REF_FLOOR = "#CBD5E1"  # 2.5% a year
GROSS = "#285E61"
NET = "#4FD1C5"
ZERO = "#9CA3AF"
GRID = "#E2E8F0"
TEXT = "#344054"
BINDING = {"cpi": IN_CPI, "earnings": IN_EARN, "floor": "#D1D5DB"}

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
    shades = [TL, IN_EARN, BP, "#81E6D9", REF_CPI]
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


PATH_STYLE = {"central": (REF_CPI, "--"), "random": (BP, "-"), "monthly_p50": (IN_EARN, "-"),
              "monthly_p90": (TL, "-")}
PATH_SHORT = {"central": "Central forecast", "random": "Random path", "monthly_p50": "Middle path",
              "monthly_p90": "90th-percentile path"}


def gaps():
    """Step 3: the weekly gap in the full new State Pension on each path shown (rule arithmetic)."""
    fig, ax = plt.subplots(figsize=(7.4, 2.8))
    ends = []
    for pid in D.PATH_IDS:
        rows = D.path_rows(D.path(pid))
        color, ls = PATH_STYLE.get(pid, (REF_CPI, "-"))
        y = [r["tl_weekly"] - r["bp_weekly"] for r in rows]
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
    ax.yaxis.set_major_formatter(WEEK)
    ax.set_xlim(right=D.FINAL + 2.6)
    ax.set_title("Full new State Pension: triple lock minus Burnham plan, £ a week")
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
    ax.bar([v + w / 2 for v in x], [r["net"] for r in rows], width=w, color=NET, label="Net of tax and other benefits")
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
    ax.plot(ys, [r["gross"] for r in central], color=REF_CPI, lw=1.4, ls="--", label="Central forecast alone, gross")
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
