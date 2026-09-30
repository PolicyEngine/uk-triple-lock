"""Figures for the working paper, drawn from paperdata (data/results.json).

Each function draws one figure and returns it; the manuscript's code cells call
them. Colours follow the dashboard (dashboard/src/lib/colors.js): the triple
lock darkest teal, the Burnham plan mid teal, CPI grey, earnings light teal.
"""

import sys

import matplotlib

if "ipykernel" not in sys.modules:  # outside the manuscript's kernel: draw off screen
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

import paperdata as D  # noqa: E402

TL = "#1D4044"
BP = "#2C7A7B"
CPI = "#6B7280"
EARN = "#38B2AC"
FLOOR = "#9CA3AF"
LIGHT = "#81E6D9"
GRID = "#E2E8F0"
TEXT = "#344054"
BINDING = {"cpi": CPI, "earnings": BP, "floor": "#D1D5DB"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8.5,
    "axes.edgecolor": "#CBD5E1",
    "axes.labelcolor": TEXT,
    "axes.titlesize": 9,
    "axes.titleweight": "semibold",
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

PCT = FuncFormatter(lambda v, _: f"{v:g}%")
BN = FuncFormatter(lambda v, _: f"£{v:g}bn")
GBP = FuncFormatter(lambda v, _: f"{'-' if v < 0 else ''}£{abs(v):,.0f}")


def _years_axis(ax, labels, every=2):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([lab if i % every == 0 else "" for i, lab in enumerate(labels)])


def history():
    """Step 1: the inputs, the rise and what set it, and the cumulative index, April 2011-2026."""
    rec = D.tl_record()
    years = [r["year"] for r in rec]
    x = range(len(years))
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    ax = axes[0]
    ax.plot(x, [100 * r["cpi"] for r in rec], color=CPI, lw=1.8, marker="o", ms=2.5, label="September CPI")
    ax.plot(x, [100 * r["earnings"] for r in rec], color=EARN, lw=1.8, marker="o", ms=2.5,
            label="May–July earnings")
    ax.axhline(100 * D.FLOOR, color=FLOOR, ls="--", lw=1, label=D.FLOOR_TEXT)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The inputs, the year before")
    _years_axis(ax, [str(y) for y in years], 3)
    ax.legend(loc="upper left")
    ax = axes[1]
    ax.bar(x, [100 * r["rate"] for r in rec], color=[BINDING[r["binding"]] for r in rec], width=0.75)
    for k, label in (("cpi", "Set by CPI"), ("earnings", "Set by earnings"), ("floor", f"Set by the {D.FLOOR_TEXT} floor")):
        ax.bar([0], [0], color=BINDING[k], label=label)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The April rise")
    _years_axis(ax, [str(y) for y in years], 3)
    ax.legend(loc="upper left")
    ax = axes[2]
    xs = [years[0] - 1, *years]
    for key, label, color, lw in (("triple_lock", "Triple lock", TL, 2.2), ("earnings", "Earnings alone", EARN, 1.4),
                                  ("cpi", "CPI alone", CPI, 1.4), ("floor", f"{D.FLOOR_TEXT} a year", FLOOR, 1.4)):
        ax.plot(xs, [100, *[100 * r["index"][key] for r in rec]], color=color, lw=lw, label=label)
    ax.set_title(f"Level (before April {years[0]} = 100)")
    ax.xaxis.set_major_locator(MaxNLocator(4, integer=True))
    ax.legend(loc="upper left")
    fig.tight_layout(w_pad=1.2)
    return fig


def past_years():
    """Step 1: the plan started earlier, the ratio of its level to the triple lock's each April."""
    groups = [g for g in D.history_groups() if g["changes"]]
    years = D.HISTORY["years"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6))
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
    _years_axis(ax, [str(y) for y in years], 3)
    ax.legend(loc="upper left")
    ax = axes[1]
    shades = [TL, BP, EARN, LIGHT, CPI]
    for g, c in zip(groups, shades):
        ratio = [g["ratio"][str(y)] for y in years]
        ax.plot(x, [100 * (r - 1) for r in ratio], color=c, lw=1.6, label=f"From {g['label']}")
    ax.axhline(0, color=FLOOR, lw=0.8)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Plan's level against the triple lock's")
    _years_axis(ax, [str(y) for y in years], 3)
    ax.legend(loc="lower left", fontsize=6.5)
    fig.tight_layout(w_pad=1.2)
    return fig


