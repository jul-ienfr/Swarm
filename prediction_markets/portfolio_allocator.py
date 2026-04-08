from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .capital_ledger import CapitalControlState, CapitalLedger
from .market_risk import MarketRiskReport
from .models import CapitalLedgerSnapshot, DecisionAction, ForecastPacket, MarketDescriptor, MarketRecommendationPacket, MarketSnapshot, TradeSide, VenueName


class AllocationMode(str, Enum):
    single = "single"
    batch = "batch"


class AllocationConstraints(BaseModel):
    schema_version: str = "v1"
    max_portfolio_fraction_of_equity: float = 0.15
    min_trade_notional: float = 5.0
    kelly_scale: float = 0.5
    confidence_weight_floor: float = 0.25
    liquidity_target: float = 50_000.0
    max_liquidity_fraction_of_equity: float = 0.08
    min_free_cash_buffer_pct: float = 0.0
    per_venue_balance_cap_usd: float = 0.0
    max_market_exposure_usd: float = 0.0
    max_theme_exposure_pct: float = 0.0
    max_open_positions: int = 0
    max_daily_loss_usd: float = 0.0
    min_resolved_markets_for_live: int = 0
    cap_buffer: float = 0.95
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "max_portfolio_fraction_of_equity",
        "kelly_scale",
        "confidence_weight_floor",
        "max_liquidity_fraction_of_equity",
        "min_free_cash_buffer_pct",
        "max_theme_exposure_pct",
    )
    @classmethod
    def _bounded_fraction(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator(
        "min_trade_notional",
        "liquidity_target",
        "per_venue_balance_cap_usd",
        "max_market_exposure_usd",
        "max_daily_loss_usd",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))

    @field_validator("cap_buffer")
    @classmethod
    def _bounded_cap_buffer(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("max_open_positions")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator("min_resolved_markets_for_live")
    @classmethod
    def _non_negative_min_resolved(cls, value: int) -> int:
        return max(0, int(value))


class AllocationRequest(BaseModel):
    schema_version: str = "v1"
    run_id: str
    market: MarketDescriptor
    snapshot: MarketSnapshot
    forecast: ForecastPacket
    recommendation: MarketRecommendationPacket
    risk_report: MarketRiskReport
    metadata: dict[str, Any] = Field(default_factory=dict)


class AllocationDecision(BaseModel):
    schema_version: str = "v1"
    allocation_id: str = Field(default_factory=lambda: f"alloc_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    mode: AllocationMode = AllocationMode.single
    action: DecisionAction = DecisionAction.no_trade
    side: TradeSide | None = None
    should_trade: bool = False
    recommended_stake: float = 0.0
    recommended_fraction: float = 0.0
    raw_kelly_fraction: float = 0.0
    confidence_weight: float = 0.0
    liquidity_weight: float = 0.0
    max_stake: float = 0.0
    market_cap_stake: float = 0.0
    theme_cap_stake: float = 0.0
    correlation_cap_stake: float = 0.0
    liquidity_cap_stake: float = 0.0
    available_cash: float = 0.0
    min_free_cash_buffer_pct: float = 0.0
    per_venue_balance_cap_usd: float = 0.0
    max_market_exposure_usd: float = 0.0
    max_theme_exposure_pct: float = 0.0
    max_open_positions: int = 0
    max_daily_loss_usd: float = 0.0
    current_market_exposure_usd: float = 0.0
    current_theme_exposure_usd: float = 0.0
    current_correlation_exposure_usd: float = 0.0
    market_exposure_room_usd: float = 0.0
    theme_exposure_room_usd: float = 0.0
    correlation_exposure_room_usd: float = 0.0
    open_position_count: int = 0
    open_position_room: int = 0
    manual_review_count: int = 0
    capital_fragmentation_score: float = 0.0
    capital_concentration_score: float = 0.0
    resolved_markets_count: int = 0
    min_resolved_markets_for_live: int = 0
    live_promotion_ready: bool = False
    promotion_stage: str = "blocked"
    no_trade_reasons: list[str] = Field(default_factory=list)
    allocation_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "recommended_stake",
        "recommended_fraction",
        "raw_kelly_fraction",
        "confidence_weight",
        "liquidity_weight",
        "max_stake",
        "market_cap_stake",
        "theme_cap_stake",
        "correlation_cap_stake",
        "liquidity_cap_stake",
        "available_cash",
        "min_free_cash_buffer_pct",
        "per_venue_balance_cap_usd",
        "max_market_exposure_usd",
        "max_theme_exposure_pct",
        "max_daily_loss_usd",
        "current_market_exposure_usd",
        "current_theme_exposure_usd",
        "current_correlation_exposure_usd",
        "market_exposure_room_usd",
        "theme_exposure_room_usd",
        "correlation_exposure_room_usd",
        "capital_fragmentation_score",
        "capital_concentration_score",
        "resolved_markets_count",
        "min_resolved_markets_for_live",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))

    @field_validator("max_open_positions", "manual_review_count")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator("resolved_markets_count", "min_resolved_markets_for_live")
    @classmethod
    def _non_negative_counts(cls, value: int) -> int:
        return max(0, int(value))


