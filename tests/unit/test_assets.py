import io

import pytest
from PIL import Image, PngImagePlugin

from moss_studio.domain.contracts import ValidationError, new_id
from moss_studio.storage.assets import AssetStore


def test_asset_decode_metadata_strip_and_project_boundary(tmp_path):
    store = AssetStore(tmp_path)
    project_id = new_id()
    image = Image.new("RGB", (32, 48), "red")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("prompt", "private provenance must not be embedded")
    data = io.BytesIO()
    image.save(data, format="PNG", pnginfo=metadata)
    asset = store.import_image(project_id, data.getvalue())
    assert asset["width"] == 32 and asset["height"] == 48
    with Image.open(store.path(project_id, asset["id"])) as result:
        assert "prompt" not in result.info
    with pytest.raises(FileNotFoundError):
        store.get(new_id(), asset["id"])
    with pytest.raises(ValidationError):
        store.import_image(project_id, b"<!DOCTYPE html><p>not an image</p>")


def test_animated_and_oversized_inputs_rejected(tmp_path):
    store = AssetStore(tmp_path)
    image = Image.new("RGB", (10, 10), "blue")
    data = io.BytesIO()
    image.save(
        data, format="WEBP", save_all=True, append_images=[Image.new("RGB", (10, 10), "red")]
    )
    with pytest.raises(ValidationError):
        store.import_image(new_id(), data.getvalue())
    with pytest.raises(ValidationError):
        store.import_image(new_id(), b"x" * (20 * 1024**2 + 1))
