"""Local UI development server with a fake engine. Proves UI/API wiring only, never GPU work.

Run from the repository root:
    python scripts/dev_server.py --data-root .runtime/dev --port 7861

The fake engine accepts every node class, simulates sampling progress and returns a
placeholder PNG at the requested size. Images are labelled so they cannot be mistaken for
model output, and nothing here may be cited as GPU, quality or tunnel evidence.
"""

import argparse
import hashlib
import io
import os
import secrets
import sys
import threading
import time
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from moss_studio.adapters.comfy import EngineSettledError  # noqa: E402


class AnyNodes(dict):
    """object_info stand-in: every node exists and declares no required inputs."""

    def get(self, key, default=None):
        return {"input": {"required": {}}}


class FakeEngine:
    def __init__(self):
        self.cancelled = set()
        self.uploaded = {}
        self.lock = threading.Lock()

    def object_info(self):
        return AnyNodes()

    def upload_image(self, name, data):
        with Image.open(io.BytesIO(data)) as image:
            self.uploaded[name] = image.size
        return name

    def cancel_owned(self, prompt_id, *, exclusive_engine):
        with self.lock:
            self.cancelled.add(prompt_id)
        return "cancelling"


def _output_size(graph: dict, engine: FakeEngine) -> tuple[int, int]:
    from moss_studio.domain.references import scaled_to_total_pixels

    sizes = [
        (inputs["width"], inputs["height"])
        for inputs in (node.get("inputs", {}) for node in graph.values())
        if isinstance(inputs.get("width"), int) and isinstance(inputs.get("height"), int)
    ]
    if sizes:  # staged upscale graphs size every pass; the last (largest) one is the output
        return max(sizes, key=lambda size: size[0] * size[1])
    # Edit graphs size the latent from the scaled main image (node 11 → 15 → GetImageSize);
    # inpaint graphs encode the already working-size source from node 11.
    main = graph.get("11", {}).get("inputs", {}).get("image")
    if main in engine.uploaded:
        if graph.get("14", {}).get("class_type") == "SetLatentNoiseMask":
            return engine.uploaded[main]
        return scaled_to_total_pixels(*engine.uploaded[main])
    return 1024, 1024


def _steps(graph: dict) -> int:
    for node in graph.values():
        if node.get("class_type") in {"KSampler", "KSamplerAdvanced"}:
            return int(node["inputs"].get("steps", 8))
    return 8


def make_runner(engine: FakeEngine, step_seconds: float):
    def runner(graph, prompt_id, event):
        event("before_submit", {})
        event("execution_start", {})
        steps = _steps(graph)
        sampler = next(
            (
                k
                for k, n in graph.items()
                if n.get("class_type") in {"KSampler", "KSamplerAdvanced"}
            ),
            "7",
        )
        decoder = next((k for k, n in graph.items() if n.get("class_type") == "VAEDecode"), "8")
        event("executing", {"node": sampler})
        for step in range(1, steps + 1):
            with engine.lock:
                if prompt_id in engine.cancelled:
                    raise EngineSettledError("dev engine interrupted")
            time.sleep(step_seconds)
            event("progress", {"value": step, "max": steps})
        event("executing", {"node": decoder})
        width, height = _output_size(graph, engine)
        tint = hashlib.sha256(repr(sorted(graph)).encode()).digest()
        image = Image.new("RGB", (width, height), (200 + tint[0] % 55, 210, 230))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=(29, 78, 216), width=8)
        draw.text((24, 24), f"DEV PLACEHOLDER (not model output) {width}x{height}", fill=(0, 0, 0))
        outputs = [image]
        # Extra SaveImage nodes (e.g. the estimated control map) come back as auxiliary images.
        for key in sorted(k for k, n in graph.items() if n.get("class_type") == "SaveImage"):
            if key != "9":
                outputs.append(Image.new("RGB", (width, height), (128, 128, 128)))
        encoded = []
        for picture in outputs:
            buffer = io.BytesIO()
            picture.save(buffer, format="PNG")
            encoded.append(buffer.getvalue())
        return encoded

    return runner


def main() -> int:
    import uvicorn

    from moss_studio.adapters.http import create_http_app
    from moss_studio.services.studio import StudioService
    from moss_studio.ui.app import build_ui

    parser = argparse.ArgumentParser(description="假引擎 UI 開發伺服器（不代表 GPU 驗收）")
    parser.add_argument("--data-root", type=Path, default=REPOSITORY / ".runtime/dev")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--step-seconds", type=float, default=0.15)
    args = parser.parse_args()
    password = os.environ.pop("MOSS_DEV_PASSWORD", "") or secrets.token_urlsafe(24)
    engine = FakeEngine()

    def no_real_downloads(artifact, staging):
        raise RuntimeError("開發伺服器不下載真實權重")

    service = StudioService(
        REPOSITORY,
        args.data_root,
        engine=engine,
        runner=make_runner(engine, args.step_seconds),
        model_root=args.data_root / "models",
        model_fetch=no_real_downloads,
    )
    app = create_http_app(service, password, build_ui)
    # Printed only to the local console of this dev process; never a Colab/tunnel credential.
    print(f"dev UI: http://localhost:{args.port}/login  password: {password}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
