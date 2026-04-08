from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DeliberationReplayEventKind(str, Enum):
    start = "start"
    turn = "turn"
    synthesis = "synthesis"
    artifact = "artifact"
    checkpoint = "checkpoint"
    decision = "decision"
    note = "note"


class DeliberationReplayEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    sequence: int
    kind: DeliberationReplayEventKind
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliberationReplayManifest(BaseModel):
    replay_id: str = Field(default_factory=lambda: f"replay_{uuid4().hex[:12]}")
    source_run_id: str
    source_manifest_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    events: list[DeliberationReplayEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def next_sequence(self) -> int:
        return len(self.events) + 1

    def append_event(
        self,
        *,
        kind: DeliberationReplayEventKind,
        payload: dict[str, Any] | None = None,
        provenance_ids: list[str] | None = None,
    ) -> DeliberationReplayEvent:
        event = DeliberationReplayEvent(
            sequence=self.next_sequence(),
            kind=kind,
            payload=payload or {},
            provenance_ids=provenance_ids or [],
        )
        self.events.append(event)
        return event

    def events_by_kind(self, kind: DeliberationReplayEventKind) -> list[DeliberationReplayEvent]:
        return [event for event in self.events if event.kind == kind]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "DeliberationReplayManifest":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
