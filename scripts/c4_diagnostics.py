"""Diagnostics of the failed forecast-error path model (C4): why it failed, and what its forward distribution rests on.

The registered test (docs/METHOD.md, C4) ran once and failed. Nothing here changes that verdict, the model or any
committed score: this script reads the registered code unchanged and asks five questions of it.

* Seed robustness: do the failing check (test B variogram ratio) and the knife-edge pass (test A floor bias) survive
  other random seeds? The scoring code seeds each origin with its year; here origin ``v`` takes ``v + offset``.
* Which origins carry the variogram excess over the first model, and which forecasts sit in their hold-out pools.
* Resolution: how many distinct error histories the 10,000 forward paths hold, and how many sit in each tail.
* Centring: the mean statutory error by determination year (Monte Carlo, and exactly from the walk's weights), and
  what removing it does to the mean share.
* Decomposition of the 2039-40 mean share: error scale, calendar-year errors, re-centring and the 2.5% floor, against
  the two published earnings scenarios of the first model.

Plus one identity on the first model's stored runs: gross saving = share x base, path by path, reproduces the stored
stratified scenario means on the 160-slot design. The failed model's paths are never converted to cash: the
registered fail clause forbids an expected cash figure from it.

It runs no microsimulation and writes data/c4/diagnostics.json.

    PYTHONPATH=src python scripts/c4_diagnostics.py
"""

import json
from pathlib import Path

import numpy as np

from triple_lock import expected_value as EV
from triple_lock import rules
from triple_lock import ts_obr_errors as C4
from triple_lock import ts_uncertainty as U
from triple_lock.central import central_path, long_run_earnings_variant
from triple_lock.config import HORIZON, STATUTORY_YEARS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "c4" / "diagnostics.json"
N_SEED_SETS = 40
SEED_OFFSET_STEP = 100_000  # seed set k gives origin v the seed v + k * SEED_OFFSET_STEP; k = 0 is the registered run
SCALES = (0.25, 0.5, 0.75, 1.0)
TAIL_PCT = 5  # each tail of the 2039-40 share whose histories are counted
LATE_YEARS = (2021, 2022, 2023)  # target years whose four-year-ahead errors carry the 2020-23 earnings swings
SCENARIO_KEYS = {"minus": "earnings_minus_0_5pp", "plus": "earnings_plus_0_5pp"}
N_FIRST_MODEL = 50_000


# ── Seed robustness and where the failure comes from ─────────────────────


def _seeded_origin_draws(offset):
    """``C4.origin_draws`` with every origin's seed moved by ``offset``; the registered code otherwise unchanged."""

    def origin_draws(record, i, variant="primary", n=C4.N_SCORE_DRAWS):
        v = C4.VARIANTS[variant]
        pool = C4.pool_indices(record["years"], int(record["years"][i]), v["pool"])
        if len(pool) < 2:
            return None, pool
        eps = C4.draw_errors({"statutory": record["statutory"][pool]}, record["years"][pool], n, C4.H,
                             seed=int(record["years"][i]) + offset, demean=v["demean"], centre=v["centre"],
                             small_sample=v["small_sample"])["statutory"]
        return record["forecast"][i][None] + eps, pool

    return origin_draws


def _check(verdict, test, name):
    return next(c["value"] for c in verdict["checks"] if c["test"] == test and c["check"] == name)


def run_seed_set(record, reference, offset):
    original = C4.origin_draws
    C4.origin_draws = _seeded_origin_draws(offset)
    try:
        result = C4.run_test("primary", record=record, log=lambda *a: None)
    finally:
        C4.origin_draws = original
    v = C4.verdict(result, reference)
    return result, {"offset": offset, "variogram_ratio_b": _check(v, "B", "variogram ratio to the first model"),
                    "floor_bias_a": _check(v, "A", "|floor_bias|"), "passes": v["passes"], "failures": v["failures"]}


