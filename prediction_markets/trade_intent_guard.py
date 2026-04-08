from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .models import (
    ExecutionProjection,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    ExecutionReadiness,
    MarketSnapshot,
    TradeIntent,
    VenueHealthReport,
    _source_refs,
)


class TradeIntentGuardVerdict(str, Enum):
    allowed = "allowed"
    annotated = "annotated"
    blocked = "blocked"


class TradeIntentGuardConstraints(BaseModel):
    schema_version: str = "v1"
    max_snapshot_staleness_ms: int = 120_000
    min_edge_after_fees_bps: float = 0.0
    min_liquidity_usd: float = 0.0
    min_depth_near_touch: float = 0.0
    min_resolution_compatibility_score: float = 0.0
    min_payout_compatibility_score: float = 0.0
    min_currency_compatibility_score: float = 0.0
    weak_edge_after_fees_bps: float = 25.0
    block_on_manual_review: bool = True
    block_on_projection_blocked: bool = True
    block_on_unhealthy_venue: bool = True
    block_on_missing_edge: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_snapshot_staleness_ms")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator(
        "min_edge_after_fees_bps",
        "min_liquidity_usd",
        "min_depth_near_touch",
        "min_resolution_compatibility_score",
        "min_payout_compatibility_score",
        "min_currency_compatibility_score",
        "weak_edge_after_fees_bps",
    )
    @classmethod
    def _non_negative_float(cls, value: float) -> float:
        return max(0.0, float(value))

    @field_validator("weak_edge_after_fees_bps")
    @classmethod
    def _weak_edge_not_below_minimum(cls, value: float, info: Any) -> float:
        minimum = info.data.get("min_edge_after_fees_bps", 0.0) if hasattr(info, "data") else 0.0
        return max(float(minimum), float(value))


