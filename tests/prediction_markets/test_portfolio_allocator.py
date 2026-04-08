from __future__ import annotations

import pytest

from prediction_markets.market_risk import MarketRiskEvaluator, MarketRiskReport, RiskConstraints, RiskLevel
from prediction_markets.portfolio_allocator import AllocationConstraints, AllocationRequest, AllocationMode, PortfolioAllocator
from prediction_markets.models import (
    CapitalLedgerSnapshot,
    DecisionAction,
    ForecastPacket,
    LedgerPosition,
    MarketDescriptor,
    MarketOrderBook,
    MarketRecommendationPacket,
    MarketSnapshot,
    MarketStatus,
    OrderBookLevel,
    TradeSide,
    VenueName,
    VenueType,
)


def _market(market_id: str, *, category: str, event_id: str) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        category=category,
        canonical_event_id=event_id,
        resolution_source="https://example.com/resolution",
        status=MarketStatus.open,
        liquidity=50_000,
    )


def _snapshot(market_id: str, *, liquidity: float = 50_000.0) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=VenueName.polymarket,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        liquidity=liquidity,
        spread_bps=90.0,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.47, size=25)],
            asks=[OrderBookLevel(price=0.53, size=25)],
        ),
        market_implied_probability=0.50,
        price_yes=0.50,
        price_no=0.50,
        midpoint_yes=0.50,
    )


def _forecast(run_id: str, market_id: str, fair_probability: float = 0.62) -> ForecastPacket:
    implied = 0.50
    edge_bps = round((fair_probability - implied) * 10000, 2)
    return ForecastPacket(
        run_id=run_id,
        market_id=market_id,
        venue=VenueName.polymarket,
        market_implied_probability=implied,
        fair_probability=fair_probability,
        confidence_low=max(0.0, fair_probability - 0.06),
        confidence_high=min(1.0, fair_probability + 0.06),
        edge_bps=edge_bps,
        edge_after_fees_bps=edge_bps - 50.0,
        recommendation_action=DecisionAction.bet,
        manual_review_required=False,
        rationale="signal",
        risks=[],
    )


def _recommendation(run_id: str, market_id: str, *, confidence: float = 0.8, edge_bps: float = 450.0) -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id=run_id,
        forecast_id=f"fcst_{run_id}",
        market_id=market_id,
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.50,
        edge_bps=edge_bps,
        confidence=confidence,
        why_now=["edge"],
        why_not_now=[],
        human_summary="trade",
    )


def test_portfolio_allocator_sizes_trade_with_kelly_lite() -> None:
    market = _market("pm_alloc_1", category="macro", event_id="event_1")
    snapshot = _snapshot("pm_alloc_1")
    forecast = _forecast("run_alloc_1", "pm_alloc_1", fair_probability=0.64)
    recommendation = _recommendation("run_alloc_1", "pm_alloc_1")
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
        run_id="run_alloc_1",
    )
    ledger = CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0)
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_1",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=ledger,
    )

    assert decision.mode == AllocationMode.single
    assert decision.should_trade is True
    assert decision.action == DecisionAction.bet
    assert decision.side == TradeSide.yes
    assert decision.recommended_stake > 0
    assert decision.recommended_stake <= 150.0
    assert decision.recommended_fraction <= 0.15
    assert decision.raw_kelly_fraction > 0


