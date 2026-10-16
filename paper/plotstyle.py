"""The paper's figure template: PolicyEngine's Plotly style, matching the dashboard's charts.

The dashboard (dashboard/src) draws its charts in Recharts with the PolicyEngine design tokens: Inter type, gray-500
tick labels at 12 px, a light gray-200 grid, no chart border, legends as a row of swatches under the plot, and the
teal PolicyEngine logo at the bottom right. The series colours are the dashboard's SERIES (dashboard/src/lib/
colors.js), one colour per concept on every tab and every figure here. policyengine-core's own ``format_fig``
predates the teal palette (blue, serif), so this module builds the template from the dashboard instead.

Figures are exported with kaleido at the size they print: the PDF's text width is 6.3 in, 605 CSS px at 96 px/in,
so 12 px type prints at 9 pt and 11 px ticks at 8.25 pt.

Presentation only: nothing here reads or changes results.
"""

import base64
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

# ── Colours: dashboard SERIES (colors.js) ────────────────────────────────

TL = "#1D4044"  # the triple lock (current law): primary-900, darkest teal
BP = "#2C7A7B"  # the Burnham plan: primary-600, mid teal
GROSS = "#234E52"  # gross saving (State Pension spending): primary-800, dark teal
NET = "#4FD1C5"  # net saving (after tax and benefits): primary-300, light teal
EARN = "#285E61"  # earnings growth, or a path that follows earnings alone: primary-700, dark teal
CPI = "#D97706"  # CPI, or a path that follows prices alone: amber
FLOOR = "#9CA3AF"  # the 2.5% floor: gray-400, pale grey (dashed as a line)
BAND_OUTER = "#81E6D9"  # middle 80% of paths: primary-200
BAND_INNER = "#38B2AC"  # middle 50% of paths: primary-400
AVERAGE = TL  # average across paths (solid)
MEDIAN = EARN  # median path (dotted)
CENTRAL = "#6B7280"  # the OBR central forecast: gray-500 (dashed)
OFFSET = "#C9A9A6"  # what shrinks a saving: muted warm
GAIN = "#319795"  # what adds to a saving: primary-500
ERROR = "#1F2937"  # Monte Carlo error whiskers: gray-800
RAMP = ["#1D4044", "#285E61", "#2C7A7B", "#38B2AC", "#4FD1C5"]  # start years, darkest first

INK = "#101828"  # gray-900: zero lines, direct labels
INK2 = "#344054"  # gray-700: axis titles, value labels
MUTED = "#6B7280"  # gray-500: tick labels (AXIS_STYLE)
GRID = "#E2E8F0"  # gray-200 / border.light: gridlines
BASELINE = "#CBD5E1"  # border.medium: axis lines

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

_LOGO = Path(__file__).resolve().parents[1] / "dashboard" / "public" / "assets" / "logos" / "policyengine-teal.png"
LOGO_URI = "data:image/png;base64," + base64.b64encode(_LOGO.read_bytes()).decode() if _LOGO.exists() else None

_axis = dict(
    showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=True, linecolor=BASELINE, linewidth=1,
    ticks="outside", tickcolor=BASELINE, ticklen=4, tickfont=dict(size=TICK, color=MUTED),
    title=dict(font=dict(size=BASE, color=INK2), standoff=6), automargin=True,
)

pio.templates["policyengine"] = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, size=BASE, color=INK2),
    paper_bgcolor="white", plot_bgcolor="white",
    colorway=[TL, BP, NET, CPI, FLOOR],
    xaxis=dict(_axis, showgrid=False),
    yaxis=_axis,
    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.2, yanchor="top", font=dict(size=TICK, color=INK2),
                bgcolor="rgba(0,0,0,0)", itemwidth=30, tracegroupgap=0, title=None),
    margin=dict(l=8, r=8, t=24, b=8),
    hoverlabel=dict(font=dict(family=FONT)),
    bargap=0.25, bargroupgap=0.05,
))
pio.templates.default = "plotly_white+policyengine"


def finish(fig, height, width=WIDTH, legend_y=-0.2, logo=True):
    """Size a figure to its print size, put the legend under it and the PolicyEngine logo at the bottom right."""
    titled = bool(fig.layout.annotations)  # panel labels sit just above the plots
    top = 58 if titled else 34
    legend = any(getattr(t, "showlegend", None) is not False for t in fig.data) and len(fig.data) > 1
    bottom = 28 if legend else 46  # room for the x-axis title when no legend sits under it
    fig.update_layout(width=width, height=height, template="plotly_white+policyengine",
                      margin=dict(l=8, r=8, t=top, b=bottom))
    fig.update_layout(legend=dict(y=legend_y, title_text=""))
    if logo and LOGO_URI:
        # Top right, in the margin above the plots (as small as the dashboard's), clear of every axis and label.
        plot_h = height - top - bottom
        fig.add_layout_image(dict(source=LOGO_URI, xref="paper", yref="paper", x=1, xanchor="right",
                                  y=1 + (top - 4) / plot_h, yanchor="top", sizex=0.13, sizey=16 / plot_h,
                                  opacity=0.85, layer="above"))
    fig.update_annotations(font=dict(size=PANEL_TITLE, color=INK))
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