class AllocationPlan(BaseModel):
    schema_version: str = "v1"
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:12]}")
    run_id: str | None = None
    mode: AllocationMode = AllocationMode.batch
    equity: float = 0.0
    available_cash: float = 0.0
    total_allocated: float = 0.0
    total_requested: float = 0.0
    decisions: list[AllocationDecision] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class PortfolioAllocator:
    constraints: AllocationConstraints | None = None

    def __post_init__(self) -> None:
        self.constraints = self.constraints or AllocationConstraints()

    def allocate(
        self,
        request: AllocationRequest,
        ledger: CapitalLedgerSnapshot | None = None,
        market_lookup: Mapping[str, MarketDescriptor] | None = None,
    ) -> AllocationDecision:
        constraints = self.constraints or AllocationConstraints()
        resolved_markets_count = _resolved_markets_count(request, ledger)
        live_promotion_ready = constraints.min_resolved_markets_for_live <= 0 or resolved_markets_count >= constraints.min_resolved_markets_for_live
        promotion_stage = _promotion_stage(request=request, live_promotion_ready=live_promotion_ready)
        equity, available_cash, capital_control_state = _ledger_capacity(
            ledger,
            market_id=request.market.market_id,
            venue=request.market.venue,
            constraints=constraints,
        )
        cap_buffer = constraints.cap_buffer
        available_cash_cap = min(available_cash, capital_control_state.capital_available_usd)
        current_market_exposure = max(0.0, float(request.risk_report.current_market_exposure))
        current_theme_exposure = max(0.0, float(request.risk_report.current_theme_exposure))
        current_correlation_exposure = max(0.0, float(request.risk_report.current_correlation_exposure))
        market_cap_room = max(0.0, request.risk_report.max_market_notional - current_market_exposure)
        if constraints.max_market_exposure_usd > 0.0:
            market_cap_room = min(
                market_cap_room,
                max(0.0, constraints.max_market_exposure_usd - current_market_exposure),
            )
        theme_exposure_pct = constraints.max_theme_exposure_pct if constraints.max_theme_exposure_pct > 0.0 else request.risk_report.max_theme_fraction_of_equity
        theme_cap = equity * theme_exposure_pct
        correlation_cap = request.risk_report.max_correlation_notional
        liquidity_cap = min(request.risk_report.max_liquidity_notional, equity * constraints.max_liquidity_fraction_of_equity)
        market_exposure_room = market_cap_room
        theme_exposure_room = max(0.0, theme_cap - current_theme_exposure)
        correlation_exposure_room = max(0.0, correlation_cap - current_correlation_exposure)
        if not request.risk_report.should_trade or request.recommendation.action != DecisionAction.bet:
            return _zero_decision(
                request=request,
                available_cash=available_cash_cap,
                reasons=_dedupe(
                    list(request.risk_report.no_trade_reasons)
                    + list(request.risk_report.cap_reasons)
                    + list(request.recommendation.why_not_now)
                    + list(capital_control_state.freeze_reasons)
                ),
                mode=AllocationMode.single,
                min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
                per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
                max_market_exposure_usd=constraints.max_market_exposure_usd,
                max_theme_exposure_pct=constraints.max_theme_exposure_pct,
                max_open_positions=constraints.max_open_positions,
                max_daily_loss_usd=constraints.max_daily_loss_usd,
                resolved_markets_count=resolved_markets_count,
                min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
                live_promotion_ready=live_promotion_ready,
                promotion_stage=promotion_stage,
                capital_control_state=capital_control_state,
                cap_buffer=cap_buffer,
                current_market_exposure_usd=current_market_exposure,
                current_theme_exposure_usd=current_theme_exposure,
                current_correlation_exposure_usd=current_correlation_exposure,
                market_exposure_room_usd=market_exposure_room,
                theme_exposure_room_usd=theme_exposure_room,
                correlation_exposure_room_usd=correlation_exposure_room,
                open_position_count=capital_control_state.open_position_count,
                open_position_room=capital_control_state.open_position_room,
                manual_review_count=capital_control_state.manual_review_count,
                capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
                capital_concentration_score=capital_control_state.capital_concentration_score,
            )
        raw_kelly = _kelly_fraction(
            price=request.recommendation.price_reference or request.snapshot.market_implied_probability or 0.5,
            probability=request.forecast.fair_probability,
            side=request.recommendation.side,
        )
        confidence_weight = max(constraints.confidence_weight_floor, float(request.recommendation.confidence))
        liquidity_weight = _liquidity_weight(request.snapshot.liquidity, constraints.liquidity_target)
        edge_weight = min(1.0, max(0.0, (request.recommendation.edge_bps or 0.0) / 500.0))
        base_fraction = raw_kelly * constraints.kelly_scale * confidence_weight * liquidity_weight * max(0.25, edge_weight)
        market_cap_stake = max(0.0, market_cap_room)
        theme_cap_stake = max(0.0, theme_cap - request.risk_report.current_theme_exposure)
        correlation_cap_stake = max(0.0, correlation_cap - request.risk_report.current_correlation_exposure)
        raw_max_stake = min(
            available_cash_cap,
            market_cap_stake,
            theme_cap_stake,
            correlation_cap_stake,
            liquidity_cap,
            equity * constraints.max_portfolio_fraction_of_equity,
        )
        max_stake = _apply_cap_buffer(raw_max_stake, cap_buffer)
        recommended_stake = min(max_stake, equity * base_fraction)
        if recommended_stake < constraints.min_trade_notional:
            return _zero_decision(
                request=request,
                available_cash=available_cash_cap,
                reasons=[
                    f"stake_below_minimum:{recommended_stake:.2f}",
                    *request.recommendation.why_not_now,
                    *capital_control_state.freeze_reasons,
                ],
                mode=AllocationMode.single,
                max_stake=max_stake,
                market_cap_stake=market_cap_stake,
                theme_cap_stake=theme_cap_stake,
                correlation_cap_stake=correlation_cap_stake,
                liquidity_cap_stake=liquidity_cap,
                raw_kelly_fraction=raw_kelly,
                confidence_weight=confidence_weight,
                liquidity_weight=liquidity_weight,
                min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
                per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
                max_market_exposure_usd=constraints.max_market_exposure_usd,
                max_open_positions=constraints.max_open_positions,
                max_daily_loss_usd=constraints.max_daily_loss_usd,
                current_market_exposure_usd=current_market_exposure,
                current_theme_exposure_usd=current_theme_exposure,
                current_correlation_exposure_usd=current_correlation_exposure,
                market_exposure_room_usd=market_exposure_room,
                theme_exposure_room_usd=theme_exposure_room,
                correlation_exposure_room_usd=correlation_exposure_room,
                open_position_count=capital_control_state.open_position_count,
                open_position_room=capital_control_state.open_position_room,
                manual_review_count=capital_control_state.manual_review_count,
                capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
                capital_concentration_score=capital_control_state.capital_concentration_score,
                resolved_markets_count=resolved_markets_count,
                min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
                live_promotion_ready=live_promotion_ready,
                promotion_stage=promotion_stage,
                capital_control_state=capital_control_state,
                cap_buffer=cap_buffer,
            )

        return AllocationDecision(
            run_id=request.run_id,
            market_id=request.market.market_id,
            venue=request.market.venue,
            mode=AllocationMode.single,
            action=DecisionAction.bet,
            side=request.recommendation.side,
            should_trade=True,
            recommended_stake=round(recommended_stake, 2),
            recommended_fraction=round(recommended_stake / equity, 6) if equity > 0 else 0.0,
            raw_kelly_fraction=round(raw_kelly, 6),
            confidence_weight=round(confidence_weight, 6),
            liquidity_weight=round(liquidity_weight, 6),
            max_stake=round(max_stake, 2),
            market_cap_stake=round(market_cap_stake, 2),
            theme_cap_stake=round(theme_cap_stake, 2),
            correlation_cap_stake=round(correlation_cap_stake, 2),
            liquidity_cap_stake=round(liquidity_cap, 2),
            available_cash=round(available_cash_cap, 2),
            min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
            per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
            max_market_exposure_usd=constraints.max_market_exposure_usd,
            max_theme_exposure_pct=theme_exposure_pct,
            max_open_positions=constraints.max_open_positions,
            max_daily_loss_usd=constraints.max_daily_loss_usd,
            current_market_exposure_usd=current_market_exposure,
            current_theme_exposure_usd=current_theme_exposure,
            current_correlation_exposure_usd=current_correlation_exposure,
            market_exposure_room_usd=market_exposure_room,
            theme_exposure_room_usd=theme_exposure_room,
            correlation_exposure_room_usd=correlation_exposure_room,
            open_position_count=capital_control_state.open_position_count,
            open_position_room=capital_control_state.open_position_room,
            manual_review_count=capital_control_state.manual_review_count,
            capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
            capital_concentration_score=capital_control_state.capital_concentration_score,
            resolved_markets_count=resolved_markets_count,
            min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
            live_promotion_ready=live_promotion_ready,
            promotion_stage=promotion_stage,
            allocation_reasons=[
                f"kelly_fraction={raw_kelly:.4f}",
                f"confidence_weight={confidence_weight:.3f}",
                f"liquidity_weight={liquidity_weight:.3f}",
                f"edge_bps={request.recommendation.edge_bps or 0.0:.2f}",
                f"cap_buffer={cap_buffer:.3f}",
                f"capital_available_usd={capital_control_state.capital_available_usd:.2f}",
                f"resolved_markets_count={resolved_markets_count}",
                f"min_resolved_markets_for_live={constraints.min_resolved_markets_for_live}",
                f"promotion_stage={promotion_stage}",
            ],
            metadata={
                "equity": equity,
                "market_lookup_used": bool(market_lookup),
                "risk_report_id": request.risk_report.risk_id,
                "capital_control_state": capital_control_state.model_dump(mode="json"),
                "current_market_exposure_usd": current_market_exposure,
                "current_theme_exposure_usd": current_theme_exposure,
                "current_correlation_exposure_usd": current_correlation_exposure,
                "market_exposure_room_usd": market_exposure_room,
                "theme_exposure_room_usd": theme_exposure_room,
                "correlation_exposure_room_usd": correlation_exposure_room,
                "open_position_count": capital_control_state.open_position_count,
                "open_position_room": capital_control_state.open_position_room,
                "manual_review_count": capital_control_state.manual_review_count,
                "capital_fragmentation_score": capital_control_state.capital_fragmentation_score,
                "capital_concentration_score": capital_control_state.capital_concentration_score,
                "cap_buffer": cap_buffer,
                "resolved_markets_count": resolved_markets_count,
                "min_resolved_markets_for_live": constraints.min_resolved_markets_for_live,
                "live_promotion_ready": live_promotion_ready,
                "promotion_stage": promotion_stage,
            },
        )

    def allocate_many(
        self,
        requests: list[AllocationRequest],
        ledger: CapitalLedgerSnapshot | None = None,
        market_lookup: Mapping[str, MarketDescriptor] | None = None,
    ) -> AllocationPlan:
        constraints = self.constraints or AllocationConstraints()
        equity, available_cash, _ = _ledger_capacity(ledger, constraints=constraints)
        working_exposures = _initial_exposures(ledger, market_lookup)
        open_markets = _initial_open_markets(ledger)
        cap_buffer = constraints.cap_buffer
        ordered = sorted(requests, key=_priority_score, reverse=True)
        decisions: list[AllocationDecision] = []
        total_allocated = 0.0
        total_requested = 0.0
        for request in ordered:
            total_requested += request.recommendation.price_reference or 0.0
            if constraints.max_open_positions > 0 and request.market.market_id not in open_markets and len(open_markets) >= constraints.max_open_positions:
                capital_control_state = _capital_control_state(
                    ledger,
                    market_id=request.market.market_id,
                    venue=request.market.venue,
                    constraints=constraints,
                )
                current_market_exposure = max(0.0, float(request.risk_report.current_market_exposure))
                current_theme_exposure = max(0.0, float(request.risk_report.current_theme_exposure))
                current_correlation_exposure = max(0.0, float(request.risk_report.current_correlation_exposure))
                decisions.append(
                    _zero_decision(
                        request=request,
                        available_cash=_apply_cap_buffer(max(0.0, available_cash - total_allocated), cap_buffer),
                        reasons=[f"max_open_positions_exceeded:{len(open_markets)}/{constraints.max_open_positions}"],
                        mode=AllocationMode.batch,
                        min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
                        per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
                        max_market_exposure_usd=constraints.max_market_exposure_usd,
                        max_open_positions=constraints.max_open_positions,
                        max_daily_loss_usd=constraints.max_daily_loss_usd,
                        capital_control_state=capital_control_state,
                        cap_buffer=cap_buffer,
                        current_market_exposure_usd=current_market_exposure,
                        current_theme_exposure_usd=current_theme_exposure,
                        current_correlation_exposure_usd=current_correlation_exposure,
                        open_position_count=capital_control_state.open_position_count,
                        open_position_room=capital_control_state.open_position_room,
                        manual_review_count=capital_control_state.manual_review_count,
                        capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
                        capital_concentration_score=capital_control_state.capital_concentration_score,
                    )
                )
                continue
            decision = self._allocate_with_state(
                request,
                equity=equity,
                available_cash=available_cash - total_allocated,
                working_exposures=working_exposures,
                capital_control_state=_capital_control_state(
                    ledger,
                    market_id=request.market.market_id,
                    venue=request.market.venue,
                    constraints=constraints,
                ),
                cap_buffer=cap_buffer,
            )
            decisions.append(decision)
            total_allocated += decision.recommended_stake
            if decision.recommended_stake > 0:
                _apply_exposure(
                    working_exposures,
                    request.market,
                    decision.recommended_stake,
                )
                if request.market.market_id not in open_markets:
                    open_markets.add(request.market.market_id)
        return AllocationPlan(
            run_id=requests[0].run_id if requests else None,
            mode=AllocationMode.batch,
            equity=equity,
            available_cash=available_cash,
            total_allocated=round(total_allocated, 2),
            total_requested=round(total_requested, 2),
            decisions=decisions,
            metadata={"request_count": len(requests)},
        )

    def _allocate_with_state(
        self,
        request: AllocationRequest,
        *,
        equity: float,
        available_cash: float,
        working_exposures: dict[str, float],
        capital_control_state: CapitalControlState | None = None,
        cap_buffer: float = 1.0,
    ) -> AllocationDecision:
        constraints = self.constraints or AllocationConstraints()
        capital_control_state = capital_control_state or CapitalControlState()
        resolved_markets_count = _resolved_markets_count(request, None)
        live_promotion_ready = constraints.min_resolved_markets_for_live <= 0 or resolved_markets_count >= constraints.min_resolved_markets_for_live
        promotion_stage = _promotion_stage(request=request, live_promotion_ready=live_promotion_ready)
        theme_key = _theme_key(request.market)
        correlation_key = _correlation_key(request.market)
        current_market = working_exposures.get(f"market:{request.market.market_id}", 0.0)
        current_theme = working_exposures.get(f"theme:{theme_key}", 0.0)
        current_correlation = working_exposures.get(f"correlation:{correlation_key}", 0.0)
        market_cap = equity * request.risk_report.max_position_fraction_of_equity
        market_cap_room = max(0.0, market_cap - current_market)
        if constraints.max_market_exposure_usd > 0.0:
            market_cap_room = min(
                market_cap_room,
                max(0.0, constraints.max_market_exposure_usd - current_market),
            )
        theme_exposure_pct = constraints.max_theme_exposure_pct if constraints.max_theme_exposure_pct > 0.0 else request.risk_report.max_theme_fraction_of_equity
        theme_cap = equity * theme_exposure_pct
        correlation_cap = equity * request.risk_report.max_correlation_fraction_of_equity
        liquidity_cap = min(request.risk_report.max_liquidity_notional, equity * constraints.max_liquidity_fraction_of_equity)
        if not request.risk_report.should_trade or request.recommendation.action != DecisionAction.bet:
            return _zero_decision(
                request=request,
                available_cash=min(available_cash, capital_control_state.capital_available_usd),
                reasons=_dedupe(
                    list(request.risk_report.no_trade_reasons)
                    + list(request.risk_report.cap_reasons)
                    + list(request.recommendation.why_not_now)
                    + list(capital_control_state.freeze_reasons)
                ),
                mode=AllocationMode.batch,
                min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
                per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
                max_market_exposure_usd=constraints.max_market_exposure_usd,
                max_theme_exposure_pct=constraints.max_theme_exposure_pct,
                max_open_positions=constraints.max_open_positions,
                max_daily_loss_usd=constraints.max_daily_loss_usd,
                resolved_markets_count=resolved_markets_count,
                min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
                live_promotion_ready=live_promotion_ready,
                promotion_stage=promotion_stage,
                capital_control_state=capital_control_state,
                cap_buffer=cap_buffer,
                current_market_exposure_usd=current_market,
                current_theme_exposure_usd=current_theme,
                current_correlation_exposure_usd=current_correlation,
                market_exposure_room_usd=market_cap_room,
                theme_exposure_room_usd=max(0.0, theme_cap - current_theme),
            correlation_exposure_room_usd=max(0.0, correlation_cap - current_correlation),
            open_position_count=capital_control_state.open_position_count,
            open_position_room=capital_control_state.open_position_room,
            manual_review_count=capital_control_state.manual_review_count,
            capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
                capital_concentration_score=capital_control_state.capital_concentration_score,
            )
        raw_kelly = _kelly_fraction(
            price=request.recommendation.price_reference or request.snapshot.market_implied_probability or 0.5,
            probability=request.forecast.fair_probability,
            side=request.recommendation.side,
        )
        confidence_weight = max(constraints.confidence_weight_floor, float(request.recommendation.confidence))
        liquidity_weight = _liquidity_weight(request.snapshot.liquidity, constraints.liquidity_target)
        edge_weight = min(1.0, max(0.0, (request.recommendation.edge_bps or 0.0) / 500.0))
        base_fraction = raw_kelly * constraints.kelly_scale * confidence_weight * liquidity_weight * max(0.25, edge_weight)
        market_cap_stake = max(0.0, market_cap_room)
        theme_cap_stake = max(0.0, theme_cap - current_theme)
        correlation_cap_stake = max(0.0, correlation_cap - current_correlation)
        raw_max_stake = min(
            min(available_cash, capital_control_state.capital_available_usd),
            market_cap_stake,
            theme_cap_stake,
            correlation_cap_stake,
            liquidity_cap,
            equity * constraints.max_portfolio_fraction_of_equity,
        )
        max_stake = _apply_cap_buffer(raw_max_stake, cap_buffer)
        recommended_stake = min(max_stake, equity * base_fraction)
        if recommended_stake < constraints.min_trade_notional:
            return _zero_decision(
                request=request,
                available_cash=min(available_cash, capital_control_state.capital_available_usd),
                reasons=[
                    f"stake_below_minimum:{recommended_stake:.2f}",
                    *request.recommendation.why_not_now,
                    *capital_control_state.freeze_reasons,
                ],
                mode=AllocationMode.batch,
                max_stake=max_stake,
                market_cap_stake=market_cap_stake,
                theme_cap_stake=theme_cap_stake,
                correlation_cap_stake=correlation_cap_stake,
                liquidity_cap_stake=liquidity_cap,
                raw_kelly_fraction=raw_kelly,
                confidence_weight=confidence_weight,
                liquidity_weight=liquidity_weight,
                min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
                per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
                max_market_exposure_usd=constraints.max_market_exposure_usd,
                max_theme_exposure_pct=theme_exposure_pct,
                max_open_positions=constraints.max_open_positions,
                max_daily_loss_usd=constraints.max_daily_loss_usd,
                current_market_exposure_usd=current_market,
                current_theme_exposure_usd=current_theme,
                current_correlation_exposure_usd=current_correlation,
                market_exposure_room_usd=market_cap_room,
                theme_exposure_room_usd=max(0.0, theme_cap - current_theme),
                correlation_exposure_room_usd=max(0.0, correlation_cap - current_correlation),
                open_position_count=capital_control_state.open_position_count,
                open_position_room=capital_control_state.open_position_room,
                manual_review_count=capital_control_state.manual_review_count,
                capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
                capital_concentration_score=capital_control_state.capital_concentration_score,
                resolved_markets_count=resolved_markets_count,
                min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
                live_promotion_ready=live_promotion_ready,
                promotion_stage=promotion_stage,
                capital_control_state=capital_control_state,
                cap_buffer=cap_buffer,
            )

        return AllocationDecision(
            run_id=request.run_id,
            market_id=request.market.market_id,
            venue=request.market.venue,
            mode=AllocationMode.batch,
            action=DecisionAction.bet,
            side=request.recommendation.side,
            should_trade=True,
            recommended_stake=round(recommended_stake, 2),
            recommended_fraction=round(recommended_stake / equity, 6) if equity > 0 else 0.0,
            raw_kelly_fraction=round(raw_kelly, 6),
            confidence_weight=round(confidence_weight, 6),
            liquidity_weight=round(liquidity_weight, 6),
            max_stake=round(max_stake, 2),
            market_cap_stake=round(market_cap_stake, 2),
            theme_cap_stake=round(theme_cap_stake, 2),
            correlation_cap_stake=round(correlation_cap_stake, 2),
            liquidity_cap_stake=round(liquidity_cap, 2),
            available_cash=round(min(available_cash, capital_control_state.capital_available_usd), 2),
            min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
            per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
            max_market_exposure_usd=constraints.max_market_exposure_usd,
            max_theme_exposure_pct=theme_exposure_pct,
            max_open_positions=constraints.max_open_positions,
            max_daily_loss_usd=constraints.max_daily_loss_usd,
            current_market_exposure_usd=current_market,
            current_theme_exposure_usd=current_theme,
            current_correlation_exposure_usd=current_correlation,
            market_exposure_room_usd=market_cap_room,
            theme_exposure_room_usd=max(0.0, theme_cap - current_theme),
            correlation_exposure_room_usd=max(0.0, correlation_cap - current_correlation),
            open_position_count=capital_control_state.open_position_count,
            open_position_room=capital_control_state.open_position_room,
            manual_review_count=capital_control_state.manual_review_count,
            capital_fragmentation_score=capital_control_state.capital_fragmentation_score,
            capital_concentration_score=capital_control_state.capital_concentration_score,
            resolved_markets_count=resolved_markets_count,
            min_resolved_markets_for_live=constraints.min_resolved_markets_for_live,
            live_promotion_ready=live_promotion_ready,
            promotion_stage=promotion_stage,
            allocation_reasons=[
                f"kelly_fraction={raw_kelly:.4f}",
                f"confidence_weight={confidence_weight:.3f}",
                f"liquidity_weight={liquidity_weight:.3f}",
                f"edge_bps={request.recommendation.edge_bps or 0.0:.2f}",
                f"cap_buffer={cap_buffer:.3f}",
                f"priority={_priority_score(request):.4f}",
                f"max_theme_exposure_pct={theme_exposure_pct:.4f}",
                f"capital_available_usd={capital_control_state.capital_available_usd:.2f}",
                f"resolved_markets_count={resolved_markets_count}",
                f"min_resolved_markets_for_live={constraints.min_resolved_markets_for_live}",
                f"promotion_stage={promotion_stage}",
            ],
            metadata={
                "equity": equity,
                "risk_report_id": request.risk_report.risk_id,
                "theme_key": theme_key,
                "correlation_key": correlation_key,
                "max_theme_exposure_pct": theme_exposure_pct,
                "capital_control_state": capital_control_state.model_dump(mode="json"),
                "current_market_exposure_usd": current_market,
                "current_theme_exposure_usd": current_theme,
                "current_correlation_exposure_usd": current_correlation,
                "market_exposure_room_usd": market_cap_room,
                "theme_exposure_room_usd": max(0.0, theme_cap - current_theme),
                "correlation_exposure_room_usd": max(0.0, correlation_cap - current_correlation),
                "open_position_count": capital_control_state.open_position_count,
                "open_position_room": capital_control_state.open_position_room,
                "manual_review_count": capital_control_state.manual_review_count,
                "capital_fragmentation_score": capital_control_state.capital_fragmentation_score,
                "capital_concentration_score": capital_control_state.capital_concentration_score,
                "cap_buffer": cap_buffer,
                "resolved_markets_count": resolved_markets_count,
                "min_resolved_markets_for_live": constraints.min_resolved_markets_for_live,
                "live_promotion_ready": live_promotion_ready,
                "promotion_stage": promotion_stage,
            },
        )


