"""Project ZIP export/import for resuming work on a new Colab VM.

The archive holds project.json, manifest.json and assets/<uuid>.png only: no model weights,
credentials, sessions or host paths. Import validates sizes, names and hashes in a private
staging step and always creates a new project id; an existing project is never overwritten.
"""

import json
import stat
import zipfile
from pathlib import Path

from moss_studio.domain.contracts import (
    TABS,
    ValidationError,
    canonical,
    new_id,
    now,
    validate_id,
    validate_project,
)
from moss_studio.storage.atomic import atomic_json, private_dir

FORMAT = "moss-studio-project"
LIMITS = {
    "archive_bytes": 1024**3,
    "expanded_bytes": 4 * 1024**3,
    "entries": 5000,
    "entry_bytes": 256 * 1024**2,
    "ratio": 100,
}


def export_project(projects, assets, project_id: str, destination: Path) -> Path:
    project = projects.get(project_id)
    entries = []
    for asset_id in project["asset_ids"]:
        meta = assets.get(project_id, asset_id)
        entries.append({k: meta[k] for k in ("id", "kind", "sha256", "bytes", "width", "height")})
    manifest = {
        "format": FORMAT,
        "schema_version": 1,
        "exported_at": now(),
        "project_id": project_id,
        "assets": entries,
    }
    destination = Path(destination)
    temporary = destination.with_suffix(".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", canonical(manifest))
        bundle.writestr("project.json", canonical(project))
        for entry in sorted(entries, key=lambda e: e["id"]):
            # PNGs are already compressed; store them to keep export fast.
            bundle.write(
                assets.path(project_id, entry["id"]),
                f"assets/{entry['id']}.png",
                compress_type=zipfile.ZIP_STORED,
            )
    temporary.replace(destination)
    return destination


def _checked_members(bundle: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = bundle.infolist()
    if len(infos) > LIMITS["entries"]:
        raise ValidationError("專案檔項目過多")
    members, expanded = {}, 0
    for info in infos:
        name = info.filename
        if name in members:
            raise ValidationError("專案檔含重複檔名")
        if stat.S_ISLNK(info.external_attr >> 16) or info.is_dir():
            raise ValidationError("專案檔不可含符號連結或資料夾項目")
        if name not in {"manifest.json", "project.json"}:
            parts = name.split("/")
            if len(parts) != 2 or parts[0] != "assets" or not parts[1].endswith(".png"):
                raise ValidationError("專案檔含不允許的路徑")
            validate_id(parts[1][: -len(".png")])
        if info.file_size > LIMITS["entry_bytes"]:
            raise ValidationError("專案檔單一項目過大")
        if info.compress_size and info.file_size / info.compress_size > LIMITS["ratio"]:
            raise ValidationError("專案檔壓縮比異常")
        expanded += info.file_size
        if expanded > LIMITS["expanded_bytes"]:
            raise ValidationError("專案檔展開後過大")
        members[name] = info
    if not {"manifest.json", "project.json"} <= members.keys():
        raise ValidationError("專案檔缺少 manifest 或 project")
    return members


def _read(bundle: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    # Read with a hard cap: declared sizes in the central directory can lie.
    with bundle.open(info) as stream:
        data = stream.read(info.file_size + 1)
    if len(data) != info.file_size:
        raise ValidationError("專案檔項目大小不符")
    return data


def import_project(projects, assets, archive: Path, staging_root: Path) -> dict:
    archive = Path(archive)
    if archive.stat().st_size > LIMITS["archive_bytes"]:
        raise ValidationError("專案檔超過 1 GiB")
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise ValidationError("不是有效的專案 ZIP") from exc
    with bundle:
        members = _checked_members(bundle)
        try:
            manifest = json.loads(_read(bundle, members["manifest.json"]))
            source = json.loads(_read(bundle, members["project.json"]))
        except ValueError as exc:
            raise ValidationError("專案檔 JSON 無效") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ValidationError("不是本工具匯出的專案檔")
        if manifest.get("schema_version") != 1:
            raise ValidationError("尚不支援此專案檔版本")
        validate_project(source)
        listed = {entry.get("id"): entry for entry in manifest.get("assets", [])}
        files = {name.split("/")[1][:-4] for name in members if name.startswith("assets/")}
        if set(listed) != files or set(source["asset_ids"]) != files:
            raise ValidationError("專案檔素材清單與內容不一致")
        project = {
            **source,
            "id": new_id(),
            "name": ("匯入 " + source["name"])[:120],
            "revision": 0,
            "created_at": now(),
            "updated_at": now(),
            "job_ids": [],  # job history stays with the original runtime's ledger
            "drafts": {tab: source["drafts"].get(tab, {}) for tab in TABS},
            "extensions": {
                **source["extensions"],
                "imported_from": {
                    "project_id": source["id"],
                    "exported_at": manifest.get("exported_at"),
                },
            },
        }
        validate_project(project)
        staging = private_dir(Path(staging_root) / project["id"])
        restored = []
        try:
            for asset_id in source["asset_ids"]:
                payload = _read(bundle, members[f"assets/{asset_id}.png"])
                restored.append(assets.restore(project["id"], listed[asset_id], payload))
            atomic_json(staging / "project.json", project)
            projects.adopt(project)
        except BaseException:
            for asset in restored:
                for suffix in (".png", ".json"):
                    (assets.root / project["id"] / f"{asset['id']}{suffix}").unlink(missing_ok=True)
            raise
        finally:
            (staging / "project.json").unlink(missing_ok=True)
            staging.rmdir()
        return project
