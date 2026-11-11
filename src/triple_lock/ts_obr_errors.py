"""C4: paths centred on the OBR forecast, with errors drawn from the OBR's own forecast record.

The rule this module implements is frozen in docs/METHOD.md between the C4 markers and was committed before any of
this code existed. This model was designed after the first model (the monthly VAR(1) residual bootstrap) failed C2.
No PolicyEngine run or survey data enters anything here.

    python -m triple_lock.ts_obr_errors --output data/c4

writes the registered test's scores and verdict (``scores.json``), the rule arithmetic on 10,000 forward paths
(``rule_arithmetic.json``) and the stratified sample for full runs, as a specification that nothing here runs
(``sample_design.json``, ``sample_specs.json``).
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from . import rules
from .config import ACTUALS_CSV, CALENDAR_YEARS, ERROR_CSV, HORIZON, REPO, STATUTORY_YEARS
from .ts_backtest import (
    APRIL_2022_TREATMENTS,
    H,
    SUSPENDED_DETERMINATION_YEAR,
    candidate_score,
    complete_statutory_origins,
    gap_pct,
    load_forecasts,
    mean_with_overlap_se,
    statutory_outturns,
    weighted_mean_with_overlap_se,
    wilson_band,
)
from .ts_methods import interval_hit

VARIABLES = ("cpi", "earnings")
N_SCORE_DRAWS = 5000
N_FORWARD = 10_000
FORWARD_SEED = 20261111
FORWARD_ORIGIN = 2026
N_FULL_RUNS = 180
SHARE_THRESHOLDS_PCT = (0, 1, 2, 3, 5, 7.5, 10)
REPORT_YEARS = (2034, 2039)
C2_REFERENCE = REPO / "data" / "pilot" / "c2-binding" / "scores.json"
C2_REFERENCE_FORM = "monthly_var1_boot"
PROPER_SCORES = ("gap_crps", "switch_crps", "floor_crps", "energy", "variogram")
RULE_SECTION_SHA256 = "1f51be2ed354fd13629c7eeb1415a2830002f4b916117dc4596353acecaccec8"
REGISTRATION_COMMIT = "7ed1244267f54f4ce7c13a7731401023f809251d"
LIMITS = {
    "annual_coverage": [0.5, 1.0], "terminal_coverage": [0.5, 1.0], "terminal_wilson_contains": 0.8,
    "gap_bias_pp": 1.5, "switch_bias": 1.0, "floor_bias": 0.25, "proper_score_ratio": 1.25,
    # The added checks of the central bands, test B only.
    "annual_coverage_80_b": [0.65, 0.95], "annual_coverage_50_b": [0.30, 0.70], "terminal_hits_50_b": [3, 10],
}
# The variants the registration names. Only "primary" enters the verdict.
VARIANTS = {
    "primary": {"pool": "target_years", "demean": True, "centre": True, "small_sample": True},
    "raw_errors": {"pool": "target_years", "demean": False, "centre": False, "small_sample": False},
    "no_centre_uncertainty": {"pool": "target_years", "demean": True, "centre": False, "small_sample": False},
    "leave_one_forecast_out": {"pool": "leave_one_out", "demean": True, "centre": True, "small_sample": True},
    "chronological": {"pool": "chronological", "demean": True, "centre": True, "small_sample": True},
}


def frozen_rule_hash(method_path=None):
    """SHA-256 of the bytes between the C4 markers of docs/METHOD.md."""
    content = Path(method_path or REPO / "docs" / "METHOD.md").read_bytes()
    begin, end = b"<!-- C4 frozen rule begins -->", b"<!-- C4 frozen rule ends -->"
    if content.count(begin) != 1 or content.count(end) != 1:
        raise ValueError("docs/METHOD.md must hold exactly one C4 frozen rule")
    return hashlib.sha256(content.split(begin, 1)[1].split(end, 1)[0]).hexdigest()


# ── The record ───────────────────────────────────────────────────────────────


def _efo_estimate(year):
    """The October 2026 EFO's calendar-year figure for a year with no calendar outturn yet (2026)."""
    from .config import CENTRAL_FORECAST_CSV

    out = {}
    with Path(CENTRAL_FORECAST_CSV).open(newline="") as f:
        for r in csv.DictReader(f):
            if r["basis"] == "calendar_year" and r["period"] == str(year) and r["variable"] in VARIABLES:
                out[r["variable"]] = float(r["value"])
    if set(out) != set(VARIABLES):
        raise ValueError(f"no EFO calendar-year estimate for {year}")
    return out


