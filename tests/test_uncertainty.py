"""The fixed candidate screen and rebuild handoff: no PolicyEngine or survey data."""

import json
from copy import deepcopy

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import expected_value as EV, rules, ts_annual, ts_monthly
from triple_lock.central import central_path, long_run_earnings_variant, obr_premium_comparator
from triple_lock.config import CALENDAR_YEARS, HORIZON
from triple_lock.ts_backtest import candidate_score, gap_pct, mean_with_overlap_se, wilson_band
from triple_lock.ts_uncertainty import (
    CANDIDATES, PRIMARY_FORM, PROPER_SCORES, adequacy, candidate_paths,
    future_draws, handoff, paired_mean_estimates, sample_design,
)


def test_first_phase_formula_matches_brute_force_monte_carlo():
    """Random first-phase strata counts must contribute between-stratum variance.

    Synthetic empirical strata have known means and variances. Each replicate
    draws N independent observations from the whole mixture, not fixed counts.
    Feed s_h² of that mixture to the plug-in formula and compare var(mean).
    """
    W = {0: 0.2, 1: 0.35, 2: 0.45}
    values = {1: np.array([-1., 1., 3.]), 2: np.array([3., 5., 7., 9.])}
    n = 200
    out = EV.stratified_estimate(values, W, n)
    # With a known-zero stratum, its (0-m)^2 term must be present.
    m = sum(W[k] * v.mean() for k, v in values.items())
    analytic = (W[0] * m*m + sum(W[k] * (v.var(ddof=1) + (v.mean()-m)**2)
                               for k, v in values.items())) / n
    assert out['variance_first_phase'] == pytest.approx(analytic, abs=1e-14)
    rng = np.random.default_rng(9231)
    # Use symmetric two-point distributions whose *population* variances equal s_h².
    rep = rng.choice([0, 1, 2], size=(30_000, n), p=list(W.values()))
    y = np.zeros_like(rep, dtype=float)
    for k, v in values.items():
        count = np.count_nonzero(rep == k)
        y[rep == k] = v.mean() + np.sqrt(v.var(ddof=1)) * rng.choice([-1, 1], count)
    assert np.var(y.mean(axis=1), ddof=1) == pytest.approx(analytic, rel=0.035)
    assert out['se']**2 == pytest.approx(out['variance_first_phase'] + out['variance_path_sampling'])
    assert out['plus_minus_95'] == pytest.approx(1.96 * out['se'])


def test_missing_zero_mass_has_the_same_first_phase_variance():
    vals = {1: [2., 4., 6.]}
    explicit = EV.stratified_estimate(vals, {0: .4, 1: .6}, 100)
    implicit = EV.stratified_estimate(vals, {1: .6}, 100)
    assert explicit == implicit


@pytest.mark.parametrize('budget', [0, 3, 19])
def test_neyman_rejects_impossible_budgets(budget):
    with pytest.raises(ValueError, match='budget'):
        EV.allocate(np.full(20, .05), np.arange(20.), np.repeat(np.arange(1, 11), 2), budget)


def test_neyman_can_include_zero_stratum_for_mean_path_pairs():
    w = np.full(100, .01)
    gap = np.r_[np.zeros(20), np.arange(80.)]
    strata = EV.stratify(w, gap, np.arange(100) < 20)
    alloc = EV.allocate(w, gap, strata, 160, include_zero=True)
    assert sum(alloc.values()) == 160 and min(alloc.values()) >= 2 and alloc[0] == 2
    assert EV.stratify(w, gap, np.ones(100, dtype=bool)).tolist() == [0] * 100


@pytest.mark.parametrize('form', CANDIDATES)
def test_candidates_shift_calendar_means_and_reproduce(form):
    years = [2017, 2018, 2019, 2020]
    target = {y: (0.01 + .003*(y-2017), .02 - .002*(y-2017)) for y in years}
    a, info = candidate_paths(form, years, 150, 41, end_obs=(2015, 12), calendar_target=target)
    b, _ = candidate_paths(form, years, 150, 41, end_obs=(2015, 12), calendar_target=target)
    for j, y in enumerate(years):
        assert a['calendar_cpi'][:, j].mean() == pytest.approx(target[y][0], abs=1e-12)
        assert a['calendar_earnings'][:, j].mean() == pytest.approx(target[y][1], abs=1e-12)
    for key in a:
        np.testing.assert_allclose(a[key], b[key], rtol=0, atol=1e-12)
    if form == 'annual_boot_gap':
        assert max(info['gap_block_starts']) + 3 <= 2015
    else:
        assert info['lag_order'] == CANDIDATES[form]['lag_order']
        assert info['last_observed_month'] == [2015,12]


