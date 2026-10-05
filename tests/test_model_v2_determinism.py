"""Aggregate-only fingerprint and minimum-cell rules, without microsimulation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location(
    "model_v2_determinism", Path(__file__).parents[1] / "scripts" / "run_model_v2_determinism.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_fingerprint_is_key_order_invariant_and_preserves_float_bits():
    assert driver.fingerprint({'a': 1., 'b': 2.}) == driver.fingerprint({'b': 2., 'a': 1.})
    assert driver.fingerprint({'a': 1.}) != driver.fingerprint({'a': float(np.nextafter(1., 2.))})
    assert driver.fingerprint({'a': 0.}) != driver.fingerprint({'a': -0.})
    with pytest.raises(ValueError):
        driver.fingerprint({'a': np.nan})


@pytest.mark.parametrize('changed', (
    'aggregate_sha256', 'calculation_head', 'source_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
    'package_sha256', 'dataset_sha256', 'full_spec_sha256'))
def test_determinism_requires_matching_aggregates_and_every_provenance_hash(changed):
    first = {key: 'a' for key in (
        'aggregate_sha256', 'calculation_head', 'source_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
        'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    first['cold_cache'] = True
    assert driver.compare_runs(first, first)['passed']
    second = {**first, changed: 'b'}
    result = driver.compare_runs(first, second)
    assert not result['passed'] and not result['matching_hashes'][changed]


def test_determinism_requires_two_cold_caches():
    run = {key: 'same' for key in ('aggregate_sha256', 'calculation_head', 'source_sha256',
        'engine_semantics_sha256', 'engine_file_sha256', 'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    run['cold_cache'] = True
    assert driver.compare_runs(run, run)['passed']
    assert not driver.compare_runs(run, {**run, 'cold_cache': False})['passed']


def test_signed_fiscal_cells_apply_the_same_minimum_contributor_floor():
    assert driver.supported_cell(0, 0.)['records'] == 0
    assert driver.supported_cell(10, -2.)['records'] == 10
    for amount in (-2., 2.):
        with pytest.raises(RuntimeError, match='ten-household'):
            driver.supported_cell(9, amount)


def test_source_fingerprint_covers_demography_and_dependencies(tmp_path):
    (tmp_path / 'src').mkdir()
    module = tmp_path / 'src' / 'demography.py'
    module.write_text('original')
    dependency = tmp_path / 'pyproject.toml'
    dependency.write_text('original')
    original = driver.source_fingerprint(tmp_path)
    module.write_text('changed')
    assert driver.source_fingerprint(tmp_path) != original
    module.write_text('original')
    dependency.write_text('changed')
    assert driver.source_fingerprint(tmp_path) != original
    dependency.write_text('original')
    (tmp_path / 'requirements-lock.txt').write_text('pinned-dependency==1.0')
    assert driver.source_fingerprint(tmp_path) != original


def test_selected_fingerprint_reads_only_reporting_years_from_completed_aggregates():
    values = {'saving_bn': {'2027': {'uk': {'net': 0.}}, '2034': {'uk': {'net': 1.}},
                           '2039': {'uk': {'net': 2.}}},
              'totals_bn': {'triple_lock': {'2027': {'uk': {'gov_balance': 0.}},
                                           '2034': {'uk': {'gov_balance': 1.}},
                                           '2039': {'uk': {'gov_balance': 2.}}}}}
    selected = driver.selected_aggregates(values, [2034, 2039])
    assert set(selected['saving_bn']) == {'2034', '2039'}
    assert set(selected['totals_bn']['triple_lock']) == {'2034', '2039'}
    assert '2027' in values['saving_bn']


def test_current_control_never_changes_historical_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    control = tmp_path / '.cache' / 'microcosm-check'
    control.mkdir(parents=True)
    (control / 'current-head-control.json').write_text('{"paused":true}')
    old = {'label': 'd_both', 'head': driver.D_BOTH}
    assert driver.current_configuration(old) is old


def test_current_control_rearchives_released_full_head(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    control = tmp_path / '.cache' / 'microcosm-check'
    control.mkdir(parents=True)
    head = 'f' * 40
    (control / 'current-head-control.json').write_text('{"paused":false,"head":"' + head + '"}')
    old_source = tmp_path / 'old-source'
    old_data = old_source / '.cache' / 'datasets'
    old_data.mkdir(parents=True)
    (old_data / 'survey.h5').write_bytes(b'file fixture, no survey records')
    fresh = tmp_path / 'fresh-source'
    fresh.mkdir()
    calls = []

    def archive(workspace, git_dir, actual_head, label):
        calls.append(actual_head)
        return fresh

    monkeypatch.setattr(driver, 'archive_source', archive)
    original = {'label': 'current_first', 'head': '0' * 40, 'source': str(old_source)}
    chosen = driver.current_configuration(original)
    assert calls == [head] and chosen['head'] == head
    assert chosen['cold_cache'] and chosen['source'] == str(fresh)
    assert (fresh / '.cache' / 'datasets' / 'survey.h5').read_bytes() == (old_data / 'survey.h5').read_bytes()


def test_public_microcosm_receipt_keeps_counts_hashes_and_flags_without_duplicate_fiscal_tables(tmp_path):
    import json

    aggregate = {'saving_bn': {'2034': {'uk': {'gross': 2., 'net': 1.}},
                               '2039': {'uk': {'gross': 3., 'net': 2.}}}}
    historical = tmp_path / 'historical.json'
    historical.write_text(json.dumps({'legacy': aggregate}))
    row = {'label': 'd_legacy', 'treatment': 'legacy', 'aggregates': aggregate,
           'aggregate_sha256': driver.fingerprint(aggregate), 'cells': {'2039': {'uk': {'saving': {'gross': 10}}}}}
    output = tmp_path / 'receipt.json'
    driver.write_public(output, [row], [], historical)
    published = json.loads(output.read_text())
    assert published['comparisons']['d_legacy']['rerun_matches_retained_D_2034_2039']
    assert 'aggregates' not in published['runs'][0]
    assert published['runs'][0]['cells'] == row['cells']
    assert published['runs'][0]['aggregate_sha256'] == row['aggregate_sha256']