class TradeIntentGuardReport(BaseModel):
    schema_version: str = "v1"
    guard_id: str = Field(default_factory=lambda: f"tiguard_{uuid4().hex[:12]}")
    intent_id: str
    run_id: str
    market_id: str
    venue: str
    verdict: TradeIntentGuardVerdict = TradeIntentGuardVerdict.blocked
    can_execute: bool = False
    manual_review_required: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
    snapshot_staleness_ms: int | None = None
    edge_after_fees_bps: float | None = None
    venue_health_status: str = "unknown"
    projection_id: str | None = None
    projection_verdict: str | None = None
    readiness_id: str | None = None
    readiness_route: str | None = None
    summary: str = ""
    guarded_trade_intent: TradeIntent
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("edge_after_fees_bps")
    @classmethod
    def _normalize_edge(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return float(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _first_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _normalized_reason_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        values = list(value)
    normalized: list[str] = []
    for item in values:
        text = " ".join(str(item).strip().split())
        if text:
            normalized.append(text)
    return normalized


def _summary(blocked_reasons: list[str], warning_reasons: list[str]) -> str:
    if not blocked_reasons and not warning_reasons:
        return "trade_intent_guard_ok"
    parts: list[str] = []
    if blocked_reasons:
        parts.append(f"blocked={';'.join(blocked_reasons[:3])}")
    if warning_reasons:
        parts.append(f"warnings={';'.join(warning_reasons[:3])}")
    return " | ".join(parts)


def _venue_health_status(venue_health: VenueHealthReport | None) -> tuple[str, list[str], list[str]]:
    if venue_health is None:
        return "unknown", [], []
    if venue_health.healthy:
        return "healthy", [], []
    if venue_health.details.get("degraded_mode") or "degraded" in venue_health.message.lower():
        return "degraded", [], [f"venue_degraded:{venue_health.message}"]
    return "unhealthy", [f"venue_unhealthy:{venue_health.message}"], []


def _projection_status(
    projection: ExecutionProjection | None,
    *,
    block_on_projection_blocked: bool,
    block_on_manual_review: bool,
) -> tuple[str | None, list[str], list[str]]:
    if projection is None:
        return None, [], []

    blocked_reasons: list[str] = []
    warning_reasons: list[str] = []
    projection_verdict = projection.projection_verdict.value

    if projection.manual_review_required and block_on_manual_review:
        blocked_reasons.append("projection_manual_review_required")

    if projection.projection_verdict == ExecutionProjectionVerdict.blocked and block_on_projection_blocked:
        blocked_reasons.extend(projection.blocking_reasons or ["projection_blocked"])
    elif projection.projection_verdict == ExecutionProjectionVerdict.degraded:
        warning_reasons.extend(projection.downgrade_reasons or ["projection_degraded"])

    if projection.projected_mode in {ExecutionProjectionOutcome.paper, ExecutionProjectionOutcome.shadow}:
        warning_reasons.append(f"projection_downgraded:{projection.projected_mode.value}")

    return projection_verdict, _dedupe(blocked_reasons), _dedupe(warning_reasons)


@dataclass
class TradeIntentGuard:
    constraints: TradeIntentGuardConstraints | None = None

    def __post_init__(self) -> None:
        self.constraints = self.constraints or TradeIntentGuardConstraints()

    def evaluate(
        self,
        trade_intent: TradeIntent,
        *,
        snapshot: MarketSnapshot | None = None,
        readiness: ExecutionReadiness | None = None,
        projection: ExecutionProjection | None = None,
        venue_health: VenueHealthReport | None = None,
        edge_after_fees_bps: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> TradeIntentGuardReport:
        constraints = self.constraints or TradeIntentGuardConstraints()
        blocked_reasons: list[str] = []
        warning_reasons: list[str] = []

        resolved_metadata = {
            **dict(trade_intent.metadata),
            **(dict(metadata) if metadata is not None else {}),
        }

        snapshot_staleness_ms = snapshot.staleness_ms if snapshot is not None else None
        resolved_snapshot_ttl_ms = _first_int(
            resolved_metadata.get("snapshot_ttl_ms"),
            resolved_metadata.get("max_snapshot_staleness_ms"),
            constraints.max_snapshot_staleness_ms,
        )
        if resolved_snapshot_ttl_ms is None:
            resolved_snapshot_ttl_ms = constraints.max_snapshot_staleness_ms
        resolved_liquidity_usd = _first_float(
            snapshot.liquidity if snapshot is not None else None,
            resolved_metadata.get("snapshot_liquidity_usd"),
            resolved_metadata.get("liquidity_usd"),
            resolved_metadata.get("market_liquidity_usd"),
        )
        resolved_depth_near_touch = _first_float(
            snapshot.depth_near_touch if snapshot is not None else None,
            resolved_metadata.get("snapshot_depth_near_touch"),
            resolved_metadata.get("depth_near_touch"),
        )
        resolved_min_liquidity_usd = max(
            0.0,
            constraints.min_liquidity_usd,
            _first_float(resolved_metadata.get("min_liquidity_usd"), resolved_metadata.get("min_liquidity")) or 0.0,
        )
        resolved_min_depth_near_touch = max(
            0.0,
            constraints.min_depth_near_touch,
            _first_float(resolved_metadata.get("min_depth_near_touch")) or 0.0,
        )
        resolved_min_edge_after_fees_bps = max(
            0.0,
            constraints.min_edge_after_fees_bps,
            _first_float(resolved_metadata.get("min_edge_after_fees_bps"), resolved_metadata.get("min_edge_bps")) or 0.0,
        )
        if snapshot is None:
            blocked_reasons.append("missing_snapshot")
        elif snapshot_staleness_ms is not None and snapshot_staleness_ms > resolved_snapshot_ttl_ms:
            blocked_reasons.append(f"snapshot_stale:{snapshot_staleness_ms}/{resolved_snapshot_ttl_ms}")
        if resolved_min_liquidity_usd > 0.0:
            if resolved_liquidity_usd is None:
                blocked_reasons.append("missing_snapshot_liquidity_usd")
            elif resolved_liquidity_usd < resolved_min_liquidity_usd:
                blocked_reasons.append(f"liquidity_below_minimum:{resolved_liquidity_usd:.2f}/{resolved_min_liquidity_usd:.2f}")
        if resolved_min_depth_near_touch > 0.0:
            if resolved_depth_near_touch is None:
                blocked_reasons.append("missing_snapshot_depth_near_touch")
            elif resolved_depth_near_touch < resolved_min_depth_near_touch:
                blocked_reasons.append(
                    f"depth_near_touch_below_minimum:{resolved_depth_near_touch:.2f}/{resolved_min_depth_near_touch:.2f}"
                )

        resolved_edge = _first_float(
            edge_after_fees_bps,
            resolved_metadata.get("edge_after_fees_bps"),
            resolved_metadata.get("trade_intent_edge_after_fees_bps"),
            resolved_metadata.get("forecast_edge_after_fees_bps"),
            readiness.edge_after_fees_bps if readiness is not None else None,
        )
        if resolved_edge is None:
            if constraints.block_on_missing_edge:
                blocked_reasons.append("missing_edge_after_fees_bps")
        elif resolved_edge <= resolved_min_edge_after_fees_bps:
            if resolved_edge <= 0.0:
                blocked_reasons.append(f"non_positive_edge_after_fees_bps:{resolved_edge:.3f}")
            blocked_reasons.append(
                f"edge_after_fees_below_minimum:{resolved_edge:.3f}/{resolved_min_edge_after_fees_bps:.3f}"
            )
        elif resolved_edge <= max(constraints.weak_edge_after_fees_bps, resolved_min_edge_after_fees_bps):
            warning_reasons.append(f"weak_edge_after_fees_bps:{resolved_edge:.3f}")

        if trade_intent.side is None:
            blocked_reasons.append("missing_trade_side")
        if trade_intent.limit_price is None:
            blocked_reasons.append("missing_limit_price")
        if trade_intent.size_usd <= 0.0:
            blocked_reasons.append("non_positive_trade_size")
        if not trade_intent.risk_checks_passed:
            blocked_reasons.append("risk_checks_failed")
        if trade_intent.manual_review_required:
            blocked_reasons.append("trade_intent_manual_review_required")
        blocked_reasons.extend(trade_intent.no_trade_reasons)

        readiness_id = readiness.readiness_id if readiness is not None else None
        readiness_route = readiness.route if readiness is not None else None
        if readiness is not None:
            blocked_reasons.extend(readiness.blocked_reasons)
            blocked_reasons.extend(readiness.no_trade_reasons)
            if readiness.manual_review_required:
                blocked_reasons.append("readiness_manual_review_required")
            if not readiness.can_materialize_trade_intent:
                blocked_reasons.append("readiness_not_materializable")

        projection_verdict, projection_blocked_reasons, projection_warning_reasons = _projection_status(
            projection,
            block_on_projection_blocked=constraints.block_on_projection_blocked,
            block_on_manual_review=constraints.block_on_manual_review,
        )
        blocked_reasons.extend(projection_blocked_reasons)
        warning_reasons.extend(projection_warning_reasons)
        projection_metadata = dict(projection.metadata or {}) if projection is not None else {}
        action_time_guard = dict(projection_metadata.get("action_time_guard") or {})
        resolution_guard_audit = dict(action_time_guard.get("resolution_guard") or {})
        if action_time_guard:
            if action_time_guard.get("resolution_guard_valid") is False:
                blocked_reasons.append("resolution_guard_not_valid")
            if action_time_guard.get("resolution_guard_approved") is False:
                blocked_reasons.append("resolution_guard_not_approved")
            if action_time_guard.get("resolution_guard_manual_review_required"):
                blocked_reasons.append("resolution_guard_manual_review_required")
            if action_time_guard.get("resolution_guard_status") not in {None, "clear"}:
                blocked_reasons.append(f"resolution_guard_status:{action_time_guard.get('resolution_guard_status')}")
        blocked_reasons.extend(_normalized_reason_list(resolution_guard_audit.get("blocked_reasons")))
        warning_reasons.extend(_normalized_reason_list(resolution_guard_audit.get("degraded_reasons")))
        resolution_completeness_score = _first_float(
            action_time_guard.get("resolution_guard_policy_completeness_score"),
            projection_metadata.get("resolution_guard_policy_completeness_score"),
            resolved_metadata.get("resolution_guard_policy_completeness_score"),
        )
        resolution_coherence_score = _first_float(
            action_time_guard.get("resolution_guard_policy_coherence_score"),
            projection_metadata.get("resolution_guard_policy_coherence_score"),
            resolved_metadata.get("resolution_guard_policy_coherence_score"),
        )
        payout_compatibility_score = _first_float(
            action_time_guard.get("resolution_guard_payout_compatibility_score"),
            projection_metadata.get("resolution_guard_payout_compatibility_score"),
            resolved_metadata.get("payout_compatibility_score"),
        )
        currency_compatibility_score = _first_float(
            action_time_guard.get("resolution_guard_currency_compatibility_score"),
            projection_metadata.get("resolution_guard_currency_compatibility_score"),
            resolved_metadata.get("currency_compatibility_score"),
        )
        resolution_threshold = max(
            0.0,
            constraints.min_resolution_compatibility_score,
            _first_float(
                resolved_metadata.get("min_resolution_compatibility_score"),
                resolved_metadata.get("min_policy_completeness_score"),
                resolved_metadata.get("min_policy_coherence_score"),
            )
            or 0.0,
        )
        payout_threshold = max(
            0.0,
            constraints.min_payout_compatibility_score,
            _first_float(resolved_metadata.get("min_payout_compatibility_score")) or 0.0,
        )
        currency_threshold = max(
            0.0,
            constraints.min_currency_compatibility_score,
            _first_float(resolved_metadata.get("min_currency_compatibility_score")) or 0.0,
        )
        if resolution_threshold > 0.0 and resolution_completeness_score is not None and resolution_completeness_score < resolution_threshold:
            blocked_reasons.append(
                "resolution_policy_completeness_below_minimum:"
                f"{resolution_completeness_score:.3f}/{resolution_threshold:.3f}"
            )
        if resolution_threshold > 0.0 and resolution_coherence_score is not None and resolution_coherence_score < resolution_threshold:
            blocked_reasons.append(
                "resolution_policy_coherence_below_minimum:"
                f"{resolution_coherence_score:.3f}/{resolution_threshold:.3f}"
            )
        if payout_threshold > 0.0 and payout_compatibility_score is not None and payout_compatibility_score < payout_threshold:
            blocked_reasons.append(
                "resolution_payout_compatibility_below_minimum:"
                f"{payout_compatibility_score:.3f}/{payout_threshold:.3f}"
            )
        if currency_threshold > 0.0 and currency_compatibility_score is not None and currency_compatibility_score < currency_threshold:
            blocked_reasons.append(
                "resolution_currency_compatibility_below_minimum:"
                f"{currency_compatibility_score:.3f}/{currency_threshold:.3f}"
            )

        venue_health_status, venue_blocked_reasons, venue_warning_reasons = _venue_health_status(venue_health)
        if venue_health is not None and not venue_health.healthy and not venue_warning_reasons and constraints.block_on_unhealthy_venue:
            blocked_reasons.extend(venue_blocked_reasons)
        else:
            warning_reasons.extend(venue_warning_reasons)

        blocked_reasons = _dedupe(blocked_reasons)
        warning_reasons = _dedupe(warning_reasons)

        if blocked_reasons:
            verdict = TradeIntentGuardVerdict.blocked
        elif warning_reasons:
            verdict = TradeIntentGuardVerdict.annotated
        else:
            verdict = TradeIntentGuardVerdict.allowed

        manual_review_required = bool(
            trade_intent.manual_review_required
            or (readiness.manual_review_required if readiness is not None else False)
            or (projection.manual_review_required if projection is not None else False)
            or blocked_reasons
        )
        can_execute = verdict != TradeIntentGuardVerdict.blocked

        summary = _summary(blocked_reasons, warning_reasons)
        guarded_metadata = {
            **resolved_metadata,
            **constraints.metadata,
            "trade_intent_guard_id": None,
            "trade_intent_guard_verdict": verdict.value,
            "trade_intent_guard_summary": summary,
            "trade_intent_guard_blocked_reasons": list(blocked_reasons),
            "trade_intent_guard_warning_reasons": list(warning_reasons),
            "trade_intent_guard_manual_review_required": manual_review_required,
            "trade_intent_guard_snapshot_staleness_ms": snapshot_staleness_ms,
            "trade_intent_guard_snapshot_ttl_ms": resolved_snapshot_ttl_ms,
            "trade_intent_guard_snapshot_liquidity_usd": resolved_liquidity_usd,
            "trade_intent_guard_snapshot_depth_near_touch": resolved_depth_near_touch,
            "trade_intent_guard_edge_after_fees_bps": resolved_edge,
            "trade_intent_guard_min_liquidity_usd": resolved_min_liquidity_usd,
            "trade_intent_guard_min_depth_near_touch": resolved_min_depth_near_touch,
            "trade_intent_guard_min_edge_after_fees_bps": resolved_min_edge_after_fees_bps,
            "trade_intent_guard_resolution_policy_completeness_score": resolution_completeness_score,
            "trade_intent_guard_resolution_policy_coherence_score": resolution_coherence_score,
            "trade_intent_guard_resolution_threshold": resolution_threshold or None,
            "trade_intent_guard_payout_compatibility_score": payout_compatibility_score,
            "trade_intent_guard_currency_compatibility_score": currency_compatibility_score,
            "trade_intent_guard_payout_threshold": payout_threshold or None,
            "trade_intent_guard_currency_threshold": currency_threshold or None,
            "trade_intent_guard_venue_health_status": venue_health_status,
            "trade_intent_guard_projection_verdict": projection_verdict,
            "trade_intent_guard_readiness_route": readiness_route,
        }

        guarded_trade_intent = trade_intent.model_copy(
            update={
                "manual_review_required": manual_review_required,
                "no_trade_reasons": _dedupe(list(trade_intent.no_trade_reasons) + blocked_reasons),
                "metadata": guarded_metadata,
            }
        )

        report = TradeIntentGuardReport(
            intent_id=trade_intent.intent_id,
            run_id=trade_intent.run_id,
            market_id=trade_intent.market_id,
            venue=trade_intent.venue.value,
            verdict=verdict,
            can_execute=can_execute,
            manual_review_required=manual_review_required,
            blocked_reasons=blocked_reasons,
            warning_reasons=warning_reasons,
            snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
            snapshot_staleness_ms=snapshot_staleness_ms,
            edge_after_fees_bps=resolved_edge,
            venue_health_status=venue_health_status,
            projection_id=projection.projection_id if projection is not None else None,
            projection_verdict=projection_verdict,
            readiness_id=readiness_id,
            readiness_route=readiness_route,
            summary=summary,
            guarded_trade_intent=guarded_trade_intent,
            metadata={
                **resolved_metadata,
                "trade_intent_guard_id": None,
                "trade_intent_guard_verdict": verdict.value,
                "trade_intent_guard_blocked_reasons": list(blocked_reasons),
                "trade_intent_guard_warning_reasons": list(warning_reasons),
                "trade_intent_guard_summary": summary,
                "trade_intent_guard_snapshot_staleness_ms": snapshot_staleness_ms,
                "trade_intent_guard_snapshot_ttl_ms": resolved_snapshot_ttl_ms,
                "trade_intent_guard_snapshot_liquidity_usd": resolved_liquidity_usd,
                "trade_intent_guard_snapshot_depth_near_touch": resolved_depth_near_touch,
                "trade_intent_guard_edge_after_fees_bps": resolved_edge,
                "trade_intent_guard_min_liquidity_usd": resolved_min_liquidity_usd,
                "trade_intent_guard_min_depth_near_touch": resolved_min_depth_near_touch,
                "trade_intent_guard_min_edge_after_fees_bps": resolved_min_edge_after_fees_bps,
                "trade_intent_guard_resolution_policy_completeness_score": resolution_completeness_score,
                "trade_intent_guard_resolution_policy_coherence_score": resolution_coherence_score,
                "trade_intent_guard_resolution_threshold": resolution_threshold or None,
                "trade_intent_guard_payout_compatibility_score": payout_compatibility_score,
                "trade_intent_guard_currency_compatibility_score": currency_compatibility_score,
                "trade_intent_guard_payout_threshold": payout_threshold or None,
                "trade_intent_guard_currency_threshold": currency_threshold or None,
                "trade_intent_guard_venue_health_status": venue_health_status,
                "trade_intent_guard_projection_verdict": projection_verdict,
                "trade_intent_guard_readiness_route": readiness_route,
            },
        )
        report.metadata["trade_intent_guard_id"] = report.guard_id
        report.guarded_trade_intent.metadata["trade_intent_guard_id"] = report.guard_id
        return report


def evaluate_trade_intent_guard(
    trade_intent: TradeIntent,
    *,
    snapshot: MarketSnapshot | None = None,
    readiness: ExecutionReadiness | None = None,
    projection: ExecutionProjection | None = None,
    venue_health: VenueHealthReport | None = None,
    edge_after_fees_bps: float | None = None,
    metadata: Mapping[str, Any] | None = None,
    constraints: TradeIntentGuardConstraints | None = None,
) -> TradeIntentGuardReport:
    return TradeIntentGuard(constraints=constraints).evaluate(
        trade_intent,
        snapshot=snapshot,
        readiness=readiness,
        projection=projection,
        venue_health=venue_health,
        edge_after_fees_bps=edge_after_fees_bps,
        metadata=metadata,
    )
