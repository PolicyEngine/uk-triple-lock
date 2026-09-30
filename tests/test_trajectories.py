"""Trajectory viewer: invariants of the methods, and checks on the committed results.

The committed file needs the private data to regenerate; these tests need none.
They check it against the code that produced it (source and input hashes),
against the rule arithmetic it records (differential and round-trip checks),
against the model series each run recorded (every one must follow its path),
and against the main results' central and Uncertainty-tab paths.
"""

import json
import math

import numpy as np
import pytest

from triple_lock import rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, OUTPUT, SWITCH_YEAR, TRIPLE_LOCK_FLOOR
from triple_lock.config import HORIZON as MAIN_HORIZON

hypothesis = pytest.importorskip("hypothesis")
pytest.importorskip("scipy")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from triple_lock import trajectories as T  # noqa: E402
from triple_lock import ts_monthly  # noqa: E402
from triple_lock.ts_backtest import statutory_outturns, switches  # noqa: E402
from triple_lock.ts_methods import (  # noqa: E402
    MIN_MARGINAL_DF,
    TiltError,
    band_depth_prerank,
    crps,
    fit_t_marginal,
    interval_hit,
    tilt,
    variogram_score,
)

HORIZON = T.TRAJECTORY_HORIZON
rates = st.floats(min_value=-0.03, max_value=0.12, allow_nan=False)
STEP = 10 ** -CENTRAL_RATE_DECIMALS


def ints(d):
    return {int(k): v for k, v in d.items()}


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
        assert bp[j] <= tl[j] + STEP + 1e-12


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON)))
def test_burnham_plan_is_the_smallest_rate_meeting_both_guarantees(pairs):
    """Minimality: after the switch each rate is on the 3 dp grid, meets both guarantees (at least
    max(CPI, 2.5%) rounded; level at least the earnings path) and 0.1 point less would break one.
    A rounded-up triple lock posing as the plan fails this whenever earnings pay more than the catch-up."""
    cpi = np.array([p[0] for p in pairs])
    earnings = np.array([p[1] for p in pairs])
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS)
        assert abs(bp[j] / STEP - round(bp[j] / STEP)) < 1e-6, "not a 3 dp rate"
        assert bp[j] >= floor - 1e-12 and level * (1 + bp[j]) >= anchor * (1 - 1e-12)
        lower = bp[j] - STEP
        assert lower < floor - 1e-12 or level * (1 + lower) < anchor * (1 - 1e-12), "a smaller rate would do"
        level *= 1 + bp[j]


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON)),
       st.sampled_from([CENTRAL_RATE_DECIMALS, None]))
def test_rate_sources_name_the_binding_input(pairs, decimals):
    cpi = {y - 1: p[0] for y, p in zip(HORIZON, pairs)}
    earnings = {y - 1: p[1] for y, p in zip(HORIZON, pairs)}
    r = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals) for p in T.POLICIES}
    src = T.rate_sources(cpi, earnings, r, HORIZON, decimals)
    for y in HORIZON:
        c, e = cpi[y - 1], earnings[y - 1]
        chosen = {"earnings": e, "cpi": c, "floor": TRIPLE_LOCK_FLOOR}[src["triple_lock"][y]]
        assert chosen == max(c, e, TRIPLE_LOCK_FLOOR)
        if y < SWITCH_YEAR:
            assert src["burnham_2030"][y] == "triple_lock"
        else:
            floor = max(c, TRIPLE_LOCK_FLOOR)
            floor = round(floor, decimals) if decimals is not None else floor
            assert (src["burnham_2030"][y] == "earnings_path") == (r["burnham_2030"][y] > floor + 1e-12)


# ── Calibration, selection and score invariants ─────────────────────────


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


def test_tilt_raises_when_the_target_is_out_of_reach():
    paths = np.random.default_rng(1).uniform(0, 1, size=(400, 2, 2))
    with pytest.raises(TiltError):
        tilt(paths, np.full((2, 2), 2.0))


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


def test_band_depth_pit_is_undefined_for_a_point_forecast():
    with pytest.raises(ValueError):
        band_depth_prerank(np.zeros((1, 4)), np.ones(4))


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 10_000), st.floats(0.01, 1000))
def test_interval_hit_ignores_the_scale_of_the_weights(seed, scale):
    rng = np.random.default_rng(seed)
    x, w, y = rng.normal(size=50), rng.uniform(0.1, 1, size=50), rng.normal()
    assert interval_hit(x, y, w=w * scale) == interval_hit(x, y, w=w / w.sum())