def seed_robustness(record, reference, registered):
    first, row0 = run_seed_set(record, reference, 0)
    reg = {c["test"] + ": " + c["check"]: c["value"] for c in registered["verdict"]["checks"]}
    assert np.isclose(row0["variogram_ratio_b"], reg["B: variogram ratio to the first model"], rtol=0, atol=1e-12)
    assert np.isclose(row0["floor_bias_a"], reg["A: |floor_bias|"], rtol=0, atol=1e-12)
    rows = [run_seed_set(record, reference, k * SEED_OFFSET_STEP)[1] for k in range(1, N_SEED_SETS + 1)]
    vario = np.array([r["variogram_ratio_b"] for r in rows])
    floor = np.array([r["floor_bias_a"] for r in rows])
    lim_v, lim_f = C4.LIMITS["proper_score_ratio"], C4.LIMITS["floor_bias"]
    return first, {
        "seed_rule": f"origin v takes seed v + k x {SEED_OFFSET_STEP}, k = 1..{N_SEED_SETS}; k = 0 reproduces the "
                     "registered scores exactly",
        "n_seed_sets": N_SEED_SETS,
        "registered": {"variogram_ratio_b": row0["variogram_ratio_b"], "floor_bias_a": row0["floor_bias_a"]},
        "variogram_ratio_b": {"min": float(vario.min()), "max": float(vario.max()), "mean": float(vario.mean()),
                              "limit": lim_v, "sets_above_limit": int((vario > lim_v).sum())},
        "floor_bias_a": {"min": float(floor.min()), "max": float(floor.max()), "mean": float(floor.mean()),
                         "limit": lim_f, "sets_above_limit": int((floor > lim_f).sum())},
        "sets_passing_every_check": int(sum(r["passes"] for r in rows)),
        "by_seed_set": rows,
    }


def variogram_by_origin(result, reference):
    """Test B, suspended treatment: each origin's variogram score against the first model's, and its hold-out pool."""
    ref = {r["origin"]: r["variogram"] for r in reference["rows"]
           if r["form"] == C4.C2_REFERENCE_FORM and r["treatment"] == "suspended"}
    rows = [r for r in result["rows"] if r["treatment"] == "suspended"]
    out = []
    for r in rows:
        out.append({"origin": r["origin"], "origin_year": r["origin_year"], "c4": r["variogram"],
                    "first_model": ref[r["origin"]], "excess": r["variogram"] - ref[r["origin"]],
                    "pool": r["pool"]})
    total = sum(o["excess"] for o in out)
    mid = [o for o in out if 2011 <= o["origin_year"] <= 2015]
    return {"rows": out, "total_excess": total, "excess_from_origins_2011_2015": sum(o["excess"] for o in mid),
            "share_from_origins_2011_2015": sum(o["excess"] for o in mid) / total}


# ── Forward paths: resolution and centring ───────────────────────────────


def _horizon():
    from triple_lock.config import CALENDAR_YEARS

    return CALENDAR_YEARS[-1] - C4.FORWARD_ORIGIN


def walk(record):
    """Each forward path's origin u and the pool positions its years 5 onward take (the registered draw, seed and
    horizon), read through ``draw_errors`` itself by coding each error with its origin's position."""
    n = len(record["years"])
    code = np.zeros((n, C4.H, 2))
    code[:, :, 0] = np.arange(n)[:, None]
    eps = C4.draw_errors({"code": code}, record["years"], C4.N_FORWARD, _horizon(), C4.FORWARD_SEED, demean=False,
                         centre=False, small_sample=False)["code"][:, :, 0]
    positions = np.rint(eps).astype(int)
    return positions[:, 0], positions[:, C4.H:len(STATUTORY_YEARS) - 1]  # years 5..12 (determination 2031-38)


