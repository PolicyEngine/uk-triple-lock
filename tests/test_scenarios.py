"""The committed scenario runs (data/scenarios), checked against the code that produced them (no private data needed).

A scenario is one full run of the central path with some rule's rates specified (docs/METHOD.md, Scenario runs).
Its rates and labels recompute from the inputs it records, its inputs are the scenario's as the code defines it
today, it passes every check a path run in the results file passes, and it publishes no survey record.
"""

import json

import pytest
import test_results as on_results  # the results file's run checks, applied to the scenario runs below

from triple_lock import engine, rules
from triple_lock.central import central_path
from triple_lock.config import HORIZON, OUTPUT, POLICIES, SCENARIO_DIR
from triple_lock.trajectories import SCENARIOS, central_spec

ints = on_results.ints
PROVENANCE = {"generated_at", "git_revision", "git_dirty", "source_hashes", "input_hashes", "engine_hashes",
              "packages", "release_bundle", "datasets"}


@pytest.fixture(scope="module")
def scenarios():
    files = sorted(SCENARIO_DIR.glob("*.json"))
    if not files:
        pytest.fail(f"no scenario runs in {SCENARIO_DIR}: run triple-lock-build --scenario NAME")
    return [json.loads(f.read_text()) for f in files]


@pytest.fixture(scope="module")
def runs(scenarios):
    return [(s["id"], s["run"]) for s in scenarios]


def test_every_named_scenario_is_committed(scenarios):
    assert sorted(s["id"] for s in scenarios) == sorted(SCENARIOS)


def test_inputs_are_the_scenario_as_the_code_defines_it(scenarios):
    """The specified rates are what trajectories.SCENARIOS gives today, and everything else is the central path."""
    central = central_path()
    for s in scenarios:
        spec = SCENARIOS[s["id"]](central)
        assert {p: ints(v) for p, v in s["specified_rates"].items()} == spec["specified_rates"], s["id"]
        base = central_spec(central)
        r = s["run"]
        for k in ("cpi", "earnings"):
            assert ints(r["statutory"][k]) == pytest.approx(base[f"statutory_{k}"], abs=1e-15), (s["id"], k)
            assert ints(r["calendar"][k]) == pytest.approx(base[k], abs=1e-15), (s["id"], k)
        assert r["rate_decimals"] == base["rate_decimals"], s["id"]


def test_rates_recompute_from_the_specified_inputs(scenarios):
    """Differential: each rule on the run's own statutory inputs with its specified rates gives the rates it paid."""
    for s in scenarios:
        r = s["run"]
        cpi, earnings = ints(r["statutory"]["cpi"]), ints(r["statutory"]["earnings"])
        specified = engine.spec_specified(s)
        for p in POLICIES:
            expected = rules.uprating_path(p, cpi, earnings, HORIZON, r["rate_decimals"], specified)
            assert ints(r["rates"][p]) == pytest.approx(expected, abs=1e-12), (s["id"], p)
        for p, by_year in specified.items():
            assert all(r["rates"][p][str(y)] == rules.round_rate(v, r["rate_decimals"]) for y, v in by_year.items())


def test_rate_sources_recompute_and_name_the_specified_years(scenarios):
    for s in scenarios:
        r = s["run"]
        cpi, earnings = ints(r["statutory"]["cpi"]), ints(r["statutory"]["earnings"])
        rates = {p: ints(r["rates"][p]) for p in r["rates"]}
        specified = engine.spec_specified(s)
        expected = engine.rate_sources(cpi, earnings, rates, HORIZON, r["rate_decimals"], specified)
        assert {p: ints(v) for p, v in r["rate_sources"].items()} == expected, s["id"]
        for p, by_year in specified.items():
            assert {y for y in HORIZON if expected[p][y] == "specified"} == set(by_year), (s["id"], p)


def test_the_scenario_passes_every_path_runs_checks(runs):
    """The model followed the path, applied the rules' flat rates, held the same law under both rules, and the savings
    reconcile with its totals and household tables, as for every run in the results file."""
    results = json.loads(OUTPUT.read_text())
    on_results.test_weekly_amounts_compound_the_rates(results, runs)
    on_results.test_the_model_applied_the_rules_flat_rates(runs)
    on_results.test_fixed_inputs_are_the_same_law_under_both_rules(runs)
    on_results.test_the_model_used_the_held_pension_types(runs)
    on_results.test_savings_reconcile_with_the_model_totals(runs)
    on_results.test_no_saving_before_the_switch(runs)
    on_results.test_every_run_followed_its_path(runs)
    on_results.test_benefit_uprating_is_not_stuck_after_2029(runs)
    for year_key in ("2034", "2039"):
        on_results.test_household_tables_sum_to_the_net_change(runs, year_key)
    on_results.test_largest_household_is_the_largest(runs)


def test_the_obr_premium_only_moves_the_triple_lock():
    """The OBR wedge specifies the triple lock alone, in every year, from the OBR's 'Triple lock' row a year earlier."""
    central = central_path()
    spec = SCENARIOS["obr_premium"](central)
    assert set(spec["specified_rates"]) == {"triple_lock"}
    assert spec["specified_rates"]["triple_lock"] == {y: central["obr_triple_lock_uprating"][y - 1] for y in HORIZON}


def test_built_from_a_clean_tree_with_full_provenance(scenarios):
    for s in scenarios:
        p = s["provenance"]
        assert PROVENANCE <= set(p), (s["id"], PROVENANCE - set(p))
        assert p["git_dirty"] is False, s["id"]
        assert p["release_bundle"]["runtime_dataset"] == s["run"]["dataset"], s["id"]


def test_no_survey_record_is_published(scenarios):
    """FRS records are licensed: a scenario file gives a record's contribution to totals, never its id, weight or
    amounts (the results file's rule, test_results.test_no_survey_record_is_published)."""
    for s in scenarios:
        on_results.test_no_survey_record_is_published(s)


def test_no_household_weight_is_published(scenarios):
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                assert "weight" not in k, f"{path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")

    for s in scenarios:
        walk(s, s["id"])
