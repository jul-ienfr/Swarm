from __future__ import annotations

import math
from itertools import combinations
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .forecast_evaluation import (
    AbstentionQualityReport,
    AsOfBenchmarkSuite,
    CalibrationBucketSummary,
    CalibrationCurveReport,
    ForecastBaselineComparisonReport,
    BenchmarkFamilySummary,
    CategoryHorizonPerformanceReport,
    CategoryHorizonPerformanceSummary,
    ForecastVersionComparisonReport,
    ForecastUpliftComparisonReport,
    build_baseline_comparison_report,
    build_abstention_quality_report,
    build_calibration_curve_report,
    build_as_of_benchmark_suite,
    build_category_horizon_performance_report,
    build_forecast_uplift_comparison_report,
    build_model_version_comparison_report,
)
from .models import EvidencePacket, SourceKind, VenueName, _source_refs, _stable_content_hash, _utc_datetime, _utc_now
from .research import ResearchFinding, findings_to_evidence, normalize_findings, synthesize_research


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _strip_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_utc(value: Any) -> datetime:
    return _utc_datetime(value) or _utc_now()


def _record_cutoff(record: Any) -> datetime | None:
    if isinstance(record, Mapping):
        value = record.get("cutoff_at")
    else:
        value = getattr(record, "cutoff_at", None)
    return _utc_datetime(value)


_MIN_UTC_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


def _record_cutoff_or_min(record: Any) -> datetime:
    return _record_cutoff(record) or _MIN_UTC_DATETIME


def _log_loss(probability: float, outcome: bool) -> float:
    p = min(max(float(probability), 1e-6), 1.0 - 1e-6)
    return round(-math.log(p if outcome else 1.0 - p), 6)


def _bucket_probability(probability: float, buckets: int = 10) -> str:
    upper = buckets - 1
    index = min(upper, max(0, int(float(probability) * buckets)))
    return f"decile_{index:02d}"


def _fuzzy_key(*values: Any) -> str:
    payload = "|".join(_strip_or_none(value) or "" for value in values)
    return _stable_content_hash(payload)[:16]


def _input_provenance_bundle_hashes(findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str]) -> list[str]:
    hashes: list[str] = []
    for finding in findings:
        if isinstance(finding, EvidencePacket):
            metadata = dict(finding.metadata)
        elif isinstance(finding, ResearchFinding):
            metadata = dict(finding.metadata)
        elif isinstance(finding, Mapping):
            metadata = dict(finding.get("metadata", {}))
        else:
            metadata = {}
        hash_value = metadata.get("provenance_bundle_content_hash")
        if hash_value:
            hashes.append(str(hash_value).strip())
            continue
        provenance_bundle = metadata.get("provenance_bundle")
        if isinstance(provenance_bundle, Mapping):
            nested_hash = provenance_bundle.get("content_hash")
            if nested_hash:
                hashes.append(str(nested_hash).strip())
    return _source_refs(hashes)


def _canonical_benchmark_key(value: Any) -> str:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = {"value": str(value)}
    return _stable_content_hash(payload)


def _strip_bookkeeping(payload: Any, bookkeeping_keys: set[str]) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_bookkeeping(value, bookkeeping_keys)
            for key, value in payload.items()
            if key not in bookkeeping_keys
        }
    if isinstance(payload, list):
        return [_strip_bookkeeping(item, bookkeeping_keys) for item in payload]
    return payload


def _benchmark_evidence_packets(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    venue: VenueName,
    run_id: str | None,
    reference_time: datetime,
) -> tuple[list[EvidencePacket], int]:
    normalized = normalize_findings(
        findings,
        market_id=market_id,
        run_id=run_id,
        reference_time=reference_time,
    )
    selected = [
        finding
        for finding in normalized
        if (finding.published_at or finding.observed_at) is None
        or _ensure_utc(finding.published_at or finding.observed_at) <= reference_time
    ]
    packets: list[EvidencePacket] = []
    for index, finding in enumerate(selected, start=1):
        observed_at = _ensure_utc(finding.observed_at or finding.published_at or reference_time)
        published_at = _ensure_utc(finding.published_at or observed_at) if finding.published_at or observed_at else None
        fingerprint = _stable_content_hash(
            {
                "market_id": market_id,
                "claim": finding.claim,
                "stance": finding.stance,
                "source_kind": finding.source_kind.value,
                "source_url": finding.source_url,
                "observed_at": observed_at.isoformat(),
                "published_at": published_at.isoformat() if published_at else None,
                "summary": finding.summary,
                "tags": list(finding.tags),
                "metadata": finding.metadata,
            }
        )[:12]
        evidence_id = f"evid_{fingerprint}"
        metadata = dict(finding.metadata)
        metadata.setdefault("market_id", market_id)
        metadata.setdefault("source", "research_finding")
        metadata.setdefault("index", index)
        metadata.setdefault("benchmark_fingerprint", fingerprint)
        packets.append(
            EvidencePacket(
                evidence_id=evidence_id,
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
                observed_at=observed_at,
                published_at=published_at,
                provenance_refs=[str(item) for item in metadata.get("provenance_refs", [])],
                tags=list(finding.tags),
                metadata=metadata,
            )
        )
    return packets, max(0, len(normalized) - len(selected))


