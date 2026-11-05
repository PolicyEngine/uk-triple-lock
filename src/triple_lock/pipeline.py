"""The build: every section of the results file, each figure from full PolicyEngine UK runs.

Sections
--------
* ``central``: the central path (central.py) and its full run (engine.run_path):
  savings by year, gross and net with their components, households affected,
  household tables and poverty. Individual-record diagnostics are omitted by
  redact_records.
* ``expected_value``: the calibrated distribution of paths and the stratified
  sample of full runs (expected_value.py), on the certified Microcosm UK Budget
  primary and the paired Enhanced FRS 1.58.2 sensitivity. Publication requires
  policyengine.py 6.11.1, the release carrying d2011's pair.
* ``trajectories``: a few paths we fully understand, past years and the method
  backtests (trajectories.py).
* ``coverage``: what each dataset holds against DWP's tables, for the UK and Great Britain, in 2026-27 to 2030-31,
  2034-35 and 2039-40 (no DWP figure past 2030-31).
* ``benchmarks``: published costings paired with the closest figure here.
* ``assumptions``: what the headline figures are conditional on, worded here from how the runs treated the
  population and the results above, for the dashboard's "What these figures assume" strip.

Model jobs are cached by input (jobs.run_jobs), so a rebuild after an
interruption, or after a change outside the engine, reruns nothing it has.
The build records the git revision, the dirty flag (ignoring its own outputs),
and source and input hashes when it starts, and fails if any change before it
ends. Before its first model job it refuses a policyengine-uk whose Housing
Benefit Guarantee Credit passport keys on entitlement rather than receipt
(housing_benefit_passport_preflight, policyengine-uk#1927), and records what that
check observed in ``provenance.preflight``.
"""

import json
import os
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import central as central_module
from . import datasets, dwp, engine, expected_value, jobs, trajectories
from .benchmarks import load_benchmarks
from .disclosure import publish_count
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
    POPULATION_PROJECTION,
    PRIMARY_DATASET,
    REPO,
    SENSITIVITY_DATASET,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)

SOURCES = sorted(p.name for p in (REPO / "src" / "triple_lock").glob("*.py"))


def published_policies():
    """config.POLICIES with the published labels (d2123); ids and rules unchanged.

    d2123 (Max, 28 October 2026): the government's adjusted Triple Lock (Budget 2026, Box 5.A; DWP's factsheet of
    6 October 2026), first called the Burnham plan here. Only the published label changes. config.POLICIES keeps
    its label, because the C2 handoff fingerprints config.py byte for byte; the id burnham_2030 keys the results,
    the handoffs and the receipts. The labels live in this function, not a module constant, so the pilot's
    protected module-level assignments are unchanged (tests/cold_source_correspondence.py).
    """
    labels = {"burnham_2030": "Adjusted Triple Lock (Budget 2026)"}
    return {k: {**v, **({"label": labels[k]} if k in labels else {})} for k, v in POLICIES.items()}


COVERAGE_YEAR = BASE_YEAR
# The years coverage jobs report: the base year and every year DWP's tables give (to 2030-31), then the household
# tables' years, which no DWP table reaches.
COVERAGE_YEARS = [*dwp.TABLE_YEARS, *(y for y in DISTRIBUTION_YEARS if y > dwp.TABLE_YEARS[-1])]

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
    "The population is aged statically, not dynamically: each survey record stands for a person of its age in "
    "every year. After the data's calibration year (2025-26) household weights follow the ONS 2024-based "
    "projection's growth by age and sex; records top-coded at 80 get represented ages from 80 to 105; and each "
    "year's State Pension type follows the person's birth cohort. Later retirees' pension amounts come from "
    "today's records of the same age, and deaths, migration and contribution histories are not simulated. "
    "Pensioners living abroad are outside the survey.",
    "In the calibration year the weights are the data's own, but policyengine-uk uprates them from the survey year "
    "by less than the data build materialized them, so they sit 0.44% below the calibrated levels "
    "(policyengine-uk-data#538), and every later year carries that.",
    "Rents and council tax stay at their 2030 amounts after 2030, and dividend, property, savings and "
    "self-employment income do not follow the path.",
    "In the survey runs Housing Benefit and council tax reduction respond only for households already receiving "
    "them: nobody the plan makes newly entitled starts claiming, which understates those offsets and so "
    "overstates the net saving.",
    "Concentration diagnostics remain private until support checks show at least ten contributing records in "
    "each reported total and each recoverable complement. Selecting ten records alone does not establish that "
    "ten records have nonzero contributions.",
    # Model
    "Every rule follows the triple lock to April 2029. The Burnham plan from April 2030 rises by at least the "
    "higher of CPI and 2.5% and by whatever else keeps the pension at its 2029-30 ratio to earnings, as DWP "
    "defines it; its top-up to the earnings path is rounded up to 0.1 point.",
    "Only the basic and new State Pension change between the rules. Under both, the additional State Pension "
    "rises with September CPI and the Pension Credit guarantee with May-July earnings (the statutory minimum), and "
    "the State Pension age follows the law's timetable by date of birth, so every age of 67 and over is above it "
    "from 2028-29. There is no behavioural response.",
    "Reported State Pension below State Pension age is not counted, as none is payable before it; every run "
    "records how many survey records report one (state_pension_accounting).",
    "policyengine-uk pays Scotland's Pension Age Winter Heating Payment at £100 a household without a qualifying "
    "benefit from winter 2025, where the regulations pay £203.40 (£305.10 at 80) a person living alone "
    "(policyengine-uk#2138), and it has no 25p age addition at 80 (policyengine-uk#2139).",
    "The primary model/data pair is the policyengine 6.2.6 certified UK bundle: policyengine-uk 2.125.1, "
    "policyengine-core 3.33.0 and Enhanced FRS from policyengine-uk-data 1.58.0. Microcosm is an uncertified sensitivity.",
    "Costs are in cash terms (nominal £) for the UK; DWP's figures are for Great Britain. Each path run in the "
    "results file also gives its saving for Great Britain.",
]



def forecast_vintages(central=None):
    """Which OBR publication each year of the central path comes from (d2124), read from the path's own sources.

    Max ruled on 28 October 2026 (d2124) to build on the October 2026 EFO to 2030 and the March 2026 long-term
    economic determinants after it, to label that mix on every figure, and to rerun the later years once the OBR
    publishes its October long-term set. Calendar 2026 comes from the forecast file's row (engine.base_year_growth).
    """
    central = central or central_module.central_path()
    calendar, statutory = central["calendar_source"], central["statutory_source"]
    sources = central["sources"]
    efo_calendar = [BASE_YEAR, *sorted(y for y, s in calendar.items() if s == "efo_calendar")]
    efo_statutory = sorted(y for y, s in statutory.items() if s == "efo_quarterly")
    later_calendar = sorted(y for y, s in calendar.items() if s != "efo_calendar")
    later_statutory = sorted(y for y, s in statutory.items() if s == "calendar")
    if (efo_calendar != list(range(BASE_YEAR, efo_calendar[-1] + 1)) or later_calendar[0] != efo_calendar[-1] + 1
            or later_statutory[0] != efo_statutory[-1] + 1):
        raise MissingFigure("the central path's sources do not split into one forecast vintage then another")
    return {
        "decision": "d2124",
        "forecast": {"title": sources["efo_calendar"]["title"], "url": sources["efo_calendar"]["url"],
                     "calendar_years": [efo_calendar[0], efo_calendar[-1]],
                     "april_rises": [efo_statutory[0] + 1, efo_statutory[-1] + 1]},
        "long_term": {"title": sources["lted_converted"]["title"], "url": sources["lted_converted"]["url"],
                      "calendar_years": [later_calendar[0], later_calendar[-1]],
                      "april_rises": [later_statutory[0] + 1, later_statutory[-1] + 1]},
        "note": vintage_note(central),
    }


def _month_order(month):
    """("October 2026") -> (2026, 10), so two publications' months compare in time. It reads the English month names
    trajectories.MONTH_YEAR admits without strptime, so no locale setting can stop the results file's assembly."""
    name, year = month.split()
    months = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December")
    return int(year), months.index(name) + 1


def vintage_note(central):
    """Why the years after the forecast follow an older long-term set, in the months the path's sources name; None
    when both come from one outlook or a source names no month."""
    import re

    forecast, long_term = trajectories.vintage_months(central)
    if not (forecast and long_term) or not _month_order(long_term) < _month_order(forecast):
        return None
    dated = re.search(rf"\d{{1,2}} {forecast}", central["sources"]["efo_calendar"]["title"])
    return (f"The OBR published no {forecast} long-term economic determinants with its "
            f"{dated.group(0) if dated else forecast} outlook, so the years after the forecast follow the "
            f"{long_term} set; a rebuild replaces them once the {forecast.split()[0]} set is out.")


