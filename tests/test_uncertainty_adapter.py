"""The C1/C2 adapters execute only fake engine jobs; no private data or PE run."""

import json
import shutil
import sys
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from historical_artifacts import historical_results
from historical_macro_inputs import ARCHIVED_INPUTS, ROOT, macro_inputs_for

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


def make_artifact(tmp_path):
    """Synthetic draws authenticated to whichever macro vintage the fixture supplies."""
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
    return central, tmp_path, manifest


@pytest.fixture(scope='module')
def base_artifact(tmp_path_factory):
    return make_artifact(tmp_path_factory.mktemp('synthetic-handoff'))


@pytest.fixture(scope='module')
def pre_budget_base_artifact(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('pre-budget-synthetic-handoff')
    patch = pytest.MonkeyPatch()
    with macro_inputs_for(historical_results(), patch, tmp_path):
        return make_artifact(tmp_path / 'handoff')


@pytest.fixture
def pre_budget_inputs(tmp_path, monkeypatch):
    """Historical pre-Budget tests use authenticated old macro bytes, scoped to each test.

    Give the unchanged provenance readers a repository-shaped root; rule and C1
    selection bytes are copied unchanged, so real C2 integrity checks still run.
    """
    from triple_lock import config

    with macro_inputs_for(historical_results(), monkeypatch, tmp_path) as root:
        for relative in ('docs/METHOD.md', 'docs/uncertainty/selection.json'):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        with monkeypatch.context() as patch:
            patch.setattr(config, 'REPO', root)
            yield root


def copied_artifact(base_artifact, tmp_path, monkeypatch, name='handoff'):
    central, source, manifest = base_artifact
    output = tmp_path / name
    shutil.copytree(source, output)
    monkeypatch.setattr(EV, 'HISTORY_WINDOWS', {})
    monkeypatch.setattr(EV, 'ev_backtest', lambda: {'diagnostic_only': True})
    monkeypatch.setattr(EV, 'past_years_check', lambda: {'diagnostic_only': True})
    return central, output, deepcopy(manifest)


@pytest.fixture
def artifact(base_artifact, tmp_path, monkeypatch):
    return copied_artifact(base_artifact, tmp_path, monkeypatch)


@pytest.fixture
def pre_budget_artifact(pre_budget_base_artifact, pre_budget_inputs, tmp_path, monkeypatch):
    return copied_artifact(pre_budget_base_artifact, tmp_path, monkeypatch, name='pre-budget-handoff')


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
    score_table.update(scoring_head='f' * 40, input_hashes=TU.handoff_input_hashes())
    score_table['origins'] = {'B': TU.binding_input_provenance(binding=False)['complete_origins']}
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
    assert result['provenance']['rule_section_sha256'] == TU.C2_RULE_SECTION_SHA256
    assert result['provenance']['scoring_inputs_sha256'] == manifest['scoring_inputs_sha256']
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
    score_table.update(scoring_head='f' * 40, input_hashes=TU.handoff_input_hashes())
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
    # The real central path (no model): method_limitations words the d2124 forecast mix from its sources.
    central = pipeline.central_module.central_path()
    monkeypatch.setattr(pipeline.central_module, 'central_path', lambda: central)
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
    # The Housing Benefit passport preflight (test_passport_preflight.py) needs the real model: stub its pass.
    preflight = {'housing_benefit_guarantee_credit_passport': {'keyed_on': 'receipt'}}
    certified = {'certified_bundle': {'passed': True, 'primary': {'dataset': 'synthetic-certified'}}}
    monkeypatch.setattr(pipeline, 'certified_bundle_preflight', lambda log=print: certified)
    monkeypatch.setattr(pipeline, 'housing_benefit_passport_preflight', lambda log=print: preflight)
    result, _ = pipeline.build(uncertainty_ruling='c')
    assert result['provenance']['preflight'] == {**certified, **preflight}
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


# ── The pre-Budget release: direct (a) through the real result assembly ──


def pre_budget_engine(calls):
    """A fake run_jobs for pipeline.build: path jobs on the adapter's fake engine, with the fixed inputs and model
    record a real run carries (assumptions reads them); coverage jobs in engine.coverage's shape."""
    from test_benchmarks_and_dwp import _stats
    from triple_lock.config import HORIZON as YEARS

    paths = fake_engine([])
    fixed = {'data_year': 2024, 'population': {'weights': 'survey', 'ages': 'survey_year',
                                               'pension_types': 'survey_year'},
             'state_pension_age': {y: [66., 67.] if y < 2028 else [67.] for y in YEARS},
             'held_pension_type_records': {y: {'BASIC': 20, 'NEW': 30, 'NONE': 50} for y in YEARS}}

    def run(jobs, **kwargs):
        calls.append((jobs, kwargs))
        out = []
        for kind, spec in jobs:
            if kind == 'coverage':
                dataset = spec.get('dataset', 'enhanced_frs_2024_25@1.58.0')
                out.append({'dataset': dataset, 'model': {'dataset': dataset}, 'max_age': 80., 'path': None,
                            'records': {'households': 3, 'people': 5}, 'data_year': 2024,
                            'by_year': {y: _stats(1 + .03 * (y - 2026)) for y in spec['years']}})
                continue
            assert kind == 'path'
            spec = {**spec, **{key: {str(y): v for y, v in spec[key].items()}
                               for key in ('statutory_cpi', 'statutory_earnings')}}
            run_ = paths([(kind, spec)], **kwargs)[0]
            out.append({**run_, 'fixed_inputs': deepcopy(fixed),
                        'model': {'dataset': spec.get('dataset', 'enhanced_frs_2024_25@1.58.0')}})
        return out
    return run


def pre_budget_stubs(monkeypatch, calls):
    """Stub only what needs PolicyEngine or the git tree; EV.build, the mean paths, coverage, redaction,
    assumptions and benchmarks all run for real."""
    from triple_lock import pipeline

    years = list(range(2011, 2027))
    history = {'years': years, 'model_years': [2024, 2025, 2026], 'suspended_earnings_year': 2022,
               'cpi': {y: .02 for y in years}, 'earnings': {y: .04 for y in years},
               'groups': [{'switch_years': [2017],
                           # trajectories.history writes each group's level ratio; the OBR replay benchmark reads it.
                           'level_ratio': {2024: .99, 2025: .985, 2026: .98},
                           'model_years': {'saving_bn': {2026: {'gross': 1.5, 'net': .9}}}}]}
    history['earnings'][2022] = history['cpi'][2022]
    engine = pre_budget_engine(calls)

    def trajectories_build(central, base, actual, workers=3, log=print):
        spec = {k: v for k, v in pipeline.trajectories.central_spec(central).items()
                if k not in ('id', 'label', 'source')}
        run = {k: v for k, v in engine([('path', spec)])[0].items() if k != 'model'}
        return {'models': {'boot': {'label': 'Synthetic bootstrap', 'runs_paths': True}},
                'paths': [{'id': 'central', 'label': 'Central', **run}], 'history': history}

    monkeypatch.setitem(sys.modules, 'policyengine_uk.system', SimpleNamespace(system=SimpleNamespace(parameters={})))
    monkeypatch.setattr(pipeline, 'snapshot', lambda: {'git_dirty': False, 'git_revision': 'synthetic'})
    monkeypatch.setattr(pipeline, 'check_unchanged', lambda *a: None)
    monkeypatch.setattr(pipeline, 'package_versions', lambda: {})
    monkeypatch.setattr(pipeline.engine, 'engine_hashes', lambda: {})
    monkeypatch.setattr(pipeline.engine, 'base_levels', lambda p: {'new_state_pension': 1., 'basic_state_pension': .8})
    monkeypatch.setattr(pipeline, 'actual_weekly', lambda p: {})
    monkeypatch.setattr(pipeline.jobs, 'run_jobs', engine)
    monkeypatch.setattr(pipeline.trajectories, 'build', trajectories_build)
    certified = {'certified_bundle': {'passed': True, 'primary': {'dataset': 'enhanced_frs_2024_25@1.58.0'}}}
    preflight = {'housing_benefit_guarantee_credit_passport': {'keyed_on': 'receipt'}}
    monkeypatch.setattr(pipeline, 'certified_bundle_preflight', lambda log=print: certified)
    monkeypatch.setattr(pipeline, 'housing_benefit_passport_preflight', lambda log=print: preflight)
    return pipeline


def test_pre_budget_direct_a_build_assembles_a_complete_labelled_results_file(pre_budget_artifact, monkeypatch):
    """The direct-(a) pre-Budget build runs through every assembly step a real build does after its model jobs,
    so an assembly error cannot first appear after ~495 of them: the same post-build verifiers then accept it."""
    import test_results as on_results

    central, output, _ = pre_budget_artifact
    calls = []
    pipeline = pre_budget_stubs(monkeypatch, calls)
    results, scenarios = pipeline.build(uncertainty_ruling='a', uncertainty_handoff=output, pre_budget=True,
                                        log=lambda _: None)
    # The baseline and both mean-path variants (161 each) ran on Enhanced FRS: no expected-value Microcosm path
    # runs, only the build's one Microcosm coverage job.
    assert sum(len(jobs) == 161 for jobs, _ in calls) == 3
    assert not any(spec.get('dataset') for jobs, _ in calls for kind, spec in jobs if kind == 'path')
    assert [spec.get('dataset') for jobs, _ in calls for kind, spec in jobs if kind == 'coverage'] == [
        None, pipeline.SENSITIVITY_DATASET]
    # As triple-lock-build writes it and the tests read it back.
    value = json.loads(json.dumps(results, allow_nan=False, default=float))
    assert value['release']['stage'] == 'pre-budget' and value['release']['recorded_ruling'] == 'c'
    from triple_lock.config import CPI_PERIOD
    assert value['release']['cpi_period'] == CPI_PERIOD
    assert value['release']['forecast_source'] == pipeline.central_module.EFO_SOURCE
    assert 'expected_value' not in value and 'uncertainty_screen' not in value
    assert value['expected_value_omission'] == {
        'requested_ruling': 'a', 'effective_ruling': 'a', 'reason': value['expected_value_omission']['reason']}
    assert 'scenario-envelope ruling' not in value['expected_value_omission']['reason']
    assert [item['key'] for item in value['assumptions']] == ['population', 'paths']
    assert value['assumptions'] == pipeline.assumptions(value)
    assert value['benchmarks'] and not any(b['our_metric'].startswith('expected_value.') for b in value['benchmarks'])
    assert set(value['mean_path_scenarios']['scenarios']) == {'earnings_minus_0_5pp', 'earnings_plus_0_5pp'}
    assert value['coverage']['rows'] and set(value['coverage']['datasets']) == {'primary', 'sensitivity'}
    assert value['provenance']['uncertainty_ruling'] == value['uncertainty_ruling']
    assert set(scenarios) == {'obr_premium'}
    for check in (on_results.test_a_pre_budget_release_is_labelled_as_interim,
                  on_results.test_recorded_uncertainty_outcome_matches_optional_expected_value_and_envelope,
                  on_results.test_no_survey_record_is_published, on_results.test_no_household_weight_is_published,
                  on_results.test_benchmarks_resolve, on_results.test_assumptions_quote_the_results,
                  on_results.test_assumptions_block_is_current,
                  on_results.test_method_text_percentiles_match_the_past_years_check):
        check(value)


def test_a_direct_a_build_without_pre_budget_keeps_its_unlabelled_shape(artifact, monkeypatch):
    import test_results as on_results

    central, output, _ = artifact
    pipeline = pre_budget_stubs(monkeypatch, [])
    results, _ = pipeline.build(uncertainty_ruling='a', uncertainty_handoff=output, log=lambda _: None)
    value = json.loads(json.dumps(results, allow_nan=False, default=float))
    assert 'release' not in value and 'release_stage' not in value['uncertainty_ruling']
    assert value['expected_value_omission']['reason'] == 'd955 scenario-envelope ruling'
    on_results.test_a_pre_budget_release_is_labelled_as_interim(value)
    on_results.test_recorded_uncertainty_outcome_matches_optional_expected_value_and_envelope(value)


def test_pre_budget_b_is_refused_before_any_job(monkeypatch):
    from triple_lock import pipeline

    monkeypatch.setattr(pipeline, 'snapshot', lambda: pytest.fail('no job or snapshot may start'))
    with pytest.raises(SystemExit, match='b is obsolete'):
        pipeline.build(uncertainty_ruling='b', pre_budget=True)


@pytest.mark.parametrize('ruling, pre_budget', [('b', False), ('c', False), ('a', True), ('c', True)])
def test_every_supported_build_runs_the_microcosm_subsample(monkeypatch, ruling, pre_budget, artifact, request):
    """Every other build asks EV.build for the paired sensitivity subsample, and EV.build refuses to omit it for any
    ruling but (b)."""
    from triple_lock import pipeline

    seen = {}

    def build(*a, **kw):
        seen.update(kw)
        raise RuntimeError('stop after the expected-value call')

    if pre_budget:
        artifact = request.getfixturevalue('pre_budget_artifact')
    pipeline_stubs = pre_budget_stubs(monkeypatch, [])
    if ruling == 'c' and pre_budget:
        # A current execution needs its own genuinely current source/input
        # hashes, never the archived pre-Budget handoff after a role change.
        _, output, _ = provisional_c_artifact(artifact)
        monkeypatch.setattr(pipeline_stubs, 'C2_DRY_RUN', output)
    monkeypatch.setattr(EV, '_handoff', lambda *a, **kw: ('synthetic', {}))
    monkeypatch.setattr(EV, 'build', build)
    with pytest.raises(RuntimeError, match='stop after'):
        pipeline_stubs.build(uncertainty_ruling=ruling, pre_budget=pre_budget, log=lambda _: None)
    assert seen['paired_sensitivity'] is True
    monkeypatch.undo()
    with pytest.raises(ValueError, match='only the interim pre-Budget ruling'):
        EV.build({}, 1., uncertainty_ruling='c', paired_sensitivity=False)


def test_the_normal_b_build_still_runs_the_40_slot_microcosm_subsample(artifact):
    central, output, _ = artifact
    calls = []
    result = EV.build(central, 1., uncertainty_ruling='b', adequacy_report={'passing_forms': []},
                      handoff_path=output, runner=fake_engine(calls), mean_paths=False)
    microcosm = [jobs for jobs, _ in calls if all(spec.get('dataset') == EV.SENSITIVITY_DATASET for _, spec in jobs)]
    assert len(microcosm) == 1 and 0 < len(microcosm[0]) <= EV.N_PATHS_SENSITIVITY
    assert sum(row['sensitivity_paths'] for row in result['strata']) == EV.N_PATHS_SENSITIVITY
    assert result['paired_difference'] and 'sensitivity' in result['estimates']
    assert 'paired_sensitivity' not in result


def test_pre_budget_refuses_any_other_ruling():
    from triple_lock import pipeline

    with pytest.raises(SystemExit, match='requires --uncertainty-ruling a or c'):
        pipeline.pre_budget_release('d')


def provisional_c_artifact(artifact, *, primary_passes=True):
    """The synthetic handoff, made a C2 dry run: the committed dry run's role in a provisional (c) build."""
    central, output, manifest = artifact
    score_table = backtest()
    score_table.update(scoring_head='f' * 40, input_hashes=TU.handoff_input_hashes())
    score_table['origins'] = {'B': TU.binding_input_provenance(binding=False)['complete_origins']}
    primary = score_table['scores']['A']['suspended'][TU.PRIMARY_FORM]
    primary['terminal_coverage']['hits'] = 4
    primary.update(terminal_scored_origins=5, annual_gap_cells=20)
    if not primary_passes:
        score_table['past_years'][TU.PRIMARY_FORM]['suspended']['realised_percentile'] = 99.
    outcome = TU.adequacy(score_table, screen='c2')
    manifest.update(TU.c2_metadata(score_table, outcome, TU.binding_input_provenance(binding=False), binding=False))
    for metadata in manifest['forms'].values():
        metadata['fiscal_eligible'] = False
    (output / 'handoff.json').write_text(json.dumps(manifest))
    return central, output, manifest


def test_pre_budget_provisional_c_build_runs_the_dry_run_primary_with_microcosm(pre_budget_artifact, monkeypatch):
    """The provisional pre-Budget (c) build (Max, 13 October): the primary's expected value on the C2 dry run's own
    paths, labelled provisional under the recorded ruling (c), with the C2 dry run's screen and the full 40-slot
    paired Microcosm cross-check. The same post-build verifiers accept the file."""
    import test_results as on_results

    central, output, manifest = provisional_c_artifact(pre_budget_artifact)
    calls = []
    pipeline = pre_budget_stubs(monkeypatch, calls)
    monkeypatch.setattr(pipeline, 'C2_DRY_RUN', output)
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda log=print: backtest())
    results, _ = pipeline.build(uncertainty_ruling='c', uncertainty_handoff=output, pre_budget=True,
                                log=lambda _: None)
    microcosm = [jobs for jobs, _ in calls if jobs and all(spec.get('dataset') == EV.SENSITIVITY_DATASET
                                                           for kind, spec in jobs if kind == 'path')
                 and any(kind == 'path' for kind, _ in jobs)]
    assert len(microcosm) == 1 and 0 < len(microcosm[0]) <= EV.N_PATHS_SENSITIVITY
    value = json.loads(json.dumps(results, allow_nan=False, default=float))
    release = value['release']
    assert release['execution_ruling'] == 'c' and release['provisional'] is True
    assert release['expected_value'].startswith('provisional under ruling (c)')
    ev = value['expected_value']
    assert ev['provenance']['ruling'] == 'c' and ev['provenance']['run_kind'] == 'dry_run'
    assert ev['adequacy'] == manifest['c2_outcome'] and ev['paired_difference']
    assert sum(row['sensitivity_paths'] for row in ev['strata']) == EV.N_PATHS_SENSITIVITY
    assert value['uncertainty_screen']['run_kind'] == 'dry_run'
    assert value['assumptions'] == pipeline.assumptions(value)
    assert 'post-Budget release' not in value['assumptions'][2]['text']
    for check in (on_results.test_a_pre_budget_release_is_labelled_as_interim,
                  on_results.test_recorded_uncertainty_outcome_matches_optional_expected_value_and_envelope,
                  on_results.test_no_survey_record_is_published, on_results.test_no_household_weight_is_published,
                  on_results.test_benchmarks_resolve, on_results.test_assumptions_quote_the_results,
                  on_results.test_assumptions_block_is_current,
                  on_results.test_expected_value_recomputes_from_the_path_records,
                  on_results.test_paired_difference_recomputes_from_the_path_records):
        check(value)


