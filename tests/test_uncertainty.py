"""Monte Carlo on synthetic forecast-error fixtures (no PolicyEngine needed)."""

import csv

import numpy as np
import pytest

from triple_lock.config import ALTERNATIVES, POLICIES
from triple_lock.uncertainty import (
    error_blocks,
    gap_blocks,
    horizon_error_schedule,
    load_forecast_errors,
    load_statutory_gaps,
    n_distinct_paths,
    run_monte_carlo,
    simulate_growth_paths,
)

YEARS = list(range(2027, 2035))
GROWTH_YEARS = [y - 1 for y in YEARS]
CENTRAL_CPI = {g: 0.02 for g in GROWTH_YEARS}
CENTRAL_EARN = {g: 0.03 for g in GROWTH_YEARS}


def write_fixture(path, vintages, percent=False, horizons=4, duplicate=False):
    """vintages: {year_made: (cpi_error, earnings_error)} constant across horizons."""
    scale = 100 if percent else 1
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["year_forecast_made", "forecast_vintage", "target_year", "horizon_years",
             "variable", "forecast", "outturn", "error", "source_url"]
        )
        for year, (ce, ee) in vintages.items():
            for h in range(1, horizons + 1):
                for var, err in (("cpi", ce * h), ("earnings", ee * h)):
                    rows = [err, err] if duplicate else [err]
                    for e in rows:
                        w.writerow([year, f"March {year} EFO", year + h, h, var,
                                    0.02 * scale, (0.02 + e) * scale, e * scale, "x"])
    return path


def test_load_averages_duplicates(tmp_path):
    single = load_forecast_errors(write_fixture(tmp_path / "a.csv", {2010: (0.01, -0.01)}))
    doubled = load_forecast_errors(write_fixture(tmp_path / "b.csv", {2010: (0.01, -0.01)}, duplicate=True))
    assert single == doubled
    (vintage,) = single
    assert vintage == (2010, "March 2010 EFO")
    assert single[vintage][("cpi", 2)] == pytest.approx(0.02)


def test_percentage_point_file_rejected(tmp_path):
    with pytest.raises(ValueError, match="decimal"):
        load_forecast_errors(write_fixture(tmp_path / "p.csv", {2010: (0.01, -0.01)}, percent=True))


def test_missing_error_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_forecast_errors(tmp_path / "absent.csv")


def test_unknown_variable_raises(tmp_path):
    path = write_fixture(tmp_path / "u.csv", {2010: (0.01, -0.01)})
    path.write_text(path.read_text().replace(",cpi,", ",rpi,", 1))
    with pytest.raises(ValueError, match="unknown variable"):
        load_forecast_errors(path)


def test_missing_columns_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("year_forecast_made,variable\n2010,cpi\n")
    with pytest.raises(ValueError):
        load_forecast_errors(p)


def test_error_blocks_drop_incomplete_vintages(tmp_path):
    path = write_fixture(tmp_path / "e.csv", {2010: (0.01, 0.0), 2011: (0.0, 0.01)})
    errors = load_forecast_errors(path)
    # A vintage with only one horizon, as the most recent EFOs have.
    errors[(2024, "March 2024 EFO")] = {("cpi", 1): 0.05, ("earnings", 1): 0.05}
    blocks, kept = error_blocks(errors)
    assert blocks.shape == (2, 4, 2)
    assert [v[0] for v in kept] == [2010, 2011]


def test_schedule_extends_with_longest_horizons():
    assert horizon_error_schedule(7, 4) == [
        (0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4)
    ]
    assert horizon_error_schedule(3, 4) == [(0, 1), (0, 2), (0, 3)]


def test_zero_errors_reproduce_central_path():
    blocks = np.zeros((3, 4, 2))
    cpi, earn = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks, n_draws=50)
    assert np.allclose(cpi, 0.02) and np.allclose(earn, 0.03)


def test_vintage_errors_stay_paired_and_horizon_zero_is_unperturbed():
    blocks = np.array([np.full((4, 2), 0.01), np.full((4, 2), -0.01)])
    blocks[:, :, 1] *= 2  # earnings error = 2 x CPI error within a vintage
    cpi, earn = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks, n_draws=500)
    assert np.allclose(cpi[:, 0], 0.02) and np.allclose(earn[:, 0], 0.03)
    # Within a block, CPI and earnings errors come from the same vintage.
    assert np.allclose(earn[:, 1:5] - 0.03, 2 * (cpi[:, 1:5] - 0.02))


