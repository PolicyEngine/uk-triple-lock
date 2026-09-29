"""Checks on the committed results file that need no data access.

They catch source changes landing without the results being regenerated,
and schema drift the dashboard would trip over.
"""

import json

import pytest

from triple_lock import config, provenance

COMMITTED = config.OUTPUT


@pytest.fixture(scope="module")
def results():
    return json.loads(COMMITTED.read_text())


def test_top_level_schema(results):
    for key in ["provenance", "horizon", "policies", "central", "uncertainty", "metadata"]:
        assert key in results
    assert results["sample"] is False
    assert results["horizon"] == config.HORIZON
    assert results["policies"] == config.POLICIES


def test_provenance_is_recorded(results):
    block = results["provenance"]
    assert block["git_revision"]
    assert block["packages"]["policyengine"]
    assert block["packages"]["policyengine-uk"]
    assert block["release_bundle"]["certified_data_build_id"]


def test_committed_output_is_not_stale(results):
    """Calculation sources must match what produced the committed numbers.

    Fails when any module or pyproject.toml changed without a rerun. Fix by
    running `triple-lock-build` with managed-data access.
    """
    recorded = results["provenance"]["source_hashes"]
    current = provenance.source_hashes()
    assert set(recorded) == set(current), "hashed source list changed — rerun"
    changed = [name for name in current if recorded[name] != current[name]]
    assert not changed, (
        f"{', '.join(changed)} changed since the committed results were generated "
        "— rerun `triple-lock-build`"
    )


def test_dashboard_copy_matches(results):
    assert json.loads(config.DASHBOARD_COPY.read_text()) == results


def test_central_is_complete(results):
    central = results["central"]
    years = {str(y) for y in config.HORIZON}
    for p in config.POLICIES:
        assert set(central["uprating"][p]) == years
        assert set(central["full_state_pension_weekly"][p]) == years
    for alt in config.ALTERNATIVES:
        cost = central["cost_vs_triple_lock_bn"][alt]
        assert set(cost["gross"]) == years and set(cost["net"]) == years
        assert len(central["by_decile"][alt]) == 10
        assert [r["quintile"] for r in central["by_quintile"][alt]] == [1, 2, 3, 4, 5]
        assert "by_constituency" not in central
        assert central["by_region"][alt]
        assert 0 <= central["households_affected"][alt]["losing_pct"] <= 100


def test_alternatives_save_money_relative_to_the_triple_lock(results):
    """Negative = saving. No rule here can uprate faster than the triple lock."""
    for alt in config.ALTERNATIVES:
        cost = results["central"]["cost_vs_triple_lock_bn"][alt]
        for y in map(str, config.HORIZON):
            assert cost["gross"][y] <= 0
        final = str(config.FINAL_YEAR)
        # Tax and means-tested benefits claw back part, not all, of the saving.
        assert cost["gross"][final] <= cost["net"][final] <= 0


def test_net_cost_cross_check(results):
    """gov_balance-based net cost equals the change in household net income."""
    for alt in config.ALTERNATIVES:
        cost = results["central"]["cost_vs_triple_lock_bn"][alt]
        for y in map(str, config.HORIZON):
            assert cost["net"][y] == pytest.approx(cost["change_in_household_net_income"][y], abs=0.02)


def test_triple_lock_weekly_matches_model_baseline(results):
    weekly = results["central"]["full_state_pension_weekly"]["triple_lock"]
    stat = results["central"]["forecast"]["statutory_2027_inputs"]
    base = results["central"]["base_year_weekly"]["new_state_pension"]
    expected = base * (1 + round(max(stat["earnings"], stat["cpi"], 0.025), 3))
    assert weekly["2027"] == pytest.approx(expected, abs=0.01)


