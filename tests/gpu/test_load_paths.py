"""Real load probes. These deliberately do not claim 8/50-step quality acceptance."""

import json
import os
import time
from copy import deepcopy
from pathlib import Path

import pytest

from moss_studio.adapters.comfy import ComfyClient
from moss_studio.domain.contracts import new_id

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def real_engine():
    if os.environ.get("MOSS_RUN_GPU") != "1":
        pytest.skip("Set MOSS_RUN_GPU=1 only in the dedicated pinned L4 runtime")
    from PIL import Image, ImageDraw

    comfy = Path(os.environ["MOSS_COMFY_ROOT"])
    client = ComfyClient()
    stats = client.health()
    assert any("L4" in device["name"] for device in stats["devices"])
    sample = Image.new("RGB", (512, 512), "#f0e0c0")
    draw = ImageDraw.Draw(sample)
    draw.rectangle((72, 120, 280, 400), fill="#d02030")
    draw.ellipse((300, 80, 460, 240), fill="#2050b0")
    sample.save(comfy / "input/stage1_reference.png")
    return client


@pytest.mark.parametrize("task", ["t2i", "vision", "edit"])
def test_real_bf16_int8_load_path(real_engine, task):
    root = Path(__file__).resolve().parents[2]
    graph = deepcopy(
        json.loads((root / f"workflows/probes/{task}_load.json").read_text(encoding="utf-8"))
    )
    graph["7"]["inputs"]["seed"] += 1  # Avoid a cached completion on rerun.
    prompt_id = new_id()
    response = real_engine.submit(graph, new_id(), prompt_id)
    assert response["prompt_id"] == prompt_id
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        history = real_engine.history(prompt_id).get(prompt_id)
        if history:
            assert history["status"]["status_str"] == "success", history["status"]
            assert any(output.get("images") for output in history["outputs"].values())
            return
        time.sleep(0.5)
    pytest.fail("real load probe did not complete within 180 seconds")
