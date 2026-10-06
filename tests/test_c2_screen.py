"""Frozen statutory screen: synthetic draws/tables only, without model jobs."""

from copy import deepcopy
from datetime import date
import json

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest

from triple_lock import ts_backtest as TB, ts_uncertainty as TU


def passing_table():
    row = {'n_origins': 6, 'expected_origins': 6}
    row.update({name: {'mean': 1.} for name in TU.PROPER_SCORES})
    row.update({name: {'mean': 0.} for name in ('gap_bias_pp', 'switch_bias', 'floor_bias')})
    row['annual_gap_coverage'] = {'mean': .8}
    row['terminal_coverage'] = {'mean': 4/6, 'hits': 4,
                                'wilson95_independent': TB.wilson_band(4, 6)}
    return {'screen': 'c2', 'scoring_head': 'f' * 40, 'input_hashes': TU.handoff_input_hashes(),
            'origins': {'A': ['synthetic'], 'B': ['synthetic']},
            'scores': {test: {treatment: {form: deepcopy(row) for form in TU.CANDIDATES}
                              for treatment in ('published', 'suspended')} for test in ('A', 'B')},
            'past_years': {form: {treatment: {'realised_percentile': 50.}
                                 for treatment in ('published', 'suspended')}
                           for form in TU.CANDIDATES}}


def test_rule_threshold_objects_are_byte_identical():
    canonical = lambda obj: json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()
    assert canonical(TU.C1_RULE['thresholds']) == canonical(TU.C2_RULE['thresholds'])
    changed = {key for key in TU.C1_RULE if canonical(TU.C1_RULE[key]) != canonical(TU.C2_RULE[key])}
    assert changed == {'treatments', 'exclusion'}


@pytest.mark.parametrize('suspended', [1995, 2020, 2031])
def test_exclusions_follow_legal_year_and_apply_to_forecast_and_outturn(suspended):
    years = [suspended - 1, suspended, suspended + 1, suspended + 2]
    observed = np.array([[.02, .01], [.03, .20], [.02, .04], [.01, .025]])
    draws = np.repeat(observed[None], 32, axis=0)
    draws[:, :, 1] += .01
    raw_draws, raw_observed = draws.copy(), observed.copy()
    actual = TB.candidate_score(draws, observed, target_years=years,
                               suspended_years=[suspended], exclude_legal_constants=True)
    corrected_draws, corrected_observed = draws.copy(), observed.copy()
    corrected_draws[:, 1, 1] = corrected_draws[:, 1, 0]
    corrected_observed[1, 1] = corrected_observed[1, 0]
    expected = TB.candidate_score(corrected_draws, corrected_observed)
    assert actual['annual_gap_cells'] == 3
    assert actual['annual_gap_excluded_cells'] == 1
    assert actual['gap_bias_pp'] == pytest.approx(1.)
    assert actual['gap_crps'] == pytest.approx(expected['gap_crps'] * 4/3)
    assert actual['terminal_coverage'] == expected['terminal_coverage']
    assert actual['terminal_bias_pp'] == expected['terminal_bias_pp']
    assert actual['energy'] == expected['energy']
    assert actual['variogram'] == expected['variogram']
    assert actual['switch_crps'] == expected['switch_crps']
    assert actual['floor_crps'] == expected['floor_crps']
    np.testing.assert_array_equal(draws, raw_draws)
    np.testing.assert_array_equal(observed, raw_observed)


def test_accidental_zero_is_scored_and_wholly_suspended_terminal_is_excluded():
    observed = np.full((4, 2), .02)
    draws = np.repeat(observed[None], 30, axis=0)
    years = [2010, 2011, 2012, 2013]
    ordinary = TB.candidate_score(draws, observed, target_years=years,
                                 suspended_years=[], exclude_legal_constants=True)
    assert ordinary['annual_gap_cells'] == 4
    assert ordinary['annual_gap_coverage'] == 1.
    assert ordinary['terminal_coverage'] == 1.
    suspended = TB.candidate_score(draws, observed, target_years=years,
                                  suspended_years=years, exclude_legal_constants=True)
    assert suspended['annual_gap_cells'] == 0
    assert suspended['terminal_coverage'] is None
    assert 'terminal_coverage' in suspended['legal_fixed_statistics']
    assert suspended['energy'] == pytest.approx(0., abs=1e-12)
    assert suspended['floor_crps'] == pytest.approx(0., abs=1e-12)


