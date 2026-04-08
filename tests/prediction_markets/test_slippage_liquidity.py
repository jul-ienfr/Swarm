from __future__ import annotations

import pytest

from prediction_markets.models import MarketOrderBook, MarketSnapshot, OrderBookLevel, MarketStatus, TradeSide, VenueName, VenueType
from prediction_markets.slippage_liquidity import (
    SlippageLiquiditySimulator,
    SlippageLiquidityStatus,
    simulate_slippage_liquidity,
)


def _snapshot(
    *,
    market_id: str = "pm_slip_test",
    price_yes: float | None = None,
    orderbook: MarketOrderBook | None = None,
    depth_near_touch: float | None = 22.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Slippage test market",
        question="Will the slippage simulator work?",
        status=MarketStatus.open,
        price_yes=price_yes,
        orderbook=orderbook,
        depth_near_touch=depth_near_touch,
        liquidity=10000.0,
    )


def test_simulator_consumes_multiple_levels_for_yes_buy() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.45, size=2.0)],
            asks=[
                OrderBookLevel(price=0.55, size=2.0),
                OrderBookLevel(price=0.60, size=3.0),
            ],
        ),
    )
    report = simulate_slippage_liquidity(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=4.0,
    )

    assert report.status == SlippageLiquidityStatus.filled
    assert report.filled_quantity == 4.0
    assert report.average_fill_price == 0.575
    assert report.slippage_bps == 750.0
    assert report.spread_mean_bps is not None
    assert report.spread_mean_bps > 0.0
    assert report.top_of_book_price == 0.55
    assert report.liquidity_available_quantity == 5.0
    assert report.liquidity_consumed_fraction == 0.8
    assert len(report.fills) == 2
    assert len(report.curve) == 2
    assert report.fills[0].fill_price == 0.55
    assert report.fills[1].fill_price == 0.6
    assert report.to_execution_metadata()["fill_ratio"] == 1.0
    postmortem = report.postmortem()
    assert postmortem.fill_rate == pytest.approx(1.0)
    assert "filled" in postmortem.notes
    assert "fragmented_execution" in postmortem.notes
    assert postmortem.recommendation == "reprice"


def test_simulator_handles_no_side_mirroring_and_partial_fill() -> None:
    snapshot = _snapshot(
        orderbook=MarketOrderBook(
            bids=[
                OrderBookLevel(price=0.42, size=1.5),
                OrderBookLevel(price=0.40, size=1.0),
            ],
            asks=[OrderBookLevel(price=0.52, size=1.0)],
        ),
    )
    report = SlippageLiquiditySimulator().simulate(
        snapshot,
        position_side=TradeSide.no,
        execution_side=TradeSide.buy,
        requested_quantity=3.0,
    )

    assert report.status == SlippageLiquidityStatus.partial
    assert report.partial_fill is True
    assert report.filled_quantity == 2.5
    assert report.remaining_quantity == 0.5
    assert report.best_fill_price == 0.58
    assert report.worst_fill_price == 0.6
    assert report.top_of_book_price == 0.58
    assert round(report.average_fill_price or 0.0, 6) == 0.588
    assert report.slippage_bps > 0
    assert report.spread_mean_bps is not None
    assert len(report.fills) == 2
    assert report.fills[0].source == "orderbook"
    assert report.fills[0].fill_price == 0.58
    assert report.fills[1].fill_price == 0.6
    assert report.postmortem().recommendation == "reduce_size"


def test_simulator_falls_back_to_synthetic_reference_without_orderbook() -> None:
    snapshot = _snapshot(price_yes=0.62, orderbook=None)
    report = simulate_slippage_liquidity(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=10.0,
    )

    assert report.status == SlippageLiquidityStatus.synthetic
    assert report.synthetic_reference is True
    assert report.filled_quantity == 10.0
    assert report.average_fill_price == 0.62
    assert report.slippage_bps == 0.0
    assert report.spread_mean_bps is None
    assert len(report.fills) == 1
    assert len(report.curve) == 1
    assert report.fills[0].source == "synthetic_reference"
    assert report.fills[0].fill_price == 0.62


def test_limit_price_excludes_all_liquidity() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=1.0)],
            asks=[
                OrderBookLevel(price=0.60, size=1.0),
                OrderBookLevel(price=0.65, size=1.0),
            ],
        ),
    )
    report = SlippageLiquiditySimulator().simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=1.0,
        limit_price=0.55,
    )

    assert report.status == SlippageLiquidityStatus.no_liquidity
    assert report.filled_quantity == 0.0
    assert report.fills == []
    assert report.curve == []
    assert "limit_price_excludes_orderbook" in report.no_trade_reasons
    assert report.spread_mean_bps is not None


def test_min_depth_near_touch_threshold_blocks_thin_books() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        depth_near_touch=10.0,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=1.0)],
            asks=[OrderBookLevel(price=0.52, size=1.0)],
        ),
    )
    report = SlippageLiquiditySimulator(min_depth_near_touch=18.0).simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=1.0,
    )

    assert report.status == SlippageLiquidityStatus.no_liquidity
    assert report.filled_quantity == 0.0
    assert report.fills == []
    assert report.curve == []
    assert any(reason.startswith("depth_near_touch_below_minimum") for reason in report.no_trade_reasons)
    assert report.metadata["min_depth_near_touch"] == pytest.approx(18.0)


def test_sell_side_simulation_tracks_cash_flow_after_fees() -> None:
    snapshot = _snapshot(
        price_yes=0.5,
        orderbook=MarketOrderBook(
            bids=[
                OrderBookLevel(price=0.48, size=2.0),
                OrderBookLevel(price=0.47, size=2.0),
            ],
            asks=[OrderBookLevel(price=0.52, size=2.0)],
        ),
    )
    report = SlippageLiquiditySimulator(fee_bps=25.0).simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.sell,
        requested_quantity=2.0,
    )

    assert report.status == SlippageLiquidityStatus.filled
    assert report.filled_quantity == 2.0
    assert report.average_fill_price == 0.48
    assert report.slippage_bps == 200.0
    assert report.gross_cash_flow == pytest.approx(0.96)
    assert report.net_cash_flow == pytest.approx(0.9576)
    assert report.effective_price_after_fees == pytest.approx(0.4788)
    assert report.effective_price_after_fees < report.average_fill_price
    assert report.to_execution_metadata()["gross_cash_flow"] == pytest.approx(report.gross_cash_flow)
    assert report.postmortem().recommendation == "reprice"