def method_limitations(central=None, omitted=None):
    """Current release wording; historical constants remain frozen for C2 correspondence.

    ``omitted`` says why a file has no expected value: "c2" when the model failed its frozen C2 screen, "ruling" for a
    direct d955(a) build. The monthly model's note then describes only the example paths it gives, never an estimate
    the file omits.
    """
    from .rules import round_rate, triple_lock_source

    central = central or central_module.central_path()
    vintages = forecast_vintages(central)
    forecast, long_term = vintages["forecast"], vintages["long_term"]
    wording = list(METHOD_LIMITATIONS)
    import re

    forecast_month, long_term_month = trajectories.vintage_months(central)
    older = bool(forecast_month and long_term_month) and _month_order(long_term_month) < _month_order(forecast_month)
    dated = re.search(r"\(dated [^)]*\)", long_term["title"])
    for i, text in enumerate(wording):
        if text.startswith("After 2030 the central path"):
            wording[i] = (
                f"The central path follows the OBR's {forecast_month + ' ' if forecast_month else ''}Economic and "
                f"fiscal outlook for calendar years {forecast['calendar_years'][0]}-{forecast['calendar_years'][1]} "
                f"and the inputs to every April rise to April {forecast['april_rises'][1]}. Later years follow the "
                f"OBR's {long_term_month + ' ' if long_term_month else ''}long-term economic determinants"
                f"{' ' + dated.group(0) if dated else ''}"
                f"{f', because the OBR published no {forecast_month} set with that outlook' if older else ''}, "
                f"and the OBR describes its long-term projection as not a forecast."
                + (f" When the OBR publishes the {forecast_month.split()[0]} set, a rebuild replaces every figure "
                   f"for {long_term['calendar_years'][0]} and later." if older else ""))
        elif text.startswith("The expected value rests on one statistical model") and omitted is not None:
            reason = {"c2": "the model failed its frozen statutory screen (C2)",
                      "ruling": "the d955 ruling publishes scenarios only"}[omitted]
            wording[i] = (
                "The simulated example paths rest on one statistical model of CPI and earnings (a monthly VAR "
                "fitted to 2000-2026), shifted so its calendar-year averages equal the OBR's. They show how prices "
                f"and earnings could move and carry no probability weight: {reason}, so the file makes no probability "
                "claim from them.")
        elif text.startswith("Every rule follows the triple lock to April 2029"):
            wording[i] = text.replace("The Burnham plan from April 2030", "The adjusted Triple Lock from April 2030")
        elif text.startswith("In every run April 2027"):
            wording[i] = (
                "On policyengine-uk 2.151.0, benefit uprating follows the previous September's CPI (#2557), to "
                "0.1 point and never cut: April 2027 uses the path's September 2026 CPI input and later years the "
                "path's September CPI the year before. Additional State Pension follows September CPI.")
        elif text.startswith("The population is aged statically"):
            wording[i] = (
                "The population is aged statically: each record represents a person of its age in every year. "
                "The Microcosm primary and Enhanced FRS 1.58.2 both anchor in their 2025-26 calibration year: "
                "each dataset's own runtime weights are retained through that year and then follow ONS 2024-based "
                "age/sex growth. Microcosm's 2025 weights are exactly its solved ones; the Enhanced FRS's are its "
                "calibrated ones times 0.9956 (policyengine-uk-data#538). Uncapped ages "
                "are retained, including genuine ages of 80; only an entirely top-coded 80+ tail gets "
                "represented ages of 80 to 105. State Pension types follow birth cohorts. Deaths, migration "
                "and contribution histories are not simulated; pensioners abroad are outside both datasets.")
        elif text.startswith("In the calibration year"):
            wording[i] = (
                "Microcosm records are built from survey donors. The same minimum of ten contributing "
                "records and complementary withholding applies to the primary and Enhanced FRS 1.58.2.")
        elif text.startswith("policyengine-uk pays Scotland"):
            wording[i] = "policyengine-uk 2.151.0 has no 25p State Pension age addition at 80 (#2340 is unmerged)."
        elif text.startswith("The primary model/data pair"):
            wording[i] = (
                "The binding primary is the UK Budget pair d2011 certifies (microcosm#1396): Microcosm national "
                "cut microcosm-uk-2024-25-national-20261025T091414Z-a6299504, policyengine-uk 2.151.0 and "
                "policyengine-core 3.33.3, certified by its policyengine.py 6.11.1 release (policyengine.py#720); "
                "publication fails closed without exactly that installed bundle. "
                + ("Enhanced FRS 1.58.2 is the paired sensitivity. " if omitted is None else
                   "This scenarios-only build runs no paired sensitivity, so Enhanced FRS 1.58.2 gives only "
                   "the data check. ")
                + "This model has September-CPI benefit uprating (#2557) but predates linked "
                "HB/Savings Credit derivation (#2576): the Savings Credit thresholds and pension-age HB "
                "allowances retain the installed lagged calendar-CPI projection (d1753); the Pension Credit "
                "guarantee still follows May-July earnings.")
    year = forecast["april_rises"][0] - 1  # the first forecast year's statutory inputs, for that next April
    earnings, cpi = (round_rate(central["statutory"][k][year]) for k in ("earnings", "cpi"))
    guarantee = (
        f"The OBR publishes no May-July earnings forecast, so the Pension Credit guarantee's rises from April {year + 1} to "
        f"April {forecast['april_rises'][1]} follow its April-June average earnings growth, the same proxy the "
        f"triple lock's earnings leg uses ({earnings:.1%} in {year}, for April {year + 1}).")
    if triple_lock_source(cpi, earnings) == "cpi":  # above the floor and at least earnings, as the rule labels it
        guarantee += (f" On the central path September CPI ({cpi:.1%}) sets April {year + 1}'s State Pension rise, "
                      f"so a lower May-July figure would make the guarantee's April {year + 1} rise smaller and "
                      f"leave the pension's unchanged.")
    wording.append(guarantee)
    wording.append(
        "The pre-Budget release used Enhanced FRS and was described as provisional in Vahid's post. "
        "The binding release uses Microcosm; bridge step (b), on the same policyengine-uk 2.151.0 model, "
        "measures that change of data.")
    return wording


def sensitivity_dataset_names():
    """Names for current and historical sensitivity records without changing frozen C2 constants."""
    return {**SENSITIVITY_DATASET_NAMES, "enhanced_frs_2024_25@1.58.2": "Enhanced FRS 1.58.2"}



def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def package_versions():
    """Every package whose version can move a result, as recorded in provenance and compared by the tests."""
    import importlib.metadata as md

    return {**engine.package_versions(), **{p: md.version(p) for p in ("scipy", "pandas")}}


class UncertifiedBundle(RuntimeError):
    """A publication build does not use the exact released, certified UK bundle."""


def certified_bundle_preflight(log=print):
    """Require d2011's exact released UK Budget pair without loading any dataset.

    The primary must be one of d2011's pairs (datasets.D2011_PAIRS), and the bundle
    checked is that pair's own: the 2.151.0 pair's, or after a fallback commit moves
    config.PRIMARY_DATASET, a133f37a's. The candidate head is not a released
    certificate. Dataset provenance checks the installed release manifest digest
    and exact model/core/artifact and local-area identity; materialization
    separately verifies the artifact's bytes before model jobs. Historical bridge
    jobs and Enhanced FRS sensitivity use separate entry points.
    """
    remedy = ("The fiscal rebuild requires the certified released policyengine.py UK Budget bundle carrying "
              "d2011's pair (microcosm#1396): UK 2.151.0 / core 3.33.3 / Microcosm a6299504, or its fallback, "
              "#715's UK 2.147.2 / Microcosm a133f37a with #699's area routing. While the pair's release identities "
              "in datasets.py are pending, this refuses. scripts/fill_release_identities.py pins them from the "
              "release (for the 2.151.0 pair, policyengine.py 6.11.1): its version, released manifest digest, "
              "certifying pull request and commit, and local-area cut, and the carrier in the lock. Install the "
              "re-resolved lock (docs/REBUILD.md). A candidate head and producer gates cannot certify a release.")
    if PRIMARY_DATASET not in datasets.D2011_PAIRS:
        raise UncertifiedBundle(remedy)
    primary = PRIMARY_DATASET
    certification = datasets.DATASETS[primary]["bundle_certification"]
    expected = {"policyengine": certification["bundle_version"],
                "policyengine-uk": certification["model_version"],
                "policyengine-core": certification["core_version"]}
    if (not expected["policyengine"] or not certification["manifest_sha256"]
            or not certification["certification_url"] or not certification["certification_commit"]):
        raise UncertifiedBundle(remedy)
    installed = package_versions()
    if any(installed.get(name) != version for name, version in expected.items()):
        raise UncertifiedBundle(remedy)
    provenance = datasets.provenance(PRIMARY_DATASET)
    if provenance.get("dataset") != primary or provenance.get("certified") is not True:
        raise UncertifiedBundle(remedy + " The installed released manifest does not certify the pinned pair.")
    log(f"Preflight: exact policyengine {expected['policyengine']} UK Budget bundle and {primary} certified")
    return {"certified_bundle": {"passed": True, "packages": expected, "primary": provenance}}


def input_files():
    from .history_data import SERIES
    from .ts_monthly import AWE_LEVEL_CSV, CPI_INDEX_CSV

    return [CENTRAL_FORECAST_CSV, ERROR_CSV, CROSSCHECK_CSV, ACTUALS_CSV, AWE_CSV, CPI_CSV, CPI_INDEX_CSV,
            AWE_LEVEL_CSV, BENCHMARKS_CSV, POPULATION_PROJECTION, dwp.TABLES, REPO / dwp.UPRATING_ANALYSIS["file"],
            *(path for path, _ in SERIES.values())]


def hashes():
    here = REPO / "src" / "triple_lock"
    return {
        "source_hashes": {**{name: engine.file_hash(here / name) for name in SOURCES},
                          "pyproject.toml": engine.file_hash(REPO / "pyproject.toml")},
        "input_hashes": {str(Path(p).relative_to(REPO)): engine.file_hash(p) for p in input_files()},
    }


# The build's own outputs do not make the tree dirty: an uncommitted results file (or scenario run) from the last
# build must not stop the next.
OUTPUT_PATHS = [":!data/results.json", ":!dashboard/public/data/results.json", ":!data/scenarios/*.json"]


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


