"""The integrated population treatments and State Pension accounting, run through policyengine-uk itself on a
synthetic survey (no private data): engine.pinned_inputs, demography.population and the model's own formulas.

Properties (every treatment, config.DEMOGRAPHY_MODES):
* in the data year, basic + new + additional State Pension equals the reported State Pension the run counts
  (the survey's over State Pension age, nil below it) for every person, to £0.01;
* a 5% cut in the flat rates cuts the basic and new State Pension by exactly 5% and leaves the additional State
  Pension unchanged, person by person;
* cohort types equal the model's own State Pension type on the same represented ages and birthday, every year;
* the raked weights equal the dataset's own in the anchor (calibration) year and every year before it;
* represented ages above 80 reach the model's State Pension age and the engine's readers of it.
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("policyengine_uk")

from policyengine_uk import Microsimulation  # noqa: E402
from policyengine_uk.data import UKSingleYearDataset  # noqa: E402

from triple_lock import demography, engine  # noqa: E402
from triple_lock.config import DEMOGRAPHY_MODES, FLAT_RATE_PARAMETERS, HORIZON  # noqa: E402

DATA_YEAR, ANCHOR = 2024, 2025
YEARS = [2027, 2030, 2034, 2039]
SEP_CPI = {y: 0.02 for y in range(2015, 2040)} | {2024: 0.017, 2025: 0.038, 2030: -0.01}
REGIONS = ["LONDON", "SCOTLAND", "WALES", "NORTHERN_IRELAND", "NORTH_WEST", "SOUTH_EAST"]


def synthetic_dataset(seed=0, households=150, below_age_reporters=3):
    """Households of one or two adults across ages 20 to 80 (80 is the survey's top code), with State Pension
    reported by everyone 66 and over (about half above the new State Pension's flat rate, so with additional
    pension or protected payments), and ``below_age_reporters`` people under State Pension age reporting one."""
    rng = np.random.default_rng(seed)
    people, units, homes = [], [], []
    ages = np.r_[np.arange(20, 80), np.full(20, 80)]
    pid = 0
    for h in range(households):
        homes.append({"household_id": h, "household_weight": float(rng.uniform(200, 3000)),
                      "region": REGIONS[h % len(REGIONS)], "council_tax": 1500.0, "tenure_type": "OWNED_OUTRIGHT",
                      "rent": 0.0})
        units.append({"benunit_id": h})
        for k in range(1 + (h % 3 == 0)):
            age = int(rng.choice(ages))
            reported = float(rng.uniform(4_000, 16_000)) if age >= 66 else 0.0
            people.append({"person_id": pid, "person_household_id": h, "person_benunit_id": h, "age": age,
                           "gender": "FEMALE" if (pid + h) % 2 else "MALE", "is_household_head": k == 0,
                           "is_benunit_head": k == 0, "state_pension_reported": reported})
            pid += 1
    for i in range(below_age_reporters):  # a reporting error: State Pension below State Pension age
        people.append({"person_id": pid, "person_household_id": i, "person_benunit_id": i, "age": 55 + i % 11,
                       "gender": "MALE", "is_household_head": False, "is_benunit_head": False,
                       "state_pension_reported": 9_000.0})
        pid += 1
    return UKSingleYearDataset(person=pd.DataFrame(people), benunit=pd.DataFrame(units),
                               household=pd.DataFrame(homes), fiscal_year=DATA_YEAR)


@pytest.fixture(scope="module")
def dataset():
    return synthetic_dataset()


@pytest.fixture(autouse=True)
def private_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(demography, "PRIVATE_CACHE", tmp_path / "demography")


def load(dataset, flat_rate_factor=None):
    """A simulation of the synthetic survey, declared and anchored as engine._managed does for a registered dataset;
    with ``flat_rate_factor`` the flat rates in the horizon are the model's own times it."""
    sim = Microsimulation(dataset=dataset)
    sim.baseline = None
    sim.triple_lock_population = dict(engine.LOADED_POPULATION)
    sim.triple_lock_provenance = {"dataset": "synthetic", "ageing_anchor": {"year": ANCHOR}}
    if flat_rate_factor is not None:
        p = sim.tax_benefit_system.parameters
        levels = {name: {y: float(p.get_child(path)(f"{y}-06-01")) * flat_rate_factor for y in HORIZON}
                  for name, path in FLAT_RATE_PARAMETERS.items()}
        engine.set_flat_rates(sim, levels)
    return sim


def pinned_run(dataset, mode, flat_rate_factor=None):
    """(pinned inputs, a fresh simulation with them pinned): as run_path builds each policy's simulation."""
    pinned, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, mode)
    sim = load(dataset, flat_rate_factor)
    engine.pin(sim, pinned)
    return pinned, sim


