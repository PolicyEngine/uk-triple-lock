"""Figures for the working paper, drawn from paperdata (data/results.json).

Each function draws one figure and returns it; the manuscript's code cells call them. The template (type, chrome,
sizes, legends) is plotstyle's, modelled on the uk-ai-study paper; the colours are the dashboard's, one per thing and
the same in every figure: the triple lock darkest teal, the Burnham plan mid teal, gross saving dark teal and net
saving light teal, CPI amber, earnings dark teal, the 2.5% floor pale grey. Units sit in the axis labels.
"""

import sys

import matplotlib

if "ipykernel" not in sys.modules:  # outside the manuscript's kernel: draw off screen
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

import paperdata as D  # noqa: E402
import plotstyle as S  # noqa: E402

S.apply_style()

BINDING = {"cpi": S.CPI, "earnings": S.EARN, "floor": S.FLOOR}
# The Burnham plan's bars: hatched in its own teal on white, beside the triple lock's solid darkest teal, so the two
# rules stay apart in print and in greyscale.
PLAN_BAR = {"color": "white", "edgecolor": S.BP, "hatch": "//////", "linewidth": 0.8}
NUM = S._signed(lambda a: f"{a:g}")  # plain numbers with a true minus; the unit is in the axis label


def _fy_axis(ax, years, every=3):
    """Fiscal years on x, labelled '2030-31' every few years and at the last."""
    ticks = [y for i, y in enumerate(years) if i % every == 0 or y == years[-1]]
    if len(ticks) > 1 and ticks[-1] - ticks[-2] < every:
        ticks.pop(-2)
    ax.set_xticks(ticks)
    ax.set_xticklabels([D.fy(y) for y in ticks])
    ax.set_xlim(years[0] - 0.6, years[-1] + 0.6)


def _april_axis(ax, years, every=3, base=False):
    """Categorical x axis of April rises at 0..n-1 (and the level before the first at -1 when ``base``)."""
    ticks = [i for i in range(len(years)) if i % every == 0 or i == len(years) - 1]
    if len(ticks) > 1 and ticks[-1] - ticks[-2] < every:
        ticks.pop(-2)
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(years[i]) for i in ticks])
    ax.set_xlim(-1.6 if base else -0.7, len(years) - 0.3)
    ax.grid(axis="x", visible=False)


def _inputs(ax, years, cpi, earnings, every=3):
    x = range(len(years))
    ax.axhline(100 * D.FLOOR, color=S.FLOOR, ls="--", lw=1.2, label=f"{D.FLOOR_TEXT} floor")
    ax.plot(x, [100 * v for v in cpi], color=S.CPI, lw=1.6, marker="o", ms=2.6, label="CPI (September)")
    ax.plot(x, [100 * v for v in earnings], color=S.EARN, lw=1.6, marker="s", ms=2.4, label="Earnings (May–July)")
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Growth, year before (%)")
    ax.set_title("Inputs")
    _april_axis(ax, years, every)


def _levels(ax, years, series, title, every=3):
    """Cumulative levels from rates: series = [(label, rates, colour, width, style)], level before the first = 100."""
    xs = list(range(-1, len(years)))
    for label, rates, color, lw, ls in series:
        level = [100.0]
        for r in rates:
            level.append(level[-1] * (1 + r))
        ax.plot(xs, level, color=color, lw=lw, ls=ls, label=label)
    ax.set_ylabel(f"Index (before April {years[0]} = 100)")
    ax.set_title(title)
    _april_axis(ax, years, every, base=True)


def _three_panels():
    return plt.subplots(1, 3, figsize=S.PANELS)


