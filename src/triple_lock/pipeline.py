"""The build: every section of the results file, each figure from full PolicyEngine UK runs.

Sections
--------
* ``central``: the central path (central.py) and its full run (engine.run_path):
  savings by year, gross and net with their components, households affected,
  household tables, poverty, and how much the single survey household that moves
  the net figure most contributes (never its identifier, weight or amounts: see
  redact_records).
* ``expected_value``: the calibrated distribution of paths and the stratified
  sample of full runs (expected_value.py), on the certified Enhanced FRS and, as
  a paired sensitivity, Microcosm.
* ``trajectories``: a few paths we fully understand, past years and the method
  backtests (trajectories.py).
* ``coverage``: what each dataset holds in 2026-27 against DWP's tables.
* ``benchmarks``: published costings paired with the closest figure here.
* ``assumptions``: what the headline figures are conditional on, worded here from the model's configuration and
  the results above, for the dashboard's "What these figures assume" strip.

Model jobs are cached by input (engine.run_jobs), so a rebuild after an
interruption, or after a change outside the engine, reruns nothing it has.
The build records the git revision, the dirty flag (ignoring its own outputs),
and source and input hashes when it starts, and fails if any change before it
ends.
"""

import json
import subprocess
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import central as central_module
from . import dwp, engine, expected_value, trajectories
from .benchmarks import load_benchmarks
from .config import (
    ACTUALS_CSV,
    AWE_CSV,
    BASE_YEAR,
    BENCHMARKS_CSV,
    CENTRAL_FORECAST_CSV,
    CPI_CSV,
    CROSSCHECK_CSV,
    DISTRIBUTION_YEARS,
    ERROR_CSV,
    FINAL_YEAR,
    FLAT_RATE_PARAMETERS,
    HORIZON,
    POLICIES,
    REPO,
    SENSITIVITY_DATASET,
    SWITCH_YEAR,
)

SOURCES = sorted(p.name for p in (REPO / "src" / "triple_lock").glob("*.py"))
COVERAGE_YEAR = BASE_YEAR

METHOD_LIMITATIONS = [
    # Forecast
    "Each rise follows the triple lock's convention of September CPI and May-July earnings (the statute requires "
    "at least earnings). The central path uses the OBR's September-quarter CPI and April-June earnings for the "
    "Aprils 2028-2031 and its calendar-year long-term path after; the monthly model builds both measures from "
    "the same simulated months.",
    "After 2030 the central path is the OBR's long-term projection, which it describes as not a forecast.",
    "The expected value rests on one statistical model of CPI and earnings (a monthly VAR fitted to 2000-2026), "
    "shifted so its calendar-year averages equal the OBR's. Its statutory inputs are off the OBR's quarterly "
    "figures in 2026-2028 (before the switch), and its September 2026 CPI is simulated from August's rather than "
    "fixed. Its backtest rests on twelve overlapping four-year windows.",
    "In every run April 2027's benefit uprating is the model's own calendar-2026 CPI forecast (2.3%), not "
    "September 2026 CPI, which is published on 21 October 2026.",
    # Data
    "The survey is not aged forward: Enhanced FRS ages are top-coded at 80 and held at their survey values, and "
    "the number of pensioners changes only through the survey weights and the State Pension age. Each person's "
    "State Pension type (basic or new) is held at its survey-year value.",
    "Rents and council tax stay at their 2030 amounts after 2030, and dividend, property, savings and "
    "self-employment income do not follow the path.",
    "In the survey runs Housing Benefit and council tax reduction respond only for households already receiving "
    "them: nobody the plan makes newly entitled starts claiming, which understates those offsets and so "
    "overstates the net saving.",
    "policyengine-uk's council tax reduction for pensioners in England tapers on income after tax without "
    "counting Pension Credit, and does not disregard the income of guarantee credit recipients as the "
    "regulations require (SI 2012/2885, Schedule 1, paragraph 13). Their council tax reduction therefore rises "
    "as the State Pension falls when it should not change: the example pensioners on Pension Credit come out "
    "slightly ahead when they should come out even. The council tax reduction offset in the survey runs is small.",
    "A pension cut of a few pounds a week can make one heavily weighted survey household eligible for Pension "
    "Credit guarantee credit, which in policyengine-uk entitles it to its full rent in Housing Benefit. One such "
    "record moves some paths' net figures by billions of pounds; the results give the largest record's "
    "contribution in every year and on every path.",
    # Model
    "Every rule follows the triple lock to April 2029. The Burnham plan from April 2030 rises by at least the "
    "higher of CPI and 2.5% and by whatever else keeps the pension at its 2029-30 ratio to earnings, as DWP "
    "defines it; its top-up to the earnings path is rounded up to 0.1 point.",
    "Only the basic and new State Pension change between the rules. Under both, the additional State Pension "
    "rises with September CPI, the Pension Credit guarantee with May-July earnings (the statutory minimum), and "
    "the State Pension age is 67 from 2028-29. There is no behavioural response.",
    "Costs are in cash terms (nominal £) for the UK; DWP's figures are for Great Britain.",
]



