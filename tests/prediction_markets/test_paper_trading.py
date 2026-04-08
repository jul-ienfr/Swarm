from __future__ import annotations

from pathlib import Path

import pytest

from prediction_markets.models import DecisionAction, MarketOrderBook, MarketSnapshot, OrderBookLevel, TradeSide, VenueName
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.paper_trading import PaperTradeReport, PaperTradeSimulator, PaperTradeStatus, PaperTradeStore, build_paper_trade_report


def _snapshot_with_book() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-paper-trade",
        venue=VenueName.polymarket,
        title="Paper trading market",
        question="Will the repo finish the paper trading track?",
        price_yes=0.5,
        price_no=0.5,
        midpoint_yes=0.5,
        market_implied_probability=0.5,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=4.0), OrderBookLevel(price=0.47, size=4.0)],
            asks=[OrderBookLevel(price=0.51, size=2.0), OrderBookLevel(price=0.53, size=1.0)],
        ),
    )


def _mirrored_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-paper-no",
        venue=VenueName.polymarket,
        title="Mirrored no-side market",
        question="Will the mirror side trade?",
        price_yes=0.62,
        price_no=0.38,
        midpoint_yes=0.62,
        market_implied_probability=0.62,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.62, size=2.0), OrderBookLevel(price=0.61, size=2.0)],
            asks=[OrderBookLevel(price=0.65, size=2.0)],
        ),
    )


def test_paper_trade_simulation_matches_orderbook_and_persists(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    simulator = PaperTradeSimulator(fee_bps=25.0, max_slippage_bps=200.0)
    snapshot = _snapshot_with_book()

    simulation = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=2.0,
        run_id="paper-run-1",
        metadata={"source": "unit-test"},
    )

    assert simulation.trade_id == "paper-run-1"
    assert simulation.run_id == "paper-run-1"
    assert simulation.status is PaperTradeStatus.partial
    assert simulation.filled_quantity == pytest.approx(3.0)
    assert simulation.requested_quantity == pytest.approx(4.0)
    assert simulation.average_fill_price == pytest.approx(0.516667, rel=1e-6)
    assert simulation.reference_price == pytest.approx(0.5)
    assert len(simulation.fills) == 2
    assert simulation.fills[0].trade_id == simulation.trade_id
    assert simulation.fills[0].run_id == simulation.run_id
    assert simulation.order_count == 1
    assert simulation.fill_count == 2
    assert simulation.settlement_status == "simulated_settled"
    assert simulation.metadata["source"] == "unit-test"
    assert "slippage_guard_triggered" not in simulation.metadata
    assert simulation.to_paper_trade_record().entry_price == pytest.approx(0.516667, rel=1e-6)
    postmortem = simulation.postmortem()
    assert postmortem.trade_id == simulation.trade_id
    assert postmortem.fill_rate == pytest.approx(0.75)
    assert postmortem.closing_line_drift_bps == pytest.approx((simulation.average_fill_price - simulation.reference_price) * 10000.0, rel=1e-6)
    assert postmortem.fee_bps == pytest.approx(25.0)
    assert postmortem.fill_count == 2
    assert postmortem.fragmented is True
    assert postmortem.fragmentation_score == pytest.approx(1.0 - (2.0 / 3.0), rel=1e-5)
    assert postmortem.no_trade_zone is False
    assert postmortem.stale_blocked is False
    assert postmortem.settlement_status == "simulated_settled"
    assert postmortem.balance_delta_usd == pytest.approx(postmortem.net_cash_flow, rel=1e-6)
    assert postmortem.effective_price_after_fees == pytest.approx(abs(postmortem.net_cash_flow) / postmortem.filled_quantity, rel=1e-6)
    assert postmortem.effective_price_after_fees > simulation.average_fill_price
    assert postmortem.recommendation == "reduce_size"

    store = PaperTradeStore(paths=paths)
    persisted_path = simulator.persist(simulation, store=store)
    loaded = store.load(simulation.trade_id)

    assert persisted_path.exists()
    assert loaded.trade_id == simulation.trade_id
    assert loaded.filled_quantity == simulation.filled_quantity
    assert loaded.status is PaperTradeStatus.partial
    assert (paths.paper_trades_dir / f"{simulation.trade_id}.json").exists()