def _allocate_to_market_context(
    market: MarketDescriptor,
    amount: float,
    working_exposures: dict[str, float],
) -> None:
    market_key = f"market:{market.market_id}"
    theme_key = f"theme:{_theme_key(market)}"
    corr_key = f"correlation:{_correlation_key(market)}"
    for key in (market_key, theme_key, corr_key):
        working_exposures[key] = working_exposures.get(key, 0.0) + amount


def _apply_exposure(working_exposures: dict[str, float], market: MarketDescriptor, amount: float) -> None:
    _allocate_to_market_context(market, amount, working_exposures)


def _initial_exposures(
    ledger: CapitalLedgerSnapshot | None,
    market_lookup: Mapping[str, MarketDescriptor] | None,
) -> dict[str, float]:
    exposures: dict[str, float] = {}
    if ledger is None:
        return exposures
    for position in ledger.positions:
        descriptor = market_lookup.get(position.market_id) if market_lookup else None
        market_key = f"market:{position.market_id}"
        market_amount = abs(float(position.quantity) * float(position.mark_price if position.mark_price is not None else position.entry_price))
        exposures[market_key] = exposures.get(market_key, 0.0) + market_amount
        if descriptor is None:
            continue
        exposures[f"theme:{_theme_key(descriptor)}"] = exposures.get(f"theme:{_theme_key(descriptor)}", 0.0) + market_amount
        exposures[f"correlation:{_correlation_key(descriptor)}"] = exposures.get(f"correlation:{_correlation_key(descriptor)}", 0.0) + market_amount
    return exposures