# Coverage rows: (label, DWP value key, model value from a coverage_stats block).
COVERAGE_ROWS = {
    "state_pension_bn": ("State Pension spending (in GB, excluding payments abroad), £bn", "state_pension_in_gb",
                         lambda m: m["state_pension_bn"]),
    "flat_rate_bn": ("Basic and new State Pension, £bn (DWP's figure includes payments abroad)",
                     "state_pension_flat_rate", lambda m: m["basic_state_pension_bn"] + m["new_state_pension_bn"]),
    "state_pension_recipients_m": ("State Pension recipients (in GB), millions", "state_pension_caseload_in_gb",
                                   lambda m: m["state_pension_recipients"] / 1e6),
    "pension_credit_bn": ("Pension Credit, £bn", "pension_credit", lambda m: m["pension_credit_bn"]),
    "pension_credit_claims_m": ("Pension Credit claims (benefit units), millions", "pension_credit_caseload",
                                lambda m: m["pension_credit_benefit_units"] / 1e6),
    "housing_benefit_bn": ("Housing Benefit (not Universal Credit housing), £bn", "housing_benefit",
                           lambda m: m["housing_benefit_bn"]),
    "housing_benefit_pension_age_bn": ("Housing Benefit, pension age, £bn", "housing_benefit_pension_age",
                                       lambda m: m["housing_benefit_pension_age_bn"]),
    "housing_benefit_pension_age_claims_m": ("Housing Benefit claims, pension age (benefit units), millions",
                                             "housing_benefit_caseload_pension_age",
                                             lambda m: m["housing_benefit_pension_age_benefit_units"] / 1e6),
}
COVERAGE_NOTE = ("The model covers the UK; DWP's tables cover Great Britain, so the model's figures set against them "
                 "are for Great Britain (households in England, Scotland and Wales), like for like. Pension-age "
                 "Housing Benefit is Housing Benefit paid under the pension-age regulations "
                 "(housing_benefit_pension_age_regulations_apply), nearest DWP's 'over Pension Credit qualifying "
                 "age'. Every year is the central path under the triple lock, with the population treated as in the "
                 "path runs (each dataset's coverage job records it: ``demography``). DWP's tables stop at 2030-31: "
                 "later years have no DWP figure. State Pension by age (Great Britain) is shown only where every "
                 "cell, in every year, rests on at least ten records; otherwise the whole table is withheld.")


def _coverage_rows(stats, targets):
    """[{key, label, dwp, <dataset>, <dataset>_gb, <dataset>_gb_over_dwp}] for one year: ``stats`` {dataset:
    coverage_stats block or None}, ``targets`` DWP's values for the year or None."""
    rows = []
    for key, (label, dwp_key, value) in COVERAGE_ROWS.items():
        row = {"key": key, "label": label, "dwp": None if targets is None else targets[dwp_key]}
        for name, s in stats.items():
            if s is None:
                continue
            row[name], row[f"{name}_gb"] = value(s["uk"]), value(s["gb"])
            if targets is not None and targets[dwp_key]:
                row[f"{name}_gb_over_dwp"] = row[f"{name}_gb"] / targets[dwp_key]
        rows.append(row)
    return rows


def _age_tables(run):
    """{year: GB State Pension by age band} from one coverage job, or every cell "withheld_family" when any cell in
    any year was suppressed: ages are fixed across years, so a small cell in one year could otherwise be recovered
    from the same band in another (disclosure)."""
    tables = {y: s["gb"].get("state_pension_by_age") for y, s in run["by_year"].items()}
    if any(t is None for t in tables.values()):
        return None
    if any(c["status"] != "available" for t in tables.values() for c in t.values()):
        return {y: {band: {k: "withheld_family" if k == "status" else None for k in c} for band, c in t.items()}
                for y, t in tables.items()}
    return tables


def coverage(results):
    """Each dataset's spending and caseloads against DWP's (GB) forecast: in 2026-27 (``rows``) and in every year a
    coverage job ran (``by_year``), for the UK and for Great Britain."""
    by_dwp = dwp.coverage_targets_by_year()
    first = by_dwp[COVERAGE_YEAR]
    results = {name: {**r, "by_year": {int(y): v for y, v in r["by_year"].items()}} for name, r in results.items()}
    for name, r in results.items():  # Great Britain is England, Scotland and Wales: every household must be in one
        for y, s in r["by_year"].items():
            if "households_by_country" not in s["uk"]:
                raise ValueError(f"{name}'s coverage in {y} does not say which country its households are in")
            unknown = s["uk"]["households_by_country"].get("UNKNOWN", 0)
            if unknown:
                raise ValueError(f"{name} has households of unknown country in {y}: Great Britain would leave them out")
    years = sorted({y for r in results.values() for y in r["by_year"]})
    by_year = {}
    for y in years:
        stats = {name: r["by_year"].get(y) for name, r in results.items()}
        targets = by_dwp.get(y)
        by_year[y] = {"dwp_year": None if targets is None else targets["year"],
                      "rows": _coverage_rows(stats, None if targets is None else targets["values"])}
    return {
        "year": COVERAGE_YEAR,
        "dwp": {"source": first["source"], "url": first["url"], "geography": first["geography"], "year": first["year"],
                "years": [by_dwp[y]["year"] for y in sorted(by_dwp)]},
        "rows": by_year[COVERAGE_YEAR]["rows"],
        "by_year": by_year,
        "model_note": COVERAGE_NOTE,
        "state_pension_by_age": {name: _age_tables(r) for name, r in results.items()},
        # Dataset facts only: no single record's weight (FRS records are licensed; see redact_records).
        "datasets": {name: {"dataset": r["dataset"], "model": r["model"], "demography": r.get("demography"),
                            "ageing": r.get("ageing"), "state_pension_accounting": r.get("state_pension_accounting"),
                            "records": r["records"],
                            **{k: r["by_year"][COVERAGE_YEAR]["uk"][k]
                               for k in ("people", "pension_type_people", "state_pension_age_people")}}
                     for name, r in results.items()},
    }


# Survey records are licensed. A record's contribution, or an aggregate that
# differs from another published aggregate by just that record, is private too.
RECORD_FIELDS = frozenset(("largest_household", "concentration_by_year",
                           "concentration_top10_by_year",
                           "largest_record_bn", "net_excluding_largest_record",
                           "max_proportionality_error_gbp", "max_additional_state_pension_gap_gbp",
                           "max_identity_error_gbp", "max_age", "survey_max_age"))


def redact_records(obj):
    """Omit whole individual-record families and suppress small support counts."""
    if isinstance(obj, dict):
        for key in list(obj):
            value = obj[key]
            if key in RECORD_FIELDS:
                del obj[key]
            elif key == "saving_support_records_by_year" and isinstance(value, dict):
                # Cached runs from before count suppression must be safe too.
                obj[key] = {year: {geo: {measure: publish_count(count) for measure, count in cells.items()}
                                  for geo, cells in by_geo.items()} for year, by_geo in value.items()}
            else:
                redact_records(value)
    elif isinstance(obj, list):
        for value in obj:
            redact_records(value)
    return obj


# Short names for the shock models the trajectories compare (trajectories.models), as the dashboard words them.
SHOCK_MODEL_NAMES = {"boot": "resampled-shock", "tcop": "Student-t", "gauss": "Gaussian"}
# How each calibration the expected value can rest on is described, and the sensitivity dataset's name.
PRIMARY_CALIBRATION_TEXT = {"means_shift": "Its paths are shifted to the OBR's average forecast."}
SENSITIVITY_DATASET_NAMES = {"microcosm_uk_2024_25": "Microcosm", "populace_uk_2023": "Populace UK 2023"}


class MissingFigure(ValueError):
    """The results lack a figure the assumptions block quotes, or carry a value it has no wording for: the build
    fails rather than publish a strip that no longer describes the model."""


def _get(results, path, *keys):
    """results at a dotted path, then at `keys` taken whole (calibration names contain dots)."""
    node = results
    for part in [*path.split("."), *keys]:
        if not isinstance(node, dict) or part not in node:
            raise MissingFigure(f"the assumptions block needs results.{'.'.join([path, *keys])}")
        node = node[part]
    return node


def _wording(table, value, what):
    if value not in table:
        raise MissingFigure(f"no wording for {what} = {value!r}: add it to pipeline.assumptions")
    return table[value]


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


