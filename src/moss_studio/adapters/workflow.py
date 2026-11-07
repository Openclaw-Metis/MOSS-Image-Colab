"""Pure compilation from validated immutable snapshots into trusted API templates."""

import json
from copy import deepcopy
from pathlib import Path

from moss_studio.domain.contracts import ValidationError, digest, validate_job_spec
from moss_studio.domain.layout import compile_layout, parse_layout


def check_profile(spec: dict, profile: dict, registry: dict, task_family: str) -> dict:
    """Profile/model compatibility. Rejects instead of silently dropping user settings."""
    if profile["id"] != spec["profile_id"]:
        raise ValidationError("採樣設定與工作快照不符")
    if profile.get("task_family") != task_family:
        raise ValidationError("E_MODEL_INCOMPATIBLE：此採樣預設不適用於目前工作模式")
    artifact = registry.get(spec["model_artifact_id"])
    if not artifact or artifact["role"] != "backbone" or artifact["dtype"] != "bf16":
        raise ValidationError("E_MODEL_INCOMPATIBLE：請選擇已宣告的 bf16 主幹")
    if spec["model_artifact_id"] not in profile.get("allowed_models", []):
        raise ValidationError("E_MODEL_INCOMPATIBLE：此採樣預設不支援目前主幹")
    if not profile.get("negative_prompt", True) and spec["negative_prompt"].strip():
        # CFG 1 never evaluates the negative branch; refuse rather than ignore the text.
        raise ValidationError("E_MODEL_INCOMPATIBLE：此預設不使用負向提示詞，請清空後再提交")
    return artifact


def model_chain(graph: dict, profile: dict, registry: dict, extra_loras=()) -> list:
    """UNET (node 1) → LoRAs (30+) → shift (20) → SLG (21); returns the sampler model ref."""
    model = ["1", 0]
    for index, lora in enumerate([*profile.get("lora_stack", []), *extra_loras]):
        artifact = registry.get(lora["artifact_id"])
        if not artifact or not artifact["filename"].startswith("loras/"):
            raise ValidationError("E_CAPABILITY：LoRA 尚未列入固定模型清單")
        node = str(30 + index)
        graph[node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": model,
                "lora_name": Path(artifact["filename"]).name,
                "strength_model": lora["strength"],
            },
        }
        model = [node, 0]
    if profile.get("tsr"):
        # Official colour/depth template: LoRA → TemporalScoreRescaling → shift → SLG.
        graph["22"] = {
            "class_type": "TemporalScoreRescaling",
            "inputs": {"model": model, **profile["tsr"]},
        }
        model = ["22", 0]
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
    return model


def validate_user_loras(stack, profile: dict, registry: dict) -> list[dict]:
    """Only presets that declare `user_loras` take a stack, and only of user-added LoRAs."""
    rules = profile.get("user_loras")
    if not stack:
        return []
    if not rules:
        raise ValidationError("E_MODEL_INCOMPATIBLE：此採樣預設不接受自加 LoRA（請改用精細 50 步）")
    if not isinstance(stack, list) or len(stack) > rules["max"]:
        raise ValidationError(f"自加 LoRA 最多 {rules['max']} 個")
    seen = set()
    for lora in stack:
        if not isinstance(lora, dict) or set(lora) != {"artifact_id", "strength"}:
            raise ValidationError("LoRA 設定欄位不符")
        artifact = registry.get(lora["artifact_id"])
        if not artifact or artifact.get("role") != "user_lora" or lora["artifact_id"] in seen:
            raise ValidationError("E_MODEL_INCOMPATIBLE：只能疊加模型頁加入的自加 LoRA，且不可重複")
        _bounded(lora["strength"], rules["strength"], "LoRA 強度")
        seen.add(lora["artifact_id"])
    return stack


