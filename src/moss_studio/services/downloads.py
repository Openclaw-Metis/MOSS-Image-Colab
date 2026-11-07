"""Pinned, public Hugging Face artifacts. Arbitrary URLs are not accepted.

The fixed list comes from configs/models.lock.json; user LoRAs are pinned by user_loras.py.
Civitai/third-party URL resolution is not implemented.
HF's official client handles its CDN; no user-supplied destination is passed to it.
"""

import hashlib
import json
import logging
import os
import re
import struct
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath

from moss_studio.domain.contracts import ValidationError
from moss_studio.services.user_loras import REPO as USER_REPO
from moss_studio.storage.atomic import file_lock, private_dir

APPROVED_REPOS = {
    "Comfy-Org/MOSS-Image",
    "Comfy-Org/MoGe",
    "lodestones/MOSS-Image-SFT-8-steps-dmd",
}
ROLES = {"diffusion_models", "text_encoders", "vae", "loras", "geometry_estimation"}


def source_path(artifact: dict) -> str:
    """Path inside the HF repo. Defaults to the local relative filename (Comfy-Org layout)."""
    return artifact.get("source_path", artifact["filename"])


def validate_download(artifact: dict) -> None:
    if artifact.get("provider") != "huggingface":
        raise ValidationError("只允許 Hugging Face 模型來源")
    if artifact.get("origin") == "user":
        # User-added LoRA: any public repo, but only into loras/user_<sha>.safetensors and only
        # under the commit + SHA256 + size pinned when it was added (see user_loras.py).
        repo, identifier = artifact.get("repo"), artifact.get("id", "")
        if not isinstance(repo, str) or not USER_REPO.fullmatch(repo) or ".." in repo:
            raise ValidationError("模型庫名稱無效")
        if artifact.get("role") != "user_lora" or artifact.get("filename") != (
            f"loras/{identifier}.safetensors"
        ):
            raise ValidationError("自加 LoRA 只能存成 loras/user_*.safetensors")
    elif artifact.get("repo") not in APPROVED_REPOS:
        raise ValidationError("只允許已審核的 Hugging Face 模型來源")
    identifier = artifact.get("id", "")
    if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in identifier):
        raise ValidationError("模型識別碼無效")
    for field, size in (("revision", 40), ("sha256", 64)):
        value = artifact.get(field)
        if (
            not isinstance(value, str)
            or len(value) != size
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValidationError("下載前必須鎖定 revision 與 SHA256")
    filename = artifact.get("filename", "")
    path = PurePosixPath(filename)
    if (
        "\\" in filename
        or len(path.parts) != 2
        or path.parts[0] not in ROLES
        or path.is_absolute()
        or ".." in path.parts
        or path.suffix != ".safetensors"
    ):
        raise ValidationError("只接受標準模型資料夾中的 safetensors")
    if "source_path" in artifact:
        remote = artifact["source_path"]
        remote_path = PurePosixPath(remote) if isinstance(remote, str) else None
        if (
            remote_path is None
            or "\\" in remote
            or remote_path.is_absolute()
            or ".." in remote_path.parts
            or not 1 <= len(remote_path.parts) <= 3
            or remote_path.suffix != ".safetensors"
        ):
            raise ValidationError("來源路徑必須是 repo 內的 safetensors")
    size = artifact.get("size_bytes")
    if type(size) is not int or not 8 < size <= 40 * 1024**3:
        raise ValidationError("模型大小未鎖定或超過限制")


def verify_artifact(path: Path, artifact: dict) -> None:
    if path.is_symlink() or path.stat().st_size != artifact["size_bytes"]:
        raise ValidationError("E_DOWNLOAD_HASH：模型大小或檔案類型不符")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != artifact["sha256"]:
            raise ValidationError("E_DOWNLOAD_HASH：模型 SHA256 不符")
        stream.seek(0)
        header_size = struct.unpack("<Q", stream.read(8))[0]
        if not 2 <= header_size <= min(100 * 1024**2, artifact["size_bytes"] - 8):
            raise ValidationError("E_DOWNLOAD_HASH：safetensors 檔頭無效")
        try:
            header = json.loads(stream.read(header_size))
            if not isinstance(header, dict) or not header:
                raise ValueError
            tensors = [value for key, value in header.items() if key != "__metadata__"]
            if not tensors:
                raise ValueError
            data_size = artifact["size_bytes"] - 8 - header_size
            for tensor in tensors:
                if not isinstance(tensor, dict) or set(tensor) != {
                    "dtype",
                    "shape",
                    "data_offsets",
                }:
                    raise ValueError
                offsets = tensor["data_offsets"]
                if (
                    not isinstance(offsets, list)
                    or len(offsets) != 2
                    or any(type(n) is not int for n in offsets)
                    or not 0 <= offsets[0] <= offsets[1] <= data_size
                ):
                    raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValidationError("E_DOWNLOAD_HASH：safetensors metadata 無效") from exc


def _retry_delay(error: Exception, attempt: int) -> float | None:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status is None:
        match = re.search(r"HTTP status (?:client|server) error \((\d{3})\b", str(error))
        status = int(match[1]) if match else None
    if status not in {429, 500, 502, 503, 504} and not isinstance(
        error, TimeoutError | ConnectionError
    ):
        return None
    delay = 30.0 * 2**attempt
    headers = getattr(response, "headers", {})
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            delay = max(delay, float(retry_after))
        except ValueError:
            try:
                delay = max(
                    delay, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                )
            except (TypeError, ValueError, OverflowError):
                pass
    return delay


def fetch_with_retry(artifact: dict, staging: Path, fetch, *, sleep=None) -> Path:
    """Three attempts at most; no credentials or signed CDN URLs in diagnostics."""
    for attempt in range(3):
        try:
            return Path(fetch(artifact, staging))
        except Exception as error:
            delay = _retry_delay(error, attempt)
            if delay is None or attempt == 2:
                raise
            logging.getLogger(__name__).warning(
                "E_DOWNLOAD_RETRY model=%s attempt=%s delay_seconds=%s",
                artifact["id"],
                attempt + 1,
                delay,
            )
            (sleep or time.sleep)(delay)
    raise AssertionError("unreachable")


def _hf_fetch(artifact: dict, staging: Path) -> Path:
    # Verified against the pinned hf_xet 1.8 XetConfig; set before its global session exists.
    os.environ.setdefault("HF_XET_CLIENT_AC_MAX_DOWNLOAD_CONCURRENCY", "2")
    os.environ.setdefault("HF_XET_CLIENT_AC_INITIAL_DOWNLOAD_CONCURRENCY", "1")
    os.environ.setdefault("HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS", "1")
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            repo_id=artifact["repo"],
            filename=source_path(artifact),
            revision=artifact["revision"],
            local_dir=staging,
            token=False,
        )
    )


def download_locked(artifact: dict, root: Path, *, fetch=None) -> Path:
    """Returns only a verified file; interrupted/hash failures never become ready.

    Official HF client owns its revision-specific partials and resumable transfer.
    Caller must perform disk/RAM preflight before invoking this synchronous worker.
    """
    validate_download(artifact)
    root = private_dir(Path(root))
    role, filename = PurePosixPath(artifact["filename"]).parts
    destination = private_dir(root / role) / filename
    with file_lock(root / f".{artifact['id']}.lock"):
        if destination.exists() or destination.is_symlink():
            verify_artifact(destination, artifact)
            return destination
        staging = private_dir(private_dir(root / ".incoming") / artifact["id"])
        source = fetch_with_retry(artifact, staging, fetch or _hf_fetch)
        if source.is_symlink() or not source.resolve().is_relative_to(staging.resolve()):
            raise ValidationError("下載回傳非預期路徑")
        verify_artifact(source, artifact)
        # Read-write handle: Windows rejects fsync on read-only descriptors (EBADF).
        with source.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(source, destination)
        return destination