def test_portfolio_allocator_applies_cap_buffer_and_clamps_it() -> None:
    market = _market("pm_alloc_cap_buffer", category="macro", event_id="event_cap_buffer")
    snapshot = _snapshot("pm_alloc_cap_buffer")
    forecast = _forecast("run_alloc_cap_buffer", "pm_alloc_cap_buffer", fair_probability=0.64)
    recommendation = _recommendation("run_alloc_cap_buffer", "pm_alloc_cap_buffer")
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
        run_id="run_alloc_cap_buffer",
    )

    wide = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
            cap_buffer=1.5,
        )
    )
    narrow = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
            cap_buffer=0.5,
        )
    )

    wide_decision = wide.allocate(
        AllocationRequest(
            run_id="run_alloc_cap_buffer",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
    )
    narrow_decision = narrow.allocate(
        AllocationRequest(
            run_id="run_alloc_cap_buffer",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
    )

    assert wide.constraints.cap_buffer == pytest.approx(1.0)
    assert narrow.constraints.cap_buffer == pytest.approx(0.5)
    assert wide_decision.metadata["cap_buffer"] == pytest.approx(1.0)
    assert narrow_decision.metadata["cap_buffer"] == pytest.approx(0.5)
    assert narrow_decision.max_stake < wide_decision.max_stake
    assert narrow_decision.recommended_stake < wide_decision.recommended_stake


def test_portfolio_allocator_surfaces_manual_review_count_from_ledger_metadata() -> None:
    market = _market("pm_alloc_review", category="macro", event_id="event_review")
    snapshot = _snapshot("pm_alloc_review")
    forecast = _forecast("run_alloc_review", "pm_alloc_review", fair_probability=0.66)
    recommendation = _recommendation("run_alloc_review", "pm_alloc_review", confidence=0.85, edge_bps=600.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
        run_id="run_alloc_review",
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_review",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(
            venue=VenueName.polymarket,
            cash=1000.0,
            reserved_cash=0.0,
            equity=1000.0,
            metadata={"manual_review_market_ids": ["pm-a", "pm-b"]},
        ),
    )

    assert decision.should_trade is True
    assert decision.manual_review_count == 2
    assert decision.metadata["manual_review_count"] == 2
    assert "manual_review_count:2" in decision.metadata["capital_control_state"]["warning_reasons"]


def test_portfolio_allocator_batch_respects_theme_cap() -> None:
    market_a = _market("pm_alloc_a", category="macro", event_id="event_a")
    market_b = _market("pm_alloc_b", category="macro", event_id="event_b")
    snapshot_a = _snapshot("pm_alloc_a")
    snapshot_b = _snapshot("pm_alloc_b")
    forecast_a = _forecast("run_alloc_a", "pm_alloc_a", fair_probability=0.66)
    forecast_b = _forecast("run_alloc_b", "pm_alloc_b", fair_probability=0.65)
    recommendation_a = _recommendation("run_alloc_a", "pm_alloc_a", confidence=0.85, edge_bps=600.0)
    recommendation_b = _recommendation("run_alloc_b", "pm_alloc_b", confidence=0.85, edge_bps=580.0)
    ledger = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=1000.0,
        reserved_cash=0.0,
        equity=1000.0,
        positions=[LedgerPosition(market_id="pm_prior", venue=VenueName.polymarket, side=TradeSide.yes, quantity=20.0, entry_price=0.75)],
    )
    risk_constraints = RiskConstraints(
        min_edge_bps=35.0,
        min_confidence=0.55,
        max_position_fraction_of_equity=0.2,
        max_theme_fraction_of_equity=0.05,
        max_correlation_fraction_of_equity=0.2,
    )
    risk_a = MarketRiskEvaluator(constraints=risk_constraints).assess(
        market=market_a,
        snapshot=snapshot_a,
        forecast=forecast_a,
        recommendation=recommendation_a,
        ledger=ledger,
        run_id="run_alloc_a",
    )
    risk_b = MarketRiskEvaluator(constraints=risk_constraints).assess(
        market=market_b,
        snapshot=snapshot_b,
        forecast=forecast_b,
        recommendation=recommendation_b,
        ledger=ledger,
        run_id="run_alloc_b",
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=1.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    )

    plan = allocator.allocate_many(
        [
            AllocationRequest(
                run_id="run_alloc_a",
                market=market_a,
                snapshot=snapshot_a,
                forecast=forecast_a,
                recommendation=recommendation_a,
                risk_report=risk_a,
            ),
            AllocationRequest(
                run_id="run_alloc_b",
                market=market_b,
                snapshot=snapshot_b,
                forecast=forecast_b,
                recommendation=recommendation_b,
                risk_report=risk_b,
            ),
        ],
        ledger=ledger,
    )

    assert plan.mode == AllocationMode.batch
    assert len(plan.decisions) == 2
    assert plan.total_allocated <= 50.0
    assert plan.decisions[0].recommended_stake >= plan.decisions[1].recommended_stake
    assert any(decision.recommended_stake == 0.0 or decision.recommended_stake <= 25.0 for decision in plan.decisions)


