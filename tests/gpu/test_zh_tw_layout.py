"""Expensive AC-19 generation run: explicitly enable only on the isolated product runtime.

This only checks that all ten fixed cases were generated. Glyph accuracy is scored by a
person in scoring.json; this test never reports AC-19 as passed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.gpu
def test_zh_tw_cases_generated_for_human_scoring():
    if os.environ.get("MOSS_RUN_LONG_GPU") != "1":
        pytest.skip("Set MOSS_RUN_LONG_GPU=1 for ten actual 50-step layout runs")
    root = Path(__file__).resolve().parents[2]
    evidence = Path(os.environ["MOSS_EVIDENCE_ROOT"]) / "zh_tw"
    subprocess.run(
        [sys.executable, str(root / "scripts/zh_tw_layout_eval.py"), str(evidence)], check=True
    )
    report = json.loads((evidence / "report.json").read_text(encoding="utf-8"))
    assert report["generated_all"]
    assert all(sample["nonblack"] for sample in report["samples"].values())
