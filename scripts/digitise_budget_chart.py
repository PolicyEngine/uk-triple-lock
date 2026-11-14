"""Digitise Budget 2026 Chart 5.1 (State Pension spending, % of GDP, under each rule) from its published SVG.

The chart is a vector file whose two lines are drawn as one straight segment per fiscal year, so each year's value
is read from the segment end points, with no image processing: x positions are 50 evenly spaced categories, 2024-25
to 2073-74, and y is calibrated on the labelled gridlines (3% at the axis to 9%, one point apart). Line colours follow
the chart's legend: light blue is the Triple Lock, dark blue the adjusted Triple Lock. The readings carry the chart's
drawing precision (about 0.01 points of GDP), not a published table's.

    python scripts/digitise_budget_chart.py   # writes data/benchmarks/budget_2026_chart_5_1.csv
"""

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "data" / "raw" / "budget-2026-chart-5.1.svg"
OUT = ROOT / "data" / "benchmarks" / "budget_2026_chart_5_1.csv"
PROV = ROOT / "data" / "benchmarks" / "budget_2026_chart_5_1.provenance.json"
URL = "https://assets.publishing.service.gov.uk/media/6ae1ec56460c1346f7be7804/Chart_5.1.svg"
LINES = {"#9ebee4": "triple_lock", "#3d7cc9": "adjusted"}  # legend: swatch left of "Triple Lock" / "Adjusted ..."
FIRST_YEAR = 2024


def gridlines(svg):
    """y positions of the axis and horizontal gridlines, bottom first, and the labels 3% ... 9% beside them."""
    ys = sorted({float(m) for m in re.findall(r'matrix\(1,0,0,-1,40\.2212,([\d.]+)\)"[^>]*d="M0 0H404\.637"', svg)},
                reverse=True)
    labels = [int(m) for m in re.findall(r'data-text="(\d)"[^>]*transform="matrix\(8\.5,0,0,-8\.5,2[01]\.\d+', svg)]
    return ys, labels


def digitise(svg):
    ys, labels = gridlines(svg)
    assert labels == list(range(3, 10)) and len(ys) == 7, (labels, ys)
    step = (ys[0] - ys[-1]) / (len(ys) - 1)
    seg = re.compile(r'<path transform="matrix\(1,0,0,-1,([\d.\-]+),([\d.\-]+)\)" stroke-width="2"[^>]*'
                     r'stroke="(#[0-9a-f]{6})" d="M0 0(-?[\d.]+)(-?[\d.]+|\s-?[\d.]+)"')
    pts = {k: [] for k in LINES.values()}
    for m in seg.finditer(svg):
        tx, ty, col = float(m[1]), float(m[2]), m[3]
        px, py = float(m[4]), float(m[5])
        name = LINES[col]
        if not pts[name]:
            pts[name].append((tx + px, ty - py))
        pts[name].append((tx, ty))
    out = {}
    for name, p in pts.items():
        p.sort()
        out[name] = [labels[0] + (ys[0] - y) / step for _, y in p]
    n = len(out["triple_lock"])
    assert n == len(out["adjusted"]) == 50
    return [(FIRST_YEAR + k, out["triple_lock"][k], out["adjusted"][k]) for k in range(n)]


def main():
    svg = SVG.read_text()
    rows = digitise(svg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year_start", "triple_lock_pct_gdp", "adjusted_pct_gdp"])
        for y, a, b in rows:
            w.writerow([y, f"{a:.3f}", f"{b:.3f}"])
    PROV.write_text(json.dumps({
        "title": "Budget 2026, Chart 5.1: This adjustment significantly improves the long-run sustainability of the "
                 "State Pension",
        "publisher": "HM Treasury",
        "document": "https://www.gov.uk/government/publications/budget-2026-document/budget-2026-html (Box 5.A)",
        "source_url": URL,
        "local_copy": "data/raw/budget-2026-chart-5.1.svg",
        "svg_sha256": hashlib.sha256(SVG.read_bytes()).hexdigest(),
        "downloaded": "2026-11-05",
        "method": "Vector digitisation: one segment per fiscal year; 50 evenly spaced categories from 2024-25; y "
                  "calibrated on the labelled gridlines 3% to 9% of GDP. No published table gives these values.",
        "precision": "About 0.01 percentage points of GDP (the drawing's coordinate precision)",
        "units": "State Pension spending, % of GDP, under each rule, the government's central forecast",
        "licence": "Open Government Licence v3.0",
        "output": "data/benchmarks/budget_2026_chart_5_1.csv",
        "script": "scripts/digitise_budget_chart.py",
    }, indent=2) + "\n")
    print(f"wrote {OUT} ({len(rows)} years)")


if __name__ == "__main__":
    main()