def path_view(pid):
    """Steps 2 and 3: a path's inputs, the rise under each rule, and the levels (2026-27 = 100)."""
    p = D.path(pid)
    rows = D.path_rows(p)
    labels = [str(r["year"]) for r in rows]
    x = list(range(len(rows)))
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    ax = axes[0]
    ax.plot(x, [100 * r["cpi"] for r in rows], color=CPI, lw=1.8, marker="o", ms=2.5, label="September CPI")
    ax.plot(x, [100 * r["earnings"] for r in rows], color=EARN, lw=1.8, marker="o", ms=2.5,
            label="May–July earnings")
    ax.axhline(100 * D.FLOOR, color=FLOOR, ls="--", lw=1, label=D.FLOOR_TEXT)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The inputs, the year before")
    _years_axis(ax, labels, 3)
    ax.legend(loc="best")
    ax = axes[1]
    w = 0.4
    ax.bar([i - w / 2 for i in x], [100 * r["tl_rate"] for r in rows], width=w, color=TL, label="Triple lock")
    ax.bar([i + w / 2 for i in x], [100 * r["bp_rate"] for r in rows], width=w, color=BP, label="Burnham plan")
    ax.axvline(labels.index(str(D.SWITCH)) - 0.5, color=FLOOR, lw=0.8, ls=":")
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("The April rise")
    _years_axis(ax, labels, 3)
    ax.legend(loc="best")
    ax = axes[2]
    base = [D.fy(D.YEARS[0] - 1)]
    lv = {"tl": [100.0], "bp": [100.0], "e": [100.0], "c": [100.0], "f": [100.0]}
    for r in rows:
        lv["tl"].append(lv["tl"][-1] * (1 + r["tl_rate"]))
        lv["bp"].append(lv["bp"][-1] * (1 + r["bp_rate"]))
        lv["e"].append(lv["e"][-1] * (1 + r["earnings"]))
        lv["c"].append(lv["c"][-1] * (1 + r["cpi"]))
        lv["f"].append(lv["f"][-1] * (1 + D.FLOOR))
    xs = list(range(len(rows) + 1))
    ax.plot(xs, lv["tl"], color=TL, lw=2.2, label="Triple lock")
    ax.plot(xs, lv["bp"], color=BP, lw=2.2, label="Burnham plan")
    ax.plot(xs, lv["e"], color=EARN, lw=1.2, ls="--", label="Earnings alone")
    ax.plot(xs, lv["c"], color=CPI, lw=1.2, ls="--", label="CPI alone")
    ax.plot(xs, lv["f"], color=FLOOR, lw=1.2, ls=":", label=f"{D.FLOOR_TEXT} a year")
    _years_axis(ax, base + [D.fy(r["year"]) for r in rows], 4)
    ax.set_title(f"Level ({base[0]} = 100)")
    ax.legend(loc="upper left")
    fig.tight_layout(w_pad=1.2)
    return fig


PATH_STYLE = {"central": (CPI, "--"), "random": (BP, "-"), "monthly_p50": (TL, "-"), "monthly_p90": (EARN, "-")}


def gaps():
    """Step 3: the weekly gap in the full new State Pension on each path shown (rule arithmetic)."""
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    for pid in D.PATH_IDS:
        p = D.path(pid)
        rows = D.path_rows(p)
        color, ls = PATH_STYLE.get(pid, (CPI, "-"))
        ax.plot([r["year"] for r in rows], [r["tl_weekly"] - r["bp_weekly"] for r in rows], color=color, ls=ls,
                lw=1.8, marker="o", ms=2.5, label=p["label"])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"£{v:g}"))
    ax.set_title("Full new State Pension: triple lock minus Burnham plan, £ a week")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def short_label(meta):
    """A panel title from the example's own fields: 'aged 70, owner, State Pension only'."""
    tenure = {"OWNED_OUTRIGHT": "owns their home", "RENT_FROM_COUNCIL": "council tenant"}.get(meta["tenure"],
                                                                                            meta["tenure"].lower())
    income = f"£{meta['private_pension']:,} private pension" if meta["private_pension"] else "State Pension only"
    return f"Aged {meta['age']}, {tenure}, {income}"


