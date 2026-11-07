"""Pure compilation from validated immutable snapshots into trusted API templates."""

import json
from copy import deepcopy
from pathlib import Path

from moss_studio.domain.contracts import ValidationError, digest, validate_job_spec
from moss_studio.domain.layout import compile_layout, parse_layout


def compile_t2i(spec: dict, template: dict, profile: dict, registry: dict) -> dict:
    validate_job_spec(spec)
    if spec["task"] not in {"t2i", "layout"}:
        raise ValidationError("此編譯器只接受文生圖與排版")
    if spec["references"] or spec["mask_asset_id"] or spec["control"] or spec["lora_stack"]:
        raise ValidationError(
            "E_MODEL_INCOMPATIBLE：文生圖預設不接受未驗證的參考、控制或 LoRA 疊加"
        )
    artifact = registry.get(spec["model_artifact_id"])
    if not artifact or artifact["role"] != "backbone" or artifact["dtype"] != "bf16":
        raise ValidationError("E_MODEL_INCOMPATIBLE：請選擇已宣告的 bf16 主幹")
    if profile["id"] != spec["profile_id"]:
        raise ValidationError("採樣設定與工作快照不符")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    graph["4"]["inputs"]["text"] = spec["prompt"]
    if spec["task"] == "layout":
        layout = parse_layout(spec["layout"], spec["width"], spec["height"])
        graph["4"]["inputs"]["text"] = json.dumps(
            compile_layout(layout["caption"], layout["items"], spec["width"], spec["height"]),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    graph["5"]["inputs"]["text"] = spec["negative_prompt"]
    graph["6"]["inputs"].update(width=spec["width"], height=spec["height"], batch_size=1)
    graph["7"]["inputs"].update(
        seed=spec["seed"],
        steps=profile["steps"],
        cfg=profile["cfg"],
        sampler_name=profile["sampler"],
        scheduler=profile["scheduler"],
    )
    graph["9"]["inputs"]["filename_prefix"] = "moss_studio"
    model = ["1", 0]
    if profile.get("shift") is not None:
        graph["20"] = {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": model, "shift": profile["shift"]},
        }
        model = ["20", 0]
    if profile.get("slg"):
        graph["21"] = {
            "class_type": "SkipLayerGuidanceDiTSimple",
            "inputs": {"model": model, **profile["slg"]},
        }
        model = ["21", 0]
    graph["7"]["inputs"]["model"] = model
    return graph


def validate_nodes(graph: dict, object_info: dict) -> None:
    """Checks actual node names, required inputs, connections and loader enum values."""
    for node in graph.values():
        info = object_info.get(node["class_type"])
        if info is None:
            raise ValidationError(f"E_CAPABILITY：缺少節點 {node['class_type']}")
        inputs = node["inputs"]
        required = info["input"].get("required", {})
        for key, declaration in required.items():
            if key not in inputs:
                raise ValidationError(f"E_CAPABILITY：節點 {node['class_type']} 缺少 {key}")
            value = inputs[key]
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                if value[0] not in graph:
                    raise ValidationError("工作流連線不存在")
                continue
            if isinstance(declaration[0], list) and value not in declaration[0]:
                raise ValidationError(f"E_CAPABILITY：{key} 的模型或選項尚未就緒")


def workflow_hash(graph: dict) -> str:
    return digest(graph)
