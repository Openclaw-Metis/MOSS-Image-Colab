from pathlib import Path

import pytest

pytest.importorskip("gradio")
from moss_studio.services.studio import StudioService  # noqa: E402
from moss_studio.ui.app import build_ui  # noqa: E402


def test_workbench_has_no_queued_or_heartbeat_sse_dependency(tmp_path):
    service = StudioService(Path(__file__).resolve().parents[2], tmp_path)
    try:
        demo = build_ui(service)
        assert not demo.config["connect_heartbeat"]
        assert all(not event["backend_fn"] for event in demo.config["dependencies"])
    finally:
        service.close()


def test_every_element_id_the_scripts_look_up_exists_in_the_markup(tmp_path):
    """A renamed id fails silently in the browser (null.textContent), so check it here."""
    import re

    from moss_studio.ui import app

    root = Path(__file__).resolve().parents[2]
    service = StudioService(root, tmp_path)
    try:
        demo = build_ui(service)
        markup = app.PROJECT_MENU_HTML + "".join(
            str(component["props"].get("value", "")) + str(component["props"].get("elem_id", ""))
            for component in demo.config["components"]
        )
    finally:
        service.close()
    declared = set(re.findall(r'id="([\w-]+)"', markup)) | {"moss-generate", "moss-cancel"}
    scripts = "".join(
        path.read_text(encoding="utf-8")
        for path in (root / "src/moss_studio/ui/static").glob("*.js")
    )
    looked_up = set(re.findall(r'\$\("([\w-]+)"\)', scripts))
    assert looked_up and looked_up <= declared, sorted(looked_up - declared)
    # Ids built from a prefix: result panels and status lines every tab relies on.
    for prefix in ("moss", "edit", "inpaint", "control", "hires"):
        for suffix in ("result", "result-empty", "result-summary", "result-actions"):
            assert f"{prefix}-{suffix}" in declared
        assert f"{prefix}-status" in declared
