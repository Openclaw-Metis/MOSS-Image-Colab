import io
import json
import time
from pathlib import Path

import pytest
from PIL import Image

from moss_studio.adapters.comfy import EngineError
from moss_studio.adapters.workflow import compile_edit
from moss_studio.domain.contracts import ValidationError, new_id
from moss_studio.domain.references import renumber, scaled_to_total_pixels
from moss_studio.services.studio import StudioService

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


REGISTRY = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}


@pytest.mark.parametrize(
    ("size", "expected"),
    [((1024, 1024), (1024, 1024)), ((1920, 1080), (1360, 768)), ((512, 768), (832, 1248))],
)
def test_main_image_size_matches_comfy_image_scale_to_total_pixels(size, expected):
    assert scaled_to_total_pixels(*size) == expected


def test_renumber_reports_every_moved_picture():
    slots, mapping = renumber(["a", None, "c", "d"])
    assert slots == ["a", "c", "d"]
    assert mapping == {1: 1, 3: 2, 4: 3}


def edit_spec(job_spec, count=2):
    return {
        **job_spec,
        "task": "instruction_edit",
        "profile_id": "edit_v1",
        "prompt": "Change only the jacket to black. Keep everything else unchanged.",
        "references": [{"asset_id": new_id(), "slot": i + 1} for i in range(count)],
    }


def test_edit_graph_feeds_same_ordered_images_to_both_encoders(job_spec):
    spec = edit_spec(job_spec)
    names = ["moss_a.png", "moss_b.png"]
    graph = compile_edit(
        spec, load("workflows/edit.json"), load("configs/profiles/edit.json"), REGISTRY, names
    )
    assert [graph["11"]["inputs"]["image"], graph["12"]["inputs"]["image"]] == names
    for encoder in ("4", "5"):
        inputs = graph[encoder]["inputs"]
        assert inputs["images.image_0"] == ["15", 0] and inputs["images.image_1"] == ["16", 0]
        assert inputs["edit_format"] == "Moss-Image-Edit" and inputs["vae"] == ["3", 0]
    assert graph["4"]["inputs"]["prompt"] == spec["prompt"]
    assert graph["15"]["inputs"]["megapixels"] == 1.0
    assert graph["15"]["inputs"]["resolution_steps"] == 16
    assert graph["10"]["inputs"]["image"] == ["15", 0]  # latent follows the scaled main image
    assert graph["30"]["inputs"]["lora_name"] == "moss_image_edit_lora_rank_64_bf16.safetensors"
    assert graph["21"]["inputs"]["end_percent"] == 1.0 and "20" not in graph
    sampler = graph["7"]["inputs"]
    assert (sampler["steps"], sampler["cfg"], sampler["scheduler"]) == (30, 4.0, "normal")
    assert sampler["model"] == ["21", 0]


@pytest.mark.parametrize(
    ("change", "names"),
    [
        ({"mask_asset_id": new_id()}, ["moss_a.png", "moss_b.png"]),
        (
            {"lora_stack": [{"artifact_id": "dmd8_lora", "strength": 1}]},
            ["moss_a.png", "moss_b.png"],
        ),
        ({}, ["moss_a.png"]),
        ({"profile_id": "quality50_v1"}, ["moss_a.png", "moss_b.png"]),
    ],
)
def test_edit_rejects_incompatible_inputs(job_spec, change, names):
    spec = {**edit_spec(job_spec), **change}
    profile = load(f"configs/profiles/{'quality50' if 'profile_id' in change else 'edit'}.json")
    with pytest.raises(ValidationError):
        compile_edit(spec, load("workflows/edit.json"), profile, REGISTRY, names)


class Engine:
    def __init__(self):
        self.uploaded, self.fail_upload = [], False

    def object_info(self):
        class Any(dict):
            def get(self, key, default=None):
                return {"input": {"required": {}}}

        return Any()

    def upload_image(self, name, data):
        if self.fail_upload:
            raise EngineError("upload refused")
        self.uploaded.append((name, len(data)))
        return name

    def cancel_owned(self, prompt_id, *, exclusive_engine):
        return "not_queued"


def png(size, color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def edit_studio(tmp_path):
    engine = Engine()
    graphs = []

    def runner(graph, prompt_id, event):
        graphs.append(graph)
        width, height = 1360, 768
        return [png((width, height), "blue")]

    service = StudioService(ROOT, tmp_path, engine=engine, runner=runner)
    try:
        yield service, engine, graphs
    finally:
        service.close()


def wait(service, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.01)
    pytest.fail("worker did not finish")


def submit_edit(service, project, refs, size):
    project = service.projects.get(project["id"])
    return service.submit(
        {
            "project_id": project["id"],
            "client_request_id": new_id(),
            "project_revision": project["revision"],
            "task": "instruction_edit",
            "profile_id": "edit_v1",
            "model_artifact_id": "sft_bf16",
            "prompt": "Change only the background to night.",
            "negative_prompt": "",
            "width": size[0],
            "height": size[1],
            "seed": 1,
            "references": [{"asset_id": a["id"], "slot": i + 1} for i, a in enumerate(refs)],
            "layout": None,
            "mask_asset_id": None,
            "control": None,
            "lora_stack": [],
        }
    )


def test_service_uploads_references_in_slot_order_and_follows_main_size(edit_studio):
    service, engine, graphs = edit_studio
    project = service.projects.create("修圖")
    main = service.import_asset(project["id"], png((1920, 1080)))
    second = service.import_asset(project["id"], png((300, 300), "green"))
    assert main["edit_size"] == [1360, 768]
    with pytest.raises(ValidationError, match="1360×768"):
        submit_edit(service, project, [main, second], (1024, 1024))
    job = wait(service, submit_edit(service, project, [main, second], (1360, 768))["id"])
    assert job["status"] == "succeeded"
    assert [name for name, _ in engine.uploaded] == [
        f"moss_{main['id']}.png",
        f"moss_{second['id']}.png",
    ]
    assert graphs[0]["11"]["inputs"]["image"] == f"moss_{main['id']}.png"


def test_reference_from_another_project_or_output_is_rejected(edit_studio):
    service, _, _ = edit_studio
    project, other = service.projects.create("甲"), service.projects.create("乙")
    foreign = service.import_asset(other["id"], png((1024, 1024)))
    with pytest.raises(ValidationError, match="不屬於"):
        submit_edit(service, project, [foreign], (1024, 1024))


def test_upload_failure_fails_job_without_fencing_the_gpu(edit_studio):
    service, engine, graphs = edit_studio
    engine.fail_upload = True
    project = service.projects.create("上傳失敗")
    main = service.import_asset(project["id"], png((1024, 1024)))
    job = wait(service, submit_edit(service, project, [main], (1024, 1024))["id"])
    assert job["status"] == "failed"
    assert not graphs and service.gpu_blocked is False
