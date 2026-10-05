"""Properties of input calibration, independent of private survey records."""

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from triple_lock.demography import (AGE_BANDS, InfeasibleTargets, age_cells,
    anchored_targets, fiscal_population, household_incidence, pension_components,
    projection_cells, projection_totals, rake_households)


@st.composite
def feasible_rakes(draw):
    n = draw(st.integers(2, 12))
    w = np.array(draw(st.lists(st.floats(0.1, 100, allow_nan=False, allow_infinity=False),
                              min_size=n, max_size=n)))
    # Singleton household support makes every generated target feasible, with
    # additional multi-person households to test coupled calibration.
    a = np.concatenate([np.eye(n), np.ones((n, 1))], axis=1)
    w = np.append(w, draw(st.floats(0.1, 100, allow_nan=False, allow_infinity=False)))
    ratio = np.array(draw(st.lists(st.floats(0.5, 2, allow_nan=False, allow_infinity=False),
                                  min_size=n + 1, max_size=n + 1)))
    return w, a, a @ (w * ratio)


@settings(max_examples=60, deadline=None)
@given(feasible_rakes())
def test_rake_feasible_bounded_positive_deterministic(case):
    weights, incidence, targets = case
    result = rake_households(weights, incidence, targets)
    assert incidence @ result == pytest.approx(targets, rel=1e-6)
    assert np.all(result > 0)
    assert np.all(result >= weights * 0.2 * (1 - 1e-12))
    assert np.all(result <= weights * 5 * (1 + 1e-12))
    assert np.array_equal(result, rake_households(weights, incidence, targets))


@given(st.lists(st.floats(0.1, 1000, allow_nan=False, allow_infinity=False), min_size=1, max_size=12))
def test_anchor_leaves_base_weights_exactly_unchanged(values):
    weights = np.array(values)
    a = np.eye(len(weights))
    targets = anchored_targets(a @ weights, np.ones(len(weights)), np.ones(len(weights)))
    assert np.array_equal(rake_households(weights, a, targets), weights)


@given(st.floats(1, 2, allow_nan=False, allow_infinity=False))
def test_increasing_one_feasible_cell_never_lowers_its_count(ratio):
    w, a = np.array([10., 20., 30.]), np.array([[1., 0., 1.], [0., 1., 1.]])
    original = a @ w
    raised = original.copy()
    raised[0] *= ratio
    result = rake_households(w, a, raised)
    assert (a @ result)[0] >= original[0] * (1 - 1e-6)


def test_person_count_uses_one_common_household_weight():
    membership, ages, female = np.array([0, 0, 1]), [60, 80, 65], [False, True, False]
    w = np.array([2., 7.])
    a = household_incidence(membership, age_cells(ages, female), len(w))
    assert (a @ w).sum() == w[membership].sum() == 11


def test_infeasible_or_invalid_targets_fail_closed():
    with pytest.raises(InfeasibleTargets):
        rake_households([1.], [[1.]], [6.])
    with pytest.raises(InfeasibleTargets):
        rake_households([1.], [[0.]], [1.])
    with pytest.raises(InfeasibleTargets):
        rake_households([1.], [[1.], [1.]], [1., 2.])
    with pytest.raises(ValueError):
        rake_households([0.], [[1.]], [1.])


@pytest.mark.parametrize("bounds,target", [((1, 5), 2), ((.2, 1), .5)])
def test_feasible_targets_when_base_weights_start_on_a_bound(bounds, target):
    assert rake_households([1.], [[1.]], [target], bounds=bounds) == pytest.approx([target], rel=1e-6)


def test_cell_boundaries_and_fiscal_population():
    assert age_cells([59, 60, 79, 80, 84, 85, 89, 90, 105], [False] * 9).tolist() == [11,12,31,32,32,33,33,34,34]
    projection = projection_totals()
    assert np.array_equal(fiscal_population(2026, projection), .75 * projection[2026] + .25 * projection[2027])
    assert len(projection_cells(projection[2024])) == 2 * len(AGE_BANDS)
    assert projection_cells(projection[2024]).sum() == projection[2024].sum()