def values(sim, variable, year):
    return np.asarray(sim.calculate(variable, year).to_numpy(), dtype=float)


@pytest.mark.parametrize("mode", DEMOGRAPHY_MODES)
def test_basic_new_and_additional_add_up_to_the_reported_pension_for_every_person(dataset, mode):
    pinned, sim = pinned_run(dataset, mode)
    parts = sum(values(sim, v, DATA_YEAR) for v in engine.STATE_PENSION_PARTS)
    reported = values(load(dataset), "state_pension_reported", DATA_YEAR)
    over = pinned.over_pension_age[DATA_YEAR]
    np.testing.assert_allclose(parts, np.where(over, reported, 0), rtol=0, atol=0.01)
    record = engine.state_pension_accounting(sim, pinned)
    assert record["max_identity_error_gbp"] <= 0.01
    # The three below-age reports are set aside, and too few to publish.
    assert int(((reported > 0) & ~over).sum()) == 3
    assert record["reports_below_pension_age"]["records"] is None
    assert record["reports_below_pension_age"]["reported_bn"] is None
    # Nobody below State Pension age is paid, in any year, and every type is paid only over it.
    for y in YEARS:
        paid = sum(values(sim, v, y) for v in engine.STATE_PENSION_PARTS)
        assert np.all(paid[~pinned.over_pension_age[y]] == 0)
        assert np.all((np.asarray(pinned["state_pension_type"][y]) != "NONE") == pinned.over_pension_age[y])


@pytest.mark.parametrize("mode", DEMOGRAPHY_MODES)
def test_a_five_percent_cut_in_the_flat_rates_moves_only_the_flat_rate_parts(dataset, mode):
    _, sim = pinned_run(dataset, mode)
    pinned, cut = pinned_run(dataset, mode, flat_rate_factor=0.95)
    for y in YEARS:
        for v in ("basic_state_pension", "new_state_pension"):
            np.testing.assert_allclose(values(cut, v, y), 0.95 * values(sim, v, y), rtol=0, atol=0.01)
        np.testing.assert_allclose(values(cut, "additional_state_pension", y),
                                   values(sim, "additional_state_pension", y), rtol=0, atol=0.01)
    assert engine.additional_pension_followed(cut, pinned, YEARS) <= 0.01
    assert engine.additional_pension_followed(sim, pinned, YEARS) <= 0.01


@pytest.mark.parametrize("mode", ["types", "both"])
def test_cohort_types_are_the_models_own_on_the_same_ages_and_birthday(dataset, mode):
    pinned, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, mode)
    oracle = load(dataset)
    for name in ("age", "months_since_last_birthday"):
        engine.pin(oracle, {name: pinned[name]})
    for y in [DATA_YEAR, *YEARS]:
        model = np.asarray(oracle.calculate("state_pension_type", y).to_numpy()).astype(str)
        np.testing.assert_array_equal(np.asarray(pinned["state_pension_type"][y]), model)
    # By 2039-40 the cohort types have moved people from the basic to the new State Pension.
    assert (np.asarray(pinned["state_pension_type"][2039]) == "BASIC").sum() < \
        (np.asarray(pinned["state_pension_type"][DATA_YEAR]) == "BASIC").sum()


@pytest.mark.parametrize("mode", ["reweight", "both"])
def test_raked_weights_are_the_datasets_own_through_the_calibration_year(dataset, mode):
    native = load(dataset)
    own = {y: values(native, "household_weight", y) for y in (DATA_YEAR, ANCHOR, 2039)}
    pinned, sim = pinned_run(dataset, mode)
    treatment = pinned.treatment
    for y in (DATA_YEAR, ANCHOR):
        assert np.array_equal(treatment.weights[y], own[y]), y
        assert np.array_equal(values(sim, "household_weight", y), own[y].astype(np.float32).astype(float)), y
    assert not np.allclose(treatment.weights[2039], own[2039])  # later years follow the ONS projection
    record = demography.readback(sim, treatment, [DATA_YEAR, ANCHOR, *YEARS])
    assert max(record["max_relative_cell_error"].values()) <= demography.REL_TOL
    assert set(record["max_relative_cell_error"]) == set(YEARS)  # nothing is raked at or before the anchor


