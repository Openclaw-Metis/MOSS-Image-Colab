"""Compiles one graph of every kind and validates it against the live ComfyUI object_info.

Run on the L4 runtime before a GPU batch: missing nodes, inputs, options or model files show up
in seconds instead of after an hour of queued jobs. Nothing is uploaded or queued.
    python scripts/engine_preflight.py            # prints one line per graph, exit 1 on failure
"""

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from moss_studio.adapters.comfy import ComfyClient  # noqa: E402
from moss_studio.adapters.workflow import (  # noqa: E402
    compile_control,
    compile_edit,
    compile_inpaint,
    compile_t2i,
    compile_upscale,
    compile_vision,
    validate_nodes,
)
from moss_studio.domain.contracts import new_id  # noqa: E402
from moss_studio.domain.hires import plan_passes  # noqa: E402
from moss_studio.domain.layout import compile_layout  # noqa: E402


def load(name: str) -> dict:
    return json.loads((REPOSITORY / name).read_text(encoding="utf-8"))


REGISTRY = {a["id"]: a for a in load("configs/models.lock.json")["artifacts"]}
NAMES = [f"moss_preflight_{i}.png" for i in range(1, 5)]


def spec(**fields) -> dict:
    base = {
        "project_id": new_id(),
        "client_request_id": new_id(),
        "project_revision": 0,
        "task": "t2i",
        "profile_id": "quality50_v1",
        "model_artifact_id": "sft_bf16",
        "prompt": "preflight",
        "negative_prompt": "",
        "width": 1024,
        "height": 1024,
        "seed": 1,
        "references": [],
        "layout": None,
        "mask_asset_id": None,
        "control": None,
        "lora_stack": [],
    }
    return {**base, **fields}


def refs(count: int) -> list[dict]:
    return [{"asset_id": new_id(), "slot": i} for i in range(1, count + 1)]


def graphs() -> dict:
    """name → (compiler thunk, image names the job itself would upload)."""
    case = load("tests/fixtures/zh_tw_layouts.json")["cases"][0]
    items = [{**item, "id": new_id(), "z_order": i} for i, item in enumerate(case["items"])]
    layout = compile_layout(case["caption"], items, 1024, 1024)
    control = {"strength": 1.0, "end_percent": 0.6, "depth_asset_id": None, "color_asset_id": None}
    upload = {
        **control,
        "geometry": "upload",
        "depth_asset_id": new_id(),
        "color_asset_id": new_id(),
    }
    control_names = {"source": NAMES[0], "depth": None, "color": None}
    upload_names = {"source": NAMES[0], "depth": NAMES[1], "color": NAMES[2]}
    p = {
        name: load(f"configs/profiles/{name}.json")
        for name in ("quality50", "fast8", "edit", "inpaint", "control", "vision", "upscale")
    }
    w = {
        name: load(f"workflows/{name}.json")
        for name in ("t2i", "edit", "inpaint", "control", "vision", "upscale")
    }
    return {
        "t2i quality50": (lambda: compile_t2i(spec(), w["t2i"], p["quality50"], REGISTRY), []),
        "t2i fast8": (
            lambda: compile_t2i(spec(profile_id="fast8_v1"), w["t2i"], p["fast8"], REGISTRY),
            [],
        ),
        "layout": (
            lambda: compile_t2i(
                spec(task="layout", layout=layout), w["t2i"], p["quality50"], REGISTRY
            ),
            [],
        ),
        "edit 1 image": (
            lambda: compile_edit(
                spec(task="instruction_edit", profile_id="edit_v1", references=refs(1)),
                w["edit"],
                p["edit"],
                REGISTRY,
                NAMES[:1],
            ),
            NAMES[:1],
        ),
        "edit 4 images": (
            lambda: compile_edit(
                spec(task="instruction_edit", profile_id="edit_v1", references=refs(4)),
                w["edit"],
                p["edit"],
                REGISTRY,
                NAMES,
            ),
            NAMES,
        ),
        "inpaint": (
            lambda: compile_inpaint(
                spec(
                    task="inpaint",
                    profile_id="inpaint_v1",
                    references=refs(1),
                    mask_asset_id=new_id(),
                    control={"denoise": 0.65, "edge_softness": 0.15, "confirm_full": False},
                ),
                w["inpaint"],
                p["inpaint"],
                REGISTRY,
                NAMES[0],
                NAMES[1],
            ),
            NAMES[:2],
        ),
        **{
            f"control {geometry}": (
                lambda g=geometry: compile_control(
                    spec(
                        task="color_depth",
                        profile_id="control_v1",
                        references=refs(1),
                        control={**control, "geometry": g},
                    ),
                    w["control"],
                    p["control"],
                    REGISTRY,
                    control_names,
                ),
                NAMES[:1],
            )
            for geometry in ("mask", "depth")
        },
        "control upload + colour": (
            lambda: compile_control(
                spec(
                    task="color_depth", profile_id="control_v1", references=refs(1), control=upload
                ),
                w["control"],
                p["control"],
                REGISTRY,
                upload_names,
            ),
            NAMES[:3],
        ),
        "vision": (
            lambda: compile_vision(
                spec(
                    task="vision",
                    profile_id="vision_v1",
                    references=refs(2),
                    control={"image_strength": 1.0},
                ),
                w["vision"],
                p["vision"],
                REGISTRY,
                NAMES[:2],
            ),
            NAMES[:2],
        ),
        "upscale 1024→2048": (
            lambda: compile_upscale(
                spec(
                    task="upscale",
                    profile_id="upscale_v1",
                    references=refs(1),
                    width=2048,
                    height=2048,
                    control={"denoise": 0.6},
                ),
                w["upscale"],
                p["upscale"],
                REGISTRY,
                NAMES[0],
                plan_passes((1024, 1024), (2048, 2048), 1.5),
            ),
            NAMES[:1],
        ),
    }


def main() -> int:
    info = ComfyClient().object_info()
    failures = 0
    for name, (build, uploads) in graphs().items():
        try:
            validate_nodes(build(), info, set(uploads))
            print(f"OK    {name}")
        except Exception as error:  # noqa: BLE001 - report every graph, then fail once
            failures += 1
            print(f"FAIL  {name}: {error}")
    print(json.dumps({"graphs": len(graphs()), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