def _initial_open_markets(ledger: CapitalLedgerSnapshot | None) -> set[str]:
    if ledger is None:
        return set()
    open_markets: set[str] = set()
    for position in ledger.positions:
        if abs(float(position.quantity)) <= 1e-12:
            continue
        open_markets.add(position.market_id)
    return open_markets


def _priority_score(request: AllocationRequest) -> float:
    confidence = max(0.0, min(1.0, float(request.recommendation.confidence)))
    liquidity = _liquidity_weight(request.snapshot.liquidity, 50_000.0)
    edge = max(0.0, float(request.recommendation.edge_bps or 0.0))
    return round(edge * confidence * liquidity, 6)


def _kelly_fraction(*, price: float, probability: float, side: TradeSide | None) -> float:
    price = max(1e-6, min(1.0 - 1e-6, float(price)))
    probability = max(0.0, min(1.0, float(probability)))
    if side == TradeSide.no:
        price = 1.0 - price
        probability = 1.0 - probability
    b = (1.0 - price) / price
    if b <= 0:
        return 0.0
    q = 1.0 - probability
    return max(0.0, (b * probability - q) / b)


def _liquidity_weight(liquidity: float | None, target: float) -> float:
    if liquidity is None or liquidity <= 0 or target <= 0:
        return 0.2
    return max(0.2, min(1.0, math.log1p(liquidity) / math.log1p(target)))