def history():
    """Step 1: the inputs, the rise and what set it, and the cumulative index, April 2011-2026."""
    rec = D.tl_record()
    years = [r["year"] for r in rec]
    x = range(len(years))
    fig, axes = _three_panels()
    _inputs(axes[0], years, [r["cpi"] for r in rec], [r["earnings"] for r in rec], every=5)
    ax = axes[1]
    rpi = [r["year"] == D.HISTORY_RPI_YEAR for r in rec]
    ax.bar(x, [100 * r["paid"] for r in rec], color=[S.MUTED if q else BINDING[r["binding"]] for q, r in zip(rpi, rec)],
           width=0.72)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Rise paid in April (%)")
    ax.set_title("Rise paid")
    _april_axis(ax, years, 5)
    _levels(axes[2], years, [
        ("Triple lock as paid", [r["paid"] for r in rec], S.TL, 2.0, "-"),
        ("Earnings alone", [r["earnings"] for r in rec], S.EARN, 1.3, "--"),
        ("CPI alone", [r["cpi"] for r in rec], S.CPI, 1.3, ":"),
        (f"{D.FLOOR_TEXT} a year", [D.FLOOR] * len(rec), S.FLOOR, 1.3, "-."),
    ], "Level", every=5)
    fig.tight_layout(w_pad=1.2)
    bars = [Patch(color=BINDING[k], label=label) for k, label in
            (("cpi", "Set by CPI"), ("earnings", "Set by earnings"), ("floor", "Set by the floor"))]
    bars.append(Patch(color=S.MUTED, label=f"Set by RPI ({D.HISTORY_RPI_YEAR})"))
    S.fig_legend(fig, (axes[0], axes[2]), ncol=4, y=-0.01, extra=bars, order=[
        "CPI (September)", "Earnings (May–July)", f"{D.FLOOR_TEXT} floor", "Triple lock as paid", "Set by CPI",
        "Set by earnings", "Set by the floor", f"Set by RPI ({D.HISTORY_RPI_YEAR})"])
    return fig


def past_years():
    """Step 1: the plan started earlier: the rises, and the ratio of its level to the triple lock's each April."""
    groups = [g for g in D.history_groups() if g["changes"]]
    years = D.HISTORY["years"]
    fig, axes = plt.subplots(1, 2, figsize=(S.TEXTWIDTH, 3.0))
    first = groups[0]
    x = list(range(len(years)))
    w = 0.4
    ax = axes[0]
    ax.bar([i - w / 2 for i in x], [100 * first["tl_rate"][str(y)] for y in years], width=w, color=S.TL,
           label="Triple lock (replayed on today's figures)")
    ax.bar([i + w / 2 for i in x], [100 * first["bp_rate"][str(y)] for y in years], width=w, **PLAN_BAR,
           label=f"Burnham plan from {first['label']}")
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Rise in April (%)")
    ax.set_title("April rises")
    _april_axis(ax, years)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1)
    ax = axes[1]
    shades = [S.EARN, S.GAIN, S.BAND_INNER, S.NET, S.BAND_OUTER]  # a teal ramp, darkest for the earliest start
    for g, c in zip(groups, shades):
        ax.plot(x, [100 * (g["ratio"][str(y)] - 1) for y in years], color=c, lw=1.6, label=f"From {g['label']}")
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Plan vs triple lock (%)")
    ax.set_title("Plan against triple lock, by start")
    _april_axis(ax, years)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1)
    fig.tight_layout(w_pad=2.0)
    return fig


def path_view(pid):
    """Steps 2 and 3: a path's inputs, the rise under each rule, and the levels."""
    p = D.path(pid)
    rows = D.path_rows(p)
    years = [r["year"] for r in rows]
    x = list(range(len(rows)))
    fig, axes = _three_panels()
    _inputs(axes[0], years, [r["cpi"] for r in rows], [r["earnings"] for r in rows])
    ax = axes[1]
    w = 0.4
    ax.bar([i - w / 2 for i in x], [100 * r["tl_rate"] for r in rows], width=w, color=S.TL, label="Triple lock")
    ax.bar([i + w / 2 for i in x], [100 * r["bp_rate"] for r in rows], width=w, **PLAN_BAR, label="Burnham plan")
    ax.axvline(years.index(D.SWITCH) - 0.5, color=S.MUTED, lw=0.8, ls=":")
    top = ax.get_ylim()[1]
    ax.set_ylim(top=top * 1.14)
    ax.text(years.index(D.SWITCH) - 0.3, top * 1.13, f"Plan from April {D.SWITCH}", fontsize=7.5, color=S.MUTED,
            va="top", ha="left")
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Rise in April (%)")
    ax.set_title("April rise")
    _april_axis(ax, years)
    ax = axes[2]
    ax.plot(x, [D.gap_pct(r) for r in rows], color=S.BP, lw=1.8, marker="o", ms=2.6)
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Plan below triple lock (%)")
    ax.set_title("Gap in the pension's level")
    _april_axis(ax, years)
    fig.tight_layout(w_pad=1.2)
    S.fig_legend(fig, (axes[0], axes[1]), ncol=5, y=-0.01, order=[
        "CPI (September)", "Earnings (May–July)", f"{D.FLOOR_TEXT} floor", "Triple lock", "Burnham plan"])
    return fig