def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def package_versions():
    """Every package whose version can move a result, as recorded in provenance and compared by the tests."""
    import importlib.metadata as md

    return {**engine.package_versions(), **{p: md.version(p) for p in ("scipy", "pandas")}}


def input_files():
    from .history_data import SERIES
    from .ts_monthly import AWE_LEVEL_CSV, CPI_INDEX_CSV

    return [CENTRAL_FORECAST_CSV, ERROR_CSV, CROSSCHECK_CSV, ACTUALS_CSV, AWE_CSV, CPI_CSV, CPI_INDEX_CSV,
            AWE_LEVEL_CSV, BENCHMARKS_CSV, dwp.TABLES, REPO / dwp.UPRATING_ANALYSIS["file"],
            *(path for path, _ in SERIES.values())]


def hashes():
    here = REPO / "src" / "triple_lock"
    return {
        "source_hashes": {**{name: engine.file_hash(here / name) for name in SOURCES},
                          "pyproject.toml": engine.file_hash(REPO / "pyproject.toml")},
        "input_hashes": {str(Path(p).relative_to(REPO)): engine.file_hash(p) for p in input_files()},
    }


# The build's own outputs do not make the tree dirty: an uncommitted results file from the last build must not
# stop the next.
OUTPUT_PATHS = [":!data/results.json", ":!dashboard/public/data/results.json"]


def git_state():
    return {"git_revision": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain", "--", ".", *OUTPUT_PATHS))}


def snapshot():
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **git_state(), **hashes()}


def check_unchanged(start, where):
    """Fail if the revision, the dirty flag (outside the build's outputs) or any source or input hash moved."""
    state = git_state()
    moved = [k for k in state if state[k] != start[k]]
    if moved:
        raise engine.SourceChanged(f"{moved} changed between the start of the build and {where}")
    now = hashes()
    changed = [k for block in now for k in set(now[block]) | set(start[block]) if start[block].get(k) != now[block].get(k)]
    if changed:
        raise engine.SourceChanged(f"{changed} changed between the start of the build and {where}")


def actual_weekly(parameters):
    """Flat rates actually paid, April 2010 (basic) / 2016 (new) to 2026."""
    return {n: {y: float(parameters.get_child(path)(f"{y}-06-01"))
                for y in range(2010 if n == "basic_state_pension" else 2016, BASE_YEAR + 1)}
            for n, path in FLAT_RATE_PARAMETERS.items()}


def coverage(results):
    """Each dataset's 2026-27 spending and caseloads against DWP's (GB) forecast."""
    targets = dwp.coverage_targets()
    t = targets["values"]
    rows = {
        "state_pension_bn": ("State Pension spending (in GB, excluding payments abroad), £bn", t["state_pension_in_gb"]),
        "flat_rate_bn": ("Basic and new State Pension, £bn (DWP's figure includes payments abroad)",
                         t["state_pension_flat_rate"]),
        "state_pension_recipients_m": ("State Pension recipients (in GB), millions", t["state_pension_caseload_in_gb"]),
        "pension_credit_bn": ("Pension Credit, £bn", t["pension_credit"]),
        "pension_credit_claims_m": ("Pension Credit claims (benefit units), millions", t["pension_credit_caseload"]),
        "housing_benefit_bn": ("Housing Benefit (not Universal Credit housing), £bn", t["housing_benefit"]),
        "housing_benefit_pension_age_bn": ("Housing Benefit, pension age, £bn", t["housing_benefit_pension_age"]),
    }
    model = {}
    for name, r in results.items():
        model[name] = {
            "state_pension_bn": r["state_pension_bn"],
            "flat_rate_bn": r["basic_state_pension_bn"] + r["new_state_pension_bn"],
            "state_pension_recipients_m": r["state_pension_recipients"] / 1e6,
            "pension_credit_bn": r["pension_credit_bn"],
            "pension_credit_claims_m": r["pension_credit_benefit_units"] / 1e6,
            "housing_benefit_bn": r["housing_benefit_bn"],
            "housing_benefit_pension_age_bn": r["housing_benefit_pensioner_benefit_units_bn"],
        }
    return {
        "year": COVERAGE_YEAR,
        "dwp": {"source": targets["source"], "url": targets["url"], "geography": targets["geography"], "year": targets["year"]},
        "rows": [{"key": k, "label": label, "dwp": v, **{name: model[name][k] for name in model}}
                 for k, (label, v) in rows.items()],
        "model_note": "The model covers the UK (DWP's tables: GB). Pension-age Housing Benefit here is Housing Benefit "
                      "paid to benefit units with someone over State Pension age.",
        # Dataset facts only: no single record's weight (FRS records are licensed; see redact_records).
        "datasets": {name: {k: r[k] for k in ("dataset", "max_age", "people", "records", "pension_type_people",
                                              "state_pension_age_people")}
                     for name, r in results.items()},
    }