def test_switches_do_not_count_a_tie_as_a_reversal():
    # earnings - CPI: +, 0, + (a tie keeps the lead) and +, -, + (two switches)
    tie = np.array([[[0.02, 0.03], [0.02, 0.02], [0.02, 0.04]]])
    flip = np.array([[[0.02, 0.03], [0.03, 0.02], [0.02, 0.04]]])
    assert switches(tie)[0] == 0 and switches(flip)[0] == 2


def test_weighted_cdf_position_gives_ties_one_position():
    x = np.array([1.0, 2.0, 2.0, 3.0])
    pos = T.weighted_cdf_position(x, np.array([1.0, 1.0, 1.0, 1.0]))
    assert pos.tolist() == [0.125, 0.5, 0.5, 0.875]


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.floats(1e-3, 1e3))
def test_select_draws_picks_inside_the_band_and_ignores_units(seed, scale):
    rng = np.random.default_rng(seed)
    paths = rng.normal(size=(4000, 3, 2))
    weights = rng.uniform(0.5, 1.5, size=4000)
    weights /= weights.sum()
    gap = paths[:, :, 1].sum(axis=1) + 0.1 * rng.normal(size=4000)
    picks = T.select_draws(paths, weights, gap)
    pos = T.weighted_cdf_position(gap, weights)
    for pick in picks:
        assert abs(pos[pick["draw"]] - pick["quantile"]) <= T.BAND
    rescaled = paths.copy()
    rescaled[:, :, 0] *= scale  # standardised distance: a series' units cannot change the pick
    assert [p["draw"] for p in T.select_draws(rescaled, weights, gap)] == [p["draw"] for p in picks]


def test_select_draws_refuses_an_empty_band():
    gap = np.array([0.0, 1.0])
    with pytest.raises(ValueError):
        T.select_draws(np.zeros((2, 1, 2)), np.array([0.5, 0.5]), gap, quantiles=(0.5,), band=0.1)


def test_bic_compares_every_lag_order_on_the_same_rows():
    months, cpi, awe, _ = ts_monthly.levels()
    model = ts_monthly.fit(months, cpi, awe)
    crit = model["criterion"]
    assert len({c["n"] for c in crit}) == 1
    assert model["p"] == min(crit, key=lambda c: c["bic"])["p"]


def test_t_marginals_are_bounded():
    heavy = np.random.default_rng(4).standard_t(1.5, size=3000)
    assert fit_t_marginal(heavy)[0] == pytest.approx(MIN_MARGINAL_DF)
    light = np.random.default_rng(5).standard_t(12, size=20000)
    assert fit_t_marginal(light)[0] > MIN_MARGINAL_DF


# ── The committed results file ──────────────────────────────────────────


@pytest.fixture(scope="module")
def tdata():
    return json.loads(T.TRAJECTORY_OUTPUT.read_text())


@pytest.fixture(scope="module")
def main():
    return json.loads(OUTPUT.read_text())


def test_not_stale(tdata):
    for block, current in (("source_hashes", T.trajectory_source_hashes()), ("input_hashes", T.input_hashes())):
        recorded = tdata["provenance"][block]
        changed = [k for k in current if recorded.get(k) != current[k]]
        assert set(recorded) == set(current) and not changed, (
            f"{changed} changed since trajectory_results.json was generated — rerun `python -m triple_lock.trajectories`")


def test_built_from_a_clean_tree(tdata):
    assert tdata["provenance"]["git_dirty"] is False


def test_dashboard_copy_matches(tdata):
    assert json.loads(T.TRAJECTORY_DASHBOARD_COPY.read_text()) == tdata


def test_horizon_reaches_2039_40(tdata):
    assert tdata["horizon"] == HORIZON and HORIZON[-1] == 2039
    for t in tdata["trajectories"]:
        assert sorted(ints(t["saving_bn"])) == HORIZON, t["id"]


def test_rates_follow_the_rules_from_the_recorded_inputs(tdata):
    for t in tdata["trajectories"]:
        cpi, earnings = ints(t["statutory"]["cpi"]), ints(t["statutory"]["earnings"])
        for p in T.POLICIES:
            expected = rules.uprating_path(p, cpi, earnings, HORIZON, decimals=t["rate_decimals"])
            assert ints(t["rates"][p]) == pytest.approx(expected, abs=1e-15), (t["id"], p)


