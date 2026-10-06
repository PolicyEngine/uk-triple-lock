"""The C1/C2 adapters execute only fake engine jobs; no private data or PE run."""

import json
import shutil
import sys
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from triple_lock import expected_value as EV, ts_backtest as TB, ts_uncertainty as TU
from triple_lock.central import central_path
from triple_lock.config import CALENDAR_YEARS, HORIZON, STATUTORY_YEARS


def backtest():
    score = {'n_origins': 12, 'expected_origins': 12,
             **{key: {'mean': 1.} for key in TU.PROPER_SCORES},
             **{key: {'mean': 0.} for key in ('gap_bias_pp', 'switch_bias', 'floor_bias')},
             'annual_gap_coverage': {'mean': .8},
             'terminal_coverage': {'mean': .8, 'wilson95_independent': [.5, .95]}}
    return {'scores': {test: {t: {f: deepcopy(score) for f in TU.CANDIDATES}
                             for t in ('published', 'suspended')} for test in ('A', 'B')},
            'past_years': {f: {t: {'realised_percentile': 50.} for t in ('published', 'suspended')}
                          for f in TU.CANDIDATES}}


@pytest.fixture(scope='module')
def base_artifact(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('synthetic-handoff')
    monkeypatch = pytest.MonkeyPatch()
    central = central_path()

    def future(form, inputs, n=50_000, seed=EV.SEED):
        cpi = np.full((n, len(STATUTORY_YEARS)), .02)
        earnings = np.full_like(cpi, .04)
        # A known-zero mass plus continuous positive gaps, from public synthetic arrays.
        cpi[:n // 10, 5::2] = .038
        cpi[n // 10:, 5::2] = np.linspace(.041, .09, n - n // 10)[:, None]
        delta = inputs['calendar']['earnings'][2035] - central['calendar']['earnings'][2035]
        earnings[:, 5:] += delta
        calendar = np.broadcast_to(np.array([[inputs['calendar'][key][y]
                                              for key in ('cpi', 'earnings')]
                                             for y in CALENDAR_YEARS]),
                                   (n, len(CALENDAR_YEARS), 2)).copy()
        return {'stat_cpi': cpi, 'stat_earnings': earnings, 'calendar': calendar,
                'info': {'shock_distribution': {'innovation_sha256': 'synthetic-shared-shocks'}}}

    monkeypatch.setattr(TU, 'future_draws', future)
    # Choose a synthetic fixture with all 160 slots distinct and a separate
    # identical-rates check, matching the committed pilot's 161-run shape.
    def distinct_sample(w, strata, allocation, seed=EV.SAMPLE_SEED):
        return {k: np.flatnonzero(strata == k)[1:count + 1].tolist()
                for k, count in allocation.items()}
    monkeypatch.setattr(EV, 'draw_sample', distinct_sample)
    # No historical calibrations are needed to test the execution adapter.
    monkeypatch.setattr(EV, 'HISTORY_WINDOWS', {})
    monkeypatch.setattr(EV, 'ev_backtest', lambda: {'diagnostic_only': True})
    monkeypatch.setattr(EV, 'past_years_check', lambda: {'diagnostic_only': True})
    manifest = TU.handoff(tmp_path, {'passing_forms': [TU.PRIMARY_FORM, 'monthly_var2_boot']},
                          log=lambda _: None, central=central, uncertainty_ruling='b')
    monkeypatch.undo()
    yield central, tmp_path, manifest


@pytest.fixture
def artifact(base_artifact, tmp_path, monkeypatch):
    central, source, manifest = base_artifact
    output = tmp_path / 'handoff'
    shutil.copytree(source, output)
    monkeypatch.setattr(EV, 'HISTORY_WINDOWS', {})
    monkeypatch.setattr(EV, 'ev_backtest', lambda: {'diagnostic_only': True})
    monkeypatch.setattr(EV, 'past_years_check', lambda: {'diagnostic_only': True})
    return central, output, deepcopy(manifest)


def test_replacement_slot_duplicates_run_once_but_keep_multiplicities(artifact):
    central, output, manifest = artifact
    primary = manifest['forms'][TU.PRIMARY_FORM]
    design = primary['design']
    indices = design['sample'][next(k for k in design['sample'] if int(k) > 0)]
    removed = indices[-1]
    indices[-1] = indices[0]
    primary['unique_full_runs'] -= 1
    specs_path = output / primary['specs_file']
    specs = [s for s in json.loads(specs_path.read_text()) if s['id'] != f'draw_{removed}']
    specs_path.write_text(json.dumps(specs))
    (output / 'handoff.json').write_text(json.dumps(manifest))
    calls = []
    result = EV.build(central, 1., uncertainty_ruling='b', adequacy_report={'passing_forms': []},
                      handoff_path=output, runner=fake_engine(calls), mean_paths=False)
    assert result['sample_slots'] == 160
    assert result['unique_full_runs'] == 160
    assert len(calls[0][0]) == 160
    assert next(p for p in result['paths'] if p['draw'] == indices[0])['times_drawn'] == 2


def fake_engine(calls, *, broken_zero=False):
    def run(jobs, **kwargs):
        calls.append((jobs, kwargs))
        results = []
        for kind, spec in jobs:
            assert kind == 'path'
            cpi = np.array([[spec['statutory_cpi'][str(y)] for y in STATUTORY_YEARS]])
            earnings = np.array([[spec['statutory_earnings'][str(y)] for y in STATUTORY_YEARS]])
            levels, rates = EV.rule_levels(cpi, earnings, 1.)
            gaps = (levels['triple_lock'] - levels['burnham_2030'])[0]
            if broken_zero and not gaps.any():
                gaps[:] = 1.
            multiplier = 2. if spec.get('dataset') else 1.
            results.append({'dataset': spec.get('dataset', 'synthetic-primary'),
                'saving_bn': {y: {'gross': float(gaps[j]) * multiplier,
                                  'net': float(gaps[j]) * multiplier / 2,
                                  'household_income_change': -float(gaps[j]) * multiplier / 2,
                                  'gb': {'gross': float(gaps[j]) * multiplier * .9,
                                         'net': float(gaps[j]) * multiplier * .45},
                                  'components': {'pension_credit': float(gaps[j]) * multiplier / 10}}
                              for j, y in enumerate(HORIZON)},
                'totals_bn': {'triple_lock': {y: {'state_pension_flat_rate': 200.} for y in HORIZON}},
                'households_affected': {y: {'losing_pct': 0.} for y in HORIZON},
                'record_diagnostics_suppressed': True,
                'statutory': {'cpi': spec['statutory_cpi'], 'earnings': spec['statutory_earnings']},
                'rates': {policy: dict(zip(HORIZON, values[0].tolist())) for policy, values in rates.items()}})
        return results
    return run


def test_no_ruling_refuses_before_any_draw_or_job(monkeypatch):
    monkeypatch.setattr(TU, 'handoff', lambda *a, **kw: pytest.fail('handoff must not start'))
    with pytest.raises(ValueError, match='d955'):
        EV.build({}, 1., adequacy_report={'passing_forms': [TU.PRIMARY_FORM]})


def test_original_primary_executes_160_slots_and_writes_paired_fields(artifact):
    central, output, manifest = artifact
    calls = []
    result = EV.build(central, 1., uncertainty_ruling='b', adequacy_report={'passing_forms': []},
                      handoff_path=output, runner=fake_engine(calls), mean_paths=False)
    assert result['sample_slots'] == 160
    assert result['unique_full_runs'] == 161
    assert len(calls[0][0]) == 161
    assert result['identical_rates']['check_run']['largest_abs_saving_bn'] == 0
    assert result['provenance']['ruling'] == 'b'
    assert 'Model-conditional' in result['interpretation']
    assert result['adequacy']['passing_forms'] == []
    assert 'gross_gb' in result['estimates']['primary']
    assert sum(s['paths'] for s in result['strata']) == 160
    assert sum(s['sensitivity_paths'] for s in result['strata']) == 40
    assert sum(p['times_drawn_sensitivity'] for p in result['paths']) == 40
    assert all('times_drawn_sensitivity' in p for p in result['paths'])
    assert all('probability' in s and 'sensitivity_paths' in s for s in result['strata'])
    assert {k: result['draws'][k] for k in ('n', 'seed', 'shocks')} == {
        'n': 50_000, 'seed': EV.SEED, 'shocks': 'boot'}
    # Round-trip exactly the shape consumed by REBUILD step 3, including the zero mass.
    from triple_lock.ageing_validation import paired_sample
    paired, masses, zero, _ = paired_sample(json.loads(json.dumps({'expected_value': result})))
    assert sum(map(len, paired.values())) == 40
    assert sum(masses.values()) == pytest.approx(1.)
    assert masses[0] == zero


def test_identical_rates_check_can_fail(artifact):
    central, output, _ = artifact
    with pytest.raises(AssertionError, match='identical rates'):
        EV.build(central, 1., uncertainty_ruling='b', adequacy_report={'passing_forms': []},
                 handoff_path=output, runner=fake_engine([], broken_zero=True), mean_paths=False)


def test_ruling_a_skips_expected_value_and_runs_independent_scenarios(artifact):
    central, output, _ = artifact
    calls = []
    result = EV.build(central, 1., uncertainty_ruling='a', handoff_path=output,
                      runner=fake_engine(calls))
    assert result['status'] == 'skipped'
    assert 'estimates' not in result
    assert len(calls) == 3  # baseline plus both mean scenarios; no Microcosm jobs
    assert all(len(jobs) == 161 for jobs, _ in calls)
    scenarios = result['mean_path_scenarios']
    assert not scenarios['adequacy_gate_applies']
    assert scenarios['provenance']['ruling'] == 'a'
    minus = scenarios['scenarios']['earnings_minus_0_5pp']
    assert minus['paired_difference']['gross'][2039]['mean'] != 0
    assert 'component.pension_credit' in minus['paired_difference']


def test_scenarios_without_ruling_run_with_presentation_pending(artifact):
    central, output, _ = artifact
    result = EV.build_mean_path_scenarios(central, 1., handoff_path=output, runner=fake_engine([]))
    assert result['provenance']['presentation_pending']
    assert not result['adequacy_gate_applies']


def test_mean_scenarios_include_nonzero_outcomes_in_baseline_zero_stratum(artifact):
    central, output, manifest = artifact
    design = manifest['forms'][TU.PRIMARY_FORM]['design']
    sample = {int(k): indices for k, indices in design['sample'].items()}
    masses = {int(k): mass for k, mass in design['stratum_weights'].items()}
    assert masses[0] > 0 and len(sample[0]) >= 2
    calls = []
    result = EV.build_mean_path_scenarios(central, 1., handoff_path=output,
                                          runner=fake_engine(calls))
    baseline = {int(spec['id'].removeprefix('draw_')): run
                for (_, spec), run in zip(calls[0][0], fake_engine([])(calls[0][0]))}
    minus = {int(spec['id'].removeprefix('draw_')): run
             for (_, spec), run in zip(calls[1][0], fake_engine([])(calls[1][0]))}
    outcomes = {k: [minus[i]['saving_bn'][2039]['gross']
                    - baseline[i]['saving_bn'][2039]['gross'] for i in indices]
                for k, indices in sample.items()}
    assert np.mean(outcomes[0]) > 0
    expected = sum(masses[k] * np.mean(values) for k, values in outcomes.items())
    omitted_zero = sum(masses[k] * np.mean(values) for k, values in outcomes.items() if k)
    actual = result['scenarios']['earnings_minus_0_5pp']['paired_difference']['gross'][2039]
    assert actual['mean'] == pytest.approx(expected)
    assert actual['mean'] > omitted_zero
    assert actual['se_first_phase'] > 0


def test_mean_scenario_refuses_unsampled_positive_baseline_zero_mass(artifact):
    central, output, manifest = artifact
    primary = manifest['forms'][TU.PRIMARY_FORM]
    design = primary['design']
    zero_key = next(k for k in design['sample'] if int(k) == 0)
    removed = design['sample'].pop(zero_key)
    count = design['allocation'].pop(zero_key)
    nonzero_key = next(iter(design['sample']))
    design['sample'][nonzero_key] += [design['sample'][nonzero_key][0]] * count
    design['allocation'][nonzero_key] += count
    primary['unique_full_runs'] -= len(removed)
    specs_path = output / primary['specs_file']
    specs_path.write_text(json.dumps([s for s in json.loads(specs_path.read_text())
                                     if int(s['id'].removeprefix('draw_')) not in removed]))
    (output / 'handoff.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='variant savings there are not known zero'):
        EV.build_mean_path_scenarios(central, 1., handoff_path=output,
                                      runner=lambda *a, **kw: pytest.fail('jobs must not start'))


def c2_routing_artifact(artifact, monkeypatch, *, primary_passes):
    """Use a frozen synthetic score table and the real C2 validator.

    Only post-Budget input readiness is supplied synthetically; rule/score
    hashes, verdict reconstruction and primary eligibility remain checked.
    """
    central, output, manifest = artifact
    score_table = backtest()
    score_table['origins'] = {'B': list(range(2010, 2022))}
    if not primary_passes:
        score_table['past_years'][TU.PRIMARY_FORM]['suspended']['realised_percentile'] = 99.
    outcome = TU.adequacy(score_table, screen='c2')
    binding_inputs = {'ready': True, 'complete_origins': score_table['origins']['B']}
    manifest.update(TU.c2_metadata(score_table, outcome, binding_inputs, binding=True))
    for form, data in manifest['forms'].items():
        data['fiscal_eligible'] = form == TU.PRIMARY_FORM and primary_passes
        data['diagnostic_only'] = not data['fiscal_eligible']
    (output / 'handoff.json').write_text(json.dumps(manifest))
    validations = []
    validate = TU.validate_c2_handoff

    def validated(value, require_binding=True):
        validations.append((value, require_binding))
        return validate(value, require_binding=require_binding)

    monkeypatch.setattr(TU, 'binding_input_provenance', lambda **kw: binding_inputs)
    monkeypatch.setattr(TU, 'validate_c2_handoff', validated)
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda **kw: pytest.fail('build must not rescore C2'))
    monkeypatch.setattr(EV, 'ev_backtest', lambda: pytest.fail('build must not compute new scores'))
    monkeypatch.setattr(EV, 'past_years_check', lambda: pytest.fail('build must not compute new scores'))
    return central, output, manifest, validations


def test_ruling_c_reads_frozen_screen_and_executes_only_passing_original_primary(artifact, monkeypatch):
    central, output, manifest, validations = c2_routing_artifact(artifact, monkeypatch, primary_passes=True)
    calls = []
    result = EV.build(central, 1., ruling='c', adequacy_report={'passing_forms': []},
                      handoff_path=output, runner=fake_engine(calls), mean_paths=False)
    assert result['form'] == TU.PRIMARY_FORM
    assert result['adequacy'] == manifest['c2_outcome']
    assert len(validations) == 1 and validations[0][1] is True
    assert len(calls) == 2  # primary and paired sensitivity, no alternative forms
    assert result['label'] == 'model-conditional'
    assert result['provenance']['rule_sha'] == TU.C2_PRE_REGISTRATION_COMMIT
    assert result['provenance']['requested_ruling'] == 'c'
    assert result['provenance']['effective_ruling'] == 'c'
    assert result['provenance']['c1_failure'] == manifest['c1_failure']
    assert result['provenance']['score_table_sha256'] == manifest['score_table_sha256']
    assert result['provenance']['c2_scores']['scores'] == manifest['score_table']['scores']
    assert result['provenance']['c2_scores']['past_years'] == manifest['score_table']['past_years']


def test_ruling_c_failing_primary_falls_back_even_if_every_alternative_passes(artifact, monkeypatch):
    central, output, manifest, _ = c2_routing_artifact(artifact, monkeypatch, primary_passes=False)
    result = EV.build(central, 1., uncertainty_ruling='c', handoff_path=output, mean_paths=False,
                      runner=lambda *a, **kw: pytest.fail('expected-value jobs must not start'))
    assert result['status'] == 'skipped'
    assert 'estimates' not in result
    assert result['adequacy']['passing_forms'] == [f for f in TU.CANDIDATES if f != TU.PRIMARY_FORM]
    assert result['provenance']['requested_ruling'] == 'c'
    assert result['provenance']['ruling'] == result['provenance']['effective_ruling'] == 'a'
    assert result['provenance']['c2_outcome'] == manifest['c2_outcome']
    assert result['provenance']['c2_scores']['scores'] == manifest['score_table']['scores']
    assert result['provenance']['c2_scores']['past_years'] == manifest['score_table']['past_years']
    assert 'realised percentile 99.00' in result['reason']


def test_ruling_c_fallback_keeps_independent_paired_scenarios(artifact, monkeypatch):
    central, output, _, _ = c2_routing_artifact(artifact, monkeypatch, primary_passes=False)
    calls = []
    result = EV.build(central, 1., uncertainty_ruling='c', handoff_path=output,
                      runner=fake_engine(calls))
    assert result['status'] == 'skipped'
    assert len(calls) == 3  # baseline and both variants; no Microcosm jobs
    assert all(kwargs['slot_prefix'] == 'efrs' for _, kwargs in calls)
    scenarios = result['mean_path_scenarios']
    assert not scenarios['adequacy_gate_applies']
    assert scenarios['provenance'] == result['provenance']
    assert scenarios['provenance']['effective_ruling'] == 'a'
    assert set(scenarios['scenarios']) == {'earnings_minus_0_5pp', 'earnings_plus_0_5pp'}


def test_standalone_c2_scenarios_keep_screen_provenance_without_ev_authorization(artifact, monkeypatch):
    central, output, manifest, validations = c2_routing_artifact(artifact, monkeypatch, primary_passes=False)
    result = EV.build_mean_path_scenarios(central, 1., uncertainty_ruling='c', handoff_path=output,
                                          runner=fake_engine([]))
    assert validations[0][1] is False  # independent scenarios do not require a binding screen
    assert not result['provenance']['expected_value_authorized']
    assert 'independent of the C2 adequacy gate' in result['provenance']['description']
    assert result['provenance']['c2_scores']['scores'] == manifest['score_table']['scores']
    assert result['provenance']['effective_ruling'] == 'a'


def test_ruling_c_missing_frozen_handoff_never_scores_or_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(TU, 'handoff', lambda *a, **kw: pytest.fail('must not create a screen or handoff'))
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda **kw: pytest.fail('must not rescore'))
    with pytest.raises(ValueError, match='frozen C2 handoff'):
        EV.build({}, 1., ruling='c', handoff_path=tmp_path / 'missing',
                 runner=lambda *a, **kw: pytest.fail('jobs must not start'))


def test_ruling_c_refuses_handoff_with_different_committed_rule_sha(artifact):
    central, output, manifest = artifact
    manifest.update(screen='c2', rule_sha='0' * 40)
    (output / 'handoff.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='rule SHA differs from the committed pre-registration'):
        EV.build(central, 1., ruling='c', handoff_path=output,
                 runner=lambda *a, **kw: pytest.fail('jobs must not start'))


def test_ruling_c_refuses_real_validated_dry_run_before_fiscal_jobs(artifact):
    central, output, manifest = artifact
    score_table = backtest()
    outcome = TU.adequacy(score_table, screen='c2')
    manifest.update(TU.c2_metadata(score_table, outcome, {}, binding=False))
    (output / 'handoff.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='dry-run handoff cannot authorize a binding fiscal rebuild'):
        EV.build(central, 1., ruling='c', handoff_path=output,
                 runner=lambda *a, **kw: pytest.fail('jobs must not start'))


def test_conflicting_ruling_alias_refuses_before_handoff(monkeypatch):
    monkeypatch.setattr(TU, 'handoff', lambda *a, **kw: pytest.fail('handoff must not start'))
    with pytest.raises(ValueError, match='disagree'):
        EV.build({}, 1., ruling='c', uncertainty_ruling='a')


def test_results_envelope_carries_existing_runs_and_dated_historical_replay():
    from triple_lock import pipeline

    years = list(range(2011, 2027))
    history = {'years': years, 'model_years': [2024, 2025, 2026],
               'suspended_earnings_year': 2022,
               'cpi': {y: .02 for y in years}, 'earnings': {y: .04 for y in years},
               'groups': [{'switch_years': [2017], 'model_years': [{'synthetic': 'historical output'}],
                           'level_ratio': {y: .99 for y in years}}]}
    history['earnings'][2022] = history['cpi'][2022]
    central = {'synthetic': 'central inputs'}
    central_run = {'model': {'private': 'metadata'}, 'saving_bn': {2039: {'gross': 1.}}}
    wedge_spec = {'label': 'OBR wedge', 'specified_rates': {'triple_lock': {2039: .04}}}
    wedge_run = {'model': {'private': 'metadata'}, 'saving_bn': {2039: {'gross': 2.}}}
    paired = {'scenarios': {label: {'synthetic': label} for label in
                            ('earnings_minus_0_5pp', 'earnings_plus_0_5pp')}}
    result = pipeline.scenario_envelope(central, central_run, {'obr_premium': (wedge_spec, wedge_run)},
                                       {'history': history}, paired)
    assert result['central']['path'] is central
    assert result['central']['run']['saving_bn'] == central_run['saving_bn']
    assert result['obr_wedge']['path'] is wedge_spec
    assert result['obr_wedge']['run']['saving_bn'] == wedge_run['saving_bn']
    assert 'model' not in result['central']['run'] and 'model' not in result['obr_wedge']['run']
    replay = result['last_decade_replay']
    assert replay['years'] == list(range(2017, 2027))
    assert replay['model_years'] == [2024, 2025, 2026]
    assert replay['counterfactual'] is history['groups'][0]
    assert replay['statutory']['earnings'][2022] == replay['statutory']['cpi'][2022]
    assert 'not a future forecast' in replay['interpretation']
    assert result['paired_earnings_mean_paths'] is paired


def test_pipeline_rejects_invalid_c2_before_any_fiscal_job(monkeypatch):
    from triple_lock import pipeline

    monkeypatch.setattr(pipeline, 'snapshot', lambda: {'git_dirty': False})
    monkeypatch.setattr(pipeline.central_module, 'central_path', lambda: {})
    monkeypatch.setattr(pipeline.jobs, 'run_jobs', lambda *a, **kw: pytest.fail('fiscal jobs must not start'))

    def invalid_handoff(*a, **kw):
        raise ValueError('C2 rule SHA differs from the committed pre-registration')

    monkeypatch.setattr(EV, '_handoff', invalid_handoff)
    with pytest.raises(ValueError, match='rule SHA'):
        pipeline.build(uncertainty_ruling='c')


@pytest.mark.parametrize('primary_passes', [False, True])
def test_pipeline_results_keep_c2_provenance_envelope_and_omission_reason(monkeypatch, primary_passes):
    """Exercise result assembly with public synthetic outputs and no PE import."""
    from triple_lock import pipeline

    effective = 'c' if primary_passes else 'a'
    provenance = {'decision': 'd955', 'ruling': effective, 'requested_ruling': 'c',
                  'effective_ruling': effective, 'screen': 'c2',
                  'rule_sha': TU.C2_PRE_REGISTRATION_COMMIT, 'run_kind': 'binding',
                  'c1_failure': {'all_five_forms_failed': True},
                  'c2_outcome': {'primary_retained': primary_passes},
                  'score_table_sha256': 'synthetic-score-hash',
                  'c2_scores': {'scores': {'A': {'suspended': {'coverage': .8}, 'published': {'coverage': .5}}},
                                'past_years': {'suspended': {'percentile': 50.}, 'published': {'percentile': 99.}}}}
    means = {'scenarios': {'earnings_minus_0_5pp': {'synthetic': 'minus'},
                           'earnings_plus_0_5pp': {'synthetic': 'plus'}}}
    ev = {'provenance': provenance, 'mean_path_scenarios': means}
    if primary_passes:
        ev.update(label='model-conditional', form=TU.PRIMARY_FORM)
    else:
        ev.update(status='skipped', reason='Original primary failed C2; automatic d955(a) fallback')
    years = list(range(2011, 2027))
    hist = {'years': years, 'model_years': [2024, 2025, 2026], 'suspended_earnings_year': 2022,
            'cpi': {y: .02 for y in years}, 'earnings': {y: .03 for y in years},
            'groups': [{'switch_years': [2017], 'model_years': {'synthetic': 'history'}}]}
    run = {'model': {'dataset': 'synthetic'}, 'saving_bn': {2039: {'gross': 1.}}}
    wedge = {'label': 'Synthetic OBR wedge'}
    monkeypatch.setitem(sys.modules, 'policyengine_uk.system', SimpleNamespace(system=SimpleNamespace(parameters={})))
    monkeypatch.setattr(pipeline, 'snapshot', lambda: {'git_dirty': False, 'git_revision': 'synthetic'})
    monkeypatch.setattr(pipeline.central_module, 'central_path', lambda: {'synthetic': 'central path'})
    monkeypatch.setattr(pipeline.central_module, 'september_cpi_history', lambda: {})
    monkeypatch.setattr(pipeline.engine, 'base_levels', lambda p: {'new_state_pension': 1., 'basic_state_pension': .8})
    monkeypatch.setattr(pipeline.engine, 'engine_hashes', lambda: {})
    monkeypatch.setattr(pipeline.trajectories, 'central_spec', lambda c: {'id': 'central'})
    monkeypatch.setattr(pipeline.jobs, 'run_jobs', lambda jobs, **kw: [deepcopy(run) for _ in jobs])
    monkeypatch.setattr(EV, '_handoff', lambda *a, **kw: ('synthetic', {}))
    monkeypatch.setattr(EV, 'build', lambda *a, **kw: deepcopy(ev))
    monkeypatch.setattr(pipeline.trajectories, 'build', lambda *a, **kw: {'history': hist})
    monkeypatch.setattr(pipeline, 'actual_weekly', lambda p: {})
    monkeypatch.setattr(pipeline, 'run_scenarios', lambda *a, **kw: {'obr_premium': (wedge, run)})
    monkeypatch.setattr(pipeline, 'coverage', lambda *a: {})
    monkeypatch.setattr(pipeline, 'assumptions', lambda r: [])
    monkeypatch.setattr(pipeline, 'load_benchmarks', lambda *a, **kw: [])
    monkeypatch.setattr(pipeline, 'check_unchanged', lambda *a: None)
    monkeypatch.setattr(pipeline, 'package_versions', lambda: {})
    monkeypatch.setattr(pipeline, 'scenario_record', lambda *a: {})
    result, _ = pipeline.build(uncertainty_ruling='c')
    assert result['uncertainty_ruling'] == provenance
    assert result['provenance']['uncertainty_ruling'] == provenance
    assert result['uncertainty_screen']['rule_sha'] == TU.C2_PRE_REGISTRATION_COMMIT
    assert result['provenance']['uncertainty_screen'] == result['uncertainty_screen']
    assert result['uncertainty_screen']['c2_scores'] == provenance['c2_scores']
    assert result['uncertainty_screen']['score_table_sha256'] == 'synthetic-score-hash'
    assert result['scenario_envelope']['paired_earnings_mean_paths'] == means
    assert result['scenario_envelope']['central']['run']['saving_bn'] == run['saving_bn']
    assert result['scenario_envelope']['obr_wedge']['run']['saving_bn'] == run['saving_bn']
    assert result['scenario_envelope']['last_decade_replay']['years'] == list(range(2017, 2027))
    if primary_passes:
        assert result['expected_value']['label'] == 'model-conditional'
        assert 'expected_value_omission' not in result
    else:
        assert 'expected_value' not in result
        assert result['expected_value_omission'] == {'requested_ruling': 'c', 'effective_ruling': 'a',
                                                     'reason': ev['reason']}


def test_modified_spec_or_array_fails_before_engine(artifact):
    central, output, manifest = artifact
    file = output / manifest['forms'][TU.PRIMARY_FORM]['specs_file']
    specs = json.loads(file.read_text())
    specs[0]['statutory_cpi']['2031'] += .01
    file.write_text(json.dumps(specs))
    with pytest.raises(ValueError, match='does not reproduce'):
        EV.build(central, 1., uncertainty_ruling='b', adequacy_report={'passing_forms': []},
                 handoff_path=output, runner=lambda *a, **kw: pytest.fail('jobs must not start'))


@settings(max_examples=35, deadline=None)
@given(st.integers(min_value=40, max_value=220), st.integers(min_value=22, max_value=400),
       st.integers(min_value=0, max_value=1000))
def test_c1_design_allocation_sums_to_slots(n, slots, seed):
    rng = np.random.default_rng(seed)
    d = {'stat_cpi': rng.uniform(.02, .07, (n, len(HORIZON))),
         'stat_earnings': rng.uniform(.005, .04, (n, len(HORIZON))),
         'calendar': rng.uniform(.01, .06, (n, len(HORIZON), 2))}
    design = TU.sample_design(d, n_runs=slots, include_zero=True)
    assert sum(design['allocation'].values()) == slots
    assert sum(map(len, design['sample'].values())) == slots
