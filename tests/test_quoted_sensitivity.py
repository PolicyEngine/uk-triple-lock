"""Quoted ranges use the estimator's eligibility decision, in both public readers."""

import copy
import json
import shutil
import subprocess

import pytest
from hypothesis import given, strategies as st

from triple_lock.config import FINAL_YEAR, OUTPUT, REPO
from triple_lock.pipeline import MissingFigure, _paths_item, assumptions


def row(mean, *, flag=True, runs=100):
    out = {"gross": {str(FINAL_YEAR): {"mean": mean, "se": 0.1}}, "effective_runs": runs}
    if flag is not None:
        out["included_in_quoted_range"] = flag
    return out


def results_with(rows):
    return {"expected_value": {"primary": "means_shift", "sensitivities": rows},
            "trajectories": {"models": {"boot": {"runs_paths": True}}}}


@given(st.lists(st.tuples(st.floats(min_value=-100, max_value=100, allow_nan=False),
                         st.booleans(), st.integers(min_value=1, max_value=500)), max_size=30),
       st.floats(min_value=-1000, max_value=1000, allow_nan=False))
def test_quoted_range_never_includes_excluded_rows_and_adding_one_cannot_move_it(rows, excluded_mean):
    sensitivities = {"shift_dynamics.anchor": row(0)}
    sensitivities.update({f"shift_dynamics.{i}": row(mean, flag=flag, runs=runs)
                          for i, (mean, flag, runs) in enumerate(rows)})
    data = results_with(sensitivities)
    facts = _paths_item(data)["facts"]
    allowed = {name: value for name, value in sensitivities.items() if value["included_in_quoted_range"]}
    means = [value["gross"][str(FINAL_YEAR)]["mean"] for value in allowed.values()]
    assert facts["lowest"]["mean"] == min(means) <= facts["highest"]["mean"] == max(means)
    assert facts["reweightings"] == len(allowed)
    assert facts["lowest"]["calibration"] in allowed and facts["highest"]["calibration"] in allowed
    sensitivities["shift_dynamics.excluded"] = row(excluded_mean, flag=False, runs=1000)
    after = _paths_item(data)["facts"]
    assert (after["lowest"], after["highest"]) == (facts["lowest"], facts["highest"])


def test_flag_takes_precedence_over_effective_runs_and_other_families_are_separate():
    data = results_with({"shift_dynamics.allowed": row(8, flag=True, runs=1),
                         "shift_dynamics.excluded": row(-100, flag=False, runs=1000),
                         "other.allowed": row(1000, flag=True)})
    facts = _paths_item(data)["facts"]
    assert facts["lowest"]["mean"] == facts["highest"]["mean"] == 8
    assert facts["reweightings"] == facts["reweightings_too_few_runs"] == 1
    assert facts["other_sensitivities"] == ["other.allowed"]


@pytest.mark.parametrize("runs, included", [(99.999, False), (100, True), (101, True),
                                         (None, False), (True, False), ("100", False),
                                         (float("inf"), False), (float("nan"), False)])
def test_legacy_rows_without_flags_need_at_least_100_finite_effective_runs(runs, included):
    data = results_with({"shift_dynamics.anchor": row(8),
                         "shift_dynamics.legacy": row(3, flag=None, runs=runs)})
    facts = _paths_item(data)["facts"]
    assert facts["reweightings"] == 1 + included
    assert facts["lowest"]["mean"] == (3 if included else 8)


def test_no_eligible_reweighting_refuses_to_quote_a_range():
    with pytest.raises(MissingFigure, match="none.*enough effective runs"):
        _paths_item(results_with({"shift_dynamics.excluded": row(3, flag=False)}))


def test_small_exclusion_count_is_spelled_in_words():
    rows = {"shift_dynamics.allowed": row(8)}
    rows.update({f"shift_dynamics.excluded.{i}": row(3, flag=False) for i in range(6)})
    item = _paths_item(results_with(rows))
    facts = item["facts"]
    assert facts["reweightings"] == 1 and facts["reweightings_too_few_runs"] == 6
    assert "Six more reweightings" in item["text"]


@pytest.mark.skipif(shutil.which("node") is None, reason="dashboard differential check needs Node.js")
def test_dashboard_range_on_committed_results_equals_live_pipeline_assumptions():
    data = json.loads(OUTPUT.read_text())
    if not any(name.startswith("shift_dynamics")
               for name in data.get("expected_value", {}).get("sensitivities", {})):
        pytest.skip("the committed release has no quoted reweightings (scenarios only)")
    # Pass filenames as arguments: the dashboard executes its actual production reader against the unchanged file.
    script = """
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
const { getSensitivityRange } = await import(pathToFileURL(process.argv[1]));
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify({gross: getSensitivityRange(data, 'gross', data.final_year),
                            net: getSensitivityRange(data, 'net', data.final_year)}));
"""
    completed = subprocess.run(["node", "--input-type=module", "-e", script,
                                str(REPO / "dashboard/src/lib/dataHelpers.js"), str(OUTPUT)],
                               check=True, text=True, capture_output=True)
    ranges = json.loads(completed.stdout)
    facts = next(item["facts"] for item in assumptions(copy.deepcopy(data)) if item["key"] == "paths")
    assert ranges["gross"]["lo"] == facts["lowest"]["mean"]
    assert ranges["gross"]["hi"] == facts["highest"]["mean"]
    assert ranges["gross"]["n"] == facts["reweightings"]
    assert ranges["gross"]["excluded"] == facts["reweightings_too_few_runs"]
    allowed = [row for name, row in data["expected_value"]["sensitivities"].items()
               if name.startswith("shift_dynamics") and
               row.get("included_in_quoted_range", row.get("effective_runs", 0) >= 100)]
    net_means = [row["net"][str(FINAL_YEAR)]["mean"] for row in allowed]
    assert (ranges["net"]["lo"], ranges["net"]["hi"]) == (min(net_means), max(net_means))
