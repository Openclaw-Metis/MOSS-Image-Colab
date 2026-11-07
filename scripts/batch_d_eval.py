"""GPU batch D: AC-12 high resolution, AC-13 backbone switching, AC-14 compatibility guards,
AC-15 project archive (export half), AC-20 native 2048² (experimental).

Usage on the L4 runtime (app already running on 127.0.0.1:7860):
    MOSS_STUDIO_PASSWORD=... python scripts/batch_d_eval.py <evidence-dir> [--only native ...]

AC-15 second half, on a NEW Colab VM, after uploading the two files the first run wrote to
<evidence-dir>/ac15/ (ac15-project.zip and ac15_manifest.json):
    MOSS_STUDIO_PASSWORD=... python scripts/batch_d_eval.py <new-dir> \
        --import ac15-project.zip --manifest ac15_manifest.json

report.json is checkpointed after every job; GPU peaks are device memory.used sampled with
nvidia-smi while each job runs. The base backbone download starts first so it overlaps the
high-resolution jobs.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

from batch_c_eval import box_mask  # noqa: E402
from batch_runner import BatchReport, png_bytes  # noqa: E402
from product_client import ProductClient  # noqa: E402

from moss_studio.domain.contracts import new_id, now  # noqa: E402
from moss_studio.domain.layout import compile_layout  # noqa: E402

SECTIONS = ("compat", "native", "upscale", "models", "archive", "native2048")
PROMPT = "一隻橘貓坐在窗邊木桌上，旁邊一盆綠色植物，午後暖陽，細緻攝影"  # batch A baseline
DEFAULT_NEGATIVE = "nsfw, worst quality, bad anatomy, watermark, jpeg artifact"


def t2i(prompt: str, size: int, seed: int, profile: str = "quality50_v1", **extra) -> dict:
    return {
        "profile_id": profile,
        "prompt": prompt,
        "width": size,
        "height": size,
        "seed": str(seed),
        **extra,
    }


def run_native(report: BatchReport, section: str, size: int, seeds: range, timeout: float) -> None:
    for seed in seeds:
        report.run(section, str(seed), lambda s=seed: t2i(PROMPT, size, s), timeout=timeout)


def run_upscale(report: BatchReport) -> None:
    for seed in range(81101, 81104):
        source = report.run(
            "upscale_source", str(seed), lambda s=seed: t2i(PROMPT, 1024, s, "fast8_v1")
        )
        if source["status"] != "succeeded":
            continue
        report.run(
            "upscale",
            str(seed),
            lambda s=seed, a=source["output_asset"]: {
                "task": "upscale",
                "profile_id": "upscale_v1",
                "prompt": PROMPT,
                "width": 2048,
                "height": 2048,
                "seed": str(s),
                "references": [{"asset_id": a, "slot": 1}],
                "control": {"denoise": 0.6},
            },
            timeout=2400,
        )


def compat_cases(report: BatchReport) -> list[tuple[str, dict]]:
    """Unsupported model/profile/LoRA combinations: each must be refused before any GPU work."""
    image = Image.linear_gradient("L").resize((1024, 1024)).convert("RGB")
    source = report.upload("compat-source", png_bytes(image))
    mask = report.upload("compat-mask", box_mask((1024, 1024), [0.25, 0.25, 0.75, 0.75]), "mask")
    ref = [{"asset_id": source["id"], "slot": 1}]
    edit = {"task": "instruction_edit", "profile_id": "edit_v1", "references": ref}
    inpaint = {
        "task": "inpaint",
        "profile_id": "inpaint_v1",
        "references": ref,
        "mask_asset_id": mask["id"],
        "control": {"denoise": 0.65, "edge_softness": 0.15, "confirm_full": False},
    }
    control = {
        "task": "color_depth",
        "profile_id": "control_v1",
        "references": ref,
        "control": {
            "geometry": "mask",
            "strength": 1.0,
            "end_percent": 0.6,
            "depth_asset_id": None,
            "color_asset_id": None,
        },
    }
    lora = [{"artifact_id": "edit_sft", "strength": 1.0}]
    return [
        ("fast8_on_base", {"profile_id": "fast8_v1", "model_artifact_id": "base_bf16"}),
        ("fast8_with_negative", {"profile_id": "fast8_v1", "negative_prompt": "blurry"}),
        ("edit_on_base", {**edit, "model_artifact_id": "base_bf16"}),
        ("control_on_base", {**control, "model_artifact_id": "base_bf16"}),
        ("t2i_with_lora", {"lora_stack": lora}),
        ("edit_with_extra_lora", {**edit, "lora_stack": lora}),
        ("inpaint_with_lora", {**inpaint, "lora_stack": lora}),
        ("t2i_with_edit_profile", {"profile_id": "edit_v1"}),
        ("encoder_as_backbone", {"model_artifact_id": "qwen_int8"}),
        ("unknown_profile", {"profile_id": "turbo_v9"}),
    ]


def run_compat(report: BatchReport) -> None:
    results = {}
    for name, fields in compat_cases(report):
        payload = report.client.base_payload(
            report.project_id, f"compat/{name}/{new_id()}", prompt=PROMPT, **fields
        )
        status, body = report.client.probe("POST", "/api/jobs", payload)
        message = body.get("message", "")
        results[name] = {
            "status": status,
            "code": body.get("code"),
            "message": message,
            "refused_for_compatibility": status == 422
            and any(c in message for c in ("E_MODEL_INCOMPATIBLE", "E_CAPABILITY")),
        }
    report.data["compat"] = results
    report.data["compat_all_refused"] = all(r["status"] == 422 for r in results.values())
    report.save()


def wait_for_model(client: ProductClient, artifact_id: str, timeout: float = 2700) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = next(m for m in client.models()["models"] if m["id"] == artifact_id)
        if state["state"] in {"ready", "failed", "missing"}:
            return state
        time.sleep(15)
    raise TimeoutError(f"{artifact_id} 下載逾時；下載仍在背景進行，稍後重跑即可")


def busy_probes(report: BatchReport) -> dict:
    """While a job runs: switching and deleting files in use must all be refused (409)."""
    client = report.client
    job = client.submit(
        client.base_payload(
            report.project_id, f"busy/{new_id()}", **t2i(PROMPT, 1024, 83100, "fast8_v1")
        )
    )
    probes = {  # submit() returned, so the job is queued: the service already counts as busy
        "activate_base": client.probe("POST", "/api/models/activate", {"artifact_id": "base_bf16"}),
        "delete_active_sft": client.probe("DELETE", "/api/models/sft_bf16"),
        "delete_shared_encoder": client.probe("DELETE", "/api/models/qwen_int8"),
        "delete_edit_lora": client.probe("DELETE", "/api/models/edit_sft"),
    }
    finished = client.wait(job)
    expected = {
        "activate_base": "工作進行中",
        "delete_active_sft": "使用中的主模型",
        "delete_shared_encoder": "每個工作",
        "delete_edit_lora": "工作進行中",
    }
    result = {
        name: {"status": status, "message": body.get("message", "")}
        for name, (status, body) in probes.items()
    }
    for name, words in expected.items():
        result[name]["ok"] = result[name]["status"] == 409 and words in result[name]["message"]
    result["job_status"] = finished["status"]
    return result


def run_models(report: BatchReport) -> None:
    client = report.client
    models = report.data.setdefault("models", {})
    if "busy" not in models:
        # The probes below expect SFT active (it is the default; a crashed earlier run may not
        # have switched back).
        status, body = client.probe("POST", "/api/models/activate", {"artifact_id": "sft_bf16"})
        if status != 200:
            raise RuntimeError(f"無法先切回 SFT：{body}")
        models["busy"] = busy_probes(report)
        report.save()
    started = time.monotonic()
    base = wait_for_model(client, "base_bf16")
    models.setdefault(
        "base_download", {"state": base["state"], "waited_s": round(time.monotonic() - started)}
    )
    report.save()
    if base["state"] != "ready":
        raise RuntimeError("base_bf16 下載失敗，AC-13 無法進行")
    switches = models.setdefault("switches", [])
    for cycle in range(1, 4):
        for artifact in ("base_bf16", "sft_bf16"):
            key = f"{cycle}-{artifact}"
            done = report.entry("switch_jobs", key)
            if done and done["status"] == "succeeded":
                continue
            status, body = client.probe("POST", "/api/models/activate", {"artifact_id": artifact})
            active = client.session_info()["model_artifact_id"]
            switches.append({"key": key, "status": status, "active_after": active, "at": now()})
            report.save()
            if status != 200 or active != artifact:
                raise RuntimeError(f"切換到 {artifact} 失敗：{body}")
            report.run(
                "switch_jobs",
                key,
                lambda a=active, c=cycle: t2i(PROMPT, 1024, 83000 + c, model_artifact_id=a),
            )
    if "recovery" not in models:
        # Failure recovery: bad targets leave the last working backbone active, then free the
        # base file (allowed now: idle, not active) and show activation needs a ready file.
        probes = {
            "activate_encoder": client.probe(
                "POST", "/api/models/activate", {"artifact_id": "vae_small"}
            ),
            "activate_unknown": client.probe(
                "POST", "/api/models/activate", {"artifact_id": "nope"}
            ),
            "delete_base_idle": client.probe("DELETE", "/api/models/base_bf16"),
            "activate_deleted_base": client.probe(
                "POST", "/api/models/activate", {"artifact_id": "base_bf16"}
            ),
        }
        models["recovery"] = {
            name: {"status": status, "body": body} for name, (status, body) in probes.items()
        }
        models["recovery"]["active_after"] = client.session_info()["model_artifact_id"]
        report.save()
    report.run("switch_jobs", "after-recovery-sft", lambda: t2i(PROMPT, 1024, 83010))
    recovery = models["recovery"]
    models["passed"] = (
        all(p["ok"] for k, p in models["busy"].items() if k != "job_status")
        and len(
            [k for k, e in report.data.get("switch_jobs", {}).items() if e["status"] == "succeeded"]
        )
        == 7
        and recovery["activate_encoder"]["status"] == 422
        and recovery["activate_unknown"]["status"] == 422
        and recovery["delete_base_idle"]["status"] == 200
        and recovery["activate_deleted_base"]["status"] == 422
        and recovery["active_after"] == "sft_bf16"
    )
    report.save()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(client: ProductClient, project_id: str) -> dict:
    """Everything AC-15 compares: drafts (layout + settings) and every asset's bytes."""
    project = client.project(project_id)
    assets = {
        meta["id"]: {
            "kind": meta["kind"],
            "width": meta["width"],
            "height": meta["height"],
            "sha256": sha256(client.asset_bytes(project_id, meta["id"])),
        }
        for meta in client.assets(project_id)
    }
    return {"name": project["name"], "drafts": project["drafts"], "assets": assets}


