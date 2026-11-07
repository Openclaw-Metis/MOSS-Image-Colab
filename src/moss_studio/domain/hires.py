"""High-resolution path: successive pixel-space upscale + re-sample passes (spec v1.3 C2).

Each pass enlarges by at most 1.5×, sizes stay multiples of 16, and the final size is the
requested target (≤ 2048² total). Upscaling the latent directly is avoided upstream because
the re-sample cannot recover the lost detail.
"""

import math

from moss_studio.domain.contracts import ValidationError

MAX_PIXELS = 2048 * 2048
NATIVE_LIMIT = 2_166_784  # 1472² — the "≤ 2.2 MP" native tier


def _align(value: float) -> int:
    return max(16, round(value / 16) * 16)


def plan_passes(source: tuple[int, int], target: tuple[int, int], max_scale: float = 1.5):
    sw, sh = source
    tw, th = target
    if min(sw, sh, tw, th) <= 0 or tw % 16 or th % 16:
        raise ValidationError("目標寬高必須是 16 的倍數")
    if tw * th > MAX_PIXELS:
        raise ValidationError("放大上限為 2048×2048（約 4.2 MP）")
    if tw <= sw or th <= sh:
        raise ValidationError("目標尺寸必須大於來源圖")
    if abs((tw / th) / (sw / sh) - 1) > 0.02:
        raise ValidationError("放大不可改變長寬比")
    count = math.ceil(math.log(tw / sw) / math.log(max_scale) - 1e-9)
    ratio = (tw / sw) ** (1 / count)
    sizes = [(_align(sw * ratio**i), _align(sh * ratio**i)) for i in range(1, count)]
    return [*sizes, (tw, th)]