def test_weekly_amounts_compound_the_rates(tdata, main):
    base = main["central"]["base_year_weekly"]["new_state_pension"]
    for t in tdata["trajectories"]:
        for p in T.POLICIES:
            expected = rules.level_path(base, ints(t["rates"][p]), HORIZON)
            assert ints(t["weekly"][p]["new_state_pension"]) == pytest.approx(expected, rel=1e-9)
            applied = ints(t["applied_new_state_pension"][p])
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
        final = t["saving_bn"][str(HORIZON[-1])]
        assert lh["income_change_excluding_bn"] + lh["contribution_bn"] == pytest.approx(final["household_income_change"], abs=1e-6)
        assert 0 <= lh["gross_contribution_bn"] <= final["gross"] + 1e-9
        for v, change in lh["change_gbp"].items():
            assert change == pytest.approx(lh["amounts_gbp"]["burnham_2030"][v] - lh["amounts_gbp"]["triple_lock"][v], abs=1e-6)


def test_final_year_concentration_is_the_largest_household(tdata):
    """Differential: the per-year concentration record and the final-year decomposition agree."""
    for t in tdata["trajectories"]:
        c, lh = t["concentration_by_year"][str(HORIZON[-1])], t["largest_household"]
        assert sorted(ints(t["concentration_by_year"])) == HORIZON
        assert c["household_id"] == lh["household_id"], t["id"]
        assert c["contribution_bn"] == pytest.approx(lh["contribution_bn"], abs=1e-9)
        assert c["share_of_income_change"] == pytest.approx(lh["share_of_income_change"], abs=1e-9)


def test_macro_path_reached_the_model(tdata):
    for t in tdata["trajectories"]:
        for series in ("cpi", "earnings"):
            applied = ints(t["applied_growth"][series])
            assert {y: applied[y] for y in T.CALENDAR_YEARS} == pytest.approx(ints(t["calendar"][series]), abs=1e-12), t["id"]
    # Calendar 2026 is not a path input: the model's own value on every path.
    for series in ("cpi", "earnings"):
        assert len({t["applied_growth"][series]["2026"] for t in tdata["trajectories"]}) == 1


def _applied(t):
    return {s: ints(t["applied_growth"][s]) for s in ("cpi", "earnings")}


@pytest.mark.parametrize("name, series, lag", [(k, s, lag) for k, (_, s, lag) in T.PATH_PARAMETERS.items()])
def test_uprated_parameters_follow_each_path_every_year(tdata, name, series, lag):
    """Benefit uprating and the Pension Credit guarantee grow by the path's CPI the year before, a
    CPI-indexed threshold by its CPI the same year, in every year to 2039-40 (catches a frozen series)."""
    for t in tdata["trajectories"]:
        growth = ints(t["path_following"][name]["growth"])
        cal = _applied(t)[series]
        for y in HORIZON:
            assert growth[y] == pytest.approx(cal[y - lag], abs=T.PATH_GROWTH_TOL), (t["id"], name, y)


def test_benefit_uprating_is_not_stuck_after_2029(tdata):
    """The upstream bug: lagged CPI stopped in 2029, so later years all grew at the path's 2028 CPI."""
    for t in tdata["trajectories"]:
        growth = ints(t["path_following"]["benefit_uprating_cpi"]["growth"])
        cal = _applied(t)["cpi"]
        if len({round(cal[y], 6) for y in range(2029, 2039)}) > 1:
            assert len({round(growth[y], 5) for y in range(2030, 2040)}) > 1, t["id"]


def test_employment_income_follows_each_path_every_year(tdata):
    for t in tdata["trajectories"]:
        growth = ints(t["path_following"]["employment_income"]["growth"])
        cal = _applied(t)["earnings"]
        for y in HORIZON:
            assert growth[y] == pytest.approx(cal[y], abs=T.PATH_GROWTH_TOL), (t["id"], y)


def test_the_models_own_triple_lock_follows_each_path(tdata):
    """Derived from the unreformed simulation on each path, not from the inputs we sent it."""
    for t in tdata["trajectories"]:
        pf, cal = t["path_following"], _applied(t)
        rate = ints(pf["model_triple_lock"]["rate"])
        for y in HORIZON:
            assert rate[y] == round(max(cal["earnings"][y - 1], cal["cpi"][y - 1], TRIPLE_LOCK_FLOOR), 3), (t["id"], y)
        nsp = ints(pf["model_new_state_pension"]["weekly"])
        expected = rules.level_path(nsp[HORIZON[0] - 1], rate, HORIZON)
        for y in HORIZON:
            assert nsp[y] == pytest.approx(expected[y], rel=T.MODEL_AMOUNT_REL_TOL), (t["id"], y)