def load_record(error_csv=ERROR_CSV, actuals_csv=ACTUALS_CSV):
    """The spring forecasts with four complete statutory outturns, and their errors.

    Returns a dict: ``origins`` [(year, label)], ``years`` (n,), ``forecast`` (n, 4, 2), ``statutory`` and
    ``calendar`` errors (n, 4, 2), each [cpi, earnings] by horizon 1..4. Statutory outturns are as published.
    """
    forecasts, calendar_outturns = load_forecasts(error_csv)
    published = statutory_outturns(actuals_csv)
    origins = complete_statutory_origins(forecasts, published)
    fc = np.array([[[forecasts[v][(var, h)] for var in VARIABLES] for h in range(1, H + 1)] for v in origins])
    stat = np.array([[published[v[0] + h] for h in range(1, H + 1)] for v in origins])
    cal = np.empty_like(fc)
    stand_in = {}
    for i, v in enumerate(origins):
        for h in range(1, H + 1):
            for k, var in enumerate(VARIABLES):
                value = calendar_outturns.get(v, {}).get((var, h))
                if value is None:
                    year = v[0] + h
                    if year != FORWARD_ORIGIN:
                        raise ValueError(f"no calendar outturn for {var} in {year}")
                    value = stand_in.setdefault(year, _efo_estimate(year))[var]
                cal[i, h - 1, k] = value
    return {"origins": origins, "years": np.array([v[0] for v in origins]), "forecast": fc,
            "statutory_outturn": stat, "statutory": stat - fc, "calendar": cal - fc,
            "calendar_stand_in_years": sorted(stand_in)}


def pool_indices(years, origin_year, rule="target_years"):
    """Indices of the record origins that may forecast ``origin_year``'s window.

    ``target_years``: origins sharing no target year with it (at least four years away), the registered hold-out.
    ``leave_one_out``: every other origin. ``chronological``: origins whose four outturns were published before it.
    ``all``: the whole record (forward use, whose target years lie after the record's).
    """
    years = np.asarray(years)
    if rule == "target_years":
        keep = np.abs(years - origin_year) >= H
    elif rule == "leave_one_out":
        keep = years != origin_year
    elif rule == "chronological":
        keep = years + H <= origin_year - 1
    elif rule == "all":
        keep = np.ones(len(years), dtype=bool)
    else:
        raise ValueError(f"unknown pool rule {rule!r}")
    return np.flatnonzero(keep)


# ── The model ────────────────────────────────────────────────────────────────


