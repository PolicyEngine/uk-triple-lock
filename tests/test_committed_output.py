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
    for key in ["sensitivity_raw_errors", "sensitivity_ex_2022_23", "sensitivity_awe_gap"]:
        assert main_fields <= set(u[key]) and u[key]["description"]
    assert results["metadata"]["triple_lock_floor"] == 0.025
    assert "sensitivity_ex_covid" not in u
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


def test_input_files_unchanged(results):
    """Every hashed input (error CSV, ONS history) matches what the results used."""
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
    assert {r["id"] for r in rows if not r["verified"]} == {"ifs_r272_2023", "ifs_r291_2023", "ifs_r272_2023_cumulative"}
    assert all(url.startswith("https://") for url in results["uncertainty"]["var_cross_check"]["sources"])


def test_composition_effect_reported(results):
    comp = results["central"]["composition_effect"]
    final = str(config.FINAL_YEAR)
    assert comp["overstatement_pct_by_year"][str(config.HORIZON[0])] == 0
    assert comp["overstatement_pct"] == comp["overstatement_pct_by_year"][final]
    assert comp["description"]
    for alt in config.ALTERNATIVES:
        model = results["central"]["cost_vs_triple_lock_bn"][alt]["gross"][final]
        fixed = comp["gross_fixed_composition"][alt][final]
        if model:
            assert model / fixed - 1 == pytest.approx(comp["overstatement_pct"] / 100, abs=0.02)


def test_net_excluding_largest_household(results):
    for alt in config.ALTERNATIVES:
        c = results["central"]["cost_vs_triple_lock_bn"][alt]
        for y in map(str, config.HORIZON):
            assert c["net_excluding_largest_household"][y] == pytest.approx(
                c["net"][y] - c["largest_single_household"][y]["contribution_bn"], abs=0.011
            )
