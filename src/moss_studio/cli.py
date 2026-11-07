"""CPU-safe environment inspection and lock auditing; never launches unverified services."""

import argparse
import json
from pathlib import Path

from moss_studio.services.capabilities import artifact_gaps
from moss_studio.services.resources import inspect_runtime, l4_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="MOSS Studio 環境與鎖定檢查")
    parser.add_argument("command", choices=["doctor", "audit-locks"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.command == "doctor":
        report = inspect_runtime(args.root)
        report["blockers"] = l4_preflight(report)
    else:
        models = json.loads((args.root / "configs/models.lock.json").read_text(encoding="utf-8"))
        report = {
            "artifacts": [
                {"id": artifact["id"], "gaps": artifact_gaps(artifact)}
                for artifact in models["artifacts"]
            ]
        }
        report["blockers"] = [a["id"] for a in report["artifacts"] if a["gaps"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