PATH_STYLE = {"central": (S.CENTRAL, "--"), "monthly_p50": ("#4B5563", "-"), "monthly_p90": (S.INK, "-")}
SHOWN_PATHS = ["central", "monthly_p50", "monthly_p90"]  # the random example path is left out (near zero, says little)
PATH_SHORT = {"central": "OBR central forecast", "random": "Example path", "monthly_p50": "Typical path",
              "monthly_p90": "High-saving path"}


def gaps():
    """Step 3: the yearly gap in the full new State Pension on each path shown (rule arithmetic)."""
    fig, ax = plt.subplots(figsize=S.WIDE)
    ends = []
    for pid in SHOWN_PATHS:
        rows = D.path_rows(D.path(pid))
        color, ls = PATH_STYLE[pid]
        y = [52 * (r["tl_weekly"] - r["bp_weekly"]) for r in rows]
        years = [r["year"] for r in rows]
        ax.plot(years, y, color=color, ls=ls, lw=1.8, marker="o", ms=2.6)
        ends.append((y[-1], PATH_SHORT.get(pid, pid), color))
    lo, hi = ax.get_ylim()
    S.end_labels(ax, ends, years[-1] + 0.4, 0.075 * (hi - lo))
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("Triple lock minus plan (£ a year)")
    _fy_axis(ax, years)
    ax.set_xlim(right=years[-1] + 3.0)
    ax.spines["bottom"].set_bounds(years[0] - 0.6, years[-1] + 0.6)
    ax.set_xlabel("Fiscal year")
    fig.tight_layout()
    return fig


def short_label(meta):
    """A panel title from the example's own fields: 'Aged 70, owns home, State Pension only'."""
    tenure = {"OWNED_OUTRIGHT": "owns home", "RENT_FROM_COUNCIL": "council tenant"}.get(meta["tenure"],
                                                                                      meta["tenure"].lower())
    income = f"£{meta['private_pension']:,} private pension" if meta["private_pension"] else "State Pension only"
    return f"Aged {meta['age']}, {tenure}, {income}"


def pensioners(pid):
    """Step 4: each example pensioner's change in State Pension and in income, each year, on a path."""
    exs = D.examples(D.path(pid))
    fig, axes = plt.subplots(2, 2, figsize=S.GRID2, sharex=True, sharey=True)
    for ax, letter, (key, ex) in zip(axes.flat, "abcd", exs.items()):
        sp = [D.ex_change(ex, "state_pension", y) for y in D.YEARS]
        net = [D.ex_change(ex, "net_income", y) for y in D.YEARS]
        ax.bar(D.YEARS, sp, color=S.BP, width=0.7, label="Change in State Pension")
        ax.plot(D.YEARS, net, color=S.TL, lw=1.6, marker="o", ms=2.6,
                label="Change in income after tax and benefits")
        S.zero_line(ax)
        ax.yaxis.set_major_formatter(NUM)
        ax.set_title(f"({letter}) {short_label(ex['meta'])}", fontsize=S.PANEL_TITLE)
        ax.grid(axis="x", visible=False)
        _fy_axis(ax, D.YEARS, every=4)
    lo, hi = axes[0, 0].get_ylim()
    axes[0, 0].set_ylim(lo, max(hi, 0) + 0.06 * (hi - lo))
    for ax in axes[:, 0]:
        ax.set_ylabel("Change (£ a year)")
    for ax in axes[1]:
        ax.set_xlabel("Fiscal year")
    fig.tight_layout(h_pad=1.2, w_pad=2.2)
    S.fig_legend(fig, axes.flat, ncol=2, y=0.0, order=["Change in State Pension"])
    return fig


