from __future__ import annotations

import math
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import EvidencePacket, ForecastPacket, VenueName, _source_refs, _stable_content_hash, _utc_now
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .research import ResearchFinding, findings_to_evidence, normalize_findings
from .storage import load_json, save_json

_MIN_UTC_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


def _utc_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_mean(values: Sequence[float], default: float = 0.0) -> float:
    if not values:
        return default
    return float(mean(values))


def _log_loss(probability_yes: float, outcome_yes: bool) -> float:
    probability_yes = max(1e-9, min(1.0 - 1e-9, float(probability_yes)))
    return -math.log(probability_yes if outcome_yes else 1.0 - probability_yes)


def _ece_bucket(probability: float, bins: int = 10) -> str:
    bins = max(1, int(bins))
    clamped = _clamp_probability(probability)
    index = min(bins - 1, int(clamped * bins))
    lower = index / bins
    upper = (index + 1) / bins
    return f"{lower:.1f}-{upper:.1f}"


def _unique_refs(*values: Any) -> list[str]:
    return _source_refs(*values)


def _record_value(record: Any, field: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


def _record_cutoff(record: Any) -> datetime | None:
    return _utc_datetime(_record_value(record, "cutoff_at"))


def _record_cutoff_or_min(record: Any) -> datetime:
    return _record_cutoff(record) or _MIN_UTC_DATETIME


def _record_comparison_key(record: Any) -> tuple[Any, ...]:
    return (
        _record_value(record, "question_id", ""),
        _record_value(record, "market_id", ""),
        _record_value(record, "venue", VenueName.polymarket),
        _record_cutoff_or_min(record),
        _record_value(record, "market_family", "unknown"),
        _record_value(record, "horizon_bucket", "unknown"),
    )


def _comparison_scope_hash(payload: Any) -> str:
    encoded = repr(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_benchmark_key(value: Any) -> str:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = {"value": str(value)}
    return _stable_content_hash(payload)


def _family_role_from_label(label: str) -> str:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", str(label).strip().lower()).split())
    if not normalized:
        return "custom"
    if "decision packet" in normalized or "decisionpacket" in normalized or "decision assisted" in normalized:
        return "DecisionPacket-assisted"
    if "ensemble" in normalized:
        return "ensemble"
    if "market only" in normalized or ("market" in normalized and "only" in normalized):
        return "market-only"
    if "forecast pur" in normalized or "forecast only" in normalized or "forecast" in normalized:
        if "decision packet" not in normalized and "decisionpacket" not in normalized and "ensemble" not in normalized:
            return "forecast-only"
    if "single" in normalized and "llm" in normalized:
        return "single-LLM"
    if "reference" in normalized:
        return "reference-only"
    return "custom"


def _gate_1_category_from_family_role(role: str) -> str:
    normalized = str(role).strip()
    if normalized in {"market-only", "forecast-only", "DecisionPacket-assisted", "ensemble"}:
        return normalized
    if normalized == "single-LLM":
        return "forecast-only"
    if normalized == "reference-only":
        return "reference-only"
    return "custom"


def _gate_1_category_rank(category: str) -> int:
    order = {
        "market-only": 0,
        "forecast-only": 1,
        "DecisionPacket-assisted": 2,
        "ensemble": 3,
        "reference-only": 4,
        "custom": 5,
    }
    return order.get(category, 5)


def _gate_1_comparator_manifest(
    family_summaries: Sequence[BenchmarkFamilySummary],
    *,
    market_only_family: str | None,
) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for summary in sorted(
        family_summaries,
        key=lambda item: (
            _gate_1_category_rank(_gate_1_category_from_family_role(item.family_role)),
            item.family_label,
            item.model_family,
            item.summary_id,
        ),
    ):
        gate_1_category = _gate_1_category_from_family_role(summary.family_role)
        manifest.append(
            {
                "summary_id": summary.summary_id,
                "family_label": summary.family_label,
                "model_family": summary.model_family,
                "family_role": summary.family_role,
                "gate_1_category": gate_1_category,
                "is_market_only_reference": bool(market_only_family and summary.model_family == market_only_family),
                "record_count": summary.record_count,
                "as_of_cutoff_at": summary.as_of_cutoff_at.isoformat(),
                "contamination_free": summary.contamination_free,
                "mean_brier_score": summary.mean_brier_score,
                "mean_log_loss": summary.mean_log_loss,
                "ece": summary.ece,
                "sharpness": summary.sharpness,
                "abstention_coverage": summary.abstention_coverage,
                "market_baseline_probability": summary.mean_market_baseline_probability,
                "market_baseline_delta": summary.mean_market_baseline_delta,
                "market_baseline_delta_bps": summary.mean_market_baseline_delta_bps,
                "canonical_score_components": dict(summary.canonical_score_components),
                "promotion_ready": bool(
                    summary.contamination_free
                    and summary.record_count > 0
                    and gate_1_category in {"market-only", "forecast-only", "DecisionPacket-assisted", "ensemble"}
                ),
            }
        )
    return manifest


def _weighted_mean(values: Sequence[tuple[float, int]], default: float = 0.0) -> float:
    total_weight = sum(max(0, weight) for _, weight in values)
    if total_weight <= 0:
        return default
    total = sum(float(value) * max(0, weight) for value, weight in values)
    return float(total / total_weight)


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
        or (_utc_datetime(finding.published_at or finding.observed_at) or _utc_now()) <= reference_time
    ]
    packets = findings_to_evidence(
        selected,
        market_id=market_id,
        venue=venue,
        run_id=run_id,
        reference_time=reference_time,
        deduplicate=True,
    )
    return packets, max(0, len(normalized) - len(selected))


def _record_metadata(record: Any) -> dict[str, Any]:
    metadata = _record_value(record, "metadata", {})
    if isinstance(metadata, dict):
        return metadata
    return {}


def _record_category(record: Any) -> str:
    metadata = _record_metadata(record)
    for key in ("category", "market_category", "theme", "sector", "segment"):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    market_family = _record_value(record, "market_family", "unknown")
    text = str(market_family).strip()
    return text or "unknown"


def _record_horizon_bucket(record: Any) -> str:
    horizon_bucket = _record_value(record, "horizon_bucket", "unknown")
    text = str(horizon_bucket).strip()
    return text or "unknown"


def _filter_evaluation_records(
    records: Sequence[Any],
    *,
    model_family: str | None = None,
    market_family: str | None = None,
    horizon_bucket: str | None = None,
    as_of: datetime | None = None,
) -> list[Any]:
    cutoff = _utc_datetime(as_of) if as_of is not None else None
    filtered: list[Any] = []
    for record in records:
        if model_family is not None and _record_value(record, "model_family", "unknown") != model_family:
            continue
        if market_family is not None and _record_value(record, "market_family", "unknown") != market_family:
            continue
        if horizon_bucket is not None and _record_value(record, "horizon_bucket", "unknown") != horizon_bucket:
            continue
        record_cutoff = _record_cutoff(record)
        if cutoff is not None and (record_cutoff is None or record_cutoff > cutoff):
            continue
        filtered.append(record)
    return sorted(filtered, key=_paired_record_sort_key)


def _paired_record_sort_key(record: Any) -> tuple[Any, ...]:
    return (
        _record_cutoff_or_min(record),
        _record_value(record, "question_id", ""),
        _record_value(record, "market_id", ""),
        _record_value(record, "evaluation_id", ""),
    )


def _winner_from_scores(left_score: float, right_score: float, left_tiebreaker: float, right_tiebreaker: float) -> str:
    if left_score < right_score:
        return "left"
    if right_score < left_score:
        return "right"
    if left_tiebreaker < right_tiebreaker:
        return "left"
    if right_tiebreaker < left_tiebreaker:
        return "right"
    return "tie"


class ForecastVersionComparisonPair(BaseModel):
    schema_version: str = "v1"
    comparison_key: str
    question_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    cutoff_at: datetime
    market_family: str
    horizon_bucket: str
    left_evaluation_id: str
    right_evaluation_id: str
    left_model_family: str
    right_model_family: str
    left_forecast_probability: float
    right_forecast_probability: float
    resolved_outcome: bool
    left_brier_score: float
    right_brier_score: float
    left_log_loss: float
    right_log_loss: float
    probability_gap: float = 0.0
    brier_gap: float = 0.0
    log_loss_gap: float = 0.0
    winner: str = "tie"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastVersionComparisonPair":
        self.cutoff_at = _utc_datetime(self.cutoff_at) or _utc_now()
        self.left_forecast_probability = _clamp_probability(self.left_forecast_probability)
        self.right_forecast_probability = _clamp_probability(self.right_forecast_probability)
        self.left_brier_score = round(float(self.left_brier_score), 6)
        self.right_brier_score = round(float(self.right_brier_score), 6)
        self.left_log_loss = round(float(self.left_log_loss), 6)
        self.right_log_loss = round(float(self.right_log_loss), 6)
        self.probability_gap = round(float(self.probability_gap), 6)
        self.brier_gap = round(float(self.brier_gap), 6)
        self.log_loss_gap = round(float(self.log_loss_gap), 6)
        self.winner = str(self.winner).strip() or "tie"
        return self


class ForecastVersionComparisonReport(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"cmp_{uuid4().hex[:12]}")
    left_model_family: str
    right_model_family: str
    market_family: str
    horizon_bucket: str
    comparison_scope: str = "same_dataset"
    aligned_pair_count: int = 0
    left_evaluation_count: int = 0
    right_evaluation_count: int = 0
    left_mean_brier_score: float = 0.0
    right_mean_brier_score: float = 0.0
    left_mean_log_loss: float = 0.0
    right_mean_log_loss: float = 0.0
    mean_probability_gap: float = 0.0
    mean_brier_gap: float = 0.0
    mean_log_loss_gap: float = 0.0
    left_win_count: int = 0
    right_win_count: int = 0
    tie_count: int = 0
    unpaired_left_count: int = 0
    unpaired_right_count: int = 0
    comparison_pairs: list[ForecastVersionComparisonPair] = Field(default_factory=list)
    comparison_scope_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastVersionComparisonReport":
        self.aligned_pair_count = max(0, int(self.aligned_pair_count))
        self.left_evaluation_count = max(0, int(self.left_evaluation_count))
        self.right_evaluation_count = max(0, int(self.right_evaluation_count))
        self.left_mean_brier_score = round(float(self.left_mean_brier_score), 6)
        self.right_mean_brier_score = round(float(self.right_mean_brier_score), 6)
        self.left_mean_log_loss = round(float(self.left_mean_log_loss), 6)
        self.right_mean_log_loss = round(float(self.right_mean_log_loss), 6)
        self.mean_probability_gap = round(float(self.mean_probability_gap), 6)
        self.mean_brier_gap = round(float(self.mean_brier_gap), 6)
        self.mean_log_loss_gap = round(float(self.mean_log_loss_gap), 6)
        self.left_win_count = max(0, int(self.left_win_count))
        self.right_win_count = max(0, int(self.right_win_count))
        self.tie_count = max(0, int(self.tie_count))
        self.unpaired_left_count = max(0, int(self.unpaired_left_count))
        self.unpaired_right_count = max(0, int(self.unpaired_right_count))
        self.comparison_pairs = sorted(self.comparison_pairs, key=lambda item: (item.comparison_key, item.left_evaluation_id, item.right_evaluation_id))
        if not self.comparison_scope_hash:
            self.comparison_scope_hash = _comparison_scope_hash(
                {
                    "left_model_family": self.left_model_family,
                    "right_model_family": self.right_model_family,
                    "market_family": self.market_family,
                    "horizon_bucket": self.horizon_bucket,
                    "pairs": [pair.model_dump(mode="json", exclude_none=True) for pair in self.comparison_pairs],
                }
            )
        if not self.content_hash:
            self.content_hash = _comparison_scope_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "comparison_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ForecastVersionComparisonReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ForecastBaselineComparisonPair(BaseModel):
    schema_version: str = "v1"
    comparison_key: str
    question_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    cutoff_at: datetime
    market_family: str
    horizon_bucket: str
    evaluation_id: str
    model_family: str
    forecast_probability: float
    baseline_probability: float
    resolved_outcome: bool
    forecast_brier_score: float
    baseline_brier_score: float
    forecast_log_loss: float
    baseline_log_loss: float
    brier_gap: float = 0.0
    log_loss_gap: float = 0.0
    probability_gap: float = 0.0
    winner: str = "tie"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastBaselineComparisonPair":
        self.cutoff_at = _utc_datetime(self.cutoff_at) or _utc_now()
        self.forecast_probability = _clamp_probability(self.forecast_probability)
        self.baseline_probability = _clamp_probability(self.baseline_probability)
        self.forecast_brier_score = round(float(self.forecast_brier_score), 6)
        self.baseline_brier_score = round(float(self.baseline_brier_score), 6)
        self.forecast_log_loss = round(float(self.forecast_log_loss), 6)
        self.baseline_log_loss = round(float(self.baseline_log_loss), 6)
        self.brier_gap = round(float(self.brier_gap), 6)
        self.log_loss_gap = round(float(self.log_loss_gap), 6)
        self.probability_gap = round(float(self.probability_gap), 6)
        self.winner = str(self.winner).strip() or "tie"
        return self


class ForecastBaselineComparisonReport(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"cmp_{uuid4().hex[:12]}")
    model_family: str
    market_family: str
    horizon_bucket: str
    baseline_label: str
    baseline_probability: float
    comparison_scope: str = "same_dataset"
    record_count: int = 0
    model_mean_brier_score: float = 0.0
    baseline_mean_brier_score: float = 0.0
    model_mean_log_loss: float = 0.0
    baseline_mean_log_loss: float = 0.0
    mean_probability_gap: float = 0.0
    mean_brier_gap: float = 0.0
    mean_log_loss_gap: float = 0.0
    model_win_count: int = 0
    baseline_win_count: int = 0
    tie_count: int = 0
    comparison_pairs: list[ForecastBaselineComparisonPair] = Field(default_factory=list)
    comparison_scope_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastBaselineComparisonReport":
        self.baseline_probability = _clamp_probability(self.baseline_probability)
        self.record_count = max(0, int(self.record_count))
        self.model_mean_brier_score = round(float(self.model_mean_brier_score), 6)
        self.baseline_mean_brier_score = round(float(self.baseline_mean_brier_score), 6)
        self.model_mean_log_loss = round(float(self.model_mean_log_loss), 6)
        self.baseline_mean_log_loss = round(float(self.baseline_mean_log_loss), 6)
        self.mean_probability_gap = round(float(self.mean_probability_gap), 6)
        self.mean_brier_gap = round(float(self.mean_brier_gap), 6)
        self.mean_log_loss_gap = round(float(self.mean_log_loss_gap), 6)
        self.model_win_count = max(0, int(self.model_win_count))
        self.baseline_win_count = max(0, int(self.baseline_win_count))
        self.tie_count = max(0, int(self.tie_count))
        self.comparison_pairs = sorted(self.comparison_pairs, key=lambda item: (item.comparison_key, item.evaluation_id))
        if not self.comparison_scope_hash:
            self.comparison_scope_hash = _comparison_scope_hash(
                {
                    "model_family": self.model_family,
                    "market_family": self.market_family,
                    "horizon_bucket": self.horizon_bucket,
                    "baseline_label": self.baseline_label,
                    "pairs": [pair.model_dump(mode="json", exclude_none=True) for pair in self.comparison_pairs],
                }
            )
        if not self.content_hash:
            self.content_hash = _comparison_scope_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "comparison_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ForecastBaselineComparisonReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ForecastUpliftComparisonReport(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"uplift_{uuid4().hex[:12]}")
    forecast_only_model_family: str
    enriched_model_family: str
    market_family: str
    horizon_bucket: str
    as_of_cutoff_at: datetime
    forecast_only_family_role: str = "forecast-only"
    enriched_family_role: str = "enriched"
    comparison_scope: str = "same_dataset"
    record_count: int = 0
    forecast_only_record_count: int = 0
    enriched_record_count: int = 0
    aligned_pair_count: int = 0
    forecast_only_mean_forecast_probability: float = 0.0
    enriched_mean_forecast_probability: float = 0.0
    forecast_only_mean_brier_score: float = 0.0
    enriched_mean_brier_score: float = 0.0
    forecast_only_mean_log_loss: float = 0.0
    enriched_mean_log_loss: float = 0.0
    forecast_only_mean_market_baseline_probability: float = 0.0
    enriched_mean_market_baseline_probability: float = 0.0
    forecast_only_mean_market_baseline_delta: float = 0.0
    enriched_mean_market_baseline_delta: float = 0.0
    forecast_only_mean_market_baseline_delta_bps: float = 0.0
    enriched_mean_market_baseline_delta_bps: float = 0.0
    brier_improvement: float = 0.0
    log_loss_improvement: float = 0.0
    probability_gap: float = 0.0
    market_baseline_probability_gap: float = 0.0
    market_baseline_delta_gap: float = 0.0
    market_baseline_delta_bps_gap: float = 0.0
    left_win_count: int = 0
    right_win_count: int = 0
    tie_count: int = 0
    comparison_scope_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastUpliftComparisonReport":
        self.as_of_cutoff_at = _utc_datetime(self.as_of_cutoff_at) or _utc_now()
        self.record_count = max(0, int(self.record_count))
        self.forecast_only_record_count = max(0, int(self.forecast_only_record_count))
        self.enriched_record_count = max(0, int(self.enriched_record_count))
        self.aligned_pair_count = max(0, int(self.aligned_pair_count))
        self.forecast_only_mean_forecast_probability = round(float(self.forecast_only_mean_forecast_probability), 6)
        self.enriched_mean_forecast_probability = round(float(self.enriched_mean_forecast_probability), 6)
        self.forecast_only_mean_brier_score = round(float(self.forecast_only_mean_brier_score), 6)
        self.enriched_mean_brier_score = round(float(self.enriched_mean_brier_score), 6)
        self.forecast_only_mean_log_loss = round(float(self.forecast_only_mean_log_loss), 6)
        self.enriched_mean_log_loss = round(float(self.enriched_mean_log_loss), 6)
        self.forecast_only_mean_market_baseline_probability = round(float(self.forecast_only_mean_market_baseline_probability), 6)
        self.enriched_mean_market_baseline_probability = round(float(self.enriched_mean_market_baseline_probability), 6)
        self.forecast_only_mean_market_baseline_delta = round(float(self.forecast_only_mean_market_baseline_delta), 6)
        self.enriched_mean_market_baseline_delta = round(float(self.enriched_mean_market_baseline_delta), 6)
        self.forecast_only_mean_market_baseline_delta_bps = round(float(self.forecast_only_mean_market_baseline_delta_bps), 2)
        self.enriched_mean_market_baseline_delta_bps = round(float(self.enriched_mean_market_baseline_delta_bps), 2)
        self.brier_improvement = round(float(self.brier_improvement), 6)
        self.log_loss_improvement = round(float(self.log_loss_improvement), 6)
        self.probability_gap = round(float(self.probability_gap), 6)
        self.market_baseline_probability_gap = round(float(self.market_baseline_probability_gap), 6)
        self.market_baseline_delta_gap = round(float(self.market_baseline_delta_gap), 6)
        self.market_baseline_delta_bps_gap = round(float(self.market_baseline_delta_bps_gap), 2)
        self.left_win_count = max(0, int(self.left_win_count))
        self.right_win_count = max(0, int(self.right_win_count))
        self.tie_count = max(0, int(self.tie_count))
        self.forecast_only_family_role = str(self.forecast_only_family_role).strip() or "forecast-only"
        self.enriched_family_role = str(self.enriched_family_role).strip() or "enriched"
        if not self.comparison_scope_hash:
            self.comparison_scope_hash = _comparison_scope_hash(
                {
                    "forecast_only_model_family": self.forecast_only_model_family,
                    "enriched_model_family": self.enriched_model_family,
                    "market_family": self.market_family,
                    "horizon_bucket": self.horizon_bucket,
                    "as_of_cutoff_at": self.as_of_cutoff_at.isoformat(),
                    "forecast_only_record_count": self.forecast_only_record_count,
                    "enriched_record_count": self.enriched_record_count,
                    "aligned_pair_count": self.aligned_pair_count,
                }
            )
        if not self.content_hash:
            self.content_hash = _comparison_scope_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "comparison_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ForecastUpliftComparisonReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _prepare_comparison_records(
    records: Sequence[Any],
    *,
    model_family: str,
    market_family: str,
    horizon_bucket: str,
    as_of: datetime | None = None,
) -> list[Any]:
    cutoff = _utc_datetime(as_of) if as_of is not None else None
    filtered = []
    for record in records:
        if _record_value(record, "model_family", "unknown") != model_family:
            continue
        if _record_value(record, "market_family", "unknown") != market_family:
            continue
        if _record_value(record, "horizon_bucket", "unknown") != horizon_bucket:
            continue
        record_cutoff = _record_cutoff(record)
        if cutoff is not None and (record_cutoff is None or record_cutoff > cutoff):
            continue
        filtered.append(record)
    return sorted(filtered, key=_paired_record_sort_key)


def build_model_version_comparison_report(
    records: Sequence[Any],
    *,
    left_model_family: str,
    right_model_family: str,
    market_family: str,
    horizon_bucket: str,
    as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> ForecastVersionComparisonReport:
    left_records = _prepare_comparison_records(
        records,
        model_family=left_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    right_records = _prepare_comparison_records(
        records,
        model_family=right_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    left_groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    right_groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for record in left_records:
        left_groups[_record_comparison_key(record)].append(record)
    for record in right_records:
        right_groups[_record_comparison_key(record)].append(record)
    aligned_keys = sorted(set(left_groups) | set(right_groups))
    pairs: list[ForecastVersionComparisonPair] = []
    left_win_count = right_win_count = tie_count = 0
    left_brier_scores: list[float] = []
    right_brier_scores: list[float] = []
    left_log_losses: list[float] = []
    right_log_losses: list[float] = []
    probability_gaps: list[float] = []
    brier_gaps: list[float] = []
    log_loss_gaps: list[float] = []
    unpaired_left_count = 0
    unpaired_right_count = 0
    for comparison_key in aligned_keys:
        left_bucket = left_groups.get(comparison_key, [])
        right_bucket = right_groups.get(comparison_key, [])
        pair_count = min(len(left_bucket), len(right_bucket))
        unpaired_left_count += max(0, len(left_bucket) - pair_count)
        unpaired_right_count += max(0, len(right_bucket) - pair_count)
        for left_record, right_record in zip(left_bucket[:pair_count], right_bucket[:pair_count]):
            cutoff_at = _record_cutoff_or_min(left_record)
            left_probability = _clamp_probability(float(_record_value(left_record, "forecast_probability", 0.0)))
            right_probability = _clamp_probability(float(_record_value(right_record, "forecast_probability", 0.0)))
            outcome = bool(_record_value(left_record, "resolved_outcome", False))
            left_brier = round(float(_record_value(left_record, "brier_score", (left_probability - float(outcome)) ** 2)), 6)
            right_brier = round(float(_record_value(right_record, "brier_score", (right_probability - float(outcome)) ** 2)), 6)
            left_log_loss = round(float(_record_value(left_record, "log_loss", _log_loss(left_probability, outcome))), 6)
            right_log_loss = round(float(_record_value(right_record, "log_loss", _log_loss(right_probability, outcome))), 6)
            winner = _winner_from_scores(left_brier, right_brier, left_log_loss, right_log_loss)
            left_win_count += 1 if winner == "left" else 0
            right_win_count += 1 if winner == "right" else 0
            tie_count += 1 if winner == "tie" else 0
            probability_gap = round(left_probability - right_probability, 6)
            brier_gap = round(left_brier - right_brier, 6)
            log_loss_gap = round(left_log_loss - right_log_loss, 6)
            pairs.append(
                ForecastVersionComparisonPair(
                    comparison_key="|".join(str(part) for part in comparison_key),
                    question_id=str(_record_value(left_record, "question_id", _record_value(right_record, "question_id", ""))),
                    market_id=str(_record_value(left_record, "market_id", _record_value(right_record, "market_id", ""))),
                    venue=_record_value(left_record, "venue", VenueName.polymarket),
                    cutoff_at=cutoff_at,
                    market_family=market_family,
                    horizon_bucket=horizon_bucket,
                    left_evaluation_id=str(_record_value(left_record, "evaluation_id", "")),
                    right_evaluation_id=str(_record_value(right_record, "evaluation_id", "")),
                    left_model_family=left_model_family,
                    right_model_family=right_model_family,
                    left_forecast_probability=left_probability,
                    right_forecast_probability=right_probability,
                    resolved_outcome=outcome,
                    left_brier_score=left_brier,
                    right_brier_score=right_brier,
                    left_log_loss=left_log_loss,
                    right_log_loss=right_log_loss,
                    probability_gap=probability_gap,
                    brier_gap=brier_gap,
                    log_loss_gap=log_loss_gap,
                    winner=winner,
                    metadata={
                        "comparison_scope": "same_dataset",
                    },
                )
            )
            left_brier_scores.append(left_brier)
            right_brier_scores.append(right_brier)
            left_log_losses.append(left_log_loss)
            right_log_losses.append(right_log_loss)
            probability_gaps.append(probability_gap)
            brier_gaps.append(brier_gap)
            log_loss_gaps.append(log_loss_gap)
    comparison_scope_hash = _comparison_scope_hash(
        {
            "left_model_family": left_model_family,
            "right_model_family": right_model_family,
            "market_family": market_family,
            "horizon_bucket": horizon_bucket,
            "as_of": _utc_datetime(as_of).isoformat() if as_of is not None else None,
            "pair_keys": [pair.comparison_key for pair in pairs],
            "left_ids": [pair.left_evaluation_id for pair in pairs],
            "right_ids": [pair.right_evaluation_id for pair in pairs],
        }
    )
    return ForecastVersionComparisonReport(
        left_model_family=left_model_family,
        right_model_family=right_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        comparison_scope="same_dataset",
        aligned_pair_count=len(pairs),
        left_evaluation_count=len(left_records),
        right_evaluation_count=len(right_records),
        left_mean_brier_score=_safe_mean(left_brier_scores),
        right_mean_brier_score=_safe_mean(right_brier_scores),
        left_mean_log_loss=_safe_mean(left_log_losses),
        right_mean_log_loss=_safe_mean(right_log_losses),
        mean_probability_gap=_safe_mean(probability_gaps),
        mean_brier_gap=_safe_mean(brier_gaps),
        mean_log_loss_gap=_safe_mean(log_loss_gaps),
        left_win_count=left_win_count,
        right_win_count=right_win_count,
        tie_count=tie_count,
        unpaired_left_count=unpaired_left_count,
        unpaired_right_count=unpaired_right_count,
        comparison_pairs=pairs,
        comparison_scope_hash=comparison_scope_hash,
        metadata={
            **dict(metadata or {}),
            "as_of_cutoff_at": _utc_datetime(as_of).isoformat() if as_of is not None else None,
            "contamination_free": as_of is not None,
            "stable_benchmark": True,
            "unpaired_left_count": unpaired_left_count,
            "unpaired_right_count": unpaired_right_count,
        },
    )


def build_baseline_comparison_report(
    records: Sequence[Any],
    *,
    model_family: str,
    market_family: str,
    horizon_bucket: str,
    baseline_probability: float,
    baseline_label: str = "simple_baseline",
    as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> ForecastBaselineComparisonReport:
    filtered = _prepare_comparison_records(
        records,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    pairs: list[ForecastBaselineComparisonPair] = []
    model_brier_scores: list[float] = []
    baseline_brier_scores: list[float] = []
    model_log_losses: list[float] = []
    baseline_log_losses: list[float] = []
    probability_gaps: list[float] = []
    brier_gaps: list[float] = []
    log_loss_gaps: list[float] = []
    model_win_count = baseline_win_count = tie_count = 0
    baseline_probability = _clamp_probability(baseline_probability)
    for record in filtered:
        probability = _clamp_probability(float(_record_value(record, "forecast_probability", 0.0)))
        outcome = bool(_record_value(record, "resolved_outcome", False))
        cutoff_at = _record_cutoff_or_min(record)
        model_brier = round(float(_record_value(record, "brier_score", (probability - float(outcome)) ** 2)), 6)
        model_log_loss = round(float(_record_value(record, "log_loss", _log_loss(probability, outcome))), 6)
        baseline_brier = round((baseline_probability - float(outcome)) ** 2, 6)
        baseline_log_loss = _log_loss(baseline_probability, outcome)
        winner = _winner_from_scores(model_brier, baseline_brier, model_log_loss, baseline_log_loss)
        model_win_count += 1 if winner == "left" else 0
        baseline_win_count += 1 if winner == "right" else 0
        tie_count += 1 if winner == "tie" else 0
        probability_gap = round(probability - baseline_probability, 6)
        brier_gap = round(model_brier - baseline_brier, 6)
        log_loss_gap = round(model_log_loss - baseline_log_loss, 6)
        pairs.append(
            ForecastBaselineComparisonPair(
                comparison_key="|".join(str(part) for part in _record_comparison_key(record)),
                question_id=str(_record_value(record, "question_id", "")),
                market_id=str(_record_value(record, "market_id", "")),
                venue=_record_value(record, "venue", VenueName.polymarket),
                cutoff_at=cutoff_at,
                market_family=market_family,
                horizon_bucket=horizon_bucket,
                evaluation_id=str(_record_value(record, "evaluation_id", "")),
                model_family=model_family,
                forecast_probability=probability,
                baseline_probability=baseline_probability,
                resolved_outcome=outcome,
                forecast_brier_score=model_brier,
                baseline_brier_score=baseline_brier,
                forecast_log_loss=model_log_loss,
                baseline_log_loss=baseline_log_loss,
                brier_gap=brier_gap,
                log_loss_gap=log_loss_gap,
                probability_gap=probability_gap,
                winner=winner,
                metadata={"comparison_scope": "same_dataset", "baseline_label": baseline_label},
            )
        )
        model_brier_scores.append(model_brier)
        baseline_brier_scores.append(baseline_brier)
        model_log_losses.append(model_log_loss)
        baseline_log_losses.append(baseline_log_loss)
        probability_gaps.append(probability_gap)
        brier_gaps.append(brier_gap)
        log_loss_gaps.append(log_loss_gap)
    comparison_scope_hash = _comparison_scope_hash(
        {
            "model_family": model_family,
            "market_family": market_family,
            "horizon_bucket": horizon_bucket,
            "baseline_label": baseline_label,
            "baseline_probability": baseline_probability,
            "as_of": _utc_datetime(as_of).isoformat() if as_of is not None else None,
            "evaluation_ids": [pair.evaluation_id for pair in pairs],
        }
    )
    return ForecastBaselineComparisonReport(
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        baseline_label=baseline_label,
        baseline_probability=baseline_probability,
        comparison_scope="same_dataset",
        record_count=len(filtered),
        model_mean_brier_score=_safe_mean(model_brier_scores),
        baseline_mean_brier_score=_safe_mean(baseline_brier_scores),
        model_mean_log_loss=_safe_mean(model_log_losses),
        baseline_mean_log_loss=_safe_mean(baseline_log_losses),
        mean_probability_gap=_safe_mean(probability_gaps),
        mean_brier_gap=_safe_mean(brier_gaps),
        mean_log_loss_gap=_safe_mean(log_loss_gaps),
        model_win_count=model_win_count,
        baseline_win_count=baseline_win_count,
        tie_count=tie_count,
        comparison_pairs=pairs,
        comparison_scope_hash=comparison_scope_hash,
        metadata={
            **dict(metadata or {}),
            "as_of_cutoff_at": _utc_datetime(as_of).isoformat() if as_of is not None else None,
            "contamination_free": as_of is not None,
            "stable_benchmark": True,
        },
    )


def _family_record_statistics(records: Sequence[Any]) -> dict[str, float]:
    ordered = list(records)
    if not ordered:
        return {
            "record_count": 0.0,
            "mean_forecast_probability": 0.0,
            "mean_brier_score": 0.0,
            "mean_log_loss": 0.0,
            "mean_market_baseline_probability": 0.0,
            "mean_market_baseline_delta": 0.0,
            "mean_market_baseline_delta_bps": 0.0,
        }
    forecast_probabilities = [
        _clamp_probability(float(_record_value(record, "forecast_probability", 0.0)))
        for record in ordered
    ]
    brier_scores = [
        round(float(_record_value(record, "brier_score", (probability - float(_record_value(record, "resolved_outcome", False))) ** 2)), 6)
        for record, probability in zip(ordered, forecast_probabilities)
    ]
    log_losses = [
        round(
            float(
                _record_value(
                    record,
                    "log_loss",
                    _log_loss(probability, bool(_record_value(record, "resolved_outcome", False))),
                )
            ),
            6,
        )
        for record, probability in zip(ordered, forecast_probabilities)
    ]
    market_baseline_probabilities = [
        _clamp_probability(float(_record_value(record, "market_baseline_probability", 0.5)))
        for record in ordered
    ]
    market_baseline_deltas = [
        round(
            float(
                _record_value(
                    record,
                    "market_baseline_delta",
                    forecast_probability - market_baseline_probability,
                )
            ),
            6,
        )
        for record, forecast_probability, market_baseline_probability in zip(
            ordered,
            forecast_probabilities,
            market_baseline_probabilities,
        )
    ]
    return {
        "record_count": float(len(ordered)),
        "mean_forecast_probability": _safe_mean(forecast_probabilities),
        "mean_brier_score": _safe_mean(brier_scores),
        "mean_log_loss": _safe_mean(log_losses),
        "mean_market_baseline_probability": _safe_mean(market_baseline_probabilities),
        "mean_market_baseline_delta": _safe_mean(market_baseline_deltas),
        "mean_market_baseline_delta_bps": _safe_mean([delta * 10000.0 for delta in market_baseline_deltas]),
    }


def build_forecast_uplift_comparison_report(
    records: Sequence[Any],
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
    left_records = _prepare_comparison_records(
        records,
        model_family=forecast_only_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    right_records = _prepare_comparison_records(
        records,
        model_family=enriched_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    pairwise_report = build_model_version_comparison_report(
        records,
        left_model_family=forecast_only_model_family,
        right_model_family=enriched_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
        metadata={
            **dict(metadata or {}),
            "comparison_type": "forecast_only_vs_enriched",
            "forecast_only_family_role": forecast_only_family_role,
            "enriched_family_role": enriched_family_role,
        },
    )
    left_stats = _family_record_statistics(left_records)
    right_stats = _family_record_statistics(right_records)
    return ForecastUpliftComparisonReport(
        forecast_only_model_family=forecast_only_model_family,
        enriched_model_family=enriched_model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of_cutoff_at=_utc_datetime(as_of) or _utc_now(),
        forecast_only_family_role=forecast_only_family_role,
        enriched_family_role=enriched_family_role,
        comparison_scope=pairwise_report.comparison_scope,
        record_count=max(len(left_records), len(right_records)),
        forecast_only_record_count=len(left_records),
        enriched_record_count=len(right_records),
        aligned_pair_count=pairwise_report.aligned_pair_count,
        forecast_only_mean_forecast_probability=left_stats["mean_forecast_probability"],
        enriched_mean_forecast_probability=right_stats["mean_forecast_probability"],
        forecast_only_mean_brier_score=left_stats["mean_brier_score"],
        enriched_mean_brier_score=right_stats["mean_brier_score"],
        forecast_only_mean_log_loss=left_stats["mean_log_loss"],
        enriched_mean_log_loss=right_stats["mean_log_loss"],
        forecast_only_mean_market_baseline_probability=left_stats["mean_market_baseline_probability"],
        enriched_mean_market_baseline_probability=right_stats["mean_market_baseline_probability"],
        forecast_only_mean_market_baseline_delta=left_stats["mean_market_baseline_delta"],
        enriched_mean_market_baseline_delta=right_stats["mean_market_baseline_delta"],
        forecast_only_mean_market_baseline_delta_bps=left_stats["mean_market_baseline_delta_bps"],
        enriched_mean_market_baseline_delta_bps=right_stats["mean_market_baseline_delta_bps"],
        brier_improvement=left_stats["mean_brier_score"] - right_stats["mean_brier_score"],
        log_loss_improvement=left_stats["mean_log_loss"] - right_stats["mean_log_loss"],
        probability_gap=right_stats["mean_forecast_probability"] - left_stats["mean_forecast_probability"],
        market_baseline_probability_gap=right_stats["mean_market_baseline_probability"] - left_stats["mean_market_baseline_probability"],
        market_baseline_delta_gap=right_stats["mean_market_baseline_delta"] - left_stats["mean_market_baseline_delta"],
        market_baseline_delta_bps_gap=right_stats["mean_market_baseline_delta_bps"] - left_stats["mean_market_baseline_delta_bps"],
        left_win_count=pairwise_report.left_win_count,
        right_win_count=pairwise_report.right_win_count,
        tie_count=pairwise_report.tie_count,
        comparison_scope_hash=_comparison_scope_hash(
            {
                "pairwise_comparison_scope_hash": pairwise_report.comparison_scope_hash,
                "forecast_only_record_count": len(left_records),
                "enriched_record_count": len(right_records),
                "forecast_only_mean_brier_score": left_stats["mean_brier_score"],
                "enriched_mean_brier_score": right_stats["mean_brier_score"],
                "forecast_only_mean_log_loss": left_stats["mean_log_loss"],
                "enriched_mean_log_loss": right_stats["mean_log_loss"],
                "forecast_only_mean_market_baseline_delta": left_stats["mean_market_baseline_delta"],
                "enriched_mean_market_baseline_delta": right_stats["mean_market_baseline_delta"],
            }
        ),
        metadata={
            **dict(metadata or {}),
            "as_of_cutoff_at": (_utc_datetime(as_of) or _utc_now()).isoformat(),
            "contamination_free": as_of is not None,
            "stable_benchmark": True,
            "forecast_only_family_role": forecast_only_family_role,
            "enriched_family_role": enriched_family_role,
            "pairwise_comparison_scope_hash": pairwise_report.comparison_scope_hash,
            "aligned_pair_count": pairwise_report.aligned_pair_count,
        },
    )


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
    model_family: str = "unknown"
    market_family: str = "unknown"
    horizon_bucket: str = "unknown"
    market_baseline_delta: float = 0.0
    market_baseline_delta_bps: float = 0.0
    forecast_ref: str | None = None
    resolution_policy_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("forecast_probability", "market_baseline_probability")
    @classmethod
    def _normalize_probability(cls, value: float) -> float:
        return _clamp_probability(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _normalize_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        return _unique_refs(values)

    @model_validator(mode="after")
    def _normalize_dates(self) -> "ForecastEvaluationRecord":
        self.cutoff_at = _utc_datetime(self.cutoff_at) or _utc_now()
        self.created_at = _utc_datetime(self.created_at) or _utc_now()
        self.forecast_probability = _clamp_probability(self.forecast_probability)
        self.market_baseline_probability = _clamp_probability(self.market_baseline_probability)
        self.market_baseline_delta = round(self.forecast_probability - self.market_baseline_probability, 6)
        self.market_baseline_delta_bps = round(self.market_baseline_delta * 10000.0, 2)
        if not self.ece_bucket:
            self.ece_bucket = _ece_bucket(self.forecast_probability)
        self.evidence_refs = _unique_refs(self.evidence_refs)
        return self

    @property
    def forecast_probability_yes(self) -> float:
        return self.forecast_probability

    @classmethod
    def evaluate(
        cls,
        *,
        question_id: str,
        market_id: str,
        forecast_probability: float,
        resolved_outcome: bool,
        venue: VenueName = VenueName.polymarket,
        cutoff_at: datetime | None = None,
        market_baseline_probability: float = 0.5,
        abstain_flag: bool = False,
        model_family: str = "unknown",
        market_family: str = "unknown",
        horizon_bucket: str = "unknown",
        forecast_ref: str | None = None,
        resolution_policy_ref: str | None = None,
        evidence_refs: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ForecastEvaluationRecord":
        forecast_probability = _clamp_probability(forecast_probability)
        baseline = _clamp_probability(market_baseline_probability)
        return cls(
            question_id=question_id,
            market_id=market_id,
            venue=venue,
            cutoff_at=cutoff_at or _utc_now(),
            forecast_probability=forecast_probability,
            market_baseline_probability=baseline,
            resolved_outcome=bool(resolved_outcome),
            brier_score=round((forecast_probability - float(resolved_outcome)) ** 2, 6),
            log_loss=round(_log_loss(forecast_probability, bool(resolved_outcome)), 6),
            ece_bucket=_ece_bucket(forecast_probability),
            market_baseline_delta=round(forecast_probability - baseline, 6),
            market_baseline_delta_bps=round((forecast_probability - baseline) * 10000.0, 2),
            abstain_flag=bool(abstain_flag),
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            forecast_ref=forecast_ref,
            resolution_policy_ref=resolution_policy_ref,
            evidence_refs=list(evidence_refs or []),
            metadata=dict(metadata or {}),
        )


class CalibrationSnapshot(BaseModel):
    schema_version: str = "v1"
    snapshot_id: str = Field(default_factory=lambda: f"cal_{uuid4().hex[:12]}")
    model_family: str
    market_family: str
    horizon_bucket: str
    window_start: datetime
    window_end: datetime
    calibration_method: str = "ece-10bin"
    ece: float = 0.0
    sharpness: float = 0.0
    coverage: float = 0.0
    record_count: int = 0
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    mean_forecast_probability: float = 0.0
    mean_market_baseline_probability: float = 0.0
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    abstention_coverage: float = 0.0
    abstain_rate: float = 0.0
    bucket_summaries: list["CalibrationBucketSummary"] = Field(default_factory=list)
    evaluation_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("window_start", "window_end", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: Any) -> Any:
        return _utc_datetime(value) or value

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationSnapshot":
        self.window_start = _utc_datetime(self.window_start) or _utc_now()
        self.window_end = _utc_datetime(self.window_end) or self.window_start
        self.ece = _clamp_probability(self.ece)
        self.sharpness = _clamp_probability(self.sharpness)
        self.coverage = _clamp_probability(self.coverage)
        self.abstention_coverage = _clamp_probability(self.abstention_coverage or self.coverage)
        self.abstain_rate = _clamp_probability(self.abstain_rate)
        self.bucket_summaries = sorted(self.bucket_summaries, key=lambda item: (item.bucket_label, item.content_hash))
        self.evaluation_refs = _unique_refs(self.evaluation_refs)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "snapshot_id": "",
                    "content_hash": "",
                }
            )
        return self

    @classmethod
    def from_records(
        cls,
        records: Sequence[ForecastEvaluationRecord],
        *,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        calibration_method: str = "ece-10bin",
        metadata: dict[str, Any] | None = None,
    ) -> "CalibrationSnapshot":
        ordered = sorted(records, key=lambda item: (item.cutoff_at, item.evaluation_id))
        if not ordered:
            now = _utc_now()
            return cls(
                model_family=model_family,
                market_family=market_family,
                horizon_bucket=horizon_bucket,
                window_start=now,
                window_end=now,
                calibration_method=calibration_method,
                metadata=dict(metadata or {}),
            )

        active = [record for record in ordered if not record.abstain_flag]
        coverage = len(active) / len(ordered)
        abstain_rate = 1.0 - coverage
        forecast_probs = [record.forecast_probability for record in active]
        outcomes = [1.0 if record.resolved_outcome else 0.0 for record in active]
        baseline_probs = [record.market_baseline_probability for record in ordered]
        baseline_deltas = [
            getattr(
                record,
                "market_baseline_delta",
                round(record.forecast_probability - record.market_baseline_probability, 6),
            )
            for record in ordered
        ]
        brier_scores = [record.brier_score for record in ordered]
        log_losses = [record.log_loss for record in ordered]
        if active:
            bins: dict[str, list[ForecastEvaluationRecord]] = {}
            for record in active:
                bins.setdefault(record.ece_bucket, []).append(record)
            weighted_error = 0.0
            for bucket_records in bins.values():
                bucket_weight = len(bucket_records) / len(active)
                bucket_probability = _safe_mean([record.forecast_probability for record in bucket_records])
                bucket_outcome = _safe_mean([1.0 if record.resolved_outcome else 0.0 for record in bucket_records])
                weighted_error += bucket_weight * abs(bucket_probability - bucket_outcome)
            ece = weighted_error
            sharpness = _safe_mean([abs(probability - 0.5) * 2.0 for probability in forecast_probs])
        else:
            ece = 0.0
            sharpness = 0.0

        return cls(
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            window_start=ordered[0].cutoff_at,
            window_end=ordered[-1].cutoff_at,
            calibration_method=calibration_method,
            ece=round(ece, 6),
            sharpness=round(sharpness, 6),
            coverage=round(coverage, 6),
            abstention_coverage=round(coverage, 6),
            record_count=len(ordered),
            mean_brier_score=round(_safe_mean(brier_scores), 6),
            mean_log_loss=round(_safe_mean(log_losses), 6),
            mean_forecast_probability=round(_safe_mean(forecast_probs), 6),
            mean_market_baseline_probability=round(_safe_mean(baseline_probs), 6),
            mean_market_baseline_delta=round(_safe_mean(baseline_deltas), 6),
            mean_market_baseline_delta_bps=round(_safe_mean([delta * 10000.0 for delta in baseline_deltas]), 2),
            abstain_rate=round(abstain_rate, 6),
            bucket_summaries=_build_calibration_bucket_summaries(ordered),
            evaluation_refs=[record.evaluation_id for record in ordered],
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_records_as_of(
        cls,
        records: Sequence[ForecastEvaluationRecord],
        *,
        as_of: datetime,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        calibration_method: str = "ece-10bin",
        metadata: dict[str, Any] | None = None,
    ) -> "CalibrationSnapshot":
        as_of_cutoff = _utc_datetime(as_of) or _utc_now()
        valid_records = [
            record
            for record in records
            if _record_cutoff(record) is not None
        ]
        filtered = [
            record
            for record in valid_records
            if (record_cutoff := _record_cutoff(record)) is not None and record_cutoff <= as_of_cutoff
        ]
        invalid_cutoff_count = max(0, len(records) - len(valid_records))
        future_cutoff_count = max(0, len(valid_records) - len(filtered))
        snapshot = cls.from_records(
            filtered,
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            calibration_method=calibration_method,
            metadata={
                **dict(metadata or {}),
                "as_of_cutoff_at": as_of_cutoff.isoformat(),
                "contamination_free": True,
                "included_record_count": len(filtered),
                "excluded_future_record_count": future_cutoff_count,
                "excluded_invalid_record_count": invalid_cutoff_count,
            },
        )
        snapshot.metadata.setdefault("as_of_cutoff_at", as_of_cutoff.isoformat())
        snapshot.metadata.setdefault("contamination_free", True)
        snapshot.metadata.setdefault("included_record_count", len(filtered))
        snapshot.metadata.setdefault("excluded_future_record_count", future_cutoff_count)
        snapshot.metadata.setdefault("excluded_invalid_record_count", invalid_cutoff_count)
        return snapshot


class CalibrationBucketSummary(BaseModel):
    schema_version: str = "v1"
    bucket_label: str
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    mean_forecast_probability: float = 0.0
    mean_outcome_yes: float = 0.0
    mean_abs_error: float = 0.0
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    mean_market_baseline_probability: float = 0.0
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    ece_component: float = 0.0
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationBucketSummary":
        self.bucket_label = str(self.bucket_label).strip() or "unknown"
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.mean_forecast_probability = _clamp_probability(self.mean_forecast_probability)
        self.mean_outcome_yes = _clamp_probability(self.mean_outcome_yes)
        self.mean_abs_error = _clamp_probability(self.mean_abs_error)
        self.mean_brier_score = max(0.0, float(self.mean_brier_score))
        self.mean_log_loss = max(0.0, float(self.mean_log_loss))
        self.mean_market_baseline_probability = _clamp_probability(self.mean_market_baseline_probability)
        self.mean_market_baseline_delta = round(float(self.mean_market_baseline_delta), 6)
        self.mean_market_baseline_delta_bps = round(float(self.mean_market_baseline_delta_bps), 2)
        self.ece_component = max(0.0, float(self.ece_component))
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "content_hash": "",
                }
            )
        return self


class CalibrationCurveReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"calcurve_{uuid4().hex[:12]}")
    model_family: str
    market_family: str
    horizon_bucket: str
    bucket_count: int = 0
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    active_coverage: float = 0.0
    abstention_coverage: float = 0.0
    abstain_rate: float = 0.0
    mean_ece: float = 0.0
    mean_sharpness: float = 0.0
    bucket_summaries: list[CalibrationBucketSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationCurveReport":
        self.bucket_count = max(0, int(self.bucket_count))
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.active_coverage = _clamp_probability(self.active_coverage)
        self.abstention_coverage = _clamp_probability(self.abstention_coverage)
        self.abstain_rate = _clamp_probability(self.abstain_rate)
        self.mean_ece = max(0.0, float(self.mean_ece))
        self.mean_sharpness = _clamp_probability(self.mean_sharpness)
        self.bucket_summaries = sorted(self.bucket_summaries, key=lambda item: (item.bucket_label, item.content_hash))
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationCurveReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class CategoryHorizonPerformanceSummary(BaseModel):
    schema_version: str = "v1"
    category: str
    horizon_bucket: str
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    mean_forecast_probability: float = 0.0
    mean_outcome_yes: float = 0.0
    hit_rate: float | None = None
    mean_market_baseline_probability: float = 0.0
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    mean_ece: float = 0.0
    mean_sharpness: float = 0.0
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CategoryHorizonPerformanceSummary":
        self.category = str(self.category).strip() or "unknown"
        self.horizon_bucket = str(self.horizon_bucket).strip() or "unknown"
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.mean_brier_score = max(0.0, float(self.mean_brier_score))
        self.mean_log_loss = max(0.0, float(self.mean_log_loss))
        self.mean_forecast_probability = _clamp_probability(self.mean_forecast_probability)
        self.mean_outcome_yes = _clamp_probability(self.mean_outcome_yes)
        self.mean_market_baseline_probability = _clamp_probability(self.mean_market_baseline_probability)
        self.mean_market_baseline_delta = round(float(self.mean_market_baseline_delta), 6)
        self.mean_market_baseline_delta_bps = round(float(self.mean_market_baseline_delta_bps), 2)
        self.mean_ece = max(0.0, float(self.mean_ece))
        self.mean_sharpness = _clamp_probability(self.mean_sharpness)
        if self.hit_rate is not None:
            self.hit_rate = _clamp_probability(self.hit_rate)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "content_hash": "",
                }
            )
        return self


class CategoryHorizonPerformanceReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"calseg_{uuid4().hex[:12]}")
    model_family: str = "unknown"
    market_family: str = "unknown"
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    segment_count: int = 0
    segments: list[CategoryHorizonPerformanceSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CategoryHorizonPerformanceReport":
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.segment_count = max(0, int(self.segment_count))
        self.segments = sorted(self.segments, key=lambda item: (item.category, item.horizon_bucket, item.content_hash))
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "CategoryHorizonPerformanceReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class AbstentionQualityReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"abstq_{uuid4().hex[:12]}")
    model_family: str = "unknown"
    market_family: str = "unknown"
    horizon_bucket: str = "unknown"
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    active_coverage: float = 0.0
    abstention_coverage: float = 0.0
    abstain_rate: float = 0.0
    mean_active_brier_score: float = 0.0
    mean_abstained_brier_score: float = 0.0
    mean_active_log_loss: float = 0.0
    mean_abstained_log_loss: float = 0.0
    mean_active_abs_margin: float = 0.0
    mean_abstained_abs_margin: float = 0.0
    mean_abstention_brier_gap: float = 0.0
    mean_abstention_margin_gap: float = 0.0
    mean_active_market_baseline_delta: float = 0.0
    mean_abstained_market_baseline_delta: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AbstentionQualityReport":
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.active_coverage = _clamp_probability(self.active_coverage)
        self.abstention_coverage = _clamp_probability(self.abstention_coverage)
        self.abstain_rate = _clamp_probability(self.abstain_rate)
        self.mean_active_brier_score = max(0.0, float(self.mean_active_brier_score))
        self.mean_abstained_brier_score = max(0.0, float(self.mean_abstained_brier_score))
        self.mean_active_log_loss = max(0.0, float(self.mean_active_log_loss))
        self.mean_abstained_log_loss = max(0.0, float(self.mean_abstained_log_loss))
        self.mean_active_abs_margin = _clamp_probability(self.mean_active_abs_margin)
        self.mean_abstained_abs_margin = _clamp_probability(self.mean_abstained_abs_margin)
        self.mean_abstention_brier_gap = float(self.mean_abstention_brier_gap)
        self.mean_abstention_margin_gap = float(self.mean_abstention_margin_gap)
        self.mean_active_market_baseline_delta = round(float(self.mean_active_market_baseline_delta), 6)
        self.mean_abstained_market_baseline_delta = round(float(self.mean_abstained_market_baseline_delta), 6)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "AbstentionQualityReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _build_calibration_bucket_summaries(records: Sequence[ForecastEvaluationRecord]) -> list[CalibrationBucketSummary]:
    active_records = [record for record in records if not record.abstain_flag]
    if not active_records:
        return []

    bucket_groups: dict[str, list[ForecastEvaluationRecord]] = defaultdict(list)
    abstain_counts: Counter[str] = Counter()
    for record in records:
        bucket_groups[record.ece_bucket].append(record)
        if record.abstain_flag:
            abstain_counts[record.ece_bucket] += 1

    summaries: list[CalibrationBucketSummary] = []
    for bucket_label in sorted(bucket_groups):
        bucket_records = bucket_groups[bucket_label]
        active_bucket_records = [record for record in bucket_records if not record.abstain_flag]
        if not active_bucket_records:
            summaries.append(
                CalibrationBucketSummary(
                    bucket_label=bucket_label,
                    record_count=len(bucket_records),
                    active_count=0,
                    abstain_count=abstain_counts[bucket_label],
                )
            )
            continue
        mean_probability = _safe_mean([record.forecast_probability for record in active_bucket_records])
        mean_outcome = _safe_mean([1.0 if record.resolved_outcome else 0.0 for record in active_bucket_records])
        mean_brier = _safe_mean([record.brier_score for record in active_bucket_records])
        mean_log_loss = _safe_mean([record.log_loss for record in active_bucket_records])
        mean_baseline = _safe_mean([record.market_baseline_probability for record in active_bucket_records])
        mean_delta = _safe_mean([record.market_baseline_delta for record in active_bucket_records])
        summaries.append(
            CalibrationBucketSummary(
                bucket_label=bucket_label,
                record_count=len(bucket_records),
                active_count=len(active_bucket_records),
                abstain_count=abstain_counts[bucket_label],
                mean_forecast_probability=mean_probability,
                mean_outcome_yes=mean_outcome,
                mean_abs_error=abs(mean_probability - mean_outcome),
                mean_brier_score=mean_brier,
                mean_log_loss=mean_log_loss,
                mean_market_baseline_probability=mean_baseline,
                mean_market_baseline_delta=mean_delta,
                mean_market_baseline_delta_bps=mean_delta * 10000.0,
                ece_component=(len(active_bucket_records) / len(active_records)) * abs(mean_probability - mean_outcome),
            )
        )
    return summaries


def build_calibration_curve_report(
    records: Sequence[Any],
    *,
    model_family: str | None = None,
    market_family: str | None = None,
    horizon_bucket: str | None = None,
    bucket_count: int = 10,
    as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> CalibrationCurveReport:
    filtered = _filter_evaluation_records(
        records,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    if not filtered:
        return CalibrationCurveReport(
            model_family=model_family or "all",
            market_family=market_family or "all",
            horizon_bucket=horizon_bucket or "all",
            bucket_count=bucket_count,
            metadata=dict(metadata or {}),
        )._normalize()

    active_records = [record for record in filtered if not _record_value(record, "abstain_flag", False)]
    bucket_groups: dict[str, list[Any]] = defaultdict(list)
    for record in filtered:
        bucket_groups[_record_value(record, "ece_bucket", _ece_bucket(_record_value(record, "forecast_probability", 0.5)))].append(record)

    active_total = len(active_records)
    total = len(filtered)
    bucket_summaries: list[CalibrationBucketSummary] = []
    weighted_ece = 0.0
    for bucket_label in sorted(bucket_groups):
        bucket_records = bucket_groups[bucket_label]
        active_bucket_records = [record for record in bucket_records if not _record_value(record, "abstain_flag", False)]
        if not active_bucket_records:
            bucket_summaries.append(
                CalibrationBucketSummary(
                    bucket_label=bucket_label,
                    record_count=len(bucket_records),
                    active_count=0,
                    abstain_count=len(bucket_records),
                )
            )
            continue
        bucket_probability = _safe_mean([float(_record_value(record, "forecast_probability", 0.0)) for record in active_bucket_records])
        bucket_outcome = _safe_mean([1.0 if _record_value(record, "resolved_outcome", False) else 0.0 for record in active_bucket_records])
        bucket_ece_component = (
            (len(active_bucket_records) / active_total) * abs(bucket_probability - bucket_outcome)
            if active_total
            else 0.0
        )
        weighted_ece += bucket_ece_component
        bucket_summaries.append(
            CalibrationBucketSummary(
                bucket_label=bucket_label,
                record_count=len(bucket_records),
                active_count=len(active_bucket_records),
                abstain_count=len(bucket_records) - len(active_bucket_records),
                mean_forecast_probability=bucket_probability,
                mean_outcome_yes=bucket_outcome,
                mean_abs_error=abs(bucket_probability - bucket_outcome),
                mean_brier_score=_safe_mean([float(_record_value(record, "brier_score", 0.0)) for record in active_bucket_records]),
                mean_log_loss=_safe_mean([float(_record_value(record, "log_loss", 0.0)) for record in active_bucket_records]),
                mean_market_baseline_probability=_safe_mean([float(_record_value(record, "market_baseline_probability", 0.0)) for record in active_bucket_records]),
                mean_market_baseline_delta=_safe_mean([float(_record_value(record, "market_baseline_delta", 0.0)) for record in active_bucket_records]),
                mean_market_baseline_delta_bps=_safe_mean([float(_record_value(record, "market_baseline_delta_bps", 0.0)) for record in active_bucket_records]),
                ece_component=bucket_ece_component,
            )
        )

    mean_sharpness = _safe_mean([abs(float(_record_value(record, "forecast_probability", 0.0)) - 0.5) * 2.0 for record in active_records])
    return CalibrationCurveReport(
        model_family=model_family or "all",
        market_family=market_family or "all",
        horizon_bucket=horizon_bucket or "all",
        bucket_count=bucket_count,
        record_count=total,
        active_count=active_total,
        abstain_count=total - active_total,
        active_coverage=(active_total / total) if total else 0.0,
        abstention_coverage=(active_total / total) if total else 0.0,
        abstain_rate=((total - active_total) / total) if total else 0.0,
        mean_ece=weighted_ece,
        mean_sharpness=mean_sharpness,
        bucket_summaries=bucket_summaries,
        metadata=dict(metadata or {}),
    )._normalize()


def build_category_horizon_performance_report(
    records: Sequence[Any],
    *,
    model_family: str | None = None,
    market_family: str | None = None,
    as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> CategoryHorizonPerformanceReport:
    filtered = _filter_evaluation_records(
        records,
        model_family=model_family,
        market_family=market_family,
        as_of=as_of,
    )
    if not filtered:
        return CategoryHorizonPerformanceReport(
            model_family=model_family or "all",
            market_family=market_family or "all",
            metadata=dict(metadata or {}),
        )._normalize()

    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for record in filtered:
        grouped[(_record_category(record), _record_horizon_bucket(record))].append(record)

    segments: list[CategoryHorizonPerformanceSummary] = []
    for (category, horizon), segment_records in sorted(grouped.items()):
        active_records = [record for record in segment_records if not _record_value(record, "abstain_flag", False)]
        active_total = len(active_records)
        all_total = len(segment_records)
        segment_briers = [float(_record_value(record, "brier_score", 0.0)) for record in segment_records]
        segment_log_losses = [float(_record_value(record, "log_loss", 0.0)) for record in segment_records]
        active_probabilities = [float(_record_value(record, "forecast_probability", 0.0)) for record in active_records]
        active_outcomes = [1.0 if _record_value(record, "resolved_outcome", False) else 0.0 for record in active_records]
        active_baselines = [float(_record_value(record, "market_baseline_probability", 0.0)) for record in active_records]
        active_deltas = [float(_record_value(record, "market_baseline_delta", 0.0)) for record in active_records]
        segments.append(
            CategoryHorizonPerformanceSummary(
                category=category,
                horizon_bucket=horizon,
                record_count=all_total,
                active_count=active_total,
                abstain_count=all_total - active_total,
                mean_brier_score=_safe_mean(segment_briers),
                mean_log_loss=_safe_mean(segment_log_losses),
                mean_forecast_probability=_safe_mean(active_probabilities),
                mean_outcome_yes=_safe_mean(active_outcomes),
                hit_rate=_safe_mean(
                    [
                        1.0
                        if (float(_record_value(record, "forecast_probability", 0.0)) >= 0.5)
                        == bool(_record_value(record, "resolved_outcome", False))
                        else 0.0
                        for record in active_records
                    ]
                )
                if active_records
                else 0.0,
                mean_market_baseline_probability=_safe_mean(active_baselines),
                mean_market_baseline_delta=_safe_mean(active_deltas),
                mean_market_baseline_delta_bps=_safe_mean([delta * 10000.0 for delta in active_deltas]),
                mean_ece=(
                    _safe_mean(
                        [
                            abs(float(_record_value(record, "forecast_probability", 0.0)) - float(_record_value(record, "resolved_outcome", False)))
                            for record in active_records
                        ]
                    )
                    if active_records
                    else 0.0
                ),
                mean_sharpness=_safe_mean([abs(probability - 0.5) * 2.0 for probability in active_probabilities]),
            )
        )

    return CategoryHorizonPerformanceReport(
        model_family=model_family or "all",
        market_family=market_family or "all",
        record_count=len(filtered),
        active_count=sum(segment.active_count for segment in segments),
        abstain_count=sum(segment.abstain_count for segment in segments),
        segment_count=len(segments),
        segments=segments,
        metadata=dict(metadata or {}),
    )._normalize()


def build_abstention_quality_report(
    records: Sequence[Any],
    *,
    model_family: str | None = None,
    market_family: str | None = None,
    horizon_bucket: str | None = None,
    as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> AbstentionQualityReport:
    filtered = _filter_evaluation_records(
        records,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        as_of=as_of,
    )
    if not filtered:
        return AbstentionQualityReport(
            model_family=model_family or "all",
            market_family=market_family or "all",
            horizon_bucket=horizon_bucket or "all",
            metadata=dict(metadata or {}),
        )._normalize()

    active_records = [record for record in filtered if not _record_value(record, "abstain_flag", False)]
    abstained_records = [record for record in filtered if _record_value(record, "abstain_flag", False)]
    active_count = len(active_records)
    abstain_count = len(abstained_records)
    total = len(filtered)
    active_abs_margins = [abs(float(_record_value(record, "forecast_probability", 0.0)) - 0.5) * 2.0 for record in active_records]
    abstained_abs_margins = [abs(float(_record_value(record, "forecast_probability", 0.0)) - 0.5) * 2.0 for record in abstained_records]
    active_briers = [float(_record_value(record, "brier_score", 0.0)) for record in active_records]
    abstained_briers = [float(_record_value(record, "brier_score", 0.0)) for record in abstained_records]
    active_log_losses = [float(_record_value(record, "log_loss", 0.0)) for record in active_records]
    abstained_log_losses = [float(_record_value(record, "log_loss", 0.0)) for record in abstained_records]
    active_baseline_deltas = [float(_record_value(record, "market_baseline_delta", 0.0)) for record in active_records]
    abstained_baseline_deltas = [float(_record_value(record, "market_baseline_delta", 0.0)) for record in abstained_records]

    return AbstentionQualityReport(
        model_family=model_family or "all",
        market_family=market_family or "all",
        horizon_bucket=horizon_bucket or "all",
        record_count=total,
        active_count=active_count,
        abstain_count=abstain_count,
        active_coverage=(active_count / total) if total else 0.0,
        abstention_coverage=(active_count / total) if total else 0.0,
        abstain_rate=(abstain_count / total) if total else 0.0,
        mean_active_brier_score=_safe_mean(active_briers),
        mean_abstained_brier_score=_safe_mean(abstained_briers),
        mean_active_log_loss=_safe_mean(active_log_losses),
        mean_abstained_log_loss=_safe_mean(abstained_log_losses),
        mean_active_abs_margin=_safe_mean(active_abs_margins),
        mean_abstained_abs_margin=_safe_mean(abstained_abs_margins),
        mean_abstention_brier_gap=_safe_mean(abstained_briers) - _safe_mean(active_briers),
        mean_abstention_margin_gap=_safe_mean(active_abs_margins) - _safe_mean(abstained_abs_margins),
        mean_active_market_baseline_delta=_safe_mean(active_baseline_deltas),
        mean_abstained_market_baseline_delta=_safe_mean(abstained_baseline_deltas),
        metadata=dict(metadata or {}),
    )._normalize()


class AsOfEvidenceSet(BaseModel):
    schema_version: str = "v1"
    evidence_set_id: str = Field(default_factory=lambda: f"asof_{uuid4().hex[:12]}")
    market_id: str
    cutoff_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)
    retrieval_policy: str = "as_of"
    freshness_summary: dict[str, Any] = Field(default_factory=dict)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AsOfEvidenceSet":
        self.cutoff_at = _utc_datetime(self.cutoff_at) or _utc_now()
        self.evidence_refs = _unique_refs(self.evidence_refs)
        self.retrieval_policy = str(self.retrieval_policy).strip() or "as_of"
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "evidence_set_id": "",
                    "content_hash": "",
                }
            )
        return self

    @classmethod
    def from_evidence(
        cls,
        evidence_packets: Sequence[EvidencePacket],
        *,
        market_id: str,
        cutoff_at: datetime,
        retrieval_policy: str = "as_of",
        metadata: dict[str, Any] | None = None,
    ) -> "AsOfEvidenceSet":
        cutoff_at = _utc_datetime(cutoff_at) or _utc_now()
        selected = [
            packet
            for packet in evidence_packets
            if packet.market_id == market_id and _utc_datetime(packet.observed_at) <= cutoff_at
        ]
        selected_refs = [packet.evidence_id for packet in selected]
        freshness_scores = [packet.freshness_score for packet in selected]
        provenance_counts = Counter(packet.source_kind.value for packet in selected)
        source_urls = sum(1 for packet in selected if packet.source_url)
        freshness_summary = {
            "count": len(selected),
            "mean_freshness_score": round(_safe_mean(freshness_scores), 6),
            "source_url_count": source_urls,
            "observed_window_start": min((packet.observed_at for packet in selected), default=cutoff_at),
            "observed_window_end": max((packet.observed_at for packet in selected), default=cutoff_at),
        }
        provenance_summary = {
            "source_kind_counts": dict(provenance_counts),
            "source_ref_count": len(_unique_refs(*(packet.provenance_refs for packet in selected))),
        }
        return cls(
            market_id=market_id,
            cutoff_at=cutoff_at,
            evidence_refs=selected_refs,
            retrieval_policy=retrieval_policy,
            freshness_summary=freshness_summary,
            provenance_summary=provenance_summary,
            metadata=dict(metadata or {}),
        )


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
        self.written_at = _utc_datetime(self.written_at) or _utc_now()
        self.as_of_cutoff_at = _utc_datetime(self.as_of_cutoff_at) or self.as_of_cutoff_at
        self.summary = str(self.summary).strip() or f"Research report for {self.market_id}"
        self.facts = _unique_refs(self.facts)
        self.theses = _unique_refs(self.theses)
        self.objections = _unique_refs(self.objections)
        self.supporting_evidence_refs = _unique_refs(self.supporting_evidence_refs)
        self.key_factors = _unique_refs(self.key_factors or self.theses or self.facts)
        self.counterarguments = _unique_refs(self.counterarguments or self.objections)
        self.open_questions = [str(item).strip() for item in self.open_questions if str(item).strip()]
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                    "evidence_set_id": "",
                }
            )
        return self

    @classmethod
    def from_evidence_set(
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
        derived_facts = list(facts or _unique_refs([packet.claim for packet in ordered[:5]]))
        derived_theses = list(theses or _unique_refs([packet.claim for packet in ordered[:3]]))
        derived_objections = list(
            objections
            or _unique_refs(
                [
                    packet.claim
                    for packet in selected
                    if packet.stance == "bearish"
                ]
                or [packet.claim for packet in ordered if packet.claim not in derived_theses]
            )
        )
        derived_key_factors = list(key_factors or derived_theses or derived_facts)
        derived_counterarguments = list(counterarguments or derived_objections)
        derived_open_questions = list(open_questions or [])
        summary = f"Research report for {evidence_set.market_id}"
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
            written_at=_utc_now(),
            as_of_cutoff_at=evidence_set.cutoff_at,
            evidence_set_id=evidence_set.evidence_set_id,
            summary=summary,
            metadata={
                **dict(metadata or {}),
                "fact_count": len(derived_facts),
                "thesis_count": len(derived_theses),
                "objection_count": len(derived_objections),
            },
        )


class BenchmarkFamilySummary(BaseModel):
    schema_version: str = "v1"
    summary_id: str = Field(default_factory=lambda: f"bfs_{uuid4().hex[:12]}")
    family_label: str
    family_role: str = "custom"
    model_family: str
    market_family: str
    horizon_bucket: str
    record_count: int = 0
    as_of_cutoff_at: datetime
    contamination_free: bool = True
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    ece: float = 0.0
    sharpness: float = 0.0
    abstention_coverage: float = 0.0
    mean_market_baseline_probability: float = 0.0
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    canonical_score_components: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "BenchmarkFamilySummary":
        self.as_of_cutoff_at = _utc_datetime(self.as_of_cutoff_at) or _utc_now()
        self.record_count = max(0, int(self.record_count))
        self.contamination_free = bool(self.contamination_free)
        self.mean_brier_score = round(float(self.mean_brier_score), 6)
        self.mean_log_loss = round(float(self.mean_log_loss), 6)
        self.ece = round(float(self.ece), 6)
        self.sharpness = round(float(self.sharpness), 6)
        self.abstention_coverage = round(float(self.abstention_coverage), 6)
        self.mean_market_baseline_probability = round(float(self.mean_market_baseline_probability), 6)
        self.mean_market_baseline_delta = round(float(self.mean_market_baseline_delta), 6)
        self.mean_market_baseline_delta_bps = round(float(self.mean_market_baseline_delta_bps), 2)
        self.family_label = str(self.family_label).strip() or self.model_family
        self.family_role = str(self.family_role).strip() or _family_role_from_label(self.family_label)
        if not self.canonical_score_components:
            self.canonical_score_components = {
                "brier_score": self.mean_brier_score,
                "log_loss": self.mean_log_loss,
                "ece": self.ece,
                "sharpness": self.sharpness,
                "abstention_coverage": self.abstention_coverage,
                "market_baseline_probability": self.mean_market_baseline_probability,
                "market_baseline_delta": self.mean_market_baseline_delta,
                "market_baseline_delta_bps": self.mean_market_baseline_delta_bps,
            }
        else:
            self.canonical_score_components = {
                str(key): round(float(value), 6 if key != "market_baseline_delta_bps" else 2)
                for key, value in self.canonical_score_components.items()
            }
        if not self.content_hash:
            self.content_hash = _comparison_scope_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "summary_id": "",
                    "content_hash": "",
                }
            )
        return self


class AsOfBenchmarkSuite(BaseModel):
    schema_version: str = "v1"
    suite_id: str = Field(default_factory=lambda: f"suite_{uuid4().hex[:12]}")
    market_id: str
    cutoff_at: datetime
    evidence_set: AsOfEvidenceSet
    research_report: ResearchReport
    calibration_snapshot: CalibrationSnapshot | None = None
    family_summaries: list[BenchmarkFamilySummary] = Field(default_factory=list)
    model_version_comparisons: list[ForecastVersionComparisonReport] = Field(default_factory=list)
    baseline_comparisons: list[ForecastBaselineComparisonReport] = Field(default_factory=list)
    family_labels: dict[str, str] = Field(default_factory=dict)
    canonical_score_components: dict[str, float] = Field(default_factory=dict)
    excluded_future_finding_count: int = 0
    excluded_future_evaluation_count: int = 0
    contamination_free: bool = True
    stable_benchmark: bool = True
    benchmark_scope_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AsOfBenchmarkSuite":
        self.cutoff_at = _utc_datetime(self.cutoff_at) or _utc_now()
        self.family_summaries = sorted(self.family_summaries, key=lambda item: (item.family_label, item.model_family, item.summary_id))
        self.model_version_comparisons = list(self.model_version_comparisons)
        self.baseline_comparisons = list(self.baseline_comparisons)
        self.family_labels = {str(key): str(value) for key, value in self.family_labels.items()}
        self.excluded_future_finding_count = max(0, int(self.excluded_future_finding_count))
        self.excluded_future_evaluation_count = max(0, int(self.excluded_future_evaluation_count))
        self.contamination_free = bool(self.contamination_free)
        self.stable_benchmark = bool(self.stable_benchmark)
        if not self.canonical_score_components:
            self.canonical_score_components = _suite_canonical_score_components(self.family_summaries)
        else:
            self.canonical_score_components = {
                str(key): round(float(value), 6 if key != "market_baseline_delta_bps" else 2)
                for key, value in self.canonical_score_components.items()
            }
        if not self.benchmark_scope_hash:
            self.benchmark_scope_hash = _comparison_scope_hash(
                {
                    "market_id": self.market_id,
                    "cutoff_at": self.cutoff_at.isoformat(),
                    "evidence_set": self.evidence_set.content_hash,
                    "research_report": self.research_report.content_hash,
                    "family_hashes": [summary.content_hash for summary in self.family_summaries],
                    "model_version_hashes": [report.content_hash for report in self.model_version_comparisons],
                    "baseline_hashes": [report.content_hash for report in self.baseline_comparisons],
                }
            )
        if not self.content_hash:
            self.content_hash = _comparison_scope_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "suite_id": "",
                    "content_hash": "",
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "AsOfBenchmarkSuite":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _suite_canonical_score_components(family_summaries: Sequence[BenchmarkFamilySummary]) -> dict[str, float]:
    if not family_summaries:
        return {
            "brier_score": 0.0,
            "log_loss": 0.0,
            "ece": 0.0,
            "sharpness": 0.0,
            "abstention_coverage": 0.0,
            "market_baseline_probability": 0.0,
            "market_baseline_delta": 0.0,
            "market_baseline_delta_bps": 0.0,
            "family_count": 0.0,
            "record_count": 0.0,
        }
    total_records = sum(summary.record_count for summary in family_summaries)

    def _weighted(selector: str, default: float = 0.0) -> float:
        return _weighted_mean([(getattr(summary, selector), summary.record_count) for summary in family_summaries], default=default)

    return {
        "brier_score": round(_weighted("mean_brier_score"), 6),
        "log_loss": round(_weighted("mean_log_loss"), 6),
        "ece": round(_weighted("ece"), 6),
        "sharpness": round(_weighted("sharpness"), 6),
        "abstention_coverage": round(_weighted("abstention_coverage"), 6),
        "market_baseline_probability": round(_weighted("mean_market_baseline_probability"), 6),
        "market_baseline_delta": round(_weighted("mean_market_baseline_delta"), 6),
        "market_baseline_delta_bps": round(_weighted("mean_market_baseline_delta_bps"), 2),
        "family_count": float(len(family_summaries)),
        "record_count": float(total_records),
    }


def _build_family_summary(
    records: Sequence[ForecastEvaluationRecord],
    *,
    family_label: str,
    market_family: str,
    horizon_bucket: str,
    as_of: datetime,
    calibration_method: str = "ece-10bin",
    metadata: dict[str, Any] | None = None,
) -> tuple[BenchmarkFamilySummary, CalibrationSnapshot]:
    model_family = records[0].model_family if records else family_label
    snapshot = CalibrationSnapshot.from_records_as_of(
        records,
        as_of=as_of,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        calibration_method=calibration_method,
        metadata={
            "family_label": family_label,
            "family_role": _family_role_from_label(family_label),
            **dict(metadata or {}),
        },
    )
    summary = BenchmarkFamilySummary(
        family_label=family_label,
        family_role=_family_role_from_label(family_label),
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        record_count=snapshot.record_count,
        as_of_cutoff_at=as_of,
        contamination_free=True,
        mean_brier_score=snapshot.mean_brier_score,
        mean_log_loss=snapshot.mean_log_loss,
        ece=snapshot.ece,
        sharpness=snapshot.sharpness,
        abstention_coverage=snapshot.abstention_coverage,
        mean_market_baseline_probability=snapshot.mean_market_baseline_probability,
        mean_market_baseline_delta=snapshot.mean_market_baseline_delta,
        mean_market_baseline_delta_bps=snapshot.mean_market_baseline_delta_bps,
        canonical_score_components={
            "brier_score": snapshot.mean_brier_score,
            "log_loss": snapshot.mean_log_loss,
            "ece": snapshot.ece,
            "sharpness": snapshot.sharpness,
            "abstention_coverage": snapshot.abstention_coverage,
            "market_baseline_probability": snapshot.mean_market_baseline_probability,
            "market_baseline_delta": snapshot.mean_market_baseline_delta,
            "market_baseline_delta_bps": snapshot.mean_market_baseline_delta_bps,
        },
        metadata={
            **dict(metadata or {}),
            "snapshot_id": snapshot.snapshot_id,
            "content_hash": snapshot.content_hash,
            "evaluation_refs": snapshot.evaluation_refs,
            "contamination_free": True,
        },
    )
    return summary, snapshot


def build_as_of_benchmark_suite(
    findings: Sequence[ResearchFinding | EvidencePacket | Mapping[str, Any] | str],
    forecast_evaluations: Sequence[ForecastEvaluationRecord] | None = None,
    *,
    market_id: str,
    as_of: datetime,
    venue: VenueName = VenueName.polymarket,
    run_id: str | None = None,
    researcher: BaseRateResearcher | None = None,
    market_family: str = "generic",
    horizon_bucket: str = "all",
    family_labels: Mapping[str, str] | None = None,
    external_baselines: Mapping[str, float] | None = None,
    calibration_method: str = "ece-10bin",
    metadata: dict[str, Any] | None = None,
) -> AsOfBenchmarkSuite:
    cutoff = _utc_datetime(as_of) or _utc_now()
    ordered_findings = sorted(list(findings), key=_canonical_benchmark_key)
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
        },
        evidence_packets=evidence_packets,
        metadata={
            "benchmark": True,
            "selected_count": len(evidence_packets),
            "discarded_future_count": discarded_future_count,
            "contamination_free": True,
        },
    )
    report = ResearchReport.from_evidence_set(
        evidence_set,
        evidence_packets,
        metadata={
            "benchmark": True,
            "contamination_free": True,
            "run_id": run_id,
            "as_of_cutoff_at": cutoff.isoformat(),
            "selected_count": len(evidence_packets),
            "discarded_future_count": discarded_future_count,
        },
    )
    all_records = list(forecast_evaluations or [])
    valid_records = [
        record
        for record in all_records
        if _record_cutoff(record) is not None
    ]
    records = [
        record
        for record in valid_records
        if _record_cutoff(record) <= cutoff
    ]
    excluded_invalid_evaluation_count = max(0, len(all_records) - len(valid_records))
    excluded_future_evaluation_count = max(0, len(valid_records) - len(records))
    family_labels = dict(family_labels or {})
    grouped_records: dict[str, list[ForecastEvaluationRecord]] = defaultdict(list)
    for record in records:
        grouped_records[record.model_family].append(record)
    family_summaries: list[BenchmarkFamilySummary] = []
    family_snapshots: dict[str, CalibrationSnapshot] = {}
    for model_family in sorted(grouped_records.keys()):
        label = family_labels.get(model_family, model_family)
        summary, snapshot = _build_family_summary(
            grouped_records[model_family],
            family_label=label,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            as_of=cutoff,
            calibration_method=calibration_method,
            metadata={
                "model_family": model_family,
                "family_role": _family_role_from_label(label),
                "contamination_free": True,
            },
        )
        family_summaries.append(summary)
        family_snapshots[model_family] = snapshot

    market_only_family = next(
        (model_family for model_family, label in family_labels.items() if _family_role_from_label(label) == "market-only"),
        None,
    )
    if market_only_family is None:
        market_only_family = next(
            (
                model_family
                for model_family in sorted(grouped_records.keys())
                if _family_role_from_label(family_labels.get(model_family, model_family)) == "market-only"
            ),
            None,
        )
    market_only_baseline_probability = (
        family_snapshots[market_only_family].mean_market_baseline_probability
        if market_only_family in family_snapshots
        else 0.5
    )

    model_version_comparisons: list[ForecastVersionComparisonReport] = []
    model_families = sorted(grouped_records.keys())
    for index, left_model_family in enumerate(model_families):
        for right_model_family in model_families[index + 1 :]:
            model_version_comparisons.append(
                build_model_version_comparison_report(
                    records,
                    left_model_family=left_model_family,
                    right_model_family=right_model_family,
                    market_family=market_family,
                    horizon_bucket=horizon_bucket,
                    as_of=cutoff,
                    metadata={
                        "benchmark": True,
                        "contamination_free": True,
                        "left_family_label": family_labels.get(left_model_family, left_model_family),
                        "right_family_label": family_labels.get(right_model_family, right_model_family),
                    },
                )
            )

    baseline_comparisons: list[ForecastBaselineComparisonReport] = []
    for model_family in model_families:
        baseline_label = "market-only" if market_only_family and model_family != market_only_family else "simple_0.5"
        baseline_probability = market_only_baseline_probability if baseline_label == "market-only" else 0.5
        baseline_comparisons.append(
            build_baseline_comparison_report(
                records,
                model_family=model_family,
                market_family=market_family,
                horizon_bucket=horizon_bucket,
                baseline_probability=baseline_probability,
                baseline_label=baseline_label,
                as_of=cutoff,
                metadata={
                    "benchmark": True,
                    "contamination_free": True,
                    "family_label": family_labels.get(model_family, model_family),
                    "family_role": _family_role_from_label(family_labels.get(model_family, model_family)),
                },
            )
        )

    gate_1_comparator_manifest = _gate_1_comparator_manifest(family_summaries, market_only_family=market_only_family)
    present_gate_1_categories = {
        entry["gate_1_category"]
        for entry in gate_1_comparator_manifest
        if entry["gate_1_category"] in {"market-only", "forecast-only", "DecisionPacket-assisted", "ensemble"}
    }
    required_gate_1_categories = ["market-only", "forecast-only", "DecisionPacket-assisted", "ensemble"]
    gate_1_blockers = [
        f"missing_gate_1_category:{category}"
        for category in required_gate_1_categories
        if category not in present_gate_1_categories
    ]
    gate_1_promotion_ready = not gate_1_blockers and market_only_family is not None

    if external_baselines:
        for baseline_label, baseline_probability in external_baselines.items():
            baseline_comparisons.append(
                build_baseline_comparison_report(
                    records,
                    model_family=model_families[0] if model_families else "baseline",
                    market_family=market_family,
                    horizon_bucket=horizon_bucket,
                    baseline_probability=baseline_probability,
                    baseline_label=str(baseline_label),
                    as_of=cutoff,
                    metadata={
                        "benchmark": True,
                        "contamination_free": True,
                        "external_reference": True,
                    },
                )
            )

    return AsOfBenchmarkSuite(
        market_id=market_id,
        cutoff_at=cutoff,
        evidence_set=evidence_set,
        research_report=report,
        calibration_snapshot=family_snapshots.get(market_only_family) if market_only_family else None,
        family_summaries=family_summaries,
        model_version_comparisons=model_version_comparisons,
        baseline_comparisons=baseline_comparisons,
        family_labels=family_labels,
        canonical_score_components=_suite_canonical_score_components(family_summaries),
        excluded_future_finding_count=discarded_future_count,
        excluded_future_evaluation_count=excluded_future_evaluation_count,
        contamination_free=True,
        stable_benchmark=True,
        metadata={
            **dict(metadata or {}),
            "benchmark": True,
            "contamination_free": True,
            "as_of_cutoff_at": cutoff.isoformat(),
            "selected_finding_count": len(evidence_packets),
            "excluded_future_finding_count": discarded_future_count,
            "selected_evaluation_count": len(records),
            "excluded_future_evaluation_count": excluded_future_evaluation_count,
            "excluded_invalid_evaluation_count": excluded_invalid_evaluation_count,
            "family_labels": family_labels,
            "family_count": len(family_summaries),
            "market_only_family": market_only_family,
            "market_only_baseline_probability": market_only_baseline_probability,
            "gate_1_required_categories": required_gate_1_categories,
            "gate_1_present_categories": sorted(present_gate_1_categories),
            "gate_1_promotion_ready": gate_1_promotion_ready,
            "gate_1_promotion_blockers": gate_1_blockers,
            "gate_1_comparator_manifest": gate_1_comparator_manifest,
            "gate_1_comparator_count": len(gate_1_comparator_manifest),
            "gate_1_promotion_evidence": "out_of_sample_contamination_free",
        },
    )


class ForecastEvaluationStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.paths = PredictionMarketPaths(base_dir) if base_dir is not None else default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "forecast_evaluation"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def records_dir(self) -> Path:
        return self.root / "records"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "snapshots"

    @property
    def evidence_sets_dir(self) -> Path:
        return self.root / "evidence_sets"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def priors_path(self) -> Path:
        return self.root / "base_rates.json"

    def ensure_layout(self) -> None:
        for directory in [self.root, self.records_dir, self.snapshots_dir, self.evidence_sets_dir, self.reports_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def save_record(self, record: ForecastEvaluationRecord) -> Path:
        self.ensure_layout()
        return save_json(self.records_dir / f"{record.evaluation_id}.json", record)

    def list_records(self) -> list[ForecastEvaluationRecord]:
        self.ensure_layout()
        records = [
            ForecastEvaluationRecord.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.records_dir.glob("*.json"))
        ]
        records.sort(key=lambda item: (item.cutoff_at, item.evaluation_id))
        return records

    def save_snapshot(self, snapshot: CalibrationSnapshot) -> Path:
        self.ensure_layout()
        return save_json(self.snapshots_dir / f"{snapshot.snapshot_id}.json", snapshot)

    def save_evidence_set(self, evidence_set: AsOfEvidenceSet) -> Path:
        self.ensure_layout()
        return save_json(self.evidence_sets_dir / f"{evidence_set.evidence_set_id}.json", evidence_set)

    def save_report(self, report: ResearchReport) -> Path:
        self.ensure_layout()
        return save_json(self.reports_dir / f"{report.report_id}.json", report)

    def load_prior_table(self) -> dict[str, Any]:
        if not self.priors_path.exists():
            return {}
        raw = load_json(self.priors_path)
        return raw if isinstance(raw, dict) else {}

    def save_prior_table(self, payload: dict[str, Any]) -> Path:
        self.ensure_layout()
        return save_json(self.priors_path, payload)


