from copy import deepcopy

import pytest

from moss_studio.domain.contracts import ValidationError, new_id, validate_asset, validate_job_spec


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("width", 1000),
        ("width", True),
        ("height", 0),
        ("width", 4112),
        ("seed", -1),
        ("task", "arbitrary_code"),
        ("prompt", " "),
        ("project_revision", True),
        ("references", [{"asset_id": new_id(), "slot": 2}]),
        ("negative_prompt", None),
        ("mask_asset_id", "../x"),
    ],
)
def test_invalid_job_input(job_spec, field, value):
    job_spec[field] = value
    with pytest.raises(ValidationError):
        validate_job_spec(job_spec)


def test_four_reference_order_and_task_requirements(job_spec):
    validate_job_spec(job_spec)
    job_spec["task"] = "instruction_edit"
    with pytest.raises(ValidationError):
        validate_job_spec(job_spec)
    job_spec["references"] = [{"asset_id": new_id(), "slot": i} for i in range(1, 5)]
    validate_job_spec(job_spec)
    job_spec["references"].append({"asset_id": new_id(), "slot": 5})
    with pytest.raises(ValidationError):
        validate_job_spec(job_spec)
    job_spec["references"] = job_spec["references"][:1]
    job_spec["task"] = "inpaint"
    with pytest.raises(ValidationError):
        validate_job_spec(job_spec)
    job_spec["mask_asset_id"] = new_id()
    validate_job_spec(job_spec)


def test_asset_metadata_and_boundary():
    asset = {
        "id": new_id(),
        "project_id": new_id(),
        "kind": "input",
        "path": "assets/a.png",
        "mime": "image/png",
        "width": 1024,
        "height": 1024,
        "bytes": 100,
        "sha256": "a" * 64,
        "transform": {},
        "source_order": 1,
    }
    validate_asset(asset)
    for field, value in [
        ("path", "../a.png"),
        ("path", "/tmp/a.png"),
        ("path", "..\\a.png"),
        ("sha256", "g" * 64),
        ("width", 20_000_000),
        ("bytes", 257 * 1024**2),
    ]:
        candidate = deepcopy(asset)
        candidate[field] = value
        with pytest.raises(ValidationError):
            validate_asset(candidate)