def _population_item(results):
    """Worded from how the path runs treated the population (engine.population_treatment, recorded in each run's
    fixed_inputs): survey weights or reweighted, ages fixed, adjusted or aged forward, State Pension types held at
    the survey year or not. Today's treatment (all three from the survey) keeps the strip's original wording. The
    strip describes every run, so the central run and every trajectory must record the same treatment."""
    fixed = _get(results, "central.run.fixed_inputs")
    population = _get(results, "central.run.fixed_inputs.population")
    for run in _get(results, "trajectories.paths"):
        other = run.get("fixed_inputs", {}).get("population")
        if other != population:
            raise MissingFigure(f"trajectory {run.get('id')!r} records the population treatment {other!r}, the "
                                f"central run {population!r}: the strip can describe only one")
    weights, ages, types = (population.get(k) for k in ("weights", "ages", "pension_types"))
    spa = {y: _get(results, f"central.run.fixed_inputs.state_pension_age.{y}") for y in HORIZON}
    settled = min(y for y in HORIZON if all(spa[z] == spa[FINAL_YEAR] for z in HORIZON if z >= y))
    records = fixed.get("held_pension_type_records")
    if ages == "survey_year" and types == "survey_year" and records:
        # With ages and types both held, a type count can move only while the State Pension age rises.
        after = [records[str(y)] for y in HORIZON if y >= settled]
        if any(r != after[0] for r in after):
            raise MissingFigure(f"the held State Pension type counts move after {settled} although the run records "
                                "survey-year ages and types")
    fy = _fy(FINAL_YEAR)
    if (weights, ages, types) == ("survey", "survey_year", "survey_year"):
        title = "Today's pensioners, held fixed"
        text = (f"Survey ages and State Pension types are fixed to {fy}, so nobody new joins on the new State Pension; "
                "the number of pensioners changes only through the survey weights and the State Pension age. "
                "DWP's costing projects the population; ours does not.")
    else:
        aged = ages == "aged_forward"
        title = "Pensioners aged forward" if aged else _wording(
            {"ons_projection": "Today's pensioners, reweighted to the ONS projection",
             "ons_total": "Today's pensioners, reweighted to the ONS population total",
             "ons_age_sex_total": "Today's pensioners, reweighted to the matched population total",
             "reweighted": "Today's pensioners, reweighted", "survey": "Today's pensioners, partly held"},
            weights, "population.weights")
        text = " ".join([
            _wording({"survey_year": f"Each record keeps its survey age in every year to {fy}.",
                      "adjusted": f"Survey ages do not move between years to {fy}, though some differ from their "
                                  "survey values.",
                      "aged_forward": f"Survey ages are aged forward each year to {fy}."}, ages, "population.ages"),
            _wording({"survey_year": "Each person's State Pension type is held at its survey-year value.",
                      "cohort": "Each person's State Pension type follows their cohort: basic if they reached State "
                                "Pension age before 6 April 2016, new otherwise.",
                      "model": "State Pension types are the model's own."}, types, "population.pension_types"),
            _wording({"survey": "The survey weights are the dataset's own." if aged else
                                "The number of pensioners changes only through the survey weights and the State "
                                "Pension age.",
                      "ons_projection": "Household weights are raked each year to the ONS population projection by "
                                        "age and sex, so the number of pensioners follows it.",
                      "ons_total": "Household weights follow only the ONS population total; the survey's age "
                                   "and sex cells are not calibration constraints.",
                      "ons_age_sex_total": "Household weights are raked to the total implied by the anchored ONS "
                                           "age/sex targets, using one population margin without age/sex constraints.",
                      "reweighted": "The survey weights are reweighted in the run, so the number of pensioners "
                                    "follows that reweighting and the State Pension age."},
                     weights, "population.weights"),
            *([] if aged else
              ["DWP's costing projects the population; ours does not." if weights == "survey" else
               "DWP's costing projects the population; ours reweights the survey rather than ageing it."]),
        ])
    facts = {"final_year": FINAL_YEAR, "data_year": fixed.get("data_year"), **population,
             "state_pension_age": spa[FINAL_YEAR], "state_pension_age_settled_year": settled}
    return {"key": "population", "title": title, "text": text, "facts": facts}


def _paths_item(results):
    """The lowest and highest gross expected saving in the final year across the reweightings of the same full runs
    that may enter a quoted range (the dashboard's getSensitivityRange), and the shock models tested but not run
    through the fiscal model. A reweighting enters only when the estimator marked it included_in_quoted_range
    (expected_value.py: at least 100 effective runs), or, in a file without that flag, has at least 100 effective
    runs; the rest are counted and left out."""
    every = _get(results, "expected_value.sensitivities")
    # The range is the reweightings to past dynamics, which the text describes; any other family of sensitivities
    # (#14 §4's mean-path sensitivity, say) is counted and named outside it.
    dynamics = [name for name in every if name.startswith("shift_dynamics")]

    def quoted(name):
        flag = every[name].get("included_in_quoted_range")
        if isinstance(flag, bool):
            return flag
        runs = every[name].get("effective_runs")
        return isinstance(runs, (int, float)) and not isinstance(runs, bool) and 100 <= runs < float("inf")

    sens = [name for name in dynamics if quoted(name)]
    too_few = len(dynamics) - len(sens)
    if dynamics and not sens:
        raise MissingFigure(f"none of the {len(dynamics)} shift_dynamics reweightings rests on enough effective runs "
                            "to enter a quoted range")
    others = [name for name in every if name not in dynamics]
    if not sens:
        if "provenance" in results["expected_value"]:
            ev = results["expected_value"]
            return {"key": "paths", "title": "Model-conditional paths",
                    "text": ev["interpretation"] + ". Monte Carlo errors measure precision of this path set. "
                            "Mean-path variants are separate scenarios, not probability intervals.",
                    "facts": {"form": ev["form"], "uncertainty_ruling": ev["provenance"]}}
        raise MissingFigure("the assumptions block needs a shift_dynamics reweighting in "
                            "results.expected_value.sensitivities")
    rows =[(name, _get(results, "expected_value.sensitivities", name, "gross", str(FINAL_YEAR)),
             _get(results, "expected_value.sensitivities", name, "effective_runs")) for name in sens]
    low = min(rows, key=lambda r: r[1]["mean"])
    high = max(rows, key=lambda r: r[1]["mean"])
    primary = _get(results, "expected_value.primary")
    models = _get(results, "trajectories.models")
    run = [m for m, v in models.items() if v["runs_paths"]]
    not_run = [m for m, v in models.items() if not v["runs_paths"]]
    with_floor = sum(name.startswith("shift_dynamics_floor") for name in sens)
    floor = f"{_fixed(100 * TRIPLE_LOCK_FLOOR, 1).rstrip('0').rstrip('.')}%"
    facts = {
        "year": FINAL_YEAR, "measure": "gross", "calibration": primary, "reweightings": len(rows),
        "reweightings_too_few_runs": too_few, "min_effective_runs": 100,
        "reweightings_with_floor": with_floor, "floor": TRIPLE_LOCK_FLOOR,
        "lowest": {"calibration": low[0], "mean": low[1]["mean"], "se": low[1]["se"]},
        "highest": {"calibration": high[0], "mean": high[1]["mean"], "se": high[1]["se"], "effective_runs": high[2]},
        "other_sensitivities": others, "shock_models_run": run, "shock_models_not_run": not_run,
    }
    floor_text = ("" if not with_floor else f" (in some versions also how often the {floor} floor binds)"
                  if with_floor < len(rows) else f" (and how often the {floor} floor binds)")
    title = "One model of prices and earnings" if len(run) == 1 else "Several models of prices and earnings"
    text = (f"{_wording(PRIMARY_CALIBRATION_TEXT, primary, 'expected_value.primary')} Reweighting the same full runs "
            "to match how much the gap between earnings growth and CPI varied in the past and how often the lead "
            f"switched{floor_text} gives separate point estimates, the lowest "
            f"{_bn(low[1]['mean'])} gross (standard error {_bn(low[1]['se'])}) and the highest {_bn(high[1]['mean'])}, "
            f"which rests on about {_fixed(high[2], 0)} effective runs (standard error {_bn(high[1]['se'])}).")
    if too_few:
        count = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve")
        count = count[too_few] if too_few < len(count) else str(too_few)
        text += (f" {count} more reweighting{'' if too_few == 1 else 's'}, resting on fewer than 100 effective runs, "
                 f"{'is' if too_few == 1 else 'are'} left out of this range.")
    if others:
        text += f" The range leaves out {len(others)} other sensitivit{'y' if len(others) == 1 else 'ies'}."
    if not_run:
        if all(m in SHOCK_MODEL_NAMES for m in not_run):
            versions = f"{_join([SHOCK_MODEL_NAMES[m] for m in not_run])} versions are"
        else:  # a model with no short name: its own label from the results
            labels = "; ".join(_get(results, "trajectories.models", m, "label") for m in not_run)
            versions = f"other versions ({labels}) are"
        text += (" This range does not include another model of prices and earnings: "
                 f"{versions} tested against past forecasts (Methodology tab) but not run through the full fiscal "
                 "model.")
    if results["expected_value"].get("label") == "model-conditional":
        title = "Model-conditional paths"
        text = (results["expected_value"]["interpretation"] + ". " + text +
                " The scenario envelope is reported separately; it is not a probability interval.")
        facts["uncertainty_ruling"] = results["expected_value"]["provenance"]
    return {"key": "paths", "title": title, "text": text, "facts": facts}


