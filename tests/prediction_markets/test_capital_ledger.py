from __future__ import annotations

from pathlib import Path

import pytest

from prediction_markets.capital_ledger import CapitalLedger, CapitalLedgerStore
from prediction_markets.models import CapitalLedgerSnapshot, DecisionAction, LedgerPosition, TradeSide, VenueName
from prediction_markets.paper_trading import PaperTradeFill, PaperTradeSimulation, PaperTradeStatus


def _paper_trade(
    *,
    trade_id: str,
    run_id: str,
    execution_side: TradeSide,
    fill_price: float,
    gross_notional: float,
    fee_paid: float,
) -> PaperTradeSimulation:
    return PaperTradeSimulation(
        trade_id=trade_id,
        run_id=run_id,
        market_id="pm-ledger",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        position_side=TradeSide.yes,
        execution_side=execution_side,
        stake=gross_notional,
        requested_quantity=10.0,
        filled_quantity=10.0,
        average_fill_price=fill_price,
        reference_price=0.5,
        gross_notional=gross_notional,
        fee_paid=fee_paid,
        cash_flow=(gross_notional - fee_paid) if execution_side == TradeSide.sell else -(gross_notional + fee_paid),
        status=PaperTradeStatus.filled,
        snapshot_id="ledger-snap",
        fills=[
            PaperTradeFill(
                trade_id=trade_id,
                run_id=run_id,
                market_id="pm-ledger",
                venue=VenueName.polymarket,
                position_side=TradeSide.yes,
                execution_side=execution_side,
                requested_quantity=10.0,
                filled_quantity=10.0,
                fill_price=fill_price,
                gross_notional=gross_notional,
                fee_paid=fee_paid,
                slippage_bps=0.0,
            )
        ],
        metadata={"scenario": "capital-ledger"},
    )


def test_capital_ledger_updates_open_position_and_persists(tmp_path: Path) -> None:
    paths = Path(tmp_path / "prediction_markets")
    store = CapitalLedgerStore(base_dir=paths)
    ledger = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket)

    buy_trade = _paper_trade(
        trade_id="trade-buy",
        run_id="run-buy",
        execution_side=TradeSide.buy,
        fill_price=0.4,
        gross_notional=4.0,
        fee_paid=0.01,
    )

    change = ledger.apply_paper_trade(buy_trade, mark_price=0.55)
    snapshot = ledger.current_snapshot()
    position = ledger.position("pm-ledger", TradeSide.yes)

    assert change.fill_count == 1
    assert snapshot.cash == pytest.approx(95.99)
    assert snapshot.realized_pnl == pytest.approx(0.0)
    assert snapshot.unrealized_pnl == pytest.approx(1.5)
    assert snapshot.equity == pytest.approx(97.49)
    assert position is not None
    assert position.quantity == pytest.approx(10.0)
    assert position.entry_price == pytest.approx(0.4)
    assert position.mark_price == pytest.approx(0.55)

    persisted = ledger.persist(store)
    loaded = store.load_snapshot(snapshot.snapshot_id)

    assert persisted.exists()
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert loaded.cash == pytest.approx(snapshot.cash)
    assert loaded.equity == pytest.approx(snapshot.equity)


def test_capital_ledger_snapshot_normalizes_currency_and_collateral_currency() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=100.0,
        reserved_cash=10.0,
        realized_pnl=2.0,
        unrealized_pnl=-1.0,
        currency=" usd ",
        collateral_currency=" eur ",
    )

    assert snapshot.currency == "USD"
    assert snapshot.collateral_currency == "EUR"
    assert snapshot.equity == pytest.approx(91.0)


