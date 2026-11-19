"""B1: full PolicyEngine UK runs on a weighted sample of the Bayesian forecast's paths (docs/METHOD.md, "Specification:
full runs on a weighted sample of the Bayesian paths, 18 November 2026").

Runs on policyengine.py 6.20.2 / policyengine-uk 2.179.1 / policyengine-core 3.34.10 and the Microcosm national file
6.20.2 certifies (fcfac709), in its own virtualenv (.venv-pe620). The engine's version and dataset pins are relaxed
here only, in memory, by ``patch()``: the published pipeline (datasets.py, model_horizon.py, engine.py) is unchanged,
and nothing here writes data/results.json. Every run-time PathNotFollowed / NotDecomposable check in the engine stays
live; ``patch()`` replaces only the upstream source-hash guard (model_horizon.check_upstream), with a guard for this
exact version that fails on any guarded file changing beyond the reviewed list.

    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py anchors
    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py design --n 100
    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py run --workers 2
    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py estimate     # rewrites estimates
    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py supplement   # unregistered check; after estimate
    PYTHONPATH=src .venv-pe620/bin/python scripts/b1_full_runs.py report

``run --with-wedge`` queues both anchors with the sample. B1_SAFETY_GIB sets the admission headroom (default 6), and
.cache/b1_full_runs/workers (an integer) sets live how many worker threads take new jobs.

Each job runs in its own process (``--job INPUT OUTPUT``, which applies the same patch); each result is cached under
.cache/b1_full_runs as it completes, keyed by its input, the engine's semantics, the package versions and the patch's
own source, so an interrupted night resumes where it stopped.
"""

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import resource
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

EXPECTED_VERSIONS = {"policyengine": "6.20.2", "policyengine-uk": "2.179.1", "policyengine-core": "3.34.10"}
DATASET = "microcosm_uk_2024_25@fcfac709"
DATA_REPO = "policyengine/populace-uk-private"
DATA_REVISION = "ad84c0602ed28f694ef52662eb9b063779e4e923"
DATA_BUILD = "uk-frs-calibration-attempt-20261115T104657Z-fcfac709"
DATA_PATH = f"releases/microcosm-uk-2024-25-national/{DATA_BUILD}/microcosm_uk_2024_25.h5"
DATA_SHA256 = "301d2fe5e7805c5a6242b37843cb118445aefd59a0593833362ab5a6e2f9ba90"

OUT_JSON = ROOT / "data" / "b1" / "full_runs.json"
REPORT = ROOT / "data" / "b1" / "full_runs_report.md"
CACHE = ROOT / ".cache" / "b1_full_runs"
WORKDIR = CACHE / "work"
LOG_DIR = Path("/private/tmp/claude-501/b1_full_runs")

SAMPLE_SEED = 20261118
BOOT_SEED = 20261118
N_BOOT = 2000
MIN_PER_STRATUM = 4
PROBABILITY_BOUNDS = (0.0, 0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 0.90, 0.95, 0.99, 1.0)
FINAL = 2039
ATTEMPTS = 2  # a failed run is retried once
SAFETY_GIB = float(os.environ.get("B1_SAFETY_GIB", "6.0"))  # headroom kept free beyond each admitted job's peak

# Guarded upstream files (model_horizon.D1727_UPSTREAM / _PARAMETERS, the 2.153.4 set, which already has #2576) that
# differ on policyengine-uk 2.179.1. Each was diffed against 2.153.4 (report, "Adaptations"); any other guarded file
# changing fails the run, as model_horizon.check_upstream would.
REVIEWED_CHANGED_2179 = (
    "policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices",
    "policyengine_uk.utils.parameters",
    "policyengine_uk.tax_benefit_system",
    "policyengine_uk.variables.gov.gov_tax",
    "policyengine_uk.variables.gov.gov_spending",
    "policyengine_uk.variables.input.state_pension",
    "policyengine_uk.variables.gov.dwp.basic_state_pension",
    "policyengine_uk.variables.gov.dwp.new_state_pension",
    "policyengine_uk.variables.gov.dwp.additional_state_pension",
    "policyengine_uk.variables.household.demographic.months_since_last_birthday",
    "policyengine_uk.variables.gov.dwp.state_pension_reported",
    "policyengine_uk.simulation",
    "policyengine_uk.parameters.gov.economic_assumptions.create_earnings_uprating",
    "policyengine_uk.parameters.gov.dwp.pension_credit.savings_credit.create_savings_credit_threshold",
    "policyengine_uk.parameters.gov.dwp.housing_benefit.allowances.create_pension_age_allowances",
    "parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml",
    "parameters/gov/dwp/pension_credit/savings_credit/threshold.yaml",
    "parameters/gov/dwp/pension_credit/savings_credit/maximum.yaml",
    "parameters/gov/dwp/housing_benefit/allowances/single/aged.yaml",
    "parameters/gov/dwp/housing_benefit/allowances/couple/aged.yaml",
    "parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged.yaml",
)
# The builders whose horizons the engine's single extension relies on, and how a Scenario reaches a simulation: these
# must be byte-identical to the reviewed 2.153.4 files.
MUST_BE_UNCHANGED = (
    "policyengine_uk.parameters.gov.economic_assumptions.lag_cpi",
    "policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings",
    "policyengine_uk.parameters.gov.economic_assumptions.lagged_series",
    "policyengine_uk.parameters.gov.economic_assumptions.create_statutory_uprating_inputs",
    "policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock",
    "policyengine_uk.parameters.gov.contrib.create_private_pension_uprating",
    "policyengine_uk.variables.gov.gov_balance",
    "policyengine_uk.utils.scenario",
    "policyengine_uk.parameters.gov.economic_assumptions.create_september_cpi_uprating",
)


# ── The in-memory relaxation (parent and every job process) ──────────────────


def patch():
    """Admit 6.20.2 / 2.179.1 and its Microcosm file for this script's runs only; returns what was relaxed."""
    from triple_lock import datasets, model_horizon

    versions = {p: importlib.metadata.version(p) for p in EXPECTED_VERSIONS}
    if versions != EXPECTED_VERSIONS:
        raise RuntimeError(f"b1_full_runs needs {EXPECTED_VERSIONS}, found {versions}")
    datasets.DATASETS[DATASET] = {
        "logical_name": "microcosm_uk_2024_25",
        "repo_id": DATA_REPO, "repo_type": "dataset", "path": DATA_PATH, "revision": DATA_REVISION,
        "sha256": DATA_SHA256, "data_package": "microcosm-data", "data_version": "0.1.0",
        "built_with": "policyengine-uk 2.177.7 (policyengine-core 3.34.10)", "build_id": DATA_BUILD,
        "certified": ["policyengine.py 6.20.2 (bundle uk-6.20.2) certifies this file for policyengine-uk 2.177.7 / "
                      "core 3.34.10 (compatibility_basis built_with_model_package); these runs use 2.179.1"],
        "bundle_certification": None,
        # calibration_diagnostics.json of the release: dataset_year 2024, all 1,534 targets dated 2025.
        "ageing_anchor": {"year": 2025, "calibration_year": 2025,
                          "source": f"{DATA_BUILD}: calibration_diagnostics.json dataset_year 2024, all 1,534 "
                                    "targets period 2025"},
    }
    model_horizon.check_upstream = check_upstream_2179
    from triple_lock import engine

    if not getattr(engine.path_following, "b1_adapted", False):
        engine.path_following = _path_following_2179(engine.path_following)
    return {"dataset_entry": DATASET, "check_upstream": "check_upstream_2179",
            "path_following": "model_new_state_pension expects the 5p-rounded projection (2.179.1 "
                              "create_rate_projection), checked exactly", "versions": versions}


