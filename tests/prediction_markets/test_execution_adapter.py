from __future__ import annotations

from prediction_markets.adapters import (
    ClobCancelOrderRequest,
    ClobPlaceOrderRequest,
    KalshiExecutionAdapter,
    PolymarketExecutionAdapter,
    bind_venue_order_transport,
    build_venue_order_lifecycle,
    build_market_execution_adapter,
    build_execution_adapter,
)
from prediction_markets.adapters import MarketExecutionRequest
from prediction_markets.models import MarketDescriptor, MarketOrderBook, MarketSnapshot, MarketStatus, OrderBookLevel, TradeSide, VenueName, VenueType


def _market(*, venue: VenueName, market_id: str = "pm_exec") -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
    )


def _snapshot(*, venue: VenueName, market_id: str = "pm_exec") -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        price_yes=0.52,
        price_no=0.48,
        midpoint_yes=0.52,
        spread_bps=25.0,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.51, size=100.0)],
            asks=[OrderBookLevel(price=0.53, size=100.0)],
        ),
        liquidity=10_000.0,
        volume=50_000.0,
    )


def test_build_execution_adapter_selects_venue_specific_implementations() -> None:
    polymarket = build_execution_adapter(VenueName.polymarket)
    kalshi = build_execution_adapter(VenueName.kalshi)

    assert isinstance(polymarket, PolymarketExecutionAdapter)
    assert isinstance(kalshi, KalshiExecutionAdapter)


def test_polymarket_execution_adapter_allows_dry_run_without_live_authorization() -> None:
    adapter = build_execution_adapter(VenueName.polymarket)
    market = _market(venue=VenueName.polymarket)

    plan = adapter.build_execution_plan(
        market=market,
        dry_run=True,
        allow_live_execution=True,
        authorized=False,
        compliance_approved=False,
        required_scope="prediction_markets:execute",
    )

    assert plan.allowed is True
    assert plan.dry_run_requested is True
    assert plan.dry_run_effective is True
    assert plan.auth_required is False
    assert plan.compliance_required is False
    assert plan.live_execution_supported is True
    assert plan.bounded_execution_supported is True
    assert plan.market_execution_supported is True
    assert plan.execution_mode == "dry_run"
    assert plan.blocked_reasons == []


def test_polymarket_execution_adapter_surfaces_env_based_runtime_config(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "https://example.com/polymarket/orders")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "https://example.com/polymarket/orders/cancel")
    monkeypatch.setenv("POLYMARKET_EXECUTION_BOUNDED_ORDER_PATH", "https://example.com/polymarket/bounded/orders")
    monkeypatch.setenv("POLYMARKET_EXECUTION_BOUNDED_CANCEL_PATH", "https://example.com/polymarket/bounded/orders/cancel")

    adapter = build_execution_adapter(VenueName.polymarket)
    market = _market(venue=VenueName.polymarket)

    capability = adapter.describe_execution_capabilities()
    plan = adapter.build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )

    assert adapter.backend_mode == "live"
    assert capability.live_order_path == "https://example.com/polymarket/orders"
    assert capability.cancel_order_path == "https://example.com/polymarket/orders/cancel"
    assert capability.metadata["runtime_mode"] == "live"
    assert capability.metadata["runtime_ready"] is True
    assert capability.metadata["ready_for_live_execution"] is True
    assert capability.metadata["mock_transport"] is False
    assert capability.metadata["missing_requirements"] == []
    assert capability.metadata["credential_evidence"]["auth_configured"] is True
    assert capability.metadata["configuration_evidence"]["live_order_path"] == "https://example.com/polymarket/orders"
    assert capability.metadata["readiness_evidence"]["runtime_ready"] is True
    assert capability.metadata["order_paths"]["bounded"] == "https://example.com/polymarket/bounded/orders"
    assert plan.venue_order_path == "https://example.com/polymarket/orders"
    assert plan.venue_order_cancel_path == "https://example.com/polymarket/orders/cancel"
    assert plan.metadata["runtime_mode"] == "live"
    assert plan.metadata["runtime_ready"] is True
    assert plan.metadata["ready_for_live_execution"] is True
    assert plan.metadata["auth_configured"] is True
    assert plan.metadata["missing_requirements"] == []
    assert plan.metadata["credential_evidence"]["auth_passed"] is True
    assert plan.metadata["configuration_evidence"]["venue_order_path"] == "https://example.com/polymarket/orders"
    assert plan.metadata["readiness_evidence"]["live_execution_supported"] is True
    assert plan.allowed is True


