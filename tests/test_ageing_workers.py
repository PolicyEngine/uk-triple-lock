"""Persistent transport executes every request, cleans processes and keeps errors private."""

import io
import contextlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from triple_lock import ageing_validation as AV, engine


def request(tmp_path, token, value):
    inp, out = tmp_path / f"in-{token}.json", tmp_path / f"out-{token}.json"
    inp.write_text(json.dumps({"value": value}))
    return {"token": token, "input": str(inp), "output": str(out)}


def test_service_executes_each_job_and_discards_stale_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = request(tmp_path, "a" * 32, 7)
    second = request(tmp_path, "b" * 32, 9)
    Path(first["output"]).write_text("stale")
    calls = []

    def job(inp, out, initialise):
        assert not initialise and not out.exists()
        value = json.loads(inp.read_text())["value"]
        calls.append(value)
        print("model progress is private")
        out.write_text(json.dumps({"computed": value}))

    output = io.StringIO()
    assert AV.serve(io.StringIO("\n".join(map(json.dumps, [first, second]))), output, job, initialise=False) == 0
    receipts = [json.loads(line[len(AV.RECEIPT_PREFIX):]) for line in output.getvalue().splitlines()]
    assert calls == [7, 9]
    assert [r["token"] for r in receipts] == ["a" * 32, "b" * 32]
    assert all(r["ok"] for r in receipts)
    assert json.loads(Path(second["output"]).read_text()) == {"computed": 9}
    assert "model progress" not in output.getvalue()
    assert os.stat(tmp_path / "ageing-worker-model.log").st_mode & 0o777 == 0o600
    memory = [json.loads(line) for line in (tmp_path / "ageing-worker-model.log").read_text().splitlines()
              if line.startswith('{"worker_rss_gib"')]
    assert len(memory) == 2 and all(row["worker_rss_gib"] > 0 for row in memory)


def test_service_failure_does_not_publish_or_log_model_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = request(tmp_path, "a" * 32, 7)

    def job(*args, **kwargs):
        raise ValueError("private pension input 123456789")

    output = io.StringIO()
    assert AV.serve(io.StringIO(json.dumps(payload) + "\n"), output, job, initialise=False) == 1
    receipt = json.loads(output.getvalue()[len(AV.RECEIPT_PREFIX):])
    assert receipt == {"token": "a" * 32, "ok": False, "error": "ValueError"}
    assert "123456789" not in output.getvalue()
    assert "123456789" not in (tmp_path / "ageing-worker-model.log").read_text()


STUB = '''
import json, pathlib, sys
prefix = "TRIPLE_LOCK_AGEING_RECEIPT "
count = 0
for line in sys.stdin:
    request = json.loads(line)
    arg = json.loads(pathlib.Path(request["input"]).read_text())["arg"]
    count += 1
    if arg.get("fail"):
        receipt = {"token": request["token"], "ok": False, "error": "ValueError"}
    else:
        pathlib.Path(request["output"]).write_text(json.dumps({"computed": arg["value"], "execution": count}))
        receipt = {"token": request["token"], "ok": True}
    print("package progress", flush=True)
    print(prefix + json.dumps(receipt), flush=True)
'''


def test_persistent_runner_reuses_process_but_executes_fresh_jobs_and_cleans_registry(tmp_path):
    before = set(engine._children)
    with AV.PersistentRunner([sys.executable, "-u", "-c", STUB]) as runner:
        first = runner("ageing_path", {"value": 7}, tmp_path, {})
        second = runner("ageing_path", {"value": 9}, tmp_path, {})
        assert first == {"computed": 7, "execution": 1}
        assert second == {"computed": 9, "execution": 2}
        assert len(runner.all_workers) == 1
        proc = runner.all_workers[0]["process"]
        assert proc.pid in engine._children
        with pytest.raises(RuntimeError, match="ValueError"):
            runner("ageing_path", {"fail": True}, tmp_path, {})
    assert proc.poll() is not None and set(engine._children) == before
    assert not list(tmp_path.glob("ageing-input-*.json"))
    assert not list(tmp_path.glob("ageing-output-*.json"))