def test_what_the_docs_say_does_not_move_does_not(tdata):
    ts = tdata["trajectories"]
    for v in T.NOT_MOVING:
        for t in ts[1:]:
            assert ints(t["not_moving"][v]) == pytest.approx(ints(ts[0]["not_moving"][v]), abs=1e-9), (t["id"], v)
    # Rents and council tax stop at their 2030 amounts (the survey data are extended to 2030).
    for v in ("rent", "council_tax"):
        assert all(abs(g) < 1e-12 for y, g in ints(ts[0]["not_moving"][v]).items() if y > 2030)


def test_private_pension_income_moves_with_the_path(tdata):
    by_id = {t["id"]: ints(t["also_moving"]["private_pension_income"]) for t in tdata["trajectories"]}
    central = by_id.pop("central")
    for tid, growth in by_id.items():
        assert any(abs(growth[y] - central[y]) > 1e-6 for y in HORIZON), tid


def test_flat_rate_pensions_scale_with_the_flat_rates(tdata):
    """No data-year denominator moves in the forward runs: every person's basic or new State Pension
    under the Burnham plan is theirs under the triple lock times the ratio of the flat rates."""
    for t in tdata["trajectories"]:
        assert t["checks"]["max_proportionality_error_gbp"] <= T.PROPORTIONALITY_TOL_GBP, t["id"]
        assert all(v == 0 for v in t["checks"]["employer_ni_incidence_bn"].values()), t["id"]


def test_central_path_matches_the_main_results(tdata, main):
    """Differential: the same central path through the same model gives the main results to 2034-35."""
    central = next(t for t in tdata["trajectories"] if t["id"] == "central")
    for y in map(str, MAIN_HORIZON):
        cost = main["central"]["cost_vs_triple_lock_bn"]["burnham_2030"]
        assert central["saving_bn"][y]["gross"] == pytest.approx(-cost["gross"][y], abs=0.006)
        assert central["saving_bn"][y]["net"] == pytest.approx(-cost["net"][y], abs=0.006)
        for p in T.POLICIES:
            assert central["weekly"][p]["new_state_pension"][y] == pytest.approx(main["central"]["full_state_pension_weekly"][p][y], abs=0.006)


def test_uncertainty_tab_paths_match_that_tab(tdata, main):
    """Differential: unrounded rates on the Uncertainty tab's own draws equal the rates that tab computed."""
    for q in ("p50", "p90"):
        t = next(t for t in tdata["trajectories"] if t["id"] == f"uncertainty_tab_{q}")
        rep = main["uncertainty"]["representative_paths"][q]
        assert t["rate_decimals"] is None
        for p in T.POLICIES:
            for y in MAIN_HORIZON:
                assert t["rates"][p][str(y)] == pytest.approx(rep["uprating"][p][str(y)], abs=1e-12), (q, p, y)


def test_model_paths_are_reproducible(tdata, main):
    """Differential: regenerating the specs from the recorded central path gives the committed paths,
    selections and model diagnostics."""
    central = next(t for t in tdata["trajectories"] if t["id"] == "central")
    cc = {2026: central["statutory"]["cpi"]["2026"]} | ints(central["calendar"]["cpi"])
    ce = {2026: central["statutory"]["earnings"]["2026"]} | ints(central["calendar"]["earnings"])
    base = main["central"]["base_year_weekly"]["new_state_pension"]
    specs, models = T.forward_specs(cc, ce, base, main)
    by_id = {s["id"]: s for s in specs}
    assert [t["id"] for t in tdata["trajectories"]] == [s["id"] for s in specs]
    for t in tdata["trajectories"]:
        s = by_id[t["id"]]
        for key in ("cpi", "earnings"):
            assert ints(t["statutory"][key]) == pytest.approx(s[f"statutory_{key}"], abs=1e-12), (t["id"], key)
            assert ints(t["calendar"][key]) == pytest.approx(s[key], abs=1e-12), (t["id"], key)
        assert t.get("selection") == s.get("selection"), t["id"]
    assert json.loads(json.dumps(models, default=float)) == tdata["models"]


def test_the_path_model_has_the_lightest_deflation_tail(tdata):
    """Why the monthly-model paths use bootstrap shocks: the run variant puts no more weight on
    September CPI below -1% and -3% than any variant not run."""
    models = tdata["models"]
    run = [m for m, v in models.items() if v["runs_paths"]]
    assert len(run) == 1
    for other, v in models.items():
        for threshold in T.DEFLATION_THRESHOLDS:
            assert models[run[0]]["september_cpi_below"][threshold]["paths"] <= v["september_cpi_below"][threshold]["paths"]