def test_annual_bridge_preserves_joint_four_year_blocks():
    years, g = ts_annual.statutory_gaps(2010)
    gb = np.array([g[j:j+4] for j in range(len(g)-3)])
    gb -= gb.mean(axis=0, keepdims=True)
    m, _ = ts_annual.paths([2012, 2013, 2014, 2015], 250, 9, end_obs=(2010, 12))
    gap = np.stack([m['statutory_cpi']-m['calendar_cpi'],
                    m['statutory_earnings']-m['calendar_earnings']], axis=2)
    # Future starts in 2011, so target block slices straddle two sampled blocks.
    whole, _ = ts_annual.paths([2011, 2012, 2013, 2014], 250, 9, end_obs=(2010, 12))
    first = np.stack([whole['statutory_cpi']-whole['calendar_cpi'],
                     whole['statutory_earnings']-whole['calendar_earnings']], axis=2)
    assert all(np.any(np.max(np.abs(gb-x), axis=(1,2)) < 1e-12) for x in first)
    assert np.isfinite(gap).all()


@settings(max_examples=5, deadline=None)
@given(st.integers(0, 1000), st.lists(st.tuples(st.floats(-.03, .08), st.floats(-.03, .08)), min_size=4, max_size=4))
def test_arbitrary_target_paths_hit_exactly(seed, targets):
    years = list(range(2027, 2031))
    m, _ = ts_monthly.paths([2026, *years], 100, seed,
                            calendar_target=dict(zip(years, targets)), lag_order=1)
    got = np.stack([m['calendar_cpi'][:, 1:].mean(axis=0),
                    m['calendar_earnings'][:, 1:].mean(axis=0)], axis=1)
    np.testing.assert_allclose(got, targets, atol=1e-12, rtol=0)


def test_mean_path_variants_reuse_exact_shocks_and_change_only_targets():
    central = central_path()
    original = deepcopy(central)
    n, seed = 180, 21
    months, c, e, extra = ts_monthly.levels()
    fit = ts_monthly.fit(months, c, e, lag_order=1)
    # Raw shocks from the shared seed are independent of the deterministic shift.
    a, _ = ts_monthly._shocks(fit, 'boot', n, 30, np.random.default_rng(seed))
    b, _ = ts_monthly._shocks(fit, 'boot', n, 30, np.random.default_rng(seed))
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)
    base = future_draws(PRIMARY_FORM, central, n, seed)
    for delta in [-.005, .005]:
        variant = long_run_earnings_variant(central, delta)
        assert all(variant['calendar']['earnings'][y] == central['calendar']['earnings'][y]
                   for y in CALENDAR_YEARS if y < 2031)
        d = future_draws(PRIMARY_FORM, variant, n, seed)
        assert d['info']['shock_distribution']['innovation_sha256'] == base['info']['shock_distribution']['innovation_sha256']
        target = np.array([[variant['calendar'][v][y] for v in ('cpi', 'earnings')] for y in CALENDAR_YEARS])
        np.testing.assert_allclose(d['calendar'].mean(axis=0), target, rtol=0, atol=1e-12)
        # Monthly drifts are common, but averaging levels is nonlinear: annual
        # growth need not move by a common factor. The innovation digest above
        # covers every actual shock, including the partially observed month.
    assert central == original


@pytest.mark.parametrize('form', CANDIDATES)
def test_rules_for_every_candidate_draw(form):
    d = future_draws(form, central_path(), n=300, seed=27)
    levels, rates = EV.rule_levels(d['stat_cpi'], d['stat_earnings'], 1.)
    c, e = rules.round_rate(d['stat_cpi']), rules.round_rate(d['stat_earnings'])
    bp, tl = levels['burnham_2030'], levels['triple_lock']
    assert np.all(rates['burnham_2030'] >= np.maximum(c, .025) - 1e-12)
    assert np.all(bp <= tl + 1e-12)
    j = HORIZON.index(2030)
    np.testing.assert_allclose(bp[:, j], tl[:, j], rtol=0, atol=1e-12)
    anchor = bp[:, j-1, None] * np.cumprod(1+e[:, j:], axis=1)
    assert np.all(bp[:, j:] >= anchor - 1e-12)
    design = sample_design(d, n_runs=120)
    assert sum(design['allocation'].values()) == 120
    assert min(design['allocation'].values()) >= 2


