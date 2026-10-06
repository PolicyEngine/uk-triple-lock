"""The expected value's calibration, sampling and estimators (no PolicyEngine needed)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import expected_value as EV
from triple_lock.central import central_path
from triple_lock.config import CALENDAR_YEARS
from triple_lock.ts_backtest import switches


def test_ageing_estimates_do_not_require_or_recreate_private_record_diagnostics():
    from triple_lock.config import HORIZON

    run = {"saving_bn": {y: {"gross": 2., "net": 1., "components": {"pension_credit": .25}} for y in HORIZON},
           "totals_bn": {"triple_lock": {y: {"state_pension_flat_rate": 200.} for y in HORIZON}},
           "households_affected": {y: {"losing_pct": 20.} for y in HORIZON},
           "record_diagnostics_suppressed": True}
    outputs = EV._outputs(run)
    assert outputs["gross"] == {y: 2. for y in HORIZON}
    assert outputs["gross_share_flat_rate_spending_pct"] == {y: 1. for y in HORIZON}
    assert "largest_record_bn" not in outputs
    assert "net_excluding_largest_record" not in outputs


def synthetic(seed, n=20_000):
    """Weights, a gap with an exact-zero mass, and an outcome that rises with the gap plus noise."""
    rng = np.random.default_rng(seed)
    w = rng.gamma(2.0, size=n)
    w /= w.sum()
    gap = np.maximum(rng.normal(3, 4, size=n), 0)
    identical = rng.uniform(size=n) < 0.05
    gap[identical] = 0
    y = np.where(identical, 0.0, 0.5 * gap + rng.normal(0, 1, size=n) * (1 + gap / 4))
    return w, gap, identical, y


def estimate(w, strata, alloc, y, seed):
    sample = EV.draw_sample(w, strata, alloc, seed)
    W = {k: float(w[strata == k].sum()) for k in alloc}
    return EV.stratified_mean({k: y[idx] for k, idx in sample.items()}, W), sample, W


def test_strata_have_equal_probability_and_zero_holds_identical_draws():
    w, gap, identical, _ = synthetic(0)
    strata = EV.stratify(w, gap, identical, 10)
    assert (strata[identical] == 0).all() and (strata[~identical] > 0).all()
    mass = np.array([w[strata == k].sum() for k in range(1, 11)])
    assert np.allclose(mass, w[~identical].sum() / 10, rtol=0.02)
    # strata are ordered on the gap
    assert all(gap[strata == k].max() <= gap[strata == k + 1].min() + 1e-12 for k in range(1, 10))


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 10_000), st.integers(20, 400))
def test_allocation_sums_to_the_sample_and_keeps_the_minimum(seed, n_paths):
    w, gap, identical, _ = synthetic(seed, 5000)
    strata = EV.stratify(w, gap, identical, 10)
    alloc = EV.allocate(w, gap, strata, n_paths)
    assert sum(alloc.values()) == n_paths
    assert min(alloc.values()) >= EV.MIN_PER_STRATUM


def test_stratified_estimator_is_unbiased_and_its_standard_error_covers():
    """Over repeated samples the estimate averages to the weighted mean and +-1.96 SE covers it about 95% of the time."""
    w, gap, identical, y = synthetic(1)
    truth = float(w @ y)  # identical draws contribute exactly zero, as in the build
    strata = EV.stratify(w, gap, identical, 10)
    alloc = EV.allocate(w, gap, strata, 120)
    est, cover = [], []
    for s in range(400):
        (m, se), _, _ = estimate(w, strata, alloc, y, s)
        est.append(m)
        cover.append(abs(m - truth) <= 1.96 * se)
    est = np.array(est)
    assert abs(est.mean() - truth) < 3 * est.std() / np.sqrt(len(est))
    assert 0.90 <= np.mean(cover) <= 0.99
    assert est.std() == pytest.approx(np.mean([estimate(w, strata, alloc, y, s)[0][1] for s in range(50)]), rel=0.25)


def test_reweighting_estimates_another_calibration_of_the_same_draws():
    """sum_h W_h mean_h(r y), r = w'/w, is unbiased for the w'-weighted mean from a sample drawn under w."""
    w, gap, identical, y = synthetic(2)
    other = w * np.exp(0.1 * gap)
    other /= other.sum()
    truth = float(other @ y)
    strata = EV.stratify(w, gap, identical, 10)
    alloc = EV.allocate(w, gap, strata, 150)
    est = []
    for s in range(300):
        sample = EV.draw_sample(w, strata, alloc, s)
        W = {k: float(w[strata == k].sum()) for k in alloc}
        m, _ = EV.stratified_mean({k: [y[i] * other[i] / w[i] for i in idx] for k, idx in sample.items()}, W)
        est.append(m)
    est = np.array(est)
    assert abs(est.mean() - truth) < 3 * est.std() / np.sqrt(len(est))


def test_stratified_mean_refuses_a_stratum_with_one_run():
    with pytest.raises(ValueError):
        EV.stratified_mean({1: [1.0], 2: [1.0, 2.0]}, {1: 0.5, 2: 0.5})


def test_moments_match_their_definitions():
    rng = np.random.default_rng(3)
    c, e = rng.normal(0.02, 0.01, (50, 13)), rng.normal(0.03, 0.01, (50, 13))
    m = EV.moments(c, e)
    assert np.allclose(m["gap_variance"], np.var(100 * (e - c), axis=1, ddof=1))
    assert np.allclose(m["switch_rate"], switches(np.stack([c, e], axis=2)) / 12)
    assert np.allclose(m["floor_share"], (np.maximum(c, e) < 0.025).mean(axis=1))


def test_history_treatments():
    """covid_excluded drops 2020-21; suspended sets 2021 earnings to CPI; published keeps both."""
    y_pub, c_pub, e_pub = EV.statutory_history(2001, 2025, "published")
    y_ex, _, _ = EV.statutory_history(2001, 2025, "covid_excluded")
    y_sus, c_sus, e_sus = EV.statutory_history(2001, 2025, "suspended")
    assert y_pub == y_sus == list(range(2001, 2026))
    assert y_ex == [y for y in y_pub if y not in (2020, 2021)]
    i = y_pub.index(2021)
    assert e_sus[i] == c_sus[i] and e_pub[i] != c_pub[i]
    with pytest.raises(ValueError):
        EV.statutory_history(2001, 2025, "invented")


@pytest.fixture(scope="module")
def cal():
    c = central_path()
    d = EV.draws(c, n=8000)
    targets = {(wn, t): EV.history_targets(*EV.HISTORY_WINDOWS[wn], t) for wn in EV.HISTORY_WINDOWS
               for t in EV.TREATMENTS}
    return c, d, EV.calibrations(d, targets)


def test_shifted_draws_match_the_central_calendar_means(cal):
    c, d, _ = cal
    target = np.array([[c["calendar"]["cpi"][y], c["calendar"]["earnings"][y]] for y in CALENDAR_YEARS])
    assert np.abs(d["shifted"]["calendar"].mean(axis=0) - target).max() < 1e-11
    assert np.abs(d["raw"]["calendar"].mean(axis=0) - target).max() > 1e-3  # the model's own means differ


def test_calibrations_hit_their_targets(cal):
    _, d, cals = cal
    assert all(c.get("weights") is not None for c in cals.values()), [n for n, c in cals.items() if c.get("weights") is None]
    assert cals[EV.PRIMARY]["draws"] == "shifted" and cals[EV.PRIMARY]["ess"] == pytest.approx(len(d["shifted"]["stat_cpi"]))
    for name, c in cals.items():
        if c.get("weights") is None:
            continue
        for k in ("gap_variance", "switch_rate", "floor_share"):
            if k in c["targeted"]:
                assert c["achieved"][k] == pytest.approx(c["targets"][k], abs=1e-4)
        if "calendar_means" in c["targeted"]:
            s = d[c["draws"]]
            target = d["target"]
            assert np.abs(np.tensordot(c["weights"], s["calendar"], axes=1) - target).max() < 1e-8


def test_path_spec_round_trips(cal):
    _, d, _ = cal
    spec = EV.path_spec(d["shifted"], 17, "populace_uk_2023")
    assert spec["dataset"] == "populace_uk_2023"
    assert [spec["statutory_cpi"][y] for y in sorted(spec["statutory_cpi"])] == d["shifted"]["stat_cpi"][17].tolist()
    assert [spec["earnings"][y] for y in CALENDAR_YEARS] == d["shifted"]["calendar"][17, :, 1].tolist()


def test_switch_rate_target_counts_consecutive_years_only():
    """With 2020-21 left out, 2019 and 2022 are not a consecutive pair."""
    t = EV.history_targets(2001, 2025, "covid_excluded")
    assert t["n_years"] == 23 and t["consecutive_pairs"] == 21
    t_pub = EV.history_targets(2001, 2025, "published")
    assert t_pub["consecutive_pairs"] == 24


def test_estimator_on_the_real_sample_design(cal):
    """The build's design (shifted draws, strata on the 2039-40 gap, Neyman allocation), at 8,000 draws and 120
    paths to keep the test quick, is unbiased and its +-1.96 SE interval covers at least 85% for the weekly gap in
    2033-34 and 2039-40."""
    c, d, cals = cal
    base = 1.0  # rule-level checks do not depend on the pension cash amount
    ds, w = d["shifted"], cals[EV.PRIMARY]["weights"]
    levels, rates = EV.rule_levels(ds["stat_cpi"], ds["stat_earnings"], base)
    gap = levels["triple_lock"] - levels["burnham_2030"]
    identical = np.all(rates["triple_lock"] == rates["burnham_2030"], axis=1)
    strata = EV.stratify(w, gap[:, -1], identical)
    alloc = EV.allocate(w, gap[:, -1], strata, 120)
    W = {k: float(w[strata == k].sum()) for k in alloc}
    for j in (6, 12):  # 2033-34 and 2039-40
        y, truth = gap[:, j], float(w @ gap[:, j])
        est, cover = [], []
        for s in range(200):
            sample = EV.draw_sample(w, strata, alloc, s)
            m, se = EV.stratified_mean({k: y[idx] for k, idx in sample.items()}, W)
            est.append(m)
            cover.append(abs(m - truth) <= 1.96 * se)
        est = np.array(est)
        assert abs(est.mean() - truth) < 3 * est.std() / np.sqrt(len(est)) + 1e-9
        assert np.mean(cover) >= 0.85


def test_backtest_gap_rounds_like_the_fiscal_runs():
    """The backtests score the policy gap with the fiscal runs' 0.1-point rounding (María's review of #10): on the
    random path's April 2030-33 inputs the four-uprating gap is 0.3846% rounded, against 0.5263% unrounded."""
    import json

    import numpy as np

    from triple_lock.config import REPO
    from triple_lock.ts_backtest import gap_pct

    data = json.loads((REPO / "data" / "results.json").read_text())
    st = next(t for t in data["trajectories"]["paths"] if t["id"] == "random")["statutory"]
    x = np.array([[[st["cpi"][y], st["earnings"][y]] for y in ("2029", "2030", "2031", "2032")]])
    assert gap_pct(x)["burnham_2030"][0] == pytest.approx(0.384615, abs=1e-5)
    assert gap_pct(x, decimals=None)["burnham_2030"][0] == pytest.approx(0.526263, abs=1e-5)