def test_capital_ledger_snapshot_exposes_canonical_surface_fields() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash_available=90.0,
        cash_locked=10.0,
        captured_at="2026-04-08T00:00:00+02:00",
        collateral_currency=" usd ",
        positions=[
            LedgerPosition(
                market_id="pm-ledger",
                venue=VenueName.polymarket,
                side=TradeSide.yes,
                quantity=2.0,
                entry_price=0.4,
            ),
            LedgerPosition(
                market_id="k-ledger",
                venue=VenueName.kalshi,
                side=TradeSide.no,
                quantity=4.0,
                entry_price=0.6,
            ),
        ],
    )

    assert snapshot.cash == pytest.approx(100.0)
    assert snapshot.reserved_cash == pytest.approx(10.0)
    assert snapshot.captured_at.isoformat() == "2026-04-07T22:00:00+00:00"
    assert snapshot.updated_at.isoformat() == "2026-04-07T22:00:00+00:00"
    assert snapshot.cash_available == pytest.approx(90.0)
    assert snapshot.cash_available_usd == pytest.approx(90.0)
    assert snapshot.cash_locked == pytest.approx(10.0)
    assert snapshot.cash_locked_usd == pytest.approx(10.0)
    assert snapshot.withdrawable_amount == pytest.approx(90.0)
    assert snapshot.withdrawable_amount_usd == pytest.approx(90.0)
    assert snapshot.collateral_currency == "USD"
    assert snapshot.open_exposure_usd == pytest.approx(3.2)
    assert snapshot.capital_by_market_usd["pm-ledger"] == pytest.approx(0.8)
    assert snapshot.capital_by_market_usd["k-ledger"] == pytest.approx(2.4)
    assert snapshot.transfer_latency_estimate_ms > 0.0
    assert snapshot.metadata["cash_available"] == pytest.approx(90.0)
    assert snapshot.metadata["capital_by_market_usd"]["k-ledger"] == pytest.approx(2.4)


def test_capital_ledger_realizes_pnl_when_position_is_closed() -> None:
    ledger = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket)

    buy_trade = _paper_trade(
        trade_id="trade-open",
        run_id="run-open",
        execution_side=TradeSide.buy,
        fill_price=0.4,
        gross_notional=4.0,
        fee_paid=0.01,
    )
    sell_trade = _paper_trade(
        trade_id="trade-close",
        run_id="run-close",
        execution_side=TradeSide.sell,
        fill_price=0.6,
        gross_notional=6.0,
        fee_paid=0.015,
    )

    ledger.apply_paper_trade(buy_trade, mark_price=0.5)
    change = ledger.apply_paper_trade(sell_trade, mark_price=0.6)
    snapshot = ledger.current_snapshot()

    assert change.fill_count == 1
    assert ledger.position("pm-ledger", TradeSide.yes) is None
    assert snapshot.cash == pytest.approx(101.975)
    assert snapshot.realized_pnl == pytest.approx(2.0)
    assert snapshot.unrealized_pnl == pytest.approx(0.0)
    assert snapshot.equity == pytest.approx(103.975)


def test_capital_ledger_exposes_fragmentation_latency_and_reallocation_metrics() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=80.0,
        reserved_cash=10.0,
        realized_pnl=2.0,
        unrealized_pnl=1.0,
        positions=[
            LedgerPosition(
                market_id="pm-ledger",
                venue=VenueName.polymarket,
                side=TradeSide.yes,
                quantity=2.0,
                entry_price=0.4,
            ),
            LedgerPosition(
                market_id="k-ledger",
                venue=VenueName.kalshi,
                side=TradeSide.no,
                quantity=4.0,
                entry_price=0.6,
            ),
        ],
        metadata={
            "equity_high_watermark": 100.0,
            "reallocation_fee_bps": 15.0,
            "opportunity_cost_bps_per_day": 4.0,
        },
    )
    ledger = CapitalLedger.from_snapshot(snapshot)
    refreshed = ledger.mark_to_market(mark_price=None)

    capital_by_venue = refreshed.metadata["capital_by_venue"]
    capital_by_market = refreshed.metadata["capital_by_market_usd"]
    assert capital_by_venue["polymarket"] == pytest.approx(90.8)
    assert capital_by_venue["kalshi"] == pytest.approx(2.4)
    assert capital_by_market["pm-ledger"] == pytest.approx(0.8)
    assert capital_by_market["k-ledger"] == pytest.approx(2.4)
    assert refreshed.metadata["equity_high_watermark"] == pytest.approx(100.0)
    assert refreshed.metadata["equity_drawdown_usd"] == pytest.approx(28.0)
    assert refreshed.metadata["equity_drawdown_pct"] == pytest.approx(0.28)
    assert refreshed.metadata["gross_position_exposure_usd"] == pytest.approx(3.2)
    assert refreshed.metadata["largest_position_notional_usd"] == pytest.approx(2.4)
    assert refreshed.metadata["largest_position_share"] == pytest.approx(0.75)
    assert refreshed.metadata["capital_fragmentation_score"] > 0.0
    assert refreshed.metadata["capital_concentration_score"] == pytest.approx(1.0 - refreshed.metadata["capital_fragmentation_score"])
    assert refreshed.metadata["transfer_latency_estimate_ms"] > 0.0
    assert refreshed.metadata["reallocation_cost_estimate_usd"] > 0.0


