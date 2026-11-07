"""Expensive AC-04 run: explicitly enable only on the isolated product runtime."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.gpu
def test_product_sft_baseline_six_runs():
    if os.environ.get("MOSS_RUN_LONG_GPU") != "1":
        pytest.skip("Set MOSS_RUN_LONG_GPU=1 for warmup + five actual 50-step runs")
    root = Path(__file__).resolve().parents[2]
    evidence = Path(os.environ["MOSS_EVIDENCE_ROOT"]) / "stage2"
    subprocess.run(
        [sys.executable, str(root / "scripts/benchmark_http.py"), str(evidence)], check=True
    )
    report = json.loads((evidence / "benchmark.json").read_text(encoding="utf-8"))
    assert report["passed"]
    assert len([s for s in report["samples"] if not s["warmup"]]) == 5
