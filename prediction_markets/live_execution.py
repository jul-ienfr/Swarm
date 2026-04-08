from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .capital_ledger import CapitalControlState, CapitalLedger, CapitalLedgerChange, CapitalLedgerStore
from .execution_edge import ExecutableEdge
from .market_risk import MarketRiskReport
from .market_execution import (
    MarketExecutionMode,
    MarketExecutionOrder,
    MarketExecutionOrderType,
    MarketExecutionRecord,
    MarketExecutionStatus,
    _venue_cancellation_receipt_from_lifecycle,
    _venue_submission_receipt_from_lifecycle,
)
from .models import (
    CapitalLedgerSnapshot,
    DecisionAction,
    ExecutionReadiness,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    MarketDescriptor,
    MarketRecommendationPacket,
    MarketSnapshot,
    PaperTradeRecord,
    ResolutionStatus,
    VenueHealthReport,
    TradeSide,
    VenueName,
    VenueType,
    _utc_datetime,
    _stable_content_hash,
)
from .adapters import VenueExecutionPlan, VenueOrderLifecycle, bind_venue_order_transport, build_execution_adapter, build_venue_order_lifecycle
from .paper_trading import PaperTradeSimulation, PaperTradeStatus, PaperTradeStore, PaperTradeSimulator
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY
from .resolution_guard import ResolutionGuardReport, evaluate_resolution_policy
from .runtime_guard import RuntimeGuardVerdict, build_runtime_guard_trace
from .storage import save_json


class LiveExecutionMode(str, Enum):
    dry_run = "dry_run"
    live = "live"


class LiveExecutionStatus(str, Enum):
    blocked = "blocked"
    dry_run = "dry_run"
    filled = "filled"
    partial = "partial"
    rejected = "rejected"


class ExecutionAuthContext(BaseModel):
    schema_version: str = "v1"
    principal: str = ""
    authorized: bool = False
    compliance_approved: bool = False
    auth_passed: bool | None = None
    compliance_passed: bool | None = None
    jurisdiction: str | None = None
    account_type: str | None = None
    automation_allowed: bool = True
    rate_limit_ok: bool = True
    tos_accepted: bool = False
    scopes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scopes", "notes", mode="before")
    @classmethod
    def _normalize_text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        normalized: list[str] = []
        for item in values:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized


@dataclass
class ExecutionProjectionRuntime:
    ttl_seconds: float = 300.0

    def project(
        self,
        *,
        run_id: str,
        market: MarketDescriptor,
        requested_mode: ExecutionProjectionMode | str,
        readiness: ExecutionReadiness | None,
        execution_plan: VenueExecutionPlan,
        ledger_before: CapitalLedgerSnapshot,
        request_metadata: Mapping[str, Any] | None = None,
        reconciliation_drift_usd: float | None = None,
        venue_health: VenueHealthReport | None = None,
        kill_switch_triggered: bool = False,
    ) -> ExecutionProjection:
        requested = _coerce_projection_mode(requested_mode)
        blocking_reasons: list[str] = []
        downgrade_reasons: list[str] = []
        runtime_guard = build_runtime_guard_trace(
            run_id=run_id,
            market=market,
            requested_mode=requested,
            ledger_before=ledger_before,
            request_metadata=request_metadata,
            reconciliation_drift_usd=reconciliation_drift_usd,
            venue_health=venue_health,
            kill_switch_triggered=kill_switch_triggered,
        )
        request_metadata_dict = dict(request_metadata or {})
        approval_gate = _human_approval_gate_from_metadata(request_metadata_dict, requested=requested)
        anchor_at = _projection_anchor_at(
            readiness=readiness,
            ledger_before=ledger_before,
            venue_health=venue_health,
            request_metadata=request_metadata_dict,
        )
        capital_control_state = CapitalLedger.from_snapshot(ledger_before).capital_control_state(
            extra_metadata=request_metadata_dict,
            reconciliation_open_drift=bool(reconciliation_drift_usd is not None and reconciliation_drift_usd > 0.0),
            reconciliation_drift_usd=reconciliation_drift_usd,
            reconciliation_manual_review_required=bool(
                (reconciliation_drift_usd is not None and reconciliation_drift_usd > 0.0)
                or request_metadata_dict.get("reconciliation_manual_review_required")
                or request_metadata_dict.get("reconciliation_status") == "drifted"
            ),
        )
        capital_control_state_snapshot = capital_control_state.model_dump(mode="json")
        capital_control_state_snapshot["state_id"] = (
            f"ccs_{_stable_content_hash({k: v for k, v in capital_control_state_snapshot.items() if k != 'state_id'})[:12]}"
        )

        readiness_ref = readiness.readiness_id if readiness is not None else None
        compliance_ref = execution_plan.adapter_name
        capital_ref = ledger_before.snapshot_id
        reconciliation_ref = None
        health_ref = None

        if readiness is None:
            blocking_reasons.append("missing_execution_readiness")
        elif not readiness.can_materialize_trade_intent:
            blocking_reasons.extend(readiness.blocked_reasons or ["readiness_not_materializable"])
        if not execution_plan.allowed:
            blocking_reasons.extend(execution_plan.blocked_reasons or ["execution_plan_blocked"])
        if approval_gate["required"] and not approval_gate["passed"]:
            blocking_reasons.append("human_approval_required_before_live")

        highest_authorized = ExecutionProjectionOutcome.blocked
        if readiness is not None and readiness.can_materialize_trade_intent and execution_plan.allowed:
            highest_authorized = ExecutionProjectionOutcome.paper
            if readiness.ready_to_live and execution_plan.live_execution_supported:
                highest_authorized = ExecutionProjectionOutcome.live
            elif readiness.route == "shadow" or bool((readiness.metadata or {}).get("shadow_allowed")):
                highest_authorized = ExecutionProjectionOutcome.shadow
        if approval_gate["required"] and not approval_gate["passed"]:
            highest_authorized = ExecutionProjectionOutcome.paper

        capital_available = capital_control_state.capital_available_usd
        highest_safe_value: str | None = ExecutionProjectionMode.live.value
        if capital_available <= 0.0:
            blocking_reasons.append("capital_unavailable")
            highest_safe_value = None
        elif readiness is not None and readiness.size_usd > 0.0 and capital_available + 1e-9 < readiness.size_usd:
            downgrade_reasons.append(f"capital_below_requested:{capital_available:.2f}/{readiness.size_usd:.2f}")
            highest_safe_value = ExecutionProjectionMode.paper.value

        max_capital_transfer_latency_ms = _float_metadata(request_metadata_dict, "max_capital_transfer_latency_ms", 0.0)
        capital_transfer_latency_estimate_ms = float(capital_control_state_snapshot.get("transfer_latency_estimate_ms", 0.0) or 0.0)
        capital_transfer_latency_exceeded = False
        resolved_markets_below_minimum = False
        if max_capital_transfer_latency_ms > 0.0:
            capital_control_state_snapshot["max_capital_transfer_latency_ms"] = max_capital_transfer_latency_ms
            capital_transfer_latency_exceeded = capital_transfer_latency_estimate_ms > max_capital_transfer_latency_ms
            capital_control_state_snapshot["capital_transfer_latency_exceeded"] = capital_transfer_latency_exceeded
            capital_control_state_snapshot["capital_transfer_latency_room_ms"] = round(
                max(0.0, max_capital_transfer_latency_ms - capital_transfer_latency_estimate_ms),
                6,
            )
            if capital_transfer_latency_exceeded:
                if requested == ExecutionProjectionMode.live:
                    downgrade_reasons.append(
                        f"capital_transfer_latency_exceeded:{capital_transfer_latency_estimate_ms:.6f}/{max_capital_transfer_latency_ms:.6f}"
                    )
                    if highest_safe_value is not None:
                        highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionOutcome.shadow).value
            else:
                downgrade_reasons.append(f"capital_transfer_latency_ok:{max_capital_transfer_latency_ms:.6f}")
        capital_transfer_latency_ready = not bool(capital_control_state_snapshot.get("capital_transfer_latency_exceeded"))

        min_resolved_markets_for_live = int(_float_metadata(request_metadata_dict, "min_resolved_markets_for_live", 0.0))
        resolved_markets_count = int(_float_metadata(request_metadata_dict, "resolved_markets_count", 0.0))
        if min_resolved_markets_for_live > 0:
            if resolved_markets_count < min_resolved_markets_for_live:
                resolved_markets_below_minimum = True
                if requested == ExecutionProjectionMode.live:
                    downgrade_reasons.append(
                        f"resolved_markets_below_minimum:{resolved_markets_count}/{min_resolved_markets_for_live}"
                    )
                    if highest_safe_value is not None:
                        highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionOutcome.shadow).value
            else:
                downgrade_reasons.append(f"resolved_markets_ready:{resolved_markets_count}/{min_resolved_markets_for_live}")

        configured_manual_review_categories = set(_normalized_category_list(request_metadata_dict.get("manual_review_categories")))
        trigger_manual_review_categories = set(
            _normalized_category_list(request_metadata_dict.get("manual_review_category"))
            + _normalized_category_list(request_metadata_dict.get("manual_review_reason_categories"))
        )
        manual_review_category_match = sorted(configured_manual_review_categories.intersection(trigger_manual_review_categories))
        if manual_review_category_match and requested == ExecutionProjectionMode.live:
            downgrade_reasons.append(f"manual_review_category:{manual_review_category_match[0]}")
            highest_safe_value = ExecutionProjectionMode.paper.value

        if (
            requested == ExecutionProjectionMode.live
            and highest_authorized == ExecutionProjectionOutcome.paper
            and readiness is not None
            and readiness.can_materialize_trade_intent
            and execution_plan.allowed
            and execution_plan.live_execution_supported
            and (capital_transfer_latency_exceeded or resolved_markets_below_minimum)
        ):
            highest_authorized = ExecutionProjectionOutcome.shadow

        if reconciliation_drift_usd is not None:
            reconciliation_ref = f"reconciliation_drift_usd:{reconciliation_drift_usd:.6f}"
            max_drift = _float_metadata(ledger_before.metadata, "max_reconciliation_drift_usd", 0.0)
            if reconciliation_drift_usd > max_drift > 0.0:
                blocking_reasons.append(f"reconciliation_drift_exceeded:{reconciliation_drift_usd:.6f}/{max_drift:.6f}")
                highest_safe_value = None
            elif reconciliation_drift_usd > 0.0 and highest_safe_value is not None:
                downgrade_reasons.append(f"reconciliation_drift:{reconciliation_drift_usd:.6f}")
                highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionOutcome.shadow).value

        if venue_health is not None:
            health_ref = f"{venue_health.venue.value}:{venue_health.checked_at.isoformat()}"
            if not venue_health.healthy:
                if venue_health.details.get("degraded_mode") or "degraded" in venue_health.message.lower():
                    downgrade_reasons.append(f"venue_degraded:{venue_health.message}")
                    if highest_safe_value is not None:
                        highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionOutcome.shadow).value
                else:
                    blocking_reasons.append(f"venue_unhealthy:{venue_health.message}")
                    highest_safe_value = None

        if readiness is not None and readiness.manual_review_required:
            downgrade_reasons.append("manual_review_required")
            if highest_safe_value is not None:
                highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionMode.paper).value
        if approval_gate["required"] and not approval_gate["passed"]:
            downgrade_reasons.append("human_approval_required_before_live")
            highest_safe_value = None

        blocking_reasons.extend(runtime_guard.blocked_reasons)
        downgrade_reasons.extend(runtime_guard.degraded_reasons)
        if runtime_guard.verdict == RuntimeGuardVerdict.blocked:
            highest_safe_value = None
        elif runtime_guard.verdict == RuntimeGuardVerdict.degraded and highest_safe_value is not None:
            highest_safe_value = min_projection_mode(highest_safe_value or ExecutionProjectionMode.live.value, ExecutionProjectionOutcome.shadow).value

        safe_outcome = (
            ExecutionProjectionOutcome.blocked
            if highest_safe_value is None
            else ExecutionProjectionOutcome(highest_safe_value)
        )
        projected_mode = min_projection_mode(requested, highest_authorized)
        projected_mode = min_projection_mode(projected_mode, safe_outcome)
        projected_mode = ExecutionProjectionOutcome(getattr(projected_mode, "value", str(projected_mode)))
        if projected_mode == ExecutionProjectionOutcome.blocked:
            verdict = ExecutionProjectionVerdict.blocked
        elif getattr(projected_mode, "value", str(projected_mode)) == getattr(requested, "value", str(requested)):
            verdict = ExecutionProjectionVerdict.ready
        else:
            verdict = ExecutionProjectionVerdict.degraded

        ttl = max(30.0, float(self.ttl_seconds))
        expires_at = _projection_expires_at(anchor_at, ttl)
        runtime_guard_snapshot = runtime_guard.model_dump(mode="json")
        runtime_guard_snapshot["trace_id"] = f"rguard_{_stable_content_hash({k: v for k, v in runtime_guard_snapshot.items() if k != 'trace_id'})[:12]}"
        projection_payload = {
            "run_id": run_id,
            "market_id": market.market_id,
            "venue": market.venue.value,
            "requested_mode": requested.value,
            "projected_mode": projected_mode.value,
            "projection_verdict": verdict.value,
            "highest_safe_mode": None if highest_safe_value is None else ExecutionProjectionMode(highest_safe_value).value,
            "highest_authorized_mode": highest_authorized.value,
            "readiness": None if readiness is None else readiness.model_dump(mode="json"),
            "execution_plan": execution_plan.model_dump(mode="json"),
            "ledger_before": ledger_before.model_dump(mode="json"),
            "reconciliation_drift_usd": reconciliation_drift_usd,
            "venue_health": None if venue_health is None else venue_health.model_dump(mode="json"),
            "metadata": {
                "capital_available": capital_available,
                "capital_control_state": capital_control_state_snapshot,
                "venue_health_healthy": None if venue_health is None else venue_health.healthy,
                "projection_anchor_at": anchor_at.isoformat(),
                "runtime_guard": runtime_guard_snapshot,
                "promotion_stage": "blocked" if highest_safe_value is None else ("live" if highest_safe_value == ExecutionProjectionMode.live.value else highest_safe_value),
                "manual_review_categories": _normalized_category_list(request_metadata_dict.get("manual_review_categories")),
                "manual_review_trigger_categories": _normalized_category_list(request_metadata_dict.get("manual_review_category"))
                + _normalized_category_list(request_metadata_dict.get("manual_review_reason_categories")),
                "manual_review_category_match": manual_review_category_match,
                "resolved_markets_count": resolved_markets_count,
                "min_resolved_markets_for_live": min_resolved_markets_for_live,
                "resolved_markets_for_live": resolved_markets_count >= min_resolved_markets_for_live,
                "capital_transfer_latency_estimate_ms": capital_transfer_latency_estimate_ms,
                "capital_transfer_latency_ready": capital_transfer_latency_ready,
                "max_capital_transfer_latency_ms": max_capital_transfer_latency_ms,
                "human_approval_required_before_live": approval_gate["required"],
                "human_approval_passed": approval_gate["passed"],
                "human_approval_actor": approval_gate["actor"],
                "human_approval_reason": approval_gate["reason"],
                "approval_gate": approval_gate,
            },
            "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
            "downgrade_reasons": list(dict.fromkeys(downgrade_reasons)),
            "manual_review_required": bool(
                (readiness.manual_review_required if readiness is not None else False)
                or (approval_gate["required"] and not approval_gate["passed"])
            ),
        }
        projection_id = f"proj_{_stable_content_hash(projection_payload)[:12]}"
        summary = _projection_summary_text(
            requested=requested,
            projected=projected_mode,
            verdict=verdict,
            blocking_reasons=blocking_reasons,
            downgrade_reasons=downgrade_reasons,
        )
        return ExecutionProjection(
            projection_id=projection_id,
            run_id=run_id,
            venue=market.venue,
            market_id=market.market_id,
            requested_mode=requested,
            projected_mode=projected_mode,
            projection_verdict=verdict,
            blocking_reasons=blocking_reasons,
            downgrade_reasons=downgrade_reasons,
            manual_review_required=bool(
                (readiness.manual_review_required if readiness is not None else False)
                or (approval_gate["required"] and not approval_gate["passed"])
            ),
            readiness_ref=readiness_ref,
            compliance_ref=compliance_ref,
            capital_ref=capital_ref,
            reconciliation_ref=reconciliation_ref,
            health_ref=health_ref,
            highest_safe_requested_mode=None if highest_safe_value is None else ExecutionProjectionMode(highest_safe_value),
            highest_safe_mode=None if highest_safe_value is None else ExecutionProjectionMode(highest_safe_value),
            highest_authorized_mode=highest_authorized,
            recommended_effective_mode=projected_mode if projected_mode != ExecutionProjectionOutcome.blocked else None,
            expires_at=expires_at,
            summary=summary,
            basis={
                "uses_execution_readiness": True,
                "uses_compliance": True,
                "uses_capital": True,
                "uses_reconciliation": reconciliation_drift_usd is not None,
                "uses_venue_health": venue_health is not None,
                "uses_human_approval": approval_gate["required"],
                "uses_manual_review_categories": bool(configured_manual_review_categories),
                "uses_resolved_markets_threshold": min_resolved_markets_for_live > 0,
                "uses_capital_transfer_latency_threshold": max_capital_transfer_latency_ms > 0.0,
                "capital_status": "available" if capital_available > 0.0 else "unavailable",
                "reconciliation_status": "available" if reconciliation_drift_usd is not None else "unavailable",
                "venue_health_status": "available" if venue_health is not None else "unavailable",
                "compliance_status": "available" if readiness is not None else "unavailable",
                "human_approval_status": approval_gate["state"],
            },
            metadata={
                "requested_rank": _mode_rank(requested),
                "projected_rank": _mode_rank(projected_mode),
                "capital_available": capital_available,
                "capital_control_state": capital_control_state_snapshot,
                "venue_health_healthy": None if venue_health is None else venue_health.healthy,
                "projection_anchor_at": anchor_at.isoformat(),
                "runtime_guard": runtime_guard_snapshot,
                "promotion_stage": "blocked" if highest_safe_value is None else ("live" if highest_safe_value == ExecutionProjectionMode.live.value else highest_safe_value),
                "manual_review_categories": _normalized_category_list(request_metadata_dict.get("manual_review_categories")),
                "manual_review_trigger_categories": _normalized_category_list(request_metadata_dict.get("manual_review_category"))
                + _normalized_category_list(request_metadata_dict.get("manual_review_reason_categories")),
                "manual_review_category_match": manual_review_category_match,
                "resolved_markets_count": resolved_markets_count,
                "min_resolved_markets_for_live": min_resolved_markets_for_live,
                "resolved_markets_for_live": resolved_markets_count >= min_resolved_markets_for_live,
                "capital_transfer_latency_estimate_ms": capital_transfer_latency_estimate_ms,
                "capital_transfer_latency_ready": capital_transfer_latency_ready,
                "max_capital_transfer_latency_ms": max_capital_transfer_latency_ms,
                "human_approval_required_before_live": approval_gate["required"],
                "human_approval_passed": approval_gate["passed"],
                "human_approval_actor": approval_gate["actor"],
                "human_approval_reason": approval_gate["reason"],
                "approval_gate": approval_gate,
                "incident_runbook": runtime_guard.incident_runbook,
            },
        )