# Survey records are licensed data (the UK Data Service's End User Licence for the FRS): the published file
# may say how much one record contributes to a total, never which record it is, its weight or its amounts.
# gross_contribution_bn goes too, since a known State Pension change would give back the weight.
RECORD_FIELDS = {
    "largest_household": ("contribution_bn", "share_of_income_change", "income_change_excluding_bn"),
    "concentration_by_year": ("contribution_bn", "share_of_income_change"),
}


def redact_records(obj):
    """Keep only RECORD_FIELDS in every largest_household and concentration_by_year entry, in place."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "largest_household" and isinstance(value, dict):
                obj[key] = {k: value[k] for k in RECORD_FIELDS[key] if k in value}
            elif key == "concentration_by_year" and isinstance(value, dict):
                obj[key] = {y: {k: c[k] for k in RECORD_FIELDS[key] if k in c} for y, c in value.items()}
            else:
                redact_records(value)
    elif isinstance(obj, list):
        for value in obj:
            redact_records(value)
    return obj


# How the engine treats the survey population (engine.pinned_inputs): survey ages are not aged forward, and each
# person's State Pension type is held at its survey-year value. assumptions() checks both against what the runs
# recorded, so a change to the engine that leaves this out of date fails the build instead of publishing it.
POPULATION = {"ages_aged_forward": False, "pension_types_held": True}

# Short names for the shock models the trajectories compare (trajectories.models), as the dashboard words them.
SHOCK_MODEL_NAMES = {"boot": "resampled-shock", "tcop": "Student-t", "gauss": "Gaussian"}


def _fixed(value, digits):
    """value.toFixed(digits) as JavaScript prints it (the exact binary value, ties away from zero), so the block's
    wording matches what the dashboard would compute from the same numbers."""
    return str(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def _bn(value, digits=1):
    """The dashboard's formatBn: £1.2bn, with a minus only when the rounded figure is not zero."""
    fixed = _fixed(abs(value), digits)
    return f"{'-' if value < 0 and float(fixed) != 0 else ''}£{fixed}bn"


def _fy(year):
    return f"{year}-{(year + 1) % 100:02d}"


def _join(names):
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _population(results, population):
    """What the runs say about the population, checked against POPULATION: types are held when the engine recorded
    the held types; with ages held too, the type counts stop moving once the State Pension age stops rising."""
    fixed = results["central"]["run"]["fixed_inputs"]
    records = fixed.get("held_pension_type_records")
    if bool(records) != population["pension_types_held"]:
        raise ValueError("POPULATION['pension_types_held'] disagrees with the central run's fixed_inputs")
    spa = {y: fixed["state_pension_age"][str(y)] for y in HORIZON}
    settled = min(y for y in HORIZON if all(spa[z] == spa[FINAL_YEAR] for z in HORIZON if z >= y))
    if records:
        after = [records[str(y)] for y in HORIZON if y >= settled]
        if all(r == after[0] for r in after) == population["ages_aged_forward"]:
            raise ValueError("POPULATION['ages_aged_forward'] disagrees with the held pension type counts after "
                             f"{settled}, when the State Pension age stops changing")
    return {**population, "final_year": FINAL_YEAR, "data_year": fixed["data_year"],
            "state_pension_age_settled_year": settled, "state_pension_age": spa[FINAL_YEAR][0],
            "max_age": results["coverage"]["datasets"]["primary"]["max_age"]}


