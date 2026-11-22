"""C4: the frozen rule, and the forecast-error path model on synthetic records (docs/METHOD.md).

Nothing here scores the model on a real forecast: the registered test is run once, by the module itself.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import ts_obr_errors as C4
from triple_lock.config import HORIZON
from triple_lock.ts_uncertainty import committed_c2_rule_hash

YEARS = np.arange(2010, 2023)


def synthetic(seed=0, n=13):
    rng = np.random.default_rng(seed)
    return rng.normal(0.004, 0.02, size=(n, 4, 2))


def test_frozen_rule_keeps_its_registered_bytes():
    assert C4.frozen_rule_hash() == C4.RULE_SECTION_SHA256


def test_registering_c4_leaves_the_c2_rule_intact():
    assert committed_c2_rule_hash()


def test_the_record_is_the_thirteen_forecasts_c2_scores():
    record = C4.load_record()
    assert [v[0] for v in record["origins"]] == list(range(2010, 2023))
    assert record["statutory"].shape == record["calendar"].shape == (13, 4, 2)
    assert record["calendar_stand_in_years"] == [2026]
    assert np.isfinite(record["statutory"]).all() and np.isfinite(record["calendar"]).all()


@pytest.mark.parametrize("origin", range(2010, 2023))
def test_held_out_pool_shares_no_target_year_with_the_scored_forecast(origin):
    pool = YEARS[C4.pool_indices(YEARS, origin)]
    scored = set(range(origin + 1, origin + 5))
    assert all(not scored & set(range(u + 1, u + 5)) for u in pool)
    assert 6 <= len(pool) <= 9


def test_other_pool_rules():
    assert list(YEARS[C4.pool_indices(YEARS, 2016, "chronological")]) == [2010, 2011]
    assert 2016 not in YEARS[C4.pool_indices(YEARS, 2016, "leave_one_out")]
    assert len(C4.pool_indices(YEARS, 2026, "all")) == 13
    assert len(C4.pool_indices(YEARS, 2026)) == 13  # the forward origin's years lie after the record's
    with pytest.raises(ValueError):
        C4.pool_indices(YEARS, 2016, "other")


def test_draws_repeat_for_a_seed_and_differ_between_seeds():
    e = synthetic()
    a = C4.draw_errors({"s": e}, YEARS, 200, 12, 7)["s"]
    assert np.array_equal(a, C4.draw_errors({"s": e}, YEARS, 200, 12, 7)["s"])
    assert not np.array_equal(a, C4.draw_errors({"s": e}, YEARS, 200, 12, 8)["s"])
    assert a.shape == (200, 12, 2)


def test_raw_draws_replay_the_record_in_order():
    """With no de-meaning and no centre draw, years 1-4 are one forecast's errors and later years follow history."""
    e = synthetic()
    d = C4.draw_errors({"s": e}, YEARS, 500, 12, 3, demean=False, centre=False, small_sample=False)["s"]
    for path in d:
        u = [i for i in range(13) if np.array_equal(path[:4], e[i])]
        assert len(u) == 1
        position = u[0]
        for j in range(4, 12):
            options = [i for i in range(13) if np.array_equal(path[j], e[i, 3])]
            assert options
            if position + 1 < 13:  # the record lasts: the next forecast's four-year-ahead error
                assert options == [position + 1]
            position = options[0]


def test_statutory_and_calendar_errors_share_each_path():
    e = synthetic()
    out = C4.draw_errors({"statutory": e, "calendar": e.copy()}, YEARS, 300, 13, 5)
    assert np.array_equal(out["statutory"], out["calendar"])
    gap = synthetic(9) * 0.1
    out = C4.draw_errors({"statutory": e + gap, "calendar": e}, YEARS, 300, 13, 5, demean=False, centre=False,
                         small_sample=False)
    difference = out["statutory"] - out["calendar"]
    assert all(any(np.allclose(p[:4], g) for g in gap) for p in difference)


def test_demeaned_draws_centre_on_zero_and_the_centre_draw_widens_them():
    e = synthetic()
    base = C4.draw_errors({"s": e}, YEARS, 40_000, 4, 1, centre=False, small_sample=False)["s"]
    full = C4.draw_errors({"s": e}, YEARS, 40_000, 4, 1)["s"]
    assert np.abs(full.mean(axis=0)).max() < 6e-4
    assert np.allclose(base.var(axis=0), e.var(axis=0), rtol=0.05)
    assert (full.var(axis=0) > base.var(axis=0)).all()
    assert len(np.unique(full[:, 0, 0])) > 1000  # the centre draw makes the distribution near continuous