def test_pre_budget_provisional_c_refuses_paths_that_are_not_the_dry_run(pre_budget_artifact, monkeypatch, tmp_path):
    import shutil

    central, output, manifest = provisional_c_artifact(pre_budget_artifact)
    dry = tmp_path / 'dry'
    shutil.copytree(output, dry)
    specs = dry / f'{TU.PRIMARY_FORM}.specs.json'
    specs.write_text(specs.read_text() + ' ')
    pipeline = pre_budget_stubs(monkeypatch, [])
    monkeypatch.setattr(pipeline, 'C2_DRY_RUN', dry)
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda log=print: backtest())
    with pytest.raises(SystemExit, match="C2 dry run's primary paths"):
        pipeline.build(uncertainty_ruling='c', uncertainty_handoff=output, pre_budget=True, log=lambda _: None)


def test_pre_budget_provisional_c_refuses_a_failing_dry_run_primary(pre_budget_artifact, monkeypatch):
    central, output, manifest = provisional_c_artifact(pre_budget_artifact, primary_passes=False)
    pipeline = pre_budget_stubs(monkeypatch, [])
    monkeypatch.setattr(pipeline, 'C2_DRY_RUN', output)
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda log=print: backtest())
    with pytest.raises(SystemExit, match='fails the C2 dry run'):
        pipeline.build(uncertainty_ruling='c', uncertainty_handoff=output, pre_budget=True, log=lambda _: None)


