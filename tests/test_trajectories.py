"""Trajectory viewer: invariants of the methods, and checks on the committed results.

The committed file needs the private data to regenerate; these tests need none.
They check it against the code that produced it (source hashes), against the
rule arithmetic it records (differential and round-trip checks), and against the
main results' central path.
"""

import json

import numpy as np
import pytest

from triple_lock import rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, HORIZON, OUTPUT, SWITCH_YEAR, TRIPLE_LOCK_FLOOR

hypothesis = pytest.importorskip("hypothesis")
pytest.importorskip("scipy")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from triple_lock import trajectories as T  # noqa: E402
from triple_lock.ts_methods import band_depth_prerank, crps, tilt, variogram_score  # noqa: E402

rates = st.floats(min_value=-0.03, max_value=0.12, allow_nan=False)


# ── Rule invariants (for all inputs) ────────────────────────────────────


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON)))
def test_burnham_plan_invariants(pairs):
    """Burnham: triple lock before the switch; at least max(CPI, 2.5%) after; level never below
    its earnings path; above the triple lock only by rounding (at most 0.1pp in a year)."""
    cpi = np.array([p[0] for p in pairs])
    earnings = np.array([p[1] for p in pairs])
    tl = rules.rates_matrix("triple_lock", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            assert bp[j] == tl[j]
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS)
        assert bp[j] >= floor - 1e-12
        level *= 1 + bp[j]
        assert level >= anchor * (1 - 1e-12)
        assert bp[j] <= tl[j] + 10 ** -CENTRAL_RATE_DECIMALS + 1e-12


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON)))
def test_rate_sources_name_the_binding_input(pairs):
    cpi = {y - 1: p[0] for y, p in zip(HORIZON, pairs)}
    earnings = {y - 1: p[1] for y, p in zip(HORIZON, pairs)}
    r = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS) for p in T.POLICIES}
    src = T.rate_sources(cpi, earnings, r, HORIZON)
    for y in HORIZON:
        c, e = cpi[y - 1], earnings[y - 1]
        chosen = {"earnings": e, "cpi": c, "floor": TRIPLE_LOCK_FLOOR}[src["triple_lock"][y]]
        assert chosen == max(c, e, TRIPLE_LOCK_FLOOR)
        if y < SWITCH_YEAR:
            assert src["burnham_2030"][y] == "triple_lock"
        elif src["burnham_2030"][y] == "earnings_path":
            assert r["burnham_2030"][y] > round(max(c, TRIPLE_LOCK_FLOOR), CENTRAL_RATE_DECIMALS)


# ── Calibration and score invariants ────────────────────────────────────


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000), st.floats(-0.5, 0.5), st.floats(-0.5, 0.5))
def test_tilt_matches_target_means(seed, shift_c, shift_e):
    rng = np.random.default_rng(seed)
    paths = rng.normal(0.02, 0.015, size=(3000, 3, 2))
    target = paths.mean(axis=0) + np.array([shift_c, shift_e]) * paths.std(axis=0)
    w, info = tilt(paths, target)
    assert np.all(w >= 0) and abs(w.sum() - 1) < 1e-9
    assert np.allclose(np.tensordot(w, paths, axes=1), target, atol=1e-8)
    assert 1 <= info["ess"] <= len(paths) + 1e-6


def test_tilt_is_identity_at_the_sample_mean():
    paths = np.random.default_rng(0).normal(size=(500, 2, 2))
    w, info = tilt(paths, paths.mean(axis=0))
    assert np.allclose(w, 1 / 500) and info["ess"] == pytest.approx(500)


def test_crps_matches_the_normal_closed_form():
    x = np.random.default_rng(1).standard_normal(200_000)
    # CRPS(N(0,1), 0) = 2 phi(0) - 1/sqrt(pi) = 0.2337
    assert crps(x, 0.0) == pytest.approx(2 / np.sqrt(2 * np.pi) - 1 / np.sqrt(np.pi), abs=0.003)


def test_variogram_score_prefers_the_true_dependence():
    rng = np.random.default_rng(2)
    L = np.linalg.cholesky(np.array([[1, 0.9], [0.9, 1]]))
    right, wrong = [], []
    for _ in range(200):
        y = L @ rng.standard_normal(2)
        right.append(variogram_score(rng.standard_normal((2000, 2)) @ L.T, y))
        wrong.append(variogram_score(rng.standard_normal((2000, 2)), y))
    assert np.mean(right) < 0.5 * np.mean(wrong)


def test_band_depth_pit_is_uniform_for_a_calibrated_forecast():
    rng = np.random.default_rng(3)
    pits = [band_depth_prerank(rng.standard_normal((400, 4)), rng.standard_normal(4)) for _ in range(600)]
    assert abs(np.mean(pits) - 0.5) < 0.05
    assert abs(np.mean(np.array(pits) < 0.2) - 0.2) < 0.05


# ── The committed results file ──────────────────────────────────────────


@pytest.fixture(scope="module")
def tdata():
    return json.loads(T.TRAJECTORY_OUTPUT.read_text())


def test_not_stale(tdata):
    recorded = tdata["provenance"]["source_hashes"]
    current = T.trajectory_source_hashes()
    changed = [k for k in current if recorded.get(k) != current[k]]
    assert set(recorded) == set(current) and not changed, (
        f"{changed} changed since trajectory_results.json was generated — rerun `python -m triple_lock.trajectories`")