def compile_t2i(spec: dict, template: dict, profile: dict, registry: dict) -> dict:
    validate_job_spec(spec)
    if spec["task"] not in {"t2i", "layout"}:
        raise ValidationError("此編譯器只接受文生圖與排版")
    if spec["references"] or spec["mask_asset_id"] or spec["control"]:
        raise ValidationError("E_MODEL_INCOMPATIBLE：文生圖預設不接受未驗證的參考或控制")
    user_loras = validate_user_loras(spec["lora_stack"], profile, registry)
    artifact = check_profile(spec, profile, registry, "t2i")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    graph["4"]["inputs"]["text"] = spec["prompt"]
    if spec["task"] == "layout":
        layout = parse_layout(spec["layout"], spec["width"], spec["height"])
        graph["4"]["inputs"]["text"] = json.dumps(
            compile_layout(
                layout["caption"], layout["items"], spec["width"], spec["height"], layout["meta"]
            ),
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
    graph["7"]["inputs"]["model"] = model_chain(graph, profile, registry, user_loras)
    return graph


def compile_edit(
    spec: dict, template: dict, profile: dict, registry: dict, engine_names: list[str]
) -> dict:
    """Ordered references: LoadImage (11+) → ImageScaleToTotalPixels (15+) → both encoders.

    The positive and negative encoders must carry the same edit_format and the same images
    in the same order; slot N in the snapshot is images.image_{N-1} here.
    """
    validate_job_spec(spec)
    if spec["task"] != "instruction_edit":
        raise ValidationError("此編譯器只接受指令修圖")
    if spec["mask_asset_id"] or spec["control"] or spec["layout"] or spec["lora_stack"]:
        raise ValidationError("E_MODEL_INCOMPATIBLE：指令修圖不接受遮罩、控制、排版或額外 LoRA")
    if len(engine_names) != len(spec["references"]) or not 1 <= len(engine_names) <= 4:
        raise ValidationError("參考圖數量與工作快照不符")
    artifact = check_profile(spec, profile, registry, "edit")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    for index, name in enumerate(engine_names):
        load, scale = str(11 + index), str(15 + index)
        graph[load] = {"class_type": "LoadImage", "inputs": {"image": name}}
        graph[scale] = {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [load, 0],
                "upscale_method": "lanczos",
                "megapixels": profile["reference_megapixels"],
                "resolution_steps": 16,
            },
        }
        for encoder in ("4", "5"):
            graph[encoder]["inputs"][f"images.image_{index}"] = [scale, 0]
    for encoder, text in (("4", spec["prompt"]), ("5", spec["negative_prompt"])):
        graph[encoder]["inputs"].update(prompt=text, edit_format=profile["edit_format"])
    graph["7"]["inputs"].update(
        seed=spec["seed"],
        steps=profile["steps"],
        cfg=profile["cfg"],
        sampler_name=profile["sampler"],
        scheduler=profile["scheduler"],
    )
    graph["7"]["inputs"]["model"] = model_chain(graph, profile, registry)
    return graph


INPAINT_CONTROL = {"denoise", "edge_softness", "confirm_full"}


def validate_inpaint_control(control, profile: dict) -> dict:
    if not isinstance(control, dict) or set(control) != INPAINT_CONTROL:
        raise ValidationError("重繪設定需包含 denoise、edge_softness、confirm_full")
    for field in ("denoise", "edge_softness"):
        value, bounds = control[field], profile[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not bounds["min"] <= value <= bounds["max"]
        ):
            raise ValidationError(f"{field} 必須在 {bounds['min']}～{bounds['max']} 之間")
    if not isinstance(control["confirm_full"], bool):
        raise ValidationError("confirm_full 必須是是非值")
    return control


def compile_inpaint(
    spec: dict, template: dict, profile: dict, registry: dict, source_name: str, mask_name: str
) -> dict:
    """Source → VAEEncode → SetLatentNoiseMask(feathered mask) → sampler at `denoise`."""
    validate_job_spec(spec)
    if spec["task"] != "inpaint":
        raise ValidationError("此編譯器只接受筆刷重繪")
    if spec["layout"] or spec["lora_stack"] or len(spec["references"]) != 1:
        raise ValidationError("E_MODEL_INCOMPATIBLE：筆刷重繪只接受一張來源圖與遮罩")
    control = validate_inpaint_control(spec["control"], profile)
    artifact = check_profile(spec, profile, registry, "inpaint")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    graph["4"]["inputs"]["text"] = spec["prompt"]
    graph["5"]["inputs"]["text"] = spec["negative_prompt"]
    graph["11"]["inputs"]["image"] = source_name
    graph["12"]["inputs"]["image"] = mask_name
    graph["7"]["inputs"].update(
        seed=spec["seed"],
        steps=profile["steps"],
        cfg=profile["cfg"],
        sampler_name=profile["sampler"],
        scheduler=profile["scheduler"],
        denoise=control["denoise"],
    )
    graph["7"]["inputs"]["model"] = model_chain(graph, profile, registry)
    return graph


CONTROL_FIELDS = {"geometry", "strength", "end_percent", "depth_asset_id", "color_asset_id"}


