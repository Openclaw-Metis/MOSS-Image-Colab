"""User-added LoRAs: one exact Hugging Face file, pinned before anything is downloaded.

The user gives repo + full 40-hex commit + path; the Hub's own metadata for that commit supplies
the LFS SHA256 and size, which then gate the download exactly like the fixed model list. No URL,
branch name or token is accepted, so the file cannot change after it is added.
"""

import re
from pathlib import PurePosixPath

from moss_studio.domain.contracts import ValidationError

REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
COMMIT = re.compile(r"[0-9a-f]{40}")
MAX_BYTES = 2 * 1024**3  # far above typical LoRAs (≤ 1.2 GB here); refuses full checkpoints
MAX_USER_LORAS = 20


def validate_source(repo, revision, path) -> tuple[str, str, str]:
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or ".." in repo or "--" in repo:
        raise ValidationError("模型庫名稱格式應為「擁有者/名稱」")
    if not isinstance(revision, str) or not COMMIT.fullmatch(revision):
        raise ValidationError("請填完整 40 碼 commit（小寫十六進位），不接受分支名稱")
    remote = PurePosixPath(path) if isinstance(path, str) else None
    if (
        remote is None
        or "\\" in path
        or remote.is_absolute()
        or ".." in remote.parts
        or not 1 <= len(remote.parts) <= 3
        or remote.suffix != ".safetensors"
    ):
        raise ValidationError("檔案路徑必須是模型庫內的 .safetensors（最多兩層資料夾）")
    return repo, revision, str(remote)


def hub_file_pin(repo: str, revision: str, path: str) -> dict:
    """Asks the Hub for the LFS SHA256 and size of that file at that commit."""
    from huggingface_hub import HfApi

    from moss_studio.services.downloads import hub_token  # local: downloads imports this module

    try:
        (info,) = HfApi().get_paths_info(repo, [path], revision=revision, token=hub_token())
    except ValueError as exc:  # unpacking: the path does not exist at that commit
        raise ValidationError("此 commit 找不到這個檔案") from exc
    except Exception as exc:  # noqa: BLE001 - network/HTTP errors may embed URLs; keep it plain
        raise ValidationError(
            "無法向 Hugging Face 查詢此檔案（模型庫不存在、需登入或網路錯誤）"
        ) from exc
    lfs = getattr(info, "lfs", None)
    if lfs is None:
        raise ValidationError("此檔案沒有 LFS 雜湊，無法鎖定內容")
    return {"sha256": lfs.sha256, "size_bytes": lfs.size}


def user_artifact(repo: str, revision: str, path: str, pin: dict) -> dict:
    sha256, size = pin.get("sha256"), pin.get("size_bytes")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValidationError("Hugging Face 回傳的 SHA256 無效")
    if type(size) is not int or not 8 < size <= MAX_BYTES:
        raise ValidationError("LoRA 檔案需小於 2 GiB")
    identifier = f"user_{sha256[:12]}"
    return {
        "id": identifier,
        "provider": "huggingface",
        "origin": "user",
        "repo": repo,
        "revision": revision,
        "source_path": path,
        "filename": f"loras/{identifier}.safetensors",
        "size_bytes": size,
        "sha256": sha256,
        "role": "user_lora",
        "dtype": None,
        "label": PurePosixPath(path).name,
        "license_url": f"https://huggingface.co/{repo}",
        "provider_declared_license": "請見來源頁",
    }
