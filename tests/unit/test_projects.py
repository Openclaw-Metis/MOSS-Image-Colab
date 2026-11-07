import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from moss_studio.domain.contracts import ConflictError, ValidationError
from moss_studio.storage.migrations import migrate_project
from moss_studio.storage.projects import ProjectStore


def test_crud_restore_and_conflict(tmp_path):
    store = ProjectStore(tmp_path)
    first = store.create("山間慢旅")
    renamed = store.rename(first["id"], "夜色", 0)
    assert renamed["revision"] == 1
    assert first["name"] == "山間慢旅"
    assert store.list()[0]["name"] == "夜色"
    with pytest.raises(ConflictError):
        store.save(first, 0)
    with pytest.raises(ValidationError):
        store.delete(first["id"], 1)
    with pytest.raises(ConflictError):
        store.delete(first["id"], 0, confirmed=True)
    store.delete(first["id"], 1, confirmed=True)
    assert store.list() == []
    assert store.restore(first["id"])["revision"] == 2
    with pytest.raises(ConflictError):
        store.restore(first["id"])


def test_failed_replace_keeps_previous_file(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    original = store.create("保存測試")

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("moss_studio.storage.atomic.os.replace", fail)
    candidate = deepcopy(original)
    candidate["drafts"]["t2i"]["prompt"] = "尚未保存"
    with pytest.raises(OSError):
        store.save(candidate, 0)
    assert store.get(original["id"]) == original
    assert not list(tmp_path.glob(".write-*"))


def test_fsync_failure_before_replace_keeps_previous_file(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    original = store.create("保存測試")

    def fail(*args):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("moss_studio.storage.atomic.os.fsync", fail)
    with pytest.raises(OSError):
        store.rename(original["id"], "不可保存", 0)
    assert store.get(original["id"]) == original
    assert not list(tmp_path.glob(".write-*"))


def test_concurrent_updates_only_one_wins(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create("原稿")
    barrier = Barrier(2)

    def update(name):
        candidate = store.get(project["id"])
        candidate["name"] = name
        barrier.wait(timeout=5)
        try:
            return store.save(candidate, 0)["revision"]
        except ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["甲", "乙"]))
    assert sorted(outcomes, key=str) == [1, "conflict"]
    assert store.get(project["id"])["revision"] == 1


@pytest.mark.parametrize("identifier", ["../escape", "/tmp/escape", "", "../../x.json"])
def test_paths_rejected(tmp_path, identifier):
    with pytest.raises(ValidationError):
        ProjectStore(tmp_path).get(identifier)


def test_symlink_not_read_or_used_as_directory(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":"do not read"}')
    store = ProjectStore(tmp_path / "projects")
    project = store.create("安全路徑")
    path = store.root / f"{project['id']}.json"
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(OSError):
        store.get(project["id"])
    link = tmp_path / "linked-root"
    link.symlink_to(store.root)
    with pytest.raises(ValidationError):
        ProjectStore(link)
    assert json.loads(outside.read_text()) == {"secret": "do not read"}


def test_schema_boundary_and_extensions(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create("版本")
    project["extensions"] = {"future": {"value": 12}}
    assert migrate_project(project) == project
    unknown = deepcopy(project)
    unknown["schema_version"] = 2
    with pytest.raises(ValidationError):
        migrate_project(unknown)
    unknown = deepcopy(project)
    unknown["unexpected"] = True
    with pytest.raises(ValidationError):
        store.save(unknown, 0)
    project["drafts"]["t2i"]["invalid"] = float("nan")
    with pytest.raises(ValidationError):
        store.save(project, 0)
