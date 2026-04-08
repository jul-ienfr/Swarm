from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from runtime_contracts.adapter_result import RunStatus


@dataclass(slots=True)
class RunMapping:
    intent_id: str
    runtime_run_id: str
    engine: str
    engine_run_id: str | None
    status: RunStatus
    correlation_id: str | None
    created_at: str
    updated_at: str


class RunMappingStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._memory_conn: sqlite3.Connection | None = None
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_mappings (
                    intent_id TEXT NOT NULL,
                    runtime_run_id TEXT PRIMARY KEY,
                    engine TEXT NOT NULL,
                    engine_run_id TEXT,
                    status TEXT NOT NULL,
                    correlation_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def create(
        self,
        intent_id: str,
        runtime_run_id: str,
        engine: str,
        correlation_id: str | None,
        *,
        status: RunStatus = RunStatus.queued,
    ) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                INSERT INTO run_mappings (
                    intent_id, runtime_run_id, engine, engine_run_id, status, correlation_id
                ) VALUES (?, ?, ?, NULL, ?, ?)
                ON CONFLICT(runtime_run_id) DO NOTHING
                """,
                (intent_id, runtime_run_id, engine, status.value, correlation_id),
            )

    def update_engine_run_id(self, runtime_run_id: str, engine_run_id: str) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                UPDATE run_mappings
                   SET engine_run_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE runtime_run_id = ?
                """,
                (engine_run_id, runtime_run_id),
            )

    def update_status(self, runtime_run_id: str, status: RunStatus) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                UPDATE run_mappings
                   SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE runtime_run_id = ?
                """,
                (status.value, runtime_run_id),
            )

    def get_by_runtime_run_id(self, runtime_run_id: str) -> RunMapping | None:
        conn = self._connect()
        if self.db_path == ":memory:":
            row = conn.execute(
                """
                SELECT intent_id, runtime_run_id, engine, engine_run_id, status,
                       correlation_id, created_at, updated_at
                  FROM run_mappings
                 WHERE runtime_run_id = ?
                """,
                (runtime_run_id,),
            ).fetchone()
        else:
            with conn:
                row = conn.execute(
                    """
                    SELECT intent_id, runtime_run_id, engine, engine_run_id, status,
                           correlation_id, created_at, updated_at
                      FROM run_mappings
                     WHERE runtime_run_id = ?
                    """,
                    (runtime_run_id,),
                ).fetchone()
        if row is None:
            return None
        return RunMapping(
            intent_id=row["intent_id"],
            runtime_run_id=row["runtime_run_id"],
            engine=row["engine"],
            engine_run_id=row["engine_run_id"],
            status=RunStatus(row["status"]),
            correlation_id=row["correlation_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
