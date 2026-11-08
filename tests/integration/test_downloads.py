import hashlib
import json
import struct

import pytest

from moss_studio.domain.contracts import ValidationError
from moss_studio.services.downloads import download_locked, fetch_with_retry


@pytest.fixture
def artifact():
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    data = struct.pack("<Q", len(header)) + header + struct.pack("<f", 1.0)
    return {
        "id": "test_model",
        "provider": "huggingface",
        "repo": "Comfy-Org/MOSS-Image",
        "revision": "a" * 40,
        "filename": "diffusion_models/test.safetensors",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }, data


def test_verified_atomic_download_and_rerun(tmp_path, artifact):
    spec, data = artifact
    calls = []

    def fetch(spec, staging):
        calls.append(True)
        path = staging / "model.safetensors"
        path.write_bytes(data)
        return path

    first = download_locked(spec, tmp_path, fetch=fetch)
    assert first.read_bytes() == data
    assert download_locked(spec, tmp_path, fetch=fetch) == first
    assert len(calls) == 1


def test_repo_path_differs_from_local_name_for_community_lora(tmp_path, artifact):
    spec, data = artifact
    spec = {
        **spec,
        "repo": "lodestones/MOSS-Image-SFT-8-steps-dmd",
        "source_path": "lora_latest.safetensors",
        "filename": "loras/dmd8_pinned.safetensors",
    }
    requested = []

    def fetch(spec, staging):
        from moss_studio.services.downloads import source_path

        requested.append(source_path(spec))
        path = staging / source_path(spec)
        path.write_bytes(data)
        return path

    final = download_locked(spec, tmp_path, fetch=fetch)
    assert requested == ["lora_latest.safetensors"]
    assert final == tmp_path / "loras" / "dmd8_pinned.safetensors"


@pytest.mark.parametrize(
    "remote", ["../escape.safetensors", "/abs.safetensors", "a\\b.safetensors", "x.bin", 7]
)
def test_unsafe_repo_source_paths_rejected(tmp_path, artifact, remote):
    spec, _ = artifact
    with pytest.raises(ValidationError):
        download_locked({**spec, "source_path": remote}, tmp_path, fetch=lambda *_: None)


def test_failed_download_never_becomes_ready(tmp_path, artifact, monkeypatch):
    spec, data = artifact
    monkeypatch.setattr("moss_studio.services.downloads.time.sleep", lambda _: None)

    def broken_fetch(spec, staging):
        path = staging / "partial"
        path.write_bytes(data[:-1])
        return path

    with pytest.raises(ValidationError):
        download_locked(spec, tmp_path, fetch=broken_fetch)
    assert not (tmp_path / spec["filename"]).exists()

    def interrupted(spec, staging):
        raise TimeoutError("simulated network interruption")

    with pytest.raises(TimeoutError):
        download_locked(spec, tmp_path, fetch=interrupted)
    assert not (tmp_path / spec["filename"]).exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repo", "attacker/model"),
        ("filename", "../model.safetensors"),
        ("filename", "diffusion_models/model.pkl"),
        ("revision", "main"),
        ("sha256", None),
        ("id", "../bad"),
        ("size_bytes", 0),
    ],
)
def test_unpinned_or_unknown_sources_rejected(tmp_path, artifact, field, value):
    spec, _ = artifact
    spec[field] = value
    with pytest.raises(ValidationError):
        download_locked(spec, tmp_path, fetch=lambda *_: pytest.fail("must not fetch"))


def test_rate_limit_backoff_resumes_same_artifact(tmp_path, artifact):
    spec, _ = artifact
    attempts, delays = [], []

    def fetch(model, staging):
        attempts.append((model, staging))
        if len(attempts) < 3:
            raise RuntimeError("HTTP status client error (429 Too Many Requests), domain: secret")
        return staging / "complete"

    assert fetch_with_retry(spec, tmp_path, fetch, sleep=delays.append) == tmp_path / "complete"
    assert delays == [30, 60]
    assert attempts == [(spec, tmp_path)] * 3


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_download_retry_limit_and_authorization_errors(tmp_path, artifact, status):
    spec, _ = artifact
    attempts, delays = [], []

    def fetch(*args):
        attempts.append(True)
        raise RuntimeError(f"HTTP status client error ({status} error)")

    with pytest.raises(RuntimeError):
        fetch_with_retry(spec, tmp_path, fetch, sleep=delays.append)
    assert len(attempts) == (3 if status == 429 else 1)


def test_retry_after_is_respected(tmp_path, artifact):
    from types import SimpleNamespace

    spec, _ = artifact
    delays = []
    error = RuntimeError("private signed URL")
    error.response = SimpleNamespace(status_code=429, headers={"retry-after": "120"})

    def fetch(*args):
        if not delays:
            raise error
        return tmp_path / "complete"

    fetch_with_retry(spec, tmp_path, fetch, sleep=delays.append)
    assert delays == [120]


def test_hub_token_comes_only_from_the_environment(tmp_path, artifact, monkeypatch):
    import huggingface_hub

    from moss_studio.services import downloads

    meta, data = artifact
    seen = []

    def fake_download(**kwargs):
        seen.append(kwargs["token"])
        path = tmp_path / "staging-copy.safetensors"
        path.write_bytes(data)
        return str(path)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    downloads._hf_fetch(meta, tmp_path)
    monkeypatch.setenv("HF_TOKEN", "  hf_test_only_value  ")
    downloads._hf_fetch(meta, tmp_path)
    monkeypatch.setenv("HF_TOKEN", "   ")
    downloads._hf_fetch(meta, tmp_path)
    # Anonymous unless a token is set; whitespace-only counts as unset.
    assert seen == [False, "hf_test_only_value", False]
