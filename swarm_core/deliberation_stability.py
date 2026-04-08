from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DeliberationStabilitySample(BaseModel):
    sample_id: str = Field(default_factory=lambda: f"sample_{uuid4().hex[:12]}")
    score: float
    passed: bool | None = None
    runtime_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliberationStabilitySummary(BaseModel):
    sample_count: int
    mean_score: float
    std_dev: float
    min_score: float
    max_score: float
    score_spread: float
    coefficient_of_variation: float
    metric_name: str = "overall"
    comparison_key: str = ""
    sample_run_ids: list[str] = Field(default_factory=list)
    minimum_sample_count: int = 2
    sample_sufficient: bool = False
    dispersion_gate_passed: bool = False
    assessment_flags: list[str] = Field(default_factory=list)
    threshold: float = 0.10
    stable: bool
    notes: str = ""
    samples: list[DeliberationStabilitySample] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_scores(
        cls,
        scores: list[float],
        *,
        threshold: float = 0.10,
        minimum_sample_count: int = 2,
        notes: str = "",
        metric_name: str = "overall",
        comparison_key: str | None = None,
        sample_run_ids: list[str] | None = None,
        sample_metadata: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DeliberationStabilitySummary":
        if not scores:
            raise ValueError("scores must not be empty")

        normalized_metric_name = _normalize_metric_name(metric_name)
        sample_count = len(scores)
        normalized_sample_run_ids = _normalize_sample_run_ids(sample_run_ids, sample_count)
        normalized_sample_metadata = _normalize_sample_metadata(sample_metadata, sample_count)
        resolved_comparison_key = _build_comparison_key(
            metric_name=normalized_metric_name,
            threshold=threshold,
            minimum_sample_count=minimum_sample_count,
            comparison_key=comparison_key,
            metadata=metadata,
        )
        mean_score = mean(scores)
        std_dev = pstdev(scores) if sample_count > 1 else 0.0
        min_score = min(scores)
        max_score = max(scores)
        score_spread = max_score - min_score
        coefficient_of_variation = 0.0 if mean_score == 0 else abs(std_dev / mean_score)
        sample_sufficient = sample_count >= max(1, int(minimum_sample_count))
        dispersion_gate_passed = std_dev <= threshold and score_spread <= (threshold * 2)
        stable = sample_sufficient and dispersion_gate_passed

        assessment_flags: list[str] = []
        if not sample_sufficient:
            assessment_flags.append(f"insufficient_samples:{sample_count}/{max(1, int(minimum_sample_count))}")
        if std_dev > threshold:
            assessment_flags.append(f"std_dev_exceeds_threshold:{std_dev:.4f}>{threshold:.4f}")
        if score_spread > (threshold * 2):
            assessment_flags.append(f"score_spread_exceeds_threshold:{score_spread:.4f}>{(threshold * 2):.4f}")

        extra_notes: list[str] = [
            f"metric_name={normalized_metric_name}",
            f"comparison_key={resolved_comparison_key}",
            f"sample_sufficient={sample_sufficient}",
            f"dispersion_gate_passed={dispersion_gate_passed}",
            f"min_samples={max(1, int(minimum_sample_count))}",
        ]
        if assessment_flags:
            extra_notes.append("flags=" + ",".join(assessment_flags))
        merged_notes = notes.strip()
        if extra_notes:
            merged_notes = f"{merged_notes}; {'; '.join(extra_notes)}" if merged_notes else "; ".join(extra_notes)

        samples: list[DeliberationStabilitySample] = []
        for index, score in enumerate(scores):
            sample_metadata_item = dict(normalized_sample_metadata[index]) if normalized_sample_metadata is not None else {}
            sample_metadata_item.setdefault("metric_name", normalized_metric_name)
            sample_metadata_item.setdefault("comparison_key", resolved_comparison_key)
            if normalized_sample_run_ids:
                sample_metadata_item.setdefault("sample_run_id", normalized_sample_run_ids[index])
            sample_metadata_item.setdefault("sample_index", index)
            samples.append(
                DeliberationStabilitySample(
                    score=score,
                    runtime_run_id=normalized_sample_run_ids[index] if normalized_sample_run_ids else None,
                    metadata=sample_metadata_item,
                )
            )

        return cls(
            sample_count=sample_count,
            mean_score=mean_score,
            std_dev=std_dev,
            min_score=min_score,
            max_score=max_score,
            score_spread=score_spread,
            coefficient_of_variation=coefficient_of_variation,
            metric_name=normalized_metric_name,
            comparison_key=resolved_comparison_key,
            sample_run_ids=normalized_sample_run_ids,
            minimum_sample_count=max(1, int(minimum_sample_count)),
            sample_sufficient=sample_sufficient,
            dispersion_gate_passed=dispersion_gate_passed,
            assessment_flags=assessment_flags,
            threshold=threshold,
            stable=stable,
            notes=merged_notes,
            samples=samples,
            metadata={
                **(metadata or {}),
                "metric_name": normalized_metric_name,
                "comparison_key": resolved_comparison_key,
                "sample_run_ids": normalized_sample_run_ids,
                "sample_count": sample_count,
                "minimum_sample_count": max(1, int(minimum_sample_count)),
                "sample_sufficient": sample_sufficient,
                "dispersion_gate_passed": dispersion_gate_passed,
                "assessment_flags": assessment_flags,
                "stable": stable,
            },
        )

    @classmethod
    def from_samples(
        cls,
        samples: list[DeliberationStabilitySample],
        *,
        threshold: float = 0.10,
        minimum_sample_count: int = 2,
        notes: str = "",
        metric_name: str = "overall",
        comparison_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DeliberationStabilitySummary":
        sample_run_ids = [sample.runtime_run_id or sample.sample_id for sample in samples]
        return cls.from_scores(
            [sample.score for sample in samples],
            threshold=threshold,
            minimum_sample_count=minimum_sample_count,
            notes=notes,
            metric_name=metric_name,
            comparison_key=comparison_key,
            sample_run_ids=sample_run_ids,
            sample_metadata=[sample.metadata for sample in samples],
            metadata={**(metadata or {}), "sample_ids": [sample.sample_id for sample in samples]},
        )


def _normalize_metric_name(metric_name: str | None) -> str:
    normalized = (metric_name or "").strip()
    return normalized or "overall"


def _normalize_sample_run_ids(sample_run_ids: list[str] | None, sample_count: int) -> list[str]:
    if sample_run_ids is None:
        return []
    normalized = [str(sample_run_id).strip() for sample_run_id in sample_run_ids if str(sample_run_id).strip()]
    if len(normalized) != sample_count:
        raise ValueError("sample_run_ids must match the number of scores when provided")
    return normalized


def _normalize_sample_metadata(
    sample_metadata: list[dict[str, Any]] | None,
    sample_count: int,
) -> list[dict[str, Any]] | None:
    if sample_metadata is None:
        return None
    if len(sample_metadata) != sample_count:
        raise ValueError("sample_metadata must match the number of scores when provided")
    return [dict(item) for item in sample_metadata]


def _build_comparison_key(
    *,
    metric_name: str,
    threshold: float,
    minimum_sample_count: int,
    comparison_key: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    explicit_value = comparison_key if comparison_key is not None else (metadata or {}).get("comparison_key")
    explicit_key = str(explicit_value).strip() if explicit_value is not None else ""
    if explicit_key:
        return explicit_key

    base_parts = [
        f"metric={metric_name}",
        f"threshold={threshold:.4f}",
        f"minimum_sample_count={max(1, int(minimum_sample_count))}",
    ]
    runtime_tag = (metadata or {}).get("runtime_used") or (metadata or {}).get("runtime_requested")
    engine_tag = (metadata or {}).get("engine_used") or (metadata or {}).get("engine_requested")
    mode_tag = (metadata or {}).get("mode")
    if mode_tag:
        base_parts.append(f"mode={mode_tag}")
    if runtime_tag:
        base_parts.append(f"runtime={runtime_tag}")
    if engine_tag:
        base_parts.append(f"engine={engine_tag}")
    return "|".join(base_parts)
