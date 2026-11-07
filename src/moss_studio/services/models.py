"""Model page service: pinned-artifact status, background downloads, active backbone.

Downloads come only from configs/models.lock.json or from user LoRAs pinned by commit, SHA256
and size (user_loras.py); there is no URL input. Downloads run on their own single worker so
they never hold the GPU lock.
"""

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from moss_studio.domain.contracts import ConflictError, ValidationError
from moss_studio.services.downloads import download_locked, validate_download
from moss_studio.services.user_loras import (
    MAX_USER_LORAS,
    hub_file_pin,
    user_artifact,
    validate_source,
)
from moss_studio.storage.atomic import atomic_json, private_dir, read_json

PUBLIC_FIELDS = (
    "id",
    "role",
    "dtype",
    "repo",
    "revision",
    "size_bytes",
    "license_url",
    "provider_declared_license",
    "label",
    "source_path",
)

# The text/vision encoder and VAE are loaded by every workflow, whichever backbone is active.
SHARED_ROLES = {"text_vision_encoder", "vae"}


class ModelManager:
    def __init__(
        self, repository: Path, model_root: Path, data_root: Path, *, fetch=None, lookup=None
    ):
        self.model_root = Path(model_root)
        self.settings_path = private_dir(Path(data_root)) / "settings.json"
        self.user_path = private_dir(Path(data_root)) / "user_loras.json"
        lock = json.loads((Path(repository) / "configs/models.lock.json").read_text("utf-8"))
        self.registry = {artifact["id"]: artifact for artifact in lock["artifacts"]}
        if self.user_path.exists():
            for artifact in read_json(self.user_path)["artifacts"]:
                validate_download(artifact)  # a tampered entry must not widen what is fetched
                if artifact.get("origin") != "user" or artifact["id"] in self.registry:
                    raise ValidationError("自加 LoRA 清單無效")
                self.registry[artifact["id"]] = artifact
        self.lookup = lookup or hub_file_pin
        self.fetch = fetch
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moss-download")
        self.lock = threading.Lock()
        self.states: dict[str, dict] = {}

    def _settings(self) -> dict:
        if self.settings_path.exists():
            return read_json(self.settings_path)
        return {"active_backbone": "sft_bf16"}

    def active_backbone(self) -> str:
        return self._settings()["active_backbone"]

    def _present(self, artifact: dict) -> bool:
        # Size match only: hashing 10 GB on every page view is too slow. The SHA256 check
        # happens in download_locked before a file is ever moved into place.
        path = self.model_root / artifact["filename"]
        return (
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size == artifact["size_bytes"]
        )

    def status(self, artifact_id: str) -> dict:
        with self.lock:
            state = dict(self.states.get(artifact_id, {}))
        if state.get("state") == "downloading":
            return state
        if self._present(self.registry[artifact_id]):
            return {"state": "ready"}
        return state or {"state": "missing"}

    def list(self) -> list[dict]:
        active = self.active_backbone()
        return [
            {key: artifact.get(key) for key in PUBLIC_FIELDS}
            | {"active": artifact["id"] == active, **self.status(artifact["id"])}
            for artifact in self.registry.values()
        ]

    def download(self, artifact_id: str) -> dict:
        artifact = self.registry.get(artifact_id)
        if artifact is None:
            raise ValidationError("模型清單中沒有此識別碼")
        if self.status(artifact_id)["state"] in {"ready", "downloading"}:
            return self.status(artifact_id)
        free = shutil.disk_usage(private_dir(self.model_root)).free
        if free < artifact["size_bytes"] + 10 * 1024**3:
            raise ValidationError("磁碟空間不足：需要模型大小加 10 GiB 工作空間")
        with self.lock:
            self.states[artifact_id] = {"state": "downloading"}
        self.pool.submit(self._download, artifact)
        return self.status(artifact_id)

    def _download(self, artifact: dict) -> None:
        try:
            download_locked(artifact, self.model_root, fetch=self.fetch)
            state = {"state": "ready"}
        except Exception as error:  # noqa: BLE001 - surfaced to the UI without secrets
            # Only our own validation messages are shown; network errors can embed signed URLs.
            state = {"state": "failed"}
            if isinstance(error, ValidationError):
                state["message"] = str(error)
        with self.lock:
            self.states[artifact["id"]] = state

    def activate(self, artifact_id: str, *, busy: bool) -> dict:
        artifact = self.registry.get(artifact_id)
        if artifact is None or artifact["role"] != "backbone":
            raise ValidationError("只能切換主模型")
        if busy:
            raise ConflictError("E_CONFLICT：工作進行中，完成或取消後再切換主模型")
        if self.status(artifact_id)["state"] != "ready":
            raise ValidationError("請先下載並校驗此主模型")
        atomic_json(self.settings_path, {**self._settings(), "active_backbone": artifact_id})
        return {"active_backbone": artifact_id}

    def _save_user_loras(self) -> None:
        users = [a for a in self.registry.values() if a.get("origin") == "user"]
        atomic_json(self.user_path, {"schema_version": 1, "artifacts": users})

    def add_user_lora(self, repo, revision, path) -> dict:
        """Pins one Hub file (network lookup) and registers it; downloading is a separate step."""
        repo, revision, path = validate_source(repo, revision, path)
        artifact = user_artifact(repo, revision, path, self.lookup(repo, revision, path))
        validate_download(artifact)
        with self.lock:
            existing = self.registry.get(artifact["id"])
            if existing is None:
                if sum(a.get("origin") == "user" for a in self.registry.values()) >= MAX_USER_LORAS:
                    raise ValidationError(f"自加 LoRA 最多 {MAX_USER_LORAS} 個，請先移除不用的")
                self.registry[artifact["id"]] = artifact
                self._save_user_loras()
            elif existing.get("origin") != "user":
                raise ValidationError("此檔案已在固定模型清單中")
        return {key: self.registry[artifact["id"]].get(key) for key in PUBLIC_FIELDS}

    def delete(self, artifact_id: str, *, busy: bool) -> dict:
        """Frees disk space; refuses anything a current or any future job is bound to read."""
        artifact = self.registry.get(artifact_id)
        if artifact is None:
            raise ValidationError("模型清單中沒有此識別碼")
        if artifact["role"] in SHARED_ROLES:
            raise ConflictError("E_CONFLICT：每個工作都會用到此檔案，不能刪除")
        if artifact_id == self.active_backbone():
            raise ConflictError("E_CONFLICT：使用中的主模型不能刪除，請先切換到其他主模型")
        if busy:
            raise ConflictError("E_CONFLICT：工作進行中，完成或取消後再刪除模型")
        if self.status(artifact_id)["state"] == "downloading":
            raise ConflictError("E_CONFLICT：下載中，完成後再刪除")
        path = self.model_root / artifact["filename"]
        if path.is_symlink():
            raise ValidationError("模型路徑不是一般檔案，已拒絕")
        path.unlink(missing_ok=True)
        with self.lock:
            self.states.pop(artifact_id, None)
            if artifact.get("origin") == "user":  # a user LoRA is removed from the list too
                del self.registry[artifact_id]
                self._save_user_loras()
                return {"state": "removed"}
        return self.status(artifact_id)

    def close(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
