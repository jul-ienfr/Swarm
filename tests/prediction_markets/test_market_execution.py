from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from prediction_markets import (
    ExecutionAuthContext,
    CapitalLedger,
    LiveExecutionEngine,
    LiveExecutionPolicy,
    LiveExecutionRequest,
    MarketDescriptor,
    MarketExecutionEngine,
    MarketExecutionStore,
    MarketSnapshot,
    MarketStatus,
    MarketRecommendationPacket,
    TradeIntent,
    TradeSide,
    VenueName,
    VenueType,
    DecisionAction,
)
from prediction_markets.market_execution import (
    BoundedMarketExecutionEngine,
    MarketExecutionMode,
    MarketExecutionOrder,
    MarketExecutionOrderLifecycleSnapshot,
    MarketExecutionOrderTraceAudit,
    MarketExecutionRecord,
    MarketExecutionRequest,
)
from prediction_markets.execution_edge import ExecutableEdge
from prediction_markets.resolution_guard import ResolutionGuardReport
from prediction_markets.models import ExecutionProjection, ExecutionProjectionMode, ExecutionProjectionOutcome, ExecutionProjectionVerdict, ResolutionStatus, ExecutionReadiness
from prediction_markets.live_execution import LiveExecutionStatus
from prediction_markets.market_execution import MarketExecutionStatus


@pytest.fixture(autouse=True)
def _live_polymarket_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/tmp/live_order")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/tmp/cancel_order")


def _descriptor() -> MarketDescriptor:
    return MarketDescriptor(
        market_id="pm_exec",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Execution test market",
        question="Will execution audit persist?",
        status=MarketStatus.open,
        liquidity=20_000.0,
        volume=90_000.0,
        resolution_source="https://example.com/resolution",
    )


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm_exec",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Execution test market",
        question="Will execution audit persist?",
        price_yes=0.54,
        price_no=0.46,
        midpoint_yes=0.54,
        spread_bps=45.0,
        liquidity=20_000.0,
        volume=90_000.0,
        staleness_ms=0,
    )


def _recommendation() -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id="run_exec",
        forecast_id="fcst_exec",
        market_id="pm_exec",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.54,
        edge_bps=420.0,
        confidence=0.88,
    )


def test_market_execution_materializes_blocked_execution(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=False,
            dry_run_enabled=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_exec",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation().model_copy(update={"action": DecisionAction.no_trade, "side": None}),
            requested_stake=12.0,
            dry_run=False,
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    )
    report = MarketExecutionEngine().materialize(
        record,
        trade_intent=TradeIntent(
            run_id="run_exec",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=None,
            size_usd=0.0,
            risk_checks_passed=False,
            no_trade_reasons=["recommendation_action:no_trade"],
        ),
    )

    assert report.status.value == "blocked"
    assert report.order.requested_stake == 12.0
    assert report.order.acknowledged_at is not None
    assert report.order.acknowledged_by == "paper_trade_simulator"
    assert report.order.status_history[:2] == ["submitted", "acknowledged"]
    assert report.order.order_source == "paper_trade_simulator"
    assert report.fill_count == 0
    assert report.position_count == len(report.positions)
    assert report.fills == []
    assert report.trade_intent_ref is not None
    assert report.execution_projection_ref == record.execution_projection.projection_id


def test_market_execution_materializes_runtime_guard_and_audit_trace(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
        )
    )
    ledger = CapitalLedger.from_cash(cash=1_000.0, venue=VenueName.polymarket).current_snapshot()
    ledger.metadata["capital_frozen"] = True
    ledger.metadata["capital_freeze_reason"] = "manual_hold"
    execution_record = engine.execute(
        LiveExecutionRequest(
            run_id="run_exec_audit",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_mode="live",
            requested_stake=12.0,
            ledger=ledger,
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
            metadata={
                "capital_frozen": True,
                "capital_freeze_reason": "manual_hold",
            },
        ),
        persist=False,
    )
    report = MarketExecutionEngine().materialize(
        execution_record,
        trade_intent=TradeIntent(
            run_id="run_exec_audit",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=0.0,
            risk_checks_passed=False,
            no_trade_reasons=["capital_frozen", "capital_freeze_reason:manual_hold"],
        ),
    )

    assert report.runtime_guard["capital_frozen"] is True
    assert "capital_frozen" in report.runtime_guard["blocked_reasons"]
    assert report.runtime_guard["incident_summary"].startswith("blocked=")
    assert report.runtime_guard["requested_mode"] == "live"
    assert report.blocked_reasons
    assert report.order.status_history[:2] == ["submitted", "acknowledged"]
    assert report.order.order_source == "paper_trade_simulator"


