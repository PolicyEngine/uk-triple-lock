"""The committed results file, checked against the code that produced it (no private data needed).

* Staleness: source, engine and input hashes recorded at build time equal today's.
* Every path's savings reconcile with its own model totals, and its rates with the rules applied to its recorded
  inputs (a differential check between the engine's output and the pure rule arithmetic).
* Every run recorded that the model followed its path.
* The expected value recomputes from the per-path records (the stratified estimator applied to what was run).
* Invariants: a saving is never negative beyond rounding; identical rates give exactly zero; household tables sum to
  the net change; the figures the dashboard prints are in the file.
"""

import json

import numpy as np
import pytest

from triple_lock import engine, expected_value, rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, DASHBOARD_COPY, FINAL_YEAR, HORIZON, OUTPUT, SWITCH_YEAR
from triple_lock.pipeline import hashes

TOL_BN = 1e-9


def ints(d):
    return {int(k): v for k, v in d.items()}


@pytest.fixture(scope="module")
def results():
    if not OUTPUT.exists():
        pytest.fail(f"{OUTPUT} is missing: run the build")
    return json.loads(OUTPUT.read_text())


@pytest.fixture(scope="module")
def runs(results):
    """Every full path run in the file: the central path and the trajectories."""
    return [("central", results["central"]["run"])] + [(t["id"], t) for t in results["trajectories"]["paths"]]


# ── Provenance ──────────────────────────────────────────────────────────


def test_not_stale(results):
    now = hashes()
    p = results["provenance"]
    assert p["source_hashes"] == now["source_hashes"], "sources changed since the build: rebuild"
    assert p["input_hashes"] == now["input_hashes"], "inputs changed since the build: rebuild"
    assert p["engine_hashes"] == engine.engine_hashes()


def test_built_from_a_clean_tree(results):
    assert results["provenance"]["git_dirty"] is False


def test_dashboard_copy_matches(results):
    assert json.loads(DASHBOARD_COPY.read_text()) == results


def test_not_a_sample(results):
    assert results["sample"] is False


# ── Every path run ──────────────────────────────────────────────────────


def test_rates_follow_the_rules_from_the_recorded_inputs(runs):
    for name, r in runs:
        cpi, earnings = ints(r["statutory"]["cpi"]), ints(r["statutory"]["earnings"])
        for p in ("triple_lock", "burnham_2030"):
            expected = rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS)
            assert ints(r["rates"][p]) == pytest.approx(expected, abs=1e-12), name


def test_weekly_amounts_compound_the_rates(results, runs):
    base = results["base_year_weekly"]
    for name, r in runs:
        for p in ("triple_lock", "burnham_2030"):
            lv = rules.level_path(base["new_state_pension"], ints(r["rates"][p]), HORIZON)
            got = ints(r["weekly"][p]["new_state_pension"])
            assert all(got[y] == pytest.approx(lv[y], abs=0.006) for y in HORIZON), name


def test_savings_reconcile_with_the_model_totals(runs):
    for name, r in runs:
        tl, bp = r["totals_bn"]["triple_lock"], r["totals_bn"]["burnham_2030"]
        for y in HORIZON:
            s, a, b = r["saving_bn"][str(y)], tl[str(y)], bp[str(y)]
            assert s["gross"] == pytest.approx(a["state_pension_flat_rate"] - b["state_pension_flat_rate"], abs=TOL_BN)
            assert s["net"] == pytest.approx(b["gov_balance"] - a["gov_balance"], abs=TOL_BN)
            assert a["state_pension_flat_rate"] == pytest.approx(a["basic_state_pension"] + a["new_state_pension"], abs=1e-6)


def test_no_saving_before_the_switch(runs):
    for name, r in runs:
        for y in HORIZON:
            if y < SWITCH_YEAR:
                assert r["saving_bn"][str(y)]["gross"] == 0.0 and r["saving_bn"][str(y)]["net"] == 0.0, name


def test_gross_saving_is_never_negative_beyond_rounding(runs):
    """The plan never pays more than the triple lock except by rounding its top-up up (0.1 point at most)."""
    for name, r in runs:
        for y in HORIZON:
            gross = r["saving_bn"][str(y)]["gross"]
            bp = r["totals_bn"]["burnham_2030"][str(y)]["state_pension_flat_rate"]
            assert gross >= -0.0011 * bp * (y - SWITCH_YEAR + 1), (name, y)


def test_every_run_followed_its_path(runs):
    for name, r in runs:
        f = r["path_following"]
        for key in engine.PATH_PARAMETERS:
            assert f[key]["max_abs_error"] <= engine.PATH_GROWTH_TOL, (name, key)
        assert f["employment_income"]["max_abs_error"] <= engine.PATH_GROWTH_TOL, name
        assert f["model_triple_lock"]["max_abs_error"] <= 1e-12, name
        assert r["checks"]["max_proportionality_error_gbp"] <= engine.PROPORTIONALITY_TOL_GBP, name
        assert all(v == 0 for v in r["checks"]["employer_ni_incidence_bn"].values()), name


def test_benefit_uprating_is_not_stuck_after_2029(runs):
    """Without the horizon extension, CPI-linked benefits stop following the path after April 2029."""
    for name, r in runs:
        g = ints(r["path_following"]["benefit_uprating_cpi"]["growth"])
        assert all(abs(g[y]) > 1e-6 for y in HORIZON if y > 2029), name