def passing_backtest():
    summary = {'n_origins': 12, 'expected_origins': 12}
    for k in PROPER_SCORES:
        summary[k] = {'mean': 1.}
    for k in ('gap_bias_pp','switch_bias','floor_bias'):
        summary[k] = {'mean': 0.}
    summary['annual_gap_coverage'] = {'mean': .8}
    summary['terminal_coverage'] = {'mean': .8, 'wilson95_independent': [.5,.95]}
    return {'scores': {test: {t: {f: deepcopy(summary) for f in CANDIDATES}
                              for t in ('published','suspended')} for test in ('A','B')},
            'past_years': {f: {t: {'realised_percentile': 50.} for t in ('published','suspended')}
                          for f in CANDIDATES}}


def test_screen_retains_primary_and_rejects_undercoverage_in_either_treatment():
    backtest = passing_backtest()
    assert adequacy(backtest)['selected_primary'] == PRIMARY_FORM
    backtest['scores']['A']['published'][PRIMARY_FORM]['terminal_coverage']['mean'] = 1/6
    screen = adequacy(backtest)
    assert not screen['forms'][PRIMARY_FORM]['passes']
    assert screen['selected_primary'] == 'monthly_var2_boot'
    for f in CANDIDATES:
        backtest['past_years'][f]['suspended']['realised_percentile'] = 99.
    assert adequacy(backtest)['selected_primary'] is None


@pytest.mark.parametrize('field', ['gap_bias_pp', 'floor_bias', 'switch_bias', 'variogram'])
def test_screen_is_not_coverage_only(field):
    backtest = passing_backtest()
    backtest['scores']['B']['suspended']['annual_boot_gap'][field]['mean'] = 2.
    assert not adequacy(backtest)['forms']['annual_boot_gap']['passes']


def test_floor_score_means_earnings_below_floor_not_both_inputs():
    observed = np.array([[.05,.01],[.01,.03],[.01,.02],[.03,.04]])
    s = candidate_score(np.repeat(observed[None], 40, axis=0), observed)
    assert s['predicted_floor_frequency'] == .5
    assert s['floor_crps'] == pytest.approx(0., abs=1e-12)
    assert s['gap_bias_pp'] == pytest.approx(0., abs=1e-12)
    assert s['predicted_switches'] == s['realised_switches']


def test_bias_sign_and_overlap_standard_error():
    y = np.full((4,2), .02)
    x = np.repeat(y[None], 100, axis=0)
    x[:,:,1] += .01
    assert candidate_score(x,y)['gap_bias_pp'] == pytest.approx(1.)
    s = mean_with_overlap_se([0,0,0,0,1,1,1,1,2,2,2,2])
    assert s['se_overlap_hac'] > s['se_independent']
    assert wilson_band(6,6)[0] <= .8 <= wilson_band(6,6)[1]
    assert wilson_band(1,6)[1] < .8


def test_paired_mean_estimator_keeps_changed_zero_stratum():
    design = {'sample': {0: [0,1], 1: [2,3]}, 'stratum_weights': {0: .4, 1: .6}}
    baseline = {i: {'saving_bn': {y: {'gross': 0., 'net': 0.} for y in HORIZON}} for i in range(4)}
    variant = deepcopy(baseline)
    for y in HORIZON:
        variant[0]['saving_bn'][y]['gross'] = 1.
        variant[1]['saving_bn'][y]['gross'] = 3.
    out = paired_mean_estimates(design, baseline, variant, 100)
    for y in (2034,2039):
        assert out['gross'][y]['mean'] == pytest.approx(.8)
        assert out['gross'][y]['se_first_phase'] > 0
        assert out['gross'][y]['plus_minus_95'] > 0