@given(st.lists(st.floats(0, 50000, allow_nan=False, allow_infinity=False), min_size=2, max_size=20))
def test_components_identity_retyped_residual_and_nonnegative(amounts):
    amount = np.array(amounts)
    types = np.resize(["BASIC", "NEW"], len(amount))
    basic, new, additional = pension_components(amount, types, 9000, 12000)
    assert basic + new + additional == pytest.approx(amount, abs=.01)
    assert np.all(additional >= 0)
    _, _, new_asp = pension_components(amount, np.full(len(amount), "NEW"), 9000, 12000)
    _, _, basic_asp = pension_components(amount, np.full(len(amount), "BASIC"), 9000, 12000)
    assert np.all(new_asp <= basic_asp)


def test_none_with_positive_report_is_zero_payable_not_a_fabricated_entitlement():
    components = pension_components([10000], ["NONE"], 9000, 12000)
    assert all(np.array_equal(component, [0]) for component in components)


@pytest.mark.parametrize("mode", ["frozen", "types", "reweight", "both"])
def test_cached_demography_reads_original_survey_ages_after_pinning(tmp_path, monkeypatch, mode):
    """Readback must never redistribute the remaining represented age-80 subset."""
    from types import SimpleNamespace
    from triple_lock import demography

    class Column:
        def __init__(self, values):
            self.values = np.asarray(values)

        def to_numpy(self):
            return self.values

    ages = np.tile(np.r_[np.arange(80), np.full(40, 80)], 2)
    ids = np.arange(len(ages))
    female = ids >= len(ids) // 2
    raw = SimpleNamespace(person={name: Column(values) for name, values in
        {"age": ages, "person_id": ids, "person_household_id": ids, "person_benunit_id": ids}.items()},
        household={"household_id": Column(ids), "household_weight": Column(np.ones(len(ids)))},
        benunit={"benunit_id": Column(ids)})

    class Dataset:
        years = [2024]
        name = "synthetic"

        def __getitem__(self, year):
            assert year == 2024
            return raw

    class Sim:
        dataset = Dataset()

        def __init__(self):
            self.pins = {}

        def calculate(self, name, year):
            if name == "is_female":
                return Column(female)
            if name in ("person_id", "household_id"):
                return Column(ids)
            if name == "household_weight" and (name, year) not in self.pins:
                return Column(np.ones(len(ids)))
            return Column(self.pins[(name, year)])

    monkeypatch.setattr(demography, "PRIVATE_CACHE", tmp_path / "private")
    sim = Sim()
    first, _, _ = demography._dataset_demography(sim, [2024, 2039], mode)
    sim.pins[("age", 2024)] = first["age"]
    sim.pins[("household_weight", 2024)] = first["weights_2024"]
    second, _, _ = demography._dataset_demography(sim, [2024, 2039], mode)
    assert len(list((tmp_path / "private").glob("*.npz"))) == 1
    for name in first:
        assert np.array_equal(first[name], second[name])
    assert np.array_equal(first["weights_2024"], np.ones(len(ids)))
    import stat
    assert stat.S_IMODE((tmp_path / "private").stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in (tmp_path / "private").glob("*.npz"))


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    """A synthetic model boundary exercising real pins, caching and readback.

    Flat components are calculated separately from the residual helper. The
    stub stores floats as float32, as PolicyEngine does, and represents two
    multi-person households with one benefit unit each. No model/data download.
    """
    import sys
    from types import SimpleNamespace
    from triple_lock import demography

    class Column:
        def __init__(self, values):
            self.values = np.asarray(values)

        def to_numpy(self):
            return self.values

    class Sim:
        def __init__(self, exceptions=1, uncapped=False, flags=True, rule=1.0, retyped=False):
            self.ages = np.r_[75, 70, np.full(exceptions, 65), 86 if uncapped else 80]
            self.female = np.r_[False, True, np.zeros(exceptions, dtype=bool), True].astype(bool)
            self.original_types = np.asarray(["BASIC", "NEW", *(["NONE"] * exceptions), "BASIC"])
            self.original_asp = np.r_[1000., 2000., np.zeros(exceptions), 2000.]
            if retyped:
                self.original_types[1], self.original_asp[1] = "BASIC", 5000
            self.reported = np.r_[10000., 14000., np.full(exceptions, 2000.), 11000.]
            self.membership = np.r_[0, 0, np.ones(exceptions + 1, dtype=int)]
            ids = np.arange(len(self.ages)) + 1001
            head = np.zeros(len(ids), dtype=bool)
            head[[0, -1]] = True
            person = {name: Column(value) for name, value in {
                "age": self.ages, "person_id": ids,
                "person_household_id": np.array([101, 202])[self.membership],
                "person_benunit_id": np.array([11, 22])[self.membership],
            }.items()}
            if flags:
                person.update({name: Column(head) for name in ("is_household_head", "is_benunit_head")})
            self.raw = SimpleNamespace(person=person,
                household={"household_id": Column([101, 202]), "household_weight": Column([100., 200.])},
                benunit={"benunit_id": Column([11, 22])})
            raw = self.raw

            class Dataset:
                years = [2024]
                calibration_year = 2024
                name = "synthetic-pinning"

                def __getitem__(self, year):
                    assert year == 2024
                    return raw

            self.dataset = Dataset()
            self.pins, self.overrides, self.deleted = {}, {}, []
            self.tax_benefit_system = SimpleNamespace(
                variables={name: None for name in (
                    "age", "household_weight", "person_weight", "benunit_weight", "state_pension_type",
                    "additional_state_pension", "is_household_head", "is_benunit_head", "is_SP_age",
                    "state_pension_age", "months_since_state_pension_age", "birth_year", "months_since_last_birthday")},
                parameters=SimpleNamespace(gov=SimpleNamespace(dwp=SimpleNamespace(state_pension=SimpleNamespace(
                    basic_state_pension=SimpleNamespace(amount=lambda y: 9000 / 52 * (1 if y == 2024 else rule)),
                    new_state_pension=SimpleNamespace(amount=lambda y: 12000 / 52 * (1 if y == 2024 else rule)))))))

        def set_input(self, name, year, values):
            dtype = np.float32 if name in ("age", "household_weight", "person_weight", "benunit_weight",
                                           "additional_state_pension", "months_since_last_birthday") else None
            self.pins[(name, year)] = np.asarray(values, dtype=dtype).copy()

        def delete_arrays(self, name, year):
            self.deleted.append((name, year))

        def calculate(self, name, year):
            key = (name, year)
            if key in self.overrides:
                return Column(self.overrides[key])
            if key in self.pins:
                return Column(self.pins[key])
            if name == "is_female":
                return Column(self.female)
            if name in ("person_id", "household_id"):
                entity = self.raw.person if name == "person_id" else self.raw.household
                return entity[name]
            if name == "age":
                return Column(self.ages)
            if name == "household_weight":
                return Column([100., 200.] if year == 2024 else [200., 600.])
            if name == "person_weight":
                return Column(self.calculate("household_weight", year).to_numpy()[self.membership])
            if name == "benunit_weight":
                return self.calculate("household_weight", year)
            if name == "is_SP_age":
                return Column(self.calculate("age", year).to_numpy() >= 67)
            if name == "state_pension_type":
                return Column(self.original_types)
            if name == "additional_state_pension":
                return Column(self.original_asp)
            if name == "state_pension_reported":
                return Column(self.reported)
            if name in ("basic_state_pension", "new_state_pension"):
                chosen, ceiling = ("BASIC", 9000) if name == "basic_state_pension" else ("NEW", 12000)
                return Column(np.where(self.calculate("state_pension_type", year).to_numpy() == chosen,
                                       np.minimum(self.reported, ceiling), 0))
            raise KeyError(name)

    monkeypatch.setattr(demography, "PRIVATE_CACHE", tmp_path / "private")
    monkeypatch.setattr(demography, "projection_totals", lambda: {
        y: np.ones((2, 106)) * (1 + .01 * (y - 2024)) for y in range(2024, 2041)})
    # pinned_inputs only imports the upstream weeks constant; substituting it
    # avoids initializing a full UK model while the two real workers run.
    monkeypatch.setitem(sys.modules, "policyengine_uk.model_api", SimpleNamespace(WEEKS_IN_YEAR=52))
    return Sim


