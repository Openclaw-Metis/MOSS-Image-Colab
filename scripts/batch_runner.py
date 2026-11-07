"""Checkpointed case runner shared by the GPU batch scripts.

The exact payload is stored before it is submitted: a rerun after a Colab hiccup resends the
same snapshot (same request id and project revision), so the server returns the original job
instead of creating a second one. Uploads are cached the same way. A case whose job failed is
retried under a new attempt number, never by resending the failed request.
"""

import hashlib
import io
import json
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from moss_studio.domain.contracts import now
from moss_studio.storage.atomic import atomic_json

REPOSITORY = Path(__file__).resolve().parents[1]


def default_negative(profile_id: str) -> str:
    name = profile_id.removesuffix("_v1")
    profile = json.loads((REPOSITORY / f"configs/profiles/{name}.json").read_text("utf-8"))
    return profile.get("default_negative_prompt", "")


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class GpuPeak:
    """Samples device memory.used via nvidia-smi while a job runs (ComfyUI is another process).

    This is what the whole GPU holds, allocator cache included, i.e. the number that decides OOM.
    Without nvidia-smi (fake-engine dry runs) the peak stays None.
    """

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.peak_mib: int | None = None
        self.available = shutil.which("nvidia-smi") is not None
        self.stop = threading.Event()

    def _sample(self) -> None:
        while not self.stop.is_set():
            try:
                value = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                ).stdout.split()[0]
                self.peak_mib = max(self.peak_mib or 0, int(value))
            except (subprocess.SubprocessError, OSError, ValueError, IndexError):
                pass
            self.stop.wait(self.interval)

    def __enter__(self):
        if self.available:
            self.thread = threading.Thread(target=self._sample, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.available:
            self.thread.join(timeout=15)


class BatchReport:
    def __init__(
        self,
        destination: Path,
        client,
        name: str,
        fixture: Path | None = None,
        project_id: str | None = None,
    ):
        self.destination = Path(destination)
        self.destination.mkdir(parents=True, exist_ok=True)
        self.path = self.destination / "report.json"
        self.client = client
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            # project_id adopts an existing project (e.g. one just imported on a new VM).
            project_id = project_id or client.create_project(name)["id"]
            self.data = {
                "schema_version": 1,
                "created_at": now(),
                "project_id": project_id,
                "runtime": client.runtime(),
                "payloads": {},
                "uploads": {},
            }
            if fixture:
                self.data["fixture_sha256"] = hashlib.sha256(Path(fixture).read_bytes()).hexdigest()
            self.save()

    @property
    def project_id(self) -> str:
        return self.data["project_id"]

    def save(self) -> None:
        atomic_json(self.path, self.data)

    def entry(self, section: str, key: str) -> dict | None:
        return self.data.setdefault(section, {}).get(key)

    def upload(self, key: str, data: bytes, kind: str = "input") -> dict:
        cached = self.data["uploads"].get(key)
        if cached:
            return cached
        meta = self.client.upload(self.project_id, data, kind)
        self.data["uploads"][key] = meta
        self.save()
        return meta

    def run(
        self, section: str, key: str, fields: Callable[[], dict], *, timeout: float = 1200
    ) -> dict:
        """Submit (or find) one job, store its output PNG and checkpoint the report."""
        previous = self.entry(section, key)
        if previous and previous["status"] == "succeeded":
            return previous
        attempt = previous["attempt"] + 1 if previous else 1
        tag = f"{section}/{key}#{attempt}"
        payload = self.data["payloads"].get(tag)
        if payload is None:
            payload = self.client.base_payload(self.project_id, tag, **fields())
            self.data["payloads"][tag] = payload
            self.save()
        with GpuPeak() as gpu:
            job = self.client.wait(self.client.submit(payload), timeout=timeout)
        entry = {
            "status": job["status"],
            "attempt": attempt,
            "job_id": job["id"],
            "seed": job["seed"],
        }
        entry["model_artifact_id"] = payload["model_artifact_id"]
        entry["gpu_peak_mib"] = gpu.peak_mib
        if job["status"] == "succeeded":
            record = job["record"]
            data, facts = self.client.download_output(job)
            name = f"{section}-{key}.png"
            (self.destination / name).write_bytes(data)
            entry.update(facts, output_file=name, output_asset=record["output_assets"][0])
            entry["seconds"] = round(record["seconds"], 2)
            for index, asset in enumerate(record.get("auxiliary_assets", [])):
                aux = f"{section}-{key}-aux{index}.png"
                (self.destination / aux).write_bytes(
                    self.client.asset_bytes(self.project_id, asset)
                )
                entry.setdefault("auxiliary_files", []).append(aux)
            for field in ("feather_px", "passes", "postprocess", "workflow_hash"):
                if field in record:
                    entry[field] = record[field]
        self.data[section][key] = entry
        self.save()
        print(
            json.dumps({"section": section, "case": key, **entry}, ensure_ascii=False), flush=True
        )
        return entry

    def output(self, entry: dict) -> bytes:
        return (self.destination / entry["output_file"]).read_bytes()
