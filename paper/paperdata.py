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
TRAJ = R["trajectories"]
HISTORY = TRAJ["history"]
CENTRAL = R["central"]
DWP = R["dwp_uprating_analysis"]
# The binding post-Budget release carries no expected value: its forecast model failed the registered test, and the
# rule then keeps the scenarios only. Fail loudly if a results file with an expected value reaches this paper.
assert "expected_value" not in R and R["expected_value_omission"]["effective_ruling"] == "a", "paper is scenarios only"


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


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
         18: "eighteen", 19: "nineteen", 20: "twenty"}


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
    """A full run on one path: the trajectories block's paths (the central run with its example households, a random
    draw and two simulated paths picked for the size of their final-year gap), or the OBR long-term path ("wedge"),
    which carries no example households."""
    if pid == "wedge":
        return {"id": "wedge", **R["scenario_envelope"]["obr_wedge"]["run"]}
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


# ── The registered test and the benchmarks ─────────────────────────────


def obr_premium_text():
    """The OBR's long-term triple-lock allowance in points, as the results file's benchmark note words it."""
    b = benchmark("obr_frs_2026")
    m = re.search(r"average earnings growth plus (\d+(?:\.\d+)?) points", b["note"])
    return m.group(1), b


def benchmark(bid):
    return next(b for b in R["benchmarks"] if b["id"] == bid)


# ── The scenario envelope ────────────────────────────────────────────────


ENVELOPE = R["scenario_envelope"]


def scenarios(years):
    """The four scenarios of the envelope, each {key, name, kind, values: {year: (gross, net, gross_pm, net_pm)}}.

    The OBR central path and the OBR long-term path are single full runs (no Monte Carlo error). The two earnings
    scenarios are averages over the same 160 simulated draws with calendar earnings growth moved from a given year;
    their margin is the file's 95% Monte Carlo error, which measures path sampling only. None is a probability
    interval, and no average of the unshifted draws is published (the registered rule withdrew it)."""
    out = []
    c = CENTRAL["run"]["saving_bn"]
    out.append({"key": "central", "name": "OBR central path", "kind": "single run",
                "values": {y: (c[str(y)]["gross"], c[str(y)]["net"], None, None) for y in years}})
    w = ENVELOPE["obr_wedge"]["run"]["saving_bn"]
    out.append({"key": "wedge", "name": "OBR long-term path", "kind": "single run",
                "values": {y: (w[str(y)]["gross"], w[str(y)]["net"], None, None) for y in years}})
    for sid, sc in sorted(EARNINGS.items(), key=lambda kv: kv[1]["calendar_earnings_delta"]):
        d = sc["calendar_earnings_delta"]
        sp = sc["scenario_path_set"]
        name = f"Earnings {'+' if d > 0 else MINUS}{num(100 * abs(d), 1)} points from {sc['from_year']}"
        out.append({"key": "plus" if d > 0 else "minus", "name": name, "kind": "draw average",
                    "values": {y: (sp["gross"][str(y)]["mean"], sp["net"][str(y)]["mean"],
                                   sp["gross"][str(y)]["plus_minus_95"], sp["net"][str(y)]["plus_minus_95"])
                               for y in years}})
    return out


def scenario(key):
    return next(s for s in scenarios(YEARS) if s["key"] == key)


EARNINGS = ENVELOPE["paired_earnings_mean_paths"]["scenarios"]
N_DRAWS = ENVELOPE["paired_earnings_mean_paths"]["sample_slots"]  # simulated draws behind each earnings scenario
assert all(v["unique_full_runs"] == N_DRAWS for v in EARNINGS.values())
WEDGE = ENVELOPE["obr_wedge"]["run"]


def scenario_gb(key, y=FINAL):
    """Great Britain gross saving for a scenario (single runs carry it; draw averages carry gross_gb)."""
    if key == "central":
        return CENTRAL["run"]["saving_bn"][str(y)]["gb"]["gross"]
    if key == "wedge":
        return WEDGE["saving_bn"][str(y)]["gb"]["gross"]
    sc = next(v for v in EARNINGS.values() if (v["calendar_earnings_delta"] > 0) == (key == "plus"))
    return sc["scenario_path_set"]["gross_gb"][str(y)]["mean"]


# ── Provenance ───────────────────────────────────────────────────────────


PROV = R["provenance"]
BUNDLE = PROV["model"]  # the certified policyengine.py bundle the runs used


# ── Facts about the method ───────────────────────────────────────────────

# Facts about the method, not results. Kept here so the prose types no number.
_NATIONAL = BUNDLE["release_manifest"]["revision"]  # microcosm-uk-2024-25-national-<stamp>-<hash>
V2 = {
    "policyengine": BUNDLE["bundle_version"],       # the certified release bundle (policyengine.py #720)
    "policyengine_uk": BUNDLE["model_version"],
    "policyengine_core": BUNDLE["core_version"],
    "microcosm": PROV["datasets"]["primary"].split("@")[1],     # the national cut's build hash
    "efrs": PROV["datasets"]["sensitivity"].split("@")[1],      # Enhanced FRS, coverage check only
    "anchor_year": str(BUNDLE["ageing_anchor"]["year"]),         # the data's calibration year
    "households": R["coverage"]["datasets"]["primary"]["records"]["households"],
    "mean_path_pp": num(100 * abs(next(iter(R["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"].values()))
                                  ["calendar_earnings_delta"]), 1),
    # Law in the model (policyengine-uk 2.151.0, gov.hmrc.income_tax.allowances.personal_allowance.amount): frozen at
    # this amount to 2030-31 by Finance Act 2021 s. 5 as amended by Finance Act 2026 s. 10, then indexed by September
    # CPI under Income Tax Act 2007 s. 57.
    "personal_allowance": "£12,570",
    # The second rule (docs/METHOD.md, "C2 frozen rule"): its section was committed alone on this date, before any
    # score under it was computed (data/pilot/c2-registration-audit.json records the commit, not printed here).
    "c2_registered": "6 October 2026",
    # The overlap-robust standard errors of the test: Newey-West (Bartlett) with this many lags for four-year windows
    # (ts_backtest.mean_with_overlap_se).
    "hac_lags": 3,
    # Each scored forecast covers four Aprils, so three changes of lead are possible in a window (ts_backtest.H).
    "window_years": 4,
    "pa_frozen_to": 2030,
    # GitHub's activity log for paper-academic-revision (PR #56): when each was pushed. The second model's
    # registration (7ed1244), its code (e1e8134) and its scores and verdict (5285818); docs/METHOD.md's C4 erratum
    # records the same times. They fix the order in which the three became public, nothing earlier.
    "c4_pushed": {"registration": "2026-11-11T15:20:01Z", "code": "2026-11-11T15:23:02Z",
                  "scores": "2026-11-11T15:23:59Z"},
    # The same log for V1: when its specification (fcf1609), first code (33c58de) and first figures (2d3af6d) were
    # pushed. docs/METHOD.md's V1 Record of order gives their commit times, a second or two earlier.
    "v1_pushed": {"spec": "2026-11-12T11:06:22Z", "code": "2026-11-12T11:07:40Z", "figures": "2026-11-12T11:09:13Z"},
    # The same log for B1: its specification (de576a5), first code (4f2bb1f) and first fit (8c798a0).
    "b1_pushed": {"spec": "2026-11-12T14:32:48Z", "code": "2026-11-12T14:38:46Z", "fit": "2026-11-12T14:40:20Z"},
    # PolicyEngine UK 2.151.0, policyengine_uk/dynamics/labour_supply.py: its step on the OBR's labour-supply
    # elasticities excludes people of this age and over (calculate_excluded_from_labour_supply_responses).
    "lsr_excluded_from_age": 60,
}


