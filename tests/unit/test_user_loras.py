"""User-added HF LoRAs: exact pin before download, quality50-only stacking, clean removal."""

import hashlib
import json
import struct
import time
from pathlib import Path

import pytest

from moss_studio.adapters.workflow import compile_t2i
from moss_studio.domain.contracts import ValidationError
from moss_studio.services.models import ModelManager
from moss_studio.services.user_loras import validate_source

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def safetensors_bytes():
    header = json.dumps({"w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    return struct.pack("<Q", len(header)) + header + struct.pack("<f", 1.0)


DATA = safetensors_bytes()


def pin(repo, revision, path):
    return {"sha256": hashlib.sha256(DATA).hexdigest(), "size_bytes": len(DATA)}


@pytest.mark.parametrize(
    "repo,revision,path",
    [
        ("no-owner", COMMIT, "lora.safetensors"),
        ("a/../b", COMMIT, "lora.safetensors"),
        ("owner/name", "main", "lora.safetensors"),
        ("owner/name", COMMIT.upper(), "lora.safetensors"),
        ("owner/name", COMMIT, "../lora.safetensors"),
        ("owner/name", COMMIT, "/abs/lora.safetensors"),
        ("owner/name", COMMIT, "a/b/c/lora.safetensors"),
        ("owner/name", COMMIT, "lora.ckpt"),
        ("owner/name", COMMIT, "dir\\lora.safetensors"),
    ],
)
def test_source_must_be_an_exact_hub_file(repo, revision, path):
    with pytest.raises(ValidationError):
        validate_source(repo, revision, path)


def wait_ready(manager, artifact_id):
    deadline = time.monotonic() + 5
    while manager.status(artifact_id)["state"] != "ready":
        assert manager.status(artifact_id)["state"] != "failed"
        assert time.monotonic() < deadline
        time.sleep(0.02)


def test_add_download_stack_and_remove(tmp_path, job_spec):
    def fetch(artifact, staging):
        assert (artifact["repo"], artifact["revision"]) == ("owner/style", COMMIT)
        assert artifact["source_path"] == "loras/style.safetensors"
        path = staging / "file.safetensors"
        path.write_bytes(DATA)
        return path

    models, data = tmp_path / "models", tmp_path / "data"
    manager = ModelManager(ROOT, models, data, fetch=fetch, lookup=pin)
    try:
        added = manager.add_user_lora("owner/style", COMMIT, "loras/style.safetensors")
        artifact_id = added["id"]
        assert artifact_id.startswith("user_") and added["label"] == "style.safetensors"
        assert manager.add_user_lora("owner/style", COMMIT, "loras/style.safetensors") == added
        # Persisted and revalidated on the next start.
        assert artifact_id in ModelManager(ROOT, models, data).registry
        manager.download(artifact_id)
        wait_ready(manager, artifact_id)
        assert (models / f"loras/{artifact_id}.safetensors").read_bytes() == DATA

        profiles = {p: load(f"configs/profiles/{p}.json") for p in ("quality50", "fast8")}
        stack = [{"artifact_id": artifact_id, "strength": 0.8}]
        graph = compile_t2i(
            {**job_spec, "lora_stack": stack},
            load("workflows/t2i.json"),
            profiles["quality50"],
            manager.registry,
        )
        assert graph["30"]["inputs"]["lora_name"] == f"{artifact_id}.safetensors"
        assert graph["30"]["inputs"]["strength_model"] == 0.8
        for profile, bad in [
            ("fast8", stack),
            ("quality50", [{"artifact_id": "edit_sft", "strength": 1.0}]),
            ("quality50", [{"artifact_id": artifact_id, "strength": 3.0}]),
            ("quality50", stack + stack),
            ("quality50", [{"artifact_id": artifact_id, "strength": 1.0, "extra": 1}]),
        ]:
            spec = {**job_spec, "profile_id": profiles[profile]["id"], "lora_stack": bad}
            if profile == "fast8":
                spec["negative_prompt"] = ""
            with pytest.raises(ValidationError):
                compile_t2i(spec, load("workflows/t2i.json"), profiles[profile], manager.registry)

        assert manager.delete(artifact_id, busy=False) == {"state": "removed"}
        assert artifact_id not in manager.registry
        assert not (models / f"loras/{artifact_id}.safetensors").exists()
        assert artifact_id not in ModelManager(ROOT, models, data).registry
    finally:
        manager.close()


def test_tampered_user_list_cannot_widen_downloads(tmp_path):
    entry = {
        "id": "user_aaaaaaaaaaaa",
        "provider": "huggingface",
        "origin": "user",
        "repo": "owner/style",
        "revision": COMMIT,
        "source_path": "style.safetensors",
        "filename": "diffusion_models/user_aaaaaaaaaaaa.safetensors",
        "size_bytes": 100,
        "sha256": "b" * 64,
        "role": "user_lora",
    }
    (tmp_path / "data").mkdir()
    path = tmp_path / "data/user_loras.json"
    path.write_text(json.dumps({"schema_version": 1, "artifacts": [entry]}), encoding="utf-8")
    with pytest.raises(ValidationError):
        ModelManager(ROOT, tmp_path / "models", tmp_path / "data")
    entry.update(filename="loras/user_aaaaaaaaaaaa.safetensors", id="sft_bf16")
    path.write_text(json.dumps({"schema_version": 1, "artifacts": [entry]}), encoding="utf-8")
    with pytest.raises(ValidationError):
        ModelManager(ROOT, tmp_path / "models", tmp_path / "data")


def test_hub_answer_must_be_a_real_pin(tmp_path):
    for answer in (
        {"sha256": "nothex", "size_bytes": 10},
        {"sha256": "c" * 64, "size_bytes": 3 * 1024**3},
    ):
        manager = ModelManager(
            ROOT, tmp_path / "models", tmp_path / "data", lookup=lambda *a, x=answer: x
        )
        try:
            with pytest.raises(ValidationError):
                manager.add_user_lora("owner/style", COMMIT, "style.safetensors")
        finally:
            manager.close()