class LiveExecutionPolicy(BaseModel):
    schema_version: str = "v1"
    kill_switch_enabled: bool = False
    max_realized_loss: float = 0.0
    max_drawdown_abs: float = 0.0
    max_drawdown_fraction_of_peak_equity: float = 0.0
    min_free_cash_buffer_pct: float = 0.0
    per_venue_balance_cap_usd: float = 0.0
    max_market_exposure_usd: float = 0.0
    max_open_positions: int = 0
    max_daily_loss_usd: float = 0.0
    dry_run_enabled: bool = True
    allow_live_execution: bool = False
    allowed_venues: set[VenueName] = Field(default_factory=lambda: {VenueName.polymarket})
    blocked_venues: set[VenueName] = Field(default_factory=set)
    blocked_market_ids: set[str] = Field(default_factory=set)
    allowed_jurisdictions: set[str] = Field(default_factory=set)
    allowed_account_types: set[str] = Field(default_factory=set)
    require_authorization: bool = True
    required_scope: str = "prediction_markets:execute"
    require_compliance_approval: bool = True
    require_human_approval_before_live: bool = False
    require_automation_allowed: bool = False
    require_rate_limit_ok: bool = False
    require_tos_accepted: bool = False
    dry_run_requires_authorization: bool = False
    dry_run_requires_compliance: bool = False
    min_ledger_equity: float = 1.0
    min_confidence: float = 0.6
    min_edge_bps: float = 35.0
    max_stake: float = 250.0
    max_fraction_of_equity: float = 0.05
    max_capital_transfer_latency_ms: float = 0.0
    min_resolved_markets_for_live: int = 0
    manual_review_categories: list[str] = Field(default_factory=list)
    persist_records: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "max_realized_loss",
        "max_drawdown_abs",
        "max_drawdown_fraction_of_peak_equity",
        "min_free_cash_buffer_pct",
        "per_venue_balance_cap_usd",
        "max_market_exposure_usd",
        "max_daily_loss_usd",
        "min_ledger_equity",
        "min_confidence",
        "min_edge_bps",
        "max_stake",
        "max_fraction_of_equity",
        "max_capital_transfer_latency_ms",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        return max(0.0, float(value))

    @field_validator("max_open_positions")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator("min_resolved_markets_for_live")
    @classmethod
    def _non_negative_min_resolved(cls, value: int) -> int:
        return max(0, int(value))

    @field_validator("manual_review_categories", mode="before")
    @classmethod
    def _normalize_manual_review_categories(cls, value: Any) -> list[str]:
        return _normalized_category_list(value)


class LiveExecutionRequest(BaseModel):
    schema_version: str = "v1"
    run_id: str
    market: MarketDescriptor
    snapshot: MarketSnapshot
    recommendation: MarketRecommendationPacket
    requested_mode: str = "paper"
    ledger: CapitalLedgerSnapshot | None = None
    risk_report: MarketRiskReport | None = None
    execution_readiness: ExecutionReadiness | None = None
    execution_projection: ExecutionProjection | None = None
    resolution_guard: ResolutionGuardReport | None = None
    executable_edge: ExecutableEdge | None = None
    reconciliation_drift_usd: float | None = None
    venue_health: VenueHealthReport | None = None
    requested_stake: float | None = None
    dry_run: bool | None = None
    auth: ExecutionAuthContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_stake")
    @classmethod
    def _non_negative(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, float(value))


