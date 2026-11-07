"""AC-19: run the fixed Traditional Chinese layout cases through the product API.

Usage on the L4 runtime (app already running on 127.0.0.1:7860):
    MOSS_STUDIO_PASSWORD=... python scripts/zh_tw_layout_eval.py <evidence-dir>

Writes report.json (checkpointed after each case), case PNGs and scoring.json. The script
never scores glyph accuracy itself: scoring.json is filled in by a person (OCR may assist)
against the criteria frozen in tests/fixtures/zh_tw_layouts.json.
"""

import hashlib
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from product_client import ProductClient  # noqa: E402

from moss_studio.domain.contracts import new_id, now  # noqa: E402
from moss_studio.domain.layout import compile_layout  # noqa: E402
from moss_studio.storage.atomic import atomic_json  # noqa: E402

FIXTURE = REPOSITORY / "tests/fixtures/zh_tw_layouts.json"


def case_layout(case: dict) -> dict:
    items = [{**item, "id": new_id(), "z_order": index} for index, item in enumerate(case["items"])]
    return compile_layout(case["caption"], items, case["width"], case["height"])


def run(destination: Path, base_url: str = "http://127.0.0.1:7860") -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "report.json"
    with ProductClient(base_url) as client:
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
        else:
            project = client.create_project("AC-19 繁中排版")
            report = {
                "schema_version": 1,
                "created_at": now(),
                "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                "project_id": project["id"],
                "runtime": client.runtime(),
                "profile_id": fixture["profile_id"],
                "samples": {},
                "payloads": {},
            }
            atomic_json(report_path, report)
        for case in fixture["cases"]:
            sample = report["samples"].get(case["id"])
            if sample and sample["status"] == "succeeded":
                continue
            project = client.project(report["project_id"])
            payload = report["payloads"].setdefault(
                case["id"],
                {
                    "project_id": project["id"],
                    "client_request_id": client.request_id(project["id"], case["id"]),
                    "project_revision": project["revision"],
                    "task": "layout",
                    "profile_id": fixture["profile_id"],
                    "model_artifact_id": "sft_bf16",
                    "prompt": case["caption"],
                    "negative_prompt": "",
                    "width": case["width"],
                    "height": case["height"],
                    "seed": str(case["seed"]),
                    "references": [],
                    "layout": case_layout(case),
                    "mask_asset_id": None,
                    "control": None,
                    "lora_stack": [],
                },
            )
            atomic_json(report_path, report)
            job = client.wait(client.submit(payload))
            sample = {"status": job["status"], "job_id": job["id"], "seed": job["seed"]}
            if job["status"] == "succeeded":
                data, facts = client.download_output(job)
                output = f"{case['id']}.png"
                (destination / output).write_bytes(data)
                sample.update(facts, output_file=output, seconds=job["record"]["seconds"])
            report["samples"][case["id"]] = sample
            atomic_json(report_path, report)
            print(json.dumps({"case": case["id"], **sample}, ensure_ascii=False), flush=True)
        scoring_path = destination / "scoring.json"
        if not scoring_path.exists():
            atomic_json(
                scoring_path,
                {
                    "criteria": fixture["scoring"],
                    "cases": {
                        case["id"]: {
                            "expected_text": [i["text"] for i in case["items"] if "text" in i],
                            "features": case["features"],
                            "title_exact": None,
                            "all_text_exact": None,
                            "title_region_ok": None,
                            "features_met": None,
                            "notes": "",
                        }
                        for case in fixture["cases"]
                    },
                },
            )
        report["generated_all"] = all(
            report["samples"].get(c["id"], {}).get("status") == "succeeded"
            for c in fixture["cases"]
        )
        atomic_json(report_path, report)
        return report


if __name__ == "__main__":
    # Optional second argument targets another loopback port (e.g. the fake-engine dev server
    # for a dry run of this script; such a run is never AC-19 evidence).
    run(Path(sys.argv[1]), *sys.argv[2:3])
