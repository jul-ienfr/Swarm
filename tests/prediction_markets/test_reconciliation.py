from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.capital_ledger import CapitalLedger, CapitalLedgerStore
from prediction_markets.models import (
    DecisionAction,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    MarketOrderBook,
    MarketRecommendationPacket,
    MarketSnapshot,
    OrderBookLevel,
    TradeSide,
    VenueName,
)
from prediction_markets.paper_trading import PaperTradeSimulator, PaperTradeStore
from prediction_markets.reconciliation import (
    ReconciliationDriftSummary,
    ReconciliationEngine,
    ReconciliationReport,
    ReconciliationStatus,
    ReconciliationStore,
    monitor_reconciliation_reports,
)
from prediction_markets.shadow_execution import ShadowExecutionEngine, ShadowExecutionStore


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-recon",
        venue=VenueName.polymarket,
        title="Reconciliation market",
        question="Will reconciliation align?",
        price_yes=0.5,
        price_no=0.5,
        midpoint_yes=0.5,
        market_implied_probability=0.5,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=4.0), OrderBookLevel(price=0.47, size=4.0)],
            asks=[OrderBookLevel(price=0.51, size=2.0), OrderBookLevel(price=0.53, size=2.0)],
        ),
    )


def _recommendation(*, run_id: str) -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id=run_id,
        forecast_id="fcst-recon",
        market_id="pm-recon",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        confidence=0.91,
        human_summary="Reconciliation check",
    )


def _projection(*, run_id: str) -> ExecutionProjection:
    return ExecutionProjection(
        run_id=run_id,
        venue=VenueName.polymarket,
        market_id="pm-recon",
        requested_mode=ExecutionProjectionMode.shadow,
        projected_mode=ExecutionProjectionOutcome.shadow,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.shadow,
        highest_safe_requested_mode=ExecutionProjectionMode.shadow,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.shadow,
        blocking_reasons=[],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        metadata={
            "anchor_at": datetime.now(timezone.utc).isoformat(),
            "stale_after_seconds": 3600.0,
        },
    )