def _benefits_item(results):
    """Pension Credit claims and pension-age Housing Benefit in the survey against DWP's, and the paired sensitivity
    dataset's difference in the final year's net saving. Great Britain against DWP's Great Britain, like for like,
    where the coverage rows give it (from model-v2); the UK model against it in a file built earlier."""
    row = {r["key"]: r for r in _get(results, "coverage.rows")}
    for key in ("pension_credit_claims_m", "housing_benefit_pension_age_bn"):
        if key not in row:
            raise MissingFigure(f"the assumptions block needs the coverage row {key}")
    gb = all("primary_gb" in row[k] for k in ("pension_credit_claims_m", "housing_benefit_pension_age_bn"))
    field = "primary_gb" if gb else "primary"
    claims, hb = ({"primary": row[k][field], "dwp": row[k]["dwp"]}
                  for k in ("pension_credit_claims_m", "housing_benefit_pension_age_bn"))
    year = _get(results, "coverage.year")
    # Historical interim pre-Budget (b) releases omitted the paired sensitivity runs.
    omitted = results["expected_value"].get("paired_sensitivity", {}).get("status") == "omitted"
    if omitted:
        dataset = _wording(sensitivity_dataset_names(), _get(results, "expected_value.paired_sensitivity.dataset"),
                           "expected_value.paired_sensitivity.dataset")
        diff, paired = None, 0
    else:
        diff = _get(results, f"expected_value.paired_difference.net.{FINAL_YEAR}")
        paired = sum(s["sensitivity_paths"] for s in _get(results, "expected_value.strata"))
        dataset = _wording(sensitivity_dataset_names(), _get(results, "expected_value.datasets.sensitivity"),
                           "expected_value.datasets.sensitivity")
    facts = {
        "coverage_year": year,
        "pension_credit_claims_m": {"primary": claims["primary"], "dwp": claims["dwp"]},
        "housing_benefit_pension_age_bn": {"primary": hb["primary"], "dwp": hb["dwp"]},
        "model_geography": "Great Britain" if gb else "UK",
        "dwp_geography": _get(results, "coverage.dwp.geography").split(",")[0],
        "paired_difference_net": ({"omitted": True, "dataset": dataset} if omitted else
                                  {"year": FINAL_YEAR, "mean": diff["mean"], "se": diff["se"], "paths": paired,
                                   "dataset": dataset}),
    }
    above = [r["primary"] > r["dwp"] for r in (claims, hb)]
    title = ("Survey benefit baselines above DWP's" if all(above) else
             "Survey benefit baselines below DWP's" if not any(above) else "Survey benefit baselines against DWP's")
    if gb:
        text = (f"In {_fy(year)} the survey has {_fixed(claims['primary'], 2)}m Pension Credit claims in Great Britain "
                f"against DWP's {_fixed(claims['dwp'], 2)}m, and {_bn(hb['primary'])} of pension-age Housing Benefit "
                f"against {_bn(hb['dwp'])}.")
    else:
        text = (f"In {_fy(year)} the survey has {_fixed(claims['primary'], 2)}m Pension Credit claims against DWP's "
                f"{_fixed(claims['dwp'], 2)}m, and {_bn(hb['primary'])} of pension-age Housing Benefit against "
                f"{_bn(hb['dwp'])}, a {facts['model_geography']} model against DWP's {facts['dwp_geography']} "
                "figures.")
    if omitted:
        text += f" The {dataset} dataset cross-check comes with the post-Budget release."
    elif paired > 0:
        text += (f" On the same {paired} paths, the {dataset} dataset gives a net saving {_bn(abs(diff['mean']))} "
                 f"{'higher' if diff['mean'] >= 0 else 'lower'} (standard error {_bn(diff['se'])}).")
    return {"key": "benefits", "title": title, "text": text, "facts": facts}


def assumptions(results):
    """What the headline figures are conditional on: [{key, title, text, facts}], the dashboard's "What these figures
    assume" strip. The wording is generated here, from how the runs treated the population and from the assembled
    results, so it changes when the model does; `facts` holds every number the text quotes. Raises MissingFigure when
    a figure is missing or a value has no wording, so the build fails rather than publish a stale strip."""
    # Worded from what the file will hold: in the build, run results carry integer year keys (jobs.run_jobs);
    # read back, every key is a string.
    # Private diagnostic payloads need not be JSON serializable. Omit them
    # before encoding while preserving the caller's original run dictionaries.
    results = json.loads(json.dumps(redact_records(deepcopy(results)), default=float))
    if "expected_value" not in results:
        ruling = results["uncertainty_ruling"]
        omission = (_get(results, "uncertainty_ruling.fallback_reason")
                    if ruling.get("requested_ruling") == "c" and ruling.get("effective_ruling") == "a"
                    else _get(results, "expected_value_omission.reason")
                    if results.get("release", {}).get("stage") == "pre-budget"
                    else "The recorded d955 ruling omits an expected value.")
        return [_population_item(results),
                {"key": "paths", "title": "Scenario envelope",
                 "text": omission + " Mean-path variants are scenarios, not probability claims.",
                 "facts": {"uncertainty_ruling": results["uncertainty_ruling"]}}]
    return [_population_item(results), _paths_item(results), _benefits_item(results)]


def scenario_envelope(central, central_run, scenario_runs, traj, mean_paths):
    """Carry independently run scenarios beside any model-conditional estimate.

    The decade replay is the existing historical counterfactual, with its
    original model years, rather than an extrapolation of those outcomes.
    """
    history = traj["history"]
    years = history["years"][-10:]
    first, last = years[0], years[-1]
    replay = next((group for group in history["groups"] if first in group["switch_years"]), None)
    if replay is None:
        raise MissingFigure(f"scenario envelope needs the historical replay starting in April {first}")
    wedge_spec, wedge_run = scenario_runs["obr_premium"]
    return {"interpretation": "scenario envelope; not a probability interval",
            "central": {"label": "Central forecast", "path": central,
                        "run": {k: v for k, v in central_run.items() if k != "model"}},
            "obr_wedge": {"label": wedge_spec["label"], "path": wedge_spec,
                          "run": {k: v for k, v in wedge_run.items() if k != "model"}},
            "last_decade_replay": {
                "label": f"Historical replay, April {first}–{last}",
                "interpretation": "historical legal replay; not a future forecast",
                "years": years, "switch_year": first,
                "statutory": {key: {y: history[key][y] for y in years} for key in ("cpi", "earnings")},
                "suspended_earnings_year": history["suspended_earnings_year"],
                "model_years": history["model_years"], "counterfactual": replay},
            "paired_earnings_mean_paths": mean_paths}


class PassportNotOnReceipt(RuntimeError):
    """The installed policyengine-uk does not key the pension-age Housing Benefit Guarantee Credit passport on receipt
    (housing_benefit_passport_preflight): the rebuild needs policyengine-uk#1927 (first released in 2.123.6) and
    refuses to run without it."""


def passport_probe_facts():
    """The preflight probe's inputs (passport_probe): synthetic, no survey record. A function, not a module constant,
    so the pilot's protected module-level assignments are unchanged (tests/cold_source_correspondence.py)."""
    return {"year": 2026, "age": 70, "state_pension": 10_000, "savings": 20_000, "rent": 6_240,
            "tenure_type": "RENT_FROM_COUNCIL"}


def passport_probe(receipt=None):
    """Two synthetic single pensioners as a policyengine-uk situation (passport_probe_facts), in benefit units
    ``non_claimant_benunit`` and ``claimant_benunit``, which differ only in whether they claim Pension Credit.

    Each is aged 70 with a £10,000 State Pension, £20,000 of savings and £6,240 a year of council rent. Under 2026's
    minimum guarantee both are entitled to Guarantee Credit (policyengine-uk 2.120.0 and 2.123.6 both calculate
    £1,336), and their savings are over pension-age Housing Benefit's £16,000 capital limit, so a means-tested family
    gets no Housing Benefit and a passported one the whole rent, its maximum (no non-dependants, no Local Housing
    Allowance). ``receipt`` ({"non_claimant": bool, "claimant": bool}) sets in_receipt_of_guarantee_credit on both
    benefit units, to check that the passport reads it."""
    facts = passport_probe_facts()
    year = facts["year"]
    people, benunits, households = {}, {}, {}
    for name, claims in (("non_claimant", False), ("claimant", True)):
        people[name] = {"age": {year: facts["age"]}, "state_pension_reported": {year: facts["state_pension"]}}
        benunits[f"{name}_benunit"] = {
            "members": [name], "would_claim_pc": {year: claims}, "would_claim_housing_benefit": {year: True},
            "would_claim_uc": {year: False},
            **({} if receipt is None else {"in_receipt_of_guarantee_credit": {year: receipt[name]}}),
        }
        households[f"{name}_household"] = {"members": [name], "rent": {year: facts["rent"]},
                                           "tenure_type": {year: facts["tenure_type"]},
                                           "savings": {year: facts["savings"]}}
    return {"people": people, "benunits": benunits, "households": households}


def passport_checks(claims, receipt, rent):
    """Named checks on original and reversed-receipt synthetic observations.

    Validate the complete observation domain before indexing, so stored provenance
    receives the same validation as a fresh calculation. Both calculations must
    preserve the pension-age, positive Guarantee Credit and Pension Credit claim
    premises; changing receipt alone must leave Guarantee Credit entitlement
    unchanged. Monetary outputs must stay within their valid bounds.

    The passport of SI 2006/214 reg 26 (NI: SR 2006/406 reg 24) disregards all
    capital and income on receipt of Guarantee Credit, on all three HB branches.
    """
    from math import isfinite
    from numbers import Real

    import numpy as np

    disregarded = ("housing_benefit_assessable_capital", "housing_benefit_tariff_income",
                   "housing_benefit_applicable_income")
    regulations = "housing_benefit_pension_age_regulations_apply"
    monetary = ("guarantee_credit", "pension_credit", *disregarded, "housing_benefit")
    domain = "both probe calculations contain exactly two finite real non-Boolean monetary values and Boolean regulation flags per variable"
    boolean = (bool, np.bool_)

    def real(value):
        if not isinstance(value, Real) or isinstance(value, boolean):
            return False
        try:
            return isfinite(value)
        except (OverflowError, TypeError, ValueError):
            return False

    def valid(values):
        if not isinstance(values, dict) or set(values) != {regulations, *monetary}:
            return False
        if any(not isinstance(items, (list, tuple, np.ndarray))
               or (isinstance(items, np.ndarray) and items.ndim != 1)
               or len(items) != 2 for items in values.values()):
            return False
        return (all(isinstance(value, boolean) for value in values[regulations])
                and all(real(value) for variable in monetary for value in values[variable]))

    if not real(rent) or rent <= 0 or not all(valid(values) for values in (claims, receipt)):
        return [(domain, False)]

    def maximum(values, i):
        return 0 <= values["housing_benefit"][i] <= rent and abs(values["housing_benefit"][i] - rent) <= 0.01

    def passported(values, i):
        return all(values[v][i] == 0 for v in disregarded) and maximum(values, i)

    def means_tested(values, i):
        return (all(values[v][i] > 0 for v in disregarded)
                and 0 <= values["housing_benefit"][i] < rent and not maximum(values, i))

    calculations = (claims, receipt)
    return [
        (domain, True),
        ("both probe calculations have non-negative monetary values and Housing Benefit no greater than rent",
         all(value >= 0 for values in calculations for variable in monetary for value in values[variable])
         and all(value <= rent for values in calculations for value in values["housing_benefit"])),
        ("the probe is under the pension-age Housing Benefit regulations",
         all(bool(value) for values in calculations for value in values[regulations])),
        ("both probe benefit units are entitled to Guarantee Credit (guarantee_credit > 0)",
         all(value > 0 for values in calculations for value in values["guarantee_credit"])),
        ("Guarantee Credit entitlement is unchanged by claim and receipt overrides",
         max(value for values in calculations for value in values["guarantee_credit"])
         - min(value for values in calculations for value in values["guarantee_credit"]) <= 0.01),
        ("only the claimant is paid Pension Credit",
         all(values["pension_credit"][0] == 0 < values["pension_credit"][1] for values in calculations)),
        ("the claimant's Pension Credit includes its Guarantee Credit entitlement in both calculations",
         all(values["pension_credit"][1] >= values["guarantee_credit"][1] for values in calculations)),
        *((f"the entitled non-claimant's {v} is counted, not disregarded", claims[v][0] > 0) for v in disregarded),
        ("the entitled non-claimant is not passported to maximum Housing Benefit", means_tested(claims, 0)),
        *((f"the claimant's {v} is disregarded", claims[v][1] == 0) for v in disregarded),
        ("the claimant, in receipt of Guarantee Credit, is passported to maximum Housing Benefit",
         maximum(claims, 1)),
        ("in_receipt_of_guarantee_credit set true passports the non-claimant", passported(receipt, 0)),
        ("in_receipt_of_guarantee_credit set false means-tests the claimant", means_tested(receipt, 1)),
    ]