def test_portfolio_allocator_respects_exposure_caps_even_when_trade_is_approved() -> None:
    market = _market("pm_alloc_cap", category="macro", event_id="event_cap")
    snapshot = _snapshot("pm_alloc_cap")
    forecast = _forecast("run_alloc_cap", "pm_alloc_cap", fair_probability=0.66)
    recommendation = _recommendation("run_alloc_cap", "pm_alloc_cap", confidence=0.9, edge_bps=700.0)
    risk = MarketRiskReport(
        run_id="run_alloc_cap",
        market_id="pm_alloc_cap",
        venue=VenueName.polymarket,
        should_trade=True,
        approved=True,
        risk_level=RiskLevel.low,
        risk_score=0.05,
        theme_key="category:macro",
        correlation_key="event:event_cap",
        current_market_exposure=100.0,
        current_theme_exposure=0.0,
        current_correlation_exposure=0.0,
        max_position_fraction_of_equity=0.1,
        max_theme_fraction_of_equity=0.2,
        max_correlation_fraction_of_equity=0.2,
        max_liquidity_fraction_of_equity=0.2,
        max_market_notional=100.0,
        max_theme_notional=200.0,
        max_correlation_notional=200.0,
        max_liquidity_notional=200.0,
        max_allowed_notional=0.0,
        available_equity=1000.0,
        no_trade_reasons=[],
        cap_reasons=[],
        signals=[],
        recommendation_action=DecisionAction.bet,
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_cap",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0),
    )

    assert decision.should_trade is False
    assert decision.recommended_stake == 0.0
    assert decision.max_stake == 0.0
    assert decision.market_cap_stake == 0.0
    assert decision.current_market_exposure_usd == pytest.approx(100.0)
    assert decision.current_theme_exposure_usd == pytest.approx(0.0)
    assert decision.current_correlation_exposure_usd == pytest.approx(0.0)
    assert decision.market_exposure_room_usd == pytest.approx(0.0)
    assert decision.theme_exposure_room_usd == pytest.approx(200.0)
    assert decision.correlation_exposure_room_usd == pytest.approx(200.0)
    assert decision.open_position_count == 0
    assert decision.open_position_room == 0
    assert decision.capital_concentration_score >= 0.0
    assert decision.capital_fragmentation_score >= 0.0
    assert decision.metadata["current_market_exposure_usd"] == pytest.approx(100.0)
    assert decision.metadata["theme_exposure_room_usd"] == pytest.approx(200.0)
    assert "stake_below_minimum:0.00" in decision.no_trade_reasons


def test_portfolio_allocator_applies_explicit_cap_controls_and_exposes_state() -> None:
    market = _market("pm_alloc_caps", category="macro", event_id="event_caps")
    snapshot = _snapshot("pm_alloc_caps")
    forecast = _forecast("run_alloc_caps", "pm_alloc_caps", fair_probability=0.68)
    recommendation = _recommendation("run_alloc_caps", "pm_alloc_caps", confidence=0.9, edge_bps=650.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1_000.0, reserved_cash=100.0, equity=1_000.0),
        run_id="run_alloc_caps",
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.2,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
            min_free_cash_buffer_pct=0.2,
            per_venue_balance_cap_usd=2_000.0,
            max_market_exposure_usd=1_000.0,
            max_theme_exposure_pct=0.03,
            max_open_positions=3,
            max_daily_loss_usd=25.0,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_caps",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(
            venue=VenueName.polymarket,
            cash=1_000.0,
            reserved_cash=100.0,
            equity=1_000.0,
        ),
    )

    assert decision.should_trade is True
    assert decision.min_free_cash_buffer_pct == pytest.approx(0.2)
    assert decision.per_venue_balance_cap_usd == pytest.approx(2_000.0)
    assert decision.max_market_exposure_usd == pytest.approx(1_000.0)
    assert decision.max_theme_exposure_pct == pytest.approx(0.03)
    assert decision.max_open_positions == 3
    assert decision.max_daily_loss_usd == pytest.approx(25.0)
    assert decision.current_market_exposure_usd == pytest.approx(0.0)
    assert decision.current_theme_exposure_usd == pytest.approx(0.0)
    assert decision.current_correlation_exposure_usd == pytest.approx(0.0)
    assert decision.market_exposure_room_usd == pytest.approx(200.0)
    assert decision.theme_exposure_room_usd == pytest.approx(30.0)
    assert decision.correlation_exposure_room_usd == pytest.approx(200.0)
    assert decision.open_position_count == 0
    assert decision.open_position_room == 3
    assert decision.metadata["capital_control_state"]["capital_available_usd"] == pytest.approx(700.0)
    assert decision.recommended_stake <= 700.0
    assert decision.theme_cap_stake == pytest.approx(30.0)
    assert decision.metadata["theme_exposure_room_usd"] == pytest.approx(30.0)
    assert decision.metadata["open_position_room"] == 3