def _apply_cap_buffer(value: float, cap_buffer: float) -> float:
    return round(max(0.0, float(value)) * max(0.0, min(1.0, float(cap_buffer))), 6)


def _ledger_capacity(
    ledger: CapitalLedgerSnapshot | None,
    *,
    market_id: str | None = None,
    venue: VenueName | None = None,
    constraints: AllocationConstraints | None = None,
) -> tuple[float, float, CapitalControlState]:
    if ledger is None:
        return 0.0, 0.0, CapitalControlState()
    equity = ledger.equity or ledger.cash - ledger.reserved_cash + ledger.realized_pnl + ledger.unrealized_pnl
    available_cash = max(0.0, ledger.cash - ledger.reserved_cash)
    return (
        max(0.0, float(equity)),
        max(0.0, float(available_cash)),
        _capital_control_state(
            ledger,
            market_id=market_id,
            venue=venue,
            constraints=constraints,
        ),
    )


def _capital_control_state(
    ledger: CapitalLedgerSnapshot | None,
    *,
    market_id: str | None = None,
    venue: VenueName | None = None,
    constraints: AllocationConstraints | None = None,
) -> CapitalControlState:
    if ledger is None:
        return CapitalControlState()
    constraints = constraints or AllocationConstraints()
    return CapitalLedger.from_snapshot(ledger).capital_control_state(
        venue=venue or ledger.venue,
        market_id=market_id,
        min_free_cash_buffer_pct=constraints.min_free_cash_buffer_pct,
        per_venue_balance_cap_usd=constraints.per_venue_balance_cap_usd,
        max_market_exposure_usd=constraints.max_market_exposure_usd,
        max_open_positions=constraints.max_open_positions,
        max_daily_loss_usd=constraints.max_daily_loss_usd,
    )