def _population_item(facts):
    fy = _fy(facts["final_year"])
    aged, held = facts["ages_aged_forward"], facts["pension_types_held"]
    if not aged and held:
        title = "Today's pensioners, held fixed"
        text = (f"Survey ages and State Pension types are fixed to {fy}, so nobody new joins on the new State Pension; "
                "the number of pensioners changes only through the survey weights and the State Pension age. "
                "DWP's costing projects the population; ours does not.")
    elif not aged:
        title = "Today's pensioners, ages held fixed"
        text = (f"Survey ages are fixed to {fy} and State Pension types follow them; the number of pensioners changes "
                "only through the survey weights and the State Pension age. DWP's costing projects the population; "
                "ours does not.")
    elif held:
        title = "Pensioners aged forward, pension types held"
        text = (f"Survey ages are aged forward to {fy}, but State Pension types are held at their survey-year values, "
                "so nobody new joins on the new State Pension.")
    else:
        title = "Pensioners aged forward"
        text = (f"Survey ages are aged forward to {fy} and each person's State Pension type follows when they reached "
                "State Pension age, so people reaching it join on the new State Pension.")
    return {"key": "population", "title": title, "text": text, "facts": facts}


def _paths_item(results):
    """The lowest and highest gross expected saving in the final year across the reweightings of the same full runs
    (the dashboard's getSensitivityRange), and the shock models tested but not run through the fiscal model."""
    sens = results["expected_value"]["sensitivities"]
    rows = [(name, s["gross"][str(FINAL_YEAR)], s["effective_runs"]) for name, s in sens.items()]
    if not rows:
        return None
    low = min(rows, key=lambda r: r[1]["mean"])
    high = max(rows, key=lambda r: r[1]["mean"])
    models = results["trajectories"]["models"]
    run = [m for m, v in models.items() if v["runs_paths"]]
    not_run = [m for m, v in models.items() if not v["runs_paths"]]
    facts = {
        "year": FINAL_YEAR, "measure": "gross", "reweightings": len(rows),
        "lowest": {"calibration": low[0], "mean": low[1]["mean"], "se": low[1]["se"]},
        "highest": {"calibration": high[0], "mean": high[1]["mean"], "se": high[1]["se"], "effective_runs": high[2]},
        "shock_models_run": run, "shock_models_not_run": not_run,
    }
    title = "One model of prices and earnings" if len(run) == 1 else "Several models of prices and earnings"
    text = ("Its paths are shifted to the OBR's average forecast. Reweighting the same full runs to match how much the "
            "gap between earnings growth and CPI varied in the past and how often the lead switched (in some versions "
            "also how often the 2.5% floor binds) gives separate point estimates, the lowest "
            f"{_bn(low[1]['mean'])} gross (standard error {_bn(low[1]['se'])}) and the highest {_bn(high[1]['mean'])}, "
            f"which rests on about {_fixed(high[2], 0)} effective runs (standard error {_bn(high[1]['se'])}).")
    if not_run:
        text += (" This range does not include another model of prices and earnings: "
                 f"{_join([SHOCK_MODEL_NAMES.get(m, m) for m in not_run])} versions are tested against past forecasts "
                 "(Methodology tab) but not run through the full fiscal model.")
    return {"key": "paths", "title": title, "text": text, "facts": facts}


def _benefits_item(results):
    """Pension Credit claims and pension-age Housing Benefit in the survey against DWP's, and the paired Microcosm
    difference in the final year's net saving."""
    cov = results["coverage"]
    row = {r["key"]: r for r in cov["rows"]}
    claims, hb = row.get("pension_credit_claims_m"), row.get("housing_benefit_pension_age_bn")
    if not claims or not hb:
        return None
    ev = results["expected_value"]
    diff = ev["paired_difference"]["net"][str(FINAL_YEAR)]
    paired = sum(s["sensitivity_paths"] for s in ev["strata"])
    facts = {
        "coverage_year": cov["year"],
        "pension_credit_claims_m": {"primary": claims["primary"], "dwp": claims["dwp"]},
        "housing_benefit_pension_age_bn": {"primary": hb["primary"], "dwp": hb["dwp"]},
        "model_geography": "UK", "dwp_geography": cov["dwp"]["geography"].split(",")[0],
        "paired_difference_net": {"year": FINAL_YEAR, "mean": diff["mean"], "se": diff["se"], "paths": paired},
    }
    above = [r["primary"] > r["dwp"] for r in (claims, hb)]
    title = ("Survey benefit baselines above DWP's" if all(above) else
             "Survey benefit baselines below DWP's" if not any(above) else "Survey benefit baselines against DWP's")
    text = (f"In {_fy(cov['year'])} the survey has {_fixed(claims['primary'], 2)}m Pension Credit claims against DWP's "
            f"{_fixed(claims['dwp'], 2)}m, and {_bn(hb['primary'])} of pension-age Housing Benefit against "
            f"{_bn(hb['dwp'])}, a {facts['model_geography']} model against DWP's {facts['dwp_geography']} figures.")
    if paired > 0:
        text += (f" On the same {paired} paths, the Microcosm dataset gives a net saving {_bn(abs(diff['mean']))} "
                 f"{'higher' if diff['mean'] >= 0 else 'lower'} (standard error {_bn(diff['se'])}).")
    return {"key": "benefits", "title": title, "text": text, "facts": facts}