def pensioners(pid):
    """Step 4: each example pensioner's change in State Pension and in income, each year, on a path."""
    p = D.path(pid)
    exs = D.examples(p)
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.4), sharex=True)
    for ax, letter, (key, ex) in zip(axes.flat, "abcd", exs.items()):
        sp = [D.ex_change(ex, "state_pension", y) for y in D.YEARS]
        net = [D.ex_change(ex, "net_income", y) for y in D.YEARS]
        ax.bar(D.YEARS, sp, color=BP, width=0.7, label="Change in State Pension")
        ax.plot(D.YEARS, net, color=TL, lw=1.8, marker="o", ms=2.5, label="Change in income after tax and benefits")
        ax.axhline(0, color=FLOOR, lw=0.8)
        ax.yaxis.set_major_formatter(GBP)
        ax.set_title(f"({letter}) {short_label(ex['meta'])}", fontsize=7.5)
        ax.xaxis.set_major_locator(MaxNLocator(5, integer=True))
    axes.flat[0].legend(loc="lower left", fontsize=6.5)
    fig.tight_layout(h_pad=1.0)
    return fig


def savings(pid):
    """Step 5: gross and net saving each year on a path (full runs)."""
    p = D.path(pid)
    rows = D.path_rows(p)
    x = [r["year"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    w = 0.4
    ax.bar([v - w / 2 for v in x], [r["gross"] for r in rows], width=w, color=BP, label="Gross (State Pension spending)")
    ax.bar([v + w / 2 for v in x], [r["net"] for r in rows], width=w, color=LIGHT, label="Net of tax and other benefits")
    ax.axhline(0, color=FLOOR, lw=0.8)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title(f"Saving each year: {p['label'].lower()}")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def expected():
    """Step 6: the expected saving, gross and net, with 1.96 Monte Carlo standard errors; the central path's gross."""
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ys = D.YEARS
    for out, color, label in (("gross", TL, "Expected saving, gross"), ("net", EARN, "Expected saving, net")):
        m = [D.est(out, y)["mean"] for y in ys]
        s = [D.est(out, y)["se"] for y in ys]
        ax.fill_between(ys, [a - 1.96 * b for a, b in zip(m, s)], [a + 1.96 * b for a, b in zip(m, s)], color=color,
                        alpha=0.18, lw=0)
        ax.plot(ys, m, color=color, lw=2, label=label)
    central = D.path_rows(D.path("central"))
    ax.plot(ys, [r["gross"] for r in central], color=CPI, lw=1.4, ls="--", label="Central forecast alone, gross")
    ax.axhline(0, color=FLOOR, lw=0.8)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Saving by fiscal year (named by its first year); shading: ±1.96 Monte Carlo standard errors")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def runs():
    """Step 6: every full run's 2039-40 saving against its weekly gap (one point per run)."""
    fy = str(D.FINAL)
    pts = [(p["gap_2039_gbp_week"], p["outputs"]["primary"]["gross"][fy], p["outputs"]["primary"]["net"][fy])
           for p in D.EV["paths"]]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.scatter([a for a, _, _ in pts], [b for _, b, _ in pts], s=9, color=TL, alpha=0.8, label="Gross saving", lw=0)
    ax.scatter([a for a, _, _ in pts], [c for _, _, c in pts], s=9, color=EARN, alpha=0.8, label="Net saving", lw=0)
    ax.yaxis.set_major_formatter(BN)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"£{v:g}"))
    ax.set_xlabel(f"Gap in the full new State Pension, {D.fy(D.FINAL)}, £ a week")
    ax.set_title(f"Every full run on the Enhanced FRS: saving in {D.fy(D.FINAL)}")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig
