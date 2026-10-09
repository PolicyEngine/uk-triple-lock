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


def test_independent_cold_runs_use_float_tolerance_and_report_exact_fingerprint_separately():
    hashes = {key: 'same' for key in ('calculation_head', 'source_sha256',
        'engine_semantics_sha256', 'engine_file_sha256', 'package_sha256', 'dataset_sha256', 'full_spec_sha256')}

    def run(net):
        aggregates = {'saving_bn': {'2039': {'uk': {'net': net}}}, 'totals_bn': {}}
        return {**hashes, 'cold_cache': True, 'aggregates': aggregates,
                'aggregate_sha256': driver.fingerprint(aggregates), 'aggregate_fingerprint_years': [2039]}

    first = run(.6332)
    replay = run(.6330)
    comparison = driver.compare_runs(first, replay)
    assert comparison['passed'] and not comparison['bit_identical_aggregates']
    assert comparison['aggregate_values_within_tolerance']
    assert comparison['absolute_tolerance_bn'] == .001 and comparison['relative_tolerance'] == 0.
    assert not driver.compare_runs(first, run(.6319))['passed']
    assert not driver.compare_runs(first, {**replay, 'source_sha256': 'changed'})['passed']


@pytest.mark.parametrize('candidate, expected', [(0.6330, True), (0.6319, False), (np.nan, False)])
def test_retained_replay_uses_one_million_pound_absolute_tolerance(candidate, expected):
    def aggregates(net):
        return {'saving_bn': {str(year): {'uk': {'net': net}, 'gb': {'net': .5}}
                              for year in (2034, 2039)}}

    comparison = driver.retained_replay_comparison(aggregates(candidate), aggregates(.6332))
    assert comparison['rerun_matches_retained_D_2034_2039_within_tolerance'] is expected
    assert comparison['absolute_tolerance_bn'] == .001
    assert comparison['numeric_differences_published'] is False


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


def test_published_e_cold_runs_match_their_recorded_sources_and_current_fixed_spec_runtime():
    import json
    from cold_source_correspondence import verify_historical_cold_receipt

    repo = Path(__file__).parents[1]
    receipt = repo / 'data' / 'pilot' / 'microcosm_support_and_determinism.json'
    if not receipt.exists():
        pytest.skip('the full-run cold-check receipt is not committed yet')
    public = json.loads(receipt.read_text())
    rows = [row for row in public['runs'] if row['label'].startswith('current')]
    if not rows:
        pytest.skip('current-head cold runs are still pending')
    verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_a_published_source_mismatch_fails_even_if_the_receipt_is_partial(tmp_path, monkeypatch):
    import json

    monkeypatch.setitem(globals(), '__file__', str(tmp_path / 'tests' / 'test_model_v2_determinism.py'))
    receipt = tmp_path / 'data' / 'pilot' / 'microcosm_support_and_determinism.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'complete': False, 'status': 'in progress',
        'runs': [{'label': 'current_first', 'source_sha256': 'mismatched'}]}))
    with pytest.raises(AssertionError):
        test_published_e_cold_runs_match_their_recorded_sources_and_current_fixed_spec_runtime()


def test_historical_correspondence_rejects_a_changed_hash_at_a_valid_recorded_head():
    import json
    from cold_source_correspondence import verify_historical_cold_receipt

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    public.update(complete=False, status='in progress')
    row = next(row for row in public['runs'] if row['label'] == 'current_first')
    row['source_sha256'] = '0' * 64
    with pytest.raises(AssertionError, match='historical cold source hash must match its committed file binding'):
        verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_historical_correspondence_never_reads_old_git_objects(monkeypatch):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    monkeypatch.setattr(correspondence, 'git', lambda *args: pytest.fail('historical Git objects must not be read'))
    assert correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})['passed']


def test_historical_manifest_rejects_changed_file_bindings():
    import copy
    import json
    from cold_source_correspondence import source_binding

    repo = Path(__file__).parents[1]
    bindings = copy.deepcopy(json.loads((repo / 'data/pilot/cold-source-binding.json').read_text()))
    source_sha256 = next(iter(bindings['sources']))
    binding = bindings['sources'][source_sha256]
    binding['scientific_files_sha256']['src/triple_lock/engine.py'] = '0' * 64
    with pytest.raises(AssertionError, match='committed file binding'):
        source_binding(bindings, source_sha256)


def test_default_git_dir_uses_a_normal_clone_without_the_private_directory(tmp_path, monkeypatch):
    monkeypatch.delenv('GIT_DIR', raising=False)
    (tmp_path / '.git').mkdir()
    assert driver.default_git_dir(tmp_path) == tmp_path / '.git'
    (tmp_path / '.git-e').mkdir()
    assert driver.default_git_dir(tmp_path) == tmp_path / '.git-e'


