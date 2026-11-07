"""CAS project CRUD. Deletion is recoverable and does not delete asset/job data."""

from copy import deepcopy
from pathlib import Path

from moss_studio.domain.contracts import (
    ConflictError,
    ValidationError,
    new_project,
    now,
    validate_id,
    validate_project,
)
from moss_studio.storage.atomic import atomic_json, file_lock, private_dir, read_json
from moss_studio.storage.migrations import migrate_project


class ProjectStore:
    def __init__(self, root: Path):
        self.root = private_dir(Path(root))
        self.trash = private_dir(self.root / "trash")

    def _path(self, project_id: str) -> Path:
        return self.root / f"{validate_id(project_id)}.json"

    def _lock(self, project_id: str):
        return file_lock(self.root / f"{validate_id(project_id)}.lock")

    def create(self, name: str) -> dict:
        project = new_project(name)
        with self._lock(project["id"]):
            atomic_json(self._path(project["id"]), project)
        return project

    def get(self, project_id: str) -> dict:
        return migrate_project(read_json(self._path(project_id)))

    def list(self) -> list[dict]:
        return sorted(
            (self.get(p.stem) for p in self.root.glob("*.json")),
            key=lambda p: (p["updated_at"], p["id"]),
            reverse=True,
        )

    def save(self, project: dict, expected_revision: int) -> dict:
        candidate = deepcopy(project)
        validate_project(candidate)
        with self._lock(candidate["id"]):
            current = self.get(candidate["id"])
            if (
                type(expected_revision) is not int
                or current["revision"] != expected_revision
                or candidate["revision"] != expected_revision
            ):
                raise ConflictError("E_CONFLICT：專案已更新，請重新載入或另存")
            if candidate["created_at"] != current["created_at"]:
                raise ValidationError("不可修改建立時間")
            candidate["revision"] += 1
            candidate["updated_at"] = now()
            atomic_json(self._path(candidate["id"]), candidate)
        return candidate

    def rename(self, project_id: str, name: str, expected_revision: int) -> dict:
        project = self.get(project_id)
        project["name"] = name
        return self.save(project, expected_revision)

    def delete(self, project_id: str, expected_revision: int, *, confirmed: bool = False) -> None:
        if not confirmed:
            raise ValidationError("請先確認刪除專案")
        with self._lock(project_id):
            project = self.get(project_id)
            if type(expected_revision) is not int or project["revision"] != expected_revision:
                raise ConflictError("E_CONFLICT：專案已更新")
            self._path(project_id).replace(self.trash / f"{project_id}.json")

    def restore(self, project_id: str) -> dict:
        with self._lock(project_id):
            path = self._path(project_id)
            if path.exists():
                raise ConflictError("同識別碼專案已存在")
            source = self.trash / f"{project_id}.json"
            project = migrate_project(read_json(source))
            project["revision"] += 1
            project["updated_at"] = now()
            atomic_json(path, project)
            source.unlink()
            return project