class ForecastEvaluationRecord(BaseModel):
    schema_version: str = "v1"
    evaluation_id: str = Field(default_factory=lambda: f"feval_{uuid4().hex[:12]}")
    question_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    cutoff_at: datetime
    forecast_probability: float
    market_baseline_probability: float = 0.5
    resolved_outcome: bool
    brier_score: float = 0.0
    log_loss: float = 0.0
    ece_bucket: str = ""
    abstain_flag: bool = False
    model_family: str = "baseline"
    market_family: str = "generic"
    horizon_bucket: str = "all"
    market_baseline_delta: float = 0.0
    market_baseline_delta_bps: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("forecast_probability", "market_baseline_probability")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return _clamp01(value)

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastEvaluationRecord":
        self.cutoff_at = _ensure_utc(self.cutoff_at)
        self.forecast_probability = _clamp01(self.forecast_probability)
        self.market_baseline_probability = _clamp01(self.market_baseline_probability)
        self.brier_score = round((self.forecast_probability - (1.0 if self.resolved_outcome else 0.0)) ** 2, 6)
        self.log_loss = _log_loss(self.forecast_probability, self.resolved_outcome)
        self.market_baseline_delta = round(self.forecast_probability - self.market_baseline_probability, 6)
        self.market_baseline_delta_bps = round(self.market_baseline_delta * 10000.0, 2)
        if not self.ece_bucket:
            self.ece_bucket = _bucket_probability(self.forecast_probability)
        return self

    @classmethod
    def from_prediction(
        cls,
        *,
        question_id: str,
        market_id: str,
        forecast_probability: float,
        resolved_outcome: bool,
        cutoff_at: datetime,
        venue: VenueName = VenueName.polymarket,
        market_baseline_probability: float = 0.5,
        abstain_flag: bool = False,
        model_family: str = "baseline",
        market_family: str = "generic",
        horizon_bucket: str = "all",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ForecastEvaluationRecord":
        return cls(
            question_id=question_id,
            market_id=market_id,
            venue=venue,
            cutoff_at=cutoff_at,
            forecast_probability=forecast_probability,
            market_baseline_probability=market_baseline_probability,
            resolved_outcome=resolved_outcome,
            abstain_flag=abstain_flag,
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            metadata=dict(metadata or {}),
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ForecastEvaluationRecord":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class CalibrationSnapshot(BaseModel):
    schema_version: str = "v1"
    snapshot_id: str = Field(default_factory=lambda: f"cal_{uuid4().hex[:12]}")
    model_family: str
    market_family: str
    horizon_bucket: str
    window_start: datetime
    window_end: datetime
    calibration_method: str = "ece_decile"
    ece: float = 0.0
    sharpness: float = 0.0
    coverage: float = 0.0
    abstention_coverage: float = 0.0
    mean_market_baseline_probability: float = 0.5
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    evaluation_count: int = 0
    abstain_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationSnapshot":
        self.window_start = _ensure_utc(self.window_start)
        self.window_end = _ensure_utc(self.window_end)
        if self.window_end < self.window_start:
            self.window_start, self.window_end = self.window_end, self.window_start
        self.ece = _clamp01(self.ece)
        self.sharpness = _clamp01(self.sharpness)
        self.coverage = _clamp01(self.coverage)
        self.abstention_coverage = _clamp01(self.abstention_coverage or self.coverage)
        self.mean_market_baseline_probability = _clamp01(self.mean_market_baseline_probability)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                _strip_bookkeeping(
                    self.model_dump(mode="json", exclude_none=True),
                    {"snapshot_id", "content_hash"},
                )
            )
        return self

    @property
    def record_count(self) -> int:
        return self.evaluation_count

    @classmethod
    def from_records(
        cls,
        records: Sequence[ForecastEvaluationRecord],
        *,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        window_start: datetime,
        window_end: datetime,
        calibration_method: str = "ece_decile",
    ) -> "CalibrationSnapshot":
        filtered = [
            record
            for record in records
            if record.model_family == model_family
            and record.market_family == market_family
            and record.horizon_bucket == horizon_bucket
            and window_start <= record.cutoff_at <= window_end
        ]
        if not filtered:
            return cls(
                model_family=model_family,
                market_family=market_family,
                horizon_bucket=horizon_bucket,
                window_start=window_start,
                window_end=window_end,
                calibration_method=calibration_method,
            )

        buckets: dict[str, list[ForecastEvaluationRecord]] = defaultdict(list)
        for record in filtered:
            buckets[record.ece_bucket].append(record)

        total = len(filtered)
        ece = 0.0
        sharpness = 0.0
        abstain_count = 0
        for record in filtered:
            if record.abstain_flag:
                abstain_count += 1
            sharpness += abs(record.forecast_probability - 0.5) * 2.0
        mean_market_baseline_probability = (
            sum(record.market_baseline_probability for record in filtered) / total
            if total
            else 0.5
        )
        mean_market_baseline_delta = (
            sum(record.forecast_probability - record.market_baseline_probability for record in filtered) / total
            if total
            else 0.0
        )
        for bucket_records in buckets.values():
            bucket_size = len(bucket_records)
            avg_prediction = sum(record.forecast_probability for record in bucket_records) / bucket_size
            avg_outcome = sum(1.0 if record.resolved_outcome else 0.0 for record in bucket_records) / bucket_size
            ece += (bucket_size / total) * abs(avg_prediction - avg_outcome)
        return cls(
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            window_start=window_start,
            window_end=window_end,
            calibration_method=calibration_method,
            ece=ece,
            sharpness=sharpness / total,
            coverage=(total - abstain_count) / total,
            abstention_coverage=(total - abstain_count) / total,
            mean_market_baseline_probability=round(mean_market_baseline_probability, 6),
            mean_market_baseline_delta=round(mean_market_baseline_delta, 6),
            mean_market_baseline_delta_bps=round(mean_market_baseline_delta * 10000.0, 2),
            evaluation_count=total,
            abstain_count=abstain_count,
            metadata={"bucket_count": len(buckets)},
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationSnapshot":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class AsOfEvidenceSet(BaseModel):
    schema_version: str = "v1"
    evidence_set_id: str = Field(default_factory=lambda: f"asof_{uuid4().hex[:12]}")
    market_id: str
    cutoff_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)
    retrieval_policy: str = "as_of_cutoff"
    freshness_summary: dict[str, Any] = Field(default_factory=dict)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_packets: list[EvidencePacket] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AsOfEvidenceSet":
        self.cutoff_at = _ensure_utc(self.cutoff_at)
        self.evidence_refs = _source_refs(self.evidence_refs)
        self.retrieval_policy = _strip_or_none(self.retrieval_policy) or "as_of_cutoff"
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                _strip_bookkeeping(
                    self.model_dump(mode="json", exclude_none=True),
                    {"evidence_set_id", "content_hash"},
                )
            )
        return self

    @classmethod
    def from_findings(
        cls,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        cutoff_at: datetime,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        retrieval_policy: str = "as_of_cutoff",
        reference_time: datetime | None = None,
    ) -> "AsOfEvidenceSet":
        cutoff = _ensure_utc(cutoff_at)
        findings_list = list(findings)
        provenance_bundle_hashes = _input_provenance_bundle_hashes(findings_list)
        normalized = normalize_findings(
            findings_list,
            market_id=market_id,
            run_id=run_id,
            reference_time=reference_time or cutoff,
        )
        selected = [
            finding
            for finding in normalized
            if (finding.published_at or finding.observed_at) is None
            or _ensure_utc(finding.published_at or finding.observed_at) <= cutoff
        ]
        evidence_packets = findings_to_evidence(
            selected,
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=cutoff,
            deduplicate=True,
        )
        evidence_refs = [packet.evidence_id for packet in evidence_packets]
        freshness_values = [finding.freshness_score for finding in selected]
        credibility_values = [finding.credibility_score for finding in selected]
        source_kinds = sorted({packet.source_kind.value for packet in evidence_packets})
        source_urls = _source_refs([packet.source_url for packet in evidence_packets if packet.source_url])
        provenance_refs = _source_refs([ref for packet in evidence_packets for ref in packet.provenance_refs])
        return cls(
            market_id=market_id,
            cutoff_at=cutoff,
            evidence_refs=evidence_refs,
            retrieval_policy=retrieval_policy,
            freshness_summary={
                "finding_count": len(selected),
                "evidence_count": len(evidence_packets),
                "average_freshness": round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else 0.0,
                "average_credibility": round(sum(credibility_values) / len(credibility_values), 6) if credibility_values else 0.0,
                "cutoff_at": cutoff.isoformat(),
            },
            provenance_summary={
                "source_kinds": source_kinds,
                "source_urls": source_urls,
                "provenance_refs": provenance_refs,
                "provenance_bundle_content_hashes": provenance_bundle_hashes,
                "provenance_bundle_count": len(provenance_bundle_hashes),
            },
            evidence_packets=evidence_packets,
            metadata={
                "selected_count": len(selected),
                "discarded_future_count": max(0, len(normalized) - len(selected)),
            },
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "AsOfEvidenceSet":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ResearchReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"rpt_{uuid4().hex[:12]}")
    market_id: str
    base_rates: dict[str, float] = Field(default_factory=dict)
    facts: list[str] = Field(default_factory=list)
    theses: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    key_factors: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    written_at: datetime = Field(default_factory=_utc_now)
    as_of_cutoff_at: datetime | None = None
    evidence_set_id: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ResearchReport":
        self.written_at = _ensure_utc(self.written_at)
        self.as_of_cutoff_at = _utc_datetime(self.as_of_cutoff_at) or self.as_of_cutoff_at
        self.facts = _source_refs(self.facts)
        self.theses = _source_refs(self.theses)
        self.objections = _source_refs(self.objections)
        self.key_factors = _source_refs(self.key_factors)
        self.supporting_evidence_refs = _source_refs(self.supporting_evidence_refs)
        self.counterarguments = _source_refs(self.counterarguments or self.objections)
        self.open_questions = _source_refs(self.open_questions)
        if not self.key_factors:
            self.key_factors = _source_refs(self.theses or self.facts)
        self.base_rates = {str(key): _clamp01(value) for key, value in self.base_rates.items()}
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                _strip_bookkeeping(
                    self.model_dump(mode="json", exclude_none=True),
                    {"report_id", "content_hash", "evidence_set_id"},
                )
            )
        return self

    @classmethod
    def from_findings(
        cls,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        as_of: datetime,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        researcher: "BaseRateResearcher | None" = None,
        evidence_set: AsOfEvidenceSet | None = None,
        market_family: str = "generic",
        horizon_bucket: str = "all",
    ) -> "ResearchReport":
        as_of_set = evidence_set or AsOfEvidenceSet.from_findings(
            findings,
            market_id=market_id,
            cutoff_at=as_of,
            venue=venue,
            run_id=run_id,
        )
        synthesis = synthesize_research(
            [packet for packet in as_of_set.evidence_packets],
            market_id=market_id,
            venue=venue,
            run_id=run_id,
            reference_time=as_of,
        )
        base_rate_researcher = researcher or BaseRateResearcher()
        estimated_base_rate = base_rate_researcher.estimate_base_rate(
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            default=synthesis.net_bias if synthesis.net_bias >= 0 else 1.0 + synthesis.net_bias,
        )
        base_rates = {
            "estimated_base_rate": round(_clamp01(estimated_base_rate), 6),
            "bullish_share": round(synthesis.bullish_count / synthesis.finding_count, 6) if synthesis.finding_count else 0.0,
            "bearish_share": round(synthesis.bearish_count / synthesis.finding_count, 6) if synthesis.finding_count else 0.0,
            "neutral_share": round(synthesis.neutral_count / synthesis.finding_count, 6) if synthesis.finding_count else 0.0,
        }
        ordered = sorted([packet for packet in as_of_set.evidence_packets], key=lambda packet: (-packet.evidence_weight, packet.evidence_id))
        facts = _source_refs(packet.claim for packet in ordered[:5])
        theses = _source_refs(synthesis.themes[:5] or synthesis.top_claims[:5])
        objections = _source_refs(
            [packet.claim for packet in as_of_set.evidence_packets if packet.stance == "bearish"]
            or [claim for claim in synthesis.top_claims if claim not in theses][:5]
        )
        key_factors = list(theses or facts)
        counterarguments = list(objections)
        open_questions = [
            f"Need more evidence before cutoff {as_of.isoformat()}",
            f"Check resolution policy coverage for {market_id}",
        ]
        summary = synthesis.summary or f"Research report for {market_id}"
        return cls(
            market_id=market_id,
            base_rates=base_rates,
            facts=facts,
            theses=theses,
            objections=objections,
            key_factors=key_factors,
            supporting_evidence_refs=as_of_set.evidence_refs,
            counterarguments=counterarguments,
            open_questions=open_questions,
            written_at=as_of,
            as_of_cutoff_at=as_of,
            evidence_set_id=as_of_set.evidence_set_id,
            summary=summary,
            metadata={
                "finding_count": synthesis.finding_count,
                "evidence_count": synthesis.evidence_count,
                "dominant_stance": synthesis.dominant_stance,
                "net_bias": synthesis.net_bias,
                "market_family": market_family,
                "horizon_bucket": horizon_bucket,
                "fact_count": len(facts),
                "thesis_count": len(theses),
                "objection_count": len(objections),
            },
        )

    @classmethod
    def from_asof_evidence_set(
        cls,
        evidence_set: AsOfEvidenceSet,
        evidence_packets: Sequence[EvidencePacket],
        *,
        base_rates: dict[str, float] | None = None,
        facts: Sequence[str] | None = None,
        theses: Sequence[str] | None = None,
        objections: Sequence[str] | None = None,
        key_factors: Sequence[str] | None = None,
        counterarguments: Sequence[str] | None = None,
        open_questions: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ResearchReport":
        selected = [
            packet
            for packet in evidence_packets
            if packet.market_id == evidence_set.market_id and packet.evidence_id in evidence_set.evidence_refs
        ]
        synthesis = synthesize_research(
            selected,
            market_id=evidence_set.market_id,
            venue=selected[0].venue if selected else VenueName.polymarket,
            reference_time=evidence_set.cutoff_at,
        )
        derived_base_rates = dict(base_rates or {})
        if not derived_base_rates:
            total = max(1, len(selected))
            stance_counts = Counter(packet.stance for packet in selected)
            derived_base_rates = {
                "bullish_share": round(stance_counts.get("bullish", 0) / total, 6),
                "bearish_share": round(stance_counts.get("bearish", 0) / total, 6),
                "neutral_share": round(stance_counts.get("neutral", 0) / total, 6),
            }
        ordered = sorted(selected, key=lambda packet: (-packet.evidence_weight, packet.evidence_id))
        derived_facts = list(facts or _source_refs(packet.claim for packet in ordered[:5]))
        derived_theses = list(theses or _source_refs(synthesis.themes[:5] or synthesis.top_claims[:5]))
        derived_objections = list(
            objections
            or _source_refs(
                [packet.claim for packet in selected if packet.stance == "bearish"]
                or [claim for claim in synthesis.top_claims if claim not in derived_theses][:5]
            )
        )
        derived_key_factors = list(key_factors or derived_theses or derived_facts)
        derived_counterarguments = list(counterarguments or derived_objections)
        derived_open_questions = list(
            open_questions
            or [
                f"Need more evidence before cutoff {evidence_set.cutoff_at.isoformat()}",
                f"Check resolution policy coverage for {evidence_set.market_id}",
            ]
        )
        summary = synthesis.summary or f"Research report for {evidence_set.market_id}"
        return cls(
            market_id=evidence_set.market_id,
            base_rates=derived_base_rates,
            facts=derived_facts,
            theses=derived_theses,
            objections=derived_objections,
            key_factors=derived_key_factors,
            supporting_evidence_refs=evidence_set.evidence_refs,
            counterarguments=derived_counterarguments,
            open_questions=derived_open_questions,
            written_at=evidence_set.cutoff_at,
            as_of_cutoff_at=evidence_set.cutoff_at,
            evidence_set_id=evidence_set.evidence_set_id,
            summary=summary,
            metadata={
                **dict(metadata or {}),
                "finding_count": synthesis.finding_count,
                "evidence_count": synthesis.evidence_count,
                "dominant_stance": synthesis.dominant_stance,
                "net_bias": synthesis.net_bias,
                "selected_evidence_count": len(selected),
                "fact_count": len(derived_facts),
                "thesis_count": len(derived_theses),
                "objection_count": len(derived_objections),
            },
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ResearchReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class AsOfBenchmarkReport(BaseModel):
    schema_version: str = "v1"
    benchmark_id: str = Field(default_factory=lambda: f"bmk_{uuid4().hex[:12]}")
    market_id: str
    cutoff_at: datetime
    evidence_set: AsOfEvidenceSet
    research_report: ResearchReport
    calibration_snapshot: CalibrationSnapshot | None = None
    model_version_comparisons: list[ForecastVersionComparisonReport] = Field(default_factory=list)
    baseline_comparisons: list[ForecastBaselineComparisonReport] = Field(default_factory=list)
    forecast_evaluation_refs: list[str] = Field(default_factory=list)
    excluded_future_finding_count: int = 0
    excluded_future_evaluation_count: int = 0
    contamination_free: bool = True
    stable_benchmark: bool = True
    benchmark_scope_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AsOfBenchmarkReport":
        self.cutoff_at = _ensure_utc(self.cutoff_at)
        self.model_version_comparisons = list(self.model_version_comparisons)
        self.baseline_comparisons = list(self.baseline_comparisons)
        self.forecast_evaluation_refs = _source_refs(self.forecast_evaluation_refs)
        self.excluded_future_finding_count = max(0, int(self.excluded_future_finding_count))
        self.excluded_future_evaluation_count = max(0, int(self.excluded_future_evaluation_count))
        self.contamination_free = bool(self.contamination_free)
        self.stable_benchmark = bool(self.stable_benchmark)
        if not self.benchmark_scope_hash:
            self.benchmark_scope_hash = _stable_content_hash(
                _strip_bookkeeping(
                    self.model_dump(mode="json", exclude_none=True),
                    {
                        "benchmark_id",
                        "content_hash",
                        "evidence_set_id",
                        "report_id",
                        "snapshot_id",
                        "research_report_id",
                        "calibration_snapshot_id",
                        "comparison_id",
                    },
                )
            )
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                _strip_bookkeeping(
                    self.model_dump(mode="json", exclude_none=True),
                    {
                        "benchmark_id",
                        "content_hash",
                        "evidence_set_id",
                        "report_id",
                        "snapshot_id",
                        "research_report_id",
                        "calibration_snapshot_id",
                        "comparison_id",
                    },
                )
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "AsOfBenchmarkReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class BaseRateResearcher(BaseModel):
    schema_version: str = "v1"
    records: list[ForecastEvaluationRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def ingest(self, record: ForecastEvaluationRecord) -> None:
        self.records.append(record)

    def estimate_base_rate(
        self,
        *,
        market_family: str,
        horizon_bucket: str,
        default: float = 0.5,
    ) -> float:
        matches = [
            record
            for record in self.records
            if record.market_family == market_family
            and record.horizon_bucket == horizon_bucket
            and not record.abstain_flag
        ]
        if not matches:
            return _clamp01(default)
        wins = sum(1 for record in matches if record.resolved_outcome)
        return round((wins + 1.0) / (len(matches) + 2.0), 6)

    def calibration_snapshot(
        self,
        *,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        window_start: datetime,
        window_end: datetime,
        calibration_method: str = "ece_decile",
    ) -> CalibrationSnapshot:
        return CalibrationSnapshot.from_records(
            self.records,
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            window_start=window_start,
            window_end=window_end,
            calibration_method=calibration_method,
        )

    def research_report(
        self,
        findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
        *,
        market_id: str,
        as_of: datetime,
        venue: VenueName = VenueName.polymarket,
        run_id: str | None = None,
        market_family: str = "generic",
        horizon_bucket: str = "all",
    ) -> ResearchReport:
        return ResearchReport.from_findings(
            findings,
            market_id=market_id,
            as_of=as_of,
            venue=venue,
            run_id=run_id,
            researcher=self,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
        )


def build_asof_evidence_set(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    cutoff_at: datetime,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    retrieval_policy: str = "as_of_cutoff",
    reference_time: datetime | None = None,
) -> AsOfEvidenceSet:
    return AsOfEvidenceSet.from_findings(
        findings,
        market_id=market_id,
        cutoff_at=cutoff_at,
        venue=venue,
        run_id=run_id,
        retrieval_policy=retrieval_policy,
        reference_time=reference_time,
    )


def build_research_report(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    *,
    market_id: str,
    as_of: datetime,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    researcher: BaseRateResearcher | None = None,
    market_family: str = "generic",
    horizon_bucket: str = "all",
) -> ResearchReport:
    return ResearchReport.from_findings(
        findings,
        market_id=market_id,
        as_of=as_of,
        venue=venue,
        run_id=run_id,
        researcher=researcher,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
    )


def build_asof_benchmark(
    findings: Iterable[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    forecast_evaluations: Sequence[ForecastEvaluationRecord] | None = None,
    *,
    market_id: str,
    as_of: datetime,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    researcher: BaseRateResearcher | None = None,
    market_family: str = "generic",
    horizon_bucket: str = "all",
    model_family: str = "baseline",
    calibration_method: str = "ece_decile",
    metadata: dict[str, Any] | None = None,
) -> AsOfBenchmarkReport:
    cutoff = _ensure_utc(as_of)
    findings_list = list(findings)
    ordered_findings = sorted(findings_list, key=_canonical_benchmark_key)
    evidence_packets, discarded_future_count = _benchmark_evidence_packets(
        ordered_findings,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=cutoff,
    )
    freshness_values = [packet.freshness_score for packet in evidence_packets]
    credibility_values = [packet.credibility_score for packet in evidence_packets]
    source_kind_counts = Counter(packet.source_kind.value for packet in evidence_packets)
    source_urls = _source_refs([packet.source_url for packet in evidence_packets if packet.source_url])
    provenance_refs = _source_refs([ref for packet in evidence_packets for ref in packet.provenance_refs])
    provenance_bundle_hashes = _input_provenance_bundle_hashes(findings_list)
    evidence_set = AsOfEvidenceSet(
        market_id=market_id,
        cutoff_at=cutoff,
        evidence_refs=[packet.evidence_id for packet in evidence_packets],
        retrieval_policy="as_of",
        freshness_summary={
            "finding_count": len(evidence_packets),
            "evidence_count": len(evidence_packets),
            "average_freshness": round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else 0.0,
            "average_credibility": round(sum(credibility_values) / len(credibility_values), 6) if credibility_values else 0.0,
            "cutoff_at": cutoff.isoformat(),
        },
        provenance_summary={
            "source_kinds": sorted(source_kind_counts.keys()),
            "source_kind_counts": dict(source_kind_counts),
            "source_urls": source_urls,
            "provenance_refs": provenance_refs,
            "provenance_bundle_content_hashes": provenance_bundle_hashes,
            "provenance_bundle_count": len(provenance_bundle_hashes),
        },
        evidence_packets=evidence_packets,
        metadata={
            "benchmark": True,
            "selected_count": len(evidence_packets),
            "discarded_future_count": discarded_future_count,
            "contamination_free": True,
        },
    )
    report = ResearchReport.from_asof_evidence_set(
        evidence_set,
        evidence_packets,
        metadata={
            "benchmark": True,
            "contamination_free": True,
            "run_id": run_id,
        },
    )

    evaluation_records = sorted(
        list(forecast_evaluations or []),
        key=lambda record: (_record_cutoff_or_min(record), record.evaluation_id, record.market_id),
    )
    valid_evaluation_records = [
        record
        for record in evaluation_records
        if _record_cutoff(record) is not None
    ]
    in_scope_records = [
        record
        for record in valid_evaluation_records
        if record.market_id == market_id and _record_cutoff(record) <= cutoff
    ]
    excluded_future_evaluations = [
        record
        for record in valid_evaluation_records
        if record.market_id == market_id and _record_cutoff(record) > cutoff
    ]
    excluded_invalid_evaluations = [
        record
        for record in evaluation_records
        if record.market_id == market_id and _record_cutoff(record) is None
    ]
    calibration_snapshot = None
    if in_scope_records:
        window_start = min(record.cutoff_at for record in in_scope_records)
        window_end = max(record.cutoff_at for record in in_scope_records)
        calibration_snapshot = build_calibration_snapshot(
            in_scope_records,
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            window_start=window_start,
            window_end=window_end,
            calibration_method=calibration_method,
        )
        calibration_snapshot = CalibrationSnapshot.model_validate(
            {
                **calibration_snapshot.model_dump(mode="json", exclude_none=True),
                "metadata": {
                    **dict(calibration_snapshot.metadata),
                    "benchmark": True,
                    "contamination_free": True,
                    "as_of_cutoff_at": cutoff.isoformat(),
                    "included_record_count": len(in_scope_records),
                    "excluded_future_record_count": len(excluded_future_evaluations),
                    "excluded_invalid_record_count": len(excluded_invalid_evaluations),
                },
            }
        )

    unique_model_families = sorted({record.model_family for record in in_scope_records})
    model_version_comparisons: list[ForecastVersionComparisonReport] = []
    for left_model_family, right_model_family in combinations(unique_model_families, 2):
        model_version_comparisons.append(
            build_model_version_comparison_report(
                in_scope_records,
                left_model_family=left_model_family,
                right_model_family=right_model_family,
                market_family=market_family,
                horizon_bucket=horizon_bucket,
                as_of=cutoff,
                metadata={
                    "benchmark": True,
                    "contamination_free": True,
                    "as_of_cutoff_at": cutoff.isoformat(),
                },
            )
        )

    baseline_comparisons: list[ForecastBaselineComparisonReport] = []
    estimated_base_rate = report.base_rates.get("estimated_base_rate", 0.5)
    mean_market_baseline_probability = (
        round(sum(record.market_baseline_probability for record in in_scope_records) / len(in_scope_records), 6)
        if in_scope_records
        else 0.5
    )
    baseline_references = [
        ("simple_0.5", 0.5),
        ("estimated_base_rate", estimated_base_rate),
        ("mean_market_baseline_probability", mean_market_baseline_probability),
    ]
    for model_family_name in unique_model_families:
        for baseline_label, baseline_probability in baseline_references:
            baseline_comparisons.append(
                build_baseline_comparison_report(
                    in_scope_records,
                    model_family=model_family_name,
                    market_family=market_family,
                    horizon_bucket=horizon_bucket,
                    baseline_probability=baseline_probability,
                    baseline_label=baseline_label,
                    as_of=cutoff,
                    metadata={
                        "benchmark": True,
                        "contamination_free": True,
                        "as_of_cutoff_at": cutoff.isoformat(),
                        "reference_source": baseline_label,
                    },
                )
            )

    benchmark_scope_hash = _stable_content_hash(
        {
            "market_id": market_id,
            "as_of": cutoff.isoformat(),
            "evidence_refs": evidence_set.evidence_refs,
            "evaluation_refs": [record.evaluation_id for record in in_scope_records],
            "model_version_comparisons": [item.content_hash for item in model_version_comparisons],
            "baseline_comparisons": [item.content_hash for item in baseline_comparisons],
            "calibration_snapshot": calibration_snapshot.content_hash if calibration_snapshot is not None else None,
            "research_report": report.content_hash,
        }
    )

    return AsOfBenchmarkReport(
        market_id=market_id,
        cutoff_at=cutoff,
        evidence_set=evidence_set,
        research_report=report,
        calibration_snapshot=calibration_snapshot,
        model_version_comparisons=model_version_comparisons,
        baseline_comparisons=baseline_comparisons,
        forecast_evaluation_refs=[record.evaluation_id for record in sorted(in_scope_records, key=lambda record: (record.cutoff_at, record.evaluation_id))],
        excluded_future_finding_count=max(0, int(evidence_set.metadata.get("discarded_future_count", 0))),
        excluded_future_evaluation_count=len(excluded_future_evaluations),
        contamination_free=True,
        stable_benchmark=True,
        benchmark_scope_hash=benchmark_scope_hash,
        metadata={
            **dict(metadata or {}),
            "run_id": run_id,
            "market_family": market_family,
            "horizon_bucket": horizon_bucket,
            "model_family": model_family,
            "calibration_method": calibration_method,
            "evidence_set_id": evidence_set.evidence_set_id,
            "research_report_id": report.report_id,
            "calibration_snapshot_id": calibration_snapshot.snapshot_id if calibration_snapshot is not None else None,
            "selected_finding_count": evidence_set.metadata.get("selected_count", len(evidence_set.evidence_refs)),
            "excluded_future_finding_count": evidence_set.metadata.get("discarded_future_count", 0),
            "in_scope_evaluation_count": len(in_scope_records),
            "excluded_future_evaluation_count": len(excluded_future_evaluations),
            "excluded_invalid_evaluation_count": len(excluded_invalid_evaluations),
            "contamination_free": True,
            "stable_benchmark": True,
            "model_version_comparison_count": len(model_version_comparisons),
            "baseline_comparison_count": len(baseline_comparisons),
            "benchmark_scope_hash": benchmark_scope_hash,
        },
    )


def build_forecast_evaluation(
    *,
    question_id: str,
    market_id: str,
    forecast_probability: float,
    resolved_outcome: bool,
    cutoff_at: datetime,
    venue: VenueName = VenueName.polymarket,
    market_baseline_probability: float = 0.5,
    abstain_flag: bool = False,
    model_family: str = "baseline",
    market_family: str = "generic",
    horizon_bucket: str = "all",
    metadata: Mapping[str, Any] | None = None,
) -> ForecastEvaluationRecord:
    return ForecastEvaluationRecord.from_prediction(
        question_id=question_id,
        market_id=market_id,
        forecast_probability=forecast_probability,
        resolved_outcome=resolved_outcome,
        cutoff_at=cutoff_at,
        venue=venue,
        market_baseline_probability=market_baseline_probability,
        abstain_flag=abstain_flag,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        metadata=metadata,
    )


def compare_forecast_only_vs_enriched(
    records: Sequence[ForecastEvaluationRecord],
    *,
    forecast_only_model_family: str,
    enriched_model_family: str,
    market_family: str,
    horizon_bucket: str,
    as_of: datetime | None = None,
    forecast_only_family_role: str = "forecast-only",
    enriched_family_role: str = "enriched",
    metadata: dict[str, Any] | None = None,
) -> ForecastUpliftComparisonReport:
    return build_forecast_uplift_comparison_report(
        records,
        forecast_only_model_family=forecast_only_model_family,
        enriched_model_family=enriched_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
        forecast_only_family_role=forecast_only_family_role,
        enriched_family_role=enriched_family_role,
        metadata=metadata,
    )


def summarize_gate_1_benchmark_suite(suite: AsOfBenchmarkSuite) -> dict[str, Any]:
    comparator_manifest = list(suite.metadata.get("gate_1_comparator_manifest", []))
    return {
        "market_id": suite.market_id,
        "cutoff_at": suite.cutoff_at.isoformat(),
        "benchmark_scope_hash": suite.benchmark_scope_hash,
        "contamination_free": suite.contamination_free,
        "stable_benchmark": suite.stable_benchmark,
        "market_only_family": suite.metadata.get("market_only_family"),
        "required_categories": list(suite.metadata.get("gate_1_required_categories", [])),
        "present_categories": list(suite.metadata.get("gate_1_present_categories", [])),
        "comparator_count": len(comparator_manifest),
        "comparator_manifest": comparator_manifest,
        "promotion_ready": bool(suite.metadata.get("gate_1_promotion_ready", False)),
        "promotion_blockers": list(suite.metadata.get("gate_1_promotion_blockers", [])),
        "promotion_evidence": suite.metadata.get("gate_1_promotion_evidence"),
        "market_only_baseline_probability": suite.metadata.get("market_only_baseline_probability"),
    }


def build_calibration_snapshot(
    records: Sequence[ForecastEvaluationRecord],
    *,
    model_family: str,
    market_family: str,
    horizon_bucket: str,
    window_start: datetime,
    window_end: datetime,
    calibration_method: str = "ece_decile",
) -> CalibrationSnapshot:
    return CalibrationSnapshot.from_records(
        records,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        window_start=window_start,
        window_end=window_end,
        calibration_method=calibration_method,
    )


__all__ = [
    "AbstentionQualityReport",
    "AsOfEvidenceSet",
    "AsOfBenchmarkReport",
    "AsOfBenchmarkSuite",
    "BaseRateResearcher",
    "CalibrationBucketSummary",
    "CalibrationCurveReport",
    "BenchmarkFamilySummary",
    "CategoryHorizonPerformanceReport",
    "CategoryHorizonPerformanceSummary",
    "CalibrationSnapshot",
    "ForecastEvaluationRecord",
    "ForecastUpliftComparisonReport",
    "ResearchReport",
    "build_asof_evidence_set",
    "build_asof_benchmark",
    "build_abstention_quality_report",
    "build_calibration_curve_report",
    "build_as_of_benchmark_suite",
    "build_category_horizon_performance_report",
    "build_calibration_snapshot",
    "compare_forecast_only_vs_enriched",
    "build_forecast_evaluation",
    "build_research_report",
    "summarize_gate_1_benchmark_suite",
]