def test_monte_carlo_cost_matches_linear_scaling():
    """With no forecast error every draw equals the deterministic answer."""
    blocks = np.zeros((2, 4, 2))
    spend = 200.0
    tl_index = 1.03 ** len(YEARS)
    mc = run_monte_carlo(CENTRAL_CPI, CENTRAL_EARN, YEARS, 2026, blocks, spend, tl_index, n_draws=100)
    # Every alternative follows the triple lock until April 2030.
    pre = sum(1 for y in YEARS if y < 2030)
    cpi_index = 1.03**pre * 1.02 ** (len(YEARS) - pre)
    expected = spend * (tl_index - cpi_index) / tl_index
    assert mc["cost_of_triple_lock_vs"]["cpi_link"]["p50"] == pytest.approx(expected)
    assert mc["cost_of_triple_lock_vs"]["earnings_link"]["p50"] == pytest.approx(0.0)
    assert mc["cost_of_triple_lock_vs"]["cpi_link"]["basis"] == "gross"
    assert all(v == 0.0 for v in mc["prob_triple_lock_binds_on_floor"].values())


def test_monte_carlo_shape_and_signs(tmp_path):
    rng = np.random.default_rng(1)
    vintages = {2010 + i: tuple(rng.normal(0, 0.01, 2)) for i in range(12)}
    errors = load_forecast_errors(write_fixture(tmp_path / "f.csv", vintages))
    blocks, _ = error_blocks(errors)
    mc = run_monte_carlo(CENTRAL_CPI, CENTRAL_EARN, YEARS, 2026, blocks, 200.0, 1.3, n_draws=10_000)
    assert mc["n_draws"] == 10_000
    for alt in ALTERNATIVES:
        q = mc["cost_of_triple_lock_vs"][alt]
        # The triple lock is never cheaper than an alternative.
        assert q["p5"] >= 0
        assert q["p5"] <= q["p10"] <= q["p25"] <= q["p50"] <= q["p75"] <= q["p90"] <= q["p95"]
    for p in POLICIES:
        for y in YEARS:
            f = mc["fan"][p][str(y)]
            assert f["p10"] <= f["p50"] <= f["p90"]
    assert all(0 <= v <= 1 for v in mc["prob_triple_lock_binds_on_floor"].values())
    for label in ("p10", "p50", "p90"):
        path = mc["representative_paths"][label]
        assert set(path["cpi"]) == {str(g) for g in GROWTH_YEARS}
        assert set(path["earnings"]) == {str(g) for g in GROWTH_YEARS}
    ranked = [mc["representative_paths"][k]["approx_cost_of_triple_lock_vs_bn"]["cpi_link"] for k in ("p10", "p50", "p90")]
    assert ranked == sorted(ranked)


def test_demeaned_draws_have_zero_mean_error_per_horizon():
    rng = np.random.default_rng(7)
    blocks = rng.normal(0.01, 0.02, (12, 4, 2))  # biased errors
    cpi, earn = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks,
                                      n_draws=200_000, demean=True)
    assert cpi.mean(axis=0) == pytest.approx(np.full(8, 0.02), abs=3e-4)
    assert earn.mean(axis=0) == pytest.approx(np.full(8, 0.03), abs=3e-4)
    raw_cpi, _ = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks, n_draws=200_000)
    assert raw_cpi[:, 1:].mean() > 0.025


def test_ex_2022_23_drops_blocks_targeting_those_years(tmp_path):
    vintages = {y: (0.0, 0.0) for y in range(2010, 2022)}
    errors = load_forecast_errors(write_fixture(tmp_path / "x.csv", vintages))
    _, kept = error_blocks(errors, exclude_target_years=(2022, 2023))
    years = [v[0] for v in kept]
    assert years == list(range(2010, 2018))
    for y in years:
        assert not {2022, 2023} & {y + h for h in range(1, 5)}


