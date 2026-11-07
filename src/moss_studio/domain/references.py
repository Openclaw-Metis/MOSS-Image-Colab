"""Reference-image rules for instruction edit: ordered slots and the engine's output size."""

import math

from moss_studio.domain.contracts import ValidationError


def scaled_to_total_pixels(width: int, height: int, megapixels: float = 1.0, step: int = 16):
    """Same arithmetic as ComfyUI ImageScaleToTotalPixels @1332fab (Python round, step align).

    The edit graph scales the main image with that node and sizes the latent from it, so the
    snapshot's width/height must equal this result or the saved output check fails.
    """
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValidationError("圖片尺寸無效")
    total = megapixels * 1024 * 1024
    scale_by = math.sqrt(total / (width * height))
    return (
        round(width * scale_by / step) * step,
        round(height * scale_by / step) * step,
    )


def renumber(slots: list) -> tuple[list, dict]:
    """Compacts empty slots. Returns the new list and old→new picture numbers for confirmation."""
    filled = [(index + 1, value) for index, value in enumerate(slots) if value is not None]
    mapping = {old: new for new, (old, _) in enumerate(filled, start=1)}
    return [value for _, value in filled], mapping