def _path_following_2179(original):
    """engine.path_following with one expectation adapted to 2.179.1.

    policyengine-uk 2.179.1 (create_rate_projection.project_state_pension_rates, a generation step absent from
    2.151.0) projects the model's own full new State Pension each April from the previous year's rate times its
    triple-lock index, rounded to the nearest gov.dwp.state_pension.weekly_rate_rounding (5p). The engine's check
    expected the unrounded compound (within 2e-4), which 5p rounding can exceed over 13 Aprils. Here the expectation is
    the same rule with the model's 5p rounding (the model's own round_weekly_rate), and the check is made exact
    (1e-9 relative) rather than loosened. Every other check in path_following runs unchanged, and the policy runs'
    flat rates (set explicitly by the engine, checked at 1e-9) are untouched.
    """
    import types
    from decimal import Decimal

    from policyengine_uk.parameters.gov.dwp.state_pension.create_rate_projection import uprate_weekly_rate
    from policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock import uprating_instant

    from triple_lock import engine, rules
    from triple_lock.config import HORIZON

    def adapted(sim, calendar, statutory):
        p = sim.tax_benefit_system.parameters
        rounding = p.gov.dwp.state_pension.weekly_rate_rounding

        def rounded_level_path(base, rates, years):
            out, value = {}, float(base)
            for y in years:
                value = uprate_weekly_rate(value, Decimal(repr(1.0 + float(rates[y]))),
                                           rounding(uprating_instant(int(y))))
                out[y] = value
            return out

        proxy = types.SimpleNamespace(**{k: getattr(rules, k) for k in dir(rules) if not k.startswith("__")})
        proxy.level_path = rounded_level_path
        engine.rules = proxy
        try:
            out = original(sim, calendar, statutory)
        finally:
            engine.rules = rules
        err = out["model_new_state_pension"]["max_rel_error"]
        out["model_new_state_pension"]["follows"] = ("previous April's rate x (1 + the model's triple lock), to the "
                                                     "nearest 5p (policyengine-uk 2.179.1 create_rate_projection)")
        if not err <= 1e-9:
            raise engine.PathNotFollowed(f"model_new_state_pension (5p-rounded projection): off by {err:.2e}")
        return out

    adapted.b1_adapted = True
    return adapted


def check_upstream_2179():
    """model_horizon.check_upstream for policyengine-uk 2.179.1: the 2.153.4 guard set, with the reviewed changes
    admitted and everything else (including MUST_BE_UNCHANGED) byte-identical."""
    from triple_lock import model_horizon as M

    version = importlib.metadata.version("policyengine-uk")
    if version != "2.179.1":
        raise M.UpstreamChanged(f"check_upstream_2179 admits only policyengine-uk 2.179.1, not {version}")
    root = Path(importlib.import_module("policyengine_uk").__file__).parent
    changed = []
    for module, expected in M.D1727_UPSTREAM.items():
        path = Path(importlib.import_module(module).__file__)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(module)
    for relative, expected in M.D1727_UPSTREAM_PARAMETERS.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            changed.append(relative)
    bad = sorted(set(changed) & set(MUST_BE_UNCHANGED))
    unreviewed = sorted(set(changed) - set(REVIEWED_CHANGED_2179))
    if bad or unreviewed:
        raise M.UpstreamChanged(f"policyengine-uk 2.179.1 changed {bad + unreviewed} beyond the reviewed list")
    ppu = importlib.import_module("policyengine_uk.parameters.gov.contrib.create_private_pension_uprating")
    if list(ppu.YEARS) not in (list(range(2020, 2035)), list(range(2020, M.END_YEAR + 1))):
        raise M.UpstreamChanged("private pension uprating YEARS is not the reviewed 2020-2034 list")
    return sorted(changed)


def patch_hash():
    """Part of every job's cache key: what the relaxation and the job process do."""
    src = "".join(inspect.getsource(f) for f in (patch, _path_following_2179, check_upstream_2179, child)) + repr(
        (REVIEWED_CHANGED_2179, MUST_BE_UNCHANGED, DATASET, DATA_SHA256))
    return hashlib.sha256(src.encode()).hexdigest()


def child(inp, out):
    """The job process: patch, extend the horizon (model_horizon.install, with its upstream guard), run the path."""
    started = time.time()
    relaxed = patch()
    from triple_lock import engine, model_horizon

    extension = model_horizon.install()
    changed = check_upstream_2179()
    arg = engine._keys_to_int(json.loads(Path(inp).read_text())["arg"])
    result = engine.run_path(arg)
    result["b1_full_runs"] = {
        "seconds": time.time() - started,
        "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30,  # bytes on macOS
        "horizon_extension": extension, "relaxed": relaxed, "upstream_changed_vs_2_153_4": changed,
    }
    Path(out).write_text(json.dumps(result, default=float, allow_nan=False))


# ── Jobs: own scheduler (one failure never cancels the queue), admission by measured memory ──────────


def _canonical(obj):
    return json.dumps(json.loads(json.dumps(obj, default=float)), sort_keys=True, separators=(",", ":"))


def job_key(arg):
    from triple_lock.engine import engine_semantics, package_versions

    return hashlib.sha256(_canonical({"arg": arg, "engine": engine_semantics(), "packages": package_versions(),
                                      "patch": patch_hash()}).encode()).hexdigest()


def cache_file(name, key):
    return CACHE / "runs" / f"{name}-{key[:24]}.json"


def load_cached(name, arg):
    path = cache_file(name, job_key(arg))
    if path.is_file():
        return json.loads(path.read_text())
    return None