def test_uncertainty_schema(results):
    u = results["uncertainty"]
    assert u["n_draws"] >= 10_000
    for key in ["title", "url", "years_used", "method"]:
        assert u["error_source"][key]
    for alt in config.ALTERNATIVES:
        q = u["cost_of_triple_lock_vs"][alt]
        assert q["basis"] == "gross"
        # Positive = the triple lock costs more.
        assert 0 <= q["p5"] <= q["p50"] <= q["p95"]
    for p in config.POLICIES:
        assert set(u["fan"][p]) == {str(y) for y in config.HORIZON}
    assert all(0 <= v <= 1 for v in u["prob_triple_lock_binds_on_floor"].values())
    for label in ("p10", "p50", "p90"):
        path = u["representative_paths"][label]
        assert path["cpi"] and path["earnings"]
    main_fields = {"n_draws", "cost_of_triple_lock_vs", "fan", "prob_triple_lock_binds_on_floor",
                   "representative_paths", "zero_floor", "cost_of_triple_lock_vs_pct_of_spend"}
    assert u["error_source"]["n_vintages"] == len(u["error_source"]["vintages_used"])
    src = u["error_source"]
    assert src["n_vintage_combinations"] == src["n_vintages"] ** 2
    # A1: distinct paths = vintage pairs x distinct first-year CPI changes, and the
    # draws cannot produce more distinct paths than that.
    stat = results["central"]["forecast"]["statutory_2027_inputs"]
    n_first = len({round(c, 10) for c in stat["aug_to_sep_changes"]})
    assert src["n_distinct_paths"] == src["n_vintage_combinations"] * n_first
    assert src["n_equally_weighted_combinations"] == src["n_vintage_combinations"] * len(stat["aug_to_sep_changes"])
    assert u["distinct_paths_sampled"] <= src["n_distinct_paths"]
    for key in ["sensitivity_proxy_only", "sensitivity_raw_errors", "sensitivity_ex_2022_23"]:
        assert main_fields <= set(u[key]) and u[key]["description"]
    assert results["metadata"]["triple_lock_floor"] == 0.025
    assert "sensitivity_ex_covid" not in u
    assert "sensitivity_awe_gap" not in u and "sensitivity_statutory_gaps" not in u
    assert u["error_source"]["basis"].startswith("statutory inputs")
    assert "gross only" in u["basis_note"]
    assert 0 <= u["zero_floor"]["share_of_draws_any_rule"] <= 1
    for y in u["sensitivity_ex_2022_23"]["years_used"]:
        assert not {2022, 2023} & {y + h for h in range(1, 5)}


def test_linear_scaling_matches_full_policyengine(results):
    """The Monte Carlo's gross-cost scaling reproduces full PolicyEngine runs."""
    runs = results["uncertainty"]["representative_path_runs"]
    assert set(runs) == {"p10", "p50", "p90"}
    for label, run in runs.items():
        for alt, c in run["cost_of_triple_lock_vs"].items():
            assert c["approximation_bn"] == pytest.approx(c["gross_bn"], rel=1e-3, abs=0.01)


def test_var_cross_check_present(results):
    v = results["uncertainty"]["var_cross_check"]
    assert v["lag_order"] in (1, 2)
    assert -1 <= v["residual_correlation"] <= 1
    assert v["n_draws"] >= 10_000 and v["method"]
    for alt in ("double_lock", "earnings_link", "cpi_link"):
        q = v["cost_of_triple_lock_vs"][alt]
        assert q["basis"] == "gross" and 0 <= q["p10"] <= q["p50"] <= q["p90"]
    for key in ("fan", "prob_triple_lock_binds_on_floor"):
        assert v[key]


EXPECTED_INPUTS = {
    "data/obr_forecast_errors.csv",
    "data/obr_central_forecast.csv",
    "data/obr_outturn_crosscheck.csv",
    "data/benchmarks.csv",
    "data/triple_lock_actual_inputs.csv",
    "data/raw/ons_kac3_awe_total_pay_3m_yoy.csv",
    "data/raw/ons_d7g7_cpi_annual_rate.csv",
    "data/raw/ons_dtwm_compensation_of_employees.csv",
    "data/raw/ons_royk_employers_social_contributions.csv",
    "data/raw/ons_mgrz_employment_16plus.csv",
    "data/raw/ons_mgrq_self_employed_16plus.csv",
}


