"""SQLite job ledger: immutable snapshots, deduplication, ordered durable events."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from moss_studio.domain.contracts import (
    ConflictError,
    ValidationError,
    canonical,
    digest,
    new_id,
    now,
    validate_id,
    validate_job_spec,
)
from moss_studio.domain.jobs import TERMINAL, validate_transition
from moss_studio.storage.atomic import private_dir


class JobLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        private_dir(self.path.parent)
        if self.path.is_symlink():
            raise ValidationError("拒絕符號連結資料庫")
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValidationError("尚不支援此 ledger 版本")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, snapshot TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL, status TEXT NOT NULL,
                    comfy_prompt_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(project_id, request_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    job_id TEXT NOT NULL REFERENCES jobs(id), seq INTEGER NOT NULL,
                    timestamp TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(job_id, seq)
                );
                CREATE TRIGGER IF NOT EXISTS immutable_snapshot
                BEFORE UPDATE OF snapshot, snapshot_hash, project_id, request_id ON jobs
                BEGIN SELECT RAISE(ABORT, 'immutable job snapshot'); END;
                PRAGMA user_version=1;
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _event(db, job_id: str, event: str, payload: dict) -> None:
        seq = db.execute(
            "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)", (job_id, seq, now(), event, canonical(payload))
        )

    @staticmethod
    def _row(row) -> dict:
        if row is None:
            raise KeyError("找不到此工作")
        record = dict(row)
        record["snapshot"] = json.loads(record["snapshot"])
        return record

    def create(self, spec: dict) -> dict:
        snapshot = deepcopy(spec)
        validate_job_spec(snapshot)
        fingerprint = digest(snapshot)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND request_id=?",
                (snapshot["project_id"], snapshot["client_request_id"]),
            ).fetchone()
            if row:
                if row["snapshot_hash"] != fingerprint:
                    raise ConflictError("同 request id 不可提交不同內容")
                return self._row(row)
            job_id, timestamp = new_id(), now()
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    snapshot["project_id"],
                    snapshot["client_request_id"],
                    canonical(snapshot),
                    fingerprint,
                    "created",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            self._event(db, job_id, "created", {"stage": "created"})
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def get(self, job_id: str) -> dict:
        validate_id(job_id)
        with self._connect() as db:
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def find_request(self, project_id: str, request_id: str) -> dict | None:
        validate_id(project_id)
        validate_id(request_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND request_id=?", (project_id, request_id)
            ).fetchone()
            return self._row(row) if row else None

    def list(self, project_id: str | None = None) -> list[dict]:
        with self._connect() as db:
            if project_id is None:
                rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
            else:
                validate_id(project_id)
                rows = db.execute(
                    "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC", (project_id,)
                ).fetchall()
            return [self._row(row) for row in rows]

    def append_event(self, job_id: str, event: str, payload: dict) -> None:
        self.get(job_id)
        if event not in {"progress", "cached", "diagnostic", "result"}:
            raise ValidationError("不支援此事件類型")
        if set(payload) - {"stage", "value", "max", "asset_id", "workflow_hash", "code"}:
            raise ValidationError("事件含不允許的敏感或未知欄位")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event(db, job_id, event, payload)

    def bind_prompt(self, job_id: str, prompt_id: str) -> None:
        validate_id(prompt_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            if row["status"] != "queued" or row["comfy_prompt_id"] not in (None, prompt_id):
                raise ConflictError("工作不可重新綁定其他引擎工作")
            db.execute(
                "UPDATE jobs SET comfy_prompt_id=?,updated_at=? WHERE id=?",
                (prompt_id, now(), job_id),
            )

    def transition(self, job_id: str, target: str, *, expected: str) -> dict:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            if row["status"] != expected:
                raise ConflictError("工作狀態已更新")
            validate_transition(expected, target)
            db.execute("UPDATE jobs SET status=?,updated_at=? WHERE id=?", (target, now(), job_id))
            self._event(db, job_id, "stage", {"stage": target})
        return self.get(job_id)

    def events(self, job_id: str, after_seq: int = 0) -> list[dict]:
        self.get(job_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq", (job_id, after_seq)
            ).fetchall()
            return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def recover_interrupted(self) -> list[dict]:
        """Called only with exclusive engine ownership at startup. Does not resubmit anything."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM jobs").fetchall()
            recovered = []
            for row in rows:
                if row["status"] not in TERMINAL:
                    db.execute(
                        "UPDATE jobs SET status='interrupted',updated_at=? WHERE id=?",
                        (now(), row["id"]),
                    )
                    self._event(db, row["id"], "interrupted", {"reconcile_history": True})
                    recovered.append(self._row(row))
            return [{**job, "status": "interrupted"} for job in recovered]
