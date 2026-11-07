import json
from copy import deepcopy
from pathlib import Path

import pytest

from moss_studio.adapters.workflow import compile_t2i, validate_nodes, workflow_hash
from moss_studio.domain.contracts import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_immutable_graph_compilation_and_no_profile_residue(job_spec):
    template = json.loads((ROOT / "workflows/t2i.json").read_text(encoding="utf-8"))
    profile = json.loads((ROOT / "configs/profiles/quality50.json").read_text(encoding="utf-8"))
    registry = {
        a["id"]: a
        for a in json.loads((ROOT / "configs/models.lock.json").read_text(encoding="utf-8"))[
            "artifacts"
        ]
    }
    original = deepcopy(template)
    graph = compile_t2i(job_spec, template, profile, registry)
    assert graph["7"]["inputs"]["steps"] == 50
    assert graph["21"]["inputs"]["single_layers"] == "22"
    assert graph["20"]["inputs"]["shift"] == 5
    assert template == original
    assert workflow_hash(graph) == workflow_hash(deepcopy(graph))
    custom = {**profile, "slg": None, "shift": None}
    other = compile_t2i(job_spec, template, custom, registry)
    assert "20" not in other and "21" not in other
    assert other["7"]["inputs"]["model"] == ["1", 0]
    assert graph != other


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


REGISTRY = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}


def test_fast8_graph_and_switch_back_has_no_residue(job_spec):
    """AC-07 contract: each profile compiles exactly its own settings from the same template."""
    template = load("workflows/t2i.json")
    quality, fast = load("configs/profiles/quality50.json"), load("configs/profiles/fast8.json")
    fast_spec = {**job_spec, "profile_id": "fast8_v1"}
    graph = compile_t2i(fast_spec, template, fast, REGISTRY)
    sampler = graph["7"]["inputs"]
    assert (sampler["steps"], sampler["cfg"], sampler["sampler_name"]) == (8, 1.0, "euler")
    assert graph["30"]["class_type"] == "LoraLoaderModelOnly"
    assert graph["30"]["inputs"] == {
        "model": ["1", 0],
        "lora_name": "moss_image_sft_dmd8_lora_latest_f95df83.safetensors",
        "strength_model": 0.7,
    }
    assert graph["20"]["inputs"]["model"] == ["30", 0]
    assert "21" not in graph  # no SLG on the distilled path
    assert sampler["model"] == ["20", 0]
    back = compile_t2i(job_spec, template, quality, REGISTRY)
    assert "30" not in back and back["7"]["inputs"]["cfg"] == 3.0
    assert back["7"]["inputs"]["steps"] == 50 and back["21"]["inputs"]["single_layers"] == "22"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"model_artifact_id": "base_bf16"}, "不支援目前主幹"),
        ({"negative_prompt": "bad anatomy"}, "負向提示詞"),
        ({"profile_id": "quality50_v1"}, "不符"),
    ],
)
def test_fast8_incompatible_requests_are_rejected_not_dropped(job_spec, change, message):
    spec = {**job_spec, "profile_id": "fast8_v1", **change}
    with pytest.raises(ValidationError, match=message):
        compile_t2i(spec, load("workflows/t2i.json"), load("configs/profiles/fast8.json"), REGISTRY)


def test_profile_lora_must_be_a_pinned_lora(job_spec):
    profile = {**load("configs/profiles/fast8.json"), "lora_stack": [{"artifact_id": "sft_bf16"}]}
    spec = {**job_spec, "profile_id": "fast8_v1"}
    with pytest.raises(ValidationError, match="LoRA"):
        compile_t2i(spec, load("workflows/t2i.json"), profile, REGISTRY)


def test_actual_node_contract_rejects_missing_weights():
    graph = {"1": {"class_type": "Loader", "inputs": {"name": "missing.safetensors"}}}
    info = {"Loader": {"input": {"required": {"name": [["ready.safetensors"]]}}}}
    with pytest.raises(ValidationError):
        validate_nodes(graph, info)
    with pytest.raises(ValidationError):
        validate_nodes(graph, {})


def test_autogrow_inputs_are_validated_in_their_flattened_api_form():
    # Declaration as served by ComfyUI 0.44 for TextEncodeMOSSImageEdit.images (live L4 query).
    autogrow = [
        "COMFY_AUTOGROW_V3",
        {
            "template": {"input": {"required": {"image": ["IMAGE", {}]}}},
            "prefix": "image_",
            "min": 1,
            "max": 10,
        },
    ]
    info = {
        "Encode": {"input": {"required": {"images": autogrow}}},
        "LoadImage": {"input": {"required": {}}},
    }
    graph = {
        "11": {"class_type": "LoadImage", "inputs": {}},
        "4": {"class_type": "Encode", "inputs": {"images.image_0": ["11", 0]}},
    }
    validate_nodes(graph, info)
    for inputs in ({}, {"images.image_0": ["99", 0]}, {"images.image_0": "x"}):
        graph["4"]["inputs"] = inputs
        with pytest.raises(ValidationError):
            validate_nodes(graph, info)


def test_own_pending_uploads_pass_image_enums_but_nothing_else_does():
    # Real ComfyUI lists only files already in its input folder; the job uploads its own later.
    info = {
        "LoadImage": {"input": {"required": {"image": [["old.png"]]}}},
        "Loader": {"input": {"required": {"name": [["ready.safetensors"]]}}},
    }
    graph = {"11": {"class_type": "LoadImage", "inputs": {"image": "moss_a.png"}}}
    with pytest.raises(ValidationError):
        validate_nodes(graph, info)
    validate_nodes(graph, info, {"moss_a.png"})
    with pytest.raises(ValidationError):
        validate_nodes(graph, info, {"moss_b.png"})
    loader = {"1": {"class_type": "Loader", "inputs": {"name": "moss_a.png"}}}
    with pytest.raises(ValidationError):  # only image loaders get the exemption
        validate_nodes(loader, info, {"moss_a.png"})
