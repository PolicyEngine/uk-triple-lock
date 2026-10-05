"""Cohort boundaries and deterministic weighted representation of top-coded ages."""

from datetime import date
import importlib.metadata

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from triple_lock.cohorts import (
    birth_dates_from_age,
    cohort_type,
    represent_topcoded_ages,
    within_year_birth_months,
)


@pytest.mark.parametrize("female,cutoff", [(False, "1951-04-06"), (True, "1953-04-06")])
def test_exact_fifth_and_sixth_april_cohort_boundary(female, cutoff):
    boundary = np.datetime64(cutoff)
    dates = boundary + np.array([-1, 0, 1]).astype("timedelta64[D]")
    assert cohort_type(dates, [female] * 3, [True] * 3).tolist() == ["BASIC", "NEW", "NEW"]
    assert cohort_type(dates, [female] * 3, [False] * 3).tolist() == ["NONE"] * 3


@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2020, 12, 31)), st.booleans(), st.booleans())
@settings(deadline=None)
def test_basic_iff_birth_precedes_sex_cutoff_and_eligible(born, female, eligible):
    cutoff = date(1953 if female else 1951, 4, 6)
    expected = "NONE" if not eligible else "BASIC" if born < cutoff else "NEW"
    assert cohort_type([born], [female], [eligible])[0] == expected


@given(st.lists(st.dates(min_value=date(1900, 1, 1), max_value=date(2020, 12, 31)), min_size=1), st.booleans())
@settings(deadline=None)
def test_type_is_monotone_in_birth_date(dates, female):
    dates = sorted(dates)
    types = cohort_type(dates, [female] * len(dates), [True] * len(dates))
    assert np.diff((types == "NEW").astype(int)).min(initial=0) >= 0


@st.composite
def weighted_records(draw):
    n = draw(st.integers(min_value=1, max_value=200))
    ages = np.asarray(draw(st.lists(st.integers(min_value=0, max_value=80), min_size=n, max_size=n)))
    # Ensure the test exercises top-coding, with both sexes when possible.
    ages[: min(n, 2)] = 80
    female = np.asarray(draw(st.lists(st.booleans(), min_size=n, max_size=n)))
    female[: min(n, 2)] = [False, True][: min(n, 2)]
    weights = np.asarray(draw(st.lists(st.integers(min_value=1, max_value=10000), min_size=n, max_size=n)), dtype=float)
    shares = {sex: dict(zip(range(80, 106), draw(st.lists(st.integers(min_value=0, max_value=100), min_size=26, max_size=26))))
              for sex in (False, True)}
    for sex in shares:
        shares[sex][80] += 1
    return ages, female, np.arange(n), weights, shares


@given(weighted_records())
@settings(max_examples=100, deadline=None)
def test_represented_age_preserves_counts_and_matches_each_sex_age_cell(records):
    ages, female, ids, weights, shares = records
    represented = represent_topcoded_ages(*records, dataset_id="synthetic")
    np.testing.assert_array_equal(represented[ages < 80], ages[ages < 80])
    assert (represented[ages == 80] >= 80).all()
    assert (represented[ages == 80] <= 105).all()
    for sex in (False, True):
        mask = (ages == 80) & (female == sex)
        if not mask.any():
            continue
        total = weights[mask].sum()
        assert weights[(represented >= 80) & (female == sex)].sum() == total
        target_sum = sum(shares[sex].values())
        for age in range(80, 106):
            actual = weights[(represented == age) & (female == sex)].sum()
            target = total * shares[sex][age] / target_sum
            assert abs(actual - target) <= weights[mask].max() + 1e-8
    np.testing.assert_array_equal(represented, represent_topcoded_ages(*records, dataset_id="synthetic"))
    permutation = np.random.default_rng(0).permutation(len(ages))
    reordered = represent_topcoded_ages(ages[permutation], female[permutation], ids[permutation],
                                     weights[permutation], shares, dataset_id="synthetic")
    np.testing.assert_array_equal(reordered[np.argsort(permutation)], represented)


def test_105_represents_the_terminal_105_plus_share_and_keeps_non_topcoded_records():
    ages = np.array([79, 80, 80])
    out = represent_topcoded_ages(ages, [False] * 3, range(3), np.ones(3),
                                 {False: {105: 1}}, dataset_id="test")
    assert out.tolist() == [79, 105, 105]


@pytest.mark.parametrize("known_older_age", [81, 90, 105, 106])
def test_uncapped_dataset_preserves_genuine_age_80_and_every_known_age(known_older_age):
    ages = np.array([7, 79, 80, 80, known_older_age], dtype=float)
    original = ages.copy()
    out = represent_topcoded_ages(ages, [False, True, False, True, True], range(5), np.ones(5),
                                 {False: {105: 1}, True: {105: 1}}, dataset_id="synthetic-uncapped")
    np.testing.assert_array_equal(out, original)
    np.testing.assert_array_equal(ages, original)
    assert not np.shares_memory(out, ages)


@given(st.lists(st.floats(min_value=0, max_value=110, allow_nan=False, allow_infinity=False),
                min_size=1, max_size=100))
@settings(deadline=None)
def test_one_known_older_age_prevents_any_topcode_redistribution(known_ages):
    ages = np.asarray([*known_ages, 80, 81])
    result = represent_topcoded_ages(ages, np.zeros(len(ages), dtype=bool), np.arange(len(ages)),
                                    np.ones(len(ages)), {}, dataset_id="synthetic-uncapped")
    np.testing.assert_array_equal(result, ages)