def test_cell_weighted_gap_statistics_do_not_average_origin_percentages():
    pooled = TB.weighted_mean_with_overlap_se([1., 0., .5], [4, 3, 3])
    assert pooled['mean'] == .55
    assert pooled['n_cells'] == 10
    assert pooled['n_scored_origins'] == 3
    assert pooled['se_independent'] > 0
    assert pooled['se_overlap_hac'] >= 0


@given(st.lists(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
                min_size=150, max_size=150))
@settings(max_examples=80, deadline=None)
def test_published_earnings_random_score_tables_never_change_c2_verdict(values):
    table = passing_table()
    expected = TU.adequacy(table, screen='c2')
    index = 0
    for test in ('A', 'B'):
        for form in TU.CANDIDATES:
            row = table['scores'][test]['published'][form]
            for key in (*TU.PROPER_SCORES, 'gap_bias_pp', 'switch_bias', 'floor_bias',
                        'annual_gap_coverage', 'terminal_coverage'):
                row[key]['mean'] = values[index]
                index += 1
            row['terminal_coverage']['wilson95_independent'] = values[index:index+2]
            index += 2
            row['n_origins'], row['expected_origins'] = values[index:index+2]
            index += 2
            table['past_years'][form]['published']['realised_percentile'] = values[index]
            index += 1
    assert TU.adequacy(table, screen='c2') == expected
    assert TU.adequacy(table, treatments=('published',), screen='c2') == expected


def test_c2_never_promotes_passing_alternative_and_routes_automatically():
    table = passing_table()
    passing = TU.adequacy(table, screen='c2')
    assert passing['selected_primary'] == TU.PRIMARY_FORM
    assert passing['effective_ruling'] == 'c'
    table['scores']['A']['suspended'][TU.PRIMARY_FORM]['terminal_coverage']['mean'] = 1/6
    failing = TU.adequacy(table, screen='c2')
    assert failing['passing_forms']
    assert TU.PRIMARY_FORM not in failing['passing_forms']
    assert failing['selected_primary'] is None
    assert failing['effective_ruling'] == 'a'
    assert failing['fallback_reason']


def test_statutory_complete_origins_do_not_wait_for_calendar_outturn_errors():
    forecasts = {(2022, 'March 2022 EFO'): {(v, h): .03 for v in ('cpi', 'earnings') for h in range(1, 5)}}
    outturns = {year: (.02, .03) for year in range(2023, 2027)}
    assert TB.complete_statutory_origins(forecasts, outturns) == [(2022, 'March 2022 EFO')]
    forecasts[(2022, 'March 2022 EFO')].pop(('earnings', 4))
    assert TB.complete_statutory_origins(forecasts, outturns) == []


def test_c2_backtest_pools_annual_exclusions_and_preserves_other_scores(monkeypatch):
    def paths(form, years, n, seed, **kwargs):
        c = np.full((n, len(years)), .02)
        e = np.full_like(c, .03)
        return {'statutory_cpi': c, 'statutory_earnings': e}, {}
    monkeypatch.setattr(TU, 'CANDIDATES', {TU.PRIMARY_FORM: {}})
    monkeypatch.setattr(TU, 'candidate_paths', paths)
    result = TB.run_candidate_backtest(n=20, log=lambda _: None, screen='c2', suspended_years=[2020])
    summary = result['scores']['A']['suspended'][TU.PRIMARY_FORM]
    assert summary['annual_gap_excluded_cells'] == 4
    assert summary['annual_gap_cells'] == 20
    rows = [row for row in result['rows'] if row['chronological'] and row['treatment'] == 'suspended']
    for metric in ('annual_gap_coverage', 'gap_crps', 'gap_bias_pp'):
        pooled = sum(row[metric] * row['annual_gap_cells'] for row in rows) / 20
        assert summary[metric]['mean'] == pytest.approx(pooled)
    assert all(row['terminal_coverage'] is not None for row in rows)