def resolution(record, d):
    origin, later = walk(record)
    hist = np.c_[origin, later]
    share = -np.expm1(-C4.log_gap(d["stat_cpi"], d["stat_earnings"]))[:, -1]
    lo, hi = np.quantile(share, TAIL_PCT / 100), np.quantile(share, 1 - TAIL_PCT / 100)
    late = [i for i, y in enumerate(record["years"]) if int(y) + C4.H in LATE_YEARS]

    def distinct(mask):
        return int(len({tuple(r) for r in hist[mask]}))

    def covering(mask, part):
        """The fewest histories that hold ``part`` of the paths in ``mask``."""
        counts = np.sort(np.unique(hist[mask], axis=0, return_counts=True)[1])[::-1]
        return int(np.searchsorted(np.cumsum(counts) / mask.sum(), part) + 1)

    top, bottom = share >= hi, share <= lo
    tails = {name: {"distinct_histories": distinct(m), "histories_holding_half": covering(m, 0.5),
                    "histories_holding_80pct": covering(m, 0.8)} for name, m in (("lowest_5pct", bottom),
                                                                                  ("highest_5pct", top))}

    return {"n_paths": C4.N_FORWARD, "distinct_histories": distinct(np.ones(len(hist), bool)),
            "history": "origin u and the origins whose four-year-ahead errors years 5 to 12 take",
            "tails_of_share_2039": tails, "tail_pct": TAIL_PCT,
            "share_paths_without_restart": float(np.mean(np.all(np.diff(hist[:, 1:], axis=1) == 1, axis=1)
                                                         & (hist[:, 1] == origin + 1))),
            "late_target_years": list(LATE_YEARS),
            "share_paths_years_5_12_use_a_late_target_year": float(np.isin(later, late).any(axis=1).mean()),
            "share_paths_years_5_12_use_all_late_target_years":
                float(np.mean([set(late) <= set(r) for r in later.tolist()]))}


def drift(record, central, d):
    """Mean statutory error by determination year 2027-2038 (points), and the walk's exact expectation from year 5."""
    c = {v: np.array([central["statutory"][v][y] for y in STATUTORY_YEARS]) for v in C4.VARIABLES}
    err = {"cpi": d["stat_cpi"] - c["cpi"], "earnings": d["stat_earnings"] - c["earnings"]}
    years = STATUTORY_YEARS[1:]
    mc = {v: [float(100 * x) for x in err[v][:, 1:].mean(axis=0)] for v in C4.VARIABLES}
    mc_se = {v: [float(100 * x) for x in err[v][:, 1:].std(axis=0) / np.sqrt(len(err[v]))] for v in C4.VARIABLES}
    # Exact: the walk moves origin u to u + 1 while the record lasts and restarts uniformly when it runs out.
    n = len(record["years"])
    P = np.zeros((n, n))
    for i in range(n):
        if i + 1 < n:
            P[i, i + 1] = 1
        else:
            P[i, :] = 1 / n
    e = record["statutory"]
    res = np.sqrt(n / (n - 1)) * (e[:, C4.H - 1] - e[:, C4.H - 1].mean(axis=0))  # four-year-ahead residuals
    w = np.full(n, 1 / n)
    exact = {v: [0.0] * C4.H for v in C4.VARIABLES}  # years 1-4: the residuals of one origin, mean zero
    weight_late = []
    for _ in range(len(years) - C4.H):
        w = w @ P
        for k, v in enumerate(C4.VARIABLES):
            exact[v].append(float(100 * w @ res[:, k]))
        weight_late.append(float(w[np.isin(record["years"] + C4.H, LATE_YEARS)].sum()))
    return {"determination_years": list(years), "units": "percentage points; statutory input less the OBR path",
            "mean_error_monte_carlo": mc, "monte_carlo_se": mc_se, "mean_error_exact": exact,
            "weight_on_late_targets_from_year_5": weight_late,
            "uniform_weight_on_late_targets": float(np.mean(np.isin(record["years"] + C4.H, LATE_YEARS))),
            "mean_error_all_years": {v: float(100 * err[v][:, 1:].mean()) for v in C4.VARIABLES}}


# ── Decomposition of the mean share ──────────────────────────────────────


def share_stats(sc, se):
    G = C4.log_gap(sc, se)
    s = -np.expm1(-G)
    out = {}
    for y in C4.REPORT_YEARS:
        j = HORIZON.index(y)
        out[str(y)] = {"mean": float(s[:, j].mean()), "p25": float(np.quantile(s[:, j], 0.25)),
                       "median": float(np.median(s[:, j])), "p75": float(np.quantile(s[:, j], 0.75)),
                       "mean_G": float(G[:, j].mean())}
    return out


def with_floor(floor, f):
    old = rules.TRIPLE_LOCK_FLOOR
    rules.TRIPLE_LOCK_FLOOR = floor
    try:
        return f()
    finally:
        rules.TRIPLE_LOCK_FLOOR = old