def prepare_fake_inputs(fake_model, mode="both", **model_options):
    from triple_lock import demography, engine

    sim = fake_model(**model_options)
    sep = {y: .03 for y in range(2024, 2040)}
    sep.update({2024: .02, 2025: -.01})
    pinned, data_year = demography.pinned_inputs(sim, [2024, 2025, 2039], sep, mode=mode, calibration_year=2024)
    engine.pin(sim, pinned)
    return sim, pinned, data_year, sep


@pytest.mark.parametrize("mode", ["frozen", "reweight", "types", "both"])
def test_pinned_inputs_and_readback_share_weights_flags_cohorts_and_cpi(fake_model, mode):
    from triple_lock import demography

    sim, pinned, data_year, _ = prepare_fake_inputs(fake_model, mode)
    assert data_year == pinned.calibration_year == 2024
    assert pinned.demography_mode == mode
    checks = demography.validate_inputs(sim, pinned, [2024, 2025, 2039], mode=mode)
    assert checks["pinned_survey_flags"] == ["is_household_head", "is_benunit_head"]
    assert checks["represented_topcoding_applied"] is True
    assert checks["uncapped_age_fallback"] is False
    for year in (2024, 2025, 2039):
        assert np.array_equal(pinned["person_weight"][year], pinned["household_weight"][year][sim.membership])
        assert np.array_equal(pinned["benunit_weight"][year], pinned["household_weight"][year])
        for flag in checks["pinned_survey_flags"]:
            assert np.array_equal(sim.calculate(flag, year).to_numpy(), sim.raw.person[flag].to_numpy())
        assert pinned["state_pension_type"][year][2] == "NONE"
        assert pinned["additional_state_pension"][year][2] == 0
    assert pinned["additional_state_pension"][2025][0] == pytest.approx(1020)
    if mode in ("types", "both"):
        assert pinned["state_pension_type"][2039][0] == "NEW"
        assert pinned["additional_state_pension"][2039][0] == 0
    else:
        assert pinned["state_pension_type"][2039][0] == "BASIC"
        assert pinned["additional_state_pension"][2039][0] == pytest.approx(1000 * 1.02 * 1.03**13)
    if mode in ("reweight", "both"):
        assert all(v["max_relative_cell_error"] <= 1e-6 for v in checks["years"].values())
    else:
        assert np.array_equal(pinned["household_weight"][2039], [200, 600])
    assert ("is_SP_age", 2024) in sim.deleted
    diagnostics = demography.data_year_diagnostics(sim, pinned, data_year)
    assert diagnostics["eligible_components_identity_within_penny"] is True
    assert diagnostics["unchanged_type_additional_matches_original_within_penny"] is True
    assert diagnostics["below_pension_age_zero_payable_components"] is True
    assert diagnostics["positive_reports_below_model_pension_age_records"] is None  # one synthetic exception
    assert diagnostics["all_records_components_identity_within_penny"] is False


