"""Loopback client for evaluation scripts that drive the product API on the L4 runtime.

Password comes from the current process environment only (never argv, reports or projects).
Reports are checkpointed after every job so a recycled Colab VM loses at most one sample.
"""

import hashlib
import io
import os
import time
from uuid import NAMESPACE_URL, uuid5

import httpx
from PIL import Image, ImageStat

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


class ProductClient:
    def __init__(self, base_url: str = "http://127.0.0.1:7860"):
        if not base_url.startswith("http://127.0.0.1:"):
            raise ValueError("evaluation only talks to the numeric loopback app")
        self.http = httpx.Client(base_url=base_url, trust_env=False, timeout=30)

    def __enter__(self):
        password = os.environ.pop("MOSS_STUDIO_PASSWORD")
        response = self.http.post("/login", data={"password": password})
        if response.status_code != 303:
            raise RuntimeError("Evaluation authentication failed")
        # The tunnel cookie is Secure; send it explicitly only on this loopback client.
        self.http.headers["Cookie"] = "moss_session=" + response.cookies["moss_session"]
        self.session = self.http.get("/api/session").json()
        self.http.headers["X-Moss-CSRF"] = self.session["csrf"]
        return self

    def __exit__(self, *exc):
        self.http.close()

    def runtime(self) -> dict:
        return self.http.get("/api/runtime").json()

    def create_project(self, name: str) -> dict:
        response = self.http.post("/api/projects", json={"name": name})
        response.raise_for_status()
        return response.json()

    def project(self, project_id: str) -> dict:
        response = self.http.get(f"/api/projects/{project_id}")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def request_id(project_id: str, key: str) -> str:
        # Deterministic per case so a resumed run finds the original job instead of resubmitting.
        return str(uuid5(NAMESPACE_URL, f"{project_id}/{key}"))

    def submit(self, payload: dict) -> str:
        response = self.http.post("/api/jobs", json=payload)
        if response.is_error:
            # Keep the service's own reason (e.g. which node input failed) in the batch log.
            raise RuntimeError(f"提交被拒（HTTP {response.status_code}）：{response.text[:500]}")
        return response.json()["id"]

    def wait(self, job_id: str, timeout: float = 1200) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.http.get(f"/api/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job["status"] in TERMINAL:
                return job
            time.sleep(1)
        raise TimeoutError("Job still running; inspect it before retrying, never resubmit")

    def upload(self, project_id: str, data: bytes, kind: str = "input") -> dict:
        response = self.http.post(
            f"/api/projects/{project_id}/assets",
            params={"kind": kind},
            content=data,
            headers={"Content-Type": "image/png"},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def asset_bytes(self, project_id: str, asset_id: str) -> bytes:
        response = self.http.get(f"/api/assets/{project_id}/{asset_id}", timeout=120)
        response.raise_for_status()
        return response.content

    def base_payload(self, project_id: str, key: str, **fields) -> dict:
        """JobSpec with deterministic request id; callers fill task-specific fields."""
        project = self.project(project_id)
        payload = {
            "project_id": project_id,
            "client_request_id": self.request_id(project_id, key),
            "project_revision": project["revision"],
            "task": "t2i",
            "profile_id": "quality50_v1",
            "model_artifact_id": "sft_bf16",
            "prompt": "",
            "negative_prompt": "",
            "width": 1024,
            "height": 1024,
            "seed": "1",
            "references": [],
            "layout": None,
            "mask_asset_id": None,
            "control": None,
            "lora_stack": [],
        }
        payload.update(fields)
        return payload

    def models(self) -> dict:
        response = self.http.get("/api/models")
        response.raise_for_status()
        return response.json()

    def session_info(self) -> dict:
        return self.http.get("/api/session").json()

    def probe(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """Raw call for negative tests: returns status and body instead of raising."""
        response = self.http.request(method, path, json=body, timeout=120)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def save_draft(self, project_id: str, tab: str, draft: dict) -> dict:
        revision = self.project(project_id)["revision"]
        response = self.http.put(
            f"/api/projects/{project_id}/draft",
            json={"draft": draft, "expected_revision": revision, "tab": tab},
        )
        response.raise_for_status()
        return response.json()

    def export_project(self, project_id: str) -> bytes:
        response = self.http.get(f"/api/projects/{project_id}/export", timeout=600)
        response.raise_for_status()
        return response.content

    def import_project(self, data: bytes) -> dict:
        response = self.http.post(
            "/api/projects/import",
            content=data,
            headers={"Content-Type": "application/zip"},
            timeout=600,
        )
        response.raise_for_status()
        return response.json()

    def assets(self, project_id: str) -> list[dict]:
        response = self.http.get(f"/api/projects/{project_id}/assets")
        response.raise_for_status()
        return response.json()

    def download_output(self, job: dict) -> tuple[bytes, dict]:
        asset = job["record"]["output_assets"][0]
        response = self.http.get(f"/api/assets/{job['project_id']}/{asset}")
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        stats = ImageStat.Stat(image)
        facts = {
            "output_sha256": hashlib.sha256(response.content).hexdigest(),
            "size": list(image.size),
            "nonblack": max(image.getextrema()[c][1] for c in range(3)) > 8
            and max(stats.stddev) > 1,
        }
        return response.content, facts
