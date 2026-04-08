from __future__ import annotations

import json
import math
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import (
    EvidencePacket,
    MarketSnapshot,
    PacketCompatibilityMode,
    SourceKind,
    VenueName,
    _source_refs,
    _utc_datetime,
    _utc_now,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _strip_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _preview(text: str | None, limit: int = 240) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def _normalize_stance(value: str | None) -> str:
    if not value:
        return "neutral"
    lowered = value.strip().lower()
    bullish_tokens = {
        "bullish",
        "support",
        "positive",
        "yes",
        "long",
        "up",
        "higher",
        "increase",
        "likely yes",
        "likely",
    }
    bearish_tokens = {
        "bearish",
        "oppose",
        "negative",
        "no",
        "short",
        "down",
        "lower",
        "decrease",
        "likely no",
        "unlikely",
    }
    neutral_tokens = {"neutral", "mixed", "unclear", "unknown", "uncertain", "hold", "wait"}
    if lowered in bullish_tokens or any(token in lowered for token in ("bullish", "support", "yes", "long", "higher", "increase")):
        return "bullish"
    if lowered in bearish_tokens or any(token in lowered for token in ("bearish", "oppose", "no", "short", "lower", "decrease")):
        return "bearish"
    if lowered in neutral_tokens:
        return "neutral"
    return "neutral"


def _source_kind_weight(source_kind: SourceKind) -> float:
    return {
        SourceKind.official: 0.92,
        SourceKind.market: 0.84,
        SourceKind.news: 0.76,
        SourceKind.social: 0.58,
        SourceKind.model: 0.64,
        SourceKind.manual: 0.52,
        SourceKind.other: 0.48,
    }.get(source_kind, 0.5)


def _theme_from_metadata(metadata: Mapping[str, Any], tags: Iterable[str] | None = None) -> str | None:
    for key in ("theme", "category", "topic", "cluster"):
        value = _strip_or_none(metadata.get(key))
        if value:
            return value.lower()
    if tags:
        for tag in tags:
            value = _strip_or_none(tag)
            if value:
                return value.lower()
    return None


def _reference_source_label(source_name: str | None, source_url: str | None) -> str | None:
    text = " ".join(part for part in [_strip_or_none(source_name), _strip_or_none(source_url)] if part).lower()
    if "metaculus" in text:
        return "metaculus"
    if "manifold" in text:
        return "manifold"
    return None


def _reference_probability_hint(finding: "ResearchFinding") -> float | None:
    metadata = dict(finding.metadata)
    payload = metadata.get("payload") if isinstance(metadata.get("payload"), Mapping) else {}
    for candidate in (
        metadata.get("probability_yes"),
        metadata.get("forecast_probability_yes"),
        metadata.get("market_probability_yes"),
        metadata.get("probability"),
        metadata.get("chance"),
        metadata.get("estimate"),
        payload.get("probability_yes") if isinstance(payload, Mapping) else None,
        payload.get("forecast_probability_yes") if isinstance(payload, Mapping) else None,
        payload.get("market_probability_yes") if isinstance(payload, Mapping) else None,
        payload.get("probability") if isinstance(payload, Mapping) else None,
        payload.get("chance") if isinstance(payload, Mapping) else None,
        payload.get("estimate") if isinstance(payload, Mapping) else None,
    ):
        if candidate is None:
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if 0.0 <= value <= 1.0:
            return round(value, 6)
    return None


class ExternalReference(BaseModel):
    schema_version: str = "v1"
    reference_id: str = Field(default_factory=lambda: f"eref_{uuid4().hex[:12]}")
    reference_source: str = "external"
    source_name: str | None = None
    source_url: str | None = None
    source_kind: SourceKind = SourceKind.other
    signal_id: str = ""
    captured_at: datetime | None = None
    reference_probability_yes: float | None = None
    market_probability_yes_hint: float | None = None
    forecast_probability_yes_hint: float | None = None
    market_delta_bps: float | None = None
    forecast_delta_bps: float | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reference_probability_yes", "market_probability_yes_hint", "forecast_probability_yes_hint")
    @classmethod
    def _clamp_probability(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _clamp01(value)

    @field_validator("market_delta_bps", "forecast_delta_bps")
    @classmethod
    def _normalize_delta(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)

    @model_validator(mode="after")
    def _normalize_model(self) -> "ExternalReference":
        self.reference_source = _strip_or_none(self.reference_source) or "external"
        self.source_name = _strip_or_none(self.source_name)
        self.source_url = _strip_or_none(self.source_url)
        self.signal_id = _strip_or_none(self.signal_id) or self.reference_id
        self.summary = _preview(self.summary, 240)
        if self.captured_at is not None:
            self.captured_at = self.captured_at.astimezone(timezone.utc)
        return self


def score_freshness(
    finding: "ResearchFinding",
    *,
    reference_time: datetime | None = None,
    half_life_hours: float = 24.0,
) -> float:
    reference = reference_time or _utc_now()
    timestamp = finding.published_at or finding.observed_at
    if timestamp is None:
        base = 0.55
    else:
        delta = max(0.0, (reference - timestamp).total_seconds() / 3600.0)
        base = math.exp(-delta / max(0.1, float(half_life_hours)))
    source_bonus = {
        SourceKind.official: 0.08,
        SourceKind.market: 0.06,
        SourceKind.news: 0.05,
        SourceKind.social: 0.02,
        SourceKind.model: 0.0,
        SourceKind.manual: 0.0,
        SourceKind.other: 0.0,
    }.get(finding.source_kind, 0.0)
    recency_bonus = 0.03 if finding.summary else 0.0
    provenance_bonus = 0.02 if finding.source_url else 0.0
    return _clamp01(base + source_bonus + recency_bonus + provenance_bonus)


def score_credibility(finding: "ResearchFinding") -> float:
    base = _source_kind_weight(finding.source_kind)
    if finding.source_url:
        base += 0.05
    if finding.raw_text:
        raw_len = len(finding.raw_text.strip())
        if raw_len >= 50:
            base += 0.03
        elif raw_len >= 20:
            base += 0.02
    if finding.summary:
        base += 0.02
    if finding.tags:
        base += min(0.03, len(finding.tags) * 0.01)
    if finding.confidence < 0.35:
        base -= 0.05
    return _clamp01(base)


class ResearchFinding(BaseModel):
    schema_version: str = "v1"
    source_kind: SourceKind = SourceKind.manual
    claim: str
    stance: str = "neutral"
    summary: str = ""
    source_url: str | None = None
    raw_text: str | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None
    confidence: float = 0.5
    freshness_score: float = 0.5
    credibility_score: float = 0.5
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("claim", "summary", "stance", "source_url", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if value is None:
            return value
        text = str(value).strip()
        return text

    @field_validator("confidence", "freshness_score", "credibility_score")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return _clamp01(value)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized: list[str] = []
        for item in candidates:
            tag = _strip_or_none(item)
            if tag is not None:
                normalized.append(tag)
        return normalized

    @model_validator(mode="after")
    def _normalize_model(self) -> "ResearchFinding":
        self.claim = _preview(self.claim, 500) or self.claim.strip()
        self.summary = _preview(self.summary or self.claim, 240)
        self.stance = _normalize_stance(self.stance)
        if self.source_url is not None:
            self.source_url = _strip_or_none(self.source_url)
        return self

    @property
    def theme(self) -> str | None:
        return _theme_from_metadata(self.metadata, self.tags)

    @property
    def evidence_weight(self) -> float:
        return round(self.confidence * self.freshness_score * self.credibility_score, 6)


class ResearchSynthesis(BaseModel):
    schema_version: str = "v1"
    synthesis_id: str = Field(default_factory=lambda: f"rsyn_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    finding_count: int = 0
    evidence_count: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    bullish_weight: float = 0.0
    bearish_weight: float = 0.0
    neutral_weight: float = 0.0
    net_bias: float = 0.0
    dominant_stance: str = "neutral"
    average_confidence: float = 0.0
    average_freshness: float = 0.0
    average_credibility: float = 0.0
    average_evidence_weight: float = 0.0
    external_reference_count: int = 0
    external_references: list[ExternalReference] = Field(default_factory=list)
    market_probability_yes_hint: float | None = None
    forecast_probability_yes_hint: float | None = None
    market_delta_bps: float | None = None
    forecast_delta_bps: float | None = None
    themes: list[str] = Field(default_factory=list)
    top_claims: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "average_confidence",
        "average_freshness",
        "average_credibility",
        "average_evidence_weight",
        "bullish_weight",
        "bearish_weight",
        "neutral_weight",
        "net_bias",
        "market_delta_bps",
        "forecast_delta_bps",
    )
    @classmethod
    def _clamp_float(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return float(value)


class ResearchBaseRateSummary(BaseModel):
    schema_version: str = "v1"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    finding_count: int = 0
    bullish_share: float = 0.0
    bearish_share: float = 0.0
    neutral_share: float = 0.0
    bullish_weight_share: float = 0.0
    bearish_weight_share: float = 0.0
    neutral_weight_share: float = 0.0
    estimated_base_rate_yes: float = 0.5
    signal_dispersion: float = 0.0
    source_kind_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchRetrievalSummary(BaseModel):
    schema_version: str = "v1"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    retrieval_policy: str = "research_inputs"
    input_count: int = 0
    normalized_count: int = 0
    deduplicated_count: int = 0
    duplicate_count: int = 0
    duplicate_rate: float = 0.0
    evidence_count: int = 0
    external_url_count: int = 0
    external_url_rate: float = 0.0
    source_kind_counts: dict[str, int] = Field(default_factory=dict)
    retrieval_status: str = "empty"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchAbstentionPolicy(BaseModel):
    schema_version: str = "v1"
    policy_id: str = Field(default_factory=lambda: f"rabst_{uuid4().hex[:12]}")
    policy_version: str = "research_abstention_v1"
    policy_scope: str = "research_only"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    abstain: bool = False
    status: str = "proceed"
    reason_codes: list[str] = Field(default_factory=list)
    finding_count: int = 0
    evidence_count: int = 0
    duplicate_rate: float = 0.0
    completeness_score: float = 1.0
    average_confidence: float = 0.0
    average_evidence_weight: float = 0.0
    net_bias: float = 0.0
    signal_strength: float = 0.0
    abstention_score: float = 0.0
    applied: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchPipelineSurface(BaseModel):
    schema_version: str = "v1"
    pipeline_id: str = Field(default_factory=lambda: f"rpipe_{uuid4().hex[:12]}")
    pipeline_version: str = "research_pipeline_v1"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    pipeline_summary: str = ""
    pipeline_steps: list[dict[str, Any]] = Field(default_factory=list)
    base_rates: ResearchBaseRateSummary
    retrieval: ResearchRetrievalSummary
    synthesis: ResearchSynthesis | None = None
    abstention_policy: ResearchAbstentionPolicy
    public_metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_research_abstention_metrics(
    pipeline: ResearchPipelineSurface,
    *,
    applied: bool | None = None,
) -> dict[str, Any]:
    policy = pipeline.abstention_policy
    synthesis = pipeline.synthesis
    retrieval = pipeline.retrieval
    base_rates = pipeline.base_rates
    return {
        "pipeline_version": pipeline.pipeline_version,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "policy_scope": policy.policy_scope,
        "status": policy.status,
        "abstain": policy.abstain,
        "applied": policy.applied if applied is None else bool(applied),
        "reason_codes": list(policy.reason_codes),
        "finding_count": policy.finding_count,
        "evidence_count": policy.evidence_count,
        "duplicate_rate": round(policy.duplicate_rate, 6),
        "completeness_score": round(policy.completeness_score, 6),
        "average_confidence": round(policy.average_confidence, 6),
        "average_evidence_weight": round(policy.average_evidence_weight, 6),
        "net_bias": round(policy.net_bias, 6),
        "signal_strength": round(policy.signal_strength, 6),
        "abstention_score": round(policy.abstention_score, 6),
        "estimated_base_rate_yes": round(base_rates.estimated_base_rate_yes, 6),
        "base_rate_bullish_share": round(base_rates.bullish_share, 6),
        "base_rate_bearish_share": round(base_rates.bearish_share, 6),
        "base_rate_neutral_share": round(base_rates.neutral_share, 6),
        "base_rate_bullish_weight_share": round(base_rates.bullish_weight_share, 6),
        "base_rate_bearish_weight_share": round(base_rates.bearish_weight_share, 6),
        "base_rate_neutral_weight_share": round(base_rates.neutral_weight_share, 6),
        "retrieval_policy": retrieval.retrieval_policy,
        "retrieval_status": retrieval.retrieval_status,
        "retrieval_input_count": retrieval.input_count,
        "retrieval_normalized_count": retrieval.normalized_count,
        "retrieval_deduplicated_count": retrieval.deduplicated_count,
        "retrieval_duplicate_count": retrieval.duplicate_count,
        "retrieval_duplicate_rate": round(retrieval.duplicate_rate, 6),
        "retrieval_evidence_count": retrieval.evidence_count,
        "retrieval_external_url_count": retrieval.external_url_count,
        "retrieval_external_url_rate": round(retrieval.external_url_rate, 6),
        "retrieval_source_kind_counts": dict(sorted(retrieval.source_kind_counts.items())),
        "dominant_stance": None if synthesis is None else synthesis.dominant_stance,
        "pipeline_summary": pipeline.pipeline_summary,
    }


class SidecarSignalPacket(BaseModel):
    schema_version: str = "v1"
    signal_id: str = Field(default_factory=lambda: f"ssig_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    sidecar_name: str | None = None
    source_kind: SourceKind = SourceKind.manual
    classification: str = "signal"
    signal_only: bool = False
    claim: str
    summary: str = ""
    source_url: str | None = None
    evidence_id: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=_utc_now)
    published_at: datetime | None = None
    confidence: float = 0.5
    freshness_score: float = 0.5
    credibility_score: float = 0.5
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("claim", "summary", "classification", "source_url", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("confidence", "freshness_score", "credibility_score")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return _clamp01(value)

    @field_validator("artifact_refs", "provenance_refs", "evidence_refs", "tags", mode="before")
    @classmethod
    def _normalize_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        return _source_refs(candidates)

    @model_validator(mode="after")
    def _normalize_model(self) -> "SidecarSignalPacket":
        self.claim = _preview(self.claim, 500) or self.claim.strip()
        self.summary = _preview(self.summary or self.claim, 240)
        self.classification = _strip_or_none(self.classification) or "signal"
        self.signal_only = bool(self.signal_only or self.classification == "signal-only")
        self.source_url = _strip_or_none(self.source_url)
        self.tags = [tag for tag in (_strip_or_none(tag) for tag in self.tags) if tag]
        self.artifact_refs = _source_refs(self.artifact_refs)
        self.provenance_refs = _source_refs(self.provenance_refs)
        self.evidence_refs = _source_refs(self.evidence_refs)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class ResearchProvenanceBundle(BaseModel):
    schema_version: str = "v1"
    provenance_id: str = Field(default_factory=lambda: f"rprov_{uuid4().hex[:12]}")
    bundle_kind: str = "research_provenance"
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    sidecar_name: str | None = None
    classification: str = "signal"
    classification_reasons: list[str] = Field(default_factory=list)
    source_path: str | None = None
    observed_at: datetime = Field(default_factory=_utc_now)
    finding_count: int = 0
    evidence_count: int = 0
    signal_packet_count: int = 0
    source_kind_counts: dict[str, int] = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    signal_packet_refs: list[str] = Field(default_factory=list)
    packet_refs: dict[str, str] = Field(default_factory=dict)
    sidecar_health: dict[str, Any] = Field(default_factory=dict)
    freshness_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("freshness_score")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return _clamp01(value)

    @field_validator("classification", "sidecar_name", "source_path", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if value is None:
            return value
        text = str(value).strip()
        return text or None

    @field_validator("artifact_refs", "evidence_refs", "provenance_refs", "social_context_refs", "signal_packet_refs", mode="before")
    @classmethod
    def _normalize_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized: list[str] = []
        for item in candidates:
            text = _strip_or_none(item)
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @field_validator("packet_refs", mode="before")
    @classmethod
    def _normalize_packet_refs(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        return {str(key): str(val) for key, val in dict(value).items()}

    @model_validator(mode="after")
    def _normalize_bundle(self) -> "ResearchProvenanceBundle":
        self.classification = _strip_or_none(self.classification) or "signal"
        self.classification_reasons = _source_refs(self.classification_reasons)
        self.observed_at = _utc_datetime(self.observed_at) or _utc_now()
        self.artifact_refs = _source_refs(self.artifact_refs)
        self.evidence_refs = _source_refs(self.evidence_refs)
        self.provenance_refs = _source_refs(self.provenance_refs)
        self.social_context_refs = _source_refs(self.social_context_refs)
        self.signal_packet_refs = _source_refs(self.signal_packet_refs)
        self.source_kind_counts = dict(sorted({str(key): int(value) for key, value in self.source_kind_counts.items()}.items()))
        self.freshness_score = _clamp01(self.freshness_score)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class ResearchBridgeBundle(BaseModel):
    schema_version: str = "v1"
    bundle_id: str = Field(default_factory=lambda: f"rbridge_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    bundle_contract_id: str = ""
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.social_bridge
    market_only_compatible: bool = True
    sidecar_name: str | None = None
    sidecar_health: dict[str, Any] = Field(default_factory=dict)
    classification: str = "signal"
    classification_reasons: list[str] = Field(default_factory=list)
    market_id: str
    venue: VenueName = VenueName.polymarket
    run_id: str | None = None
    findings: list[ResearchFinding] = Field(default_factory=list)
    synthesis: ResearchSynthesis | None = None
    pipeline: ResearchPipelineSurface | None = None
    abstention_policy: ResearchAbstentionPolicy | None = None
    provenance_bundle: ResearchProvenanceBundle | None = None
    signal_packets: list[SidecarSignalPacket] = Field(default_factory=list)
    source_bundle_content_hash: str | None = None
    source_bundle_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    packet_refs: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    freshness_score: float = 0.0
    content_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("packet_version", mode="before")
    @classmethod
    def _normalize_packet_version(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else "1.0.0"
        return text or "1.0.0"

    @field_validator("bundle_contract_id", mode="before")
    @classmethod
    def _normalize_bundle_contract_id(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        return text

    @field_validator("artifact_refs", "evidence_refs", "social_context_refs", mode="before")
    @classmethod
    def _normalize_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized: list[str] = []
        for item in candidates:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @field_validator("packet_refs", mode="before")
    @classmethod
    def _normalize_packet_refs(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        return {str(key): str(val) for key, val in dict(value).items()}

    @field_validator("source_bundle_content_hash", mode="before")
    @classmethod
    def _normalize_source_bundle_content_hash(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("source_bundle_refs", mode="before")
    @classmethod
    def _normalize_source_bundle_refs(cls, value: Any) -> list[str]:
        return _source_refs(value or [])

    @model_validator(mode="after")
    def _normalize_bundle(self) -> "ResearchBridgeBundle":
        if self.compatibility_mode == PacketCompatibilityMode.market_only:
            self.market_only_compatible = True
        self.classification = _strip_or_none(self.classification) or "signal"
        self.classification_reasons = _source_refs(self.classification_reasons)
        self.findings = list(self.findings)
        self.signal_packets = list(self.signal_packets)
        if self.source_bundle_content_hash is None:
            self.source_bundle_content_hash = _strip_or_none(
                self.metadata.get("source_bundle_content_hash") or self.metadata.get("sidecar_bundle_content_hash")
            )
        self.source_bundle_refs = _source_refs(
            self.source_bundle_refs,
            self.metadata.get("source_bundle_refs", []),
            self.metadata.get("sidecar_bundle_refs", []),
            self.source_bundle_content_hash,
        )
        self.artifact_refs = _source_refs(
            self.artifact_refs,
            [ref for packet in self.signal_packets for ref in packet.artifact_refs],
            self.social_context_refs,
        )
        self.evidence_refs = _source_refs(self.evidence_refs)
        if not self.evidence_refs and self.signal_packets:
            self.evidence_refs = _source_refs(packet.evidence_id for packet in self.signal_packets if packet.evidence_id)
        signal_provenance = []
        for packet in self.signal_packets:
            signal_provenance.extend(packet.provenance_refs)
        self.provenance_refs = _source_refs(self.provenance_refs, signal_provenance, self.social_context_refs)
        if self.provenance_bundle is None:
            self.provenance_bundle = build_research_provenance_bundle(
                self.findings,
                evidence_refs=self.evidence_refs,
                signal_packets=self.signal_packets,
                market_id=self.market_id,
                venue=self.venue,
                run_id=self.run_id,
                sidecar_name=self.sidecar_name,
                classification=self.classification,
                classification_reasons=self.classification_reasons,
                source_path=self.metadata.get("source_path") or self.metadata.get("sidecar_source_path"),
                sidecar_health=self.sidecar_health,
                reference_time=self.created_at,
                social_context_refs=self.social_context_refs,
                packet_refs=self.packet_refs,
            )
        else:
            self.provenance_bundle = self.provenance_bundle.model_copy(deep=True)
        if not self.freshness_score:
            freshness_values = [finding.freshness_score for finding in self.findings]
            if freshness_values:
                self.freshness_score = round(sum(freshness_values) / len(freshness_values), 6)
            elif self.provenance_bundle is not None:
                self.freshness_score = self.provenance_bundle.freshness_score
        if self.provenance_bundle is not None:
            self.metadata.setdefault("provenance_bundle", self.provenance_bundle.model_dump(mode="json"))
            self.metadata.setdefault("provenance_bundle_content_hash", self.provenance_bundle.content_hash)
            self.metadata.setdefault("provenance_bundle_freshness_score", self.provenance_bundle.freshness_score)
        if self.source_bundle_content_hash is not None:
            self.metadata.setdefault("source_bundle_content_hash", self.source_bundle_content_hash)
        if self.source_bundle_refs:
            self.metadata.setdefault("source_bundle_refs", list(self.source_bundle_refs))
        if not self.bundle_contract_id:
            self.bundle_contract_id = (
                f"{self.schema_version}:research_bridge:{self.packet_version}:{self.compatibility_mode.value}:{self.classification}"
            )
        self.metadata.setdefault("bundle_contract_id", self.bundle_contract_id)
        if self.pipeline is not None and self.abstention_policy is None:
            self.abstention_policy = self.pipeline.abstention_policy
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ResearchBridgeBundle":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SidecarClassificationSummary:
    classification: str
    reasons: list[str]
    signal_only: bool


def classify_sidecar_health(
    *,
    healthy: bool,
    alerts: Sequence[str] | None = None,
    issues: Sequence[str] | None = None,
    force_signal_only: bool | None = None,
) -> SidecarClassificationSummary:
    reasons = _source_refs(alerts or [], issues or [])
    if force_signal_only is None:
        signal_only = (not healthy) or bool(reasons)
    else:
        signal_only = force_signal_only
    classification = "signal-only" if signal_only else "signal"
    return SidecarClassificationSummary(classification=classification, reasons=reasons, signal_only=signal_only)


def annotate_sidecar_findings(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    run_id: str | None = None,
    source_kind: SourceKind | None = None,
    reference_time: datetime | None = None,
    sidecar_name: str,
    sidecar_health: Mapping[str, Any] | None = None,
    classification: str = "signal",
    classification_reasons: Sequence[str] | None = None,
    source_path: str | None = None,
) -> list[ResearchFinding]:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        source_kind=source_kind,
        reference_time=reference_time,
    )
    reasons = _source_refs(classification_reasons or [])
    health_payload = dict(sidecar_health or {})
    for finding in normalized:
        metadata = dict(finding.metadata)
        metadata["sidecar_name"] = sidecar_name
        metadata["source_channel"] = sidecar_name
        metadata["classification"] = classification
        metadata["classification_reasons"] = list(reasons)
        metadata["sidecar_health"] = health_payload
        if source_path:
            metadata.setdefault("sidecar_source_path", source_path)
        if classification == "signal-only":
            metadata["signal_only"] = True
        finding.metadata = metadata
    return normalized


def build_sidecar_research_bundle(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    reference_time: datetime | None = None,
    snapshot: MarketSnapshot | None = None,
    forecast_probability_yes: float | None = None,
    sidecar_name: str,
    sidecar_health: Mapping[str, Any] | None = None,
    classification: str = "signal",
    classification_reasons: Sequence[str] | None = None,
    source_path: str | None = None,
    source_bundle_content_hash: str | None = None,
    source_bundle_refs: Sequence[str] | None = None,
    pipeline: ResearchPipelineSurface | None = None,
) -> ResearchBridgeBundle:
    normalized = annotate_sidecar_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
        sidecar_name=sidecar_name,
        sidecar_health=sidecar_health,
        classification=classification,
        classification_reasons=classification_reasons,
        source_path=source_path,
    )
    synthesis = synthesize_research(
        normalized,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=reference_time,
        snapshot=snapshot,
        forecast_probability_yes=forecast_probability_yes,
    )
    evidence = findings_to_evidence(
        normalized,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=reference_time,
    )
    signal_packets = build_signal_packets(
        normalized,
        evidence=evidence,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        sidecar_name=sidecar_name,
        classification=classification,
        classification_reasons=classification_reasons,
        sidecar_health=sidecar_health,
        source_path=source_path,
    )
    artifact_refs = _source_refs(
        source_path,
        [packet.evidence_id for packet in signal_packets if packet.evidence_id],
        [ref for packet in signal_packets for ref in packet.artifact_refs],
    )
    freshness_values = [finding.freshness_score for finding in normalized]
    if pipeline is None:
        pipeline = build_research_pipeline_surface(
            normalized,
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=reference_time,
            snapshot=snapshot,
            forecast_probability_yes=forecast_probability_yes,
            retrieval_policy="sidecar_findings",
            input_count=len(normalized),
            evidence_count=len(evidence),
            applied=False,
        )
    abstention_metrics = build_research_abstention_metrics(pipeline)
    provenance_bundle = build_research_provenance_bundle(
        normalized,
        evidence=evidence,
        signal_packets=signal_packets,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        sidecar_name=sidecar_name,
        classification=classification,
        classification_reasons=classification_reasons,
        source_path=source_path,
        sidecar_health=sidecar_health,
        reference_time=reference_time,
        social_context_refs=[source_path] if source_path else None,
    )
    return ResearchBridgeBundle(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        findings=normalized,
        synthesis=synthesis,
        pipeline=pipeline,
        abstention_policy=pipeline.abstention_policy,
        provenance_bundle=provenance_bundle,
        signal_packets=signal_packets,
        source_bundle_content_hash=source_bundle_content_hash,
        source_bundle_refs=_source_refs(source_bundle_refs or [], source_bundle_content_hash, source_path),
        artifact_refs=artifact_refs,
        evidence_refs=[packet.evidence_id for packet in evidence],
        provenance_refs=_source_refs(
            source_path or "",
            [ref for packet in signal_packets for ref in packet.provenance_refs],
        ),
        sidecar_name=sidecar_name,
        sidecar_health=dict(sidecar_health or {}),
        classification=classification,
        classification_reasons=list(_source_refs(classification_reasons or [])),
        freshness_score=round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else 0.0,
        metadata={
            "finding_count": len(normalized),
            "evidence_count": len(evidence),
            "signal_packet_count": len(signal_packets),
            "sidecar_name": sidecar_name,
            "classification": classification,
            "classification_reasons": list(_source_refs(classification_reasons or [])),
            "sidecar_health": dict(sidecar_health or {}),
            "source_path": source_path,
            "source_bundle_content_hash": source_bundle_content_hash,
            "source_bundle_refs": _source_refs(source_bundle_refs or [], source_bundle_content_hash, source_path),
            "artifact_refs": artifact_refs,
            "freshness_score": round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else 0.0,
            "provenance_bundle": provenance_bundle.model_dump(mode="json"),
            "provenance_bundle_content_hash": provenance_bundle.content_hash,
            "provenance_bundle_freshness_score": provenance_bundle.freshness_score,
            "pipeline_summary": pipeline.pipeline_summary,
            "public_metrics": dict(pipeline.public_metrics),
            "abstention_policy": pipeline.abstention_policy.model_dump(mode="json"),
            "abstention_metrics": abstention_metrics,
            "content_hash": _stable_content_hash(
                {
                    "market_id": market_id,
                    "venue": venue.value,
                    "run_id": run_id,
                    "finding_count": len(normalized),
                    "evidence_refs": [packet.evidence_id for packet in evidence],
                    "signal_packet_refs": [packet.signal_id for packet in signal_packets],
                    "artifact_refs": artifact_refs,
                    "classification": classification,
                    "classification_reasons": list(_source_refs(classification_reasons or [])),
                    "pipeline_summary": pipeline.pipeline_summary,
                }
            ),
        },
    )


@dataclass(frozen=True)
class ResearchHealthSummary:
    status: str
    completeness_score: float
    duplicate_count: int
    issues: list[str]
    alerts: list[str]
    source_kinds: list[SourceKind]


def normalize_finding(
    finding: ResearchFinding | EvidencePacket | Mapping[str, Any] | str,
    *,
    market_id: str | None = None,
    run_id: str | None = None,
    source_kind: SourceKind | None = None,
    reference_time: datetime | None = None,
) -> ResearchFinding:
    if isinstance(finding, ResearchFinding):
        normalized = finding.model_copy(deep=True)
    elif isinstance(finding, EvidencePacket):
        normalized = ResearchFinding(
            source_kind=finding.source_kind,
            claim=finding.claim,
            stance=finding.stance,
            summary=finding.summary,
            source_url=finding.source_url,
            raw_text=finding.raw_text,
            observed_at=finding.observed_at,
            published_at=finding.published_at,
            confidence=finding.confidence,
            freshness_score=finding.freshness_score,
            credibility_score=finding.credibility_score,
            tags=list(finding.tags),
            metadata=dict(finding.metadata),
        )
    elif isinstance(finding, Mapping):
        payload = dict(finding)
        claim = payload.get("claim") or payload.get("summary") or payload.get("text") or payload.get("content") or payload.get("raw_text") or "research finding"
        normalized = ResearchFinding(
            source_kind=payload.get("source_kind", source_kind or SourceKind.manual),
            claim=claim,
            stance=payload.get("stance", "neutral"),
            summary=payload.get("summary") or "",
            source_url=payload.get("source_url"),
            raw_text=payload.get("raw_text") or payload.get("text") or payload.get("content"),
            observed_at=payload.get("observed_at"),
            published_at=payload.get("published_at"),
            confidence=payload.get("confidence", 0.5),
            freshness_score=payload.get("freshness_score", 0.5),
            credibility_score=payload.get("credibility_score", 0.5),
            tags=payload.get("tags", []),
            metadata=dict(payload.get("metadata", {})),
        )
    else:
        text = str(finding).strip()
        normalized = ResearchFinding(
            source_kind=source_kind or SourceKind.manual,
            claim=text,
            stance=_normalize_stance(text),
            summary=text[:240],
            raw_text=text,
            confidence=0.5,
            freshness_score=0.5,
            credibility_score=0.5,
        )

    if market_id:
        normalized.metadata.setdefault("market_id", market_id)
    if run_id:
        normalized.metadata.setdefault("run_id", run_id)
    normalized.source_kind = source_kind or normalized.source_kind
    normalized.stance = _normalize_stance(normalized.stance)
    normalized.claim = _preview(normalized.claim, 500)
    normalized.summary = _preview(normalized.summary or normalized.claim, 240)
    normalized.source_url = _strip_or_none(normalized.source_url)
    normalized.tags = [tag for tag in (_strip_or_none(tag) for tag in normalized.tags) if tag]

    if normalized.freshness_score in (0.0, 0.5):
        normalized.freshness_score = score_freshness(normalized, reference_time=reference_time)
    else:
        normalized.freshness_score = _clamp01(normalized.freshness_score)
    if normalized.credibility_score in (0.0, 0.5):
        normalized.credibility_score = score_credibility(normalized)
    else:
        normalized.credibility_score = _clamp01(normalized.credibility_score)
    normalized.confidence = _clamp01(normalized.confidence)
    return normalized


def normalize_findings(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str | None = None,
    run_id: str | None = None,
    source_kind: SourceKind | None = None,
    reference_time: datetime | None = None,
) -> list[ResearchFinding]:
    return [
        normalize_finding(
            finding,
            market_id=market_id,
            run_id=run_id,
            source_kind=source_kind,
            reference_time=reference_time,
        )
        for finding in findings
    ]


def _build_external_references(
    findings: Sequence[ResearchFinding],
    *,
    market_probability_yes_hint: float | None,
    forecast_probability_yes_hint: float | None,
) -> list[ExternalReference]:
    references: list[ExternalReference] = []
    for finding in findings:
        source_name = _strip_or_none(
            finding.metadata.get("source_name")
            or finding.metadata.get("source")
            or finding.metadata.get("reference_source")
        )
        source_label = _reference_source_label(source_name, finding.source_url)
        if source_label is None:
            continue
        reference_probability_yes = _reference_probability_hint(finding)
        market_delta_bps = (
            round((reference_probability_yes - market_probability_yes_hint) * 10_000.0, 2)
            if reference_probability_yes is not None and market_probability_yes_hint is not None
            else None
        )
        forecast_delta_bps = (
            round((reference_probability_yes - forecast_probability_yes_hint) * 10_000.0, 2)
            if reference_probability_yes is not None and forecast_probability_yes_hint is not None
            else None
        )
        references.append(
            ExternalReference(
                reference_source=source_label,
                source_name=source_name,
                source_url=finding.source_url,
                source_kind=SourceKind.market,
                signal_id=str(finding.metadata.get("signal_id") or finding.metadata.get("record_id") or finding.claim[:24]),
                captured_at=finding.published_at or finding.observed_at,
                reference_probability_yes=reference_probability_yes,
                market_probability_yes_hint=market_probability_yes_hint,
                forecast_probability_yes_hint=forecast_probability_yes_hint,
                market_delta_bps=market_delta_bps,
                forecast_delta_bps=forecast_delta_bps,
                summary=finding.summary or finding.claim,
                metadata={
                    "market_id": finding.metadata.get("market_id"),
                    "run_id": finding.metadata.get("run_id"),
                    "theme": finding.theme,
                    "stance": finding.stance,
                    "source_kind": finding.source_kind.value,
                    "payload": finding.metadata.get("payload"),
                },
            )
        )
    return references


def _average_optional(values: Sequence[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return round(sum(cleaned) / len(cleaned), 6)


def synthesize_research(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    reference_time: datetime | None = None,
    snapshot: MarketSnapshot | None = None,
    forecast_probability_yes: float | None = None,
) -> ResearchSynthesis:
    normalized = normalize_findings(findings, market_id=market_id, run_id=run_id, reference_time=reference_time)
    if not normalized:
        return ResearchSynthesis(market_id=market_id, venue=venue, run_id=run_id, summary="No findings available.")

    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    weights = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    confidences = []
    freshnesses = []
    credibilities = []
    themes: list[str] = []
    top_claims: list[str] = []
    for finding in normalized:
        stance = _normalize_stance(finding.stance)
        counts[stance] = counts.get(stance, 0) + 1
        weight = finding.evidence_weight
        weights[stance] = weights.get(stance, 0.0) + weight
        confidences.append(finding.confidence)
        freshnesses.append(finding.freshness_score)
        credibilities.append(finding.credibility_score)
        if finding.theme and finding.theme not in themes:
            themes.append(finding.theme)
        if finding.claim not in top_claims:
            top_claims.append(finding.claim)

    total_weight = sum(weights.values()) or 1.0
    net_bias = round((weights["bullish"] - weights["bearish"]) / total_weight, 6)
    dominant_stance = max(weights.items(), key=lambda item: item[1])[0]
    market_probability_yes_hint = None
    if snapshot is not None:
        market_probability_yes_hint = snapshot.midpoint_yes if snapshot.midpoint_yes is not None else snapshot.yes_price
    if market_probability_yes_hint is None:
        market_probability_yes_hint = 0.5
    external_references = _build_external_references(
        normalized,
        market_probability_yes_hint=market_probability_yes_hint,
        forecast_probability_yes_hint=forecast_probability_yes,
    )
    summary_parts = [
        f"{len(normalized)} findings",
        f"{counts['bullish']} bullish",
        f"{counts['bearish']} bearish",
        f"{counts['neutral']} neutral",
    ]
    if themes:
        summary_parts.append(f"themes={', '.join(themes[:5])}")
    if top_claims:
        summary_parts.append(f"top={'; '.join(top_claims[:3])}")
    if external_references:
        summary_parts.append(
            f"external_refs={', '.join(dict.fromkeys(ref.reference_source for ref in external_references))}"
        )

    return ResearchSynthesis(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        finding_count=len(normalized),
        evidence_count=len(normalized),
        bullish_count=counts["bullish"],
        bearish_count=counts["bearish"],
        neutral_count=counts["neutral"],
        bullish_weight=round(weights["bullish"], 6),
        bearish_weight=round(weights["bearish"], 6),
        neutral_weight=round(weights["neutral"], 6),
        net_bias=net_bias,
        dominant_stance=dominant_stance,
        average_confidence=round(sum(confidences) / len(confidences), 6),
        average_freshness=round(sum(freshnesses) / len(freshnesses), 6),
        average_credibility=round(sum(credibilities) / len(credibilities), 6),
        average_evidence_weight=round(sum(finding.evidence_weight for finding in normalized) / len(normalized), 6),
        external_reference_count=len(external_references),
        external_references=external_references,
        market_probability_yes_hint=market_probability_yes_hint,
        forecast_probability_yes_hint=forecast_probability_yes,
        market_delta_bps=_average_optional([ref.market_delta_bps for ref in external_references]),
        forecast_delta_bps=_average_optional([ref.forecast_delta_bps for ref in external_references]),
        themes=themes,
        top_claims=top_claims[:5],
        summary="; ".join(summary_parts),
        metadata={"normalized_findings": len(normalized)},
    )


def _source_kind_counts(findings: Sequence[ResearchFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        key = finding.source_kind.value
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def estimate_base_rates(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    reference_time: datetime | None = None,
) -> ResearchBaseRateSummary:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    if not normalized:
        return ResearchBaseRateSummary(market_id=market_id, venue=venue, run_id=run_id)

    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    weights = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for finding in normalized:
        stance = _normalize_stance(finding.stance)
        counts[stance] = counts.get(stance, 0) + 1
        weights[stance] = round(weights.get(stance, 0.0) + finding.evidence_weight, 6)

    total_findings = len(normalized)
    total_weight = sum(weights.values()) or 1.0
    estimated_yes = (
        weights["bullish"] + (weights["neutral"] * 0.5)
    ) / total_weight
    return ResearchBaseRateSummary(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        finding_count=total_findings,
        bullish_share=round(counts["bullish"] / total_findings, 6),
        bearish_share=round(counts["bearish"] / total_findings, 6),
        neutral_share=round(counts["neutral"] / total_findings, 6),
        bullish_weight_share=round(weights["bullish"] / total_weight, 6),
        bearish_weight_share=round(weights["bearish"] / total_weight, 6),
        neutral_weight_share=round(weights["neutral"] / total_weight, 6),
        estimated_base_rate_yes=round(_clamp01(estimated_yes), 6),
        signal_dispersion=round(abs(weights["bullish"] - weights["bearish"]) / total_weight, 6),
        source_kind_counts=_source_kind_counts(normalized),
        metadata={"total_weight": round(total_weight, 6)},
    )


def build_research_pipeline_surface(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    reference_time: datetime | None = None,
    snapshot: MarketSnapshot | None = None,
    forecast_probability_yes: float | None = None,
    retrieval_policy: str = "research_inputs",
    input_count: int | None = None,
    evidence_count: int | None = None,
    applied: bool = False,
) -> ResearchPipelineSurface:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    unique_findings, duplicate_count, _ = dedupe_findings(
        normalized,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    health = assess_findings_health(unique_findings, duplicate_count=duplicate_count)
    synthesis = synthesize_research(
        unique_findings,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=reference_time,
        snapshot=snapshot,
        forecast_probability_yes=forecast_probability_yes,
    )
    base_rates = estimate_base_rates(
        unique_findings,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=reference_time,
    )
    normalized_count = len(normalized)
    deduplicated_count = len(unique_findings)
    resolved_input_count = normalized_count if input_count is None else input_count
    resolved_evidence_count = deduplicated_count if evidence_count is None else evidence_count
    duplicate_rate = round(duplicate_count / max(1, normalized_count), 6)
    external_url_count = sum(1 for finding in unique_findings if finding.source_url)
    external_url_rate = round(external_url_count / max(1, deduplicated_count), 6)
    source_kind_counts = _source_kind_counts(unique_findings)
    retrieval_status = "empty"
    if deduplicated_count > 0:
        retrieval_status = "degraded" if duplicate_rate > 0.5 or health.status != "healthy" else "ok"
    retrieval = ResearchRetrievalSummary(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        retrieval_policy=retrieval_policy,
        input_count=resolved_input_count,
        normalized_count=normalized_count,
        deduplicated_count=deduplicated_count,
        duplicate_count=duplicate_count,
        duplicate_rate=duplicate_rate,
        evidence_count=resolved_evidence_count,
        external_url_count=external_url_count,
        external_url_rate=external_url_rate,
        source_kind_counts=source_kind_counts,
        retrieval_status=retrieval_status,
        metadata={
            "health_status": health.status,
            "health_issues": list(health.issues),
            "health_alerts": list(health.alerts),
        },
    )

    average_confidence = synthesis.average_confidence if synthesis is not None else 0.0
    average_evidence_weight = synthesis.average_evidence_weight if synthesis is not None else 0.0
    net_bias = synthesis.net_bias if synthesis is not None else 0.0
    signal_strength = _clamp01(
        (abs(net_bias) * 0.55)
        + (average_evidence_weight * 0.25)
        + (health.completeness_score * 0.2)
    )
    abstention_reasons: list[str] = []
    abstention_score = 0.0
    if deduplicated_count == 0:
        abstention_reasons.append("no_research_findings")
        abstention_score += 0.7
    if health.completeness_score < 0.55:
        abstention_reasons.append("low_research_completeness")
        abstention_score += 0.3
    if duplicate_rate > 0.5:
        abstention_reasons.append("high_duplicate_rate")
        abstention_score += 0.25
    if synthesis is not None and abs(synthesis.net_bias) < 0.08 and synthesis.dominant_stance == "neutral":
        abstention_reasons.append("weak_directionality")
        abstention_score += 0.25
    if average_confidence < 0.45:
        abstention_reasons.append("low_average_confidence")
        abstention_score += 0.2
    if average_evidence_weight < 0.18:
        abstention_reasons.append("low_evidence_weight")
        abstention_score += 0.15
    if signal_strength < 0.22:
        abstention_reasons.append("signal_strength_too_low")
        abstention_score += 0.2
    wait_like_findings = [
        finding
        for finding in unique_findings
        if any(
            token in " ".join(part for part in [finding.claim, finding.summary, finding.raw_text or ""] if part).lower()
            for token in ("wait", "more data", "need more data", "uncertain", "hold", "not enough data")
        )
    ]
    if deduplicated_count > 0 and len(wait_like_findings) == deduplicated_count:
        abstention_reasons.append("explicit_wait_signal")
        abstention_score += 0.35
    abstention_score = round(min(1.0, abstention_score), 6)
    abstain = abstention_score >= 0.5
    abstention_policy = ResearchAbstentionPolicy(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        abstain=abstain,
        status="abstain" if abstain else "proceed",
        reason_codes=list(dict.fromkeys(abstention_reasons)),
        finding_count=deduplicated_count,
        evidence_count=resolved_evidence_count,
        duplicate_rate=duplicate_rate,
        completeness_score=round(health.completeness_score, 6),
        average_confidence=round(average_confidence, 6),
        average_evidence_weight=round(average_evidence_weight, 6),
        net_bias=round(net_bias, 6),
        signal_strength=round(signal_strength, 6),
        abstention_score=abstention_score,
        applied=applied,
        metadata={
            "health_status": health.status,
            "health_issues": list(health.issues),
            "health_alerts": list(health.alerts),
            "external_reference_count": 0 if synthesis is None else synthesis.external_reference_count,
        },
    )
    pipeline_steps = [
        {
            "name": "base_rates",
            "status": "ok" if base_rates.finding_count > 0 else "empty",
            "metrics": {
                "finding_count": base_rates.finding_count,
                "estimated_base_rate_yes": base_rates.estimated_base_rate_yes,
                "signal_dispersion": base_rates.signal_dispersion,
            },
        },
        {
            "name": "retrieval",
            "status": retrieval.retrieval_status,
            "metrics": {
                "input_count": retrieval.input_count,
                "normalized_count": retrieval.normalized_count,
                "deduplicated_count": retrieval.deduplicated_count,
                "duplicate_rate": retrieval.duplicate_rate,
                "external_url_rate": retrieval.external_url_rate,
            },
        },
        {
            "name": "synthesis",
            "status": "ok" if synthesis is not None and synthesis.finding_count > 0 else "empty",
            "metrics": {
                "finding_count": 0 if synthesis is None else synthesis.finding_count,
                "dominant_stance": None if synthesis is None else synthesis.dominant_stance,
                "net_bias": 0.0 if synthesis is None else synthesis.net_bias,
                "average_evidence_weight": 0.0 if synthesis is None else synthesis.average_evidence_weight,
            },
        },
        {
            "name": "abstention",
            "status": abstention_policy.status,
            "metrics": {
                "abstain": abstention_policy.abstain,
                "abstention_score": abstention_policy.abstention_score,
                "signal_strength": abstention_policy.signal_strength,
                "reason_codes": list(abstention_policy.reason_codes),
            },
        },
    ]
    pipeline_summary = (
        f"base_rates={base_rates.estimated_base_rate_yes:.3f}; "
        f"retrieval={retrieval.deduplicated_count}/{retrieval.input_count}; "
        f"synthesis={synthesis.dominant_stance if synthesis is not None else 'empty'}; "
        f"abstention={abstention_policy.status}"
    )
    return ResearchPipelineSurface(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        pipeline_summary=pipeline_summary,
        pipeline_steps=pipeline_steps,
        base_rates=base_rates,
        retrieval=retrieval,
        synthesis=synthesis,
        abstention_policy=abstention_policy,
        public_metrics={
            "finding_count": deduplicated_count,
            "evidence_count": resolved_evidence_count,
            "duplicate_rate": duplicate_rate,
            "completeness_score": round(health.completeness_score, 6),
            "signal_strength": abstention_policy.signal_strength,
            "abstain": abstention_policy.abstain,
            "abstention_score": abstention_policy.abstention_score,
            "estimated_base_rate_yes": base_rates.estimated_base_rate_yes,
            "net_bias": round(net_bias, 6),
        },
        metadata={
            "health_status": health.status,
            "health_issues": list(health.issues),
            "health_alerts": list(health.alerts),
            "input_count": resolved_input_count,
        },
    )


def findings_to_evidence(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    reference_time: datetime | None = None,
    deduplicate: bool = False,
    duplicate_count: int = 0,
) -> list[EvidencePacket]:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    applied_duplicate_count = duplicate_count
    if deduplicate:
        normalized, deduped_duplicate_count, _ = dedupe_findings(normalized)
        applied_duplicate_count = max(applied_duplicate_count, deduped_duplicate_count)
    evidence: list[EvidencePacket] = []
    for index, finding in enumerate(normalized, start=1):
        metadata = dict(finding.metadata)
        metadata.setdefault("market_id", market_id)
        metadata.setdefault("source", "research_finding")
        metadata.setdefault("index", index)
        if applied_duplicate_count > 0:
            metadata.setdefault("duplicate_count", applied_duplicate_count)
        if run_id is not None:
            metadata.setdefault("run_id", run_id)
        artifact_refs = _source_refs(
            metadata.get("artifact_refs", []),
            metadata.get("sidecar_source_path"),
            metadata.get("source_path"),
            metadata.get("sidecar_name"),
        )
        if artifact_refs:
            metadata.setdefault("artifact_refs", artifact_refs)
        evidence.append(
            EvidencePacket(
                market_id=market_id,
                venue=venue,
                source_kind=finding.source_kind,
                claim=finding.claim,
                stance=finding.stance,
                summary=finding.summary or _preview(finding.claim, 240),
                source_url=finding.source_url,
                raw_text=finding.raw_text,
                confidence=finding.confidence,
                freshness_score=finding.freshness_score,
                credibility_score=finding.credibility_score,
                provenance_refs=[str(item) for item in metadata.get("provenance_refs", [])],
                tags=list(finding.tags),
                metadata=metadata,
            )
        )
    return evidence


def build_signal_packets(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    evidence: Sequence[EvidencePacket] | None = None,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    sidecar_name: str | None = None,
    classification: str = "signal",
    classification_reasons: Sequence[str] | None = None,
    context_refs: Sequence[str] | None = None,
    sidecar_health: Mapping[str, Any] | None = None,
    source_path: str | None = None,
    reference_time: datetime | None = None,
) -> list[SidecarSignalPacket]:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    evidence_list = list(evidence or findings_to_evidence(normalized, market_id=market_id, venue=venue, run_id=run_id, reference_time=reference_time))
    reasons = _source_refs(classification_reasons or [])
    packets: list[SidecarSignalPacket] = []
    for index, finding in enumerate(normalized, start=1):
        evidence_packet = evidence_list[index - 1] if index - 1 < len(evidence_list) else None
        provenance_refs = _source_refs(
            finding.metadata.get("provenance_refs", []),
            evidence_packet.provenance_refs if evidence_packet is not None else [],
            context_refs or [],
            source_path,
            finding.metadata.get("sidecar_source_path"),
        )
        artifact_refs = _source_refs(
            finding.metadata.get("artifact_refs", []),
            evidence_packet.metadata.get("artifact_refs", []) if evidence_packet is not None else [],
            source_path,
            finding.metadata.get("sidecar_source_path"),
            context_refs or [],
        )
        signal_id = f"signal_{(finding.metadata.get('record_fingerprint') or _finding_fingerprint(finding))[:12]}"
        packets.append(
            SidecarSignalPacket(
                signal_id=signal_id,
                market_id=market_id,
                venue=venue,
                run_id=run_id,
                sidecar_name=sidecar_name,
                source_kind=finding.source_kind,
                classification=classification,
                signal_only=classification == "signal-only",
                claim=finding.claim,
                summary=finding.summary or finding.claim,
                source_url=finding.source_url,
                evidence_id=evidence_packet.evidence_id if evidence_packet is not None else None,
                artifact_refs=artifact_refs,
                provenance_refs=provenance_refs,
                evidence_refs=[evidence_packet.evidence_id] if evidence_packet is not None else [],
                observed_at=finding.observed_at or _utc_now(),
                published_at=finding.published_at,
                confidence=finding.confidence,
                freshness_score=finding.freshness_score,
                credibility_score=finding.credibility_score,
                tags=list(finding.tags),
                metadata={
                    **dict(finding.metadata),
                    "classification": classification,
                    "classification_reasons": list(reasons),
                    "sidecar_name": sidecar_name,
                    "sidecar_health": dict(sidecar_health or {}),
                    "source_path": source_path,
                    "signal_index": index,
                    "signal_only": classification == "signal-only",
                    "evidence_id": evidence_packet.evidence_id if evidence_packet is not None else None,
                    "artifact_refs": artifact_refs,
                },
            )
        )
    return packets


@dataclass
class ResearchCollector:
    venue: VenueName = VenueName.polymarket

    def normalize_findings(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str | None = None,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        source_kind: SourceKind | None = None,
    ) -> list[ResearchFinding]:
        return normalize_findings(
            findings,
            market_id=market_id,
            run_id=run_id,
            source_kind=source_kind,
            reference_time=reference_time,
        )

    def score_freshness(
        self,
        finding: ResearchFinding,
        *,
        reference_time: datetime | None = None,
    ) -> float:
        return score_freshness(finding, reference_time=reference_time)

    def score_credibility(self, finding: ResearchFinding) -> float:
        return score_credibility(finding)

    def estimate_base_rates(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        run_id: str | None = None,
        reference_time: datetime | None = None,
    ) -> ResearchBaseRateSummary:
        return estimate_base_rates(
            findings,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
        )

    def build_pipeline(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        snapshot: MarketSnapshot | None = None,
        forecast_probability_yes: float | None = None,
        retrieval_policy: str = "research_inputs",
        input_count: int | None = None,
        evidence_count: int | None = None,
        applied: bool = False,
    ) -> ResearchPipelineSurface:
        return build_research_pipeline_surface(
            findings,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            snapshot=snapshot,
            forecast_probability_yes=forecast_probability_yes,
            retrieval_policy=retrieval_policy,
            input_count=input_count,
            evidence_count=evidence_count,
            applied=applied,
        )

    def synthesize(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        snapshot: MarketSnapshot | None = None,
        forecast_probability_yes: float | None = None,
    ) -> ResearchSynthesis:
        return synthesize_research(
            findings,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            snapshot=snapshot,
            forecast_probability_yes=forecast_probability_yes,
        )

    def to_evidence(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        deduplicate: bool = False,
        duplicate_count: int = 0,
    ) -> list[EvidencePacket]:
        return findings_to_evidence(
            findings,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            deduplicate=deduplicate,
            duplicate_count=duplicate_count,
        )

    def from_notes(
        self,
        *,
        market_id: str,
        notes: list[str],
        run_id: str | None = None,
        source_kind: SourceKind = SourceKind.manual,
    ) -> list[EvidencePacket]:
        findings = [
            ResearchFinding(
                source_kind=source_kind,
                claim=note.strip(),
                stance=self._infer_stance(note),
                summary=_preview(note, 240),
                raw_text=note.strip(),
                confidence=0.55 if self._infer_stance(note) != "neutral" else 0.45,
                freshness_score=0.75,
                credibility_score=0.65,
                metadata={"run_id": run_id, "source": "research_notes", "index": index},
            )
            for index, note in enumerate(notes, start=1)
            if note and note.strip()
        ]
        return self.to_evidence(findings, market_id=market_id, run_id=run_id)

    def from_findings(
        self,
        *,
        market_id: str,
        findings: list[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        run_id: str | None = None,
    ) -> list[EvidencePacket]:
        return self.to_evidence(findings, market_id=market_id, run_id=run_id)

    def bridge_bundle(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        run_id: str | None = None,
        reference_time: datetime | None = None,
        snapshot: MarketSnapshot | None = None,
        forecast_probability_yes: float | None = None,
        social_context_refs: list[str] | None = None,
        packet_refs: dict[str, str] | None = None,
    ) -> ResearchBridgeBundle:
        normalized = normalize_findings(
            findings,
            market_id=market_id,
            run_id=run_id,
            reference_time=reference_time,
        )
        pipeline = build_research_pipeline_surface(
            normalized,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            snapshot=snapshot,
            forecast_probability_yes=forecast_probability_yes,
            retrieval_policy="bridge_bundle",
            input_count=len(normalized),
            evidence_count=len(normalized),
            applied=False,
        )
        synthesis = synthesize_research(
            normalized,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            snapshot=snapshot,
            forecast_probability_yes=forecast_probability_yes,
        )
        evidence = findings_to_evidence(normalized, market_id=market_id, venue=self.venue, run_id=run_id, reference_time=reference_time)
        signal_packets = build_signal_packets(
            normalized,
            evidence=evidence,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            reference_time=reference_time,
            classification="signal",
            sidecar_name="research_collector",
            context_refs=social_context_refs or list(packet_refs.values()),
        )
        provenance_bundle = build_research_provenance_bundle(
            normalized,
            evidence=evidence,
            signal_packets=signal_packets,
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            sidecar_name="research_collector",
            classification="signal",
            source_path=None,
            social_context_refs=social_context_refs or [],
            packet_refs=packet_refs or {},
            reference_time=reference_time,
        )
        return ResearchBridgeBundle(
            market_id=market_id,
            venue=self.venue,
            run_id=run_id,
            findings=normalized,
            synthesis=synthesis,
            pipeline=pipeline,
            abstention_policy=pipeline.abstention_policy,
            provenance_bundle=provenance_bundle,
            signal_packets=signal_packets,
            artifact_refs=_source_refs(
                social_context_refs or [],
                [packet.evidence_id for packet in signal_packets if packet.evidence_id],
                [ref for packet in signal_packets for ref in packet.artifact_refs],
            ),
            evidence_refs=[packet.evidence_id for packet in evidence],
            provenance_refs=_source_refs([ref for packet in signal_packets for ref in packet.provenance_refs]),
            social_context_refs=social_context_refs or [],
            packet_refs=packet_refs or {},
            freshness_score=synthesis.average_freshness,
            metadata={
                "finding_count": len(normalized),
                "evidence_count": len(evidence),
                "signal_packet_count": len(signal_packets),
                "artifact_refs": _source_refs(
                    social_context_refs or [],
                    [packet.evidence_id for packet in signal_packets if packet.evidence_id],
                    [ref for packet in signal_packets for ref in packet.artifact_refs],
                ),
                "freshness_score": synthesis.average_freshness,
                "pipeline_summary": pipeline.pipeline_summary,
                "public_metrics": dict(pipeline.public_metrics),
                "abstention_policy": pipeline.abstention_policy.model_dump(mode="json"),
                "abstention_metrics": build_research_abstention_metrics(pipeline),
                "provenance_bundle": provenance_bundle.model_dump(mode="json"),
                "provenance_bundle_content_hash": provenance_bundle.content_hash,
                "provenance_bundle_freshness_score": provenance_bundle.freshness_score,
                "content_hash": _stable_content_hash(
                    {
                        "market_id": market_id,
                        "run_id": run_id,
                        "finding_count": len(normalized),
                        "evidence_refs": [packet.evidence_id for packet in evidence],
                        "signal_packet_refs": [packet.signal_id for packet in signal_packets],
                        "social_context_refs": social_context_refs or [],
                        "packet_refs": packet_refs or {},
                        "pipeline_summary": pipeline.pipeline_summary,
                    }
                ),
            },
        )

    @staticmethod
    def _infer_stance(text: str) -> str:
        lowered = text.lower()
        bullish_tokens = ("bullish", "support", "yes", "likely", "increase", "higher", "positive")
        bearish_tokens = ("bearish", "oppose", "no", "unlikely", "decrease", "lower", "negative")
        if any(token in lowered for token in bullish_tokens):
            return "bullish"
        if any(token in lowered for token in bearish_tokens):
            return "bearish"
        return "neutral"


def _stable_serialize(value: Any) -> str:
    if value is None or isinstance(value, (bool, int, float, str)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, datetime):
        return json.dumps(value.isoformat(), sort_keys=True, separators=(",", ":"))
    if isinstance(value, Mapping):
        items = ",".join(
            f"{json.dumps(str(key), sort_keys=True, separators=(',', ':'))}:{_stable_serialize(item)}"
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        )
        return f"{{{items}}}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_stable_serialize(item) for item in value) + "]"
    return json.dumps(str(value), sort_keys=True, separators=(",", ":"))


def _stable_content_hash(value: Any) -> str:
    return hashlib.sha256(_stable_serialize(value).encode("utf-8")).hexdigest()


def _finding_fingerprint(finding: ResearchFinding) -> str:
    metadata = dict(finding.metadata)
    return _stable_content_hash(
        {
            "claim": finding.claim,
            "summary": finding.summary,
            "stance": finding.stance,
            "source_kind": finding.source_kind.value,
            "source_url": finding.source_url,
            "raw_text": finding.raw_text,
            "observed_at": finding.observed_at.isoformat() if finding.observed_at else None,
            "published_at": finding.published_at.isoformat() if finding.published_at else None,
            "tags": list(finding.tags),
            "provenance_refs": list(metadata.get("provenance_refs", [])),
            "record_fingerprint": metadata.get("record_fingerprint"),
            "record_id": metadata.get("record_id"),
            "tweet_id": metadata.get("tweet_id"),
        }
    )


def build_research_provenance_bundle(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    evidence: Sequence[EvidencePacket] | None = None,
    evidence_refs: Sequence[str] | None = None,
    signal_packets: Sequence[SidecarSignalPacket] | None = None,
    market_id: str,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    sidecar_name: str | None = None,
    classification: str = "signal",
    classification_reasons: Sequence[str] | None = None,
    source_path: str | None = None,
    sidecar_health: Mapping[str, Any] | None = None,
    reference_time: datetime | None = None,
    social_context_refs: Sequence[str] | None = None,
    packet_refs: Mapping[str, str] | None = None,
) -> ResearchProvenanceBundle:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    evidence_list = list(evidence or [])
    signal_packet_list = list(signal_packets or [])
    freshness_values = [finding.freshness_score for finding in normalized]
    source_kind_counts = Counter(finding.source_kind.value for finding in normalized)
    evidence_ref_list = _source_refs(
        [packet.evidence_id for packet in evidence_list if packet.evidence_id],
        evidence_refs or [],
    )
    provenance_refs = _source_refs(
        [ref for packet in evidence_list for ref in packet.provenance_refs],
        [ref for packet in signal_packet_list for ref in packet.provenance_refs],
        social_context_refs or [],
    )
    artifact_refs = _source_refs(
        source_path or "",
        [ref for packet in signal_packet_list for ref in packet.artifact_refs],
        [ref for packet in evidence_list for ref in packet.metadata.get("artifact_refs", [])],
        social_context_refs or [],
    )
    if not evidence_list and evidence_ref_list:
        evidence_count = len(evidence_ref_list)
    else:
        evidence_count = len(evidence_list)
    signal_packet_refs = _source_refs([packet.signal_id for packet in signal_packet_list if packet.signal_id])
    packet_ref_map = {str(key): str(val) for key, val in dict(packet_refs or {}).items()}
    observed_at = _utc_datetime(reference_time) or _utc_now()
    return ResearchProvenanceBundle(
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        sidecar_name=sidecar_name,
        classification=classification,
        classification_reasons=list(_source_refs(classification_reasons or [])),
        source_path=source_path,
        observed_at=observed_at,
        finding_count=len(normalized),
        evidence_count=len(evidence_list),
        signal_packet_count=len(signal_packet_list),
        source_kind_counts=dict(sorted(source_kind_counts.items())),
        artifact_refs=artifact_refs,
        evidence_refs=evidence_ref_list,
        provenance_refs=provenance_refs,
        social_context_refs=list(_source_refs(social_context_refs or [])),
        signal_packet_refs=signal_packet_refs,
        packet_refs=packet_ref_map,
        sidecar_health=dict(sidecar_health or {}),
        freshness_score=round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else 0.0,
        metadata={
            "finding_count": len(normalized),
            "evidence_count": evidence_count,
            "signal_packet_count": len(signal_packet_list),
            "source_path": source_path,
            "sidecar_health": dict(sidecar_health or {}),
            "classification": classification,
            "classification_reasons": list(_source_refs(classification_reasons or [])),
            "social_context_refs": list(_source_refs(social_context_refs or [])),
            "packet_refs": packet_ref_map,
        },
    )


def dedupe_findings(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str | None = None,
    run_id: str | None = None,
    source_kind: SourceKind | None = None,
    reference_time: datetime | None = None,
) -> tuple[list[ResearchFinding], int, list[str]]:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        source_kind=source_kind,
        reference_time=reference_time,
    )
    deduped: list[ResearchFinding] = []
    duplicate_count = 0
    seen: set[str] = set()
    duplicate_fingerprints: list[str] = []
    for finding in normalized:
        fingerprint = str(finding.metadata.get("record_fingerprint") or _finding_fingerprint(finding))
        if fingerprint in seen:
            duplicate_count += 1
            duplicate_fingerprints.append(fingerprint)
            continue
        seen.add(fingerprint)
        finding.metadata = dict(finding.metadata, record_fingerprint=fingerprint)
        deduped.append(finding)
    return deduped, duplicate_count, duplicate_fingerprints


def assess_findings_health(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    duplicate_count: int = 0,
) -> ResearchHealthSummary:
    normalized = normalize_findings(findings)
    if not normalized:
        return ResearchHealthSummary(
            status="unhealthy",
            completeness_score=0.0,
            duplicate_count=duplicate_count,
            issues=["no_signals"],
            alerts=["no_signals"],
            source_kinds=[],
        )

    issues: list[str] = []
    alerts: list[str] = []
    completeness_score = 1.0

    if duplicate_count > 0:
        issues.append("duplicate_signals_dropped")
        alerts.append("duplicate_records_dropped")
        completeness_score -= min(0.2, duplicate_count * 0.05)

    has_external_url = any(finding.source_url for finding in normalized)
    if not has_external_url:
        issues.append("no_external_source_urls")
        alerts.append("no_external_source_urls")
        completeness_score -= 0.15

    source_kinds = list(dict.fromkeys(finding.source_kind for finding in normalized))
    if len(source_kinds) == 1 and source_kinds[0] == SourceKind.manual:
        issues.append("manual_only_sidecar")
        alerts.append("manual_only_sidecar")
        completeness_score -= 0.1

    if all(finding.stance == "neutral" for finding in normalized):
        issues.append("all_stances_unknown")
        alerts.append("all_stances_unknown")
        completeness_score -= 0.15

    if duplicate_count > 0 and "duplicate_records_dropped" not in alerts:
        alerts.append("duplicate_records_dropped")

    status = "degraded" if issues else "healthy"
    return ResearchHealthSummary(
        status=status,
        completeness_score=round(_clamp01(completeness_score), 6),
        duplicate_count=duplicate_count,
        issues=issues,
        alerts=alerts,
        source_kinds=source_kinds,
    )


__all__ = [
    "ExternalReference",
    "ResearchAbstentionPolicy",
    "ResearchBaseRateSummary",
    "ResearchBridgeBundle",
    "ResearchCollector",
    "ResearchFinding",
    "ResearchHealthSummary",
    "ResearchPipelineSurface",
    "ResearchRetrievalSummary",
    "ResearchSynthesis",
    "SidecarSignalPacket",
    "SidecarClassificationSummary",
    "annotate_sidecar_findings",
    "build_signal_packets",
    "build_research_abstention_metrics",
    "build_research_pipeline_surface",
    "build_sidecar_research_bundle",
    "classify_sidecar_health",
    "assess_findings_health",
    "dedupe_findings",
    "estimate_base_rates",
    "findings_to_evidence",
    "normalize_findings",
    "normalize_finding",
    "score_credibility",
    "score_freshness",
    "synthesize_research",
]