def _bounded(value, bounds: dict, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not bounds["min"] <= value <= bounds["max"]
    ):
        raise ValidationError(f"{field} 必須在 {bounds['min']}～{bounds['max']} 之間")


def validate_control(control, profile: dict) -> dict:
    if not isinstance(control, dict) or set(control) != CONTROL_FIELDS:
        raise ValidationError("控制設定欄位不符")
    if control["geometry"] not in profile["geometry"]:
        raise ValidationError("未知的幾何來源")
    _bounded(control["strength"], profile["strength"], "strength")
    _bounded(control["end_percent"], profile["end_percent"], "end_percent")
    if control["geometry"] == "upload" and not control["depth_asset_id"]:
        raise ValidationError("選擇上傳深度圖時需要提供深度圖")
    if control["geometry"] != "upload" and control["depth_asset_id"]:
        raise ValidationError("只有上傳模式才使用自備深度圖")
    return control


def compile_control(spec: dict, template: dict, profile: dict, registry: dict, names: dict) -> dict:
    """Source → (MoGe 3 mask|depth or uploaded depth) [+ colour map] → MOSSImageControl."""
    validate_job_spec(spec)
    if spec["task"] != "color_depth":
        raise ValidationError("此編譯器只接受色彩／深度控制")
    if (
        spec["mask_asset_id"]
        or spec["layout"]
        or spec["lora_stack"]
        or len(spec["references"]) != 1
    ):
        raise ValidationError("E_MODEL_INCOMPATIBLE：控制模式只接受一張來源圖")
    control = validate_control(spec["control"], profile)
    artifact = check_profile(spec, profile, registry, "control")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    graph["4"]["inputs"]["text"] = spec["prompt"]
    graph["5"]["inputs"]["text"] = spec["negative_prompt"]
    graph["6"]["inputs"].update(width=spec["width"], height=spec["height"])
    applied = graph["53"]["inputs"]
    applied.update(strength=control["strength"], end_percent=control["end_percent"])
    if control["geometry"] in {"mask", "depth"}:
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": names["source"]}}
        graph["15"] = {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["11", 0],
                "upscale_method": "lanczos",
                "megapixels": profile["working_megapixels"],
                "resolution_steps": 16,
            },
        }
        moge = registry.get("moge3_vitg")
        if not moge:
            raise ValidationError("E_CAPABILITY：幾何估計模型未列入固定清單")
        graph["40"] = {
            "class_type": "LoadMoGeModel",
            "inputs": {"model_name": Path(moge["filename"]).name},
        }
        graph["41"] = {
            "class_type": "MoGeInference",
            "inputs": {
                "moge_model": ["40", 0],
                "image": ["15", 0],
                "resolution_level": 9,
                "fov_x_degrees": 0.0,
                "batch_size": 4,
                "force_projection": True,
                "apply_mask": True,
                "refine_steps": 3,
            },
        }
        graph["42"] = {
            "class_type": "MoGeRender",
            "inputs": {"moge_geometry": ["41", 0], "output": control["geometry"]},
        }
        applied["depth_map"] = ["42", 0]
        # Saved as an auxiliary output so the user can see the geometry that was applied.
        graph["46"] = {
            "class_type": "SaveImage",
            "inputs": {"images": ["42", 0], "filename_prefix": "moss_studio_control_map"},
        }
    else:
        graph["43"] = {"class_type": "LoadImage", "inputs": {"image": names["depth"]}}
        applied["depth_map"] = ["43", 0]
    if control["color_asset_id"]:
        graph["44"] = {"class_type": "LoadImage", "inputs": {"image": names["color"]}}
        applied["color_map"] = ["44", 0]
    graph["7"]["inputs"].update(
        seed=spec["seed"],
        steps=profile["steps"],
        cfg=profile["cfg"],
        sampler_name=profile["sampler"],
        scheduler=profile["scheduler"],
    )
    graph["7"]["inputs"]["model"] = model_chain(graph, profile, registry)
    return graph


