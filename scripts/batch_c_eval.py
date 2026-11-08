"""GPU batch C: AC-08 instruction edit, AC-09 inpaint, AC-11 colour/depth control, AC-10 vision.

Usage on the L4 runtime (app already running on 127.0.0.1:7860):
    MOSS_STUDIO_PASSWORD=... python scripts/batch_c_eval.py <evidence-dir> [--only edit ...]

Source images are generated in the same session with fast8 (no real photos, no licensing
questions), downloaded and uploaded again as ordinary input assets, exactly as a user would.
report.json is checkpointed after every case. scoring.json is filled in by a person against the
features frozen in tests/fixtures/batch_c_cases.json; only the AC-09 pixel preservation outside
the feathered band is measured here, because it is an exact check.
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

from batch_runner import BatchReport, default_negative, png_bytes  # noqa: E402
from product_client import ProductClient  # noqa: E402

from moss_studio.domain.masks import binary_mask, feather_radius, feathered_alpha  # noqa: E402

FIXTURE = REPOSITORY / "tests/fixtures/batch_c_cases.json"
SECTIONS = ("edit", "inpaint", "control", "control_off", "vision", "vision_off")
EDGE_SOFTNESS = 0.15  # inpaint_v1 default, i.e. what a user gets without touching the slider
# Two flat regions for the colour-map case; any distinct colours work, they are region IDs.
COLOR_SPLIT = ((40, 90, 200), (230, 120, 30))


def refs(fixtures: dict, names: list[str]) -> list[dict]:
    return [{"asset_id": fixtures[n]["id"], "slot": i} for i, n in enumerate(names, start=1)]


def make_fixtures(report: BatchReport, cases: dict) -> dict:
    fixtures = {}
    for fixture in cases["fixtures"]:
        entry = report.run(
            "fixtures",
            fixture["id"],
            lambda f=fixture: {
                "profile_id": "fast8_v1",
                "prompt": f["prompt"],
                "width": f["width"],
                "height": f["height"],
                "seed": str(f["seed"]),
            },
        )
        if entry["status"] != "succeeded":
            raise RuntimeError(f"來源圖 {fixture['id']} 生成失敗，後續案例無法進行")
        fixtures[fixture["id"]] = report.upload(f"fixture-{fixture['id']}", report.output(entry))
    return fixtures


def box_mask(size: tuple[int, int], box: list[float]) -> bytes:
    width, height = size
    image = Image.new("L", size, 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(image).rectangle(
        (round(x0 * width), round(y0 * height), round(x1 * width) - 1, round(y1 * height) - 1),
        fill=255,
    )
    return png_bytes(image)


def preservation(source: bytes, output: bytes, mask: bytes, size: tuple[int, int]) -> dict:
    """Recomputes the service's feather support and compares pixels outside it exactly."""
    with Image.open(io.BytesIO(source)) as image:
        original = np.asarray(image.convert("RGB").resize(size, Image.Resampling.LANCZOS))
    with Image.open(io.BytesIO(output)) as image:
        produced = np.asarray(image.convert("RGB"))
    with Image.open(io.BytesIO(mask)) as image:
        selected = binary_mask(image)
    radius = feather_radius(*size, EDGE_SOFTNESS)
    outside = feathered_alpha(selected, radius) == 0
    identical = (original == produced).all(axis=2)
    difference = np.abs(original.astype(np.int16) - produced.astype(np.int16)).mean(axis=2)
    return {
        "feather_px": radius,
        "outside_pixels": int(outside.sum()),
        "outside_identical_ratio": float(identical[outside].mean()),
        "inside_mean_abs_diff": round(float(difference[selected].mean()), 3),
    }