@pytest.mark.parametrize("name,message", [
    ("age", "pinned age"), ("state_pension_type", "pinned state_pension_type"),
    ("is_household_head", "pinned is_household_head"), ("is_benunit_head", "pinned is_benunit_head"),
    ("months_since_last_birthday", "pinned months_since_last_birthday"),
    ("person_weight", "person weights differ"), ("benunit_weight", "benefit-unit weights differ"),
])
def test_readback_rejects_changed_age_type_head_flags_and_inherited_weights(fake_model, name, message):
    from triple_lock import demography

    sim, pinned, _, _ = prepare_fake_inputs(fake_model)
    changed = sim.calculate(name, 2039).to_numpy().copy()
    if name == "state_pension_type":
        changed[0] = "NONE"
    elif name.startswith("is_"):
        changed[0] = not changed[0]
    else:
        changed[0] += 1
    sim.overrides[(name, 2039)] = changed
    with pytest.raises(RuntimeError, match=message):
        demography.validate_inputs(sim, pinned, [2024, 2025, 2039])


def test_uncapped_fallback_and_missing_survey_flags_are_explicit_aggregates(fake_model):
    import json
    from triple_lock import demography

    sim, pinned, _, _ = prepare_fake_inputs(fake_model, uncapped=True, flags=False)
    checks = demography.validate_inputs(sim, pinned, [2024, 2025, 2039])
    assert checks["pinned_survey_flags"] == []
    assert checks["represented_topcoding_applied"] is False
    assert checks["uncapped_age_fallback"] is True
    assert np.array_equal(pinned["age"][2024], sim.ages)
    assert "person_id" not in json.dumps(checks)
    assert "household_weight" not in json.dumps(checks)


