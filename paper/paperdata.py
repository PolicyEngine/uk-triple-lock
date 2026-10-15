"""Every number the working paper prints, read from the committed results.

The manuscript (index.qmd) types no result by hand. It reads this module,
which reads only ``data/results.json`` (the file the dashboard shows) and the
committed input files under ``data/``. Nothing here runs PolicyEngine or
changes a figure: it selects, formats and tabulates. Every fiscal and household
figure in the file is a full PolicyEngine UK run; rule arithmetic (weekly
amounts, rates, the gap distribution across paths) is labelled as such where
the paper shows it.

FRS records are licensed data. The results file carries no survey record's
identifier, weight, amounts or contribution, and this module reads only
totals over the survey.
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results.json"
R = json.loads(RESULTS.read_text())

POLICIES = ("triple_lock", "burnham_2030")
YEARS = list(R["horizon"])
FINAL = int(R["final_year"])
SWITCH = int(R["switch_year"])
DIST_YEARS = list(R["distribution_years"])
EV = R["expected_value"]
TRAJ = R["trajectories"]
HISTORY = TRAJ["history"]
CENTRAL = R["central"]
DWP = R["dwp_uprating_analysis"]
PRIMARY = EV["primary"]


# ── Formatting ───────────────────────────────────────────────────────────


MINUS = "\u2212"  # a typographic minus sign


def _rounded(x, d):
    """``x`` to ``d`` places, half away from zero on its shortest decimal form; never negative zero."""
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return abs(q) if q == 0 else q


def num(x, d=1):
    """``x`` to ``d`` places with thousands commas and a minus sign: -0.604 -> '\u22120.60'.

    A result that rounds to zero prints unsigned ("0.0", not "\u22120.0").
    """
    q = _rounded(x, d)
    return f"{MINUS if q < 0 else ''}{abs(q):,.{d}f}"


def bn(x, d=2):
    """£ billions: 0.659 -> '£0.66bn'; negative -> '\u2212£0.04bn'."""
    q = _rounded(x, d)
    return f"{MINUS if q < 0 else ''}£{abs(q):,.{d}f}bn"


def gbp(x, d=0):
    """Pounds: 1363.7 -> '£1,364'."""
    q = _rounded(x, d)
    return f"{MINUS if q < 0 else ''}£{abs(q):,.{d}f}"


def wk(x):
    """Weekly pounds to the penny: 359.846 -> '£359.85'."""
    return gbp(x, 2)


def pct(x, d=1):
    """A value already in per cent: 19.84 -> '19.8%'."""
    return f"{num(x, d)}%"


def rate(x, d=1):
    """A decimal rate as a percentage: 0.0362 -> '3.6%'."""
    return f"{num(100 * x, d)}%"


def points(x, d=2):
    """A decimal difference in percentage points: 0.00546 -> '0.55'."""
    return num(100 * x, d)


def fy(y):
    """Fiscal year named by its start year: 2039 -> '2039-40'."""
    y = int(y)
    return f"{y}-{str(y + 1)[-2:]}"


def count(x):
    return f"{int(round(x)):,}"


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def words(n):
    """Small whole numbers as words, as house style prefers in prose: 5 -> 'five'."""
    return WORDS.get(int(n), count(n))


def ordinal(n):
    """Rounded half away from zero, as num() and the dashboard's Math.round: 2.5 -> '3rd'."""
    n = int(_rounded(n, 0))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def listing(items, conj="and", sep=", "):
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return f"{sep.join(items[:-1])}{sep.rstrip() if sep != ', ' else ''} {conj} {items[-1]}"


