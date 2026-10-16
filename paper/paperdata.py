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


HISTORY_RPI_YEAR = 2011  # April 2011's rise was set by RPI under that year's up-rating order (uprating2011), not CPI
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
    "policyengine": BUNDLE["bundle_version"],       # the release bundle (policyengine.py #555)
    "policyengine_uk": BUNDLE["model_version"],
    "policyengine_core": BUNDLE["core_version"],
    "data": PROV["datasets"]["primary"].split("@")[1],  # Enhanced FRS, enhanced_frs_2024_25@1.58.0
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
    # Law in the model (policyengine-uk 2.125.1, gov.hmrc.income_tax.allowances.personal_allowance.amount): frozen at
    # this amount to 2030-31, then uprated by the path's CPI.
    "personal_allowance": "£12,570",
    "pa_frozen_to": 2030,
}


# ── Revision 5 (review round 1): further reads of the same results ──────


def run_weights():
    """Each full run's weight in the expected saving: its group's share of the paths over the runs drawn in it."""
    strata = {s["stratum"]: s for s in EV["strata"]}
    return [strata[p["stratum"]]["probability"] * p["times_drawn"] / strata[p["stratum"]]["paths"] for p in EV["paths"]]


def reckoner():
    """The final-year saving per £1 a week of gap in the full new State Pension, across the full runs.

    Gross State Pension spending is exactly proportional to the gap (the population and its weights do not depend on
    the path, and both rules move the basic and new pension by the same percentage), so a least-squares slope through
    the origin fits every run; net is close to proportional. Returns slopes (£bn per £1 a week), R², the largest
    absolute residual, the slope expressed as full-rate equivalent recipients (millions), and the slope times the
    average gap over all the model's paths."""
    fy_ = str(FINAL)
    x = [p["gap_2039_gbp_week"] for p in EV["paths"]]
    out = {}
    for k in ("gross", "net", "gross_gb", "net_gb"):
        y = [p["outputs"]["primary"][k][fy_] for p in EV["paths"]]
        b = sum(a * c for a, c in zip(x, y)) / sum(a * a for a in x)
        m = sum(y) / len(y)
        ss = sum((c - m) ** 2 for c in y)
        res = [c - b * a for a, c in zip(x, y)]
        out[k] = {"slope": b, "r2": 1 - sum(r * r for r in res) / ss, "max_resid": max(abs(r) for r in res),
                  "at_mean_gap": b * EV["gap_by_calibration"][PRIMARY]["mean_gap_gbp_week"]}
    out["full_rate_equivalents_m"] = out["gross"]["slope"] * 1e9 / 52 / 1e6
    return out


TARGET_WORDS = {
    ("gap_variance", "switch_rate"): "gap spread, lead changes",
    ("gap_variance", "switch_rate", "floor_share"): "+ floor years",
}


def _post_stratified(key, field, year=FINAL):
    """A path output reweighted to calibration ``key`` directly from the full runs, as a post-stratified ratio
    estimate: each group's target share of the paths under the reweighting times the ratio-weighted average of its
    runs, sum_h P'_h (sum_i r_i y_i / sum_i r_i), with r = w'/w and each run counted as often as it was drawn.

    The runs' own weights already sum to each group's share under the paths as they are; reweighting changes those
    shares, so each group's average is normalised by its own reweighted mass rather than left unnormalised (which
    loses probability mass and biases the estimate down). Paths on which the rules never differ save nothing."""
    mass = EV["sensitivities"][key]["first_phase_stratum_probabilities"]
    total = 0.0
    for h, m in mass.items():
        runs = [p for p in EV["paths"] if str(p["stratum"]) == h]
        if h == "0" or not runs:
            continue
        r = [p["weight_ratio"][key] * p["times_drawn"] for p in runs]
        y = [field(p) for p in runs]
        total += m * sum(a * b for a, b in zip(r, y)) / sum(r)
    return total


def reweighted():
    """The paths reweighted to past variation. For each: the window, how 2020-22 is treated, what is matched, the
    reweighted average gap over all the paths, the ready-reckoner gross figure (slope times that gap, exact for gross)
    and, from the full runs directly, the post-stratified gross and net (the net uses each run's own net saving, so
    it does not assume net is proportional to the gap)."""
    rk = reckoner()
    fy_ = str(FINAL)
    out = []
    for k, v in EV["sensitivities"].items():
        window, treatment, _ = calibration_parts(k)
        targets = tuple(EV["calibrations"][k]["targeted"])
        gap_k = EV["gap_by_calibration"][k]["mean_gap_gbp_week"]
        out.append({
            "key": k, "window": window, "treatment": treatment, "targets": TARGET_WORDS[targets],
            "effective_runs": v["effective_runs"], "included": v["included_in_quoted_range"],
            "gross": rk["gross"]["slope"] * gap_k, "net_reckoner": rk["net"]["slope"] * gap_k, "gap": gap_k,
            "ps_gap": _post_stratified(k, lambda p: p["gap_2039_gbp_week"]),
            "ps_gross": _post_stratified(k, lambda p: p["outputs"]["primary"]["gross"][fy_]),
            "net": _post_stratified(k, lambda p: p["outputs"]["primary"]["net"][fy_]),
            "unnormalised_gross": v["gross"][fy_]["mean"],
        })
    return out