def run_inpaint(report: BatchReport, cases: dict, fixtures: dict) -> None:
    for case in cases["inpaint"]:
        source = fixtures[case["source"]]
        size = tuple(source["inpaint_size"])
        mask_bytes = box_mask(size, case["box"])
        mask = report.upload(f"mask-{case['id']}", mask_bytes, "mask")
        entry = report.run(
            "inpaint",
            case["id"],
            lambda c=case, s=source, m=mask, size=size: {
                "task": "inpaint",
                "profile_id": "inpaint_v1",
                "prompt": c["prompt"],
                "negative_prompt": default_negative("inpaint_v1"),
                "width": size[0],
                "height": size[1],
                "seed": str(c["seed"]),
                "references": [{"asset_id": s["id"], "slot": 1}],
                "mask_asset_id": m["id"],
                "control": {
                    "denoise": c["denoise"],
                    "edge_softness": EDGE_SOFTNESS,
                    "confirm_full": False,
                },
            },
        )
        if entry["status"] == "succeeded" and "preservation" not in entry:
            source_bytes = report.client.asset_bytes(report.project_id, source["id"])
            entry["preservation"] = preservation(
                source_bytes, report.output(entry), mask_bytes, size
            )
            (report.destination / f"inpaint-{case['id']}-mask.png").write_bytes(mask_bytes)
            report.save()


