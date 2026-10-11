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
            "saving_support_records_by_year": {y: {"uk": {"gross": 20, "net": 20, "offset": 20},
                                                    "gb": {"gross": 10, "net": 10, "offset": 10}}
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
        rows = result[kind]
        assert all(r["status"] == "withheld_family" for r in rows)
        assert all(r["value_bn" if kind == "central" else "estimate_bn"] is None for r in rows)


@pytest.mark.parametrize("offset", [None, 1, 9])
def test_small_or_missing_gross_net_offset_withholds_both_totals(offset):
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    runs["draw_2"]["saving_support_records_by_year"][2039]["gb"]["offset"] = offset
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    assert all(row["status"] == "withheld_family" for rows in result.values() for row in rows)


def coverage_table(uk_total=40, uk_older=20, gb_total=20, gb_older=10):
    return {geo: {"programme_support_records": {
        "housing_benefit": total, "housing_benefit_pension_age": older}}
        for geo, total, older in (("uk", uk_total, uk_older), ("gb", gb_total, gb_older))}


@pytest.mark.parametrize("counts", [(21, 20, 10, 10), (40, 20, 21, 20),
                                   (41, 20, 30, 10)])
def test_hb_family_rejects_small_subset_or_geographic_complement(counts):
    assert not bridge.hb_family_supported([coverage_table(*counts)])


def test_hb_family_closes_across_years():
    assert bridge.hb_family_supported([coverage_table(), coverage_table()])
    assert not bridge.hb_family_supported([coverage_table(), coverage_table(21, 20, 10, 10)])


def test_public_coverage_withholds_both_linked_hb_metrics(monkeypatch):
    tables = {2024: coverage_table(), 2025: coverage_table(21, 20, 10, 10)}
    for table in tables.values():
        for row in table.values():
            row["programme_support_records"].update(
                state_pension=20 if row is table["uk"] else 10,
                pension_credit=20 if row is table["uk"] else 10,
                council_tax_reduction=20 if row is table["uk"] else 10)
            row.update({metric: 1.0 for metric in bridge.METRICS})
    monkeypatch.setattr(bridge.dwp, "coverage_targets_by_year", lambda **kw: {})
    monkeypatch.setattr(bridge, "digest", lambda path: "synthetic-source")
    rows = bridge.coverage_tables({"by_year": tables})["rows"]
    hb = [r for r in rows if r["metric"].startswith("housing_benefit")]
    assert len(hb) == 4
    assert all(r["status"] == "withheld_family" and r["UK"] is None and r["GB"] is None
               and r["support_UK"] is None and r["support_GB"] is None for r in hb)
    assert all(r["status"] == "available" for r in rows if r not in hb)


def test_source_change_between_batches_is_rejected(monkeypatch):
    start = {"source": "original", "packages": {"policyengine-uk": "2.125.1"}}
    monkeypatch.setattr(bridge, "execution_snapshot", lambda: deepcopy(start))
    bridge.check_snapshot(start, "before batch")
    monkeypatch.setattr(bridge, "execution_snapshot", lambda: {**start, "source": "changed"})
    with pytest.raises(bridge.engine.SourceChanged, match="changed at after batch"):
        bridge.check_snapshot(start, "after batch")


def test_incompatible_resumed_receipt_is_rejected(tmp_path):
    receipt = tmp_path / "bridge.json"
    receipt.write_text(json.dumps({"provenance": {"execution_snapshot": {"source": "old"}}}))
    with pytest.raises(bridge.engine.SourceChanged, match="incompatible source provenance"):
        bridge.check_resume(receipt, {"source": "new"})
    bridge.check_resume(receipt, {"source": "old"})


def test_reviewed_recipe_redaction_preserves_exact_pilot_design():
    root = Path(__file__).parents[1]
    path = root / "data/pilot/d_macro_specs.json"
    pilot = json.loads((root / "data/pilot/model_v2_e.json").read_text())
    specs = _keys_to_int(json.loads(path.read_text()))
    _, sample, weights = bridge.design(specs, bridge.CERTIFIED)
    bridge.verify_pilot_recipe(path, pilot, sample, weights)
    altered = deepcopy(sample)
    stratum = next(iter(altered))
    altered[stratum][0] += 1
    with pytest.raises(ValueError, match="differ from the pilot"):
        bridge.verify_pilot_recipe(path, pilot, altered, weights)
