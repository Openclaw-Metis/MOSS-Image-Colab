"""GPU batch E (Stage 9) pieces that no earlier script covers: AC-18 general generation and the
CPU/HTTP contract suite run on the release runtime itself.

Usage on the L4 runtime (app already running on 127.0.0.1:7860):
    MOSS_STUDIO_PASSWORD=... python scripts/batch_e_eval.py <evidence-dir> [--only cpu ac18]

The notebook's batch E cell also reruns benchmark_http.py (AC-04, AC-06) and the batch C/D
scripts into the same evidence folder; AC-01 (rerun without a second engine or re-download) is
recorded by the cell itself because it needs the notebook's bootstrap objects.
"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

from batch_runner import BatchReport  # noqa: E402
from product_client import ProductClient  # noqa: E402

from moss_studio.storage.atomic import atomic_json  # noqa: E402

FIXTURE = REPOSITORY / "tests/fixtures/ac18_cases.json"
SECTIONS = ("cpu", "ac18")


def run_cpu(destination: Path) -> dict:
    """Unit + integration suites (AC-02, 05, 07, 14, 16, 17 contracts) on this runtime."""
    junit = destination / "cpu_tests.xml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            "tests/unit",
            "tests/integration",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
    )
    suite = ElementTree.parse(junit).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    counts = {k: int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}
    result = {**counts, "exit_code": completed.returncode, "tail": completed.stdout[-2000:]}
    result["passed"] = completed.returncode == 0 and counts["failures"] == counts["errors"] == 0
    atomic_json(destination / "cpu_tests.json", result)
    return result


def run_ac18(destination: Path, base_url: str) -> dict:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with ProductClient(base_url) as client:
        report = BatchReport(destination / "ac18", client, "AC-18 一般生成", FIXTURE)
        for case in cases["cases"]:
            report.run(
                "general",
                case["id"],
                lambda c=case: {
                    "profile_id": cases["profile_id"],
                    "prompt": c["prompt"],
                    "width": c["width"],
                    "height": c["height"],
                    "seed": str(c["seed"]),
                },
            )
        scoring = report.destination / "scoring.json"
        if not scoring.exists():
            scoring.write_text(
                json.dumps(
                    {
                        "criteria": cases["scoring"],
                        "general": {
                            c["id"]: {
                                "features": c["features"],
                                "features_met": None,
                                "severe_artifact": None,
                                "notes": "",
                            }
                            for c in cases["cases"]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        general = report.data.get("general", {})
        report.data["generated_all"] = len(general) == len(cases["cases"]) and all(
            e["status"] == "succeeded" and e.get("nonblack") for e in general.values()
        )
        report.save()
        return report.data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU 批次 E：AC-18 一般生成與契約測試")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", nargs="+", choices=SECTIONS, default=list(SECTIONS))
    # Another loopback port targets the fake-engine dev server for a dry run of this script;
    # such a run is never GPU evidence.
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    if "cpu" in args.only:
        print(json.dumps({"cpu": run_cpu(args.destination)["passed"]}), flush=True)
    if "ac18" in args.only:
        outcome = run_ac18(args.destination, args.base_url)
        print(json.dumps({"ac18_generated_all": outcome["generated_all"]}), flush=True)
