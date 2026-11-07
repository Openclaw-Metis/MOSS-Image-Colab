import io
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from moss_studio.adapters.comfy import EngineError, EngineSettledError
from moss_studio.domain.contracts import ConflictError, new_id
from moss_studio.services.studio import StudioService

ROOT = Path(__file__).resolve().parents[2]


class EngineStub:
    def __init__(self):
        self.cancelled = set()
        self.offline = False
        self.info_calls = 0

    def object_info(self):
        self.info_calls += 1
        if self.offline:
            raise EngineError("offline")
        names = [
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "CLIPTextEncode",
            "KSampler",
            "EmptyFlux2LatentImage",
            "VAEDecode",
            "SaveImage",
            "ModelSamplingAuraFlow",
            "SkipLayerGuidanceDiTSimple",
        ]
        return {name: {"input": {"required": {}}} for name in names}

    def cancel_owned(self, prompt_id, *, exclusive_engine):
        assert exclusive_engine
        self.cancelled.add(prompt_id)


class RunnerStub:
    def __init__(self, engine):
        self.engine = engine
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.calls, self.active, self.max_active = 0, 0, 0
        buffer = io.BytesIO()
        Image.new("RGB", (1024, 1024), "red").save(buffer, format="PNG")
        self.png = buffer.getvalue()

    def __call__(self, graph, prompt_id, event):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            event("before_submit", {})
            event("execution_start", {})
            self.entered.set()
            assert self.release.wait(timeout=5)
            if prompt_id in self.engine.cancelled:
                raise EngineSettledError("interrupted")
            event("executing", {"node": "7"})
            event("progress", {"value": 1, "max": 50})
            event("executing", {"node": "8"})
            return [self.png]
        finally:
            self.active -= 1


def wait_terminal(service, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.01)
    pytest.fail("unit worker did not terminate")


@pytest.fixture
def studio(tmp_path, job_spec):
    engine = EngineStub()
    runner = RunnerStub(engine)
    service = StudioService(ROOT, tmp_path, engine=engine, runner=runner)
    project = service.projects.create("單元測試專案")
    job_spec["project_id"] = project["id"]
    job_spec["seed"] = None
    try:
        yield service, engine, runner, job_spec
    finally:
        runner.release.set()
        service.close()


def test_saved_result_immutable_seed_and_offline_duplicate(studio):
    service, engine, runner, payload = studio
    job = service.submit(payload)
    result = wait_terminal(service, job["id"])
    assert result["status"] == "succeeded"
    assert result["seed"] is not None
    assert result["record"]["seed"] == result["seed"]
    asset_id = result["record"]["output_assets"][0]
    assert service.assets.path(payload["project_id"], asset_id).is_file()
    assert asset_id in service.projects.get(payload["project_id"])["asset_ids"]
    stages = [e["payload"]["stage"] for e in result["events"] if e["type"] in {"created", "stage"}]
    assert stages == [
        "created",
        "validating",
        "queued",
        "encoding",
        "sampling",
        "decoding",
        "saving",
        "succeeded",
    ]
    engine.offline = True
    assert service.submit(payload)["id"] == result["id"]
    assert runner.calls == 1 and engine.info_calls == 1
    different = deepcopy(payload)
    different["prompt"] = "different"
    with pytest.raises(ConflictError):
        service.submit(different)


def test_queue_bound_and_cancel_affects_only_requested_job(studio):
    service, engine, runner, payload = studio
    runner.release.clear()
    first = service.submit(payload)
    assert runner.entered.wait(timeout=3)

    def next_job():
        snapshot = deepcopy(payload)
        snapshot["client_request_id"] = new_id()
        snapshot["project_revision"] = service.projects.get(payload["project_id"])["revision"]
        return service.submit(snapshot)

    second, third = next_job(), next_job()
    with pytest.raises(ConflictError):
        next_job()
    assert service.cancel(second["id"])["status"] == "cancelled"
    assert second["id"] not in engine.cancelled  # Never entered the engine queue.
    assert service.cancel(first["id"])["status"] == "cancelling"
    runner.release.set()
    assert wait_terminal(service, first["id"])["status"] == "cancelled"
    assert wait_terminal(service, third["id"])["status"] == "succeeded"
    assert runner.max_active == 1


def test_result_record_write_failure_never_reports_success(studio, monkeypatch):
    service, _, _, payload = studio

    def fail(*args):
        raise OSError("simulated result persistence failure")

    monkeypatch.setattr("moss_studio.services.studio.atomic_json", fail)
    job = service.submit(payload)
    result = wait_terminal(service, job["id"])
    assert result["status"] == "failed" and "record" not in result
    assert service.ledger.get(job["id"])["snapshot"]["prompt"] == payload["prompt"]


def test_uncertain_engine_fences_next_job_instead_of_false_cancellation(studio):
    service, _, runner, payload = studio
    runner.release.clear()

    def uncertain(*args):
        runner.entered.set()
        assert runner.release.wait(3)
        raise EngineError("lost connection while engine might still be running")

    service.runner = uncertain
    first = service.submit(payload)
    assert runner.entered.wait(3)
    payload["client_request_id"] = new_id()
    payload["project_revision"] = service.projects.get(payload["project_id"])["revision"]
    second = service.submit(payload)

    service.cancel(first["id"])
    runner.release.set()
    assert wait_terminal(service, first["id"])["status"] == "interrupted"
    # The queued job never enters the engine while the former lease is uncertain.
    assert wait_terminal(service, second["id"])["status"] == "interrupted"
    assert service.gpu_blocked
    payload["client_request_id"] = new_id()
    payload["project_revision"] = service.projects.get(payload["project_id"])["revision"]
    with pytest.raises(ConflictError, match="E_ENGINE_UNCERTAIN"):
        service.submit(payload)
