"""Application boundary: immutable jobs, single GPU scheduling, durable saved results."""

import io
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from PIL import Image

from moss_studio.adapters.comfy import ComfyClient, EngineError, EngineSettledError
from moss_studio.adapters.execution import execute_graph
from moss_studio.adapters.workflow import (
    compile_control,
    compile_edit,
    compile_inpaint,
    compile_t2i,
    compile_upscale,
    compile_vision,
    validate_control,
    validate_inpaint_control,
    validate_nodes,
    workflow_hash,
)
from moss_studio.domain.contracts import (
    TABS,
    ConflictError,
    ValidationError,
    digest,
    validate_job_spec,
)
from moss_studio.domain.hires import plan_passes
from moss_studio.domain.jobs import PIPELINE, TERMINAL
from moss_studio.domain.masks import (
    binary_mask,
    check_coverage,
    composite,
    feather_radius,
    feathered_alpha,
    mask_png,
    png_bytes,
    resize_mask,
)
from moss_studio.domain.references import scaled_to_total_pixels
from moss_studio.services.models import ModelManager
from moss_studio.storage.assets import AssetStore
from moss_studio.storage.atomic import atomic_json, private_dir, read_json
from moss_studio.storage.ledger import JobLedger
from moss_studio.storage.projects import ProjectStore


