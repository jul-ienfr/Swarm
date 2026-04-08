from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .capital_ledger import CapitalLedgerChange
from .execution_edge import ExecutableEdge
from .models import CapitalLedgerSnapshot, ExecutionProjection, ExecutionProjectionVerdict, LedgerPosition, MarketDescriptor, MarketSnapshot, ResolutionStatus, TradeIntent, TradeSide, VenueName
from .paper_trading import PaperTradeFill, PaperTradeSimulation, PaperTradeSimulator, PaperTradeStatus
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .resolution_guard import ResolutionGuardReport, evaluate_resolution_policy
from .storage import save_json


class MarketExecutionMode(str, Enum):
    bounded_dry_run = "bounded_dry_run"
    bounded_live = "bounded_live"


class MarketExecutionStatus(str, Enum):
    blocked = "blocked"
    cancelled = "cancelled"
    filled = "filled"
    partial = "partial"
    rejected = "rejected"


class MarketExecutionOrderType(str, Enum):
    market = "market"
    limit = "limit"


class MarketExecutionOrder(BaseModel):
    schema_version: str = "v1"
    execution_id: str = Field(default_factory=lambda: f"mexec_{uuid4().hex[:12]}")
    order_id: str = Field(default_factory=lambda: f"mord_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide = TradeSide.buy
    order_type: MarketExecutionOrderType = MarketExecutionOrderType.market
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    limit_price: float | None = None
    time_in_force: str = "ioc"
    status: str = "submitted"
    venue_order_submission_state: str = "simulated"
    venue_order_ack_state: str = "not_acknowledged"
    venue_order_cancel_state: str = "not_cancelled"
    venue_order_execution_state: str = "simulated"
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    acknowledged_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_reason: str | None = None
    cancelled_by: str | None = None
    status_history: list[str] = Field(default_factory=list)
    order_source: str = "unavailable"
    order_path: str = "unavailable"
    order_cancel_path: str = "unavailable"
    order_trace_kind: str = "unavailable"
    order_flow: str = "unavailable"
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_quantity", "requested_notional")
    @classmethod
    def _non_negative(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @field_validator("limit_price")
    @classmethod
    def _clamp_price(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    @property
    def requested_stake(self) -> float:
        return self.requested_notional

    @property
    def lifecycle_snapshot_model(self) -> "MarketExecutionOrderLifecycleSnapshot":
        return MarketExecutionOrderLifecycleSnapshot.from_order(self)

    @property
    def order_trace_audit_model(self) -> "MarketExecutionOrderTraceAudit | None":
        return MarketExecutionOrderTraceAudit.from_payload(self.metadata.get("order_trace_audit"))


def _coerce_datetime_value(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class MarketExecutionOrderLifecycleSnapshot(BaseModel):
    schema_version: str = "v1"
    venue_order_id: str | None = None
    venue_order_status: str = "unavailable"
    venue_order_source: str = "unavailable"
    venue_order_submission_state: str = "simulated"
    venue_order_ack_state: str = "not_acknowledged"
    venue_order_cancel_state: str = "not_cancelled"
    venue_order_execution_state: str = "simulated"
    venue_order_status_history: list[str] = Field(default_factory=list)
    venue_order_acknowledged_at: datetime | None = None
    venue_order_acknowledged_by: str | None = None
    venue_order_acknowledged_reason: str | None = None
    venue_order_cancel_reason: str | None = None
    venue_order_cancelled_at: datetime | None = None
    venue_order_cancelled_by: str | None = None
    venue_order_path: str = "unavailable"
    venue_order_ack_path: str = "unavailable"
    venue_order_cancel_path: str = "unavailable"
    venue_order_trace_kind: str = "unavailable"
    venue_order_flow: str = "unavailable"

    @classmethod
    def from_order(cls, order: MarketExecutionOrder) -> "MarketExecutionOrderLifecycleSnapshot":
        metadata = dict(order.metadata or {})
        return cls(
            venue_order_id=metadata.get("venue_order_id"),
            venue_order_status=order.status or metadata.get("venue_order_status") or "unavailable",
            venue_order_source=order.order_source or metadata.get("venue_order_source") or "unavailable",
            venue_order_submission_state=order.venue_order_submission_state or metadata.get("venue_order_submission_state") or "simulated",
            venue_order_ack_state=order.venue_order_ack_state or metadata.get("venue_order_ack_state") or "not_acknowledged",
            venue_order_cancel_state=order.venue_order_cancel_state or metadata.get("venue_order_cancel_state") or "not_cancelled",
            venue_order_execution_state=order.venue_order_execution_state or metadata.get("venue_order_execution_state") or "simulated",
            venue_order_status_history=list(order.status_history or metadata.get("venue_order_status_history") or []),
            venue_order_acknowledged_at=_coerce_datetime_value(metadata.get("venue_order_acknowledged_at")) or order.acknowledged_at,
            venue_order_acknowledged_by=metadata.get("venue_order_acknowledged_by") or order.acknowledged_by,
            venue_order_acknowledged_reason=metadata.get("venue_order_acknowledged_reason") or order.acknowledged_reason,
            venue_order_cancel_reason=metadata.get("venue_order_cancel_reason") or order.cancelled_reason,
            venue_order_cancelled_at=_coerce_datetime_value(metadata.get("venue_order_cancelled_at")) or order.cancelled_at,
            venue_order_cancelled_by=metadata.get("venue_order_cancelled_by") or order.cancelled_by,
            venue_order_path=order.order_path or metadata.get("venue_order_path") or "unavailable",
            venue_order_ack_path=_derived_venue_order_ack_path(metadata),
            venue_order_cancel_path=order.order_cancel_path or metadata.get("venue_order_cancel_path") or "unavailable",
            venue_order_trace_kind=order.order_trace_kind or metadata.get("venue_order_trace_kind") or "unavailable",
            venue_order_flow=order.order_flow or metadata.get("venue_order_flow") or "unavailable",
        )


class MarketExecutionOrderTraceAudit(BaseModel):
    schema_version: str = "v1"
    trace_source: str = "venue_order_lifecycle"
    venue_order_id: str | None = None
    venue_order_status: str | None = None
    venue_order_source: str | None = None
    venue_order_submission_state: str = "simulated"
    venue_order_ack_state: str = "not_acknowledged"
    venue_order_cancel_state: str = "not_cancelled"
    venue_order_execution_state: str = "simulated"
    venue_order_status_history: list[str] = Field(default_factory=list)
    venue_order_acknowledged_at: datetime | None = None
    venue_order_acknowledged_by: str | None = None
    venue_order_acknowledged_reason: str | None = None
    venue_order_cancel_reason: str | None = None
    venue_order_cancelled_at: datetime | None = None
    venue_order_cancelled_by: str | None = None
    venue_order_path: str | None = None
    venue_order_ack_path: str | None = None
    venue_order_cancel_path: str | None = None
    venue_order_configured: bool = False
    venue_order_trace_kind: str | None = None
    venue_order_flow: str | None = None
    live_execution_status: str = "blocked"
    live_preflight_passed: bool = False
    attempted_live: bool = False
    live_submission_performed: bool = False
    live_submission_phase: str = "dry_run"
    submission_error_type: str | None = None
    venue_live_submission_bound: bool = False
    transport_mode: str = "dry_run"
    runtime_live_claimed: bool = False
    runtime_honest_mode: str = "dry_run"
    place_auditable: bool = True
    cancel_auditable: bool = True
    ack_auditable: bool = False

    @classmethod
    def from_payload(cls, payload: Any) -> "MarketExecutionOrderTraceAudit | None":
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class MarketExecutionFill(BaseModel):
    schema_version: str = "v1"
    fill_id: str = Field(default_factory=lambda: f"mfill_{uuid4().hex[:12]}")
    order_id: str
    trade_id: str
    run_id: str
    market_id: str
    venue: VenueName
    position_side: TradeSide
    execution_side: TradeSide
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    fill_price: float = 0.0
    gross_notional: float = 0.0
    fee_paid: float = 0.0
    slippage_bps: float = 0.0
    level_index: int | None = None
    source: str = "paper_trade"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_quantity", "filled_quantity", "fill_price", "gross_notional", "fee_paid")
    @classmethod
    def _non_negative(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))


class MarketExecutionPosition(BaseModel):
    schema_version: str = "v1"
    position_id: str = Field(default_factory=lambda: f"mpos_{uuid4().hex[:12]}")
    order_id: str
    run_id: str
    market_id: str
    venue: VenueName
    side: TradeSide
    quantity: float = 0.0
    entry_price: float = 0.0
    mark_price: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    source: str = "ledger"
    audited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "entry_price")
    @classmethod
    def _normalize_non_negative(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @classmethod
    def from_ledger_position(
        cls,
        position: LedgerPosition,
        *,
        order_id: str,
        run_id: str,
        source: str,
    ) -> "MarketExecutionPosition":
        return cls(
            order_id=order_id,
            run_id=run_id,
            market_id=position.market_id,
            venue=position.venue,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.metadata.get("realized_pnl"),
            source=source,
            metadata=dict(position.metadata),
        )


class MarketExecutionRequest(BaseModel):
    schema_version: str = "v1"
    model_config = ConfigDict(extra="allow")

    run_id: str = ""
    market: MarketDescriptor | None = None
    snapshot: MarketSnapshot | None = None
    venue: VenueName = VenueName.polymarket
    market_id: str = ""
    position_side: TradeSide = TradeSide.yes
    execution_side: TradeSide = TradeSide.buy
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    stake: float = 0.0
    limit_price: float | None = None
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    trade_intent: TradeIntent | None = None
    paper_trade: PaperTradeSimulation | None = None
    ledger_before: CapitalLedgerSnapshot | None = None
    ledger_after: CapitalLedgerSnapshot | None = None
    execution_projection: ExecutionProjection | None = None
    resolution_guard: ResolutionGuardReport | None = None
    executable_edge: ExecutableEdge | None = None

    @field_validator("requested_quantity", "requested_notional", "stake")
    @classmethod
    def _non_negative(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @field_validator("limit_price")
    @classmethod
    def _clamp_price(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))


class MarketExecutionRecord(BaseModel):
    schema_version: str = "v1"
    model_config = ConfigDict(extra="allow")

    report_id: str = Field(default_factory=lambda: f"mexec_{uuid4().hex[:12]}")
    execution_id: str = Field(default_factory=lambda: f"mexec_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    mode: MarketExecutionMode = MarketExecutionMode.bounded_dry_run
    status: MarketExecutionStatus = MarketExecutionStatus.blocked
    dry_run: bool = True
    bounded_execution_supported: bool = True
    live_execution_supported: bool = False
    requested_stake: float = 0.0
    executed_stake: float = 0.0
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    order: MarketExecutionOrder
    fills: list[MarketExecutionFill] = Field(default_factory=list)
    positions: list[MarketExecutionPosition] = Field(default_factory=list)
    fill_count: int = 0
    position_count: int = 0
    position_before: MarketExecutionPosition | None = None
    position_after: MarketExecutionPosition | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    paper_trade: PaperTradeSimulation | None = None
    ledger_before: CapitalLedgerSnapshot | None = None
    ledger_after: CapitalLedgerSnapshot | None = None
    ledger_change: CapitalLedgerChange | None = None
    capability: dict[str, Any] = Field(default_factory=dict)
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    trade_intent_ref: str | None = None
    execution_projection_ref: str | None = None
    runtime_guard: dict[str, Any] = Field(default_factory=dict)
    action_time_guard: dict[str, Any] = Field(default_factory=dict)
    live_execution_status: str = "blocked"
    venue_submission_state: str = "simulated"
    venue_ack_state: str = "not_acknowledged"
    venue_cancel_state: str = "not_cancelled"
    venue_execution_state: str = "simulated"
    venue_order_ack_path: str = "unavailable"
    live_preflight_passed: bool = False
    attempted_live: bool = False
    live_submission_performed: bool = False
    live_submission_phase: str = "dry_run"
    venue_live_submission_bound: bool = False
    operator_bound: bool = False
    live_runtime_honest_mode: str = "dry_run"
    live_submission_failed: str | None = None
    live_acknowledged: bool = False
    live_cancel_observed: bool = False
    live_submission_receipt: dict[str, Any] = Field(default_factory=dict)
    venue_submission_receipt: dict[str, Any] = Field(default_factory=dict)
    venue_cancellation_receipt: dict[str, Any] = Field(default_factory=dict)
    live_transport_readiness: dict[str, Any] = Field(default_factory=dict)
    venue_live_configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    live_route_evidence: dict[str, Any] = Field(default_factory=dict)
    live_auth_compliance_evidence: dict[str, Any] = Field(default_factory=dict)
    selected_live_path_receipt: dict[str, Any] = Field(default_factory=dict)
    order_trace_artifacts: dict[str, Any] = Field(default_factory=dict)
    live_attempt_timeline: dict[str, Any] = Field(default_factory=dict)
    live_blocker_snapshot: dict[str, Any] = Field(default_factory=dict)
    selected_live_path_audit: dict[str, Any] = Field(default_factory=dict)
    live_lifecycle_snapshot: dict[str, Any] = Field(default_factory=dict)
    cancelled_reason: str | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def lifecycle_snapshot_model(self) -> MarketExecutionOrderLifecycleSnapshot:
        lifecycle_payload = self.metadata.get("venue_order_lifecycle")
        if isinstance(lifecycle_payload, dict):
            return MarketExecutionOrderLifecycleSnapshot.model_validate(lifecycle_payload)
        return self.order.lifecycle_snapshot_model

    @property
    def order_trace_audit_model(self) -> MarketExecutionOrderTraceAudit | None:
        payload = self.metadata.get("order_trace_audit") or self.order.metadata.get("order_trace_audit")
        return MarketExecutionOrderTraceAudit.from_payload(payload)

    @classmethod
    def from_paper_trade(
        cls,
        *,
        paper_trade: PaperTradeSimulation,
        order: MarketExecutionOrder,
        mode: MarketExecutionMode,
        capability: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
        ledger_before: CapitalLedgerSnapshot | None = None,
        ledger_after: CapitalLedgerSnapshot | None = None,
        ledger_change: CapitalLedgerChange | None = None,
        trade_intent_ref: str | None = None,
        execution_projection_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MarketExecutionRecord":
        fills = _fills_from_paper_trade(order.order_id, paper_trade)
        positions = _positions_from_ledger(order.order_id, order.run_id, order.market_id, ledger_after)
        if not positions:
            positions = [_position_from_paper_trade(order.order_id, order.run_id, paper_trade)]
        position_before = _position_from_ledger(order.order_id, order.run_id, order.market_id, ledger_before)
        position_after = positions[0] if positions else None
        status = _status_from_paper_trade(paper_trade)
        acknowledged_at = datetime.now(timezone.utc).replace(microsecond=0)
        lifecycle = _market_execution_order_lifecycle(
            order,
            final_status=paper_trade.status.value if paper_trade.status.value in {"filled", "partial", "rejected"} else "acknowledged",
            source="paper_trade_simulator",
            live_execution_supported=mode == MarketExecutionMode.bounded_live,
        )
        order.acknowledged_at = acknowledged_at
        order.acknowledged_by = "paper_trade_simulator"
        order.acknowledged_reason = "paper_trade_materialized"
        order.status = paper_trade.status.value if paper_trade.status.value in {"filled", "partial", "rejected"} else "acknowledged"
        _apply_order_lifecycle(order, lifecycle)
        order_trace_audit = _order_trace_audit_from_lifecycle(
            order.metadata,
            live_execution_status=paper_trade.status.value,
            final_status=order.status,
        )
        order.metadata["order_trace_audit"] = order_trace_audit
        submission_receipt = _venue_submission_receipt_from_lifecycle(
            order.metadata,
            transport_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            runtime_honest_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            attempted_live=False,
            live_submission_performed=False,
            live_submission_phase="simulated",
            submitted_payload=order.metadata.get("venue_live_submitted_payload"),
        )
        return cls(
            report_id=order.execution_id,
            execution_id=order.execution_id,
            run_id=order.run_id,
            market_id=order.market_id,
            venue=order.venue,
            mode=mode,
            status=status,
            dry_run=mode == MarketExecutionMode.bounded_dry_run,
            bounded_execution_supported=True,
            live_execution_supported=mode == MarketExecutionMode.bounded_live,
            requested_stake=order.requested_notional or paper_trade.stake,
            executed_stake=paper_trade.stake,
            requested_quantity=order.requested_quantity or paper_trade.requested_quantity,
            filled_quantity=paper_trade.filled_quantity,
            average_fill_price=paper_trade.average_fill_price,
            order=order,
            fills=fills,
            positions=positions,
            fill_count=len(fills),
            position_count=len(positions),
            position_before=position_before,
            position_after=position_after,
            blocked_reasons=[] if status != MarketExecutionStatus.blocked else [paper_trade.status.value],
            paper_trade=paper_trade,
            ledger_before=ledger_before,
            ledger_after=ledger_after,
            ledger_change=ledger_change,
            capability=dict(capability or {}),
            execution_plan=dict(execution_plan or {}),
            trade_intent_ref=trade_intent_ref,
            execution_projection_ref=execution_projection_ref,
            live_execution_status=paper_trade.status.value,
            venue_submission_state=str(order.metadata.get("venue_order_submission_state") or "simulated"),
            venue_ack_state=str(order.metadata.get("venue_order_ack_state") or "not_acknowledged"),
            venue_cancel_state=str(order.metadata.get("venue_order_cancel_state") or "not_cancelled"),
            venue_execution_state=str(order.metadata.get("venue_order_execution_state") or "simulated"),
            venue_submission_receipt=submission_receipt,
            venue_cancellation_receipt=_venue_cancellation_receipt_from_lifecycle(
                order.metadata,
                transport_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
                runtime_honest_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
                attempted_live=False,
                live_submission_performed=False,
                cancellation_performed=order.metadata.get("venue_order_cancel_state") == "venue_cancelled",
                cancellation_phase="simulated",
                cancelled_payload=order.metadata.get("venue_live_cancelled_payload"),
            ),
            metadata={
                **dict(metadata or {}),
                "order_trace_audit": order_trace_audit,
                "venue_submission_receipt": submission_receipt,
            },
        )

    @classmethod
    def from_cancelled(
        cls,
        *,
        order: MarketExecutionOrder,
        mode: MarketExecutionMode,
        reason: str,
        cancelled_by: str = "live_execution_kill_switch",
        capability: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
        ledger_before: CapitalLedgerSnapshot | None = None,
        ledger_after: CapitalLedgerSnapshot | None = None,
        ledger_change: CapitalLedgerChange | None = None,
        trade_intent_ref: str | None = None,
        execution_projection_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MarketExecutionRecord":
        cancelled_at = datetime.now(timezone.utc).replace(microsecond=0)
        lifecycle = _market_execution_order_lifecycle(
            order,
            final_status=MarketExecutionStatus.cancelled.value,
            source=cancelled_by,
            live_execution_supported=mode == MarketExecutionMode.bounded_live,
            cancelled_reason=reason,
        )
        order.cancelled_at = cancelled_at
        order.cancelled_reason = reason
        order.cancelled_by = cancelled_by
        order.acknowledged_at = cancelled_at
        order.acknowledged_by = cancelled_by
        order.acknowledged_reason = reason
        order.status = MarketExecutionStatus.cancelled.value
        _apply_order_lifecycle(order, lifecycle)
        order_trace_audit = _order_trace_audit_from_lifecycle(
            order.metadata,
            live_execution_status=MarketExecutionStatus.cancelled.value,
            final_status=order.status,
        )
        order.metadata["order_trace_audit"] = order_trace_audit
        submission_receipt = _venue_submission_receipt_from_lifecycle(
            order.metadata,
            transport_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            runtime_honest_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            attempted_live=False,
            live_submission_performed=False,
            live_submission_phase="simulated",
            submitted_payload=order.metadata.get("venue_live_submitted_payload"),
        )
        cancellation_receipt = _venue_cancellation_receipt_from_lifecycle(
            order.metadata,
            transport_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            runtime_honest_mode="live" if order.metadata.get("venue_order_trace_kind") == "external_live" else "dry_run",
            attempted_live=False,
            live_submission_performed=False,
            cancellation_performed=True,
            cancellation_phase="simulated",
            cancelled_payload=order.metadata.get("venue_live_cancelled_payload"),
        )
        return cls(
            report_id=order.execution_id,
            execution_id=order.execution_id,
            run_id=order.run_id,
            market_id=order.market_id,
            venue=order.venue,
            mode=mode,
            status=MarketExecutionStatus.cancelled,
            dry_run=mode == MarketExecutionMode.bounded_dry_run,
            bounded_execution_supported=True,
            live_execution_supported=mode == MarketExecutionMode.bounded_live,
            requested_stake=order.requested_notional,
            executed_stake=0.0,
            requested_quantity=order.requested_quantity,
            filled_quantity=0.0,
            average_fill_price=None,
            order=order,
            fills=[],
            positions=[],
            fill_count=0,
            position_count=0,
            position_before=_position_from_ledger(order.order_id, order.run_id, order.market_id, ledger_before),
            position_after=_position_from_ledger(order.order_id, order.run_id, order.market_id, ledger_after),
            blocked_reasons=[reason],
            paper_trade=None,
            ledger_before=ledger_before,
            ledger_after=ledger_after,
            ledger_change=ledger_change,
            capability=dict(capability or {}),
            execution_plan=dict(execution_plan or {}),
            trade_intent_ref=trade_intent_ref,
            execution_projection_ref=execution_projection_ref,
            live_execution_status=MarketExecutionStatus.cancelled.value,
            venue_submission_state=str(order.metadata.get("venue_order_submission_state") or "simulated"),
            venue_ack_state=str(order.metadata.get("venue_order_ack_state") or "not_acknowledged"),
            venue_cancel_state=str(order.metadata.get("venue_order_cancel_state") or "not_cancelled"),
            venue_execution_state=str(order.metadata.get("venue_order_execution_state") or "simulated"),
            venue_submission_receipt=submission_receipt,
            venue_cancellation_receipt=cancellation_receipt,
            cancelled_reason=reason,
            cancelled_by=cancelled_by,
            cancelled_at=cancelled_at,
            metadata={
                **dict(metadata or {}),
                "cancelled": True,
                "cancelled_reason": reason,
                "cancelled_by": cancelled_by,
                "order_trace_audit": order_trace_audit,
                "venue_submission_receipt": submission_receipt,
                "venue_cancellation_receipt": cancellation_receipt,
            },
        )


def _market_execution_order_lifecycle(
    order: MarketExecutionOrder,
    *,
    final_status: str,
    source: str,
    live_execution_supported: bool,
    cancelled_reason: str | None = None,
) -> dict[str, Any]:
    metadata = dict(order.metadata or {})
    raw_history = metadata.get("venue_order_status_history") or metadata.get("status_history") or metadata.get("order_status_history")
    history = _normalize_status_history(raw_history) if raw_history else []
    if final_status == MarketExecutionStatus.cancelled.value:
        history = ["submitted", "acknowledged", "cancelled"]
    elif not history:
        if final_status in {"filled", "partial", "rejected"}:
            history = ["submitted", "acknowledged", final_status]
        elif final_status == "acknowledged":
            history = ["submitted", "acknowledged"]
        elif final_status == "submitted":
            history = ["submitted"]
        else:
            history = [final_status or "unavailable"]
    configured = bool(
        metadata.get("venue_order_configured")
        or metadata.get("venue_order_id")
        or metadata.get("venue_order_status_history")
        or metadata.get("venue_order_flow")
        or metadata.get("venue_order_trace_kind") not in {None, "unavailable"}
    )
    trace_kind = metadata.get("venue_order_trace_kind") or ("external_live" if configured else "local_surrogate")
    order_source = source if final_status == MarketExecutionStatus.cancelled.value else (metadata.get("venue_order_source") or source)
    order_path = metadata.get("venue_order_path") or (
        "external_live_api" if configured and live_execution_supported else "local_surrogate_order_path"
    )
    order_cancel_path = metadata.get("venue_order_cancel_path") or (
        "external_live_cancel_api" if configured and live_execution_supported else "local_surrogate_cancel_path"
    )
    flow = "->".join(history) if final_status == MarketExecutionStatus.cancelled.value else (metadata.get("venue_order_flow") or "->".join(history))
    return {
        "venue_order_status_history": list(history),
        "venue_order_source": order_source,
        "venue_order_submission_state": metadata.get("venue_order_submission_state") or ("venue_submitted" if final_status != "simulated" else "simulated"),
        "venue_order_ack_state": metadata.get("venue_order_ack_state") or (
            "venue_acknowledged"
            if any(
                [
                    metadata.get("venue_order_acknowledged_at"),
                    metadata.get("venue_order_acknowledged_by"),
                    metadata.get("venue_order_acknowledged_reason"),
                    "acknowledged" in history,
                ]
            )
            else "not_acknowledged"
        ),
        "venue_order_cancel_state": metadata.get("venue_order_cancel_state") or (
            "venue_cancelled"
            if any(
                [
                    cancelled_reason,
                    metadata.get("venue_order_cancelled_at"),
                    metadata.get("venue_order_cancelled_by"),
                    "cancelled" in history,
                ]
            )
            else "not_cancelled"
        ),
        "venue_order_execution_state": metadata.get("venue_order_execution_state")
        or (
            "venue_cancelled"
            if any(
                [
                    cancelled_reason,
                    metadata.get("venue_order_cancelled_at"),
                    metadata.get("venue_order_cancelled_by"),
                    "cancelled" in history,
                ]
            )
            else "venue_acknowledged"
            if any(
                [
                    metadata.get("venue_order_acknowledged_at"),
                    metadata.get("venue_order_acknowledged_by"),
                    metadata.get("venue_order_acknowledged_reason"),
                    "acknowledged" in history,
                ]
            )
            else "venue_submitted"
            if final_status != "simulated"
            else "simulated"
        ),
        "venue_order_path": order_path,
        "venue_order_cancel_path": order_cancel_path,
        "venue_order_trace_kind": trace_kind,
        "venue_order_flow": flow,
        "venue_order_cancel_reason": cancelled_reason or metadata.get("venue_order_cancel_reason"),
    }


def _apply_order_lifecycle(order: MarketExecutionOrder, lifecycle: dict[str, Any]) -> None:
    order.status_history = list(lifecycle.get("venue_order_status_history") or [])
    order.order_source = str(lifecycle.get("venue_order_source") or "unavailable")
    order.venue_order_submission_state = str(lifecycle.get("venue_order_submission_state") or "simulated")
    order.venue_order_ack_state = str(lifecycle.get("venue_order_ack_state") or "not_acknowledged")
    order.venue_order_cancel_state = str(lifecycle.get("venue_order_cancel_state") or "not_cancelled")
    order.venue_order_execution_state = str(lifecycle.get("venue_order_execution_state") or "simulated")
    order.order_path = str(lifecycle.get("venue_order_path") or "unavailable")
    order.order_cancel_path = str(lifecycle.get("venue_order_cancel_path") or "unavailable")
    order.order_trace_kind = str(lifecycle.get("venue_order_trace_kind") or "unavailable")
    order.order_flow = str(lifecycle.get("venue_order_flow") or "unavailable")
    order.metadata = {
        **dict(order.metadata or {}),
        **{k: v for k, v in lifecycle.items() if v is not None},
    }


def _derived_venue_order_ack_path(lifecycle: dict[str, Any] | None) -> str:
    if not isinstance(lifecycle, dict):
        return "unavailable"
    explicit = lifecycle.get("venue_order_ack_path")
    if explicit:
        return str(explicit)
    history = set(_normalize_status_history(lifecycle.get("venue_order_status_history")))
    acknowledged = bool(
        lifecycle.get("venue_order_acknowledged_at")
        or lifecycle.get("venue_order_acknowledged_by")
        or lifecycle.get("venue_order_acknowledged_reason")
        or "acknowledged" in history
    )
    venue_order_path = lifecycle.get("venue_order_path")
    if acknowledged and venue_order_path:
        return str(venue_order_path)
    return "unavailable"


def _merge_order_trace_audit_payload(
    base_payload: dict[str, Any] | None,
    computed_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if base_payload is None:
        return computed_payload
    if computed_payload is None:
        return dict(base_payload)
    merged = dict(base_payload)
    merged.update({key: value for key, value in computed_payload.items() if value is not None})
    return merged


def _order_trace_audit_from_lifecycle(
    lifecycle: dict[str, Any] | None,
    *,
    live_execution_status: str,
    final_status: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(lifecycle, dict):
        return None
    transport_mode = "live" if lifecycle.get("venue_order_trace_kind") == "external_live" else "dry_run"
    venue_order_ack_path = _derived_venue_order_ack_path(lifecycle)
    place_auditable = bool(lifecycle.get("venue_order_path") and lifecycle.get("venue_order_path") != "unavailable")
    cancel_auditable = bool(lifecycle.get("venue_order_cancel_path") and lifecycle.get("venue_order_cancel_path") != "unavailable")
    ack_auditable = bool(venue_order_ack_path and venue_order_ack_path != "unavailable")
    venue_order_status = final_status or lifecycle.get("venue_order_status")
    return {
        "schema_version": "v1",
        "trace_source": "venue_order_lifecycle",
        "venue_order_id": lifecycle.get("venue_order_id"),
        "venue_order_status": venue_order_status,
        "venue_order_source": lifecycle.get("venue_order_source"),
        "venue_order_submission_state": lifecycle.get("venue_order_submission_state"),
        "venue_order_ack_state": lifecycle.get("venue_order_ack_state"),
        "venue_order_cancel_state": lifecycle.get("venue_order_cancel_state"),
        "venue_order_execution_state": lifecycle.get("venue_order_execution_state"),
        "venue_order_status_history": list(lifecycle.get("venue_order_status_history") or []),
        "venue_order_acknowledged_at": lifecycle.get("venue_order_acknowledged_at"),
        "venue_order_acknowledged_by": lifecycle.get("venue_order_acknowledged_by"),
        "venue_order_acknowledged_reason": lifecycle.get("venue_order_acknowledged_reason"),
        "venue_order_cancel_reason": lifecycle.get("venue_order_cancel_reason"),
        "venue_order_cancelled_at": lifecycle.get("venue_order_cancelled_at"),
        "venue_order_cancelled_by": lifecycle.get("venue_order_cancelled_by"),
        "venue_order_path": lifecycle.get("venue_order_path"),
        "venue_order_ack_path": venue_order_ack_path,
        "venue_order_cancel_path": lifecycle.get("venue_order_cancel_path"),
        "venue_order_configured": bool(lifecycle.get("venue_order_configured", False)),
        "venue_order_trace_kind": lifecycle.get("venue_order_trace_kind"),
        "venue_order_flow": lifecycle.get("venue_order_flow"),
        "venue_submission_state": lifecycle.get("venue_order_submission_state", "simulated"),
        "venue_ack_state": lifecycle.get("venue_order_ack_state", "not_acknowledged"),
        "venue_cancel_state": lifecycle.get("venue_order_cancel_state", "not_cancelled"),
        "venue_execution_state": lifecycle.get("venue_order_execution_state", "simulated"),
        "live_execution_status": live_execution_status,
        "live_preflight_passed": bool(lifecycle.get("live_preflight_passed")),
        "attempted_live": bool(lifecycle.get("attempted_live") or lifecycle.get("venue_live_submission_attempted")),
        "live_submission_performed": bool(
            lifecycle.get("live_submission_performed") or lifecycle.get("venue_live_submission_performed")
        ),
        "live_submission_phase": str(
            lifecycle.get("live_submission_phase")
            or (
                "performed_live"
                if bool(lifecycle.get("live_submission_performed") or lifecycle.get("venue_live_submission_performed"))
                else "attempted_live"
                if bool(lifecycle.get("attempted_live") or lifecycle.get("venue_live_submission_attempted"))
                else "dry_run"
            )
        ),
        "submission_error_type": lifecycle.get("live_submission_failed") or lifecycle.get("submission_error_type"),
        "venue_live_submission_bound": bool(
            lifecycle.get("venue_live_submission_bound") or lifecycle.get("live_transport_bound")
        ),
        "transport_mode": transport_mode,
        "runtime_live_claimed": transport_mode == "live",
        "runtime_honest_mode": transport_mode,
        "place_auditable": place_auditable,
        "cancel_auditable": cancel_auditable,
        "ack_auditable": ack_auditable,
    }


def _venue_order_state_fields(lifecycle: Mapping[str, Any] | None) -> dict[str, str]:
    payload = dict(lifecycle or {})
    submission_state = str(payload.get("venue_order_submission_state") or "simulated")
    ack_state = str(payload.get("venue_order_ack_state") or "not_acknowledged")
    cancel_state = str(payload.get("venue_order_cancel_state") or "not_cancelled")
    execution_state = str(payload.get("venue_order_execution_state") or "simulated")
    return {
        "venue_order_submission_state": submission_state,
        "venue_order_ack_state": ack_state,
        "venue_order_cancel_state": cancel_state,
        "venue_order_execution_state": execution_state,
    }


def _venue_submission_receipt_from_lifecycle(
    lifecycle: Mapping[str, Any] | None,
    *,
    transport_mode: str,
    runtime_honest_mode: str,
    attempted_live: bool,
    live_submission_performed: bool,
    live_submission_phase: str,
    submission_error_type: str | None = None,
    submitted_payload: Any | None = None,
    blocked_reasons: Iterable[str] | None = None,
) -> dict[str, Any]:
    payload = dict(lifecycle or {})
    history = list(payload.get("venue_order_status_history") or [])
    submitted_payload_hash = None
    if submitted_payload is not None:
        try:
            submitted_payload_hash = _stable_content_hash(submitted_payload)[:12]
        except Exception:  # pragma: no cover - defensive hashing
            submitted_payload_hash = None
    receipt = {
        "schema_version": "v1",
        "receipt_source": "venue_order_submission",
        "transport_mode": transport_mode,
        "runtime_honest_mode": runtime_honest_mode,
        "attempted_live": bool(attempted_live),
        "live_submission_performed": bool(live_submission_performed),
        "live_submission_phase": live_submission_phase,
        "submission_error_type": submission_error_type,
        "venue_live_submission_bound": bool(payload.get("venue_live_submission_bound") or payload.get("live_transport_bound")),
        "venue_order_id": payload.get("venue_order_id"),
        "venue_order_status": payload.get("venue_order_status"),
        "venue_order_source": payload.get("venue_order_source"),
        "venue_order_submission_state": payload.get("venue_order_submission_state", "simulated"),
        "venue_order_ack_state": payload.get("venue_order_ack_state", "not_acknowledged"),
        "venue_order_cancel_state": payload.get("venue_order_cancel_state", "not_cancelled"),
        "venue_order_execution_state": payload.get("venue_order_execution_state", "simulated"),
        "venue_order_trace_kind": payload.get("venue_order_trace_kind"),
        "venue_order_path": payload.get("venue_order_path"),
        "venue_order_ack_path": payload.get("venue_order_ack_path") or payload.get("venue_order_path"),
        "venue_order_cancel_path": payload.get("venue_order_cancel_path"),
        "venue_order_status_history": history,
        "submitted_payload_present": submitted_payload is not None,
        "submitted_payload_hash": submitted_payload_hash,
        "acknowledged": bool(
            payload.get("venue_order_acknowledged_at")
            or payload.get("venue_order_acknowledged_by")
            or payload.get("venue_order_acknowledged_reason")
            or "acknowledged" in history
        ),
        "cancel_observed": bool(
            payload.get("venue_order_cancelled_at")
            or payload.get("venue_order_cancelled_by")
            or payload.get("venue_order_cancel_reason")
            or "cancelled" in history
        ),
        "blocked_reasons": list(blocked_reasons or []),
    }
    return receipt


def _venue_cancellation_receipt_from_lifecycle(
    lifecycle: Mapping[str, Any] | None,
    *,
    transport_mode: str,
    runtime_honest_mode: str,
    attempted_live: bool,
    live_submission_performed: bool,
    cancellation_performed: bool,
    cancellation_phase: str,
    cancellation_error_type: str | None = None,
    cancelled_payload: Any | None = None,
    blocked_reasons: Iterable[str] | None = None,
) -> dict[str, Any]:
    payload = dict(lifecycle or {})
    history = list(payload.get("venue_order_status_history") or [])
    cancelled_payload_hash = None
    if cancelled_payload is not None:
        try:
            cancelled_payload_hash = _stable_content_hash(cancelled_payload)[:12]
        except Exception:  # pragma: no cover - defensive hashing
            cancelled_payload_hash = None
    receipt = {
        "schema_version": "v1",
        "receipt_source": "venue_order_cancellation",
        "transport_mode": transport_mode,
        "runtime_honest_mode": runtime_honest_mode,
        "attempted_live": bool(attempted_live),
        "live_submission_performed": bool(live_submission_performed),
        "cancellation_performed": bool(cancellation_performed),
        "cancellation_phase": cancellation_phase,
        "cancellation_error_type": cancellation_error_type,
        "venue_live_cancellation_bound": bool(payload.get("venue_live_cancellation_bound") or payload.get("live_transport_bound")),
        "venue_order_id": payload.get("venue_order_id"),
        "venue_order_status": payload.get("venue_order_status"),
        "venue_order_source": payload.get("venue_order_source"),
        "venue_order_submission_state": payload.get("venue_order_submission_state", "simulated"),
        "venue_order_ack_state": payload.get("venue_order_ack_state", "not_acknowledged"),
        "venue_order_cancel_state": payload.get("venue_order_cancel_state", "not_cancelled"),
        "venue_order_execution_state": payload.get("venue_order_execution_state", "simulated"),
        "venue_order_trace_kind": payload.get("venue_order_trace_kind"),
        "venue_order_path": payload.get("venue_order_path"),
        "venue_order_ack_path": payload.get("venue_order_ack_path") or payload.get("venue_order_path"),
        "venue_order_cancel_path": payload.get("venue_order_cancel_path"),
        "venue_order_status_history": history,
        "cancelled_payload_present": cancelled_payload is not None,
        "cancelled_payload_hash": cancelled_payload_hash,
        "acknowledged": bool(
            payload.get("venue_order_acknowledged_at")
            or payload.get("venue_order_acknowledged_by")
            or payload.get("venue_order_acknowledged_reason")
            or "acknowledged" in history
        ),
        "cancel_observed": bool(
            payload.get("venue_order_cancelled_at")
            or payload.get("venue_order_cancelled_by")
            or payload.get("venue_order_cancel_reason")
            or "cancelled" in history
        ),
        "blocked_reasons": list(blocked_reasons or []),
    }
    return receipt


def _normalize_status_history(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split("->") if "->" in value else value.split(",")
    else:
        items = list(value)
    history: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            history.append(text)
    return history


def _apply_live_execution_status(report: MarketExecutionRecord, live_status: str) -> None:
    report.live_execution_status = live_status
    report.metadata = {
        **dict(report.metadata or {}),
        "live_execution_status": live_status,
    }
    report.order.metadata = {
        **dict(report.order.metadata or {}),
        "live_execution_status": live_status,
    }


def _apply_live_execution_audit(report: MarketExecutionRecord, audit_payload: dict[str, Any] | None) -> None:
    if not isinstance(audit_payload, dict):
        return
    venue_order_ack_path = str(audit_payload.get("venue_order_ack_path") or "unavailable")
    live_preflight_passed = bool(audit_payload.get("live_preflight_passed"))
    attempted_live = bool(audit_payload.get("attempted_live"))
    live_submission_performed = bool(audit_payload.get("live_submission_performed"))
    live_submission_phase = str(audit_payload.get("live_submission_phase") or "dry_run")
    venue_live_submission_bound = bool(audit_payload.get("venue_live_submission_bound"))
    operator_bound = bool(audit_payload.get("operator_bound") or venue_live_submission_bound)
    live_runtime_honest_mode = str(audit_payload.get("runtime_honest_mode") or "dry_run")
    live_submission_failed = (
        audit_payload.get("submission_error_type")
        or report.metadata.get("venue_live_submission_failed")
        or report.metadata.get("live_submission_failed")
        or None
    )
    live_acknowledged = bool(audit_payload.get("ack_auditable"))
    live_cancel_observed = bool(
        audit_payload.get("venue_order_cancelled_at")
        or audit_payload.get("venue_order_cancelled_by")
        or audit_payload.get("venue_order_cancel_reason")
        or "cancelled" in list(audit_payload.get("venue_order_status_history") or [])
    )
    venue_state_fields = _venue_order_state_fields(audit_payload)
    live_submission_receipt = dict(report.metadata.get("live_submission_receipt") or {})
    if not live_submission_receipt:
        live_submission_receipt = {
            **_venue_submission_receipt_from_lifecycle(
                audit_payload,
                transport_mode=audit_payload.get("transport_mode", "dry_run"),
                runtime_honest_mode=live_runtime_honest_mode,
                attempted_live=attempted_live,
                live_submission_performed=live_submission_performed,
                live_submission_phase=live_submission_phase,
                submission_error_type=live_submission_failed,
                submitted_payload=report.metadata.get("venue_live_submitted_payload"),
                blocked_reasons=report.metadata.get("live_blocker_snapshot", {}).get("transport_failures", []) if isinstance(report.metadata.get("live_blocker_snapshot"), dict) else None,
            ),
            "receipt_source": "order_trace_audit",
        }
    venue_submission_receipt = dict(report.metadata.get("venue_submission_receipt") or {})
    if not venue_submission_receipt:
        venue_submission_receipt = _venue_submission_receipt_from_lifecycle(
            audit_payload,
            transport_mode=audit_payload.get("transport_mode", "dry_run"),
            runtime_honest_mode=live_runtime_honest_mode,
            attempted_live=attempted_live,
            live_submission_performed=live_submission_performed,
            live_submission_phase=live_submission_phase,
            submission_error_type=live_submission_failed,
            submitted_payload=report.metadata.get("venue_live_submitted_payload"),
            blocked_reasons=report.metadata.get("live_blocker_snapshot", {}).get("transport_failures", []) if isinstance(report.metadata.get("live_blocker_snapshot"), dict) else None,
        )
    venue_cancellation_receipt = dict(report.metadata.get("venue_cancellation_receipt") or {})
    if not venue_cancellation_receipt:
        venue_cancellation_receipt = _venue_cancellation_receipt_from_lifecycle(
            audit_payload,
            transport_mode=audit_payload.get("transport_mode", "dry_run"),
            runtime_honest_mode=live_runtime_honest_mode,
            attempted_live=attempted_live,
            live_submission_performed=live_submission_performed,
            cancellation_performed=live_cancel_observed,
            cancellation_phase=live_submission_phase if live_cancel_observed else "dry_run",
            cancellation_error_type=live_submission_failed,
            cancelled_payload=report.metadata.get("venue_live_cancelled_payload"),
            blocked_reasons=report.metadata.get("live_blocker_snapshot", {}).get("transport_failures", []) if isinstance(report.metadata.get("live_blocker_snapshot"), dict) else None,
        )
    live_transport_readiness = dict(report.metadata.get("live_transport_readiness") or {})
    if not live_transport_readiness:
        live_transport_readiness = {
            "schema_version": "v1",
            "adapter_name": report.execution_plan.get("adapter_name"),
            "backend_mode": report.execution_plan.get("backend_mode"),
            "route_supported": bool(report.execution_plan.get("route_supported", True)),
            "runtime_ready": bool(report.metadata.get("live_route_allowed", False)),
            "ready_for_live_execution": bool(report.metadata.get("live_route_allowed", False)),
            "live_route_allowed": bool(report.metadata.get("live_route_allowed", False)),
            "live_preflight_passed": live_preflight_passed,
            "transport_bound": venue_live_submission_bound,
            "operator_bound": operator_bound,
            "transport_callable": bool(report.metadata.get("live_transport_callable")),
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "live_submission_phase": live_submission_phase,
            "transport_mode": audit_payload.get("transport_mode", "dry_run"),
            "runtime_honest_mode": live_runtime_honest_mode,
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
            "selected_trace_kind": audit_payload.get("venue_order_trace_kind"),
            "selected_order_path": audit_payload.get("venue_order_path"),
            "selected_ack_path": venue_order_ack_path,
            "selected_cancel_path": audit_payload.get("venue_order_cancel_path"),
        }
    venue_live_configuration_snapshot = dict(report.metadata.get("venue_live_configuration_snapshot") or {})
    if not venue_live_configuration_snapshot:
        plan_metadata = dict(report.execution_plan.get("metadata") or {})
        venue_live_configuration_snapshot = {
            "schema_version": "v1",
            "venue": report.venue.value,
            "adapter_name": report.execution_plan.get("adapter_name"),
            "backend_mode": report.execution_plan.get("backend_mode") or plan_metadata.get("selected_backend_mode"),
            "execution_mode": report.execution_plan.get("execution_mode"),
            "live_execution_supported": bool(report.execution_plan.get("live_execution_supported")),
            "bounded_execution_supported": bool(report.execution_plan.get("bounded_execution_supported")),
            "market_execution_supported": bool(report.execution_plan.get("market_execution_supported")),
            "venue_order_configured": bool(audit_payload.get("venue_order_configured")),
            "venue_order_path": audit_payload.get("venue_order_path"),
            "venue_order_cancel_path": audit_payload.get("venue_order_cancel_path"),
            "auth_configured": bool(plan_metadata.get("auth_configured")),
            "auth_scheme": plan_metadata.get("auth_scheme"),
            "runtime_ready": bool(plan_metadata.get("runtime_ready", False)),
            "ready_for_live_execution": bool(plan_metadata.get("ready_for_live_execution", False)),
            "mock_transport": bool(plan_metadata.get("mock_transport", False)),
            "missing_requirements": list(plan_metadata.get("missing_requirements") or []),
            "readiness_notes": list(plan_metadata.get("readiness_notes") or []),
            "credential_evidence": dict(plan_metadata.get("credential_evidence") or {}),
            "configuration_evidence": dict(plan_metadata.get("configuration_evidence") or {}),
            "readiness_evidence": dict(plan_metadata.get("readiness_evidence") or {}),
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
        }
    live_auth_compliance_evidence = dict(report.metadata.get("live_auth_compliance_evidence") or {})
    if not live_auth_compliance_evidence:
        live_auth_compliance_evidence = {
            "schema_version": "v1",
            "principal": report.metadata.get("auth_principal"),
            "scopes": list(report.metadata.get("auth_scopes") or []),
            "auth_required": bool(report.auth_required),
            "auth_passed": bool(report.auth_passed),
            "compliance_required": bool(report.compliance_required),
            "compliance_passed": bool(report.compliance_passed),
            "jurisdiction_required": bool(report.jurisdiction_required),
            "jurisdiction_passed": bool(report.jurisdiction_passed),
            "account_type_required": bool(report.account_type_required),
            "account_type_passed": bool(report.account_type_passed),
            "automation_required": bool(report.automation_required),
            "automation_passed": bool(report.automation_passed),
            "rate_limit_required": bool(report.rate_limit_required),
            "rate_limit_passed": bool(report.rate_limit_passed),
            "tos_required": bool(report.tos_required),
            "tos_passed": bool(report.tos_passed),
            "venue_allowed": bool(report.venue_allowed),
            "live_allowed": bool(report.live_allowed),
            "blocked_reason": report.blocked_reason,
            "no_trade_reasons": list(report.no_trade_reasons),
            "execution_reasons": list(report.execution_reasons),
        }
    live_route_evidence = dict(report.metadata.get("live_route_evidence") or {})
    if not live_route_evidence:
        live_route_evidence = {
            "schema_version": "v1",
            "requested_mode": report.metadata.get("requested_mode"),
            "projected_mode": report.metadata.get("projected_mode"),
            "projection_verdict": report.metadata.get("projection_verdict"),
            "effective_mode": report.mode.value,
            "dry_run": bool(report.dry_run),
            "live_preflight_passed": live_preflight_passed,
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "live_submission_phase": live_submission_phase,
            "live_submission_failed": live_submission_failed,
            "transport_mode": audit_payload.get("transport_mode", "dry_run"),
            "runtime_honest_mode": live_runtime_honest_mode,
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
            "selected_order_source": audit_payload.get("venue_order_source"),
            "selected_trace_kind": audit_payload.get("venue_order_trace_kind"),
            "selected_order_flow": audit_payload.get("venue_order_flow"),
            "selected_order_path": audit_payload.get("venue_order_path"),
            "selected_ack_path": venue_order_ack_path,
            "selected_cancel_path": audit_payload.get("venue_order_cancel_path"),
        }
    selected_live_path_receipt = dict(report.metadata.get("selected_live_path_receipt") or {})
    if not selected_live_path_receipt:
        selected_live_path_receipt = {
            "schema_version": "v1",
            "receipt_source": "selected_live_path",
            "venue": report.venue.value,
            "adapter_name": report.execution_plan.get("adapter_name"),
            "backend_mode": report.execution_plan.get("backend_mode"),
            "selected_transport_mode": audit_payload.get("transport_mode", "dry_run"),
            "runtime_honest_mode": live_runtime_honest_mode,
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
            "venue_live_submission_bound": venue_live_submission_bound,
            "selected_order_source": audit_payload.get("venue_order_source"),
            "selected_trace_kind": audit_payload.get("venue_order_trace_kind"),
            "selected_order_path": audit_payload.get("venue_order_path"),
            "selected_ack_path": venue_order_ack_path,
            "selected_cancel_path": audit_payload.get("venue_order_cancel_path"),
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "live_submission_phase": live_submission_phase,
            "submission_error_type": live_submission_failed,
        }
    order_trace_artifacts = dict(report.metadata.get("order_trace_artifacts") or {})
    if not order_trace_artifacts:
        order_trace_artifacts = {
            "schema_version": "v1",
            "artifact_source": "market_execution",
            "venue_order_lifecycle": dict(
                report.metadata.get("venue_order_lifecycle") or report.order.metadata.get("venue_order_lifecycle") or {}
            ),
            "order_trace_audit": dict(audit_payload),
            "live_submission_receipt": dict(live_submission_receipt),
            "venue_submission_receipt": dict(venue_submission_receipt),
            "venue_cancellation_receipt": dict(venue_cancellation_receipt),
            "selected_live_path_receipt": dict(selected_live_path_receipt),
        }
    live_attempt_timeline = dict(report.metadata.get("live_attempt_timeline") or {})
    if not live_attempt_timeline:
        live_attempt_timeline = {
            "schema_version": "v1",
            "timeline_source": "market_execution_materialize",
            "created_at": report.created_at.isoformat(),
            "phase_initial": report.metadata.get("live_submission_phase_initial") or report.metadata.get("live_submission_phase"),
            "phase_current": live_submission_phase,
            "phase_history": list(report.metadata.get("live_submission_phase_history") or []),
            "last_transition_at": report.metadata.get("live_submission_last_transition_at"),
            "attempted_at": report.metadata.get("live_submission_attempted_at"),
            "performed_at": report.metadata.get("live_submission_performed_at"),
            "failed_at": report.metadata.get("live_submission_failed_at"),
            "acknowledged_at": audit_payload.get("venue_order_acknowledged_at"),
            "cancelled_at": audit_payload.get("venue_order_cancelled_at"),
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "acknowledged": live_acknowledged,
            "cancel_observed": live_cancel_observed,
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
        }
    live_blocker_snapshot = dict(report.metadata.get("live_blocker_snapshot") or {})
    selected_live_path_audit = dict(report.metadata.get("selected_live_path_audit") or {})
    if not selected_live_path_audit:
        selected_live_path_audit = {
            "schema_version": "v1",
            "audit_source": "selected_live_path",
            "selected_live_path_receipt": dict(selected_live_path_receipt),
            "live_transport_readiness": dict(live_transport_readiness),
            "live_route_evidence": dict(live_route_evidence),
            "live_auth_compliance_evidence": dict(live_auth_compliance_evidence),
        }
    live_lifecycle_snapshot = dict(report.metadata.get("live_lifecycle_snapshot") or {})
    if not live_lifecycle_snapshot:
        live_lifecycle_snapshot = {
            "schema_version": "v1",
            "snapshot_source": "market_execution_lifecycle",
            **dict(report.metadata.get("venue_order_lifecycle") or report.order.metadata.get("venue_order_lifecycle") or {}),
            "transport_mode": audit_payload.get("transport_mode", "dry_run"),
            "runtime_honest_mode": live_runtime_honest_mode,
            "submission_error_type": live_submission_failed,
            "acknowledged": live_acknowledged,
            "cancel_observed": live_cancel_observed,
            "venue_submission_state": venue_state_fields["venue_order_submission_state"],
            "venue_ack_state": venue_state_fields["venue_order_ack_state"],
            "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
            "venue_execution_state": venue_state_fields["venue_order_execution_state"],
        }
    report.venue_order_ack_path = venue_order_ack_path
    report.live_preflight_passed = live_preflight_passed
    report.attempted_live = attempted_live
    report.live_submission_performed = live_submission_performed
    report.live_submission_phase = live_submission_phase
    report.order.metadata["live_submission_failed"] = live_submission_failed
    report.venue_live_submission_bound = venue_live_submission_bound
    report.operator_bound = operator_bound
    report.live_runtime_honest_mode = live_runtime_honest_mode
    report.live_submission_failed = live_submission_failed
    report.live_acknowledged = live_acknowledged
    report.live_cancel_observed = live_cancel_observed
    report.live_submission_receipt = dict(live_submission_receipt)
    report.venue_submission_receipt = dict(venue_submission_receipt)
    report.venue_cancellation_receipt = dict(venue_cancellation_receipt)
    report.live_transport_readiness = dict(live_transport_readiness)
    report.venue_live_configuration_snapshot = dict(venue_live_configuration_snapshot)
    report.live_route_evidence = dict(live_route_evidence)
    report.live_auth_compliance_evidence = dict(live_auth_compliance_evidence)
    report.selected_live_path_receipt = dict(selected_live_path_receipt)
    report.order_trace_artifacts = dict(order_trace_artifacts)
    report.live_attempt_timeline = dict(live_attempt_timeline)
    report.live_blocker_snapshot = dict(live_blocker_snapshot)
    report.selected_live_path_audit = dict(selected_live_path_audit)
    report.live_lifecycle_snapshot = dict(live_lifecycle_snapshot)
    report.venue_submission_state = str(venue_state_fields["venue_order_submission_state"])
    report.venue_ack_state = str(venue_state_fields["venue_order_ack_state"])
    report.venue_cancel_state = str(venue_state_fields["venue_order_cancel_state"])
    report.venue_execution_state = str(venue_state_fields["venue_order_execution_state"])
    report.order.venue_order_submission_state = str(venue_state_fields["venue_order_submission_state"])
    report.order.venue_order_ack_state = str(venue_state_fields["venue_order_ack_state"])
    report.order.venue_order_cancel_state = str(venue_state_fields["venue_order_cancel_state"])
    report.order.venue_order_execution_state = str(venue_state_fields["venue_order_execution_state"])
    report.metadata = {
        **dict(report.metadata or {}),
        "venue_order_ack_path": venue_order_ack_path,
        "live_preflight_passed": live_preflight_passed,
        "attempted_live": attempted_live,
        "live_submission_performed": live_submission_performed,
        "live_submission_phase": live_submission_phase,
        "venue_live_submission_bound": venue_live_submission_bound,
        "operator_bound": operator_bound,
        "live_runtime_honest_mode": live_runtime_honest_mode,
        "live_submission_failed": live_submission_failed,
        "live_acknowledged": live_acknowledged,
        "live_cancel_observed": live_cancel_observed,
        "live_submission_receipt": live_submission_receipt,
        "venue_submission_receipt": venue_submission_receipt,
        "venue_cancellation_receipt": venue_cancellation_receipt,
        "live_transport_readiness": live_transport_readiness,
        "venue_live_configuration_snapshot": venue_live_configuration_snapshot,
        "live_route_evidence": live_route_evidence,
        "live_auth_compliance_evidence": live_auth_compliance_evidence,
        "selected_live_path_receipt": selected_live_path_receipt,
        "order_trace_artifacts": order_trace_artifacts,
        "live_attempt_timeline": live_attempt_timeline,
        "live_blocker_snapshot": live_blocker_snapshot,
        "selected_live_path_audit": selected_live_path_audit,
        "live_lifecycle_snapshot": live_lifecycle_snapshot,
        "venue_submission_state": venue_state_fields["venue_order_submission_state"],
        "venue_ack_state": venue_state_fields["venue_order_ack_state"],
        "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
        "venue_execution_state": venue_state_fields["venue_order_execution_state"],
    }
    report.order.metadata = {
        **dict(report.order.metadata or {}),
        "venue_order_ack_path": venue_order_ack_path,
        "live_preflight_passed": live_preflight_passed,
        "attempted_live": attempted_live,
        "live_submission_performed": live_submission_performed,
        "live_submission_phase": live_submission_phase,
        "venue_live_submission_bound": venue_live_submission_bound,
        "operator_bound": operator_bound,
        "live_runtime_honest_mode": live_runtime_honest_mode,
        "live_submission_failed": live_submission_failed,
        "live_acknowledged": live_acknowledged,
        "live_cancel_observed": live_cancel_observed,
        "live_submission_receipt": live_submission_receipt,
        "venue_submission_receipt": venue_submission_receipt,
        "venue_cancellation_receipt": venue_cancellation_receipt,
        "live_transport_readiness": live_transport_readiness,
        "venue_live_configuration_snapshot": venue_live_configuration_snapshot,
        "live_route_evidence": live_route_evidence,
        "live_auth_compliance_evidence": live_auth_compliance_evidence,
        "selected_live_path_receipt": selected_live_path_receipt,
        "order_trace_artifacts": order_trace_artifacts,
        "live_attempt_timeline": live_attempt_timeline,
        "live_blocker_snapshot": live_blocker_snapshot,
        "selected_live_path_audit": selected_live_path_audit,
        "live_lifecycle_snapshot": live_lifecycle_snapshot,
        "venue_submission_state": venue_state_fields["venue_order_submission_state"],
        "venue_ack_state": venue_state_fields["venue_order_ack_state"],
        "venue_cancel_state": venue_state_fields["venue_order_cancel_state"],
        "venue_execution_state": venue_state_fields["venue_order_execution_state"],
    }


def _market_action_time_guard(
    *,
    market: MarketDescriptor,
    snapshot: MarketSnapshot | None,
    execution_projection: ExecutionProjection | None,
    resolution_guard: ResolutionGuardReport | None,
    executable_edge: ExecutableEdge | None,
    require_execution_projection: bool = True,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    blocked_reasons: list[str] = []
    warning_reasons: list[str] = []

    projection_valid = True
    projection_audit: dict[str, Any] = {
        "projection_present": execution_projection is not None,
        "projection_valid": None,
        "projection_id": getattr(execution_projection, "projection_id", None),
        "projection_verdict": getattr(getattr(execution_projection, "projection_verdict", None), "value", None),
        "projection_projected_mode": getattr(getattr(execution_projection, "projected_mode", None), "value", None),
        "projection_expires_at": getattr(getattr(execution_projection, "expires_at", None), "isoformat", lambda: None)(),
        "projection_manual_review_required": getattr(execution_projection, "manual_review_required", None),
    }
    if execution_projection is None and require_execution_projection:
        blocked_reasons.append("missing_execution_projection")
        projection_valid = False
    elif execution_projection is not None:
        if execution_projection.is_expired(now):
            blocked_reasons.append("execution_projection_expired")
            projection_valid = False
        elif execution_projection.is_stale(now):
            blocked_reasons.append("execution_projection_stale")
            projection_valid = False
        if execution_projection.projection_verdict == execution_projection.projection_verdict.blocked:
            blocked_reasons.append("execution_projection_blocked")
            projection_valid = False
        if execution_projection.manual_review_required:
            blocked_reasons.append("execution_projection_manual_review_required")
            projection_valid = False
    projection_audit["projection_valid"] = projection_valid

    resolved_resolution_guard = resolution_guard or evaluate_resolution_policy(market, snapshot=snapshot)
    resolution_valid = bool(
        resolved_resolution_guard is not None
        and resolved_resolution_guard.approved
        and resolved_resolution_guard.can_forecast
        and not resolved_resolution_guard.manual_review_required
        and resolved_resolution_guard.status == ResolutionStatus.clear
    )
    if resolved_resolution_guard is None:
        blocked_reasons.append("missing_resolution_guard")
    else:
        if not resolved_resolution_guard.approved:
            blocked_reasons.append("resolution_guard_not_approved")
        if not resolved_resolution_guard.can_forecast:
            blocked_reasons.append("resolution_guard_cannot_forecast")
        if resolved_resolution_guard.manual_review_required:
            blocked_reasons.append("resolution_guard_manual_review_required")
        if resolved_resolution_guard.status != ResolutionStatus.clear:
            blocked_reasons.append(f"resolution_guard_status:{resolved_resolution_guard.status.value}")
        if not resolved_resolution_guard.official_source:
            blocked_reasons.append("resolution_guard_missing_official_source")
            resolution_valid = False

    edge_valid = True
    edge_audit: dict[str, Any] = {
        "executable_edge_present": executable_edge is not None,
        "executable_edge_valid": None,
        "executable_edge_id": getattr(executable_edge, "edge_id", None),
        "executable_edge_expires_at": getattr(getattr(executable_edge, "expires_at", None), "isoformat", lambda: None)(),
        "executable_edge_manual_review_required": getattr(executable_edge, "manual_review_required", None),
        "executable_edge_confidence": getattr(executable_edge, "confidence", None),
        "executable_edge_bps": getattr(executable_edge, "executable_edge_bps", None),
    }
    if executable_edge is not None:
        if executable_edge.expires_at <= now:
            blocked_reasons.append("executable_edge_expired")
            edge_valid = False
        if executable_edge.manual_review_required:
            blocked_reasons.append("executable_edge_manual_review_required")
            edge_valid = False
        if not executable_edge.executable:
            blocked_reasons.append("executable_edge_not_executable")
            edge_valid = False
        if executable_edge.executable_edge_bps <= 0.0:
            blocked_reasons.append("executable_edge_non_positive")
            edge_valid = False
    edge_audit["executable_edge_valid"] = edge_valid

    blocked_reasons = list(dict.fromkeys(blocked_reasons))
    verdict = "blocked" if blocked_reasons else "ok"
    if not blocked_reasons and execution_projection is not None and execution_projection.projection_verdict.value != "ready":
        warning_reasons.append(f"projection_verdict:{execution_projection.projection_verdict.value}")
        verdict = "annotated"
    summary_parts = [f"verdict={verdict}"]
    if blocked_reasons:
        summary_parts.append("blocked=" + ";".join(blocked_reasons[:6]))
    if warning_reasons:
        summary_parts.append("warnings=" + ";".join(warning_reasons[:6]))
    return {
        "action_time_guard_id": f"maguard_{uuid4().hex[:12]}",
        "market_id": market.market_id,
        "venue": market.venue.value,
        "timestamp": now.isoformat(),
        "verdict": verdict,
        "summary": " | ".join(summary_parts),
        "projection_valid": projection_valid,
        "resolution_guard_valid": resolution_valid,
        "executable_edge_valid": edge_valid,
        "projection": projection_audit,
        "resolution_guard": {
            "resolution_guard_present": resolved_resolution_guard is not None,
            "resolution_guard_valid": resolution_valid,
            "resolution_guard_status": getattr(resolved_resolution_guard.status, "value", None) if resolved_resolution_guard is not None else None,
            "resolution_guard_approved": getattr(resolved_resolution_guard, "approved", None),
            "resolution_guard_manual_review_required": getattr(resolved_resolution_guard, "manual_review_required", None),
            "resolution_guard_can_forecast": getattr(resolved_resolution_guard, "can_forecast", None),
            "resolution_guard_id": getattr(resolved_resolution_guard, "policy_id", None),
            "resolution_guard_official_source": getattr(resolved_resolution_guard, "official_source", None),
        },
        "executable_edge": edge_audit,
        "blocked_reasons": blocked_reasons,
        "warning_reasons": warning_reasons,
    }


class MarketExecutionStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "market_execution"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, report: MarketExecutionRecord) -> Path:
        path = self.root / f"{report.report_id}.json"
        save_json(path, report)
        return path

    def load(self, report_id: str) -> MarketExecutionRecord:
        return MarketExecutionRecord.model_validate_json((self.root / f"{report_id}.json").read_text(encoding="utf-8"))

    def list(self) -> list[MarketExecutionRecord]:
        if not self.root.exists():
            return []
        records: list[MarketExecutionRecord] = []
        for path in sorted(self.root.glob("*.json")):
            records.append(MarketExecutionRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return records


class MarketExecutionEngine:
    def materialize(
        self,
        live_execution: Any,
        *,
        trade_intent: TradeIntent | None = None,
        execution_projection: Any | None = None,
        ledger_after: CapitalLedgerSnapshot | None = None,
        persist: bool = False,
        store: MarketExecutionStore | None = None,
    ) -> MarketExecutionRecord:
        live_metadata = getattr(live_execution, "metadata", {}) or {}
        live_status = getattr(getattr(live_execution, "status", None), "value", str(getattr(live_execution, "status", "")))
        effective_projection = execution_projection or getattr(live_execution, "execution_projection", None)
        execution_mode = (
            MarketExecutionMode.bounded_dry_run
            if bool(getattr(live_execution, "dry_run", False)) or live_status == "dry_run"
            else MarketExecutionMode.bounded_live
        )
        order = MarketExecutionOrder(
            execution_id=live_execution.execution_id,
            run_id=live_execution.run_id,
            market_id=live_execution.market_id,
            venue=live_execution.venue,
            position_side=_position_side_from_live(live_execution),
            execution_side=TradeSide.buy,
            order_type=MarketExecutionOrderType.limit
            if getattr(live_execution.paper_trade, "reference_price", None) is not None
            else MarketExecutionOrderType.market,
            requested_quantity=getattr(live_execution.paper_trade, "requested_quantity", 0.0) or 0.0,
            requested_notional=live_execution.requested_stake,
            limit_price=getattr(live_execution.paper_trade, "reference_price", None),
            metadata={
                "dry_run": live_execution.dry_run,
                "execution_adapter": getattr(live_execution, "execution_adapter", ""),
            },
        )
        status = _status_from_live_execution(live_execution, live_execution.paper_trade)
        if effective_projection is None and live_status != MarketExecutionStatus.blocked.value:
            status = MarketExecutionStatus.blocked
        report = MarketExecutionRecord.from_paper_trade(
            paper_trade=live_execution.paper_trade
            or PaperTradeSimulation(
                run_id=live_execution.run_id,
                market_id=live_execution.market_id,
                venue=live_execution.venue,
                position_side=_position_side_from_live(live_execution),
                execution_side=TradeSide.buy,
                stake=live_execution.requested_stake,
                status=PaperTradeStatus.rejected,
                metadata={"source": "market_execution_fallback"},
            ),
            order=order,
            mode=execution_mode,
            capability=getattr(live_execution, "execution_capability", {}),
            execution_plan=getattr(live_execution, "execution_plan", {}),
            ledger_before=live_execution.ledger_before,
            ledger_after=ledger_after or live_execution.ledger_after,
            ledger_change=getattr(live_execution, "ledger_change", None),
            trade_intent_ref=getattr(trade_intent, "intent_id", None) or live_metadata.get("trade_intent_id"),
            execution_projection_ref=getattr(effective_projection, "projection_id", None),
            metadata={
                **live_metadata,
                "live_execution_status": getattr(live_execution.status, "value", str(live_execution.status)),
                "missing_execution_projection": effective_projection is None,
            },
        )
        _apply_live_execution_status(report, live_status)
        report.runtime_guard = dict(live_metadata.get("runtime_guard") or getattr(live_execution, "runtime_guard", {}) or {})
        action_time_guard = dict(live_metadata.get("action_time_guard") or getattr(live_execution, "action_time_guard", {}) or {})
        report.action_time_guard = action_time_guard
        order_trace_audit = _merge_order_trace_audit_payload(
            live_metadata.get("order_trace_audit"),
            _order_trace_audit_from_lifecycle(
                report.order.metadata.get("venue_order_lifecycle") or report.metadata.get("venue_order_lifecycle") or live_metadata.get("venue_order_lifecycle"),
                live_execution_status=live_status,
                final_status=getattr(report.status, "value", str(report.status)),
            ),
        )
        if order_trace_audit is not None:
            report.metadata["order_trace_audit"] = order_trace_audit
            report.order.metadata["order_trace_audit"] = order_trace_audit
            if order_trace_audit.get("venue_order_ack_path") is not None:
                report.metadata["venue_order_ack_path"] = order_trace_audit.get("venue_order_ack_path")
                report.order.metadata["venue_order_ack_path"] = order_trace_audit.get("venue_order_ack_path")
            _apply_live_execution_audit(report, order_trace_audit)
        if effective_projection is None and live_status != MarketExecutionStatus.blocked.value:
            missing_projection_guard = {
                "action_time_guard_id": f"maguard_{uuid4().hex[:12]}",
                "market_id": report.market_id,
                "venue": report.venue.value,
                "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "verdict": "blocked",
                "summary": "verdict=blocked | blocked=missing_execution_projection",
                "projection_valid": False,
                "resolution_guard_valid": None,
                "executable_edge_valid": None,
                "projection": {
                    "projection_present": False,
                    "projection_valid": False,
                    "projection_id": None,
                    "projection_verdict": None,
                    "projection_projected_mode": None,
                    "projection_expires_at": None,
                    "projection_manual_review_required": None,
                },
                "resolution_guard": {},
                "executable_edge": {},
                "blocked_reasons": ["missing_execution_projection"],
                "warning_reasons": [],
            }
            report.action_time_guard = missing_projection_guard
            report.metadata["action_time_guard"] = missing_projection_guard
            report.status = MarketExecutionStatus.blocked
            report.blocked_reasons = list(dict.fromkeys([*report.blocked_reasons, "missing_execution_projection"]))
        if action_time_guard:
            report.metadata["action_time_guard"] = action_time_guard
        if live_status == MarketExecutionStatus.cancelled.value:
            cancelled_reason = None
            for candidate in (
                getattr(live_execution, "venue_order_cancel_reason", None),
                getattr(getattr(live_execution, "market_execution", None), "cancelled_reason", None),
                getattr(live_execution, "blocked_reason", None),
                "; ".join(action_time_guard.get("blocked_reasons", [])) if action_time_guard.get("blocked_reasons") else None,
                "; ".join(getattr(live_execution, "no_trade_reasons", [])) if getattr(live_execution, "no_trade_reasons", None) else None,
                "live_execution_cancelled",
            ):
                if candidate:
                    cancelled_reason = str(candidate)
                    break
            cancelled_by = (
                getattr(live_execution, "venue_order_cancelled_by", None)
                or getattr(getattr(live_execution, "market_execution", None), "cancelled_by", None)
                or getattr(live_execution, "blocked_by", None)
                or "live_execution"
            )
            cancelled_at = (
                getattr(live_execution, "venue_order_cancelled_at", None)
                or getattr(getattr(live_execution, "market_execution", None), "cancelled_at", None)
                or datetime.now(timezone.utc).replace(microsecond=0)
            )
            order.cancelled_reason = cancelled_reason
            order.cancelled_by = cancelled_by
            order.cancelled_at = cancelled_at
            order.acknowledged_reason = cancelled_reason
            order.acknowledged_by = cancelled_by
            order.acknowledged_at = cancelled_at
            order.status = MarketExecutionStatus.cancelled.value
            report = MarketExecutionRecord.from_cancelled(
                order=order,
                mode=execution_mode,
                reason=cancelled_reason,
                cancelled_by=cancelled_by,
                capability=getattr(live_execution, "execution_capability", {}),
                execution_plan=getattr(live_execution, "execution_plan", {}),
                ledger_before=live_execution.ledger_before,
                ledger_after=ledger_after or live_execution.ledger_after,
                ledger_change=getattr(live_execution, "ledger_change", None),
                trade_intent_ref=getattr(trade_intent, "intent_id", None) or live_metadata.get("trade_intent_id"),
                execution_projection_ref=getattr(execution_projection, "projection_id", None)
                or getattr(getattr(live_execution, "execution_projection", None), "projection_id", None),
                metadata={
                    **live_metadata,
                    "live_execution_status": live_status,
                    "cancelled_reason": cancelled_reason,
                    "cancelled_by": cancelled_by,
                },
            )
            _apply_live_execution_status(report, live_status)
            report.runtime_guard = dict(live_metadata.get("runtime_guard") or getattr(live_execution, "runtime_guard", {}) or {})
            report.action_time_guard = action_time_guard
            order_trace_audit = _merge_order_trace_audit_payload(
                live_metadata.get("order_trace_audit"),
                _order_trace_audit_from_lifecycle(
                    report.order.metadata.get("venue_order_lifecycle") or report.metadata.get("venue_order_lifecycle") or live_metadata.get("venue_order_lifecycle"),
                    live_execution_status=live_status,
                    final_status=getattr(report.status, "value", str(report.status)),
                ),
            )
            if order_trace_audit is not None:
                report.metadata["order_trace_audit"] = order_trace_audit
                report.order.metadata["order_trace_audit"] = order_trace_audit
                if order_trace_audit.get("venue_order_ack_path") is not None:
                    report.metadata["venue_order_ack_path"] = order_trace_audit.get("venue_order_ack_path")
                    report.order.metadata["venue_order_ack_path"] = order_trace_audit.get("venue_order_ack_path")
                _apply_live_execution_audit(report, order_trace_audit)
            if action_time_guard:
                report.metadata["action_time_guard"] = action_time_guard
            if trade_intent is not None and (not trade_intent.risk_checks_passed or trade_intent.no_trade_reasons):
                report.blocked_reasons = list(dict.fromkeys([*report.blocked_reasons, *(trade_intent.no_trade_reasons or [])]))
            if persist:
                (store or MarketExecutionStore()).save(report)
            return report
        report.status = status
        if action_time_guard.get("blocked_reasons"):
            if report.status != MarketExecutionStatus.cancelled:
                report.status = MarketExecutionStatus.blocked
            report.blocked_reasons = list(dict.fromkeys([*report.blocked_reasons, *action_time_guard.get("blocked_reasons", [])]))
        if trade_intent is not None and (not trade_intent.risk_checks_passed or trade_intent.no_trade_reasons):
            report.status = MarketExecutionStatus.blocked
            report.blocked_reasons = list(trade_intent.no_trade_reasons or [getattr(live_execution.status, "value", str(live_execution.status))])
        elif getattr(live_execution.status, "value", str(live_execution.status)) == MarketExecutionStatus.blocked.value:
            report.status = MarketExecutionStatus.blocked
            report.blocked_reasons = list(getattr(live_execution, "no_trade_reasons", [])) or [MarketExecutionStatus.blocked.value]
        if persist:
            (store or MarketExecutionStore()).save(report)
        return report


class BoundedMarketExecutionEngine:
    paper_simulator: PaperTradeSimulator

    def __init__(self, paper_simulator: PaperTradeSimulator | None = None) -> None:
        self.paper_simulator = paper_simulator or PaperTradeSimulator()

    def execute(
        self,
        request: MarketExecutionRequest,
        *,
        capability: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
    ) -> MarketExecutionRecord:
        snapshot = request.snapshot
        paper_trade = request.paper_trade
        market = request.market or MarketDescriptor(
            market_id=request.market_id or (snapshot.market_id if snapshot is not None else ""),
            venue=request.venue or (snapshot.venue if snapshot is not None else VenueName.polymarket),
            title=request.market.title if request.market is not None else (snapshot.title if snapshot is not None else ""),
            question=request.market.question if request.market is not None else (snapshot.question if snapshot is not None else ""),
        )
        action_time_guard = _market_action_time_guard(
            market=market,
            snapshot=snapshot,
            execution_projection=request.execution_projection,
            resolution_guard=request.resolution_guard,
            executable_edge=request.executable_edge,
            require_execution_projection=False,
        )
        if action_time_guard["blocked_reasons"]:
            order = MarketExecutionOrder(
                run_id=request.run_id or f"mexec_{uuid4().hex[:12]}",
                market_id=request.market_id or (request.market.market_id if request.market is not None else (snapshot.market_id if snapshot is not None else "")),
                venue=request.venue or (request.market.venue if request.market is not None else (snapshot.venue if snapshot is not None else VenueName.polymarket)),
                position_side=request.position_side,
                execution_side=request.execution_side,
                requested_quantity=request.requested_quantity,
                requested_notional=request.requested_notional or request.stake,
                limit_price=request.limit_price,
                metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
            )
            report = MarketExecutionRecord.from_cancelled(
                order=order,
                mode=MarketExecutionMode.bounded_dry_run if request.dry_run else MarketExecutionMode.bounded_live,
                reason="; ".join(action_time_guard["blocked_reasons"]),
                cancelled_by="action_time_guard",
                capability=capability,
                execution_plan=execution_plan,
                ledger_before=request.ledger_before,
                ledger_after=request.ledger_after,
                metadata={**dict(request.metadata), "action_time_guard": action_time_guard, "action_time_guard_blocked": True},
            )
            report.action_time_guard = action_time_guard
            report.metadata["action_time_guard"] = action_time_guard
            return report
        if paper_trade is None and snapshot is not None:
            stake = request.requested_notional or request.stake
            paper_trade = self.paper_simulator.simulate(
                snapshot,
                position_side=request.position_side,
                execution_side=request.execution_side,
                stake=stake,
                run_id=request.run_id or f"mexec_{uuid4().hex[:12]}",
                market_id=request.market_id or snapshot.market_id,
                venue=request.venue or snapshot.venue,
                limit_price=request.limit_price,
                metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
            )
        if paper_trade is None:
            order = MarketExecutionOrder(
                run_id=request.run_id or f"mexec_{uuid4().hex[:12]}",
                market_id=request.market_id or (request.market.market_id if request.market is not None else ""),
                venue=request.venue or (request.market.venue if request.market is not None else VenueName.polymarket),
                position_side=request.position_side,
                execution_side=request.execution_side,
                requested_quantity=request.requested_quantity,
                requested_notional=request.requested_notional or request.stake,
                limit_price=request.limit_price,
                metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
            )
            report = MarketExecutionRecord.from_paper_trade(
                paper_trade=PaperTradeSimulation(
                    run_id=order.run_id,
                    market_id=order.market_id,
                    venue=order.venue,
                    position_side=order.position_side,
                    execution_side=order.execution_side,
                    stake=order.requested_notional,
                    status=PaperTradeStatus.skipped,
                    metadata={"source": "bounded_engine_no_snapshot"},
                ),
                order=order,
                mode=MarketExecutionMode.bounded_dry_run if request.dry_run else MarketExecutionMode.bounded_live,
                capability=capability,
                execution_plan=execution_plan,
                ledger_before=request.ledger_before,
                ledger_after=request.ledger_after,
                metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
            )
            report.action_time_guard = action_time_guard
            report.metadata["action_time_guard"] = action_time_guard
            return report
        order = MarketExecutionOrder(
            run_id=request.run_id or paper_trade.run_id,
            market_id=request.market_id or paper_trade.market_id,
            venue=request.venue or paper_trade.venue,
            position_side=request.position_side,
            execution_side=request.execution_side,
            order_type=MarketExecutionOrderType.limit if request.limit_price is not None else MarketExecutionOrderType.market,
            requested_quantity=paper_trade.requested_quantity,
            requested_notional=request.requested_notional or request.stake or paper_trade.stake,
            limit_price=request.limit_price or paper_trade.reference_price,
            metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
        )
        report = MarketExecutionRecord.from_paper_trade(
            paper_trade=paper_trade,
            order=order,
            mode=MarketExecutionMode.bounded_dry_run if request.dry_run else MarketExecutionMode.bounded_live,
            capability=capability,
            execution_plan=execution_plan,
            ledger_before=request.ledger_before,
            ledger_after=request.ledger_after,
            metadata={**dict(request.metadata), "action_time_guard": action_time_guard},
        )
        report.action_time_guard = action_time_guard
        report.metadata["action_time_guard"] = action_time_guard
        return report


def _status_from_paper_trade(paper_trade: PaperTradeSimulation) -> MarketExecutionStatus:
    if paper_trade.status == PaperTradeStatus.partial:
        return MarketExecutionStatus.partial
    if paper_trade.status == PaperTradeStatus.filled:
        return MarketExecutionStatus.filled
    if paper_trade.status == PaperTradeStatus.rejected:
        return MarketExecutionStatus.rejected
    return MarketExecutionStatus.blocked


def _status_from_live_execution(record: Any, paper_trade: PaperTradeSimulation | None) -> MarketExecutionStatus:
    status = getattr(record, "status", None)
    if status is None:
        return MarketExecutionStatus.blocked
    status_value = getattr(status, "value", str(status))
    if status_value == MarketExecutionStatus.blocked.value:
        return MarketExecutionStatus.blocked
    if status_value == MarketExecutionStatus.cancelled.value:
        return MarketExecutionStatus.cancelled
    if status_value == "dry_run" and paper_trade is not None:
        return _status_from_paper_trade(paper_trade)
    if status_value == MarketExecutionStatus.filled.value:
        return MarketExecutionStatus.filled
    if status_value == MarketExecutionStatus.partial.value:
        return MarketExecutionStatus.partial
    if status_value == MarketExecutionStatus.rejected.value:
        return MarketExecutionStatus.rejected
    return MarketExecutionStatus.blocked


def _position_side_from_live(record: Any) -> TradeSide:
    if getattr(record, "paper_trade", None) is not None:
        return record.paper_trade.position_side
    return TradeSide.yes


def _position_from_ledger(
    order_id: str,
    run_id: str,
    market_id: str,
    ledger: CapitalLedgerSnapshot | None,
) -> MarketExecutionPosition | None:
    if ledger is None:
        return None
    for position in ledger.positions:
        if position.market_id == market_id:
            return MarketExecutionPosition.from_ledger_position(position, order_id=order_id, run_id=run_id, source="ledger")
    return None


def _position_from_paper_trade(order_id: str, run_id: str, paper_trade: PaperTradeSimulation) -> MarketExecutionPosition:
    quantity = paper_trade.filled_quantity or paper_trade.requested_quantity
    entry_price = paper_trade.average_fill_price if paper_trade.average_fill_price is not None else paper_trade.reference_price or 0.0
    return MarketExecutionPosition(
        order_id=order_id,
        run_id=run_id,
        market_id=paper_trade.market_id,
        venue=paper_trade.venue,
        side=paper_trade.position_side,
        quantity=quantity,
        entry_price=entry_price,
        mark_price=paper_trade.average_fill_price if paper_trade.average_fill_price is not None else paper_trade.reference_price,
        unrealized_pnl=0.0,
        source="paper_trade",
        metadata={"trade_id": paper_trade.trade_id, "status": paper_trade.status.value},
    )


def _fills_from_paper_trade(order_id: str, paper_trade: PaperTradeSimulation) -> list[MarketExecutionFill]:
    fills: list[MarketExecutionFill] = []
    for fill in paper_trade.fills:
        fills.append(
            MarketExecutionFill(
                order_id=order_id,
                trade_id=paper_trade.trade_id,
                run_id=paper_trade.run_id,
                market_id=paper_trade.market_id,
                venue=paper_trade.venue,
                position_side=fill.position_side,
                execution_side=fill.execution_side,
                requested_quantity=fill.requested_quantity,
                filled_quantity=fill.filled_quantity,
                fill_price=fill.fill_price,
                gross_notional=fill.gross_notional,
                fee_paid=fill.fee_paid,
                slippage_bps=fill.slippage_bps,
                level_index=fill.level_index,
                timestamp=fill.timestamp,
                metadata=dict(fill.metadata),
            )
        )
    return fills


def _positions_from_ledger(
    order_id: str,
    run_id: str,
    market_id: str,
    ledger: CapitalLedgerSnapshot | None,
) -> list[MarketExecutionPosition]:
    if ledger is None:
        return []
    positions: list[MarketExecutionPosition] = []
    for position in ledger.positions:
        if position.market_id != market_id:
            continue
        positions.append(
            MarketExecutionPosition.from_ledger_position(
                position,
                order_id=order_id,
                run_id=run_id,
                source="ledger",
            )
        )
    return positions


ExecutionOrderStatus = MarketExecutionStatus
ExecutionOrder = MarketExecutionOrder
ExecutionFill = MarketExecutionFill
ExecutionPositionSnapshot = MarketExecutionPosition
MarketExecutionReport = MarketExecutionRecord


__all__ = [
    "BoundedMarketExecutionEngine",
    "ExecutionFill",
    "ExecutionOrder",
    "ExecutionOrderStatus",
    "ExecutionPositionSnapshot",
    "MarketExecutionEngine",
    "MarketExecutionFill",
    "MarketExecutionMode",
    "MarketExecutionOrder",
    "MarketExecutionOrderType",
    "MarketExecutionPosition",
    "MarketExecutionRecord",
    "MarketExecutionRequest",
    "MarketExecutionReport",
    "MarketExecutionStatus",
    "MarketExecutionStore",
]
