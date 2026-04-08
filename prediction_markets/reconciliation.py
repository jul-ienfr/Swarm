from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from .capital_ledger import CapitalLedger, CapitalLedgerStore
from .models import CapitalLedgerSnapshot, LedgerPosition, TradeSide, VenueName
from .paper_trading import PaperTradeSimulation, PaperTradeStore
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .shadow_execution import ShadowExecutionEngine, ShadowExecutionResult, ShadowExecutionStore
from .storage import save_json


class ReconciliationStatus(str, Enum):
    aligned = "aligned"
    drifted = "drifted"
    incomplete = "incomplete"


class LedgerFieldDrift(BaseModel):
    schema_version: str = "v1"
    field_name: str
    expected: float
    observed: float
    delta: float
    tolerance: float
    within_tolerance: bool = True


class PositionDrift(BaseModel):
    schema_version: str = "v1"
    market_id: str
    venue: VenueName
    side: TradeSide
    expected_quantity: float = 0.0
    observed_quantity: float = 0.0
    quantity_drift: float = 0.0
    expected_entry_price: float = 0.0
    observed_entry_price: float = 0.0
    entry_price_drift: float = 0.0
    expected_mark_price: float | None = None
    observed_mark_price: float | None = None
    mark_price_drift: float | None = None
    expected_unrealized_pnl: float | None = None
    observed_unrealized_pnl: float | None = None
    unrealized_pnl_drift: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerComparison(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"reconcmp_{uuid4().hex[:12]}")
    label: str
    expected_snapshot_id: str
    observed_snapshot_id: str | None = None
    field_drifts: list[LedgerFieldDrift] = Field(default_factory=list)
    position_drifts: list[PositionDrift] = Field(default_factory=list)
    expected_position_count: int = 0
    observed_position_count: int = 0
    status: ReconciliationStatus = ReconciliationStatus.aligned
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionDrift(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"reconexec_{uuid4().hex[:12]}")
    run_id: str
    paper_trade_id: str | None = None
    shadow_id: str | None = None
    theoretical_price: float | None = None
    executable_price: float | None = None
    price_drift: float | None = None
    price_drift_bps: float | None = None
    paper_order_count: int = 1
    shadow_order_count: int = 0
    paper_fill_count: int = 0
    shadow_fill_count: int = 0
    paper_fee_paid: float = 0.0
    shadow_fee_paid: float = 0.0
    paper_slippage_bps: float | None = None
    shadow_slippage_bps: float | None = None
    slippage_drift_bps: float | None = None
    paper_settlement_status: str = "not_settled"
    filled_quantity_drift: float = 0.0
    average_fill_price_drift: float = 0.0
    fee_paid_drift: float = 0.0
    gross_notional_drift: float = 0.0
    cash_drift: float = 0.0
    reserved_cash_drift: float = 0.0
    equity_drift: float = 0.0
    settlement_status: str = "unavailable"
    status: ReconciliationStatus = ReconciliationStatus.aligned
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationDriftSummary(BaseModel):
    schema_version: str = "v1"
    status: ReconciliationStatus = ReconciliationStatus.incomplete
    manual_review_required: bool = False
    manual_review_reason: str | None = None
    price_drift_count: int = 0
    max_abs_price_drift_bps: float = 0.0
    avg_abs_price_drift_bps: float = 0.0
    slippage_drift_count: int = 0
    max_abs_slippage_drift_bps: float = 0.0
    avg_abs_slippage_drift_bps: float = 0.0
    fee_drift_count: int = 0
    settlement_drift_count: int = 0
    field_drift_count: int = 0
    position_drift_count: int = 0
    execution_drift_count: int = 0
    balance_drift_count: int = 0
    max_abs_cash_drift: float = 0.0
    max_abs_equity_drift: float = 0.0
    paper_trade_count: int = 0
    shadow_execution_count: int = 0
    observed_snapshot_count: int = 0
    new_orders_blocked: bool = False
    new_orders_blocking_reasons: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationReport(BaseModel):
    schema_version: str = "v1"
    reconciliation_id: str = Field(default_factory=lambda: f"recon_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    status: ReconciliationStatus = ReconciliationStatus.incomplete
    theoretical_ledger_snapshot: CapitalLedgerSnapshot
    paper_projection_snapshot: CapitalLedgerSnapshot
    shadow_projection_snapshot: CapitalLedgerSnapshot | None = None
    observed_ledger_snapshot: CapitalLedgerSnapshot | None = None
    paper_projection_drift: LedgerComparison | None = None
    shadow_projection_drift: LedgerComparison | None = None
    paper_vs_shadow_drift: LedgerComparison | None = None
    execution_drifts: list[ExecutionDrift] = Field(default_factory=list)
    drift_summary: ReconciliationDriftSummary = Field(default_factory=ReconciliationDriftSummary)
    manual_review_required: bool = False
    manual_review_reason: str | None = None
    new_orders_blocked: bool = False
    new_orders_blocking_reasons: list[str] = Field(default_factory=list)
    paper_trade_ids: list[str] = Field(default_factory=list)
    shadow_execution_ids: list[str] = Field(default_factory=list)
    observed_snapshot_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationMonitorReport(BaseModel):
    schema_version: str = "v1"
    monitor_id: str = Field(default_factory=lambda: f"reconmon_{uuid4().hex[:12]}")
    report_count: int = 0
    aligned_count: int = 0
    drifted_count: int = 0
    incomplete_count: int = 0
    manual_review_count: int = 0
    new_orders_blocked_count: int = 0
    material_drift_count: int = 0
    latest_reconciliation_id: str | None = None
    latest_status: ReconciliationStatus = ReconciliationStatus.incomplete
    latest_report: ReconciliationReport | None = None
    recovered: bool = False
    recovery_required: bool = False
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "reconciliation"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, report: ReconciliationReport) -> Path:
        path = self.root / f"{report.reconciliation_id}.json"
        save_json(path, report)
        return path

    def load(self, reconciliation_id: str) -> ReconciliationReport:
        return ReconciliationReport.model_validate_json((self.root / f"{reconciliation_id}.json").read_text(encoding="utf-8"))

    def list(self) -> list[ReconciliationReport]:
        if not self.root.exists():
            return []
        reports: list[ReconciliationReport] = []
        for path in sorted(self.root.glob("*.json")):
            reports.append(ReconciliationReport.model_validate_json(path.read_text(encoding="utf-8")))
        return reports


