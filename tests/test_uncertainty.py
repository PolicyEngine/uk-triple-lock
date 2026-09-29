"""Monte Carlo on synthetic forecast-error fixtures (no PolicyEngine needed)."""

import csv

import numpy as np
import pytest

from triple_lock.config import ALTERNATIVES, POLICIES
from triple_lock.uncertainty import (
    error_blocks,
    horizon_error_schedule,
    load_forecast_errors,
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
    cpi_index = 1.02 ** len(YEARS)
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