def test_dashboard_copy_matches(tdata):
    assert json.loads(T.TRAJECTORY_DASHBOARD_COPY.read_text()) == tdata


def test_rates_follow_the_rules_from_the_recorded_inputs(tdata):
    for t in tdata["trajectories"]:
        cpi = {int(k): v for k, v in t["statutory"]["cpi"].items()}
        earnings = {int(k): v for k, v in t["statutory"]["earnings"].items()}
        for p in T.POLICIES:
            expected = rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS)
            assert {int(k): v for k, v in t["rates"][p].items()} == pytest.approx(expected), (t["id"], p)


def test_weekly_amounts_compound_the_rates(tdata):
    main = json.loads(OUTPUT.read_text())
    base = main["central"]["base_year_weekly"]["new_state_pension"]
    for t in tdata["trajectories"]:
        for p in T.POLICIES:
            r = {int(k): v for k, v in t["rates"][p].items()}
            expected = rules.level_path(base, r, HORIZON)
            got = {int(k): v for k, v in t["weekly"][p]["new_state_pension"].items()}
            assert got == pytest.approx(expected, rel=1e-9)
            applied = {int(k): v for k, v in t["applied_new_state_pension"][p].items()}
            assert applied == pytest.approx(expected, rel=1e-6), (t["id"], p, "model did not take the rule's amounts")


def test_savings_reconcile_with_the_model_totals(tdata):
    for t in tdata["trajectories"]:
        tl, bp = t["totals_bn"]["triple_lock"], t["totals_bn"]["burnham_2030"]
        for y in map(str, HORIZON):
            s = t["saving_bn"][y]
            assert s["gross"] == pytest.approx(tl[y]["state_pension_flat_rate"] - bp[y]["state_pension_flat_rate"], abs=1e-9)
            assert s["net"] == pytest.approx(bp[y]["gov_balance"] - tl[y]["gov_balance"], abs=1e-9)
            assert abs(s["components"]["additional_state_pension"]) < 1e-9  # pinned
        lh = t["largest_household"]
        final = t["saving_bn"][str(HORIZON[-1])]["household_income_change"]
        assert lh["income_change_excluding_bn"] + lh["contribution_bn"] == pytest.approx(final, abs=1e-6)


def test_macro_path_reached_the_model(tdata):
    for t in tdata["trajectories"]:
        for series in ("cpi", "earnings"):
            assert t["applied_growth"][series] == pytest.approx(t["calendar"][series], abs=1e-9), t["id"]


def test_central_path_matches_the_main_results(tdata):
    main = json.loads(OUTPUT.read_text())
    central = next(t for t in tdata["trajectories"] if t["id"] == "central")
    for y in map(str, HORIZON):
        assert central["saving_bn"][y]["gross"] == pytest.approx(-main["central"]["cost_vs_triple_lock_bn"]["burnham_2030"]["gross"][y], abs=0.006)
        assert central["saving_bn"][y]["net"] == pytest.approx(-main["central"]["cost_vs_triple_lock_bn"]["burnham_2030"]["net"][y], abs=0.006)
        for p in T.POLICIES:
            assert central["weekly"][p]["new_state_pension"][y] == pytest.approx(main["central"]["full_state_pension_weekly"][p][y], abs=0.006)


def test_model_paths_are_reproducible(tdata):
    """Differential: regenerating the specs from the recorded central path gives the committed paths."""
    main = json.loads(OUTPUT.read_text())
    central = next(t for t in tdata["trajectories"] if t["id"] == "central")
    cc = {int(k): v for k, v in central["calendar"]["cpi"].items()}
    ce = {int(k): v for k, v in central["calendar"]["earnings"].items()}
    base = main["central"]["base_year_weekly"]["new_state_pension"]
    specs, _ = T.forward_specs(cc, ce, {}, base, main)
    by_id = {s["id"]: s for s in specs}
    for t in tdata["trajectories"]:
        assert t["id"] in by_id
        if "statutory_cpi" in by_id[t["id"]]:
            got = {int(k): v for k, v in t["statutory"]["cpi"].items()}
            assert got == pytest.approx(by_id[t["id"]]["statutory_cpi"], abs=1e-12)


def test_history_counterfactual_is_reproducible(tdata):
    cpi, earnings = T.history_inputs()
    for g in tdata["history"]["groups"]:
        cf = T.history_counterfactual(g["switch_years"][0], cpi, earnings)
        assert {int(k): v for k, v in g["level_ratio"].items()} == pytest.approx(cf["level_ratio"], abs=1e-12)
        if g["changes_anything"]:
            m = g["model_years"]
            for y, ratio in ((str(y), cf["level_ratio"][y]) for y in tdata["history"]["model_years"]):
                assert m["counterfactual_weekly"]["new_state_pension"][y] == pytest.approx(
                    m["actual_weekly"]["new_state_pension"][y] * ratio, rel=1e-12)
                assert m["applied_new_state_pension"][y] == pytest.approx(m["counterfactual_weekly"]["new_state_pension"][y], rel=1e-6)
        else:
            assert g["model_years"] is None and np.allclose(list(g["level_ratio"].values()), 1)