def test_input_files_unchanged(results):
    """Every input that feeds the results is hashed, and matches what the results used."""
    assert set(results["provenance"]["input_hashes"]) == EXPECTED_INPUTS
    for rel, digest in results["provenance"]["input_hashes"].items():
        assert provenance.file_hash(config.REPO / rel) == digest, f"{rel} changed — rerun"


BREAKDOWN_KEYS = ["by_decile", "by_quintile", "by_region", "by_hh_type", "by_tenure", "by_age_band"]


@pytest.mark.parametrize("key", BREAKDOWN_KEYS)
def test_breakdowns_sum_to_the_net_cost(results, key):
    """Each breakdown's total_bn sums to the net cost (= change in household net income)."""
    central = results["central"]
    for year, tables in [(config.FINAL_YEAR, central), (config.EXTRA_DISTRIBUTION_YEAR, central[f"distribution_{config.EXTRA_DISTRIBUTION_YEAR}"])]:
        for alt in config.ALTERNATIVES:
            rows = tables[key][alt]
            net = central["cost_vs_triple_lock_bn"][alt]["change_in_household_net_income"][str(year)]
            assert sum(r["total_bn"] for r in rows) == pytest.approx(net, abs=0.01 + 0.0005 * len(rows))
            assert sum(r["share_of_households_pct"] for r in rows) == pytest.approx(100, abs=0.1)
            for r in rows:
                assert {"label", "mean_change_gbp", "pct_income_change", "total_bn", "share_of_households_pct"} <= set(r)


def test_benchmarks(results):
    from triple_lock.benchmarks import resolve

    rows = results["metadata"]["benchmarks"]
    assert rows
    for row in rows:
        assert row["url"].startswith("https://")
        assert row["like_for_like"] in {"yes", "partial", "no"}
        assert resolve(results, row["our_metric"]) == row["our_value"]
        assert isinstance(row["our_value"], (int, float))
        assert isinstance(row["verified"], bool)
    assert all(r["verified"] for r in rows), "every benchmark shown must be checked against its source"
    assert all(url.startswith("https://") for url in results["uncertainty"]["var_cross_check"]["sources"])


def test_composition_effect_reported(results):
    comp = results["central"]["composition_effect"]
    final = str(config.FINAL_YEAR)
    assert comp["difference_pct_by_year"][str(config.HORIZON[0])] == 0
    assert comp["difference_pct"] == comp["difference_pct_by_year"][final]
    assert comp["description"]
    for alt in config.ALTERNATIVES:
        model = results["central"]["cost_vs_triple_lock_bn"][alt]["gross"][final]
        fixed = comp["gross_fixed_composition"][alt][final]
        if model:
            assert model / fixed - 1 == pytest.approx(comp["difference_pct"] / 100, abs=0.02)


def test_net_excluding_largest_household(results):
    for alt in config.ALTERNATIVES:
        c = results["central"]["cost_vs_triple_lock_bn"][alt]
        for y in map(str, config.HORIZON):
            assert c["net_excluding_largest_household"][y] == pytest.approx(
                c["net"][y] - c["largest_single_household"][y]["contribution_bn"], abs=0.011
            )