def housing_benefit_passport_preflight(simulate=None, log=print):
    """Refuse to run the rebuild unless the installed policyengine-uk keys the Housing Benefit Guarantee Credit
    passport on receipt, as policyengine-uk#1927 does (first released in 2.123.6).

    Keyed on entitlement (``guarantee_credit > 0``), as in policyengine-uk 2.120.0, the passport gives a pensioner whom
    the Burnham plan makes entitled to Guarantee Credit maximum Housing Benefit without a Pension Credit claim. The
    check is behavioural: it calculates passport_probe in the installed model (``simulate``: situation -> simulation,
    by default policyengine_uk.Simulation), once with claims as given and once with in_receipt_of_guarantee_credit
    set, and requires every passport_checks check. Returns what it observed, for the run's provenance; raises
    PassportNotOnReceipt naming each failing check. Called before any model job by build, mean_path_scenarios,
    scenario and both ageing command entry points; the pilot scripts, which replay the 2.120.0 record, never call it.
    """
    import importlib.metadata
    from math import isfinite

    facts = passport_probe_facts()
    variables = ("housing_benefit_pension_age_regulations_apply", "guarantee_credit", "pension_credit",
                 "housing_benefit_assessable_capital", "housing_benefit_tariff_income",
                 "housing_benefit_applicable_income", "housing_benefit")
    calculations = {"claims": None, "receipt_set": {"non_claimant": True, "claimant": False}}
    try:
        version = importlib.metadata.version("policyengine-uk")
    except importlib.metadata.PackageNotFoundError:
        version = "(not installed)"
    problem = (f"The rebuild needs policyengine-uk#1927 (https://github.com/PolicyEngine/policyengine-uk/pull/1927, "
               f"first released in policyengine-uk 2.123.6), which keys the Housing Benefit Guarantee Credit passport "
               f"on receipt (in_receipt_of_guarantee_credit), not entitlement. The installed policyengine-uk {version}")
    remedy = ("Install the certified d778 bundle, which must pin policyengine-uk 2.123.6 or later "
              "(docs/REBUILD.md, What it waits for).")
    observed = {}
    try:
        if simulate is None:
            from policyengine_uk import Simulation

            def simulate(situation):
                return Simulation(situation=situation)

        for name, receipt in calculations.items():
            sim = simulate(passport_probe(receipt))
            observed[name] = {v: [x.item() if hasattr(x, "item") else x for x in sim.calculate(v, facts["year"])]
                              for v in variables}
            for variable, values in observed[name].items():
                if len(values) != 2 or not all(isfinite(value) for value in values):
                    raise ValueError(f"{name}.{variable}: expected two finite synthetic-household values, got {values!r}")
        checks = passport_checks(observed["claims"], observed["receipt_set"], facts["rent"])
    except Exception as error:
        raise PassportNotOnReceipt(
            f"{problem} could not calculate the preflight probe "
            f"(housing_benefit_passport_preflight): {error!r}. {remedy}") from error
    failing = [name for name, passed in checks if not passed]
    if failing:
        raise PassportNotOnReceipt(
            f"{problem} fails the preflight check of the Housing Benefit Guarantee Credit passport:\n"
            + "".join(f"  - failed: {name}\n" for name in failing)
            + f"Observed, [non-claimant, claimant]: {json.dumps(observed, sort_keys=True, default=float)}\n{remedy}")
    log(f"Preflight: policyengine-uk {version} keys the Housing Benefit Guarantee Credit passport on receipt "
        "(policyengine-uk#1927)")
    return {"housing_benefit_guarantee_credit_passport": {
        "keyed_on": "receipt", "upstream": "PolicyEngine/policyengine-uk#1927", "first_release": "2.123.6",
        "policyengine_uk": version, "probe": facts, "checks": [name for name, _ in checks], "observed": observed}}


PRE_BUDGET_RULINGS = ("a", "b", "c")
# The frozen C2 dry run (docs/pilot/C2-dry-run.md): its score table and the primary's path design, on today's inputs.
C2_DRY_RUN = REPO / "data" / "pilot" / "c2-dry-run"


def c2_dry_run():
    """The committed C2 dry-run handoff, and the primary's pre-registered C2 scores it records (test A, suspended)."""
    from . import ts_uncertainty as TU

    manifest = json.loads((C2_DRY_RUN / "handoff.json").read_text())
    if manifest.get("screen") != "c2" or manifest.get("run_kind") != "dry_run":
        raise SystemExit(f"{C2_DRY_RUN / 'handoff.json'} is not the C2 dry-run handoff")
    try:
        TU.validate_c2_handoff(manifest, require_binding=False)
    except ValueError as error:
        raise SystemExit(f"invalid C2 dry-run handoff: {error}") from error
    row = manifest["score_table"]["scores"]["A"]["suspended"][TU.PRIMARY_FORM]
    scores = {"terminal_hits": row["terminal_coverage"]["hits"], "terminal_origins": row["terminal_scored_origins"],
              "annual_coverage": row["annual_gap_coverage"]["mean"], "annual_cells": row["annual_gap_cells"]}
    return manifest, scores


def pre_budget_release(uncertainty_ruling):
    """The ``release`` block of an interim pre-Budget file (``triple-lock-build --pre-budget``; docs/REBUILD.md,
    Interim pre-Budget release).

    Ruling (c) publishes a provisional, model-conditional expected value only after the frozen C2 dry-run
    integrity checks, with the paired sensitivity runs. Ruling (a) shows scenarios only. The obsolete public (b)
    route is refused. The binding C2 check follows the Budget inputs; primary failure then removes the expected
    value. Refuse once inputs no longer match the pre-Budget vintage named by this block.
    """
    from .config import CPI_PERIOD

    from .ts_uncertainty import C2_BUDGET_DATE

    budget_label = f"{C2_BUDGET_DATE.day} {C2_BUDGET_DATE:%B %Y}"
    if uncertainty_ruling == "b":
        raise SystemExit("--pre-budget --uncertainty-ruling b is obsolete: use c for the provisional C2-checked "
                         "expected value with paired Enhanced FRS sensitivity runs, or a for scenarios only.")
    if uncertainty_ruling not in ("a", "c"):
        raise SystemExit("--pre-budget writes an interim file and requires --uncertainty-ruling a or c "
                         "(docs/REBUILD.md, Interim pre-Budget release).")
    if CPI_PERIOD != "2026 AUG" or "March 2026" not in central_module.EFO_SOURCE:
        raise SystemExit(f"--pre-budget describes August 2026 CPI and the OBR's March 2026 forecast, but the committed "
                         f"inputs use CPI_PERIOD={CPI_PERIOD!r} and {central_module.EFO_SOURCE!r}: use the binding "
                         "route (docs/REBUILD.md, Commands).")
    release = {"stage": "pre-budget", "interim": True, "execution_ruling": uncertainty_ruling,
               "forecast": "OBR March 2026", "forecast_source": central_module.EFO_SOURCE,
               "cpi_period": CPI_PERIOD,
               "april_2027_cpi_leg": "August 2026 CPI (provisional; September published 21 Oct)",
               "expected_value": f"withheld until the binding C2 score on the {budget_label} Budget inputs",
               "recorded_ruling": "c", "budget_date": C2_BUDGET_DATE.isoformat(),
               "binding_route": "triple-lock-build --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2"}
    if uncertainty_ruling == "c":
        _, scores = c2_dry_run()
        release["provisional"] = True
        release["c2_dry_run"] = scores
        release["expected_value"] = (
            f"provisional under ruling (c): model-conditional; the primary passes the pre-registered C2 screen in the dry run on current "
            f"data ({scores['terminal_hits']} of {scores['terminal_origins']} terminal, "
            f"{scores['annual_coverage']:.0%} annual); the binding check runs on the {budget_label} Budget inputs, "
            "and if it fails the update drops the expected value and says why")
    return release


