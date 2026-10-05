"""Properties of input calibration, independent of private survey records."""

import numpy as np
from scipy import sparse
import pytest
from hypothesis import given, settings, strategies as st

from triple_lock.demography import (AGE_BANDS, InfeasibleTargets, age_cells, annual_weights,
    anchored_targets, fiscal_population, household_incidence, payable_reported, pension_components,
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




@st.composite
def anchored_years(draw):
    """Weights in a data year, an anchor year and later years, households in age cells, and any positive cell growth
    the bounded rake can reach (singleton support, ratios within its bounds)."""
    n = draw(st.integers(2, 10))
    cells = draw(st.lists(st.integers(0, 2 * len(AGE_BANDS) - 1), min_size=n, max_size=n, unique=True))
    incidence = household_incidence(np.arange(n), np.array(cells), n)
    data_year = draw(st.integers(2023, 2025))
    anchor = draw(st.integers(data_year, 2026))
    last = draw(st.integers(anchor, 2040))
    base = np.array(draw(st.lists(st.floats(1, 1e4, allow_nan=False), min_size=n, max_size=n)))
    native = {y: base * (1 + 0.004) ** (y - data_year) for y in range(data_year, last + 1)}
    growth = {y: np.array(draw(st.lists(st.floats(0.5, 2.0, allow_nan=False), min_size=2 * len(AGE_BANDS),
                                        max_size=2 * len(AGE_BANDS)))) for y in range(anchor + 1, last + 1)}
    return native, anchor, incidence, growth


@settings(max_examples=80, deadline=None)
@given(anchored_years())
def test_raked_weights_equal_the_base_weights_through_the_calibration_year_for_any_growth(case):
    """The anchoring property (#14 section 3): whatever growth the projection gives, the raked weights in the anchor
    (calibration) year and every year before it are the dataset's own, exactly; later years hit their targets."""
    native, anchor, incidence, growth = case
    raked = annual_weights(native, anchor, incidence, growth)
    for y, weights in raked.items():
        if y <= anchor:
            assert np.array_equal(weights, native[y]), y
        else:
            margins = np.asarray(incidence @ native[anchor]).ravel()
            assert np.asarray(incidence @ weights).ravel() == pytest.approx(margins * growth[y], rel=1e-6)
    assert annual_weights(native, anchor, incidence, growth, rake=False).keys() == native.keys()
    for y, weights in annual_weights(native, anchor, incidence, growth, rake=False).items():
        assert np.array_equal(weights, native[y])


def test_an_anchor_without_weights_fails():
    with pytest.raises(ValueError, match="anchor"):
        annual_weights({2024: np.ones(2)}, 2025, np.eye(2), {})


@given(st.lists(st.tuples(st.floats(0, 50000, allow_nan=False), st.booleans()), min_size=1, max_size=30),
       st.sampled_from(["BASIC", "NEW"]))
def test_payable_reports_and_components_add_up_for_every_record(rows, kind):
    """With the below-pension-age rule, basic + new + additional equals the counted report for every record, and
    the excess over the flat rate never goes negative."""
    reported = np.array([r for r, _ in rows])
    over = np.array([o for _, o in rows])
    payable = payable_reported(reported, over)
    types = np.where(over, kind, "NONE")
    basic, new, additional = pension_components(payable, types, 9000, 12000)
    np.testing.assert_allclose(basic + new + additional, payable, rtol=0, atol=1e-9)
    assert np.all(payable[~over] == 0) and np.all(additional >= 0)


@settings(max_examples=60, deadline=None)
@given(feasible_rakes(), st.lists(st.booleans(), min_size=1, max_size=13))
def test_households_without_weight_keep_none_and_the_rest_are_raked(case, zero):
    """Microcosm holds households of zero weight: they stay at zero and the others hit the targets."""
    weights, incidence, _ = case
    zero = np.resize(np.asarray(zero), len(weights))
    zero[-1] = False  # the household in every cell keeps each cell supported
    base = np.where(zero, 0.0, weights)
    growth = np.linspace(0.6, 1.8, len(weights))  # a feasible reweighting within the 0.2-5 bounds
    targets = incidence @ (base * growth)
    result = rake_households(base, incidence, targets)
    assert np.all(result[zero] == 0) and np.all(result[~zero] > 0)
    assert incidence @ result == pytest.approx(targets, rel=1e-6)


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(1, 1e4, allow_nan=False), min_size=4, max_size=10), st.integers(0, 3),
       st.floats(0.6, 1.6, allow_nan=False))
