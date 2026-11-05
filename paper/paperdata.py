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
         11: "eleven", 12: "twelve", 13: "thirteen"}


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

    The OBR central forecast and the OBR long-term path are single full runs (no Monte Carlo error). The two earnings
    scenarios are averages over the same 160 simulated draws with calendar earnings growth moved from a given year;
    their margin is the file's 95% Monte Carlo error, which measures path sampling only. None is a probability
    interval, and no average of the unshifted draws is published (the registered rule withdrew it)."""
    out = []
    c = CENTRAL["run"]["saving_bn"]
    out.append({"key": "central", "name": "OBR central forecast", "kind": "single run",
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
    "pa_frozen_to": 2030,
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


FORM_NAMES = {"monthly_var1_boot": "Monthly (used here)", "monthly_var2_boot": "Monthly, two lags",
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
