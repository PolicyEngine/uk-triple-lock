"""Figures for the working paper, drawn from paperdata (data/results.json) with Plotly Express.

Each function builds one figure, registers it in ``FIGS`` (the build exports the figures a chunk registers) and
returns it; the manuscript's code cells call them. The look is PolicyEngine's, as on the dashboard (plotstyle): Inter
type, gray tick labels, a light grid, legends under the plot and the PolicyEngine logo. Colours are the dashboard's,
one per thing and the same in every figure: the triple lock darkest teal, the Burnham plan mid teal, gross saving
dark teal and net saving light teal, CPI amber, earnings dark teal, the 2.5% floor pale grey. Units sit in the axis
titles. Single-panel figures carry no title (the caption is the title); panels carry a short label.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import paperdata as D
import plotstyle as S

FIGS = []  # figures built since the build last cleared it

BINDING = {"cpi": S.CPI, "earnings": S.EARN, "floor": S.FLOOR}
BINDING_NAME = {"cpi": "Set by CPI", "earnings": "Set by earnings", "floor": f"Set by the {D.FLOOR_TEXT} floor"}
PATH_STYLE = {"central": (S.CENTRAL, "dash"), "monthly_p50": ("#4B5563", "solid"), "monthly_p90": (S.INK, "solid")}
SHOWN_PATHS = ["central", "monthly_p50", "monthly_p90"]  # the random example path is left out (near zero, says little)
PATH_SHORT = {"central": "OBR central forecast", "random": "Example path", "monthly_p50": "Typical path",
              "monthly_p90": "High-saving path"}


def _done(fig):
    FIGS.append(fig)
    return fig


def _add(fig, pxfig, row=None, col=None, showlegend=True):
    """Move a Plotly Express figure's traces into a panel of a subplot figure."""
    for tr in pxfig.data:
        tr.showlegend = showlegend and tr.showlegend is not False
        fig.add_trace(tr, row=row, col=col)


def _inputs_px(years, cpi, earnings, legend=True):
    """Inputs behind each April's rise: CPI, earnings and the floor, as % lines on an April axis."""
    df = pd.DataFrame({"April": years * 2, "value": [100 * v for v in cpi] + [100 * v for v in earnings],
                       "series": ["CPI (September)"] * len(years) + ["Earnings (May–July)"] * len(years)})
    f = px.line(df, x="April", y="value", color="series", markers=True,
                color_discrete_map={"CPI (September)": S.CPI, "Earnings (May–July)": S.EARN})
    f.update_traces(line=dict(width=2), marker=dict(size=4))
    f.add_trace(go.Scatter(x=[years[0], years[-1]], y=[100 * D.FLOOR] * 2, mode="lines", name=f"{D.FLOOR_TEXT} floor",
                           line=dict(color=S.FLOOR, width=1.5, dash="dash"), showlegend=legend))
    return f


def _levels_px(years, series):
    """Cumulative levels from rates, level before the first April = 100. series = [(label, rates, colour, dash)]."""
    rows = []
    xs = [years[0] - 1] + list(years)
    for label, rates, color, dash in series:
        level = [100.0]
        for r in rates:
            level.append(level[-1] * (1 + r))
        rows += [{"April": x, "Index": v, "series": label} for x, v in zip(xs, level)]
    f = px.line(pd.DataFrame(rows), x="April", y="Index", color="series",
                color_discrete_map={label: c for label, _, c, _ in series},
                line_dash="series", line_dash_map={label: d for label, _, _, d in series})
    f.update_traces(line=dict(width=2))
    f.for_each_trace(lambda t: t.update(line=dict(width=3 if t.name.startswith("Triple lock") else 1.6)))
    return f