def compile_vision(
    spec: dict, template: dict, profile: dict, registry: dict, engine_names: list[str]
) -> dict:
    """Experimental: references reach only the text encoder's vision tower (no VAE, no LoRA)."""
    validate_job_spec(spec)
    if spec["task"] != "vision":
        raise ValidationError("此編譯器只接受視覺參考")
    if spec["mask_asset_id"] or spec["layout"] or spec["lora_stack"]:
        raise ValidationError("E_MODEL_INCOMPATIBLE：視覺參考不接受遮罩、排版或 LoRA")
    if len(engine_names) != len(spec["references"]) or not 1 <= len(engine_names) <= 4:
        raise ValidationError("參考圖數量與工作快照不符")
    control = spec["control"]
    if not isinstance(control, dict) or set(control) != {"image_strength"}:
        raise ValidationError("視覺參考設定只接受 image_strength")
    _bounded(control["image_strength"], profile["image_strength"], "image_strength")
    artifact = check_profile(spec, profile, registry, "vision")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    for index, name in enumerate(engine_names):
        node = str(11 + index)
        graph[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
        for encoder in ("4", "5"):
            graph[encoder]["inputs"][f"images.image_{index}"] = [node, 0]
    for encoder, text in (("4", spec["prompt"]), ("5", spec["negative_prompt"])):
        graph[encoder]["inputs"].update(prompt=text, image_strength=control["image_strength"])
    graph["6"]["inputs"].update(width=spec["width"], height=spec["height"])
    graph["7"]["inputs"].update(
        seed=spec["seed"],
        steps=profile["steps"],
        cfg=profile["cfg"],
        sampler_name=profile["sampler"],
        scheduler=profile["scheduler"],
    )
    graph["7"]["inputs"]["model"] = model_chain(graph, profile, registry)
    return graph


def compile_upscale(
    spec: dict, template: dict, profile: dict, registry: dict, source_name: str, passes: list
) -> dict:
    """Per pass: ImageScale (pixel space) → VAEEncode → KSampler(denoise) → VAEDecode.

    The first sampler is node "7" and the final decoder node "8" so job stages advance the
    same way as other tasks; intermediate passes use 120+/130+ ids.
    """
    validate_job_spec(spec)
    if spec["task"] != "upscale":
        raise ValidationError("此編譯器只接受高解析放大")
    if (
        spec["mask_asset_id"]
        or spec["layout"]
        or spec["lora_stack"]
        or len(spec["references"]) != 1
    ):
        raise ValidationError("E_MODEL_INCOMPATIBLE：放大只接受一張來源圖")
    control = spec["control"]
    if not isinstance(control, dict) or set(control) != {"denoise"}:
        raise ValidationError("放大設定只接受 denoise")
    _bounded(control["denoise"], profile["denoise"], "denoise")
    if not passes or tuple(passes[-1]) != (spec["width"], spec["height"]):
        raise ValidationError("放大段數與目標尺寸不符")
    artifact = check_profile(spec, profile, registry, "upscale")
    graph = deepcopy(template)
    graph["1"]["inputs"]["unet_name"] = Path(artifact["filename"]).name
    graph["4"]["inputs"]["text"] = spec["prompt"]
    graph["5"]["inputs"]["text"] = spec["negative_prompt"]
    graph["11"]["inputs"]["image"] = source_name
    model = model_chain(graph, profile, registry)
    image = ["11", 0]
    for index, (width, height) in enumerate(passes):
        last = index == len(passes) - 1
        scale, encode = str(100 + index), str(110 + index)
        sampler = "7" if index == 0 else str(120 + index)
        decode = "8" if last else str(130 + index)
        graph[scale] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": image,
                "upscale_method": "lanczos",
                "width": width,
                "height": height,
                "crop": "disabled",
            },
        }
        graph[encode] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": [scale, 0], "vae": ["3", 0]},
        }
        graph[sampler] = {
            "class_type": "KSampler",
            "inputs": {
                "model": model,
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": [encode, 0],
                "seed": spec["seed"],
                "steps": profile["steps"],
                "cfg": profile["cfg"],
                "sampler_name": profile["sampler"],
                "scheduler": profile["scheduler"],
                "denoise": control["denoise"],
            },
        }
        graph[decode] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": [sampler, 0], "vae": ["3", 0]},
        }
        image = [decode, 0]
    return graph


def validate_nodes(graph: dict, object_info: dict, pending_uploads=frozenset()) -> None:
    """Checks actual node names, required inputs, connections and loader enum values.

    ComfyUI lists LoadImage/LoadImageMask choices from files already in its input folder, but the
    service uploads a job's own images only when the job runs. Those names (moss_*.png, passed as
    pending_uploads) are therefore accepted; model and option enums stay strict.
    """
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
            if (
                key == "image"
                and node["class_type"] in {"LoadImage", "LoadImageMask"}
                and value in pending_uploads
            ):
                continue
            if isinstance(declaration[0], list) and value not in declaration[0]:
                raise ValidationError(f"E_CAPABILITY：{key} 的模型或選項尚未就緒")


def workflow_hash(graph: dict) -> str:
    return digest(graph)