def test_represented_ages_reach_the_state_pension_age_readers(dataset):
    pinned, sim = pinned_run(dataset, "both")
    ages = np.asarray(pinned["age"][2039])
    assert ages.max() > 80 and pinned.treatment.represented_topcoding_applied
    assert np.array_equal(values(sim, "age", 2039), ages.astype(np.float32).astype(float))
    over = values(sim, "is_SP_age", 2039).astype(bool)
    assert over[ages > 80].all()
    band = engine.state_pension_age_band(sim, 2039)
    assert band == [67.0]
    stats = engine.coverage_stats(sim, 2039)
    by_age = stats["uk"]["state_pension_by_age"]
    assert set(by_age) == {name for _, _, name in engine.COVERAGE_AGE_BANDS}
    assert all(cell["status"] in ("available", "suppressed") for cell in by_age.values())
    population = engine.population_treatment(sim, pinned, DATA_YEAR, YEARS)
    assert population == {"weights": "ons_projection", "ages": "adjusted", "pension_types": "cohort"}


def test_the_population_is_cached_across_paths_and_checked_against_the_model(dataset, monkeypatch):
    first, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "both")
    files = list(demography.PRIVATE_CACHE.glob("*.npz"))
    assert len(files) == 1
    # A second path (another September CPI) reuses the population; only the additional pension differs.
    other_cpi = {y: v + 0.01 for y, v in SEP_CPI.items()}
    second, _ = engine.pinned_inputs(load(dataset), YEARS, other_cpi, "both")
    assert list(demography.PRIVATE_CACHE.glob("*.npz")) == files
    for name in ("age", "household_weight", "state_pension_type"):
        for y in YEARS:
            assert np.array_equal(first[name][y], second[name][y])
    assert np.all(second["additional_state_pension"][2039] >= first["additional_state_pension"][2039])
    assert np.any(second["additional_state_pension"][2039] > first["additional_state_pension"][2039])
    # A cached State Pension age mask the model no longer gives fails the run rather than reuse stale types.
    with np.load(files[0]) as saved:
        arrays = {k: saved[k] for k in saved.files}
    arrays["over_pension_age_2039"] = ~arrays["over_pension_age_2039"]
    np.savez_compressed(files[0], **arrays)
    with pytest.raises(demography.EligibilityChanged, match="2039"):
        engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "both")


def test_the_cache_is_private(dataset):
    import stat

    engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "types")
    assert stat.S_IMODE(demography.PRIVATE_CACHE.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in demography.PRIVATE_CACHE.glob("*.npz"))


@pytest.mark.parametrize("mode", ["legacy", "frozen"])
def test_survey_year_types_hold_the_survey_type_while_over_state_pension_age(dataset, mode):
    survey = np.asarray(load(dataset).calculate("state_pension_type", DATA_YEAR).to_numpy()).astype(str)
    pinned, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, mode)
    for y in YEARS:
        over = pinned.over_pension_age[y]
        assert np.array_equal(np.asarray(pinned["state_pension_type"][y])[over], survey[over])


def test_frozen_and_legacy_differ_only_by_represented_ages(dataset):
    legacy, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "legacy")
    frozen, _ = engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "frozen")
    for y in YEARS:
        np.testing.assert_array_equal(legacy["state_pension_type"][y], frozen["state_pension_type"][y])
        np.testing.assert_allclose(legacy["additional_state_pension"][y], frozen["additional_state_pension"][y],
                                   rtol=0, atol=1e-9)
    assert "household_weight" not in frozen and "age" in frozen


@pytest.mark.parametrize("name", ["age", "months_since_last_birthday", "household_weight", "is_household_head"])
def test_readback_fails_when_the_model_does_not_use_a_pinned_input(dataset, name):
    pinned, sim = pinned_run(dataset, "both")
    changed = np.asarray(pinned[name][2034]).copy()
    changed[0] = (not changed[0]) if changed.dtype == bool else changed[0] + 1
    sim.set_input(name, 2034, changed)
    with pytest.raises(RuntimeError, match=f"pinned {name}|targets missed"):
        demography.readback(sim, pinned.treatment, YEARS)


def test_a_survey_with_ages_above_80_keeps_every_age():
    """If any age is above 80 the survey is not top-coded at 80: nobody is given a represented age."""
    data = synthetic_dataset()
    person = data.person.copy()
    person.loc[0, "age"] = 86
    data = UKSingleYearDataset(person=person, benunit=data.benunit, household=data.household, fiscal_year=DATA_YEAR)
    pinned, _ = engine.pinned_inputs(load(data), YEARS, SEP_CPI, "both")
    assert pinned.treatment.uncapped_age_fallback and not pinned.treatment.represented_topcoding_applied
    assert np.array_equal(pinned["age"][2039], person["age"].to_numpy(dtype=float))
    assert pinned.treatment.declared["ages"] == "survey_year"


