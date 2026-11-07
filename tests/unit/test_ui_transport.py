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