@dataclass
class ReconciliationEngine:
    cash_tolerance: float = 1e-6
    pnl_tolerance: float = 1e-6
    quantity_tolerance: float = 1e-8
    price_tolerance: float = 1e-6

    def reconcile(
        self,
        theoretical_ledger: CapitalLedgerSnapshot,
        *,
        paper_trades: Sequence[PaperTradeSimulation] | None = None,
        shadow_executions: Sequence[ShadowExecutionResult] | None = None,
        observed_ledger: CapitalLedgerSnapshot | None = None,
        observed_ledger_snapshots: Sequence[CapitalLedgerSnapshot] | None = None,
        paper_trade_ids: Sequence[str] | None = None,
        shadow_execution_ids: Sequence[str] | None = None,
        ledger_snapshot_ids: Sequence[str] | None = None,
        run_id: str | None = None,
        market_id: str | None = None,
        venue: VenueName | None = None,
        persist: bool = False,
        store: ReconciliationStore | None = None,
        base_dir: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReconciliationReport:
        paths = self._resolve_paths(store=store, base_dir=base_dir)
        paper_trades = list(paper_trades or [])
        shadow_executions = list(shadow_executions or [])
        observed_ledger_snapshots = list(observed_ledger_snapshots or [])

        if paper_trade_ids:
            paper_trades.extend(PaperTradeStore(paths=paths).load(trade_id) for trade_id in paper_trade_ids)
        if shadow_execution_ids:
            shadow_executions.extend(ShadowExecutionStore(paths=paths).load(shadow_id) for shadow_id in shadow_execution_ids)
        if ledger_snapshot_ids:
            observed_ledger_snapshots.extend(CapitalLedgerStore(paths=paths).load_snapshot(snapshot_id) for snapshot_id in ledger_snapshot_ids)

        observed_ledger = observed_ledger or (observed_ledger_snapshots[-1] if observed_ledger_snapshots else None)
        venue = venue or theoretical_ledger.venue
        market_id = market_id or theoretical_ledger.metadata.get("market_id") or self._infer_market_id(paper_trades, shadow_executions) or "reconciliation"
        run_id = run_id or self._infer_run_id(paper_trades, shadow_executions) or f"recon_{uuid4().hex[:12]}"

        paper_projection_snapshot = self._project_paper_trades(theoretical_ledger, paper_trades)
        shadow_projection_snapshot = self._project_shadow_executions(theoretical_ledger, shadow_executions)

        paper_projection_drift = self._compare_snapshots(
            label="paper_projection_vs_observed",
            expected=paper_projection_snapshot,
            observed=observed_ledger,
        )
        shadow_projection_drift = self._compare_snapshots(
            label="shadow_projection_vs_observed",
            expected=shadow_projection_snapshot,
            observed=observed_ledger,
        ) if shadow_projection_snapshot is not None else None
        paper_vs_shadow_drift = self._compare_snapshots(
            label="paper_vs_shadow",
            expected=paper_projection_snapshot,
            observed=shadow_projection_snapshot,
        ) if shadow_projection_snapshot is not None else None

        execution_drifts = self._compare_execution_sequences(paper_trades=paper_trades, shadow_executions=shadow_executions)
        drift_summary = self._summarize(
            paper_projection_drift=paper_projection_drift,
            shadow_projection_drift=shadow_projection_drift,
            paper_vs_shadow_drift=paper_vs_shadow_drift,
            execution_drifts=execution_drifts,
            observed_ledger=observed_ledger,
            paper_trade_count=len(paper_trades),
            shadow_execution_count=len(shadow_executions),
            observed_snapshot_count=len(observed_ledger_snapshots) if observed_ledger_snapshots else (1 if observed_ledger is not None else 0),
        )

        report = ReconciliationReport(
            run_id=run_id,
            market_id=market_id,
            venue=venue,
            status=drift_summary.status,
            theoretical_ledger_snapshot=theoretical_ledger.model_copy(deep=True),
            paper_projection_snapshot=paper_projection_snapshot,
            shadow_projection_snapshot=shadow_projection_snapshot,
            observed_ledger_snapshot=observed_ledger.model_copy(deep=True) if observed_ledger is not None else None,
            paper_projection_drift=paper_projection_drift,
            shadow_projection_drift=shadow_projection_drift,
            paper_vs_shadow_drift=paper_vs_shadow_drift,
            execution_drifts=execution_drifts,
            drift_summary=drift_summary,
            manual_review_required=drift_summary.manual_review_required,
            manual_review_reason=drift_summary.manual_review_reason,
            paper_trade_ids=[trade.trade_id for trade in paper_trades],
            shadow_execution_ids=[execution.shadow_id for execution in shadow_executions],
            observed_snapshot_ids=[snapshot.snapshot_id for snapshot in observed_ledger_snapshots],
            metadata=metadata or {},
        )
        report.new_orders_blocked = drift_summary.new_orders_blocked
        report.new_orders_blocking_reasons = list(drift_summary.new_orders_blocking_reasons)
        report.metadata = {
            **dict(report.metadata),
            "new_orders_blocked": report.new_orders_blocked,
            "new_orders_blocking_reasons": list(report.new_orders_blocking_reasons),
            "reconciliation_new_orders_blocked": report.new_orders_blocked,
            "reconciliation_new_orders_blocking_reasons": list(report.new_orders_blocking_reasons),
            "drift_summary": drift_summary.model_dump(mode="json"),
        }

        if persist:
            (store or ReconciliationStore(paths=paths)).save(report)
        return report

    def _project_paper_trades(
        self,
        theoretical_ledger: CapitalLedgerSnapshot,
        paper_trades: Sequence[PaperTradeSimulation],
    ) -> CapitalLedgerSnapshot:
        ledger = CapitalLedger.from_snapshot(theoretical_ledger)
        for paper_trade in paper_trades:
            ledger.apply_paper_trade(
                paper_trade,
                mark_price=paper_trade.reference_price if paper_trade.reference_price is not None else paper_trade.average_fill_price,
            )
        return ledger.current_snapshot()

    def _project_shadow_executions(
        self,
        theoretical_ledger: CapitalLedgerSnapshot,
        shadow_executions: Sequence[ShadowExecutionResult],
    ) -> CapitalLedgerSnapshot | None:
        if not shadow_executions:
            return None
        ledger = CapitalLedger.from_snapshot(theoretical_ledger)
        for shadow_execution in shadow_executions:
            if shadow_execution.paper_trade is not None:
                ledger.apply_paper_trade(
                    shadow_execution.paper_trade,
                    mark_price=shadow_execution.paper_trade.average_fill_price
                    if shadow_execution.paper_trade.average_fill_price is not None
                    else shadow_execution.paper_trade.reference_price,
                )
                if shadow_execution.ledger_after is not None:
                    ledger = CapitalLedger.from_snapshot(shadow_execution.ledger_after)
            elif shadow_execution.ledger_after is not None:
                ledger = CapitalLedger.from_snapshot(shadow_execution.ledger_after)
        return ledger.current_snapshot()

    def _compare_snapshots(
        self,
        *,
        label: str,
        expected: CapitalLedgerSnapshot,
        observed: CapitalLedgerSnapshot | None,
    ) -> LedgerComparison | None:
        if observed is None:
            return None
        field_specs = [
            ("cash", self.cash_tolerance),
            ("reserved_cash", self.cash_tolerance),
            ("realized_pnl", self.pnl_tolerance),
            ("unrealized_pnl", self.pnl_tolerance),
            ("equity", self.pnl_tolerance),
        ]
        field_drifts: list[LedgerFieldDrift] = []
        for field_name, tolerance in field_specs:
            expected_value = float(getattr(expected, field_name))
            observed_value = float(getattr(observed, field_name))
            delta = round(observed_value - expected_value, 6)
            field_drifts.append(
                LedgerFieldDrift(
                    field_name=field_name,
                    expected=expected_value,
                    observed=observed_value,
                    delta=delta,
                    tolerance=tolerance,
                    within_tolerance=abs(delta) <= tolerance,
                )
            )

        position_drifts = self._compare_positions(expected.positions, observed.positions)
        notes: list[str] = []
        if not expected.positions and not observed.positions:
            notes.append("no_positions")
        elif len(expected.positions) != len(observed.positions):
            notes.append("position_count_mismatch")

        status = self._status_from_drifts(field_drifts, position_drifts, notes=notes)
        return LedgerComparison(
            label=label,
            expected_snapshot_id=expected.snapshot_id,
            observed_snapshot_id=observed.snapshot_id,
            field_drifts=field_drifts,
            position_drifts=position_drifts,
            expected_position_count=len(expected.positions),
            observed_position_count=len(observed.positions),
            status=status,
            notes=notes,
        )

    def _compare_positions(
        self,
        expected_positions: Sequence[LedgerPosition],
        observed_positions: Sequence[LedgerPosition],
    ) -> list[PositionDrift]:
        expected_map = {_position_key(position): position for position in expected_positions}
        observed_map = {_position_key(position): position for position in observed_positions}
        drift_keys = sorted(set(expected_map) | set(observed_map))
        drifts: list[PositionDrift] = []
        for key in drift_keys:
            expected = expected_map.get(key)
            observed = observed_map.get(key)
            if expected is None and observed is None:
                continue
            market_id, venue_name, side_name = key
            venue = VenueName(venue_name)
            side = TradeSide(side_name)
            if expected is None:
                drifts.append(
                    PositionDrift(
                        market_id=market_id,
                        venue=venue,
                        side=side,
                        expected_quantity=0.0,
                        observed_quantity=observed.quantity,
                        quantity_drift=round(observed.quantity, 8),
                        expected_entry_price=0.0,
                        observed_entry_price=observed.entry_price,
                        entry_price_drift=round(observed.entry_price, 6),
                        expected_mark_price=None,
                        observed_mark_price=observed.mark_price,
                        mark_price_drift=observed.mark_price,
                        expected_unrealized_pnl=0.0,
                        observed_unrealized_pnl=observed.unrealized_pnl,
                        unrealized_pnl_drift=observed.unrealized_pnl,
                        metadata={"reason": "unexpected_observed_position"},
                    )
                )
                continue
            if observed is None:
                drifts.append(
                    PositionDrift(
                        market_id=market_id,
                        venue=venue,
                        side=side,
                        expected_quantity=expected.quantity,
                        observed_quantity=0.0,
                        quantity_drift=round(-expected.quantity, 8),
                        expected_entry_price=expected.entry_price,
                        observed_entry_price=0.0,
                        entry_price_drift=round(-expected.entry_price, 6),
                        expected_mark_price=expected.mark_price,
                        observed_mark_price=None,
                        mark_price_drift=None if expected.mark_price is None else round(-expected.mark_price, 6),
                        expected_unrealized_pnl=expected.unrealized_pnl,
                        observed_unrealized_pnl=0.0,
                        unrealized_pnl_drift=None if expected.unrealized_pnl is None else round(-expected.unrealized_pnl, 6),
                        metadata={"reason": "missing_observed_position"},
                    )
                )
                continue

            quantity_drift = round(observed.quantity - expected.quantity, 8)
            entry_price_drift = round(observed.entry_price - expected.entry_price, 6)
            mark_price_drift = None
            if expected.mark_price is not None and observed.mark_price is not None:
                mark_price_drift = round(observed.mark_price - expected.mark_price, 6)
            unrealized_pnl_drift = None
            if expected.unrealized_pnl is not None and observed.unrealized_pnl is not None:
                unrealized_pnl_drift = round(observed.unrealized_pnl - expected.unrealized_pnl, 6)

            drifts.append(
                PositionDrift(
                    market_id=market_id,
                    venue=venue,
                    side=side,
                    expected_quantity=expected.quantity,
                    observed_quantity=observed.quantity,
                    quantity_drift=quantity_drift,
                    expected_entry_price=expected.entry_price,
                    observed_entry_price=observed.entry_price,
                    entry_price_drift=entry_price_drift,
                    expected_mark_price=expected.mark_price,
                    observed_mark_price=observed.mark_price,
                    mark_price_drift=mark_price_drift,
                    expected_unrealized_pnl=expected.unrealized_pnl,
                    observed_unrealized_pnl=observed.unrealized_pnl,
                    unrealized_pnl_drift=unrealized_pnl_drift,
                    metadata={},
                )
            )
        return drifts

    def _compare_execution_sequences(
        self,
        *,
        paper_trades: Sequence[PaperTradeSimulation],
        shadow_executions: Sequence[ShadowExecutionResult],
    ) -> list[ExecutionDrift]:
        if not paper_trades and not shadow_executions:
            return []
        shadow_by_trade_id: dict[str, ShadowExecutionResult] = {}
        shadow_by_run_id: dict[str, ShadowExecutionResult] = {}
        for shadow_execution in shadow_executions:
            shadow_by_run_id[shadow_execution.run_id] = shadow_execution
            if shadow_execution.paper_trade is not None:
                shadow_by_trade_id[shadow_execution.paper_trade.trade_id] = shadow_execution

        drifts: list[ExecutionDrift] = []
        matched_shadow_ids: set[str] = set()
        matched_paper_trade_ids: set[str] = set()
        for paper_trade in paper_trades:
            shadow = shadow_by_trade_id.get(paper_trade.trade_id) or shadow_by_run_id.get(paper_trade.run_id)
            if shadow is None or shadow.paper_trade is None:
                continue
            theoretical_price, executable_price, price_drift, price_drift_bps = self._execution_price_surface(
                paper_trade,
                shadow,
            )
            matched_shadow_ids.add(shadow.shadow_id)
            matched_paper_trade_ids.add(paper_trade.trade_id)
            observed = shadow.paper_trade
            filled_quantity_drift = round(observed.filled_quantity - paper_trade.filled_quantity, 8)
            average_fill_price_drift = round((observed.average_fill_price or 0.0) - (paper_trade.average_fill_price or 0.0), 6)
            fee_paid_drift = round(observed.fee_paid - paper_trade.fee_paid, 6)
            gross_notional_drift = round(observed.gross_notional - paper_trade.gross_notional, 6)
            cash_drift = 0.0
            reserved_cash_drift = 0.0
            equity_drift = 0.0
            if shadow.ledger_before is not None and shadow.ledger_after is not None:
                cash_drift = round(shadow.ledger_after.cash - shadow.ledger_before.cash, 6)
                reserved_cash_drift = round(shadow.ledger_after.reserved_cash - shadow.ledger_before.reserved_cash, 6)
                equity_drift = round(shadow.ledger_after.equity - shadow.ledger_before.equity, 6)
            notes: list[str] = []
            if abs(filled_quantity_drift) > self.quantity_tolerance:
                notes.append("filled_quantity_drift")
            if abs(average_fill_price_drift) > self.price_tolerance:
                notes.append("average_fill_price_drift")
            if price_drift_bps is not None and abs(price_drift_bps) > max(1e-6, self.price_tolerance * 10000.0):
                notes.append("price_drift")
            paper_slippage_bps = paper_trade.slippage_bps
            shadow_slippage_bps = observed.slippage_bps
            slippage_drift_bps: float | None = None
            if paper_slippage_bps is not None and shadow_slippage_bps is not None:
                slippage_drift_bps = round(shadow_slippage_bps - paper_slippage_bps, 2)
                if abs(slippage_drift_bps) > max(1e-6, self.price_tolerance * 10000.0):
                    notes.append("slippage_drift")
            if abs(fee_paid_drift) > self.pnl_tolerance:
                notes.append("fee_paid_drift")
            if abs(gross_notional_drift) > self.pnl_tolerance:
                notes.append("gross_notional_drift")
            if shadow.ledger_change is None:
                notes.append("settlement_unconfirmed")
            status = ReconciliationStatus.aligned if not notes else ReconciliationStatus.drifted
            drifts.append(
                ExecutionDrift(
                    run_id=paper_trade.run_id,
                    paper_trade_id=paper_trade.trade_id,
                    shadow_id=shadow.shadow_id,
                    theoretical_price=theoretical_price,
                    executable_price=executable_price,
                    price_drift=price_drift,
                    price_drift_bps=price_drift_bps,
                    paper_order_count=max(1, int(getattr(paper_trade, "order_count", 1) or 1)),
                    shadow_order_count=1,
                    paper_fill_count=len(paper_trade.fills),
                    shadow_fill_count=len(observed.fills),
                    paper_fee_paid=paper_trade.fee_paid,
                    shadow_fee_paid=observed.fee_paid,
                    paper_slippage_bps=paper_trade.slippage_bps,
                    shadow_slippage_bps=observed.slippage_bps,
                    slippage_drift_bps=slippage_drift_bps,
                    paper_settlement_status=getattr(paper_trade, "settlement_status", "not_settled"),
                    filled_quantity_drift=filled_quantity_drift,
                    average_fill_price_drift=average_fill_price_drift,
                    fee_paid_drift=fee_paid_drift,
                    gross_notional_drift=gross_notional_drift,
                    cash_drift=cash_drift,
                    reserved_cash_drift=reserved_cash_drift,
                    equity_drift=equity_drift,
                    settlement_status=self._settlement_status(shadow),
                    status=status,
                    notes=notes,
                    metadata={
                        "paper_status": paper_trade.status.value,
                        "shadow_would_trade": shadow.would_trade,
                        "settlement_status": self._settlement_status(shadow),
                    },
                )
            )
        for shadow_execution in shadow_executions:
            if shadow_execution.shadow_id in matched_shadow_ids:
                continue
            if shadow_execution.paper_trade is None:
                continue
            if shadow_execution.paper_trade.trade_id in matched_paper_trade_ids:
                continue
            theoretical_price, executable_price, price_drift, price_drift_bps = self._execution_price_surface(
                shadow_execution.paper_trade,
                shadow_execution,
            )
            drifts.append(
                ExecutionDrift(
                    run_id=shadow_execution.run_id,
                    paper_trade_id=shadow_execution.paper_trade.trade_id,
                    shadow_id=shadow_execution.shadow_id,
                    theoretical_price=theoretical_price,
                    executable_price=executable_price,
                    price_drift=price_drift,
                    price_drift_bps=price_drift_bps,
                    paper_order_count=max(1, int(getattr(shadow_execution.paper_trade, "order_count", 1) or 1)),
                    shadow_order_count=1,
                    paper_fill_count=len(shadow_execution.paper_trade.fills),
                    shadow_fill_count=len(shadow_execution.paper_trade.fills),
                    paper_fee_paid=shadow_execution.paper_trade.fee_paid,
                    shadow_fee_paid=shadow_execution.paper_trade.fee_paid,
                    paper_slippage_bps=shadow_execution.paper_trade.slippage_bps,
                    shadow_slippage_bps=shadow_execution.paper_trade.slippage_bps,
                    slippage_drift_bps=0.0,
                    paper_settlement_status=getattr(shadow_execution.paper_trade, "settlement_status", "not_settled"),
                    settlement_status=self._settlement_status(shadow_execution),
                    status=ReconciliationStatus.drifted,
                    notes=["missing_paper_trade"],
                    metadata={
                        "paper_status": shadow_execution.paper_trade.status.value,
                        "shadow_would_trade": shadow_execution.would_trade,
                    },
                )
            )
        if paper_trades:
            for paper_trade in paper_trades:
                if paper_trade.trade_id in matched_paper_trade_ids:
                    continue
                theoretical_price, executable_price, price_drift, price_drift_bps = self._execution_price_surface(paper_trade)
                drifts.append(
                    ExecutionDrift(
                        run_id=paper_trade.run_id,
                        paper_trade_id=paper_trade.trade_id,
                        theoretical_price=theoretical_price,
                        executable_price=executable_price,
                        price_drift=price_drift,
                        price_drift_bps=price_drift_bps,
                        paper_order_count=max(1, int(getattr(paper_trade, "order_count", 1) or 1)),
                        shadow_order_count=0,
                        paper_fill_count=len(paper_trade.fills),
                        shadow_fill_count=0,
                        paper_fee_paid=paper_trade.fee_paid,
                        shadow_fee_paid=0.0,
                        paper_slippage_bps=paper_trade.slippage_bps,
                        shadow_slippage_bps=None,
                        slippage_drift_bps=None,
                        paper_settlement_status=getattr(paper_trade, "settlement_status", "not_settled"),
                        settlement_status="unavailable",
                        status=ReconciliationStatus.drifted,
                        notes=["missing_shadow_execution"],
                        metadata={
                            "paper_status": paper_trade.status.value,
                            "shadow_would_trade": False,
                        },
                    )
                )
        return drifts

    def _summarize(
        self,
        *,
        paper_projection_drift: LedgerComparison | None,
        shadow_projection_drift: LedgerComparison | None,
        paper_vs_shadow_drift: LedgerComparison | None,
        execution_drifts: Sequence[ExecutionDrift],
        observed_ledger: CapitalLedgerSnapshot | None,
        paper_trade_count: int,
        shadow_execution_count: int,
        observed_snapshot_count: int,
    ) -> ReconciliationDriftSummary:
        comparisons = [
            comparison
            for comparison in (paper_projection_drift, shadow_projection_drift, paper_vs_shadow_drift)
            if comparison is not None
        ]
        material_observed_comparisons = [
            comparison
            for comparison in (paper_projection_drift, shadow_projection_drift)
            if comparison is not None
        ]
        field_drift_count = sum(
            1
            for comparison in comparisons
            for field_drift in comparison.field_drifts
            if not field_drift.within_tolerance
        )
        position_drift_count = sum(
            1
            for comparison in comparisons
            for position_drift in comparison.position_drifts
            if self._position_drift_is_significant(position_drift)
        )
        execution_drift_count = sum(1 for execution in execution_drifts if execution.status == ReconciliationStatus.drifted)
        balance_drift_count = sum(
            1
            for comparison in comparisons
            for field_drift in comparison.field_drifts
            if field_drift.field_name in {"cash", "reserved_cash", "equity"} and not field_drift.within_tolerance
        )
        max_abs_cash_drift = max(
            [abs(field_drift.delta) for comparison in comparisons for field_drift in comparison.field_drifts if field_drift.field_name == "cash"],
            default=0.0,
        )
        max_abs_equity_drift = max(
            [abs(field_drift.delta) for comparison in comparisons for field_drift in comparison.field_drifts if field_drift.field_name == "equity"],
            default=0.0,
        )
        price_drift_values = [
            abs(execution.price_drift_bps)
            for execution in execution_drifts
            if execution.price_drift_bps is not None
        ]
        slippage_drift_values = [
            abs(execution.slippage_drift_bps)
            for execution in execution_drifts
            if execution.slippage_drift_bps is not None
        ]
        price_drift_count = sum(
            1
            for execution in execution_drifts
            if execution.price_drift_bps is not None
            and abs(execution.price_drift_bps) > max(1e-6, self.price_tolerance * 10_000.0)
        )
        slippage_drift_count = sum(
            1
            for execution in execution_drifts
            if execution.slippage_drift_bps is not None
            and abs(execution.slippage_drift_bps) > max(1e-6, self.price_tolerance * 10_000.0)
        )
        max_abs_price_drift_bps = max(price_drift_values, default=0.0)
        avg_abs_price_drift_bps = round(sum(price_drift_values) / len(price_drift_values), 2) if price_drift_values else 0.0
        max_abs_slippage_drift_bps = max(slippage_drift_values, default=0.0)
        avg_abs_slippage_drift_bps = round(sum(slippage_drift_values) / len(slippage_drift_values), 2) if slippage_drift_values else 0.0
        fee_drift_count = sum(1 for execution in execution_drifts if abs(execution.fee_paid_drift) > self.pnl_tolerance)
        settlement_drift_count = sum(1 for execution in execution_drifts if execution.settlement_status != "settled")
        new_orders_blocked = False
        new_orders_blocking_reasons: list[str] = []
        manual_review_required = False
        manual_review_reason: str | None = None
        if observed_ledger is None:
            status = ReconciliationStatus.incomplete
            manual_review_required = True
            manual_review_reason = "observed_ledger_missing"
            new_orders_blocked = True
            new_orders_blocking_reasons.append("observed_ledger_missing")
        elif (
            any(comparison.status == ReconciliationStatus.drifted for comparison in material_observed_comparisons)
            or (paper_vs_shadow_drift is not None and paper_vs_shadow_drift.status == ReconciliationStatus.drifted)
            or execution_drift_count > 0
        ):
            status = ReconciliationStatus.drifted
            manual_review_required = True
            manual_review_reason = "material_drift_detected"
            new_orders_blocked = True
            new_orders_blocking_reasons.append("material_drift_detected")
        else:
            status = ReconciliationStatus.aligned
        if price_drift_count > 0:
            new_orders_blocked = True
            if "price_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("price_drift_detected")
        if fee_drift_count > 0:
            new_orders_blocked = True
            if "fee_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("fee_drift_detected")
        if settlement_drift_count > 0:
            new_orders_blocked = True
            if "settlement_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("settlement_drift_detected")
        if position_drift_count > 0:
            new_orders_blocked = True
            if "position_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("position_drift_detected")
        if balance_drift_count > 0:
            new_orders_blocked = True
            if "balance_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("balance_drift_detected")
        if paper_vs_shadow_drift is not None and paper_vs_shadow_drift.status == ReconciliationStatus.drifted:
            new_orders_blocked = True
            if "paper_vs_shadow_drift_detected" not in new_orders_blocking_reasons:
                new_orders_blocking_reasons.append("paper_vs_shadow_drift_detected")
            if not manual_review_required:
                manual_review_required = True
            if manual_review_reason is None:
                manual_review_reason = "paper_vs_shadow_drift_detected"
        drift_categories = list(
            dict.fromkeys(
                [
                    *(["price"] if price_drift_count > 0 else []),
                    *(["fee"] if fee_drift_count > 0 else []),
                    *(["settlement"] if settlement_drift_count > 0 else []),
                    *(["position"] if position_drift_count > 0 else []),
                    *(["balance"] if balance_drift_count > 0 else []),
                    *(["paper_vs_shadow"] if paper_vs_shadow_drift is not None and paper_vs_shadow_drift.status == ReconciliationStatus.drifted else []),
                ]
            )
        )
        summary = (
            f"status={status.value}; price_drift_count={price_drift_count}; field_drift_count={field_drift_count}; "
            f"position_drift_count={position_drift_count}; execution_drift_count={execution_drift_count}; "
            f"slippage_drift_count={slippage_drift_count}; fee_drift_count={fee_drift_count}; "
            f"settlement_drift_count={settlement_drift_count}; "
            f"balance_drift_count={balance_drift_count}; blocked={new_orders_blocked}"
        )
        return ReconciliationDriftSummary(
            status=status,
            manual_review_required=manual_review_required,
            manual_review_reason=manual_review_reason,
            price_drift_count=price_drift_count,
            max_abs_price_drift_bps=round(max_abs_price_drift_bps, 2),
            avg_abs_price_drift_bps=avg_abs_price_drift_bps,
            slippage_drift_count=slippage_drift_count,
            max_abs_slippage_drift_bps=round(max_abs_slippage_drift_bps, 2),
            avg_abs_slippage_drift_bps=avg_abs_slippage_drift_bps,
            fee_drift_count=fee_drift_count,
            settlement_drift_count=settlement_drift_count,
            field_drift_count=field_drift_count,
            position_drift_count=position_drift_count,
            execution_drift_count=execution_drift_count,
            balance_drift_count=balance_drift_count,
            max_abs_cash_drift=round(max_abs_cash_drift, 6),
            max_abs_equity_drift=round(max_abs_equity_drift, 6),
            paper_trade_count=paper_trade_count,
            shadow_execution_count=shadow_execution_count,
            observed_snapshot_count=observed_snapshot_count,
            new_orders_blocked=new_orders_blocked,
            new_orders_blocking_reasons=list(dict.fromkeys(new_orders_blocking_reasons)),
            summary=summary,
            metadata={
                "drift_categories": drift_categories,
                "price_drift_count": price_drift_count,
                "fee_drift_count": fee_drift_count,
                "settlement_drift_count": settlement_drift_count,
                "balance_drift_count": balance_drift_count,
                "position_drift_count": position_drift_count,
            },
        )

    @staticmethod
    def _position_drift_is_significant(position_drift: PositionDrift) -> bool:
        if abs(position_drift.quantity_drift) > 1e-8:
            return True
        if abs(position_drift.entry_price_drift) > 1e-6:
            return True
        if position_drift.mark_price_drift is not None and abs(position_drift.mark_price_drift) > 1e-6:
            return True
        if position_drift.unrealized_pnl_drift is not None and abs(position_drift.unrealized_pnl_drift) > 1e-6:
            return True
        return False

    @staticmethod
    def _status_from_drifts(
        field_drifts: Sequence[LedgerFieldDrift],
        position_drifts: Sequence[PositionDrift],
        *,
        notes: Sequence[str] | None = None,
    ) -> ReconciliationStatus:
        if any(not field_drift.within_tolerance for field_drift in field_drifts):
            return ReconciliationStatus.drifted
        if any(
            abs(position_drift.quantity_drift) > 1e-8
            or abs(position_drift.entry_price_drift) > 1e-6
            or (position_drift.mark_price_drift is not None and abs(position_drift.mark_price_drift) > 1e-6)
            or (position_drift.unrealized_pnl_drift is not None and abs(position_drift.unrealized_pnl_drift) > 1e-6)
            for position_drift in position_drifts
        ):
            return ReconciliationStatus.drifted
        if notes and "position_count_mismatch" in notes:
            return ReconciliationStatus.drifted
        return ReconciliationStatus.aligned

    @staticmethod
    def _settlement_status(shadow: ShadowExecutionResult) -> str:
        if shadow.paper_trade is None:
            return "unavailable"
        if shadow.ledger_after is None:
            return "unsettled"
        if shadow.ledger_change is None:
            return "observed"
        return "settled"

    @staticmethod
    def _execution_price_surface(
        paper_trade: PaperTradeSimulation | None,
        shadow_execution: ShadowExecutionResult | None = None,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        source_trade = shadow_execution.paper_trade if shadow_execution is not None and shadow_execution.paper_trade is not None else paper_trade
        if source_trade is None:
            return None, None, None, None
        theoretical_price = source_trade.reference_price
        executable_price = source_trade.average_fill_price if source_trade.average_fill_price is not None else source_trade.reference_price
        if theoretical_price is None or executable_price is None:
            return theoretical_price, executable_price, None, None
        price_drift = round(executable_price - theoretical_price, 6)
        price_drift_bps = round(price_drift * 10_000.0, 2)
        return theoretical_price, executable_price, price_drift, price_drift_bps

    @staticmethod
    def _infer_run_id(
        paper_trades: Sequence[PaperTradeSimulation],
        shadow_executions: Sequence[ShadowExecutionResult],
    ) -> str | None:
        if paper_trades:
            return paper_trades[0].run_id
        if shadow_executions:
            return shadow_executions[0].run_id
        return None

    @staticmethod
    def _infer_market_id(
        paper_trades: Sequence[PaperTradeSimulation],
        shadow_executions: Sequence[ShadowExecutionResult],
    ) -> str | None:
        if paper_trades:
            return paper_trades[0].market_id
        if shadow_executions:
            return shadow_executions[0].market_id
        return None

    @staticmethod
    def _resolve_paths(
        *,
        store: ReconciliationStore | None,
        base_dir: str | Path | None,
    ) -> PredictionMarketPaths:
        if store is not None:
            return store.paths
        if base_dir is not None:
            return PredictionMarketPaths(Path(base_dir))
        return default_prediction_market_paths()

    def blocking_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.manual_review_required:
            reasons.append(self.manual_review_reason or "manual_review_required")
        if self.status == ReconciliationStatus.drifted:
            reasons.append("reconciliation_drifted")
        if self.paper_projection_drift is not None and self.paper_projection_drift.status == ReconciliationStatus.drifted:
            reasons.append("paper_projection_drifted")
        if self.shadow_projection_drift is not None and self.shadow_projection_drift.status == ReconciliationStatus.drifted:
            reasons.append("shadow_projection_drifted")
        if self.paper_vs_shadow_drift is not None and self.paper_vs_shadow_drift.status == ReconciliationStatus.drifted:
            reasons.append("paper_vs_shadow_drifted")
        return list(dict.fromkeys(reasons))

    def has_open_drift(self) -> bool:
        return self.new_orders_blocked or self.status == ReconciliationStatus.drifted or bool(self.blocking_reasons())


def monitor_reconciliation_reports(
    reports: Sequence[ReconciliationReport] | ReconciliationReport,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> ReconciliationMonitorReport:
    report_list = [reports] if isinstance(reports, ReconciliationReport) else list(reports)
    if not report_list:
        return ReconciliationMonitorReport(
            summary="reports=0; status=empty",
            metadata=dict(metadata or {}),
        )

    latest_report = report_list[-1]
    aligned_count = sum(1 for report in report_list if report.status == ReconciliationStatus.aligned)
    drifted_count = sum(1 for report in report_list if report.status == ReconciliationStatus.drifted)
    incomplete_count = sum(1 for report in report_list if report.status == ReconciliationStatus.incomplete)
    manual_review_count = sum(1 for report in report_list if report.manual_review_required or report.drift_summary.manual_review_required)
    new_orders_blocked_count = sum(1 for report in report_list if report.new_orders_blocked or report.drift_summary.new_orders_blocked)
    material_drift_categories = sorted(
        {
            category
            for report in report_list
            for category in (report.drift_summary.metadata.get("drift_categories") or [])
            if category
        }
    )
    material_drift_count = sum(
        1
        for report in report_list
        if (
            report.status == ReconciliationStatus.drifted
            or report.manual_review_required
            or report.new_orders_blocked
            or bool(report.drift_summary.metadata.get("drift_categories"))
        )
    )

    prior_unhealthy = any(
        report.status != ReconciliationStatus.aligned or report.manual_review_required or report.new_orders_blocked
        for report in report_list[:-1]
    )
    recovered = latest_report.status == ReconciliationStatus.aligned and prior_unhealthy
    recovery_required = latest_report.status != ReconciliationStatus.aligned or latest_report.manual_review_required or latest_report.new_orders_blocked

    incident_runbook = _reconciliation_monitor_runbook(latest_report, recovery_required=recovery_required, recovered=recovered)
    summary = (
        f"reports={len(report_list)}; aligned={aligned_count}; drifted={drifted_count}; incomplete={incomplete_count}; "
        f"manual_review={manual_review_count}; new_orders_blocked={new_orders_blocked_count}; "
        f"material_drift={material_drift_count}; "
        f"latest={latest_report.status.value}; recovery_required={recovery_required}; recovered={recovered}"
    )
    return ReconciliationMonitorReport(
        report_count=len(report_list),
        aligned_count=aligned_count,
        drifted_count=drifted_count,
        incomplete_count=incomplete_count,
        manual_review_count=manual_review_count,
        new_orders_blocked_count=new_orders_blocked_count,
        material_drift_count=material_drift_count,
        latest_reconciliation_id=latest_report.reconciliation_id,
        latest_status=latest_report.status,
        latest_report=latest_report,
        recovered=recovered,
        recovery_required=recovery_required,
        incident_runbook=incident_runbook,
        summary=summary,
        metadata={
            **dict(metadata or {}),
            "latest_market_id": latest_report.market_id,
            "latest_venue": latest_report.venue.value,
            "reconciliation_ids": [report.reconciliation_id for report in report_list],
            "status_sequence": [report.status.value for report in report_list],
            "material_drift_count": material_drift_count,
            "material_drift_categories": material_drift_categories,
        },
    )


def _position_key(position: LedgerPosition) -> tuple[str, str, str]:
    return (position.market_id, position.venue.value, position.side.value)


def _reconciliation_monitor_runbook(
    report: ReconciliationReport,
    *,
    recovery_required: bool,
    recovered: bool,
) -> dict[str, Any]:
    if not recovery_required:
        return {
            "runbook_id": "reconciliation_ok",
            "runbook_kind": "state",
            "summary": "Reconciliation is aligned and no new orders are blocked.",
            "recommended_action": "continue_shadow",
            "owner": "operator",
            "priority": "low",
            "status": "ok",
            "trigger_reasons": [],
            "next_steps": [
                "Keep polling the reconciliation engine on a regular cadence.",
                "Continue recording paper and shadow snapshots for the next incident review.",
            ],
            "signals": {
                "recovered": recovered,
                "manual_review_required": report.manual_review_required,
                "new_orders_blocked": report.new_orders_blocked,
            },
        }

    trigger_reason_candidates = list(report.new_orders_blocking_reasons)
    trigger_reason_candidates.extend(report.drift_summary.new_orders_blocking_reasons or [])
    trigger_reason_candidates.extend(report.blocking_reasons())
    if report.manual_review_required and report.manual_review_reason:
        trigger_reason_candidates.append(report.manual_review_reason)
    drift_categories = []
    if isinstance(report.drift_summary.metadata, dict):
        drift_categories = list(report.drift_summary.metadata.get("drift_categories") or [])
        trigger_reason_candidates.extend(f"drift_category:{category}" for category in drift_categories)
    trigger_reasons = [reason for reason in dict.fromkeys(trigger_reason_candidates) if reason]
    return {
        "runbook_id": "reconciliation_drifted",
        "runbook_kind": "incident" if report.new_orders_blocked or report.manual_review_required else "degraded_mode",
        "summary": "Reconciliation is not aligned; freeze new orders and keep the recovery loop running.",
        "recommended_action": "freeze_new_orders",
        "owner": "operator",
        "priority": "high" if report.manual_review_required or report.new_orders_blocked else "medium",
        "status": "blocked" if report.manual_review_required or report.new_orders_blocked else "degraded",
        "trigger_reasons": trigger_reasons,
        "next_steps": [
            "Stop new order placement until reconciliation returns to aligned.",
            "Run the reconciliation engine again on the next snapshot batch.",
            "Review the drift summary and operator notes before resuming.",
        ],
        "signals": {
            "recovered": recovered,
            "manual_review_required": report.manual_review_required,
            "new_orders_blocked": report.new_orders_blocked,
            "latest_status": report.status.value,
            "drift_categories": drift_categories,
            "fee_drift_count": getattr(report.drift_summary, "fee_drift_count", 0),
            "settlement_drift_count": getattr(report.drift_summary, "settlement_drift_count", 0),
        },
    }