def _theme_key(descriptor: MarketDescriptor) -> str:
    if descriptor.category:
        return descriptor.category.strip().lower()
    if descriptor.categories:
        return descriptor.categories[0].strip().lower()
    if descriptor.tags:
        return descriptor.tags[0].strip().lower()
    if descriptor.canonical_event_id:
        return descriptor.canonical_event_id
    return descriptor.market_id


def _correlation_key(descriptor: MarketDescriptor) -> str:
    if descriptor.canonical_event_id:
        return descriptor.canonical_event_id
    if descriptor.source_url:
        return descriptor.source_url
    return descriptor.market_id


def _resolved_markets_count(request: AllocationRequest, ledger: CapitalLedgerSnapshot | None) -> int:
    metadata_sources: list[Mapping[str, Any]] = [request.metadata or {}, request.risk_report.metadata or {}, request.forecast.metadata or {}, request.recommendation.metadata or {}]
    if ledger is not None:
        metadata_sources.append(ledger.metadata or {})
    for metadata in metadata_sources:
        for key in ("resolved_markets_count", "resolved_market_count"):
            if key in metadata:
                try:
                    return max(0, int(metadata[key]))
                except (TypeError, ValueError):
                    continue
        for key in ("resolved_markets", "resolved_market_ids"):
            if key in metadata:
                value = metadata.get(key)
                if isinstance(value, (list, tuple, set)):
                    return len([item for item in value if str(item).strip()])
    return 0


