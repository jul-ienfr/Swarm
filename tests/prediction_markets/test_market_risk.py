from __future__ import annotations

import pytest

from prediction_markets.market_risk import MarketRiskEvaluator, RiskConstraints, RiskLevel
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
    ResolutionStatus,
    TradeSide,
    VenueName,
    VenueType,
)


def _market(*, market_id: str, category: str, canonical_event_id: str) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        category=category,
        canonical_event_id=canonical_event_id,
        resolution_source="https://example.com/resolution",
        status=MarketStatus.open,
        liquidity=10_000,
    )


def _snapshot(
    market_id: str,
    *,
    liquidity: float = 10_000.0,
    staleness_ms: int = 0,
    spread_bps: float = 120.0,
    depth_near_touch: float | None = 22.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=VenueName.polymarket,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        liquidity=liquidity,
        depth_near_touch=depth_near_touch,
        staleness_ms=staleness_ms,
        spread_bps=spread_bps,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.44, size=10)],
            asks=[OrderBookLevel(price=0.56, size=10)],
        ),
        market_implied_probability=0.50,
        price_yes=0.50,
        price_no=0.50,
        midpoint_yes=0.50,
    )


def _forecast(run_id: str, market_id: str) -> ForecastPacket:
    return ForecastPacket(
        run_id=run_id,
        market_id=market_id,
        venue=VenueName.polymarket,
        market_implied_probability=0.50,
        fair_probability=0.58,
        confidence_low=0.54,
        confidence_high=0.62,
        edge_bps=800.0,
        edge_after_fees_bps=600.0,
        recommendation_action=DecisionAction.bet,
        manual_review_required=False,
        rationale="signal",
        risks=[],
    )


def _recommendation(run_id: str, market_id: str, *, confidence: float = 0.8, edge_bps: float = 600.0) -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id=run_id,
        forecast_id=f"fcst_{run_id}",
        market_id=market_id,
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.5,
        edge_bps=edge_bps,
        confidence=confidence,
        why_now=["edge"],
        why_not_now=[],
        human_summary="trade",
    )


def test_market_risk_blocks_stale_low_confidence_low_liquidity_markets() -> None:
    market = _market(market_id="pm_risk_1", category="politics", canonical_event_id="event_1")
    snapshot = _snapshot("pm_risk_1", liquidity=250.0, staleness_ms=180_000, spread_bps=800.0)
    forecast = _forecast("run_risk_1", "pm_risk_1")
    recommendation = _recommendation("run_risk_1", "pm_risk_1", confidence=0.42, edge_bps=20.0)
    ledger = CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0)
    report = MarketRiskEvaluator(
        constraints=RiskConstraints(min_edge_bps=35.0, min_confidence=0.55, min_liquidity=1000.0, max_spread_bps=500.0)
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger,
        run_id="run_risk_1",
    )

    assert report.approved is False
    assert report.should_trade is False
    assert report.risk_level in {RiskLevel.high, RiskLevel.blocker}
    assert any(reason.startswith("edge_below_minimum") for reason in report.no_trade_reasons)
    assert any(reason.startswith("confidence_below_minimum") for reason in report.no_trade_reasons)
    assert any(reason.startswith("liquidity_below_minimum") for reason in report.no_trade_reasons)
    assert any(reason.startswith("spread_above_maximum") for reason in report.no_trade_reasons)
    assert any(reason.startswith("snapshot_stale") for reason in report.no_trade_reasons)
    assert report.max_allowed_notional > 0.0


def test_risk_constraints_accept_canonical_threshold_names_and_aliases() -> None:
    constraints = RiskConstraints(
        snapshot_ttl_ms=90_000,
        min_liquidity_usd=2_500.0,
        min_depth_near_touch=18.0,
        min_edge_after_fees_bps=42.0,
    )
    legacy = RiskConstraints(
        max_snapshot_staleness_ms=90_000,
        min_liquidity=2_500.0,
        min_edge_bps=42.0,
    )

    assert constraints.snapshot_ttl_ms == 90_000
    assert constraints.min_liquidity_usd == pytest.approx(2_500.0)
    assert constraints.min_depth_near_touch == pytest.approx(18.0)
    assert constraints.min_edge_after_fees_bps == pytest.approx(42.0)
    assert constraints.max_snapshot_staleness_ms == 90_000
    assert constraints.min_liquidity == pytest.approx(2_500.0)
    assert constraints.min_edge_bps == pytest.approx(42.0)
    assert legacy.snapshot_ttl_ms == 90_000
    assert legacy.min_liquidity_usd == pytest.approx(2_500.0)
    assert legacy.min_edge_after_fees_bps == pytest.approx(42.0)