def check_dry_run_design(output, manifest):
    """A provisional (c) file runs the C2 dry run's own primary paths: the handoff the build generated must hold the
    same path design and specs, and the same paired mean-path specs, byte for byte."""
    import hashlib
    from . import ts_uncertainty as TU

    names = [f"{TU.PRIMARY_FORM}.design.json", f"{TU.PRIMARY_FORM}.specs.json",
             *(meta["specs_file"] for meta in manifest["mean_paths"].values())]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    differ = [name for name in names if digest(output / name) != digest(C2_DRY_RUN / name)]
    if differ:
        raise SystemExit("--pre-budget --uncertainty-ruling c needs the C2 dry run's primary paths, but these differ "
                         f"from {C2_DRY_RUN}: {', '.join(differ)}")
    return names


def label_provisional_c(ev, manifest, scores):
    """Relabel the primary's model-conditional expected value as provisional under the recorded ruling (c).

    The primary's paths are the C2 dry run's (check_dry_run_design), which it passes; the provenance is the dry run's
    C2 provenance (run_kind "dry_run", no binding authorization) with the interim labels added.
    """
    from .ts_uncertainty import C2_BUDGET_DATE, PRIMARY_FORM

    budget_label = f"{C2_BUDGET_DATE.day} {C2_BUDGET_DATE:%B %Y}"
    description = (f"Provisional, model-conditional pre-Budget release under the recorded d955 ruling (c): the original primary passes "
                   f"the pre-registered C2 screen in the dry run on current data ({scores['terminal_hits']} of "
                   f"{scores['terminal_origins']} terminal, {scores['annual_coverage']:.0%} annual), so the expected "
                   f"value is shown as provisional. The binding C2 check runs on the {budget_label} Budget inputs; if "
                   "it fails, the update drops the expected value and says why.")
    if not manifest["c2_outcome"]["forms"][PRIMARY_FORM]["passes"]:
        raise SystemExit("the original primary fails the C2 dry run: a provisional (c) file has no expected value")
    provenance = {**expected_value._c2_provenance(manifest, manifest["c2_outcome"]),
                  "release_stage": "pre-budget", "interim": True, "provisional": True, "recorded_ruling": "c",
                  "authorization": "Provisional pre-Budget release on the C2 dry run; the binding check follows the "
                                   f"{budget_label} Budget",
                  "description": description}
    ev = {**ev, "provenance": provenance, "adequacy": manifest["c2_outcome"],
          # The banner and release block say it is provisional; the strip quotes this once.
          "interpretation": expected_value.UNCERTAINTY_RULINGS["c"]}
    if ev.get("mean_path_scenarios") is not None:
        means = ev["mean_path_scenarios"]
        ev["mean_path_scenarios"] = {**means, "provenance": {
            **provenance, "description": "Paired mean-path scenarios; independent of the C2 adequacy gate",
            "expected_value_authorized": False,
            "authorization": "Paired mean-path scenarios: this command does not authorize an expected value"}}
    return ev


def label_pre_budget(ev):
    """Label a scenarios-only (a) result as interim under the recorded ruling (c)."""
    from .ts_uncertainty import C2_BUDGET_DATE

    if ev["provenance"]["ruling"] != "a":
        raise ValueError("only scenarios-only ruling (a) uses label_pre_budget; use provisional (c) for expected value")
    budget_label = f"{C2_BUDGET_DATE.day} {C2_BUDGET_DATE:%B %Y}"
    interim = {"release_stage": "pre-budget", "interim": True, "recorded_ruling": "c",
               "description": "Interim pre-Budget release under the recorded d955 ruling (c): scenario envelope "
                              f"only, no expected value until the binding C2 score on the {budget_label} Budget "
                              "inputs. Not a new d955 ruling."}
    ev = {**ev, "provenance": {**ev["provenance"], **interim},
          "reason": "Withheld pending the post-Budget binding score. This interim pre-Budget release shows "
                    "scenarios only; the recorded d955 ruling (c) scores the expected value on the "
                    f"{budget_label} Budget inputs, so this file is not a new d955 ruling."}
    if ev.get("mean_path_scenarios") is not None:
        means = ev["mean_path_scenarios"]
        ev["mean_path_scenarios"] = {**means, "provenance": {**means["provenance"], **interim}}
    return ev


def build(workers=3, allow_dirty=False, log=print, sensitivity_workers=1,
          uncertainty_ruling=None, uncertainty_handoff=None, pre_budget=False, mean_paths=True):
    """The results file and every registered scenario run: (results, {scenario id: run}).

    One full build refreshes both, so no scenario file is left stale by a rebuild; ``triple-lock-build --scenario
    NAME`` reruns one alone. ``pre_budget`` labels an interim file (pre_budget_release). With ruling (c) it runs the
    primary on the C2 dry run's own paths through the model-conditional route and labels the result provisional
    (label_provisional_c); the binding (c) build needs the frozen post-Budget handoff instead.

    ``mean_paths=False`` builds the scenarios-first interim file (scenarios_first): every job of the full build
    except the paired mean paths, which are most of the jobs. It is allowed only where the file has no expected
    value anyway: ruling (a), or a binding (c) handoff whose primary failed C2. Its jobs are the full build's, so
    the full build reuses them from the job cache.
    """
    expected_value._ruling(uncertainty_ruling)
    if not mean_paths and (pre_budget or uncertainty_ruling not in ("a", "c")):
        raise SystemExit("a scenarios-first file needs --uncertainty-ruling a, or c with the binding handoff, and "
                         "no --pre-budget")
    release = pre_budget_release(uncertainty_ruling) if pre_budget else None
    provisional_c = pre_budget and uncertainty_ruling == "c"
    dry_run = c2_dry_run() if provisional_c else None
    start = snapshot()
    if start["git_dirty"] and not allow_dirty:
        raise SystemExit("The git tree has uncommitted changes outside the build's own outputs (data/results.json, "
                         "its dashboard copy and data/scenarios/*.json): commit first, or pass --allow-dirty (the "
                         "file will say so).")
    central = central_module.central_path()
    # Reject an unfrozen, stale or dry-run C2 handoff before any fiscal job.
    if uncertainty_ruling == "c" and not provisional_c:
        _, manifest = expected_value._handoff(central, None, "c", uncertainty_handoff, log)
        if not mean_paths:
            scenarios_first_ruling(manifest)
    certified = certified_bundle_preflight(log=log)
    # Before any PolicyEngine job: the installed model must key the Housing Benefit passport on receipt.
    start["preflight"] = {**certified, **housing_benefit_passport_preflight(log=log)}
    from policyengine_uk.system import system

    parameters = system.parameters
    base = engine.base_levels(parameters)

    log("Central path")
    central_run = jobs.run_jobs([("path", {k: v for k, v in trajectories.central_spec(central).items()
                                             if k not in ("id", "label", "source")})],
                                  workers=1, slot_prefix="efrs", log=log)[0]
    log("Dataset coverage")
    hist = central_module.september_cpi_history()
    cov_spec = {k: v for k, v in trajectories.central_spec(central).items() if k not in ("id", "label", "source")}
    cov_runs = jobs.run_jobs([("coverage", {"years": COVERAGE_YEARS, "september_cpi_history": hist,
                                            "spec": cov_spec}),
                              ("coverage", {"years": COVERAGE_YEARS, "dataset": SENSITIVITY_DATASET,
                                            "september_cpi_history": hist, "spec": cov_spec})],
                             workers=1, slot_prefix="microcosm", log=log)
    ev = expected_value.build(central, base["new_state_pension"], log=log, workers=workers,
                              sensitivity_dataset=SENSITIVITY_DATASET, sensitivity_workers=sensitivity_workers,
                              # A provisional (c) file runs the primary through the model-conditional route.
                              uncertainty_ruling="b" if provisional_c else uncertainty_ruling,
                              handoff_path=uncertainty_handoff,
                              paired_sensitivity=True, mean_paths=mean_paths)
    if not mean_paths and ev.get("status") != "skipped":
        raise SystemExit("a scenarios-first file must have no expected value")
    traj = trajectories.build(central, base, actual_weekly(parameters), workers=workers, log=log)
    log("Scenario runs")
    scenario_runs = run_scenarios(central, sorted(trajectories.SCENARIOS), log=log)
    if provisional_c:
        check_dry_run_design(Path(uncertainty_handoff) if uncertainty_handoff else REPO / ".cache" / "uncertainty-adapter",
                             dry_run[0])
        ev = label_provisional_c(ev, *dry_run)
    elif release is not None:
        ev = label_pre_budget(ev)
    ruling = ev["provenance"]
    mean_paths = ev.pop("mean_path_scenarios", None)
    screen = {key: ruling[key] for key in ("screen", "rule_sha", "run_kind", "c1_failure", "c2_outcome",
                                         "rule_section_sha256", "scoring_inputs_sha256",
                                         "score_table_sha256", "c2_scores", "scoring_head",
                                         "expected_value_authorized", "authorization")
              if key in ruling}

    results = {
        "sample": False,
        "horizon": HORIZON,
        "final_year": FINAL_YEAR,
        "switch_year": SWITCH_YEAR,
        "distribution_years": DISTRIBUTION_YEARS,
        "policies": published_policies(),
        "base_year_weekly": {"year": BASE_YEAR, **{k: round(v, 2) for k, v in base.items()}},
        **({"release": release} if release is not None else {}),
        "central": {"path": central, "run": {k: v for k, v in central_run.items() if k != "model"}},
        **({"expected_value": ev} if ev.get("status") != "skipped" else {}),
        "uncertainty_ruling": ruling,
        **({"expected_value_omission": {"requested_ruling": ruling.get("requested_ruling", ruling["ruling"]),
                                        "effective_ruling": ruling.get("effective_ruling", ruling["ruling"]),
                                        "reason": ev["reason"]}} if ev.get("status") == "skipped" else {}),
        **({"uncertainty_screen": screen} if screen else {}),
        "mean_path_scenarios": mean_paths,
        "scenario_envelope": scenario_envelope(central, central_run, scenario_runs, traj, mean_paths),
        "trajectories": traj,
        "coverage": coverage({"primary": cov_runs[0], "sensitivity": cov_runs[1]}),
        "dwp_uprating_analysis": dwp.UPRATING_ANALYSIS,
        # A pre-Budget file awaits the binding score: it keeps the historical note (METHOD_LIMITATIONS), which the
        # dashboard files under the expected saving to come.
        "method_limitations": method_limitations(omitted=None if ev.get("status") != "skipped" or release is not None
                                                 else "c2" if ruling.get("requested_ruling", ruling["ruling"]) == "c"
                                                 else "ruling"),
    }
    redact_records(results)
    results["assumptions"] = assumptions(results)
    results["benchmarks"] = load_benchmarks(results, skip_expected_value=ev.get("status") == "skipped")
    if ev.get("status") == "skipped":
        # Said, not silently dropped: these compare a figure the file does not have.
        from .benchmarks import expected_value_benchmarks
        results["benchmarks_omitted"] = [{**b, "reason": "It compares the expected value, which this file omits."}
                                         for b in expected_value_benchmarks()]
    check_unchanged(start, "the end of the build")
    import importlib.metadata as md

    results["provenance"] = {
        **start,
        "snapshot": "revision, dirty flag and hashes taken when the build started; rechecked at its end",
        "engine_hashes": engine.engine_hashes(),
        "packages": package_versions(),
        # The installed bundle and primary dataset's certification (datasets.provenance).
        "model": central_run["model"],
        "datasets": {"primary": central_run["model"]["dataset"], "sensitivity": SENSITIVITY_DATASET},
        "forecast_vintages": forecast_vintages(central),
        "uncertainty_ruling": ruling,
        **({"uncertainty_screen": screen} if screen else {}),
        **({"release": release} if release is not None else {}),
    }
    if not mean_paths:
        results["scenarios_first"] = results["provenance"]["scenarios_first"] = scenarios_first_label()
    scenarios = {name: scenario_record(spec, run, start, "build")
                 for name, (spec, run) in scenario_runs.items()}
    return results, scenarios