def scenario_shares(central, design, floor=None):
    """The two published earnings scenarios' stratified mean shares (rule arithmetic on the 160-slot design)."""
    out = {}
    for k, (delta, start) in {"minus": (-0.005, 2031), "plus": (0.005, 2031)}.items():
        dv = U.future_draws(U.PRIMARY_FORM, long_run_earnings_variant(central, delta, start), N_FIRST_MODEL)

        def compute(dv=dv):
            s = -np.expm1(-C4.log_gap(dv["stat_cpi"], dv["stat_earnings"]))
            res = {}
            for y in C4.REPORT_YEARS:
                j = HORIZON.index(y)
                res[str(y)] = float(sum(design["stratum_weights"][int(h)] * np.mean(s[idx, j])
                                        for h, idx in design["sample"].items()))
            sd = {v: [float(100 * x) for x in dv[f"stat_{v}"][:, 1:].std(axis=0)] for v in C4.VARIABLES}
            return res, sd

        res, sd = compute() if floor is None else with_floor(floor, compute)
        out[k] = {"share": res, "input_sd_points": sd}
    return out


def decomposition(record, central, d, design, results):
    c = {v: np.array([central["statutory"][v][y] for y in STATUTORY_YEARS]) for v in C4.VARIABLES}
    ec, ee = d["stat_cpi"] - c["cpi"], d["stat_earnings"] - c["earnings"]
    rc, re_ = d["stat_cpi"] - ec.mean(axis=0), d["stat_earnings"] - ee.mean(axis=0)
    eps = C4.draw_errors({"s": record["calendar"]}, record["years"], C4.N_FORWARD, _horizon(), C4.FORWARD_SEED)["s"]
    cal_c, cal_e = np.tile(c["cpi"], (C4.N_FORWARD, 1)), np.tile(c["earnings"], (C4.N_FORWARD, 1))
    cal_c[:, 1:] += eps[:, :len(STATUTORY_YEARS) - 1, 0]
    cal_e[:, 1:] += eps[:, :len(STATUTORY_YEARS) - 1, 1]
    out = {"registered": share_stats(d["stat_cpi"], d["stat_earnings"]),
           "error_scale": {str(k): share_stats(c["cpi"] + k * ec, c["earnings"] + k * ee) for k in SCALES},
           "calendar_errors": share_stats(cal_c, cal_e),
           "re_centred": share_stats(rc, re_),
           "floor_off": with_floor(0.0, lambda: share_stats(d["stat_cpi"], d["stat_earnings"])),
           "re_centred_floor_off": with_floor(0.0, lambda: share_stats(rc, re_)),
           "obr_path": share_stats(c["cpi"][None], c["earnings"][None]),
           "input_sd_points": {"cpi": [float(100 * x) for x in ec[:, 1:].std(axis=0)],
                               "earnings": [float(100 * x) for x in ee[:, 1:].std(axis=0)]}}
    on, off = scenario_shares(central, design), scenario_shares(central, design, floor=0.0)
    published = {k: results["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"][SCENARIO_KEYS[k]]
                 ["scenario_path_set"]["gross_share_flat_rate_spending_pct"] for k in on}
    for k in on:
        for y in C4.REPORT_YEARS:  # the stratified rule arithmetic is the published share
            assert abs(100 * on[k]["share"][str(y)] - published[k][str(y)]["mean"]) < 1e-5, (k, y)
    out["scenarios"] = {k: {"share": on[k]["share"], "share_floor_off": off[k]["share"],
                            "input_sd_points": on[k]["input_sd_points"]} for k in on}
    y = str(C4.REPORT_YEARS[-1])
    sc_on = np.mean([on[k]["share"][y] for k in on])
    sc_off = np.mean([off[k]["share"][y] for k in on])
    gap_on = out["registered"][y]["mean"] - sc_on
    gap_off = out["floor_off"][y]["mean"] - sc_off
    out["gap_to_scenarios_2039"] = {
        "note": "C4 mean share less the mean of the two published scenario shares, with the floor and without it",
        "with_floor": float(gap_on), "floor_off": float(gap_off), "floor_part": float(gap_on - gap_off),
        "re_centring_part": float(out["registered"][y]["mean"] - out["re_centred"][y]["mean"])}
    return out


