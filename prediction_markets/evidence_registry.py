from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import EvidencePacket
from .paths import PredictionMarketPaths, default_prediction_market_paths


class EvidenceRegistryIndexEntry(BaseModel):
    evidence_id: str
    market_id: str
    venue: str
    run_id: str | None = None
    source_kind: str = "manual"
    source_type: str | None = None
    classification: str | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    path: str
    observed_at: str
    freshness_score: float = 0.0
    credibility_score: float = 0.0
    content_hash: str | None = None
    stored_at: str | None = None
    size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRegistryIndex(BaseModel):
    schema_version: str = "v1"
    entries: list[EvidenceRegistryIndexEntry] = Field(default_factory=list)

    def save(self, path: str | Path) -> Path:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump_json(indent=2)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(file_path.parent), encoding="utf-8") as handle:
            handle.write(payload)
            tmp_path = Path(handle.name)
        tmp_path.replace(file_path)
        return file_path

    @classmethod
    def load(cls, path: str | Path) -> "EvidenceRegistryIndex":
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        return cls.model_validate_json(file_path.read_text(encoding="utf-8"))

    def upsert(self, entry: EvidenceRegistryIndexEntry) -> None:
        self.entries = [item for item in self.entries if item.evidence_id != entry.evidence_id] + [entry]
        self.entries.sort(key=lambda item: (item.observed_at, item.evidence_id))


class EvidenceRegistryAudit(BaseModel):
    schema_version: str = "v1"
    healthy: bool = True
    total_entries: int = 0
    markets: list[str] = Field(default_factory=list)
    duplicate_content_hashes: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    content_hash_mismatches: list[str] = Field(default_factory=list)
    artifact_ref_mismatches: list[str] = Field(default_factory=list)
    provenance_bundle_hash_mismatches: list[str] = Field(default_factory=list)
    stored_at_mismatches: list[str] = Field(default_factory=list)
    execution_like_metadata: list[str] = Field(default_factory=list)
    latest_observed_at: str | None = None
    issues: list[str] = Field(default_factory=list)