def test_ten_or_more_reports_below_pension_age_are_published_as_aggregates():
    data = synthetic_dataset(below_age_reporters=12)
    pinned, sim = pinned_run(data, "both")
    aside = engine.state_pension_accounting(sim, pinned)["reports_below_pension_age"]
    assert aside["records"] == 12 and aside["people"] > 0 and aside["reported_bn"] > 0


@pytest.mark.parametrize("broken", ["identity", "paid_below_age"])
def test_the_accounting_check_fails_the_run(dataset, broken):
    pinned, sim = pinned_run(dataset, "types")
    basic = values(sim, "basic_state_pension", DATA_YEAR)
    if broken == "identity":
        i = int(np.flatnonzero(basic > 0)[0])
        basic[i] += 1
    else:  # pay a below-age reporter their report, which keeps every other identity
        below = ~pinned.over_pension_age[DATA_YEAR]
        i = int(np.flatnonzero(below & (pinned.reported > 0))[0])
        basic[i] = pinned.reported[i]
        payable = dict(pinned["state_pension_reported"])
        payable[DATA_YEAR] = payable[DATA_YEAR].copy()
        payable[DATA_YEAR][i] = pinned.reported[i]
        pinned["state_pension_reported"] = payable
    sim.set_input("basic_state_pension", DATA_YEAR, basic)
    with pytest.raises(engine.PathNotFollowed, match="off the reported|below State Pension age"):
        engine.state_pension_accounting(sim, pinned)


def test_an_ageing_treatment_needs_an_anchor(dataset):
    sim = load(dataset)
    sim.triple_lock_provenance = {"dataset": "synthetic"}
    with pytest.raises(ValueError, match="explicit calibration year"):
        engine.pinned_inputs(sim, YEARS, SEP_CPI, "both")
    assert not list(demography.PRIVATE_CACHE.glob("*.npz"))
    assert engine.pinned_inputs(sim, YEARS, SEP_CPI, "legacy")[1] == DATA_YEAR  # legacy needs none


def test_an_unknown_treatment_fails(dataset):
    with pytest.raises(ValueError, match="unknown demography treatment"):
        engine.pinned_inputs(load(dataset), YEARS, SEP_CPI, "aged")


def test_the_reported_state_pension_enters_nothing_but_the_three_parts():
    """The below-age rule pins the data year's state_pension_reported; that moves no other figure only while
    policyengine-uk reads it nowhere else. Every variable formula that reads it, in the installed release, is one of
    the three parts or the variable itself (its carry-forward)."""
    import ast
    import importlib.util
    from pathlib import Path

    root = Path(importlib.util.find_spec("policyengine_uk").origin).parent
    readers = set()
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "state_pension_reported" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "state_pension_reported":
                readers.add(path.stem)
    # Parameters can name variables too (the adds and subtracts lists formulas read).
    for path in [*root.rglob("*.yaml"), *root.rglob("*.yml")]:
        if "tests" in path.parts:
            continue
        if "state_pension_reported" in path.read_text(encoding="utf-8"):
            readers.add(f"parameter {path.relative_to(root)}")
    # uprating_indices.yaml uprates the stored report into the dataset's later years, which no formula reads: the
    # three parts read the data year's.
    assert readers == {"basic_state_pension", "new_state_pension", "additional_state_pension",
                       "state_pension_reported", "parameter data/uprating_indices.yaml"}, readers


def test_a_dataset_whose_anchor_weights_are_not_proportional_keeps_upstreams_types(dataset):
    """A data file with its own calibration-year weights (not the survey year's uprated) would move records within
    their year of age if the birthday were drawn on them: it is drawn on the survey year's, as upstream draws it, so
    every record that keeps its survey age keeps policyengine-uk's type."""
    sim = load(dataset)
    native = values(sim, "household_weight", ANCHOR)
    sim.set_input("household_weight", ANCHOR, native * np.linspace(0.5, 1.5, len(native)))
    pinned, _ = engine.pinned_inputs(sim, YEARS, SEP_CPI, "frozen")
    assert pinned.treatment.data_year_type_changes == 0
    survey = np.asarray(load(dataset).calculate("state_pension_type", DATA_YEAR).to_numpy()).astype(str)
    assert np.array_equal(np.asarray(pinned["state_pension_type"][DATA_YEAR]), survey)