def test_persistent_runner_rejects_stale_receipt(tmp_path):
    command = [sys.executable, "-u", "-c", 'import sys; sys.stdin.readline(); print(\'TRIPLE_LOCK_AGEING_RECEIPT {"token":"wrong","ok":true}\', flush=True)']
    with AV.PersistentRunner(command) as runner:
        with pytest.raises(RuntimeError, match="unmatched receipt"):
            runner("ageing_path", {"value": 7}, tmp_path, {})


def test_persistent_runner_stops_on_process_death_without_hanging(tmp_path):
    command = [sys.executable, "-u", "-c", "import sys; sys.stdin.readline(); sys.exit(2)"]
    with AV.PersistentRunner(command) as runner:
        with pytest.raises(RuntimeError, match="stopped before returning"):
            runner("ageing_path", {"value": 7}, tmp_path, {})
        proc = runner.all_workers[0]["process"]
        runner.all_workers[0]["reader"].join(timeout=2)
        assert proc.pid not in engine._children  # Dead children are reaped before context exit.


def test_persistent_runner_recycles_after_bounded_job_count(tmp_path):
    before = set(engine._children)
    with AV.PersistentRunner([sys.executable, "-u", "-c", STUB], max_jobs=1) as runner:
        assert runner("ageing_path", {"value": 7}, tmp_path, {}) == {"computed": 7, "execution": 1}
        assert not runner.workers and not runner.all_workers
        assert runner("ageing_path", {"value": 9}, tmp_path, {}) == {"computed": 9, "execution": 1}
        assert not runner.workers and not runner.all_workers
    assert set(engine._children) == before


def test_isolated_exception_prints_class_only(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ValueError("private pension input 123456789")

    monkeypatch.setattr(AV, "_job", fail)
    assert AV.main(["--job", "input", "output"]) == 1
    output = capsys.readouterr()
    assert output.err == "ValueError\n" and output.out == ""


def test_equivalence_gate_compares_same_job_after_another_persistent_path(monkeypatch, tmp_path):
    calls = []

    def run(kind, arg, workdir, semantics):
        calls.append((arg["id"], Path(workdir).name))
        return {"bundle": {"fixture": True}, "computed": arg["id"]}

    class Runner:
        def __enter__(self):
            return run

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(AV, "isolated_runner", run)
    monkeypatch.setattr(AV, "PersistentRunner", Runner)
    monkeypatch.setattr(engine, "slot_lock", lambda path: contextlib.nullcontext())
    monkeypatch.setattr(engine, "WORKDIRS", tmp_path)
    monkeypatch.setattr(engine, "engine_semantics", lambda: {})
    plan = {"labels": [("central", "both"), ("draw_1", "legacy")],
            "jobs": [("ageing_path", {"id": "central"}), ("ageing_path", {"id": "draw_1"})],
            "calibration_year": 2024, "validation_semantics": {}}
    proof = AV.verify_worker_equivalence(plan)
    assert proof["identical"] and proof["preceding_path"] == "draw_1"
    assert calls == [("central", "ageing-equivalence-isolated"), ("draw_1", "ageing-equivalence-persistent"),
                     ("central", "ageing-equivalence-persistent")]


def test_engine_cancellation_stops_registered_persistent_worker(tmp_path):
    stop = threading.Event()
    errors = []
    command = [sys.executable, "-u", "-c", "import sys,time; sys.stdin.readline(); time.sleep(30)"]
    with AV.PersistentRunner(command) as runner:
        runner._worker(tmp_path.resolve(), stop)
        def run():
            try:
                runner("ageing_path", {"value": 7}, tmp_path, {}, stop)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        time.sleep(0.1)
        assert engine.kill_children(stop, grace=0.1) == 1
        thread.join(timeout=5)
        assert not thread.is_alive() and stop.is_set()
        assert errors and isinstance(errors[0], RuntimeError)
