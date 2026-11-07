"""Contain canvas coordinates ↔ normalized boxes ↔ MOSS centralized yxyx JSON."""

import json
import math

from moss_studio.domain.contracts import ValidationError, new_id, validate_id


def finite(value) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValidationError("座標必須是有限數值")
    return float(value)


def canvas_point(u, v, width, height, viewport_width, viewport_height) -> tuple[float, float]:
    values = [finite(x) for x in (u, v, width, height, viewport_width, viewport_height)]
    u, v, width, height, viewport_width, viewport_height = values
    if min(width, height, viewport_width, viewport_height) <= 0:
        raise ValidationError("畫布及可視區大小必須大於零")
    scale = min(viewport_width / width, viewport_height / height)
    ox, oy = (viewport_width - width * scale) / 2, (viewport_height - height * scale) / 2
    return (min(width, max(0, (u - ox) / scale)), min(height, max(0, (v - oy) / scale)))


def normalized_bbox(values) -> list[float]:
    if not isinstance(values, tuple | list) or len(values) != 4:
        raise ValidationError("bbox 必須包含四個座標")
    x0, y0, x1, y1 = [finite(value) for value in values]
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValidationError("框不可為零面積、反向或超出畫布")
    return [x0, y0, x1, y1]


def normalize_drag(start, end, width, height, viewport_width, viewport_height) -> list[float]:
    x0, y0 = canvas_point(*start, width, height, viewport_width, viewport_height)
    x1, y1 = canvas_point(*end, width, height, viewport_width, viewport_height)
    return normalized_bbox(
        [min(x0, x1) / width, min(y0, y1) / height, max(x0, x1) / width, max(y0, y1) / height]
    )


def compile_layout(caption: str, items: list[dict], width: int, height: int) -> dict:
    if not isinstance(caption, str) or not caption.strip():
        raise ValidationError("請輸入整張圖片的描述")
    if not isinstance(items, list) or not 1 <= len(items) <= 32:
        raise ValidationError("排版需要 1～32 個框")
    if (
        type(width) is not int
        or type(height) is not int
        or min(width, height) <= 0
        or width % 16
        or height % 16
    ):
        raise ValidationError("畫布寬高必須為正整數且為 16 的倍數")
    result, identifiers = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("框資料必須是物件")
        if set(item) - {"id", "label", "caption", "text", "normalized_bbox", "z_order"}:
            raise ValidationError("框含未知欄位")
        identifier = validate_id(item.get("id"))
        if identifier in identifiers:
            raise ValidationError("框識別碼不可重複")
        identifiers.add(identifier)
        label, description = item.get("label"), item.get("caption")
        if label not in {"text", "object"} or not isinstance(description, str) or not description:
            raise ValidationError("框種類及描述必填")
        if label == "text" and (not isinstance(item.get("text"), str) or not item["text"].strip()):
            raise ValidationError("文字框需填寫要顯示的文字")
        if label == "object" and "text" in item:
            raise ValidationError("物件框不可附帶 text 欄位")
        x0, y0, x1, y1 = normalized_bbox(item.get("normalized_bbox"))
        px = [
            math.floor(v * size + 0.5)
            for v, size in [(x0, width), (y0, height), (x1, width), (y1, height)]
        ]
        if px[0] == px[2] or px[1] == px[3]:
            raise ValidationError("框小於一個原圖像素")
        output = {
            "label": label,
            "caption": description,
            "bbox": [
                px[1] - height // 2,
                px[0] - width // 2,
                px[3] - height // 2,
                px[2] - width // 2,
            ],
        }
        if label == "text":
            output["text"] = item["text"]
        result.append(output)
    return {
        "summary": {"meta": ["poster"], "canvas": "single", "caption": caption},
        "items": result,
        "bbox_coord_space": "abs_centralized",
        "bbox_format": "yxyx",
    }


def parse_layout(value: str | dict, width: int, height: int, previous: list | None = None) -> dict:
    if (
        type(width) is not int
        or type(height) is not int
        or min(width, height) <= 0
        or width % 16
        or height % 16
    ):
        raise ValidationError("畫布寬高必須為正整數且為 16 的倍數")
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError) as exc:
        raise ValidationError("排版 JSON 無法解析；保留上一次有效畫布") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"summary", "items", "bbox_coord_space", "bbox_format"}
        or value["bbox_coord_space"] != "abs_centralized"
        or value["bbox_format"] != "yxyx"
    ):
        raise ValidationError("排版必須是中心原點 abs_centralized / yxyx 格式")
    summary = value["summary"]
    if (
        not isinstance(summary, dict)
        or set(summary) != {"meta", "canvas", "caption"}
        or not isinstance(summary["meta"], list)
        or summary["canvas"] != "single"
    ):
        raise ValidationError("summary 格式不符")
    if not isinstance(value["items"], list):
        raise ValidationError("items 必須是清單")
    items = []
    for i, item in enumerate(value["items"]):
        if (
            not isinstance(item, dict)
            or set(item) - {"label", "caption", "text", "bbox"}
            or not isinstance(item.get("bbox"), list)
            or len(item["bbox"]) != 4
        ):
            raise ValidationError("排版框欄位不符")
        y0, x0, y1, x1 = [finite(v) for v in item["bbox"]]
        bbox = normalized_bbox(
            [
                (x0 + width / 2) / width,
                (y0 + height / 2) / height,
                (x1 + width / 2) / width,
                (y1 + height / 2) / height,
            ]
        )
        identifier = previous[i]["id"] if previous and i < len(previous) else new_id()
        result = {
            "id": identifier,
            "label": item.get("label"),
            "caption": item.get("caption"),
            "normalized_bbox": bbox,
            "z_order": i,
        }
        if "text" in item:
            result["text"] = item["text"]
        items.append(result)
    compile_layout(summary["caption"], items, width, height)
    return {"caption": summary["caption"], "items": items}
