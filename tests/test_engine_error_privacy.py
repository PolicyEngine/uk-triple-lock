"""A failed job under an ageing treatment keeps its error output out of the build's log (jobs._run_isolated)."""

import json
import stat
import traceback
from pathlib import Path

import pytest

from triple_lock import jobs
from triple_lock.config import DEMOGRAPHY

PRIVATE_VALUE = "household_id=991337 private_weight=28765.4321 pension_amount=14392.76"
CHILD_ERROR = "Traceback (most recent call last):\nValueError: " + PRIVATE_VALUE


@pytest.mark.parametrize("kind,arg", [("path", {"demography": m}) for m in ("frozen", "reweight", "types", "both")]
                         + [("path", {}), ("coverage", {"demography": "both"}), ("history", {})])
def test_ageing_job_failure_keeps_child_output_private(tmp_path, monkeypatch, capsys, kind, arg):
    def failed_child(cmd, cwd, env=None, stop=None):
        assert Path(cmd[-2]).exists()
        return 23, "synthetic stdout " + PRIVATE_VALUE, CHILD_ERROR

    monkeypatch.setattr(jobs, "run_child", failed_child)
    with pytest.raises(RuntimeError) as caught:
        jobs._run_isolated(kind, arg, tmp_path, {})
    message = str(caught.value)
    formatted = "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert "exit 23" in message and "kept privately" in message
    for fragment in (PRIVATE_VALUE, "991337", "28765.4321", "14392.76", "ValueError:"):
        assert fragment not in message
        assert fragment not in formatted
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    kept = list(tmp_path.glob("failed-*.stderr"))
    assert len(kept) == 1 and kept[0].read_text() == CHILD_ERROR
    assert stat.S_IMODE(kept[0].stat().st_mode) == 0o600
    assert not list(tmp_path.glob("input-*.json")) and not list(tmp_path.glob("output-*.json"))


@pytest.mark.parametrize("kind,arg", [("path", {"demography": "legacy"}), ("coverage", {"demography": "legacy"}),
                                      ("examples", {})])
def test_legacy_and_other_job_errors_keep_their_diagnostics(tmp_path, monkeypatch, kind, arg):
    monkeypatch.setattr(jobs, "run_child", lambda *args, **kwargs: (23, "", CHILD_ERROR))
    with pytest.raises(RuntimeError) as caught:
        jobs._run_isolated(kind, arg, tmp_path, {})
    assert CHILD_ERROR in str(caught.value)
    assert not list(tmp_path.glob("failed-*.stderr"))
    assert not list(tmp_path.glob("input-*.json"))


def test_the_default_treatment_is_an_ageing_one():
    assert DEMOGRAPHY != "legacy" and jobs.private_inputs("path", {})


@pytest.mark.parametrize("mode", ["legacy", "both"])
def test_successful_job_returns_its_output_and_cleans_transport(tmp_path, monkeypatch, mode):
    # A synthetic result tests transport; no tax-benefit model is run here.
    output = {"saving_bn": {"2039": 1.25}, "fixed_inputs": {"demography": mode}}

    def successful_child(cmd, cwd, env=None, stop=None):
        inp, out = Path(cmd[-2]), Path(cmd[-1])
        assert json.loads(inp.read_text())["arg"]["demography"] == mode
        out.write_text(json.dumps(output))
        return 0, "synthetic stdout " + PRIVATE_VALUE, CHILD_ERROR

    monkeypatch.setattr(jobs, "run_child", successful_child)
    assert jobs._run_isolated("path", {"demography": mode}, tmp_path, {}) == output
    assert not list(tmp_path.glob("input-*.json")) and not list(tmp_path.glob("output-*.json"))
    assert not list(tmp_path.glob("failed-*.stderr"))