def test_same_cpi_produces_identical_private_inputs_under_different_flat_rate_rules(fake_model):
    _, first, _, _ = prepare_fake_inputs(fake_model, rule=1.05)
    _, second, _, _ = prepare_fake_inputs(fake_model, rule=1.50)
    for name in first:
        for year in first[name]:
            assert np.array_equal(first[name][year], second[name][year])


def test_data_year_diagnostics_keeps_forty_below_age_reports_as_aggregate_exceptions(fake_model):
    from triple_lock import demography

    sim, pinned, data_year, _ = prepare_fake_inputs(fake_model, exceptions=40)
    diagnostics = demography.data_year_diagnostics(sim, pinned, data_year)
    assert diagnostics["positive_reports_below_model_pension_age_records"] == 40
    assert diagnostics["data_year_type_changes_records"] == 0
    assert diagnostics["eligible_components_identity_within_penny"] is True
    assert diagnostics["all_records_components_identity_within_penny"] is False
    assert (pinned["state_pension_type"][data_year][2:-1] == "NONE").all()
    assert (pinned["additional_state_pension"][data_year][2:-1] == 0).all()


def test_retyped_data_year_record_repartitions_without_changing_eligible_reported_total(fake_model):
    from triple_lock import demography

    sim, pinned, data_year, _ = prepare_fake_inputs(fake_model, retyped=True)
    assert pinned.original_types[1] == "BASIC"
    assert pinned["state_pension_type"][data_year][1] == "NEW"
    assert pinned.original_asp[1] == 5000
    assert pinned["additional_state_pension"][data_year][1] == 2000
    assert sim.calculate("new_state_pension", data_year).to_numpy()[1] == 12000
    diagnostics = demography.data_year_diagnostics(sim, pinned, data_year)
    assert diagnostics["eligible_components_identity_within_penny"] is True
    assert diagnostics["unchanged_type_additional_matches_original_within_penny"] is True
    assert diagnostics["data_year_type_changes_records"] is None  # suppress one changed synthetic record


@pytest.mark.parametrize("failure", ["eligible_identity", "unchanged_asp", "below_age_payment"])
def test_accounting_gates_reject_each_failure_independently(fake_model, failure):
    from triple_lock import demography

    sim, pinned, data_year, _ = prepare_fake_inputs(fake_model)
    basic = sim.calculate("basic_state_pension", data_year).to_numpy().copy()
    if failure == "eligible_identity":
        basic[0] += 1
    elif failure == "unchanged_asp":
        asp = sim.calculate("additional_state_pension", data_year).to_numpy().copy()
        asp[0] += 1
        basic[0] -= 1  # preserve identity, so the independent unchanged-type check catches this
        sim.overrides[("additional_state_pension", data_year)] = asp
    else:
        basic[2] = sim.reported[2]  # even an identity-matching payment below SPA must fail
    sim.overrides[("basic_state_pension", data_year)] = basic
    with pytest.raises(RuntimeError, match="State Pension accounting failed"):
        demography.data_year_diagnostics(sim, pinned, data_year)


def test_changed_survey_flags_invalidate_the_private_input_cache(fake_model):
    from triple_lock import demography

    sim = fake_model()
    first, _, _ = demography._dataset_demography(sim, [2024], "both", 2024)
    sim.raw.person["is_household_head"].values = ~sim.raw.person["is_household_head"].values
    second, _, _ = demography._dataset_demography(sim, [2024], "both", 2024)
    assert not np.array_equal(first["flag_is_household_head"], second["flag_is_household_head"])
    assert len(list(demography.PRIVATE_CACHE.glob("*.npz"))) == 2
