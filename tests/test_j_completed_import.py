"""Completed-job imports reject altered evidence and unsuccessful timings."""

import hashlib
from types import SimpleNamespace

import pytest

from scripts import import_model_v2_j_completed as importer


def test_import_rejects_changed_receipt_before_parsing_or_publication(tmp_path, monkeypatch):
    original = b'{"complete": true}'
    monkeypatch.setattr(importer, "RECEIPTS", {"receipt.json": hashlib.sha256(original).hexdigest()})
    cache = tmp_path / ".cache"
    cache.mkdir()
    (cache / "receipt.json").write_bytes(original)
    assert importer.read_receipts(tmp_path) == {"receipt.json": {"complete": True}}
    (cache / "receipt.json").write_bytes(b'{"complete": true, "private_records": [1]}')
    with pytest.raises(ValueError, match="receipt bytes changed"):
        importer.read_receipts(tmp_path)


def wrappers():
    return "\n".join(f"{name} attempt=2 rc=0 wall_s=100 started=2026-10-12T08:00:00Z"
                     for name in ("c2-dry-run", "bridge-model-step", "bridge-certified",
                                  "rehearsal-core", "rehearsal-coverage", "rehearsal-sample"))


def test_stopped_attempts_cannot_supply_completed_wrapper_measurements():
    stopped = "bridge-certified attempt=1 rc=1 wall_s=9999 started=2026-10-12T07:00:00Z\n"
    rows = importer.completed_wrappers(stopped + wrappers())
    assert len(rows) == 6
    assert all(row["wall_seconds"] == 100 and row["attempt"] == 2 for row in rows)


@pytest.mark.parametrize("raw", ["", "malformed", wrappers().split("\n", 1)[1], wrappers() + "\n" + wrappers()])
def test_incomplete_duplicate_or_malformed_completed_timings_are_rejected(raw):
    with pytest.raises(ValueError):
        importer.completed_wrappers(raw)


def test_missing_exact_cache_refuses_rehearsal_reconstruction(tmp_path):
    engine = SimpleNamespace(cached=lambda *_args, **_kwargs: None)
    with pytest.raises(ValueError, match="Missing exact-key"):
        importer.cached_jobs(engine, [("path", {"id": "missing"})], tmp_path)


def test_cache_reconstruction_preserves_job_order(tmp_path):
    engine = SimpleNamespace(cached=lambda _kind, arg, **_kwargs: {"result": arg["id"]})
    jobs = [("path", {"id": 2}), ("coverage", {"id": 1})]
    assert importer.cached_jobs(engine, jobs, tmp_path) == [{"result": 2}, {"result": 1}]


def timing_row(**updates):
    return {"dataset": "efrs", "kind": "path", "job_key": "path:1", "cache": "cold",
            "status": "completed", "wall_seconds": 12.0, **updates}


def timing_engine():
    return SimpleNamespace(job_key=lambda kind, arg: f"{kind}:{arg['id']}")


def test_timing_plan_preserves_repeated_warm_jobs_and_omits_private_fields():
    requested = [("path", {"id": 1}), ("path", {"id": 1})]
    rows = [timing_row(private_fiscal_value=123), timing_row(cache="warm", wall_seconds=None)]
    verified = importer.verify_timings(timing_engine(), requested, {"timings": rows})
    assert verified == [timing_row(), timing_row(cache="warm", wall_seconds=None)]
    with pytest.raises(ValueError, match="exact stage plan"):
        importer.verify_timings(timing_engine(), requested, {"timings": rows[:1]})


@pytest.mark.parametrize("updates", [{"job_key": "path:2"}, {"kind": "history"}, {"dataset": "microcosm"}])
def test_timing_row_must_match_the_reconstructed_job(updates):
    with pytest.raises(ValueError, match="exact stage plan"):
        importer.verify_timings(timing_engine(), [("path", {"id": 1})], {"timings": [timing_row(**updates)]})


@pytest.mark.parametrize("updates", [
    {"status": "failed"}, {"wall_seconds": None}, {"wall_seconds": float("nan")},
    {"wall_seconds": float("inf")}, {"wall_seconds": -1}, {"wall_seconds": True},
    {"cache": "warm"}, {"cache": "unknown"},
])
def test_incomplete_or_invalid_timing_cannot_enter_planning(updates):
    with pytest.raises(ValueError):
        importer.verify_timings(timing_engine(), [("path", {"id": 1})], {"timings": [timing_row(**updates)]})


def test_saved_passport_requires_receipt_keying_and_all_probe_checks():
    pipeline = SimpleNamespace(passport_probe_facts=lambda: {"rent": 100},
                               passport_checks=lambda *_: [("receipt", True)])
    passport = {"keyed_on": "receipt", "policyengine_uk": "2.125.1", "probe": {"rent": 100}, "checks": ["receipt"],
                "observed": {"claims": {}, "receipt_set": {}}}
    provenance = {"preflight": {"housing_benefit_guarantee_credit_passport": passport}}
    importer.verify_passport(pipeline, provenance)
    passport["keyed_on"] = "entitlement"
    with pytest.raises(ValueError, match="passport fails"):
        importer.verify_passport(pipeline, provenance)
    passport["keyed_on"] = "receipt"
    pipeline.passport_checks = lambda *_: [("receipt", False)]
    with pytest.raises(ValueError, match="passport fails"):
        importer.verify_passport(pipeline, provenance)
