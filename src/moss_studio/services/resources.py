"""Read actual resources; subscription names do not imply GPU allocation."""

import csv
import platform
import shutil
import subprocess
from pathlib import Path

from moss_studio.domain.contracts import now


def inspect_runtime(root: Path) -> dict:
    memory = {}
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.split()[0]) * 1024
    gpus, gpu_error = [], None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        for name, driver, total, free in csv.reader(result.stdout.splitlines()):
            gpus.append(
                {
                    "name": name.strip(),
                    "driver": driver.strip(),
                    "total_bytes": int(total) * 1024**2,
                    "free_bytes": int(free) * 1024**2,
                }
            )
    except (OSError, subprocess.SubprocessError, ValueError):
        gpu_error = "E_GPU_PROFILE：無法讀取 NVIDIA GPU"
    disk = shutil.disk_usage(root)
    return {
        "timestamp": now(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "ram_total_bytes": memory.get("MemTotal"),
        "ram_available_bytes": memory.get("MemAvailable"),
        "disk_free_bytes": disk.free,
        "gpus": gpus,
        "gpu_error": gpu_error,
    }


def l4_preflight(report: dict, remaining_download_bytes: int = 0) -> list[str]:
    errors = []
    gpus = report["gpus"]
    if len(gpus) != 1 or "L4" not in gpus[0]["name"]:
        errors.append("需要單一 NVIDIA L4；本設定尚未驗證其他 GPU")
    elif gpus[0]["total_bytes"] < 22 * 1024**3:
        errors.append("L4 顯存不足已宣告設定")
    if (report.get("ram_available_bytes") or 0) < 6 * 1024**3:
        errors.append("可用系統記憶體須至少 6 GiB")
    if report["disk_free_bytes"] < remaining_download_bytes + 10 * 1024**3:
        errors.append("磁碟須容納剩餘下載及 10 GiB 工作空間")
    return errors