@pytest.mark.parametrize('change', ['cpi_period', 'forecast'])
def test_pre_budget_refuses_once_the_inputs_are_not_pre_budget(monkeypatch, change, pre_budget_inputs):
    from triple_lock import config, pipeline

    # Undo this deliberate one-input change before the historical fixture
    # restores the live vintage, so pytest teardown cannot restore old labels.
    with monkeypatch.context() as patch:
        if change == 'cpi_period':
            patch.setattr(config, 'CPI_PERIOD', '2026 SEP')
        else:
            patch.setattr(pipeline.central_module, 'EFO_SOURCE', 'OBR Economic and fiscal outlook, October 2026')
        patch.setattr(pipeline, 'snapshot', lambda: pytest.fail('nothing may start'))
        with pytest.raises(SystemExit, match='binding route'):
            pipeline.build(uncertainty_ruling='a', pre_budget=True)


def test_live_post_budget_inputs_refuse_pre_budget_before_any_job(monkeypatch):
    """The live September/October vintage must never enter the historical release route."""
    from triple_lock import config, pipeline

    assert config.CPI_PERIOD == '2026 SEP'
    assert 'October 2026' in pipeline.central_module.EFO_SOURCE
    monkeypatch.setattr(pipeline, 'snapshot', lambda: pytest.fail('nothing may start'))
    with pytest.raises(SystemExit, match='binding route'):
        pipeline.build(uncertainty_ruling='a', pre_budget=True)


