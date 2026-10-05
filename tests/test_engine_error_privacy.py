"""Isolated demographic jobs redact child failures while retaining job transport."""

import json
from pathlib import Path
import traceback

import pytest

from triple_lock import engine


PRIVATE_VALUE = "household_id=991337 private_weight=28765.4321 pension_amount=14392.76"
CHILD_ERROR = "Traceback (most recent call last):\nValueError: " + PRIVATE_VALUE


@pytest.mark.parametrize("mode", ["frozen", "reweight", "types", "both"])
def test_demographic_isolated_failure_withholds_child_values_and_traceback(tmp_path, monkeypatch, capsys, mode):
    def failed_child(cmd, cwd, env=None, stop=None):
        assert Path(cmd[-2]).exists()
        return 23, "synthetic stdout " + PRIVATE_VALUE, CHILD_ERROR

    monkeypatch.setattr(engine, "run_child", failed_child)
    with pytest.raises(RuntimeError) as caught:
        engine._run_isolated("path", {"demography": mode}, tmp_path, {})
    message = str(caught.value)
    formatted = "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert "exit 23" in message
    assert "child diagnostics withheld" in message
    for fragment in (PRIVATE_VALUE, "991337", "28765.4321", "14392.76", "ValueError:"):
        assert fragment not in message
        assert fragment not in formatted
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert not list(tmp_path.glob("input-*.json"))
    assert not list(tmp_path.glob("output-*.json"))


@pytest.mark.parametrize("kind,arg", [("path", {}), ("path", {"demography": "legacy"}),
                                      ("history", {"demography": "both"})])
def test_legacy_and_other_isolated_job_errors_keep_existing_child_diagnostics(tmp_path, monkeypatch, kind, arg):
    monkeypatch.setattr(engine, "run_child", lambda *args, **kwargs: (23, "", CHILD_ERROR))
    with pytest.raises(RuntimeError) as caught:
        engine._run_isolated(kind, arg, tmp_path, {})
    assert CHILD_ERROR in str(caught.value)
    assert "child diagnostics withheld" not in str(caught.value)
    assert not list(tmp_path.glob("input-*.json"))


@pytest.mark.parametrize("mode", ["legacy", "both"])
def test_successful_isolated_job_returns_identical_output_and_cleans_transport(tmp_path, monkeypatch, mode):
    # A synthetic result tests transport; no tax-benefit model is run here.
    output = {"saving_bn": {"2039": 1.25}, "fixed_inputs": {"demography": mode}}

    def successful_child(cmd, cwd, env=None, stop=None):
        inp, out = Path(cmd[-2]), Path(cmd[-1])
        assert json.loads(inp.read_text())["arg"]["demography"] == mode
        out.write_text(json.dumps(output))
        return 0, "synthetic stdout " + PRIVATE_VALUE, CHILD_ERROR

    monkeypatch.setattr(engine, "run_child", successful_child)
    assert engine._run_isolated("path", {"demography": mode}, tmp_path, {}) == output
    assert not list(tmp_path.glob("input-*.json"))
    assert not list(tmp_path.glob("output-*.json"))