def test_reconciliation_detects_drift_between_theoretical_paper_and_shadow_snapshots(tmp_path: Path) -> None:
    paths = Path(tmp_path / "prediction_markets")
    recon_store = ReconciliationStore(base_dir=paths)
    theoretical = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket).current_snapshot()
    snapshot = _snapshot()
    simulator = PaperTradeSimulator(fee_bps=25.0)
    paper_trade = simulator.simulate(snapshot, position_side=TradeSide.yes, execution_side=TradeSide.buy, stake=2.0, run_id="run-recon")
    shadow_engine = ShadowExecutionEngine(starting_cash=100.0, default_stake=2.0)
    _projection(run_id="run-recon").persist(paths / "runs" / "run-recon" / "execution_projection.json")
    shadow_result = shadow_engine.run(_recommendation(run_id="run-recon"), snapshot, stake=2.0)

    PaperTradeStore(base_dir=paths).save(paper_trade)
    ShadowExecutionStore(base_dir=paths).save(shadow_result)
    CapitalLedgerStore(base_dir=paths).save_snapshot(shadow_result.ledger_after)

    report = ReconciliationEngine().reconcile(
        theoretical,
        paper_trade_ids=[paper_trade.trade_id],
        shadow_execution_ids=[shadow_result.shadow_id],
        ledger_snapshot_ids=[shadow_result.ledger_after.snapshot_id],
        persist=True,
        store=recon_store,
        metadata={"scenario": "aligned"},
    )

    loaded = recon_store.load(report.reconciliation_id)

    assert report.status is ReconciliationStatus.drifted
    assert report.drift_summary.status is ReconciliationStatus.drifted
    assert report.manual_review_required is True
    assert report.drift_summary.manual_review_required is True
    assert report.paper_projection_drift is not None
    assert report.shadow_projection_drift is not None
    assert report.paper_vs_shadow_drift is not None
    assert report.paper_projection_drift.status is ReconciliationStatus.drifted
    assert report.shadow_projection_drift.status is ReconciliationStatus.aligned
    assert report.paper_vs_shadow_drift.status is ReconciliationStatus.drifted
    assert report.paper_vs_shadow_drift.notes == ["position_count_mismatch"]
    assert report.drift_summary.field_drift_count >= 1
    assert report.drift_summary.position_drift_count >= 1
    assert report.drift_summary.execution_drift_count >= 1
    assert report.drift_summary.balance_drift_count >= 1
    assert report.drift_summary.new_orders_blocked is True
    assert report.drift_summary.summary.startswith("status=")
    assert "price_drift_count=" in report.drift_summary.summary
    assert report.new_orders_blocked is True
    assert "material_drift_detected" in report.new_orders_blocking_reasons
    assert report.paper_trade_ids == [paper_trade.trade_id]
    assert report.shadow_execution_ids == [shadow_result.shadow_id]
    assert report.observed_snapshot_ids == [shadow_result.ledger_after.snapshot_id]
    assert report.execution_drifts
    assert report.execution_drifts[0].theoretical_price is not None
    assert report.execution_drifts[0].executable_price is not None
    assert report.execution_drifts[0].paper_order_count == 1
    assert report.execution_drifts[0].shadow_order_count == 0
    assert report.execution_drifts[0].paper_fill_count >= 1
    assert report.execution_drifts[0].shadow_fill_count == 0
    assert report.execution_drifts[0].paper_fee_paid >= 0.0
    assert report.execution_drifts[0].shadow_fee_paid >= 0.0
    assert report.execution_drifts[0].paper_settlement_status in {"simulated_settled", "not_settled"}
    assert report.execution_drifts[0].slippage_drift_bps is None
    assert report.paper_projection_snapshot.cash < shadow_result.ledger_after.cash
    assert loaded.reconciliation_id == report.reconciliation_id
    assert loaded.status is ReconciliationStatus.drifted


def test_reconciliation_detects_drift_against_persisted_snapshot(tmp_path: Path) -> None:
    paths = Path(tmp_path / "prediction_markets")
    theoretical = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket).current_snapshot()
    snapshot = _snapshot()
    simulator = PaperTradeSimulator(fee_bps=25.0)
    paper_trade = simulator.simulate(snapshot, position_side=TradeSide.yes, execution_side=TradeSide.buy, stake=2.0, run_id="run-drift")
    shadow_engine = ShadowExecutionEngine(starting_cash=100.0, default_stake=2.0)
    _projection(run_id="run-drift").persist(paths / "runs" / "run-drift" / "execution_projection.json")
    shadow_result = shadow_engine.run(_recommendation(run_id="run-drift"), snapshot, stake=2.0)

    PaperTradeStore(base_dir=paths).save(paper_trade)
    ShadowExecutionStore(base_dir=paths).save(shadow_result)

    observed = shadow_result.ledger_after.model_copy(
        update={
            "cash": shadow_result.ledger_after.cash + 1.0,
            "equity": shadow_result.ledger_after.equity + 1.0,
        }
    )
    CapitalLedgerStore(base_dir=paths).save_snapshot(observed)

    report = ReconciliationEngine().reconcile(
        theoretical,
        paper_trade_ids=[paper_trade.trade_id],
        shadow_execution_ids=[shadow_result.shadow_id],
        ledger_snapshot_ids=[observed.snapshot_id],
        base_dir=paths,
        metadata={"scenario": "drift"},
    )

    assert report.status is ReconciliationStatus.drifted
    assert report.drift_summary.status is ReconciliationStatus.drifted
    assert report.manual_review_required is True
    assert report.drift_summary.manual_review_required is True
    assert report.new_orders_blocked is True
    assert report.drift_summary.new_orders_blocked is True
    assert report.drift_summary.price_drift_count >= 0
    assert report.drift_summary.max_abs_price_drift_bps >= 0.0
    assert report.drift_summary.slippage_drift_count >= 0
    assert report.drift_summary.avg_abs_slippage_drift_bps >= 0.0
    assert "price_drift_count=" in report.drift_summary.summary
    assert report.manual_review_reason == "material_drift_detected"
    assert report.paper_projection_drift is not None
    assert report.shadow_projection_drift is not None
    assert report.paper_projection_drift.status is ReconciliationStatus.drifted
    assert report.shadow_projection_drift.status is ReconciliationStatus.drifted
    assert report.paper_vs_shadow_drift is not None
    assert report.paper_vs_shadow_drift.status is ReconciliationStatus.drifted
    cash_drift = next(field for field in report.paper_projection_drift.field_drifts if field.field_name == "cash")
    equity_drift = next(field for field in report.paper_projection_drift.field_drifts if field.field_name == "equity")
    assert cash_drift.delta > 0.0
    assert equity_drift.delta > 0.0
    assert report.drift_summary.max_abs_cash_drift > 0.0
    assert report.drift_summary.max_abs_equity_drift > 0.0
    assert report.drift_summary.balance_drift_count >= 1


