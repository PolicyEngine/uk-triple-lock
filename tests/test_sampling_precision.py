"""First-phase precision for reweighted macro draws, without survey data."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import expected_value as EV
from triple_lock.config import HORIZON


@settings(max_examples=80, deadline=None)
@given(n=st.integers(2, 500), scale=st.floats(1e-8, 1e8, allow_nan=False, allow_infinity=False))
def test_equal_draw_weights_reduce_to_plain_first_phase_formula(n, scale):
    values = {1: [-2., 0., 2.], 2: [3., 5., 7.]}
    probabilities = {0: .2, 1: .3, 2: .5}
    plain = EV.stratified_estimate(values, probabilities, n)
    equal = EV.stratified_estimate(
        values, probabilities, n, first_phase_effective_n=EV.effective_sample_size(np.full(n, scale)))
    assert EV.effective_sample_size(np.full(n, scale)) == pytest.approx(n)
    assert equal == pytest.approx(plain)
    for v in values.values():
        mean, variance = EV._weighted_moments(v, np.full(len(v), scale))
        assert mean == pytest.approx(np.mean(v))
        assert variance == pytest.approx(np.var(v, ddof=1))


def test_reweighted_first_phase_uses_target_moments_and_macro_draw_ess():
    primary = np.full(6, 1 / 6)
    other = np.array([.05, .05, .1, .1, .35, .35])
    strata = np.repeat([0, 1, 2], 2)
    sample = {1: [2, 3], 2: [4, 5]}
    probabilities = {1: 1 / 3, 2: 1 / 3}
    outcome = [0., 0., 1., 3., 4., 8.]
    runs = {i: {'saving_bn': {y: {'gross': value, 'net': value / 2} for y in HORIZON}}
            for i, value in enumerate(outcome)}
    estimate = EV.reweighted(sample, runs, probabilities, primary, other, strata=strata)
    pseudo = {k: [outcome[i] * other[i] / primary[i] for i in idx] for k, idx in sample.items()}
    old = EV.stratified_estimate(pseudo, probabilities, len(other))
    moments = {1: (.2, 2., 2.), 2: (.7, 6., 8.)}
    target_mean = sum(p * mean for p, mean, _ in moments.values())
    numerator = (.1 * target_mean**2 + sum(
        p * (variance + (mean - target_mean)**2) for p, mean, variance in moments.values()))
    ess = 1 / np.sum(other**2)
    gross = estimate['gross'][2039]
    assert estimate['first_phase_effective_n'] == pytest.approx(ess)
    assert estimate['first_phase_stratum_probabilities'] == pytest.approx({1: .2, 2: .7})
    assert gross['mean'] == pytest.approx(old['mean'])
    assert gross['variance_path_sampling'] == pytest.approx(old['variance_path_sampling'])
    assert gross['variance_first_phase'] == pytest.approx(numerator / ess)
    # Dividing the r*y variance by ESS would count the weighting a second time.
    assert gross['variance_first_phase'] != pytest.approx(old['variance_first_phase'] * len(other) / ess)
    with pytest.raises(ValueError, match='full first-phase stratum labels'):
        EV.reweighted(sample, runs, probabilities, primary, other)


def test_unequal_weight_first_phase_matches_brute_force_monte_carlo():
    """Conditional weights independent of outcomes: Var(weighted mean)=Var(Y)/ESS.

    Each replicate samples strata randomly, including a known-zero stratum,
    rather than fixing their counts. Fixed unequal draw weights exercise both
    the within-stratum and between-stratum contribution to first-phase error.
    This is the plug-in approximation's assumption, not a calibration claim.
    """
    rng = np.random.default_rng(20160406)
    draw_weights = np.tile([1., 2., 3., 16.], 30)
    draw_weights /= draw_weights.sum()
    probabilities = {0: .2, 1: .3, 2: .5}
    values = {1: [-2., 0., 2.], 2: [3., 5., 7.]}
    estimate = EV.stratified_estimate(
        values, probabilities, len(draw_weights),
        first_phase_effective_n=EV.effective_sample_size(draw_weights))
    strata = rng.choice(3, size=(25_000, len(draw_weights)), p=list(probabilities.values()))
    outcomes = np.zeros(strata.shape)
    for k, v in values.items():
        mask = strata == k
        outcomes[mask] = np.mean(v) + np.sqrt(np.var(v, ddof=1)) * rng.choice([-1., 1.], mask.sum())
    monte_carlo = np.var(outcomes @ draw_weights, ddof=1)
    assert monte_carlo == pytest.approx(estimate['variance_first_phase'], rel=.035)
    plain = EV.stratified_estimate(values, probabilities, len(draw_weights))
    assert estimate['variance_first_phase'] > 2 * plain['variance_first_phase']


def test_published_reweighting_reconstructs_exact_target_masses_and_ess():
    primary = np.full(6, 1 / 6)
    other = np.array([.05, .05, .1, .1, .35, .35])
    sample = {1: [2, 3], 2: [4, 5]}
    probabilities = {1: 1 / 3, 2: 1 / 3}
    outcome = [0., 0., 1., 3., 4., 8.]
    runs = {i: {'saving_bn': {y: {'gross': value, 'net': value / 2} for y in HORIZON}}
            for i, value in enumerate(outcome)}
    sensitivity = EV.reweighted(sample, runs, probabilities, primary, other,
                                strata=np.repeat([0, 1, 2], 2))
    published = {
        'primary': 'synthetic', 'draws': {'n': 6},
        'strata': [{'stratum': k, 'probability': p} for k, p in probabilities.items()],
        'calibrations': {'tilted': {'ess': sensitivity['first_phase_effective_n']}},
        'estimates': {}, 'paired_difference': {}, 'sensitivities': {'tilted': sensitivity},
        'paths': [{'stratum': k, 'times_drawn': 1,
                   'weight_ratio': {'tilted': float(other[i] / primary[i])},
                   'outputs': {'primary': {key: {str(y): runs[i]['saving_bn'][y][key] for y in HORIZON}
                                            for key in EV.OUTPUTS}}}
                  for k, indices in sample.items() for i in indices],
    }
    reconstructed = EV.reestimate_published(published)['sensitivities']['tilted']
    assert not reconstructed['first_phase_masses_approximate']
    assert reconstructed['first_phase_effective_n'] == pytest.approx(sensitivity['first_phase_effective_n'])
    for key in EV.OUTPUTS:
        for y in HORIZON:
            assert reconstructed[key][y] == pytest.approx(sensitivity[key][y])


@pytest.mark.parametrize('weights', [[], [0., 0.], [-1., 2.], [np.inf, 1.], [np.nan, 1.]])
def test_effective_sample_size_refuses_invalid_weights(weights):
    with pytest.raises(ValueError, match='draw weights'):
        EV.effective_sample_size(weights)