def scenarios_first_ruling(manifest):
    """Refuse a scenarios-first file on a binding handoff whose primary passed C2: that file has an expected value."""
    provenance = expected_value._c2_provenance(manifest, manifest["c2_outcome"])
    if provenance["effective_ruling"] != "a":
        raise SystemExit("the binding C2 primary passed, so the file has an expected value: run the full build")
    return provenance


def scenarios_first_label():
    """What a scenarios-first interim file is and what it leaves out (pipeline.build with mean_paths=False)."""
    return {
        "interim": True,
        "contents": ("every run of the full build except the paired mean paths: the central path, the coverage "
                     "runs, the trajectories, the past-year cases and the scenario runs, from the same jobs the full "
                     "build reuses"),
        "omits": ["mean_path_scenarios", "scenario_envelope.paired_earnings_mean_paths"],
        "complete_build": ("triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c "
                           "--uncertainty-handoff out/uncertainty-c2"),
    }


def mean_path_scenarios(workers=3, allow_dirty=False, uncertainty_ruling=None,
                        handoff_path=None, log=print):
    """Standalone paired scenarios; their execution does not require a passing macro model."""
    start = snapshot()
    if start["git_dirty"] and not allow_dirty:
        raise SystemExit("Commit changes first, or pass --allow-dirty for recorded scenario provenance")
    certified = certified_bundle_preflight(log=log)
    # Before any PolicyEngine job: the installed model must key the Housing Benefit passport on receipt.
    start["preflight"] = {**certified, **housing_benefit_passport_preflight(log=log)}
    from policyengine_uk.system import system
    result = expected_value.build_mean_path_scenarios(
        central_module.central_path(), engine.base_levels(system.parameters)["new_state_pension"],
        log=log, workers=workers, uncertainty_ruling=uncertainty_ruling, handoff_path=handoff_path)
    check_unchanged(start, "the end of the mean-path scenario runs")
    result["provenance"].update({**start, "packages": package_versions(), "engine_hashes": engine.engine_hashes()})
    return redact_records(result)


def run_scenarios(central, names, log=print):
    """{name: (spec, full run)} for the named scenarios (trajectories.SCENARIOS): one engine job each, cached."""
    specs = [trajectories.SCENARIOS[name](central) for name in names]
    for spec in specs:
        log(f"Scenario {spec['id']}: {spec['label']}")
    runs = jobs.run_jobs([("path", {k: v for k, v in spec.items() if k not in ("id", "label", "source")})
                            for spec in specs], workers=1, slot_prefix="efrs", log=log)
    return {name: (spec, run) for name, spec, run in zip(names, specs, runs)}


def scenario_record(spec, run, start, what):
    """A scenario run as data/scenarios/NAME.json holds it: its inputs, the run and the provenance the results file
    records (``start``: the snapshot of the build or single run, ``what``), records redacted."""
    run = dict(run)
    model = run.pop("model")
    return redact_records({
        **{k: spec[k] for k in ("id", "label", "source", "specified_rates")},
        "run": run,
        "provenance": {
            **start,
            "snapshot": f"revision, dirty flag and hashes taken when the {what} started; rechecked at its end",
            "engine_hashes": engine.engine_hashes(),
            "packages": package_versions(),
            "model": model,
            "datasets": {"primary": model["dataset"]},
        },
    })


def scenario(name, allow_dirty=False, log=print):
    """One scenario run alone (a full build runs them all), redacted, with the provenance the results file records.

    Nothing else in the build runs, and the results file is untouched.
    """
    start = snapshot()
    if start["git_dirty"] and not allow_dirty:
        raise SystemExit("The git tree has uncommitted changes outside the build's own outputs (data/results.json, "
                         "its dashboard copy and data/scenarios/*.json): commit first, or pass --allow-dirty (the "
                         "file will say so).")
    certified = certified_bundle_preflight(log=log)
    # Before any PolicyEngine job: the installed model must key the Housing Benefit passport on receipt.
    start["preflight"] = {**certified, **housing_benefit_passport_preflight(log=log)}
    spec, run = run_scenarios(central_module.central_path(), [name], log=log)[name]
    check_unchanged(start, "the end of the scenario run")
    return scenario_record(spec, run, start, "run")


def rehearsal_output_directory(directory):
    """A separate workspace cache/output directory, never a publication tree."""
    directory = Path(directory).resolve()
    allowed = (REPO / ".cache", REPO / "out")
    if (not directory.is_relative_to(REPO.resolve())
            or any(directory.is_relative_to((REPO / tree).resolve()) for tree in ("data", "dashboard"))
            or not any(directory.is_relative_to(root.resolve()) and directory != root.resolve() for root in allowed)):
        raise ValueError("rehearsal output directory must be a separate directory below workspace .cache/ or out/")
    if any(part.lower() == "results.json" for part in directory.parts):
        raise ValueError("rehearsal cannot produce results.json")
    return directory


def _rehearsal_metadata(value):
    if isinstance(value, dict):
        if value.get("rehearsal") is True or value.get("run_kind") == "rehearsal":
            yield value
        for child in value.values():
            yield from _rehearsal_metadata(child)
    elif isinstance(value, list):
        for child in value:
            yield from _rehearsal_metadata(child)


def validate_write_paths(results, paths):
    """Check every publication boundary before opening a destination."""
    paths = [Path(path) for path in paths]
    if any(_rehearsal_metadata(results)):
        output = results.get("rehearsal_output_dir")
        if output is None:
            raise ValueError("rehearsal writes require a separate rehearsal_output_dir")
        directory = rehearsal_output_directory(REPO / output)
        # Validate every destination before writing any. resolve() also catches
        # existing symlinks that lead into the publication trees.
        if any(path.name.lower() == "results.json" or path.resolve().name.lower() == "results.json"
               or not path.resolve().is_relative_to(directory)
               or path.resolve() == directory for path in paths):
            raise ValueError("rehearsal cannot produce results.json or write outside its separate output directory")
    return paths


def _reject_rehearsal_hardlinks(paths):
    for path in paths:
        try:
            links = path.stat().st_nlink
        except FileNotFoundError:
            continue
        if links > 1:
            raise ValueError("rehearsal cannot write a multiply linked destination")


def _write_rehearsal_receipt(results, path, text):
    """Replace a rehearsal receipt without truncating any existing inode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Revalidate after writing the temporary bytes: a destination can
        # become a publication alias while serialization is in progress.
        validate_write_paths(results, [path])
        _reject_rehearsal_hardlinks([path])
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write(results, paths):
    paths = validate_write_paths(results, paths)
    rehearsal = any(_rehearsal_metadata(results))
    if rehearsal:
        # Reject every hardlink before producing even the first receipt.
        _reject_rehearsal_hardlinks(paths)
    text = json.dumps(results, indent=1, default=float, allow_nan=False) + "\n"
    for path in paths:
        if rehearsal:
            _write_rehearsal_receipt(results, path, text)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        print(f"Results written to {path}")
