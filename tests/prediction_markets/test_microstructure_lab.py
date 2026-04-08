from __future__ import annotations

import pytest

from prediction_markets.microstructure_lab import (
    MicrostructureLab,
    MicrostructureStatus,
    simulate_microstructure_lab,
)
from prediction_markets.models import MarketOrderBook, MarketSnapshot, MarketStatus, OrderBookLevel, TradeSide, VenueName, VenueType


def _snapshot(*, orderbook: MarketOrderBook | None, price_yes: float | None = None, spread_bps: float | None = 40.0) -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm_microstructure",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Microstructure test market",
        question="Will the microstructure lab work?",
        status=MarketStatus.open,
        price_yes=price_yes,
        spread_bps=spread_bps,
        orderbook=orderbook,
        liquidity=50_000.0,
        staleness_ms=0,
    )


def test_microstructure_lab_simulates_partial_fill_across_levels() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        spread_bps=80.0,
        orderbook=MarketOrderBook(
            bids=[
                OrderBookLevel(price=0.42, size=1.0),
                OrderBookLevel(price=0.40, size=2.0),
            ],
            asks=[
                OrderBookLevel(price=0.55, size=1.0),
                OrderBookLevel(price=0.60, size=2.0),
            ],
        ),
    )

    report = simulate_microstructure_lab(
        snapshot,
        position_side=TradeSide.no,
        execution_side=TradeSide.buy,
        requested_quantity=3.5,
    )

    assert report.status == MicrostructureStatus.partial
    assert report.partial_fill is True
    assert report.filled_quantity == pytest.approx(3.0)
    assert report.remaining_quantity == pytest.approx(0.5)
    assert report.fill_count == 2
    assert report.spread_mean_bps == pytest.approx(80.0)
    assert report.average_fill_price == pytest.approx(0.593333, rel=1e-6)
    assert report.top_of_book_price == pytest.approx(0.58)
    assert report.fills[0].fill_price == pytest.approx(0.58)
    assert report.fills[1].fill_price == pytest.approx(0.6)
    assert report.to_execution_metadata()["fill_ratio"] == pytest.approx(3.0 / 3.5)
    assert report.to_execution_metadata()["fill_count"] == 2
    postmortem = report.postmortem()
    assert postmortem.fill_rate == pytest.approx(3.0 / 3.5)
    assert "partial_fill" in postmortem.notes
    assert postmortem.recommendation == "reduce_size"


def test_microstructure_lab_flags_queue_miss_when_top_level_is_consumed_by_queue() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        spread_bps=80.0,
        orderbook=MarketOrderBook(
            asks=[OrderBookLevel(price=0.55, size=1.0)],
            bids=[OrderBookLevel(price=0.45, size=1.0)],
        ),
    )

    report = MicrostructureLab().simulate(
        snapshot=snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=1.0,
        queue_ahead_quantity=2.0,
    )

    assert report.status == MicrostructureStatus.queue_miss
    assert report.queue_miss is True
    assert report.filled_quantity == 0.0
    assert report.fills == []
    assert report.no_trade_reasons == ["queue_miss"]
    assert report.spread_mean_bps == pytest.approx(80.0)


def test_microstructure_lab_detects_spread_collapse_and_reduces_accessible_liquidity() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        spread_bps=10.0,
        orderbook=MarketOrderBook(
            asks=[
                OrderBookLevel(price=0.55, size=2.0),
                OrderBookLevel(price=0.60, size=2.0),
            ],
            bids=[OrderBookLevel(price=0.45, size=1.0)],
        ),
    )

    report = simulate_microstructure_lab(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=2.0,
        spread_collapse_threshold_bps=20.0,
        collapse_liquidity_multiplier=0.25,
    )

    assert report.status == MicrostructureStatus.spread_collapse
    assert report.spread_collapse is True
    assert report.filled_quantity == pytest.approx(1.0)
    assert report.remaining_quantity == pytest.approx(1.0)
    assert report.partial_fill is True
    assert report.fill_count == 2
    assert report.spread_mean_bps == pytest.approx(10.0)
    assert report.fills[0].filled_quantity == pytest.approx(0.5)
    assert report.fills[1].filled_quantity == pytest.approx(0.5)


def test_microstructure_lab_blocks_when_capital_is_locked() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        orderbook=MarketOrderBook(
            asks=[OrderBookLevel(price=0.55, size=2.0)],
            bids=[OrderBookLevel(price=0.45, size=2.0)],
        ),
    )

    report = simulate_microstructure_lab(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=1.0,
        capital_available_usd=50.0,
        capital_locked_usd=50.0,
    )

    assert report.status == MicrostructureStatus.capital_locked
    assert report.capital_locked is True
    assert report.filled_quantity == 0.0
    assert report.fills == []
    assert "capital_locked" in report.no_trade_reasons
    assert report.spread_mean_bps == pytest.approx(40.0)
    assert report.postmortem().recommendation == "wait"