def test_reconciliation_flags_missing_shadow_execution_as_settlement_drift(tmp_path: Path) -> None:
    paths = Path(tmp_path / "prediction_markets")
    recon_store = ReconciliationStore(base_dir=paths)
    theoretical = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket).current_snapshot()
    snapshot = _snapshot()
    simulator = PaperTradeSimulator(fee_bps=25.0)
    paper_trade = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=2.0,
        run_id="run-missing-shadow",
    )

    PaperTradeStore(base_dir=paths).save(paper_trade)
    observed_ledger = CapitalLedger.from_snapshot(theoretical)
    observed_ledger.apply_paper_trade(paper_trade, mark_price=paper_trade.reference_price)

    report = ReconciliationEngine().reconcile(
        theoretical,
        paper_trade_ids=[paper_trade.trade_id],
        observed_ledger=observed_ledger.current_snapshot(),
        persist=True,
        store=recon_store,
        metadata={"scenario": "missing-shadow"},
    )

    assert report.status is ReconciliationStatus.drifted
    assert report.drift_summary.status is ReconciliationStatus.drifted
    assert report.manual_review_required is True
    assert report.drift_summary.manual_review_required is True
    assert report.drift_summary.execution_drift_count == 1
    assert report.drift_summary.new_orders_blocked is True
    assert report.drift_summary.price_drift_count >= 0
    assert len(report.execution_drifts) == 1
    execution_drift = report.execution_drifts[0]
    assert execution_drift.paper_trade_id == paper_trade.trade_id
    assert execution_drift.status is ReconciliationStatus.drifted
    assert execution_drift.notes == ["missing_shadow_execution"]
    assert execution_drift.settlement_status == "unavailable"
    assert execution_drift.theoretical_price is not None
    assert execution_drift.executable_price is not None
    assert execution_drift.price_drift_bps is not None
    assert execution_drift.paper_order_count == 1
    assert execution_drift.paper_fill_count == len(paper_trade.fills)
    assert execution_drift.paper_fee_paid == pytest.approx(paper_trade.fee_paid)
    assert execution_drift.paper_slippage_bps == pytest.approx(paper_trade.slippage_bps)
    assert report.paper_projection_drift is not None
    assert report.paper_projection_drift.status is ReconciliationStatus.aligned