def test_handoff_blocks_failed_forms_and_pairs_same_indices(tmp_path):
    screen = {'passing_forms': []}
    manifest = handoff(tmp_path, screen, n=150, n_runs=30, log=lambda _: None)
    assert list(manifest['forms']) == [PRIMARY_FORM]
    assert not manifest['forms'][PRIMARY_FORM]['fiscal_eligible']
    base = json.loads((tmp_path / f'{PRIMARY_FORM}.specs.json').read_text())
    baseline_arrays = dict(np.load(tmp_path / f'{PRIMARY_FORM}.npz'))
    for label, metadata in manifest['mean_paths'].items():
        specs = json.loads((tmp_path / metadata['specs_file']).read_text())
        assert metadata['fiscal_eligible']
        assert metadata['interpretation'] == 'scenario'
        assert metadata['presentation_pending_d955']
        assert [s['id'] for s in specs] == [s['id'] for s in base]
        arrays = dict(np.load(tmp_path / f'{label}.npz'))
        for spec in specs:
            i = int(spec['id'].removeprefix('draw_'))
            for j, year in enumerate(HORIZON):
                assert spec['statutory_cpi'][str(year-1)] == arrays['stat_cpi'][i,j]
                assert spec['statutory_earnings'][str(year-1)] == arrays['stat_earnings'][i,j]
                assert spec['earnings'][str(year)] == arrays['calendar'][i,j,1]
        np.testing.assert_allclose(arrays['stat_cpi'], baseline_arrays['stat_cpi'], rtol=0, atol=1e-12)
        assert not metadata['extra_check_requires_zero_saving']
    assert obr_premium_comparator(central_path()) == pytest.approx(.5571666666667)


