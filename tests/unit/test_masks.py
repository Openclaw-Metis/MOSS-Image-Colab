"""AC-09 CPU parts: mask direction, finite feather support, exact source outside it."""

import io
import json
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from moss_studio.adapters.workflow import compile_inpaint
from moss_studio.domain.contracts import ValidationError, new_id
from moss_studio.domain.masks import (
    binary_mask,
    check_coverage,
    composite,
    feather_radius,
    feathered_alpha,
    resize_mask,
)
from moss_studio.services.studio import StudioService

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def circle_mask(size=(256, 256), box=(96, 96, 160, 160)):
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).ellipse(box, fill=255)
    return np.asarray(image) > 127


def test_product_feather_mapping():
    assert feather_radius(1024, 1024, 0.15) == 15
    assert feather_radius(1360, 768, 0.15) == 12
    assert feather_radius(1024, 1024, 0) == 0
    with pytest.raises(ValidationError):
        feather_radius(1024, 1024, 1.5)


@pytest.mark.parametrize("radius", [0, 1, 6, 15])
def test_feather_is_one_inside_and_exactly_zero_beyond_radius(radius):
    mask = circle_mask()
    alpha = feathered_alpha(mask, radius)
    assert (alpha[mask] == 1).all()
    ys, xs = np.nonzero(mask)
    yy, xx = np.mgrid[: mask.shape[0], : mask.shape[1]]
    # Chebyshev distance to the nearest selected pixel (MaxFilter grows a square).
    distance = np.full(mask.shape, 10**9)
    for y, x in zip(ys[::7], xs[::7], strict=True):
        distance = np.minimum(distance, np.maximum(abs(yy - y), abs(xx - x)))
    far = distance > radius + 8  # sampled seeds over-estimate distance by < 8 px
    assert (alpha[far] == 0).all()
    assert 0 <= alpha.min() and alpha.max() <= 1


def test_composite_keeps_source_bytes_outside_support_and_engine_inside():
    rng = np.random.default_rng(1)
    source = Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))
    generated = Image.new("RGB", (256, 256), (255, 0, 255))
    mask = circle_mask()
    alpha = feathered_alpha(mask, 10)
    result = np.asarray(composite(source, generated, alpha))
    original = np.asarray(source)
    assert (result[alpha == 0] == original[alpha == 0]).all()
    assert (result[mask] == (255, 0, 255)).all()


def test_black_or_white_brush_on_transparent_layer_and_opaque_bw_mask():
    layer = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle((0, 0, 10, 10), fill=(0, 0, 0, 255))  # black brush
    draw.rectangle((40, 40, 50, 50), fill=(255, 255, 255, 255))  # white brush
    selected = binary_mask(layer)
    assert selected[5, 5] and selected[45, 45] and not selected[30, 30]
    bw = Image.new("RGB", (64, 64), "black")
    ImageDraw.Draw(bw).rectangle((0, 0, 31, 63), fill="white")
    selected = binary_mask(bw)
    assert selected[:, :32].all() and not selected[:, 32:].any()


def test_empty_and_full_masks():
    with pytest.raises(ValidationError, match="E_MASK_EMPTY"):
        check_coverage(np.zeros((8, 8), bool), confirm_full=False)
    with pytest.raises(ValidationError, match="整張"):
        check_coverage(np.ones((8, 8), bool), confirm_full=False)
    check_coverage(np.ones((8, 8), bool), confirm_full=True)


def test_nearest_resize_stays_binary():
    resized = resize_mask(circle_mask(), (100, 50))
    assert resized.dtype == bool and resized.shape == (50, 100) and resized.any()


def inpaint_spec(job_spec, **change):
    return {
        **job_spec,
        "task": "inpaint",
        "profile_id": "inpaint_v1",
        "references": [{"asset_id": new_id(), "slot": 1}],
        "mask_asset_id": new_id(),
        "control": {"denoise": 0.65, "edge_softness": 0.15, "confirm_full": False},
        **change,
    }


def test_inpaint_graph_contract(job_spec):
    registry = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}
    graph = compile_inpaint(
        inpaint_spec(job_spec),
        load("workflows/inpaint.json"),
        load("configs/profiles/inpaint.json"),
        registry,
        "moss_src.png",
        "moss_mask.png",
    )
    assert graph["14"]["class_type"] == "SetLatentNoiseMask"
    assert graph["12"]["inputs"] == {"image": "moss_mask.png", "channel": "red"}
    assert graph["7"]["inputs"]["latent_image"] == ["14", 0]
    assert graph["7"]["inputs"]["denoise"] == 0.65