def control_fields(report: BatchReport, case: dict, fixtures: dict) -> dict:
    source = fixtures[case["source"]]
    width, height = source["inpaint_size"]  # control_v1 shares the 1 MP / 16 px working size
    color = None
    if case.get("color_split"):
        image = Image.new("RGB", (width, height), COLOR_SPLIT[0])
        image.paste(COLOR_SPLIT[1], (width // 2, 0, width, height))
        color = report.upload(f"color-{case['id']}", png_bytes(image), "control")["id"]
    return {
        "task": "color_depth",
        "profile_id": "control_v1",
        "prompt": case["prompt"],
        "negative_prompt": default_negative("control_v1"),
        "width": width,
        "height": height,
        "seed": str(case["seed"]),
        "references": [{"asset_id": source["id"], "slot": 1}],
        "control": {
            "geometry": case["geometry"],
            "strength": 1.0,
            "end_percent": 0.6,
            "depth_asset_id": None,
            "color_asset_id": color,
        },
    }


def off_fields(fields: dict) -> dict:
    """Same prompt, seed and size as plain quality50 text-to-image: what the control adds."""
    return {
        "profile_id": "quality50_v1",
        **{k: fields[k] for k in ("prompt", "negative_prompt", "width", "height", "seed")},
    }


def vision_fields(case: dict, fixtures: dict) -> dict:
    return {
        "task": "vision",
        "profile_id": "vision_v1",
        "prompt": case["prompt"],
        "width": case["width"],
        "height": case["height"],
        "seed": str(case["seed"]),
        "references": refs(fixtures, case["refs"]),
        "control": {"image_strength": 1.0},
    }


def scoring_template(cases: dict) -> dict:
    def blank(case: dict, **extra) -> dict:
        return {
            "features": case["features"],
            "features_met": None,
            "severe_artifact": None,
            **extra,
            "notes": "",
        }

    return {
        "criteria": cases["scoring"],
        "edit": {c["id"]: blank(c, refs=c["refs"], mapping_ok=None) for c in cases["edit"]},
        "inpaint": {c["id"]: blank(c) for c in cases["inpaint"]},
        "control": {
            c["id"]: blank(c, differs_from_off=None if c["id"] in cases["control_off"] else "n/a")
            for c in cases["control"]
        },
        "vision": {c["id"]: blank(c, differs_from_off=None) for c in cases["vision"]},
    }


def retest_cases(cases: dict, only: set[str] | None, inpaint_denoise: float | None) -> dict:
    """Re-run frozen cases after a recipe fix: same prompts, seeds and features, fewer cases."""
    known = {c["id"] for s in ("edit", "inpaint", "control", "vision") for c in cases[s]}
    if only:
        if only - known:
            raise SystemExit(f"未知案例：{sorted(only - known)}")
        for section in ("edit", "inpaint", "control", "vision"):
            cases[section] = [c for c in cases[section] if c["id"] in only]
        cases["control_off"] = [c for c in cases["control_off"] if c in only]
    if inpaint_denoise is not None:
        for case in cases["inpaint"]:
            case["denoise"] = inpaint_denoise
    return cases


def run(
    destination: Path,
    sections: set[str],
    base_url: str,
    only: set[str] | None = None,
    inpaint_denoise: float | None = None,
) -> dict:
    cases = retest_cases(json.loads(FIXTURE.read_text(encoding="utf-8")), only, inpaint_denoise)
    with ProductClient(base_url) as client:
        report = BatchReport(destination, client, "GPU 批次 C", FIXTURE)
        if only or inpaint_denoise is not None:
            report.data["retest"] = {
                "cases": sorted(only or []),
                "inpaint_denoise": inpaint_denoise,
            }
            report.save()
        fixtures = make_fixtures(report, cases)
        if "edit" in sections:
            for case in cases["edit"]:
                first = fixtures[case["refs"][0]]
                report.run(
                    "edit",
                    case["id"],
                    lambda c=case, f=first: {
                        "task": "instruction_edit",
                        "profile_id": "edit_v1",
                        "prompt": c["prompt"],
                        "negative_prompt": default_negative("edit_v1"),
                        "width": f["edit_size"][0],
                        "height": f["edit_size"][1],
                        "seed": str(c["seed"]),
                        "references": refs(fixtures, c["refs"]),
                    },
                )
        if "inpaint" in sections:
            run_inpaint(report, cases, fixtures)
        control = {case["id"]: case for case in cases["control"]}
        if "control" in sections:
            for case in cases["control"]:
                report.run(
                    "control", case["id"], lambda c=case: control_fields(report, c, fixtures)
                )
        if "control_off" in sections:
            for case_id in cases["control_off"]:
                case = control[case_id]
                report.run(
                    "control_off",
                    case_id,
                    lambda c=case: off_fields(control_fields(report, c, fixtures)),
                )
        for case in cases["vision"]:
            fields = vision_fields(case, fixtures)
            fields["negative_prompt"] = default_negative("vision_v1")
            if "vision" in sections:
                report.run("vision", case["id"], lambda f=fields: f)
            if "vision_off" in sections:
                report.run("vision_off", case["id"], lambda f=fields: off_fields(f))
        scoring_path = destination / "scoring.json"
        if not scoring_path.exists():
            scoring_path.write_text(
                json.dumps(scoring_template(cases), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        expected = {
            "fixtures": [f["id"] for f in cases["fixtures"]],
            "edit": [c["id"] for c in cases["edit"]],
            "inpaint": [c["id"] for c in cases["inpaint"]],
            "control": list(control),
            "control_off": cases["control_off"],
            "vision": [c["id"] for c in cases["vision"]],
            "vision_off": [c["id"] for c in cases["vision"]],
        }
        report.data["summary"] = {
            section: sum(
                report.data.get(section, {}).get(k, {}).get("status") == "succeeded"
                and report.data[section][k].get("nonblack", False)
                for k in keys
            )
            for section, keys in expected.items()
        }
        report.data["generated_all"] = all(
            report.data["summary"][s] == len(k) for s, k in expected.items()
        )
        preserved = [
            e.get("preservation", {}).get("outside_identical_ratio")
            for e in report.data.get("inpaint", {}).values()
        ]
        report.data["inpaint_outside_exact"] = bool(preserved) and all(p == 1.0 for p in preserved)
        report.save()
        return report.data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU 批次 C：修圖、重繪、控制、視覺參考")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", nargs="+", choices=SECTIONS, default=list(SECTIONS))
    # Another loopback port targets the fake-engine dev server for a dry run of this script;
    # such a run is never GPU evidence.
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument("--cases", nargs="+", help="只重跑這些案例 id（修正後重測用）")
    parser.add_argument("--inpaint-denoise", type=float, help="重測時覆寫重繪強度")
    args = parser.parse_args()
    result = run(
        args.destination,
        set(args.only),
        args.base_url,
        set(args.cases) if args.cases else None,
        args.inpaint_denoise,
    )
    print(
        json.dumps(
            {
                "summary": result["summary"],
                "generated_all": result["generated_all"],
                "inpaint_outside_exact": result["inpaint_outside_exact"],
            },
            ensure_ascii=False,
        )
    )