class Runner:
    """Run named path jobs on ``workers`` threads, each launching a job process; admit a launch only while the host
    keeps ``budget_gib`` (the measured peak) plus SAFETY_GIB free beyond what running jobs may still allocate."""

    def __init__(self, workers, budget_gib, log):
        self.workers, self.budget_gib, self.log = workers, budget_gib, log
        self.lock = threading.Lock()
        self.running = {}  # pid -> started
        self.admissions = []

    def outstanding(self):
        import psutil

        total = 0.0
        for pid in list(self.running):
            try:
                rss = psutil.Process(pid).memory_info().rss / 2**30
            except Exception:
                rss = 0.0
            total += max(0.0, self.budget_gib - rss)
        return total

    def admit(self, name):
        from triple_lock import host

        while True:
            with self.lock:
                reading = host.measure()
                need = self.budget_gib + SAFETY_GIB + self.outstanding()
                applied = host.assess(reading["available_gib"], reading["load_1m"], reading["cpu_count"], need)
                record = {"job": name, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          **reading, **applied}
                if applied["admitted"]:
                    self.admissions.append(record)
                    return record
            self.log(f"  waiting to admit {name}: {host.describe(reading, applied)}")
            time.sleep(60)

    def launch(self, name, arg):
        import psutil

        WORKDIR.mkdir(parents=True, exist_ok=True)
        WORKDIR.chmod(0o700)
        tag = hashlib.sha256(f"{name}{time.time()}{threading.get_ident()}".encode()).hexdigest()[:12]
        inp, out = WORKDIR / f"in-{tag}.json", WORKDIR / f"out-{tag}.json"
        inp.write_text(json.dumps({"arg": arg}, default=float))
        err_path = WORKDIR / f"err-{tag}.txt"
        admission = self.admit(name)
        started = time.time()
        with open(err_path, "w") as err:
            os.chmod(err_path, 0o600)
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--job", str(inp), str(out)],
                                    cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                                    stdout=subprocess.DEVNULL, stderr=err, start_new_session=True)
            with self.lock:
                self.running[proc.pid] = started
            peak = 0.0
            while proc.poll() is None:
                try:
                    peak = max(peak, psutil.Process(proc.pid).memory_info().rss / 2**30)
                except Exception:
                    pass
                time.sleep(5)
            with self.lock:
                self.running.pop(proc.pid, None)
        seconds = time.time() - started
        try:
            if proc.returncode != 0:
                text = err_path.read_text()
                # The last exception line only (aggregate messages); the full trace stays owner-only on disk.
                lines = [l for l in text.strip().splitlines() if l.strip()]
                reason = lines[-1][:600] if lines else f"exit {proc.returncode}"
                kept = CACHE / "failed" / f"{name}-{tag}.stderr"
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_text(text)
                os.chmod(kept, 0o600)
                return None, {"reason": reason, "exit": proc.returncode, "seconds": seconds,
                              "polled_peak_rss_gib": peak, "stderr_kept": str(kept.relative_to(ROOT))}
            result = json.loads(out.read_text())
            result.setdefault("b1_full_runs", {})["polled_peak_rss_gib"] = peak
            result["b1_full_runs"]["wall_seconds"] = seconds
            result["b1_full_runs"]["admission"] = admission
            return result, None
        finally:
            for p in (inp, out, err_path):
                p.unlink(missing_ok=True)

    def run(self, jobs):
        """jobs: [(name, arg)]. Returns {name: {"result"|None, "failures": [...]}}; caches each success at once."""
        import queue

        q = queue.Queue()
        for job in jobs:
            q.put(job)
        outcomes = {}

        control = CACHE / "workers"  # an integer: how many worker threads may take new jobs (live control)

        def allowed():
            try:
                return int(control.read_text().strip())
            except (OSError, ValueError):
                return self.workers

        def worker(index):
            while True:
                while index >= allowed():
                    time.sleep(30)
                try:
                    name, arg = q.get_nowait()
                except queue.Empty:
                    return
                key = job_key(arg)
                path = cache_file(name, key)
                if path.is_file():
                    outcomes[name] = {"result": json.loads(path.read_text())["result"], "failures": [], "cached": True}
                    continue
                failures = []
                for attempt in range(1, ATTEMPTS + 1):
                    self.log(f"  start {name} (attempt {attempt})")
                    result, failure = self.launch(name, arg)
                    if result is not None:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = path.with_suffix(".tmp")
                        tmp.write_text(json.dumps({"key": key, "name": name, "arg": arg, "failures": failures,
                                                   "result": result}, default=float, allow_nan=False))
                        os.chmod(tmp, 0o600)
                        tmp.replace(path)
                        info = result["b1_full_runs"]
                        self.log(f"  done {name} in {info['wall_seconds']:.0f}s, peak {info['peak_rss_gib']:.1f} GiB; "
                                 f"2039 net {result['saving_bn']['2039']['net']:.3f}bn")
                        outcomes[name] = {"result": result, "failures": failures, "cached": False}
                        break
                    failures.append({"attempt": attempt, **failure})
                    self.log(f"  FAILED {name} (attempt {attempt}): {failure['reason']}")
                else:
                    outcomes[name] = {"result": None, "failures": failures, "cached": False}
                    record = CACHE / "failures" / f"{name}-{key[:24]}.json"
                    record.parent.mkdir(parents=True, exist_ok=True)
                    record.write_text(json.dumps({"name": name, "key": key, "failures": failures}))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(self.workers)]
        for i, t in enumerate(threads):
            t.start()
            time.sleep(90 if i < len(threads) - 1 else 0)  # stagger loads so peaks do not coincide
        for t in threads:
            t.join()
        return outcomes


def logger():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "runs.log"

    def log(msg):
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(path, "a") as f:
            f.write(line + "\n")
    return log


# ── Specs ────────────────────────────────────────────────────────────────


def stored_results():
    return json.loads((ROOT / "data" / "results.json").read_text())


def anchor_specs(results=None):
    """The stored OBR central and long-term ('wedge') specs, exactly as the stored runs received them, on the new
    dataset."""
    from triple_lock import trajectories
    from triple_lock.engine import _keys_to_int

    results = stored_results() if results is None else results
    env = _keys_to_int(results["scenario_envelope"])
    central = {k: v for k, v in trajectories.central_spec(env["central"]["path"]).items()
               if k not in ("id", "label", "source")}
    wedge = {k: v for k, v in env["obr_wedge"]["path"].items() if k not in ("id", "label", "source")}
    return {"anchor_central": {**central, "dataset": DATASET}, "anchor_obr_wedge": {**wedge, "dataset": DATASET}}


def b1_paths():
    """The headline's 399,440 statutory paths (n, STATUTORY_YEARS, 2) and their rule arithmetic."""
    from triple_lock import b1_bayes as B

    _, theta, _ = B.load_posterior(B.POSTERIOR)
    inputs = B.forward_inputs(theta)
    ctx = B.cash_context()
    return inputs, B.arithmetic(inputs, ctx), ctx


def path_spec(inputs, i, central_calendar, centre, september_history):
    """Engine spec for B1 path i: statutory inputs as drawn; calendar growth = central calendar growth + the path's
    statutory deviation from the centre in determination year t (2039: the 2038 deviation)."""
    from triple_lock.config import CALENDAR_YEARS, CENTRAL_RATE_DECIMALS, STATUTORY_YEARS

    dev = inputs[i] - centre
    cal = {}
    for k, s in enumerate(("cpi", "earnings")):
        cal[s] = {}
        for y in CALENDAR_YEARS:
            t = y if y in STATUTORY_YEARS else STATUTORY_YEARS[-1]
            cal[s][y] = float(central_calendar[s][y] + dev[STATUTORY_YEARS.index(t), k])
    return {"rate_decimals": CENTRAL_RATE_DECIMALS, "cpi": cal["cpi"], "earnings": cal["earnings"],
            "statutory_cpi": {y: float(inputs[i, j, 0]) for j, y in enumerate(STATUTORY_YEARS)},
            "statutory_earnings": {y: float(inputs[i, j, 1]) for j, y in enumerate(STATUTORY_YEARS)},
            "september_cpi_history": september_history, "dataset": DATASET}


def _int_keys(d):
    return {int(k): float(v) for k, v in d.items()}


# ── Modes ────────────────────────────────────────────────────────────────


def environment_record():
    import platform

    pk = ("policyengine", "policyengine-uk", "policyengine-core", "microdf-python", "numpy", "pandas", "scipy",
          "h5py", "tables", "huggingface-hub", "psutil")
    out = {"python": platform.python_version(), "platform": platform.platform(),
           "packages": {p: importlib.metadata.version(p) for p in pk}}
    manifest = Path(importlib.metadata.distribution("policyengine").locate_file("policyengine/data/bundle/manifest.json"))
    raw = manifest.read_bytes()
    m = json.loads(raw)
    uk = m["data_releases"]["uk"]
    out["bundle"] = {"manifest_sha256": hashlib.sha256(raw).hexdigest(), "bundle_id": uk["bundle_id"],
                     "certified_model": uk["model_package"]["version"],
                     "certified_core": m["packages"]["policyengine-core"]["version"],
                     "certified_data_artifact": uk["certified_data_artifact"],
                     "certification": uk["certification"]}
    out["dataset"] = {"name": DATASET, "repo": DATA_REPO, "revision": DATA_REVISION, "path": DATA_PATH,
                      "sha256": DATA_SHA256, "matches_bundle_artifact": uk["certified_data_artifact"]["sha256"] == DATA_SHA256}
    out["certified_pair"] = False
    out["certified_pair_note"] = ("policyengine.py 6.20.2 pins and certifies policyengine-uk 2.177.7 with this file; "
                                  "the runs use policyengine-uk 2.179.1 (the author's instruction and the registered "
                                  "specification), so the model/data pair is not a certified one")
    return out


