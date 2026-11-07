"""Stage 7 CPU contracts: staged upscale plan/graph and the model page service."""

import hashlib
import io
import json
import struct
import time
from pathlib import Path

import pytest
from PIL import Image

from moss_studio.adapters.workflow import compile_upscale
from moss_studio.domain.contracts import ConflictError, ValidationError, new_id
from moss_studio.domain.hires import plan_passes
from moss_studio.services.models import ModelManager
from moss_studio.services.studio import StudioService

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("source", "target", "count"),
    [
        ((1024, 1024), (2048, 2048), 2),
        ((1024, 1024), (1536, 1536), 1),
        ((1360, 768), (2048, 1152), 2),
    ],
)
def test_each_pass_is_at_most_one_and_a_half_times(source, target, count):
    passes = plan_passes(source, target)
    assert len(passes) == count and passes[-1] == target
    previous = source
    for width, height in passes:
        assert width % 16 == 0 and height % 16 == 0
        assert width / previous[0] <= 1.5 + 0.02 and height / previous[1] <= 1.5 + 0.02
        previous = (width, height)


@pytest.mark.parametrize(
    "target", [(1024, 1024), (4096, 4096), (2048, 1024), (2050, 2048), (1000, 1000)]
)
def test_invalid_upscale_targets(target):
    with pytest.raises(ValidationError):
        plan_passes((1024, 1024), target)


def test_upscale_graph_chains_passes_with_stage_ids(job_spec):
    passes = plan_passes((1024, 1024), (2048, 2048))
    spec = {
        **job_spec,
        "task": "upscale",
        "profile_id": "upscale_v1",
        "width": 2048,
        "height": 2048,
        "references": [{"asset_id": new_id(), "slot": 1}],
        "control": {"denoise": 0.6},
    }
    registry = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}
    graph = compile_upscale(
        spec,
        load("workflows/upscale.json"),
        load("configs/profiles/upscale.json"),
        registry,
        "moss_src.png",
        passes,
    )
    assert graph["100"]["inputs"]["image"] == ["11", 0]
    assert graph["7"]["inputs"]["latent_image"] == ["110", 0]
    assert graph["101"]["inputs"]["image"] == ["130", 0]  # pass 2 scales pass 1's decode
    assert graph["8"]["inputs"]["samples"] == ["121", 0]
    assert graph["9"]["inputs"]["images"] == ["8", 0]
    assert graph["101"]["inputs"]["width"] == 2048
    assert all(graph[n]["inputs"]["denoise"] == 0.6 for n in ("7", "121"))
    with pytest.raises(ValidationError):
        compile_upscale(
            {**spec, "control": {"denoise": 0.95}},
            load("workflows/upscale.json"),
            load("configs/profiles/upscale.json"),
            registry,
            "moss_src.png",
            passes,
        )


def tiny_safetensors():
    header = json.dumps({"w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    return struct.pack("<Q", len(header)) + header + struct.pack("<f", 1.0)


def test_model_page_downloads_only_pinned_and_switch_needs_idle_and_ready(tmp_path):
    data = tiny_safetensors()

    def fetch(artifact, staging):
        path = staging / "file.safetensors"
        path.write_bytes(data)
        return path

    manager = ModelManager(ROOT, tmp_path / "models", tmp_path / "data", fetch=fetch)
    base = manager.registry["base_bf16"]
    base.update(size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    try:
        assert {m["id"]: m["state"] for m in manager.list()}["base_bf16"] == "missing"
        with pytest.raises(ValidationError):
            manager.download("https://example.invalid/model.safetensors")
        with pytest.raises(ValidationError, match="下載"):
            manager.activate("base_bf16", busy=False)
        manager.download("base_bf16")
        deadline = time.monotonic() + 5
        while manager.status("base_bf16")["state"] != "ready":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        with pytest.raises(ConflictError):
            manager.activate("base_bf16", busy=True)
        with pytest.raises(ValidationError):
            manager.activate("vae_small", busy=False)
        assert manager.activate("base_bf16", busy=False) == {"active_backbone": "base_bf16"}
        assert (
            ModelManager(ROOT, tmp_path / "models", tmp_path / "data").active_backbone()
            == "base_bf16"
        )
    finally:
        manager.close()


def test_service_upscales_an_output_in_passes(tmp_path):
    class Engine:
        uploaded = []

        def object_info(self):
            class Any(dict):
                def get(self, key, default=None):
                    return {"input": {"required": {}}}

            return Any()

        def upload_image(self, name, data):
            self.uploaded.append(name)
            return name

        def cancel_owned(self, prompt_id, *, exclusive_engine):
            return "not_queued"

    def png(size):
        buffer = io.BytesIO()
        Image.new("RGB", size, "teal").save(buffer, format="PNG")
        return buffer.getvalue()

    service = StudioService(
        ROOT, tmp_path, engine=Engine(), runner=lambda g, p, e: [png((2048, 2048))]
    )
    try:
        project = service.projects.create("放大")
        source = service.import_asset(project["id"], png((1024, 1024)))
        project = service.projects.get(project["id"])
        job = service.submit(
            {
                "project_id": project["id"],
                "client_request_id": new_id(),
                "project_revision": project["revision"],
                "task": "upscale",
                "profile_id": "upscale_v1",
                "model_artifact_id": "sft_bf16",
                "prompt": "teal",
                "negative_prompt": "",
                "width": 2048,
                "height": 2048,
                "seed": 1,
                "references": [{"asset_id": source["id"], "slot": 1}],
                "layout": None,
                "mask_asset_id": None,
                "control": {"denoise": 0.6},
                "lora_stack": [],
            }
        )
        deadline = time.monotonic() + 5
        while service.get_job(job["id"])["status"] not in {"succeeded", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        record = service.get_job(job["id"])["record"]
        assert record["postprocess"] == "staged_upscale"
        assert record["passes"] == [[1456, 1456], [2048, 2048]]
    finally:
        service.close()