def test_bounded_market_execution_blocks_when_projection_is_expired_at_action_time() -> None:
    market = _descriptor()
    expired_projection = ExecutionProjection(
        run_id="run_bounded_projection",
        venue=VenueName.polymarket,
        market_id=market.market_id,
        requested_mode=ExecutionProjectionMode.live,
        projected_mode=ExecutionProjectionOutcome.live,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.live,
        highest_safe_requested_mode=ExecutionProjectionMode.live,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.live,
        blocking_reasons=[],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1),
    )
    resolution_guard = ResolutionGuardReport(
        market_id=market.market_id,
        venue=market.venue.value,
        approved=True,
        can_forecast=True,
        manual_review_required=False,
        reasons=["resolution_policy_clear"],
        ambiguity_flags=[],
        official_source=market.resolution_source,
        status=ResolutionStatus.clear,
        metadata={},
    )
    executable_edge = ExecutableEdge(
        market_ref=market.market_id,
        raw_edge_bps=120.0,
        fees_bps=20.0,
        slippage_bps=10.0,
        hedge_risk_bps=5.0,
        confidence=0.9,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1),
    )

    report = BoundedMarketExecutionEngine().execute(
        MarketExecutionRequest(
            run_id="run_bounded_projection",
            market=market,
            snapshot=_snapshot(),
            venue=VenueName.polymarket,
            market_id="pm_exec",
            requested_notional=12.0,
            dry_run=False,
            execution_projection=expired_projection,
            resolution_guard=resolution_guard,
            executable_edge=executable_edge,
        )
    )

    assert report.status == MarketExecutionStatus.cancelled
    assert report.cancelled_reason is not None
    assert "execution_projection_expired" in report.cancelled_reason
    assert report.action_time_guard.get("projection_valid", False) is False
    assert "execution_projection_expired" in report.action_time_guard["blocked_reasons"]
    assert report.order.status_history == ["submitted", "acknowledged", "cancelled"]
    assert report.order.order_source == "action_time_guard"
    assert report.order.order_trace_kind == "local_surrogate"
    assert report.order.order_flow == "submitted->acknowledged->cancelled"


def test_market_execution_materialize_carries_action_time_guard_from_live_execution(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_action_guard",
        market=_descriptor(),
        snapshot=_snapshot(),
        recommendation=_recommendation(),
        requested_mode="live",
        requested_stake=12.0,
        dry_run=False,
        auth=ExecutionAuthContext(
            principal="tester",
            authorized=True,
            compliance_approved=True,
            scopes=["prediction_markets:execute"],
        ),
        executable_edge=ExecutableEdge(
            market_ref="pm_exec",
            raw_edge_bps=30.0,
            fees_bps=20.0,
            slippage_bps=15.0,
            hedge_risk_bps=10.0,
            confidence=0.4,
            expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1),
        ),
    )
    live_record = engine.execute(request, persist=False)
    report = MarketExecutionEngine().materialize(
        live_record,
        trade_intent=TradeIntent(
            run_id="run_action_guard",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=0.0,
            risk_checks_passed=False,
            no_trade_reasons=live_record.no_trade_reasons,
        ),
    )

    assert live_record.status == LiveExecutionStatus.blocked
    assert live_record.action_time_guard["executable_edge_valid"] is False
    assert "executable_edge_not_executable" in live_record.action_time_guard["blocked_reasons"]
    assert report.action_time_guard["blocked_reasons"] == live_record.action_time_guard["blocked_reasons"]
    assert "executable_edge_not_executable" in report.blocked_reasons
    assert report.order.status_history[0] == "submitted"
    assert report.order.order_source == "paper_trade_simulator"


