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