@dataclass
class BaseRateResearcher:
    base_dir: str | Path | None = None

    def __post_init__(self) -> None:
        self.store = ForecastEvaluationStore(self.base_dir)

    def fit(self, records: Sequence[ForecastEvaluationRecord]) -> dict[str, float]:
        grouped: dict[str, list[ForecastEvaluationRecord]] = {}
        for record in records:
            grouped.setdefault(record.market_family, []).append(record)
        priors: dict[str, float] = {}
        for market_family, family_records in grouped.items():
            resolved = [1.0 if record.resolved_outcome else 0.0 for record in family_records if not record.abstain_flag]
            priors[market_family] = round(_safe_mean(resolved, default=0.5), 6)
        self.store.save_prior_table(priors)
        return priors

    def estimate(self, market_family: str, *, fallback: float = 0.5) -> float:
        priors = self.store.load_prior_table()
        value = priors.get(market_family)
        if value is None:
            return _clamp_probability(fallback)
        return _clamp_probability(value)


@dataclass
class ForecastEvaluationHarness:
    base_dir: str | Path | None = None

    def __post_init__(self) -> None:
        self.store = ForecastEvaluationStore(self.base_dir)
        self.base_rate_researcher = BaseRateResearcher(self.base_dir)

    def evaluate_forecast(
        self,
        forecast: ForecastPacket,
        *,
        question_id: str,
        resolved_outcome: bool,
        market_baseline_probability: float = 0.5,
        abstain_flag: bool = False,
        market_family: str = "unknown",
        horizon_bucket: str = "unknown",
        evidence_packets: Sequence[EvidencePacket] | None = None,
        cutoff_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ForecastEvaluationRecord:
        record = ForecastEvaluationRecord.evaluate(
            question_id=question_id,
            market_id=forecast.market_id,
            venue=forecast.venue,
            cutoff_at=cutoff_at or forecast.created_at,
            forecast_probability=forecast.fair_probability,
            resolved_outcome=resolved_outcome,
            market_baseline_probability=market_baseline_probability,
            abstain_flag=abstain_flag,
            model_family=forecast.model_used,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            forecast_ref=forecast.forecast_id,
            resolution_policy_ref=forecast.resolution_policy_id,
            evidence_refs=[*forecast.evidence_refs, *(packet.evidence_id for packet in evidence_packets or [])],
            metadata={
                "forecast_metadata": dict(forecast.metadata),
                "extra_metadata": dict(metadata or {}),
            },
        )
        self.store.save_record(record)
        return record

    def build_as_of_evidence_set(
        self,
        evidence_packets: Sequence[EvidencePacket],
        *,
        market_id: str,
        cutoff_at: datetime,
        retrieval_policy: str = "as_of",
        metadata: dict[str, Any] | None = None,
    ) -> AsOfEvidenceSet:
        evidence_set = AsOfEvidenceSet.from_evidence(
            evidence_packets,
            market_id=market_id,
            cutoff_at=cutoff_at,
            retrieval_policy=retrieval_policy,
            metadata=metadata,
        )
        self.store.save_evidence_set(evidence_set)
        return evidence_set

    def build_research_report(
        self,
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
    ) -> ResearchReport:
        report = ResearchReport.from_evidence_set(
            evidence_set,
            evidence_packets,
            base_rates=base_rates,
            facts=facts,
            theses=theses,
            objections=objections,
            key_factors=key_factors,
            counterarguments=counterarguments,
            open_questions=open_questions,
            metadata=metadata,
        )
        self.store.save_report(report)
        return report

    def summarize_calibration(
        self,
        records: Sequence[ForecastEvaluationRecord] | None = None,
        *,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        calibration_method: str = "ece-10bin",
        metadata: dict[str, Any] | None = None,
    ) -> CalibrationSnapshot:
        snapshot = CalibrationSnapshot.from_records(
            list(records or self.store.list_records()),
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            calibration_method=calibration_method,
            metadata=metadata,
        )
        self.store.save_snapshot(snapshot)
        return snapshot

    def summarize_calibration_as_of(
        self,
        records: Sequence[ForecastEvaluationRecord] | None = None,
        *,
        as_of: datetime,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        calibration_method: str = "ece-10bin",
        metadata: dict[str, Any] | None = None,
    ) -> CalibrationSnapshot:
        snapshot = CalibrationSnapshot.from_records_as_of(
            list(records or self.store.list_records()),
            as_of=as_of,
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            calibration_method=calibration_method,
            metadata=metadata,
        )
        self.store.save_snapshot(snapshot)
        return snapshot

    def fit_base_rates(self, records: Sequence[ForecastEvaluationRecord] | None = None) -> dict[str, float]:
        return self.base_rate_researcher.fit(list(records or self.store.list_records()))

    def compare_model_versions(
        self,
        records: Sequence[ForecastEvaluationRecord] | None = None,
        *,
        left_model_family: str,
        right_model_family: str,
        market_family: str,
        horizon_bucket: str,
        as_of: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ForecastVersionComparisonReport:
        return build_model_version_comparison_report(
            list(records or self.store.list_records()),
            left_model_family=left_model_family,
            right_model_family=right_model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            as_of=as_of,
            metadata=metadata,
        )

    def compare_against_baseline(
        self,
        records: Sequence[ForecastEvaluationRecord] | None = None,
        *,
        model_family: str,
        market_family: str,
        horizon_bucket: str,
        baseline_probability: float = 0.5,
        baseline_label: str = "simple_baseline",
        as_of: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ForecastBaselineComparisonReport:
        return build_baseline_comparison_report(
            list(records or self.store.list_records()),
            model_family=model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            baseline_probability=baseline_probability,
            baseline_label=baseline_label,
            as_of=as_of,
            metadata=metadata,
        )

    def compare_forecast_only_vs_enriched(
        self,
        records: Sequence[ForecastEvaluationRecord] | None = None,
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
            list(records or self.store.list_records()),
            forecast_only_model_family=forecast_only_model_family,
            enriched_model_family=enriched_model_family,
            market_family=market_family,
            horizon_bucket=horizon_bucket,
            as_of=as_of,
            forecast_only_family_role=forecast_only_family_role,
            enriched_family_role=enriched_family_role,
            metadata=metadata,
        )


def build_as_of_calibration_snapshot(
    records: Sequence[ForecastEvaluationRecord],
    *,
    as_of: datetime,
    model_family: str,
    market_family: str,
    horizon_bucket: str,
    calibration_method: str = "ece-10bin",
    metadata: dict[str, Any] | None = None,
) -> CalibrationSnapshot:
    return CalibrationSnapshot.from_records_as_of(
        records,
        as_of=as_of,
        model_family=model_family,
        market_family=market_family,
        horizon_bucket=horizon_bucket,
        calibration_method=calibration_method,
        metadata=metadata,
    )


__all__ = [
    "AbstentionQualityReport",
    "AsOfEvidenceSet",
    "AsOfBenchmarkSuite",
    "BaseRateResearcher",
    "BenchmarkFamilySummary",
    "CalibrationBucketSummary",
    "CalibrationCurveReport",
    "CalibrationSnapshot",
    "CategoryHorizonPerformanceReport",
    "CategoryHorizonPerformanceSummary",
    "ForecastBaselineComparisonPair",
    "ForecastBaselineComparisonReport",
    "ForecastEvaluationHarness",
    "ForecastEvaluationRecord",
    "ForecastEvaluationStore",
    "ForecastVersionComparisonPair",
    "ForecastVersionComparisonReport",
    "ForecastUpliftComparisonReport",
    "ResearchReport",
    "build_abstention_quality_report",
    "build_as_of_calibration_snapshot",
    "build_as_of_benchmark_suite",
    "build_calibration_curve_report",
    "build_category_horizon_performance_report",
    "build_baseline_comparison_report",
    "build_forecast_uplift_comparison_report",
    "build_model_version_comparison_report",
]