class EvidenceRegistry:
    def __init__(self, paths: PredictionMarketPaths | None = None) -> None:
        self.paths = paths or default_prediction_market_paths()
        self.paths.ensure_layout()

    @property
    def index_path(self) -> Path:
        return self.paths.evidence_index_path

    def load_index(self) -> EvidenceRegistryIndex:
        return EvidenceRegistryIndex.load(self.index_path)

    def save_index(self, index: EvidenceRegistryIndex) -> Path:
        return index.save(self.index_path)

    def add(self, evidence: EvidencePacket) -> EvidencePacket:
        evidence_path = self.paths.evidence_path(evidence.evidence_id, evidence.market_id)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = dict(evidence.metadata)
        artifact_refs = _normalize_refs(
            metadata.get("artifact_refs", []),
            metadata.get("source_path"),
            metadata.get("sidecar_source_path"),
            str(evidence_path),
        )
        stored_at = datetime.now(timezone.utc).isoformat()
        metadata["artifact_refs"] = artifact_refs
        metadata["stored_at"] = stored_at
        evidence.metadata = metadata
        evidence.content_hash = _sha256_text(
            json.dumps(evidence.model_dump(mode="json", exclude={"content_hash"}), sort_keys=True, separators=(",", ":"))
        )
        payload = evidence.model_dump_json(indent=2, exclude_none=True)
        evidence_path.write_text(payload, encoding="utf-8")
        index = self.load_index()
        index.upsert(
            EvidenceRegistryIndexEntry(
                evidence_id=evidence.evidence_id,
                market_id=evidence.market_id,
                venue=evidence.venue.value,
                run_id=evidence.metadata.get("run_id"),
                source_kind=evidence.source_kind.value,
                source_type=str(evidence.metadata.get("source_type") or evidence.metadata.get("source") or ""),
                classification=str(evidence.metadata.get("classification") or ""),
                provenance_refs=list(evidence.provenance_refs),
                artifact_refs=list(artifact_refs),
                path=str(evidence_path),
                observed_at=evidence.observed_at.isoformat(),
                freshness_score=evidence.freshness_score,
                credibility_score=evidence.credibility_score,
                content_hash=_sha256_text(payload),
                stored_at=stored_at,
                size_bytes=len(payload.encode("utf-8")),
                metadata=dict(evidence.metadata),
            )
        )
        self.save_index(index)
        return evidence

    def add_many(self, evidences: list[EvidencePacket]) -> list[EvidencePacket]:
        return [self.add(evidence) for evidence in evidences]

    def get(self, evidence_id: str) -> EvidencePacket | None:
        index = self.load_index()
        for entry in index.entries:
            if entry.evidence_id == evidence_id:
                return self._load_entry(entry)
        return None

    def list_by_market(self, market_id: str) -> list[EvidencePacket]:
        index = self.load_index()
        evidence: list[EvidencePacket] = []
        for entry in index.entries:
            if entry.market_id != market_id:
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                evidence.append(packet)
        return evidence

    def list_by_run(self, run_id: str) -> list[EvidencePacket]:
        index = self.load_index()
        evidence: list[EvidencePacket] = []
        for entry in index.entries:
            if entry.run_id != run_id:
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                evidence.append(packet)
        return evidence

    def list_recent(self, limit: int = 20) -> list[EvidencePacket]:
        index = self.load_index()
        entries = index.entries[-limit:]
        evidence: list[EvidencePacket] = []
        for entry in entries:
            packet = self._load_entry(entry)
            if packet is not None:
                evidence.append(packet)
        return evidence

    def list_by_content_hash(self, content_hash: str) -> list[EvidencePacket]:
        index = self.load_index()
        packets: list[EvidencePacket] = []
        for entry in index.entries:
            if entry.content_hash != content_hash:
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                packets.append(packet)
        return packets

    def list_by_provenance_ref(self, provenance_ref: str) -> list[EvidencePacket]:
        index = self.load_index()
        packets: list[EvidencePacket] = []
        for entry in index.entries:
            if provenance_ref not in entry.provenance_refs:
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                packets.append(packet)
        return packets

    def list_by_source_kind(self, source_kind: str) -> list[EvidencePacket]:
        index = self.load_index()
        packets: list[EvidencePacket] = []
        for entry in index.entries:
            if entry.source_kind != source_kind:
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                packets.append(packet)
        return packets

    def list_signal_only(self) -> list[EvidencePacket]:
        index = self.load_index()
        packets: list[EvidencePacket] = []
        for entry in index.entries:
            if entry.classification != "signal-only":
                continue
            packet = self._load_entry(entry)
            if packet is not None:
                packets.append(packet)
        return packets

    def audit(self) -> EvidenceRegistryAudit:
        index = self.load_index()
        missing_files: list[str] = []
        duplicate_content_hashes: list[str] = []
        content_hash_mismatches: list[str] = []
        artifact_ref_mismatches: list[str] = []
        provenance_bundle_hash_mismatches: list[str] = []
        stored_at_mismatches: list[str] = []
        execution_like_metadata: list[str] = []
        seen_hashes: set[str] = set()
        markets: list[str] = []
        latest_observed_at: str | None = None
        for entry in index.entries:
            if entry.market_id not in markets:
                markets.append(entry.market_id)
            resolved_path = self._resolve_entry_path(entry)
            if not resolved_path.exists():
                missing_files.append(entry.evidence_id)
                continue
            packet = self._load_entry(entry)
            if packet is None:
                missing_files.append(entry.evidence_id)
                continue
            if entry.content_hash:
                packet_hash = _sha256_text(resolved_path.read_text(encoding="utf-8"))
                if packet_hash != entry.content_hash and entry.evidence_id not in content_hash_mismatches:
                    content_hash_mismatches.append(entry.evidence_id)
                if entry.content_hash in seen_hashes and entry.content_hash not in duplicate_content_hashes:
                    duplicate_content_hashes.append(entry.content_hash)
                seen_hashes.add(entry.content_hash)
            packet_artifact_refs = _normalize_refs(
                packet.metadata.get("artifact_refs", []),
                packet.metadata.get("source_path"),
                packet.metadata.get("sidecar_source_path"),
                str(resolved_path),
            )
            if packet_artifact_refs != _normalize_refs(entry.artifact_refs) and entry.evidence_id not in artifact_ref_mismatches:
                artifact_ref_mismatches.append(entry.evidence_id)
            provenance_bundle = packet.metadata.get("provenance_bundle")
            provenance_bundle_hash = str(
                packet.metadata.get("provenance_bundle_content_hash")
                or (provenance_bundle.get("content_hash") if isinstance(provenance_bundle, dict) else "")
                or ""
            ).strip()
            if provenance_bundle_hash and isinstance(provenance_bundle, dict):
                canonical_bundle_hash = _sha256_text(
                    json.dumps(
                        {key: value for key, value in provenance_bundle.items() if key != "content_hash"},
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    )
                )
                if canonical_bundle_hash != provenance_bundle_hash and entry.evidence_id not in provenance_bundle_hash_mismatches:
                    provenance_bundle_hash_mismatches.append(entry.evidence_id)
            packet_stored_at = str(packet.metadata.get("stored_at") or "").strip()
            if entry.stored_at and packet_stored_at and packet_stored_at != entry.stored_at and entry.evidence_id not in stored_at_mismatches:
                stored_at_mismatches.append(entry.evidence_id)
            execution_keys = _execution_like_metadata_keys(packet.metadata)
            if execution_keys:
                execution_like_metadata.append(f"{entry.evidence_id}:{','.join(execution_keys)}")
            if latest_observed_at is None or entry.observed_at > latest_observed_at:
                latest_observed_at = entry.observed_at
        issues: list[str] = []
        if missing_files:
            issues.append("missing_files")
        if duplicate_content_hashes:
            issues.append("duplicate_content_hashes")
        if content_hash_mismatches:
            issues.append("content_hash_mismatches")
        if artifact_ref_mismatches:
            issues.append("artifact_ref_mismatches")
        if provenance_bundle_hash_mismatches:
            issues.append("provenance_bundle_hash_mismatches")
        if stored_at_mismatches:
            issues.append("stored_at_mismatches")
        if execution_like_metadata:
            issues.append("execution_like_metadata")
        healthy = not issues
        return EvidenceRegistryAudit(
            healthy=healthy,
            total_entries=len(index.entries),
            markets=markets,
            duplicate_content_hashes=duplicate_content_hashes,
            missing_files=missing_files,
            content_hash_mismatches=content_hash_mismatches,
            artifact_ref_mismatches=artifact_ref_mismatches,
            provenance_bundle_hash_mismatches=provenance_bundle_hash_mismatches,
            stored_at_mismatches=stored_at_mismatches,
            execution_like_metadata=execution_like_metadata,
            latest_observed_at=latest_observed_at,
            issues=issues,
        )

    def _load_entry(self, entry: EvidenceRegistryIndexEntry) -> EvidencePacket | None:
        path = self._resolve_entry_path(entry)
        if path.exists():
            return EvidencePacket.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    def _resolve_entry_path(self, entry: EvidenceRegistryIndexEntry) -> Path:
        path = Path(entry.path)
        if path.is_absolute():
            return path
        candidate = self.index_path.parent / path
        if candidate.exists():
            return candidate
        return self.paths.root / path


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = list(value)
        else:
            candidates = [value]
        for item in candidates:
            text = str(item).strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _execution_like_metadata_keys(metadata: dict[str, Any]) -> list[str]:
    suspicious_keys = {
        "acknowledged_at",
        "acknowledged_by",
        "cancel_reason",
        "decision_id",
        "execution_id",
        "execution_projection",
        "execution_status",
        "fill_id",
        "filled_at",
        "live_execution",
        "order_id",
        "trade_intent",
    }
    return sorted(key for key in metadata if key in suspicious_keys and metadata.get(key) not in (None, "", [], {}))