def _promotion_stage(*, request: AllocationRequest, live_promotion_ready: bool) -> str:
    if not request.risk_report.should_trade or request.recommendation.action != DecisionAction.bet:
        return "blocked"
    if live_promotion_ready:
        return "live_candidate"
    if request.risk_report.approved:
        return "shadow"
    return "paper"


def _zero_decision(
    *,
    request: AllocationRequest,
    available_cash: float,
    reasons: list[str],
    mode: AllocationMode,
    max_stake: float = 0.0,
    market_cap_stake: float = 0.0,
    theme_cap_stake: float = 0.0,
    correlation_cap_stake: float = 0.0,
    liquidity_cap_stake: float = 0.0,
    raw_kelly_fraction: float = 0.0,
    confidence_weight: float = 0.0,
    liquidity_weight: float = 0.0,
    min_free_cash_buffer_pct: float = 0.0,
    per_venue_balance_cap_usd: float = 0.0,
    max_market_exposure_usd: float = 0.0,
    max_theme_exposure_pct: float = 0.0,
    max_open_positions: int = 0,
    max_daily_loss_usd: float = 0.0,
    current_market_exposure_usd: float = 0.0,
    current_theme_exposure_usd: float = 0.0,
    current_correlation_exposure_usd: float = 0.0,
    market_exposure_room_usd: float = 0.0,
    theme_exposure_room_usd: float = 0.0,
    correlation_exposure_room_usd: float = 0.0,
    open_position_count: int = 0,
    open_position_room: int = 0,
    manual_review_count: int = 0,
    capital_fragmentation_score: float = 0.0,
    capital_concentration_score: float = 0.0,
    resolved_markets_count: int = 0,
    min_resolved_markets_for_live: int = 0,
    live_promotion_ready: bool = False,
    promotion_stage: str = "blocked",
    capital_control_state: CapitalControlState | None = None,
    cap_buffer: float = 1.0,
) -> AllocationDecision:
    metadata = {"blocked": True}
    if capital_control_state is not None:
        metadata["capital_control_state"] = capital_control_state.model_dump(mode="json")
    manual_review_count = max(
        0,
        int(manual_review_count or (capital_control_state.manual_review_count if capital_control_state is not None else 0)),
    )
    metadata["cap_buffer"] = max(0.0, min(1.0, float(cap_buffer)))
    return AllocationDecision(
        run_id=request.run_id,
        market_id=request.market.market_id,
        venue=request.market.venue,
        mode=mode,
        action=request.recommendation.action if request.recommendation.action != DecisionAction.bet else DecisionAction.no_trade,
        side=request.recommendation.side,
        should_trade=False,
        recommended_stake=0.0,
        recommended_fraction=0.0,
        raw_kelly_fraction=round(raw_kelly_fraction, 6),
        confidence_weight=round(confidence_weight, 6),
        liquidity_weight=round(liquidity_weight, 6),
        max_stake=round(max_stake, 2),
        market_cap_stake=round(market_cap_stake, 2),
        theme_cap_stake=round(theme_cap_stake, 2),
        correlation_cap_stake=round(correlation_cap_stake, 2),
        liquidity_cap_stake=round(liquidity_cap_stake, 2),
        available_cash=round(available_cash, 2),
        min_free_cash_buffer_pct=round(min_free_cash_buffer_pct, 6),
        per_venue_balance_cap_usd=round(per_venue_balance_cap_usd, 2),
        max_market_exposure_usd=round(max_market_exposure_usd, 2),
        max_theme_exposure_pct=round(max_theme_exposure_pct, 6),
        max_open_positions=max(0, int(max_open_positions)),
        max_daily_loss_usd=round(max_daily_loss_usd, 2),
        current_market_exposure_usd=round(current_market_exposure_usd, 2),
        current_theme_exposure_usd=round(current_theme_exposure_usd, 2),
        current_correlation_exposure_usd=round(current_correlation_exposure_usd, 2),
        market_exposure_room_usd=round(market_exposure_room_usd, 2),
        theme_exposure_room_usd=round(theme_exposure_room_usd, 2),
        correlation_exposure_room_usd=round(correlation_exposure_room_usd, 2),
        open_position_count=max(0, int(open_position_count)),
        open_position_room=max(0, int(open_position_room)),
        manual_review_count=manual_review_count,
        capital_fragmentation_score=round(capital_fragmentation_score, 6),
        capital_concentration_score=round(capital_concentration_score, 6),
        resolved_markets_count=max(0, int(resolved_markets_count)),
        min_resolved_markets_for_live=max(0, int(min_resolved_markets_for_live)),
        live_promotion_ready=bool(live_promotion_ready),
        promotion_stage=promotion_stage,
        no_trade_reasons=_dedupe(reasons),
        allocation_reasons=[],
        metadata={
            **metadata,
            "resolved_markets_count": max(0, int(resolved_markets_count)),
            "min_resolved_markets_for_live": max(0, int(min_resolved_markets_for_live)),
            "live_promotion_ready": bool(live_promotion_ready),
            "promotion_stage": promotion_stage,
            "current_market_exposure_usd": round(current_market_exposure_usd, 2),
            "current_theme_exposure_usd": round(current_theme_exposure_usd, 2),
            "current_correlation_exposure_usd": round(current_correlation_exposure_usd, 2),
            "market_exposure_room_usd": round(market_exposure_room_usd, 2),
            "theme_exposure_room_usd": round(theme_exposure_room_usd, 2),
            "correlation_exposure_room_usd": round(correlation_exposure_room_usd, 2),
            "open_position_count": max(0, int(open_position_count)),
            "open_position_room": max(0, int(open_position_room)),
            "manual_review_count": manual_review_count,
            "capital_fragmentation_score": round(capital_fragmentation_score, 6),
            "capital_concentration_score": round(capital_concentration_score, 6),
        },
    )


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