@pytest.mark.parametrize('changed', ('src/triple_lock/engine.py', 'data/ons_npp_2024_uk_age_sex.csv',
                                    'data/pilot/d_macro_specs.json'))
def test_historical_correspondence_refuses_changed_fixed_spec_fiscal_sources_or_inputs(monkeypatch, changed):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    current[changed] += b'\n# synthetic tampering\n'
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='fixed-spec fiscal source'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_historical_correspondence_refuses_changed_expected_value_rule_arithmetic(monkeypatch):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    path = 'src/triple_lock/expected_value.py'
    changed = current[path].replace(b'return levels, rates', b'return rates, levels', 1)
    assert changed != current[path]
    current[path] = changed
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='reviewed current F module bytes changed'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('replacement', (
    'rule_levels: object = lambda *args, **kwargs: ("changed levels", "changed rates")\n',
    'if True:\n    rule_levels = lambda *args, **kwargs: ("changed levels", "changed rates")\n',
    'globals().__setitem__("rule_levels", lambda *args, **kwargs: ("changed levels", "changed rates"))\n',
))
def test_historical_correspondence_rejects_effective_top_level_rule_replacements(monkeypatch, replacement):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    path = 'src/triple_lock/expected_value.py'
    original = current[path]
    current[path] += b'\n' + replacement.encode()
    symbols, options = correspondence.PROTECTED_AST[path]
    # Each form bypassed the old protected-function AST subset and actually
    # replaces the callable when the amended module is executed.
    assert correspondence.selected_ast(current[path], symbols, **options) == \
        correspondence.selected_ast(original, symbols, **options)
    namespace = {'__name__': 'triple_lock.source_tamper_probe', '__package__': 'triple_lock'}
    exec(compile(current[path], path, 'exec'), namespace)
    assert namespace['rule_levels'](None, None, None) == ('changed levels', 'changed rates')
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='reviewed current F module bytes changed'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('changed', (
    'src/triple_lock/expected_value.py', 'src/triple_lock/pipeline.py',
    'src/triple_lock/ts_backtest.py', 'src/triple_lock/ts_uncertainty.py',
    'src/triple_lock/history_data.py',
))
def test_historical_correspondence_binds_every_authorized_f_module_byte(monkeypatch, changed):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    current[changed] += b'\n# any unreviewed byte change requires a new explicit binding\n'
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='reviewed current F module bytes changed'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('invalid_manifest', ('missing', 'unexpected'))
def test_historical_correspondence_requires_exact_f_module_binding_coverage(tmp_path, monkeypatch, invalid_manifest):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    bindings = json.loads((repo / correspondence.BINDING_FILE).read_text())
    reviewed = bindings['reviewed_current_F_files_sha256']
    if invalid_manifest == 'missing':
        reviewed.pop('src/triple_lock/expected_value.py')
    else:
        reviewed['src/triple_lock/unreviewed.py'] = '0' * 64
    binding_path = tmp_path / correspondence.BINDING_FILE
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(json.dumps(bindings))
    current = correspondence.current_files(repo)
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='binding must cover every authorized module'):
        correspondence.verify_historical_cold_receipt(tmp_path, public, {'current_first', 'current_repeat'})


