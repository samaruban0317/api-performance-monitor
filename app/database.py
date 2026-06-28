"""SQLite data-access layer.

A thin, dependency-free layer over ``sqlite3``. Connections use WAL mode so the
probe writer and the Flask/Grafana readers do not block each other, and a row
factory so queries return dict-like rows.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    url             TEXT    NOT NULL,
    method          TEXT    NOT NULL DEFAULT 'GET',
    headers         TEXT    NOT NULL DEFAULT '{}',
    body            TEXT,
    expected_status INTEGER NOT NULL DEFAULT 200,
    timeout         REAL    NOT NULL DEFAULT 10,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS metrics (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id        INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    ts               TEXT    NOT NULL,
    response_time_ms REAL,
    status_code      INTEGER,
    success          INTEGER NOT NULL,
    error            TEXT,
    response_size    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_metrics_target_ts ON metrics(target_id, ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Database:
    """Owns the SQLite file and hands out short-lived connections."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._write_lock = threading.Lock()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=5000;")
            yield conn
        finally:
            conn.close()

    # -- targets ------------------------------------------------------------

    def upsert_target(self, row: dict[str, Any]) -> int:
        """Insert or update a target keyed by unique ``name``. Returns its id."""
        with self._write_lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO targets
                    (name, url, method, headers, body, expected_status,
                     timeout, interval_seconds, enabled)
                VALUES
                    (:name, :url, :method, :headers, :body, :expected_status,
                     :timeout, :interval_seconds, :enabled)
                ON CONFLICT(name) DO UPDATE SET
                    url=excluded.url,
                    method=excluded.method,
                    headers=excluded.headers,
                    body=excluded.body,
                    expected_status=excluded.expected_status,
                    timeout=excluded.timeout,
                    interval_seconds=excluded.interval_seconds,
                    enabled=excluded.enabled
                """,
                row,
            )
            cur = conn.execute("SELECT id FROM targets WHERE name = ?", (row["name"],))
            return int(cur.fetchone()["id"])

    def list_targets(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM targets"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(query).fetchall()]

    def get_target(self, target_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM targets WHERE id = ?", (target_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_target(self, target_id: int) -> bool:
        with self._write_lock, self.connect() as conn:
            cur = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
            return cur.rowcount > 0

    # -- metrics ------------------------------------------------------------

    def insert_metric(self, metric: dict[str, Any]) -> None:
        with self._write_lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics
                    (target_id, ts, response_time_ms, status_code,
                     success, error, response_size)
                VALUES
                    (:target_id, :ts, :response_time_ms, :status_code,
                     :success, :error, :response_size)
                """,
                metric,
            )

    def recent_metrics(
        self, target_id: int, limit: int = 200
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, response_time_ms, status_code, success, error
                FROM metrics
                WHERE target_id = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (target_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def prune(self, retention_days: int) -> int:
        """Delete metric samples older than the retention window."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._write_lock, self.connect() as conn:
            cur = conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
            return cur.rowcount
