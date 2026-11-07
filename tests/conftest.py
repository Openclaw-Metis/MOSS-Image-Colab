import pytest

from moss_studio.domain.contracts import new_id


@pytest.fixture
def job_spec():
    return {
        "project_id": new_id(),
        "client_request_id": new_id(),
        "project_revision": 0,
        "task": "t2i",
        "profile_id": "quality50_v1",
        "model_artifact_id": "sft_bf16",
        "prompt": "米白色山景旅遊海報",
        "negative_prompt": "",
        "width": 1024,
        "height": 1024,
        "seed": 42001,
        "references": [],
        "layout": None,
        "mask_asset_id": None,
        "control": None,
        "lora_stack": [],
    }