def test_portfolio_allocator_surfaces_live_promotion_readiness_from_resolved_markets() -> None:
    market = _market("pm_alloc_promo", category="macro", event_id="event_promo")
    snapshot = _snapshot("pm_alloc_promo")
    forecast = _forecast("run_alloc_promo", "pm_alloc_promo", fair_probability=0.67)
    recommendation = _recommendation("run_alloc_promo", "pm_alloc_promo", confidence=0.88, edge_bps=640.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1_000.0, reserved_cash=0.0, equity=1_000.0),
        run_id="run_alloc_promo",
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.2,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
            min_resolved_markets_for_live=3,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_promo",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
            metadata={"resolved_markets_count": 1},
        ),
        ledger=CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1_000.0, reserved_cash=0.0, equity=1_000.0),
    )

    assert decision.should_trade is True
    assert decision.resolved_markets_count == 1
    assert decision.min_resolved_markets_for_live == 3
    assert decision.live_promotion_ready is False
    assert decision.promotion_stage == "shadow"
    assert decision.metadata["promotion_stage"] == "shadow"
    assert "resolved_markets_count=1" in " ".join(decision.allocation_reasons)


def test_portfolio_allocator_blocks_when_open_positions_and_daily_loss_caps_are_breached() -> None:
    market = _market("pm_alloc_blocked_caps", category="macro", event_id="event_blocked_caps")
    snapshot = _snapshot("pm_alloc_blocked_caps")
    forecast = _forecast("run_alloc_blocked_caps", "pm_alloc_blocked_caps", fair_probability=0.67)
    recommendation = _recommendation("run_alloc_blocked_caps", "pm_alloc_blocked_caps", confidence=0.9, edge_bps=620.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=CapitalLedgerSnapshot(
            venue=VenueName.polymarket,
            cash=1_000.0,
            reserved_cash=0.0,
            equity=1_000.0,
            positions=[
                LedgerPosition(
                    market_id="pm_existing",
                    venue=VenueName.polymarket,
                    side=TradeSide.yes,
                    quantity=5.0,
                    entry_price=0.5,
                )
            ],
            metadata={"daily_loss_usd": 50.0},
        ),
        run_id="run_alloc_blocked_caps",
    )
    allocator = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.2,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
            min_free_cash_buffer_pct=0.1,
            per_venue_balance_cap_usd=2_000.0,
            max_market_exposure_usd=1_000.0,
            max_open_positions=1,
            max_daily_loss_usd=25.0,
        )
    )

    decision = allocator.allocate(
        AllocationRequest(
            run_id="run_alloc_blocked_caps",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=CapitalLedgerSnapshot(
            venue=VenueName.polymarket,
            cash=1_000.0,
            reserved_cash=0.0,
            equity=1_000.0,
            positions=[
                LedgerPosition(
                    market_id="pm_existing",
                    venue=VenueName.polymarket,
                    side=TradeSide.yes,
                    quantity=5.0,
                    entry_price=0.5,
                )
            ],
            metadata={"daily_loss_usd": 50.0},
        ),
    )

    assert decision.should_trade is False
    assert decision.recommended_stake == 0.0
    assert any("max_open_positions_exceeded" in reason for reason in decision.no_trade_reasons)
    assert any("max_daily_loss_usd_exceeded" in reason for reason in decision.no_trade_reasons)
