import json

import pytest

from moss_studio.domain.contracts import ValidationError, new_id
from moss_studio.domain.layout import compile_layout, normalize_drag, parse_layout

BOXES = [
    (0, 0, 1, 1),
    (0.1, 0.1, 0.9, 0.9),
    (0, 0.2, 0.3, 0.5),
    (0.7, 0.7, 1, 1),
    (0.2, 0, 0.8, 0.1),
    (0.1, 0.8, 0.9, 1),
    (0.25, 0.25, 0.75, 0.75),
    (0.5, 0.1, 0.6, 0.6),
    (0.1, 0.5, 0.6, 0.6),
    (0.001, 0.001, 0.999, 0.999),
]


@pytest.mark.parametrize(("width", "height"), [(1024, 1024), (1536, 1024), (1024, 1536)])
@pytest.mark.parametrize("box", BOXES)
def test_thirty_contain_drag_and_centralized_roundtrips(width, height, box):
    vw, vh = 1000, 600
    scale = min(vw / width, vh / height)
    ox, oy = (vw - width * scale) / 2, (vh - height * scale) / 2
    x0, y0, x1, y1 = box
    start = (ox + x0 * width * scale, oy + y0 * height * scale)
    end = (ox + x1 * width * scale, oy + y1 * height * scale)
    # Reverse drags are normalized by the pointer handler, never by imported JSON.
    normalized = normalize_drag(end, start, width, height, vw, vh)
    assert normalized == pytest.approx(box)
    item = {
        "id": new_id(),
        "label": "text",
        "caption": "深藍標題",
        "text": "山間慢旅",
        "normalized_bbox": normalized,
        "z_order": 0,
    }
    payload = compile_layout("米白色山景海報", [item], width, height)
    parsed = parse_layout(json.dumps(payload), width, height, [item])
    assert parsed["items"][0]["id"] == item["id"]
    for actual, expected, size in zip(
        parsed["items"][0]["normalized_bbox"], box, [width, height, width, height], strict=True
    ):
        assert abs(actual - expected) * size <= 1


@pytest.mark.parametrize(
    "box",
    [[0, 0, 0, 1], [1, 0, 0, 1], [-1, 0, 1, 1], [0, 0, float("nan"), 1], [0, 0, float("inf"), 1]],
)
def test_invalid_boxes_are_not_silently_clamped_on_import(box):
    item = {"id": new_id(), "label": "object", "caption": "山景", "normalized_bbox": box}
    with pytest.raises(ValidationError):
        compile_layout("測試", [item], 1024, 1024)


def test_raw_json_and_kind_contracts():
    with pytest.raises(ValidationError):
        parse_layout('{"items":', 1024, 1024)
    item = {"id": new_id(), "label": "object", "caption": "山景", "normalized_bbox": [0, 0, 1, 1]}
    payload = compile_layout("測試", [item], 1024, 1024)
    payload["items"][0]["bbox"] = [0, 0, -512, -512]
    with pytest.raises(ValidationError):
        parse_layout(payload, 1024, 1024)
    item["text"] = "不可混用"
    with pytest.raises(ValidationError):
        compile_layout("測試", [item], 1024, 1024)