def test_scored_draws_ignore_every_error_measured_on_the_scored_years():
    record = C4.load_record()
    i = list(record["years"]).index(2016)
    before, pool = C4.origin_draws(record, i, n=50)
    changed = {**record, "statutory": record["statutory"].copy()}
    near = np.abs(record["years"] - 2016) < 4
    changed["statutory"][near] += 0.5
    after, _ = C4.origin_draws(changed, i, n=50)
    assert np.array_equal(before, after) and not near[pool].any()


def test_too_small_a_pool_is_refused():
    with pytest.raises(ValueError):
        C4.draw_errors({"s": synthetic(n=1)}, YEARS[:1], 10, 4, 0)
    with pytest.raises(ValueError):
        C4.draw_errors({"s": synthetic()[:, :3]}, YEARS, 10, 4, 0)


def _result(floor_bias=0.1, annual_50=0.5, hits_50=6):
    def block(n):
        stat = lambda m: {"mean": m}
        return {"n_origins": n, "expected_origins": n, "annual_gap_coverage": stat(0.8),
                "terminal_coverage": {"mean": 0.8, "hits": round(0.8 * n), "wilson95_independent": [0.5, 0.95]},
                "gap_bias_pp": stat(0.5), "switch_bias": stat(0.2), "floor_bias": stat(floor_bias),
                "annual_gap_coverage_50": stat(annual_50), "terminal_coverage_50": {"mean": hits_50 / n, "hits": hits_50},
                **{k: stat(1.0) for k in C4.PROPER_SCORES}}
    return {"failures": [], "scores": {"A": {"suspended": block(7)}, "B": {"suspended": block(13)}}}


REFERENCE = {"scores": {t: {"suspended": {C4.C2_REFERENCE_FORM: {k: {"mean": 1.0} for k in C4.PROPER_SCORES}}}
                        for t in "AB"}}


def test_verdict_applies_the_registered_limits():
    assert C4.verdict(_result(), REFERENCE)["passes"]
    failed = C4.verdict(_result(floor_bias=0.2501), REFERENCE)
    assert not failed["passes"] and len(failed["failures"]) == 2 and "floor_bias" in failed["failures"][0]
    assert not C4.verdict(_result(annual_50=0.75), REFERENCE)["passes"]
    assert not C4.verdict(_result(hits_50=11), REFERENCE)["passes"]
    assert C4.verdict(_result(hits_50=10), REFERENCE)["passes"]
    worse = {"scores": {t: {"suspended": {C4.C2_REFERENCE_FORM: {k: {"mean": 0.79} for k in C4.PROPER_SCORES}}}
                        for t in "AB"}}
    assert not C4.verdict(_result(), worse)["passes"]
    missing = _result()
    missing["failures"] = [{"origin": "March 2016 EFO", "error": "pool"}]
    assert not C4.verdict(missing, REFERENCE)["passes"]
    assert "not scored" in C4.verdict(_result(), REFERENCE)["past_years_check"]


def test_log_gap_is_zero_when_earnings_always_lead_and_opens_after_a_price_led_year():
    n = len(HORIZON)
    cpi, earnings = np.full(n, 0.02), np.full(n, 0.04)
    assert np.allclose(C4.log_gap(cpi, earnings), 0)
    cpi = cpi.copy()
    cpi[HORIZON.index(2032)] = 0.08  # prices lead once, after the switch: the adjusted rule then rises by less
    G = C4.log_gap(cpi, earnings)[0]
    assert np.allclose(G[: HORIZON.index(2032) + 1], 0) and G[-1] > 0
    assert np.isclose(G[HORIZON.index(2033)], np.log(1.04) - np.log(1.025))


def test_distribution_reports_the_registered_statistics():
    x = np.linspace(0, 0.1, 1001)
    d = C4.distribution(x, C4.SHARE_THRESHOLDS_PCT)
    assert set(d) == {"mean", "median", "p5", "p25", "p75", "p95", "probability_above_pct"}
    assert np.isclose(d["median"], 0.05) and np.isclose(d["probability_above_pct"]["5"], 0.5, atol=2e-3)


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(2, 13), horizon=st.integers(1, 13))
def test_draws_are_finite_for_any_pool(seed, n, horizon):
    years = YEARS[:n]
    d = C4.draw_errors({"s": synthetic(seed, n)}, years, 64, horizon, seed)["s"]
    assert d.shape == (64, horizon, 2) and np.isfinite(d).all()