def test_anchoring_holds_with_households_of_no_weight(weights, n_zero, growth):
    """With zero-weight households (Microcosm), the weights through the anchor are still the dataset's own, a cell
    only they support has no target and no weight, and the other cells hit their targets."""
    n = len(weights)
    base = np.array(weights)
    base[:n_zero] = 0.0
    cells = np.arange(n)  # one household per cell: the zero households' cells are supported by nobody with weight
    incidence = household_incidence(np.arange(n), cells, n)
    native = {2024: base / 1.0072, 2025: base, 2026: base * 1.0038}
    g = {2026: np.full(2 * len(AGE_BANDS), growth)}
    raked = annual_weights(native, 2025, incidence, g)
    assert np.array_equal(raked[2024], native[2024]) and np.array_equal(raked[2025], native[2025])
    assert np.all(raked[2026][:n_zero] == 0)
    margins = np.asarray(incidence @ base).ravel()
    assert np.asarray(incidence @ raked[2026]).ravel() == pytest.approx(margins * growth, rel=1e-6)


def test_rake_reaches_feasible_targets_where_least_squares_stalls_on_a_bound():
    """Hypothesis found this: feasible targets (each household's weight times a ratio in [0.5, 2]) where least
    squares on the residual stalls at a 21% miss because one weight sits on its lower bound. The dual Newton fallback
    reaches them, within the 0.2-5 bounds."""
    w = np.array([4., 2., 2., 2., 2., 1., 0.25, 0.25, 2.])
    a = np.concatenate([np.eye(8), np.ones((8, 1))], axis=1)
    targets = np.array([10., 6., 6., 6., 6., 4., 2.25, 2.5])
    result = rake_households(w, a, targets)
    assert a @ result == pytest.approx(targets, rel=1e-6)
    assert np.all(result >= 0.2 * w * (1 - 1e-12)) and np.all(result <= 5 * w * (1 + 1e-12))


def test_the_dual_fallback_alone_reaches_the_targets(monkeypatch):
    """With least squares made to return its start point, the rake reaches the targets through the dual fallback
    alone (so the case above exercises it whatever least squares does)."""
    from types import SimpleNamespace

    from triple_lock import demography

    monkeypatch.setattr(demography, "least_squares", lambda fun, x0, **kwargs: SimpleNamespace(x=x0))
    w = np.array([4., 2., 2., 2., 2., 1., 0.25, 0.25, 2.])
    a = np.concatenate([np.eye(8), np.ones((8, 1))], axis=1)
    targets = np.array([10., 6., 6., 6., 6., 4., 2.25, 2.5])
    result = demography.rake_households(w, a, targets)
    assert a @ result == pytest.approx(targets, rel=1e-6)
    # And it fails closed on targets every cell's bounds allow but no weights meet together (cells 0 and 1 need
    # both weights at 5, cell 2 their sum at 2): the per-cell checks pass, so this reaches the fallback.
    with pytest.raises(demography.InfeasibleTargets):
        demography.rake_households(np.ones(2), np.array([[1., 0.], [0., 1.], [1., 1.]]), np.array([5., 5., 2.]))


@settings(max_examples=40, deadline=None)
@given(feasible_rakes(), st.integers(1, 6), st.floats(0.05, 2, allow_nan=False))
def test_the_dual_ascent_returns_the_best_point_it_visited(case, iterations, shake):
    """Whatever it is capped at and wherever it starts, the dual ascent returns the point with the smallest miss it
    visited (a later iterate can miss by more), so it never does worse than where least squares left it."""
    from triple_lock import demography

    weights, incidence, targets = case
    total = weights.sum()
    a = sparse.csr_matrix(incidence, dtype=float)
    c = a.multiply((total / targets)[:, None]).tocsr()
    wn = weights / total
    lo, hi = np.log(0.2), np.log(5.0)

    def missed(lam):
        w = wn * np.exp(np.clip(np.asarray(c.T @ lam).ravel(), lo, hi))
        return float(np.max(np.abs(np.asarray(a @ (w * total)).ravel() / targets - 1)))

    start = np.full(len(targets), shake)
    best, misses = demography._ascend(start, c, wn, lo, hi, missed, 0.0, iterations=iterations)
    assert missed(best) == min(misses) and missed(best) <= missed(start)