# ── Further reads of the same results ───────────────────────────────────


def paid_vs_replay():
    """April rises where the replay on today's figures differs from what was paid."""
    return [r for r in tl_record() if round(1000 * r["paid"]) != round(1000 * r["rate"])]


def paid_index():
    """Cumulative rise actually paid, April first to last."""
    f = 1.0
    for r in tl_record():
        f *= 1 + r["paid"]
    return f


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


FORM_NAMES = {"monthly_var1_boot": "Monthly (baseline model)", "monthly_var2_boot": "Monthly, two lags",
              "monthly_var1_tcop": "Monthly, heavy tails", "monthly_var1_gauss": "Monthly, normal shocks",
              "annual_boot_gap": "Annual"}




# ── The registered test (C2), its fallback and the forward rule (C3) ────


SCREEN = R["uncertainty_screen"]
C2 = SCREEN["c2_scores"]
PRIMARY_FORM = "monthly_var1_boot"


def screen_primary(test="A"):
    """The original primary's C2 scores on one test, April 2022 scored as the law applied it."""
    return C2["scores"][test]["suspended"][PRIMARY_FORM]


def screen_failures():
    """The primary's failed checks as (statistic, value, limit), parsed from the file's failure strings."""
    out = []
    for f in SCREEN["c2_outcome"]["forms"][PRIMARY_FORM]["failures"]:
        m = re.search(r"\|(\w+)\| (\d+\.\d+) exceeds (\d+\.\d+)", f)
        out.append((m.group(1), float(m.group(2)), float(m.group(3))))
    return out


def origins(test="A"):
    return C2["origins"][test]


C3_OC = json.loads((ROOT / "docs" / "uncertainty" / "c3-operating-characteristics.json").read_text())


def c3_pass_rate(case, years):
    """Share of simulated outcomes on which a figure passes every shared C3 check, after ``years`` years."""
    return C3_OC["pass_rates"][case][str(years)]["all"]


C3_FIRST = C3_OC["first_outcome_year"]  # the first determination year the prospective test scores
C3_YEARS = 8                            # determination years 2027 to 2034 before any verdict (C3 "Verdict")


# ── The second model (C4): anchored on the OBR's forecast errors; it failed ──
#
# The registration (docs/METHOD.md, C4) fixes what the paper may say if the model fails: scenarios only, every score
# and the verdict published, and the model's distribution of G and the share given once, in an appendix, labelled as
# the output of a model that failed its test, with no probability statement and no expected cash figure. Nothing
# below converts the model's paths to cash. data/c4/diagnostics.json comes from scripts/c4_diagnostics.py.


C4_DIR = ROOT / "data" / "c4"
C4_SCORES = json.loads((C4_DIR / "scores.json").read_text())
C4_ARITH = json.loads((C4_DIR / "rule_arithmetic.json").read_text())
C4_DIAG = json.loads((C4_DIR / "diagnostics.json").read_text())
assert C4_SCORES["verdict"]["passes"] is False and C4_ARITH["c4_passes"] is False, \
    "the paper's C4 text is written for a failed model; a pass needs a ruling and a rewrite"
assert "failed its registered test" in C4_ARITH["label"]
C4_LABEL = C4_ARITH["label"]
C4_PATHS = C4_ARITH["n_paths"]
C4_YEARS = [int(y) for y in C4_ARITH["years"]]  # 2034, 2039: fiscal years 2034-35 and 2039-40
C4_ORIGIN_YEARS = sorted({int(r["origin_year"]) for r in C4_SCORES["primary"]["rows"]})
C4_TARGET_YEARS = sorted({y for r in C4_SCORES["primary"]["rows"] for y in r["target_years"]})
C4_LIMITS = C4_SCORES["limits"]


def c4_check(test, name):
    """One registered check of the primary C4 model: (value, limit, passes)."""
    c = next(c for c in C4_SCORES["verdict"]["checks"] if c["test"] == test and c["check"] == name)
    return c["value"], c["limit"], c["passes"]


def c4_failures():
    """The failed checks as (test, check, value, limit)."""
    return [(c["test"], c["check"], c["value"], c["limit"]) for c in C4_SCORES["verdict"]["checks"] if not c["passes"]]


def c4_summary(test):
    """The primary's suspended-treatment summaries on one test (A: seven forecasts, B: thirteen)."""
    return C4_SCORES["primary"]["scores"][test]["suspended"]


def c4_sensitivities_passing():
    """Sensitivities (no influence on the verdict) that would have met every check."""
    return [k for k, v in C4_SCORES["sensitivities_no_influence_on_verdict"].items() if v["would_pass"]]


def c4_distribution(y, what="share"):
    """Mean and quartiles of the share (fraction) or G (log points) over the forward paths, fiscal year ``y``.
    The outer percentiles and threshold shares stay in the data file: the tails rest on a few past years."""
    d = C4_ARITH["distribution"][str(y)]["share" if what == "share" else "log_gap_G"]
    return {k: d[k] for k in ("mean", "p25", "median", "p75")}


C4_SEEDS = C4_DIAG["seed_robustness"]
C4_RES = C4_DIAG["resolution"]
C4_DRIFT = C4_DIAG["drift"]
C4_DECOMP = C4_DIAG["decomposition"]
C4_VARIO = C4_DIAG["variogram_by_origin_b"]
C4_DROP1 = C4_DIAG["variogram_dropping_one_score_b"]  # computed after the verdict, not registered
C4_CONC = C4_DIAG["history_concentration"]
assert C4_DIAG["registered"] is False


