from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, Field

from .models import EvidencePacket, SourceKind, VenueName
from .research import (
    ResearchBridgeBundle,
    ResearchFinding,
    SidecarSignalPacket,
    assess_findings_health,
    annotate_sidecar_findings,
    build_signal_packets,
    build_sidecar_research_bundle,
    classify_sidecar_health,
    dedupe_findings,
    findings_to_evidence,
    normalize_finding,
)


class SidecarPayloadKind(str, Enum):
    json = "json"
    ndjson = "ndjson"
    mapping = "mapping"
    sequence = "sequence"
    text = "text"
    unknown = "unknown"


class SidecarHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


class TwitterWatcherSidecarHealthSnapshot(BaseModel):
    schema_version: str = "v1"
    sidecar_name: str = "twitter_watcher"
    healthy: bool = False
    status: SidecarHealthStatus = SidecarHealthStatus.unhealthy
    message: str = "uninitialized"
    source_path: str | None = None
    payload_kind: SidecarPayloadKind = SidecarPayloadKind.unknown
    record_count: int = 0
    parsed_count: int = 0
    error_count: int = 0
    duplicate_count: int = 0
    completeness_score: float = 0.0
    alerts: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class TwitterWatcherSidecarBundle(BaseModel):
    schema_version: str = "v1"
    sidecar_name: str = "twitter_watcher"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    source_path: str | None = None
    payload_kind: SidecarPayloadKind = SidecarPayloadKind.unknown
    record_count: int = 0
    parsed_count: int = 0
    findings: list[ResearchFinding] = Field(default_factory=list)
    signal_packets: list[SidecarSignalPacket] = Field(default_factory=list)
    evidence: list[EvidencePacket] = Field(default_factory=list)
    clusters: list["TwitterWatcherSidecarClusterSummary"] = Field(default_factory=list)
    linkage: "TwitterWatcherSidecarLinkageSummary" = Field(default_factory=lambda: TwitterWatcherSidecarLinkageSummary())
    deep_artifacts: dict[str, Any] = Field(default_factory=dict)
    health: TwitterWatcherSidecarHealthSnapshot = Field(default_factory=TwitterWatcherSidecarHealthSnapshot)
    provenance_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    freshness_score: float = 0.0
    content_hash: str = ""
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "TwitterWatcherSidecarBundle":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def rehydrate_research_bundle(self, *, reference_time: datetime | None = None) -> ResearchBridgeBundle:
        classification = classify_sidecar_health(
            healthy=self.health.status == SidecarHealthStatus.healthy,
            alerts=self.health.alerts,
            issues=self.health.metadata.get("issues", []),
        )
        research_bundle = build_sidecar_research_bundle(
            self.findings,
            market_id=self.market_id,
            venue=self.venue,
            run_id=self.run_id,
            reference_time=reference_time or self.observed_at,
            sidecar_name=self.sidecar_name,
            sidecar_health=self.health.model_dump(mode="json"),
            classification=classification.classification,
            classification_reasons=classification.reasons,
            source_path=self.source_path,
            source_bundle_content_hash=self.content_hash,
            source_bundle_refs=[ref for ref in [self.content_hash, self.source_path] if ref],
        )
        research_bundle.artifact_refs = _dedupe(
            [
                *research_bundle.artifact_refs,
                *self.artifact_refs,
                *self.deep_artifacts.get("artifact_refs", []),
            ]
        )
        research_bundle.evidence_refs = _dedupe(
            [
                *research_bundle.evidence_refs,
                *[packet.evidence_id for packet in self.evidence if packet.evidence_id],
            ]
        )
        research_bundle.provenance_refs = _dedupe(
            [
                *research_bundle.provenance_refs,
                *self.provenance_refs,
                *[ref for packet in self.signal_packets for ref in packet.provenance_refs],
            ]
        )
        research_bundle.metadata.update(
            {
                "rehydrated_from_sidecar_bundle": True,
                "sidecar_bundle_content_hash": self.content_hash,
                "sidecar_bundle_observed_at": self.observed_at.isoformat(),
                "deep_artifacts": self.deep_artifacts,
                "clusters": [cluster.model_dump(mode="json") for cluster in self.clusters],
                "linkage": self.linkage.model_dump(mode="json"),
                "cluster_refs": [cluster.cluster_id for cluster in self.clusters],
                "cluster_labels": [cluster.label for cluster in self.clusters],
                "deep_artifact_refs": list(self.deep_artifacts.get("artifact_refs", [])),
                "linked_market_refs": list(self.linkage.market_refs),
                "linked_event_refs": list(self.linkage.event_refs),
            }
        )
        return research_bundle


