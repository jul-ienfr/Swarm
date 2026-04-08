from __future__ import annotations

import json
import math
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .advisor import MarketAdvisor
from .forecast_evaluation import CalibrationSnapshot
from .forecast_evaluation import (
    AbstentionQualityReport,
    CalibrationCurveReport,
    CategoryHorizonPerformanceReport,
    build_abstention_quality_report,
    build_calibration_curve_report,
    build_category_horizon_performance_report,
)
from .models import DecisionAction, ForecastPacket, ReplayReport, RunManifest, VenueName, _stable_content_hash
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .replay import MarketReplayRunner
from .storage import load_json, save_json


def _clamp_probability(value: float) -> float:
    return max(1e-9, min(1.0 - 1e-9, float(value)))


def _safe_mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _is_abstention(score: "CalibrationScore") -> bool:
    forecast = score.forecast
    if forecast is None:
        return False
    return forecast.recommendation_action in {
        DecisionAction.no_trade,
        DecisionAction.wait,
        DecisionAction.manual_review,
    }


def _score_metadata(score: "CalibrationScore") -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    metadata.update(dict(score.manifest.metadata) if score.manifest is not None else {})
    metadata.update(dict(score.manifest.inputs) if score.manifest is not None else {})
    if score.forecast is not None:
        metadata.update(dict(score.forecast.metadata))
    metadata.update(dict(score.metadata))
    return metadata


def _score_market_family(score: "CalibrationScore") -> str:
    metadata = _score_metadata(score)
    for key in ("market_family", "category", "market_category", "theme", "sector", "segment"):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return str(score.venue.value if hasattr(score.venue, "value") else score.venue).strip() or "unknown"


def _score_category(score: "CalibrationScore") -> str:
    metadata = _score_metadata(score)
    for key in ("category", "market_category", "theme", "sector", "segment"):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return _score_market_family(score)


def _score_horizon_bucket(score: "CalibrationScore") -> str:
    metadata = _score_metadata(score)
    for key in ("horizon_bucket", "horizon", "time_horizon", "window_bucket"):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return "unknown"


def _score_ece_bucket(probability: float, buckets: int = 10) -> str:
    clamped = max(0.0, min(1.0 - 1e-9, float(probability)))
    index = min(max(0, int(clamped * buckets)), max(0, buckets - 1))
    lower = index / buckets
    upper = (index + 1) / buckets
    return f"{lower:.1f}-{upper:.1f}"


def _score_record_payload(score: "CalibrationScore") -> dict[str, Any]:
    probability_yes = _clamp_probability(score.probability_yes)
    outcome_yes = bool(score.outcome_yes)
    metadata = _score_metadata(score)
    forecast_market_implied = (
        score.forecast.market_implied_probability if score.forecast is not None else probability_yes
    )
    return {
        "evaluation_id": score.run_id,
        "question_id": score.market_id,
        "market_id": score.market_id,
        "forecast_probability": probability_yes,
        "market_baseline_probability": _clamp_probability(forecast_market_implied),
        "resolved_outcome": outcome_yes,
        "brier_score": round(float(score.brier_score), 6),
        "log_loss": round(float(score.log_loss), 6),
        "ece_bucket": _score_ece_bucket(probability_yes),
        "abstain_flag": _is_abstention(score),
        "model_family": _score_model_family(score),
        "market_family": _score_market_family(score),
        "horizon_bucket": _score_horizon_bucket(score),
        "market_baseline_delta": round(probability_yes - _clamp_probability(forecast_market_implied), 6),
        "market_baseline_delta_bps": round(
            (probability_yes - _clamp_probability(forecast_market_implied)) * 10000.0,
            2,
        ),
        "cutoff_at": score.forecast.forecast_ts if score.forecast is not None else (
            score.manifest.updated_at if score.manifest is not None else datetime.now(timezone.utc)
        ),
        "metadata": metadata,
    }