def c4_sensitivity_failures(name):
    """A sensitivity's failed checks (no influence on the verdict) as (test, check, value), from scores.json's
    "would_fail_on" record, in its order. Values stay strings ("0.35961...", "[0.158..., 0.749...]", "11")."""
    out = []
    for line in C4_SCORES["sensitivities_no_influence_on_verdict"][name]["would_fail_on"]:
        m = re.match(r"^([AB]): (.+?) (\[[^\]]+\]|[-\d.]+) outside ", line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def c4_sensitivity_summary(name, test="A"):
    """A sensitivity's suspended-treatment summaries on one test."""
    return C4_SCORES["sensitivities_no_influence_on_verdict"][name]["scores"][test]["suspended"]


# ── Sources quoted in the paper ─────────────────────────────────────────


BUDGET = json.loads((ROOT / "data" / "raw" / "budget-2026-html.json").read_text())
BUDGET_TEXT = re.sub(r"<[^>]+>", "", BUDGET["details"]["body"]) if isinstance(BUDGET.get("details"), dict) and \
    "body" in BUDGET["details"] else re.sub(r"<[^>]+>", "", json.dumps(BUDGET))


def budget_quote(pattern):
    """A passage of the Budget 2026 document, verbatim from the committed GOV.UK content."""
    m = re.search(pattern, BUDGET_TEXT)
    assert m, pattern
    return m.group(0)


def quoted(bid, n=0):
    """The ``n``-th double-quoted passage of a benchmark's figure text (the source's own words)."""
    return re.findall(r"\"([^\"]+)\"", benchmark(bid)["figure_text"])[n]


def plan_below_earnings(pid):
    """Aprils from SWITCH+1 to FINAL in which the plan's rise is below May-July earnings growth (to 0.1 point) on a
    path: the years in which it pays less than section 150A's earnings minimum (rule arithmetic)."""
    out = []
    for r in path_rows(path(pid)):
        if r["year"] > SWITCH and round(1000 * r["bp_rate"]) < round(1000 * r["earnings"]):
            out.append(r["year"])
    return out


# ── Rule arithmetic on the inputs of a path (no simulation) ─────────────


def _lead(cpi, earnings):
    """+1 when the higher of CPI and the floor beats earnings (d > 0), -1 when earnings lead, 0 on a tie."""
    m = max(cpi, FLOOR)
    return 1 if round(1000 * m) > round(1000 * earnings) else (-1 if round(1000 * m) < round(1000 * earnings) else 0)


def lead_changes(leads):
    """Times the lead passes between earnings and the higher of CPI and the floor; a tie keeps the previous lead."""
    n, prev = 0, 0
    for s in leads:
        if s == 0:
            continue
        if prev and s != prev:
            n += 1
        prev = s
    return n


def path_leads(pid):
    """Lead statistics for the Aprils from SWITCH to FINAL on a path: changes of lead, Aprils with May-July earnings
    growth below the floor, and the log gap G between the two rules' levels in the final year."""
    import math
    rows = [r for r in path_rows(path(pid)) if r["year"] >= SWITCH]
    leads = [_lead(r["cpi"], r["earnings"]) for r in rows]
    G = sum(math.log(1 + r["tl_rate"]) - math.log(1 + r["bp_rate"]) for r in path_rows(path(pid)))
    return {"changes": lead_changes(leads), "below_floor": sum(r["earnings"] < FLOOR for r in rows),
            "price_led": sum(s > 0 for s in leads), "G": G}


def flat_rate_spending(pid, y=FINAL):
    """Basic and new State Pension spending under the triple lock on a single run, £bn."""
    return path(pid)["totals_bn"]["triple_lock"][str(y)]["state_pension_flat_rate"]


def scenario_share(key, y=FINAL):
    """Gross saving as % of basic and new State Pension spending under the triple lock: single runs from their totals,
    the earnings scenarios from the file's own stratified estimate of that share (with its 95% Monte Carlo error)."""
    if key in ("central", "wedge"):
        s = scenario(key)["values"][y][0]
        return 100 * s / flat_rate_spending(key, y), None
    sc = next(v for v in EARNINGS.values() if (v["calendar_earnings_delta"] > 0) == (key == "plus"))
    v = sc["scenario_path_set"]["gross_share_flat_rate_spending_pct"][str(y)]
    return v["mean"], v["plus_minus_95"]


def history_windows():
    """The rule replayed from each earlier start: the level against the triple lock in the last year, the changes of
    lead over the window and the Aprils in which the adjusted rule rose by less than the triple lock."""
    last = str(HISTORY["model_years"][-1])
    out = []
    for g in history_groups():
        first = g["switch_years"][0]
        yrs = [y for y in HISTORY["triple_lock"]["years"] if y >= first]
        leads = [_lead(HISTORY["cpi"][str(y)], HISTORY["earnings"][str(y)]) for y in yrs]
        opened = [y for y in yrs if round(1000 * g["bp_rate"][str(y)]) < round(1000 * g["tl_rate"][str(y)])]
        out.append({"label": g["label"], "first": first, "gap_pct": 100 * (1 - g["ratio"][last]),
                    "changes": lead_changes(leads), "opened": opened, "model": g["model"]})
    return out


# The sampling design behind the earnings scenarios: the model's draws, and the groups by size of the final-year gap
# (one group holds the draws on which the two rules pay the same) from which the fully run paths were sampled.
# The binding release's files (data/pilot/c2-binding); docs/uncertainty holds an earlier rehearsal's.
BINDING = ROOT / "data" / "pilot" / "c2-binding"
DESIGN = json.loads((BINDING / f"{PRIMARY_FORM}.design.json").read_text())
N_POPULATION = DESIGN["n_draws"]
N_GROUPS = len(DESIGN["allocation"]) - 1  # groups by gap size, besides the group where the rules pay the same
assert sum(DESIGN["allocation"].values()) == N_DRAWS


def price_level(y0, y1, pid="central"):
    """Ratio of the price level in calendar year y1 to y0 on a path's applied CPI growth (for deflating cash)."""
    g = path(pid)["applied_growth"]["cpi"]
    f = 1.0
    for y in range(y0 + 1, y1 + 1):
        f *= 1 + g[str(y)]
    return f


# ── Rule arithmetic on the sampled paths of the earnings scenarios (no simulation) ─────────────────────────────
#
# Each earnings scenario's specs file holds the statutory inputs (September CPI, May-July earnings) of every path the
# sampling design ran in full. With the design's group weights, any rule-arithmetic quantity of those inputs has the
# same stratified estimate of its mean over all the model's draws as the fiscal figures do. These are diagnostics of
# the inputs and of the log gap G, not fiscal results; no full run is read and nothing here averages the unshifted
# draws, whose average the registered rule withdrew.

import math as _math
import sys as _sys

import numpy as _np

_sys.path.insert(0, str(ROOT / "src"))
from triple_lock import rules as _rules  # noqa: E402  (the rule arithmetic every run used)
from triple_lock import demography as _demography  # noqa: E402  (the population step every run used)

# The rake of later years' household weights (demography.rake_households): each household's weight stays within
# these multiples of its anchor-year weight, over age-sex cells built from these age bands (two sexes). The prose
# describes the bands as five-year bands below the first single year, single years to the last, then the rest.
RAKE_BOUNDS = _demography.RATIO_BOUNDS
RAKE_CELLS = 2 * len(_demography.AGE_BANDS)
_bands = list(_demography.AGE_BANDS)
RAKE_SINGLE = (min(lo for lo, hi in _bands if hi - lo == 1), max(lo for lo, hi in _bands if hi - lo == 1))
assert [b for b in _bands if b[0] < RAKE_SINGLE[0]] == [(a, a + 5) for a in range(0, RAKE_SINGLE[0], 5)]
RAKE_OLD = [b for b in _bands if b[0] > RAKE_SINGLE[1]]  # [(80, 85), (85, 90), (90, 106)]: 80-84, 85-89, 90+
assert RAKE_OLD[0][0] == RAKE_SINGLE[1] + 1 and RAKE_OLD[-1][1] > 100
# Each fiscal year's population: three quarters of its first mid-year and a quarter of the next.
assert _demography.fiscal_population(0, {0: 1.0, 1: 0.0}) == 0.75

_W = {int(k): v for k, v in DESIGN["stratum_weights"].items()}
_SAMPLE = {int(k): v for k, v in DESIGN["sample"].items()}
SIM_KEYS = {"minus": "earnings_minus_0_5pp", "plus": "earnings_plus_0_5pp"}
FORWARD = [y for y in YEARS if y > SWITCH]  # the Aprils 2031-2039, when the rules can first differ


def _lead_sign_changes(sign):
    """Changes of sign along one path; a tie keeps the previous lead (ts_backtest.switches)."""
    n, prev = 0, 0
    for s in sign:
        if s == 0:
            continue
        if prev and s != prev:
            n += 1
        prev = s
    return n


def _slot(spec):
    c = _np.array([spec["statutory_cpi"][str(y - 1)] for y in YEARS])
    e = _np.array([spec["statutory_earnings"][str(y - 1)] for y in YEARS])
    tl = _rules.rates_matrix("triple_lock", c, e, YEARS, RATE_DECIMALS)[0]
    bp = _rules.rates_matrix("burnham_2030", c, e, YEARS, RATE_DECIMALS)[0]
    cr, er = _rules.round_rate(c, RATE_DECIMALS), _rules.round_rate(e, RATE_DECIMALS)
    lg = _np.log1p(tl) - _np.log1p(bp)
    after = _np.array([y >= SWITCH for y in YEARS])
    fwd = _np.array([y in FORWARD for y in YEARS])
    late = _np.array([y >= 2034 for y in YEARS])  # after the OBR's long-term premium is fully in
    m = _np.maximum(cr, FLOOR)
    return {
        "c": cr, "e": er,
        "G": {y: float(lg[: j + 1].sum()) for j, y in enumerate(YEARS)},
        "y": float((_np.log1p(tl) - _np.log1p(er))[after].sum()),  # the triple lock's excess over earnings
        "below": float((er[fwd] < FLOOR).mean()),  # share of the Aprils 2031-2039 with earnings below the floor
        "switch": _lead_sign_changes(_np.sign(er - cr)) / (len(YEARS) - 1),  # CPI against earnings, per transition
        "switch_floor": _lead_sign_changes(_np.sign(er - m)[after]) / (after.sum() - 1),
        "premium": float((tl - er)[late].mean()),  # the triple lock's rate less May-July earnings, April 2034-2039
        "earn_fwd": float(er[fwd].mean()),
    }


def _slots(key):
    specs = {s["id"]: s for s in json.loads((BINDING / f"{SIM_KEYS[key]}.specs.json").read_text())}
    return {h: [_slot(specs[f"draw_{i}"]) for i in ids] for h, ids in _SAMPLE.items()}


SIM = {k: _slots(k) for k in SIM_KEYS}


def sim_mean(key, f):
    """Stratified estimate of the mean of f(slot) over the model's draws, and its 95% Monte Carlo margin."""
    g = SIM[key]
    mean = sum(_W[h] * _np.mean([f(s) for s in g[h]], axis=0) for h in g)
    var = sum(_W[h] ** 2 * _np.var([f(s) for s in g[h]], axis=0, ddof=1) / len(g[h]) for h in g if len(g[h]) > 1)
    return mean, 1.96 * _np.sqrt(var)


def sim_paired(f):
    """The plus scenario less the minus one, slot by slot on the shared draws: stratified mean and 95% margin."""
    g1, g0 = SIM["plus"], SIM["minus"]
    d = {h: [f(a) - f(b) for a, b in zip(g1[h], g0[h])] for h in g1}
    mean = sum(_W[h] * _np.mean(d[h]) for h in d)
    var = sum(_W[h] ** 2 * _np.var(d[h], ddof=1) / len(d[h]) for h in d if len(d[h]) > 1)
    return float(mean), float(1.96 * _np.sqrt(var))


def sim_mean_inputs(key):
    """Mean September CPI and May-July earnings growth setting each April, over the scenario's draws."""
    c, _ = sim_mean(key, lambda s: s["c"])
    e, _ = sim_mean(key, lambda s: s["e"])
    return {y: (float(c[j]), float(e[j])) for j, y in enumerate(YEARS)}


def sim_mean_path_gap(key, y=FINAL):
    """G on the single path through the scenario's mean inputs: the gap with the year-to-year variation removed."""
    mi = sim_mean_inputs(key)
    c = _np.array([mi[t][0] for t in YEARS])
    e = _np.array([mi[t][1] for t in YEARS])
    tl = _rules.rates_matrix("triple_lock", c, e, YEARS, RATE_DECIMALS)[0]
    bp = _rules.rates_matrix("burnham_2030", c, e, YEARS, RATE_DECIMALS)[0]
    j = YEARS.index(y)
    return float((_np.log1p(tl) - _np.log1p(bp))[: j + 1].sum())


def _kish(w):
    return float(w.sum() ** 2 / (w ** 2).sum())


def sim_tilt(key, target, hold_mean=False, y=FINAL):
    """Exponential tilting of the sampled paths so that their share of Aprils 2031-2039 with earnings below the floor
    equals ``target`` (and, with ``hold_mean``, so that their mean May-July earnings growth over those Aprils stays as
    it was). Returns None when no finite tilt meets the targets (the targets lie outside the sampled paths' hull)."""
    g = SIM[key]
    slots = [(_W[h] / len(g[h]), s) for h in g for s in g[h]]
    w0 = _np.array([a for a, _ in slots])
    w0 = w0 / w0.sum()
    X = _np.array([[s["below"], s["earn_fwd"]] for _, s in slots])
    t = _np.array([target, float(w0 @ X[:, 1])])
    if not hold_mean:
        X, t = X[:, :1], t[:1]
    lam = _np.zeros(X.shape[1])
    # A finite tilt exists only if the targets lie strictly inside the convex hull of the sampled paths' values: in
    # every direction some path lies beyond them (checked on a fine grid of directions, scaled to the two units).
    sc = X.std(axis=0)
    ang = _np.linspace(0, 2 * _math.pi, 3600, endpoint=False)
    dirs = _np.stack([_np.cos(ang), _np.sin(ang)], 1)[:, : X.shape[1]] if X.shape[1] == 2 else _np.array([[1.0], [-1.0]])
    if not _np.all((dirs @ ((X - t) / sc).T).max(axis=1) > 0):
        return None

    def obj(l):
        with _np.errstate(over="ignore"):
            v = float(w0 @ _np.exp((X - t) @ l))
        return _math.log(v) if 0 < v < _math.inf else _math.inf

    for _ in range(200):
        with _np.errstate(over="ignore", invalid="ignore"):
            w = w0 * _np.exp((X - t) @ lam)
            w = w / w.sum()
        grad = w @ (X - t)
        cov = ((X - t) * w[:, None]).T @ (X - t) - _np.outer(grad, grad)
        if not _np.all(_np.isfinite(cov)):
            return None
        step = _np.linalg.solve(cov + 1e-12 * _np.eye(len(lam)), grad)
        a = 1.0
        while obj(lam - a * step) > obj(lam) and a > 1e-8:
            a /= 2
        lam = lam - a * step
    with _np.errstate(over="ignore", invalid="ignore"):
        w = w0 * _np.exp((X - t) @ lam)
        w = w / w.sum()
    if not _np.all(_np.isfinite(w)) or _np.max(_np.abs(w @ X - t)) > 1e-6:
        return None
    G = _np.array([s["G"][y] for _, s in slots])
    Y = _np.array([s["y"] for _, s in slots])
    return {"G": float(w @ G), "G0": float(w0 @ G), "y": float(w @ Y), "y0": float(w0 @ Y),
            "share": float(w @ (1 - _np.exp(-G))), "share0": float(w0 @ (1 - _np.exp(-G))),
            "kish": _kish(w), "kish0": _kish(w0),
            "earn": float(w @ _np.array([s["earn_fwd"] for _, s in slots])),
            "earn0": float(w0 @ _np.array([s["earn_fwd"] for _, s in slots]))}


def path_excess(pid):
    """(G, y) on a full-run path: the log gap between the rules in the final year and the triple lock's log excess
    over its earnings path from the switch (rule arithmetic on the path's own rates and rounded inputs)."""
    rows = path_rows(path(pid))
    G = sum(_math.log1p(r["tl_rate"]) - _math.log1p(r["bp_rate"]) for r in rows)
    y = sum(_math.log1p(r["tl_rate"]) - _math.log1p(float(_rules.round_rate(r["earnings"], RATE_DECIMALS)))
            for r in rows if r["year"] >= SWITCH)
    return G, y


def history_excess():
    """(G, y) on the replay from the earliest start that changes anything, to the last April."""
    g = next(x for x in history_groups() if x["changes"])
    yrs = [y for y in HISTORY["triple_lock"]["years"] if y >= g["switch_years"][0]]
    G = sum(_math.log1p(g["tl_rate"][str(y)]) - _math.log1p(g["bp_rate"][str(y)]) for y in yrs)
    y_ = sum(_math.log1p(g["tl_rate"][str(y)]) - _math.log1p(float(_rules.round_rate(HISTORY["earnings"][str(y)],
                                                                                        RATE_DECIMALS)))
             for y in yrs)
    return G, y_


def wedge_split():
    """The OBR long-term path's G in the final year as the central path's gap plus the log excess of the OBR's
    long-term triple-lock rate over May-July earnings from April 2032, and the range of that yearly excess once the
    premium is fully in (April 2034 on)."""
    rows = path_rows(path("wedge"))
    ex = {r["year"]: _math.log1p(r["tl_rate"]) - _math.log1p(float(_rules.round_rate(r["earnings"], RATE_DECIMALS)))
          for r in rows if r["year"] >= OBR_LT_FROM}
    Gc = path_excess("central")[0]
    late = [r["tl_rate"] - float(_rules.round_rate(r["earnings"], RATE_DECIMALS)) for r in rows if r["year"] >= 2034]
    return {"central": Gc, "rest": sum(ex.values()), "total": Gc + sum(ex.values()),
            "late_min": min(late), "late_max": max(late), "late_mean": sum(late) / len(late)}


def rounding_gap(pid):
    """How much of a full-run path's final-year G the rounding up of the top-up adds: G as run less G with the same
    rounded inputs and rates but the top-up to the earnings path left unrounded (rule arithmetic)."""
    rows = path_rows(path(pid))
    level = anchor = 1.0
    exact = 0.0
    for r in rows:
        tl = r["tl_rate"]
        if r["year"] < SWITCH:
            rate = tl
            level *= 1 + rate
            anchor = level
        else:
            anchor *= 1 + float(_rules.round_rate(r["earnings"], RATE_DECIMALS))
            floor_rate = max(float(_rules.round_rate(r["cpi"], RATE_DECIMALS)), FLOOR)
            rate = max(floor_rate, anchor / level - 1)
            level *= 1 + rate
        exact += _math.log1p(tl) - _math.log1p(rate)
    return path_excess(pid)[0] - exact


OBR_LT_FROM = 2032  # the first April whose inputs the central path takes from the OBR's long-term determinants
HANDOFF = json.loads((BINDING / "handoff.json").read_text())
OBR_PREMIUM_2034_2039 = HANDOFF["obr_2034_2039_premium_pp"]  # the OBR long-term rate less fiscal-year earnings, points


# ── Round 3 of review: official trajectories, the expected gap under independent differences, diagnostics ────────


import csv as _csv

# Budget 2026 Chart 5.1, digitised from its vector file (scripts/digitise_budget_chart.py): State Pension spending as
# a share of GDP under each rule, the government's central forecast, by fiscal year. Drawing precision about 0.01
# points of GDP; the Budget publishes no table of these values.
CHART_5_1 = {int(r["fiscal_year_start"]): (float(r["triple_lock_pct_gdp"]), float(r["adjusted_pct_gdp"]))
             for r in _csv.DictReader((ROOT / "data" / "benchmarks" / "budget_2026_chart_5_1.csv").open())}


def chart_share(y):
    """The adjusted rule's spending below the triple lock's on Chart 5.1 in fiscal year y, as a share (0-1)."""
    tl, adj = CHART_5_1[y]
    return 1 - adj / tl


def chart_first_differ():
    return min(y for y, (a, b) in CHART_5_1.items() if round(a, 2) != round(b, 2))


# The OBR's October 2026 outlook, paragraphs 3.50-3.54, verbatim from the PDF (data/raw).
EFO_TEXT = re.sub(r"\s+", " ", (ROOT / "data" / "raw" / "efo-october-2026-paras-3-50-3-54.txt").read_text())


def efo_replay_pcts():
    """Para 3.51: payments under the adjusted rule on average (a)% lower than under the triple lock and (b)% higher
    than under earnings uprating, 1990-2025."""
    m = re.search(r"on average ([\d.]+) per cent lower each year than under the current triple lock and ([\d.]+) per "
                  r"cent higher than under earnings uprating", EFO_TEXT)
    return float(m.group(1)), float(m.group(2))


def efo_debt_pcts():
    """Para 3.52: debt in 2075-76 about (a)% of GDP lower than under the triple lock and (b)% of GDP higher than under
    earnings uprating."""
    a = re.search(r"reduce the projected long-term increase in debt by around (\d+) per cent of GDP in 2075-76", EFO_TEXT)
    b = re.search(r"Debt would be around (\d+) per cent of GDP higher in the long-term than under an earnings", EFO_TEXT)
    return float(a.group(1)), float(b.group(1))


EFO_CARE = re.search(r"the Government stated its intention to expand state provision of social care", EFO_TEXT).group(0)


def _npos(m, s):
    """E[X+] for X ~ N(m, s^2)."""
    from statistics import NormalDist
    if s <= 0:
        return max(m, 0.0)
    n = NormalDist()
    return m * n.cdf(m / s) + s * n.pdf(m / s)


def spitzer_gap(mu, sigma, n):
    """E[G_n] and E[y_n] when the yearly differences d are independent N(mu, sigma^2): Spitzer's identity gives
    E[x_n] = sum_k E[(D_k)+]/k, so E[G_n] = sum_k (E[d+] - E[(D_k)+]/k), and E[y_n] = n E[d+]."""
    ey = n * _npos(mu, sigma)
    ex = sum(_npos(k * mu, _math.sqrt(k) * sigma) / k for k in range(1, n + 1))
    return ey - ex, ey


def _d(cpi, earnings):
    return _math.log1p(max(float(_rules.round_rate(cpi, RATE_DECIMALS)), FLOOR)) - \
        _math.log1p(float(_rules.round_rate(earnings, RATE_DECIMALS)))


def history_d():
    """The yearly differences d_t on the replay's inputs, from its earliest start that changes anything to the last
    April (April 2022 as the law applied it), and their mean and standard deviation."""
    g = next(x for x in history_groups() if x["changes"])
    yrs = [y for y in HISTORY["triple_lock"]["years"] if y >= g["switch_years"][0]]
    d = [_d(HISTORY["cpi"][str(y)], HISTORY["earnings"][str(y)]) for y in yrs]
    return d, float(_np.mean(d)), float(_np.std(d, ddof=1))


def sim_d_moments(key):
    """Mean and standard deviation of d_t over the scenario's paths and the Aprils from the switch to the final year,
    pooled (stratified weights)."""
    after = _np.array([y >= SWITCH for y in YEARS])
    dd = lambda s: _np.log1p(_np.maximum(s["c"], FLOOR))[after] - _np.log1p(s["e"])[after]
    m1, _ = sim_mean(key, lambda s: float(dd(s).mean()))
    m2, _ = sim_mean(key, lambda s: float((dd(s) ** 2).mean()))
    return float(m1), float(_math.sqrt(m2 - m1 ** 2)), int(after.sum())


def sim_ratio_per_path(key):
    """Stratified mean over paths with a positive excess of the per-path share G/y removed, final year."""
    g = SIM[key]
    num = sum(_W[h] * _np.mean([s["G"][FINAL] / s["y"] if s["y"] > 1e-12 else 0.0 for s in g[h]]) for h in g)
    den = sum(_W[h] * _np.mean([1.0 if s["y"] > 1e-12 else 0.0 for s in g[h]]) for h in g)
    return float(num / den)


def sim_hold_inputs(years=(2030, 2031), source="minus"):
    """The earnings scenarios recomputed with May-July earnings setting the given Aprils held, path by path, at the
    ``source`` scenario's values, so that both scenarios share those inputs: G in the final year for each, and the
    paired share difference in the middle and final years (rule arithmetic)."""
    specs = {k: {s["id"]: s for s in json.loads((BINDING / f"{SIM_KEYS[k]}.specs.json").read_text())} for k in SIM_KEYS}
    out = {}
    for k in SIM_KEYS:
        groups = {}
        for h, ids in _SAMPLE.items():
            rows = []
            for i in ids:
                sp = json.loads(json.dumps(specs[k][f"draw_{i}"]))
                for y in years:
                    sp["statutory_earnings"][str(y - 1)] = specs[source][f"draw_{i}"]["statutory_earnings"][str(y - 1)]
                rows.append(_slot(sp))
            groups[h] = rows
        out[k] = groups

    def mean(g, f):
        return float(sum(_W[h] * _np.mean([f(s) for s in g[h]]) for h in g))

    def paired(f):
        d = {h: [f(a) - f(b) for a, b in zip(out["plus"][h], out["minus"][h])] for h in out["plus"]}
        m = sum(_W[h] * _np.mean(d[h]) for h in d)
        v = sum(_W[h] ** 2 * _np.var(d[h], ddof=1) / len(d[h]) for h in d if len(d[h]) > 1)
        return float(m), float(1.96 * _np.sqrt(v))

    return {"G": {k: mean(out[k], lambda s: s["G"][FINAL]) for k in out},
            "pair": {y: paired(lambda s, y=y: 1 - _math.exp(-s["G"][y])) for y in (DIST_YEARS[0], FINAL)}}


def floor_years_distinct(test="A"):
    """The determination years the test's four-year windows cover, the ones in which May-July earnings growth was below
    the floor, and the model's expected count over those distinct years (each year's expected share averaged over the
    windows that cover it; April 2022's earnings leg as the law applied it)."""
    scores = json.loads((BINDING / "scores.json").read_text())
    rows = [r for r in scores["rows"] if r["form"] == PRIMARY_FORM and r["treatment"] == "suspended"
            and r["origin"] in C2["origins"][test]]
    cover = {}
    for r in rows:
        for y in r["target_years"]:
            cover.setdefault(y, []).append(r["predicted_floor_frequency"])
    years = sorted(cover)
    # May-July earnings of determination year y set April y+1; the last, May-July 2026, sets April 2027.
    earn = {**{int(k) - 1: v for k, v in HISTORY["earnings"].items()},
            2026: CENTRAL["path"]["april_2027_inputs"]["earnings"]}
    below = [y for y in years if earn[y] < FLOOR]
    # Each window's realised share must match the years counted here.
    assert all(abs(sum(y in below for y in r["target_years"]) / len(r["target_years"]) - r["realised_floor_frequency"])
               < 1e-9 for r in rows)
    expected = sum(sum(v) / len(v) for v in cover.values())
    return years, below, expected


def wedge_from(first=SWITCH + 1):
    """The OBR long-term path with the premium paid in full from April ``first`` instead of phased in from April 2032:
    the triple lock pays the higher of its own rate on the path and May-July earnings plus the full premium (the path's
    own premium once fully in, to the rule's 0.1 point), the adjusted rule as on the path. Returns G and y in the final
    year and the ratio of the triple lock's final-year level to the path's (rule arithmetic; spending scales with the
    level, caseload held)."""
    rows = path_rows(path("wedge"))
    prem = wedge_split()["late_mean"]
    G = y = lv = 0.0
    for r in rows:
        tl = r["tl_rate"]
        if r["year"] >= first:
            e = float(_rules.round_rate(r["earnings"], RATE_DECIMALS))
            tl = max(tl, float(_rules.round_rate(e + prem, RATE_DECIMALS)))
        lv += _math.log1p(tl) - _math.log1p(r["tl_rate"])
        G += _math.log1p(tl) - _math.log1p(r["bp_rate"])
        if r["year"] >= SWITCH:
            y += _math.log1p(tl) - _math.log1p(float(_rules.round_rate(r["earnings"], RATE_DECIMALS)))
    return {"G": G, "y": y, "level": _math.exp(lv)}


def last_price_led(pid):
    """The last April from the switch to the final year in which the higher of CPI and the floor beat earnings."""
    rows = [r for r in path_rows(path(pid)) if r["year"] >= SWITCH]
    led = [r["year"] for r in rows if _lead(r["cpi"], r["earnings"]) > 0]
    return led[-1] if led else None


def record_lead_changes(as_law=True):
    """Changes of lead per April transition in the inputs that set the April 2011-2026 rises, counted on d_t (earnings
    against the higher of CPI and the floor); April 2022 as the law applied it, or on the published earnings."""
    yrs = HISTORY["triple_lock"]["years"]
    e = {str(y): (HISTORY["earnings"][str(y)] if as_law else HISTORY["triple_lock"]["earnings_published"][str(y)])
         for y in yrs}
    leads = [_lead(HISTORY["cpi"][str(y)], e[str(y)]) for y in yrs]
    return lead_changes(leads) / (len(yrs) - 1)
CHART_PRECISION = 0.01  # points of GDP: the drawing precision of the digitised Chart 5.1


# ── Results under stated volatility (V1): a conditional sensitivity ─────────────────────────────────────────────
# docs/METHOD.md, "Conditional volatility bands (V1)": pushed before the first V1 code and figures; the public record
# shows that order and no more (its Record of order), and the spans were chosen after seeing the inputs' standard
# deviations over several spans and both models' results (its Changes of 12 November 2026). Not a registration and
# not output of either registered model (C2, C4): rule arithmetic on paths centred on the OBR central path, whose
# deviations follow a stated span of past statutory inputs, under two settings that the paper always shows together.
# Cash comes from the identity gross = share x B x (path TL level / central TL level), which reproduces every stored
# microsimulation run (data/v1/identity_check.json); net is gross times the stored runs' net/gross ratio.
V1_DIR = ROOT / "data" / "v1"
V1 = json.loads((V1_DIR / "bands.json").read_text())
V1_IDENTITY = json.loads((V1_DIR / "identity_check.json").read_text())
assert "not a calibrated forecast" in V1["label"] and "not output of the C2 or C4 models" in V1["label"]
assert V1["no_microsimulation"] is True and V1["antithetic"] is True
V1_SETTINGS = ("a", "b")  # always shown together
V1_LABEL = {k: V1["settings"][k]["label"].replace("-", "–") for k in V1_SETTINGS}
V1_EXCLUDED = V1["settings"]["b"]["excluded_years"]
V1_PATHS = V1["n_paths"]
V1_RHO = V1["net_ratio"]
V1_QS = (5, 25, 50, 75, 95)
V1_KAC3_FROM = min(int(y) for y, r in V1["series"].items() if r["earnings_source"].startswith("KAC3"))


def v1(setting, year, measure="gross_bn", stat="p50"):
    """One summary of V1 for a setting ("a", "b"), an April year (fiscal year), a measure (G, share, gross_bn,
    net_bn) and a statistic (mean, p5, p25, p50, p75, p95)."""
    return V1["settings"][setting]["by_year"][str(year)][measure][stat]


def v1_same(setting, year):
    """Share of V1 paths on which the two rules pay the same rate in every April to ``year``."""
    return V1["settings"][setting]["pay_same_share"][str(year)]


def v1_param(setting, what, variable=None):
    s = V1["settings"][setting]
    return s[what] if variable is None else s[what][variable]


def v1_identity_max_bn():
    """The largest error of the cash identity on any stored run or stored scenario mean, £bn."""
    single = max(r["max_abs_gross_error_bn"] for r in V1_IDENTITY["single_path_runs"].values())
    sc = max(r["max_abs_stratified_mean_error_bn"] for r in V1_IDENTITY["earnings_scenarios_stratified_means"].values())
    return max(single, sc)


# Robustness of V1 (scripts/v1_robustness.py, docs/METHOD.md V1 Changes of 12 November 2026): each run changes one
# stated assumption with V1's own draws and arithmetic; none is a third setting.
V1_ROBUST = json.loads((V1_DIR / "robustness.json").read_text())
assert V1_ROBUST["n_paths"] == V1_PATHS and V1_ROBUST["final_year"] == FINAL
VARIABLES_V1 = ("cpi", "earnings")
# The higher innovation correlation tried, near the OBR's forecast errors' (scripts/v1_robustness.py).
V1_CORR_HIGH = max(float(r.rsplit("_", 1)[1]) for r in V1_ROBUST["runs"]["a"]
                   if r.startswith("innovation_correlation_"))


def v1_robust(setting, run, stat="p50"):
    """Final-year gross saving, £bn, of one robustness run for a setting."""
    return V1_ROBUST["runs"][setting][run]["gross_bn"][stat]


def v1_robust_move(runs, stat="p50"):
    """The largest absolute change, £bn, of a final-year gross statistic from the setting's own, over the named runs
    and every setting that has them."""
    return max(abs(v1_robust(k, r, stat) - v1(k, FINAL, "gross_bn", stat))
               for k in V1_SETTINGS for r in runs if r in V1_ROBUST["runs"][k])


def v1_robust_share(setting, run):
    """Final-year median share of spending saved, as a fraction, of one robustness run."""
    return V1_ROBUST["runs"][setting][run]["share_p50"]


def v1_input_sd_range(setting):
    """(min, max) over the determination years 2027-2038 and both inputs of V1's statutory input sd, as a fraction."""
    sd = V1_ROBUST["statutory_input_sd_by_year"][setting]
    vals = [x for v in VARIABLES_V1 for x in sd[v]]
    return min(vals), max(vals)



def v1_obr_errors(kind):
    """The OBR spring forecasts' errors one to four years ahead: (sd min, sd max, corr min, corr max), sd as a fraction.
    kind "calendar": calendar-year CPI and earnings growth (data/obr_forecast_error_summary.csv); "statutory": September
    CPI and May-July earnings growth less the forecast for the same year."""
    E = V1_ROBUST["obr_forecast_errors"]
    hs = ("1", "2", "3", "4")
    if kind == "calendar":
        c = E["calendar_year_summary"]["spring_vintages"]
        sds = [c[v][h]["sd"] for v in VARIABLES_V1 for h in hs]
        cors = [c["cpi"][h]["corr_cpi_earnings"] for h in hs]
    else:
        b = E["statutory_spring"]["by_horizon"]
        sds = [b[h]["sd"][v] for v in VARIABLES_V1 for h in hs]
        cors = [b[h]["corr_cpi_earnings"] for h in hs]
    return min(sds), max(sds), min(cors), max(cors)


def v1_se(setting, year, stat):
    """Batch-means Monte Carlo standard error, £bn, of a gross-saving percentile (p5, p50, p95)."""
    return V1["settings"][setting]["gross_bn_mc_se"][str(year)][stat]


def v1_above_largest_run(setting, year):
    """Share of V1 paths whose gross saving exceeds the largest stored microsimulation run's."""
    return V1["settings"][setting]["share_gross_above_max_stored"][str(year)]


# ── The Bayesian forecast of the uprating inputs (B1): the paper's headline ──────────────────────────────────────
# docs/METHOD.md, "Bayesian forecast of the uprating inputs (B1)", with its record of order, results, the supplementary
# runs registered after an independent review and the erratum of 12 November 2026. The headline stands on Max's ruling
# of that day, not on a test: B1 was designed after the first two models failed their tests and V1 was seen. Every
# figure is rule arithmetic and the cash identity on 399,440 posterior predictive paths; no microsimulation. The mean
# and the largest path saving are not exposed: the lower tail of the forward inputs is heavier than the record, so the
# paper quotes percentiles and probabilities only.
B1_DIR = ROOT / "data" / "b1"
B1 = json.loads((B1_DIR / "forecast.json").read_text())
B1_FIT = json.loads((B1_DIR / "fit.json").read_text())
B1_VAL = json.loads((B1_DIR / "validation.json").read_text())
B1_BT = json.loads((B1_DIR / "backtest.json").read_text())
B1_SENS = json.loads((B1_DIR / "sensitivity.json").read_text())
B1_SUP = json.loads((B1_DIR / "supplementary.json").read_text())
assert B1["no_microsimulation"] is True and B1_FIT["headline_permitted"] is True
assert B1_FIT["convergence"]["gate_met"] and all(r.get("gate_met", True) for r in B1_SENS["runs"].values())
assert B1_SUP["status"] == "sensitivities and diagnostics; none replaces the headline"
B1_QS = ("p5", "p25", "p50", "p75", "p95")
B1_PATHS = B1["n_paths"]
B1_DRAWS = B1["n_draws"]
B1_RHO = B1["net_ratio"]
B1_THRESHOLDS = (5, 10)  # £bn: the probabilities the paper reports besides any saving


def b1(year, measure="gross_bn", stat="p50"):
    """One B1 percentile for a fiscal year (its first calendar year): measure gross_bn, net_bn, share or G."""
    if stat not in B1_QS:
        raise ValueError("the paper quotes B1 percentiles only, never the mean or the largest path")
    return B1["by_year"][str(year)][measure][stat]


def b1_prob(year, threshold=0, kind="gross"):
    """Posterior predictive probability that the saving exceeds ``threshold`` £bn (0: any saving)."""
    return B1["by_year"][str(year)]["probability"][kind][f"above_{threshold}"]


def b1_real(year, stat="p50"):
    """Gross saving at the central path's levels (without the path's triple-lock level against the central path's)."""
    if stat not in B1_QS:
        raise ValueError("percentiles only")
    return B1_SUP["d_real_terms_and_share"]["by_year"][str(year)]["real_gross_bn"][stat]


def b1_real_prob(year, threshold):
    return B1_SUP["d_real_terms_and_share"]["by_year"][str(year)]["real_probability"][f"above_{threshold}"]


def b1_level_ratio(year, stat="p50"):
    """The path's triple-lock level against the central path's, the factor between cash and central-level savings."""
    return B1_SUP["d_real_terms_and_share"]["by_year"][str(year)]["tl_index_ratio"][stat]


def b1_se(year, key):
    """Batch-means Monte Carlo standard error: gross_p5, gross_p50, gross_p95 (£bn) or a probability."""
    return B1["monte_carlo_se"][str(year)][key]


def b1_param(name, stat="p50"):
    """Posterior summary of a derived parameter (phi_cc, phi_ee, phi_ec, phi_ce, sigma_c, sigma_e, rho_F, nu, ...)."""
    return B1_FIT["posterior"][name][stat]


def b1_run(sid, year=None, stat="p50", prob=None):
    """A registered sensitivity run S1-S15: gross percentile, or the probability above ``prob`` £bn."""
    r = B1_SENS["runs"][sid][str(year or FINAL)]
    return r["gross_bn"][stat] if prob is None else r["probability"]["gross"][f"above_{prob}"]


def b1_sup(key, year=None, stat="p50", prob=None):
    """A supplementary run's gross percentile or probability. key: a1, a2, a3, c, g, h1, h2, or b_<prior run>."""
    S = B1_SUP
    where = {"a1": S["a_basis_split"]["a1_calendar_errors_no_basis"],
             "a2": S["a_basis_split"]["a2_calendar_errors_plus_basis"], "a3": S["a3_statutory_same_cells"],
             "c": S["c_bounded_inputs"]["report"], "g": S["g_delta_times_4"],
             "h1": S["h_horizons"]["h1_only"], "h2": S["h_horizons"]["h2plus_only"]}
    r = (where[key] if key in where else S["b_prior_runs"][key])[str(year or FINAL)]
    return r["gross_bn"][stat] if prob is None else r["probability"][f"above_{prob}"]


B1_PRIOR_RUNS = tuple(B1_SUP["b_prior_runs"])
B1_REG_PRIOR_RUNS = ("S1", "S2", "S3", "S4", "S5", "S6", "S8", "S9")


def b1_prior_range(year=None):
    """Lowest and highest gross median over every prior run: the registered S1-S6, S8, S9 and the supplementary (b).

    Supplementary run (g), the long-run shift's standard deviations quadrupled, is a diagnostic the analysis plan keeps
    out of the registered prior range (S8 removes the shift and S9 doubles it), so it is not in this range; the paper
    states it beside the range."""
    v = [b1_run(s, year) for s in B1_REG_PRIOR_RUNS] + [b1_sup(k, year) for k in B1_PRIOR_RUNS]
    return min(v), max(v)


def b1_all_range(year=None):
    """Lowest and highest gross median over S1-S15 and every supplementary run."""
    keys = ("a1", "a2", "a3", "c", "g", "h1", "h2") + B1_PRIOR_RUNS
    v = [b1_run(s, year) for s in B1_SENS["runs"]] + [b1_sup(k, year) for k in keys]
    return min(v), max(v)


def b1_basis_share():
    """£bn of the final-year median that the statutory-minus-calendar basis carries: (headline less a1, a3 less a1)."""
    a1 = b1_sup("a1")
    return b1(FINAL) - a1, b1_sup("a3") - a1


def b1_below_zero(variable):
    """Share of forward path-years with the statutory input below zero, and the record's count of such years."""
    c = B1_SUP["c_bounded_inputs"]
    return (c["share_of_path_years_below_zero"][variable], c["history_years_below_zero_1989_2025"][variable],
            c["history_years"])


def b1_floor_bias(hold_out):
    """Test A's floor bias over the path seeds (min, max), the number of seeds and the number passing C4's rule."""
    r = B1_SUP["f_backtest_path_seeds"][hold_out]
    return r["floor_bias_range"][0], r["floor_bias_range"][1], len(r["by_path_seed"]), r["seeds_passing"]


def b1_check(hold_out, test, check):
    """One check of the registered backtest: (value, limit, passes)."""
    c = next(c for c in B1_BT["hold_outs"][hold_out]["checks_against_c2_c4_limits"]
             if c["test"] == test and c["check"] == check)
    return c["value"], c["limit"], c["passes"]


def b1_ppc(stat):
    """A registered posterior predictive statistic of the error record: realised, replicated median, share at or above."""
    s = B1_VAL["replicated_error_records"]["statistics"][stat]
    return s["realised"], s["replicated_p50"], s["share_at_or_above_realised"]


B1_PPC_OUTSIDE = B1_VAL["replicated_error_records"]["outside_central_98"]
B1_PPC_BAND = 98  # per cent: the central band of replications the analysis plan names
B1_GAP_PPC = B1_SUP["e_gap_spread_post_hoc"]["by_horizon"]  # post hoc
B1_HIST = B1_SUP["headline_2039_histogram"]
assert B1_HIST["paths"] == B1_PATHS


# The convergence gate as first coded (docs/METHOD.md, B1 record of order): divergent transitions on the first fit and
# on the rerun the gate allows, read from the record; the rerun's count is also in gate_record.json.
_B1_RECORD = (ROOT / "docs" / "METHOD.md").read_text()
B1_WALL_DIV = tuple(int(x) for x in re.search(r"with (\d+) transitions flagged divergent against the gate's 10; the "
                                               r"rerun.*?and (\d+) flagged", _B1_RECORD, re.S).groups())
B1_GATE = json.loads((B1_DIR / "gate_record.json").read_text())
assert str(B1_WALL_DIV[1]) in B1_GATE["wall_coded"]["fit"]


def b1_prob_above(threshold_bn):
    """Share of the headline's paths whose 2039-40 gross saving exceeds ``threshold_bn``, from the stored histogram.

    The histogram (supplementary.json, a presentation of the stored forecast) counts paths in £0.5bn bands from zero,
    with the paths that save nothing apart and those beyond its last edge in one count, so the threshold must be a band
    edge; tests check that it reproduces the forecast's own probabilities above £5bn and £10bn."""
    h = B1_HIST
    if threshold_bn not in h["edges_bn"]:
        raise ValueError(f"£{threshold_bn}bn is not an edge of the histogram's £{h['bin_bn']}bn bands")
    i = h["edges_bn"].index(threshold_bn)
    return (sum(h["counts"][i:]) + h["beyond_last_edge"]) / h["paths"]


def b1_record():
    """The forecast-error record as the fit used it: its last origin, and each target year with a single cell, with
    that cell's origin and horizon (the spring forecasts in data/obr_forecast_errors.csv at the fit's origins)."""
    data = B1_FIT["data"]
    origins = data["error_origins"]
    single = sorted(int(t) for t, n in data["error_cells_by_target_year"].items() if n == 1)
    rows = {}
    with open(ROOT / "data" / "obr_forecast_errors.csv") as f:
        for r in _csv.DictReader(f):
            v, t, h = int(r["year_forecast_made"]), int(r["target_year"]), int(r["horizon_years"])
            if v in origins and h <= 4 and t in single:
                rows.setdefault(t, set()).add((v, h))
    for t in single:
        assert len(rows[t]) == 1, (t, rows.get(t))
    assert origins == list(range(origins[0], origins[-1] + 1))
    return {"first_origin": origins[0], "last_origin": origins[-1],
            "single_cell": {t: next(iter(rows[t])) for t in single}}