def draw_errors(errors, years, n_draws, horizon, seed, *, demean=True, centre=True, small_sample=True):
    """Error paths (n_draws, horizon, 2) for each array in ``errors``, drawn jointly from one pool.

    ``errors`` maps a name to an array (n, 4, 2) of one kind of error (statutory, calendar) for the pool's origins,
    whose forecast years are ``years``. Every array uses the same resample, the same origin and the same target
    years on each path. The steps are those of the registration: a moving-block resample of the pool for the centre
    (step 1), one origin's residuals for years 1 to 4 (step 2), and from year 5 the four-year-ahead residuals of
    the target years that followed that origin's, restarting at a random target year when the record runs out
    (step 3).
    """
    years = np.asarray(years)
    n = len(years)
    if n < 2:
        raise ValueError("the pool needs at least two forecasts")
    if list(years) != sorted(set(years.tolist())):
        raise ValueError("pool years must be distinct and increasing")
    rng = np.random.default_rng(seed)
    blocks = -(-n // H)
    starts = rng.integers(0, n, size=(n_draws, blocks))
    resample = ((starts[:, :, None] + np.arange(H)[None, None, :]) % n).reshape(n_draws, -1)[:, :n]
    origin = rng.integers(0, n, size=n_draws)
    restarts = rng.integers(0, n, size=(n_draws, max(horizon - H, 0)))
    # Position in the pool of the origin whose four-year-ahead residual each later year takes.
    position_of = {int(y): i for i, y in enumerate(years)}
    later = np.empty((n_draws, max(horizon - H, 0)), dtype=int)
    current = years[origin]
    for j in range(horizon - H):
        wanted = current + 1
        found = np.array([position_of.get(int(y), -1) for y in wanted])
        found = np.where(found >= 0, found, restarts[:, j])
        later[:, j] = found
        current = years[found]
    factor = np.sqrt(n / (n - 1)) if small_sample else 1.0
    out = {}
    for name, e in errors.items():
        e = np.asarray(e, dtype=float)
        if e.shape != (n, H, 2):
            raise ValueError(f"{name} errors must have shape ({n}, {H}, 2)")
        mean = e.mean(axis=0) if demean else np.zeros((H, 2))
        residual = factor * (e - mean) if demean else e
        shift = e[resample].mean(axis=1) - e.mean(axis=0) if centre else np.zeros((n_draws, H, 2))
        path = np.empty((n_draws, horizon, 2))
        first = min(horizon, H)
        path[:, :first] = shift[:, :first] + residual[origin][:, :first]
        if horizon > H:
            path[:, H:] = shift[:, H - 1][:, None, :] + residual[later, H - 1]
        out[name] = path
    return out


# ── The registered test ──────────────────────────────────────────────────────


def central_50(draws, outcome, target_years, suspended_years):
    """Central-50% hits for the annual gaps (unsuspended cells) and the four-year gap, C2's legal treatment applied."""
    active = np.array([y not in set(suspended_years) for y in target_years])
    draws, outcome = np.array(draws, copy=True), np.array(outcome, copy=True)
    draws[:, ~active, 1] = draws[:, ~active, 0]
    outcome[~active, 1] = outcome[~active, 0]
    gaps = 100 * (draws[:, :, 1] - draws[:, :, 0])
    observed = 100 * (outcome[:, 1] - outcome[:, 0])
    terminal = gap_pct(draws, decimals=None)["burnham_2030"]
    realised = float(gap_pct(outcome[None], decimals=None)["burnham_2030"][0])
    annual = [interval_hit(gaps[:, j], observed[j], lo=0.25, hi=0.75) for j in np.flatnonzero(active)]
    return {"annual_gap_coverage_50": float(np.mean(annual)) if annual else None,
            "terminal_coverage_50": float(interval_hit(terminal, realised, lo=0.25, hi=0.75))}


def origin_draws(record, i, variant="primary", n=N_SCORE_DRAWS):
    """Statutory draws (n, 4, 2) for record origin ``i`` from its held-out pool; None if the pool is too small."""
    v = VARIANTS[variant]
    pool = pool_indices(record["years"], int(record["years"][i]), v["pool"])
    if len(pool) < 2:
        return None, pool
    eps = draw_errors({"statutory": record["statutory"][pool]}, record["years"][pool], n, H,
                      seed=int(record["years"][i]), demean=v["demean"], centre=v["centre"],
                      small_sample=v["small_sample"])["statutory"]
    return record["forecast"][i][None] + eps, pool


def run_test(variant="primary", n=N_SCORE_DRAWS, record=None, log=print):
    """Score one variant on C2's origins and treatments; rows per origin and summaries per test."""
    record = load_record() if record is None else record
    regime = (SUSPENDED_DETERMINATION_YEAR,)
    outturns = {"published": statutory_outturns(), "suspended": statutory_outturns(suspended_years=regime)}
    kept = record["origins"]
    chrono = [v for v in kept if sum(u[0] + H <= v[0] - 1 for u in kept) >= 2]
    rows, failures = [], []
    for i, v in enumerate(kept):
        years = [v[0] + h for h in range(1, H + 1)]
        draws, pool = origin_draws(record, i, variant, n)
        if draws is None:
            failures.append({"origin": v[1], "error": f"pool of {len(pool)} forecasts"})
            continue
        log(f"C4 {variant} {v[1]}: pool of {len(pool)}")
        if not np.isfinite(draws).all():
            failures.append({"origin": v[1], "error": "non-finite draws"})
            continue
        for treatment in APRIL_2022_TREATMENTS:
            d = draws.copy()
            suspended = treatment == "suspended"
            if suspended:
                for j, year in enumerate(years):
                    if year in regime:
                        d[:, j, 1] = d[:, j, 0]
            y = np.array([outturns[treatment][yy] for yy in years])
            metrics = candidate_score(d, y, v[0], target_years=years, suspended_years=regime,
                                      exclude_legal_constants=suspended)
            metrics.update(central_50(d, y, years, regime if suspended else ()))
            if not suspended:
                metrics["annual_gap_cells"] = H
            rows.append({"origin": v[1], "origin_year": v[0], "target_years": years, "chronological": v in chrono,
                         "treatment": treatment, "pool": [kept[j][1] for j in pool], **metrics})
    summaries = {}
    for test, origins in (("A", chrono), ("B", kept)):
        summaries[test] = {}
        for treatment in APRIL_2022_TREATMENTS:
            selected = [r for r in rows if r["treatment"] == treatment and (test == "B" or r["chronological"])]
            summaries[test][treatment] = _summary(selected, len(origins), treatment == "suspended")
    return {"variant": variant, "settings": VARIANTS[variant], "n_draws": n,
            "origins": {"A": [v[1] for v in chrono], "B": [v[1] for v in kept]},
            "bias_convention": "forecast mean minus realised; positive = overprediction",
            "rows": rows, "failures": failures, "scores": summaries}


SKIP = ("origin", "origin_year", "target_years", "chronological", "treatment", "pool", "annual_gap_cells",
        "annual_gap_excluded_cells", "legal_fixed_statistics")
CELL_WEIGHTED = ("gap_crps", "gap_bias_pp", "annual_gap_coverage", "annual_gap_coverage_50")


def _summary(selected, expected, suspended):
    """Means with C2's standard errors: annual-gap statistics pooled by cell, the rest by origin."""
    out = {"n_origins": len(selected), "expected_origins": expected}
    if len(selected) < 2:
        return out
    for k in [k for k in selected[0] if k not in SKIP]:
        eligible = [r for r in selected if r[k] is not None]
        if len(eligible) < 2:
            out[k] = {"mean": eligible[0][k] if eligible else None, "n_scored_origins": len(eligible)}
        elif suspended and k in CELL_WEIGHTED:
            out[k] = weighted_mean_with_overlap_se([r[k] for r in eligible], [r["annual_gap_cells"] for r in eligible])
        else:
            out[k] = mean_with_overlap_se([r[k] for r in eligible])
    for k in ("terminal_coverage", "terminal_coverage_50"):
        out[k]["hits"] = int(sum(r[k] for r in selected))
        out[k]["n"] = len(selected)
    out["terminal_coverage"]["wilson95_independent"] = wilson_band(out["terminal_coverage"]["hits"], len(selected))
    out["annual_gap_cells"] = sum(r["annual_gap_cells"] for r in selected)
    return out


def verdict(result, reference=None):
    """Apply the registered pass rule literally to a variant's suspended-treatment scores."""
    reference = json.loads(C2_REFERENCE.read_text()) if reference is None else reference
    failures, checks = [], []

    def check(tag, name, value, ok, limit):
        checks.append({"test": tag, "check": name, "value": value, "limit": limit, "passes": bool(ok)})
        if not ok:
            failures.append(f"{tag}: {name} {value} outside {limit}")

    if result["failures"]:
        failures.append(f"failed or missing origins: {[f['origin'] for f in result['failures']]}")
    for test in ("A", "B"):
        s = result["scores"][test]["suspended"]
        if s["n_origins"] != s["expected_origins"] or s["n_origins"] < 2:
            failures.append(f"{test}: missing origins ({s['n_origins']} of {s['expected_origins']})")
            continue
        means = [m["mean"] for m in s.values() if isinstance(m, dict) and "mean" in m]
        check(test, "finite scores", all(m is not None and np.isfinite(m) for m in means),
              all(m is not None and np.isfinite(m) for m in means), True)
        for k, key in (("annual_gap_coverage", "annual_coverage"), ("terminal_coverage", "terminal_coverage")):
            lo, hi = LIMITS[key]
            check(test, k, s[k]["mean"], lo <= s[k]["mean"] <= hi, [lo, hi])
        lo, hi = s["terminal_coverage"]["wilson95_independent"]
        check(test, "terminal Wilson band contains 0.80", [lo, hi], lo <= LIMITS["terminal_wilson_contains"] <= hi,
              LIMITS["terminal_wilson_contains"])
        for k in ("gap_bias_pp", "switch_bias", "floor_bias"):
            check(test, f"|{k}|", abs(s[k]["mean"]), abs(s[k]["mean"]) <= LIMITS[k], LIMITS[k])
        ref = reference["scores"][test]["suspended"][C2_REFERENCE_FORM]
        for k in PROPER_SCORES:
            base = ref[k]["mean"]
            ratio = s[k]["mean"] / base if base > 0 else (1.0 if s[k]["mean"] == 0 else float("inf"))
            check(test, f"{k} ratio to the first model", ratio, np.isfinite(ratio) and
                  ratio <= LIMITS["proper_score_ratio"], LIMITS["proper_score_ratio"])
    b = result["scores"]["B"]["suspended"]
    if b.get("annual_gap_coverage"):
        lo, hi = LIMITS["annual_coverage_80_b"]
        check("B", "annual central-80% coverage (added)", b["annual_gap_coverage"]["mean"],
              lo <= b["annual_gap_coverage"]["mean"] <= hi, [lo, hi])
        lo, hi = LIMITS["annual_coverage_50_b"]
        check("B", "annual central-50% coverage (added)", b["annual_gap_coverage_50"]["mean"],
              lo <= b["annual_gap_coverage_50"]["mean"] <= hi, [lo, hi])
        lo, hi = LIMITS["terminal_hits_50_b"]
        check("B", "four-year gaps inside the central-50% band (added)", b["terminal_coverage_50"]["hits"],
              lo <= b["terminal_coverage_50"]["hits"] <= hi, [lo, hi])
    return {"passes": not failures, "failures": failures, "checks": checks,
            "past_years_check": "not scored: no error record exists before 2011; never counted as passed"}


# ── Forward use: rule arithmetic and the sample for full runs ────────────────


def forward_draws(n=N_FORWARD, seed=FORWARD_SEED, record=None, central=None):
    """Draw set in the layout ``expected_value.path_spec`` reads: statutory inputs 2026-2038, calendar 2027-2039."""
    from .central import central_path

    record = load_record() if record is None else record
    central = central_path() if central is None else central
    horizon = CALENDAR_YEARS[-1] - FORWARD_ORIGIN
    eps = draw_errors({"statutory": record["statutory"], "calendar": record["calendar"]}, record["years"], n,
                      horizon, seed)
    stat = np.empty((n, len(STATUTORY_YEARS), 2))
    for j, y in enumerate(STATUTORY_YEARS):
        centre = np.array([central["statutory"][v][y] for v in VARIABLES])
        stat[:, j] = centre if y == FORWARD_ORIGIN else centre + eps["statutory"][:, y - FORWARD_ORIGIN - 1]
    cal = np.stack([np.array([central["calendar"][v][y] for v in VARIABLES]) + eps["calendar"][:, y - FORWARD_ORIGIN - 1]
                    for y in CALENDAR_YEARS], axis=1)
    return {"stat_cpi": stat[:, :, 0], "stat_earnings": stat[:, :, 1], "calendar": cal,
            "info": {"model": "c4_obr_forecast_errors", "n": n, "seed": seed, "pool": [v[1] for v in record["origins"]]}}


def log_gap(stat_cpi, stat_earnings):
    """G by April year (n, len(HORIZON)): cumulative ln(1 + triple-lock rise) - ln(1 + adjusted rise), 0.1-point rates."""
    from .config import CENTRAL_RATE_DECIMALS

    tl = rules.rates_matrix("triple_lock", stat_cpi, stat_earnings, HORIZON, CENTRAL_RATE_DECIMALS)
    bp = rules.rates_matrix("burnham_2030", stat_cpi, stat_earnings, HORIZON, CENTRAL_RATE_DECIMALS)
    return np.cumsum(np.log1p(tl) - np.log1p(bp), axis=1)


def distribution(x, thresholds=None):
    out = {"mean": float(np.mean(x)), "median": float(np.median(x)),
           **{f"p{q}": float(np.quantile(x, q / 100)) for q in (5, 25, 75, 95)}}
    if thresholds is not None:
        out["probability_above_pct"] = {str(t): float(np.mean(100 * x > t)) for t in thresholds}
    return out


def rule_arithmetic(d):
    """The distribution of G and of the share 1 - exp(-G) over a draw set, in the registered years."""
    G = log_gap(d["stat_cpi"], d["stat_earnings"])
    out = {}
    for y in REPORT_YEARS:
        g = G[:, HORIZON.index(y)]
        out[str(y)] = {"log_gap_G": distribution(g), "share": distribution(-np.expm1(-g), SHARE_THRESHOLDS_PCT)}
    return out


def design(d, n_runs=N_FULL_RUNS):
    """The stratified sample for full runs and its engine specs. Nothing here runs them."""
    from . import expected_value as EV
    from .ts_uncertainty import sample_design, validate_rule_draws

    checks = validate_rule_draws(d)
    spec = sample_design(d, n_runs=n_runs, include_zero=True)
    strata, gap = spec.pop("strata"), spec.pop("gap")
    slots = [i for indices in spec["sample"].values() for i in indices]
    extra = {spec["identical_check_draw"]} if spec["identical_check_draw"] is not None else set()
    unique = sorted(set(slots) | extra)
    spec.update(sample_slots=len(slots), unique_full_runs=len(unique), gap_unit="level relative to base pension = 1",
                stratum_gap_range={str(k): [float(gap[strata == k].min()), float(gap[strata == k].max())]
                                   for k in sorted(set(strata.tolist()))},
                all_draw_rule_checks=checks, run_status="specification only; not run")
    return spec, [EV.path_spec(d, i) for i in unique]


def _write(path, value):
    path.write_text(json.dumps(value, indent=1, sort_keys=True, default=float) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=REPO / "data" / "c4")
    args = parser.parse_args()
    if frozen_rule_hash() != RULE_SECTION_SHA256:
        raise SystemExit("the C4 rule in docs/METHOD.md differs from its registered bytes")
    args.output.mkdir(parents=True, exist_ok=True)
    record = load_record()
    provenance = {"screen": "c4", "registration_commit": REGISTRATION_COMMIT,
                  "rule_section_sha256": RULE_SECTION_SHA256, "numpy_version": np.__version__,
                  "no_microsimulation": True,
                  "designed_after": "the monthly VAR(1) residual bootstrap failed the binding C2 test",
                  "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (ERROR_CSV, ACTUALS_CSV, C2_REFERENCE)},
                  "calendar_stand_in_years": record["calendar_stand_in_years"]}
    results = {name: run_test(name, record=record) for name in VARIANTS}
    primary = results["primary"]
    outcome = verdict(primary)
    scores = {**provenance, "limits": LIMITS, "verdict": outcome, "primary": primary,
              "sensitivities_no_influence_on_verdict": {
                  name: {"scores": r["scores"], "failures": r["failures"], "settings": r["settings"],
                         "would_pass": verdict(r)["passes"], "would_fail_on": verdict(r)["failures"]}
                  for name, r in results.items() if name != "primary"}}
    _write(args.output / "scores.json", scores)
    d = forward_draws(record=record)
    label = ("conditional on a model that passed its registered test" if outcome["passes"]
             else "output of a model that failed its registered test; not a probability statement")
    _write(args.output / "rule_arithmetic.json",
           {**provenance, "c4_passes": outcome["passes"], "label": label, "n_paths": N_FORWARD, "seed": FORWARD_SEED,
            "years": {str(y): f"{y}-{str(y + 1)[2:]}" for y in REPORT_YEARS}, "units": "G in log points; share as a fraction",
            "identical_share": float(np.mean(log_gap(d["stat_cpi"], d["stat_earnings"])[:, -1] == 0)),
            "distribution": rule_arithmetic(d)})
    spec, specs = design(d)
    _write(args.output / "sample_design.json", {**provenance, "c4_passes": outcome["passes"], "n_draws": N_FORWARD,
                                                "draw_seed": FORWARD_SEED, **spec})
    _write(args.output / "sample_specs.json", specs)
    print(json.dumps({"passes": outcome["passes"], "failures": outcome["failures"]}, indent=1))


if __name__ == "__main__":
    main()