def layout_case() -> tuple[dict, dict]:
    fixture = json.loads((REPOSITORY / "tests/fixtures/zh_tw_layouts.json").read_text("utf-8"))
    case = fixture["cases"][0]
    items = [{**item, "id": new_id(), "z_order": i} for i, item in enumerate(case["items"])]
    return case, {"items": items, "layout": compile_layout(case["caption"], items, 1024, 1024)}


def run_archive_export(destination: Path, client: ProductClient) -> None:
    """Builds a project with input, mask, layout, settings and outputs, then exports it."""
    report = BatchReport(destination / "ac15", client, "AC-15 匯出入")
    case, layout = layout_case()
    first = report.run(
        "jobs",
        "layout",
        lambda: {
            "task": "layout",
            "profile_id": "fast8_v1",
            "prompt": case["caption"],
            "width": 1024,
            "height": 1024,
            "seed": str(case["seed"]),
            "layout": layout["layout"],
        },
    )
    source = report.upload("source", report.output(first))
    mask = report.upload(
        "mask", box_mask(tuple(source["inpaint_size"]), [0.1, 0.55, 0.5, 0.95]), "mask"
    )
    inpaint_prompt = "一隻白色小貓坐在草地上"
    if "drafts_saved" not in report.data:
        client.save_draft(
            report.project_id,
            "t2i",
            {
                "prompt": case["caption"],
                "negative": "",
                "width": 1024,
                "height": 1024,
                "seed": str(case["seed"]),
                "layout_enabled": True,
                "profile_id": "fast8_v1",
                "layout_items": layout["items"],
                "layout_caption": None,
                "layout_meta": None,
            },
        )
        client.save_draft(
            report.project_id,
            "inpaint",
            {
                "source": {
                    "asset_id": source["id"],
                    "width": source["width"],
                    "height": source["height"],
                    "inpaint_size": source["inpaint_size"],
                },
                "prompt": inpaint_prompt,
                "negative": "",
                "seed": "84001",
                "denoise": 0.8,
                "edge_softness": 0.15,
                "mask_asset_id": mask["id"],
            },
        )
        report.data["drafts_saved"] = True
        report.save()
    report.run("jobs", "inpaint", lambda: inpaint_fields(source, mask, inpaint_prompt, 84001))
    archive = client.export_project(report.project_id)
    (report.destination / "ac15-project.zip").write_bytes(archive)
    manifest = {
        "exported_at": now(),
        "project_id": report.project_id,
        "archive_sha256": sha256(archive),
        "archive_bytes": len(archive),
        **snapshot(client, report.project_id),
    }
    (report.destination / "ac15_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report.data["exported"] = {k: manifest[k] for k in ("archive_sha256", "archive_bytes")}
    report.save()


def inpaint_fields(source: dict, mask: dict, prompt: str, seed: int) -> dict:
    width, height = source["inpaint_size"]
    return {
        "task": "inpaint",
        "profile_id": "inpaint_v1",
        "prompt": prompt,
        "width": width,
        "height": height,
        "seed": str(seed),
        "references": [{"asset_id": source["id"], "slot": 1}],
        "mask_asset_id": mask["id"],
        "control": {"denoise": 0.8, "edge_softness": 0.15, "confirm_full": False},
    }


def run_archive_import(destination: Path, client: ProductClient, archive: Path, manifest: Path):
    """New VM: import, compare hashes and drafts, then keep editing the imported project."""
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if (Path(destination) / "report.json").exists():  # resumed: the import already happened
        report = BatchReport(destination, client, "")
    else:
        data = archive.read_bytes()
        if sha256(data) != expected["archive_sha256"]:
            raise RuntimeError("專案檔與 manifest 不符（傳輸損壞？）")
        imported = client.import_project(data)["id"]
        report = BatchReport(destination, client, "", project_id=imported)
        report.data["archive_sha256"] = expected["archive_sha256"]
    got = snapshot(client, report.project_id)
    if "comparison" not in report.data:
        # Compared once, straight after import: the continued jobs below add new outputs.
        report.data["comparison"] = {
            "assets_identical": got["assets"] == expected["assets"],
            "drafts_identical": got["drafts"] == expected["drafts"],
            "asset_count": len(got["assets"]),
            "new_project_id": report.project_id != expected["project_id"],
        }
        report.save()
    inpaint = got["drafts"]["inpaint"]
    source = {**inpaint["source"], "id": inpaint["source"]["asset_id"]}
    mask = {"id": inpaint["mask_asset_id"]}
    report.run(
        "continued",
        "inpaint",
        lambda: inpaint_fields(source, mask, "一隻黑色小狗坐在草地上", 84002),
    )
    t2i_draft = got["drafts"]["t2i"]
    report.run(
        "continued",
        "t2i",
        lambda: t2i(t2i_draft["prompt"], 1024, 84003, t2i_draft["profile_id"]),
    )
    report.data["passed"] = all(
        report.data["comparison"][k]
        for k in ("assets_identical", "drafts_identical", "new_project_id")
    ) and all(e["status"] == "succeeded" for e in report.data["continued"].values())
    report.save()
    return report.data


def run(destination: Path, sections: set[str], base_url: str) -> dict:
    with ProductClient(base_url) as client:
        report = BatchReport(destination, client, "GPU 批次 D")
        if "models" in sections and not report.data.get("models", {}).get("passed"):
            # Start the ~10 GB base download now so it overlaps the long high-resolution jobs.
            status, body = client.probe("POST", "/api/models/base_bf16/download")
            report.data["base_download_request"] = {"status": status, "body": body}
            report.save()
        if "compat" in sections:
            run_compat(report)
        if "native" in sections:
            run_native(report, "native", 1456, range(81001, 81004), timeout=1800)
        if "upscale" in sections:
            run_upscale(report)
        if "models" in sections:
            run_models(report)
        if "archive" in sections:
            run_archive_export(destination, client)
        if "native2048" in sections:
            run_native(report, "native2048", 2048, range(82001, 82004), timeout=3600)
        report.data["summary"] = {
            section: {
                "succeeded": sum(
                    e["status"] == "succeeded" and e.get("nonblack", False)
                    for e in report.data.get(section, {}).values()
                ),
                "seconds": [e.get("seconds") for e in report.data.get(section, {}).values()],
                "gpu_peak_mib": [
                    e.get("gpu_peak_mib") for e in report.data.get(section, {}).values()
                ],
            }
            for section in ("native", "upscale", "switch_jobs", "native2048")
        }
        report.save()
        return report.data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU 批次 D：高解析、模型切換、相容性、專案匯出入")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", nargs="+", choices=SECTIONS, default=list(SECTIONS))
    parser.add_argument("--import", dest="archive", type=Path, help="AC-15：在新 VM 匯入的專案 ZIP")
    parser.add_argument("--manifest", type=Path, help="AC-15：匯出時寫下的 ac15_manifest.json")
    # Another loopback port targets the fake-engine dev server for a dry run of this script;
    # such a run is never GPU evidence.
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    args = parser.parse_args()
    if args.archive:
        if not args.manifest:
            parser.error("--import 需要同時提供 --manifest")
        with ProductClient(args.base_url) as product:
            outcome = run_archive_import(args.destination, product, args.archive, args.manifest)
        print(
            json.dumps(
                {"comparison": outcome["comparison"], "passed": outcome["passed"]},
                ensure_ascii=False,
            )
        )
    else:
        outcome = run(args.destination, set(args.only), args.base_url)
        print(
            json.dumps(
                {
                    "summary": outcome["summary"],
                    "compat_all_refused": outcome.get("compat_all_refused"),
                    "models_passed": outcome.get("models", {}).get("passed"),
                },
                ensure_ascii=False,
            )
        )
