from copy import deepcopy

import pytest

from moss_studio.adapters.transport import CHECKS, TransportEvidence
from moss_studio.domain.contracts import ValidationError
from moss_studio.services.capabilities import artifact_gaps, require_released
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