def test_kalshi_execution_adapter_blocks_live_execution_cleanly() -> None:
    adapter = build_execution_adapter(VenueName.kalshi)
    market = _market(venue=VenueName.kalshi, market_id="kalshi_exec")

    plan = adapter.build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
    )

    assert plan.allowed is False
    assert plan.live_execution_requested is True
    assert plan.live_execution_supported is False
    assert plan.bounded_execution_supported is True
    assert plan.execution_mode == "bounded_live"
    assert "live_execution_unsupported:kalshi" in plan.blocked_reasons


def test_execution_adapter_blocks_compliance_constraints_explicitly() -> None:
    adapter = build_execution_adapter(VenueName.polymarket)
    market = _market(venue=VenueName.polymarket)

    plan = adapter.build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        jurisdiction="fr",
        account_type="demo",
        automation_allowed=False,
        rate_limit_ok=False,
        tos_accepted=False,
        allowed_jurisdictions={"us"},
        allowed_account_types={"retail"},
        require_automation_allowed=True,
        require_rate_limit_ok=True,
        require_tos_accepted=True,
    )

    assert plan.allowed is False
    assert plan.jurisdiction_required is True
    assert plan.account_type_required is True
    assert plan.automation_required is True
    assert plan.rate_limit_required is True
    assert plan.tos_required is True
    assert "jurisdiction_not_allowed" in plan.blocked_reasons
    assert "account_type_not_allowed" in plan.blocked_reasons
    assert "automation_not_allowed" in plan.blocked_reasons
    assert "rate_limit_exceeded" in plan.blocked_reasons
    assert "tos_not_accepted" in plan.blocked_reasons


def test_market_execution_adapter_exposes_bounded_capabilities() -> None:
    polymarket = build_market_execution_adapter(VenueName.polymarket)
    kalshi = build_market_execution_adapter(VenueName.kalshi)

    polymarket_capabilities = polymarket.describe_market_execution_capabilities()
    kalshi_capabilities = kalshi.describe_market_execution_capabilities()

    assert polymarket_capabilities.bounded_execution_supported is True
    assert polymarket_capabilities.market_execution_supported is True
    assert kalshi_capabilities.bounded_execution_supported is True
    assert kalshi_capabilities.market_execution_supported is True


def test_build_venue_order_lifecycle_falls_back_to_local_surrogate_when_unconfigured() -> None:
    lifecycle = build_venue_order_lifecycle(
        order_id="mord_exec_123",
        execution_id="mexec_exec_123",
        request_metadata={},
        status="submitted",
        live_execution_supported=False,
    )

    assert lifecycle.venue_order_configured is False
    assert lifecycle.venue_order_source == "local_surrogate"
    assert lifecycle.venue_order_id == "venue_mexec_exec_123_mord_exec_123"
    assert lifecycle.venue_order_status == "submitted"
    assert lifecycle.venue_order_trace_kind == "local_surrogate"
    assert lifecycle.venue_order_flow == "submitted"


