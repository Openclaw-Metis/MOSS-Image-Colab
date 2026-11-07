"""Application boundary: immutable jobs, single GPU scheduling, durable saved results."""

import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from moss_studio.adapters.comfy import ComfyClient, EngineSettledError
from moss_studio.adapters.execution import execute_graph
from moss_studio.adapters.workflow import compile_t2i, validate_nodes, workflow_hash
from moss_studio.domain.contracts import ConflictError, ValidationError, digest, validate_job_spec
from moss_studio.domain.jobs import PIPELINE, TERMINAL
from moss_studio.storage.assets import AssetStore
from moss_studio.storage.atomic import atomic_json, private_dir, read_json
from moss_studio.storage.ledger import JobLedger
from moss_studio.storage.projects import ProjectStore


class StudioService:
    tasks = frozenset({"t2i", "layout"})

    def __init__(self, repository: Path, data_root: Path, *, engine=None, runner=None):
        self.repository = Path(repository)
        self.root = private_dir(Path(data_root))
        self.projects = ProjectStore(self.root / "projects")
        self.assets = AssetStore(self.root / "assets")
        self.ledger = JobLedger(self.root / "jobs.sqlite")
        self.records = private_dir(self.root / "records")
        self.engine = engine or ComfyClient()
        self.runner = runner or execute_graph
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moss-gpu")
        self.lock = threading.RLock()
        self.futures = {}
        self.gpu_blocked = False
        self.registry = {
            a["id"]: a
            for a in json.loads((self.repository / "configs/models.lock.json").read_text())[
                "artifacts"
            ]
        }
        self.profile = json.loads((self.repository / "configs/profiles/quality50.json").read_text())

    def _project_update(self, project_id: str, *, job_id=None, asset_id=None) -> dict:
        for _ in range(3):
            project = self.projects.get(project_id)
            if job_id and job_id not in project["job_ids"]:
                project["job_ids"].append(job_id)
            if asset_id and asset_id not in project["asset_ids"]:
                project["asset_ids"].append(asset_id)
            try:
                return self.projects.save(project, project["revision"])
            except ConflictError:
                continue
        raise ConflictError("E_CONFLICT：專案持續更新，未宣告結果已保存")

    def save_draft(self, project_id: str, draft: dict, expected_revision: int) -> dict:
        with self.lock:
            project = self.projects.get(project_id)
            project["drafts"]["t2i"] = draft
            return self.projects.save(project, expected_revision)

    def submit(self, payload: dict) -> dict:
        with self.lock:
            return self._submit(payload)

    def _submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("工作必須是 JSON 物件")
        spec = deepcopy(payload)
        existing = self.ledger.find_request(spec.get("project_id"), spec.get("client_request_id"))
        if spec.get("seed") is None:
            spec["seed"] = existing["snapshot"]["seed"] if existing else secrets.randbelow(2**63)
        validate_job_spec(spec)
        if existing:
            if existing["snapshot_hash"] != digest(spec):
                raise ConflictError("同 request id 不可提交不同工作內容")
            return self.get_job(existing["id"])
        if spec.get("task") not in self.tasks:
            raise ValidationError("E_CAPABILITY：此功能仍在後續階段開發中")
        if self.gpu_blocked:
            raise ConflictError("E_ENGINE_UNCERTAIN：引擎工作狀態未確認，請先核對診斷並恢復引擎")
        template = json.loads((self.repository / "workflows/t2i.json").read_text())
        graph = compile_t2i(spec, template, self.profile, self.registry)
        validate_nodes(graph, self.engine.object_info())
        with self.lock:
            project = self.projects.get(spec["project_id"])
            existing = self.ledger.find_request(spec["project_id"], spec["client_request_id"])
            if existing:
                if existing["snapshot_hash"] != digest(spec):
                    raise ConflictError("同 request id 不可提交不同工作內容")
                return self.get_job(existing["id"])
            if project["revision"] != spec["project_revision"]:
                raise ConflictError("E_CONFLICT：專案已更新，請先重新載入")
            active = [j for j in self.ledger.list() if j["status"] not in TERMINAL]
            if len(active) >= 3:
                raise ConflictError("佇列已滿（1 執行 + 2 等候），請等待目前工作")
            job = self.ledger.create(spec)
            self.ledger.transition(job["id"], "validating", expected="created")
            try:
                self._project_update(spec["project_id"], job_id=job["id"])
            except BaseException:
                self.ledger.transition(job["id"], "failed", expected="validating")
                raise
            self.ledger.transition(job["id"], "queued", expected="validating")
            self.ledger.bind_prompt(job["id"], job["id"])
            self.futures[job["id"]] = self.pool.submit(
                self._run, job["id"], graph, deepcopy(self.profile)
            )
            return self.get_job(job["id"])

    def _advance(self, job_id: str, target: str) -> None:
        with self.lock:
            state = self.ledger.get(job_id)["status"]
            if state in TERMINAL or state == "cancelling":
                return
            while state != target:
                index = PIPELINE.index(state)
                if index >= PIPELINE.index(target):
                    return
                next_state = PIPELINE[index + 1]
                self.ledger.transition(job_id, next_state, expected=state)
                state = next_state

    def _on_event(self, job_id: str, event: str, data: dict) -> None:
        if event == "before_submit":
            with self.lock:
                if self.ledger.get(job_id)["status"] == "cancelling":
                    raise EngineSettledError("工作在提交引擎前已要求取消")
        elif event == "execution_start":
            if self.ledger.get(job_id)["status"] == "cancelling":
                self.engine.cancel_owned(job_id, exclusive_engine=True)
        if event == "executing":
            node = data.get("node")
            if node == "7":
                self._advance(job_id, "sampling")
            elif node == "8":
                self._advance(job_id, "decoding")
        elif event == "progress":
            self.ledger.append_event(
                job_id,
                "progress",
                {"stage": "sampling", "value": data.get("value"), "max": data.get("max")},
            )
        elif event == "diagnostic":
            self.ledger.append_event(job_id, "diagnostic", {"code": data.get("code")})

    def _run(self, job_id: str, graph: dict, profile: dict) -> None:
        started = time.monotonic()
        engine_finished = False
        try:
            with self.lock:
                state = self.ledger.get(job_id)["status"]
                if state == "cancelling":
                    self.ledger.transition(job_id, "cancelled", expected=state)
                    return
                if state == "cancelled":
                    return
                if self.gpu_blocked:
                    self.ledger.append_event(job_id, "diagnostic", {"code": "E_ENGINE_UNCERTAIN"})
                    self.ledger.transition(job_id, "interrupted", expected=state)
                    return
                self._advance(job_id, "encoding")
            outputs = self.runner(
                graph, job_id, lambda event, data: self._on_event(job_id, event, data)
            )
            engine_finished = True
            with self.lock:
                job = self.ledger.get(job_id)
                if job["status"] == "cancelling":
                    self.ledger.transition(job_id, "cancelled", expected="cancelling")
                    return
                self._advance(job_id, "saving")
                asset = self.assets.import_image(job["project_id"], outputs[0], kind="output")
                if (asset["width"], asset["height"]) != (
                    job["snapshot"]["width"],
                    job["snapshot"]["height"],
                ):
                    raise ValidationError("輸出尺寸與工作快照不同")
                self._project_update(job["project_id"], asset_id=asset["id"])
                record = {
                    "job_id": job_id,
                    "output_assets": [asset["id"]],
                    "workflow_hash": workflow_hash(graph),
                    "profile": profile,
                    "seconds": time.monotonic() - started,
                    "seed": job["snapshot"]["seed"],
                    "snapshot_hash": job["snapshot_hash"],
                }
                atomic_json(self.records / f"{job_id}.json", record)
                self.ledger.append_event(
                    job_id,
                    "result",
                    {"asset_id": asset["id"], "workflow_hash": record["workflow_hash"]},
                )
                self.ledger.transition(job_id, "succeeded", expected="saving")
        except Exception as error:
            with self.lock:
                current = self.ledger.get(job_id)["status"]
                confirmed = engine_finished or isinstance(error, EngineSettledError)
                if not confirmed:
                    # An event/HTTP timeout is not proof the GPU stopped. Fence subsequent
                    # work rather than releasing the logical lease and reporting cancellation.
                    self.gpu_blocked = True
                    self.ledger.append_event(job_id, "diagnostic", {"code": "E_ENGINE_UNCERTAIN"})
                    if current not in TERMINAL:
                        self.ledger.transition(job_id, "interrupted", expected=current)
                elif current == "cancelling":
                    self.ledger.transition(job_id, "cancelled", expected=current)
                elif current not in TERMINAL:
                    self.ledger.append_event(job_id, "diagnostic", {"code": "E_ENGINE_OR_SAVE"})
                    self.ledger.transition(job_id, "failed", expected=current)
        finally:
            with self.lock:
                self.futures.pop(job_id, None)

    def close(self) -> None:
        self.pool.shutdown(wait=True)

    def get_job(self, job_id: str, after_seq: int = 0) -> dict:
        job = self.ledger.get(job_id)
        project = self.projects.get(job["project_id"])
        response = {
            "id": job_id,
            "project_id": job["project_id"],
            "status": job["status"],
            "events": self.ledger.events(job_id, after_seq),
            "project_revision": project["revision"],
            "draft_hash": digest(project["drafts"]["t2i"]),
            "seed": job["snapshot"]["seed"],
        }
        if job["status"] == "succeeded":
            response["record"] = read_json(self.records / f"{job_id}.json")
        return response

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            job = self.ledger.get(job_id)
            if job["status"] in TERMINAL:
                return self.get_job(job_id)
            if job["status"] != "cancelling":
                self.ledger.transition(job_id, "cancelling", expected=job["status"])
            future = self.futures.get(job_id)
            if future and future.cancel():
                self.ledger.transition(job_id, "cancelled", expected="cancelling")
                self.futures.pop(job_id, None)
            else:
                self.engine.cancel_owned(job_id, exclusive_engine=True)
            return self.get_job(job_id)