def test_reconciliation_flags_fee_and_settlement_drift_with_explicit_blocking_reasons(tmp_path: Path) -> None:
    paths = Path(tmp_path / "prediction_markets")
    theoretical = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket).current_snapshot()
    snapshot = _snapshot()
    simulator = PaperTradeSimulator(fee_bps=25.0)
    paper_trade = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=2.0,
        run_id="run-fee-settlement",
    )
    shadow_engine = ShadowExecutionEngine(starting_cash=100.0, default_stake=2.0)
    _projection(run_id="run-fee-settlement").persist(paths / "runs" / "run-fee-settlement" / "execution_projection.json")
    shadow_result = shadow_engine.run(_recommendation(run_id="run-fee-settlement"), snapshot, stake=2.0)
    shadow_result = shadow_result.model_copy(
        update={
            "paper_trade": paper_trade.model_copy(update={"fee_paid": paper_trade.fee_paid + 0.5}),
            "ledger_change": None,
        }
    )

    report = ReconciliationEngine().reconcile(
        theoretical,
        paper_trades=[paper_trade],
        shadow_executions=[shadow_result],
        observed_ledger=shadow_result.ledger_after,
        base_dir=paths,
        metadata={"scenario": "fee-settlement-drift"},
    )

    assert report.status is ReconciliationStatus.drifted
    assert report.manual_review_required is True
    assert report.new_orders_blocked is True
    assert "material_drift_detected" in report.new_orders_blocking_reasons
    assert "fee_drift_detected" in report.new_orders_blocking_reasons
    assert "settlement_drift_detected" in report.new_orders_blocking_reasons
    assert report.drift_summary.fee_drift_count >= 1
    assert report.drift_summary.settlement_drift_count >= 1
    assert "fee" in report.drift_summary.metadata["drift_categories"]
    assert "settlement" in report.drift_summary.metadata["drift_categories"]
    assert report.drift_summary.summary.startswith("status=drifted")
    assert report.metadata["drift_summary"]["fee_drift_count"] >= 1


def test_reconciliation_monitor_reports_recovery_after_drift(tmp_path: Path) -> None:
    snapshot = CapitalLedger.from_cash(cash=100.0, venue=VenueName.polymarket).current_snapshot()
    drifted_report = ReconciliationReport(
        run_id="run-monitor",
        market_id="pm-monitor",
        venue=VenueName.polymarket,
        status=ReconciliationStatus.drifted,
        theoretical_ledger_snapshot=snapshot,
        paper_projection_snapshot=snapshot,
        shadow_projection_snapshot=snapshot,
        observed_ledger_snapshot=snapshot,
        drift_summary=ReconciliationDriftSummary(
            status=ReconciliationStatus.drifted,
            manual_review_required=True,
            manual_review_reason="material_drift_detected",
            new_orders_blocked=True,
            new_orders_blocking_reasons=["material_drift_detected"],
            summary="status=drifted",
        ),
        manual_review_required=True,
        manual_review_reason="material_drift_detected",
        new_orders_blocked=True,
        new_orders_blocking_reasons=["material_drift_detected"],
    )
    recovered_report = drifted_report.model_copy(
        update={
            "reconciliation_id": "recon_monitor_recovered",
            "status": ReconciliationStatus.aligned,
            "drift_summary": drifted_report.drift_summary.model_copy(
                update={
                    "status": ReconciliationStatus.aligned,
                    "manual_review_required": False,
                    "manual_review_reason": None,
                    "new_orders_blocked": False,
                    "new_orders_blocking_reasons": [],
                    "summary": "status=aligned",
                }
            ),
            "manual_review_required": False,
            "manual_review_reason": None,
            "new_orders_blocked": False,
            "new_orders_blocking_reasons": [],
        }
    )

    report = monitor_reconciliation_reports([drifted_report, recovered_report])

    assert report.report_count == 2
    assert report.drifted_count == 1
    assert report.aligned_count == 1
    assert report.material_drift_count == 1
    assert report.latest_status is ReconciliationStatus.aligned
    assert report.recovery_required is False
    assert report.recovered is True
    assert report.incident_runbook["runbook_id"] == "reconciliation_ok"
    assert report.summary.startswith("reports=2; aligned=1; drifted=1; incomplete=0; manual_review=1; new_orders_blocked=1; material_drift=1")
    assert report.metadata["material_drift_count"] == 1
    assert "material_drift_categories" in report.metadata