@pytest.mark.parametrize("year_key", ["2034", str(FINAL_YEAR)])
def test_household_tables_sum_to_the_net_change(runs, year_key):
    for name, r in runs:
        change = r["saving_bn"][year_key]["household_income_change"]
        for key, rows in r["distribution"][year_key].items():
            if key == "households_affected":
                continue
            assert sum(row["total_bn"] for row in rows) == pytest.approx(change, abs=0.002 * len(rows)), (name, key)


def test_largest_household_is_the_largest(runs):
    for name, r in runs:
        lh, c = r["largest_household"], r["concentration_by_year"][str(FINAL_YEAR)]
        assert lh["household_id"] == c["household_id"] and lh["contribution_bn"] == pytest.approx(c["contribution_bn"]), name


# ── The central path ────────────────────────────────────────────────────


def test_central_run_is_the_central_path(results):
    path, run = results["central"]["path"], results["central"]["run"]
    assert ints(run["statutory"]["cpi"]) == pytest.approx(ints(path["statutory"]["cpi"]))
    assert ints(run["calendar"]["earnings"]) == pytest.approx(ints(path["calendar"]["earnings"]))
    central_traj = next(t for t in results["trajectories"]["paths"] if t["id"] == "central")
    assert central_traj["saving_bn"] == run["saving_bn"]  # the same cached job


# ── The expected value ──────────────────────────────────────────────────


def test_expected_value_recomputes_from_the_path_records(results):
    """Stratified estimator on the recorded paths (each counted as often as it was drawn) reproduces the estimates."""
    ev = results["expected_value"]
    W = {s["stratum"]: s["probability"] for s in ev["strata"]}
    for y in (str(SWITCH_YEAR + 1), str(FINAL_YEAR)):
        for o in ("gross", "net"):
            vals = {k: [] for k in W}
            for p in ev["paths"]:
                vals[p["stratum"]] += [p["saving_bn"]["primary"][y][o]] * p["times_drawn"]
            m, se = expected_value.stratified_mean(vals, W)
            assert m == pytest.approx(ev["estimates"]["primary"][o][y]["mean"], abs=1e-9)
            assert se == pytest.approx(ev["estimates"]["primary"][o][y]["se"], abs=1e-9)


def test_strata_probabilities_sum_to_one(results):
    ev = results["expected_value"]
    total = sum(s["probability"] for s in ev["strata"]) + ev["identical_rates"]["probability"]
    assert total == pytest.approx(1.0, abs=1e-9)
    assert all(s["paths"] >= expected_value.MIN_PER_STRATUM for s in ev["strata"])


def test_identical_rates_saved_exactly_nothing(results):
    check = results["expected_value"]["identical_rates"]["check_run"]
    assert check is None or check["largest_abs_saving_bn"] == 0.0


def test_paired_difference_recomputes_from_the_path_records(results):
    """Microcosm minus Enhanced FRS on the same paths, stratified: it reproduces the recorded difference and the
    Microcosm estimate."""
    ev = results["expected_value"]
    W = {s["stratum"]: s["probability"] for s in ev["strata"]}
    for y in (str(SWITCH_YEAR + 1), str(FINAL_YEAR)):
        for o in ("gross", "net"):
            diff, micro = {k: [] for k in W}, {k: [] for k in W}
            for p in ev["paths"]:
                n = p.get("times_drawn_sensitivity", 0)
                if n:
                    diff[p["stratum"]] += [p["saving_bn"]["sensitivity"][y][o] - p["saving_bn"]["primary"][y][o]] * n
                    micro[p["stratum"]] += [p["saving_bn"]["sensitivity"][y][o]] * n
            m, se = expected_value.stratified_mean(diff, W)
            assert m == pytest.approx(ev["paired_difference"][o][y]["mean"], abs=1e-9)
            assert se == pytest.approx(ev["paired_difference"][o][y]["se"], abs=1e-9)
            m, _ = expected_value.stratified_mean(micro, W)
            assert m == pytest.approx(ev["estimates"]["sensitivity"][o][y]["mean"], abs=1e-9)


def test_primary_calibration_matches_the_central_means(results):
    ev = results["expected_value"]
    c = ev["calibrations"][ev["primary"]]
    assert c["draws"] == "shifted" and c["ess"] == pytest.approx(ev["draws"]["n"])


def test_dashboard_prose_matches_the_backtest(results):
    """The Method tab says: the OBR point path misses by the most; the shift's bias is within its standard error;
    the dynamics tilt made the bias larger. Check each against the file."""
    s = results["expected_value"]["backtest"]["summary"]["suspended"]
    assert abs(s["obr_point"]["bias_pct_points"]) == max(abs(r["bias_pct_points"]) for r in s.values())
    assert abs(s["means_shift"]["bias_pct_points"]) <= s["means_shift"]["bias_se_independent"]
    assert abs(s["shift_dynamics"]["bias_pct_points"]) > abs(s["means_shift"]["bias_pct_points"])


def test_benchmarks_resolve(results):
    from triple_lock.benchmarks import resolve

    for b in results["benchmarks"]:
        assert resolve(results, b["our_metric"]) == b["our_value"]