def assumptions(results, population=POPULATION):
    """What the headline figures are conditional on: [{key, title, text, facts}], the dashboard's "What these figures
    assume" strip. The wording is generated here, from the model's configuration and the assembled results, so it
    changes when the model does; `facts` holds every number the text quotes."""
    # Worded from what the file will hold: in the build, run results carry integer year keys (engine.run_jobs);
    # read back, every key is a string.
    results = json.loads(json.dumps(results, default=float))
    items = [_population_item(_population(results, population)), _paths_item(results), _benefits_item(results)]
    return [item for item in items if item is not None]


def build(workers=3, allow_dirty=False, log=print, sensitivity_workers=2):
    from policyengine_uk.system import system

    start = snapshot()
    if start["git_dirty"] and not allow_dirty:
        raise SystemExit("The git tree has uncommitted changes outside the build's own outputs (data/results.json and "
                         "its dashboard copy): commit first, or pass --allow-dirty (the file will say so).")
    parameters = system.parameters
    central = central_module.central_path()
    base = engine.base_levels(parameters)

    log("Central path")
    central_run = engine.run_jobs([("path", {k: v for k, v in trajectories.central_spec(central).items()
                                             if k not in ("id", "label", "source")})],
                                  workers=1, slot_prefix="efrs", log=log)[0]
    log("Dataset coverage")
    hist = central_module.september_cpi_history()
    cov_runs = engine.run_jobs([("coverage", {"year": COVERAGE_YEAR, "september_cpi_history": hist}),
                                ("coverage", {"year": COVERAGE_YEAR, "dataset": SENSITIVITY_DATASET,
                                              "september_cpi_history": hist})],
                               workers=1, slot_prefix="microcosm", log=log)
    ev = expected_value.build(central, base["new_state_pension"], log=log, workers=workers,
                              sensitivity_dataset=SENSITIVITY_DATASET, sensitivity_workers=sensitivity_workers)
    traj = trajectories.build(central, base, actual_weekly(parameters), workers=workers, log=log)

    results = {
        "sample": False,
        "horizon": HORIZON,
        "final_year": FINAL_YEAR,
        "switch_year": SWITCH_YEAR,
        "distribution_years": DISTRIBUTION_YEARS,
        "policies": POLICIES,
        "base_year_weekly": {"year": BASE_YEAR, **{k: round(v, 2) for k, v in base.items()}},
        "central": {"path": central, "run": {k: v for k, v in central_run.items() if k != "bundle"}},
        "expected_value": ev,
        "trajectories": traj,
        "coverage": coverage({"primary": cov_runs[0], "sensitivity": cov_runs[1]}),
        "dwp_uprating_analysis": dwp.UPRATING_ANALYSIS,
        "method_limitations": METHOD_LIMITATIONS,
    }
    redact_records(results)
    results["assumptions"] = assumptions(results)
    results["benchmarks"] = load_benchmarks(results)
    check_unchanged(start, "the end of the build")
    import importlib.metadata as md

    results["provenance"] = {
        **start,
        "snapshot": "revision, dirty flag and hashes taken when the build started; rechecked at its end",
        "engine_hashes": engine.engine_hashes(),
        "packages": package_versions(),
        "release_bundle": central_run["bundle"],
        "datasets": {"primary": central_run["bundle"]["runtime_dataset"], "sensitivity": SENSITIVITY_DATASET},
    }
    return results


def write(results, paths):
    text = json.dumps(results, indent=1, default=float, allow_nan=False) + "\n"
    for path in paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        print(f"Results written to {path}")
