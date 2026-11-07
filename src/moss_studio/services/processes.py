"""Linux process ownership for rerunnable notebook bootstraps.

PID alone is not ownership: verify start ticks and command before adopting/stopping.
"""

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

from moss_studio.domain.contracts import ConflictError, ValidationError
from moss_studio.storage.atomic import atomic_json, file_lock, private_dir, read_json


def identity(pid: int) -> dict | None:
    try:
        base = Path(f"/proc/{pid}")
        fields = (base / "stat").read_text().rsplit(") ", 1)[1].split()
        if fields[0] == "Z":
            return None
        command = (base / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")
        if not command or not command[0]:
            return None
        return {
            "pid": pid,
            "start_ticks": int(fields[19]),
            "command": [part.decode() for part in command],
        }
    except (OSError, ValueError, IndexError):
        return None


def owns_port(pid: int, port: int) -> bool:
    try:
        sockets = {p.readlink().as_posix() for p in Path(f"/proc/{pid}/fd").iterdir()}
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if (
                fields[1] == f"0100007F:{port:04X}"
                and fields[3] == "0A"
                and f"socket:[{fields[9]}]" in sockets
            ):
                return True
    except OSError:
        pass
    return False


class ManagedProcess:
    def __init__(self, runtime_root: Path, name: str):
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz_-" for c in name):
            raise ValidationError("程序名稱無效")
        self.root = private_dir(Path(runtime_root))
        self.record = self.root / f"{name}.json"
        self.lock = self.root / f"{name}.lock"
        self.log = self.root / f"{name}.log"
        self.child = None

    def start(self, command: list[str], cwd: Path, port: int, health, timeout: float = 60) -> dict:
        with file_lock(self.lock):
            if self.record.exists():
                recorded = read_json(self.record)
                current = identity(recorded["pid"])
                if current == recorded:
                    if current["command"] != command or not owns_port(current["pid"], port):
                        raise ConflictError("現有程序的命令或連接埠不同，請先停止本工具程序")
                    health()
                    return {**current, "reused": True}
                if current is not None:
                    raise ConflictError("PID 已被其他程序使用，不會採用或停止它")
                self.record.unlink()
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise ConflictError("連接埠已被其他程序使用")
            with self.log.open("ab") as log:
                child = subprocess.Popen(
                    command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
                )
            self.child = child
            record = identity(child.pid)
            identity_deadline = time.monotonic() + min(5, timeout)
            while record is None and child.poll() is None and time.monotonic() < identity_deadline:
                time.sleep(0.01)
                record = identity(child.pid)
            if record is None:
                child.wait(timeout=1)
                raise RuntimeError("程序啟動失敗，請查看本機日誌")
            atomic_json(self.record, record)
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise RuntimeError("程序啟動失敗，請查看本機日誌")
                    if owns_port(child.pid, port):
                        try:
                            health()
                            return {**record, "reused": False}
                        except (OSError, RuntimeError):
                            pass
                    time.sleep(0.1)
                raise TimeoutError("啟動逾時，請查看本機日誌")
            except BaseException:
                self._stop_owned(record)
                self.record.unlink(missing_ok=True)
                raise

    def _stop_owned(self, record: dict) -> None:
        if identity(record["pid"]) != record:
            return
        os.kill(record["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 5
        while identity(record["pid"]) == record and time.monotonic() < deadline:
            time.sleep(0.05)
        if identity(record["pid"]) == record:
            os.kill(record["pid"], signal.SIGKILL)
        if self.child is not None and self.child.pid == record["pid"]:
            self.child.wait(timeout=5)

    def stop(self) -> None:
        with file_lock(self.lock):
            if not self.record.exists():
                return
            record = read_json(self.record)
            if identity(record["pid"]) not in (None, record):
                raise ConflictError("PID 屬於其他程序，不會停止它")
            self._stop_owned(record)
            self.record.unlink(missing_ok=True)