def test_capital_ledger_freezes_capital_when_reconciliation_is_open() -> None:
    ledger = CapitalLedger.from_cash(
        cash=100.0,
        reserved_cash=10.0,
        venue=VenueName.polymarket,
        metadata={"capital_freeze_reason": "manual_hold"},
    )

    state = ledger.capital_control_state(
        reconciliation_open_drift=True,
        reconciliation_manual_review_required=True,
        reconciliation_drift_usd=0.25,
    )

    assert state.capital_frozen is True
    assert state.capital_available_usd == pytest.approx(0.0)
    assert state.cash_available_usd == pytest.approx(0.0)
    assert state.cash_locked_usd == pytest.approx(100.0)
    assert state.raw_capital_available_usd == pytest.approx(90.0)
    assert state.withdrawable_amount_usd == pytest.approx(0.0)
    assert state.reconciliation_open_drift is True
    assert state.reconciliation_manual_review_required is True
    assert state.reconciliation_drift_usd == pytest.approx(0.25)
    assert state.manual_review_count == 1
    assert state.collateral_currency == "USD"
    assert state.open_exposure_usd == pytest.approx(state.gross_position_exposure_usd)
    assert state.transfer_latency_estimate_ms >= 0.0
    assert state.capital_by_market_usd == {}
    assert "capital_freeze_reason:manual_hold" in state.freeze_reasons
    assert "reconciliation_open_drift" in state.freeze_reasons
    assert "reconciliation_manual_review_required" in state.freeze_reasons
    assert state.metadata["capital_available_usd"] == pytest.approx(0.0)
    assert state.metadata["capital_available"] == pytest.approx(0.0)
    assert state.metadata["cash_available"] == pytest.approx(0.0)
    assert state.metadata["cash_locked"] == pytest.approx(100.0)
    assert state.metadata["raw_capital_available_usd"] == pytest.approx(90.0)
    assert state.metadata["withdrawable_amount"] == pytest.approx(0.0)
    assert state.metadata["manual_review_count"] == 1
    assert state.metadata["capital_by_market"] == {}
    assert state.metadata["capital_by_venue"]["polymarket"] == pytest.approx(110.0)


def test_capital_ledger_exposes_manual_review_count_from_metadata() -> None:
    ledger = CapitalLedger.from_cash(
        cash=100.0,
        reserved_cash=10.0,
        venue=VenueName.polymarket,
        metadata={"manual_review_market_ids": ["pm-1", "pm-2"]},
    )

    state = ledger.capital_control_state()

    assert state.manual_review_count == 2
    assert state.metadata["manual_review_count"] == 2
    assert "manual_review_count:2" in state.warning_reasons


