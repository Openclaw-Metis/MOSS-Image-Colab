"""Inpaint masks: white = repaint, black = keep. Feathering has finite support.

Guarantee tested by AC-09: every pixel farther than feather_radius_px from the painted area is
copied from the source unchanged. Only the band inside that radius blends with engine output.
"""

import io

import numpy as np
from PIL import Image, ImageFilter

from moss_studio.domain.contracts import ValidationError


def feather_radius(width: int, height: int, edge_softness: float) -> int:
    """Product mapping of edge_softness (0–1, default 0.15): 1024² at 0.15 → 15 px."""
    if not isinstance(edge_softness, int | float) or not 0 <= edge_softness <= 1:
        raise ValidationError("柔邊必須在 0～1 之間")
    return round(0.1 * min(width, height) * edge_softness)


def binary_mask(image: Image.Image) -> np.ndarray:
    """A brush layer with transparency: any opaque stroke counts, black or white brush alike.
    An opaque black/white image: white (luminance > 127) is selected."""
    if "A" in image.getbands():
        alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
        if (alpha < 255).any():
            return alpha > 127
    return np.asarray(image.convert("L"), dtype=np.uint8) > 127


def check_coverage(mask: np.ndarray, *, confirm_full: bool) -> None:
    if not mask.any():
        raise ValidationError("E_MASK_EMPTY：請先塗抹要修改的區域")
    if mask.all() and not confirm_full:
        raise ValidationError("遮罩涵蓋整張圖；請勾選「確認整張重繪」後再提交")


def feathered_alpha(mask: np.ndarray, radius: int) -> np.ndarray:
    """1.0 inside the mask, ramping to 0 within `radius` px outside it, exactly 0 beyond."""
    selected = mask.astype(np.float32)
    if radius <= 0:
        return selected
    image = Image.fromarray((mask * 255).astype(np.uint8))
    support = image
    remaining = radius
    while remaining > 0:  # MaxFilter(3) grows the support by exactly 1 px per pass
        support = support.filter(ImageFilter.MaxFilter(3))
        remaining -= 1
    blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(radius / 2)), dtype=np.float32)
    ramp = np.clip(blurred / 127.5, 0.0, 1.0)
    alpha = np.maximum(selected, ramp) * (np.asarray(support) > 0)
    return alpha.astype(np.float32)


def resize_mask(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Binary masks are resized with nearest neighbour so they stay binary."""
    image = Image.fromarray((mask * 255).astype(np.uint8)).resize(size, Image.Resampling.NEAREST)
    return np.asarray(image) > 127


def composite(source: Image.Image, generated: Image.Image, alpha: np.ndarray) -> Image.Image:
    if source.size != generated.size or alpha.shape != (source.height, source.width):
        raise ValidationError("輸出尺寸與遮罩不一致")
    original = np.asarray(source.convert("RGB"), dtype=np.float32)
    produced = np.asarray(generated.convert("RGB"), dtype=np.float32)
    weight = alpha[..., None]
    blended = np.rint(original * (1 - weight) + produced * weight)
    # Outside the support keep the exact source bytes, not a float round trip.
    result = np.where(weight > 0, blended, original).astype(np.uint8)
    return Image.fromarray(result)


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def mask_png(alpha: np.ndarray) -> bytes:
    """Grey-level mask for ComfyUI LoadImageMask (red channel), 255 = repaint."""
    return png_bytes(Image.fromarray(np.rint(alpha * 255).astype(np.uint8)).convert("RGB"))