def test_gap_statistics_are_reproducible(tdata):
    assert json.loads(json.dumps(T.gap_statistics(), default=float)) == tdata["gap_statistics"]


def test_statutory_backtest_reports_both_treatments_of_april_2022(tdata):
    bt = tdata["backtest"]["statutory"]["treatments"]
    assert set(bt) == {"published", "suspended"}
    c21, e21 = statutory_outturns()[2021]
    assert statutory_outturns(suspend_2022=True)[2021] == (c21, c21)
    for t, block in bt.items():
        for m in block["chronological"]["methods"].values():
            assert 0 <= m["burnham_2030_inside"] <= m["n_origins"]
            assert 1 <= m["min_draws"] <= m["max_draws"]
        assert block["chronological"]["methods"]["obr_point"]["path_inside_80_pct"] is None


def test_history_counterfactual_is_reproducible(tdata):
    cpi, earnings = T.history_inputs()
    for g in tdata["history"]["groups"]:
        cf = T.history_counterfactual(g["switch_years"][0], cpi, earnings)
        assert ints(g["level_ratio"]) == pytest.approx(cf["level_ratio"], abs=1e-12)
        if g["changes_anything"]:
            m = g["model_years"]
            for y, ratio in ((str(y), cf["level_ratio"][y]) for y in tdata["history"]["model_years"]):
                assert m["counterfactual_weekly"]["new_state_pension"][y] == pytest.approx(
                    m["actual_weekly"]["new_state_pension"][y] * ratio, rel=1e-12)
                assert m["applied_new_state_pension"][y] == pytest.approx(m["counterfactual_weekly"]["new_state_pension"][y], rel=1e-6)
        else:
            assert g["model_years"] is None and np.allclose(list(g["level_ratio"].values()), 1)


def test_past_year_pensions_scale_by_the_level_ratio(tdata):
    """H1: every person's counterfactual basic or new State Pension is their actual one times the
    level ratio, checked person by person in each run; the survey-year denominator stays at actual law."""
    for g in tdata["history"]["groups"]:
        m = g["model_years"]
        if not m:
            continue
        assert m["max_proportionality_error_gbp"] <= T.PROPORTIONALITY_TOL_GBP, g["switch_years"]
        for n, amount in m["data_year_denominator_weekly"].items():
            assert amount == m["actual_weekly"][n][str(m["data_year"])]


def test_actual_rises_come_from_the_models_pension_amounts(tdata):
    rise = ints(tdata["history"]["actual_rise"])
    weekly = ints(tdata["history"]["actual_weekly"]["basic_state_pension"])
    for y in range(min(weekly) + 1, max(weekly) + 1):
        assert rise[y] == round(weekly[y] / weekly[y - 1] - 1, 3)
    assert not any(math.isnan(v) for v in rise.values())


# ── The model-horizon extension (needs policyengine-uk, no data) ────────


def test_model_horizon_extension_reaches_2041():
    """Built the way a Scenario builds its parameters (reset, change, process), with a CPI path the
    default does not have, every extended series follows it to 2041."""
    pytest.importorskip("policyengine_uk")
    from policyengine_uk.tax_benefit_system import CountryTaxBenefitSystem

    from triple_lock import model_horizon

    path = {y: 0.02 + 0.001 * (y - 2030) for y in range(2030, 2042)}
    with model_horizon.installed():
        system = CountryTaxBenefitSystem()
        system.reset_parameters()
        obr = system.parameters.gov.economic_assumptions.yoy_growth.obr
        for y, g in path.items():
            obr.consumer_price_index.update(period=f"year:{y}-01-01:1", value=g)
        system.process_parameters()
        p = system.parameters
        obr = p.gov.economic_assumptions.yoy_growth.obr
        for y in range(2031, 2042):
            assert obr.lagged_cpi(f"{y}-06-01") == pytest.approx(path[y - 1]), y
            assert obr.lagged_average_earnings(f"{y}-06-01") == pytest.approx(obr.average_earnings(f"{y - 1}-06-01")), y
            assert p.gov.economic_assumptions.yoy_growth.triple_lock(f"{y}-06-01") == round(
                max(obr.average_earnings(f"{y - 1}-06-01"), path[y - 1], 0.025), 3), y