def test_market_execution_materialize_preserves_cancelled_live_execution_audit(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
        )
    )
    live_record = engine.execute(
        LiveExecutionRequest(
            run_id="run_cancelled_live",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_mode="live",
            requested_stake=12.0,
            dry_run=False,
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
        ).model_copy(
        update={
            "status": MarketExecutionStatus.cancelled,
            "venue_order_status": "cancelled",
            "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
            "venue_order_cancel_reason": "venue_cancelled",
            "venue_order_cancelled_by": "venue_api",
            "venue_order_cancelled_at": datetime.now(timezone.utc).replace(microsecond=0),
            "paper_trade": None,
        }
    )

    store = MarketExecutionStore(base_dir=tmp_path / "prediction_markets")
    report = MarketExecutionEngine().materialize(live_record, persist=True, store=store)
    loaded = store.load(report.report_id)

    assert report.status == MarketExecutionStatus.cancelled
    assert report.order.status == "cancelled"
    assert report.order.cancelled_reason == "venue_cancelled"
    assert report.order.cancelled_by == "venue_api"
    assert report.order.cancelled_at is not None
    assert report.order.acknowledged_reason == "venue_cancelled"
    assert report.order.acknowledged_by == "venue_api"
    assert report.order.acknowledged_at == report.order.cancelled_at
    assert report.order.status_history == ["submitted", "acknowledged", "cancelled"]
    assert report.order.order_flow == "submitted->acknowledged->cancelled"
    assert report.fills == []
    assert report.positions == []
    assert report.live_execution_status == "cancelled"
    assert report.metadata["order_trace_audit"]["venue_order_status"] == "cancelled"
    assert report.metadata["order_trace_audit"]["transport_mode"] == "dry_run"
    assert report.order.metadata["order_trace_audit"] == report.metadata["order_trace_audit"]
    assert loaded.order.status == "cancelled"
    assert loaded.order.cancelled_reason == "venue_cancelled"
    assert loaded.fills == []
    assert loaded.positions == []


def test_market_execution_exposes_structured_lifecycle_and_audit_models() -> None:
    order = MarketExecutionOrder(
        run_id="run_structured_models",
        market_id="pm_exec",
        venue=VenueName.polymarket,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=4.0,
        requested_notional=10.0,
        metadata={
            "venue_order_id": "external_structured_01",
            "venue_order_source": "external",
            "venue_order_status": "submitted",
            "venue_order_status_history": ["submitted", "acknowledged"],
            "venue_order_acknowledged_at": "2026-04-08T13:00:00+00:00",
            "venue_order_acknowledged_by": "mock_transport",
            "venue_order_acknowledged_reason": "submitted",
            "venue_order_path": "external_live_api",
            "venue_order_cancel_path": "external_live_cancel_api",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged",
        },
    )
    report = MarketExecutionRecord.from_cancelled(
        order=order,
        mode=MarketExecutionMode.bounded_live,
        reason="manual_cancel",
        cancelled_by="ops_bot",
    )

    order_lifecycle = report.order.lifecycle_snapshot_model
    report_lifecycle = report.lifecycle_snapshot_model
    audit = report.order_trace_audit_model

    assert isinstance(order_lifecycle, MarketExecutionOrderLifecycleSnapshot)
    assert isinstance(report_lifecycle, MarketExecutionOrderLifecycleSnapshot)
    assert isinstance(audit, MarketExecutionOrderTraceAudit)
    assert order_lifecycle.venue_order_id == "external_structured_01"
    assert report_lifecycle.venue_order_status == "cancelled"
    assert report_lifecycle.venue_order_trace_kind == "external_live"
    assert report_lifecycle.venue_order_ack_path == "external_live_api"
    assert report_lifecycle.venue_order_flow == "submitted->acknowledged->cancelled"
    assert audit.transport_mode == "live"
    assert audit.venue_order_status == "cancelled"
    assert audit.venue_order_trace_kind == "external_live"
    assert audit.venue_order_ack_path == report.order.metadata["venue_order_path"]


def test_market_execution_materialize_preserves_dry_run_live_status(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    live_record = engine.execute(
        LiveExecutionRequest(
            run_id="run_dry_materialize",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_stake=12.0,
            dry_run=True,
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    )

    report = MarketExecutionEngine().materialize(
        live_record,
        trade_intent=TradeIntent(
            run_id="run_dry_materialize",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=12.0,
            limit_price=0.54,
            forecast_ref="fcst_exec",
            recommendation_ref="mrec_exec",
            risk_checks_passed=True,
        ),
    )

    assert live_record.status.value == "dry_run"
    assert report.mode == MarketExecutionMode.bounded_dry_run
    assert report.live_execution_status == "dry_run"
    assert report.metadata["live_execution_status"] == "dry_run"
    assert report.order.metadata["live_execution_status"] == "dry_run"
    assert report.metadata["order_trace_audit"]["live_execution_status"] == "dry_run"
    assert report.order.metadata["order_trace_audit"] == report.metadata["order_trace_audit"]
    assert report.cancelled_reason is None
    assert report.order.status_history[:2] == ["submitted", "acknowledged"]
    assert report.order.order_source == "paper_trade_simulator"
    assert report.status in {MarketExecutionStatus.filled, MarketExecutionStatus.partial, MarketExecutionStatus.rejected}


def test_market_execution_materialize_blocks_when_execution_projection_is_missing(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
        )
    )
    live_record = engine.execute(
        LiveExecutionRequest(
            run_id="run_missing_projection",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_stake=12.0,
            dry_run=False,
            requested_mode="live",
            execution_readiness=ExecutionReadiness(
                run_id="run_missing_projection",
                market_id="pm_exec",
                venue=VenueName.polymarket,
                decision_action=DecisionAction.bet,
                side=TradeSide.yes,
                size_usd=12.0,
                limit_price=0.54,
                confidence=0.88,
                edge_after_fees_bps=420.0,
                risk_checks_passed=True,
                blocked_reasons=[],
                no_trade_reasons=[],
                ready_to_live=True,
                ready_to_paper=True,
                ready_to_execute=True,
                can_materialize_trade_intent=True,
                metadata={"live_gate_passed": True},
            ),
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    ).model_copy(update={"execution_projection": None})

    report = MarketExecutionEngine().materialize(
        live_record,
        trade_intent=TradeIntent(
            run_id="run_missing_projection",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=12.0,
            limit_price=0.54,
            forecast_ref="fcst_exec",
            recommendation_ref="mrec_exec",
            risk_checks_passed=True,
        ),
    )

    assert report.status == MarketExecutionStatus.blocked
    assert "missing_execution_projection" in report.action_time_guard["blocked_reasons"]
    assert "missing_execution_projection" in (report.blocked_reasons or [])


def test_market_execution_persists_order_fill_and_positions(tmp_path: Path) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
            min_confidence=0.2,
            min_edge_bps=1.0,
        )
    )
    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_exec_live",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_stake=15.0,
            dry_run=False,
            requested_mode="live",
            execution_readiness=ExecutionReadiness(
                run_id="run_exec_live",
                market_id="pm_exec",
                venue=VenueName.polymarket,
                decision_action=DecisionAction.bet,
                side=TradeSide.yes,
                size_usd=15.0,
                limit_price=0.54,
                confidence=0.88,
                edge_after_fees_bps=420.0,
                risk_checks_passed=True,
                blocked_reasons=[],
                no_trade_reasons=[],
                ready_to_live=True,
                ready_to_paper=True,
                ready_to_execute=True,
                can_materialize_trade_intent=True,
                metadata={"live_gate_passed": True},
            ),
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    )
    report = MarketExecutionEngine().materialize(
        record,
        trade_intent=TradeIntent(
            run_id="run_exec_live",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=15.0,
            limit_price=0.54,
            forecast_ref="fcst_exec",
            recommendation_ref="mrec_exec",
            risk_checks_passed=True,
        ),
        persist=True,
        store=MarketExecutionStore(base_dir=tmp_path / "prediction_markets"),
    )

    loaded = MarketExecutionStore(base_dir=tmp_path / "prediction_markets").load(report.report_id)
    assert loaded.order.execution_id == record.execution_id
    assert loaded.order.acknowledged_at is not None
    assert loaded.order.acknowledged_by == "paper_trade_simulator"
    assert loaded.order.status in {"filled", "partial", "rejected"}
    assert loaded.order.status_history[:2] == ["submitted", "acknowledged"]
    assert loaded.order.order_source == "paper_trade_simulator"
    assert report.fill_count == len(report.fills)
    assert report.position_count == len(report.positions)
    assert loaded.fills
    assert loaded.positions
    assert loaded.trade_intent_ref is not None
    assert loaded.execution_projection_ref == record.execution_projection.projection_id