def test_zero_floor_share_and_pct_of_spend():
    # One vintage with deflation: every draw hits the zero floor for the CPI link.
    blocks = np.full((2, 4, 2), -0.05)
    mc = run_monte_carlo(CENTRAL_CPI, CENTRAL_EARN, YEARS, 2026, blocks, 200.0, 1.3, n_draws=100)
    assert mc["zero_floor"]["share_of_draws_any_rule"] == 1.0
    assert mc["zero_floor"]["share_of_draws_by_rule"]["cpi_link"] == 1.0
    q, pct = mc["cost_of_triple_lock_vs"]["cpi_link"], mc["cost_of_triple_lock_vs_pct_of_spend"]["cpi_link"]
    assert pct["p50"] == pytest.approx(100 * q["p50"] / 200.0)


def test_gap_blocks_align_with_target_years_and_are_demeaned():
    kept = [(2010, "a"), (2011, "b")]
    gaps = {y: (0.001 * y, -0.002 * y) for y in range(2011, 2016)}
    g = gap_blocks(kept, gaps, block_horizon=4)
    assert g.shape == (2, 4, 2)
    assert g.mean(axis=0) == pytest.approx(np.zeros((4, 2)), abs=1e-12)  # per horizon
    # vintage 2011 horizon 1 targets 2012; vintage 2010 horizon 1 targets 2011
    assert g[1, 0, 0] - g[0, 0, 0] == pytest.approx(0.001)
    assert g[1, 0, 1] - g[0, 0, 1] == pytest.approx(-0.002)
    with pytest.raises(KeyError):
        gap_blocks([(2012, "c")], gaps, block_horizon=4)  # 2016 missing


def test_gaps_widen_draws_without_moving_the_centre():
    rng = np.random.default_rng(3)
    blocks = rng.normal(0, 0.01, (12, 4, 2))
    gaps = rng.normal(0, 0.01, (12, 4, 2))
    gaps -= gaps.mean(axis=(0, 1), keepdims=True)
    base, _ = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks,
                                    n_draws=50_000, demean=True)
    wide, _ = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks,
                                    n_draws=50_000, demean=True, gaps=gaps)
    assert wide[:, 0] == pytest.approx(base[:, 0])  # horizon 0 untouched
    assert wide[:, 1:].mean() == pytest.approx(0.02, abs=5e-4)
    assert wide[:, 1:].std() > base[:, 1:].std()
    with pytest.raises(ValueError):
        simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks, gaps=gaps[:, :2])


def test_load_statutory_gaps_uses_rebuilt_earnings_when_outturn_missing(tmp_path):
    path = tmp_path / "cc.csv"
    path.write_text(
        "year,cpi_obr_outturn,cpi_ons_d7g7_september,earnings_obr_outturn,"
        "earnings_obr_def_rebuilt_latest_ons,awe_kac3_may_jul\n"
        "2024,0.025,0.017,0.05,0.0501,0.044\n"
        "2025,0.034,0.038,,0.041,0.049\n"
        "2026,,,,,0.039\n"
    )
    gaps = load_statutory_gaps(path)
    assert set(gaps) == {2024, 2025}
    assert gaps[2024] == pytest.approx((-0.008, -0.006))
    assert gaps[2025] == pytest.approx((0.004, 0.008))


def test_n_distinct_paths():
    # horizons 1-7 with blocks of 4: one full block plus one of three horizons
    assert n_distinct_paths(12, 7, 4) == 144
    assert n_distinct_paths(12, 4, 4) == 12


def test_first_year_cpi_shocks_move_only_forecast_year_cpi():
    rng = np.random.default_rng(5)
    blocks = rng.normal(0, 0.01, (12, 4, 2))
    shocks = [-0.005, 0.0, 0.007]
    cpi, earn = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks,
                                      n_draws=5_000, demean=True, first_year_cpi_shocks=shocks)
    base_cpi, base_earn = simulate_growth_paths(CENTRAL_CPI, CENTRAL_EARN, GROWTH_YEARS, 2026, blocks,
                                                n_draws=5_000, demean=True)
    assert set(np.round(cpi[:, 0] - 0.02, 6)) == {-0.005, 0.0, 0.007}
    assert (earn[:, 0] == 0.03).all()
    assert cpi[:, 1:] == pytest.approx(base_cpi[:, 1:])  # block picks unchanged
    assert earn == pytest.approx(base_earn)
