"""The examples shown in the UI must stay the pre-registered cases that passed on the GPU."""

import json
from pathlib import Path

from moss_studio.domain.contracts import new_id
from moss_studio.domain.layout import compile_layout

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = json.loads((ROOT / "configs/examples.json").read_text(encoding="utf-8"))


def _source(example: dict) -> dict:
    path, _, pointer = example["source"].partition("#")
    document = json.loads((ROOT / path).read_text(encoding="utf-8"))
    section, _, case_id = pointer.rpartition("/")
    cases = document[section] if section else document["cases"]
    return next(case for case in cases if case["id"] == case_id)


def test_examples_match_their_registered_cases():
    for tab in ("t2i", "edit", "inpaint", "control"):
        assert EXAMPLES[tab]
        for example in EXAMPLES[tab]:
            case = _source(example)
            assert example["prompt"] == case.get("prompt", case.get("caption")), example["id"]
            assert example["label"] and example["hint"]
            if tab == "t2i":
                for key in ("width", "height", "seed"):
                    assert example[key] == case[key], (example["id"], key)
            if "geometry" in example:
                assert example["geometry"] == case["geometry"]
    assert len({e["id"] for e in EXAMPLES["t2i"]}) == len(EXAMPLES["t2i"])


def test_t2i_examples_are_submittable():
    profiles = {
        json.loads(p.read_text(encoding="utf-8"))["id"]
        for p in (ROOT / "configs/profiles").glob("*.json")
    }
    for example in EXAMPLES["t2i"]:
        assert example["profile_id"] in profiles
        assert example["width"] % 16 == 0 and example["height"] % 16 == 0
        if "layout_items" in example:
            items = [
                {**item, "id": new_id(), "z_order": index}
                for index, item in enumerate(example["layout_items"])
            ]
            layout = compile_layout(example["prompt"], items, example["width"], example["height"])
            assert [item["label"] for item in layout["items"]] == ["text", "object"]
