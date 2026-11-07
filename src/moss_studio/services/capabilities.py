"""Release gates use evidence, never merely file existence."""

from moss_studio.domain.contracts import ValidationError

STATES = {"unverified", "probing", "verified", "released", "blocked", "disabled"}
REQUIRED_ARTIFACT_FIELDS = {
    "id",
    "provider",
    "repo",
    "revision",
    "filename",
    "size_bytes",
    "sha256",
    "license_url",
    "role",
    "dtype",
    "base_family",
    "supported_tasks",
    "tested_workflow_hash",
}


def artifact_gaps(artifact: dict) -> list[str]:
    gaps = [field for field in sorted(REQUIRED_ARTIFACT_FIELDS) if not artifact.get(field)]
    for field, length in (("revision", 40), ("sha256", 64), ("tested_workflow_hash", 64)):
        value = artifact.get(field)
        if value and (
            not isinstance(value, str)
            or len(value) != length
            or any(c not in "0123456789abcdef" for c in value)
        ):
            gaps.append(field)
    if artifact.get("size_bytes") is not None and (
        type(artifact["size_bytes"]) is not int or artifact["size_bytes"] <= 0
    ):
        gaps.append("size_bytes")
    return sorted(set(gaps))


def require_released(capability: dict) -> None:
    if capability.get("state") not in STATES:
        raise ValidationError("能力狀態無效")
    if (
        capability["state"] != "released"
        or not capability.get("evidence")
        or not capability.get("workflow_hash")
    ):
        raise ValidationError("E_CAPABILITY：此功能尚缺已驗證的節點、權重或實測證據")