def load_out():
    return json.loads(OUT_JSON.read_text()) if OUT_JSON.is_file() else {}


def save_out(out):
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, default=float, allow_nan=False) + "\n")
    tmp.replace(OUT_JSON)


def summarise_run(result):
    """What full_runs.json keeps of one run (the full output stays in the cache)."""
    y = str(FINAL)
    s = result["saving_bn"][y]
    info = result.get("b1_full_runs", {})
    return {
        "gross_bn": s["gross"], "net_bn": s["net"], "household_income_change_bn": s["household_income_change"],
        "components_bn": s.get("components"), "gb": {"gross_bn": s["gb"]["gross"], "net_bn": s["gb"]["net"]},
        "households_affected": result["households_affected"][y],
        "poverty_pct": {p: result["poverty_pct"][p][y] for p in result["poverty_pct"]},
        "rates": result["rates"], "weekly_new_state_pension_2039": {p: result["weekly"][p]["new_state_pension"][y]
                                                                     for p in result["weekly"]},
        "flat_rate_spending_triple_lock_bn": result["totals_bn"]["triple_lock"][y]["state_pension_flat_rate"],
        "path_following_max_errors": {k: v.get("max_abs_error", v.get("max_rel_error"))
                                      for k, v in result["path_following"].items() if isinstance(v, dict)},
        "checks": result["checks"],
        "seconds": info.get("wall_seconds", info.get("seconds")), "peak_rss_gib": info.get("peak_rss_gib"),
        "polled_peak_rss_gib": info.get("polled_peak_rss_gib"),
    }


def mode_anchors(args):
    log = logger()
    patch()
    from triple_lock.pipeline import housing_benefit_passport_preflight

    out = load_out()
    out["environment"] = environment_record()
    out["preflight"] = {"housing_benefit_passport": housing_benefit_passport_preflight(log=log)}
    specs = anchor_specs()
    names = [n for n in args.only] if args.only else list(specs)
    runner = Runner(args.workers, args.budget_gib, log)
    outcomes = runner.run([(n, specs[n]) for n in names])
    stored = stored_results()["scenario_envelope"]
    anchors = out.setdefault("anchors", {})
    for n in names:
        o = outcomes[n]
        key = "central" if n == "anchor_central" else "obr_wedge"
        run = stored[key]["run"]
        st = {"gross_bn": run["saving_bn"]["2039"]["gross"], "net_bn": run["saving_bn"]["2039"]["net"],
              "households_affected": run["households_affected"]["2039"],
              "flat_rate_spending_triple_lock_bn": run["totals_bn"]["triple_lock"]["2039"]["state_pension_flat_rate"],
              "components_bn": run["saving_bn"]["2039"].get("components")}
        anchors[key] = {"spec_source": f"data/results.json scenario_envelope.{key}.path",
                        "stored_6_11_1": st, "failures": o["failures"],
                        "rerun_6_20_2": summarise_run(o["result"]) if o["result"] else None}
    out["anchors_admissions"] = runner.admissions
    save_out(out)
    log(json.dumps({k: {"rerun": (v["rerun_6_20_2"] or {}).get("net_bn"), "stored": v["stored_6_11_1"]["net_bn"]}
                    for k, v in anchors.items()}))


def stratify_b1(gross, same):
    """Stratum per path: 0 where both rules pay the same every April to 2039; positive-saving paths by their 2039
    rule-arithmetic gross at PROBABILITY_BOUNDS of those paths. Returns (strata, info)."""
    n = len(gross)
    strata = np.zeros(n, dtype=int)
    pos = ~same & (gross > 0)
    other = ~same & ~(gross > 0)
    idx = np.where(pos)[0]
    order = idx[np.argsort(gross[idx], kind="stable")]
    cw = (np.arange(len(order)) + 1) / len(order)
    k = np.searchsorted(np.array(PROBABILITY_BOUNDS[1:]), cw - 1e-12, side="left") + 1
    strata[order] = k
    strata[other] = 1  # not identical but no positive 2039 saving: the lowest sampled stratum (recorded)
    info = {"n_paths": int(n), "identical": int(same.sum()), "positive": int(pos.sum()),
            "not_identical_non_positive_2039": int(other.sum()),
            "not_identical_non_positive_rule": "assigned to stratum 1 (the spec's strata cover positive-saving paths)"}
    return strata, info


