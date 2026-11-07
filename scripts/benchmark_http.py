"""Run an explicit long GPU baseline through the product API, checkpointing each result.

Only numeric loopback is accepted. Password comes from the current process environment,
never argv, a report, or a project. Keep the product UI idle during this benchmark.
"""

import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from PIL import Image, ImageStat

from moss_studio.domain.contracts import now
from moss_studio.storage.atomic import atomic_json


def benchmark(destination: Path, *, count: int = 5, profile: str = "quality50_v1") -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "benchmark.json"
    with httpx.Client(base_url="http://127.0.0.1:7860", trust_env=False, timeout=30) as client:
        password = os.environ.pop("MOSS_STUDIO_PASSWORD")
        response = client.post("/login", data={"password": password})
        if response.status_code != 303:
            raise RuntimeError("Benchmark authentication failed")
        # The public HTTPS cookie is correctly Secure. Explicitly use it only on this
        # trusted loopback test client; browser behavior is tested on the real tunnel.
        client.headers["Cookie"] = "moss_session=" + response.cookies["moss_session"]
        session = client.get("/api/session").json()
        client.headers["X-Moss-CSRF"] = session["csrf"]
        if report_path.exists():
            report = json.loads(report_path.read_text())
        else:
            response = client.post("/api/projects", json={"name": "Stage 2 固定 GPU 基準"})
            response.raise_for_status()
            report = {
                "schema_version": 1,
                "created_at": now(),
                "project_id": response.json()["id"],
                "runtime": client.get("/api/runtime").json(),
                "profile_id": profile,
                "warmup_count": 1,
                "measured_count": count,
                "model_pins": json.loads(
                    (Path(__file__).resolve().parents[1] / "configs/models.lock.json").read_text()
                ),
                "samples": [],
            }
            atomic_json(report_path, report)
        for index in range(count + 1):
            if any(s["index"] == index and s["status"] == "succeeded" for s in report["samples"]):
                continue
            project = client.get(f"/api/projects/{report['project_id']}").json()
            payload = {
                "project_id": project["id"],
                "client_request_id": str(uuid5(NAMESPACE_URL, project["id"] + f"/{index}")),
                "project_revision": project["revision"],
                "task": "t2i",
                "profile_id": profile,
                "model_artifact_id": "sft_bf16",
                "prompt": "一隻橘貓坐在窗邊木桌上，旁邊一盆綠色植物，午後暖陽，細緻攝影",
                "negative_prompt": "",
                "width": 1024,
                "height": 1024,
                "seed": str(52001 + index),
                "references": [],
                "layout": None,
                "mask_asset_id": None,
                "control": None,
                "lora_stack": [],
            }
            submissions = report.setdefault("submissions", {})
            payload = submissions.setdefault(str(index), payload)
            atomic_json(report_path, report)
            response = client.post("/api/jobs", json=payload)
            response.raise_for_status()
            job_id = response.json()["id"]
            sample = {"index": index, "warmup": index == 0, "job_id": job_id, "status": "running"}
            report["samples"] = [s for s in report["samples"] if s["index"] != index] + [sample]
            atomic_json(report_path, report)
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                response = client.get(f"/api/jobs/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
                    break
                time.sleep(1)
            else:
                raise TimeoutError(
                    "Benchmark left the original job intact; inspect before retrying"
                )
            sample.update(status=job["status"], seed=job["seed"])
            if job["status"] == "succeeded":
                asset = job["record"]["output_assets"][0]
                response = client.get(f"/api/assets/{project['id']}/{asset}")
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content)).convert("RGB")
                stats = ImageStat.Stat(image)
                sample.update(
                    record=job["record"],
                    output_sha256=hashlib.sha256(response.content).hexdigest(),
                    size=list(image.size),
                    channel_stddev=stats.stddev,
                    nonblack=max(image.getextrema()[channel][1] for channel in range(3)) > 8
                    and max(stats.stddev) > 1,
                    output_file=f"sample-{index}.png",
                )
                (destination / sample["output_file"]).write_bytes(response.content)
            atomic_json(report_path, report)
            print(json.dumps({k: sample[k] for k in ("index", "status", "seed")}), flush=True)
            if sample["status"] != "succeeded" or not sample.get("nonblack"):
                raise RuntimeError("Real baseline failed; evidence retained")
        report["passed"] = len(report["samples"]) == count + 1 and all(
            s["status"] == "succeeded" and s.get("nonblack") and s.get("size") == [1024, 1024]
            for s in report["samples"]
        )
        atomic_json(report_path, report)
        return report


if __name__ == "__main__":
    benchmark(Path(sys.argv[1]))