def synthetic_manifest(monkeypatch, *, binding=True):
    table = passing_table()
    snapshot = {'ready': True, 'complete_origins': ['synthetic'], 'data_hashes': {}}
    monkeypatch.setattr(TU, 'binding_input_provenance', lambda **kwargs: snapshot)
    manifest = TU.c2_metadata(table, TU.adequacy(table, screen='c2'), snapshot, binding=binding)
    manifest.update(input_hashes=TU.handoff_input_hashes(),
                    forms={form: {'fiscal_eligible': binding and form == TU.PRIMARY_FORM} for form in TU.CANDIDATES})
    return manifest


def test_handoff_records_actual_preregistration_sha_and_frozen_section(monkeypatch):
    manifest = synthetic_manifest(monkeypatch)
    assert manifest['rule_sha'] == '65343e2ee43a359f056ce5a027739509d32ab49f'
    assert manifest['rule_section_sha256'] == TU.committed_c2_rule_hash()
    assert manifest['rule_section_sha256'] == TU.C2_RULE_SECTION_SHA256
    assert manifest['scoring_inputs_sha256'] == TU._canonical_hash(manifest['input_hashes'])
    assert TU.validate_c2_handoff(manifest)['selected_primary'] == TU.PRIMARY_FORM


def test_frozen_rule_content_hash_needs_no_historical_git_objects(monkeypatch):
    monkeypatch.setattr(TU, '_git_bytes', lambda *args: pytest.fail('historical Git objects must not be read'))
    assert TU.committed_c2_rule_hash() == TU.C2_RULE_SECTION_SHA256


@pytest.mark.parametrize('change', ['rule', 'line_endings', 'markers'])
def test_frozen_rule_refuses_changed_bytes(monkeypatch, tmp_path, change):
    from triple_lock import config
    method = (config.REPO / 'docs/METHOD.md').read_bytes()
    if change == 'rule':
        method = method.replace(b'at most 1.5 percentage points', b'at most 1.6 percentage points')
    elif change == 'line_endings':
        method = method.replace(b'\n', b'\r\n')
    else:
        method += b'\n<!-- C2 frozen rule begins -->\n'
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/METHOD.md').write_bytes(method)
    monkeypatch.setattr(config, 'REPO', tmp_path)
    with pytest.raises(ValueError, match='C2 (rule differs|frozen rule markers)'):
        TU.committed_c2_rule_hash()


@pytest.mark.parametrize('field,value,match', [
    ('rule_sha', 'bad', 'rule SHA'),
    ('rule_section_sha256', 'bad', 'rule differs'),
    ('score_table_sha256', 'bad', 'score table'),
    ('scoring_inputs_sha256', 'bad', 'scoring file hashes'),
    ('input_hashes', {}, 'scoring file hashes'),
])
def test_handoff_rejects_rule_and_score_or_input_tampering(monkeypatch, field, value, match):
    manifest = synthetic_manifest(monkeypatch)
    manifest[field] = value
    with pytest.raises(ValueError, match=match):
        TU.validate_c2_handoff(manifest)


def test_handoff_cannot_make_alternative_fiscally_eligible(monkeypatch):
    manifest = synthetic_manifest(monkeypatch)
    manifest['forms']['monthly_var2_boot']['fiscal_eligible'] = True
    with pytest.raises(ValueError, match='primary-only'):
        TU.validate_c2_handoff(manifest)


def test_dry_run_handoff_cannot_authorize_a_binding_build(monkeypatch):
    manifest = synthetic_manifest(monkeypatch, binding=False)
    with pytest.raises(ValueError, match='dry-run'):
        TU.validate_c2_handoff(manifest)
    assert TU.validate_c2_handoff(manifest, require_binding=False)['effective_ruling'] == 'c'


def test_today_inputs_are_explicitly_unready_and_binding_refuses_them():
    snapshot = TU.binding_input_provenance(today=date(2026, 10, 6))
    assert not snapshot['ready']
    assert any('september_2026_cpi' in missing for missing in snapshot['missing_requirements'])
    assert snapshot['complete_origins']
    with pytest.raises(ValueError, match='post-Budget'):
        TU.binding_input_provenance(binding=True, today=date(2026, 10, 6))


