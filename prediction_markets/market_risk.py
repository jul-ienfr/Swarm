from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .models import CapitalLedgerSnapshot, DecisionAction, ForecastPacket, MarketDescriptor, MarketRecommendationPacket, MarketSnapshot, MarketStatus, VenueName


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    blocker = "blocker"


class RiskConstraints(BaseModel):
    schema_version: str = "v1"
    min_edge_after_fees_bps: float = Field(default=35.0, validation_alias=AliasChoices("min_edge_after_fees_bps", "min_edge_bps"))
    min_confidence: float = 0.55
    min_liquidity_usd: float = Field(default=1_000.0, validation_alias=AliasChoices("min_liquidity_usd", "min_liquidity"))
    min_depth_near_touch: float = 0.0
    max_spread_bps: float = 500.0
    snapshot_ttl_ms: int = Field(default=120_000, validation_alias=AliasChoices("snapshot_ttl_ms", "max_snapshot_staleness_ms"))
    max_position_fraction_of_equity: float = 0.05
    max_theme_fraction_of_equity: float = 0.12
    max_correlation_fraction_of_equity: float = 0.18
    max_liquidity_fraction_of_equity: float = 0.08
    min_equity: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "min_edge_after_fees_bps",
        "min_liquidity_usd",
        "min_depth_near_touch",
        "max_spread_bps",
        "min_equity",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))

    @field_validator(
        "min_confidence",
        "max_position_fraction_of_equity",
        "max_theme_fraction_of_equity",
        "max_correlation_fraction_of_equity",
        "max_liquidity_fraction_of_equity",
    )
    @classmethod
    def _bounded_fraction(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("snapshot_ttl_ms")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @property
    def min_edge_bps(self) -> float:
        return self.min_edge_after_fees_bps

    @property
    def min_liquidity(self) -> float:
        return self.min_liquidity_usd

    @property
    def max_snapshot_staleness_ms(self) -> int:
        return self.snapshot_ttl_ms


class MarketRiskReport(BaseModel):
    schema_version: str = "v1"
    risk_id: str = Field(default_factory=lambda: f"risk_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    should_trade: bool = False
    approved: bool = False
    risk_level: RiskLevel = RiskLevel.high
    risk_score: float = 1.0
    theme_key: str = ""
    correlation_key: str = ""
    current_market_exposure: float = 0.0
    current_theme_exposure: float = 0.0
    current_correlation_exposure: float = 0.0
    max_position_fraction_of_equity: float = 0.0
    max_theme_fraction_of_equity: float = 0.0
    max_correlation_fraction_of_equity: float = 0.0
    max_liquidity_fraction_of_equity: float = 0.0
    max_market_notional: float = 0.0
    max_theme_notional: float = 0.0
    max_correlation_notional: float = 0.0
    max_liquidity_notional: float = 0.0
    max_allowed_notional: float = 0.0
    available_equity: float = 0.0
    no_trade_reasons: list[str] = Field(default_factory=list)
    cap_reasons: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    recommendation_action: DecisionAction | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("risk_score")
    @classmethod
    def _clamp_risk_score(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


@dataclass
class MarketRiskEvaluator:
    constraints: RiskConstraints | None = None

    def __post_init__(self) -> None:
        self.constraints = self.constraints or RiskConstraints()

    def assess(
        self,
        market: MarketDescriptor,
        snapshot: MarketSnapshot,
        recommendation: MarketRecommendationPacket | None = None,
        forecast: ForecastPacket | None = None,
        ledger: CapitalLedgerSnapshot | None = None,
        market_lookup: Mapping[str, MarketDescriptor] | None = None,
        run_id: str | None = None,
    ) -> MarketRiskReport:
        constraints = self.constraints or RiskConstraints()
        run_id = run_id or (recommendation.run_id if recommendation is not None else (forecast.run_id if forecast is not None else f"risk_{uuid4().hex[:12]}"))
        equity, available_cash = _ledger_capacity(ledger)
        theme_key = _theme_key(market)
        correlation_key = _correlation_key(market)
        current_market_exposure = _current_exposure(
            ledger=ledger,
            market_lookup=market_lookup,
            target_key=market.market_id,
            key_fn=lambda descriptor: descriptor.market_id,
        )
        current_theme_exposure = _current_exposure(
            ledger=ledger,
            market_lookup=market_lookup,
            target_key=theme_key,
            key_fn=_theme_key,
        )
        current_correlation_exposure = _current_exposure(
            ledger=ledger,
            market_lookup=market_lookup,
            target_key=correlation_key,
            key_fn=_correlation_key,
        )

        max_market_notional = equity * constraints.max_position_fraction_of_equity
        max_theme_notional = equity * constraints.max_theme_fraction_of_equity
        max_correlation_notional = equity * constraints.max_correlation_fraction_of_equity
        max_liquidity_notional = (snapshot.liquidity or 0.0) * constraints.max_liquidity_fraction_of_equity
        max_allowed_notional = max(
            0.0,
            min(
                available_cash,
                max_market_notional - current_market_exposure,
                max_theme_notional - current_theme_exposure,
                max_correlation_notional - current_correlation_exposure,
                max_liquidity_notional,
            ),
        )

        no_trade_reasons: list[str] = []
        cap_reasons: list[str] = []
        signals: list[str] = []
        effective_edge_bps = _effective_edge_bps(recommendation, forecast)
        forecast_snapshot_reliable, forecast_resolution_reliable, snapshot_reliability_reasons, resolution_reliability_reasons, forecast_metadata = _forecast_surface_flags(forecast)
        market_price_reference, market_alignment, market_price_source = _market_alignment_gap(forecast_metadata)

        if not forecast_snapshot_reliable:
            no_trade_reasons.append("snapshot_unreliable")
            no_trade_reasons.extend(f"snapshot_unreliable:{reason}" for reason in snapshot_reliability_reasons)
        if not forecast_resolution_reliable:
            no_trade_reasons.append("resolution_unreliable")
            no_trade_reasons.extend(f"resolution_unreliable:{reason}" for reason in resolution_reliability_reasons)
        if forecast is not None and forecast.manual_review_required:
            no_trade_reasons.append("forecast_manual_review_required")
        if forecast is not None and not forecast_metadata.get("paper_eligible", True):
            no_trade_reasons.append("paper_ineligible")
        if equity < constraints.min_equity:
            no_trade_reasons.append(f"equity_below_minimum:{equity:.2f}")
        if market.status not in {MarketStatus.open, MarketStatus.unknown} or snapshot.status not in {MarketStatus.open, MarketStatus.unknown}:
            no_trade_reasons.append(f"market_not_open:{snapshot.status.value}")
        if recommendation is not None and recommendation.action != DecisionAction.bet:
            no_trade_reasons.append(f"recommendation_action:{recommendation.action.value}")
        if effective_edge_bps is not None and effective_edge_bps < constraints.min_edge_after_fees_bps:
            no_trade_reasons.append(f"edge_below_minimum:{effective_edge_bps:.2f}")
        if recommendation is not None and recommendation.confidence < constraints.min_confidence:
            no_trade_reasons.append(f"confidence_below_minimum:{recommendation.confidence:.2f}")
        if snapshot.liquidity is not None and snapshot.liquidity < constraints.min_liquidity_usd:
            no_trade_reasons.append(f"liquidity_below_minimum:{snapshot.liquidity:.2f}")
        if snapshot.depth_near_touch is not None and snapshot.depth_near_touch < constraints.min_depth_near_touch:
            no_trade_reasons.append(f"depth_near_touch_below_minimum:{snapshot.depth_near_touch:.2f}")
        if snapshot.spread_bps is not None and snapshot.spread_bps > constraints.max_spread_bps:
            no_trade_reasons.append(f"spread_above_maximum:{snapshot.spread_bps:.2f}")
        if snapshot.staleness_ms is not None and snapshot.staleness_ms > constraints.snapshot_ttl_ms:
            no_trade_reasons.append(f"snapshot_stale:{snapshot.staleness_ms}")

        if current_market_exposure >= max_market_notional > 0:
            cap_reasons.append(f"market_cap_reached:{current_market_exposure:.2f}/{max_market_notional:.2f}")
        if current_theme_exposure >= max_theme_notional > 0:
            cap_reasons.append(f"theme_cap_reached:{current_theme_exposure:.2f}/{max_theme_notional:.2f}")
        if current_correlation_exposure >= max_correlation_notional > 0:
            cap_reasons.append(f"correlation_cap_reached:{current_correlation_exposure:.2f}/{max_correlation_notional:.2f}")
        if max_liquidity_notional <= 0:
            cap_reasons.append("liquidity_cap_zero")

        if recommendation is not None:
            signals.append(f"action={recommendation.action.value}")
            if recommendation.side is not None:
                signals.append(f"side={recommendation.side.value}")
            if recommendation.edge_bps is not None:
                signals.append(f"edge_bps={recommendation.edge_bps:.2f}")
        if forecast is not None:
            signals.append(f"fair_probability={forecast.fair_probability:.3f}")
            signals.append(f"market_probability={forecast.market_implied_probability:.3f}")
        if effective_edge_bps is not None:
            signals.append(f"effective_edge_bps={effective_edge_bps:.2f}")
        signals.extend([f"liquidity={snapshot.liquidity or 0.0:.2f}", f"spread_bps={snapshot.spread_bps or 0.0:.2f}"])

        approved = not no_trade_reasons and not cap_reasons
        should_trade = approved
        risk_score = _risk_score(no_trade_reasons, cap_reasons, snapshot, recommendation, forecast)
        risk_level = _risk_level(risk_score, approved=approved)

        return MarketRiskReport(
            run_id=run_id,
            market_id=market.market_id,
            venue=market.venue,
            should_trade=should_trade,
            approved=approved,
            risk_level=risk_level,
            risk_score=risk_score,
            theme_key=theme_key,
            correlation_key=correlation_key,
            current_market_exposure=current_market_exposure,
            current_theme_exposure=current_theme_exposure,
            current_correlation_exposure=current_correlation_exposure,
            max_position_fraction_of_equity=constraints.max_position_fraction_of_equity,
            max_theme_fraction_of_equity=constraints.max_theme_fraction_of_equity,
            max_correlation_fraction_of_equity=constraints.max_correlation_fraction_of_equity,
            max_liquidity_fraction_of_equity=constraints.max_liquidity_fraction_of_equity,
            max_market_notional=max_market_notional,
            max_theme_notional=max_theme_notional,
            max_correlation_notional=max_correlation_notional,
            max_liquidity_notional=max_liquidity_notional,
            max_allowed_notional=max_allowed_notional,
            available_equity=available_cash,
            no_trade_reasons=_dedupe(no_trade_reasons),
            cap_reasons=_dedupe(cap_reasons),
            signals=_dedupe(signals),
            recommendation_action=recommendation.action if recommendation is not None else None,
            metadata={
                "equity": equity,
                "snapshot_ttl_ms": constraints.snapshot_ttl_ms,
                "min_liquidity_usd": constraints.min_liquidity_usd,
                "min_depth_near_touch": constraints.min_depth_near_touch,
                "min_edge_after_fees_bps": constraints.min_edge_after_fees_bps,
                "market_status": market.status.value,
                "snapshot_status": snapshot.status.value,
                "snapshot_reliable": forecast_snapshot_reliable,
                "resolution_reliable": forecast_resolution_reliable,
                "resolution_status": forecast_metadata.get("resolution_status"),
                "resolution_can_forecast": forecast_metadata.get("resolution_can_forecast"),
                "market_price_reference": market_price_reference,
                "market_price_reference_source": market_price_source,
                "market_alignment": market_alignment,
                "paper_eligible": forecast_metadata.get("paper_eligible", True),
                "snapshot_reliability_reasons": snapshot_reliability_reasons,
                "resolution_reliability_reasons": resolution_reliability_reasons,
            },
        )


def assess_market_risk(
    market: MarketDescriptor,
    snapshot: MarketSnapshot,
    recommendation: MarketRecommendationPacket | None = None,
    forecast: ForecastPacket | None = None,
    ledger: CapitalLedgerSnapshot | None = None,
    market_lookup: Mapping[str, MarketDescriptor] | None = None,
    run_id: str | None = None,
    constraints: RiskConstraints | None = None,
) -> MarketRiskReport:
    return MarketRiskEvaluator(constraints=constraints).assess(
        market=market,
        snapshot=snapshot,
        recommendation=recommendation,
        forecast=forecast,
        ledger=ledger,
        market_lookup=market_lookup,
        run_id=run_id,
    )


def _ledger_capacity(ledger: CapitalLedgerSnapshot | None) -> tuple[float, float]:
    if ledger is None:
        return 0.0, 0.0
    equity = ledger.equity or ledger.cash - ledger.reserved_cash + ledger.realized_pnl + ledger.unrealized_pnl
    available_cash = max(0.0, ledger.cash - ledger.reserved_cash)
    return max(0.0, float(equity)), max(0.0, float(available_cash))


def _current_exposure(
    *,
    ledger: CapitalLedgerSnapshot | None,
    market_lookup: Mapping[str, MarketDescriptor] | None,
    target_key: str,
    key_fn,
) -> float:
    if ledger is None:
        return 0.0
    total = 0.0
    for position in ledger.positions:
        descriptor = market_lookup.get(position.market_id) if market_lookup else None
        if descriptor is None:
            key = position.market_id
        else:
            key = key_fn(descriptor)
        if key != target_key:
            continue
        mark = position.mark_price if position.mark_price is not None else position.entry_price
        total += abs(float(position.quantity) * float(mark))
    return round(total, 6)


def _theme_key(descriptor: MarketDescriptor) -> str:
    if descriptor.category:
        return f"category:{descriptor.category.strip().lower()}"
    if descriptor.categories:
        return f"categories:{descriptor.categories[0].strip().lower()}"
    if descriptor.tags:
        return f"tag:{descriptor.tags[0].strip().lower()}"
    if descriptor.canonical_event_id:
        return f"event:{descriptor.canonical_event_id}"
    return f"market:{descriptor.market_id}"


def _correlation_key(descriptor: MarketDescriptor) -> str:
    if descriptor.canonical_event_id:
        return f"event:{descriptor.canonical_event_id}"
    if descriptor.source_url:
        return f"source:{descriptor.source_url}"
    return f"market:{descriptor.market_id}"


def _risk_score(
    no_trade_reasons: list[str],
    cap_reasons: list[str],
    snapshot: MarketSnapshot,
    recommendation: MarketRecommendationPacket | None,
    forecast: ForecastPacket | None,
) -> float:
    score = 0.12
    score += 0.16 * min(1.0, len(no_trade_reasons) / 5.0)
    score += 0.12 * min(1.0, len(cap_reasons) / 3.0)
    if snapshot.spread_bps is not None:
        score += min(0.15, snapshot.spread_bps / 5000.0)
    if snapshot.staleness_ms is not None:
        score += min(0.15, snapshot.staleness_ms / 180000.0)
    if snapshot.liquidity is not None:
        score += max(0.0, 0.12 - min(0.12, snapshot.liquidity / 250000.0))
    if recommendation is not None:
        score += max(0.0, 0.1 - recommendation.confidence * 0.05)
    if forecast is not None:
        score += max(0.0, 0.08 - abs(forecast.edge_bps) / 20000.0)
    return round(max(0.0, min(1.0, score)), 6)


def _effective_edge_bps(
    recommendation: MarketRecommendationPacket | None,
    forecast: ForecastPacket | None,
) -> float | None:
    if recommendation is not None and recommendation.edge_bps is not None:
        return float(recommendation.edge_bps)
    if forecast is not None:
        return float(forecast.edge_after_fees_bps if forecast.edge_after_fees_bps is not None else forecast.edge_bps)
    return None


def _normalized_surface_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _forecast_surface_flags(
    forecast: ForecastPacket | None,
) -> tuple[bool, bool, list[str], list[str], dict[str, Any]]:
    if forecast is None:
        return True, True, [], [], {}
    metadata = _normalized_surface_dict(getattr(forecast, "metadata", {}))
    snapshot_quality = _normalized_surface_dict(metadata.get("snapshot_quality"))
    snapshot_reliable = metadata.get("snapshot_reliable")
    resolution_reliable = metadata.get("resolution_reliable")
    snapshot_reasons = list(snapshot_quality.get("reliability_reasons") or metadata.get("snapshot_reliability_reasons") or [])
    resolution_reasons = list(metadata.get("resolution_reliability_reasons") or [])
    if snapshot_reliable is None:
        snapshot_reliable = bool(snapshot_quality.get("reliable", True))
    if resolution_reliable is None:
        resolution_reliable = not bool(metadata.get("resolution_manual_review_required") or metadata.get("requires_manual_review"))
        if metadata.get("resolution_status") not in {None, "clear"}:
            resolution_reliable = False
    if not snapshot_reasons and not snapshot_reliable:
        snapshot_reasons = ["snapshot_unreliable"]
    if not resolution_reasons and not resolution_reliable:
        resolution_reasons = ["resolution_unreliable"]
    return bool(snapshot_reliable), bool(resolution_reliable), snapshot_reasons, resolution_reasons, metadata


def _market_alignment_gap(metadata: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    reference = metadata.get("market_price_reference")
    alignment = metadata.get("market_alignment")
    source = metadata.get("market_price_reference_source")
    try:
        if reference is None:
            return None, alignment, source
        return float(reference), alignment, source
    except (TypeError, ValueError):
        return None, alignment, source


def _risk_level(score: float, *, approved: bool) -> RiskLevel:
    if not approved:
        if score >= 0.85:
            return RiskLevel.blocker
        if score >= 0.65:
            return RiskLevel.high
        return RiskLevel.medium
    if score < 0.3:
        return RiskLevel.low
    if score < 0.55:
        return RiskLevel.medium
    return RiskLevel.high


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
