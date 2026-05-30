"""SQLite-backed runtime persistence for jobs, watchlists, and alert rules."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


def runtime_db_path() -> Path:
    configured = os.environ.get("KRONOS_RUNTIME_DB")
    if configured:
        return Path(configured)
    return Path.cwd() / ".hermes" / "runtime.sqlite3"


class RuntimeStore:
    """Small SQLite repository for operational runtime state."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else runtime_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    weights_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    note TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlists_updated_at ON watchlists(updated_at DESC)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load(value: str | None, default: Any = None) -> Any:
        if value is None:
            return default
        return json.loads(value)

    def upsert_job(self, job: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(job_id, kind, status, steps_json, result_json, error, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    kind=excluded.kind,
                    status=excluded.status,
                    steps_json=excluded.steps_json,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                """,
                (
                    job["job_id"],
                    job["kind"],
                    job["status"],
                    self._dump(job.get("steps", [])),
                    self._dump(job.get("result")) if job.get("result") is not None else None,
                    job.get("error"),
                    float(job.get("created_at", time.time())),
                    float(job.get("updated_at", time.time())),
                ),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, limit: int = 50, status: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if status:
            clauses.append("status = ?")
            args.append(status)
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(max(1, min(int(limit), 200)))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM jobs{where} ORDER BY updated_at DESC LIMIT ?", args).fetchall()
        return [self._row_to_job(row) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            return cur.rowcount > 0

    def prune_jobs(self, max_jobs: int = 100, ttl_seconds: int = 3600) -> None:
        cutoff = time.time() - ttl_seconds
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE updated_at < ?", (cutoff,))
            rows = conn.execute(
                "SELECT job_id FROM jobs ORDER BY updated_at DESC LIMIT -1 OFFSET ?",
                (max(1, max_jobs),),
            ).fetchall()
            for row in rows:
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (row["job_id"],))

    def _row_to_job(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "status": row["status"],
            "steps": self._load(row["steps_json"], []),
            "result": self._load(row["result_json"], None),
            "error": row["error"],
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def upsert_watchlist(self, item: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlists(id, name, market, symbols_json, weights_json, tags_json, note, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    market=excluded.market,
                    symbols_json=excluded.symbols_json,
                    weights_json=excluded.weights_json,
                    tags_json=excluded.tags_json,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    item["id"],
                    item["name"],
                    item.get("market", "cn"),
                    self._dump(item.get("symbols", [])),
                    self._dump(item.get("weights", {})),
                    self._dump(item.get("tags", [])),
                    item.get("note"),
                    float(item.get("created_at", time.time())),
                    float(item.get("updated_at", time.time())),
                ),
            )

    def get_watchlist(self, watchlist_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
        return self._row_to_watchlist(row) if row else None

    def list_watchlists(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watchlists ORDER BY updated_at DESC").fetchall()
        return [self._row_to_watchlist(row) for row in rows]

    def delete_watchlist(self, watchlist_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
            return cur.rowcount > 0

    def _row_to_watchlist(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "market": row["market"],
            "symbols": self._load(row["symbols_json"], []),
            "weights": self._load(row["weights_json"], {}),
            "tags": self._load(row["tags_json"], []),
            "note": row["note"],
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def replace_alert_rules(self, rules: list[dict[str, Any]]) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("DELETE FROM alert_rules")
            for rule in rules:
                conn.execute(
                    "INSERT INTO alert_rules(id, payload_json, updated_at) VALUES(?, ?, ?)",
                    (rule["id"], self._dump(rule), now),
                )

    def list_alert_rules(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload_json FROM alert_rules ORDER BY updated_at DESC").fetchall()
        return [self._load(row["payload_json"], {}) for row in rows]


def get_runtime_store(path: str | Path | None = None) -> RuntimeStore:
    return RuntimeStore(path)