def test_market_execution_materialize_preserves_attempted_live_audit_from_bound_transport() -> None:
    submitted_calls: list[tuple[object, object]] = []

    def _submit_order(order, payload):  # noqa: ANN001
        submitted_calls.append((order, payload))
        return {
            "venue_order_id": "external_venue_order_live_002",
            "venue_order_source": "external",
            "venue_order_status": "submitted",
            "venue_order_status_history": ["submitted", "acknowledged"],
            "venue_order_acknowledged_at": "2026-04-08T14:00:00+00:00",
            "venue_order_acknowledged_by": "polymarket_api",
            "venue_order_acknowledged_reason": "submitted",
            "venue_order_path": "external_live_api",
            "venue_order_cancel_path": "external_live_cancel_api",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged",
        }

    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
            min_confidence=0.2,
            min_edge_bps=1.0,
        ),
        venue_order_submitters={VenueName.polymarket: _submit_order},
    )
    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_exec_live_bound",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_stake=15.0,
            dry_run=False,
            requested_mode="live",
            execution_readiness=ExecutionReadiness(
                run_id="run_exec_live_bound",
                market_id="pm_exec",
                venue=VenueName.polymarket,
                decision_action=DecisionAction.bet,
                side=TradeSide.yes,
                size_usd=15.0,
                limit_price=0.54,
                confidence=0.88,
                edge_after_fees_bps=420.0,
                risk_checks_passed=True,
                blocked_reasons=[],
                no_trade_reasons=[],
                ready_to_live=True,
                ready_to_paper=True,
                ready_to_execute=True,
                can_materialize_trade_intent=True,
                metadata={"live_gate_passed": True},
            ),
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    )

    report = MarketExecutionEngine().materialize(
        record,
        trade_intent=TradeIntent(
            run_id="run_exec_live_bound",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=15.0,
            limit_price=0.54,
            forecast_ref="fcst_exec",
            recommendation_ref="mrec_exec",
            risk_checks_passed=True,
        ),
    )

    audit = report.order_trace_audit_model

    assert submitted_calls
    assert audit is not None
    assert audit.transport_mode == "live"
    assert audit.live_preflight_passed is True
    assert audit.attempted_live is True
    assert audit.live_submission_performed is True
    assert audit.live_submission_phase == "performed_live"
    assert audit.venue_order_submission_state == "venue_submitted"
    assert audit.venue_order_ack_state == "venue_acknowledged"
    assert audit.venue_order_execution_state == "venue_acknowledged"
    assert audit.venue_order_ack_path == record.metadata["venue_order_path"]
    assert audit.ack_auditable is True
    assert report.venue_order_ack_path == record.metadata["venue_order_path"]
    assert report.live_preflight_passed is True
    assert report.attempted_live is True
    assert report.live_submission_performed is True
    assert report.live_submission_phase == "performed_live"
    assert report.venue_live_submission_bound is True
    assert report.operator_bound is True
    assert report.live_runtime_honest_mode == "live"
    assert report.live_submission_failed is None
    assert report.live_acknowledged is True
    assert report.live_cancel_observed is False
    assert report.live_submission_receipt["transport_mode"] == "live"
    assert report.venue_submission_state == "venue_submitted"
    assert report.venue_ack_state == "venue_acknowledged"
    assert report.venue_execution_state == "venue_acknowledged"
    assert report.venue_submission_receipt["venue_order_submission_state"] == "venue_submitted"
    assert report.venue_cancellation_receipt["venue_order_cancel_state"] == "not_cancelled"
    assert report.live_transport_readiness["transport_mode"] == "live"
    assert report.live_transport_readiness["operator_bound"] is True
    assert report.venue_live_configuration_snapshot["runtime_ready"] is True
    assert report.live_route_evidence["selected_order_source"] == "external"
    assert report.selected_live_path_receipt["selected_transport_mode"] == "live"
    assert report.order_trace_artifacts["live_submission_receipt"]["acknowledged"] is True
    assert report.live_attempt_timeline["phase_history"][0] == "preflight_ready"
    assert report.live_attempt_timeline["attempted_at"] is not None
    assert report.live_blocker_snapshot["is_blocked"] is False
    assert report.live_blocker_snapshot["operator_bound"] is True
    assert report.selected_live_path_audit["selected_live_path_receipt"]["selected_transport_mode"] == "live"
    assert report.live_lifecycle_snapshot["venue_order_trace_kind"] == "external_live"
    assert report.order.metadata["venue_order_ack_path"] == audit.venue_order_ack_path
    assert report.metadata["order_trace_audit"]["attempted_live"] is True