class StudioService:
    tasks = frozenset(
        {"t2i", "layout", "instruction_edit", "inpaint", "color_depth", "vision", "upscale"}
    )

    def __init__(
        self,
        repository: Path,
        data_root: Path,
        *,
        engine=None,
        runner=None,
        model_root: Path | None = None,
        model_fetch=None,
    ):
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
            for a in json.loads(
                (self.repository / "configs/models.lock.json").read_text(encoding="utf-8")
            )["artifacts"]
        }
        self.profiles = {}
        for path in sorted((self.repository / "configs/profiles").glob("*.json")):
            profile = json.loads(path.read_text(encoding="utf-8"))
            self.profiles[profile["id"]] = profile
        self.default_profile_id = "quality50_v1"
        self.models = ModelManager(
            self.repository,
            model_root or Path("/content/models"),
            self.root,
            fetch=model_fetch,
        )

    def profile_for(self, profile_id: str) -> dict:
        profile = self.profiles.get(profile_id)
        if profile is None:
            raise ValidationError("E_CAPABILITY：未知的採樣預設")
        return profile

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

    def save_draft(
        self, project_id: str, draft: dict, expected_revision: int, tab: str = "t2i"
    ) -> dict:
        if tab not in TABS:
            raise ValidationError("未知的分頁")
        if not isinstance(draft, dict):
            raise ValidationError("草稿必須是物件")
        with self.lock:
            project = self.projects.get(project_id)
            project["drafts"][tab] = draft
            return self.projects.save(project, expected_revision)

    def import_asset(self, project_id: str, data: bytes, kind: str = "input") -> dict:
        """Decoded, metadata-free upload attached to the project; the file name is never kept."""
        if kind not in {"input", "mask", "control"}:
            raise ValidationError("未知素材種類")
        self.projects.get(project_id)
        asset = self.assets.import_image(project_id, data, kind=kind)
        project = self._project_update(project_id, asset_id=asset["id"])
        edit, inpaint = self.profiles["edit_v1"], self.profiles["inpaint_v1"]
        # Colour/depth control uses the same 1 MP / 16 px working size as inpaint.
        sizes = {
            "edit_size": list(
                scaled_to_total_pixels(
                    asset["width"], asset["height"], edit["reference_megapixels"]
                )
            ),
            "inpaint_size": list(
                scaled_to_total_pixels(
                    asset["width"], asset["height"], inpaint["working_megapixels"]
                )
            ),
        }
        return {**asset, "project_revision": project["revision"], **sizes}

    def _reference_inputs(self, spec: dict, profile: dict) -> list[tuple[str, Path]]:
        """Resolves ordered reference assets and checks the snapshot follows the main image."""
        project = self.projects.get(spec["project_id"])
        inputs = []
        for reference in spec["references"]:
            asset_id = reference["asset_id"]
            if asset_id not in project["asset_ids"]:
                raise ValidationError("參考圖不屬於此專案")
            asset = self.assets.get(spec["project_id"], asset_id)
            if asset["kind"] != "input":
                raise ValidationError("參考圖必須是上傳的圖片")
            if not inputs:
                expected = scaled_to_total_pixels(
                    asset["width"], asset["height"], profile["reference_megapixels"]
                )
                if (spec["width"], spec["height"]) != expected:
                    raise ValidationError(
                        f"輸出尺寸須跟隨圖 1：{expected[0]}×{expected[1]}，請重新整理後再提交"
                    )
            inputs.append((f"moss_{asset_id}.png", self.assets.path(spec["project_id"], asset_id)))
        return inputs

    def _owned_asset(self, project: dict, asset_id, kind: str) -> dict:
        if asset_id not in project["asset_ids"]:
            raise ValidationError("素材不屬於此專案")
        asset = self.assets.get(project["id"], asset_id)
        if asset["kind"] != kind:
            raise ValidationError("素材種類不符")
        return asset

    def _inpaint_plan(self, spec: dict, profile: dict) -> dict:
        """Prepares the working-size source and feathered mask, and the final composite."""
        control = validate_inpaint_control(spec["control"], profile)
        project = self.projects.get(spec["project_id"])
        source_meta = self._owned_asset(project, spec["references"][0]["asset_id"], "input")
        mask_meta = self._owned_asset(project, spec["mask_asset_id"], "mask")
        size = scaled_to_total_pixels(
            source_meta["width"], source_meta["height"], profile["working_megapixels"]
        )
        # The brush canvas works at the working size (bounded undo memory); a full-resolution
        # mask is also accepted. Either way it is resized with nearest neighbour below.
        if (mask_meta["width"], mask_meta["height"]) not in {
            (source_meta["width"], source_meta["height"]),
            size,
        }:
            raise ValidationError("遮罩尺寸必須等於來源圖或工作尺寸")
        if (spec["width"], spec["height"]) != size:
            raise ValidationError(f"輸出尺寸須為 {size[0]}×{size[1]}（跟隨來源圖）")
        with Image.open(self.assets.path(project["id"], source_meta["id"])) as image:
            source = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        with Image.open(self.assets.path(project["id"], mask_meta["id"])) as image:
            selected = binary_mask(image)
        check_coverage(selected, confirm_full=control["confirm_full"])
        selected = resize_mask(selected, size)
        check_coverage(selected, confirm_full=control["confirm_full"])
        radius = feather_radius(*size, control["edge_softness"])
        alpha = feathered_alpha(selected, radius)
        source_name = f"moss_{source_meta['id']}_{size[0]}x{size[1]}.png"
        mask_name = f"moss_{mask_meta['id']}_f{radius}_{size[0]}x{size[1]}.png"
        graph = compile_inpaint(
            spec, self._template("inpaint"), profile, self.registry, source_name, mask_name
        )

        def finish(output: bytes) -> bytes:
            with Image.open(io.BytesIO(output)) as generated:
                return png_bytes(composite(source, generated.convert("RGB"), alpha))

        return {
            "graph": graph,
            "inputs": [(source_name, png_bytes(source)), (mask_name, mask_png(alpha))],
            "finish": finish,
            "record": {"postprocess": "feathered_composite", "feather_px": radius},
        }

    def _control_plan(self, spec: dict, profile: dict) -> dict:
        control = validate_control(spec["control"], profile)
        project = self.projects.get(spec["project_id"])
        source = self._owned_asset(project, spec["references"][0]["asset_id"], "input")
        size = scaled_to_total_pixels(
            source["width"], source["height"], profile["working_megapixels"]
        )
        if (spec["width"], spec["height"]) != size:
            raise ValidationError(f"輸出尺寸須為 {size[0]}×{size[1]}（跟隨來源圖）")
        names = {"source": f"moss_{source['id']}.png", "depth": None, "color": None}
        inputs = [(names["source"], self.assets.path(project["id"], source["id"]))]
        # User maps are resized here to the exact output size the control node expects:
        # depth smoothly, the colour map with nearest neighbour so region IDs stay flat.
        for key, field, method in (
            ("depth", "depth_asset_id", Image.Resampling.BILINEAR),
            ("color", "color_asset_id", Image.Resampling.NEAREST),
        ):
            if not control[field]:
                continue
            meta = self._owned_asset(project, control[field], "control")
            with Image.open(self.assets.path(project["id"], meta["id"])) as image:
                resized = image.convert("RGB").resize(size, method)
            names[key] = f"moss_{meta['id']}_{key}_{size[0]}x{size[1]}.png"
            inputs.append((names[key], png_bytes(resized)))
        graph = compile_control(spec, self._template("control"), profile, self.registry, names)
        return {"graph": graph, "inputs": inputs, "finish": None, "record": {}}

    def _vision_plan(self, spec: dict, profile: dict) -> dict:
        project = self.projects.get(spec["project_id"])
        inputs = []
        for reference in spec["references"]:
            meta = self._owned_asset(project, reference["asset_id"], "input")
            inputs.append((f"moss_{meta['id']}.png", self.assets.path(project["id"], meta["id"])))
        graph = compile_vision(
            spec, self._template("vision"), profile, self.registry, [n for n, _ in inputs]
        )
        return {"graph": graph, "inputs": inputs, "finish": None, "record": {"experimental": True}}

    def _upscale_plan(self, spec: dict, profile: dict) -> dict:
        project = self.projects.get(spec["project_id"])
        asset_id = spec["references"][0]["asset_id"]
        if asset_id not in project["asset_ids"]:
            raise ValidationError("素材不屬於此專案")
        meta = self.assets.get(project["id"], asset_id)
        if meta["kind"] not in {"input", "output"}:
            raise ValidationError("只能放大上傳的圖片或作品")
        passes = plan_passes(
            (meta["width"], meta["height"]),
            (spec["width"], spec["height"]),
            profile["max_scale_per_pass"],
        )
        name = f"moss_{asset_id}.png"
        graph = compile_upscale(
            spec, self._template("upscale"), profile, self.registry, name, passes
        )
        record = {"postprocess": "staged_upscale", "passes": [list(p) for p in passes]}
        inputs = [(name, self.assets.path(project["id"], asset_id))]
        return {"graph": graph, "inputs": inputs, "finish": None, "record": record}

    def _compile(self, spec: dict, profile: dict) -> dict:
        plan = {"inputs": [], "finish": None, "record": {}}
        if spec["task"] in {"t2i", "layout"}:
            template = self._template("t2i")
            return {**plan, "graph": compile_t2i(spec, template, profile, self.registry)}
        if spec["task"] == "instruction_edit":
            inputs = self._reference_inputs(spec, profile)
            graph = compile_edit(
                spec, self._template("edit"), profile, self.registry, [n for n, _ in inputs]
            )
            return {**plan, "graph": graph, "inputs": inputs}
        if spec["task"] == "inpaint":
            return self._inpaint_plan(spec, profile)
        if spec["task"] == "color_depth":
            return self._control_plan(spec, profile)
        if spec["task"] == "vision":
            return self._vision_plan(spec, profile)
        if spec["task"] == "upscale":
            return self._upscale_plan(spec, profile)
        raise ValidationError("E_CAPABILITY：此功能仍在後續階段開發中")

    def _template(self, name: str) -> dict:
        return json.loads((self.repository / f"workflows/{name}.json").read_text(encoding="utf-8"))

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
        profile = self.profile_for(spec["profile_id"])
        plan = self._compile(spec, profile)
        graph = plan["graph"]
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
                self._run, job["id"], graph, deepcopy(profile), plan
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

    def _run(self, job_id: str, graph: dict, profile: dict, plan: dict | None = None) -> None:
        plan = plan or {"inputs": [], "finish": None, "record": {}}
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
            for name, data in plan["inputs"]:
                try:
                    payload = data.read_bytes() if isinstance(data, Path) else data
                    self.engine.upload_image(name, payload)
                except (EngineError, OSError) as error:
                    # Nothing was submitted to the sampler yet, so the GPU state is certain.
                    raise EngineSettledError("E_ENGINE：參考圖無法送入引擎") from error
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
                output = plan["finish"](outputs[0]) if plan["finish"] else outputs[0]
                asset = self.assets.import_image(job["project_id"], output, kind="output")
                if (asset["width"], asset["height"]) != (
                    job["snapshot"]["width"],
                    job["snapshot"]["height"],
                ):
                    raise ValidationError("輸出尺寸與工作快照不同")
                self._project_update(job["project_id"], asset_id=asset["id"])
                auxiliary = []
                for extra in outputs[1:]:
                    # e.g. the MoGe map the control job actually applied; shown, never the result.
                    meta = self.assets.import_image(job["project_id"], extra, kind="control")
                    self._project_update(job["project_id"], asset_id=meta["id"])
                    auxiliary.append(meta["id"])
                record = {
                    "job_id": job_id,
                    "output_assets": [asset["id"]],
                    "auxiliary_assets": auxiliary,
                    "workflow_hash": workflow_hash(graph),
                    "profile": profile,
                    "seconds": time.monotonic() - started,
                    "seed": job["snapshot"]["seed"],
                    "snapshot_hash": job["snapshot_hash"],
                    **plan["record"],
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

    def busy(self) -> bool:
        return any(j["status"] not in TERMINAL for j in self.ledger.list())

    def close(self) -> None:
        self.pool.shutdown(wait=True)
        self.models.close()

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
            "draft_hashes": {tab: digest(project["drafts"][tab]) for tab in TABS},
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