def test_market_risk_blocks_low_depth_near_touch_and_reports_thresholds() -> None:
    market = _market(market_id="pm_risk_depth", category="macro", canonical_event_id="event_depth")
    snapshot = _snapshot("pm_risk_depth", liquidity=5_000.0, depth_near_touch=12.0, spread_bps=70.0)
    forecast = _forecast("run_risk_depth", "pm_risk_depth")
    recommendation = _recommendation("run_risk_depth", "pm_risk_depth", confidence=0.9, edge_bps=500.0)
    ledger = CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=10_000.0, reserved_cash=0.0, equity=10_000.0)

    report = MarketRiskEvaluator(
        constraints=RiskConstraints(
            snapshot_ttl_ms=90_000,
            min_liquidity_usd=1_000.0,
            min_depth_near_touch=18.0,
            min_edge_after_fees_bps=35.0,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger,
        run_id="run_risk_depth",
    )

    assert report.should_trade is False
    assert report.approved is False
    assert any(reason.startswith("depth_near_touch_below_minimum") for reason in report.no_trade_reasons)
    assert report.metadata["snapshot_ttl_ms"] == 90_000
    assert report.metadata["min_liquidity_usd"] == pytest.approx(1_000.0)
    assert report.metadata["min_depth_near_touch"] == pytest.approx(18.0)
    assert report.metadata["min_edge_after_fees_bps"] == pytest.approx(35.0)


def test_market_risk_respects_theme_and_correlation_caps_with_portfolio_context() -> None:
    target_market = _market(market_id="pm_target", category="macro", canonical_event_id="event_macro")
    same_theme_market = _market(market_id="pm_same_theme", category="macro", canonical_event_id="event_other")
    same_correlation_market = _market(market_id="pm_same_corr", category="macro", canonical_event_id="event_macro")
    same_correlation_market_2 = _market(market_id="pm_same_corr_2", category="macro", canonical_event_id="event_macro")
    ledger = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=1000.0,
        reserved_cash=0.0,
        positions=[
            LedgerPosition(market_id="pm_same_theme", venue=VenueName.polymarket, side=TradeSide.yes, quantity=80.0, entry_price=0.9),
            LedgerPosition(market_id="pm_same_corr", venue=VenueName.polymarket, side=TradeSide.yes, quantity=70.0, entry_price=0.8),
            LedgerPosition(market_id="pm_same_corr_2", venue=VenueName.polymarket, side=TradeSide.yes, quantity=70.0, entry_price=0.8),
        ],
        equity=1000.0,
    )
    lookup = {
        "pm_same_theme": same_theme_market,
        "pm_same_corr": same_correlation_market,
        "pm_same_corr_2": same_correlation_market_2,
        "pm_target": target_market,
    }
    snapshot = _snapshot("pm_target")
    forecast = _forecast("run_risk_2", "pm_target")
    recommendation = _recommendation("run_risk_2", "pm_target")
    report = MarketRiskEvaluator(
        constraints=RiskConstraints(
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.1,
            max_correlation_fraction_of_equity=0.1,
        )
    ).assess(
        market=target_market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger,
        market_lookup=lookup,
        run_id="run_risk_2",
    )

    assert report.approved is False
    assert report.should_trade is False
    assert report.current_theme_exposure > 100.0
    assert report.current_correlation_exposure > 100.0
    assert any("theme_cap_reached" in reason for reason in report.cap_reasons)
    assert any("correlation_cap_reached" in reason for reason in report.cap_reasons)
    assert report.theme_key == "category:macro"
    assert report.correlation_key == "event:event_macro"


def test_market_risk_blocks_unreliable_snapshot_and_resolution_metadata() -> None:
    market = _market(market_id="pm_risk_meta", category="politics", canonical_event_id="event_meta")
    snapshot = _snapshot("pm_risk_meta", liquidity=8_000.0, staleness_ms=0, spread_bps=80.0)
    forecast = ForecastPacket(
        run_id="run_risk_meta",
        market_id="pm_risk_meta",
        venue=VenueName.polymarket,
        market_implied_probability=0.50,
        fair_probability=0.58,
        confidence_low=0.54,
        confidence_high=0.62,
        edge_bps=800.0,
        edge_after_fees_bps=600.0,
        recommendation_action=DecisionAction.bet,
        manual_review_required=False,
        rationale="signal",
        risks=[],
        metadata={
            "snapshot_reliable": False,
            "snapshot_reliability_reasons": ["missing_price_proxy"],
            "snapshot_quality": {
                "reliable": False,
                "reliability_reasons": ["missing_price_proxy"],
            },
            "resolution_status": "manual_review",
            "resolution_can_forecast": False,
            "resolution_manual_review_required": True,
            "resolution_reliable": False,
            "resolution_reliability_reasons": ["resolution_manual_review_required"],
            "paper_eligible": False,
            "market_price_reference": 0.50,
            "market_alignment": "dislocated",
        },
    )
    recommendation = _recommendation("run_risk_meta", "pm_risk_meta", confidence=0.8, edge_bps=600.0)
    ledger = CapitalLedgerSnapshot(venue=VenueName.polymarket, cash=1000.0, reserved_cash=0.0, equity=1000.0)

    report = MarketRiskEvaluator(constraints=RiskConstraints(min_edge_bps=35.0, min_confidence=0.55, min_liquidity=1000.0)).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger,
        run_id="run_risk_meta",
    )

    assert report.approved is False
    assert report.should_trade is False
    assert "snapshot_unreliable" in report.no_trade_reasons
    assert "resolution_unreliable" in report.no_trade_reasons
    assert "paper_ineligible" in report.no_trade_reasons
    assert report.metadata["snapshot_reliable"] is False
    assert report.metadata["resolution_reliable"] is False
    assert report.metadata["paper_eligible"] is False
    assert report.metadata["market_alignment"] == "dislocated"


def test_risk_constraints_clamp_fractional_thresholds() -> None:
    constraints = RiskConstraints(
        min_confidence=1.5,
        max_position_fraction_of_equity=1.4,
        max_theme_fraction_of_equity=1.3,
        max_correlation_fraction_of_equity=2.2,
        max_liquidity_fraction_of_equity=3.0,
    )

    assert constraints.min_confidence == pytest.approx(1.0)
    assert constraints.max_position_fraction_of_equity == pytest.approx(1.0)
    assert constraints.max_theme_fraction_of_equity == pytest.approx(1.0)
    assert constraints.max_correlation_fraction_of_equity == pytest.approx(1.0)
    assert constraints.max_liquidity_fraction_of_equity == pytest.approx(1.0)
