from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvenanceKind(str, Enum):
    document = "document"
    profile = "profile"
    belief_state = "belief_state"
    graph_node = "graph_node"
    graph_edge = "graph_edge"
    simulation = "simulation"
    report = "report"
    decision = "decision"
    trace = "trace"
    artifact = "artifact"


@dataclass(slots=True)
class ProvenanceRecord:
    record_id: str
    run_id: str
    kind: ProvenanceKind
    subject_id: str
    source: str
    created_at: str
    parent_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProvenanceRecord":
        return cls(
            record_id=str(payload["record_id"]),
            run_id=str(payload["run_id"]),
            kind=ProvenanceKind(str(payload["kind"])),
            subject_id=str(payload["subject_id"]),
            source=str(payload["source"]),
            created_at=str(payload["created_at"]),
            parent_id=payload.get("parent_id"),
            details=dict(payload.get("details") or {}),
        )


class ProvenanceRegistry:
    """
    Lightweight provenance registry for deliberation runs.

    The registry is intentionally bounded and file-backed so it can be reused
    later by the massive deliberation pipeline without any integration work.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._records: dict[str, ProvenanceRecord] = {}
        if self.storage_path is not None:
            self._load()

    def record(
        self,
        *,
        run_id: str,
        kind: ProvenanceKind | str,
        subject_id: str,
        source: str,
        parent_id: str | None = None,
        details: dict[str, Any] | None = None,
        created_at: str | None = None,
        record_id: str | None = None,
    ) -> ProvenanceRecord:
        entry = ProvenanceRecord(
            record_id=record_id or uuid.uuid4().hex,
            run_id=run_id,
            kind=kind if isinstance(kind, ProvenanceKind) else ProvenanceKind(str(kind)),
            subject_id=subject_id,
            source=source,
            created_at=created_at or _utc_now(),
            parent_id=parent_id,
            details=dict(details or {}),
        )
        self._records[entry.record_id] = entry
        self.save()
        return entry

    def get(self, record_id: str) -> ProvenanceRecord | None:
        return self._records.get(record_id)

    def list(self, *, run_id: str | None = None, kind: ProvenanceKind | str | None = None) -> list[ProvenanceRecord]:
        items: Iterable[ProvenanceRecord] = self._records.values()
        if run_id is not None:
            items = [item for item in items if item.run_id == run_id]
        if kind is not None:
            kind_value = kind if isinstance(kind, ProvenanceKind) else ProvenanceKind(str(kind))
            items = [item for item in items if item.kind == kind_value]
        return sorted(items, key=lambda item: (item.created_at, item.record_id))

    def lineage(self, record_id: str) -> list[ProvenanceRecord]:
        lineage: list[ProvenanceRecord] = []
        current = self._records.get(record_id)
        while current is not None:
            lineage.append(current)
            if current.parent_id is None:
                break
            current = self._records.get(current.parent_id)
        return lineage

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [record.to_dict() for record in self.list()]}
        self.storage_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8") or "{}")
        self._records = {}
        for item in payload.get("records", []):
            record = ProvenanceRecord.from_dict(item)
            self._records[record.record_id] = record

    def to_dict(self) -> dict[str, Any]:
        return {"records": [record.to_dict() for record in self.list()]}