def history():
    """Step 1: the inputs, the rise and what set it, and the cumulative index, April 2011-2026."""
    rec = D.tl_record()
    years = [r["year"] for r in rec]
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Inputs", "Rise paid", "Level"), horizontal_spacing=0.09)
    _add(fig, _inputs_px(years, [r["cpi"] for r in rec], [r["earnings"] for r in rec]), 1, 1)
    bars = pd.DataFrame({"April": years, "Rise": [100 * r["paid"] for r in rec],
                         "set": ["Set by RPI" if r["year"] == D.HISTORY_RPI_YEAR else BINDING_NAME[r["binding"]]
                                 for r in rec]})
    cmap = {BINDING_NAME[k]: c for k, c in BINDING.items()} | {"Set by RPI": "#4B5563"}
    _add(fig, px.bar(bars, x="April", y="Rise", color="set", color_discrete_map=cmap), 1, 2)
    _add(fig, _levels_px(years, [
        ("Triple lock as paid", [r["paid"] for r in rec], S.TL, "solid"),
        ("Earnings alone", [r["earnings"] for r in rec], S.EARN, "dash"),
        ("CPI alone", [r["cpi"] for r in rec], S.CPI, "dot"),
        (f"Floor alone ({D.FLOOR_TEXT} a year)", [D.FLOOR] * len(rec), S.FLOOR, "dashdot"),
    ]), 1, 3)
    t, lab = S.year_ticks(years, 5)
    fig.update_xaxes(tickvals=t, ticktext=lab, range=[years[0] - 1.3, years[-1] + 0.7])
    fig.update_yaxes(title_text="Growth, year before (%)", row=1, col=1)
    fig.update_yaxes(title_text="Rise paid in April (%)", row=1, col=2)
    fig.update_yaxes(title_text=f"Index (before April {years[0]} = 100)", row=1, col=3)
    fig.update_layout(barmode="overlay")
    return _done(S.finish(fig, S.PANELS_H + 40, legend_y=-0.22))


def past_years():
    """Step 1: the plan started earlier: the rises, and the plan's level against the triple lock's, by start year."""
    groups = [g for g in D.history_groups() if g["changes"]]
    years = D.HISTORY["years"]
    first = groups[0]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("April rises", "Plan against triple lock, by start"),
                        horizontal_spacing=0.12)
    tl_name, bp_name = "Triple lock (replayed on today's figures)", f"Burnham plan from {first['label']}"
    bars = pd.DataFrame({"April": years * 2,
                         "Rise": [100 * first["tl_rate"][str(y)] for y in years]
                         + [100 * first["bp_rate"][str(y)] for y in years],
                         "rule": [tl_name] * len(years) + [bp_name] * len(years)})
    _add(fig, px.bar(bars, x="April", y="Rise", color="rule", barmode="group",
                     color_discrete_map={tl_name: S.TL, bp_name: S.BP}), 1, 1)
    rows = []
    for g in groups:
        sy = g["switch_years"]
        name = f"From {sy[0]}–{sy[-1]}" if len(sy) > 1 and sy[-1] - sy[0] == len(sy) - 1 else f"From {sy[0]}"
        rows += [{"April": y, "gap": 100 * (g["ratio"][str(y)] - 1), "start": name} for y in years]
    lines = px.line(pd.DataFrame(rows), x="April", y="gap", color="start", color_discrete_sequence=S.RAMP)
    lines.update_traces(line=dict(width=2))
    _add(fig, lines, 1, 2)
    S.zero_line(fig, 1, 2)
    t, lab = S.year_ticks(years, 5)
    fig.update_xaxes(tickvals=t, ticktext=lab, range=[years[0] - 0.7, years[-1] + 0.7])
    fig.update_yaxes(title_text="Rise in April (%)", row=1, col=1)
    fig.update_yaxes(title_text="Plan vs triple lock (%)", row=1, col=2)
    fig.update_layout(bargap=0.2)
    return _done(S.finish(fig, S.PANELS_H + 60, legend_y=-0.22))