def test_pre_budget_macro_context_authenticates_each_loader_and_restores_live_cpi(monkeypatch, tmp_path):
    from triple_lock import config, history_data, pipeline, trajectories

    source = historical_results()
    live_rate_path = config.CPI_CSV
    live_history_source = history_data.SERIES['D7G7']
    live_aliases = [(module, name, getattr(module, name)) for module, name in (
        (pipeline, 'CENTRAL_FORECAST_CSV'), (pipeline, 'ACTUALS_CSV'), (pipeline, 'CPI_CSV'),
        (TB, 'ERROR_CSV'), (trajectories, 'ACTUALS_CSV'), (trajectories, 'CPI_CSV'))]
    with macro_inputs_for(source, monkeypatch, tmp_path):
        assert history_data.SERIES['D7G7'] == (config.CPI_CSV, live_history_source[1])
        assert TB.ERROR_CSV == config.ERROR_CSV
        assert trajectories.ACTUALS_CSV == config.ACTUALS_CSV
        assert trajectories.CPI_CSV == pipeline.CPI_CSV == config.CPI_CSV
        assert pipeline.CENTRAL_FORECAST_CSV == config.CENTRAL_FORECAST_CSV
        assert pipeline.ACTUALS_CSV == config.ACTUALS_CSV
        forecasts, _ = TB.load_forecasts()
        assert ('cpi', 4) not in forecasts[(2022, 'March 2022 EFO')]
        assert ('earnings', 4) not in forecasts[(2022, 'March 2022 EFO')]
        _, earnings = trajectories.history_inputs()
        assert earnings[2026] == .049  # The archived July 2025 vintage precedes October's 4.8% revision.
        hashes = TU.handoff_input_hashes()
        for relative in ARCHIVED_INPUTS:
            assert hashes[relative.rsplit('/', 1)[-1]] == source['provenance']['input_hashes'][relative]
    assert config.CPI_CSV == live_rate_path
    assert history_data.SERIES['D7G7'] == live_history_source
    assert all(getattr(module, name) == value for module, name, value in live_aliases)


