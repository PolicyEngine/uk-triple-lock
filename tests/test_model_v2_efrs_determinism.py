"""Cold Enhanced FRS case selection and aggregate comparisons without PE."""

import importlib.util
from pathlib import Path
import sys


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("efrs_determinism", SCRIPTS / "run_model_v2_efrs_determinism.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_plan_repeats_four_original_pilot_cases_and_keeps_the_macro_specs():
    central = {"cpi": {2027: .02}}
    paired = {"cpi": {2027: .04}}
    rows = driver.plan({"central": central, "paired": {"2948": {"spec": paired}}})
    assert len(rows) == 8 and len({row["label"] for row in rows}) == 8
    cases = {row["case"] for row in rows}
    assert cases == {"central_legacy", "central_frozen", "central_both", "draw_2948_both"}
    for case in cases:
        pair = [row for row in rows if row["case"] == case]
        assert {row["repeat"] for row in pair} == {"first", "repeat"}
        assert pair[0]["specification"] is pair[1]["specification"]
    assert next(row for row in rows if row["case"] == "draw_2948_both")["specification"] is paired
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


def test_two_worker_admission_runs_all_cases_in_pairs_without_extra_workers(tmp_path, monkeypatch):
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
    monkeypatch.setattr(driver, 'write_public', lambda out, runs, resources, specs, workers:
                        writes.append((len(runs), workers)))
    args = SimpleNamespace(out=tmp_path / 'out.json', head='f' * 40, specs=specs,
                           workers=2, minimum_available_gib=1, git_dir=tmp_path / '.git-e', run_label='test')
    driver.main(args)
    assert peak == 2 and len(completed) == len(set(completed)) == 8
    assert writes[-1] == (8, 2)


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
