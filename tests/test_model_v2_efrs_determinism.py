"""Cold Enhanced FRS case selection and aggregate comparisons without PE."""

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("efrs_determinism", SCRIPTS / "run_model_v2_efrs_determinism.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_plan_repeats_only_central_both_and_keeps_the_macro_specification():
    central = {"cpi": {2027: .02}}
    rows = driver.plan({"central": central})
    assert len(rows) == 2 and {row["label"] for row in rows} == {
        "central_both_first", "central_both_repeat"}
    assert {row["case"] for row in rows} == {"central_both"}
    assert {row["repeat"] for row in rows} == {"first", "repeat"}
    assert all(row["treatment"] == "both" and row["specification"] is central for row in rows)
    assert driver.TARGET_YEARS == [2034, 2039]


def test_comparison_waits_for_both_cold_runs_and_detects_any_changed_aggregate():
    hashes = {key: 'same' for key in (
        'aggregate_sha256', 'calculation_head', 'source_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
        'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    hashes['cold_cache'] = True
    first = {"case": "central_both", **hashes}
    assert driver.comparison_table([first]) == {}
    assert driver.comparison_table([first, first])["central_both"]["passed"]
    changed = {**first, "aggregate_sha256": "changed"}
    assert not driver.comparison_table([first, changed])["central_both"]["passed"]


def test_public_receipt_records_full_calculation_then_selected_fingerprint_years(tmp_path):
    import json

    specs = tmp_path / 'specs.json'
    specs.write_text('{}')
    out = tmp_path / 'receipt.json'
    run = {'case': 'central_both', 'aggregate_sha256': 'opaque',
           'aggregates': {'saving_bn': {'2039': {'uk': {'net': 1.}}}}}
    driver.write_public(out, [run], [], specs)
    public = json.loads(out.read_text())
    assert public['fiscal_output_years'] == list(range(2027, 2040))
    assert public['aggregate_fingerprint_years'] == [2034, 2039]
    assert 'aggregates' not in public['runs'][0]
    assert public['runs'][0]['aggregate_sha256'] == 'opaque'
    assert public['complete'] is False and public['status'] == 'in progress'


@pytest.mark.parametrize('correspondence', [None, {'passed': False}])
def test_complete_receipt_refuses_unmatched_final_scientific_source(tmp_path, correspondence):
    specs = tmp_path / 'specs.json'
    specs.write_text('{}')
    hashes = {key: 'same' for key in (
        'aggregate_sha256', 'calculation_head', 'source_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
        'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    rows = [{**row, **hashes, 'cold_cache': True} for row in driver.plan({'central': {}})]
    with pytest.raises(RuntimeError, match='source correspondence failed'):
        driver.write_public(tmp_path / 'out.json', rows, [], specs, correspondence=correspondence)


def test_complete_central_pair_receipt_records_source_correspondence(tmp_path):
    import json

    specs = tmp_path / 'specs.json'
    specs.write_text('{}')
    hashes = {key: 'same' for key in (
        'aggregate_sha256', 'calculation_head', 'source_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
        'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    rows = [{**row, **hashes, 'cold_cache': True} for row in driver.plan({'central': {}})]
    out = tmp_path / 'out.json'
    driver.write_public(out, rows, [], specs, correspondence={'passed': True})
    public = json.loads(out.read_text())
    assert public['complete'] and public['status'] == 'passed'
    assert public['final_head_scientific_source_correspondence'] == {'passed': True}
    assert public['comparisons']['central_both']['absolute_tolerance_bn'] == .001


def test_two_worker_admission_runs_only_central_pair_without_extra_workers(tmp_path, monkeypatch):
    import json
    from threading import Barrier, Lock
    from types import SimpleNamespace
    from triple_lock import datasets

    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'synthetic.h5'
    source.write_bytes(b'fixture without survey data')
    specs = tmp_path / 'specs.json'
    specs.write_text(json.dumps({'central': {}, 'paired': {'2948': {'spec': {}}}}))
    monkeypatch.setattr(datasets, 'materialize', lambda *args, **kwargs: source)
    barrier, lock = Barrier(2), Lock()
    active, peak, completed = 0, 0, []

    def fake_execute(row, *args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
            completed.append(row['label'])
        return dict(row), {'label': row['label']}

    writes = []
    monkeypatch.setattr(driver, 'execute_job', fake_execute)
    checks = []
    monkeypatch.setattr(driver, 'source_correspondence', lambda git_dir, runs, prefix:
                        checks.append((len(runs), prefix)) or {'passed': True})
    monkeypatch.setattr(driver, 'write_public', lambda out, runs, resources, specs, workers, correspondence:
                        writes.append((len(runs), workers, correspondence)))
    args = SimpleNamespace(out=tmp_path / 'out.json', head='f' * 40, specs=specs,
                           workers=2, minimum_available_gib=1, git_dir=tmp_path / '.git-e', run_label='test')
    driver.main(args)
    assert peak == 2 and len(completed) == len(set(completed)) == 2
    assert writes[-1] == (2, 2, {'passed': True})
    assert checks == [(2, 'central_both_')]


def test_each_repeat_keeps_a_distinct_source_and_cache_and_full_fiscal_default(tmp_path, monkeypatch):
    import json
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
    args = SimpleNamespace(head='f' * 40, git_dir=tmp_path / '.git-e', run_label='test',
                           workers=2, minimum_available_gib=1)
    rows = driver.plan({'central': {}, 'paired': {'2948': {'spec': {}}}})
    for row in rows[:2]:
        driver.execute_job(row, args, tmp_path, data, store)
    assert configurations[0]['source'] != configurations[1]['source']
    assert all(row['cold_cache'] for row in configurations)
    assert all('fiscal_output_years' not in row for row in configurations)
    assert all(row['fingerprint_years'] == [2034, 2039] for row in configurations)
