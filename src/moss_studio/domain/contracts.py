"""Version 1 persistence contracts. No network, GPU, or arbitrary object serialization."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4


class ValidationError(ValueError):
    """Invalid user or persisted data."""


class ConflictError(ValidationError):
    """Optimistic concurrency or idempotency conflict."""


def new_id() -> str:
    return str(uuid4())


def validate_id(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("識別碼必須是標準 UUID") from exc
    return value


def now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: object) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("資料必須可序列化為有限值 JSON") from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value: object, low: int, high: int, field: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{field} 必須是 {low}～{high} 的整數")


def validate_name(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValidationError("名稱必填，最多 120 字")


TABS = ("t2i", "edit", "inpaint", "control", "models")
TASKS = ("t2i", "layout", "instruction_edit", "inpaint", "vision", "color_depth")


def new_project(name: str) -> dict:
    validate_name(name)
    return {
        "schema_version": 1,
        "id": new_id(),
        "name": name,
        "revision": 0,
        "created_at": now(),
        "updated_at": now(),
        "drafts": {tab: {} for tab in TABS},
        "asset_ids": [],
        "job_ids": [],
        "extensions": {},
    }


def validate_project(project: dict) -> None:
    required = {
        "schema_version",
        "id",
        "name",
        "revision",
        "created_at",
        "updated_at",
        "drafts",
        "asset_ids",
        "job_ids",
        "extensions",
    }
    if not isinstance(project, dict) or set(project) != required:
        raise ValidationError("專案欄位不符 schema v1，擴充欄位請放 extensions")
    if type(project["schema_version"]) is not int or project["schema_version"] != 1:
        raise ValidationError("尚不支援此專案版本")
    validate_id(project["id"])
    validate_name(project["name"])
    integer(project["revision"], 0, 2**63 - 1, "revision")
    if not isinstance(project["drafts"], dict) or set(project["drafts"]) != set(TABS):
        raise ValidationError("五分頁草稿欄位不完整")
    if any(not isinstance(d, dict) for d in project["drafts"].values()):
        raise ValidationError("分頁草稿必須是物件")
    for field in ("asset_ids", "job_ids"):
        if not isinstance(project[field], list):
            raise ValidationError(f"{field} 必須是清單")
        for identifier in project[field]:
            validate_id(identifier)
        if len(set(project[field])) != len(project[field]):
            raise ValidationError("不可重複引用相同識別碼")
    if not isinstance(project["extensions"], dict):
        raise ValidationError("extensions 必須是物件")
    for field in ("created_at", "updated_at"):
        try:
            if datetime.fromisoformat(project[field]).tzinfo is None:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValidationError("時間必須含時區") from exc
    canonical(project)


def validate_asset(asset: dict) -> None:
    required = {
        "id",
        "project_id",
        "kind",
        "path",
        "mime",
        "width",
        "height",
        "bytes",
        "sha256",
        "transform",
        "source_order",
    }
    if not isinstance(asset, dict) or set(asset) != required:
        raise ValidationError("素材欄位不符 schema v1")
    validate_id(asset["id"])
    validate_id(asset["project_id"])
    if asset["kind"] not in {"input", "output", "mask", "control"}:
        raise ValidationError("未知素材種類")
    if not isinstance(asset["path"], str):
        raise ValidationError("素材路徑必須是文字")
    path = PurePosixPath(asset["path"])
    if path.is_absolute() or ".." in path.parts or "\\" in asset["path"] or not path.parts:
        raise ValidationError("素材路徑必須在專案內")
    if asset["mime"] not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValidationError("不支援此素材格式")
    integer(asset["width"], 1, 20_000_000, "width")
    integer(asset["height"], 1, 20_000_000, "height")
    if asset["width"] * asset["height"] > 20_000_000:
        raise ValidationError("素材超過 20MP")
    # Uploaded bytes are separately capped at 20 MiB before decoding. A lossless,
    # metadata-free PNG of a valid 20MP JPEG can be larger than its source upload.
    integer(asset["bytes"], 1, 256 * 1024**2, "bytes")
    if (
        not isinstance(asset["sha256"], str)
        or len(asset["sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in asset["sha256"])
    ):
        raise ValidationError("素材 hash 必須是 SHA256")
    integer(asset["source_order"], 0, 4, "source_order")
    if not isinstance(asset["transform"], dict):
        raise ValidationError("transform 必須是物件")
    canonical(asset)


def validate_job_spec(spec: dict) -> None:
    required = {
        "project_id",
        "client_request_id",
        "project_revision",
        "task",
        "profile_id",
        "model_artifact_id",
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "seed",
        "references",
        "layout",
        "mask_asset_id",
        "control",
        "lora_stack",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValidationError("工作欄位不符 JobSpec v1")
    for field in ("project_id", "client_request_id"):
        validate_id(spec[field])
    integer(spec["project_revision"], 0, 2**63 - 1, "project_revision")
    if spec["task"] not in TASKS:
        raise ValidationError("未知工作模式")
    for field in ("profile_id", "model_artifact_id", "prompt"):
        if not isinstance(spec[field], str) or not spec[field].strip():
            raise ValidationError(f"{field} 必填")
    if not isinstance(spec["negative_prompt"], str):
        raise ValidationError("negative_prompt 必須是文字")
    for field in ("width", "height"):
        integer(spec[field], 512, 4096, field)
        if spec[field] % 16:
            raise ValidationError("寬高必須是 16 的倍數")
    if spec["width"] * spec["height"] > 2048**2:
        raise ValidationError("總像素超過上限")
    integer(spec["seed"], 0, 2**63 - 1, "seed")
    refs = spec["references"]
    if not isinstance(refs, list) or len(refs) > 4:
        raise ValidationError("最多四張參考圖")
    for slot, reference in enumerate(refs, start=1):
        if (
            not isinstance(reference, dict)
            or set(reference) != {"asset_id", "slot"}
            or type(reference["slot"]) is not int
            or reference["slot"] != slot
        ):
            raise ValidationError("參考圖號必須連續並保留順序")
        validate_id(reference["asset_id"])
    if spec["task"] in {"instruction_edit", "inpaint", "vision", "color_depth"} and not refs:
        raise ValidationError("此工作需要來源圖")
    if spec["task"] == "inpaint" and spec["mask_asset_id"] is None:
        raise ValidationError("局部重繪需要遮罩")
    if spec["mask_asset_id"] is not None:
        validate_id(spec["mask_asset_id"])
    if spec["layout"] is not None and not isinstance(spec["layout"], dict):
        raise ValidationError("layout 必須是物件")
    if spec["task"] == "layout" and spec["layout"] is None:
        raise ValidationError("排版工作需要排版資料")
    if spec["control"] is not None and not isinstance(spec["control"], dict):
        raise ValidationError("control 必須是物件")
    if not isinstance(spec["lora_stack"], list):
        raise ValidationError("lora_stack 必須是清單")
    canonical(spec)