class LiveExecutionRecord(BaseModel):
    schema_version: str = "v1"
    execution_id: str = Field(default_factory=lambda: f"lexec_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    mode: LiveExecutionMode = LiveExecutionMode.dry_run
    status: LiveExecutionStatus = LiveExecutionStatus.blocked
    dry_run: bool = True
    kill_switch_triggered: bool = False
    loss_cap_triggered: bool = False
    live_allowed: bool = False
    requested_mode: str = "paper"
    projected_mode: str = "blocked"
    projection_verdict: str = "blocked"
    auth_required: bool = True
    auth_passed: bool = False
    compliance_required: bool = True
    compliance_passed: bool = False
    jurisdiction_required: bool = False
    jurisdiction_passed: bool = True
    account_type_required: bool = False
    account_type_passed: bool = True
    automation_required: bool = False
    automation_passed: bool = True
    rate_limit_required: bool = False
    rate_limit_passed: bool = True
    tos_required: bool = False
    tos_passed: bool = True
    venue_allowed: bool = False
    blocked_reason: str | None = None
    loss_cap_reason: str | None = None
    requested_stake: float = 0.0
    executed_stake: float = 0.0
    recommendation_id: str | None = None
    forecast_id: str | None = None
    risk_report_id: str | None = None
    allocation_id: str | None = None
    ledger_before: CapitalLedgerSnapshot
    ledger_after: CapitalLedgerSnapshot
    ledger_change: CapitalLedgerChange | None = None
    paper_trade: PaperTradeSimulation | None = None
    market_execution: MarketExecutionRecord | None = None
    execution_projection: ExecutionProjection | None = None
    venue_order_id: str | None = None
    venue_order_status: str = "unavailable"
    venue_order_source: str = "unavailable"
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
    live_preflight_passed: bool = False
    attempted_live: bool = False
    live_submission_performed: bool = False
    live_submission_phase: str = "dry_run"
    venue_submission_state: str = "simulated"
    venue_ack_state: str = "not_acknowledged"
    venue_cancel_state: str = "not_cancelled"
    venue_execution_state: str = "simulated"
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
    runtime_guard: dict[str, Any] = Field(default_factory=dict)
    action_time_guard: dict[str, Any] = Field(default_factory=dict)
    no_trade_reasons: list[str] = Field(default_factory=list)
    execution_reasons: list[str] = Field(default_factory=list)
    execution_adapter: str = ""
    execution_capability: dict[str, Any] = Field(default_factory=dict)
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveExecutionStore:
    def __init__(self, paths: PredictionMarketPaths | None = None, *, base_dir: str | Path | None = None) -> None:
        if paths is not None:
            self.paths = paths
        elif base_dir is not None:
            self.paths = PredictionMarketPaths(Path(base_dir))
        else:
            self.paths = default_prediction_market_paths()
        self.paths.ensure_layout()
        self.root = self.paths.root / "live_executions"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: LiveExecutionRecord) -> Path:
        path = self.root / f"{record.execution_id}.json"
        save_json(path, record)
        return path

    def load(self, execution_id: str) -> LiveExecutionRecord:
        return LiveExecutionRecord.model_validate_json((self.root / f"{execution_id}.json").read_text(encoding="utf-8"))

    def list(self) -> list[LiveExecutionRecord]:
        if not self.root.exists():
            return []
        records: list[LiveExecutionRecord] = []
        for path in sorted(self.root.glob("*.json")):
            records.append(LiveExecutionRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return records

    def list_by_run(self, run_id: str) -> list[LiveExecutionRecord]:
        return [record for record in self.list() if record.run_id == run_id]

    def list_by_market(self, market_id: str) -> list[LiveExecutionRecord]:
        return [record for record in self.list() if record.market_id == market_id]


@dataclass
class LiveExecutionEngine:
    policy: LiveExecutionPolicy | None = None
    paper_simulator: PaperTradeSimulator = field(default_factory=PaperTradeSimulator)
    projection_runtime: ExecutionProjectionRuntime = field(default_factory=ExecutionProjectionRuntime)
    venue_order_submitters: dict[VenueName, Callable[[MarketExecutionOrder, dict[str, Any]], Any]] = field(default_factory=dict)
    venue_order_cancel_submitters: dict[VenueName, Callable[[MarketExecutionOrder, dict[str, Any]], Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.policy = self.policy or LiveExecutionPolicy()

    def _bind_venue_transport(self, adapter: Any, venue: VenueName) -> Any:
        return bind_venue_order_transport(
            adapter,
            order_submitter=self.venue_order_submitters.get(venue),
            cancel_submitter=self.venue_order_cancel_submitters.get(venue),
        )

    def execute(
        self,
        request: LiveExecutionRequest,
        *,
        persist: bool | None = None,
        store: LiveExecutionStore | None = None,
        ledger_store: CapitalLedgerStore | None = None,
        paper_trade_store: PaperTradeStore | None = None,
    ) -> LiveExecutionRecord:
        policy = self.policy or LiveExecutionPolicy()
        persist = policy.persist_records if persist is None else persist
        ledger_engine = CapitalLedger.from_snapshot(
            request.ledger
            or CapitalLedgerSnapshot(
                venue=request.market.venue,
                cash=1000.0,
                reserved_cash=0.0,
                metadata={"source": "live_execution_default"},
            )
        )
        capital_control_state = ledger_engine.capital_control_state(
            extra_metadata=dict(request.metadata or {}),
            reconciliation_drift_usd=request.reconciliation_drift_usd,
            venue=request.market.venue,
            market_id=request.market.market_id,
            min_free_cash_buffer_pct=policy.min_free_cash_buffer_pct,
            per_venue_balance_cap_usd=policy.per_venue_balance_cap_usd,
            max_market_exposure_usd=policy.max_market_exposure_usd,
            max_open_positions=policy.max_open_positions,
            max_daily_loss_usd=policy.max_daily_loss_usd,
            max_capital_transfer_latency_ms=policy.max_capital_transfer_latency_ms,
        )
        ledger_before = ledger_engine.current_snapshot()
        ledger_before.metadata.update(capital_control_state.metadata)
        ledger_after = ledger_before.model_copy(deep=True)

        auth = request.auth or ExecutionAuthContext()
        request_metadata_input = dict(request.metadata or {})
        auth_passed_override = _metadata_bool_or_none(request_metadata_input, "auth_passed")
        if auth_passed_override is None and auth.auth_passed is not None:
            auth_passed_override = bool(auth.auth_passed)
        compliance_passed_override = _metadata_bool_or_none(request_metadata_input, "compliance_passed")
        if compliance_passed_override is None and auth.compliance_passed is not None:
            compliance_passed_override = bool(auth.compliance_passed)
        dry_run = policy.dry_run_enabled if request.dry_run is None else bool(request.dry_run)
        requested_mode = _coerce_requested_mode(request.requested_mode, dry_run=dry_run, allow_live_execution=policy.allow_live_execution)
        approval_gate = _human_approval_gate_metadata(
            request=request,
            auth=auth,
            policy=policy,
            dry_run=dry_run,
            requested_mode=requested_mode,
        )
        requested_stake, explicit_request = _resolve_requested_stake(request, policy, ledger_before)
        execution_reasons: list[str] = []
        no_trade_reasons: list[str] = []
        loss_cap_triggered, loss_cap_reason = _loss_cap_triggered(policy, ledger_before)
        if loss_cap_triggered and loss_cap_reason:
            no_trade_reasons.append(loss_cap_reason)
        if capital_control_state.freeze_reasons:
            no_trade_reasons.extend(capital_control_state.freeze_reasons)

        execution_adapter = self._bind_venue_transport(build_execution_adapter(request.market.venue), request.market.venue)
        execution_capability = execution_adapter.describe_execution_capabilities()
        execution_plan = execution_adapter.build_execution_plan(
            market=request.market,
            dry_run=dry_run,
            allow_live_execution=policy.allow_live_execution,
            authorized=auth_passed_override if auth_passed_override is not None else auth.authorized,
            compliance_approved=compliance_passed_override if compliance_passed_override is not None else auth.compliance_approved,
            required_scope=policy.required_scope,
            scopes=list(auth.scopes),
            jurisdiction=auth.jurisdiction,
            account_type=auth.account_type,
            automation_allowed=auth.automation_allowed,
            rate_limit_ok=auth.rate_limit_ok,
            tos_accepted=auth.tos_accepted,
            allowed_jurisdictions=set(policy.allowed_jurisdictions),
            allowed_account_types=set(policy.allowed_account_types),
            require_automation_allowed=policy.require_automation_allowed,
            require_rate_limit_ok=policy.require_rate_limit_ok,
            require_tos_accepted=policy.require_tos_accepted,
            dry_run_requires_authorization=policy.dry_run_requires_authorization,
            dry_run_requires_compliance=policy.dry_run_requires_compliance,
        )
        venue_health_live_allowed, venue_health_live_reason = _venue_health_live_allowed(request.venue_health)
        if not venue_health_live_allowed and not dry_run and venue_health_live_reason:
            execution_reasons.append(venue_health_live_reason)
        resolved_markets_count = _resolved_markets_count(request)
        resolved_markets_for_live = policy.min_resolved_markets_for_live <= 0 or resolved_markets_count >= policy.min_resolved_markets_for_live
        manual_review_categories = _normalized_category_list(policy.manual_review_categories)
        manual_review_trigger_categories = _manual_review_trigger_categories(request)
        capital_transfer_latency_estimate_ms = capital_control_state.transfer_latency_estimate_ms
        capital_transfer_latency_ready = not (
            policy.max_capital_transfer_latency_ms > 0.0
            and capital_transfer_latency_estimate_ms > policy.max_capital_transfer_latency_ms
        )
        if policy.max_capital_transfer_latency_ms > 0.0 and capital_transfer_latency_estimate_ms > policy.max_capital_transfer_latency_ms:
            execution_reasons.append(
                f"capital_transfer_latency_exceeded:{capital_transfer_latency_estimate_ms:.2f}/{policy.max_capital_transfer_latency_ms:.2f}"
            )
        if policy.min_resolved_markets_for_live > 0 and not resolved_markets_for_live:
            execution_reasons.append(
                f"resolved_markets_below_minimum:{resolved_markets_count}/{policy.min_resolved_markets_for_live}"
            )
        manual_review_category_match = _manual_review_category_match(manual_review_categories, manual_review_trigger_categories)
        if manual_review_category_match:
            execution_reasons.append(f"manual_review_category:{manual_review_category_match}")
        request_metadata = {
            **dict(request.metadata or {}),
            **_live_threshold_metadata(request),
        }
        request.metadata = request_metadata
        execution_request_metadata = {
            **request_metadata,
            **approval_gate,
            **capital_control_state.metadata,
            "auth_principal": auth.principal,
            "auth_scopes": list(auth.scopes),
            "auth_authorized": bool(auth.authorized),
            "auth_compliance_approved": bool(auth.compliance_approved),
            "venue_order_path": execution_plan.venue_order_path,
            "venue_order_cancel_path": execution_plan.venue_order_cancel_path,
            "min_free_cash_buffer_pct": policy.min_free_cash_buffer_pct,
            "per_venue_balance_cap_usd": policy.per_venue_balance_cap_usd,
            "max_market_exposure_usd": policy.max_market_exposure_usd,
            "max_open_positions": policy.max_open_positions,
            "max_daily_loss_usd": policy.max_daily_loss_usd,
            "market_id": request.market.market_id,
            "venue": request.market.venue.value,
            "execution_backend_mode": execution_plan.backend_mode,
            "venue_health_live_allowed": venue_health_live_allowed,
            "venue_health_live_reason": venue_health_live_reason,
            "resolved_markets_count": resolved_markets_count,
            "min_resolved_markets_for_live": policy.min_resolved_markets_for_live,
            "resolved_markets_for_live": resolved_markets_for_live,
            "manual_review_categories": manual_review_categories,
            "manual_review_trigger_categories": manual_review_trigger_categories,
            "manual_review_category_match": manual_review_category_match,
            "capital_transfer_latency_estimate_ms": capital_transfer_latency_estimate_ms,
            "capital_transfer_latency_ready": capital_transfer_latency_ready,
            "max_capital_transfer_latency_ms": policy.max_capital_transfer_latency_ms,
        }
        execution_reasons.extend([f"execution_adapter={execution_capability.adapter_name}"])
        if execution_plan.blocked_reasons:
            no_trade_reasons.extend(execution_plan.blocked_reasons)
        venue_allowed, venue_reason = _venue_allowed(request.market, policy)
        if not venue_allowed:
            no_trade_reasons.append(venue_reason or "venue_blocked")
        if policy.kill_switch_enabled:
            no_trade_reasons.append("kill_switch_enabled")
        if request.market.market_id in policy.blocked_market_ids:
            no_trade_reasons.append(f"market_blocked:{request.market.market_id}")
        if request.market.venue_type not in {VenueType.execution, VenueType.execution_equivalent}:
            no_trade_reasons.append(f"non_execution_venue_type:{request.market.venue_type.value}")
        auth_required = _authorization_required(policy, dry_run=dry_run)
        compliance_required = _compliance_required(policy, dry_run=dry_run)
        auth_passed = (
            auth_passed_override
            if auth_passed_override is not None
            else _auth_passed(auth, policy, dry_run=dry_run)
        )
        compliance_passed = (
            compliance_passed_override
            if compliance_passed_override is not None
            else _compliance_passed(auth, policy, dry_run=dry_run)
        )
        execution_request_metadata = {
            **execution_request_metadata,
            "auth_authorized": bool(auth_passed),
            "auth_compliance_approved": bool(compliance_passed),
            "auth_authorized_raw": bool(auth.authorized),
            "auth_compliance_approved_raw": bool(auth.compliance_approved),
            "auth_passed_effective": bool(auth_passed),
            "compliance_passed_effective": bool(compliance_passed),
            "auth_passed_override_present": auth_passed_override is not None,
            "compliance_passed_override_present": compliance_passed_override is not None,
        }
        live_allowed = (
            policy.allow_live_execution
            and not dry_run
            and execution_plan.allowed
            and execution_plan.live_execution_supported
            and venue_health_live_allowed
            and capital_transfer_latency_ready
            and resolved_markets_for_live
            and not manual_review_category_match
            and (not approval_gate["human_approval_required_before_live"] or approval_gate["human_approval_passed"])
        )
        readiness = request.execution_readiness or _build_execution_readiness(
            request=request,
            requested_stake=requested_stake,
            execution_plan=execution_plan,
            auth=auth,
            compliance_required=compliance_required,
            compliance_passed=compliance_passed,
            ledger_before=ledger_before,
            venue_allowed=venue_allowed,
            venue_reason=venue_reason,
            no_trade_reasons=list(no_trade_reasons),
            live_allowed=live_allowed,
            shadow_allowed=not bool(no_trade_reasons) and not bool(manual_review_category_match),
            human_approval_required=bool(approval_gate["human_approval_required_before_live"]),
            human_approval_passed=bool(approval_gate["human_approval_passed"]),
        )
        projection = request.execution_projection or self.projection_runtime.project(
            run_id=request.run_id,
            market=request.market,
            requested_mode=requested_mode,
            readiness=readiness,
            execution_plan=execution_plan,
            ledger_before=ledger_before,
            request_metadata=execution_request_metadata,
            reconciliation_drift_usd=request.reconciliation_drift_usd,
            venue_health=request.venue_health,
            kill_switch_triggered=policy.kill_switch_enabled,
        )
        runtime_guard = dict((projection.metadata or {}).get("runtime_guard") or {})
        action_time_guard = _action_time_guard(
            request=request,
            projection=projection,
            resolution_guard=request.resolution_guard,
            executable_edge=request.executable_edge,
        )
        request.metadata = {**request_metadata, "action_time_guard": action_time_guard}
        execution_request_metadata = {**execution_request_metadata, "action_time_guard": action_time_guard}
        projection.metadata = {
            **dict(projection.metadata or {}),
            "action_time_guard": action_time_guard,
        }
        no_trade_reasons.extend([reason for reason in runtime_guard.get("blocked_reasons", []) if reason not in no_trade_reasons])
        execution_reasons.extend([reason for reason in runtime_guard.get("degraded_reasons", []) if reason not in execution_reasons])
        no_trade_reasons.extend([reason for reason in action_time_guard.get("blocked_reasons", []) if reason not in no_trade_reasons])
        execution_reasons.extend([reason for reason in action_time_guard.get("warning_reasons", []) if reason not in execution_reasons])
        live_transport_bound = bool(getattr(execution_adapter, "order_submitter", None))
        live_transport_callable = callable(getattr(execution_adapter, "place_order", None))
        live_route_allowed = (
            not dry_run
            and live_allowed
            and projection.projected_mode == ExecutionProjectionOutcome.live
            and projection.projection_verdict == ExecutionProjectionVerdict.ready
        )
        live_submission_metadata = _initial_live_submission_runtime_metadata(
            requested_mode=requested_mode,
            dry_run=dry_run,
            live_route_allowed=live_route_allowed,
            live_transport_bound=live_transport_bound,
            live_transport_callable=live_transport_callable,
        )
        request.metadata = {
            **dict(request.metadata or {}),
            **live_submission_metadata,
        }
        execution_request_metadata = {
            **execution_request_metadata,
            **live_submission_metadata,
        }
        if projection.projection_verdict == ExecutionProjectionVerdict.blocked:
            no_trade_reasons.extend(projection.blocking_reasons)
        elif projection.projection_verdict == ExecutionProjectionVerdict.degraded:
            execution_reasons.extend(projection.downgrade_reasons)
        if projection.projected_mode == ExecutionProjectionOutcome.blocked:
            market_execution = _cancelled_market_execution(
                request=request,
                ledger_before=ledger_before,
                execution_capability=execution_capability,
                execution_plan=execution_plan,
                execution_projection=projection,
                reason="; ".join(_dedupe(no_trade_reasons or projection.blocking_reasons or ["projection_blocked"])),
            )
            market_execution.runtime_guard = runtime_guard
            venue_order_lifecycle = _build_venue_order_lifecycle(
                request=request,
                market_execution=market_execution,
                execution_plan=execution_plan,
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            record = LiveExecutionRecord(
                run_id=request.run_id,
                market_id=request.market.market_id,
                venue=request.market.venue,
                mode=LiveExecutionMode.dry_run if dry_run else LiveExecutionMode.live,
                status=LiveExecutionStatus.blocked,
                dry_run=dry_run,
                kill_switch_triggered=policy.kill_switch_enabled,
                loss_cap_triggered=loss_cap_triggered,
                live_allowed=live_allowed,
                requested_mode=requested_mode.value,
                projected_mode=projection.projected_mode.value,
                projection_verdict=projection.projection_verdict.value,
                auth_required=auth_required,
                auth_passed=auth_passed,
                compliance_required=compliance_required,
                compliance_passed=compliance_passed,
                jurisdiction_required=execution_plan.jurisdiction_required,
                jurisdiction_passed=execution_plan.jurisdiction_passed,
                account_type_required=execution_plan.account_type_required,
                account_type_passed=execution_plan.account_type_passed,
                automation_required=execution_plan.automation_required,
                automation_passed=execution_plan.automation_passed,
                rate_limit_required=execution_plan.rate_limit_required,
                rate_limit_passed=execution_plan.rate_limit_passed,
                tos_required=execution_plan.tos_required,
                tos_passed=execution_plan.tos_passed,
                venue_allowed=venue_allowed,
                blocked_reason="; ".join(_dedupe(no_trade_reasons)),
                loss_cap_reason=loss_cap_reason,
                requested_stake=requested_stake,
                executed_stake=0.0,
                recommendation_id=request.recommendation.recommendation_id,
                forecast_id=request.recommendation.forecast_id,
                risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                no_trade_reasons=_dedupe(no_trade_reasons),
                execution_reasons=_dedupe(execution_reasons),
                execution_adapter=execution_capability.adapter_name,
                execution_capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                execution_projection=projection,
                runtime_guard=runtime_guard,
                action_time_guard=action_time_guard,
                market_execution=market_execution,
                venue_order_id=venue_order_lifecycle.venue_order_id,
                venue_order_status=venue_order_lifecycle.venue_order_status,
                venue_order_source=venue_order_lifecycle.venue_order_source,
                venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason,
                metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
            _attach_venue_order_context(record, market_execution, venue_order_lifecycle)
            return self._persist_if_needed(record, persist=persist, store=store, ledger_store=ledger_store, paper_trade_store=paper_trade_store)

        if request.recommendation.action != DecisionAction.bet:
            no_trade_reasons.append(f"recommendation_action:{request.recommendation.action.value}")
        if request.recommendation.side not in {TradeSide.yes, TradeSide.no}:
            no_trade_reasons.append("missing_executable_side")
        if request.recommendation.confidence < policy.min_confidence:
            no_trade_reasons.append(f"confidence_below_minimum:{request.recommendation.confidence:.2f}")
        if (request.recommendation.edge_bps or 0.0) < policy.min_edge_bps:
            no_trade_reasons.append(f"edge_below_minimum:{request.recommendation.edge_bps or 0.0:.2f}")

        if request.risk_report is not None and not request.risk_report.should_trade:
            no_trade_reasons.extend([f"risk_block:{reason}" for reason in request.risk_report.no_trade_reasons or ["risk_report_denied"]])

        if not auth_passed:
            no_trade_reasons.append("authorization_failed")
        if not compliance_passed:
            no_trade_reasons.append("compliance_failed")
        if not dry_run and not policy.allow_live_execution:
            no_trade_reasons.append("live_execution_disabled")

        if ledger_before.equity < policy.min_ledger_equity:
            no_trade_reasons.append(f"ledger_equity_below_minimum:{ledger_before.equity:.2f}")

        if request.requested_stake is None and request.metadata.get("requested_stake") is not None:
            try:
                requested_stake = max(0.0, float(request.metadata["requested_stake"]))
                explicit_request = True
            except (TypeError, ValueError):
                requested_stake = requested_stake

        stake_limit = _stake_limit(policy, ledger_before, request, capital_control_state=capital_control_state)
        if explicit_request and requested_stake > stake_limit + 1e-9:
            no_trade_reasons.append(f"stake_above_maximum:{requested_stake:.2f}/{stake_limit:.2f}")
        elif requested_stake > stake_limit:
            requested_stake = stake_limit

        if request.risk_report is not None and request.risk_report.max_allowed_notional > 0:
            requested_stake = min(requested_stake, request.risk_report.max_allowed_notional)

        if request.risk_report is not None and request.risk_report.cap_reasons:
            execution_reasons.extend(request.risk_report.cap_reasons)
        if request.metadata.get("allocation_id"):
            execution_reasons.append(f"allocation_id={request.metadata['allocation_id']}")

        readiness = _build_execution_readiness(
            request=request,
            requested_stake=requested_stake,
            execution_plan=execution_plan,
            auth=auth,
            compliance_required=compliance_required,
            compliance_passed=compliance_passed,
            ledger_before=ledger_before,
            venue_allowed=venue_allowed,
            venue_reason=venue_reason,
            no_trade_reasons=no_trade_reasons,
            live_allowed=live_allowed,
            shadow_allowed=not bool(no_trade_reasons),
            human_approval_required=bool(approval_gate["required"]),
            human_approval_passed=bool(approval_gate["passed"]),
        )
        projection = request.execution_projection or self.projection_runtime.project(
            run_id=request.run_id,
            market=request.market,
            requested_mode=requested_mode,
            readiness=readiness,
            execution_plan=execution_plan,
            ledger_before=ledger_before,
            request_metadata=execution_request_metadata,
            reconciliation_drift_usd=request.reconciliation_drift_usd,
            venue_health=request.venue_health,
            kill_switch_triggered=policy.kill_switch_enabled,
        )
        runtime_guard = dict((projection.metadata or {}).get("runtime_guard") or {})
        no_trade_reasons.extend([reason for reason in runtime_guard.get("blocked_reasons", []) if reason not in no_trade_reasons])
        execution_reasons.extend([reason for reason in runtime_guard.get("degraded_reasons", []) if reason not in execution_reasons])
        if projection.projection_verdict == ExecutionProjectionVerdict.blocked:
            no_trade_reasons.extend(projection.blocking_reasons)
            market_execution = _cancelled_market_execution(
                request=request,
                ledger_before=ledger_before,
                execution_capability=execution_capability,
                execution_plan=execution_plan,
                execution_projection=projection,
                reason="; ".join(_dedupe(no_trade_reasons or projection.blocking_reasons or ["projection_blocked"])),
            )
            market_execution.runtime_guard = runtime_guard
            venue_order_lifecycle = _build_venue_order_lifecycle(
                request=request,
                market_execution=market_execution,
                execution_plan=execution_plan,
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            record = LiveExecutionRecord(
                run_id=request.run_id,
                market_id=request.market.market_id,
                venue=request.market.venue,
                mode=LiveExecutionMode.dry_run if dry_run else LiveExecutionMode.live,
                status=LiveExecutionStatus.blocked,
                dry_run=dry_run,
                kill_switch_triggered=policy.kill_switch_enabled,
                loss_cap_triggered=loss_cap_triggered,
                live_allowed=live_allowed,
                requested_mode=requested_mode.value,
                projected_mode=getattr(projection.projected_mode, "value", str(projection.projected_mode)),
                projection_verdict=projection.projection_verdict.value,
                auth_required=auth_required,
                auth_passed=auth_passed,
                compliance_required=compliance_required,
                compliance_passed=compliance_passed,
                jurisdiction_required=execution_plan.jurisdiction_required,
                jurisdiction_passed=execution_plan.jurisdiction_passed,
                account_type_required=execution_plan.account_type_required,
                account_type_passed=execution_plan.account_type_passed,
                automation_required=execution_plan.automation_required,
                automation_passed=execution_plan.automation_passed,
                rate_limit_required=execution_plan.rate_limit_required,
                rate_limit_passed=execution_plan.rate_limit_passed,
                tos_required=execution_plan.tos_required,
                tos_passed=execution_plan.tos_passed,
                venue_allowed=venue_allowed,
                blocked_reason="; ".join(_dedupe(no_trade_reasons)),
                loss_cap_reason=loss_cap_reason,
                requested_stake=requested_stake,
                executed_stake=0.0,
                recommendation_id=request.recommendation.recommendation_id,
                forecast_id=request.recommendation.forecast_id,
                risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                no_trade_reasons=_dedupe(no_trade_reasons),
                execution_reasons=_dedupe(execution_reasons),
                execution_adapter=execution_capability.adapter_name,
                execution_capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                execution_projection=projection,
                runtime_guard=runtime_guard,
                action_time_guard=action_time_guard,
                market_execution=market_execution,
                venue_order_id=venue_order_lifecycle.venue_order_id,
                venue_order_status=venue_order_lifecycle.venue_order_status,
                venue_order_source=venue_order_lifecycle.venue_order_source,
                venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason,
                metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
            _attach_venue_order_context(record, market_execution, venue_order_lifecycle)
            return self._persist_if_needed(record, persist=persist, store=store, ledger_store=ledger_store, paper_trade_store=paper_trade_store)

        if no_trade_reasons:
            venue_order_lifecycle = build_venue_order_lifecycle(
                order_id=f"cancel_{request.run_id}_{request.market.market_id}",
                execution_id=f"cancel_{request.run_id}_{request.market.market_id}",
                request_metadata=request.metadata,
                status=MarketExecutionStatus.cancelled.value,
                cancelled_reason="; ".join(_dedupe(no_trade_reasons)),
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            record = LiveExecutionRecord(
                run_id=request.run_id,
                market_id=request.market.market_id,
                venue=request.market.venue,
                mode=LiveExecutionMode.dry_run if dry_run else LiveExecutionMode.live,
                status=LiveExecutionStatus.blocked,
                dry_run=dry_run,
                kill_switch_triggered=policy.kill_switch_enabled,
                loss_cap_triggered=loss_cap_triggered,
                live_allowed=live_allowed,
                requested_mode=requested_mode.value,
                projected_mode=projection.projected_mode.value,
                projection_verdict=projection.projection_verdict.value,
                auth_required=auth_required,
                auth_passed=auth_passed,
                compliance_required=compliance_required,
                compliance_passed=compliance_passed,
                jurisdiction_required=execution_plan.jurisdiction_required,
                jurisdiction_passed=execution_plan.jurisdiction_passed,
                account_type_required=execution_plan.account_type_required,
                account_type_passed=execution_plan.account_type_passed,
                automation_required=execution_plan.automation_required,
                automation_passed=execution_plan.automation_passed,
                rate_limit_required=execution_plan.rate_limit_required,
                rate_limit_passed=execution_plan.rate_limit_passed,
                tos_required=execution_plan.tos_required,
                tos_passed=execution_plan.tos_passed,
                venue_allowed=venue_allowed,
                blocked_reason="; ".join(no_trade_reasons),
                loss_cap_reason=loss_cap_reason,
                requested_stake=requested_stake,
                executed_stake=0.0,
                recommendation_id=request.recommendation.recommendation_id,
                forecast_id=request.recommendation.forecast_id,
                risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                no_trade_reasons=_dedupe(no_trade_reasons),
                execution_reasons=_dedupe(execution_reasons),
                execution_adapter=execution_capability.adapter_name,
                execution_capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                execution_projection=projection,
                runtime_guard=runtime_guard,
                action_time_guard=action_time_guard,
                market_execution=_cancelled_market_execution(
                    request=request,
                    ledger_before=ledger_before,
                    execution_capability=execution_capability,
                    execution_plan=execution_plan,
                    execution_projection=projection,
                    reason="; ".join(_dedupe(no_trade_reasons)),
                ),
                venue_order_id=venue_order_lifecycle.venue_order_id,
                venue_order_status=venue_order_lifecycle.venue_order_status,
                venue_order_source=venue_order_lifecycle.venue_order_source,
                venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason,
                metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
            _attach_venue_order_context(
                record,
                record.market_execution,
                _build_venue_order_lifecycle(
                    request=request,
                    market_execution=record.market_execution,
                    execution_plan=execution_plan,
                    live_execution_supported=bool(execution_capability.live_execution_supported),
                ),
            )
            return self._persist_if_needed(record, persist=persist, store=store, ledger_store=ledger_store, paper_trade_store=paper_trade_store)

        if requested_stake <= 0.0:
            no_trade_reasons.append("stake_below_minimum:0.00")
            venue_order_lifecycle = build_venue_order_lifecycle(
                order_id=f"cancel_{request.run_id}_{request.market.market_id}",
                execution_id=f"cancel_{request.run_id}_{request.market.market_id}",
                request_metadata=request.metadata,
                status=MarketExecutionStatus.cancelled.value,
                cancelled_reason="; ".join(_dedupe(no_trade_reasons)),
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            record = LiveExecutionRecord(
                run_id=request.run_id,
                market_id=request.market.market_id,
                venue=request.market.venue,
                mode=LiveExecutionMode.dry_run if dry_run else LiveExecutionMode.live,
                status=LiveExecutionStatus.blocked,
                dry_run=dry_run,
                kill_switch_triggered=policy.kill_switch_enabled,
                loss_cap_triggered=loss_cap_triggered,
                live_allowed=live_allowed,
                requested_mode=requested_mode.value,
                projected_mode=projection.projected_mode.value,
                projection_verdict=projection.projection_verdict.value,
                auth_required=auth_required,
                auth_passed=auth_passed,
                compliance_required=compliance_required,
                compliance_passed=compliance_passed,
                jurisdiction_required=execution_plan.jurisdiction_required,
                jurisdiction_passed=execution_plan.jurisdiction_passed,
                account_type_required=execution_plan.account_type_required,
                account_type_passed=execution_plan.account_type_passed,
                automation_required=execution_plan.automation_required,
                automation_passed=execution_plan.automation_passed,
                rate_limit_required=execution_plan.rate_limit_required,
                rate_limit_passed=execution_plan.rate_limit_passed,
                tos_required=execution_plan.tos_required,
                tos_passed=execution_plan.tos_passed,
                venue_allowed=venue_allowed,
                blocked_reason="; ".join(_dedupe(no_trade_reasons)),
                loss_cap_reason=loss_cap_reason,
                requested_stake=requested_stake,
                executed_stake=0.0,
                recommendation_id=request.recommendation.recommendation_id,
                forecast_id=request.recommendation.forecast_id,
                risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                no_trade_reasons=_dedupe(no_trade_reasons),
                execution_reasons=_dedupe(execution_reasons),
                execution_adapter=execution_capability.adapter_name,
                execution_capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                execution_projection=projection,
                market_execution=_cancelled_market_execution(
                    request=request,
                    ledger_before=ledger_before,
                    execution_capability=execution_capability,
                    execution_plan=execution_plan,
                    execution_projection=projection,
                    reason="; ".join(_dedupe(no_trade_reasons)),
                ),
                venue_order_id=venue_order_lifecycle.venue_order_id,
                venue_order_status=venue_order_lifecycle.venue_order_status,
                venue_order_source=venue_order_lifecycle.venue_order_source,
                venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason,
                metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
            _attach_venue_order_context(record, record.market_execution, venue_order_lifecycle)
            return self._persist_if_needed(record, persist=persist, store=store, ledger_store=ledger_store, paper_trade_store=paper_trade_store)

        paper_trade = self.paper_simulator.simulate(
            request.snapshot,
            position_side=_position_side(request.recommendation.side),
            execution_side=TradeSide.buy,
            stake=requested_stake,
            run_id=request.run_id,
            market_id=request.market.market_id,
            venue=request.market.venue,
            limit_price=request.recommendation.price_reference,
            action=request.recommendation.action,
            metadata={
                "source": "live_execution",
                "dry_run": dry_run,
                "auth_principal": auth.principal,
                "allow_live_execution": policy.allow_live_execution,
            },
        )
        venue_order_lifecycle: VenueOrderLifecycle | None = None
        live_venue_trace: Any | None = None
        if dry_run or not live_route_allowed:
            if not dry_run and projection.projected_mode != ExecutionProjectionOutcome.live:
                execution_reasons.append(f"projection_downgraded_to_{projection.projected_mode.value}")
            market_execution = MarketExecutionRecord.from_paper_trade(
                paper_trade=paper_trade,
                order=MarketExecutionOrder(
                    run_id=request.run_id,
                    market_id=request.market.market_id,
                    venue=request.market.venue,
                    position_side=_position_side(request.recommendation.side),
                    execution_side=TradeSide.buy,
                    order_type=MarketExecutionOrderType.limit
                    if request.recommendation.price_reference is not None
                    else MarketExecutionOrderType.market,
                    requested_quantity=paper_trade.requested_quantity,
                    requested_notional=requested_stake,
                    limit_price=request.recommendation.price_reference,
                    metadata={
                        "source": "live_execution",
                        "dry_run": dry_run,
                        "allow_live_execution": policy.allow_live_execution,
                    },
                ),
                mode=MarketExecutionMode.bounded_dry_run,
                capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                trade_intent_ref=request.metadata.get("trade_intent_id"),
                execution_projection_ref=projection.projection_id,
                metadata={
                    **request.metadata,
                    "request_type": "live_execution",
                    "persisted": persist,
                },
            )
            market_execution.runtime_guard = runtime_guard
            venue_order_lifecycle = _build_venue_order_lifecycle(
                request=request,
                market_execution=market_execution,
                execution_plan=execution_plan,
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            status = LiveExecutionStatus.dry_run
            execution_reasons.append("dry_run_mode")
        else:
            if live_transport_bound and live_transport_callable:
                live_submission_metadata = {
                    **dict(execution_request_metadata),
                    "source": "live_execution",
                    "dry_run": False,
                    "allow_live_execution": True,
                    "live_transport_bound": True,
                    "live_transport_attempted": True,
                }
                try:
                    execution_request_metadata = _update_live_submission_runtime_metadata(
                        execution_request_metadata,
                        attempted_live=True,
                        live_submission_phase="attempted_live",
                    )
                    request.metadata = _update_live_submission_runtime_metadata(
                        request.metadata,
                        attempted_live=True,
                        live_submission_phase="attempted_live",
                    )
                    live_venue_trace = execution_adapter.place_order(
                        market=request.market,
                        run_id=request.run_id,
                        position_side=_position_side(request.recommendation.side),
                        execution_side=TradeSide.buy,
                        requested_quantity=paper_trade.requested_quantity,
                        requested_notional=requested_stake,
                        limit_price=request.recommendation.price_reference,
                        dry_run=False,
                        allow_live_execution=True,
                        authorized=auth_passed,
                        compliance_approved=compliance_passed,
                        required_scope=policy.required_scope,
                        scopes=list(auth.scopes),
                        metadata=live_submission_metadata,
                    )
                    execution_reasons.append("venue_live_submission_attempted")
                    if getattr(live_venue_trace, "live_submission_performed", False):
                        execution_reasons.append("venue_live_submission_performed")
                    else:
                        execution_reasons.append("venue_live_submission_not_performed")
                    execution_request_metadata = _update_live_submission_runtime_metadata(
                        execution_request_metadata,
                        attempted_live=bool(getattr(live_venue_trace, "live_submission_attempted", True)),
                        live_submission_performed=bool(getattr(live_venue_trace, "live_submission_performed", False)),
                        live_submission_phase=(
                            "performed_live"
                            if bool(getattr(live_venue_trace, "live_submission_performed", False))
                            else "attempted_live_not_performed"
                        ),
                    )
                    request.metadata = _update_live_submission_runtime_metadata(
                        request.metadata,
                        attempted_live=bool(getattr(live_venue_trace, "live_submission_attempted", True)),
                        live_submission_performed=bool(getattr(live_venue_trace, "live_submission_performed", False)),
                        live_submission_phase=(
                            "performed_live"
                            if bool(getattr(live_venue_trace, "live_submission_performed", False))
                            else "attempted_live_not_performed"
                        ),
                    )
                    trace_lifecycle = dict(getattr(live_venue_trace, "venue_order_lifecycle", {}) or {})
                    if trace_lifecycle:
                        trace_metadata = {
                            key: value
                            for key, value in trace_lifecycle.items()
                            if value is not None
                        }
                        request.metadata = {**dict(request.metadata or {}), **trace_metadata, "venue_order_lifecycle": trace_lifecycle}
                        execution_request_metadata = {
                            **execution_request_metadata,
                            **trace_metadata,
                            "venue_order_lifecycle": trace_lifecycle,
                            "venue_live_submission_bound": True,
                            "venue_live_submission_attempted": bool(getattr(live_venue_trace, "live_submission_attempted", False)),
                            "venue_live_submission_performed": bool(getattr(live_venue_trace, "live_submission_performed", False)),
                        }
                        if getattr(live_venue_trace, "submitted_payload", None) is not None:
                            execution_request_metadata["venue_live_submitted_payload"] = getattr(live_venue_trace, "submitted_payload")
                    else:
                        execution_request_metadata = {
                            **execution_request_metadata,
                            "venue_live_submission_bound": True,
                            "venue_live_submission_attempted": bool(getattr(live_venue_trace, "live_submission_attempted", False)),
                            "venue_live_submission_performed": bool(getattr(live_venue_trace, "live_submission_performed", False)),
                        }
                    if getattr(live_venue_trace, "blocked_reasons", None):
                        execution_reasons.extend(
                            [reason for reason in getattr(live_venue_trace, "blocked_reasons", []) if reason not in execution_reasons]
                        )
                    if getattr(live_venue_trace, "notes", None):
                        execution_reasons.extend([reason for reason in getattr(live_venue_trace, "notes", []) if reason not in execution_reasons])
                except Exception as exc:  # pragma: no cover - defensive path
                    execution_reasons.append(f"venue_live_submission_failed:{type(exc).__name__}")
                    execution_request_metadata = _update_live_submission_runtime_metadata(
                        execution_request_metadata,
                        attempted_live=True,
                        live_submission_performed=False,
                        live_submission_phase="attempted_live_failed",
                        live_submission_failed=type(exc).__name__,
                    )
                    request.metadata = _update_live_submission_runtime_metadata(
                        request.metadata,
                        attempted_live=True,
                        live_submission_performed=False,
                        live_submission_phase="attempted_live_failed",
                        live_submission_failed=type(exc).__name__,
                    )
            elif live_transport_bound:
                execution_reasons.append("venue_live_transport_unavailable")
                execution_request_metadata = _update_live_submission_runtime_metadata(
                    execution_request_metadata,
                    attempted_live=False,
                    live_submission_performed=False,
                    live_submission_phase="preflight_only",
                )
                request.metadata = _update_live_submission_runtime_metadata(
                    request.metadata,
                    attempted_live=False,
                    live_submission_performed=False,
                    live_submission_phase="preflight_only",
                )
            ledger_change = ledger_engine.apply_paper_trade(
                paper_trade,
                mark_price=request.snapshot.market_implied_probability or request.snapshot.midpoint_yes or paper_trade.reference_price,
            )
            ledger_after = ledger_engine.current_snapshot()
            status = _status_from_paper_trade(paper_trade)
            execution_reasons.append("live_execution_enabled")
            market_execution = MarketExecutionRecord.from_paper_trade(
                paper_trade=paper_trade,
                order=MarketExecutionOrder(
                    run_id=request.run_id,
                    market_id=request.market.market_id,
                    venue=request.market.venue,
                    position_side=_position_side(request.recommendation.side),
                    execution_side=TradeSide.buy,
                    order_type=MarketExecutionOrderType.limit
                    if request.recommendation.price_reference is not None
                    else MarketExecutionOrderType.market,
                    requested_quantity=paper_trade.requested_quantity,
                    requested_notional=requested_stake,
                    limit_price=request.recommendation.price_reference,
                    metadata={
                        "source": "live_execution",
                        "dry_run": dry_run,
                        "allow_live_execution": policy.allow_live_execution,
                    },
                ),
                mode=MarketExecutionMode.bounded_live,
                capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                trade_intent_ref=request.metadata.get("trade_intent_id"),
                execution_projection_ref=projection.projection_id,
                metadata={
                    **request.metadata,
                    "request_type": "live_execution",
                    "persisted": persist,
                },
            )
            market_execution.runtime_guard = runtime_guard
            venue_order_lifecycle = _build_venue_order_lifecycle(
                request=request,
                market_execution=market_execution,
                execution_plan=execution_plan,
                live_execution_supported=bool(execution_capability.live_execution_supported),
            )
            record = LiveExecutionRecord(
                run_id=request.run_id,
                market_id=request.market.market_id,
                venue=request.market.venue,
                mode=LiveExecutionMode.live,
                status=status,
                dry_run=False,
                kill_switch_triggered=policy.kill_switch_enabled,
                loss_cap_triggered=loss_cap_triggered,
                live_allowed=live_allowed,
                requested_mode=requested_mode.value,
                projected_mode=projection.projected_mode.value,
                projection_verdict=projection.projection_verdict.value,
                auth_required=auth_required,
                auth_passed=auth_passed,
                compliance_required=compliance_required,
                compliance_passed=compliance_passed,
                jurisdiction_required=execution_plan.jurisdiction_required,
                jurisdiction_passed=execution_plan.jurisdiction_passed,
                account_type_required=execution_plan.account_type_required,
                account_type_passed=execution_plan.account_type_passed,
                automation_required=execution_plan.automation_required,
                automation_passed=execution_plan.automation_passed,
                rate_limit_required=execution_plan.rate_limit_required,
                rate_limit_passed=execution_plan.rate_limit_passed,
                tos_required=execution_plan.tos_required,
                tos_passed=execution_plan.tos_passed,
                venue_allowed=venue_allowed,
                blocked_reason=None,
                loss_cap_reason=loss_cap_reason,
                requested_stake=requested_stake,
                executed_stake=paper_trade.stake,
                recommendation_id=request.recommendation.recommendation_id,
                forecast_id=request.recommendation.forecast_id,
                risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
                allocation_id=request.metadata.get("allocation_id"),
                ledger_before=ledger_before,
                ledger_after=ledger_after,
                ledger_change=ledger_change,
                paper_trade=paper_trade,
                market_execution=market_execution,
                no_trade_reasons=[],
                execution_reasons=_dedupe(execution_reasons + [f"paper_trade_status={paper_trade.status.value}"]),
                execution_adapter=execution_capability.adapter_name,
                execution_capability=execution_capability.model_dump(mode="json"),
                execution_plan=execution_plan.model_dump(mode="json"),
                execution_projection=projection,
                runtime_guard=runtime_guard,
                action_time_guard=action_time_guard,
                venue_order_id=venue_order_lifecycle.venue_order_id if venue_order_lifecycle is not None else None,
                venue_order_status=venue_order_lifecycle.venue_order_status if venue_order_lifecycle is not None else "unavailable",
                venue_order_source=venue_order_lifecycle.venue_order_source if venue_order_lifecycle is not None else "unavailable",
                venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason if venue_order_lifecycle is not None else None,
                metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
            if venue_order_lifecycle is not None:
                _attach_venue_order_context(record, market_execution, venue_order_lifecycle)
            return self._persist_if_needed(
                record,
                persist=persist,
                store=store,
                ledger_store=ledger_store,
                paper_trade_store=paper_trade_store,
            )

        record = LiveExecutionRecord(
            run_id=request.run_id,
            market_id=request.market.market_id,
            venue=request.market.venue,
            mode=LiveExecutionMode.dry_run,
            status=status,
            dry_run=True,
            kill_switch_triggered=policy.kill_switch_enabled,
            loss_cap_triggered=loss_cap_triggered,
            live_allowed=False,
            requested_mode=requested_mode.value,
            projected_mode=projection.projected_mode.value,
            projection_verdict=projection.projection_verdict.value,
            auth_required=auth_required,
            auth_passed=auth_passed,
            compliance_required=compliance_required,
            compliance_passed=compliance_passed,
            jurisdiction_required=execution_plan.jurisdiction_required,
            jurisdiction_passed=execution_plan.jurisdiction_passed,
            account_type_required=execution_plan.account_type_required,
            account_type_passed=execution_plan.account_type_passed,
            automation_required=execution_plan.automation_required,
            automation_passed=execution_plan.automation_passed,
            rate_limit_required=execution_plan.rate_limit_required,
            rate_limit_passed=execution_plan.rate_limit_passed,
            tos_required=execution_plan.tos_required,
            tos_passed=execution_plan.tos_passed,
            venue_allowed=venue_allowed,
            blocked_reason=None,
            loss_cap_reason=loss_cap_reason,
            requested_stake=requested_stake,
            executed_stake=paper_trade.stake,
            recommendation_id=request.recommendation.recommendation_id,
            forecast_id=request.recommendation.forecast_id,
            risk_report_id=request.risk_report.risk_id if request.risk_report is not None else None,
            allocation_id=request.metadata.get("allocation_id"),
            ledger_before=ledger_before,
            ledger_after=ledger_after,
            paper_trade=paper_trade,
            market_execution=market_execution,
            no_trade_reasons=[],
            execution_reasons=_dedupe(execution_reasons + [f"paper_trade_status={paper_trade.status.value}"]),
            execution_adapter=execution_capability.adapter_name,
            execution_capability=execution_capability.model_dump(mode="json"),
            execution_plan=execution_plan.model_dump(mode="json"),
            execution_projection=projection,
            runtime_guard=runtime_guard,
            action_time_guard=action_time_guard,
            venue_order_id=venue_order_lifecycle.venue_order_id if venue_order_lifecycle is not None else None,
            venue_order_status=venue_order_lifecycle.venue_order_status if venue_order_lifecycle is not None else "unavailable",
            venue_order_source=venue_order_lifecycle.venue_order_source if venue_order_lifecycle is not None else "unavailable",
            venue_order_cancel_reason=venue_order_lifecycle.venue_order_cancel_reason if venue_order_lifecycle is not None else None,
            metadata=_record_metadata(execution_request_metadata, runtime_guard, persist),
            )
        if venue_order_lifecycle is not None:
            _attach_venue_order_context(record, market_execution, venue_order_lifecycle)
        return self._persist_if_needed(record, persist=persist, store=store, ledger_store=ledger_store, paper_trade_store=paper_trade_store)

    def _persist_if_needed(
        self,
        record: LiveExecutionRecord,
        *,
        persist: bool,
        store: LiveExecutionStore | None,
        ledger_store: CapitalLedgerStore | None,
        paper_trade_store: PaperTradeStore | None,
    ) -> LiveExecutionRecord:
        if not persist:
            return record
        execution_store = store or LiveExecutionStore()
        execution_store.save(record)
        if record.paper_trade is not None:
            (paper_trade_store or PaperTradeStore(execution_store.paths)).save(record.paper_trade)
        if record.ledger_after is not None:
            (ledger_store or CapitalLedgerStore(execution_store.paths)).save_snapshot(record.ledger_after)
        return record


def execute_live_trade(
    request: LiveExecutionRequest,
    *,
    policy: LiveExecutionPolicy | None = None,
    persist: bool | None = None,
    store: LiveExecutionStore | None = None,
    ledger_store: CapitalLedgerStore | None = None,
    paper_trade_store: PaperTradeStore | None = None,
    ) -> LiveExecutionRecord:
    return LiveExecutionEngine(policy=policy).execute(
        request,
        persist=persist,
        store=store,
        ledger_store=ledger_store,
        paper_trade_store=paper_trade_store,
    )


def _human_approval_gate_metadata(
    *,
    request: LiveExecutionRequest,
    auth: ExecutionAuthContext,
    policy: LiveExecutionPolicy,
    dry_run: bool,
    requested_mode: ExecutionProjectionMode | ExecutionProjectionOutcome | str,
) -> dict[str, Any]:
    metadata = {
        **dict(request.metadata or {}),
        **dict(auth.metadata or {}),
        "requested_mode": getattr(requested_mode, "value", str(requested_mode)),
    }
    gate = _human_approval_gate_from_metadata(metadata, requested=requested_mode)
    gate["required"] = bool(policy.require_human_approval_before_live and not dry_run and gate["requested_mode"] == ExecutionProjectionMode.live.value)
    gate["state"] = (
        "not_required"
        if not gate["required"]
        else "approved"
        if gate["passed"]
        else "missing"
    )
    gate["human_approval_required_before_live"] = gate["required"]
    gate["human_approval_passed"] = gate["passed"]
    gate["human_approval_state"] = gate["state"]
    gate["human_approval_actor"] = gate["actor"]
    gate["human_approval_reason"] = gate["reason"]
    gate["policy_required"] = bool(policy.require_human_approval_before_live)
    gate["dry_run"] = dry_run
    gate["requested_mode"] = getattr(requested_mode, "value", str(requested_mode))
    gate["approval_gate"] = {
        "required": gate["required"],
        "passed": gate["passed"],
        "state": gate["state"],
        "actor": gate["actor"],
        "reason": gate["reason"],
        "approved_at": gate["approved_at"],
        "requested_mode": gate["requested_mode"],
        "policy_required": gate["policy_required"],
        "dry_run": gate["dry_run"],
    }
    return gate


def _human_approval_gate_from_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    requested: ExecutionProjectionMode | ExecutionProjectionOutcome | str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    requested_mode = _coerce_projection_mode(requested)
    required = bool(_metadata_bool(payload, "human_approval_required_before_live") and requested_mode == ExecutionProjectionMode.live)
    passed = _metadata_bool(payload, "human_approval_passed") or _metadata_bool(payload, "human_approved")
    actor = _first_non_empty(
        payload.get("human_approval_actor"),
        payload.get("approval_actor"),
        payload.get("approved_by"),
    )
    reason = _first_non_empty(
        payload.get("human_approval_reason"),
        payload.get("approval_reason"),
    )
    approved_at = _first_non_empty(
        payload.get("human_approval_at"),
        payload.get("approved_at"),
    )
    state = "not_required" if not required else "approved" if passed else "missing"
    return {
        "required": required,
        "passed": passed,
        "state": state,
        "actor": actor,
        "reason": reason,
        "approved_at": approved_at,
        "requested_mode": requested_mode.value,
    }


def _metadata_bool(metadata: Mapping[str, Any], key: str) -> bool:
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"1", "true", "yes", "y", "on", "approved", "recorded"}
    return bool(value)


def _metadata_bool_or_none(metadata: Mapping[str, Any] | None, key: str) -> bool | None:
    if metadata is None or key not in metadata:
        return None
    return _metadata_bool(metadata, key)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = " ".join(str(value).strip().split())
        if text:
            return text
    return None


def _normalized_category_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    normalized: list[str] = []
    for item in items:
        text = " ".join(str(item).strip().split()).lower()
        if text:
            normalized.append(text)
    return normalized


def _manual_review_trigger_categories(request: LiveExecutionRequest) -> list[str]:
    categories: list[str] = []
    metadata = dict(request.metadata or {})
    categories.extend(_normalized_category_list(metadata.get("manual_review_category")))
    categories.extend(_normalized_category_list(metadata.get("manual_review_categories")))
    categories.extend(_normalized_category_list(metadata.get("manual_review_reason_categories")))
    if request.execution_readiness is not None:
        readiness_metadata = dict(request.execution_readiness.metadata or {})
        categories.extend(_normalized_category_list(readiness_metadata.get("manual_review_category")))
        categories.extend(_normalized_category_list(readiness_metadata.get("manual_review_categories")))
        categories.extend(_normalized_category_list(readiness_metadata.get("manual_review_reason_categories")))
    if request.risk_report is not None:
        categories.extend(_normalized_category_list(request.risk_report.metadata.get("manual_review_category")))
        categories.extend(_normalized_category_list(request.risk_report.metadata.get("manual_review_categories")))
    return list(dict.fromkeys(item for item in categories if item))


def _manual_review_category_match(configured_categories: list[str], trigger_categories: list[str]) -> str | None:
    configured = {category.strip().lower() for category in configured_categories if category and str(category).strip()}
    triggered = {category.strip().lower() for category in trigger_categories if category and str(category).strip()}
    for category in sorted(configured.intersection(triggered)):
        return category
    return None


def _live_threshold_metadata(request: LiveExecutionRequest) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    request_metadata = dict(request.metadata or {})
    risk_metadata = dict(request.risk_report.metadata or {}) if request.risk_report is not None else {}
    resolution_metadata = dict(request.resolution_guard.metadata or {}) if request.resolution_guard is not None else {}

    def _first_float(*values: Any) -> float | None:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _first_int(*values: Any) -> int | None:
        for value in values:
            if value is None:
                continue
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
        return None

    snapshot = request.snapshot
    metadata["snapshot_staleness_ms"] = snapshot.staleness_ms
    metadata["snapshot_liquidity_usd"] = snapshot.liquidity
    metadata["snapshot_depth_near_touch"] = snapshot.depth_near_touch
    metadata["snapshot_spread_bps"] = snapshot.spread_bps
    metadata["snapshot_edge_after_fees_bps"] = _first_float(
        request_metadata.get("snapshot_edge_after_fees_bps"),
        risk_metadata.get("snapshot_edge_after_fees_bps"),
        risk_metadata.get("edge_after_fees_bps"),
        risk_metadata.get("effective_edge_after_fees_bps"),
        request_metadata.get("edge_after_fees_bps"),
    )

    metadata["snapshot_ttl_ms"] = _first_int(
        request_metadata.get("snapshot_ttl_ms"),
        request_metadata.get("max_snapshot_staleness_ms"),
        risk_metadata.get("snapshot_ttl_ms"),
        risk_metadata.get("max_snapshot_staleness_ms"),
    )
    metadata["min_liquidity_usd"] = _first_float(
        request_metadata.get("min_liquidity_usd"),
        request_metadata.get("min_liquidity"),
        risk_metadata.get("min_liquidity_usd"),
        risk_metadata.get("min_liquidity"),
    )
    metadata["min_depth_near_touch"] = _first_float(
        request_metadata.get("min_depth_near_touch"),
        risk_metadata.get("min_depth_near_touch"),
    )
    metadata["min_edge_after_fees_bps"] = _first_float(
        request_metadata.get("min_edge_after_fees_bps"),
        request_metadata.get("min_edge_bps"),
        risk_metadata.get("min_edge_after_fees_bps"),
        risk_metadata.get("min_edge_bps"),
    )
    metadata["min_resolution_compatibility_score"] = _first_float(
        request_metadata.get("min_resolution_compatibility_score"),
        request_metadata.get("min_policy_completeness_score"),
        request_metadata.get("min_policy_coherence_score"),
        risk_metadata.get("min_resolution_compatibility_score"),
    )
    metadata["min_payout_compatibility_score"] = _first_float(
        request_metadata.get("min_payout_compatibility_score"),
        risk_metadata.get("min_payout_compatibility_score"),
    )
    metadata["min_currency_compatibility_score"] = _first_float(
        request_metadata.get("min_currency_compatibility_score"),
        risk_metadata.get("min_currency_compatibility_score"),
    )

    if request.resolution_guard is not None:
        metadata["resolution_guard_policy_completeness_score"] = request.resolution_guard.policy_completeness_score
        metadata["resolution_guard_policy_coherence_score"] = request.resolution_guard.policy_coherence_score
        metadata["resolution_guard_approved"] = request.resolution_guard.approved
        metadata["resolution_guard_can_forecast"] = request.resolution_guard.can_forecast
        metadata["resolution_guard_manual_review_required"] = request.resolution_guard.manual_review_required
        metadata["resolution_guard_status"] = request.resolution_guard.status.value
        metadata["resolution_guard_official_source"] = request.resolution_guard.official_source
    if resolution_metadata:
        metadata["resolution_compatibility_score"] = _first_float(
            resolution_metadata.get("resolution_compatibility_score"),
            resolution_metadata.get("policy_completeness_score"),
            resolution_metadata.get("resolution_guard_policy_completeness_score"),
        )
        metadata["resolution_coherence_score"] = _first_float(
            resolution_metadata.get("resolution_coherence_score"),
            resolution_metadata.get("policy_coherence_score"),
            resolution_metadata.get("resolution_guard_policy_coherence_score"),
        )
        metadata["payout_compatibility_score"] = _first_float(
            resolution_metadata.get("payout_compatibility_score"),
        )
        metadata["currency_compatibility_score"] = _first_float(
            resolution_metadata.get("currency_compatibility_score"),
        )

    return {key: value for key, value in metadata.items() if value is not None}


def _resolved_markets_count(request: LiveExecutionRequest) -> int:
    metadata_sources: list[Mapping[str, Any]] = [dict(request.metadata or {})]
    if request.execution_readiness is not None:
        metadata_sources.append(dict(request.execution_readiness.metadata or {}))
    if request.risk_report is not None:
        metadata_sources.append(dict(request.risk_report.metadata or {}))
    for metadata in metadata_sources:
        for key in ("resolved_markets_count", "resolved_market_count"):
            if key in metadata:
                try:
                    return max(0, int(metadata[key]))
                except (TypeError, ValueError):
                    continue
        for key in ("resolved_markets", "resolved_market_ids"):
            if key in metadata:
                value = metadata.get(key)
                if isinstance(value, (list, tuple, set)):
                    return len([item for item in value if str(item).strip()])
    return 0


def _record_metadata(request_metadata: Mapping[str, Any] | None, runtime_guard: Mapping[str, Any] | None, persist: bool) -> dict[str, Any]:
    metadata = dict(request_metadata or {})
    metadata["request_type"] = "live_execution"
    metadata["persisted"] = persist
    if runtime_guard is not None:
        incident_runbook = runtime_guard.get("incident_runbook") if isinstance(runtime_guard, Mapping) else None
        if incident_runbook is not None:
            metadata["incident_runbook"] = incident_runbook
    return metadata


def _initial_live_submission_runtime_metadata(
    *,
    requested_mode: ExecutionProjectionMode,
    dry_run: bool,
    live_route_allowed: bool,
    live_transport_bound: bool,
    live_transport_callable: bool,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    requested_live = requested_mode == ExecutionProjectionMode.live
    if dry_run:
        phase = "dry_run"
    elif not requested_live:
        phase = "non_live_request"
    elif not live_route_allowed:
        phase = "preflight_blocked"
    elif live_transport_bound and live_transport_callable:
        phase = "preflight_ready"
    else:
        phase = "preflight_only"
    return {
        "requested_live_execution": requested_live,
        "live_preflight_required": requested_live and not dry_run,
        "live_preflight_passed": bool(live_route_allowed),
        "live_route_allowed": bool(live_route_allowed),
        "live_transport_bound": bool(live_transport_bound),
        "live_transport_callable": bool(live_transport_callable),
        "attempted_live": False,
        "live_submission_performed": False,
        "live_submission_phase": phase,
        "live_submission_phase_initial": phase,
        "live_submission_phase_history": [phase],
        "live_submission_last_transition_at": now_iso,
        "venue_live_submission_bound": bool(live_transport_bound),
        "operator_bound": bool(live_transport_bound),
        "venue_live_submission_attempted": False,
        "venue_live_submission_performed": False,
    }


def _update_live_submission_runtime_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    attempted_live: bool | None = None,
    live_submission_performed: bool | None = None,
    live_submission_phase: str | None = None,
    live_submission_failed: str | None = None,
) -> dict[str, Any]:
    updated = dict(metadata or {})
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    phase_history = [str(item).strip() for item in list(updated.get("live_submission_phase_history") or []) if str(item).strip()]
    if attempted_live is not None:
        updated["attempted_live"] = bool(attempted_live)
        updated["venue_live_submission_attempted"] = bool(attempted_live)
        if attempted_live and not updated.get("live_submission_attempted_at"):
            updated["live_submission_attempted_at"] = now_iso
    if live_submission_performed is not None:
        updated["live_submission_performed"] = bool(live_submission_performed)
        updated["venue_live_submission_performed"] = bool(live_submission_performed)
        if live_submission_performed and not updated.get("live_submission_performed_at"):
            updated["live_submission_performed_at"] = now_iso
    if live_submission_phase is not None:
        phase = str(live_submission_phase)
        updated["live_submission_phase"] = phase
        updated.setdefault("live_submission_phase_initial", phase)
        if not phase_history or phase_history[-1] != phase:
            phase_history.append(phase)
        updated["live_submission_phase_history"] = phase_history
        updated["live_submission_last_transition_at"] = now_iso
    if live_submission_failed:
        updated["venue_live_submission_failed"] = live_submission_failed
        updated["live_submission_failed"] = live_submission_failed
        updated.setdefault("live_submission_failed_at", now_iso)
    elif phase_history:
        updated["live_submission_phase_history"] = phase_history
    return updated


def _execution_projection_action_valid(
    projection: ExecutionProjection | None,
    *,
    now: datetime,
    requested_mode: ExecutionProjectionMode,
) -> tuple[bool, list[str], dict[str, Any]]:
    blocked_reasons: list[str] = []
    if projection is None:
        blocked_reasons.append("missing_execution_projection")
        return False, blocked_reasons, {
            "projection_present": False,
            "projection_valid": False,
            "projection_verdict": None,
            "projection_projected_mode": None,
            "projection_expires_at": None,
            "projection_manual_review_required": None,
        }

    projection_valid = True
    if projection.is_expired(now):
        blocked_reasons.append("execution_projection_expired")
        projection_valid = False
    elif projection.is_stale(now):
        blocked_reasons.append("execution_projection_stale")
        projection_valid = False

    if projection.projection_verdict == ExecutionProjectionVerdict.blocked:
        blocked_reasons.append("execution_projection_blocked")
        projection_valid = False
    if requested_mode == ExecutionProjectionMode.live and projection.manual_review_required:
        blocked_reasons.append("execution_projection_manual_review_required")
        projection_valid = False

    return projection_valid, blocked_reasons, {
        "projection_present": True,
        "projection_valid": projection_valid,
        "projection_verdict": projection.projection_verdict.value,
        "projection_projected_mode": projection.projected_mode.value,
        "projection_expires_at": projection.expires_at.isoformat(),
        "projection_manual_review_required": projection.manual_review_required,
        "projection_id": projection.projection_id,
        "projection_summary": projection.summary,
    }


def _resolution_guard_action_valid(
    *,
    market: MarketDescriptor,
    snapshot: MarketSnapshot,
    resolution_guard: ResolutionGuardReport | None,
    request_metadata: Mapping[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    guard = resolution_guard or evaluate_resolution_policy(market, snapshot=snapshot)
    blocked_reasons: list[str] = []
    if guard is None:
        blocked_reasons.append("missing_resolution_guard")
        return False, blocked_reasons, {
            "resolution_guard_present": False,
            "resolution_guard_valid": False,
            "resolution_guard_status": None,
            "resolution_guard_approved": False,
            "resolution_guard_manual_review_required": True,
        }

    request_metadata_dict = dict(request_metadata or {})
    guard_valid = bool(guard.approved and guard.can_forecast and not guard.manual_review_required and guard.status == ResolutionStatus.clear)
    if not guard.approved:
        blocked_reasons.append("resolution_guard_not_approved")
    if not guard.can_forecast:
        blocked_reasons.append("resolution_guard_cannot_forecast")
    if guard.manual_review_required:
        blocked_reasons.append("resolution_guard_manual_review_required")
    if guard.status != ResolutionStatus.clear:
        blocked_reasons.append(f"resolution_guard_status:{guard.status.value}")
    if not guard.official_source:
        blocked_reasons.append("resolution_guard_missing_official_source")
        guard_valid = False

    completeness_threshold = max(
        0.0,
        _float_metadata(request_metadata_dict, "min_resolution_compatibility_score", 0.0),
        _float_metadata(request_metadata_dict, "min_policy_completeness_score", 0.0),
    )
    coherence_threshold = max(
        0.0,
        _float_metadata(request_metadata_dict, "min_resolution_compatibility_score", 0.0),
        _float_metadata(request_metadata_dict, "min_policy_coherence_score", 0.0),
    )
    payout_threshold = max(0.0, _float_metadata(request_metadata_dict, "min_payout_compatibility_score", 0.0))
    currency_threshold = max(0.0, _float_metadata(request_metadata_dict, "min_currency_compatibility_score", 0.0))

    completeness_score = float(getattr(guard, "policy_completeness_score", 0.0) or 0.0)
    coherence_score = float(getattr(guard, "policy_coherence_score", 0.0) or 0.0)
    payout_score = (
        _float_metadata(request_metadata_dict, "payout_compatibility_score", 0.0)
        if "payout_compatibility_score" in request_metadata_dict
        else None
    )
    currency_score = (
        _float_metadata(request_metadata_dict, "currency_compatibility_score", 0.0)
        if "currency_compatibility_score" in request_metadata_dict
        else None
    )

    if completeness_threshold > 0.0 and completeness_score < completeness_threshold:
        blocked_reasons.append(
            "resolution_policy_completeness_below_minimum:"
            f"{completeness_score:.3f}/{completeness_threshold:.3f}"
        )
        guard_valid = False
    if coherence_threshold > 0.0 and coherence_score < coherence_threshold:
        blocked_reasons.append(
            "resolution_policy_coherence_below_minimum:"
            f"{coherence_score:.3f}/{coherence_threshold:.3f}"
        )
        guard_valid = False
    if payout_threshold > 0.0 and payout_score is not None and payout_score < payout_threshold:
        blocked_reasons.append(
            "resolution_payout_compatibility_below_minimum:"
            f"{payout_score:.3f}/{payout_threshold:.3f}"
        )
        guard_valid = False
    if currency_threshold > 0.0 and currency_score is not None and currency_score < currency_threshold:
        blocked_reasons.append(
            "resolution_currency_compatibility_below_minimum:"
            f"{currency_score:.3f}/{currency_threshold:.3f}"
        )
        guard_valid = False

    return guard_valid, _dedupe(blocked_reasons), {
        "resolution_guard_present": True,
        "resolution_guard_valid": guard_valid,
        "resolution_guard_status": guard.status.value,
        "resolution_guard_approved": guard.approved,
        "resolution_guard_manual_review_required": guard.manual_review_required,
        "resolution_guard_can_forecast": guard.can_forecast,
        "resolution_guard_id": guard.policy_id,
        "resolution_guard_official_source": guard.official_source,
        "resolution_guard_policy_completeness_score": completeness_score,
        "resolution_guard_policy_coherence_score": coherence_score,
        "resolution_guard_min_compatibility_score": max(completeness_threshold, coherence_threshold),
        "resolution_guard_min_payout_compatibility_score": payout_threshold or None,
        "resolution_guard_min_currency_compatibility_score": currency_threshold or None,
        "resolution_guard_payout_compatibility_score": payout_score,
        "resolution_guard_currency_compatibility_score": currency_score,
    }


def _executable_edge_action_valid(
    *,
    request: LiveExecutionRequest,
    executable_edge: ExecutableEdge | None,
    now: datetime,
) -> tuple[bool, list[str], dict[str, Any], ExecutableEdge]:
    edge = executable_edge
    if edge is None:
        edge = _derive_executable_edge_from_request(request, now=now)

    blocked_reasons: list[str] = []
    if edge is None:
        blocked_reasons.append("missing_executable_edge")
        return False, blocked_reasons, {
            "executable_edge_present": False,
            "executable_edge_valid": False,
            "executable_edge_expires_at": None,
            "executable_edge_manual_review_required": True,
            "executable_edge_confidence": None,
            "executable_edge_bps": None,
            "executable_edge_id": None,
        }, edge

    edge_valid = bool(edge.executable and edge.expires_at > now)
    if edge.expires_at <= now:
        blocked_reasons.append("executable_edge_expired")
    if edge.manual_review_required:
        blocked_reasons.append("executable_edge_manual_review_required")
    if not edge.executable:
        blocked_reasons.append("executable_edge_not_executable")
    if edge.executable_edge_bps <= 0.0:
        blocked_reasons.append("executable_edge_non_positive")

    return edge_valid, _dedupe(blocked_reasons), {
        "executable_edge_present": True,
        "executable_edge_valid": edge_valid,
        "executable_edge_expires_at": edge.expires_at.isoformat(),
        "executable_edge_manual_review_required": edge.manual_review_required,
        "executable_edge_confidence": edge.confidence,
        "executable_edge_bps": edge.executable_edge_bps,
        "executable_edge_id": edge.edge_id,
        "executable_edge_ref": edge.proof_ref,
        "executable_edge_summary": edge.surface(),
    }, edge


def _derive_executable_edge_from_request(
    request: LiveExecutionRequest,
    *,
    now: datetime,
) -> ExecutableEdge | None:
    raw_edge_bps = _float_metadata(request.metadata, "execution_edge_bps", default=float(request.recommendation.edge_bps or 0.0))
    confidence = max(0.0, min(1.0, float(request.recommendation.confidence or 0.0)))
    if raw_edge_bps <= 0.0 and confidence <= 0.0:
        return None
    return ExecutableEdge(
        market_ref=request.market.market_id,
        counterparty_market_ref=_first_non_empty(
            request.metadata.get("execution_edge_counterparty_market_ref"),
            request.metadata.get("counterparty_market_ref"),
        ),
        proof_ref=_first_non_empty(
            request.metadata.get("execution_edge_proof_ref"),
            request.metadata.get("proof_ref"),
        ),
        raw_edge_bps=raw_edge_bps,
        fees_bps=_float_metadata(request.metadata, "execution_edge_fees_bps", default=0.0),
        slippage_bps=_float_metadata(request.metadata, "execution_edge_slippage_bps", default=0.0),
        hedge_risk_bps=_float_metadata(request.metadata, "execution_edge_hedge_risk_bps", default=0.0),
        confidence=confidence,
        expires_at=_utc_datetime(_first_non_empty(request.metadata.get("execution_edge_expires_at"))) or (now + timedelta(seconds=300)),
        manual_review_required=_metadata_bool(request.metadata, "execution_edge_manual_review_required"),
        reason_codes=[
            reason
            for reason in _dedupe(
                [
                    str(reason).strip()
                    for reason in (
                        [request.metadata.get("execution_edge_reason_codes")]
                        if isinstance(request.metadata.get("execution_edge_reason_codes"), str)
                        else list(request.metadata.get("execution_edge_reason_codes", []))
                    )
                    if str(reason).strip()
                ]
            )
        ],
        metadata={
            "source": "live_execution_action_time",
            "run_id": request.run_id,
            "market_id": request.market.market_id,
            "requested_mode": request.requested_mode,
            "requested_stake": request.requested_stake,
        },
    )


def _action_time_guard(
    *,
    request: LiveExecutionRequest,
    projection: ExecutionProjection,
    resolution_guard: ResolutionGuardReport | None,
    executable_edge: ExecutableEdge | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    requested_mode = _coerce_requested_mode(request.requested_mode, dry_run=bool(request.dry_run), allow_live_execution=True)
    projection_valid, projection_blocked_reasons, projection_audit = _execution_projection_action_valid(
        projection,
        now=now,
        requested_mode=requested_mode,
    )
    resolution_valid, resolution_blocked_reasons, resolution_audit = _resolution_guard_action_valid(
        market=request.market,
        snapshot=request.snapshot,
        resolution_guard=resolution_guard,
        request_metadata=request.metadata,
    )
    edge_valid, edge_blocked_reasons, edge_audit, resolved_edge = _executable_edge_action_valid(
        request=request,
        executable_edge=executable_edge,
        now=now,
    )

    strict_live_requested = (
        requested_mode == ExecutionProjectionMode.live
        and not bool(request.dry_run)
        and projection.projected_mode == ExecutionProjectionOutcome.live
    )
    blocked_reasons = _dedupe([
        *projection_blocked_reasons,
        *resolution_blocked_reasons,
        *edge_blocked_reasons,
    ])
    if not strict_live_requested and blocked_reasons:
        verdict = "annotated"
    elif blocked_reasons:
        verdict = "blocked"
    else:
        verdict = "ok"

    summary_parts = [f"requested_mode={requested_mode.value}", f"verdict={verdict}"]
    if blocked_reasons:
        summary_parts.append("blocked=" + ";".join(blocked_reasons[:6]))
    summary = " | ".join(summary_parts)
    return {
        "action_time_guard_id": f"aguard_{uuid4().hex[:12]}",
        "requested_mode": requested_mode.value,
        "strict_live_requested": strict_live_requested,
        "verdict": verdict,
        "summary": summary,
        "projection": projection_audit,
        "resolution_guard": resolution_audit,
        "executable_edge": edge_audit,
        "resolved_executable_edge": resolved_edge.model_dump(mode="json") if resolved_edge is not None else None,
        "projection_valid": projection_valid,
        "resolution_guard_valid": resolution_valid,
        "executable_edge_valid": edge_valid,
        "blocked_reasons": blocked_reasons,
        "warning_reasons": [],
        "timestamp": now.isoformat(),
    }


def _status_from_paper_trade(paper_trade: PaperTradeSimulation) -> LiveExecutionStatus:
    if paper_trade.status == PaperTradeStatus.partial:
        return LiveExecutionStatus.partial
    if paper_trade.status == PaperTradeStatus.filled:
        return LiveExecutionStatus.filled
    return LiveExecutionStatus.rejected


def _resolve_requested_stake(
    request: LiveExecutionRequest,
    policy: LiveExecutionPolicy,
    ledger_before: CapitalLedgerSnapshot,
) -> tuple[float, bool]:
    if request.requested_stake is not None:
        return float(request.requested_stake), True
    if "requested_stake" in request.metadata:
        try:
            return max(0.0, float(request.metadata["requested_stake"])), True
        except (TypeError, ValueError):
            pass
    if request.risk_report is not None and request.risk_report.max_allowed_notional > 0:
        return min(policy.max_stake, request.risk_report.max_allowed_notional), False
    return min(policy.max_stake, max(0.0, ledger_before.equity * policy.max_fraction_of_equity)), False


def _stake_limit(
    policy: LiveExecutionPolicy,
    ledger_before: CapitalLedgerSnapshot,
    request: LiveExecutionRequest,
    *,
    capital_control_state: CapitalControlState | None = None,
) -> float:
    equity_limit = max(0.0, ledger_before.equity * policy.max_fraction_of_equity)
    stake_limit = min(policy.max_stake, equity_limit)
    if capital_control_state is not None:
        stake_limit = min(stake_limit, max(0.0, capital_control_state.capital_available_usd))
    if request.risk_report is not None and request.risk_report.max_allowed_notional > 0:
        stake_limit = min(stake_limit, request.risk_report.max_allowed_notional)
    if request.metadata.get("max_stake") is not None:
        try:
            stake_limit = min(stake_limit, max(0.0, float(request.metadata["max_stake"])))
        except (TypeError, ValueError):
            pass
    return max(0.0, stake_limit)


def _loss_cap_triggered(policy: LiveExecutionPolicy, ledger_before: CapitalLedgerSnapshot) -> tuple[bool, str | None]:
    realized_loss = max(0.0, -float(ledger_before.realized_pnl or 0.0))
    if policy.max_realized_loss > 0.0 and realized_loss > policy.max_realized_loss:
        return True, f"realized_loss_cap_exceeded:{realized_loss:.2f}/{policy.max_realized_loss:.2f}"

    daily_loss = CapitalLedger.from_snapshot(ledger_before).daily_loss_usd()
    if policy.max_daily_loss_usd > 0.0 and daily_loss > policy.max_daily_loss_usd:
        return True, f"daily_loss_cap_exceeded:{daily_loss:.2f}/{policy.max_daily_loss_usd:.2f}"

    peak_equity = _equity_peak_from_metadata(ledger_before)
    drawdown = max(0.0, peak_equity - float(ledger_before.equity or 0.0))
    drawdown_limit = max(0.0, policy.max_drawdown_abs, peak_equity * policy.max_drawdown_fraction_of_peak_equity)
    if drawdown_limit > 0.0 and drawdown > drawdown_limit:
        return True, f"drawdown_cap_exceeded:{drawdown:.2f}/{drawdown_limit:.2f}"
    return False, None


def _equity_peak_from_metadata(ledger_before: CapitalLedgerSnapshot) -> float:
    metadata = ledger_before.metadata or {}
    for key in ("equity_high_watermark", "peak_equity", "equity_peak"):
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    return max(0.0, float(ledger_before.equity or 0.0))


def _venue_allowed(market: MarketDescriptor, policy: LiveExecutionPolicy) -> tuple[bool, str | None]:
    if market.venue in policy.blocked_venues:
        return False, f"venue_blocked:{market.venue.value}"
    if policy.allowed_venues and market.venue not in policy.allowed_venues:
        return False, f"venue_not_allowed:{market.venue.value}"
    return True, None


def _venue_health_live_allowed(venue_health: VenueHealthReport | None) -> tuple[bool, str | None]:
    if venue_health is None:
        return True, None
    if venue_health.healthy:
        return True, None
    message = str(venue_health.message or "").strip() or "venue_unhealthy"
    details = dict(getattr(venue_health, "details", {}) or {})
    if details.get("degraded_mode") or "degraded" in message.lower():
        return False, f"venue_health_degraded:{message}"
    return False, f"venue_health_unhealthy:{message}"


def _authorization_required(policy: LiveExecutionPolicy, *, dry_run: bool) -> bool:
    if dry_run:
        return bool(policy.dry_run_requires_authorization)
    return bool(policy.require_authorization)


def _compliance_required(policy: LiveExecutionPolicy, *, dry_run: bool) -> bool:
    if dry_run:
        return bool(policy.dry_run_requires_compliance)
    return bool(policy.require_compliance_approval)


def _auth_passed(auth: ExecutionAuthContext, policy: LiveExecutionPolicy, *, dry_run: bool) -> bool:
    required = _authorization_required(policy, dry_run=dry_run)
    if not required:
        return True
    if not auth.authorized:
        return False
    if policy.required_scope and policy.required_scope not in auth.scopes:
        return False
    return True


def _compliance_passed(auth: ExecutionAuthContext, policy: LiveExecutionPolicy, *, dry_run: bool) -> bool:
    if not _compliance_required(policy, dry_run=dry_run):
        return True
    return auth.compliance_approved


def _position_side(side: TradeSide | None) -> TradeSide:
    if side == TradeSide.no:
        return TradeSide.no
    return TradeSide.yes


def _coerce_requested_mode(
    value: str | LiveExecutionMode | ExecutionProjectionMode | None,
    *,
    dry_run: bool,
    allow_live_execution: bool,
) -> ExecutionProjectionMode:
    if isinstance(value, ExecutionProjectionMode):
        return value
    text = str(value).strip().lower() if value is not None else ""
    if text in {"live", "bounded_live"}:
        return ExecutionProjectionMode.live if allow_live_execution and not dry_run else ExecutionProjectionMode.paper
    if text in {"shadow"}:
        return ExecutionProjectionMode.shadow
    if text in {"paper", "dry_run", "bounded_dry_run", ""}:
        return ExecutionProjectionMode.paper
    return ExecutionProjectionMode.paper


def _coerce_projection_mode(value: str | ExecutionProjectionMode | ExecutionProjectionOutcome | None) -> ExecutionProjectionOutcome | ExecutionProjectionMode:
    if isinstance(value, (ExecutionProjectionMode, ExecutionProjectionOutcome)):
        return value
    text = str(value).strip().lower() if value is not None else ""
    if text in {"live"}:
        return ExecutionProjectionOutcome.live
    if text in {"shadow"}:
        return ExecutionProjectionOutcome.shadow
    if text in {"paper", "dry_run", "bounded_dry_run"}:
        return ExecutionProjectionOutcome.paper
    if text in {"blocked", ""}:
        return ExecutionProjectionMode.paper
    return ExecutionProjectionOutcome.paper


def _mode_rank(mode: ExecutionProjectionMode | ExecutionProjectionOutcome) -> int:
    value = getattr(mode, "value", str(mode))
    order = {
        "blocked": 0,
        "paper": 1,
        "shadow": 2,
        "live": 3,
    }
    return order.get(value, 1)


def min_projection_mode(
    left: ExecutionProjectionMode | ExecutionProjectionOutcome | str,
    right: ExecutionProjectionMode | ExecutionProjectionOutcome | str,
) -> ExecutionProjectionMode | ExecutionProjectionOutcome:
    left_mode = _coerce_projection_mode(left)
    right_mode = _coerce_projection_mode(right)
    return left_mode if _mode_rank(left_mode) <= _mode_rank(right_mode) else right_mode


def _float_metadata(metadata: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    if not metadata or key not in metadata:
        return default
    try:
        return float(metadata[key])
    except (TypeError, ValueError):
        return default


def _projection_anchor_at(
    *,
    readiness: ExecutionReadiness | None,
    ledger_before: CapitalLedgerSnapshot,
    venue_health: VenueHealthReport | None,
    request_metadata: Mapping[str, Any] | None,
) -> datetime:
    anchor = _utc_datetime(request_metadata.get("anchor_at")) if request_metadata is not None else None
    if anchor is None and readiness is not None:
        anchor = readiness.created_at
    if anchor is None:
        anchor = ledger_before.updated_at
    if venue_health is not None and venue_health.checked_at > anchor:
        anchor = venue_health.checked_at
    return anchor.replace(microsecond=0)


def _projection_expires_at(anchor_at: datetime, ttl_seconds: float) -> datetime:
    ttl = max(30.0, float(ttl_seconds))
    return anchor_at + timedelta(seconds=ttl)


def _projection_summary_text(
    *,
    requested: ExecutionProjectionMode | ExecutionProjectionOutcome,
    projected: ExecutionProjectionMode | ExecutionProjectionOutcome,
    verdict: ExecutionProjectionVerdict,
    blocking_reasons: list[str],
    downgrade_reasons: list[str],
) -> str:
    parts = [f"requested={requested.value}", f"projected={projected.value}", f"verdict={verdict.value}"]
    if blocking_reasons:
        parts.append(f"blocked={';'.join(blocking_reasons[:3])}")
    if downgrade_reasons:
        parts.append(f"downgraded={';'.join(downgrade_reasons[:3])}")
    return " | ".join(parts)


def _build_execution_readiness(
    *,
    request: LiveExecutionRequest,
    requested_stake: float,
    execution_plan: VenueExecutionPlan,
    auth: ExecutionAuthContext,
    compliance_required: bool,
    compliance_passed: bool,
    ledger_before: CapitalLedgerSnapshot,
    venue_allowed: bool,
    venue_reason: str | None,
    no_trade_reasons: list[str],
    live_allowed: bool,
    shadow_allowed: bool = False,
    human_approval_required: bool = False,
    human_approval_passed: bool = False,
) -> ExecutionReadiness:
    base = request.execution_readiness.model_dump(mode="python") if request.execution_readiness is not None else {}
    base_metadata = dict(base.get("metadata") or {})
    execution_notes = list(base.get("execution_notes") or [])
    blocked_reasons = _dedupe([*(base.get("blocked_reasons") or []), *(base.get("no_trade_reasons") or []), *no_trade_reasons])
    if not venue_allowed and venue_reason:
        blocked_reasons = _dedupe([*blocked_reasons, venue_reason])
    decision_action = request.recommendation.action
    side = request.recommendation.side
    risk_checks_passed = (
        decision_action == DecisionAction.bet
        and side is not None
        and request.recommendation.price_reference is not None
        and requested_stake > 0.0
        and not blocked_reasons
        and (request.risk_report is None or request.risk_report.should_trade)
    )
    if request.risk_report is not None and not request.risk_report.should_trade:
        blocked_reasons = _dedupe([*blocked_reasons, *(f"risk_block:{reason}" for reason in request.risk_report.no_trade_reasons or ["risk_report_denied"])])
    manual_review_required = bool(base.get("manual_review_required", False) or (human_approval_required and not human_approval_passed))
    ready_to_live = live_allowed and risk_checks_passed and not blocked_reasons and base_metadata.get("live_gate_passed", False)
    route = "live_candidate" if ready_to_live else ("shadow" if shadow_allowed and risk_checks_passed else ("paper" if risk_checks_passed else "blocked"))
    payload = {
        **base,
        "run_id": request.run_id,
        "market_id": request.market.market_id,
        "venue": request.market.venue,
        "decision_id": base.get("decision_id"),
        "forecast_id": base.get("forecast_id") or request.recommendation.forecast_id,
        "recommendation_id": base.get("recommendation_id") or request.recommendation.recommendation_id,
        "trade_intent_id": base.get("trade_intent_id"),
        "decision_action": decision_action,
        "side": side,
        "size_usd": requested_stake,
        "limit_price": request.recommendation.price_reference,
        "max_slippage_bps": max(_float_metadata(base_metadata, "max_slippage_bps", 0.0), 0.0, float(request.recommendation.confidence * 100.0)),
        "confidence": request.recommendation.confidence,
        "edge_after_fees_bps": request.recommendation.edge_bps or 0.0,
        "risk_checks_passed": risk_checks_passed,
        "manual_review_required": manual_review_required,
        "ready_to_execute": risk_checks_passed,
        "ready_to_paper": risk_checks_passed,
        "ready_to_live": ready_to_live,
        "can_materialize_trade_intent": risk_checks_passed,
        "blocked_reasons": blocked_reasons,
        "no_trade_reasons": blocked_reasons,
        "route": route,
        "execution_notes": _dedupe([
            *execution_notes,
            f"requested_mode={request.requested_mode}",
            f"venue_allowed={venue_allowed}",
            f"live_allowed={live_allowed}",
            f"shadow_allowed={shadow_allowed}",
            f"human_approval_required_before_live={human_approval_required}",
            f"human_approval_passed={human_approval_passed}",
            f"risk_checks_passed={risk_checks_passed}",
        ]),
        "metadata": {
            **base_metadata,
            "live_gate_passed": ready_to_live,
            "venue_allowed": venue_allowed,
            "venue_reason": venue_reason,
            "requested_stake": requested_stake,
            "execution_adapter": execution_plan.adapter_name,
            "execution_mode": execution_plan.execution_mode,
            "human_approval_required_before_live": human_approval_required,
            "human_approval_passed": human_approval_passed,
            "shadow_allowed": shadow_allowed,
        },
    }
    payload["route"] = route
    return ExecutionReadiness.model_validate(payload)


def _cancelled_market_execution(
    *,
    request: LiveExecutionRequest,
    ledger_before: CapitalLedgerSnapshot,
    execution_capability: Any,
    execution_plan: VenueExecutionPlan,
    execution_projection: ExecutionProjection | None = None,
    reason: str,
    ) -> MarketExecutionRecord:
    order = MarketExecutionOrder(
        run_id=request.run_id,
        market_id=request.market.market_id,
        venue=request.market.venue,
        position_side=_position_side(request.recommendation.side),
        execution_side=TradeSide.buy,
        order_type=MarketExecutionOrderType.limit
        if request.recommendation.price_reference is not None
        else MarketExecutionOrderType.market,
        requested_quantity=max(0.0, float(request.requested_stake or 0.0)),
        requested_notional=max(0.0, float(request.requested_stake or 0.0)),
        limit_price=request.recommendation.price_reference,
        status=MarketExecutionStatus.cancelled.value,
        cancelled_reason=reason,
        cancelled_by="live_execution_projection",
        cancelled_at=datetime.now(timezone.utc).replace(microsecond=0),
        metadata={
            "source": "live_execution",
            "reason": reason,
            "dry_run": True,
            "allow_live_execution": False,
        },
    )
    record = MarketExecutionRecord.from_cancelled(
        order=order,
        mode=MarketExecutionMode.bounded_dry_run,
        reason=reason,
        cancelled_by="live_execution_projection",
        capability=execution_capability.model_dump(mode="json") if hasattr(execution_capability, "model_dump") else dict(execution_capability),
        execution_plan=execution_plan.model_dump(mode="json"),
        ledger_before=ledger_before,
        ledger_after=ledger_before,
        trade_intent_ref=request.metadata.get("trade_intent_id"),
        execution_projection_ref=getattr(execution_projection, "projection_id", None),
        metadata={
            **request.metadata,
            "request_type": "live_execution",
            "persisted": False,
            "projection_cancelled": True,
        },
    )
    record.live_execution_status = LiveExecutionStatus.blocked.value
    record.metadata = {
        **dict(record.metadata or {}),
        "live_execution_status": LiveExecutionStatus.blocked.value,
    }
    record.order.metadata = {
        **dict(record.order.metadata or {}),
        "live_execution_status": LiveExecutionStatus.blocked.value,
    }
    return record


def _build_venue_order_lifecycle(
    *,
    request: LiveExecutionRequest,
    market_execution: MarketExecutionRecord,
    execution_plan: VenueExecutionPlan,
    live_execution_supported: bool,
) -> VenueOrderLifecycle:
    return build_venue_order_lifecycle(
        order_id=market_execution.order.order_id,
        execution_id=market_execution.execution_id,
        request_metadata={
            **dict(market_execution.order.metadata or {}),
            **dict(request.metadata or {}),
        },
        status=market_execution.order.status,
        acknowledged_at=market_execution.order.acknowledged_at,
        acknowledged_by=market_execution.order.acknowledged_by,
        acknowledged_reason=market_execution.order.acknowledged_reason,
        cancelled_reason=market_execution.order.cancelled_reason,
        live_execution_supported=live_execution_supported,
        venue_order_path=execution_plan.venue_order_path,
        venue_order_cancel_path=execution_plan.venue_order_cancel_path,
    )


def _attach_venue_order_context(
    record: LiveExecutionRecord,
    market_execution: MarketExecutionRecord | None,
    lifecycle: VenueOrderLifecycle,
) -> None:
    live_status = record.status.value
    attempted_live = bool(record.metadata.get("attempted_live") or record.metadata.get("venue_live_submission_attempted"))
    live_submission_performed = bool(
        record.metadata.get("live_submission_performed") or record.metadata.get("venue_live_submission_performed")
    )
    live_preflight_passed = bool(record.metadata.get("live_preflight_passed"))
    live_transport_bound = bool(record.metadata.get("venue_live_submission_bound") or record.metadata.get("live_transport_bound"))
    live_submission_failed = (
        record.metadata.get("venue_live_submission_failed")
        or record.metadata.get("live_submission_failed")
        or _execution_reason_failure_type(record.execution_reasons)
    )
    live_submission_phase = str(
        record.metadata.get("live_submission_phase")
        or (
            "performed_live"
            if live_submission_performed
            else "attempted_live"
            if attempted_live
            else "dry_run"
        )
    )
    if live_submission_failed and attempted_live and not live_submission_performed:
        live_submission_phase = "attempted_live_failed"
    venue_order_ack_path = _venue_order_ack_path(lifecycle)
    lifecycle_payload = {
        **lifecycle.model_dump(mode="json"),
        "venue_order_ack_path": venue_order_ack_path,
        "live_preflight_passed": live_preflight_passed,
        "attempted_live": attempted_live,
        "live_submission_performed": live_submission_performed,
        "live_submission_phase": live_submission_phase,
        "live_submission_failed": live_submission_failed,
        "venue_live_submission_bound": live_transport_bound,
    }
    order_trace_audit = _venue_order_trace_audit(
        lifecycle,
        live_status=live_status,
        venue_order_ack_path=venue_order_ack_path,
        live_preflight_passed=live_preflight_passed,
        live_route_allowed=bool(record.metadata.get("live_route_allowed")),
        attempted_live=attempted_live,
        live_submission_performed=live_submission_performed,
        live_submission_phase=live_submission_phase,
        live_submission_failed=live_submission_failed,
        live_transport_bound=live_transport_bound,
    )
    live_submission_receipt = _live_submission_receipt(
        lifecycle=lifecycle,
        order_trace_audit=order_trace_audit,
        metadata=record.metadata,
        venue_order_ack_path=venue_order_ack_path,
    )
    live_transport_readiness = _live_transport_readiness_snapshot(
        record=record,
        lifecycle=lifecycle,
        order_trace_audit=order_trace_audit,
        venue_order_ack_path=venue_order_ack_path,
    )
    venue_live_configuration_snapshot = _venue_live_configuration_snapshot(
        record=record,
        lifecycle=lifecycle,
    )
    live_auth_compliance_evidence = _live_auth_compliance_evidence(record)
    live_route_evidence = _live_route_evidence(
        record=record,
        lifecycle=lifecycle,
        order_trace_audit=order_trace_audit,
        live_submission_receipt=live_submission_receipt,
        venue_order_ack_path=venue_order_ack_path,
        live_submission_failed=live_submission_failed,
    )
    selected_live_path_receipt = _selected_live_path_receipt(
        record=record,
        lifecycle=lifecycle,
        order_trace_audit=order_trace_audit,
        live_submission_receipt=live_submission_receipt,
        venue_order_ack_path=venue_order_ack_path,
        live_submission_failed=live_submission_failed,
    )
    live_attempt_timeline = _live_attempt_timeline(
        record=record,
        lifecycle=lifecycle,
        order_trace_audit=order_trace_audit,
        live_submission_receipt=live_submission_receipt,
    )
    live_blocker_snapshot = _live_blocker_snapshot(record)
    selected_live_path_audit = _selected_live_path_audit(
        selected_live_path_receipt=selected_live_path_receipt,
        live_transport_readiness=live_transport_readiness,
        live_route_evidence=live_route_evidence,
        live_auth_compliance_evidence=live_auth_compliance_evidence,
    )
    live_lifecycle_snapshot = _live_lifecycle_snapshot(
        lifecycle_payload=lifecycle_payload,
        order_trace_audit=order_trace_audit,
        live_submission_receipt=live_submission_receipt,
    )
    order_trace_artifacts = _order_trace_artifacts_bundle(
        lifecycle_payload=lifecycle_payload,
        order_trace_audit=order_trace_audit,
        live_submission_receipt=live_submission_receipt,
        selected_live_path_receipt=selected_live_path_receipt,
    )
    live_runtime_honest_mode = str(order_trace_audit.get("runtime_honest_mode") or "dry_run")
    live_acknowledged = bool(live_submission_receipt.get("acknowledged"))
    live_cancel_observed = bool(live_submission_receipt.get("cancel_observed"))
    if market_execution is not None:
        market_execution.order.metadata = {
            **dict(market_execution.order.metadata or {}),
            "venue_order_id": lifecycle.venue_order_id,
            "venue_order_status": lifecycle.venue_order_status,
            "venue_order_source": lifecycle.venue_order_source,
            "venue_order_submission_state": lifecycle.venue_order_submission_state,
            "venue_order_ack_state": lifecycle.venue_order_ack_state,
            "venue_order_cancel_state": lifecycle.venue_order_cancel_state,
            "venue_order_execution_state": lifecycle.venue_order_execution_state,
            "venue_order_status_history": list(lifecycle.venue_order_status_history),
            "venue_order_acknowledged_at": lifecycle.venue_order_acknowledged_at.isoformat() if lifecycle.venue_order_acknowledged_at is not None else None,
            "venue_order_acknowledged_by": lifecycle.venue_order_acknowledged_by,
            "venue_order_acknowledged_reason": lifecycle.venue_order_acknowledged_reason,
            "venue_order_cancel_reason": lifecycle.venue_order_cancel_reason,
            "venue_order_cancelled_at": lifecycle.venue_order_cancelled_at.isoformat() if lifecycle.venue_order_cancelled_at is not None else None,
            "venue_order_cancelled_by": lifecycle.venue_order_cancelled_by,
            "venue_order_path": lifecycle.venue_order_path,
            "venue_order_ack_path": venue_order_ack_path,
            "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
            "venue_order_configured": lifecycle.venue_order_configured,
            "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
            "venue_order_flow": lifecycle.venue_order_flow,
            "live_preflight_passed": live_preflight_passed,
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "live_submission_phase": live_submission_phase,
            "live_submission_failed": live_submission_failed,
            "venue_live_submission_bound": live_transport_bound,
            "live_execution_status": live_status,
            "order_trace_audit": order_trace_audit,
            "live_submission_receipt": live_submission_receipt,
            "venue_submission_receipt": _venue_submission_receipt_from_lifecycle(
                lifecycle,
                transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
                runtime_honest_mode=str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
                attempted_live=attempted_live,
                live_submission_performed=live_submission_performed,
                live_submission_phase=live_submission_phase,
                submission_error_type=live_submission_failed,
                submitted_payload=record.metadata.get("venue_live_submitted_payload"),
                blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
            ),
            "venue_cancellation_receipt": _venue_cancellation_receipt_from_lifecycle(
                lifecycle,
                transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
                runtime_honest_mode=str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
                attempted_live=attempted_live,
                live_submission_performed=live_submission_performed,
                cancellation_performed=live_cancel_observed,
                cancellation_phase=live_submission_phase if live_cancel_observed else "dry_run",
                cancellation_error_type=live_submission_failed,
                cancelled_payload=record.metadata.get("venue_live_cancelled_payload"),
                blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
            ),
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
        }
        market_execution.order.status = lifecycle.venue_order_status
        market_execution.order.acknowledged_at = lifecycle.venue_order_acknowledged_at
        market_execution.order.acknowledged_by = lifecycle.venue_order_acknowledged_by
        market_execution.order.acknowledged_reason = lifecycle.venue_order_acknowledged_reason
        market_execution.order.cancelled_at = lifecycle.venue_order_cancelled_at
        market_execution.order.cancelled_by = lifecycle.venue_order_cancelled_by
        market_execution.order.cancelled_reason = lifecycle.venue_order_cancel_reason
        market_execution.metadata = {
            **dict(market_execution.metadata or {}),
            "venue_order_id": lifecycle.venue_order_id,
            "venue_order_status": lifecycle.venue_order_status,
            "venue_order_source": lifecycle.venue_order_source,
            "venue_order_status_history": list(lifecycle.venue_order_status_history),
            "venue_order_acknowledged_at": lifecycle.venue_order_acknowledged_at.isoformat() if lifecycle.venue_order_acknowledged_at is not None else None,
            "venue_order_acknowledged_by": lifecycle.venue_order_acknowledged_by,
            "venue_order_acknowledged_reason": lifecycle.venue_order_acknowledged_reason,
            "venue_order_cancel_reason": lifecycle.venue_order_cancel_reason,
            "venue_order_cancelled_at": lifecycle.venue_order_cancelled_at.isoformat() if lifecycle.venue_order_cancelled_at is not None else None,
            "venue_order_cancelled_by": lifecycle.venue_order_cancelled_by,
            "venue_order_ack_path": venue_order_ack_path,
            "venue_order_configured": lifecycle.venue_order_configured,
            "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
            "venue_order_flow": lifecycle.venue_order_flow,
            "live_preflight_passed": live_preflight_passed,
            "attempted_live": attempted_live,
            "live_submission_performed": live_submission_performed,
            "live_submission_phase": live_submission_phase,
            "live_submission_failed": live_submission_failed,
            "venue_live_submission_bound": live_transport_bound,
            "live_execution_status": live_status,
            "venue_order_lifecycle": lifecycle_payload,
            "order_trace_audit": order_trace_audit,
            "live_submission_receipt": live_submission_receipt,
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
            "venue_submission_state": lifecycle.venue_order_submission_state,
            "venue_ack_state": lifecycle.venue_order_ack_state,
            "venue_cancel_state": lifecycle.venue_order_cancel_state,
            "venue_execution_state": lifecycle.venue_order_execution_state,
        }
        market_execution.live_execution_status = live_status
        market_execution.venue_order_ack_path = venue_order_ack_path
        market_execution.live_preflight_passed = live_preflight_passed
        market_execution.attempted_live = attempted_live
        market_execution.live_submission_performed = live_submission_performed
        market_execution.live_submission_phase = live_submission_phase
        market_execution.venue_submission_state = lifecycle.venue_order_submission_state
        market_execution.venue_ack_state = lifecycle.venue_order_ack_state
        market_execution.venue_cancel_state = lifecycle.venue_order_cancel_state
        market_execution.venue_execution_state = lifecycle.venue_order_execution_state
        market_execution.venue_live_submission_bound = live_transport_bound
        market_execution.operator_bound = live_transport_bound
        market_execution.live_runtime_honest_mode = live_runtime_honest_mode
        market_execution.live_submission_failed = live_submission_failed
        market_execution.live_acknowledged = live_acknowledged
        market_execution.live_cancel_observed = live_cancel_observed
        market_execution.live_submission_receipt = dict(live_submission_receipt)
        market_execution.venue_submission_receipt = _venue_submission_receipt_from_lifecycle(
            lifecycle,
            transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
            runtime_honest_mode=str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
            attempted_live=attempted_live,
            live_submission_performed=live_submission_performed,
            live_submission_phase=live_submission_phase,
            submission_error_type=live_submission_failed,
            submitted_payload=record.metadata.get("venue_live_submitted_payload"),
            blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
        )
        market_execution.venue_cancellation_receipt = _venue_cancellation_receipt_from_lifecycle(
            lifecycle,
            transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
            runtime_honest_mode=str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
            attempted_live=attempted_live,
            live_submission_performed=live_submission_performed,
            cancellation_performed=live_cancel_observed,
            cancellation_phase=live_submission_phase if live_cancel_observed else "dry_run",
            cancellation_error_type=live_submission_failed,
            cancelled_payload=record.metadata.get("venue_live_cancelled_payload"),
            blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
        )
        market_execution.live_transport_readiness = dict(live_transport_readiness)
        market_execution.venue_live_configuration_snapshot = dict(venue_live_configuration_snapshot)
        market_execution.live_route_evidence = dict(live_route_evidence)
        market_execution.live_auth_compliance_evidence = dict(live_auth_compliance_evidence)
        market_execution.selected_live_path_receipt = dict(selected_live_path_receipt)
        market_execution.order_trace_artifacts = dict(order_trace_artifacts)
        market_execution.live_attempt_timeline = dict(live_attempt_timeline)
        market_execution.live_blocker_snapshot = dict(live_blocker_snapshot)
        market_execution.selected_live_path_audit = dict(selected_live_path_audit)
        market_execution.live_lifecycle_snapshot = dict(live_lifecycle_snapshot)
    record.venue_order_id = lifecycle.venue_order_id
    record.venue_order_status = lifecycle.venue_order_status
    record.venue_order_source = lifecycle.venue_order_source
    record.venue_order_status_history = list(lifecycle.venue_order_status_history)
    record.venue_order_acknowledged_at = lifecycle.venue_order_acknowledged_at
    record.venue_order_acknowledged_by = lifecycle.venue_order_acknowledged_by
    record.venue_order_acknowledged_reason = lifecycle.venue_order_acknowledged_reason
    record.venue_order_cancel_reason = lifecycle.venue_order_cancel_reason
    record.venue_order_cancelled_at = lifecycle.venue_order_cancelled_at
    record.venue_order_cancelled_by = lifecycle.venue_order_cancelled_by
    record.venue_order_path = lifecycle.venue_order_path
    record.venue_order_ack_path = venue_order_ack_path
    record.venue_order_cancel_path = lifecycle.venue_order_cancel_path
    record.venue_order_trace_kind = lifecycle.venue_order_trace_kind
    record.venue_order_flow = lifecycle.venue_order_flow
    record.venue_submission_state = lifecycle.venue_order_submission_state
    record.venue_ack_state = lifecycle.venue_order_ack_state
    record.venue_cancel_state = lifecycle.venue_order_cancel_state
    record.venue_execution_state = lifecycle.venue_order_execution_state
    record.live_preflight_passed = live_preflight_passed
    record.attempted_live = attempted_live
    record.live_submission_performed = live_submission_performed
    record.live_submission_phase = live_submission_phase
    record.venue_live_submission_bound = live_transport_bound
    record.operator_bound = live_transport_bound
    record.live_runtime_honest_mode = live_runtime_honest_mode
    record.live_submission_failed = live_submission_failed
    record.live_acknowledged = live_acknowledged
    record.live_cancel_observed = live_cancel_observed
    record.live_submission_receipt = dict(live_submission_receipt)
    record.venue_submission_receipt = _venue_submission_receipt_from_lifecycle(
        lifecycle,
        transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
        runtime_honest_mode=live_runtime_honest_mode,
        attempted_live=attempted_live,
        live_submission_performed=live_submission_performed,
        live_submission_phase=live_submission_phase,
        submission_error_type=live_submission_failed,
        submitted_payload=record.metadata.get("venue_live_submitted_payload"),
        blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
    )
    record.venue_cancellation_receipt = _venue_cancellation_receipt_from_lifecycle(
        lifecycle,
        transport_mode=str(order_trace_audit.get("transport_mode") or "dry_run"),
        runtime_honest_mode=live_runtime_honest_mode,
        attempted_live=attempted_live,
        live_submission_performed=live_submission_performed,
        cancellation_performed=live_cancel_observed,
        cancellation_phase=live_submission_phase if live_cancel_observed else "dry_run",
        cancellation_error_type=live_submission_failed,
        cancelled_payload=record.metadata.get("venue_live_cancelled_payload"),
        blocked_reasons=live_blocker_snapshot.get("transport_failures") if isinstance(live_blocker_snapshot, dict) else None,
    )
    record.live_transport_readiness = dict(live_transport_readiness)
    record.venue_live_configuration_snapshot = dict(venue_live_configuration_snapshot)
    record.live_route_evidence = dict(live_route_evidence)
    record.live_auth_compliance_evidence = dict(live_auth_compliance_evidence)
    record.selected_live_path_receipt = dict(selected_live_path_receipt)
    record.order_trace_artifacts = dict(order_trace_artifacts)
    record.live_attempt_timeline = dict(live_attempt_timeline)
    record.live_blocker_snapshot = dict(live_blocker_snapshot)
    record.selected_live_path_audit = dict(selected_live_path_audit)
    record.live_lifecycle_snapshot = dict(live_lifecycle_snapshot)
    record.metadata = {
        **dict(record.metadata or {}),
        "live_execution_status": live_status,
        "venue_order_id": lifecycle.venue_order_id,
        "venue_order_status": lifecycle.venue_order_status,
        "venue_order_source": lifecycle.venue_order_source,
        "venue_order_status_history": list(lifecycle.venue_order_status_history),
        "venue_order_acknowledged_at": lifecycle.venue_order_acknowledged_at.isoformat() if lifecycle.venue_order_acknowledged_at is not None else None,
        "venue_order_acknowledged_by": lifecycle.venue_order_acknowledged_by,
        "venue_order_acknowledged_reason": lifecycle.venue_order_acknowledged_reason,
        "venue_order_cancel_reason": lifecycle.venue_order_cancel_reason,
        "venue_order_cancelled_at": lifecycle.venue_order_cancelled_at.isoformat() if lifecycle.venue_order_cancelled_at is not None else None,
        "venue_order_cancelled_by": lifecycle.venue_order_cancelled_by,
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_ack_path": venue_order_ack_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
        "venue_order_configured": lifecycle.venue_order_configured,
        "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
        "venue_order_flow": lifecycle.venue_order_flow,
        "venue_order_submission_state": lifecycle.venue_order_submission_state,
        "venue_order_ack_state": lifecycle.venue_order_ack_state,
        "venue_order_cancel_state": lifecycle.venue_order_cancel_state,
        "venue_order_execution_state": lifecycle.venue_order_execution_state,
        "live_preflight_passed": live_preflight_passed,
        "attempted_live": attempted_live,
        "live_submission_performed": live_submission_performed,
        "live_submission_phase": live_submission_phase,
        "venue_live_submission_bound": live_transport_bound,
        "operator_bound": live_transport_bound,
        "live_runtime_honest_mode": live_runtime_honest_mode,
        "live_submission_failed": live_submission_failed,
        "live_acknowledged": live_acknowledged,
        "live_cancel_observed": live_cancel_observed,
        "live_submission_receipt": live_submission_receipt,
        "venue_submission_receipt": record.venue_submission_receipt,
        "venue_cancellation_receipt": record.venue_cancellation_receipt,
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
        "venue_submission_state": lifecycle.venue_order_submission_state,
        "venue_ack_state": lifecycle.venue_order_ack_state,
        "venue_cancel_state": lifecycle.venue_order_cancel_state,
        "venue_execution_state": lifecycle.venue_order_execution_state,
        "venue_order_lifecycle": lifecycle_payload,
        "order_trace_audit": order_trace_audit,
    }


def _venue_order_ack_path(lifecycle: VenueOrderLifecycle) -> str:
    history = {str(item).strip() for item in lifecycle.venue_order_status_history or [] if str(item).strip()}
    acknowledged = bool(
        lifecycle.venue_order_acknowledged_at is not None
        or lifecycle.venue_order_acknowledged_by
        or lifecycle.venue_order_acknowledged_reason
        or "acknowledged" in history
    )
    if acknowledged and lifecycle.venue_order_path:
        return lifecycle.venue_order_path
    return "unavailable"


def _live_submission_receipt(
    *,
    lifecycle: VenueOrderLifecycle,
    order_trace_audit: Mapping[str, Any],
    metadata: Mapping[str, Any] | None,
    venue_order_ack_path: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    submitted_payload = payload.get("venue_live_submitted_payload")
    history = [str(item).strip() for item in lifecycle.venue_order_status_history or [] if str(item).strip()]
    acknowledged = bool(
        lifecycle.venue_order_acknowledged_at is not None
        or lifecycle.venue_order_acknowledged_by
        or lifecycle.venue_order_acknowledged_reason
        or "acknowledged" in history
    )
    cancel_observed = bool(
        lifecycle.venue_order_cancelled_at is not None
        or lifecycle.venue_order_cancelled_by
        or lifecycle.venue_order_cancel_reason
        or "cancelled" in history
    )
    submitted_payload_hash = None
    if submitted_payload is not None:
        try:
            submitted_payload_hash = _stable_content_hash(submitted_payload)[:12]
        except Exception:  # pragma: no cover - defensive hashing
            submitted_payload_hash = None
    return {
        "schema_version": "v1",
        "receipt_source": "venue_order_lifecycle",
        "transport_mode": order_trace_audit.get("transport_mode", "dry_run"),
        "runtime_honest_mode": order_trace_audit.get("runtime_honest_mode", "dry_run"),
        "live_route_allowed": bool(order_trace_audit.get("live_route_allowed")),
        "attempted_live": bool(order_trace_audit.get("attempted_live")),
        "live_submission_performed": bool(order_trace_audit.get("live_submission_performed")),
        "live_submission_phase": str(order_trace_audit.get("live_submission_phase") or "dry_run"),
        "submission_error_type": (
            payload.get("venue_live_submission_failed")
            or payload.get("live_submission_failed")
            or order_trace_audit.get("submission_error_type")
        ),
        "venue_live_submission_bound": bool(order_trace_audit.get("venue_live_submission_bound")),
        "operator_bound": bool(order_trace_audit.get("operator_bound") or order_trace_audit.get("venue_live_submission_bound")),
        "venue_order_id": lifecycle.venue_order_id,
        "venue_order_status": lifecycle.venue_order_status,
        "venue_order_source": lifecycle.venue_order_source,
        "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_ack_path": venue_order_ack_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
        "venue_submission_state": lifecycle.venue_order_submission_state,
        "venue_ack_state": lifecycle.venue_order_ack_state,
        "venue_cancel_state": lifecycle.venue_order_cancel_state,
        "venue_execution_state": lifecycle.venue_order_execution_state,
        "venue_order_status_history": history,
        "submitted_payload_present": submitted_payload is not None,
        "submitted_payload_hash": submitted_payload_hash,
        "acknowledged": acknowledged,
        "cancel_observed": cancel_observed,
    }


def _live_transport_readiness_snapshot(
    *,
    record: LiveExecutionRecord,
    lifecycle: VenueOrderLifecycle,
    order_trace_audit: Mapping[str, Any],
    venue_order_ack_path: str,
) -> dict[str, Any]:
    plan = dict(record.execution_plan or {})
    plan_metadata = dict(plan.get("metadata") or {})
    metadata = dict(record.metadata or {})
    return {
        "schema_version": "v1",
        "adapter_name": record.execution_adapter or plan.get("adapter_name"),
        "backend_mode": plan.get("backend_mode") or metadata.get("execution_backend_mode"),
        "route_supported": bool(plan.get("route_supported", True)),
        "runtime_ready": bool(plan_metadata.get("runtime_ready", metadata.get("live_route_allowed", False))),
        "ready_for_live_execution": bool(plan_metadata.get("ready_for_live_execution", metadata.get("live_route_allowed", False))),
        "live_route_allowed": bool(metadata.get("live_route_allowed")),
        "live_preflight_passed": bool(order_trace_audit.get("live_preflight_passed")),
        "transport_bound": bool(metadata.get("live_transport_bound") or metadata.get("venue_live_submission_bound")),
        "operator_bound": bool(metadata.get("operator_bound") or metadata.get("live_transport_bound") or metadata.get("venue_live_submission_bound")),
        "transport_callable": bool(metadata.get("live_transport_callable")),
        "attempted_live": bool(order_trace_audit.get("attempted_live")),
        "live_submission_performed": bool(order_trace_audit.get("live_submission_performed")),
        "live_submission_phase": str(order_trace_audit.get("live_submission_phase") or "dry_run"),
        "transport_mode": str(order_trace_audit.get("transport_mode") or "dry_run"),
        "runtime_honest_mode": str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
        "selected_trace_kind": lifecycle.venue_order_trace_kind,
        "selected_order_path": lifecycle.venue_order_path,
        "selected_ack_path": venue_order_ack_path,
        "selected_cancel_path": lifecycle.venue_order_cancel_path,
    }


def _venue_live_configuration_snapshot(
    *,
    record: LiveExecutionRecord,
    lifecycle: VenueOrderLifecycle,
) -> dict[str, Any]:
    plan = dict(record.execution_plan or {})
    plan_metadata = dict(plan.get("metadata") or {})
    return {
        "schema_version": "v1",
        "venue": record.venue.value,
        "adapter_name": record.execution_adapter or plan.get("adapter_name"),
        "backend_mode": plan.get("backend_mode") or plan_metadata.get("selected_backend_mode"),
        "execution_mode": plan.get("execution_mode"),
        "live_execution_supported": bool(plan.get("live_execution_supported")),
        "bounded_execution_supported": bool(plan.get("bounded_execution_supported")),
        "market_execution_supported": bool(plan.get("market_execution_supported")),
        "venue_order_configured": bool(lifecycle.venue_order_configured),
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
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
        "venue_submission_state": record.venue_submission_state,
        "venue_ack_state": record.venue_ack_state,
        "venue_cancel_state": record.venue_cancel_state,
        "venue_execution_state": record.venue_execution_state,
    }


def _live_auth_compliance_evidence(record: LiveExecutionRecord) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "auth_required": bool(record.auth_required),
        "auth_passed": bool(record.auth_passed),
        "compliance_required": bool(record.compliance_required),
        "compliance_passed": bool(record.compliance_passed),
        "jurisdiction_required": bool(record.jurisdiction_required),
        "jurisdiction_passed": bool(record.jurisdiction_passed),
        "account_type_required": bool(record.account_type_required),
        "account_type_passed": bool(record.account_type_passed),
        "automation_required": bool(record.automation_required),
        "automation_passed": bool(record.automation_passed),
        "rate_limit_required": bool(record.rate_limit_required),
        "rate_limit_passed": bool(record.rate_limit_passed),
        "tos_required": bool(record.tos_required),
        "tos_passed": bool(record.tos_passed),
        "venue_allowed": bool(record.venue_allowed),
        "live_allowed": bool(record.live_allowed),
        "blocked_reason": record.blocked_reason,
        "no_trade_reasons": list(record.no_trade_reasons),
        "execution_reasons": list(record.execution_reasons),
        "principal": record.metadata.get("auth_principal"),
        "scopes": list(record.metadata.get("auth_scopes") or []),
        "venue_submission_state": record.venue_submission_state,
        "venue_ack_state": record.venue_ack_state,
        "venue_cancel_state": record.venue_cancel_state,
        "venue_execution_state": record.venue_execution_state,
    }


def _live_route_evidence(
    *,
    record: LiveExecutionRecord,
    lifecycle: VenueOrderLifecycle,
    order_trace_audit: Mapping[str, Any],
    live_submission_receipt: Mapping[str, Any],
    venue_order_ack_path: str,
    live_submission_failed: str | None,
) -> dict[str, Any]:
    venue_submission_state = (
        lifecycle.venue_order_submission_state
        or order_trace_audit.get("venue_submission_state")
        or record.venue_submission_state
        or "simulated"
    )
    venue_ack_state = (
        lifecycle.venue_order_ack_state
        or order_trace_audit.get("venue_ack_state")
        or record.venue_ack_state
        or "not_acknowledged"
    )
    venue_cancel_state = (
        "venue_cancelled"
        if bool(live_submission_receipt.get("cancel_observed"))
        else "not_cancelled"
    )
    venue_execution_state = (
        lifecycle.venue_order_execution_state
        or order_trace_audit.get("venue_execution_state")
        or record.venue_execution_state
        or "simulated"
    )
    return {
        "schema_version": "v1",
        "requested_mode": record.requested_mode,
        "projected_mode": record.projected_mode,
        "projection_verdict": record.projection_verdict,
        "effective_mode": record.mode.value,
        "dry_run": bool(record.dry_run),
        "live_route_allowed": bool(record.metadata.get("live_route_allowed")),
        "live_preflight_passed": bool(order_trace_audit.get("live_preflight_passed")),
        "attempted_live": bool(order_trace_audit.get("attempted_live")),
        "live_submission_performed": bool(order_trace_audit.get("live_submission_performed")),
        "live_submission_phase": str(order_trace_audit.get("live_submission_phase") or "dry_run"),
        "live_submission_failed": live_submission_failed,
        "transport_mode": str(order_trace_audit.get("transport_mode") or "dry_run"),
        "runtime_honest_mode": str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
        "venue_submission_state": venue_submission_state,
        "venue_ack_state": venue_ack_state,
        "venue_cancel_state": venue_cancel_state,
        "venue_execution_state": venue_execution_state,
        "operator_bound": bool(order_trace_audit.get("operator_bound") or order_trace_audit.get("venue_live_submission_bound")),
        "selected_order_source": lifecycle.venue_order_source,
        "selected_trace_kind": lifecycle.venue_order_trace_kind,
        "selected_order_flow": lifecycle.venue_order_flow,
        "selected_order_path": lifecycle.venue_order_path,
        "selected_ack_path": venue_order_ack_path,
        "selected_cancel_path": lifecycle.venue_order_cancel_path,
        "credential_evidence": dict(record.execution_plan.get("metadata", {}).get("credential_evidence") or {}),
        "configuration_evidence": dict(record.execution_plan.get("metadata", {}).get("configuration_evidence") or {}),
        "readiness_evidence": dict(record.execution_plan.get("metadata", {}).get("readiness_evidence") or {}),
    }


def _selected_live_path_receipt(
    *,
    record: LiveExecutionRecord,
    lifecycle: VenueOrderLifecycle,
    order_trace_audit: Mapping[str, Any],
    live_submission_receipt: Mapping[str, Any],
    venue_order_ack_path: str,
    live_submission_failed: str | None,
) -> dict[str, Any]:
    plan = dict(record.execution_plan or {})
    plan_metadata = dict(plan.get("metadata") or {})
    venue_submission_state = (
        lifecycle.venue_order_submission_state
        or order_trace_audit.get("venue_submission_state")
        or record.venue_submission_state
        or "simulated"
    )
    venue_ack_state = (
        lifecycle.venue_order_ack_state
        or order_trace_audit.get("venue_ack_state")
        or record.venue_ack_state
        or "not_acknowledged"
    )
    venue_cancel_state = (
        "venue_cancelled"
        if bool(live_submission_receipt.get("cancel_observed"))
        else "not_cancelled"
    )
    venue_execution_state = (
        lifecycle.venue_order_execution_state
        or order_trace_audit.get("venue_execution_state")
        or record.venue_execution_state
        or "simulated"
    )
    return {
        "schema_version": "v1",
        "receipt_source": "selected_live_path",
        "venue": record.venue.value,
        "adapter_name": record.execution_adapter or plan.get("adapter_name"),
        "backend_mode": plan.get("backend_mode") or plan_metadata.get("selected_backend_mode"),
        "selected_transport_mode": str(order_trace_audit.get("transport_mode") or "dry_run"),
        "runtime_honest_mode": str(order_trace_audit.get("runtime_honest_mode") or "dry_run"),
        "live_route_allowed": bool(order_trace_audit.get("live_route_allowed")),
        "venue_submission_state": venue_submission_state,
        "venue_ack_state": venue_ack_state,
        "venue_cancel_state": venue_cancel_state,
        "venue_execution_state": venue_execution_state,
        "venue_live_submission_bound": bool(order_trace_audit.get("venue_live_submission_bound")),
        "operator_bound": bool(order_trace_audit.get("operator_bound") or order_trace_audit.get("venue_live_submission_bound")),
        "selected_order_source": lifecycle.venue_order_source,
        "selected_trace_kind": lifecycle.venue_order_trace_kind,
        "selected_order_path": lifecycle.venue_order_path,
        "selected_ack_path": venue_order_ack_path,
        "selected_cancel_path": lifecycle.venue_order_cancel_path,
        "attempted_live": bool(order_trace_audit.get("attempted_live")),
        "live_submission_performed": bool(order_trace_audit.get("live_submission_performed")),
        "live_submission_phase": str(order_trace_audit.get("live_submission_phase") or "dry_run"),
        "submission_error_type": live_submission_failed or order_trace_audit.get("submission_error_type"),
        "credential_evidence": dict(plan_metadata.get("credential_evidence") or {}),
        "configuration_evidence": dict(plan_metadata.get("configuration_evidence") or {}),
        "readiness_evidence": dict(plan_metadata.get("readiness_evidence") or {}),
    }


def _live_attempt_timeline(
    *,
    record: LiveExecutionRecord,
    lifecycle: VenueOrderLifecycle,
    order_trace_audit: Mapping[str, Any],
    live_submission_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = dict(record.metadata or {})
    phase_current = str(order_trace_audit.get("live_submission_phase") or metadata.get("live_submission_phase") or "dry_run")
    phase_history = [str(item).strip() for item in list(metadata.get("live_submission_phase_history") or []) if str(item).strip()]
    if not phase_history or phase_history[-1] != phase_current:
        phase_history.append(phase_current)
    last_transition_at = metadata.get("live_submission_last_transition_at")
    attempted_at = metadata.get("live_submission_attempted_at") or (last_transition_at if bool(order_trace_audit.get("attempted_live")) else None)
    performed_at = metadata.get("live_submission_performed_at") or (
        last_transition_at if bool(order_trace_audit.get("live_submission_performed")) else None
    )
    failed_at = metadata.get("live_submission_failed_at") or (
        last_transition_at if order_trace_audit.get("submission_error_type") else None
    )
    return {
        "schema_version": "v1",
        "timeline_source": "live_execution_runtime",
        "created_at": record.created_at.isoformat(),
        "phase_initial": metadata.get("live_submission_phase_initial") or metadata.get("live_submission_phase"),
        "phase_current": phase_current,
        "phase_history": phase_history,
        "last_transition_at": last_transition_at,
        "attempted_at": attempted_at,
        "performed_at": performed_at,
        "failed_at": failed_at,
        "acknowledged_at": lifecycle.venue_order_acknowledged_at.isoformat() if lifecycle.venue_order_acknowledged_at is not None else None,
        "cancelled_at": lifecycle.venue_order_cancelled_at.isoformat() if lifecycle.venue_order_cancelled_at is not None else None,
        "attempted_live": bool(order_trace_audit.get("attempted_live")),
        "live_submission_performed": bool(order_trace_audit.get("live_submission_performed")),
        "operator_bound": bool(order_trace_audit.get("operator_bound") or order_trace_audit.get("venue_live_submission_bound")),
        "acknowledged": bool(live_submission_receipt.get("acknowledged")),
        "cancel_observed": bool(live_submission_receipt.get("cancel_observed")),
        "venue_submission_state": lifecycle.venue_order_submission_state or record.venue_submission_state,
        "venue_ack_state": lifecycle.venue_order_ack_state or record.venue_ack_state,
        "venue_cancel_state": "venue_cancelled" if bool(live_submission_receipt.get("cancel_observed")) else "not_cancelled",
        "venue_execution_state": lifecycle.venue_order_execution_state or record.venue_execution_state,
    }


def _live_blocker_snapshot(record: LiveExecutionRecord) -> dict[str, Any]:
    no_trade_reasons = [str(item) for item in record.no_trade_reasons or [] if str(item).strip()]
    execution_reasons = [str(item) for item in record.execution_reasons or [] if str(item).strip()]
    action_time_blockers = [str(item) for item in list((record.action_time_guard or {}).get("blocked_reasons") or []) if str(item).strip()]

    def _match(prefixes: tuple[str, ...], items: list[str]) -> list[str]:
        matched: list[str] = []
        for item in items:
            lowered = item.lower()
            if any(prefix in lowered for prefix in prefixes):
                matched.append(item)
        return matched

    auth_blockers = _match(("authorization", "missing_scope", "scope:"), no_trade_reasons + execution_reasons)
    compliance_blockers = _match(("compliance", "jurisdiction", "account_type", "tos", "automation", "rate_limit"), no_trade_reasons + execution_reasons)
    route_blockers = _match(
        ("venue_blocked", "live_execution_disabled", "non_execution_venue_type", "projection_", "recommendation_action"),
        no_trade_reasons + execution_reasons,
    )
    transport_blockers = _match(("polymarket_live_not_ready", "polymarket_missing:", "venue_live_transport_unavailable", "preflight"), no_trade_reasons + execution_reasons)
    transport_failures = _match(("venue_live_submission_failed:", "live_submitter_failed:"), no_trade_reasons + execution_reasons)
    capital_blockers = _match(("capital_", "stake_", "ledger_equity", "loss_cap", "drawdown"), no_trade_reasons + execution_reasons)
    manual_review_blockers = _match(("manual_review",), no_trade_reasons + execution_reasons)
    readiness_blockers = _match(
        ("live_route_blocked", "preflight_blocked", "runtime_ready_false", "ready_for_live_execution_blocked"),
        no_trade_reasons + execution_reasons,
    )
    config_blockers = _match(("missing_", "polymarket_missing:", "transport_unavailable", "not_ready"), no_trade_reasons + execution_reasons)
    known = set(
        auth_blockers
        + compliance_blockers
        + route_blockers
        + transport_blockers
        + transport_failures
        + capital_blockers
        + manual_review_blockers
        + readiness_blockers
        + config_blockers
        + action_time_blockers
    )
    other_blockers = [item for item in no_trade_reasons + execution_reasons if item not in known]
    blocker_summary = "; ".join((auth_blockers + compliance_blockers + route_blockers + transport_blockers + transport_failures + capital_blockers + manual_review_blockers + readiness_blockers + config_blockers + action_time_blockers + other_blockers)[:8])
    route_state = "available"
    if route_blockers or transport_blockers or transport_failures:
        route_state = "blocked"
    elif auth_blockers or compliance_blockers or capital_blockers or manual_review_blockers or readiness_blockers or config_blockers or action_time_blockers:
        route_state = "degraded"
    return {
        "schema_version": "v1",
        "is_blocked": bool(record.blocked_reason or no_trade_reasons or action_time_blockers),
        "live_available": bool(
            (record.live_allowed or record.live_preflight_passed or record.live_submission_performed)
            and not route_blockers
            and not transport_blockers
            and not transport_failures
        ),
        "route_state": route_state,
        "operator_bound": bool(record.venue_live_submission_bound or record.metadata.get("operator_bound") or record.metadata.get("live_transport_bound")),
        "blocked_reason_summary": blocker_summary,
        "auth_blockers": auth_blockers,
        "compliance_blockers": compliance_blockers,
        "route_blockers": route_blockers,
        "transport_blockers": transport_blockers,
        "transport_failures": transport_failures,
        "capital_blockers": capital_blockers,
        "manual_review_blockers": manual_review_blockers,
        "readiness_blockers": readiness_blockers,
        "configuration_blockers": config_blockers,
        "action_time_blockers": action_time_blockers,
        "other_blockers": other_blockers,
    }


def _selected_live_path_audit(
    *,
    selected_live_path_receipt: Mapping[str, Any],
    live_transport_readiness: Mapping[str, Any],
    live_route_evidence: Mapping[str, Any],
    live_auth_compliance_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "audit_source": "selected_live_path",
        "selected_live_path_receipt": dict(selected_live_path_receipt),
        "live_transport_readiness": dict(live_transport_readiness),
        "live_route_evidence": dict(live_route_evidence),
        "live_auth_compliance_evidence": dict(live_auth_compliance_evidence),
    }


def _live_lifecycle_snapshot(
    *,
    lifecycle_payload: Mapping[str, Any],
    order_trace_audit: Mapping[str, Any],
    live_submission_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = dict(lifecycle_payload)
    snapshot.update(
        {
            "schema_version": "v1",
            "snapshot_source": "live_execution_lifecycle",
            "transport_mode": order_trace_audit.get("transport_mode", "dry_run"),
            "runtime_honest_mode": order_trace_audit.get("runtime_honest_mode", "dry_run"),
            "submission_error_type": order_trace_audit.get("submission_error_type"),
            "acknowledged": bool(live_submission_receipt.get("acknowledged")),
            "cancel_observed": bool(live_submission_receipt.get("cancel_observed")),
            "operator_bound": bool(order_trace_audit.get("operator_bound") or order_trace_audit.get("venue_live_submission_bound")),
            "venue_submission_state": lifecycle_payload.get("venue_submission_state") or order_trace_audit.get("venue_submission_state") or "simulated",
            "venue_ack_state": lifecycle_payload.get("venue_ack_state") or order_trace_audit.get("venue_ack_state") or "not_acknowledged",
            "venue_cancel_state": lifecycle_payload.get("venue_cancel_state") or order_trace_audit.get("venue_cancel_state") or "not_cancelled",
            "venue_execution_state": lifecycle_payload.get("venue_execution_state") or order_trace_audit.get("venue_execution_state") or "simulated",
        }
    )
    return snapshot


def _order_trace_artifacts_bundle(
    *,
    lifecycle_payload: Mapping[str, Any],
    order_trace_audit: Mapping[str, Any],
    live_submission_receipt: Mapping[str, Any],
    selected_live_path_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "artifact_source": "live_execution",
        "venue_order_lifecycle": dict(lifecycle_payload),
        "order_trace_audit": dict(order_trace_audit),
        "live_submission_receipt": dict(live_submission_receipt),
        "selected_live_path_receipt": dict(selected_live_path_receipt),
    }


def _execution_reason_failure_type(reasons: Iterable[str] | None) -> str | None:
    for reason in reasons or []:
        text = str(reason).strip()
        if not text:
            continue
        for prefix in ("venue_live_submission_failed:", "live_submitter_failed:"):
            if text.startswith(prefix):
                suffix = text.split(":", 1)[1].strip()
                if suffix:
                    return suffix
    return None


def _venue_order_trace_audit(
    lifecycle: VenueOrderLifecycle,
    *,
    live_status: str,
    venue_order_ack_path: str,
    live_preflight_passed: bool,
    live_route_allowed: bool,
    attempted_live: bool,
    live_submission_performed: bool,
    live_submission_phase: str,
    live_submission_failed: str | None,
    live_transport_bound: bool,
) -> dict[str, Any]:
    transport_mode = "live" if lifecycle.live_execution_supported and lifecycle.venue_order_trace_kind == "external_live" else "dry_run"
    place_auditable = bool(lifecycle.venue_order_path and lifecycle.venue_order_path != "unavailable")
    cancel_auditable = bool(lifecycle.venue_order_cancel_path and lifecycle.venue_order_cancel_path != "unavailable")
    ack_auditable = bool(venue_order_ack_path and venue_order_ack_path != "unavailable")
    return {
        "schema_version": "v1",
        "trace_source": "venue_order_lifecycle",
        "venue_order_id": lifecycle.venue_order_id,
        "venue_order_status": lifecycle.venue_order_status,
        "venue_order_source": lifecycle.venue_order_source,
        "venue_order_status_history": list(lifecycle.venue_order_status_history),
        "venue_order_acknowledged_at": lifecycle.venue_order_acknowledged_at.isoformat() if lifecycle.venue_order_acknowledged_at is not None else None,
        "venue_order_acknowledged_by": lifecycle.venue_order_acknowledged_by,
        "venue_order_acknowledged_reason": lifecycle.venue_order_acknowledged_reason,
        "venue_order_cancel_reason": lifecycle.venue_order_cancel_reason,
        "venue_order_cancelled_at": lifecycle.venue_order_cancelled_at.isoformat() if lifecycle.venue_order_cancelled_at is not None else None,
        "venue_order_cancelled_by": lifecycle.venue_order_cancelled_by,
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_ack_path": venue_order_ack_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
        "venue_order_configured": lifecycle.venue_order_configured,
        "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
        "venue_order_flow": lifecycle.venue_order_flow,
        "live_execution_supported": lifecycle.live_execution_supported,
        "live_execution_status": live_status,
        "live_preflight_passed": live_preflight_passed,
        "live_route_allowed": live_route_allowed,
        "attempted_live": attempted_live,
        "live_submission_performed": live_submission_performed,
        "live_submission_phase": live_submission_phase,
        "submission_error_type": live_submission_failed,
        "venue_live_submission_bound": live_transport_bound,
        "operator_bound": live_transport_bound,
        "transport_mode": transport_mode,
        "runtime_live_claimed": transport_mode == "live",
        "runtime_honest_mode": transport_mode,
        "place_auditable": place_auditable,
        "cancel_auditable": cancel_auditable,
        "ack_auditable": ack_auditable,
    }


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


__all__ = [
    "ExecutionAuthContext",
    "ExecutionProjection",
    "ExecutionProjectionMode",
    "ExecutionProjectionOutcome",
    "ExecutionProjectionVerdict",
    "LiveExecutionEngine",
    "LiveExecutionMode",
    "LiveExecutionPolicy",
    "LiveExecutionRecord",
    "LiveExecutionRequest",
    "LiveExecutionStatus",
    "LiveExecutionStore",
    "MarketExecutionRecord",
    "execute_live_trade",
]