def test_cohort_helpers_emit_no_person_ids_or_record_weights(capsys, caplog):
    # Synthetic inputs only: this test never opens or prints survey records.
    ids, weights = np.array([910001, 910002]), np.array([137.25, 241.75])
    ages = represent_topcoded_ages([80, 80], [False, True], ids, weights,
                                  {False: {84: 1}, True: {93: 1}}, dataset_id="synthetic-private")
    months = within_year_birth_months(ids, ages, [False, True], weights)
    cohort_type(birth_dates_from_age(ages, months, 2026), [False, True], [True, True])
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert not caplog.records


def test_birth_date_reference_is_sixth_october_and_preserves_april_boundaries():
    dates = birth_dates_from_age([75, 75, 75, 73, 73], [6 + 1 / 31, 6, 0, 6 + 1 / 31, 6], 2026)
    np.testing.assert_array_equal(dates, np.array(["1951-04-05", "1951-04-06", "1951-10-06",
                                                "1953-04-05", "1953-04-06"], dtype="datetime64[D]"))


def test_fractional_age_overrides_birthday_input():
    np.testing.assert_array_equal(birth_dates_from_age([75.5], [0], 2026),
                                  birth_dates_from_age([75], [6], 2026))


@given(st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=100))
@settings(deadline=None)
def test_birthday_draw_is_deterministic_and_order_invariant(weights):
    ids = np.arange(len(weights))
    ages = np.full(len(weights), 75)
    female = ids % 2 == 0
    months = within_year_birth_months(ids, ages, female, weights)
    assert ((months >= 0) & (months < 12)).all()
    np.testing.assert_array_equal(months, within_year_birth_months(ids, ages, female, weights))
    np.testing.assert_array_equal(months, within_year_birth_months(ids[::-1], ages[::-1], female[::-1], weights[::-1])[::-1])


def test_bad_inputs_fail_before_producing_cohorts():
    with pytest.raises(ValueError, match="aligned"):
        cohort_type(["1950-01-01"], [], [True])
    with pytest.raises(ValueError, match="known"):
        cohort_type(["NaT"], [False], [True])
    with pytest.raises(ValueError, match="unique"):
        within_year_birth_months([1, 1], [70, 70], [False, False], [1, 1])
    with pytest.raises(ValueError, match="positive total"):
        represent_topcoded_ages([80], [False], [1], [0], {False: {80: 1}}, dataset_id="test")


def require_upstream_birthday_draw():
    try:
        installed = importlib.metadata.version("policyengine-uk")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("PolicyEngine UK is not installed")
    if tuple(map(int, installed.split(".")[:3])) < (2, 118, 0):
        pytest.skip("The 2.90.2 runtime is not an exact legal-cutoff/birthday oracle")
    stochastic = pytest.importorskip("policyengine_uk.utils.stochastic")
    if not hasattr(stochastic, "stratified_uniform"):
        pytest.skip("This runtime does not expose the newer upstream birthday draw")
    return stochastic


def test_upstream_2118_draw_and_birth_dates_are_exact_differential_oracles():
    stochastic = require_upstream_birthday_draw()
    splitmix64_uniform, stratified_uniform = stochastic.splitmix64_uniform, stochastic.stratified_uniform
    from policyengine_uk.utils.state_pension_age import date_of_birth

    ids = np.arange(1, 201)
    ages = np.tile(np.arange(60, 80), 10)
    female = ids % 3 == 0
    weights = (ids * 7919) % 1000 + 1
    upstream_months = (12 * stratified_uniform(ages * 2 + ~female,
                                             splitmix64_uniform(ids, salt=2), weights)).astype(np.float32)
    months = within_year_birth_months(ids, ages, female, weights)
    np.testing.assert_array_equal(months, upstream_months)
    _, integer_dates = date_of_birth(ages, months, 2026)
    formatted = [f"{d // 10000:04d}-{d // 100 % 100:02d}-{d % 100:02d}" for d in integer_dates]
    np.testing.assert_array_equal(birth_dates_from_age(ages, months, 2026), np.asarray(formatted, dtype="datetime64[D]"))


def test_upstream_2118_cohort_types_agree_for_the_same_birth_draw_every_year(monkeypatch):
    require_upstream_birthday_draw()
    from policyengine_uk import Simulation
    from policyengine_uk.tax_benefit_system import system

    # Reuse the already imported model definitions, following upstream's own
    # property-test fixture; populations and parameter tree are still cloned.
    monkeypatch.setattr("policyengine_uk.simulation.CountryTaxBenefitSystem", system.clone)

    years = range(2024, 2040)
    ages = np.tile(np.arange(60, 106), 4)
    ids = np.arange(len(ages))
    female = ids >= len(ages) // 2
    months = within_year_birth_months(ids, ages, female, ids * 17 + 1)
    # Include the exact 5/6 April cutoffs as well as the weighted birth draw.
    ages = np.concatenate([ages, [75, 75, 73, 73]])
    female = np.concatenate([female, [False, False, True, True]])
    months = np.concatenate([months, np.array([6 + 1 / 31, 6, 6 + 1 / 31, 6], dtype=np.float32)])
    people = {f"p{i}": {"age": {y: int(age) for y in years},
                          "is_male": {y: bool(not female[i]) for y in years},
                          "months_since_last_birthday": {y: float(months[i]) for y in years}}
              for i, age in enumerate(ages)}
    members = list(people)
    sim = Simulation(situation={"people": people, "benunits": {"b": {"members": members}},
                                "households": {"h": {"members": members}}})
    for year in years:
        eligible = sim.calculate("is_SP_age", year)
        expected = cohort_type(birth_dates_from_age(ages, months, year), female, eligible)
        calculated = sim.calculate("state_pension_type", year)
        actual = calculated.decode_to_str() if hasattr(calculated, "decode_to_str") else np.asarray(calculated)
        np.testing.assert_array_equal(actual, expected)