def test_build_without_ruling_stops_before_engine_import(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('draw generation or engine work must not start')
    monkeypatch.setattr(EV, 'draws', forbidden)
    with pytest.raises(ValueError, match='d955'):
        EV.build({}, 1., adequacy_report={'passing_forms': []})


def test_reweightings_below_100_effective_runs_are_excluded_from_range():
    # Equal weights give 40 effective full runs, independent of macro-draw ESS.
    sample = {1: list(range(40))}
    results = {i: {'saving_bn': {y: {'gross': float(i), 'net': float(i)/2} for y in HORIZON}}
               for i in range(40)}
    w = np.full(40, 1/40)
    s = EV.reweighted(sample, results, {1: 1.}, w, w)
    assert s['effective_runs'] == pytest.approx(40.)
    assert not s['included_in_quoted_range']
    for y in (2034,2039):
        assert s['gross'][y]['se_first_phase'] > 0
        assert s['gross'][y]['plus_minus_95'] > 0


def test_published_estimator_preserves_means_and_updates_every_se():
    """Public aggregate outputs are sufficient; no survey data or engine needed."""
    from pathlib import Path
    ev = json.loads((Path(__file__).parents[1] / 'data/results.json').read_text())['expected_value']
    updated = EV.reestimate_published(ev)
    assert updated['diagnostic_only']
    for dataset, outputs in ev['estimates'].items():
        for key, years in outputs.items():
            for year, old in years.items():
                new = updated['estimates'][dataset][key][int(year)]
                assert new['mean'] == pytest.approx(old['mean'], abs=1e-12)
                assert new['se_path_sampling'] == pytest.approx(old['se'], abs=1e-12)
                assert new['se']**2 == pytest.approx(old['se']**2 + new['variance_first_phase'], abs=1e-12)
                assert new['plus_minus_95'] == pytest.approx(1.96*new['se'])
    for name, old in ev['sensitivities'].items():
        row = updated['sensitivities'][name]
        assert row['included_in_quoted_range'] == (old['effective_runs'] >= 100)
        for key in ('gross', 'net'):
            for year in ('2034','2039'):
                assert row[key][int(year)]['mean'] == pytest.approx(old[key][year]['mean'], abs=1e-12)
                assert row[key][int(year)]['se_path_sampling'] == pytest.approx(old[key][year]['se'], abs=1e-12)
    for key, years in ev['paired_difference'].items():
        for year, old in years.items():
            new = updated['paired_difference'][key][int(year)]
            assert new['mean'] == pytest.approx(old['mean'], abs=1e-12)
            assert new['se_path_sampling'] == pytest.approx(old['se'], abs=1e-12)


def test_no_ruling_is_blocked_even_after_a_passing_gate(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy draws or engine work must not start')
    monkeypatch.setattr(EV, 'draws', forbidden)
    with pytest.raises(ValueError, match='d955'):
        EV.build({}, 1., adequacy_report={'passing_forms': [PRIMARY_FORM]})


def test_committed_screen_and_doc_score_tables_match_artifacts():
    from pathlib import Path
    root = Path(__file__).parents[1] / 'docs'
    scores = json.loads((root/'uncertainty/scores.json').read_text())
    selection = json.loads((root/'uncertainty/selection.json').read_text())
    assert adequacy(scores) == selection
    text = (root/'UNCERTAINTY_PILOT.md').read_text()
    labels = {'monthly_var1_boot': 'VAR(1) bootstrap', 'monthly_var2_boot': 'VAR(2) bootstrap',
              'annual_boot_gap': 'Annual bootstrap + gap blocks', 'monthly_var1_tcop': 'VAR(1) Student-t',
              'monthly_var1_gauss': 'VAR(1) Gaussian'}
    for test in ('A','B'):
        for treatment in ('published','suspended'):
            for form,row in scores['scores'][test][treatment].items():
                metrics = [f"{row[k]['mean']:.3f} ± {row[k]['se_overlap_hac']:.3f}" for k in PROPER_SCORES]
                expected = '| '+' | '.join([test+' / '+treatment,labels[form],*metrics])+' |'
                assert expected in text


def test_backtest_suspension_and_training_boundary_are_applied(monkeypatch):
    from triple_lock import ts_backtest as TB, ts_uncertainty as TU
    calls=[]
    def fake_paths(form, years, n, seed, end_obs=None, calendar_target=None):
        calls.append((years,end_obs,calendar_target))
        assert end_obs == (years[0]-2,12)
        assert calendar_target is None or set(calendar_target) == set(years)
        c = np.full((n,len(years)),.02)
        e = np.full_like(c,.03)
        if 2021 in years:
            e[:,years.index(2021)] = .10
        return {'statutory_cpi':c,'statutory_earnings':e,'calendar_cpi':c,'calendar_earnings':e}, {}
    monkeypatch.setattr(TU,'CANDIDATES',{PRIMARY_FORM: {'lag_order':1,'kind':'boot'}})
    def with_past(form,years,n,seed,end_obs=None,calendar_target=None):
        if years[0] == 2011 and len(years) == 15:
            # Past fit ends in 2010; unlike forecast targets, simulation starts immediately.
            assert end_obs == (2010,12)
            adjusted = (years[0]-2,12)
            return fake_paths(form,years,n,seed,adjusted,calendar_target)
        return fake_paths(form,years,n,seed,end_obs,calendar_target)
    monkeypatch.setattr(TU,'candidate_paths',with_past)
    result=TB.run_candidate_backtest(n=30,log=lambda _:None)
    row=next(r for r in result['rows'] if r['origin_year']==2017 and r['treatment']=='suspended')
    years=row['target_years']
    observed=TB.statutory_outturns(suspend_2022=True)
    realised=np.array([observed[y] for y in years])
    d=np.full((30,4,2),[.02,.03])
    d[:,years.index(2021),1] = .02
    correct=TB.candidate_score(d,realised,2017)
    assert row['gap_crps'] == pytest.approx(correct['gap_crps'])
    assert row['terminal_bias_pp'] == pytest.approx(correct['terminal_bias_pp'])
    assert not result['failures']


def test_monthly_fit_receives_only_pre_origin_months(monkeypatch):
    original=ts_monthly.fit
    seen=[]
    def fit(months,cpi,awe,**kwargs):
        seen.extend(months)
        assert max(months) <= (2015,12)
        return original(months,cpi,awe,**kwargs)
    monkeypatch.setattr(ts_monthly,'fit',fit)
    candidate_paths(PRIMARY_FORM,[2017,2018,2019,2020],30,1,end_obs=(2015,12))
    assert seen and max(seen) == (2015,12)


def test_historical_artifact_is_reproducible_from_repo_code(tmp_path):
    from pathlib import Path
    from triple_lock.ts_uncertainty import write_historical_estimator
    committed=json.loads((Path(__file__).parents[1]/'docs/uncertainty/historical_estimator.json').read_text())
    regenerated = write_historical_estimator(tmp_path)
    assert json.loads(json.dumps(regenerated)) == committed
    assert json.loads((tmp_path/'historical_estimator.json').read_text()) == committed


def test_nonfinite_scores_and_past_percentiles_fail_the_screen():
    result=passing_backtest()
    result['scores']['A']['published'][PRIMARY_FORM]['gap_bias_pp']['mean'] = float('nan')
    assert not adequacy(result)['forms'][PRIMARY_FORM]['passes']
    result=passing_backtest()
    result['past_years'][PRIMARY_FORM]['published']['realised_percentile'] = float('nan')
    assert not adequacy(result)['forms'][PRIMARY_FORM]['passes']


def test_scipy_dependency_is_pinned():
    import tomllib
    from pathlib import Path
    project=tomllib.loads((Path(__file__).parents[1]/'pyproject.toml').read_text())
    assert 'scipy==1.18.1' in project['project']['dependencies']
