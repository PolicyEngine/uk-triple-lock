"""Bridge design, estimator and linked suppression checks without survey data."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import run_model_v2_j_bridge as bridge
from triple_lock.engine import _keys_to_int


def test_frozen_bridge_uses_full_both_paths_and_original_forty_indices():
    specs = _keys_to_int(json.loads((Path(__file__).parents[1] / "data/pilot/d_macro_specs.json").read_text()))
    planned, sample, weights = bridge.design(specs, bridge.CERTIFIED)
    assert len(planned) == 42
    assert len({i for indices in sample.values() for i in indices}) == 40
    assert sum(map(len, sample.values())) == 40
    assert sum(weights.values()) + specs["identical_rates_probability"] == pytest.approx(1)
    assert all(job[1]["demography"] == "both" for _, job in planned)
    assert all(job[1]["dataset"] == bridge.CERTIFIED for _, job in planned)
    assert planned[-1][1][1]["years"] == [*range(2024, 2031), 2034, 2039]
    assert planned[0][1][1]["fiscal_output_years"] == [2034, 2039]


@pytest.mark.parametrize("uk,gb,expected", [(20, 10, True), (19, 10, False), (10, 10, True),
                                           (9, 0, False), (0, 0, True), (True, 0, False), (10, 20, False)])
def test_linked_support_includes_northern_ireland_complement(uk, gb, expected):
    assert bridge.linked_support(uk, gb) is expected


def fake_run(value):
    return {"saving_bn": {y: {"gross": value, "net": value, "gb": {"gross": value, "net": value}}
                          for y in bridge.YEARS},
            "saving_support_records_by_year": {y: {"uk": {"gross": 20, "net": 20},
                                                    "gb": {"gross": 10, "net": 10}}
                                               for y in bridge.YEARS}}


def test_partial_checkpoint_does_not_estimate_missing_draws():
    runs = {"central": fake_run(1), "draw_1": fake_run(2)}
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    assert len(result["central"]) == 8 and result["paired"] == []


def test_paired_estimator_uses_saved_stratum_mass_and_se_components():
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: .5})
    assert len(result["paired"]) == 8
    estimate = result["paired"][0]["estimate_bn"]
    assert estimate["mean"] == 1.5
    assert estimate["variance_path_sampling"] == .25
    assert estimate["variance_first_phase"] > 0


def test_one_small_complement_withholds_linked_measure_family():
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    runs["draw_2"]["saving_support_records_by_year"][2039]["uk"]["net"] = 19
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    for kind in ("central", "paired"):
        rows = [r for r in result[kind] if r["measure"] == "net"]
        assert all(r["status"] == "withheld_family" for r in rows)
        assert all(r["value_bn" if kind == "central" else "estimate_bn"] is None for r in rows)
        assert all(r["status"] == "available" for r in result[kind] if r["measure"] == "gross")