def test_build_venue_order_lifecycle_preserves_external_ack_and_terminal_history() -> None:
    lifecycle = build_venue_order_lifecycle(
        order_id="mord_exec_124",
        execution_id="mexec_exec_124",
        request_metadata={
            "venue_order_id": "external_venue_order_124",
            "venue_order_source": "external",
            "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
            "venue_order_acknowledged_at": "2026-04-08T12:00:00+00:00",
            "venue_order_acknowledged_by": "venue_api",
            "venue_order_acknowledged_reason": "user_cancelled",
            "venue_order_cancel_reason": "user_cancelled",
            "venue_order_cancelled_at": "2026-04-08T12:05:00+00:00",
            "venue_order_cancelled_by": "venue_api",
        },
        status="submitted",
        live_execution_supported=True,
    )

    assert lifecycle.venue_order_configured is True
    assert lifecycle.venue_order_source == "external"
    assert lifecycle.venue_order_status == "cancelled"
    assert lifecycle.venue_order_status_history == ["submitted", "acknowledged", "cancelled"]
    assert lifecycle.venue_order_submission_state == "venue_submitted"
    assert lifecycle.venue_order_ack_state == "venue_acknowledged"
    assert lifecycle.venue_order_cancel_state == "venue_cancelled"
    assert lifecycle.venue_order_execution_state == "venue_cancelled"
    assert lifecycle.venue_order_acknowledged_at is not None
    assert lifecycle.venue_order_acknowledged_by == "venue_api"
    assert lifecycle.venue_order_acknowledged_reason == "user_cancelled"
    assert lifecycle.venue_order_cancelled_by == "venue_api"
    assert lifecycle.venue_order_flow == "submitted->acknowledged->cancelled"
    assert lifecycle.venue_order_trace_kind == "external_live"
    assert lifecycle.metadata["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert lifecycle.metadata["venue_order_trace_kind"] == "external_live"


def test_market_execution_adapter_attaches_venue_order_lifecycle_to_bounded_record() -> None:
    adapter = build_market_execution_adapter(VenueName.polymarket)
    request = MarketExecutionRequest(
        run_id="run_exec_bounded",
        market_id="pm_exec",
        venue=VenueName.polymarket,
        snapshot=_snapshot(venue=VenueName.polymarket),
        requested_notional=12.0,
        requested_quantity=10.0,
        dry_run=True,
        metadata={"venue_order_id": "external_venue_order_77"},
    )

    record = adapter.execute_bounded(request)

    assert record.order.metadata["venue_order_id"] == "external_venue_order_77"
    assert record.order.metadata["venue_order_source"] == "external"
    assert record.order.metadata["venue_order_configured"] is True


def test_polymarket_execution_adapter_binds_submission_and_cancellation_receipts(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "https://example.com/polymarket/orders")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "https://example.com/polymarket/orders/cancel")

    submitted_calls: list[tuple[object, object]] = []
    cancelled_calls: list[tuple[object, object]] = []

    def _submit(order, payload):  # noqa: ANN001
        submitted_calls.append((order, payload))
        return {
            "venue_order_id": "external_venue_order_submit_001",
            "venue_order_source": "external",
            "venue_order_status": "submitted",
            "venue_order_status_history": ["submitted", "acknowledged"],
            "venue_order_acknowledged_at": "2026-04-08T12:30:00+00:00",
            "venue_order_acknowledged_by": "polymarket_api",
            "venue_order_acknowledged_reason": "submitted",
            "venue_order_path": "https://example.com/polymarket/orders",
            "venue_order_cancel_path": "https://example.com/polymarket/orders/cancel",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged",
            "venue_order_submission_state": "venue_submitted",
            "venue_order_ack_state": "venue_acknowledged",
            "venue_order_cancel_state": "not_cancelled",
            "venue_order_execution_state": "venue_acknowledged",
        }

    def _cancel(order, payload):  # noqa: ANN001
        cancelled_calls.append((order, payload))
        return {
            "venue_order_id": "external_venue_order_submit_001",
            "venue_order_source": "external",
            "venue_order_status": "cancelled",
            "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
            "venue_order_acknowledged_at": "2026-04-08T12:30:00+00:00",
            "venue_order_acknowledged_by": "polymarket_api",
            "venue_order_acknowledged_reason": "manual_cancel",
            "venue_order_cancel_reason": "manual_cancel",
            "venue_order_cancelled_at": "2026-04-08T12:35:00+00:00",
            "venue_order_cancelled_by": "polymarket_api",
            "venue_order_path": "https://example.com/polymarket/orders",
            "venue_order_cancel_path": "https://example.com/polymarket/orders/cancel",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged->cancelled",
            "venue_order_submission_state": "venue_submitted",
            "venue_order_ack_state": "venue_acknowledged",
            "venue_order_cancel_state": "venue_cancelled",
            "venue_order_execution_state": "venue_cancelled",
        }

    adapter = bind_venue_order_transport(build_execution_adapter(VenueName.polymarket), order_submitter=_submit, cancel_submitter=_cancel)
    market = _market(venue=VenueName.polymarket)

    submit_trace = adapter.place_order(
        market=market,
        run_id="run_receipt_submit",
        requested_notional=12.0,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )
    cancel_trace = adapter.cancel_order(
        submit_trace.order,
        reason="manual_cancel",
        cancelled_by="tester",
    )

    assert submitted_calls
    assert cancel_trace is not None
    assert submit_trace.order.metadata["venue_order_submission_state"] == "venue_submitted"
    assert submit_trace.order.metadata["venue_order_ack_state"] == "venue_acknowledged"
    assert submit_trace.order.metadata["venue_order_execution_state"] == "venue_acknowledged"
    assert submit_trace.submitted_payload is not None
    assert submit_trace.metadata["order_trace_audit"]["venue_order_submission_state"] == "venue_submitted"
    assert submit_trace.metadata["order_trace_audit"]["operator_bound"] is True
    assert submit_trace.metadata["live_submission_receipt"]["operator_bound"] is True
    assert cancel_trace.order.metadata["venue_order_cancel_state"] == "venue_cancelled"
    assert cancel_trace.order.metadata["venue_order_execution_state"] == "venue_cancelled"
    assert cancel_trace.cancelled_payload is not None
    assert cancelled_calls
    assert cancel_trace.order.metadata["venue_order_id"] == "external_venue_order_submit_001"
    assert cancel_trace.venue_order_lifecycle["venue_order_source"] == "external"