def test_paper_trade_simulation_mirrors_no_side_book(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    simulator = PaperTradeSimulator(fee_bps=25.0)
    snapshot = _mirrored_snapshot()

    simulation = simulator.simulate(
        snapshot,
        position_side=TradeSide.no,
        execution_side=TradeSide.buy,
        stake=0.76,
        run_id="paper-run-no-side",
    )

    assert simulation.status is PaperTradeStatus.filled
    assert simulation.reference_price == pytest.approx(0.38)
    assert simulation.filled_quantity == pytest.approx(2.0)
    assert len(simulation.fills) == 1
    assert simulation.fills[0].fill_price == pytest.approx(0.38)
    assert simulation.average_fill_price == pytest.approx(0.38)
    assert simulation.fills[0].position_side is TradeSide.no
    assert simulation.fills[0].execution_side is TradeSide.buy
    assert simulation.order_count == 1
    assert simulation.fill_count == 1
    assert simulation.settlement_status == "simulated_settled"
    assert simulation.to_paper_trade_record().side is TradeSide.no
    postmortem = simulation.postmortem()
    assert postmortem.fill_rate == pytest.approx(1.0)
    assert postmortem.fill_count == 1
    assert postmortem.fragmented is False
    assert postmortem.no_trade_zone is False
    assert postmortem.stale_blocked is False
    assert postmortem.settlement_status == "simulated_settled"

    store = PaperTradeStore(paths=paths)
    store.save(simulation)
    assert store.load(simulation.trade_id).trade_id == simulation.trade_id


def test_paper_trade_simulation_sell_side_accounts_for_fees_and_exit_cash_flow() -> None:
    simulator = PaperTradeSimulator(fee_bps=25.0)
    snapshot = _snapshot_with_book()

    simulation = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.sell,
        stake=0.96,
        run_id="paper-run-sell-side",
    )

    assert simulation.status is PaperTradeStatus.filled
    assert simulation.order_count == 1
    assert simulation.fill_count == 1
    assert simulation.requested_quantity == pytest.approx(1.92)
    assert simulation.filled_quantity == pytest.approx(1.92)
    assert simulation.average_fill_price == pytest.approx(0.48)
    assert simulation.gross_notional == pytest.approx(0.9216, rel=1e-6)
    assert simulation.fee_paid == pytest.approx(simulation.gross_notional * 0.0025, rel=1e-6)
    assert simulation.cash_flow == pytest.approx(simulation.gross_notional - simulation.fee_paid, rel=1e-6)

    postmortem = simulation.postmortem()
    assert postmortem.gross_cash_flow == pytest.approx(simulation.gross_notional, rel=1e-6)
    assert postmortem.net_cash_flow == pytest.approx(simulation.gross_notional - simulation.fee_paid, rel=1e-6)
    assert postmortem.effective_price_after_fees == pytest.approx(abs(postmortem.net_cash_flow) / postmortem.filled_quantity, rel=1e-6)
    assert postmortem.effective_price_after_fees < simulation.average_fill_price
    assert postmortem.fee_paid == pytest.approx(simulation.fee_paid)
    assert postmortem.no_trade_zone is False
    assert postmortem.stale_blocked is False
    assert postmortem.settlement_status == "simulated_settled"


def test_paper_trade_simulation_marks_no_trade_zone_for_non_bet_recommendation() -> None:
    simulator = PaperTradeSimulator(fee_bps=25.0)
    snapshot = _snapshot_with_book()

    simulation = simulator.simulate_from_recommendation(
        snapshot,
        recommendation_action=DecisionAction.no_trade,
        side=None,
        stake=1.0,
        run_id="paper-run-no-trade",
    )

    assert simulation.status is PaperTradeStatus.skipped
    assert simulation.metadata["no_trade_zone"] is True
    assert simulation.metadata["recommendation_action"] == DecisionAction.no_trade.value
    assert simulation.postmortem().no_trade_zone is True
    assert simulation.postmortem().recommendation == "no_trade"
    assert simulation.postmortem().fill_count == 0


def test_paper_trade_simulation_blocks_stale_snapshot_and_persists_report(tmp_path: Path) -> None:
    simulator = PaperTradeSimulator(fee_bps=25.0)
    stale_snapshot = _snapshot_with_book().model_copy(update={"staleness_ms": 240_000})

    stale_simulation = simulator.simulate(
        stale_snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=1.0,
        run_id="paper-run-stale",
    )
    partial_simulation = simulator.simulate(
        _snapshot_with_book(),
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=2.0,
        run_id="paper-run-partial",
    )
    filled_simulation = simulator.simulate(
        _mirrored_snapshot(),
        position_side=TradeSide.no,
        execution_side=TradeSide.buy,
        stake=0.76,
        run_id="paper-run-filled",
    )

    assert stale_simulation.status is PaperTradeStatus.skipped
    assert stale_simulation.metadata["reason"] == "snapshot_stale"
    assert stale_simulation.metadata["stale_blocked"] is True
    assert stale_simulation.postmortem().stale_blocked is True
    assert stale_simulation.postmortem().fill_rate == pytest.approx(0.0)

    report = build_paper_trade_report(
        [partial_simulation, stale_simulation, filled_simulation],
        metadata={"source": "unit-test"},
    )
    persisted = report.persist(tmp_path / "paper_trade_report.json")
    loaded = PaperTradeReport.load(persisted)

    assert report.surface.trade_count == 3
    assert report.surface.order_count == 3
    assert report.surface.fill_count == 3
    assert report.surface.partial_fill_rate == pytest.approx(1 / 3)
    assert report.surface.no_trade_zone_count == 1
    assert report.surface.no_trade_zone_rate == pytest.approx(1 / 3)
    assert report.surface.stale_block_count == 1
    assert report.surface.stale_block_rate == pytest.approx(1 / 3)
    assert report.surface.fill_rate == pytest.approx(5 / 8)
    assert report.surface.reject_rate == pytest.approx(0.0)
    assert report.surface.settlement_rate == pytest.approx(2 / 3)
    assert report.surface.settled_trade_count == 2
    assert report.surface.fee_paid_usd > 0.0
    assert report.surface.average_slippage_bps >= 0.0
    assert report.surface.spread_mean_bps is not None
    assert loaded.surface.stale_block_rate == pytest.approx(report.surface.stale_block_rate)
    assert loaded.surface.no_trade_zone_rate == pytest.approx(report.surface.no_trade_zone_rate)
    assert loaded.content_hash == report.content_hash


def test_paper_trade_simulation_rejects_non_positive_stake() -> None:
    simulator = PaperTradeSimulator(fee_bps=25.0)
    snapshot = _snapshot_with_book()

    simulation = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=0.0,
        run_id="paper-run-zero-stake",
    )

    assert simulation.status is PaperTradeStatus.rejected
    assert simulation.metadata["no_trade_zone"] is True
    assert simulation.metadata["reason"] == "stake must be positive"
    assert simulation.order_count == 1
    assert simulation.fill_count == 0
    assert simulation.settlement_status == "not_settled"
    assert simulation.postmortem().no_trade_zone is True