def savings(pid):
    """Step 5: gross and net saving each year on a path (full runs)."""
    rows = D.path_rows(D.path(pid))
    x = [r["year"] for r in rows]
    fig, ax = plt.subplots(figsize=S.WIDE)
    w = 0.4
    ax.bar([v - w / 2 for v in x], [r["gross"] for r in rows], width=w, color=S.GROSS,
           label="Gross (State Pension spending)")
    ax.bar([v + w / 2 for v in x], [r["net"] for r in rows], width=w, color=S.NET, label="Net of tax and benefits")
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Saving (£ billion)")
    ax.grid(axis="x", visible=False)
    _fy_axis(ax, x)
    ax.set_xlabel("Fiscal year")
    S.legend_below(ax, 2, y=-0.28)
    fig.tight_layout()
    return fig


def expected():
    """Step 6: the expected saving, gross and net, with 1.96 Monte Carlo standard errors; the central path's gross."""
    fig, ax = plt.subplots(figsize=S.WIDE)
    ys = D.YEARS
    for out, color, label in (("gross", S.GROSS, "Expected saving, gross"), ("net", S.NET, "Expected saving, net")):
        m = [D.est(out, y)["mean"] for y in ys]
        s = [D.est(out, y)["se"] for y in ys]
        ax.fill_between(ys, [a - 1.96 * b for a, b in zip(m, s)], [a + 1.96 * b for a, b in zip(m, s)], color=color,
                        alpha=0.25, lw=0)
        ax.plot(ys, m, color=color, lw=2.0, label=label)
    central = D.path_rows(D.path("central"))
    ax.plot(ys, [r["gross"] for r in central], color=S.CENTRAL, lw=1.4, ls="--", label="OBR central forecast, gross")
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Saving (£ billion)")
    _fy_axis(ax, ys)
    ax.set_xlabel("Fiscal year")
    S.legend_below(ax, 3, y=-0.28)
    fig.tight_layout()
    return fig


def runs():
    """Step 6: every full run's final-year saving against its weekly gap (one point per run)."""
    fy = str(D.FINAL)
    pts = [(p["gap_2039_gbp_week"], p["outputs"]["primary"]["gross"][fy], p["outputs"]["primary"]["net"][fy])
           for p in D.EV["paths"]]
    fig, ax = plt.subplots(figsize=(0.75 * S.TEXTWIDTH, 2.6))
    ax.scatter([a for a, _, _ in pts], [b for _, b, _ in pts], s=12, color=S.GROSS, alpha=0.85, label="Gross saving",
               lw=0)
    ax.scatter([a for a, _, _ in pts], [c for _, _, c in pts], s=12, color=S.NET, alpha=0.9, label="Net saving", lw=0)
    rk = D.reckoner()
    xs = [0, max(a for a, _, _ in pts) * 1.03]
    ax.plot(xs, [rk["gross"]["slope"] * v for v in xs], color=S.GROSS, lw=0.9, ls="--", zorder=1)
    ax.plot(xs, [rk["net"]["slope"] * v for v in xs], color=S.NET, lw=0.9, ls="--", zorder=1)
    ax.yaxis.set_major_formatter(NUM)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel(f"Gap in the full new State Pension, {D.fy(D.FINAL)} (£ a week)")
    ax.set_ylabel(f"Saving, {D.fy(D.FINAL)} (£ billion)")
    S.legend_below(ax, 2, y=-0.22)
    fig.tight_layout()
    return fig