# ── Gross = share x base on the first model's stored runs ────────────────


def gross_identity(results, central, design):
    cr = results["scenario_envelope"]["central"]["run"]
    paths = {p["id"]: p for p in results["trajectories"]["paths"]}
    paths["obr_wedge"] = results["scenario_envelope"]["obr_wedge"]["run"]
    single = 0.0
    for p in paths.values():
        for y in map(str, HORIZON):
            tl, bp = (p["weekly"][k]["new_state_pension"][y] for k in ("triple_lock", "burnham_2030"))
            base = cr["totals_bn"]["triple_lock"][y]["state_pension_flat_rate"] * tl / \
                cr["weekly"]["triple_lock"]["new_state_pension"][y]
            single = max(single, abs((1 - bp / tl) * base - p["saving_bn"][y]["gross"]))
    base_w = results["base_year_weekly"]["new_state_pension"]
    stratified = {}
    for k, key in SCENARIO_KEYS.items():
        sc = results["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"][key]
        dv = U.future_draws(U.PRIMARY_FORM, long_run_earnings_variant(central, sc["calendar_earnings_delta"],
                                                                      sc["from_year"]), N_FIRST_MODEL)
        lv, _ = EV.rule_levels(dv["stat_cpi"], dv["stat_earnings"], base_w)
        worst = 0.0
        for j, y in enumerate(HORIZON):
            ys = str(y)
            g = (1 - lv["burnham_2030"][:, j] / lv["triple_lock"][:, j]) * \
                cr["totals_bn"]["triple_lock"][ys]["state_pension_flat_rate"] * lv["triple_lock"][:, j] / \
                cr["weekly"]["triple_lock"]["new_state_pension"][ys]
            est = sum(design["stratum_weights"][int(h)] * np.mean(g[idx]) for h, idx in design["sample"].items())
            worst = max(worst, abs(est - sc["scenario_path_set"]["gross"][ys]["mean"]))
        stratified[k] = worst
    return {"single_paths_max_abs_error_bn": single, "scenario_stratified_max_abs_error_bn": stratified,
            "sample_slots": sum(len(v) for v in design["sample"].values()),
            "use": "checks the first model's stored runs only; the failed model is never converted to cash"}


def main():
    record = C4.load_record()
    central = central_path()
    registered = json.loads((ROOT / "data" / "c4" / "scores.json").read_text())
    reference = json.loads(C4.C2_REFERENCE.read_text())
    results = json.loads((ROOT / "data" / "results.json").read_text())
    first, seeds = seed_robustness(record, reference, registered)
    d = C4.forward_draws(record=record, central=central)
    stored = json.loads((ROOT / "data" / "c4" / "rule_arithmetic.json").read_text())["distribution"]
    for y in C4.REPORT_YEARS:  # the forward draws are the registered ones
        s = -np.expm1(-C4.log_gap(d["stat_cpi"], d["stat_earnings"]))[:, HORIZON.index(y)]
        assert np.isclose(s.mean(), stored[str(y)]["share"]["mean"], rtol=0, atol=1e-12)
    design = U.sample_design(U.future_draws(U.PRIMARY_FORM, central, N_FIRST_MODEL), n_runs=160, include_zero=True)
    out = {
        "label": "diagnostics of a model that failed its registered test; no probability statement and no cash figure",
        "no_microsimulation": True,
        "registration_commit": C4.REGISTRATION_COMMIT,
        "rule_section_sha256": C4.RULE_SECTION_SHA256,
        "seed_robustness": seeds,
        "variogram_by_origin_b": variogram_by_origin(first, reference),
        "resolution": resolution(record, d),
        "drift": drift(record, central, d),
        "decomposition": decomposition(record, central, d, design, results),
        "gross_identity": gross_identity(results, central, design),
    }
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: out[k] for k in ("resolution", "gross_identity")}, indent=1))
    print(json.dumps({k: v for k, v in seeds.items() if k != "by_seed_set"}, indent=1))


if __name__ == "__main__":
    main()
