"""Persistent transport executes every request, cleans processes and keeps errors private."""

import io
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
