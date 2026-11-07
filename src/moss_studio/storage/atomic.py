"""Durable writes and inter-process locking.

Colab/Linux is the product runtime. The Windows branch exists only so maintainers can run
the CPU test suite on a Windows workstation; it must never weaken the POSIX path.
"""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from moss_studio.domain.contracts import ValidationError, canonical

if os.name == "nt":  # pragma: no cover - exercised only on Windows workstations
    import msvcrt
    import time

    def _lock(fd: int) -> None:
        # LK_LOCK sleeps a full second between its internal retries, which made contended
        # saves slow enough to trip test deadlines; poll the non-blocking form instead.
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.01)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def _sharing_retry(action):
        # Windows refuses to open a file that another thread is replacing, and refuses to
        # replace a file another thread has open (PermissionError); POSIX allows both.
        # Retry briefly so concurrent readers and atomic writers behave like on Linux.
        for _ in range(200):
            try:
                return action()
            except PermissionError:
                time.sleep(0.005)
        return action()

    def _open_nofollow(path: Path, flags: int, mode: int = 0o600) -> int:
        # Windows has no O_NOFOLLOW; refuse links explicitly before opening.
        if Path(path).is_symlink():
            raise ValidationError("拒絕符號連結檔案")
        return _sharing_retry(lambda: os.open(path, flags | getattr(os, "O_BINARY", 0), mode))

    def _replace(source, target) -> None:
        _sharing_retry(lambda: os.replace(source, target))

    def _sync_directory(path: Path) -> None:
        # Directories cannot be opened for fsync on Windows; os.replace is already atomic.
        return None

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _open_nofollow(path: Path, flags: int, mode: int = 0o600) -> int:
        return os.open(path, flags | os.O_NOFOLLOW, mode)

    def _replace(source, target) -> None:
        os.replace(source, target)

    def _sync_directory(path: Path) -> None:
        parent_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)


def private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise ValidationError("拒絕符號連結目錄")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


@contextmanager
def file_lock(path: Path):
    fd = _open_nofollow(path, os.O_CREAT | os.O_RDWR)
    try:
        _lock(fd)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value: dict) -> None:
    data = canonical(value).encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temp, path)
        _sync_directory(path.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    fd = _open_nofollow(path, os.O_RDONLY)
    with os.fdopen(fd, encoding="utf-8") as stream:
        return json.load(stream)