def test_historical_correspondence_refuses_changed_history_data_error_blocks(monkeypatch):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    path = 'src/triple_lock/history_data.py'
    changed = current[path].replace(b'return blocks, kept', b'return blocks[::-1], kept', 1)
    assert changed != current[path]
    current[path] = changed
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='reviewed current F module bytes changed: src/triple_lock/history_data.py'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_historical_correspondence_refuses_changed_count_redaction(monkeypatch):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    current = correspondence.current_files(repo)
    path = 'src/triple_lock/pipeline.py'
    changed = current[path].replace(b'publish_count(count) for measure', b'count for measure', 1)
    assert changed != current[path]
    current[path] = changed
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    with pytest.raises(AssertionError, match='reviewed current F module bytes changed: src/triple_lock/pipeline.py'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('filename,labels', (
    ('microcosm_support_and_determinism.json', {'current_first', 'current_repeat'}),
    ('efrs_determinism.json', {'central_both_first', 'central_both_repeat'}),
))
def test_rebuild_entrypoint_proof_distinguishes_restored_historical_bytes(filename, labels):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot' / filename).read_text())
    bindings = json.loads((repo / correspondence.BINDING_FILE).read_text())
    proof = correspondence.verify_historical_cold_receipt(repo, public, labels)
    path = 'src/triple_lock/ageing_validation.py'
    current = (repo / path).read_bytes()
    restored = correspondence.rebuild_entrypoint_normalized_source(current)
    metadata = proof['rebuild_entrypoint_preflight'][path]
    assert set(proof['rebuild_entrypoint_preflight']) == {path}
    assert path not in proof['unchanged_fiscal_source_input_sha256']
    assert path in proof['changed_scientific_files']
    assert path not in proof['authorized_F_modules']
    assert metadata['accepted_file_sha256'] == correspondence.digest(current)
    assert metadata['restored_historical_file_sha256'] == correspondence.digest(restored)
    assert metadata['accepted_file_sha256'] != metadata['restored_historical_file_sha256']
    assert metadata['normalization_removes_only_reviewed_preflight_provenance_insertions'] is True
    for row in public['runs']:
        if row['label'] in labels:
            original = correspondence.source_binding(bindings, row['source_sha256'])
            assert correspondence.digest(restored) == original['scientific_files_sha256'][path]


@pytest.fixture
def rebuild_entrypoint_tamper_case(tmp_path, monkeypatch):
    import json
    import cold_source_correspondence as correspondence

    repo = Path(__file__).parents[1]
    public = json.loads((repo / 'data/pilot/microcosm_support_and_determinism.json').read_text())
    bindings = json.loads((repo / correspondence.BINDING_FILE).read_text())
    binding_path = tmp_path / correspondence.BINDING_FILE
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(json.dumps(bindings))
    current = correspondence.current_files(repo)
    monkeypatch.setattr(correspondence, 'current_files', lambda repo: current)
    return correspondence, tmp_path, public, current, bindings, binding_path


def test_rebuild_entrypoint_rejects_raw_current_byte_mutation(rebuild_entrypoint_tamper_case):
    correspondence, repo, public, current, _, _ = rebuild_entrypoint_tamper_case
    current['src/triple_lock/ageing_validation.py'] += b'\n# unreviewed current module byte\n'
    with pytest.raises(AssertionError, match='reviewed rebuild entrypoint bytes changed'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_rebuild_entrypoint_rejects_changed_arithmetic_even_with_refreshed_digest(rebuild_entrypoint_tamper_case):
    import json

    correspondence, repo, public, current, bindings, binding_path = rebuild_entrypoint_tamper_case
    path = 'src/triple_lock/ageing_validation.py'
    original = current[path]
    current[path] = original.replace(b'values["reweight"] - values["frozen"]',
                                     b'values["reweight"] - values["frozen"] + 0.25', 1)
    assert current[path] != original
    bindings['rebuild_entrypoint_preflight'][path]['accepted_file_sha256'] = correspondence.digest(current[path])
    binding_path.write_text(json.dumps(bindings))
    with pytest.raises(AssertionError, match='fixed-spec fiscal source changed outside exact rebuild CLI insertions'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('insertion', (0, 1))
@pytest.mark.parametrize('mutation', ('changed', 'missing', 'duplicated'))
def test_rebuild_entrypoint_rejects_changed_exact_insertion_with_refreshed_digest(
        rebuild_entrypoint_tamper_case, insertion, mutation):
    import json

    correspondence, repo, public, current, bindings, binding_path = rebuild_entrypoint_tamper_case
    path = 'src/triple_lock/ageing_validation.py'
    before, after = correspondence.REBUILD_ENTRYPOINT_EDITS[insertion]
    if mutation == 'changed':
        replacement = after.replace(b'preflight', b'replaced_preflight', 1)
    elif mutation == 'missing':
        replacement = before
    else:
        replacement = after + after
    assert current[path].count(after) == 1
    current[path] = current[path].replace(after, replacement, 1)
    bindings['rebuild_entrypoint_preflight'][path]['accepted_file_sha256'] = correspondence.digest(current[path])
    binding_path.write_text(json.dumps(bindings))
    with pytest.raises(AssertionError, match='reviewed rebuild preflight/provenance insertion changed'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


@pytest.mark.parametrize('invalid_manifest', ('missing', 'unexpected_module', 'unexpected_metadata'))
def test_rebuild_entrypoint_requires_exact_manifest_authorization(rebuild_entrypoint_tamper_case, invalid_manifest):
    import json

    correspondence, repo, public, _, bindings, binding_path = rebuild_entrypoint_tamper_case
    reviewed = bindings['rebuild_entrypoint_preflight']
    path = 'src/triple_lock/ageing_validation.py'
    if invalid_manifest == 'missing':
        reviewed.pop(path)
    elif invalid_manifest == 'unexpected_module':
        reviewed['src/triple_lock/jobs.py'] = {'accepted_file_sha256': '0' * 64, 'scope': 'unreviewed'}
    else:
        reviewed[path]['edits'] = ['arbitrary normalization is forbidden']
    binding_path.write_text(json.dumps(bindings))
    with pytest.raises(AssertionError, match='reviewed rebuild entrypoint binding'):
        correspondence.verify_historical_cold_receipt(repo, public, {'current_first', 'current_repeat'})


def test_reuse_requires_both_actual_original_heads_and_untampered_aggregates(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(driver, 'bound_historical_source', lambda *args: 'source')
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

    def fake_child(command, workspace, source, private_log, stop=None):
        configuration = json.loads(Path(command[-2]).read_text())
        configurations.append(configuration)
        Path(command[-1]).write_text(json.dumps({'label': configuration['label']}))
        return 0

    monkeypatch.setattr(driver, 'archive_source', archive)
    monkeypatch.setattr(driver, 'run_checked_child', fake_child)
    args = SimpleNamespace(current_head='f' * 40, git_dir=tmp_path / '.git-e', run_label='test',
                           workers=2, minimum_available_gib=44)
    plans = [(label, args.current_head, 'both') for label in ('current_first', 'current_repeat')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda plan: driver.execute_mc_job(plan, args, tmp_path, data, store, {}), plans))
    assert len(rows) == 2 and len(configurations) == 2
    assert configurations[0]['source'] != configurations[1]['source']
    assert all(row['cold_cache'] and not row['honour_current_head_control'] for row in configurations)
    assert all('fiscal_output_years' not in row for row in configurations)


@pytest.mark.parametrize('interruption', ['keyboard', 'term', 'failure'])
def test_cold_pool_stops_children_before_executor_shutdown(monkeypatch, interruption):
    from threading import Event
    from triple_lock import jobs
    import signal

    started, stopped = Event(), Event()
    calls = []

    def fake_kill(stop):
        calls.append('kill')
        stop.set()

    def active_child(stop):
        started.set()
        assert stop.wait(5), 'the coordinator joined its worker before stopping children'
        stopped.set()

    monkeypatch.setattr(jobs, 'kill_children', fake_kill)
    expected = {'keyboard': KeyboardInterrupt, 'term': jobs.Terminated, 'failure': RuntimeError}[interruption]
    with pytest.raises(expected):
        with driver.cold_pool(1) as (pool, stop):
            future = pool.submit(active_child, stop)
            assert started.wait(5)
            if interruption == 'keyboard':
                raise KeyboardInterrupt
            if interruption == 'term':
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            raise RuntimeError('synthetic failed run')
    assert stopped.is_set() and future.done() and calls == ['kill']


def test_cold_child_registration_preserves_stop_and_keeps_diagnostics_private(tmp_path, monkeypatch):
    from threading import Event
    from triple_lock import jobs

    stop = Event()
    calls = []

    def fake_run(command, *, cwd, env, stop):
        calls.append((command, cwd, env, stop))
        return 0, 'synthetic stdout\n', 'synthetic stderr\n'

    monkeypatch.setattr(jobs, 'run_child', fake_run)
    private = tmp_path / 'private.log'
    assert driver.run_checked_child(['synthetic-worker'], tmp_path, tmp_path / 'source', private, stop) == 0
    command, cwd, env, supplied_stop = calls[0]
    assert command == ['synthetic-worker'] and cwd == tmp_path and supplied_stop is stop
    assert env['PYTHONPATH'] == str(tmp_path / 'source' / 'src')
    assert all(env[key] == '1' for key in (
        'OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'))
    assert private.read_text() == 'synthetic stdout\nsynthetic stderr\n'


def test_stopped_cold_coordinator_never_starts_another_child(tmp_path):
    from threading import Event
    from triple_lock import jobs

    stop = Event()
    stop.set()
    with pytest.raises(jobs.Aborted):
        driver.run_checked_child(['must-never-start'], tmp_path, tmp_path, tmp_path / 'private.log', stop)


def test_interrupt_reaps_the_coordinators_registered_child_before_returning(tmp_path):
    """A real idle stand-in verifies pool cleanup without a PolicyEngine run."""
    import os
    import sys
    import time
    from triple_lock import jobs

    with pytest.raises(KeyboardInterrupt):
        with driver.cold_pool(1) as (pool, stop):
            future = pool.submit(jobs.run_child,
                [sys.executable, '-c', 'import time; time.sleep(30)'], tmp_path, stop=stop)
            deadline = time.monotonic() + 15
            while True:
                with jobs._children_lock:
                    registered = list(jobs._children.values())
                if registered:
                    break
                assert time.monotonic() < deadline, 'the harmless test child did not start'
                time.sleep(.01)
            assert len(registered) == 1
            child = registered[0]
            raise KeyboardInterrupt
    assert future.done() and future.result()[0] != 0
    assert child.poll() is not None
    with jobs._children_lock:
        assert child.pid not in jobs._children
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)


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
    assert published['comparisons']['d_legacy']['rerun_matches_retained_D_2034_2039_within_tolerance']
    assert published['comparisons']['d_legacy']['absolute_tolerance_bn'] == .001
    assert 'aggregates' not in published['runs'][0]
    assert published['runs'][0]['cells'] == row['cells']
    assert published['runs'][0]['aggregate_sha256'] == row['aggregate_sha256']
