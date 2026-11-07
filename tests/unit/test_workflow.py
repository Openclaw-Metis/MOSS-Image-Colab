import json
from copy import deepcopy
from pathlib import Path

import pytest

from moss_studio.adapters.workflow import compile_t2i, validate_nodes, workflow_hash
from moss_studio.domain.contracts import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_immutable_graph_compilation_and_no_profile_residue(job_spec):
    template = json.loads((ROOT / "workflows/t2i.json").read_text())
    profile = json.loads((ROOT / "configs/profiles/quality50.json").read_text())
    registry = {
        a["id"]: a for a in json.loads((ROOT / "configs/models.lock.json").read_text())["artifacts"]
    }
    original = deepcopy(template)
    graph = compile_t2i(job_spec, template, profile, registry)
    assert graph["7"]["inputs"]["steps"] == 50
    assert graph["21"]["inputs"]["single_layers"] == "22"
    assert graph["20"]["inputs"]["shift"] == 5
    assert template == original
    assert workflow_hash(graph) == workflow_hash(deepcopy(graph))
    custom = {**profile, "slg": None, "shift": None}
    other = compile_t2i(job_spec, template, custom, registry)
    assert "20" not in other and "21" not in other
    assert other["7"]["inputs"]["model"] == ["1", 0]
    assert graph != other


def test_actual_node_contract_rejects_missing_weights():
    graph = {"1": {"class_type": "Loader", "inputs": {"name": "missing.safetensors"}}}
    info = {"Loader": {"input": {"required": {"name": [["ready.safetensors"]]}}}}
    with pytest.raises(ValidationError):
        validate_nodes(graph, info)
    with pytest.raises(ValidationError):
        validate_nodes(graph, {})