def s150a_share():
    """Share of path-years, April SWITCH+1 to FINAL, in which the plan's rise is below May-July earnings growth (to
    the 0.1 point the rules use), over all the model's paths (rule arithmetic)."""
    return RA["forms"][RA["primary_form"]]["plan_rise_below_earnings_share"]


def first_saving_year():
    """The first fiscal year with a positive expected saving."""
    return next(y for y in YEARS if est("gross", y)["mean"] > 0.005)


def cumulative(output, start=SWITCH, end=FINAL):
    """The expected saving summed over fiscal years (cash, £bn)."""
    return sum(est(output, y)["mean"] for y in YEARS if start <= y <= end)


def central_cpi_deflator(base=None, end=FINAL):
    """Price growth from fiscal year ``base`` to ``end`` on the OBR central forecast's calendar-year CPI (each fiscal
    year taken at its first calendar year)."""
    cal = CENTRAL["path"]["calendar"]["cpi"]
    base = base if base is not None else min(int(y) for y in cal) - 1
    f = 1.0
    for y in range(base + 1, end + 1):
        f *= 1 + cal[str(y)]
    return base, f


def paid_vs_replay():
    """April rises where the replay on today's figures differs from what was paid."""
    return [r for r in tl_record() if round(1000 * r["paid"]) != round(1000 * r["rate"])]


def paid_index():
    """Cumulative rise actually paid, April first to last."""
    f = 1.0
    for r in tl_record():
        f *= 1 + r["paid"]
    return f


def backtest_rows():
    """Past OBR forecasts: for each way of making the paths, the average gap the two rules open after four rises,
    predicted and realised, its bias (predicted minus realised, with a standard error that treats the forecasts as
    independent) and mean absolute error, with April 2022 as in law and as published."""
    s = EV["backtest"]["summary"]
    return {t: {k: s[t][k] for k in ("means_shift", "shift_dynamics", "model", "obr_point")} for t in s}


def screen_rule():
    """The past-forecast test's pass rule, as the test code fixed it before the scores (no results)."""
    return SCREEN_RULE


def screen_failure_ratio(form):
    """The score ratio named in a form's failure, e.g. 1.279 from 'switch_crps ratio 1.279 exceeds 1.25'."""
    fails = R["uncertainty_screen"]["c2_outcome"]["forms"][form]["failures"]
    m = re.search(r"ratio (\d+\.\d+)", " ".join(fails))
    return float(m.group(1)) if m else None


def signed_share(s):
    """The share of a lower State Pension that reaches income: a percentage, or a gain said as one."""
    if s is None:
        return "no change in pension"
    if s < -0.005:
        return f"{MINUS}{num(-100 * s, 0)}% (income rises)"
    if s <= 0.005:
        return "none"
    return pct(100 * s, 0)


def stylised_example():
    """A two-year example of the two rules on made-up inputs (in STYLISED), computed by the rules' arithmetic."""
    (c1, e1), (c2, e2) = STYLISED
    tl = (1 + max(c1, e1, FLOOR)) * (1 + max(c2, e2, FLOOR))
    l1 = 1 + max(c1, FLOOR, e1)  # the first rise after the switch equals the triple lock's
    anchor = (1 + e1) * (1 + e2)
    plan = max(l1 * (1 + max(c2, FLOOR)), anchor)
    return {"tl": tl - 1, "plan": plan - 1, "gap": 1 - plan / tl, "points": tl - plan}


# Made-up inputs for the two-year example in the rules section: (CPI, earnings) in each year.
STYLISED = ((0.06, 0.02), (0.02, 0.04))

# The past-forecast test's thresholds, as ts_uncertainty.C2_RULE fixed them before any score was seen.
SCREEN_RULE = {
    "coverage_low": 50, "coverage_high": 100, "wilson_contains": 80, "gap_bias": 1.5, "switch_bias": 1.0,
    "floor_bias": 0.25, "score_ratio": 1.25, "past_low": 5, "past_high": 95,
}


# ── Revision 6 (review round 2): rule arithmetic on every path ──────────
#
# scripts/paper_rule_arithmetic.py applies the two rules to all the model's paths (no PolicyEngine run) and writes
# the block read here. It must describe the same draws as the expected saving.