def _score_model_family(score: "CalibrationScore") -> str:
    metadata = _score_metadata(score)
    for key in ("model_family", "engine_used", "model_used"):
        value = metadata.get(key)
        if value is None and score.forecast is not None:
            value = getattr(score.forecast, key, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    if score.forecast is not None:
        text = str(score.forecast.model_used).strip()
        if text:
            return text
    return "unknown"


class CalibrationLabel(BaseModel):
    schema_version: str = "v1"
    run_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    outcome_yes: bool
    source: str = "manual"
    note: str = ""
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalibrationScore(BaseModel):
    schema_version: str = "v1"
    run_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    probability_yes: float
    outcome_yes: bool
    hit: bool = False
    brier_score: float
    log_loss: float
    closing_line_drift_bps: float = 0.0
    edge_after_fees_bps: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)
    replay_consistent: bool | None = None
    replay_report: ReplayReport | None = None
    forecast: ForecastPacket | None = None
    manifest: RunManifest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def postmortem(self) -> "CalibrationPostmortem":
        notes = []
        if self.hit:
            notes.append("directionally_correct")
        else:
            notes.append("directionally_incorrect")
        if self.replay_consistent is False:
            notes.append("replay_inconsistent")
        if self.closing_line_drift_bps:
            notes.append("market_line_and_model_diverged")
        if not self.score_components:
            self.score_components = {
                "brier_score": round(float(self.brier_score), 6),
                "log_loss": round(float(self.log_loss), 6),
                "closing_line_drift_bps": round(float(self.closing_line_drift_bps), 2),
                "edge_after_fees_bps": round(float(self.edge_after_fees_bps), 2),
                "hit": 1.0 if self.hit else 0.0,
            }
        else:
            self.score_components = {
                str(key): round(float(value), 6)
                for key, value in self.score_components.items()
            }
        return CalibrationPostmortem(
            run_id=self.run_id,
            market_id=self.market_id,
            venue=self.venue,
            probability_yes=self.probability_yes,
            outcome_yes=self.outcome_yes,
            hit=self.hit,
            brier_score=self.brier_score,
            log_loss=self.log_loss,
            closing_line_drift_bps=self.closing_line_drift_bps,
            edge_after_fees_bps=self.edge_after_fees_bps,
            replay_consistent=self.replay_consistent,
            recommendation="keep" if self.hit and self.edge_after_fees_bps >= 0 else "review",
            notes=notes,
            metadata=dict(self.metadata),
        )


class CalibrationPostmortem(BaseModel):
    schema_version: str = "v1"
    postmortem_id: str = Field(default_factory=lambda: f"calpm_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName = VenueName.polymarket
    probability_yes: float
    outcome_yes: bool
    hit: bool = False
    brier_score: float = 0.0
    log_loss: float = 0.0
    closing_line_drift_bps: float = 0.0
    edge_after_fees_bps: float = 0.0
    replay_consistent: bool | None = None
    recommendation: str = "review"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalibrationSegmentSummary(BaseModel):
    schema_version: str = "v1"
    category: str = "unknown"
    horizon_bucket: str = "unknown"
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    mean_probability_yes: float = 0.0
    mean_outcome_yes: float = 0.0
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    mean_closing_line_drift_bps: float = 0.0
    mean_abs_closing_line_drift_bps: float = 0.0
    mean_edge_after_fees_bps: float = 0.0
    mean_abs_edge_after_fees_bps: float = 0.0
    mean_hit_rate: float | None = None
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationSegmentSummary":
        self.category = str(self.category).strip() or "unknown"
        self.horizon_bucket = str(self.horizon_bucket).strip() or "unknown"
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.mean_probability_yes = _clamp_probability(self.mean_probability_yes)
        self.mean_outcome_yes = _clamp_probability(self.mean_outcome_yes)
        self.mean_brier_score = max(0.0, float(self.mean_brier_score))
        self.mean_log_loss = max(0.0, float(self.mean_log_loss))
        self.mean_closing_line_drift_bps = round(float(self.mean_closing_line_drift_bps), 2)
        self.mean_abs_closing_line_drift_bps = round(float(self.mean_abs_closing_line_drift_bps), 2)
        self.mean_edge_after_fees_bps = round(float(self.mean_edge_after_fees_bps), 2)
        self.mean_abs_edge_after_fees_bps = round(float(self.mean_abs_edge_after_fees_bps), 2)
        if self.mean_hit_rate is not None:
            self.mean_hit_rate = _clamp_probability(self.mean_hit_rate)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "content_hash": "",
                }
            )
        return self


class ClosingLineQualityReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"clq_{uuid4().hex[:12]}")
    record_count: int = 0
    active_count: int = 0
    abstain_count: int = 0
    segment_count: int = 0
    mean_closing_line_drift_bps: float = 0.0
    mean_abs_closing_line_drift_bps: float = 0.0
    mean_edge_after_fees_bps: float = 0.0
    mean_abs_edge_after_fees_bps: float = 0.0
    segments: list[CalibrationSegmentSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "ClosingLineQualityReport":
        self.record_count = max(0, int(self.record_count))
        self.active_count = max(0, int(self.active_count))
        self.abstain_count = max(0, int(self.abstain_count))
        self.segment_count = max(0, int(self.segment_count))
        self.mean_closing_line_drift_bps = round(float(self.mean_closing_line_drift_bps), 2)
        self.mean_abs_closing_line_drift_bps = round(float(self.mean_abs_closing_line_drift_bps), 2)
        self.mean_edge_after_fees_bps = round(float(self.mean_edge_after_fees_bps), 2)
        self.mean_abs_edge_after_fees_bps = round(float(self.mean_abs_edge_after_fees_bps), 2)
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
    def load(cls, path: str | Path) -> "ClosingLineQualityReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class CalibrationSummary(BaseModel):
    schema_version: str = "v1"
    count: int = 0
    mean_brier_score: float = 0.0
    mean_log_loss: float = 0.0
    mean_ece: float = 0.0
    mean_sharpness: float = 0.0
    mean_probability_yes: float = 0.0
    mean_outcome_yes: float = 0.0
    hit_rate: float | None = None
    abstention_coverage: float = 0.0
    mean_market_baseline_probability: float = 0.0
    mean_market_baseline_delta: float = 0.0
    mean_market_baseline_delta_bps: float = 0.0
    mean_closing_line_drift_bps: float = 0.0
    mean_abs_closing_line_drift_bps: float = 0.0
    mean_edge_after_fees_bps: float = 0.0
    replay_consistency_rate: float | None = None
    labels: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationSummary":
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "content_hash": "",
                }
            )
        return self


class CalibrationReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"calrpt_{uuid4().hex[:12]}")
    summary: CalibrationSummary
    scores: list[CalibrationScore] = Field(default_factory=list)
    postmortems: list[CalibrationPostmortem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "CalibrationReport":
        self.summary = self.summary._normalize()
        if not self.content_hash:
            self.content_hash = _stable_content_hash(
                {
                    **self.model_dump(mode="json", exclude_none=True),
                    "report_id": "",
                    "content_hash": "",
                    "summary": {
                        **self.summary.model_dump(mode="json", exclude_none=True),
                        "content_hash": "",
                    },
                }
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class CalibrationHistoryStore:
    def __init__(self, paths: PredictionMarketPaths | None = None) -> None:
        self.paths = paths or default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "calibration"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def labels_path(self) -> Path:
        return self.root / "labels.json"

    @property
    def scores_path(self) -> Path:
        return self.root / "scores.json"

    @property
    def snapshots_path(self) -> Path:
        return self.root / "snapshots"

    def load_labels(self) -> dict[str, CalibrationLabel]:
        if not self.labels_path.exists():
            return {}
        raw = json.loads(self.labels_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {run_id: CalibrationLabel.model_validate(payload) for run_id, payload in raw.items()}

    def save_labels(self, labels: dict[str, CalibrationLabel]) -> Path:
        payload = {run_id: label.model_dump(mode="json") for run_id, label in labels.items()}
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(self.root), encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
            tmp_path = Path(handle.name)
        tmp_path.replace(self.labels_path)
        return self.labels_path

    def load_scores(self) -> list[CalibrationScore]:
        if not self.scores_path.exists():
            return []
        raw = json.loads(self.scores_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [CalibrationScore.model_validate(item) for item in raw]

    def save_scores(self, scores: list[CalibrationScore]) -> Path:
        payload = [score.model_dump(mode="json") for score in scores]
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(self.root), encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
            tmp_path = Path(handle.name)
        tmp_path.replace(self.scores_path)
        return self.scores_path

    def record_label(self, label: CalibrationLabel) -> CalibrationLabel:
        labels = self.load_labels()
        labels[label.run_id] = label
        self.save_labels(labels)
        return label

    def get_label(self, run_id: str) -> CalibrationLabel | None:
        return self.load_labels().get(run_id)

    def append_score(self, score: CalibrationScore) -> CalibrationScore:
        scores = self.load_scores()
        scores = [item for item in scores if item.run_id != score.run_id] + [score]
        scores.sort(key=lambda item: item.run_id)
        self.save_scores(scores)
        return score

    def save_snapshot(self, snapshot: CalibrationSnapshot) -> Path:
        self.snapshots_path.mkdir(parents=True, exist_ok=True)
        return save_json(self.snapshots_path / f"{snapshot.snapshot_id}.json", snapshot)


@dataclass
class CalibrationLab:
    base_dir: str | Path | None = None
    replay_backend_mode: str = "surrogate"

    def __post_init__(self) -> None:
        self.paths = PredictionMarketPaths(self.base_dir) if self.base_dir is not None else default_prediction_market_paths()
        self.paths.ensure_layout()
        self.store = CalibrationHistoryStore(self.paths)
        self.advisor = MarketAdvisor(paths=self.paths, backend_mode=self.replay_backend_mode)
        self.replay_runner = MarketReplayRunner(advisor=self.advisor, paths=self.paths)

    def record_label(
        self,
        run_id: str,
        *,
        outcome_yes: bool,
        market_id: str,
        venue: VenueName = VenueName.polymarket,
        source: str = "manual",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CalibrationLabel:
        label = CalibrationLabel(
            run_id=run_id,
            market_id=market_id,
            venue=venue,
            outcome_yes=outcome_yes,
            source=source,
            note=note,
            created_at=_now_iso(),
            metadata=metadata or {},
        )
        return self.store.record_label(label)

    def score_run(
        self,
        run_id: str,
        *,
        outcome_yes: bool | None = None,
        replay: bool = True,
    ) -> CalibrationScore:
        manifest = self._load_manifest(run_id)
        forecast = self._load_forecast(run_id)
        label = self.store.get_label(run_id)
        resolved_outcome = outcome_yes
        if resolved_outcome is None and label is not None:
            resolved_outcome = label.outcome_yes
        if resolved_outcome is None:
            resolved_outcome = self._infer_outcome_from_manifest(manifest)
        if resolved_outcome is None:
            raise ValueError(f"No outcome label available for run_id={run_id!r}")

        probability_yes = _clamp_probability(forecast.probability_yes if forecast is not None else 0.5)
        brier_score = (probability_yes - float(resolved_outcome)) ** 2
        log_loss = -math.log(probability_yes if resolved_outcome else 1.0 - probability_yes)
        hit = (probability_yes >= 0.5) == bool(resolved_outcome)
        closing_line_drift_bps = 0.0
        edge_after_fees_bps = 0.0
        if forecast is not None:
            closing_line_drift_bps = round((forecast.fair_probability - forecast.market_implied_probability) * 10000.0, 2)
            edge_after_fees_bps = round(float(forecast.edge_after_fees_bps), 2)
        replay_report = self.replay_runner.replay(run_id) if replay else None
        replay_consistent = None if replay_report is None else (
            replay_report.same_forecast and replay_report.same_recommendation and replay_report.same_decision
        )

        score = CalibrationScore(
            run_id=run_id,
            market_id=manifest.market_id,
            venue=manifest.venue,
            probability_yes=probability_yes,
            outcome_yes=bool(resolved_outcome),
            hit=hit,
            brier_score=brier_score,
            log_loss=log_loss,
            closing_line_drift_bps=closing_line_drift_bps,
            edge_after_fees_bps=edge_after_fees_bps,
            replay_consistent=replay_consistent,
            replay_report=replay_report,
            forecast=forecast,
            manifest=manifest,
            score_components={
                "brier_score": round(brier_score, 6),
                "log_loss": round(log_loss, 6),
                "closing_line_drift_bps": round(closing_line_drift_bps, 2),
                "edge_after_fees_bps": round(edge_after_fees_bps, 2),
                "hit": 1.0 if hit else 0.0,
            },
            metadata={
                "label_source": None if label is None else label.source,
                "label_note": None if label is None else label.note,
                "hit": hit,
                "closing_line_drift_bps": closing_line_drift_bps,
                "edge_after_fees_bps": edge_after_fees_bps,
                "model_family": forecast.model_used if forecast is not None else None,
                "market_family": manifest.metadata.get("market_family") or manifest.inputs.get("market_family") or "unknown",
                "category": manifest.metadata.get("category")
                or manifest.inputs.get("category")
                or manifest.metadata.get("theme")
                or manifest.inputs.get("theme")
                or "unknown",
                "horizon_bucket": manifest.metadata.get("horizon_bucket")
                or manifest.inputs.get("horizon_bucket")
                or "unknown",
            },
        )
        self.store.append_score(score)
        return score

    def score_runs(self, run_ids: list[str], *, replay: bool = True) -> list[CalibrationScore]:
        return [self.score_run(run_id, replay=replay) for run_id in run_ids]

    def summarize(self, scores: list[CalibrationScore] | None = None) -> CalibrationSummary:
        items = scores if scores is not None else self.store.load_scores()
        if not items:
            return CalibrationSummary()._normalize()

        count = len(items)
        mean_brier_score = sum(item.brier_score for item in items) / count
        mean_log_loss = sum(item.log_loss for item in items) / count
        active_items = [item for item in items if not _is_abstention(item)]
        abstention_coverage = len(active_items) / count
        active_probabilities = [item.probability_yes for item in active_items]
        market_baseline_probabilities = [
            float(item.forecast.market_implied_probability if item.forecast is not None else item.probability_yes)
            for item in items
        ]
        market_baseline_deltas = [
            float(item.probability_yes - baseline)
            for item, baseline in zip(items, market_baseline_probabilities, strict=True)
        ]
        mean_ece = 0.0
        mean_sharpness = 0.0
        if active_items:
            buckets: dict[str, list[CalibrationScore]] = {}
            for item in active_items:
                bucket_index = min(9, max(0, int(max(1e-9, min(1.0 - 1e-9, float(item.probability_yes))) * 10)))
                buckets.setdefault(f"decile_{bucket_index:02d}", []).append(item)
            weighted_error = 0.0
            for bucket_items in buckets.values():
                bucket_weight = len(bucket_items) / len(active_items)
                bucket_probability = _safe_mean([item.probability_yes for item in bucket_items])
                bucket_outcome = _safe_mean([1.0 if item.outcome_yes else 0.0 for item in bucket_items])
                weighted_error += bucket_weight * abs(bucket_probability - bucket_outcome)
            mean_ece = weighted_error
            mean_sharpness = _safe_mean([abs(item.probability_yes - 0.5) * 2.0 for item in active_items])
        mean_probability_yes = sum(item.probability_yes for item in items) / count
        mean_outcome_yes = sum(1.0 if item.outcome_yes else 0.0 for item in items) / count
        hit_rate = sum(1.0 if item.hit else 0.0 for item in items) / count
        mean_market_baseline_probability = _safe_mean(market_baseline_probabilities)
        mean_market_baseline_delta = _safe_mean(market_baseline_deltas)
        mean_market_baseline_delta_bps = _safe_mean([delta * 10000.0 for delta in market_baseline_deltas])
        mean_closing_line_drift_bps = sum(item.closing_line_drift_bps for item in items) / count
        mean_abs_closing_line_drift_bps = sum(abs(item.closing_line_drift_bps) for item in items) / count
        mean_edge_after_fees_bps = sum(item.edge_after_fees_bps for item in items) / count
        replay_flags = [item.replay_consistent for item in items if item.replay_consistent is not None]
        replay_consistency_rate = None
        if replay_flags:
            replay_consistency_rate = sum(1.0 if flag else 0.0 for flag in replay_flags) / len(replay_flags)

        label_counts = {"yes": 0, "no": 0}
        for item in items:
            label_counts["yes" if item.outcome_yes else "no"] += 1

        return CalibrationSummary(
            count=count,
            mean_brier_score=mean_brier_score,
            mean_log_loss=mean_log_loss,
            mean_ece=mean_ece,
            mean_sharpness=mean_sharpness,
            mean_probability_yes=mean_probability_yes,
            mean_outcome_yes=mean_outcome_yes,
            hit_rate=hit_rate,
            abstention_coverage=abstention_coverage,
            mean_market_baseline_probability=mean_market_baseline_probability,
            mean_market_baseline_delta=mean_market_baseline_delta,
            mean_market_baseline_delta_bps=mean_market_baseline_delta_bps,
            mean_closing_line_drift_bps=mean_closing_line_drift_bps,
            mean_abs_closing_line_drift_bps=mean_abs_closing_line_drift_bps,
            mean_edge_after_fees_bps=mean_edge_after_fees_bps,
            replay_consistency_rate=replay_consistency_rate,
            labels=label_counts,
        )._normalize()

    def report(self, scores: list[CalibrationScore] | None = None) -> CalibrationReport:
        items = scores if scores is not None else self.store.load_scores()
        summary = self.summarize(items)
        return CalibrationReport(
            summary=summary,
            scores=list(items),
            postmortems=[item.postmortem() for item in items],
            metadata={
                "count": summary.count,
                "hit_rate": summary.hit_rate,
                "mean_edge_after_fees_bps": summary.mean_edge_after_fees_bps,
                "mean_market_baseline_delta_bps": summary.mean_market_baseline_delta_bps,
                "abstention_coverage": summary.abstention_coverage,
            },
        )._normalize()

    def calibration_curve(
        self,
        scores: list[CalibrationScore] | None = None,
        *,
        bucket_count: int = 10,
        metadata: dict[str, Any] | None = None,
    ) -> CalibrationCurveReport:
        items = scores if scores is not None else self.store.load_scores()
        return build_calibration_curve_report(
            [_score_record_payload(item) for item in items],
            bucket_count=bucket_count,
            metadata={
                "source": "calibration_lab",
                **dict(metadata or {}),
                "score_count": len(items),
            },
        )

    def performance_by_category_and_horizon(
        self,
        scores: list[CalibrationScore] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> CategoryHorizonPerformanceReport:
        items = scores if scores is not None else self.store.load_scores()
        return build_category_horizon_performance_report(
            [_score_record_payload(item) for item in items],
            metadata={
                "source": "calibration_lab",
                **dict(metadata or {}),
                "score_count": len(items),
            },
        )

    def abstention_quality(
        self,
        scores: list[CalibrationScore] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> AbstentionQualityReport:
        items = scores if scores is not None else self.store.load_scores()
        return build_abstention_quality_report(
            [_score_record_payload(item) for item in items],
            metadata={
                "source": "calibration_lab",
                **dict(metadata or {}),
                "score_count": len(items),
            },
        )

    def closing_line_quality(
        self,
        scores: list[CalibrationScore] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ClosingLineQualityReport:
        items = scores if scores is not None else self.store.load_scores()
        return _build_closing_line_quality_report(
            items,
            metadata={
                "source": "calibration_lab",
                **dict(metadata or {}),
                "score_count": len(items),
            },
        )

    def summarize_calibration_as_of(
        self,
        records: list[ForecastEvaluationRecord] | None = None,
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

    def _load_manifest(self, run_id: str) -> RunManifest:
        return RunManifest.model_validate_json(self.paths.run_manifest_path(run_id).read_text(encoding="utf-8"))

    def _load_forecast(self, run_id: str) -> ForecastPacket:
        return ForecastPacket.model_validate_json(self.paths.forecast_path(run_id).read_text(encoding="utf-8"))

    @staticmethod
    def _infer_outcome_from_manifest(manifest: RunManifest) -> bool | None:
        for key in ("outcome_yes", "label_yes", "resolved_yes", "actual_outcome_yes"):
            value = manifest.metadata.get(key)
            if isinstance(value, bool):
                return value
        return None


def _build_closing_line_quality_report(
    scores: list[CalibrationScore],
    *,
    metadata: dict[str, Any] | None = None,
) -> ClosingLineQualityReport:
    items = list(scores)
    if not items:
        return ClosingLineQualityReport(metadata=dict(metadata or {}))._normalize()

    grouped: dict[tuple[str, str], list[CalibrationScore]] = {}
    for score in items:
        grouped.setdefault((_score_category(score), _score_horizon_bucket(score)), []).append(score)

    segments: list[CalibrationSegmentSummary] = []
    for (category, horizon_bucket), segment_scores in sorted(grouped.items()):
        active_scores = [score for score in segment_scores if not _is_abstention(score)]
        active_count = len(active_scores)
        abstain_count = len(segment_scores) - active_count
        active_hit_rate = _safe_mean([1.0 if score.hit else 0.0 for score in active_scores]) if active_scores else 0.0
        segments.append(
            CalibrationSegmentSummary(
                category=category,
                horizon_bucket=horizon_bucket,
                record_count=len(segment_scores),
                active_count=active_count,
                abstain_count=abstain_count,
                mean_probability_yes=_safe_mean([score.probability_yes for score in active_scores]) if active_scores else _safe_mean([score.probability_yes for score in segment_scores]),
                mean_outcome_yes=_safe_mean([1.0 if score.outcome_yes else 0.0 for score in segment_scores]),
                mean_brier_score=_safe_mean([score.brier_score for score in segment_scores]),
                mean_log_loss=_safe_mean([score.log_loss for score in segment_scores]),
                mean_closing_line_drift_bps=_safe_mean([score.closing_line_drift_bps for score in segment_scores]),
                mean_abs_closing_line_drift_bps=_safe_mean([abs(score.closing_line_drift_bps) for score in segment_scores]),
                mean_edge_after_fees_bps=_safe_mean([score.edge_after_fees_bps for score in segment_scores]),
                mean_abs_edge_after_fees_bps=_safe_mean([abs(score.edge_after_fees_bps) for score in segment_scores]),
                mean_hit_rate=active_hit_rate,
            )
        )

    return ClosingLineQualityReport(
        record_count=len(items),
        active_count=sum(segment.active_count for segment in segments),
        abstain_count=sum(segment.abstain_count for segment in segments),
        segment_count=len(segments),
        mean_closing_line_drift_bps=_safe_mean([score.closing_line_drift_bps for score in items]),
        mean_abs_closing_line_drift_bps=_safe_mean([abs(score.closing_line_drift_bps) for score in items]),
        mean_edge_after_fees_bps=_safe_mean([score.edge_after_fees_bps for score in items]),
        mean_abs_edge_after_fees_bps=_safe_mean([abs(score.edge_after_fees_bps) for score in items]),
        segments=segments,
        metadata=dict(metadata or {}),
    )._normalize()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
