from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DeliberationMode(str, Enum):
    committee = "committee"
    simulation = "simulation"
    hybrid = "hybrid"


class DeliberationProvenanceKind(str, Enum):
    source = "source"
    signal = "signal"
    decision = "decision"
    observation = "observation"
    artifact = "artifact"


class DeliberationArtifactKind(str, Enum):
    input = "input"
    profile = "profile"
    transcript = "transcript"
    report = "report"
    graph = "graph"
    visual = "visual"
    trace = "trace"
    summary = "summary"
    replay = "replay"
    benchmark = "benchmark"
    other = "other"


class DeliberationProvenanceItem(BaseModel):
    provenance_id: str
    kind: DeliberationProvenanceKind
    title: str = ""
    source_uri: str | None = None
    content: str | None = None
    confidence: float | None = None
    parent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliberationArtifact(BaseModel):
    artifact_id: str
    kind: DeliberationArtifactKind = DeliberationArtifactKind.other
    title: str = ""
    uri: str | None = None
    content_hash: str | None = None
    content_type: str | None = None
    provenance_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliberationRunManifest(BaseModel):
    schema_version: str = "v1"
    manifest_version: str = "v1"
    run_id: str
    topic: str = ""
    objective: str = ""
    mode: DeliberationMode = DeliberationMode.committee
    engine_used: str | None = None
    seed: dict[str, Any] = Field(default_factory=dict)
    profile_version: str | None = None
    graph_version: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    inputs: dict[str, Any] = Field(default_factory=dict)
    provenance: list[DeliberationProvenanceItem] = Field(default_factory=list)
    artifacts: list[DeliberationArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_provenance(self, item: DeliberationProvenanceItem) -> None:
        self.provenance.append(item)
        self.updated_at = datetime.now(timezone.utc)

    def add_artifact(self, item: DeliberationArtifact) -> None:
        self.artifacts.append(item)
        if item.uri and item.uri not in self.artifact_refs:
            self.artifact_refs.append(item.uri)
        self.updated_at = datetime.now(timezone.utc)

    def add_input_ref(self, ref: str | None) -> None:
        if ref and ref not in self.input_refs:
            self.input_refs.append(ref)
            self.updated_at = datetime.now(timezone.utc)

    def refresh_refs(self) -> None:
        self.artifact_refs = [artifact.uri for artifact in self.artifacts if artifact.uri]
        self.updated_at = datetime.now(timezone.utc)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "DeliberationRunManifest":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
