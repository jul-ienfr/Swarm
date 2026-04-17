from __future__ import annotations

import json
import math
import os
import sys
import hashlib
from importlib import import_module
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field, field_validator


TIMESFM_UPSTREAM_REPOSITORY = "https://github.com/google-research/timesfm"
TIMESFM_UPSTREAM_BRANCH = "master"
TIMESFM_UPSTREAM_COMMIT = "d720daa6786539c2566a44464fbda1019c0a82c0"
TIMESFM_VENDOR_ROOT = Path(__file__).resolve().parent / "vendors" / "timesfm_master_snapshot"
TIMESFM_VENDOR_SRC = TIMESFM_VENDOR_ROOT / "src"
TIMESFM_DEFAULT_MODEL_ID = "google/timesfm-2.5-200m-pytorch"
TIMESFM_DEFAULT_MAX_CONTEXT = 256
TIMESFM_DEFAULT_MAX_HORIZON = 48


_TIMESFM_VENDOR_MODEL: Any | None = None
_TIMESFM_VENDOR_MODEL_CACHE_KEY: tuple[Any, ...] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round_prob(value: float | None) -> float | None:
    if value is None:
        return None
    return round(_clamp01(value), 6)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _safe_positive_float(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return max(0.0, parsed)


def _safe_iso(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedupe_strs(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _history_to_floats(history: Sequence[Any] | None) -> list[float]:
    if not history:
        return []
    values: list[float] = []
    for item in history:
        if isinstance(item, Mapping):
            parsed = _safe_float(item.get("price"))
        else:
            parsed = _safe_float(item)
        if parsed is None:
            continue
        values.append(_clamp01(parsed))
    return values


class TimesFMMode(str, Enum):
    off = "off"
    auto = "auto"
    required = "required"


class TimesFMLane(str, Enum):
    microstructure = "microstructure"
    event_probability = "event_probability"


class TimesFMLaneStatus(str, Enum):
    ready = "ready"
    abstained = "abstained"
    ineligible = "ineligible"


class TimesFMHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    blocked = "blocked"


class TimesFMSidecarRequest(BaseModel):
    run_id: str
    market_id: str
    venue: str = "polymarket"
    question: str = ""
    request_mode: str = "predict"
    timesfm_mode: TimesFMMode = TimesFMMode.auto
    timesfm_lanes: list[TimesFMLane] = Field(
        default_factory=lambda: [TimesFMLane.microstructure, TimesFMLane.event_probability]
    )
    history: list[Any] = Field(default_factory=list)
    midpoint_yes: float | None = None
    yes_price: float | None = None
    spread_bps: float | None = None
    depth_near_touch: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    cross_venue_gap_bps: float | None = None
    catalyst_due_at: str | None = None
    regime: str | None = None
    force_fixture_backend: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timesfm_lanes", mode="before")
    @classmethod
    def _normalize_lanes(cls, value: Any) -> list[str]:
        if value is None:
            return [TimesFMLane.microstructure.value, TimesFMLane.event_probability.value]
        if isinstance(value, str):
            return [value]
        return list(value)


class TimesFMSidecarHealth(BaseModel):
    healthy: bool
    status: TimesFMHealthStatus
    backend: str
    dependency_status: str
    issues: list[str] = Field(default_factory=list)
    summary: str


class TimesFMLaneForecast(BaseModel):
    lane: TimesFMLane
    status: TimesFMLaneStatus
    eligible: bool
    influences_research_aggregate: bool = False
    comparator_id: str
    comparator_kind: str = "candidate_model"
    basis: str
    model_family: str = "timesfm-2.5"
    pipeline_id: str = "timesfm-master-snapshot"
    pipeline_version: str = TIMESFM_UPSTREAM_COMMIT[:12]
    probability_yes: float | None = None
    confidence: float | None = None
    probability_band: dict[str, float] | None = None
    quantiles: dict[str, float] | None = None
    horizon: int | None = None
    summary: str
    rationale: str
    reasons: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("probability_yes", "confidence", mode="before")
    @classmethod
    def _normalize_probability(cls, value: Any) -> float | None:
        parsed = _safe_float(value)
        return _round_prob(parsed)


class TimesFMSidecarBundle(BaseModel):
    schema_version: str = "v1"
    sidecar_name: str = "timesfm_sidecar"
    run_id: str
    market_id: str
    venue: str
    question: str
    requested_mode: TimesFMMode
    effective_mode: TimesFMMode
    requested_lanes: list[TimesFMLane]
    selected_lane: TimesFMLane | None = None
    generated_at: str = Field(default_factory=_iso_now)
    health: TimesFMSidecarHealth
    vendor: dict[str, Any]
    lanes: dict[str, TimesFMLaneForecast] = Field(default_factory=dict)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "TimesFMSidecarBundle":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class _VendorImportStatus(BaseModel):
    available: bool
    backend: str
    dependency_status: str
    issues: list[str] = Field(default_factory=list)


class _VendorModelSettings(BaseModel):
    model_id: str
    model_revision: str | None = None
    model_cache_dir: str | None = None
    local_files_only: bool = True
    torch_compile: bool = False
    max_context: int = TIMESFM_DEFAULT_MAX_CONTEXT
    max_horizon: int = TIMESFM_DEFAULT_MAX_HORIZON

    @property
    def cache_key(self) -> tuple[Any, ...]:
        return (
            self.model_id,
            self.model_revision,
            self.model_cache_dir,
            self.local_files_only,
            self.torch_compile,
            self.max_context,
            self.max_horizon,
        )


class _VendorForecast(BaseModel):
    backend: str
    probability_yes: float
    confidence: float
    probability_band: dict[str, float]
    quantiles: dict[str, float]
    diagnostics: dict[str, Any] = Field(default_factory=dict)


def _vendor_metadata() -> dict[str, Any]:
    settings = _vendor_model_settings()
    return {
        "repository": TIMESFM_UPSTREAM_REPOSITORY,
        "branch": TIMESFM_UPSTREAM_BRANCH,
        "commit": TIMESFM_UPSTREAM_COMMIT,
        "snapshot_dir": str(TIMESFM_VENDOR_ROOT),
        "source_dir": str(TIMESFM_VENDOR_SRC),
        "model_id": settings.model_id,
        "model_revision": settings.model_revision,
        "model_cache_dir": settings.model_cache_dir,
        "local_files_only": settings.local_files_only,
    }


def _stable_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_feature_names(values: Sequence[str]) -> list[str]:
    return _dedupe_strs(values)


def _build_lane_features_used(
    lane: TimesFMLane,
    request: TimesFMSidecarRequest,
    *,
    history_points: int,
) -> list[str]:
    features = ["history_yes_price"]
    if request.midpoint_yes is not None:
        features.append("midpoint_yes")
    if request.yes_price is not None:
        features.append("yes_price")
    if request.spread_bps is not None:
        features.append("spread_bps")
    if request.depth_near_touch is not None:
        features.append("depth_near_touch")
    if request.liquidity_usd is not None:
        features.append("liquidity_usd")
    if request.volume_24h_usd is not None:
        features.append("volume_24h_usd")
    if request.cross_venue_gap_bps is not None:
        features.append("cross_venue_gap_bps")
    if request.catalyst_due_at:
        features.append("catalyst_due_at")
    if request.regime:
        features.append("regime")
    if lane == TimesFMLane.microstructure and history_points > 0:
        features.append("microstructure_lane_policy")
    if lane == TimesFMLane.event_probability:
        features.append("event_probability_lane_policy")
    return _normalize_feature_names(features)


def _build_lane_content_hash(
    lane: TimesFMLane,
    request: TimesFMSidecarRequest,
    history: Sequence[float],
    *,
    horizon: int,
    backend: str,
) -> str:
    return _stable_json_hash({
        "lane": lane.value,
        "market_id": request.market_id,
        "venue": request.venue,
        "requested_mode": request.timesfm_mode.value,
        "history": [round(value, 6) for value in history],
        "midpoint_yes": _round_prob(_safe_float(request.midpoint_yes)),
        "yes_price": _round_prob(_safe_float(request.yes_price)),
        "spread_bps": _safe_positive_float(request.spread_bps),
        "depth_near_touch": _safe_positive_float(request.depth_near_touch),
        "liquidity_usd": _safe_positive_float(request.liquidity_usd),
        "volume_24h_usd": _safe_positive_float(request.volume_24h_usd),
        "cross_venue_gap_bps": _safe_float(request.cross_venue_gap_bps),
        "catalyst_due_at": request.catalyst_due_at,
        "regime": request.regime,
        "horizon": horizon,
        "backend": backend,
        "vendor_commit": TIMESFM_UPSTREAM_COMMIT,
    })


def _ensure_vendor_path() -> None:
    vendor_src = str(TIMESFM_VENDOR_SRC)
    if vendor_src not in sys.path:
        sys.path.insert(0, vendor_src)


def _vendor_import_status() -> _VendorImportStatus:
    if not TIMESFM_VENDOR_SRC.exists():
        return _VendorImportStatus(
            available=False,
            backend="unavailable",
            dependency_status="vendor_snapshot_missing",
            issues=["vendor_snapshot_missing"],
        )
    try:
        _ensure_vendor_path()
        import numpy  # noqa: F401
        import timesfm  # noqa: F401
    except Exception as exc:  # pragma: no cover - backend-specific import failures vary
        return _VendorImportStatus(
            available=False,
            backend="unavailable",
            dependency_status="vendor_import_failed",
            issues=[f"vendor_import_failed:{type(exc).__name__}"],
        )
    return _VendorImportStatus(
        available=True,
        backend="vendor_torch_candidate",
        dependency_status="vendor_import_available",
        issues=[],
    )


def _vendor_model_settings() -> _VendorModelSettings:
    model_path = os.getenv("SWARM_TIMESFM_MODEL_PATH", "").strip()
    model_id = model_path or os.getenv("SWARM_TIMESFM_MODEL_ID", TIMESFM_DEFAULT_MODEL_ID).strip() or TIMESFM_DEFAULT_MODEL_ID
    allow_remote_weights = _env_flag("SWARM_TIMESFM_ALLOW_REMOTE_WEIGHTS", default=False)
    local_files_only = _env_flag("SWARM_TIMESFM_LOCAL_FILES_ONLY", default=not allow_remote_weights)
    return _VendorModelSettings(
        model_id=model_id,
        model_revision=os.getenv("SWARM_TIMESFM_MODEL_REVISION", "").strip() or None,
        model_cache_dir=os.getenv("SWARM_TIMESFM_MODEL_CACHE_DIR", "").strip() or None,
        local_files_only=local_files_only,
        torch_compile=_env_flag("SWARM_TIMESFM_TORCH_COMPILE", default=False),
        max_context=_env_int("SWARM_TIMESFM_MAX_CONTEXT", default=TIMESFM_DEFAULT_MAX_CONTEXT),
        max_horizon=_env_int("SWARM_TIMESFM_MAX_HORIZON", default=TIMESFM_DEFAULT_MAX_HORIZON),
    )


def _load_vendor_model() -> tuple[Any, _VendorModelSettings]:
    global _TIMESFM_VENDOR_MODEL, _TIMESFM_VENDOR_MODEL_CACHE_KEY

    settings = _vendor_model_settings()
    if _TIMESFM_VENDOR_MODEL is not None and _TIMESFM_VENDOR_MODEL_CACHE_KEY == settings.cache_key:
        return _TIMESFM_VENDOR_MODEL, settings

    _ensure_vendor_path()
    timesfm = import_module("timesfm")
    model_class = getattr(timesfm, "TimesFM_2p5_200M_torch", None)
    if model_class is None:
        raise RuntimeError("vendored_timesfm_torch_backend_missing")

    model = model_class.from_pretrained(
        model_id=settings.model_id,
        revision=settings.model_revision,
        cache_dir=settings.model_cache_dir,
        local_files_only=settings.local_files_only,
        torch_compile=settings.torch_compile,
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=settings.max_context,
            max_horizon=settings.max_horizon,
            normalize_inputs=True,
            per_core_batch_size=1,
            fix_quantile_crossing=True,
            force_flip_invariance=True,
        )
    )

    _TIMESFM_VENDOR_MODEL = model
    _TIMESFM_VENDOR_MODEL_CACHE_KEY = settings.cache_key
    return model, settings


def _estimate_vendor_forecast(
    history: Sequence[float],
    *,
    horizon: int,
) -> _VendorForecast:
    if not history:
        raise ValueError("empty_history")

    model, settings = _load_vendor_model()
    point_forecast, quantile_forecast = model.forecast(horizon=horizon, inputs=[list(history)])
    point_row = point_forecast[0]
    quantile_row = quantile_forecast[0]
    last_point = _round_prob(_safe_float(point_row[-1]))
    if last_point is None:
        raise RuntimeError("vendor_forecast_missing_point")

    # The upstream tensor exposes a point head at index 5 alongside quantiles.
    low = _round_prob(_safe_float(quantile_row[-1][1])) if len(quantile_row[-1]) > 1 else None
    high = _round_prob(_safe_float(quantile_row[-1][9])) if len(quantile_row[-1]) > 9 else None
    center = _round_prob(_safe_float(quantile_row[-1][5])) if len(quantile_row[-1]) > 5 else last_point
    if low is None:
        low = min(last_point, center if center is not None else last_point)
    if high is None:
        high = max(last_point, center if center is not None else last_point)
    center = center if center is not None else last_point
    band_width = max(0.0, high - low)
    confidence = _clamp01(0.8 - min(0.45, band_width * 1.5))

    return _VendorForecast(
        backend="vendor_torch",
        probability_yes=last_point,
        confidence=round(confidence, 6),
        probability_band={
            "low": round(low, 6),
            "center": round(center, 6),
            "high": round(high, 6),
        },
        quantiles={
            "p10": round(low, 6),
            "p50": round(center, 6),
            "p90": round(high, 6),
        },
        diagnostics={
            "history_points": len(history),
            "vendor_model_id": settings.model_id,
            "vendor_model_revision": settings.model_revision,
            "vendor_local_files_only": settings.local_files_only,
            "vendor_max_context": settings.max_context,
            "vendor_max_horizon": settings.max_horizon,
            "forecast_last_step": round(last_point, 6),
            "forecast_mean": round(sum(float(value) for value in point_row) / max(1, len(point_row)), 6),
            "quantile_band_width": round(band_width, 6),
        },
    )


def _estimate_fixture_forecast(
    history: Sequence[float],
    *,
    horizon: int,
    spread_bps: float | None,
    cross_venue_gap_bps: float | None,
) -> tuple[float, float, dict[str, float], dict[str, float], dict[str, Any]]:
    sample = list(history[-max(4, min(len(history), 24)):])
    last = sample[-1]
    first = sample[0]
    trend = (last - first) / max(1, len(sample) - 1)
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / max(1, len(sample))
    volatility = math.sqrt(max(0.0, variance))
    projected = _clamp01(last + (trend * min(horizon, 6)))
    liquidity_bonus = 0.0
    if spread_bps is not None:
        liquidity_bonus -= min(0.04, max(0.0, spread_bps) / 20_000.0)
    if cross_venue_gap_bps is not None:
        liquidity_bonus += min(0.03, abs(cross_venue_gap_bps) / 20_000.0)
    center = _clamp01(projected + liquidity_bonus)
    band_width = max(0.03, min(0.18, volatility * 1.5 + abs(trend) * 2.0))
    low = _clamp01(center - band_width)
    high = _clamp01(center + band_width)
    confidence = _clamp01(0.45 + min(0.3, len(sample) / 80.0) - band_width / 2.0)
    quantiles = {
        "p10": round(low, 6),
        "p50": round(center, 6),
        "p90": round(high, 6),
    }
    band = {
        "low": round(low, 6),
        "center": round(center, 6),
        "high": round(high, 6),
    }
    diagnostics = {
        "history_points": len(history),
        "trend_per_step": round(trend, 6),
        "volatility": round(volatility, 6),
        "band_width": round(band_width, 6),
    }
    return round(center, 6), round(confidence, 6), band, quantiles, diagnostics


class TimesFMSidecarBridge:
    def run(self, request: TimesFMSidecarRequest) -> TimesFMSidecarBundle:
        history = _history_to_floats(request.history)
        vendor_status = _vendor_import_status()
        use_fixture_backend = request.force_fixture_backend or os.getenv("SWARM_TIMESFM_FIXTURE_BACKEND") == "1"
        backend = "fixture" if use_fixture_backend else vendor_status.backend
        lanes: dict[str, TimesFMLaneForecast] = {}
        issues: list[str] = list(vendor_status.issues)
        selected_lane: TimesFMLane | None = None

        catalyst_due_at = _safe_iso(request.catalyst_due_at)
        catalyst_imminent = (
            catalyst_due_at is not None
            and (catalyst_due_at - _utc_now()).total_seconds() <= 72 * 3600
        )

        for lane in request.timesfm_lanes:
            lane_issues: list[str] = []
            basis = "timesfm_microstructure" if lane == TimesFMLane.microstructure else "timesfm_event_probability"
            comparator_id = f"candidate_{basis}"
            min_history = 16 if lane == TimesFMLane.microstructure else 32
            if len(history) < min_history:
                lane_issues.append(f"insufficient_history:{len(history)}/{min_history}")
                lanes[lane.value] = TimesFMLaneForecast(
                    lane=lane,
                    status=TimesFMLaneStatus.ineligible,
                    eligible=False,
                    influences_research_aggregate=lane == TimesFMLane.microstructure,
                    comparator_id=comparator_id,
                    basis=basis,
                    summary=f"{lane.value} lane skipped because price history is too short.",
                    rationale=f"TimesFM needs at least {min_history} historical points for the {lane.value} lane.",
                    reasons=lane_issues,
                    metadata={
                        "history_points": len(history),
                        "features_used": _build_lane_features_used(lane, request, history_points=len(history)),
                        "content_hash": _build_lane_content_hash(lane, request, history, horizon=16, backend=backend),
                        "provenance": {
                            "repository": TIMESFM_UPSTREAM_REPOSITORY,
                            "branch": TIMESFM_UPSTREAM_BRANCH,
                            "commit": TIMESFM_UPSTREAM_COMMIT,
                            "lane": lane.value,
                        },
                    },
                )
                issues.extend(lane_issues)
                continue

            if lane == TimesFMLane.event_probability and catalyst_imminent:
                lane_issues.append("catalyst_imminent")
                lanes[lane.value] = TimesFMLaneForecast(
                    lane=lane,
                    status=TimesFMLaneStatus.abstained,
                    eligible=False,
                    influences_research_aggregate=False,
                    comparator_id=comparator_id,
                    basis=basis,
                    summary="event_probability lane abstained because a catalyst is too close.",
                    rationale="Bench-only event probability stays conservative when the contract is in a catalyst-imminent regime.",
                    reasons=lane_issues,
                    metadata={
                        "history_points": len(history),
                        "catalyst_due_at": request.catalyst_due_at,
                        "features_used": _build_lane_features_used(lane, request, history_points=len(history)),
                        "content_hash": _build_lane_content_hash(lane, request, history, horizon=48, backend=backend),
                        "provenance": {
                            "repository": TIMESFM_UPSTREAM_REPOSITORY,
                            "branch": TIMESFM_UPSTREAM_BRANCH,
                            "commit": TIMESFM_UPSTREAM_COMMIT,
                            "lane": lane.value,
                        },
                    },
                )
                issues.extend(lane_issues)
                continue

            if not use_fixture_backend and not vendor_status.available:
                lane_issues.append(vendor_status.dependency_status)
                lanes[lane.value] = TimesFMLaneForecast(
                    lane=lane,
                    status=TimesFMLaneStatus.abstained,
                    eligible=False,
                    influences_research_aggregate=lane == TimesFMLane.microstructure,
                    comparator_id=comparator_id,
                    basis=basis,
                    summary=f"{lane.value} lane abstained because the vendored TimesFM backend is unavailable.",
                    rationale="The local vendor snapshot could not be imported with the current Python dependencies.",
                    reasons=lane_issues,
                    metadata={
                        "history_points": len(history),
                        "features_used": _build_lane_features_used(lane, request, history_points=len(history)),
                        "content_hash": _build_lane_content_hash(lane, request, history, horizon=16 if lane == TimesFMLane.microstructure else 48, backend=backend),
                        "provenance": {
                            "repository": TIMESFM_UPSTREAM_REPOSITORY,
                            "branch": TIMESFM_UPSTREAM_BRANCH,
                            "commit": TIMESFM_UPSTREAM_COMMIT,
                            "lane": lane.value,
                        },
                    },
                )
                issues.extend(lane_issues)
                continue

            horizon = 24 if lane == TimesFMLane.microstructure else 48
            diagnostics: dict[str, Any]
            if use_fixture_backend:
                backend = "fixture"
                probability_yes, confidence, probability_band, quantiles, diagnostics = _estimate_fixture_forecast(
                    history,
                    horizon=horizon,
                    spread_bps=_safe_positive_float(request.spread_bps),
                    cross_venue_gap_bps=_safe_float(request.cross_venue_gap_bps),
                )
            else:
                try:
                    vendor_forecast = _estimate_vendor_forecast(history, horizon=horizon)
                except Exception as exc:
                    lane_issues.append(f"vendor_forecast_failed:{type(exc).__name__}")
                    lanes[lane.value] = TimesFMLaneForecast(
                        lane=lane,
                        status=TimesFMLaneStatus.abstained,
                        eligible=False,
                        influences_research_aggregate=lane == TimesFMLane.microstructure,
                        comparator_id=comparator_id,
                        basis=basis,
                        summary=f"{lane.value} lane abstained because the vendored TimesFM model could not produce a forecast.",
                        rationale="The vendored TimesFM snapshot imported successfully, but model weights or forecast execution were unavailable for this environment.",
                        reasons=lane_issues,
                        metadata={
                            "history_points": len(history),
                            "features_used": _build_lane_features_used(lane, request, history_points=len(history)),
                            "content_hash": _build_lane_content_hash(lane, request, history, horizon=horizon, backend=backend),
                            "provenance": {
                                "repository": TIMESFM_UPSTREAM_REPOSITORY,
                                "branch": TIMESFM_UPSTREAM_BRANCH,
                                "commit": TIMESFM_UPSTREAM_COMMIT,
                                "lane": lane.value,
                            },
                        },
                    )
                    issues.extend(lane_issues)
                    continue
                backend = vendor_forecast.backend
                probability_yes = vendor_forecast.probability_yes
                confidence = vendor_forecast.confidence
                probability_band = vendor_forecast.probability_band
                quantiles = vendor_forecast.quantiles
                diagnostics = vendor_forecast.diagnostics
            summary = (
                f"{lane.value} lane forecast { _percent(probability_yes) } "
                f"with { _percent(confidence) } confidence via {backend}."
            )
            rationale = (
                "Local TimesFM wrapper used the vendored master snapshot for inference when available and kept the fixture backend for explicit test fallback."
                if backend == "vendor_torch"
                else "Local TimesFM wrapper produced a deterministic bounded forecast from frozen price history via the explicit fixture backend."
            )
            lanes[lane.value] = TimesFMLaneForecast(
                lane=lane,
                status=TimesFMLaneStatus.ready,
                eligible=True,
                influences_research_aggregate=lane == TimesFMLane.microstructure,
                comparator_id=comparator_id,
                basis=basis,
                probability_yes=probability_yes,
                confidence=confidence,
                probability_band=probability_band,
                quantiles=quantiles,
                horizon=horizon,
                summary=summary,
                rationale=rationale,
                reasons=[],
                source_refs=[TIMESFM_UPSTREAM_REPOSITORY, f"commit:{TIMESFM_UPSTREAM_COMMIT}"],
                metadata={
                    **diagnostics,
                    "backend": backend,
                    "request_mode": request.request_mode,
                    "regime": request.regime,
                    "liquidity_usd": _safe_positive_float(request.liquidity_usd),
                    "volume_24h_usd": _safe_positive_float(request.volume_24h_usd),
                    "depth_near_touch": _safe_positive_float(request.depth_near_touch),
                    "spread_bps": _safe_positive_float(request.spread_bps),
                    "cross_venue_gap_bps": _safe_float(request.cross_venue_gap_bps),
                    "features_used": _build_lane_features_used(lane, request, history_points=len(history)),
                    "content_hash": _build_lane_content_hash(lane, request, history, horizon=horizon, backend=backend),
                    "provenance": {
                        "repository": TIMESFM_UPSTREAM_REPOSITORY,
                        "branch": TIMESFM_UPSTREAM_BRANCH,
                        "commit": TIMESFM_UPSTREAM_COMMIT,
                        "lane": lane.value,
                    },
                },
            )
            if selected_lane is None:
                selected_lane = lane

        ready_count = sum(1 for lane in lanes.values() if lane.status == TimesFMLaneStatus.ready)
        healthy = ready_count > 0
        if request.timesfm_mode == TimesFMMode.required and ready_count == 0:
            health_status = TimesFMHealthStatus.blocked
        elif healthy and issues:
            health_status = TimesFMHealthStatus.degraded
        elif healthy:
            health_status = TimesFMHealthStatus.healthy
        else:
            health_status = TimesFMHealthStatus.degraded if request.timesfm_mode == TimesFMMode.auto else TimesFMHealthStatus.blocked

        dependency_status = "fixture_backend" if use_fixture_backend else vendor_status.dependency_status
        health = TimesFMSidecarHealth(
            healthy=healthy,
            status=health_status,
            backend=backend,
            dependency_status=dependency_status,
            issues=_dedupe_strs(issues),
            summary=(
                f"TimesFM {health_status.value}; ready_lanes={ready_count}/{len(request.timesfm_lanes)} "
                f"backend={backend} dependency={dependency_status}"
            ),
        )
        summary = (
            f"TimesFM requested {request.timesfm_mode.value} on {', '.join(lane.value for lane in request.timesfm_lanes)}; "
            f"selected={selected_lane.value if selected_lane else 'none'}; {health.summary}."
        )
        return TimesFMSidecarBundle(
            run_id=request.run_id,
            market_id=request.market_id,
            venue=request.venue,
            question=request.question,
            requested_mode=request.timesfm_mode,
            effective_mode=request.timesfm_mode,
            requested_lanes=request.timesfm_lanes,
            selected_lane=selected_lane,
            health=health,
            vendor=_vendor_metadata(),
            lanes=lanes,
            summary=summary,
            metadata={
                "history_points": len(history),
                "midpoint_yes": _round_prob(_safe_float(request.midpoint_yes)),
                "yes_price": _round_prob(_safe_float(request.yes_price)),
                "catalyst_due_at": request.catalyst_due_at,
                "catalyst_imminent": catalyst_imminent,
                "regime": request.regime,
                "cross_venue_gap_bps": _safe_float(request.cross_venue_gap_bps),
                "content_hash": _stable_json_hash({
                    "run_id": request.run_id,
                    "market_id": request.market_id,
                    "requested_mode": request.timesfm_mode.value,
                    "requested_lanes": [lane.value for lane in request.timesfm_lanes],
                    "history": [round(value, 6) for value in history],
                    "midpoint_yes": _round_prob(_safe_float(request.midpoint_yes)),
                    "yes_price": _round_prob(_safe_float(request.yes_price)),
                    "spread_bps": _safe_positive_float(request.spread_bps),
                    "depth_near_touch": _safe_positive_float(request.depth_near_touch),
                    "liquidity_usd": _safe_positive_float(request.liquidity_usd),
                    "volume_24h_usd": _safe_positive_float(request.volume_24h_usd),
                    "cross_venue_gap_bps": _safe_float(request.cross_venue_gap_bps),
                    "catalyst_due_at": request.catalyst_due_at,
                    "regime": request.regime,
                    "vendor_commit": TIMESFM_UPSTREAM_COMMIT,
                }),
            },
        )


def run_timesfm_sidecar(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = TimesFMSidecarRequest.model_validate(payload)
    bundle = TimesFMSidecarBridge().run(request)
    return bundle.model_dump(mode="json", exclude_none=True)


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    output = run_timesfm_sidecar(payload)
    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
