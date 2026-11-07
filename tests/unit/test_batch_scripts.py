"""CPU checks for the GPU batch C/D scripts: frozen fixtures and the exact AC-09 measurement."""

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from moss_studio.domain.masks import binary_mask, composite, feather_radius, feathered_alpha

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import batch_c_eval  # noqa: E402
import batch_d_eval  # noqa: E402

CASES = json.loads((ROOT / "tests/fixtures/batch_c_cases.json").read_text(encoding="utf-8"))


def test_batch_c_fixture_is_consistent():
    fixtures = {f["id"] for f in CASES["fixtures"]}
    ids = [c["id"] for s in ("edit", "inpaint", "control", "vision") for c in CASES[s]]
    assert len(ids) == len(set(ids)) == 29
    for case in CASES["edit"] + CASES["vision"]:
        assert 1 <= len(case["refs"]) <= 4 and set(case["refs"]) <= fixtures
    for case in CASES["inpaint"] + CASES["control"]:
        assert case["source"] in fixtures
    for case in CASES["inpaint"]:
        x0, y0, x1, y1 = case["box"]
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and 0.05 <= case["denoise"] <= 1
    assert set(CASES["control_off"]) <= {c["id"] for c in CASES["control"]}
    assert {c["geometry"] for c in CASES["control"]} == {"mask", "depth"}
    for section in ("edit", "inpaint", "control", "vision"):
        assert all(len(c["features"]) == 3 for c in CASES[section])
    template = batch_c_eval.scoring_template(CASES)
    assert set(template["edit"]) == {c["id"] for c in CASES["edit"]}
    assert all(e["mapping_ok"] is None for e in template["edit"].values())


def test_box_mask_covers_exactly_the_normalised_box():
    mask = Image.open(io.BytesIO(batch_c_eval.box_mask((100, 200), [0.1, 0.5, 0.3, 1.0])))
    selected = binary_mask(mask)
    assert selected.shape == (200, 100)
    ys, xs = np.nonzero(selected)
    assert (xs.min(), xs.max(), ys.min(), ys.max()) == (10, 29, 100, 199)


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_preservation_measures_pixels_outside_the_feather_band():
    size = (320, 240)
    rng = np.random.default_rng(0)
    source = Image.fromarray(rng.integers(0, 255, (240, 320, 3), dtype=np.uint8))
    mask = batch_c_eval.box_mask(size, [0.25, 0.25, 0.6, 0.7])
    alpha = feathered_alpha(
        binary_mask(Image.open(io.BytesIO(mask))),
        feather_radius(*size, batch_c_eval.EDGE_SOFTNESS),
    )
    result = composite(source, Image.new("RGB", size, (0, 255, 0)), alpha)
    good = batch_c_eval.preservation(png(source), png(result), mask, size)
    assert good["outside_identical_ratio"] == 1.0 and good["inside_mean_abs_diff"] > 50
    assert good["feather_px"] == round(0.1 * 240 * 0.15)
    tampered = np.asarray(result).copy()
    tampered[0, 0] ^= 1  # one corner pixel far outside the band
    bad = batch_c_eval.preservation(png(source), png(Image.fromarray(tampered)), mask, size)
    assert bad["outside_identical_ratio"] < 1.0


def test_batch_d_compat_cases_cover_models_profiles_and_loras():
    class Report:
        project_id = "p"

        def upload(self, key, data, kind="input"):
            return {"id": f"{key}-id"}

    cases = dict(batch_d_eval.compat_cases(Report()))
    assert len(cases) == 10
    assert {c.get("model_artifact_id") for c in cases.values()} >= {"base_bf16", "qwen_int8"}
    assert sum("lora_stack" in c for c in cases.values()) == 3
    assert cases["inpaint_with_lora"]["mask_asset_id"] == "compat-mask-id"
