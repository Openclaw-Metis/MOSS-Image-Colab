"""Stage 8 CPU parts of AC-15/AC-17: project ZIP round trip and hostile archives."""

import hashlib
import io
import json
import stat
import zipfile

import pytest
from PIL import Image

from moss_studio.domain.contracts import ValidationError
from moss_studio.storage.archive import export_project, import_project
from moss_studio.storage.assets import AssetStore
from moss_studio.storage.projects import ProjectStore


def png(color, size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def stores(tmp_path):
    projects, assets = ProjectStore(tmp_path / "projects"), AssetStore(tmp_path / "assets")
    project = projects.create("山間慢旅")
    a = assets.import_image(project["id"], png("red"))
    m = assets.import_image(project["id"], png("white"), kind="mask")
    project["asset_ids"] += [a["id"], m["id"]]
    project["drafts"]["edit"] = {
        "slots": [{"asset_id": a["id"]}, None, None, None],
        "prompt": "改色",
    }
    project["drafts"]["inpaint"] = {"source": {"asset_id": a["id"]}, "mask_asset_id": m["id"]}
    project = projects.save(project, project["revision"])
    return projects, assets, project, tmp_path


def test_round_trip_keeps_drafts_assets_and_hashes_under_a_new_id(stores):
    projects, assets, project, tmp = stores
    archive = export_project(projects, assets, project["id"], tmp / "out.zip")
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert {"manifest.json", "project.json"} <= names
        assert all(n.startswith("assets/") for n in names - {"manifest.json", "project.json"})
        assert not any(n.endswith((".safetensors", ".sqlite")) for n in bundle.namelist())
    other_projects, other_assets = (
        ProjectStore(tmp / "vm2/projects"),
        AssetStore(tmp / "vm2/assets"),
    )
    imported = import_project(other_projects, other_assets, archive, tmp / "vm2/staging")
    assert imported["id"] != project["id"] and imported["job_ids"] == []
    assert imported["drafts"] == project["drafts"]
    assert imported["extensions"]["imported_from"]["project_id"] == project["id"]
    for asset_id in project["asset_ids"]:
        before = hashlib.sha256(assets.path(project["id"], asset_id).read_bytes()).hexdigest()
        after = hashlib.sha256(other_assets.path(imported["id"], asset_id).read_bytes()).hexdigest()
        assert before == after
        assert (
            other_assets.get(imported["id"], asset_id)["kind"]
            == assets.get(project["id"], asset_id)["kind"]
        )
    assert other_projects.get(imported["id"])["revision"] == 0
    assert not list((tmp / "vm2/staging").iterdir())


def rewrite(archive, target, mutate):
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(target, "w") as out:
        entries = {i.filename: source.read(i) for i in source.infolist()}
        for name, data, info in mutate(entries):
            out.writestr(info or name, data)
    return target


def keep(entries):
    return [(n, d, None) for n, d in entries.items()]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: [*keep(e), ("../escape.png", b"x", None)],
        lambda e: [*keep(e), ("assets/not-a-uuid.png", b"x", None)],
        lambda e: [*keep(e), ("notes.txt", b"x", None)],
        lambda e: [(n, d, None) for n, d in e.items() if n != "manifest.json"],
        lambda e: [
            (n, d if not n.startswith("assets/") else d[:-1] + b"\0", None) for n, d in e.items()
        ],
        lambda e: [(n, d, None) for n, d in e.items() if not n.startswith("assets/")],
        lambda e: [
            (
                n,
                json.dumps({**json.loads(d), "format": "other"}).encode()
                if n == "manifest.json"
                else d,
                None,
            )
            for n, d in e.items()
        ],
    ],
)
def test_hostile_or_inconsistent_archives_are_rejected_without_side_effects(stores, mutate):
    projects, assets, project, tmp = stores
    archive = export_project(projects, assets, project["id"], tmp / "out.zip")
    bad = rewrite(archive, tmp / "bad.zip", mutate)
    target = ProjectStore(tmp / "vm2/projects")
    with pytest.raises(ValidationError):
        import_project(target, AssetStore(tmp / "vm2/assets"), bad, tmp / "vm2/staging")
    assert target.list() == []


def test_symlink_entry_and_compression_bomb_rejected(stores):
    projects, assets, project, tmp = stores
    archive = export_project(projects, assets, project["id"], tmp / "out.zip")

    def with_symlink(entries):
        link = zipfile.ZipInfo("assets/" + project["asset_ids"][0] + ".png")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        return [
            (n, d, None)
            for n, d in entries.items()
            if not n.endswith(project["asset_ids"][0] + ".png")
        ] + [(link.filename, b"/etc/passwd", link)]

    bad = rewrite(archive, tmp / "link.zip", with_symlink)
    with pytest.raises(ValidationError, match="符號連結"):
        import_project(ProjectStore(tmp / "a"), AssetStore(tmp / "b"), bad, tmp / "c")
    bomb = tmp / "bomb.zip"
    with (
        zipfile.ZipFile(archive) as source,
        zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as out,
    ):
        for info in source.infolist():
            out.writestr(info.filename, source.read(info))
        out.writestr("assets/00000000-0000-4000-8000-000000000000.png", b"\0" * (5 * 1024**2))
    with pytest.raises(ValidationError, match="壓縮比"):
        import_project(ProjectStore(tmp / "d"), AssetStore(tmp / "e"), bomb, tmp / "f")