def mode_design(args):
    log = logger()
    from triple_lock import expected_value as EV
    from triple_lock import v1_bands as V
    from triple_lock.central import september_cpi_history
    from triple_lock.config import HORIZON

    inputs, ar, ctx = b1_paths()
    j = HORIZON.index(FINAL)
    gross, same = ar["gross_bn"][:, j], ar["same"][:, j]
    forecast = json.loads((ROOT / "data" / "b1" / "forecast.json").read_text())
    p50 = forecast["by_year"][str(FINAL)]["gross_bn"]["p50"]
    if len(inputs) != forecast["n_paths"] or abs(float(np.percentile(gross, 50)) - p50) > 1e-9:
        raise RuntimeError("regenerated paths do not reproduce forecast.json's 2039 gross median")
    strata, info = stratify_b1(gross, same)
    w = np.ones(len(gross))
    alloc = EV.allocate(w, gross, strata, n_paths=args.n, min_per=MIN_PER_STRATUM)
    sample = EV.draw_sample(w, strata, alloc, seed=SAMPLE_SEED)
    W = {int(k): float((strata == k).mean()) for k in range(0, len(PROBABILITY_BOUNDS))}
    bounds = {int(k): {"probability": [PROBABILITY_BOUNDS[k - 1], PROBABILITY_BOUNDS[k]],
                       "gross_bn": [float(gross[strata == k].min()), float(gross[strata == k].max())],
                       "paths": int((strata == k).sum()), "W": W[k],
                       "rule_gross_mean_bn": float(gross[strata == k].mean()),
                       "rule_gross_sd_bn": float(gross[strata == k].std())}
              for k in range(1, len(PROBABILITY_BOUNDS))}
    # Calendar mapping check: a zero-deviation path is the central spec.
    results = stored_results()
    central_calendar = {s: _int_keys(results["scenario_envelope"]["central"]["path"]["calendar"][s])
                        for s in ("cpi", "earnings")}
    centre = V.centre()
    hist = september_cpi_history()
    zero = path_spec(centre[None], 0, central_calendar, centre, hist)
    ref = anchor_specs(results)["anchor_central"]
    mismatch = max(abs(zero[s][y] - float(ref[s][y] if y in ref[s] else ref[s][str(y)])) for s in
                   ("cpi", "earnings", "statutory_cpi", "statutory_earnings") for y in zero[s])
    if mismatch > 1e-12:
        raise RuntimeError(f"a zero-deviation path is not the central spec (off by {mismatch:.2e})")
    out = load_out()
    out["design"] = {
        "specification": "docs/METHOD.md, 'Specification: full runs on a weighted sample of the Bayesian paths, "
                         "18 November 2026'",
        "paths": {"posterior": "data/b1/posterior.npy",
                  "posterior_sha256": hashlib.sha256((ROOT / "data/b1/posterior.npy").read_bytes()).hexdigest(),
                  "predictive_seed": 20261113, **info,
                  "reproduces_forecast_gross_median_2039_bn": p50},
        "calendar_mapping": "calendar growth in year t = central path's calendar growth + the path's statutory "
                            "deviation from the centre in determination year t (September CPI, May-July earnings); "
                            "2039 takes the 2038 deviation. A zero-deviation path reproduces the central spec "
                            f"(max difference {mismatch:.1e}).",
        "stratification_variable": "2039-40 rule-arithmetic gross saving, £bn (b1_bayes.arithmetic, stored central "
                                   "run's base)",
        "probability_bounds": list(PROBABILITY_BOUNDS),
        "W": W, "strata": bounds,
        "allocation": {"method": "expected_value.allocate (Neyman on rule-arithmetic gross), min 4 per stratum",
                       "n_total": int(args.n), "by_stratum": alloc},
        "sample_seed": SAMPLE_SEED,
        "sample": {int(k): v for k, v in sample.items()},
        "unique_paths": int(len({i for v in sample.values() for i in v})),
        "n_choice": args.n_note,
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_out(out)
    log(f"design: N={args.n}, alloc {alloc}, unique {out['design']['unique_paths']}")


def sample_jobs(out):
    """[(name, spec)] for the design's unique sampled paths, extremes first, then round-robin across strata."""
    from triple_lock import v1_bands as V
    from triple_lock.central import september_cpi_history

    d = out["design"]
    inputs, ar, ctx = b1_paths()
    results = stored_results()
    central_calendar = {s: _int_keys(results["scenario_envelope"]["central"]["path"]["calendar"][s])
                        for s in ("cpi", "earnings")}
    centre = V.centre()
    hist = september_cpi_history()
    from triple_lock.config import HORIZON

    gross = ar["gross_bn"][:, HORIZON.index(FINAL)]
    per = {int(k): list(dict.fromkeys(v)) for k, v in d["sample"].items()}
    first = [max(per[max(per)], key=lambda i: gross[i]), min(per[min(per)], key=lambda i: gross[i])]
    order, seen = [], set()
    for i in first:
        order.append(i)
        seen.add(i)
    depth = max(len(v) for v in per.values())
    for r in range(depth):
        for k in sorted(per):
            if r < len(per[k]) and per[k][r] not in seen:
                order.append(per[k][r])
                seen.add(per[k][r])
    return [(f"path_{i}", path_spec(inputs, i, central_calendar, centre, hist)) for i in order], ar


def mode_run(args):
    log = logger()
    patch()
    out = load_out()
    jobs, ar = sample_jobs(out)
    if args.limit:
        jobs = jobs[: args.limit]
    if args.with_wedge:  # the long-term anchor shares the queue (same cache key as ``anchors`` mode)
        a = anchor_specs()
        jobs = [jobs[0], ("anchor_obr_wedge", a["anchor_obr_wedge"]), jobs[1], ("anchor_central", a["anchor_central"]),
                *jobs[2:]]
    log(f"run: {len(jobs)} unique paths on {args.workers} workers, budget {args.budget_gib} GiB each")
    runner = Runner(args.workers, args.budget_gib, log)
    outcomes = runner.run(jobs)
    out = load_out()
    out.setdefault("run_admissions", []).extend(runner.admissions)
    save_out(out)
    log(f"run finished: {sum(o['result'] is not None for o in outcomes.values())} ok, "
        f"{sum(o['result'] is None for o in outcomes.values())} failed")


# ── Estimation ───────────────────────────────────────────────────────────


def weighted_quantile(values, weights, q=0.5):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    o = np.argsort(values, kind="stable")
    v, w = values[o], weights[o]
    c = np.cumsum(w) / w.sum()
    i = int(np.searchsorted(c, q - 1e-12, side="left"))
    return float(v[min(i, len(v) - 1)])


def mixture(by_stratum, W, zero_mass):
    """Values and weights of the stratum-weighted distribution: each run of stratum k weighs W_k / n_k; stratum 0 a
    point mass at zero."""
    vals, wts = ([0.0], [zero_mass]) if zero_mass > 0 else ([], [])
    for k, v in by_stratum.items():
        v = np.asarray(v, float)
        vals.extend(v.tolist())
        wts.extend([W[k] / len(v)] * len(v))
    return np.array(vals), np.array(wts)


def boot(by_stratum, stat, rng, n=N_BOOT):
    draws = []
    for _ in range(n):
        res = {k: np.asarray(v, float)[rng.integers(0, len(v), len(v))] for k, v in by_stratum.items()}
        draws.append(stat(res))
    draws = np.array(draws)
    return {"se": float(draws.std(ddof=1)), "interval_95": [float(np.percentile(draws, 2.5)),
                                                          float(np.percentile(draws, 97.5))],
            "bootstrap_mean": float(draws.mean())}


def read_b1_rho():
    """paper/paperdata.py's B1_RHO without importing the paper module: B1 = forecast.json, B1_RHO = B1['net_ratio']."""
    text = (ROOT / "paper" / "paperdata.py").read_text()
    m = re.search(r"^B1_RHO\s*=\s*(.+)$", text, re.M)
    m2 = re.search(r"^B1\s*=\s*(.+)$", text, re.M)
    forecast = json.loads((ROOT / "data" / "b1" / "forecast.json").read_text())
    return {"expression": m.group(1).strip() if m else None, "B1_expression": m2.group(1).strip() if m2 else None,
            "value": float(forecast["net_ratio"]["rho"] if isinstance(forecast["net_ratio"], dict)
                           else forecast["net_ratio"])}


def mode_estimate(args):
    log = logger()
    patch()
    from triple_lock import b1_bayes as B
    from triple_lock import expected_value as EV
    from triple_lock import v1_bands as V
    from triple_lock.config import HORIZON

    out = load_out()
    d = out["design"]
    W = {int(k): v for k, v in d["W"].items()}
    jobs, ar = sample_jobs(out)
    by_name = {n: a for n, a in jobs}
    runs, failures = {}, {}
    for name, arg in jobs:
        path = cache_file(name, job_key(arg))
        if path.is_file():
            rec = json.loads(path.read_text())
            runs[name] = summarise_run(rec["result"])
            if rec.get("failures"):
                runs[name]["earlier_failed_attempts"] = rec["failures"]
        else:
            fpath = CACHE / "failures" / f"{name}-{job_key(arg)[:24]}.json"
            if fpath.is_file():
                failures[name] = json.loads(fpath.read_text())["failures"]
    jf = HORIZON.index(FINAL)
    gross_ra = ar["gross_bn"][:, jf]
    # Engine rates must be the rule arithmetic's for that path.
    inputs_all, _, _ = b1_paths()
    rate_err = 0.0
    for name, r in runs.items():
        i = int(name.split("_")[1])
        ra_i = V.rule_arithmetic(inputs_all[i:i + 1, :, 0], inputs_all[i:i + 1, :, 1])
        for p, key in (("triple_lock", "tl"), ("burnham_2030", "bp")):
            eng = np.array([r["rates"][p][str(y)] for y in HORIZON])
            rate_err = max(rate_err, float(np.abs(eng - ra_i[key][0]).max()))
    # Anchors, refreshed from the cache (the wedge and central reruns may have run in the sample queue).
    stored = stored_results()["scenario_envelope"]
    for key, name in (("central", "anchor_central"), ("obr_wedge", "anchor_obr_wedge")):
        rec = load_cached(name, anchor_specs()[name])
        run = stored[key]["run"]
        out.setdefault("anchors", {})[key] = {
            "spec_source": f"data/results.json scenario_envelope.{key}.path (same spec, the 6.20.2 dataset)",
            "stored_6_11_1": {"gross_bn": run["saving_bn"]["2039"]["gross"], "net_bn": run["saving_bn"]["2039"]["net"],
                              "households_affected": run["households_affected"]["2039"],
                              "flat_rate_spending_triple_lock_bn":
                                  run["totals_bn"]["triple_lock"]["2039"]["state_pension_flat_rate"],
                              "components_bn": run["saving_bn"]["2039"].get("components")},
            "rerun_6_20_2": summarise_run(rec["result"]) if rec else None,
            "earlier_failed_attempts": rec.get("failures") if rec else None}
    # Per-stratum values (draws with replacement: a path drawn twice counts twice).
    sample = {int(k): v for k, v in d["sample"].items()}
    strata_of = {}
    for k, idx in sample.items():
        for i in idx:
            strata_of.setdefault(i, k)

    def values(field, include_failed=None):
        by = {}
        missing = {}
        for k, idx in sample.items():
            vals = []
            for i in idx:
                r = runs.get(f"path_{i}")
                if r is None:
                    missing.setdefault(k, 0)
                    missing[k] += 1
                    continue
                vals.append(field(r))
            if include_failed in ("min", "max") and missing.get(k) and vals:
                fill = min(vals) if include_failed == "min" else max(vals)
                vals = vals + [fill] * missing[k]
            if vals:
                by[k] = vals
        return by, missing

    net = lambda r: r["net_bn"]
    gross = lambda r: r["gross_bn"]
    loss = lambda r: r["households_affected"]["mean_loss_gbp"]
    rng = np.random.default_rng(BOOT_SEED)
    W0 = W[0]

    def median_net(by):
        v, w = mixture(by, W, W0)
        return weighted_quantile(v, w)

    def loss_median(by):  # over positive-saving paths only (stratum 0: nobody loses; mean_loss_gbp is 0 there)
        v, w = mixture(by, W, 0.0)
        return weighted_quantile(v, w)

    # The median-gross stratum: the stratum holding the rule-arithmetic 2039 gross median over all paths.
    med_gross_all = float(np.percentile(gross_ra, 50))
    strata_arr = np.zeros(len(gross_ra), dtype=int)
    for k, b in d["strata"].items():
        pass
    from_bounds = [(int(k), b["gross_bn"]) for k, b in d["strata"].items()]
    k_med = next(k for k, (lo, hi) in sorted(from_bounds) if lo <= med_gross_all <= hi)

    def stratum_mean(by, k):
        return float(np.mean(by[k]))

    est = {}
    for label, mode in (("as_run", None), ("failed_at_stratum_min", "min"), ("failed_at_stratum_max", "max")):
        if label != "as_run" and not failures:
            continue
        by_net, missing = values(net, mode)
        by_loss, _ = values(loss, mode)
        by_gross, _ = values(gross, mode)
        e = {"runs_by_stratum": {k: len(v) for k, v in by_net.items()}, "missing_by_stratum": missing}
        e["median_net_bn"] = {"estimate": median_net(by_net), **boot(by_net, median_net, rng)}
        e["mean_loss_gbp_weighted_median_over_paths"] = {"estimate": loss_median(by_loss),
                                                         **boot(by_loss, loss_median, rng)}
        e["mean_loss_gbp_in_median_gross_stratum"] = {
            "stratum": k_med, "estimate": stratum_mean(by_loss, k_med),
            **boot({k_med: by_loss[k_med]}, lambda b: float(np.mean(b[k_med])), rng)}
        e["median_gross_bn_full_runs"] = {"estimate": median_net(by_gross), **boot(by_gross, median_net, rng)}
        mean = EV.stratified_estimate({k: v for k, v in by_net.items() if len(v) >= 2}, W,
                                      n_draws=d["paths"]["n_paths"])
        e["weighted_mean_net_bn_error_budget_only"] = mean
        est[label] = e
    # Rule-arithmetic gross median: stored 6.11.1 central base and the 6.20.2 central rerun's base.
    anchors = out.get("anchors", {})
    ra = {"median_gross_bn_rule_arithmetic_stored_base": med_gross_all}
    if anchors.get("central", {}).get("rerun_6_20_2"):
        rec = load_cached("anchor_central", anchor_specs()["anchor_central"])
        base_new = np.array([rec["result"]["totals_bn"]["triple_lock"][str(y)]["state_pension_flat_rate"]
                             for y in HORIZON])
        ctx = B.cash_context()
        inputs, _, _ = b1_paths()
        a2 = B.arithmetic(inputs, {**ctx, "base": base_new})
        ra["median_gross_bn_rule_arithmetic_6_20_2_base"] = float(np.percentile(a2["gross_bn"][:, jf], 50))
        ra["base_2039_bn"] = {"stored_6_11_1": float(ctx["base"][jf]), "rerun_6_20_2": float(base_new[jf])}
        gross_ra_new = a2["gross_bn"][:, jf]
    else:
        gross_ra_new = None
    # Per-run full-run gross against the rule arithmetic, and net/gross by stratum.
    rho = read_b1_rho()
    by_stratum = {}
    for k, idx in sample.items():
        rs = [(i, runs[f"path_{i}"]) for i in dict.fromkeys(idx) if f"path_{i}" in runs]
        ratios = [r["net_bn"] / r["gross_bn"] for _, r in rs if r["gross_bn"] > 1e-6]
        gr = [r["gross_bn"] / gross_ra[i] for i, r in rs if gross_ra[i] > 1e-6]
        by_stratum[k] = {"unique_runs": len(rs), "net_to_gross": {
            "mean": float(np.mean(ratios)) if ratios else None, "min": float(np.min(ratios)) if ratios else None,
            "max": float(np.max(ratios)) if ratios else None},
            "full_gross_over_rule_gross": {"mean": float(np.mean(gr)) if gr else None,
                                           "min": float(np.min(gr)) if gr else None,
                                           "max": float(np.max(gr)) if gr else None},
            "full_gross_over_rule_gross_6_20_2_base": (lambda g: {"mean": float(np.mean(g)), "min": float(np.min(g)),
                                                                   "max": float(np.max(g))} if g else None)(
                [r["gross_bn"] / gross_ra_new[i] for i, r in rs if gross_ra_new is not None and gross_ra_new[i] > 1e-6]),
            "mean_loss_gbp": {"mean": float(np.mean([r["households_affected"]["mean_loss_gbp"] for _, r in rs]))
                              if rs else None},
            "net_bn": {"mean": float(np.mean([r["net_bn"] for _, r in rs])) if rs else None}}
    out["runs"] = runs
    out["failures"] = failures
    out["estimates"] = {
        "year": "2039-40", "bootstrap": {"resamples": N_BOOT, "seed": BOOT_SEED, "within_strata": True},
        "stratum_0": "rules identical every April to 2039: net saving exactly zero (point mass W0); no household "
                     "loses, so mean_loss_gbp is excluded from its median over paths (taken over positive-saving "
                     "paths, weights W1..W10 renormalised)",
        "median_gross_stratum": k_med, "median_gross_rule_arithmetic_all_paths_bn": med_gross_all,
        **est, "rule_arithmetic": ra, "by_stratum": by_stratum, "paper_fixed_ratio": rho,
        "max_engine_vs_rule_arithmetic_rate_error": rate_err,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_out(out)
    log(json.dumps({k: est["as_run"][k] for k in ("median_net_bn", "mean_loss_gbp_weighted_median_over_paths",
                                                   "mean_loss_gbp_in_median_gross_stratum")}, indent=1))


ADAPTATIONS = [
    {"what": "Version and dataset pins (datasets.py, model_horizon.check_upstream)",
     "how": "relaxed in memory by this script only: a DATASETS entry for the fcfac709 file (SHA-256 checked before "
            "every use by datasets.materialize) and check_upstream_2179, which admits exactly the 21 reviewed changed "
            "files of the 2.153.4 guard set and still fails if any other guarded file, or any of the builders the "
            "horizon extension and Scenario entry rely on (lagged series, statutory inputs, triple lock, private "
            "pension uprating, gov_balance, scenario, September-CPI uprating), differs"},
    {"what": "path_following: model_new_state_pension",
     "how": "2.179.1 projects the model's own full new State Pension each April from the previous year's rate to "
            "the nearest 5p (create_rate_projection, not in 2.151.0). The unrounded expectation (tolerance 2e-4) "
            "failed on the first B1 path (3.9e-4). Expectation replaced by the same 5p-rounded rule on the model's "
            "own triple lock, checked exactly (1e-9); every other check unchanged"},
    {"what": "Host admission",
     "how": "jobs.py reserves 40 GiB per Microcosm job; the shared host had 12-16 GiB available (about 40 GiB held, "
            "mostly compressed, by other workloads on the machine). Admission instead used host.assess with a floor "
            "of a 6 GiB job budget (resident peaks 5.6-15 GiB measured) + 2 GiB + what running jobs may still "
            "allocate; jobs ran partly compressed/swapped, which slows them but never changed a result"},
]


def mode_report(args):
    out = load_out()
    env, d, e = out["environment"], out["design"], out["estimates"]
    a = e["as_run"]
    pk = env["packages"]
    def f(x, nd=2):
        return "n/a" if x is None else f"{x:,.{nd}f}"
    def est(x, nd=2, unit=""):
        return f"{unit}{f(x['estimate'], nd)} (SE {f(x['se'], nd)}; 95% {unit}{f(x['interval_95'][0], nd)} to {unit}{f(x['interval_95'][1], nd)})"
    L = []
    L.append("# B1 full runs on a weighted sample of the Bayesian paths: report")
    L.append("")
    L.append(f"Generated {datetime.now(timezone.utc).isoformat(timespec='minutes')} by `scripts/b1_full_runs.py` "
             "(docs/METHOD.md, \"Specification: full runs on a weighted sample of the Bayesian paths, 18 November "
             "2026\"). Full data: `data/b1/full_runs.json`. Nothing here changes `data/results.json` or the paper.")
    L.append("")
    L.append("## What was run")
    L.append(f"- policyengine.py {pk['policyengine']}, policyengine-uk {pk['policyengine-uk']}, policyengine-core "
             f"{pk['policyengine-core']}, Python {env['python']}; Microcosm national file `{DATA_BUILD}` "
             f"(SHA-256 {DATA_SHA256[:12]}..., the file the 6.20.2 bundle certifies).")
    L.append(f"- **Not a certified pair:** 6.20.2 pins and certifies policyengine-uk "
             f"{env['bundle']['certified_model']} / core {env['bundle']['certified_core']} with this file; the runs use "
             "2.179.1 as instructed and registered (see deviations).")
    L.append(f"- Paths: the headline's {d['paths']['n_paths']:,} B1 paths (seed 20261113; 2039 rule-arithmetic gross "
             f"median reproduced, £{d['paths']['reproduces_forecast_gross_median_2039_bn']:.2f}bn). Stratum 0 (rules "
             f"identical every April to 2039): {d['paths']['identical']:,} paths, W0 = {d['W']['0']:.4f}, no runs. "
             f"Non-identical paths with no positive 2039 saving: {d['paths']['not_identical_non_positive_2039']}.")
    L.append(f"- Sample: N = {d['allocation']['n_total']} draws (seed {d['sample_seed']}, min 4 per stratum, Neyman "
             f"on rule-arithmetic gross), {d['unique_paths']} unique paths. {d.get('n_choice', '')}")
    L.append("")
    L.append("| Stratum | Probability | 2039 rule gross £bn | W | Draws | Runs ok | Net/gross mean (min-max) | Full/rule gross (6.20.2 base) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k in range(1, 11):
        b, bs = d["strata"][str(k)], e["by_stratum"].get(str(k), e["by_stratum"].get(k, {}))
        ng, fr = bs.get("net_to_gross", {}), (bs.get("full_gross_over_rule_gross_6_20_2_base") or {})
        L.append(f"| {k} | {b['probability'][0]:.2f}-{b['probability'][1]:.2f} | {b['gross_bn'][0]:.1f}-{b['gross_bn'][1]:.1f} | "
                 f"{b['W']:.4f} | {d['allocation']['by_stratum'][str(k)]} | {a['runs_by_stratum'].get(str(k), a['runs_by_stratum'].get(k, 0))} | "
                 f"{f(ng.get('mean'), 3)} ({f(ng.get('min'), 3)}-{f(ng.get('max'), 3)}) | {f(fr.get('mean'), 4)} ({f(fr.get('min'), 4)}-{f(fr.get('max'), 4)}) |")
    L.append("")
    L.append("## Anchor reruns (2039-40), 6.20.2 against stored 6.11.1")
    L.append("| Path | Gross £bn | Net £bn | Households losing % | Mean loss £ | Run time s | Peak RSS GiB |")
    L.append("|---|---|---|---|---|---|---|")
    for key, label in (("central", "OBR central"), ("obr_wedge", "OBR long-term (wedge)")):
        an = out["anchors"].get(key, {})
        st, rr = an.get("stored_6_11_1", {}), an.get("rerun_6_20_2") or {}
        sh, rh = st.get("households_affected", {}), rr.get("households_affected", {})
        L.append(f"| {label} | {f(st.get('gross_bn'))} -> {f(rr.get('gross_bn'))} | {f(st.get('net_bn'))} -> {f(rr.get('net_bn'))} | "
                 f"{f(sh.get('losing_pct'))} -> {f(rh.get('losing_pct'))} | {f(sh.get('mean_loss_gbp'), 0)} -> {f(rh.get('mean_loss_gbp'), 0)} | "
                 f"{f(rr.get('seconds'), 0)} | {f(rr.get('peak_rss_gib'), 1)} |")
    L.append("")
    L.append("## Headline estimates, 2039-40 (stratified bootstrap, 2,000 resamples within strata, seed 20261118)")
    L.append(f"- **Median net saving:** £{est(a['median_net_bn'])}bn.")
    L.append(f"- **Average annual loss among losing households (mean_loss_gbp):** stratum-weighted median over paths "
             f"£{est(a['mean_loss_gbp_weighted_median_over_paths'], 0)}; in the median-gross stratum (stratum "
             f"{a['mean_loss_gbp_in_median_gross_stratum']['stratum']}) £{est(a['mean_loss_gbp_in_median_gross_stratum'], 0)}.")
    ra = e["rule_arithmetic"]
    L.append(f"- **Gross median:** full runs £{est(a['median_gross_bn_full_runs'])}bn; rule arithmetic "
             f"£{f(ra['median_gross_bn_rule_arithmetic_stored_base'])}bn on the stored 6.11.1 base, "
             f"£{f(ra.get('median_gross_bn_rule_arithmetic_6_20_2_base'))}bn on the 6.20.2 central rerun's base.")
    rho = e["paper_fixed_ratio"]["value"]
    L.append(f"- **Net-to-gross:** the paper's fixed ratio is {rho:.3f} (D.B1_RHO); by stratum see the table. "
             f"Fixed ratio x full-run gross median = £{rho * a['median_gross_bn_full_runs']['estimate']:.2f}bn.")
    sup = e.get("supplementary_ratio_estimator")
    if sup:
        L.append(f"- *Not registered, a check on the above:* full-run gross equals the rule arithmetic path by path "
                 f"(table), so the 100-run median carries sampling noise (its gross median £{a['median_gross_bn_full_runs']['estimate']:.2f}bn "
                 f"against £{sup['median_gross_bn_rule_arithmetic_6_20_2_base']:.2f}bn over all paths). Each stratum's mean net/gross "
                 f"and loss/gross applied to all 399,440 paths gives median net £{est(sup['median_net_bn'])}bn and "
                 f"median mean_loss_gbp £{est(sup['mean_loss_gbp_median_over_positive_paths'], 0)}; pooled net/gross "
                 f"{sup['pooled_net_to_gross']:.3f}.")
    z = a.get("mean_loss_gbp_weighted_median_over_paths_stratum0_at_zero")
    if z:
        L.append(f"- mean_loss_gbp median with stratum 0 at the engine's £0 (the reading parallel to the net median): "
                 f"£{est(z, 0)}.")
    an = e.get("anchor_net_to_gross_6_20_2")
    if an:
        L.append(f"- Like-for-like net/gross: 6.20.2 anchors {an['central']:.3f} (central) and {an['obr_wedge']:.3f} "
                 f"(long-term), against {e['supplementary_ratio_estimator']['pooled_net_to_gross']:.3f} pooled over the "
                 f"sample and 0.683 fixed in the paper (stored 6.11.1 anchors "
                 f"{e['anchor_net_to_gross_6_11_1']['central']:.3f} and {e['anchor_net_to_gross_6_11_1']['obr_wedge']:.3f}).")
    m = a["weighted_mean_net_bn_error_budget_only"]
    L.append(f"- Weighted mean net (error budget only, not for print): £{m['mean']:.2f}bn, SE {m['se']:.2f} "
             f"(path sampling {m['se_path_sampling']:.2f}).")
    L.append(f"- Engine rates against rule arithmetic, every run: max difference {e['max_engine_vs_rule_arithmetic_rate_error']:.1e}.")
    fails = out.get("failures", {})
    if fails:
        L.append(f"- **Failed runs ({len(fails)}):** " + "; ".join(f"{n}: {v[-1]['reason'][:160]}" for n, v in fails.items()))
        for lab in ("failed_at_stratum_min", "failed_at_stratum_max"):
            if lab in e:
                L.append(f"  - {lab}: median net £{est(e[lab]['median_net_bn'])}bn; loss median "
                         f"£{est(e[lab]['mean_loss_gbp_weighted_median_over_paths'], 0)}.")
    else:
        L.append("- Failed runs: none after retry.")
    L.append("")
    L.append("## Adaptations and deviations from the registered design")
    for x in (out.get("adaptations") or ADAPTATIONS):
        if x["what"] == "Host admission":
            continue  # stated once, among the deviations
        L.append(f"- **{x['what']}:** {x['how']}.")
    for x in out.get("deviations", []):
        L.append(f"- {x}")
    L.append("")
    for key in ("linked_pension_credit_hb_derivation", "upstream_files_read", "guard_set_note"):
        if out.get("checks_outside_runs", {}).get(key):
            L.append(f"- {out['checks_outside_runs'][key]}")
    L.append("")
    L.append("## Caveats")
    for x in out.get("caveats", []):
        L.append(f"- {x}")
    REPORT.write_text("\n".join(L) + "\n")
    print(REPORT)


def mode_supplement(args):
    """Not registered: a model-assisted check on the registered median. Full-run gross equals the rule arithmetic
    (on the 6.20.2 central base) path by path, so each stratum's mean ratio of net (and of mean_loss_gbp) to gross,
    applied to every one of the 399,440 paths' rule-arithmetic gross, gives a population median free of the
    sampling noise in the 100-run median. Bootstrap: runs resampled within strata (2,000, seed fixed)."""
    log = logger()
    from triple_lock import b1_bayes as B
    from triple_lock.config import HORIZON

    out = load_out()
    d, jf = out["design"], HORIZON.index(FINAL)
    inputs, ar, ctx = b1_paths()
    rec = load_cached("anchor_central", anchor_specs()["anchor_central"])
    base_new = np.array([rec["result"]["totals_bn"]["triple_lock"][str(y)]["state_pension_flat_rate"] for y in HORIZON])
    gross = B.arithmetic(inputs, {**ctx, "base": base_new})["gross_bn"][:, jf]
    strata, _ = stratify_b1(ar["gross_bn"][:, jf], ar["same"][:, jf])
    runs = out["runs"]
    sample = {int(k): v for k, v in d["sample"].items()}
    ratio = {k: np.array([runs[f"path_{i}"]["net_bn"] / runs[f"path_{i}"]["gross_bn"] for i in idx]) for k, idx in sample.items()}
    lossr = {k: np.array([runs[f"path_{i}"]["households_affected"]["mean_loss_gbp"] / runs[f"path_{i}"]["gross_bn"]
                          for i in idx]) for k, idx in sample.items()}
    k_med = out["estimates"]["median_gross_stratum"]

    def stats(rr, lr):
        net = np.zeros(len(gross))
        loss = np.full(len(gross), np.nan)
        for k in rr:
            m = strata == k
            net[m] = gross[m] * rr[k].mean()
            loss[m] = gross[m] * lr[k].mean()
        pos = strata > 0
        return (float(np.median(net)), float(np.median(loss[pos])), float(np.mean(net)))

    point = stats(ratio, lossr)
    rng = np.random.default_rng(BOOT_SEED)
    draws = []
    for _ in range(N_BOOT):
        pick = {k: rng.integers(0, len(v), len(v)) for k, v in ratio.items()}
        draws.append(stats({k: ratio[k][pick[k]] for k in ratio}, {k: lossr[k][pick[k]] for k in lossr}))
    draws = np.array(draws)
    def summ(j):
        return {"estimate": point[j], "se": float(draws[:, j].std(ddof=1)),
                "interval_95": [float(np.percentile(draws[:, j], 2.5)), float(np.percentile(draws[:, j], 97.5))]}
    out["estimates"]["supplementary_ratio_estimator"] = {
        "registered": False, "method": mode_supplement.__doc__.strip(),
        "median_net_bn": summ(0), "mean_loss_gbp_median_over_positive_paths": summ(1), "mean_net_bn": summ(2),
        "median_gross_bn_rule_arithmetic_6_20_2_base": float(np.median(gross)),
        "pooled_net_to_gross": float(sum(runs[f"path_{i}"]["net_bn"] for v in sample.values() for i in v)
                                     / sum(runs[f"path_{i}"]["gross_bn"] for v in sample.values() for i in v)),
    }
    save_out(out)
    log(json.dumps(out["estimates"]["supplementary_ratio_estimator"], indent=1)[:1500])


def ar_rates(ar, key):
    if key not in ar:
        raise KeyError(key)
    return ar[key]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--job":
        child(argv[1], argv[2])
        return 0
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("anchors")
    a.add_argument("--workers", type=int, default=1)
    a.add_argument("--budget-gib", type=float, default=30.0)
    a.add_argument("--only", nargs="*")
    d = sub.add_parser("design")
    d.add_argument("--n", type=int, required=True)
    d.add_argument("--n-note", default="")
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--budget-gib", type=float, default=30.0)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--with-wedge", action="store_true")
    sub.add_parser("estimate")
    sub.add_parser("report")
    sub.add_parser("supplement")
    args = p.parse_args(argv)
    {"anchors": mode_anchors, "design": mode_design, "run": mode_run, "estimate": mode_estimate, "report": mode_report, "supplement": mode_supplement}[args.mode](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