RA = R["paper_rule_arithmetic"]
assert RA["n_draws"] == EV["draws"]["n"] and RA["seed"] == EV["draws"]["seed"], "rerun paper_rule_arithmetic.py"
assert (RA["forms"][RA["primary_form"]]["innovation_sha256"]
        == EV["draws"]["model"]["shock_distribution"]["innovation_sha256"]), "rerun paper_rule_arithmetic.py"
assert abs(RA["forms"][RA["primary_form"]]["mean_gap_gbp_week"][str(FINAL)]
           - EV["gap_by_calibration"][PRIMARY]["mean_gap_gbp_week"]) < 1e-3, "rerun paper_rule_arithmetic.py"

FORM_NAMES = {"monthly_var1_boot": "Monthly (used here)", "monthly_var2_boot": "Monthly, two lags",
              "monthly_var1_tcop": "Monthly, heavy tails", "monthly_var1_gauss": "Monthly, normal shocks",
              "annual_boot_gap": "Annual"}


def _run_gap(p, y):
    """A full run's gap in the full new State Pension in April year ``y``, £ a week, from its rates."""
    base = BASE["new_state_pension"]
    lv = {k: base for k in POLICIES}
    for yy in YEARS:
        if yy > y:
            break
        for k in POLICIES:
            lv[k] *= 1 + p["rates"][k][str(yy)]
    return lv["triple_lock"] - lv["burnham_2030"]


def reckoner_by_year():
    """{year: £bn of gross saving per £1 a week of gap}, a least-squares slope through zero across the full runs, with
    its largest residual. Gross saving is exactly proportional to the gap in every year: the population does not
    depend on the path, and both rules move every flat-rate pension by the same percentage."""
    out = {}
    for y in YEARS:
        if y <= SWITCH:
            continue
        x = [_run_gap(p, y) for p in EV["paths"]]
        g = [p["outputs"]["primary"]["gross"][str(y)] for p in EV["paths"]]
        b = sum(a * c for a, c in zip(x, g)) / sum(a * a for a in x)
        out[y] = {"slope": b, "max_resid": max(abs(c - b * a) for a, c in zip(x, g))}
    return out


def exact_gross(y, form=None):
    """Expected gross saving in year ``y`` from all the paths: the slope times the average gap (exact, no Monte Carlo
    error from the choice of runs)."""
    if y <= SWITCH:
        return 0.0
    form = form or RA["primary_form"]
    return reckoner_by_year()[y]["slope"] * RA["forms"][form]["mean_gap_gbp_week"][str(y)]


def model_versions():
    """Every version of the price-and-earnings model that passes the test on past forecasts: its average final-year
    gap over its own 50,000 paths and the gross saving that implies (slope times gap)."""
    k = reckoner_by_year()[FINAL]["slope"]
    rows = []
    for form, v in RA["forms"].items():
        gap_ = v["mean_gap_gbp_week"][str(FINAL)]
        rows.append({"form": form, "label": FORM_NAMES.get(form, form), "gap": gap_, "gross": k * gap_,
                     "dynamics": v["dynamics"], "primary": form == RA["primary_form"]})
    return rows


def earnings_exact():
    """The paired earnings scenarios costed exactly from all the shifted paths: {sid: {delta, from_year, gross: {year:
    £bn}, diff: {year: £bn against the paths as they are}, dynamics}}."""
    k = reckoner_by_year()
    prim = RA["forms"][RA["primary_form"]]["mean_gap_gbp_week"]
    out = {}
    for sid, v in RA["earnings_variants"].items():
        g = {y: k[y]["slope"] * v["mean_gap_gbp_week"][str(y)] for y in k}
        out[sid] = {"delta": v["calendar_earnings_delta"], "from_year": v["from_year"], "gross": g,
                    "diff": {y: g[y] - k[y]["slope"] * prim[str(y)] for y in k}, "dynamics": v["dynamics"]}
    return out


def dynamics_rows():
    """How the model's paths behave over the plan's input years against the statutory history: lead changes a year,
    variance and year-to-year correlation of the gap between earnings and CPI, share of years with both below the
    floor."""
    h = RA["history"]
    rows = [("Model paths, as they are", RA["forms"][RA["primary_form"]]["dynamics"])]
    for key, label in (("2010_2025.suspended", "History 2010–2025, 2022 as in law"),
                       ("2010_2025.published", "History 2010–2025, 2022 as published"),
                       ("2001_2025.suspended", "History 2001–2025, 2022 as in law"),
                       ("2001_2010.published", "History 2001–2010")):
        rows.append((label, h[key]))
    return rows