def test_main_uncertainty_includes_statutory_gaps_and_september_cpi(results):
    """C2: the main range adds the statutory-input gaps; A6: September 2026 CPI is drawn."""
    u = results["uncertainty"]
    main = u["cost_of_triple_lock_vs"]["earnings_link"]
    proxy = u["sensitivity_proxy_only"]["cost_of_triple_lock_vs"]["earnings_link"]
    assert main["p90"] - main["p10"] > proxy["p90"] - proxy["p10"]
    stat = results["central"]["forecast"]["statutory_2027_inputs"]
    assert len(stat["aug_to_sep_changes"]) == stat["aug_to_sep_years"][1] - stat["aug_to_sep_years"][0] + 1
    assert max(stat["aug_to_sep_changes"]) == stat["largest_aug_to_sep_cpi_rise"]
    tl_2027 = u["fan"]["triple_lock"]["2027"]
    assert tl_2027["p10"] == tl_2027["p90"]  # triple lock stays on the 3.9% earnings leg
    # Every alternative follows the triple lock until April 2030, then diverges.
    for alt in config.ALTERNATIVES:
        for y in ("2027", "2028", "2029"):
            assert u["fan"][alt][y] == u["fan"]["triple_lock"][y]
    assert u["fan"]["cpi_link"]["2030"]["p50"] < u["fan"]["triple_lock"]["2030"]["p50"]


def test_central_position_model_average_and_backtest(results):
    """A7: the central cost's place in the exact distribution, a pooled range, a backtest."""
    u = results["uncertainty"]
    pos = u["central_position"]
    assert pos["n_combinations"] == u["error_source"]["n_equally_weighted_combinations"]
    for alt in config.ALTERNATIVES:
        p = pos["by_alternative"][alt]
        assert p["central_bn"] == -results["central"]["cost_vs_triple_lock_bn"][alt]["gross"][str(config.FINAL_YEAR)]
        assert 0 <= p["share_below_central"] <= 1
        assert p["minimum_bn"] <= p["p5_bn"] <= p["median_bn"]
        q = u["model_average"]["cost_of_triple_lock_vs"][alt]
        assert q["p10"] <= q["p50"] <= q["p90"]
    assert u["sensitivity_median_centred"]["cost_of_triple_lock_vs"]
    bt = u["backtest"]
    assert len(bt["retrospective"]["vintages"]) == u["error_source"]["n_vintages"]
    roll = bt["rolling_origin"]
    assert 0 < roll["n_tested"] < u["error_source"]["n_vintages"]
    for row in roll["vintages"]:
        assert row["n_training"] >= 2
    for part in (bt["retrospective"], roll):
        for alt in config.ALTERNATIVES:
            assert part["n_within_p10_p90"][alt] <= part["n_tested"]
    assert "Not a reform-cost distribution" in u["model_average"]["description"]
    # A1: the limitation text agrees with the computed count.
    n = u["error_source"]["n_distinct_paths"]
    assert any(f"{n:,} distinct paths" in item for item in results["metadata"]["method_limitations"])


def test_late_horizon_sensitivity(results):
    """A8: the path is labelled by source, and the OBR long-term sensitivity is reported."""
    c = results["central"]
    assert c["path_sources"]["policyengine_long_run"] == list(config.LATE_HORIZON_YEARS)
    s = c["late_horizon_sensitivity"]
    assert s["conversion_check_max_error_pp"] < 0.1
    for alt in config.ALTERNATIVES:
        g = s["gross_bn"][alt]
        assert g["central"] == c["cost_vs_triple_lock_bn"][alt]["gross"][str(config.FINAL_YEAR)]
    assert s["gross_bn"]["cpi_link"]["obr_long_term"] > s["gross_bn"]["cpi_link"]["central"]


def test_alternatives_switch_in_april_2030(results):
    """Before April 2030 every rule equals the triple lock (the government's promise)."""
    c = results["central"]
    for alt in config.ALTERNATIVES:
        for y in (2027, 2028, 2029):
            assert c["uprating"][alt][str(y)] == c["uprating"]["triple_lock"][str(y)]
            assert c["cost_vs_triple_lock_bn"][alt]["gross"][str(y)] == 0
    assert c["cost_vs_triple_lock_bn"]["burnham_2030"]["gross"]["2034"] < 0
