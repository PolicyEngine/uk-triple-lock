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


def test_cached_demography_reads_original_survey_ages_after_pinning(tmp_path, monkeypatch):
    """Readback must never redistribute the remaining represented age-80 subset."""
    from types import SimpleNamespace
    from triple_lock import demography

    class Column:
        def __init__(self, values):
            self.values = np.asarray(values)

        def to_numpy(self):
            return self.values

    ages = np.tile(np.arange(106), 2)
    ids = np.arange(len(ages))
    female = ids >= 106
    raw = SimpleNamespace(person={name: Column(values) for name, values in
        {"age": ages, "person_id": ids, "person_household_id": ids}.items()},
        household={"household_id": Column(ids), "household_weight": Column(np.ones(len(ids)))})

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
            return Column(self.pins[(name, year)])

    monkeypatch.setattr(demography, "PRIVATE_CACHE", tmp_path / "private")
    sim = Sim()
    first, _, _ = demography._dataset_demography(sim, [2024, 2039], "both")
    sim.pins[("age", 2024)] = first["age"]
    sim.pins[("household_weight", 2024)] = first["weights_2024"]
    second, _, _ = demography._dataset_demography(sim, [2024, 2039], "both")
    assert len(list((tmp_path / "private").glob("*.npz"))) == 1
    for name in first:
        assert np.array_equal(first[name], second[name])
    assert np.array_equal(first["weights_2024"], np.ones(len(ids)))
