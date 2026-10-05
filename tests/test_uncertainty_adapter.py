"""The C1 adapter executes only fake engine jobs; no private data or PE run."""

import json
import shutil
from copy import deepcopy

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


def test_ruling_c_reruns_suspended_screen_and_selects_only_passing_form(artifact, monkeypatch):
    central, output, _ = artifact
    report = backtest()
    # The published episode fails every form; only VAR(2) passes suspended.
    for form in TU.CANDIDATES:
        report['scores']['A']['published'][form]['terminal_coverage']['mean'] = .1
        if form != 'monthly_var2_boot':
            report['past_years'][form]['suspended']['realised_percentile'] = 99.
    calls = []
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda **kw: calls.append('screen') or report)
    result = EV.build(central, 1., uncertainty_ruling='c', adequacy_report={'passing_forms': []},
                      handoff_path=output, runner=fake_engine([]), mean_paths=False)
    assert calls == ['screen']
    assert result['form'] == 'monthly_var2_boot'
    assert result['adequacy']['screen_treatments'] == ['suspended']
    assert result['adequacy']['passing_forms'] == ['monthly_var2_boot']


def test_ruling_c_with_no_passing_form_refuses_jobs(artifact, monkeypatch):
    central, output, _ = artifact
    report = backtest()
    for form in TU.CANDIDATES:
        report['past_years'][form]['suspended']['realised_percentile'] = 99.
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda **kw: report)
    with pytest.raises(ValueError, match='suspended-treatment adequacy gate'):
        EV.build(central, 1., uncertainty_ruling='c', handoff_path=output,
                 runner=lambda *a, **kw: pytest.fail('jobs must not start'))


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