def md_table(headers, rows, align=None):
    """A pipe table. ``align``: a string of 'l'/'r' per column (default: first left, rest right)."""
    align = align or "l" + "r" * (len(headers) - 1)
    rule = ["---:" if a == "r" else ":---" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


# ── Policies and the speech ──────────────────────────────────────────────


LABELS = {p: R["policies"][p]["label"] for p in POLICIES}
BASE = R["base_year_weekly"]
FLOOR_TEXT = re.search(r"(\d+(?:\.\d+)?%)", R["policies"]["triple_lock"]["rule"]).group(1)  # '2.5%'
FLOOR = float(FLOOR_TEXT.rstrip("%")) / 100
RATE_DECIMALS = int(CENTRAL["run"]["rate_decimals"])  # rates to 0.1 point, as ONS publishes the inputs


# ── Step 1: the triple lock since 2011 ───────────────────────────────────


def tl_record():
    """The triple lock replayed on the published inputs, April 2011-2026, one row per April."""
    t = HISTORY["triple_lock"]
    rows = []
    for y in t["years"]:
        s = str(y)
        rows.append({
            "year": y,
            "cpi": HISTORY["cpi"][s],
            "earnings": t["earnings_published"][s],
            "earnings_used": HISTORY["earnings"][s],
            "rate": t["rate"][s],
            "binding": t["binding"][s],
            "paid": HISTORY["actual_rise"][s],
            "index": {k: t["index"][k][s] for k in ("triple_lock", "cpi", "earnings", "floor")},
        })
    return rows


BINDING_WORDS = {"cpi": "CPI", "earnings": "earnings", "floor": "the 2.5% floor"}


def history_groups():
    """Past-years counterfactuals: the plan started in an earlier April."""
    out = []
    for g in HISTORY["groups"]:
        sy = g["switch_years"]
        m = g.get("model_years") or None
        out.append({"switch_years": sy, "label": "April " + listing(sy, "or"), "changes": g["changes_anything"],
                    "model": m, "tl_rate": g["triple_lock_rate"], "bp_rate": g["burnham_rate"],
                    "ratio": g["level_ratio"]})
    return out


# ── Paths (steps 2 to 5) ─────────────────────────────────────────────────


PATH_IDS = [p["id"] for p in TRAJ["paths"]]


def path(pid):
    if pid == "central":
        # The trajectories block repeats the central run with its example households.
        return next(p for p in TRAJ["paths"] if p["id"] == "central")
    return next(p for p in TRAJ["paths"] if p["id"] == pid)


def path_rows(p):
    """One row per April rise: statutory inputs (the year before), rates, what set them, levels and savings."""
    rows = []
    for y in YEARS:
        s, g = str(y), str(y - 1)
        sv = p["saving_bn"][s]
        rows.append({
            "year": y,
            "cpi": p["statutory"]["cpi"][g],
            "earnings": p["statutory"]["earnings"][g],
            "tl_rate": p["rates"]["triple_lock"][s],
            "bp_rate": p["rates"]["burnham_2030"][s],
            "tl_source": p["rate_sources"]["triple_lock"][s],
            "bp_source": p["rate_sources"]["burnham_2030"][s],
            "tl_weekly": p["weekly"]["triple_lock"]["new_state_pension"][s],
            "bp_weekly": p["weekly"]["burnham_2030"]["new_state_pension"][s],
            "gross": sv["gross"],
            "net": sv["net"],
            "components": sv["components"],
            "losing_pct": p["households_affected"][s]["losing_pct"],
            "mean_loss": p["households_affected"][s]["mean_loss_gbp"],
        })
    return rows


def row(p, y):
    return next(r for r in path_rows(p) if r["year"] == y)


TL_SOURCE = {"earnings": "earnings", "cpi": "CPI", "floor": "2.5% floor"}
BP_SOURCE = {"triple_lock": "triple lock", "earnings_path": "its earnings path", "cpi": "CPI",
             "floor": "2.5% floor"}

def differs(r):
    """Whether the two rules' rates differ this year, to 0.1 point."""
    return round((r["bp_rate"] - r["tl_rate"]) * 10 ** RATE_DECIMALS) != 0


def gap_pct(r):
    """How far the plan's full new State Pension is below the triple lock's, % of the triple lock's."""
    return 100 * (1 - r["bp_weekly"] / r["tl_weekly"])


# ── Households ───────────────────────────────────────────────────────────


ACCOUNT = [
    ("state_pension", "State Pension", 1),
    ("income_tax", "Income tax paid", -1),
    ("pension_credit", "Pension Credit", 1),
    ("housing_benefit", "Housing Benefit", 1),
    ("council_tax_reduction", "Council tax reduction", 1),
    ("winter_fuel_payment", "Winter Fuel Payment", 1),
]


def examples(p):
    h = p["households"]
    return {k: {"meta": v, "res": h["results"][k]} for k, v in h["examples"].items()}


def ex_change(ex, key, y):
    """Plan minus triple lock, £ a year (for income tax: the change in tax paid)."""
    res = ex["res"]
    return res["burnham_2030"][key][str(y)] - res["triple_lock"][key][str(y)]


def ex_level(ex, policy, key, y):
    return ex["res"][policy][key][str(y)]


def borne_share(ex, y):
    """Share of the State Pension loss that shows up in the pensioner's income (None when there is no loss)."""
    sp = ex_change(ex, "state_pension", y)
    net = ex_change(ex, "net_income", y)
    return None if sp > -0.5 else net / sp


# ── The net account (step 5) ─────────────────────────────────────────────


NET_ACCOUNT = [
    ("pension_credit", "Extra Pension Credit", -1),
    ("housing_benefit", "Extra Housing Benefit", -1),
    ("council_tax_reduction", "Extra council tax reduction", -1),
    ("universal_credit", "Extra Universal Credit", -1),
    ("winter_fuel_payment", "Extra Winter Fuel Payment", -1),
    ("income_tax", "Less income tax", 1),
]


def net_account(p, y):
    """Gross saving, each offset (signed so it adds up to the net saving), everything else, net."""
    sv = p["saving_bn"][str(y)]
    rows = [(label, sign * sv["components"][k]) for k, label, sign in NET_ACCOUNT]
    other = sv["net"] - sv["gross"] - sum(v for _, v in rows)
    return {"gross": sv["gross"], "net": sv["net"], "rows": rows, "other": other}


# ── Every path (step 6) ──────────────────────────────────────────────────


def est(output, y, dataset="primary"):
    return EV["estimates"][dataset][output][str(y)]


def spread(output, y, qs=(0.1, 0.9)):
    """Weighted percentiles of a path output across the full runs, as the dashboard computes them (getSavingSpread):
    each run stands for its stratum's share of the paths, and paths on which the rules never differ sit at zero."""
    strata = {s["stratum"]: s for s in EV["strata"]}
    pairs = []
    for p in EV["paths"]:
        s = strata[p["stratum"]]
        pairs.append((p["outputs"]["primary"][output][str(y)], s["probability"] * p["times_drawn"] / s["paths"]))
    zero = max(0.0, 1 - sum(w for _, w in pairs))
    if zero > 0:
        pairs.append((0.0, zero))
    pairs.sort()
    total = sum(w for _, w in pairs)
    out = []
    for q in qs:
        cum = 0.0
        for v, w in pairs:
            cum += w
            if cum >= q * total:
                out.append(v)
                break
        else:
            out.append(pairs[-1][0])
    return out


def spread80(output, y):
    """The middle 80% of paths: (10th, 90th) percentiles."""
    return spread(output, y)


def pm(e, d=2):
    """'£8.41bn (SE £0.04bn)'."""
    return f"{bn(e['mean'], d)} (SE {bn(e['se'], d)})"


def n_runs():
    return sum(s["paths"] for s in EV["strata"])


def n_unique():
    return sum(s["unique_paths"] for s in EV["strata"])


def n_sensitivity():
    return sum(s["sensitivity_paths"] for s in EV["strata"])


CALIBRATION_WORDS = {
    "covid_excluded": "2020-21 left out",
    "suspended": "2022 as in law",
    "published": "2022 as published",
}


def calibration_parts(name):
    """(window, treatment, targets) from 'shift_dynamics.2001_2025.covid_excluded'."""
    kind, window, treatment = name.split(".")
    a, b = window.split("_")
    what = "variance, leads, floor share" if kind.endswith("_floor") else "variance, leads"
    return f"{a}-{b}", CALIBRATION_WORDS[treatment], what


def premium():
    return EV["gap_by_calibration"][PRIMARY]["mean_rate_minus_earnings_2034_2039"]


def obr_premium_text():
    """The OBR's long-term triple-lock assumption as the determinants file words it (from the benchmarks)."""
    b = next(b for b in R["benchmarks"] if b["id"] == "obr_lted_triple_lock_premium")
    m = re.search(r"plus (\d+(?:\.\d+)?) percentage points", b["figure_text"])
    return m.group(1), b


def benchmark(bid):
    return next(b for b in R["benchmarks"] if b["id"] == bid)


# ── The scenario envelope ────────────────────────────────────────────────


ENVELOPE = R["scenario_envelope"]


def scenarios(years):
    """The single scenarios beside the expected saving, each {name, kind, values: {year: (gross, net, gross_se, net_se)}}.
    The central path and the OBR long-term path are single runs (no Monte Carlo error); the earnings scenarios are
    averages over the same simulated paths as the expected saving, with earnings growth shifted from a given year."""
    out = []
    c = CENTRAL["run"]["saving_bn"]
    out.append({"name": "OBR central forecast", "kind": "single run",
                "values": {y: (c[str(y)]["gross"], c[str(y)]["net"], None, None) for y in years}})
    w = ENVELOPE["obr_wedge"]["run"]["saving_bn"]
    out.append({"name": "OBR long-term path (triple lock above earnings)", "kind": "single run",
                "values": {y: (w[str(y)]["gross"], w[str(y)]["net"], None, None) for y in years}})
    for sid, sc in ENVELOPE["paired_earnings_mean_paths"]["scenarios"].items():
        d = sc["calendar_earnings_delta"]
        sp = sc["scenario_path_set"]
        name = f"Earnings {'+' if d > 0 else MINUS}{num(100 * abs(d), 1)} points from {sc['from_year']}"
        out.append({"name": name, "kind": "path average",
                    "values": {y: (sp["gross"][str(y)]["mean"], sp["net"][str(y)]["mean"],
                                   sp["gross"][str(y)]["se"], sp["net"][str(y)]["se"]) for y in years}})
    return out


# ── Backtests ────────────────────────────────────────────────────────────


BACKTEST_LABELS = {
    "model": "Not calibrated",
    "means_tilt": "Tilt to the OBR means",
    "means_shift": "Drift shift (used here)",
    "shift_dynamics": "Drift shift, then tilt to past dynamics",
    "obr_point": "OBR forecast as one path",
}

STATUTORY_SHORT = {
    "monthly_boot+shift": "Monthly, drift shift (used here)",
    "monthly_boot+tilt": "Monthly, tilted",
    "monthly_boot+raw": "Monthly, not calibrated",
    "monthly_tcop+tilt": "Monthly, t-copula, tilted",
    "monthly_gauss+tilt": "Monthly, Gaussian, tilted",
    "annual_boot_var+tilt+gap_blocks": "Annual, plus past gaps",
    "annual_boot_var+tilt+no_gaps": "Annual, calendar only",
    "block_bootstrap_statutory": "Past OBR errors",
    "iid_normal": "Independent normal",
    "obr_point": "OBR forecast (a point)",
}

STATUTORY_LABELS = {
    "monthly_boot+shift": "Monthly model, drift shift to the OBR means (used here)",
    "monthly_boot+tilt": "Monthly model, tilted to the OBR means",
    "monthly_boot+raw": "Monthly model, not calibrated",
    "monthly_tcop+tilt": "Monthly model, t-copula shocks, tilted",
    "monthly_gauss+tilt": "Monthly model, Gaussian shocks, tilted",
    "annual_boot_var+tilt+gap_blocks": "Annual model plus past statutory gaps",
    "annual_boot_var+tilt+no_gaps": "Annual model, calendar measures only",
    "block_bootstrap_statutory": "Past OBR forecast errors",
    "iid_normal": "Independent normal errors",
    "obr_point": "OBR forecast alone (a point)",
}


# ── Provenance ───────────────────────────────────────────────────────────


PROV = R["provenance"]
BUNDLE = PROV["model"]  # the certified policyengine.py bundle the runs used


# ── Facts about the method ───────────────────────────────────────────────

# Facts about the method, not results. Kept here so the prose types no number.
V2 = {
    "policyengine": "6.2.6",          # the release bundle (policyengine.py #555)
    "policyengine_uk": "2.125.1",
    "policyengine_core": "3.33.0",
    "data": "1.58.0",                 # Enhanced FRS, enhanced_frs_2024_25
    "pilot_uk": "2.120.0",            # the uncertified pilot's model
    "passport_uk": "2.123.6",
    "ctr_fix_uk": "2.104.2",         # council tax reduction disregards guarantee credit recipients (#1909)
    "new_hb_claims_uk": "2.102.5",   # pension-age families may make new Housing Benefit claims         # first policyengine-uk release with #1927
    "top_code": "80",                 # Enhanced FRS ages are top-coded here
    "age_cap": "105",                 # represented ages run from the top code to this
    "anchor_year": "2025",            # the data build's calibration year (frs_release.py)
    "weight_gap": "0.44%",            # policyengine-uk-data #538: calibration-year totals this much low
    "c1": "C1",                      # the first pre-registered screen
    "c2": "C2",                      # the second, pre-registered at c2_commit
    "c1_forms": "five",
    "c1_terminal": "one of six",      # test A terminal coverage with April 2022 as published
    "c2_commit": "65343e2",           # the C2 pre-registration commit
    "c2_cells": "four",               # test A annual gap cells the legal rule fixes
    "c2_cells_of": "24",
    "slots": "160",                   # sample slots in the C2 handoff design
    "microcosm_slots": "40",
    "mean_path_pp": "0.5",            # the paired earnings mean-path variants, ± points
    "spa_rise": "67",
    "spa_now": "66",
    "rake_low": "a fifth",           # raking bounds on the ratio to the anchor-year weight
    "rake_high": "five times",
    "rake_cells": "five-year bands up to 59, single years from 60 to 79, then 80 to 84, 85 to 89, and 90 and over",
    "fy_mix": "three-quarters of the mid-year population of its first year and a quarter of the next",
    "nsp_born_men": "6 April 1951",
    "nsp_born_women": "6 April 1953",
    "spa67_born": "6 April 1960",
    "type_date": "6 October",
    "accounting_tol": "£0.01",
    "min_effective_runs": "100",     # tilt sensitivities below this are left out of any quoted range
    "gap_bias": "1.5",               # C1/C2 threshold, percentage points
    "score_ratio": "1.25",            # C1/C2 threshold, proper scores against the primary
    "past_band": "5th and 95th",     # C1/C2 past-years check
}