def test_standardized_execution_adapter_transport_wraps_place_and_cancel_with_structured_clob_traces(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "https://example.com/polymarket/orders")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "https://example.com/polymarket/orders/cancel")

    adapter = build_execution_adapter(VenueName.polymarket)
    submitted_payloads: list[dict[str, object]] = []
    cancelled_payloads: list[dict[str, object]] = []
    bind_venue_order_transport(
        adapter,
        order_submitter=lambda order, payload: submitted_payloads.append(payload) or {
            "venue_order_id": f"external_{order.order_id}",
            "venue_order_source": "external",
            "venue_order_status": "submitted",
            "venue_order_status_history": ["submitted", "acknowledged"],
            "venue_order_acknowledged_at": "2026-04-08T12:00:00+00:00",
            "venue_order_acknowledged_by": "venue_api",
            "venue_order_acknowledged_reason": "submitted",
            "venue_order_path": "external_live_api",
            "venue_order_cancel_path": "external_live_cancel_api",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged",
        },
        cancel_submitter=lambda order, payload: cancelled_payloads.append(payload) or {
            "venue_order_id": f"external_{order.order_id}",
            "venue_order_source": "external",
            "venue_order_status": "cancelled",
            "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
            "venue_order_acknowledged_at": "2026-04-08T12:00:00+00:00",
            "venue_order_acknowledged_by": "venue_api",
            "venue_order_acknowledged_reason": "manual_cancel",
            "venue_order_cancel_reason": "manual_cancel",
            "venue_order_cancelled_at": "2026-04-08T12:05:00+00:00",
            "venue_order_cancelled_by": "venue_api",
            "venue_order_path": "external_live_api",
            "venue_order_cancel_path": "external_live_cancel_api",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged->cancelled",
        },
    )

    market = _market(venue=VenueName.polymarket, market_id="pm_exec_transport")
    place_trace = adapter.place_order(
        market=market,
        run_id="run_exec_transport",
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=5.0,
        requested_notional=11.0,
        limit_price=0.51,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
        metadata={"request_marker": "connector_round_trip"},
    )

    assert isinstance(adapter, PolymarketExecutionAdapter)
    assert submitted_payloads
    assert submitted_payloads[0]["metadata"]["request_marker"] == "connector_round_trip"
    assert place_trace.live_submission_performed is True
    assert place_trace.order.metadata["venue_order_id"] == f"external_{place_trace.order.order_id}"
    assert place_trace.order.metadata["venue_order_trace_kind"] == "external_live"
    assert place_trace.metadata["order_trace_audit"]["transport_mode"] == "live"
    assert place_trace.metadata["order_trace_audit"]["venue_order_trace_kind"] == "external_live"
    assert place_trace.metadata["order_trace_audit"]["operator_bound"] is True
    assert place_trace.metadata["live_submission_receipt"]["operator_bound"] is True

    cancel_trace = adapter.cancel_order(place_trace.order, reason="manual_cancel")
    assert cancelled_payloads
    assert cancelled_payloads[0]["metadata"]["cancel_reason"] == "manual_cancel"
    assert cancel_trace.live_submission_performed is True
    assert cancel_trace.order.cancelled_reason == "manual_cancel"
    assert cancel_trace.order.metadata["venue_order_status"] == "cancelled"
    assert cancel_trace.order.metadata["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert cancel_trace.metadata["order_trace_audit"]["transport_mode"] == "live"
    assert cancel_trace.metadata["order_trace_audit"]["venue_order_status"] == "cancelled"
    assert cancel_trace.metadata["order_trace_audit"]["operator_bound"] is True
    assert cancel_trace.metadata["venue_cancellation_receipt"]["operator_bound"] is True


def test_standardized_execution_adapter_accepts_structured_clob_requests_and_transport_object(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "token-456")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "https://example.com/polymarket/orders")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "https://example.com/polymarket/orders/cancel")

    submitted_payloads: list[dict[str, object]] = []
    cancelled_payloads: list[dict[str, object]] = []

    class _MockTransport:
        def place_order(self, order, payload):  # noqa: ANN001
            submitted_payloads.append(payload)
            return {
                "venue_order_id": f"transport_{order.order_id}",
                "venue_order_source": "external",
                "venue_order_status": "submitted",
                "venue_order_status_history": ["submitted", "acknowledged"],
                "venue_order_acknowledged_at": "2026-04-08T12:30:00+00:00",
                "venue_order_acknowledged_by": "mock_transport",
                "venue_order_acknowledged_reason": "submitted",
                "venue_order_path": "external_live_api",
                "venue_order_cancel_path": "external_live_cancel_api",
                "venue_order_trace_kind": "external_live",
                "venue_order_flow": "submitted->acknowledged",
            }

        def cancel_order(self, order, payload):  # noqa: ANN001
            cancelled_payloads.append(payload)
            return {
                "venue_order_id": f"transport_{order.order_id}",
                "venue_order_source": "external",
                "venue_order_status": "cancelled",
                "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
                "venue_order_acknowledged_at": "2026-04-08T12:30:00+00:00",
                "venue_order_acknowledged_by": "mock_transport",
                "venue_order_acknowledged_reason": "manual_cancel",
                "venue_order_cancel_reason": "manual_cancel",
                "venue_order_cancelled_at": "2026-04-08T12:31:00+00:00",
                "venue_order_cancelled_by": "mock_transport",
                "venue_order_path": "external_live_api",
                "venue_order_cancel_path": "external_live_cancel_api",
                "venue_order_trace_kind": "external_live",
                "venue_order_flow": "submitted->acknowledged->cancelled",
            }

    adapter = build_execution_adapter(VenueName.polymarket)
    bind_venue_order_transport(adapter, transport=_MockTransport())

    place_trace = adapter.place_order(
        ClobPlaceOrderRequest(
            market=_market(venue=VenueName.polymarket, market_id="pm_exec_structured"),
            run_id="run_exec_structured",
            position_side=TradeSide.yes,
            execution_side=TradeSide.buy,
            requested_quantity=3.0,
            requested_notional=8.5,
            limit_price=0.52,
            dry_run=False,
            allow_live_execution=True,
            authorized=True,
            compliance_approved=True,
            scopes=["prediction_markets:execute"],
            metadata={"request_marker": "structured_place"},
        )
    )

    assert submitted_payloads
    assert submitted_payloads[0]["metadata"]["request_marker"] == "structured_place"
    assert place_trace.live_submission_performed is True
    assert place_trace.order.metadata["venue_order_id"] == f"transport_{place_trace.order.order_id}"
    assert place_trace.order.metadata["venue_order_trace_kind"] == "external_live"
    assert place_trace.metadata["order_trace_audit"]["operator_bound"] is True
    assert place_trace.metadata["live_submission_receipt"]["operator_bound"] is True

    cancel_trace = adapter.cancel_order(
        ClobCancelOrderRequest(
            order=place_trace.order,
            reason="manual_cancel",
            cancelled_by="ops_bot",
            metadata={"cancel_marker": "structured_cancel"},
        )
    )

    assert cancelled_payloads
    assert cancelled_payloads[0]["metadata"]["cancel_marker"] == "structured_cancel"
    assert cancelled_payloads[0]["metadata"]["cancelled_by"] == "ops_bot"
    assert cancel_trace.live_submission_performed is True
    assert cancel_trace.order.metadata["venue_order_status"] == "cancelled"
    assert cancel_trace.metadata["order_trace_audit"]["transport_mode"] == "live"
    assert cancel_trace.metadata["order_trace_audit"]["operator_bound"] is True
    assert cancel_trace.metadata["venue_cancellation_receipt"]["operator_bound"] is True
