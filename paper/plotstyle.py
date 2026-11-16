"""The paper's figure template: PolicyEngine's Plotly style, matching the dashboard's charts.

The dashboard (dashboard/src) draws its charts in Recharts with the PolicyEngine design tokens: Inter type, gray-500
tick labels at 12 px, a light gray-200 grid, no chart border and legends as a row of swatches under the plot. The paper's
figures carry no logo. The series colours come from the
PolicyEngine design tokens (16 November 2026), one colour per concept on every figure. policyengine-core's own ``format_fig``
predates the teal palette (blue, serif), so this module builds the template from the dashboard instead.

Figures are exported with kaleido at the size they print: the PDF's text width is 6.3 in, 605 CSS px at 96 px/in,
so 12 px type prints at 9 pt and 11 px ticks at 8.25 pt.

Presentation only: nothing here reads or changes results.
"""

import plotly.graph_objects as go
import plotly.io as pio

# ── Colours: PolicyEngine design tokens (@policyengine/ui-kit theme.css) ──
# One colour per concept on every figure, from the five chart tokens and the teal and slate scales. The two rules are
# dark blue against teal; the two inputs are blue (CPI) against dark teal (earnings); OBR paths are slate.

TEAL = "#319795"  # --chart-1, teal-500
BLUE = "#0EA5E9"  # --chart-2
DARK_TEAL = "#285E61"  # --chart-3, teal-700
DARK_BLUE = "#026AA2"  # --chart-4
SLATE = "#64748B"  # --chart-5, gray-500

TL = DARK_BLUE  # the triple lock (current law)
BP = TEAL  # the adjusted Triple Lock
GROSS = DARK_TEAL  # gross saving (State Pension spending)
NET = "#4FD1C5"  # net saving (after tax and benefits): teal-300
EARN = DARK_TEAL  # earnings growth, or a path that follows earnings alone
CPI = BLUE  # CPI, or a path that follows prices alone
FLOOR = "#94A3B8"  # the 2.5% floor: slate-400 (dashed as a line)
BAND_OUTER = "#B2F5EA"  # middle 90% of paths: teal-100
BAND_INNER = "#4FD1C5"  # middle 50% of paths: teal-300
AVERAGE = "#234E52"  # median or average across paths: teal-800
MEDIAN = AVERAGE
CENTRAL = SLATE  # the OBR central path (dashed)
WEDGE = "#344054"  # the OBR long-term path: gray-700 (dash-dot)
OFFSET = "#CBD5E1"  # what shrinks a saving: slate-300
GAIN = TEAL  # what adds to a saving
ERROR = "#344054"  # Monte Carlo error whiskers: gray-700
RAMP = ["#1D4044", "#285E61", "#319795", "#4FD1C5", "#81E6D9"]  # start years, teal-900 to teal-200

INK = "#101828"  # gray-900: zero lines, direct labels
INK2 = "#344054"  # gray-700: axis titles, value labels
MUTED = "#64748B"  # gray-500: tick labels
GRID = "#E2E8F0"  # --border: gridlines
BASELINE = "#CBD5E1"  # slate-300: axis lines

FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"

# ── Sizes: CSS px at 96 px/in; the PDF's text width is 6.3 in ───────────

PX_PER_IN = 96
TEXTWIDTH = 6.3
WIDTH = round(TEXTWIDTH * PX_PER_IN)  # 605
WIDE_H = 270  # one wide panel with a legend row
PANELS_H = 300  # two or three panels side by side with a legend
GRID2_H = 430  # a 2 x 2 grid
SCATTER = (round(0.8 * WIDTH), 270)
SINGLE = (round(0.85 * WIDTH), 270)
BASE = 12  # px: body text in the figure (9 pt in print)
TICK = 11  # px: tick labels (8.25 pt)
PANEL_TITLE = 12


_axis = dict(
    showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=True, linecolor=BASELINE, linewidth=1,
    ticks="outside", tickcolor=BASELINE, ticklen=4, tickfont=dict(size=TICK, color=MUTED),
    title=dict(font=dict(size=BASE, color=INK2), standoff=6), automargin=True,
)

pio.templates["policyengine"] = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, size=BASE, color=INK2),
    paper_bgcolor="white", plot_bgcolor="white",
    colorway=[TL, BP, DARK_TEAL, BLUE, SLATE],
    xaxis=dict(_axis, showgrid=False),
    yaxis=_axis,
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.2, yanchor="top", font=dict(size=TICK, color=INK2),
                bgcolor="rgba(0,0,0,0)", itemwidth=30, tracegroupgap=0, title=None),
    margin=dict(l=8, r=8, t=24, b=8),
    hoverlabel=dict(font=dict(family=FONT)),
    bargap=0.25, bargroupgap=0.05,
))
pio.templates.default = "plotly_white+policyengine"


def finish(fig, height, width=WIDTH, legend_y=-0.2):
    """Size a figure to its print size and put the legend under it."""
    titled = bool(fig.layout.annotations)  # panel labels sit just above the plots
    top = 58 if titled else 34
    legend = any(getattr(t, "showlegend", None) is not False for t in fig.data) and len(fig.data) > 1
    bottom = 28 if legend else 46  # room for the x-axis title when no legend sits under it
    fig.update_layout(width=width, height=height, template="plotly_white+policyengine",
                      margin=dict(l=8, r=8, t=top, b=bottom))
    fig.update_layout(legend=dict(y=legend_y, title_text=""))
    fig.update_annotations(font=dict(size=PANEL_TITLE, color=INK))
    for a in fig.layout.annotations:  # panel titles (make_subplots) only are semibold, not labels in the plots
        if a.xref == "paper" and a.yref == "paper" and a.yanchor == "bottom" and a.xanchor == "center":
            a.font.weight = 600
    return fig


def zero_line(fig, row=None, col=None):
    """A thin dark rule at zero, over the grid."""
    fig.add_hline(y=0, line=dict(color=INK, width=1), row=row, col=col)


def fy_ticks(years, every=3):
    """Fiscal-year tick positions and labels ('2030-31'), every few years and the last."""
    ticks = [y for i, y in enumerate(years) if i % every == 0 or y == years[-1]]
    if len(ticks) > 1 and ticks[-1] - ticks[-2] < every:
        ticks.pop(-2)
    return ticks, [f"{y}-{str(y + 1)[-2:]}" for y in ticks]


def year_ticks(years, every=3):
    ticks = [y for i, y in enumerate(years) if i % every == 0 or y == years[-1]]
    if len(ticks) > 1 and ticks[-1] - ticks[-2] < every:
        ticks.pop(-2)
    return ticks, [str(y) for y in ticks]


def signed(v, fmt="{:g}"):
    """A number with a true minus sign."""
    s = fmt.format(abs(v))
    return ("−" if v < 0 else "") + s
