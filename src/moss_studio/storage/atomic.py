"""Colab/Linux durable writes and inter-process locking."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from moss_studio.domain.contracts import ValidationError, canonical


def private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise ValidationError("拒絕符號連結目錄")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


@contextmanager
def file_lock(path: Path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_json(path: Path, value: dict) -> None:
    data = canonical(value).encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as stream:
        return json.load(stream)