@pytest.mark.parametrize('argv', [['--pre-budget'],
                                  ['--pre-budget', '--uncertainty-ruling', 'b'],
                                  ['--pre-budget', '--uncertainty-ruling', 'a', '--scenario', 'obr_premium'],
                                  ['--pre-budget', '--uncertainty-ruling', 'a', '--uncertainty-handoff', 'x']])
def test_pre_budget_cli_refuses_misuse(monkeypatch, argv):
    from triple_lock import cli, pipeline

    monkeypatch.setattr(pipeline, 'build', lambda *a, **kw: pytest.fail('the build must not start'))
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2


def test_pre_budget_cli_passes_the_flag_to_the_build(monkeypatch, tmp_path):
    from triple_lock import cli, pipeline

    seen = {}

    def build(**kwargs):
        seen.update(kwargs)
        return {'synthetic': True}, {}

    monkeypatch.setattr(pipeline, 'build', build)
    monkeypatch.setattr(pipeline, 'write', lambda value, paths: seen.setdefault('written', []).append(paths))
    for ruling in ('a', 'c'):
        assert cli.main(['--pre-budget', '--uncertainty-ruling', ruling, '--workers', '3',
                         '--sensitivity-workers', '1']) == 0
        assert seen['pre_budget'] is True and seen['uncertainty_ruling'] == ruling
        assert seen['uncertainty_handoff'] is None


