"""Decoded, metadata-free project assets addressed by UUID, never user filenames."""

import hashlib
import io
import os
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from moss_studio.domain.contracts import ValidationError, new_id, validate_asset, validate_id
from moss_studio.storage.atomic import atomic_json, private_dir, read_json


class AssetStore:
    def __init__(self, root: Path):
        self.root = private_dir(Path(root))

    def _directory(self, project_id: str) -> Path:
        return private_dir(self.root / validate_id(project_id))

    def import_image(
        self, project_id: str, data: bytes, *, kind: str = "input", source_order: int = 0
    ) -> dict:
        if not 0 < len(data) <= 20 * 1024**2:
            raise ValidationError("圖片需小於 20 MiB")
        try:
            with Image.open(io.BytesIO(data)) as source:
                if (
                    source.format not in {"PNG", "JPEG", "WEBP"}
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise ValidationError("請使用 PNG、JPEG 或靜態 WebP")
                if source.width * source.height > 20_000_000:
                    raise ValidationError("圖片超過 20 MP")
                source.load()
                image = ImageOps.exif_transpose(source).convert(
                    "RGBA" if "A" in source.getbands() or "transparency" in source.info else "RGB"
                )
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValidationError("無法解碼這張圖片，保留原有輸入") from exc
        target = io.BytesIO()
        # Rebuild pixels so EXIF, GPS, prompt chunks and user filenames are not copied.
        Image.frombytes(image.mode, image.size, image.tobytes()).save(target, format="PNG")
        encoded = target.getvalue()
        identifier = new_id()
        asset = {
            "id": identifier,
            "project_id": project_id,
            "kind": kind,
            "path": f"{project_id}/{identifier}.png",
            "mime": "image/png",
            "width": image.width,
            "height": image.height,
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "transform": {},
            "source_order": source_order,
        }
        validate_asset(asset)
        directory = self._directory(project_id)
        temporary = directory / f".{identifier}.part"
        final = directory / f"{identifier}.png"
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(final)
            atomic_json(directory / f"{identifier}.json", asset)
        except BaseException:
            temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise
        return asset

    def restore(self, project_id: str, meta: dict, data: bytes) -> dict:
        """Imports an exported asset under a new project, keeping its id (drafts refer to it).

        The bytes must match the manifest hash and decode as a single-frame PNG; metadata is
        rebuilt from the decoded image instead of trusting the archive.
        """
        identifier = validate_id(meta.get("id"))
        if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            raise ValidationError("專案檔素材 hash 不符")
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("專案檔素材必須是 PNG")
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValidationError("專案檔素材無法解碼") from exc
        asset = {
            "id": identifier,
            "project_id": project_id,
            "kind": meta.get("kind"),
            "path": f"{project_id}/{identifier}.png",
            "mime": "image/png",
            "width": width,
            "height": height,
            "bytes": len(data),
            "sha256": meta["sha256"],
            "transform": {},
            "source_order": 0,
        }
        validate_asset(asset)
        directory = self._directory(project_id)
        final = directory / f"{identifier}.png"
        if final.exists():
            raise ValidationError("素材已存在")
        temporary = directory / f".{identifier}.part"
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(final)
            atomic_json(directory / f"{identifier}.json", asset)
        except BaseException:
            temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise
        return asset

    def get(self, project_id: str, asset_id: str) -> dict:
        directory = self._directory(project_id)
        asset = read_json(directory / f"{validate_id(asset_id)}.json")
        validate_asset(asset)
        if asset["id"] != asset_id or asset["project_id"] != project_id:
            raise ValidationError("素材不屬於此專案")
        return asset

    def path(self, project_id: str, asset_id: str) -> Path:
        asset = self.get(project_id, asset_id)
        path = self.root / asset["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValidationError("素材路徑超出專案")
        if not path.is_file():
            raise ValidationError("素材檔案遺失")
        return path