def path_view(pid):
    """Steps 2 and 3: a path's inputs, the rise under each rule, and the gap in the pension's level."""
    rows = D.path_rows(D.path(pid))
    years = [r["year"] for r in rows]
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Inputs", "April rise", "Gap in the pension's level"),
                        horizontal_spacing=0.09)
    _add(fig, _inputs_px(years, [r["cpi"] for r in rows], [r["earnings"] for r in rows]), 1, 1)
    bars = pd.DataFrame({"April": years * 2, "Rise": [100 * r["tl_rate"] for r in rows]
                         + [100 * r["bp_rate"] for r in rows],
                         "rule": ["Triple lock"] * len(rows) + ["Burnham plan"] * len(rows)})
    _add(fig, px.bar(bars, x="April", y="Rise", color="rule", barmode="group",
                     color_discrete_map={"Triple lock": S.TL, "Burnham plan": S.BP}), 1, 2)
    fig.add_vline(x=D.SWITCH - 0.5, line=dict(color=S.MUTED, width=1, dash="dot"), row=1, col=2)
    top = max(max(100 * r["tl_rate"], 100 * r["bp_rate"]) for r in rows)
    fig.update_yaxes(range=[0, top * 1.2], row=1, col=2)
    fig.add_annotation(x=D.SWITCH - 0.3, y=1, yref="y2 domain", xref="x2", text=f"Plan from April {D.SWITCH}",
                       showarrow=False, xanchor="left", yanchor="top", font=dict(size=10, color=S.MUTED))
    gap = px.line(x=years, y=[D.gap_pct(r) for r in rows], markers=True)
    gap.update_traces(line=dict(color=S.BP, width=2), marker=dict(size=4), showlegend=False)
    _add(fig, gap, 1, 3, showlegend=False)
    S.zero_line(fig, 1, 3)
    t, lab = S.year_ticks(years, 3)
    fig.update_xaxes(tickvals=t, ticktext=lab, range=[years[0] - 0.7, years[-1] + 0.7])
    fig.update_yaxes(title_text="Growth, year before (%)", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Rise in April (%)", row=1, col=2)
    fig.update_yaxes(title_text="Plan below triple lock (%)", row=1, col=3)
    fig.update_layout(bargap=0.2)
    return _done(S.finish(fig, S.PANELS_H + 40, legend_y=-0.22))


def gaps():
    """Step 3: the yearly gap in the full new State Pension on each path shown (rule arithmetic)."""
    rows = []
    for pid in SHOWN_PATHS:
        for r in D.path_rows(D.path(pid)):
            rows.append({"year": r["year"], "gap": 52 * (r["tl_weekly"] - r["bp_weekly"]), "path": PATH_SHORT[pid]})
    df = pd.DataFrame(rows)
    fig = px.line(df, x="year", y="gap", color="path", markers=True, line_dash="path",
                  color_discrete_map={PATH_SHORT[p]: PATH_STYLE[p][0] for p in SHOWN_PATHS},
                  line_dash_map={PATH_SHORT[p]: PATH_STYLE[p][1] for p in SHOWN_PATHS})
    fig.update_traces(line=dict(width=2), marker=dict(size=4))
    S.zero_line(fig)
    years = sorted(df["year"].unique())
    t, lab = S.fy_ticks(years)
    fig.update_xaxes(tickvals=t, ticktext=lab, title_text="Fiscal year", range=[years[0] - 0.4, years[-1] + 0.4])
    fig.update_yaxes(title_text="Triple lock minus plan (£ a year)", tickformat=",.0f", tickprefix="£")
    return _done(S.finish(fig, S.WIDE_H + 20, legend_y=-0.28))


def short_label(meta):
    """A panel title from the example's own fields: 'Aged 70, owns home, State Pension only'."""
    tenure = {"OWNED_OUTRIGHT": "owns home", "RENT_FROM_COUNCIL": "council tenant"}.get(meta["tenure"],
                                                                                      meta["tenure"].lower())
    income = f"£{meta['private_pension']:,} private pension" if meta["private_pension"] else "State Pension only"
    return f"Aged {meta['age']}, {tenure}, {income}"


def pensioners(pid):
    """Step 4: each example pensioner's change in State Pension and in income, each year, on a path."""
    exs = D.examples(D.path(pid))
    titles = [f"({l}) {short_label(ex['meta'])}" for l, ex in zip("abcd", exs.values())]
    fig = make_subplots(rows=2, cols=2, subplot_titles=titles, shared_xaxes=True, shared_yaxes=True,
                        vertical_spacing=0.14, horizontal_spacing=0.06)
    for i, ex in enumerate(exs.values()):
        r, c = divmod(i, 2)
        sp = px.bar(x=D.YEARS, y=[D.ex_change(ex, "state_pension", y) for y in D.YEARS])
        sp.update_traces(marker_color=S.BP, name="Change in State Pension", showlegend=i == 0)
        net = px.line(x=D.YEARS, y=[D.ex_change(ex, "net_income", y) for y in D.YEARS], markers=True)
        net.update_traces(line=dict(color=S.TL, width=2), marker=dict(size=4),
                          name="Change in income after tax and benefits", showlegend=i == 0)
        _add(fig, sp, r + 1, c + 1, showlegend=i == 0)
        _add(fig, net, r + 1, c + 1, showlegend=i == 0)
        S.zero_line(fig, r + 1, c + 1)
    t, lab = S.fy_ticks(D.YEARS, 4)
    fig.update_xaxes(tickvals=t, ticktext=lab)
    fig.update_yaxes(title_text="Change (£ a year)", col=1)
    fig.update_layout(bargap=0.3)
    return _done(S.finish(fig, S.GRID2_H + 40, legend_y=-0.1))


def savings(pid):
    """Step 5: gross and net saving each year on a path (full runs)."""
    rows = D.path_rows(D.path(pid))
    df = pd.DataFrame({"year": [r["year"] for r in rows] * 2, "saving": [r["gross"] for r in rows]
                       + [r["net"] for r in rows],
                       "measure": ["Gross (State Pension spending)"] * len(rows)
                       + ["Net of tax and benefits"] * len(rows)})
    fig = px.bar(df, x="year", y="saving", color="measure", barmode="group",
                 color_discrete_map={"Gross (State Pension spending)": S.GROSS, "Net of tax and benefits": S.NET})
    S.zero_line(fig)
    yrs = sorted(df["year"].unique())
    t, lab = S.fy_ticks(yrs)
    fig.update_xaxes(tickvals=t, ticktext=lab, title_text="Fiscal year", range=[yrs[0] - 0.6, yrs[-1] + 0.6])
    fig.update_yaxes(title_text="Saving", tickprefix="£", ticksuffix="bn")
    return _done(S.finish(fig, S.WIDE_H + 20, legend_y=-0.28))


def expected():
    """Step 6: the expected saving, gross and net, with 1.96 Monte Carlo standard errors; the central path's gross."""
    ys = D.YEARS
    fig = go.Figure()
    for out, color, label in (("gross", S.GROSS, "Expected saving, gross"), ("net", S.NET, "Expected saving, net")):
        m = [D.est(out, y)["mean"] for y in ys]
        s = [D.est(out, y)["se"] for y in ys]
        fig.add_trace(go.Scatter(x=ys + ys[::-1], y=[a + 1.96 * b for a, b in zip(m, s)]
                                 + [a - 1.96 * b for a, b in zip(m, s)][::-1], fill="toself", fillcolor=color,
                                 opacity=0.25, line=dict(width=0), hoverinfo="skip", showlegend=False))
        line = px.line(x=ys, y=m)
        line.update_traces(line=dict(color=color, width=2.5), name=label, showlegend=True)
        _add(fig, line)
    central = px.line(x=ys, y=[r["gross"] for r in D.path_rows(D.path("central"))])
    central.update_traces(line=dict(color=S.CENTRAL, width=1.8, dash="dash"), name="OBR central forecast, gross",
                          showlegend=True)
    _add(fig, central)
    S.zero_line(fig)
    t, lab = S.fy_ticks(ys)
    fig.update_xaxes(tickvals=t, ticktext=lab, title_text="Fiscal year", range=[ys[0] - 0.4, ys[-1] + 0.4])
    fig.update_yaxes(title_text="Saving", tickprefix="£", ticksuffix="bn")
    return _done(S.finish(fig, S.WIDE_H + 20, legend_y=-0.28))


def runs():
    """Step 6: every full run's final-year saving against its weekly gap (one point per run)."""
    fy = str(D.FINAL)
    rows = []
    for p in D.EV["paths"]:
        g = p["gap_2039_gbp_week"]
        rows.append({"gap": g, "saving": p["outputs"]["primary"]["gross"][fy], "measure": "Gross saving"})
        rows.append({"gap": g, "saving": p["outputs"]["primary"]["net"][fy], "measure": "Net saving"})
    df = pd.DataFrame(rows)
    fig = px.scatter(df, x="gap", y="saving", color="measure",
                     color_discrete_map={"Gross saving": S.GROSS, "Net saving": S.NET})
    fig.update_traces(marker=dict(size=6, opacity=0.85, line=dict(width=0)))
    rk = D.reckoner()
    xs = [0, df["gap"].max() * 1.03]
    for key, color in (("gross", S.GROSS), ("net", S.NET)):
        fig.add_trace(go.Scatter(x=xs, y=[rk[key]["slope"] * v for v in xs], mode="lines", showlegend=False,
                                 line=dict(color=color, width=1.2, dash="dash")))
    fig.update_xaxes(title_text=f"Gap in the full new State Pension, {D.fy(D.FINAL)} (£ a week)", showgrid=True)
    fig.update_yaxes(title_text=f"Saving, {D.fy(D.FINAL)}", tickprefix="£", ticksuffix="bn")
    return _done(S.finish(fig, S.SCATTER[1] + 20, width=S.SCATTER[0], legend_y=-0.28))


def fan():
    """The saving each year across the paths, as on the dashboard: the average, the median, the middle 50% and 80% of
    paths (weighted full runs), and the OBR central forecast. Gross, in State Pension spending."""
    ys = [y for y in D.YEARS if y >= D.SWITCH]
    q = {k: [D.spread("gross", y, (k,))[0] for y in ys] for k in (0.1, 0.25, 0.5, 0.75, 0.9)}
    mean = [D.est("gross", y)["mean"] for y in ys]
    central = {r["year"]: r["gross"] for r in D.path_rows(D.path("central"))}
    fig = go.Figure()
    for lo, hi, color, name in ((0.1, 0.9, S.BAND_OUTER, "Middle 80% of paths"),
                                (0.25, 0.75, S.BAND_INNER, "Middle 50% of paths")):
        fig.add_trace(go.Scatter(x=ys + ys[::-1], y=q[hi] + q[lo][::-1], fill="toself", fillcolor=color,
                                 opacity=0.45, line=dict(width=0), name=name, hoverinfo="skip"))
    df = pd.DataFrame({"year": ys * 3, "saving": mean + q[0.5] + [central[y] for y in ys],
                       "series": ["Average across paths"] * len(ys) + ["Median across paths, each year"] * len(ys)
                       + ["OBR central forecast"] * len(ys)})
    lines = px.line(df, x="year", y="saving", color="series", line_dash="series",
                    color_discrete_map={"Average across paths": S.AVERAGE, "Median across paths, each year": S.MEDIAN,
                                        "OBR central forecast": S.CENTRAL},
                    line_dash_map={"Average across paths": "solid", "Median across paths, each year": "dot",
                                   "OBR central forecast": "dash"})
    lines.for_each_trace(lambda t: t.update(line=dict(width=3 if t.name.startswith("Average") else 2)))
    _add(fig, lines)
    t, lab = S.fy_ticks(ys, 3)
    fig.update_xaxes(tickvals=t, ticktext=lab, range=[ys[0] - 0.3, ys[-1] + 0.3])
    fig.update_yaxes(title_text="Gross saving", rangemode="tozero", tickprefix="£", ticksuffix="bn")
    return _done(S.finish(fig, S.WIDE_H + 40, legend_y=-0.18))


def scenario_bars():
    """The single scenarios in the final year: gross and net, with 95% Monte Carlo error on the path averages."""
    rows = D.scenarios([D.FINAL])
    recs = []
    for r in rows:
        g, n, gse, nse = r["values"][D.FINAL]
        recs.append({"scenario": r["name"], "measure": "Gross (State Pension spending)", "saving": g,
                     "err": 1.96 * gse if gse else 0})
        recs.append({"scenario": r["name"], "measure": "Net of tax and benefits", "saving": n,
                     "err": 1.96 * nse if nse else 0})
    df = pd.DataFrame(recs)
    fig = px.bar(df, y="scenario", x="saving", color="measure", orientation="h", barmode="group", error_x="err",
                 text=df["saving"].map(lambda v: f"{v:.1f}"),
                 color_discrete_map={"Gross (State Pension spending)": S.GROSS, "Net of tax and benefits": S.NET},
                 category_orders={"scenario": [r["name"] for r in rows],
                                  "measure": ["Gross (State Pension spending)", "Net of tax and benefits"]})
    fig.update_traces(textposition="outside", textfont=dict(size=10, color=S.INK2), cliponaxis=False,
                      error_x=dict(color=S.ERROR, thickness=1.2, width=3))
    fig.update_yaxes(title_text=None, showgrid=False, autorange="reversed", ticks="")
    fig.update_xaxes(title_text=f"Saving in {D.fy(D.FINAL)}", tickprefix="£", ticksuffix="bn", showgrid=True,
                     range=[0, df["saving"].max() * 1.18])
    return _done(S.finish(fig, S.WIDE_H + 30, legend_y=-0.22))


def deciles(pid):
    """The change in household income by income decile on a path in the final year, % of income."""
    rows = D.path(pid)["distribution"][str(D.FINAL)]["by_decile"]
    df = pd.DataFrame({"decile": [r["decile"] for r in rows], "change": [r["pct_income_change"] for r in rows]})
    fig = px.bar(df, x="decile", y="change", text=df["change"].map(lambda v: S.signed(v, "{:.2f}")))
    fig.update_traces(marker_color=S.BP, textposition="outside", textfont=dict(size=10, color=S.INK2),
                      cliponaxis=False)
    S.zero_line(fig)
    fig.update_xaxes(tickmode="linear", dtick=1, title_text="Income decile, before housing costs (1 = lowest income)")
    fig.update_yaxes(title_text="Change in household income (%)")
    span = df["change"].max() - min(df["change"].min(), 0)
    fig.update_yaxes(range=[min(df["change"].min(), 0) - 0.16 * span, max(df["change"].max(), 0) + 0.06 * span])
    return _done(S.finish(fig, S.SINGLE[1] + 30, width=S.SINGLE[0]))
