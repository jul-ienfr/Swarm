from __future__ import annotations

from prediction_markets.adapters import build_market_execution_adapter
from prediction_markets.market_execution import MarketExecutionRequest, MarketExecutionStatus
from prediction_markets.models import MarketDescriptor, MarketOrderBook, MarketSnapshot, MarketStatus, OrderBookLevel, TradeSide, VenueName, VenueType


def _market(*, venue: VenueName, market_id: str) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        liquidity=25_000.0,
        resolution_source="https://example.com/resolution",
    )


def _snapshot(*, venue: VenueName, market_id: str) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        price_yes=0.56,
        price_no=0.44,
        midpoint_yes=0.56,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.55, size=80.0), OrderBookLevel(price=0.54, size=120.0)],
            asks=[OrderBookLevel(price=0.57, size=90.0), OrderBookLevel(price=0.58, size=110.0)],
        ),
        liquidity=25_000.0,
        spread_bps=200.0,
    )


def test_polymarket_bounded_market_execution_builds_auditable_artifacts() -> None:
    adapter = build_market_execution_adapter(VenueName.polymarket)
    request = MarketExecutionRequest(
        run_id="run-bounded-pm",
        market=_market(venue=VenueName.polymarket, market_id="pm_bounded"),
        snapshot=_snapshot(venue=VenueName.polymarket, market_id="pm_bounded"),
        position_side=TradeSide.yes,
        stake=12.0,
        dry_run=True,
        metadata={"scenario": "bounded"},
    )

    record = adapter.execute_bounded(request)

    assert record.status in {MarketExecutionStatus.filled, MarketExecutionStatus.partial}
    assert record.order.order_type.value == "market"
    assert record.order.requested_notional == 12.0
    assert record.metadata["venue_order_lifecycle"]["venue_order_path"] == "external_bounded_api"
    assert record.metadata["venue_order_lifecycle"]["venue_order_cancel_path"] == "external_live_cancel_api"
    assert record.fills
    assert record.positions
    assert record.positions[0].quantity > 0
    assert record.positions[0].source in {"ledger", "paper_trade"}
    assert record.paper_trade is not None


def test_kalshi_bounded_market_execution_is_available_without_live_support() -> None:
    adapter = build_market_execution_adapter(VenueName.kalshi)
    request = MarketExecutionRequest(
        run_id="run-bounded-kalshi",
        market=_market(venue=VenueName.kalshi, market_id="ks_bounded"),
        snapshot=_snapshot(venue=VenueName.kalshi, market_id="ks_bounded"),
        position_side=TradeSide.yes,
        stake=8.0,
        dry_run=False,
        metadata={"scenario": "bounded"},
    )

    record = adapter.execute_bounded(request)

    assert adapter.describe_market_execution_capabilities().live_execution_supported is False
    assert adapter.describe_market_execution_capabilities().bounded_execution_supported is True
    assert record.status in {MarketExecutionStatus.filled, MarketExecutionStatus.partial}
    assert record.metadata["venue_order_lifecycle"]["venue_order_path"] == "external_bounded_api"
    assert record.metadata["venue_order_lifecycle"]["venue_order_cancel_path"] == "external_bounded_cancel_api"
    assert record.positions
    assert record.positions[0].quantity > 0