def test_market_execution_materialize_preserves_failed_live_attempt_evidence() -> None:
    submitted_calls: list[tuple[object, object]] = []

    def _submit_order(order, payload):  # noqa: ANN001
        submitted_calls.append((order, payload))
        raise RuntimeError("venue unavailable")

    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            allow_live_execution=True,
            dry_run_enabled=False,
            allowed_venues={VenueName.polymarket},
            min_confidence=0.2,
            min_edge_bps=1.0,
        ),
        venue_order_submitters={VenueName.polymarket: _submit_order},
    )
    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_exec_live_failed",
            market=_descriptor(),
            snapshot=_snapshot(),
            recommendation=_recommendation(),
            requested_stake=15.0,
            dry_run=False,
            requested_mode="live",
            execution_readiness=ExecutionReadiness(
                run_id="run_exec_live_failed",
                market_id="pm_exec",
                venue=VenueName.polymarket,
                decision_action=DecisionAction.bet,
                side=TradeSide.yes,
                size_usd=15.0,
                limit_price=0.54,
                confidence=0.88,
                edge_after_fees_bps=420.0,
                risk_checks_passed=True,
                blocked_reasons=[],
                no_trade_reasons=[],
                ready_to_live=True,
                ready_to_paper=True,
                ready_to_execute=True,
                can_materialize_trade_intent=True,
                metadata={"live_gate_passed": True},
            ),
            auth=ExecutionAuthContext(
                principal="tester",
                authorized=True,
                compliance_approved=True,
                scopes=["prediction_markets:execute"],
            ),
        ),
        persist=False,
    )

    report = MarketExecutionEngine().materialize(
        record,
        trade_intent=TradeIntent(
            run_id="run_exec_live_failed",
            venue=VenueName.polymarket,
            market_id="pm_exec",
            side=TradeSide.yes,
            size_usd=15.0,
            limit_price=0.54,
            forecast_ref="fcst_exec",
            recommendation_ref="mrec_exec",
            risk_checks_passed=True,
        ),
    )

    assert submitted_calls
    assert report.attempted_live is True
    assert report.live_submission_performed is False
    assert report.live_submission_phase == "attempted_live_failed"
    assert report.venue_live_submission_bound is True
    assert report.operator_bound is True
    assert report.live_runtime_honest_mode == "live"
    assert report.live_submission_failed == "RuntimeError"
    assert report.live_submission_receipt["submission_error_type"] == "RuntimeError"
    assert report.live_submission_receipt["attempted_live"] is True
    assert report.live_submission_receipt["live_submission_performed"] is False
    assert report.live_submission_receipt["runtime_honest_mode"] == "live"
    assert report.live_submission_receipt["operator_bound"] is True
    assert report.live_transport_readiness["live_submission_phase"] == "attempted_live_failed"
    assert report.live_route_evidence["live_submission_failed"] == "RuntimeError"
    assert report.selected_live_path_receipt["submission_error_type"] == "RuntimeError"
    assert report.selected_live_path_receipt["operator_bound"] is True
    assert report.order_trace_artifacts["live_submission_receipt"]["submission_error_type"] == "RuntimeError"
    assert report.live_attempt_timeline["phase_history"][-1] == "attempted_live_failed"
    assert report.live_attempt_timeline["failed_at"] is not None
    assert any("RuntimeError" in reason for reason in report.live_blocker_snapshot["transport_failures"])
    assert report.selected_live_path_audit["selected_live_path_receipt"]["submission_error_type"] == "RuntimeError"
    assert report.live_lifecycle_snapshot["submission_error_type"] == "RuntimeError"
    assert report.live_blocker_snapshot["blocked_reason_summary"]
    assert report.live_blocker_snapshot["route_state"] in {"blocked", "degraded", "available"}
    assert report.metadata["order_trace_audit"]["attempted_live"] is True
    assert report.metadata["order_trace_audit"]["live_submission_performed"] is False
