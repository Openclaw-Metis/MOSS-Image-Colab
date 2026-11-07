"""AC-19 fixture integrity: cases are frozen before any model run and must all compile."""

import json
from pathlib import Path

from moss_studio.domain.contracts import new_id
from moss_studio.domain.layout import compile_layout

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/zh_tw_layouts.json"
# Characters whose Traditional form differs from Simplified; at least one per case title set.
TRADITIONAL_ONLY = set("臺灣鐵節龍會麵閱豐藝週須備與飲遠邊夜鬱聽見間慢燈畫館")


def test_ten_fixed_cases_compile_with_unique_ids_and_seeds():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    assert len(cases) == 10
    assert len({c["id"] for c in cases}) == 10
    assert len({c["seed"] for c in cases}) == 10
    for case in cases:
        texts = [i["text"] for i in case["items"] if i["label"] == "text"]
        assert texts, case["id"]
        assert set("".join(texts)) & TRADITIONAL_ONLY, case["id"]
        assert len(case["features"]) == 3
        assert case["width"] * case["height"] <= 2_166_784
        items = [{**i, "id": new_id(), "z_order": n} for n, i in enumerate(case["items"])]
        compiled = compile_layout(case["caption"], items, case["width"], case["height"])
        assert [i.get("text") for i in compiled["items"] if i["label"] == "text"] == texts
