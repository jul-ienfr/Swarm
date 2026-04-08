from __future__ import annotations

import json
import sqlite3
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


class LoopMemoryEntryType(str, Enum):
    benchmark = "benchmark"
    self_critique = "self_critique"
    decision = "decision"
    suggestion = "suggestion"


class LoopMemoryEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: f"loop_mem_{uuid4().hex[:12]}")
    target_id: str
    round_index: int
    entry_type: LoopMemoryEntryType
    summary: str
    details: dict = Field(default_factory=dict)
    candidate_version: str | None = None
    applied: bool | None = None
    score_delta: float | None = None
    created_at: str | None = None


class LoopMemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None
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
                CREATE TABLE IF NOT EXISTS improvement_loop_memory (
                    entry_id TEXT PRIMARY KEY,
                    target_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    entry_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    candidate_version TEXT,
                    applied INTEGER,
                    score_delta REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def append(self, entry: LoopMemoryEntry) -> LoopMemoryEntry:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                INSERT INTO improvement_loop_memory (
                    entry_id, target_id, round_index, entry_type, summary, details_json,
                    candidate_version, applied, score_delta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.target_id,
                    entry.round_index,
                    entry.entry_type.value,
                    entry.summary,
                    json.dumps(entry.details),
                    entry.candidate_version,
                    None if entry.applied is None else int(entry.applied),
                    entry.score_delta,
                ),
            )
            created = conn.execute(
                "SELECT created_at FROM improvement_loop_memory WHERE entry_id = ?",
                (entry.entry_id,),
            ).fetchone()
        return entry.model_copy(update={"created_at": created["created_at"] if created else None})

    def write_round_feedback(
        self,
        *,
        target_id: str,
        round_index: int,
        entry_type: LoopMemoryEntryType,
        summary: str,
        details: dict | None = None,
        candidate_version: str | None = None,
        applied: bool | None = None,
        score_delta: float | None = None,
    ) -> LoopMemoryEntry:
        return self.append(
            LoopMemoryEntry(
                target_id=target_id,
                round_index=round_index,
                entry_type=entry_type,
                summary=summary,
                details=details or {},
                candidate_version=candidate_version,
                applied=applied,
                score_delta=score_delta,
            )
        )

    def list_recent(self, *, target_id: str, limit: int = 20) -> list[LoopMemoryEntry]:
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT entry_id, target_id, round_index, entry_type, summary, details_json,
                   candidate_version, applied, score_delta, created_at
            FROM improvement_loop_memory
            WHERE target_id = ?
            ORDER BY round_index DESC, created_at DESC
            LIMIT ?
            """,
            (target_id, limit),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_latest_round_index(self, *, target_id: str) -> int:
        conn = self._connect()
        row = conn.execute(
            "SELECT COALESCE(MAX(round_index), 0) AS max_round FROM improvement_loop_memory WHERE target_id = ?",
            (target_id,),
        ).fetchone()
        return int(row["max_round"]) if row else 0

    def consecutive_non_improvements(self, *, target_id: str, limit: int) -> int:
        entries = [
            entry
            for entry in self.list_recent(target_id=target_id, limit=limit * 2)
            if entry.entry_type == LoopMemoryEntryType.decision
        ]
        count = 0
        for entry in entries:
            if entry.applied and (entry.score_delta or 0.0) > 0:
                break
            count += 1
            if count >= limit:
                return count
        return count

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LoopMemoryEntry:
        return LoopMemoryEntry.model_validate(
            {
                "entry_id": row["entry_id"],
                "target_id": row["target_id"],
                "round_index": row["round_index"],
                "entry_type": row["entry_type"],
                "summary": row["summary"],
                "details": json.loads(row["details_json"]),
                "candidate_version": row["candidate_version"],
                "applied": None if row["applied"] is None else bool(row["applied"]),
                "score_delta": row["score_delta"],
                "created_at": row["created_at"],
            }
        )