class TwitterWatcherSidecarClusterSummary(BaseModel):
    schema_version: str = "v1"
    cluster_id: str
    label: str
    source_kind: str = "unknown"
    stance: str = "neutral"
    topic: str = "general"
    record_count: int = 0
    finding_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    signal_refs: list[str] = Field(default_factory=list)
    market_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    keyword_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    freshness_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TwitterWatcherSidecarLinkageSummary(BaseModel):
    schema_version: str = "v1"
    linkage_id: str = ""
    market_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    question_hints: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    cluster_refs: list[str] = Field(default_factory=list)
    cluster_labels: list[str] = Field(default_factory=list)
    linked_pairs: list[str] = Field(default_factory=list)
    finding_count: int = 0
    evidence_count: int = 0
    signal_count: int = 0
    provenance_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class TwitterWatcherSidecarBridge:
    sidecar_name: str = "twitter_watcher"
    default_source_kind: SourceKind = SourceKind.social

    def ingest(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        source_kind: SourceKind | None = None,
    ) -> TwitterWatcherSidecarBundle:
        payload, payload_kind, source_path, errors = _load_payload(source)
        records = _extract_records(payload)
        inferred_market_id = market_id or _infer_market_id(payload, records) or "twitter_watcher"
        findings: list[ResearchFinding] = []
        finding_errors: list[str] = list(errors)

        for index, record in enumerate(records, start=1):
            try:
                finding = self._record_to_finding(
                    record,
                    market_id=inferred_market_id,
                    venue=venue,
                    run_id=run_id,
                    reference_time=reference_time,
                    source_kind=source_kind,
                    source_path=source_path,
                    record_index=index,
                    payload_kind=payload_kind,
                )
            except Exception as exc:  # pragma: no cover - defensive conversion guard
                finding_errors.append(f"record_{index}:{exc}")
                continue
            findings.append(finding)

        unique_findings, duplicate_count, duplicate_fingerprints = dedupe_findings(
            findings,
        )
        health_summary = assess_findings_health(
            unique_findings,
            duplicate_count=duplicate_count,
        )
        classification = classify_sidecar_health(
            healthy=health_summary.status == "healthy",
            alerts=health_summary.alerts,
            issues=health_summary.issues,
        )
        annotated_findings = annotate_sidecar_findings(
            unique_findings,
            market_id=inferred_market_id,
            run_id=run_id,
            reference_time=reference_time,
            sidecar_name=self.sidecar_name,
            sidecar_health={
                "status": health_summary.status,
                "alerts": list(health_summary.alerts),
                "issues": list(health_summary.issues),
                "completeness_score": health_summary.completeness_score,
            },
            classification=classification.classification,
            classification_reasons=classification.reasons,
            source_path=str(source_path) if source_path is not None else None,
        )
        evidence = findings_to_evidence(
            annotated_findings,
            market_id=inferred_market_id,
            venue=venue,
            run_id=run_id,
            reference_time=reference_time,
            deduplicate=False,
            duplicate_count=duplicate_count,
        )
        signal_packets = build_signal_packets(
            annotated_findings,
            evidence=evidence,
            market_id=inferred_market_id,
            venue=venue,
            run_id=run_id,
            sidecar_name=self.sidecar_name,
            classification=classification.classification,
            classification_reasons=classification.reasons,
            source_path=str(source_path) if source_path is not None else None,
            sidecar_health={
                "status": health_summary.status,
                "alerts": list(health_summary.alerts),
                "issues": list(health_summary.issues),
                "completeness_score": health_summary.completeness_score,
            },
            reference_time=reference_time,
        )
        health = _build_health(
            source_path=source_path,
            payload_kind=payload_kind,
            record_count=len(records),
            parsed_count=len(annotated_findings),
            error_count=len(finding_errors),
            duplicate_count=duplicate_count,
            sidecar_name=self.sidecar_name,
            errors=finding_errors,
            health_summary=health_summary,
        )
        provenance_refs = _default_provenance_refs(source_path, inferred_market_id, run_id)
        deep_artifacts = _build_deep_artifacts(
            findings=annotated_findings,
            evidence=evidence,
            signal_packets=signal_packets,
            market_id=inferred_market_id,
            run_id=run_id,
            source_path=source_path,
            sidecar_name=self.sidecar_name,
        )
        clusters = deep_artifacts["clusters"]
        linkage = deep_artifacts["linkage"]
        deep_artifact_refs = deep_artifacts["artifact_refs"]
        artifact_refs = _bundle_artifact_refs(
            source_path=source_path,
            market_id=inferred_market_id,
            run_id=run_id,
            signal_packets=signal_packets,
            evidence=evidence,
            deep_artifact_refs=deep_artifact_refs,
        )
        freshness_score = _bundle_freshness_score(annotated_findings)
        bundle = TwitterWatcherSidecarBundle(
            market_id=inferred_market_id,
            venue=venue,
            run_id=run_id,
            source_path=str(source_path) if source_path is not None else None,
            payload_kind=payload_kind,
            record_count=len(records),
            parsed_count=len(annotated_findings),
            findings=annotated_findings,
            signal_packets=signal_packets,
            evidence=evidence,
            clusters=clusters,
            linkage=linkage,
            deep_artifacts=deep_artifacts,
            health=health,
            provenance_refs=provenance_refs,
            artifact_refs=artifact_refs,
            observed_at=health.observed_at,
            freshness_score=freshness_score,
            errors=finding_errors,
            metadata={
                "source": self.sidecar_name,
                "source_type": "twitter_watcher_sidecar",
                "classification": classification.classification,
                "classification_reasons": classification.reasons,
                "signal_only": classification.signal_only,
                "research_health": {
                    "status": health_summary.status,
                    "completeness_score": health_summary.completeness_score,
                    "issues": list(health_summary.issues),
                    "alerts": list(health_summary.alerts),
                },
                "provenance_refs": provenance_refs,
                "artifact_refs": artifact_refs,
                "cluster_count": len(clusters),
                "cluster_refs": [cluster.cluster_id for cluster in clusters],
                "cluster_labels": [cluster.label for cluster in clusters],
                "linked_market_refs": list(linkage.market_refs),
                "linked_event_refs": list(linkage.event_refs),
                "deep_artifact_refs": deep_artifact_refs,
                "deep_artifacts": {
                    "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
                    "linkage": linkage.model_dump(mode="json"),
                },
                "signal_packet_refs": [packet.signal_id for packet in signal_packets],
                "signal_packet_count": len(signal_packets),
                "observed_at": health.observed_at.isoformat(),
                "freshness_score": freshness_score,
                "runtime": {
                    "record_count": len(records),
                    "parsed_count": len(annotated_findings),
                    "duplicate_count": duplicate_count,
                    "error_count": len(finding_errors),
                    "payload_kind": payload_kind.value,
                    "source_kinds": [kind.value for kind in health_summary.source_kinds],
                },
                "alerts": list(health_summary.alerts),
                "duplicate_record_fingerprints": duplicate_fingerprints,
            },
        )
        bundle.content_hash = _bundle_content_hash(bundle)
        bundle.metadata["content_hash"] = bundle.content_hash
        return bundle

    def to_research_bundle(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        source_kind: SourceKind | None = None,
    ) -> ResearchBridgeBundle:
        bundle = self.ingest(
            source,
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=reference_time,
            source_kind=source_kind,
        )
        return bundle.rehydrate_research_bundle(reference_time=reference_time)

    def to_findings(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[ResearchFinding]:
        return self.ingest(
            source,
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=reference_time,
            source_kind=source_kind,
        ).findings

    def to_evidence(
        self,
        source: Any,
        *,
        market_id: str | None = None,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[EvidencePacket]:
        return self.ingest(
            source,
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=reference_time,
            source_kind=source_kind,
        ).evidence

    def _record_to_finding(
        self,
        record: Mapping[str, Any] | str | Any,
        *,
        market_id: str,
        venue: VenueName,
        run_id: str | None,
        reference_time: datetime | None,
        source_kind: SourceKind | None,
        source_path: Path | None,
        record_index: int,
        payload_kind: SidecarPayloadKind,
    ) -> ResearchFinding:
        payload = _coerce_record(record)
        inferred_source_kind = source_kind or _source_kind_from_record(payload, default=self.default_source_kind)
        payload.setdefault("stance", _infer_stance_from_payload(payload))
        finding = normalize_finding(
            payload,
            market_id=market_id,
            run_id=run_id,
            source_kind=inferred_source_kind,
            reference_time=reference_time,
        )
        metadata = dict(finding.metadata)
        metadata.update(
            {
                "source": self.sidecar_name,
                "source_type": "twitter_watcher_sidecar",
                "source_path": str(source_path) if source_path is not None else None,
                "record_index": record_index,
                "payload_kind": payload_kind.value,
                "payload_keys": sorted(payload.keys()) if isinstance(payload, Mapping) else [],
            }
        )
        metadata["record_fingerprint"] = _record_fingerprint(payload)
        market_refs = _extract_market_refs(payload, market_id)
        event_refs = _extract_event_refs(payload)
        question_hints = _extract_question_hints(payload)
        topic_hints = _extract_topic_hints(payload)
        provenance_refs = list(metadata.get("provenance_refs", []))
        if source_path is not None:
            provenance_refs.append(str(source_path))
        if run_id:
            provenance_refs.append(f"run:{run_id}")
        tweet_id = _strip_or_none(
            payload.get("tweet_id")
            or payload.get("id")
            or payload.get("status_id")
            or payload.get("post_id")
        )
        if tweet_id:
            provenance_refs.append(f"tweet:{tweet_id}")
            metadata.setdefault("tweet_id", tweet_id)
        author = _first_text(payload, ("author", "username", "screen_name", "user", "handle"))
        if author:
            metadata.setdefault("author", author)
            provenance_refs.append(f"author:{author}")
        url = _first_text(payload, ("url", "permalink", "link", "tweet_url"))
        if url:
            provenance_refs.append(url)
        metadata["provenance_refs"] = _dedupe(provenance_refs)
        metadata["market_refs"] = market_refs
        metadata["event_refs"] = event_refs
        metadata["question_hints"] = question_hints
        metadata["topic_hints"] = topic_hints
        metadata["cluster_key"] = _cluster_key_from_parts(
            inferred_source_kind.value,
            payload.get("stance") or _infer_stance_from_payload(payload),
            topic_hints[0] if topic_hints else (finding.tags[0] if finding.tags else "general"),
        )
        finding.metadata = metadata
        tag_values: list[Any] = list(finding.tags)
        for key in ("hashtags", "tags", "topics", "keywords"):
            tag_values.extend(_string_list(payload.get(key)))
        finding.tags = _flatten_strings(tag_values)
        finding.source_url = finding.source_url or url
        if not finding.summary:
            finding.summary = finding.claim[:240]
        return finding


def _load_payload(source: Any) -> tuple[Any, SidecarPayloadKind, Path | None, list[str]]:
    if isinstance(source, Mapping):
        return dict(source), SidecarPayloadKind.mapping, None, []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source), SidecarPayloadKind.sequence, None, []
    if isinstance(source, Path):
        return _load_payload_from_path(source)
    if isinstance(source, bytes):
        return _load_payload_from_text(source.decode("utf-8"))
    if isinstance(source, str):
        maybe_path = Path(source).expanduser()
        if _looks_like_path(source) and maybe_path.exists() and maybe_path.is_file():
            return _load_payload_from_path(maybe_path)
        return _load_payload_from_text(source)
    return {"text": str(source)}, SidecarPayloadKind.text, None, []


def _load_payload_from_path(path: Path) -> tuple[Any, SidecarPayloadKind, Path | None, list[str]]:
    text = path.read_text(encoding="utf-8")
    payload, payload_kind, errors = _parse_text_payload(text)
    return payload, payload_kind, path, errors


def _load_payload_from_text(text: str) -> tuple[Any, SidecarPayloadKind, Path | None, list[str]]:
    payload, payload_kind, errors = _parse_text_payload(text)
    return payload, payload_kind, None, errors


def _parse_text_payload(text: str) -> tuple[Any, SidecarPayloadKind, list[str]]:
    stripped = text.strip()
    if not stripped:
        return [], SidecarPayloadKind.text, ["empty_payload"]
    try:
        return json.loads(stripped), SidecarPayloadKind.json, []
    except json.JSONDecodeError:
        errors: list[str] = []
        records: list[Any] = []
        for line_no, line in enumerate(stripped.splitlines(), start=1):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                records.append(json.loads(candidate))
            except json.JSONDecodeError as exc:
                errors.append(f"line_{line_no}:{exc.msg}")
        return records, SidecarPayloadKind.ndjson, errors


def _extract_records(payload: Any) -> list[Any]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return list(payload)
    if isinstance(payload, Mapping):
        records: list[Any] = []
        for key in ("tweets", "posts", "items", "records", "data", "results", "entries", "messages", "comments"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                records.extend(list(value))
        if records:
            return records
        return [payload]
    return [payload]


def _coerce_record(record: Mapping[str, Any] | str | Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if isinstance(record, str):
        return {"text": record.strip()}
    return {"text": str(record)}


def _source_kind_from_record(record: Mapping[str, Any] | str, *, default: SourceKind) -> SourceKind:
    if isinstance(record, str):
        text = record.lower()
        if any(token in text for token in ("tweet", "post", "reply", "retweet", "quote")):
            return SourceKind.social
        return default
    raw = record.get("source_kind") or record.get("kind") or record.get("source")
    if raw is None:
        return default
    token = str(raw).strip().lower()
    mapping = {
        "social": SourceKind.social,
        "tweet": SourceKind.social,
        "twitter": SourceKind.social,
        "x": SourceKind.social,
        "news": SourceKind.news,
        "market": SourceKind.market,
        "official": SourceKind.official,
        "manual": SourceKind.manual,
        "model": SourceKind.model,
    }
    return mapping.get(token, default)


def _infer_stance_from_payload(payload: Mapping[str, Any]) -> str:
    text = " ".join(
        filter(
            None,
            [
                _first_text(payload, ("stance",)),
                _first_text(payload, ("title", "headline")),
                _first_text(payload, ("summary", "message", "note", "body", "text", "content")),
            ],
        )
    ).lower()
    if any(token in text for token in ("bullish", "support", "yes", "likely", "increase", "higher", "positive")):
        return "bullish"
    if any(token in text for token in ("bearish", "oppose", "no", "unlikely", "decrease", "lower", "negative")):
        return "bearish"
    return "neutral"


def _default_provenance_refs(source_path: Path | None, market_id: str, run_id: str | None) -> list[str]:
    refs = [f"sidecar:twitter_watcher", f"market:{market_id}"]
    if source_path is not None:
        refs.append(str(source_path))
    if run_id:
        refs.append(f"run:{run_id}")
    return _dedupe(refs)


def _bundle_artifact_refs(
    *,
    source_path: Path | None,
    market_id: str,
    run_id: str | None,
    signal_packets: Sequence[SidecarSignalPacket],
    evidence: Sequence[EvidencePacket],
    deep_artifact_refs: Sequence[str] | None = None,
) -> list[str]:
    refs = _default_provenance_refs(source_path, market_id, run_id)
    refs.extend(f"signal:{packet.signal_id}" for packet in signal_packets if packet.signal_id)
    refs.extend(f"evidence:{packet.evidence_id}" for packet in evidence if packet.evidence_id)
    refs.extend(deep_artifact_refs or [])
    return _dedupe(refs)


def _bundle_freshness_score(findings: Sequence[ResearchFinding]) -> float:
    if not findings:
        return 0.0
    return round(sum(finding.freshness_score for finding in findings) / len(findings), 6)


def _bundle_content_hash(bundle: TwitterWatcherSidecarBundle) -> str:
    payload = bundle.model_dump(mode="json", exclude={"content_hash"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _build_health(
    *,
    source_path: Path | None,
    payload_kind: SidecarPayloadKind,
    record_count: int,
    parsed_count: int,
    error_count: int,
    duplicate_count: int,
    sidecar_name: str,
    errors: Sequence[str],
    health_summary: Any,
) -> TwitterWatcherSidecarHealthSnapshot:
    if parsed_count <= 0:
        status = SidecarHealthStatus.unhealthy
        healthy = False
        message = "no records parsed"
    elif health_summary.issues:
        status = SidecarHealthStatus.degraded
        healthy = True
        message = "; ".join(health_summary.alerts) if health_summary.alerts else "parsed with recoverable issues"
    elif error_count > 0:
        status = SidecarHealthStatus.degraded
        healthy = True
        message = "parsed with recoverable errors"
    else:
        status = SidecarHealthStatus.healthy
        healthy = True
        message = "healthy"
    return TwitterWatcherSidecarHealthSnapshot(
        sidecar_name=sidecar_name,
        healthy=healthy,
        status=status,
        message=message,
        source_path=str(source_path) if source_path is not None else None,
        payload_kind=payload_kind,
        record_count=record_count,
        parsed_count=parsed_count,
        error_count=error_count,
        duplicate_count=duplicate_count,
        completeness_score=health_summary.completeness_score,
        alerts=list(health_summary.alerts),
        source_kinds=[kind.value for kind in health_summary.source_kinds],
        metadata={"errors": list(errors), "issues": list(health_summary.issues)},
    )


def _looks_like_path(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped.startswith("{") or stripped.startswith("["):
        return False
    return "/" in stripped or "." in Path(stripped).name


def _first_text(payload: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        text = _strip_or_none(value)
        if text:
            return text
    return None


def _strip_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
        return [str(item) for item in values if _strip_or_none(item)]
    return [str(values)]


def _flatten_strings(values: Iterable[Any]) -> list[str]:
    flattened: list[str] = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            text = _strip_or_none(item)
            if text:
                flattened.append(text)
            continue
        if isinstance(item, Iterable) and not isinstance(item, (str, bytes, bytearray)):
            flattened.extend(_flatten_strings(item))
            continue
        text = _strip_or_none(item)
        if text:
            flattened.append(text)
    return _dedupe(flattened)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _strip_or_none(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _record_fingerprint(payload: Mapping[str, Any]) -> str:
    fingerprint_payload = {
        "record_id": _strip_or_none(
            payload.get("tweet_id")
            or payload.get("id")
            or payload.get("status_id")
            or payload.get("post_id")
        ),
        "text": _first_text(payload, ("text", "body", "content", "message", "summary")),
        "author": _first_text(payload, ("author", "username", "screen_name", "user", "handle")),
        "source_url": _first_text(payload, ("url", "permalink", "link", "tweet_url")),
        "source_kind": _strip_or_none(payload.get("source_kind") or payload.get("kind") or payload.get("source")),
        "published_at": _first_text(payload, ("created_at", "published_at", "timestamp", "observed_at")),
        "hashtags": _string_list(payload.get("hashtags")),
    }
    return hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _build_deep_artifacts(
    *,
    findings: Sequence[ResearchFinding],
    evidence: Sequence[EvidencePacket],
    signal_packets: Sequence[SidecarSignalPacket],
    market_id: str,
    run_id: str | None,
    source_path: Path | None,
    sidecar_name: str,
) -> dict[str, Any]:
    evidence_by_ref = {packet.evidence_id: packet for packet in evidence if packet.evidence_id}
    signal_by_ref = {packet.evidence_id: packet for packet in signal_packets if packet.evidence_id}
    clusters: list[TwitterWatcherSidecarClusterSummary] = []
    cluster_map: dict[str, list[int]] = {}
    for index, finding in enumerate(findings):
        key = _cluster_key_for_finding(finding)
        cluster_map.setdefault(key, []).append(index)

    for key, indexes in sorted(cluster_map.items()):
        cluster_findings = [findings[index] for index in indexes]
        cluster_evidence = [evidence[index] for index in indexes if index < len(evidence)]
        cluster_signals = [signal_packets[index] for index in indexes if index < len(signal_packets)]
        topic = _cluster_topic(cluster_findings)
        stance = _cluster_stance(cluster_findings)
        source_kind = _cluster_source_kind(cluster_findings)
        cluster_id = _stable_ref("twitter_cluster", market_id, run_id, key)
        finding_refs = [_finding_ref(finding) for finding in cluster_findings]
        evidence_refs = [packet.evidence_id for packet in cluster_evidence if packet.evidence_id]
        signal_refs = [packet.signal_id for packet in cluster_signals if packet.signal_id]
        market_refs = _dedupe(
            [f"market:{market_id}", *(_refs_from_findings(cluster_findings, "market_refs")), *(_market_refs_from_findings(cluster_findings))]
        )
        event_refs = _dedupe(_refs_from_findings(cluster_findings, "event_refs"))
        keyword_refs = _dedupe(_cluster_keywords(cluster_findings))
        provenance_refs = _dedupe(
            [
                f"cluster:{cluster_id}",
                *(_refs_from_findings(cluster_findings, "provenance_refs")),
                str(source_path) if source_path is not None else None,
                *(f"signal:{signal_id}" for signal_id in signal_refs),
                *(f"evidence:{evidence_id}" for evidence_id in evidence_refs),
            ]
        )
        artifact_refs = _dedupe(
            [
                f"cluster:{cluster_id}",
                f"cluster_topic:{topic}",
                *(f"signal:{signal_id}" for signal_id in signal_refs),
                *(f"evidence:{evidence_id}" for evidence_id in evidence_refs),
            ]
        )
        freshness_score = round(sum(finding.freshness_score for finding in cluster_findings) / len(cluster_findings), 6)
        clusters.append(
            TwitterWatcherSidecarClusterSummary(
                cluster_id=cluster_id,
                label=f"{source_kind}:{stance}:{topic}",
                source_kind=source_kind,
                stance=stance,
                topic=topic,
                record_count=len(cluster_findings),
                finding_refs=finding_refs,
                evidence_refs=evidence_refs,
                signal_refs=signal_refs,
                market_refs=market_refs,
                event_refs=event_refs,
                keyword_refs=keyword_refs,
                provenance_refs=provenance_refs,
                artifact_refs=artifact_refs,
                freshness_score=freshness_score,
                metadata={
                    "cluster_key": key,
                    "source_kinds": _dedupe([finding.source_kind.value for finding in cluster_findings]),
                },
            )
        )

    market_refs = _dedupe(
        [f"market:{market_id}", *(_refs_from_findings(findings, "market_refs")), *(_market_refs_from_findings(findings))]
    )
    event_refs = _dedupe(_refs_from_findings(findings, "event_refs"))
    question_hints = _dedupe(_refs_from_findings(findings, "question_hints"))
    source_urls = _dedupe([finding.source_url for finding in findings if finding.source_url])
    cluster_refs = [cluster.cluster_id for cluster in clusters]
    cluster_labels = [cluster.label for cluster in clusters]
    linked_pairs = _dedupe(
        [f"{market_ref}|{event_ref}" for market_ref in market_refs for event_ref in event_refs] or [f"market:{market_id}"]
    )
    linkage_id = _stable_ref("twitter_linkage", market_id, run_id, *cluster_refs, *market_refs, *event_refs)
    provenance_refs = _dedupe(
        [
            f"linkage:{linkage_id}",
            f"sidecar:{sidecar_name}",
            f"market:{market_id}",
            str(source_path) if source_path is not None else None,
            *(f"cluster:{cluster_ref}" for cluster_ref in cluster_refs),
        ]
    )
    artifact_refs = _dedupe(
        [
            f"linkage:{linkage_id}",
            *(f"cluster:{cluster_ref}" for cluster_ref in cluster_refs),
            *(ref for cluster in clusters for ref in cluster.artifact_refs),
            *(ref for cluster in clusters for ref in cluster.provenance_refs),
        ]
    )
    linkage = TwitterWatcherSidecarLinkageSummary(
        linkage_id=linkage_id,
        market_refs=market_refs,
        event_refs=event_refs,
        question_hints=question_hints,
        source_urls=source_urls,
        source_kinds=_dedupe([finding.source_kind.value for finding in findings]),
        cluster_refs=cluster_refs,
        cluster_labels=cluster_labels,
        linked_pairs=linked_pairs,
        finding_count=len(findings),
        evidence_count=len(evidence),
        signal_count=len(signal_packets),
        provenance_refs=provenance_refs,
        artifact_refs=artifact_refs,
        metadata={
            "source": sidecar_name,
            "cluster_count": len(clusters),
        },
    )
    deep_artifact_refs = _dedupe(
        [
            linkage_id,
            *(cluster.cluster_id for cluster in clusters),
            *(ref for cluster in clusters for ref in cluster.artifact_refs),
            *(ref for cluster in clusters for ref in cluster.provenance_refs),
        ]
    )
    return {
        "clusters": clusters,
        "linkage": linkage,
        "artifact_refs": deep_artifact_refs,
        "cluster_count": len(clusters),
        "cluster_refs": cluster_refs,
        "cluster_labels": cluster_labels,
        "market_refs": market_refs,
        "event_refs": event_refs,
    }


def _refs_from_findings(findings: Sequence[ResearchFinding], key: str) -> list[str]:
    refs: list[str] = []
    for finding in findings:
        refs.extend(_string_list(finding.metadata.get(key)))
    return _dedupe(refs)


def _extract_market_refs(payload: Mapping[str, Any], market_id: str) -> list[str]:
    refs = [f"market:{market_id}"]
    for key in ("market_id", "market_ids", "market_slug", "market", "market_ref", "question_market_id"):
        refs.extend(_prefixed_refs("market", _string_list(payload.get(key))))
    return _dedupe(refs)


def _extract_event_refs(payload: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("event_id", "event_ids", "canonical_event_id", "event_ref", "topic_id", "story_id"):
        refs.extend(_string_list(payload.get(key)))
    normalized: list[str] = []
    for ref in refs:
        text = _strip_or_none(ref)
        if not text:
            continue
        normalized.append(text if text.startswith("event:") else f"event:{text}")
    return _dedupe(normalized)


def _extract_question_hints(payload: Mapping[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("question", "question_hint", "prompt", "topic", "market_slug", "title", "headline"):
        value = _strip_or_none(payload.get(key))
        if value:
            hints.append(_normalize_topic(value))
    return _dedupe(hints)


def _extract_topic_hints(payload: Mapping[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("topic", "theme", "category", "cluster", "hashtag", "hashtags", "tags", "keywords"):
        hints.extend(_string_list(payload.get(key)))
    return _dedupe([_normalize_topic(hint) for hint in hints if hint])


def _market_refs_from_findings(findings: Sequence[ResearchFinding]) -> list[str]:
    refs: list[str] = []
    for finding in findings:
        market_id = _strip_or_none(finding.metadata.get("market_id"))
        if market_id:
            refs.append(f"market:{market_id}")
        refs.extend(_prefixed_refs("market", _string_list(finding.metadata.get("market_refs"))))
    return _dedupe(refs)


def _cluster_key_from_parts(*parts: str) -> str:
    normalized = [part for part in (_strip_or_none(part) for part in parts) if part]
    if not normalized:
        normalized = ["general"]
    return "|".join(normalized)


def _cluster_key_for_finding(finding: ResearchFinding) -> str:
    topic = _cluster_topic([finding])
    stance = finding.stance
    source_kind = finding.source_kind.value
    return f"{source_kind}|{stance}|{topic}"


def _cluster_topic(findings: Sequence[ResearchFinding]) -> str:
    candidate_values: list[str] = []
    for finding in findings:
        candidate_values.extend(_string_list(finding.tags))
        candidate_values.extend(_string_list(finding.metadata.get("keyword_refs")))
        candidate_values.extend(_string_list(finding.metadata.get("question_hints")))
        candidate_values.extend(_string_list(finding.metadata.get("topic_hints")))
    keyword = next((value for value in candidate_values if value), None)
    return _normalize_topic(keyword or "general")


def _cluster_stance(findings: Sequence[ResearchFinding]) -> str:
    stance_order = {"bullish": 3, "bearish": 2, "neutral": 1}
    if not findings:
        return "neutral"
    return max(findings, key=lambda finding: stance_order.get(finding.stance, 0)).stance


def _cluster_source_kind(findings: Sequence[ResearchFinding]) -> str:
    if not findings:
        return "unknown"
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.source_kind.value] = counts.get(finding.source_kind.value, 0) + 1
    return max(counts, key=counts.get)


def _cluster_keywords(findings: Sequence[ResearchFinding]) -> list[str]:
    keywords: list[str] = []
    for finding in findings:
        keywords.extend(_string_list(finding.tags))
        keywords.extend(_string_list(finding.metadata.get("question_hints")))
        keywords.extend(_string_list(finding.metadata.get("topic_hints")))
    return _dedupe(keywords[:8])


def _finding_ref(finding: ResearchFinding) -> str:
    record_fingerprint = _strip_or_none(finding.metadata.get("record_fingerprint"))
    if record_fingerprint:
        return f"finding:{record_fingerprint}"
    stable_payload = {
        "claim": finding.claim,
        "stance": finding.stance,
        "summary": finding.summary,
        "source_url": finding.source_url,
        "tags": list(finding.tags),
    }
    digest = hashlib.sha256(json.dumps(stable_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"finding:{digest[:16]}"


def _stable_ref(prefix: str, market_id: str, run_id: str | None, *parts: str) -> str:
    payload = {
        "prefix": prefix,
        "market_id": market_id,
        "run_id": run_id,
        "parts": [part for part in parts if _strip_or_none(part)],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _normalize_topic(value: str) -> str:
    text = _strip_or_none(value) or "general"
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "general"


def _prefixed_refs(prefix: str, values: Iterable[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        text = _strip_or_none(value)
        if not text:
            continue
        refs.append(text if text.startswith(f"{prefix}:") else f"{prefix}:{text}")
    return refs
