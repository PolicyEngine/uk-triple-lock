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


def test_committed_source_fingerprint_matches_files_and_excludes_document_only_edits(tmp_path, monkeypatch):
    import io
    import tarfile
    from types import SimpleNamespace

    (tmp_path / 'src').mkdir()
    files = {'src/demography.py': b'VALUE = 1\n', 'pyproject.toml': b'dependencies=[]\n',
             'requirements-lock.txt': b'pinned==1\n', 'docs/METHOD.md': b'document-only text\n'}
    for name, contents in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def fake_git(command, **kwargs):
        if 'ls-tree' in command:
            return SimpleNamespace(stdout='\0'.join(files).encode() + b'\0')
        selected = command[command.index('archive') + 2:]
        assert 'requirements-lock.txt' in selected and 'docs/METHOD.md' not in selected
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:') as tar:
            for name in selected:
                info = tarfile.TarInfo(name)
                info.size = len(files[name])
                tar.addfile(info, io.BytesIO(files[name]))
        return SimpleNamespace(stdout=stream.getvalue())

    monkeypatch.setattr(driver.subprocess, 'run', fake_git)
    assert driver.committed_source_fingerprint(tmp_path / '.git-e', 'f' * 40) == driver.source_fingerprint(tmp_path)


def test_published_current_cold_runs_match_the_checked_out_scientific_sources():
    import json

    repo = Path(__file__).parents[1]
    receipt = repo / 'data' / 'pilot' / 'microcosm_support_and_determinism.json'
    if not receipt.exists():
        pytest.skip('the full-run cold-check receipt is not committed yet')
    public = json.loads(receipt.read_text())
    rows = [row for row in public['runs'] if row['label'].startswith('current')]
    if not rows:
        pytest.skip('current-head cold runs are still pending')
    assert all(row['source_sha256'] == driver.source_fingerprint(repo) for row in rows)


def test_a_published_source_mismatch_fails_even_if_the_receipt_is_partial(tmp_path, monkeypatch):
    import json

    monkeypatch.setitem(globals(), '__file__', str(tmp_path / 'tests' / 'test_model_v2_determinism.py'))
    receipt = tmp_path / 'data' / 'pilot' / 'microcosm_support_and_determinism.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'complete': False, 'status': 'in progress',
        'runs': [{'label': 'current_first', 'source_sha256': 'mismatched'}]}))
    with pytest.raises(AssertionError):
        test_published_current_cold_runs_match_the_checked_out_scientific_sources()