def future_inputs(tmp_path, monkeypatch):
    """Fabricate dated aggregate series and committed-byte receipts, never scores."""
    import csv
    from triple_lock import config

    monkeypatch.setattr(config, 'REPO', tmp_path)
    monkeypatch.setattr(config, 'CPI_PERIOD', '2026 SEP')
    monkeypatch.setattr(config, 'AWE_PERIOD', '2026 JUL')
    monkeypatch.setattr(TU, 'committed_c2_rule_hash', lambda: 'frozen-section')
    paths = {}
    for name in ('ACTUALS_CSV', 'CENTRAL_FORECAST_CSV', 'ERROR_CSV', 'CPI_CSV', 'AWE_CSV'):
        path = tmp_path / f'{name}.csv'
        paths[name] = path
        monkeypatch.setattr(config, name, path)
    for name in ('CPI_INDEX_CSV', 'AWE_LEVEL_CSV'):
        path = tmp_path / f'{name}.csv'
        paths[name] = path
        monkeypatch.setattr(TU.ts_monthly, name, path)
    def write(name, fields, rows):
        with paths[name].open('w', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    fields = ['determination_year', 'cpi_september_12m', 'awe_total_pay_may_jul_3m_yoy']
    write('ACTUALS_CSV', fields, [{'determination_year': year, 'cpi_september_12m': .02,
                                 'awe_total_pay_may_jul_3m_yoy': .03} for year in range(2011, 2027)])
    paths['CPI_INDEX_CSV'].write_text('2025 SEP,100\n2026 SEP,102\n')
    paths['AWE_LEVEL_CSV'].write_text('2025 MAY,100\n2025 JUN,100\n2025 JUL,100\n2026 MAY,103\n2026 JUN,103\n2026 JUL,103\n')
    paths['CPI_CSV'].write_text('2026 SEP,2.0\n')
    paths['AWE_CSV'].write_text('2026 JUL,3.0\n')
    rows = []
    for variable in ('cpi', 'earnings'):
        for basis, quarter in (('calendar_year', ''), ('q3_yoy' if variable == 'cpi' else 'q2_yoy', 'Q3' if variable == 'cpi' else 'Q2')):
            rows.extend({'variable': variable, 'basis': basis, 'period': f'{year}{quarter}', 'value': .02,
                         'source': 'OBR Budget 28 October 2026 EFO', 'source_url': 'https://obr.uk/budget-2026.xlsx', 'note': ''}
                        for year in range(2026, 2031))
    write('CENTRAL_FORECAST_CSV', ['variable', 'basis', 'period', 'value', 'source', 'source_url', 'note'], rows)
    fields = ['year_forecast_made', 'forecast_vintage', 'horizon_years', 'variable', 'forecast', 'outturn']
    write('ERROR_CSV', fields, [{'year_forecast_made': 2022, 'forecast_vintage': 'March 2022 EFO',
                               'horizon_years': h, 'variable': variable, 'forecast': .02, 'outturn': ''}
                              for variable in ('cpi', 'earnings') for h in range(1, 5)])
    committed = {path.name: path.read_bytes() for path in paths.values()}
    monkeypatch.setattr(TU, '_git_bytes', lambda *args: committed[args[-1].split(':', 1)[1]])
    return paths


def test_binding_accepts_complete_dated_committed_macro_bundle(tmp_path, monkeypatch):
    future_inputs(tmp_path, monkeypatch)
    snapshot = TU.binding_input_provenance(binding=True, today=date(2026, 10, 29))
    assert snapshot['ready']
    assert snapshot['complete_origins'] == ['March 2022 EFO']
    assert len(snapshot['obr_forecast_sources']) == 20
    assert snapshot['statutory_inputs']['september_2026_cpi']['actual'] == .02


@pytest.mark.parametrize('fault', ['stale_period', 'stale_quarter', 'missing_forecast',
                                  'uncommitted', 'mismatched_rate', 'mismatched_monthly'])
def test_binding_refuses_incomplete_or_inconsistent_future_bundle(tmp_path, monkeypatch, fault):
    paths = future_inputs(tmp_path, monkeypatch)
    if fault == 'stale_period':
        from triple_lock import config
        monkeypatch.setattr(config, 'CPI_PERIOD', '2026 AUG')
    elif fault == 'stale_quarter':
        path = paths['CENTRAL_FORECAST_CSV']
        content = path.read_text().replace('OBR Budget 28 October 2026 EFO', 'OBR March 2026 EFO', 1)
        path.write_text(content)
    elif fault == 'missing_forecast':
        path = paths['ERROR_CSV']
        rows = path.read_text().splitlines()
        path.write_text('\n'.join(rows[:-1]) + '\n')
    elif fault == 'mismatched_rate':
        paths['CPI_CSV'].write_text('2026 SEP,4.0\n')
    elif fault == 'mismatched_monthly':
        paths['CPI_INDEX_CSV'].write_text('2025 SEP,100\n2026 SEP,105\n')
    else:
        monkeypatch.setattr(TU, '_git_bytes', lambda *args: b'not committed data')
    with pytest.raises(ValueError, match='post-Budget'):
        TU.binding_input_provenance(binding=True, today=date(2026, 10, 29))


@pytest.mark.parametrize('legal_exclusion', [False, True])
def test_frozen_candidate_terminal_gap_preserves_unrounded_rates(legal_exclusion):
    # Both paths have two CPI leads followed by two earnings leads, with the
    # floor path always at least the cumulative earnings anchor. Compounding
    # gives 1 - ((1+b)/(1+a))**2 exactly; published-rate rounding is different.
    a, b = .02651, .02549
    observed = np.array([[a, b], [a, b], [b, a], [b, a]])
    draw = np.array([[a, b], [b, a], [a, b], [b, a]])
    draws = np.repeat(draw[None], 32, axis=0)
    result = TB.candidate_score(draws, observed, target_years=[2010, 2011, 2012, 2013],
                               suspended_years=[], exclude_legal_constants=legal_exclusion)
    expected = 100 * (1 - ((1 + b) / (1 + a)) ** 2)
    rounded = 100 * (1 - (1.025 / 1.027) ** 2)
    assert expected != pytest.approx(rounded)
    assert result['predicted_terminal_gap_pct'] == pytest.approx(expected, abs=1e-12)
    assert result['realised_terminal_gap_pct'] == pytest.approx(expected, abs=1e-12)
    assert result['terminal_bias_pp'] == pytest.approx(0., abs=1e-12)


def test_frozen_past_years_terminal_gap_preserves_unrounded_boundary(monkeypatch):
    a, b = .02651, .02549
    forecasts = {(year, f'March {year} EFO'): {(v, h): .026 for v in ('cpi', 'earnings')
                                            for h in range(1, 5)} for year in (2010, 2011)}
    outturns = {year: (a, b) if year % 2 else (b, a) for year in range(2011, 2026)}
    def paths(form, years, n, seed, **kwargs):
        rates = np.array([outturns[year] for year in years])
        return {'statutory_cpi': np.repeat(rates[None, :, 0], n, axis=0),
                'statutory_earnings': np.repeat(rates[None, :, 1], n, axis=0)}, {}
    monkeypatch.setattr(TU, 'CANDIDATES', {TU.PRIMARY_FORM: {}})
    monkeypatch.setattr(TU, 'candidate_paths', paths)
    monkeypatch.setattr(TB, 'load_forecasts', lambda: (forecasts, {}))
    monkeypatch.setattr(TB, 'statutory_outturns', lambda **kwargs: outturns)
    result = TB.run_candidate_backtest(n=20, log=lambda _: None, screen='c2', suspended_years=[])
    # Fifteen years beginning with a CPI lead have seven (a-b) ratchets.
    expected = 100 * (1 - ((1 + b) / (1 + a)) ** 7)
    rounded = 100 * (1 - (1.025 / 1.027) ** 7)
    assert expected != pytest.approx(rounded)
    for treatment in ('published', 'suspended'):
        past = result['past_years'][TU.PRIMARY_FORM][treatment]
        assert past['mean_gap_pct'] == pytest.approx(expected, abs=1e-12)
        assert past['realised_gap_pct'] == pytest.approx(expected, abs=1e-12)
        assert past['realised_percentile'] == pytest.approx(50., abs=1e-12)


@pytest.mark.parametrize('binding,primary_passes', [(False, True), (False, False),
                                                    (True, True), (True, False)])
def test_execution_authorization_is_distinct_from_diagnostic_c2_verdict(monkeypatch, binding, primary_passes):
    table = passing_table()
    if not primary_passes:
        table['scores']['A']['suspended'][TU.PRIMARY_FORM]['terminal_coverage']['mean'] = 1/6
    before = deepcopy(table)
    outcome = TU.adequacy(table, screen='c2')
    original_outcome = deepcopy(outcome)
    manifest = TU.c2_metadata(table, outcome, {'ready': True}, binding=binding)
    assert manifest['expected_value_authorized'] is (binding and primary_passes)
    if not binding:
        assert manifest['authorization'] == 'dry run: no expected value authorization'
    assert manifest['c2_outcome'] == original_outcome
    assert manifest['score_table'] == before
    assert table == before
    assert TU.adequacy(table, screen='c2') == original_outcome


def test_handoff_refuses_false_execution_authorization(monkeypatch):
    manifest = synthetic_manifest(monkeypatch, binding=False)
    manifest['expected_value_authorized'] = True
    with pytest.raises(ValueError, match='authorization disagrees'):
        TU.validate_c2_handoff(manifest, require_binding=False)


def test_dry_run_cli_marks_both_score_and_selection_artifacts(monkeypatch, tmp_path):
    import sys
    table = passing_table()
    before = deepcopy(table)
    outcome = TU.adequacy(table, screen='c2')
    monkeypatch.setattr(TB, 'run_candidate_backtest', lambda *args, **kwargs: table)
    monkeypatch.setattr(TU, 'binding_input_provenance', lambda **kwargs: {'ready': False})
    monkeypatch.setattr(TU, 'committed_c2_rule_hash', lambda: 'frozen-section')
    monkeypatch.setattr(sys, 'argv', ['ts_uncertainty', '--screen', 'c2', '--scores-only',
                                    '--output', str(tmp_path)])
    TU.main()
    scores = json.loads((tmp_path / 'scores.json').read_text())
    selection = json.loads((tmp_path / 'selection.json').read_text())
    for artifact in (scores, selection):
        assert artifact['run_kind'] == 'dry_run'
        assert len(artifact['scoring_head']) == 40
        assert artifact['expected_value_authorized'] is False
        assert artifact['authorization'] == 'dry run: no expected value authorization'
    assert scores['input_hashes'] == TU.handoff_input_hashes()
    assert selection['scoring_inputs_sha256'] == TU._canonical_hash(scores['input_hashes'])
    assert selection['effective_ruling'] == outcome['effective_ruling'] == 'c'
    assert scores['scores'] == before['scores']
    assert scores['past_years'] == before['past_years']
    assert TU.adequacy(scores, screen='c2') == outcome


@pytest.mark.parametrize('scoring_head', [None, 'not-a-commit', '0' * 40])
def test_handoff_refuses_missing_or_malformed_scoring_provenance(monkeypatch, scoring_head):
    manifest = synthetic_manifest(monkeypatch)
    manifest['scoring_head'] = scoring_head
    with pytest.raises(ValueError, match='scoring head'):
        TU.validate_c2_handoff(manifest)


def test_handoff_accepts_absent_scoring_commit_when_file_hashes_match(monkeypatch):
    manifest = synthetic_manifest(monkeypatch)
    # Provenance can refer to a commit outside a shallow/squashed checkout.
    # Current source/data files and the frozen rule content are the binding.
    monkeypatch.setattr(TU, '_git_bytes', lambda *args: pytest.fail('historical Git objects must not be read'))
    assert TU.validate_c2_handoff(manifest)['selected_primary'] == TU.PRIMARY_FORM


@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_handoff_refuses_score_input_hash_drift_even_with_matching_score_hash(monkeypatch, fault):
    manifest = synthetic_manifest(monkeypatch)
    if fault == 'missing':
        manifest['score_table'].pop('input_hashes')
    else:
        manifest['score_table']['input_hashes']['ts_uncertainty.py'] = '0' * 64
    manifest['score_table_sha256'] = TU._canonical_hash(manifest['score_table'])
    with pytest.raises(ValueError, match='scoring file hashes'):
        TU.validate_c2_handoff(manifest)
