"""Binding dataset roles on invented records only; no registered artifact is opened."""

import hashlib
import json
import numpy as np
import pytest

from triple_lock import config, datasets, demography, disclosure, expected_value, pipeline


def test_binding_roles_and_current_wording_preserve_frozen_pipeline_constants():
    assert config.PRIMARY_DATASET == "microcosm_uk_2024_25@a133f37a"
    assert config.SENSITIVITY_DATASET == "enhanced_frs_2024_25@1.58.2"
    assert datasets.resolve() == config.PRIMARY_DATASET
    assert datasets.ageing_anchor()["year"] == 2024
    assert datasets.ageing_anchor()["calibration_year"] is None
    assert datasets.ageing_anchor(config.SENSITIVITY_DATASET)["year"] == 2025
    assert "enhanced_frs_2024_25@1.58.0" in datasets.DATASETS
    assert pipeline.sensitivity_dataset_names()[config.SENSITIVITY_DATASET] == "Enhanced FRS 1.58.2"
    assert "Microcosm is an uncertified sensitivity" in " ".join(pipeline.METHOD_LIMITATIONS)
    current = " ".join(pipeline.method_limitations())
    assert "Microcosm is an uncertified sensitivity" not in current
    for wanted in ("#715", "2.147.2", "3.33.3", "1.58.2", "#2557", "#2576", "d1753", "Vahid", "step (b)"):
        assert wanted in current
    # Preserve exactly the historical imports/constants and redactor that C2 protects.
    import cold_source_correspondence as cold
    source = (config.REPO / "src/triple_lock/pipeline.py").read_bytes()
    symbols, options = cold.PROTECTED_AST["src/triple_lock/pipeline.py"]
    assert cold.selected_ast(source, symbols, **options) == (
        "aef8eb1b3aa01159491876136992ce3150ca988f88fac41fc058078ad7e0c1fc"
    )


def test_the_frozen_c2_forty_slots_change_only_dataset_role():
    """The historical handoff supplies the design; capture jobs without invoking a model."""
    handoff = config.REPO / "docs/uncertainty/handoff.json"
    before = hashlib.sha256(handoff.read_bytes()).hexdigest()
    frozen = json.loads(handoff.read_text())["forms"]["monthly_var1_boot"]["design"]
    sample = {int(k): value for k, value in frozen["sample"].items()}
    paired = expected_value._paired_subsample(sample, 40)
    # The pre-registered first-slot allocation, including the two zero-stratum slots.
    assert {key: len(value) for key, value in paired.items()} == {
        0: 2, 1: 5, 2: 3, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 4, 10: 14,
    }
    assert all(value == sample[key][:len(value)] for key, value in paired.items())
    assert sum(map(len, paired.values())) == 40
    indices = sorted({i for group in paired.values() for i in group})
    calls = []
    def runner(jobs, **kwargs):
        calls.append(jobs)
        return [{"invented": True} for _ in jobs]
    specs = {i: {"id": f"draw_{i}"} for i in indices}
    expected_value._execute(specs, indices, 1, lambda _: None, runner=runner)
    expected_value._execute(specs, indices, 1, lambda _: None, config.SENSITIVITY_DATASET, runner)
    assert all(datasets.resolve(arg.get("dataset")) == config.PRIMARY_DATASET for _, arg in calls[0])
    assert all(arg["dataset"] == config.SENSITIVITY_DATASET for _, arg in calls[1])
    assert [arg["id"] for _, arg in calls[0]] == [arg["id"] for _, arg in calls[1]]
    assert hashlib.sha256(handoff.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("records,status", [(0, "available"), (9, "suppressed"), (10, "available")])
def test_microcosm_donors_keep_the_same_ten_record_withholding(records, status):
    amounts = np.ones(records)
    cell = disclosure.coverage_cell(
        {"state_pension": amounts, "basic_state_pension": amounts,
         "new_state_pension": np.zeros(records)}, np.ones(records), np.ones(records, dtype=bool))
    assert cell["status"] == status
    assert cell["records"] == (None if status == "suppressed" else records)


def test_microcosm_style_ids_ages_anchor_and_state_pension_identity(tmp_path, monkeypatch):
    """Twenty-four invented single-person households exercise the exact installed wheel."""
    pd = pytest.importorskip("pandas")
    pytest.importorskip("policyengine_uk")
    from policyengine_uk import Microsimulation
    from policyengine_uk.data import UKSingleYearDataset
    from triple_lock import engine

    monkeypatch.setattr(demography, "PRIVATE_CACHE", tmp_path / "demography")
    n = 24
    ids = np.arange(n, dtype=np.int64) + 2**40 + 1000
    ages = np.tile([55, 65, 70, 80, 85, 95], 4)
    people = pd.DataFrame({
        "person_id": ids + 100, "person_household_id": ids, "person_benunit_id": ids,
        "age": ages, "gender": np.where(np.arange(n) % 2, "FEMALE", "MALE"),
        "is_household_head": True, "is_benunit_head": True,
        "state_pension_reported": np.where(ages >= 65, 13_000., 500.),
    })
    household = pd.DataFrame({"household_id": ids, "household_weight": np.arange(1., n + 1),
                              "region": np.tile(["LONDON", "NORTHERN_IRELAND"], n // 2),
                              "tenure_type": "OWNED_OUTRIGHT", "council_tax": 1500., "rent": 0.})
    data = UKSingleYearDataset(person=people, benunit=pd.DataFrame({"benunit_id": ids}),
                               household=household, fiscal_year=2024)
    assert getattr(data, "calibration_year", None) is None
    sim = Microsimulation(dataset=data)
    sim.baseline = None
    sim.triple_lock_population = dict(engine.LOADED_POPULATION)
    sim.triple_lock_provenance = {"dataset": config.PRIMARY_DATASET,
                                 "ageing_anchor": datasets.ageing_anchor()}
    np.testing.assert_array_equal(sim.calculate("person_id", 2024).to_numpy(), (ids + 100).astype(np.int32))
    native = sim.calculate("household_weight", 2024).to_numpy().copy()
    pinned, year = engine.pinned_inputs(sim, [2026, 2027], {y: .02 for y in range(2024, 2027)}, "both")
    assert year == pinned.treatment.anchor == 2024
    assert pinned.treatment.uncapped_age_fallback and not pinned.treatment.represented_topcoding_applied
    for y in (2024, 2026, 2027):
        np.testing.assert_array_equal(pinned["age"][y], ages)
    np.testing.assert_array_equal(pinned.treatment.weights[2024], native)
    engine.pin(sim, pinned)
    assert engine.state_pension_accounting(sim, pinned)["max_identity_error_gbp"] <= .01
    assert max(demography.readback(sim, pinned.treatment, [2026, 2027])["max_relative_cell_error"].values()) <= 1e-6
    # The same GB mask feeds coverage against DWP, excluding Northern Ireland.
    stats = engine.coverage_stats(sim, 2026)
    assert stats["gb"]["state_pension_bn"] < stats["uk"]["state_pension_bn"]
    rows = {row["key"]: row for row in pipeline._coverage_rows({"primary": stats}, pipeline.dwp.coverage_targets()["values"])}
    row = rows["state_pension_bn"]
    assert row["primary_gb"] == stats["gb"]["state_pension_bn"]
    assert row["primary_gb_over_dwp"] == pytest.approx(row["primary_gb"] / row["dwp"])
    assert row["dwp"] == pipeline.dwp.coverage_targets()["values"]["state_pension_in_gb"]