@pytest.mark.parametrize('field', [
    'screen', 'rule_sha', 'rule_section_sha256', 'rule', 'scoring_head',
    'input_hashes', 'scoring_inputs_sha256', 'score_table_sha256',
    'c1_failure', 'run_kind', 'expected_value_authorized', 'authorization',
    'binding_inputs', 'fiscal_eligible',
])
def test_pre_budget_rejects_tampered_dry_run_metadata(pre_budget_artifact, monkeypatch, field):
    from triple_lock import pipeline

    _, output, manifest = provisional_c_artifact(pre_budget_artifact)
    if field == 'fiscal_eligible':
        manifest['forms'][TU.PRIMARY_FORM]['fiscal_eligible'] = True
    elif field == 'expected_value_authorized':
        manifest[field] = True
    elif field in ('input_hashes', 'rule', 'c1_failure', 'binding_inputs'):
        manifest[field] = {}
    else:
        manifest[field] = '0' * 40
    (output / 'handoff.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(pipeline, 'C2_DRY_RUN', output)
    monkeypatch.setattr(pipeline, 'snapshot', lambda: pytest.fail('nothing may start after tampering'))
    with pytest.raises(SystemExit, match='C2 dry.run|C2 dry-run'):
        pipeline.build(uncertainty_ruling='c', pre_budget=True)


def test_pre_budget_display_dates_follow_the_budget_constant(monkeypatch, pre_budget_inputs):
    from datetime import date
    from triple_lock import pipeline

    monkeypatch.setattr(TU, 'C2_BUDGET_DATE', date(2026, 11, 4))
    monkeypatch.setattr(pipeline, 'c2_dry_run', lambda: ({}, {
        'terminal_hits': 4, 'terminal_origins': 5, 'annual_coverage': .8, 'annual_cells': 20}))
    release = pipeline.pre_budget_release('c')
    assert release['budget_date'] == '2026-11-04'
    assert '4 November 2026' in release['expected_value']
    assert '28 October' not in release['expected_value']
    scenario = pipeline.label_pre_budget({'provenance': {'ruling': 'a'}})
    assert '4 November 2026' in scenario['reason']