def test_capital_ledger_applies_risk_caps_and_exposes_control_surface() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=100.0,
        reserved_cash=10.0,
        realized_pnl=-5.0,
        unrealized_pnl=0.0,
        positions=[
            LedgerPosition(
                market_id="pm-risk-1",
                venue=VenueName.polymarket,
                side=TradeSide.yes,
                quantity=10.0,
                entry_price=0.6,
                mark_price=0.65,
            ),
            LedgerPosition(
                market_id="pm-risk-2",
                venue=VenueName.polymarket,
                side=TradeSide.no,
                quantity=6.0,
                entry_price=0.4,
                mark_price=0.45,
            ),
        ],
        metadata={"daily_loss_usd": 15.0, "equity_high_watermark": 120.0},
    )

    state = CapitalLedger.from_snapshot(snapshot).capital_control_state(
        venue=VenueName.polymarket,
        market_id="pm-risk-1",
        min_free_cash_buffer_pct=0.2,
        per_venue_balance_cap_usd=50.0,
        max_market_exposure_usd=5.0,
        max_open_positions=1,
        max_daily_loss_usd=10.0,
        max_gross_position_exposure_usd=5.0,
        max_equity_drawdown_pct=0.2,
        max_position_concentration_share=0.6,
    )

    assert state.capital_frozen is True
    assert state.capital_available_usd == pytest.approx(0.0)
    assert state.raw_capital_available_usd == pytest.approx(90.0)
    assert state.min_free_cash_buffer_pct == pytest.approx(0.2)
    assert state.free_cash_buffer_usd == pytest.approx(17.0)
    assert state.per_venue_balance_cap_usd == pytest.approx(50.0)
    assert state.venue_balance_usd > state.per_venue_balance_cap_usd
    assert state.max_market_exposure_usd == pytest.approx(5.0)
    assert state.market_exposure_usd > state.max_market_exposure_usd
    assert state.max_open_positions == 1
    assert state.open_position_count == 2
    assert state.max_daily_loss_usd == pytest.approx(10.0)
    assert state.daily_loss_usd == pytest.approx(15.0)
    assert state.equity_high_watermark == pytest.approx(120.0)
    assert state.equity_drawdown_usd == pytest.approx(35.0)
    assert state.equity_drawdown_pct == pytest.approx(0.291667)
    assert state.gross_position_exposure_usd > 0.0
    assert state.largest_position_notional_usd > 0.0
    assert state.largest_position_share > 0.0
    assert state.capital_concentration_score >= state.capital_fragmentation_score
    assert "per_venue_balance_cap_exceeded" in " ".join(state.freeze_reasons)
    assert "max_market_exposure_usd_exceeded" in " ".join(state.freeze_reasons)
    assert "max_daily_loss_usd_exceeded" in " ".join(state.freeze_reasons)
    assert "gross_position_exposure_usd_exceeded" in " ".join(state.freeze_reasons)
    assert "equity_drawdown_pct_exceeded" in " ".join(state.freeze_reasons)
    assert "position_concentration_share_exceeded" in " ".join(state.freeze_reasons)
    assert state.metadata["min_free_cash_buffer_pct"] == pytest.approx(0.2)
    assert state.metadata["per_venue_balance_cap_usd"] == pytest.approx(50.0)
    assert state.metadata["max_market_exposure_usd"] == pytest.approx(5.0)
    assert state.metadata["max_open_positions"] == 1
    assert state.metadata["max_daily_loss_usd"] == pytest.approx(10.0)
    assert state.metadata["equity_drawdown_pct"] == pytest.approx(0.291667)
    assert state.metadata["gross_position_exposure_usd"] > 0.0
    assert state.metadata["largest_position_share"] > 0.0
    assert state.metadata["cash_available"] == pytest.approx(0.0)
    assert state.metadata["cash_locked"] == pytest.approx(snapshot.cash)
    assert state.metadata["withdrawable_amount"] == pytest.approx(0.0)


def test_capital_ledger_applies_free_cash_buffer_without_freezing() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=1_000.0,
        reserved_cash=100.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        metadata={},
    )

    state = CapitalLedger.from_snapshot(snapshot).capital_control_state(
        min_free_cash_buffer_pct=0.2,
    )

    assert state.capital_frozen is False
    assert state.raw_capital_available_usd == pytest.approx(900.0)
    assert state.free_cash_buffer_usd == pytest.approx(180.0)
    assert state.capital_available_usd == pytest.approx(720.0)
    assert state.cash_available_usd == pytest.approx(720.0)
    assert state.cash_locked_usd == pytest.approx(280.0)
    assert state.withdrawable_amount_usd == pytest.approx(720.0)
    assert "min_free_cash_buffer_pct_applied" in " ".join(state.warning_reasons)


def test_capital_ledger_surfaces_capital_transfer_latency_threshold() -> None:
    snapshot = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=80.0,
        reserved_cash=10.0,
        realized_pnl=2.0,
        unrealized_pnl=1.0,
        positions=[
            LedgerPosition(
                market_id="pm-ledger",
                venue=VenueName.polymarket,
                side=TradeSide.yes,
                quantity=2.0,
                entry_price=0.4,
            ),
            LedgerPosition(
                market_id="k-ledger",
                venue=VenueName.kalshi,
                side=TradeSide.no,
                quantity=4.0,
                entry_price=0.6,
            ),
        ],
        metadata={
            "equity_high_watermark": 100.0,
            "max_capital_transfer_latency_ms": 10_000.0,
        },
    )
    state = CapitalLedger.from_snapshot(snapshot).capital_control_state()

    assert state.transfer_latency_estimate_ms > state.max_capital_transfer_latency_ms
    assert state.capital_transfer_latency_exceeded is True
    assert state.capital_transfer_latency_room_ms == pytest.approx(0.0)
    assert state.capital_frozen is False
    assert "capital_transfer_latency_exceeded" in " ".join(state.warning_reasons)
