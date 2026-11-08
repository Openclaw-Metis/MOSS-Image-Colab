import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from moss_studio.adapters.transport import CHECKS, TransportEvidence
from moss_studio.domain.contracts import ValidationError
from moss_studio.services.capabilities import artifact_gaps, load_capabilities, require_released
from moss_studio.services.resources import l4_preflight


def test_transport_requires_every_real_check_and_no_quick_sse():
    checks = dict.fromkeys(CHECKS, True)
    TransportEvidence("quick_polling", checks, False).require_pass()
    for mode, values, sse in [
        ("quick_polling", checks, True),
        ("share", checks, False),
        ("named", {**checks, "auth": False}, False),
        ("named", {}, False),
    ]:
        with pytest.raises(ValidationError):
            TransportEvidence(mode, values, sse).require_pass()


def test_unverified_capability_and_artifact_cannot_release():
    assert "revision" in artifact_gaps({"id": "candidate"})
    for state in ("unverified", "blocked", "verified", "released"):
        with pytest.raises(ValidationError):
            require_released({"state": state})
    require_released(
        {"state": "released", "evidence": ["actual-report"], "workflow_hash": "a" * 64}
    )


def test_capability_file_drives_ui_wording_and_rejects_unknown_states(tmp_path):
    root = Path(__file__).resolve().parents[2]
    capabilities = load_capabilities(root)
    assert capabilities["fast_8"]["state"] == "verified"
    assert capabilities["native_2048"]["class"] == "experimental"
    # Every id a tab script asks for must exist, or the UI would say "驗收狀態未知".
    scripts = "".join(
        p.read_text("utf-8") for p in (root / "src/moss_studio/ui/static").glob("*.js")
    )
    wanted = set(re.findall(r'capabilityLabel\([^,]+,"([a-z0-9_]+)"\)', scripts))
    assert len(wanted) >= 9 and wanted <= set(capabilities), wanted - set(capabilities)
    (tmp_path / "configs").mkdir()
    bad = {"capabilities": [{"id": "x", "class": "required", "state": "great", "reason": ""}]}
    (tmp_path / "configs/capabilities.json").write_text(json.dumps(bad), "utf-8")
    with pytest.raises(ValidationError):
        load_capabilities(tmp_path)


def test_l4_preflight_uses_actual_resources():
    report = {
        "gpus": [{"name": "NVIDIA L4", "total_bytes": 23 * 1024**3}],
        "ram_available_bytes": 40 * 1024**3,
        "disk_free_bytes": 100 * 1024**3,
    }
    assert l4_preflight(report, 20 * 1024**3) == []
    for field, value in [("gpus", []), ("ram_available_bytes", 1), ("disk_free_bytes", 1)]:
        candidate = deepcopy(report)
        candidate[field] = value
        assert l4_preflight(candidate)


def test_notebook_downloads_only_locked_models_and_leaves_base_to_the_model_tab():
    root = Path(__file__).resolve().parents[2]
    lock = json.loads((root / "configs/models.lock.json").read_text("utf-8"))
    notebook = json.loads((root / "notebooks/MOSS_Image_Colab.ipynb").read_text("utf-8"))
    code = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]

    def model_ids(src):
        lines = [x for x in src.splitlines() if "download([" in x or "_models = [" in x]
        return {name for x in lines for name in re.findall(r"'([a-z0-9_]+)'", x)}

    named = set().union(*map(model_ids, code))
    assert named and named <= {a["id"] for a in lock["artifacts"]}
    setup = next(src for src in code if src.startswith("# @title 2."))
    # Cell 2 fetches what every default UI path needs, never the optional 10 GB Base.
    default_paths = {"sft_bf16", "qwen_int8", "vae_small", "dmd8_lora", "edit_sft"}
    assert default_paths | {"color_depth", "moge3_vitg"} <= model_ids(setup)
    assert "base_bf16" not in setup
    assert 'DOWNLOAD_FEATURE_MODELS = True # @param {type:"boolean"}' in setup
