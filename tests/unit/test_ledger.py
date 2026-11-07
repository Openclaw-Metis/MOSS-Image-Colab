import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from moss_studio.domain.contracts import ConflictError, ValidationError, new_id
from moss_studio.domain.jobs import PIPELINE
from moss_studio.storage.ledger import JobLedger


def test_idempotency_and_immutable_snapshot(tmp_path, job_spec):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    job = ledger.create(job_spec)
    assert ledger.create(job_spec)["id"] == job["id"]
    candidate = deepcopy(job_spec)
    candidate["seed"] += 1
    with pytest.raises(ConflictError):
        ledger.create(candidate)
    job_spec["prompt"] = "mutable draft"
    job["snapshot"]["prompt"] = "mutable result"
    assert ledger.get(job["id"])["snapshot"]["prompt"] == "米白色山景旅遊海報"
    with sqlite3.connect(ledger.path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE jobs SET snapshot='{}' WHERE id=?", (job["id"],))


def test_parallel_duplicate_submit(tmp_path, job_spec):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: ledger.create(job_spec), range(12)))
    assert len({job["id"] for job in jobs}) == 1
    assert len(ledger.events(jobs[0]["id"])) == 1


def test_transition_contract_and_ordered_events(tmp_path, job_spec):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    job = ledger.create(job_spec)
    with pytest.raises(ValidationError):
        ledger.transition(job["id"], "succeeded", expected="created")
    previous = "created"
    for target in (*PIPELINE[1:], "succeeded"):
        job = ledger.transition(job["id"], target, expected=previous)
        previous = target
    with pytest.raises(ValidationError):
        ledger.transition(job["id"], "queued", expected="succeeded")
    assert [e["seq"] for e in ledger.events(job["id"])] == list(range(1, 9))
    assert len(ledger.events(job["id"], after_seq=6)) == 2
    assert JobLedger(ledger.path).get(job["id"])["status"] == "succeeded"


def test_cancellation_never_reports_success(tmp_path, job_spec):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    job = ledger.create(job_spec)
    ledger.transition(job["id"], "cancelling", expected="created")
    with pytest.raises(ConflictError):
        ledger.transition(job["id"], "failed", expected="created")
    with pytest.raises(ValidationError):
        ledger.transition(job["id"], "succeeded", expected="cancelling")
    ledger.transition(job["id"], "cancelled", expected="cancelling")
    assert ledger.recover_interrupted() == []


def test_restart_requires_history_reconciliation(tmp_path, job_spec):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    job = ledger.create(job_spec)
    ledger.transition(job["id"], "validating", expected="created")
    ledger.transition(job["id"], "queued", expected="validating")
    prompt_id = new_id()
    ledger.bind_prompt(job["id"], prompt_id)
    with pytest.raises(ConflictError):
        ledger.bind_prompt(job["id"], new_id())
    restored = JobLedger(ledger.path)
    assert restored.recover_interrupted()[0]["status"] == "interrupted"
    assert restored.get(job["id"])["comfy_prompt_id"] == prompt_id
    assert restored.events(job["id"])[-1]["payload"] == {"reconcile_history": True}
    assert restored.recover_interrupted() == []