def test_reuse_requires_both_actual_original_heads_and_untampered_aggregates(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(driver, 'committed_source_fingerprint', lambda *args: 'source')
    aggregates = {'saving_bn': {str(y): {} for y in range(2027, 2040)}, 'totals_bn': {}}
    paths = []
    for label, head in [('d_legacy', driver.D_LEGACY), ('d_both', driver.D_BOTH)]:
        row = {'label': label, 'calculation_head': head, 'dataset': driver.MICROCOSM,
               'passed': True, 'cold_cache': True, 'minimum_contributing_records': 10,
               'aggregates': aggregates, 'aggregate_sha256': driver.fingerprint(aggregates),
               'source_sha256': 'source',
               'cells': {'2039': {'uk': {'saving': {'gross': 20}}, 'gb': {'saving': {'gross': 10}}}}}
        path = tmp_path / f'{label}.json'
        path.write_text(json.dumps(row))
        paths.append(path)
    assert [row['label'] for row in driver.load_historical_receipts(paths[::-1], tmp_path)] == ['d_legacy', 'd_both']
    with pytest.raises(ValueError, match='exactly'):
        driver.load_historical_receipts(paths[:1], tmp_path)
    row['aggregate_sha256'] = 'changed'
    paths[-1].write_text(json.dumps(row))
    with pytest.raises(ValueError, match='aggregate fingerprint'):
        driver.load_historical_receipts(paths, tmp_path)


def test_two_microcosm_workers_require_validated_receipts_and_eighty_gib_admission():
    for available in (64, 76, 79.99):
        with pytest.raises(RuntimeError, match='80 GiB'):
            driver.check_parallel_admission(2, True, {'available_bytes': available * 2**30})
    driver.check_parallel_admission(2, True, {'available_bytes': 80 * 2**30})
    with pytest.raises(ValueError, match='validated historical'):
        driver.check_parallel_admission(2, False, {'available_bytes': 120 * 2**30})
    with pytest.raises(ValueError, match='one or two'):
        driver.check_parallel_admission(3, True, {'available_bytes': 120 * 2**30})


@pytest.mark.parametrize('uk,gb', [(19, 10), (25, 20), (9, 0), (20, 9), (20, 21)])
def test_linked_counts_protect_small_geographic_complements(uk, gb):
    cells = {'2039': {'uk': {'saving': {'gross': uk}}, 'gb': {'saving': {'gross': gb}}}}
    with pytest.raises(RuntimeError, match='complement floor'):
        driver.validate_support_counts(cells)


def test_linked_counts_allow_zero_and_ten_record_complements():
    cells = {'2039': {'uk': {'saving': {'gross': 20, 'net': 10}},
                      'gb': {'saving': {'gross': 10, 'net': 10}}}}
    assert driver.validate_support_counts(cells) == 10
    with pytest.raises(RuntimeError, match='both UK and GB'):
        driver.validate_support_counts({'2039': {'uk': {'saving': {'gross': 20}}}})


def test_explicit_new_cli_head_cannot_be_redirected_by_a_stale_control_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    control = tmp_path / '.cache' / 'microcosm-check'
    control.mkdir(parents=True)
    (control / 'current-head-control.json').write_text('{"paused":true}')
    configuration = {'label': 'current_first', 'head': 'f' * 40, 'honour_current_head_control': False}
    assert driver.current_configuration(configuration) is configuration


def test_parallel_microcosm_repeats_have_separate_cold_archives_and_full_fiscal_defaults(tmp_path, monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    data = tmp_path / 'synthetic.h5'
    data.write_bytes(b'fixture without survey data')
    store = tmp_path / 'receipts'
    store.mkdir()
    configurations = []
    monkeypatch.setattr(driver, 'resource_receipt', lambda: {'available_bytes': 2**40})

    def archive(workspace, git_dir, head, label):
        path = tmp_path / label
        path.mkdir()
        return path

    class FakeProcess:
        def __init__(self, command, **kwargs):
            configuration = json.loads(Path(command[-2]).read_text())
            configurations.append(configuration)
            Path(command[-1]).write_text(json.dumps({'label': configuration['label']}))

        def wait(self):
            return 0

    monkeypatch.setattr(driver, 'archive_source', archive)
    monkeypatch.setattr(driver.subprocess, 'Popen', FakeProcess)
    args = SimpleNamespace(current_head='f' * 40, git_dir=tmp_path / '.git-e', run_label='test',
                           workers=2, minimum_available_gib=44)
    plans = [(label, args.current_head, 'both') for label in ('current_first', 'current_repeat')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda plan: driver.execute_mc_job(plan, args, tmp_path, data, store, {}), plans))
    assert len(rows) == 2 and len(configurations) == 2
    assert configurations[0]['source'] != configurations[1]['source']
    assert all(row['cold_cache'] and not row['honour_current_head_control'] for row in configurations)
    assert all('fiscal_output_years' not in row for row in configurations)


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
           'aggregate_sha256': driver.fingerprint(aggregate),
           'cells': {'2039': {'uk': {'saving': {'gross': 20}}, 'gb': {'saving': {'gross': 10}}}}}
    output = tmp_path / 'receipt.json'
    driver.write_public(output, [row], [], historical)
    published = json.loads(output.read_text())
    assert published['comparisons']['d_legacy']['rerun_matches_retained_D_2034_2039']
    assert 'aggregates' not in published['runs'][0]
    assert published['runs'][0]['cells'] == row['cells']
    assert published['runs'][0]['aggregate_sha256'] == row['aggregate_sha256']
