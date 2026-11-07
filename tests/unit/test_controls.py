"""Stage 6 CPU contracts: colour/depth control graph, experimental vision graph, service maps."""

import io
import json
import time
from pathlib import Path

import pytest
from PIL import Image

from moss_studio.adapters.workflow import compile_control, compile_vision
from moss_studio.domain.contracts import ValidationError, new_id
from moss_studio.services.studio import StudioService

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


REGISTRY = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}


def control_spec(job_spec, **control):
    return {
        **job_spec,
        "task": "color_depth",
        "profile_id": "control_v1",
        "references": [{"asset_id": new_id(), "slot": 1}],
        "control": {
            "geometry": "mask",
            "strength": 1.0,
            "end_percent": 0.6,
            "depth_asset_id": None,
            "color_asset_id": None,
            **control,
        },
    }


def compile_c(spec, names=None):
    names = names or {"source": "moss_src.png", "depth": "moss_d.png", "color": "moss_c.png"}
    return compile_control(
        spec, load("workflows/control.json"), load("configs/profiles/control.json"), REGISTRY, names
    )


def test_moge_geometry_feeds_control_with_template_sampling(job_spec):
    graph = compile_c(control_spec(job_spec, geometry="depth"))
    assert graph["42"]["inputs"]["output"] == "depth"
    assert graph["40"]["inputs"]["model_name"] == "moge_3_vitg_fp16.safetensors"
    assert graph["53"]["inputs"]["depth_map"] == ["42", 0]
    assert "color_map" not in graph["53"]["inputs"]
    assert graph["53"]["inputs"]["end_percent"] == 0.6
    assert graph["30"]["inputs"]["lora_name"] == "moss_image_color_depth_control.safetensors"
    assert graph["22"]["class_type"] == "TemporalScoreRescaling"
    assert graph["22"]["inputs"]["model"] == ["30", 0] and graph["20"]["inputs"]["model"] == [
        "22",
        0,
    ]
    assert graph["21"]["inputs"]["single_layers"] == "24"
    sampler = graph["7"]["inputs"]
    assert (sampler["sampler_name"], sampler["steps"], sampler["cfg"]) == ("er_sde", 25, 3.0)
    assert sampler["positive"] == ["53", 0] and sampler["negative"] == ["53", 1]


def test_uploaded_depth_and_colour_maps_replace_estimation(job_spec):
    spec = control_spec(
        job_spec, geometry="upload", depth_asset_id=new_id(), color_asset_id=new_id()
    )
    graph = compile_c(spec)
    assert "40" not in graph and "41" not in graph
    assert graph["53"]["inputs"]["depth_map"] == ["43", 0]
    assert graph["53"]["inputs"]["color_map"] == ["44", 0]


@pytest.mark.parametrize(
    "control",
    [
        {"geometry": "pose"},
        {"geometry": "upload"},
        {"geometry": "mask", "depth_asset_id": "x"},
        {"strength": 3.0},
        {"end_percent": 0.0},
        {"strength": True},
    ],
)
def test_control_validation(job_spec, control):
    with pytest.raises(ValidationError):
        compile_c(control_spec(job_spec, **control))


def test_vision_is_text_encoder_only(job_spec):
    spec = {
        **job_spec,
        "task": "vision",
        "profile_id": "vision_v1",
        "references": [{"asset_id": new_id(), "slot": 1}, {"asset_id": new_id(), "slot": 2}],
        "control": {"image_strength": 1.5},
        "width": 1024,
        "height": 1536,
    }
    graph = compile_vision(
        spec,
        load("workflows/vision.json"),
        load("configs/profiles/vision.json"),
        REGISTRY,
        ["moss_a.png", "moss_b.png"],
    )
    for encoder in ("4", "5"):
        inputs = graph[encoder]["inputs"]
        assert "vae" not in inputs  # no reference latents: vision tower only
        assert inputs["images.image_1"] == ["12", 0] and inputs["image_strength"] == 1.5
    assert not any(n["class_type"] == "LoraLoaderModelOnly" for n in graph.values())
    assert graph["6"]["inputs"]["height"] == 1536
    with pytest.raises(ValidationError):
        compile_vision(
            {**spec, "control": {"image_strength": 9}},
            load("workflows/vision.json"),
            load("configs/profiles/vision.json"),
            REGISTRY,
            ["moss_a.png", "moss_b.png"],
        )


class Engine:
    def __init__(self):
        self.uploaded = {}

    def object_info(self):
        class Any(dict):
            def get(self, key, default=None):
                return {"input": {"required": {}}}

        return Any()

    def upload_image(self, name, data):
        self.uploaded[name] = data
        return name

    def cancel_owned(self, prompt_id, *, exclusive_engine):
        return "not_queued"


def png(size, color):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_service_resizes_colour_map_with_flat_regions_and_checks_kinds(tmp_path):
    engine = Engine()
    service = StudioService(
        ROOT, tmp_path, engine=engine, runner=lambda g, p, e: [png((1360, 768), "white")]
    )
    try:
        project = service.projects.create("控制")
        source = service.import_asset(project["id"], png((1920, 1080), "gray"))
        colour = Image.new("RGB", (64, 36), "red")
        colour.paste((0, 0, 255), (32, 0, 64, 36))
        buffer = io.BytesIO()
        colour.save(buffer, format="PNG")
        colour_asset = service.import_asset(project["id"], buffer.getvalue(), kind="control")
        project = service.projects.get(project["id"])
        spec = {
            **control_spec(
                {
                    "project_id": project["id"],
                    "client_request_id": new_id(),
                    "project_revision": project["revision"],
                    "model_artifact_id": "sft_bf16",
                    "prompt": "a dancer",
                    "negative_prompt": "",
                    "width": 1360,
                    "height": 768,
                    "seed": 5,
                    "layout": None,
                    "mask_asset_id": None,
                    "lora_stack": [],
                },
                color_asset_id=colour_asset["id"],
            ),
            "references": [{"asset_id": source["id"], "slot": 1}],
        }
        with pytest.raises(ValidationError, match="素材種類"):
            service.submit({**spec, "control": {**spec["control"], "color_asset_id": source["id"]}})
        job_id = service.submit(spec)["id"]
        deadline = time.monotonic() + 5
        while service.get_job(job_id)["status"] not in {"succeeded", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert service.get_job(job_id)["status"] == "succeeded"
        colour_name = next(n for n in engine.uploaded if "_color_" in n)
        uploaded = Image.open(io.BytesIO(engine.uploaded[colour_name]))
        assert uploaded.size == (1360, 768)
        assert set(uploaded.getdata()) == {(255, 0, 0), (0, 0, 255)}  # nearest: no blended IDs
    finally:
        service.close()
