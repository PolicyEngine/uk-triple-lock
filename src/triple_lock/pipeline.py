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

Model jobs are cached by input (jobs.run_jobs), so a rebuild after an
interruption, or after a change outside the engine, reruns nothing it has.
The build records the git revision, the dirty flag (ignoring its own outputs),
and source and input hashes when it starts, and fails if any change before it
ends.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import central as central_module
from . import dwp, engine, expected_value, jobs, trajectories
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
    central_run = jobs.run_jobs([("path", {k: v for k, v in trajectories.central_spec(central).items()
                                             if k not in ("id", "label", "source")})],
                                  workers=1, slot_prefix="efrs", log=log)[0]
    log("Dataset coverage")
    hist = central_module.september_cpi_history()
    cov_runs = jobs.run_jobs([("coverage", {"year": COVERAGE_YEAR, "september_cpi_history": hist}),
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
