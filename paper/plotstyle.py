"""The paper's figure template: the look of the uk-ai-study working paper with the dashboard's colours.

Chrome and type scale follow uk-ai-study (analysis/figstyle.py): a serif face, 10 pt text with 9 pt ticks and
legends, a light grey grid under the data, no top or right spine, frameless legends centred under the axes, and no
title on a single-panel figure (the caption is its title). Series colours are the dashboard's
(dashboard/src/lib/colors.js, SERIES), one colour per concept on every tab and figure.

Unlike uk-ai-study, which draws an 8-inch canvas and shrinks it to 70% of the text width, every figure here is drawn
at the size it prints (the PDF's text width is 6.3 in), so 9 pt type prints at 9 pt.

Presentation only: nothing here reads or changes results.
"""

import glob
import os

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

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

# Ink and chrome (dashboard greys; the roles of uk-ai-study's INK / INK2 / MUTED / GRID / BASELINE).
INK = "#101828"  # titles, direct labels, zero lines: gray-900
INK2 = "#344054"  # axis labels, value labels: gray-700
MUTED = "#6B7280"  # tick labels: gray-500
GRID = "#F2F4F7"  # gridlines: gray-100
BASELINE = "#D1D5DB"  # axis edges: gray-300

# ── Sizes (inches): the PDF's text width is 455.3 pt = 6.3 in ───────────

TEXTWIDTH = 6.3
SINGLE = (0.85 * TEXTWIDTH, 2.9)  # one panel, printed at 85% of the text width
WIDE = (TEXTWIDTH, 2.7)  # one wide panel (year axes), full width
PANELS = (TEXTWIDTH, 2.75)  # two or three panels side by side, full width
GRID2 = (TEXTWIDTH, 4.6)  # a 2 x 2 grid, full width
PANEL_TITLE = 9.5  # a panel's short label in a multi-panel figure

# ── Type: Latin Modern, the PDF's body face, where TeX provides it ──────

_LM_DIRS = [
    os.path.expanduser("~/texlive*/texmf-dist/fonts/opentype/public/lm"),
    "/usr/local/texlive/*/texmf-dist/fonts/opentype/public/lm",
    "/Library/TeX/Root/texmf-dist/fonts/opentype/public/lm",
    "/usr/share/texmf/fonts/opentype/public/lm",
    "/usr/share/texlive/texmf-dist/fonts/opentype/public/lm",
    os.path.expanduser("~/Library/Caches/TectonicProject.Tectonic/bundles/data/*"),
    os.path.expanduser("~/.cache/Tectonic/bundles/data/*"),
]


def _register_latin_modern():
    for pattern in _LM_DIRS:
        for d in glob.glob(pattern):
            files = [os.path.join(d, f"lmroman10-{s}.otf") for s in ("regular", "bold", "italic")]
            if all(os.path.exists(f) for f in files):
                for f in files:
                    fm.fontManager.addfont(f)
                return True
    return False


# Falls back as uk-ai-study does when the first choice is missing.
_SERIF = ["Latin Modern Roman", "Roboto Serif", "Source Serif Pro", "Charter", "DejaVu Serif"]


def apply_style():
    """uk-ai-study's rcParams (figstyle.apply_style), sized for print and with the dashboard's greys."""
    _register_latin_modern()
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": _SERIF,
        "mathtext.fontset": "cm",
        "font.size": 10,
        "axes.titlesize": 10.5,
        "axes.titleweight": "normal",
        "axes.titlecolor": INK,
        "axes.titlelocation": "center",
        "axes.titlepad": 6,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "text.color": INK,
        "axes.labelcolor": INK2,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 0.8,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": MUTED,
        "ytick.labelcolor": MUTED,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.handlelength": 1.8,
        "legend.columnspacing": 1.4,
        "lines.solid_capstyle": "butt",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "figure.dpi": 200,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    })


# ── Number formats (a true minus sign) ───────────────────────────────────


def _signed(fmt):
    return FuncFormatter(lambda v, _: ("−" if v < -1e-12 else "") + fmt(abs(v)))


PCT = _signed(lambda a: f"{a:g}%")
PCT2 = _signed(lambda a: f"{a:.2f}%")
BN = _signed(lambda a: f"£{a:g}bn")
GBP = _signed(lambda a: f"£{a:,.0f}")
WEEK = FuncFormatter(lambda v, _: f"£{v:g}")


# ── Helpers ──────────────────────────────────────────────────────────────


def zero_line(ax):
    """The zero rule, in ink, as uk-ai-study draws it."""
    ax.axhline(0, color=INK, lw=0.8, zorder=2)


def legend_below(ax, ncol, y=-0.16, **kw):
    """A legend centred under the axes: legends never sit on data (uk-ai-study house style)."""
    ax.legend(ncol=ncol, loc="upper center", bbox_to_anchor=(0.5, y), **kw)


def handles_by_label(axes):
    """Each axis's legend entries, each label once, in drawing order."""
    seen = {}
    for ax in axes:
        for h, label in zip(*ax.get_legend_handles_labels()):
            if not label.startswith("_"):
                seen.setdefault(label, h)
    return seen


def fig_legend(fig, axes, ncol, y=0.0, order=None, extra=()):
    """One legend for the whole figure, centred under it, read across the rows. ``order`` lists labels to put
    first; ``extra`` adds handles that no axis draws (for example a colour key for bars)."""
    seen = handles_by_label(axes)
    for h in extra:
        seen[h.get_label()] = h
    labels = [k for k in (order or []) if k in seen] + [k for k in seen if k not in (order or [])]
    # matplotlib fills a legend column by column; reorder so it reads row by row.
    rows = -(-len(labels) // ncol)
    grid = [labels[r * ncol:(r + 1) * ncol] for r in range(rows)]
    labels = [row[c] for c in range(ncol) for row in grid if c < len(row)]
    fig.legend([seen[k] for k in labels], labels, loc="upper center", ncol=ncol, bbox_to_anchor=(0.5, y))


def bar_labels(ax, xs, ys, fmt, horizontal=False, pad=0.015, size=8):
    """Value labels just beyond each bar's end (above or below zero), in INK2."""
    lo, hi = (ax.get_xlim() if horizontal else ax.get_ylim())
    off = pad * (hi - lo)
    for x, y in zip(xs, ys):
        text = fmt(y)
        if horizontal:
            ax.text(y + (off if y >= 0 else -off), x, text, va="center", ha="left" if y >= 0 else "right",
                    fontsize=size, color=INK2)
        else:
            ax.text(x, y + (off if y >= 0 else -off), text, ha="center", va="bottom" if y >= 0 else "top",
                    fontsize=size, color=INK2)


def end_labels(ax, ends, x, min_gap):
    """Direct labels at the right end of lines: ends = [(y, text, colour)], nudged apart by at least min_gap."""
    placed = []
    for y, text, color in sorted(ends):
        pos = y if not placed or y - placed[-1] >= min_gap else placed[-1] + min_gap
        placed.append(pos)
        ax.annotate(text, (x, y), xytext=(x, pos), textcoords="data", xycoords="data", color=color, fontsize=8.5,
                    va="center", ha="left", annotation_clip=False)