@pytest.mark.parametrize(
    "control",
    [
        None,
        {"denoise": 0.01, "edge_softness": 0.15, "confirm_full": False},
        {"denoise": 0.6, "edge_softness": 2, "confirm_full": False},
        {"denoise": 0.6, "edge_softness": 0.1, "confirm_full": "yes"},
        {"denoise": 0.6, "edge_softness": 0.1},
    ],
)
def test_inpaint_rejects_bad_controls(job_spec, control):
    registry = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}
    with pytest.raises(ValidationError):
        compile_inpaint(
            inpaint_spec(job_spec, control=control),
            load("workflows/inpaint.json"),
            load("configs/profiles/inpaint.json"),
            registry,
            "moss_src.png",
            "moss_mask.png",
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


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_service_composites_and_never_alters_pixels_outside_feather(tmp_path):
    engine = Engine()

    def runner(graph, prompt_id, event):
        return [png(Image.new("RGB", (1024, 1024), (255, 0, 255)))]

    service = StudioService(ROOT, tmp_path, engine=engine, runner=runner)
    try:
        project = service.projects.create("重繪")
        rng = np.random.default_rng(2)
        source = Image.fromarray(rng.integers(0, 256, (512, 512, 3), dtype=np.uint8))
        source_asset = service.import_asset(project["id"], png(source))
        mask = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        ImageDraw.Draw(mask).ellipse((200, 200, 300, 300), fill=(255, 255, 255, 255))
        mask_asset = service.import_asset(project["id"], png(mask), kind="mask")
        project = service.projects.get(project["id"])
        spec = {
            "project_id": project["id"],
            "client_request_id": new_id(),
            "project_revision": project["revision"],
            "task": "inpaint",
            "profile_id": "inpaint_v1",
            "model_artifact_id": "sft_bf16",
            "prompt": "a red flower",
            "negative_prompt": "",
            "width": 1024,
            "height": 1024,
            "seed": 3,
            "references": [{"asset_id": source_asset["id"], "slot": 1}],
            "layout": None,
            "mask_asset_id": mask_asset["id"],
            "control": {"denoise": 0.65, "edge_softness": 0.15, "confirm_full": False},
            "lora_stack": [],
        }
        with pytest.raises(ValidationError, match="1024×1024"):
            service.submit({**spec, "width": 512, "height": 512})
        job_id = service.submit(spec)["id"]
        deadline = time.monotonic() + 10
        while service.get_job(job_id)["status"] not in {"succeeded", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        job = service.get_job(job_id)
        assert job["status"] == "succeeded"
        assert job["record"]["feather_px"] == 15
        output = np.asarray(
            Image.open(service.assets.path(project["id"], job["record"]["output_assets"][0]))
        )
        working = np.asarray(source.resize((1024, 1024), Image.Resampling.LANCZOS))
        # Far corner is outside any feather band: must equal the working-size source exactly.
        assert (output[:300, :300] == working[:300, :300]).all()
        assert (output[512, 512] == (255, 0, 255)).all()
        names = sorted(engine.uploaded)
        assert any(source_asset["id"] in n for n in names)
        assert any(mask_asset["id"] in n for n in names)
    finally:
        service.close()


def test_service_rejects_empty_mask_without_creating_a_job(tmp_path):
    service = StudioService(ROOT, tmp_path, engine=Engine(), runner=lambda *a: [])
    try:
        project = service.projects.create("空遮罩")
        source = service.import_asset(project["id"], png(Image.new("RGB", (512, 512), "gray")))
        empty = service.import_asset(
            project["id"], png(Image.new("RGBA", (512, 512), (0, 0, 0, 0))), kind="mask"
        )
        project = service.projects.get(project["id"])
        with pytest.raises(ValidationError, match="E_MASK_EMPTY"):
            service.submit(
                {
                    "project_id": project["id"],
                    "client_request_id": new_id(),
                    "project_revision": project["revision"],
                    "task": "inpaint",
                    "profile_id": "inpaint_v1",
                    "model_artifact_id": "sft_bf16",
                    "prompt": "x",
                    "negative_prompt": "",
                    "width": 1024,
                    "height": 1024,
                    "seed": 1,
                    "references": [{"asset_id": source["id"], "slot": 1}],
                    "layout": None,
                    "mask_asset_id": empty["id"],
                    "control": {"denoise": 0.65, "edge_softness": 0.15, "confirm_full": False},
                    "lora_stack": [],
                }
            )
        assert service.ledger.list(project["id"]) == []
    finally:
        service.close()