def fan():
    """The saving each year across the paths, as on the dashboard: the average, the median, the middle 50% and 80% of
    paths (weighted full runs), and the OBR central forecast. Gross, in State Pension spending."""
    ys = [y for y in D.YEARS if y >= D.SWITCH]
    q = {k: [D.spread("gross", y, (k,))[0] for y in ys] for k in (0.1, 0.25, 0.5, 0.75, 0.9)}
    mean = [D.est("gross", y)["mean"] for y in ys]
    central = {r["year"]: r["gross"] for r in D.path_rows(D.path("central"))}
    fig, ax = plt.subplots(figsize=S.WIDE)
    ax.fill_between(ys, q[0.1], q[0.9], color=S.BAND_OUTER, alpha=0.6, lw=0, label="Middle 80% of paths")
    ax.fill_between(ys, q[0.25], q[0.75], color=S.BAND_INNER, alpha=0.6, lw=0, label="Middle 50% of paths")
    ax.plot(ys, mean, color=S.AVERAGE, lw=2.0, label="Average across paths")
    ax.plot(ys, q[0.5], color=S.MEDIAN, lw=1.4, ls=":", label="Median across paths, each year")
    ax.plot(ys, [central[y] for y in ys], color=S.CENTRAL, lw=1.4, ls="--", label="OBR central forecast")
    S.zero_line(ax)
    ax.yaxis.set_major_formatter(NUM)
    ax.set_ylabel("Gross saving (£ billion)")
    _fy_axis(ax, ys, every=3)
    ax.set_xlabel("Fiscal year")
    S.legend_below(ax, 3, y=-0.28)
    fig.tight_layout()
    return fig


def scenario_bars():
    """The single scenarios in the final year: gross and net, with 95% Monte Carlo error on the path averages."""
    rows = D.scenarios([D.FINAL])
    fig, ax = plt.subplots(figsize=(S.TEXTWIDTH, 2.6))
    names = [r["name"] for r in rows][::-1]
    vals = [r["values"][D.FINAL] for r in rows][::-1]
    y = list(range(len(rows)))
    h = 0.36
    err = {"ecolor": S.ERROR, "lw": 0.9, "capsize": 2.5}
    gross = [v[0] for v in vals]
    net = [v[1] for v in vals]
    ax.barh([i + h / 2 for i in y], gross, height=h, color=S.GROSS, label="Gross (State Pension spending)",
            xerr=[1.96 * v[2] if v[2] else 0 for v in vals], error_kw=err)
    ax.barh([i - h / 2 for i in y], net, height=h, color=S.NET, label="Net of tax and benefits",
            xerr=[1.96 * v[3] if v[3] else 0 for v in vals], error_kw=err)
    ax.set_yticks(y)
    ax.set_yticklabels(names, color=S.INK2)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_formatter(NUM)
    ax.set_xlabel(f"Saving in {D.fy(D.FINAL)} (£ billion)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(gross) * 1.12)
    # Value labels past the whisker, so they never sit on it.
    for i, v in enumerate(vals):
        for k, off in ((0, h / 2), (1, -h / 2)):
            end = v[k] + (1.96 * v[k + 2] if v[k + 2] else 0)
            ax.text(end + 0.01 * ax.get_xlim()[1], i + off, f"{v[k]:.1f}", va="center", ha="left", fontsize=8,
                    color=S.INK2)
    S.legend_below(ax, 2, y=-0.24)
    fig.tight_layout()
    return fig


def deciles(pid):
    """The change in household income by income decile on a path in the final year, % of income."""
    rows = D.path(pid)["distribution"][str(D.FINAL)]["by_decile"]
    fig, ax = plt.subplots(figsize=S.SINGLE)
    x = [r["decile"] for r in rows]
    y = [r["pct_income_change"] for r in rows]
    ax.bar(x, y, color=S.BP, width=0.7)
    S.zero_line(ax)
    lo = min(min(y), 0)
    hi = max(max(y), 0)
    span = hi - lo
    ax.set_ylim(lo - 0.14 * span, hi + 0.06 * span)
    S.bar_labels(ax, x, y, lambda v: ("−" if v < 0 else "") + f"{abs(v):.2f}")
    ax.set_xticks(x)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Income decile (1 = lowest income)")
    ax.set_ylabel("Change in household income (%)")
    ax.yaxis.set_major_formatter(NUM)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    fig.tight_layout()
    return fig
