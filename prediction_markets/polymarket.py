from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import requests
from pydantic import BaseModel, Field, model_validator

try:
    import websocket as websocket_client
except Exception:  # pragma: no cover - optional dependency guard
    websocket_client = None

from .adapters import (
    HttpJSONSource,
    PolymarketExecutionAdapter as BasePolymarketExecutionAdapter,
    _event_markets,
    _load_position_records,
    build_venue_order_cancellation_receipt,
    build_venue_order_submission_receipt,
    build_venue_order_lifecycle,
    _resolve_polymarket_backend_mode,
    _resolve_polymarket_execution_runtime_config,
)
from .models import LedgerPosition, MarketDescriptor, MarketOrderBook, MarketSnapshot, OrderBookLevel, TradeRecord, TradeSide, VenueName, VenueType, _stable_content_hash, _utc_now
from .market_execution import MarketExecutionOrder, MarketExecutionOrderType, MarketExecutionRequest
from .resolution_guard import (
    ResolutionPolicyCompletenessReport,
    ResolutionPolicySurface,
    build_resolution_policy_completeness_report,
    describe_resolution_policy_surface,
)


GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com"
POLYMARKET_MARKET_WEBSOCKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
POLYMARKET_USER_WEBSOCKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
POLYMARKET_RTDS_URL = "wss://ws-live-data.polymarket.com"


class MarketDataSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    backend_mode: str = "unknown"
    ingestion_mode: str = "read_only_http_json"
    market_feed_kind: str = "market_snapshot"
    user_feed_kind: str = "position_snapshot"
    supports_market_feed: bool = True
    supports_user_feed: bool = True
    supports_events: bool = True
    supports_positions: bool = True
    supports_websocket: bool = False
    supports_rtds: bool = False
    live_streaming: bool = False
    websocket_status: str = "unavailable"
    market_websocket_status: str = "unavailable"
    user_feed_websocket_status: str = "unavailable"
    market_feed_transport: str = "http_json"
    user_feed_transport: str = "http_json"
    market_feed_connector: str = "http_json_market_snapshot"
    user_feed_connector: str = "http_json_position_snapshot"
    rtds_connector: str = "unavailable"
    market_feed_status: str = "endpoint_configured"
    user_feed_status: str = "endpoint_configured"
    rtds_status: str = "unavailable"
    market_feed_replayable: bool = True
    user_feed_replayable: bool = True
    rtds_replayable: bool = False
    market_feed_cache_backed: bool = False
    user_feed_cache_backed: bool = False
    rtds_cache_backed: bool = False
    events_source: str = "markets"
    positions_source: str = "positions"
    market_feed_source: str = "markets"
    user_feed_source: str = "positions"
    configured_endpoints: dict[str, str] = Field(default_factory=dict)
    route_refs: dict[str, str] = Field(default_factory=dict)
    availability_probes: dict[str, Any] = Field(default_factory=dict)
    cache_fallbacks: dict[str, Any] = Field(default_factory=dict)
    subscription_preview: dict[str, Any] = Field(default_factory=dict)
    probe_bundle: dict[str, Any] = Field(default_factory=dict)
    capability_summary: dict[str, Any] = Field(default_factory=dict)
    connector_contracts: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    runbook: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolymarketExecutionSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName = VenueName.polymarket
    backend_mode: str = "auto"
    requested_backend_mode: str = "auto"
    selected_backend_mode: str = "auto"
    auth_scheme: str = "bearer"
    auth_configured: bool = False
    mock_transport: bool = False
    live_execution_ready: bool = False
    ready_for_live_execution: bool = False
    live_order_path: str = "external_live_api"
    bounded_order_path: str = "external_bounded_api"
    cancel_order_path: str = "external_live_cancel_api"
    bounded_cancel_path: str = "external_bounded_cancel_api"
    order_sources: dict[str, list[str]] = Field(default_factory=dict)
    auth_sources: list[str] = Field(default_factory=list)
    readiness_notes: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolymarketOrderAction(str, Enum):
    place = "place"
    cancel = "cancel"


class PolymarketOrderExecutionSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName = VenueName.polymarket
    requested_backend_mode: str = "auto"
    selected_backend_mode: str = "auto"
    transport_mode: str = "mock"
    live_execution_ready: bool = False
    mock_transport: bool = False
    live_submission_bound: bool = False
    place_order_path: str = "external_live_api"
    cancel_order_path: str = "external_live_cancel_api"
    place_auditable: bool = True
    cancel_auditable: bool = True
    readiness_notes: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolymarketOrderTrace(BaseModel):
    schema_version: str = "v1"
    trace_id: str = Field(default_factory=lambda: f"pm_order_{uuid4().hex[:12]}")
    action: PolymarketOrderAction
    requested_backend_mode: str
    selected_backend_mode: str
    transport_mode: str
    live_execution_ready: bool
    mock_transport: bool
    live_submission_bound: bool
    live_submission_attempted: bool = False
    live_submission_performed: bool = False
    dry_run: bool = True
    market: MarketDescriptor
    request: MarketExecutionRequest
    order: MarketExecutionOrder
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    venue_order_lifecycle: dict[str, Any] = Field(default_factory=dict)
    submitted_payload: dict[str, Any] | None = None
    cancelled_payload: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class PolymarketRealtimeCredentials:
    api_key: str | None = None
    secret: str | None = None
    passphrase: str | None = None
    gamma_auth_address: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret and self.passphrase)

    @property
    def user_feed_ready(self) -> bool:
        return self.configured

    def user_auth_payload(self) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("Polymarket user websocket requires api_key, secret, and passphrase.")
        return {
            "apiKey": str(self.api_key),
            "secret": str(self.secret),
            "passphrase": str(self.passphrase),
        }

    def gamma_auth_payload(self) -> dict[str, str] | None:
        if not self.gamma_auth_address:
            return None
        return {"address": str(self.gamma_auth_address)}


@dataclass
class PolymarketWebSocketSession:
    endpoint: str
    channel: str
    subscription_message: dict[str, Any]
    connection: Any
    auth_requirement: str
    session_requirement: str
    heartbeat_interval_seconds: float
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    closed_at: datetime | None = None
    _closed: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _heartbeat_thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def start_heartbeat(self) -> None:
        if self.heartbeat_interval_seconds <= 0 or self._heartbeat_thread is not None:
            return

        def _heartbeat_loop() -> None:
            while not self._closed.wait(self.heartbeat_interval_seconds):
                try:
                    self.connection.send("PING")
                except Exception:
                    break

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"polymarket-{self.channel}-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def send(self, payload: Any) -> None:
        if isinstance(payload, (dict, list)):
            self.connection.send(json.dumps(payload))
            return
        self.connection.send(payload)

    def recv(self) -> Any:
        return self.connection.recv()

    def close(self) -> None:
        self._closed.set()
        try:
            self.connection.close()
        finally:
            self.closed_at = datetime.now(timezone.utc)
            if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=0.25)

    def __enter__(self) -> "PolymarketWebSocketSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _order_trace_audit_from_lifecycle(
    lifecycle: dict[str, Any],
    *,
    transport_mode: str,
    live_execution_ready: bool,
    live_submission_attempted: bool,
    live_submission_performed: bool,
    live_submission_bound: bool = False,
) -> dict[str, Any]:
    operator_bound = bool(
        live_submission_bound
        or lifecycle.get("venue_live_submission_bound")
        or lifecycle.get("live_submission_bound")
        or lifecycle.get("operator_bound")
    )
    return {
        "schema_version": "v1",
        "trace_source": "venue_order_lifecycle",
        "venue_order_id": lifecycle.get("venue_order_id"),
        "venue_order_status": lifecycle.get("venue_order_status"),
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
        "venue_order_ack_path": lifecycle.get("venue_order_ack_path") or lifecycle.get("venue_order_path"),
        "venue_order_cancel_path": lifecycle.get("venue_order_cancel_path"),
        "venue_order_configured": bool(lifecycle.get("venue_order_configured", False)),
        "venue_order_trace_kind": lifecycle.get("venue_order_trace_kind"),
        "venue_order_flow": lifecycle.get("venue_order_flow"),
        "transport_mode": transport_mode,
        "runtime_live_claimed": transport_mode == "live",
        "runtime_honest_mode": transport_mode,
        "live_execution_ready": live_execution_ready,
        "live_submission_attempted": live_submission_attempted,
        "live_submission_performed": live_submission_performed,
        "operator_bound": operator_bound,
        "place_auditable": True,
        "cancel_auditable": True,
    }


class PolymarketResolutionPolicySurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName = VenueName.polymarket
    policy_surface: ResolutionPolicySurface
    summary: str = ""
    no_trade: bool = True
    policy_complete: bool = False
    policy_coherent: bool = False
    completeness_rate: float = 0.0
    coherence_rate: float = 0.0
    policy_status: str = "unavailable"
    manual_review_required: bool = True
    official_source: str | None = None
    official_source_url: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    required_fields_count: int = 0
    present_fields_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "PolymarketResolutionPolicySurface":
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude_none=True))
        return self


class PolymarketResolutionPolicyCompletenessReport(BaseModel):
    schema_version: str = "v1"
    venue: VenueName = VenueName.polymarket
    report: ResolutionPolicyCompletenessReport
    summary: str = ""
    manual_review_rate: float = 0.0
    ambiguous_rate: float = 0.0
    unavailable_rate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "PolymarketResolutionPolicyCompletenessReport":
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude_none=True))
        return self


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = " ".join(str(value).strip().split())
        if text:
            return text
    return None


def _market_data_surface(
    *,
    backend_mode: str,
    events_source: str,
    positions_source: str,
    market_feed_source: str,
    user_feed_source: str,
    supports_positions: bool = True,
    transport_prefix: str = "http_json",
    notes: list[str] | None = None,
) -> MarketDataSurface:
    fixture_mode = backend_mode == "fixture"
    surrogate_mode = backend_mode == "surrogate"
    ingestion_mode = "read_only_fixture" if fixture_mode else "read_only_http_json"
    market_status = "fixture_available" if fixture_mode else ("surrogate_available" if surrogate_mode else "endpoint_configured")
    user_status = (
        "fixture_available"
        if fixture_mode and supports_positions
        else ("local_cache" if surrogate_mode and supports_positions else ("endpoint_configured" if supports_positions else "unavailable"))
    )
    market_connector = "fixture_market_snapshot" if fixture_mode else ("surrogate_market_snapshot" if surrogate_mode else "http_json_market_snapshot")
    user_connector = (
        "fixture_positions_snapshot"
        if fixture_mode and supports_positions
        else ("local_position_cache" if surrogate_mode and supports_positions else ("http_json_position_snapshot" if supports_positions else "unavailable"))
    )
    route_refs = {
        "events": events_source,
        "positions": positions_source,
        "market_feed": market_feed_source,
        "user_feed": user_feed_source,
    }
    availability_probes = {
        "market_feed": {
            "status": market_status,
            "transport": transport_prefix,
            "connector": market_connector,
            "route_ref": market_feed_source,
            "replayable": True,
            "cache_backed": fixture_mode or surrogate_mode,
            "probe_ready": True,
            "operational_status": "ready",
            "recommended_action": "use_cache_backed_snapshot" if fixture_mode or surrogate_mode else "poll_http_snapshot",
            "severity": "info",
            "gap_reason": "snapshot_only_no_push" if fixture_mode or surrogate_mode else "poll_only_surface",
            "documented_route_ref": market_feed_source,
            "auth_requirement": "none",
            "session_requirement": "none",
            "subscription_capable": False,
            "preview_only": False,
            "gap_class": "snapshot_only" if fixture_mode or surrogate_mode else "poll_only_surface",
        },
        "user_feed": {
            "status": user_status,
            "transport": transport_prefix if supports_positions else "unavailable",
            "connector": user_connector,
            "route_ref": user_feed_source,
            "replayable": supports_positions,
            "cache_backed": (fixture_mode or surrogate_mode) and supports_positions,
            "probe_ready": bool(supports_positions and user_feed_source),
            "operational_status": "ready" if supports_positions and user_feed_source else "unavailable",
            "recommended_action": (
                "read_user_feed_cache"
                if (fixture_mode or surrogate_mode) and supports_positions
                else ("poll_http_snapshot" if supports_positions else "treat_as_unavailable")
            ),
            "severity": "info" if supports_positions and user_feed_source else "warning",
            "gap_reason": "user_feed_proxy_cache" if (fixture_mode or surrogate_mode) and supports_positions else "no_user_feed_binding",
            "documented_route_ref": user_feed_source,
            "auth_requirement": "none",
            "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            "subscription_capable": False,
            "preview_only": False,
            "gap_class": "cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
        },
        "websocket_market": {
            "status": "unavailable",
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": None,
            "replayable": False,
            "cache_backed": False,
            "supported": False,
            "probe_ready": False,
            "operational_status": "not_supported",
            "recommended_action": "do_not_assume_live_websocket",
            "severity": "info",
            "gap_reason": "live_websocket_not_bound",
            "documented_route_ref": None,
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "subscription_capable": False,
            "preview_only": True,
            "gap_class": "not_bound",
        },
        "websocket_user": {
            "status": "unavailable",
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": None,
            "replayable": False,
            "cache_backed": False,
            "supported": False,
            "probe_ready": False,
            "operational_status": "not_supported",
            "recommended_action": "do_not_assume_live_websocket",
            "severity": "info",
            "gap_reason": "live_user_feed_not_bound",
            "documented_route_ref": None,
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "subscription_capable": False,
            "preview_only": True,
            "gap_class": "not_bound",
        },
        "rtds": {
            "status": "unavailable",
            "transport": "rtds",
            "connector": "unavailable",
            "route_ref": None,
            "replayable": False,
            "cache_backed": False,
            "supported": False,
            "probe_ready": False,
            "operational_status": "not_supported",
            "recommended_action": "do_not_assume_rtds",
            "severity": "info",
            "gap_reason": "rtds_not_bound",
            "documented_route_ref": None,
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "subscription_capable": False,
            "preview_only": True,
            "gap_class": "not_bound",
        },
    }
    cache_fallbacks = {
        "market_feed": {
            "status": "ready" if fixture_mode or surrogate_mode else "not_configured",
            "connector": market_connector,
            "route_ref": market_feed_source,
            "replayable": True,
            "cache_backed": fixture_mode or surrogate_mode,
            "operational_status": "ready" if fixture_mode or surrogate_mode else "not_configured",
            "recommended_action": "use_cache_fallback" if fixture_mode or surrogate_mode else "no_cache_fallback",
        },
        "user_feed": {
            "status": "ready" if (fixture_mode or surrogate_mode) and supports_positions else "not_configured",
            "connector": user_connector,
            "route_ref": user_feed_source,
            "replayable": supports_positions,
            "cache_backed": (fixture_mode or surrogate_mode) and supports_positions,
            "operational_status": "ready" if (fixture_mode or surrogate_mode) and supports_positions else "not_configured",
            "recommended_action": "use_cache_fallback" if (fixture_mode or surrogate_mode) and supports_positions else "no_cache_fallback",
        },
        "rtds": {
            "status": "not_configured",
            "connector": "unavailable",
            "route_ref": None,
            "replayable": False,
            "cache_backed": False,
            "operational_status": "not_configured",
            "recommended_action": "no_cache_fallback",
        },
    }
    connector_contracts = {
        "market_feed": {
            "mode": "read_only",
            "transport": transport_prefix,
            "connector": market_connector,
            "route_ref": market_feed_source,
            "kind": "market_snapshot",
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": True,
            "cache_backed": fixture_mode or surrogate_mode,
            "readiness": availability_probes["market_feed"]["operational_status"],
            "auth_requirement": "none",
            "session_requirement": "none",
            "preview_only": False,
            "gap_class": "snapshot_only" if fixture_mode or surrogate_mode else "poll_only_surface",
            "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
            "endpoint_contract": {
                "method": "GET",
                "route_ref": market_feed_source,
                "request_mode": "pull",
                "response_kind": "market_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "user_feed": {
            "mode": "read_only",
            "transport": transport_prefix if supports_positions else "unavailable",
            "connector": user_connector,
            "route_ref": user_feed_source,
            "kind": "position_snapshot",
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": supports_positions,
            "cache_backed": (fixture_mode or surrogate_mode) and supports_positions,
            "readiness": availability_probes["user_feed"]["operational_status"],
            "auth_requirement": "none",
            "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            "preview_only": False,
            "gap_class": "cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
            "auth_session": {
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            },
            "endpoint_contract": {
                "method": "GET",
                "route_ref": user_feed_source,
                "request_mode": "pull",
                "response_kind": "position_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_market": {
            "mode": "preview_only",
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": None,
            "kind": "market_stream",
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": False,
            "cache_backed": False,
            "readiness": availability_probes["websocket_market"]["operational_status"],
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "preview_only": True,
            "gap_class": "not_bound",
            "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            "endpoint_contract": {
                "method": "PREVIEW_ONLY",
                "route_ref": None,
                "request_mode": "preview_only",
                "response_kind": "market_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_user": {
            "mode": "preview_only",
            "transport": "websocket",
            "connector": "unavailable",
            "route_ref": None,
            "kind": "user_stream",
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": False,
            "cache_backed": False,
            "readiness": availability_probes["websocket_user"]["operational_status"],
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "preview_only": True,
            "gap_class": "not_bound",
            "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            "endpoint_contract": {
                "method": "PREVIEW_ONLY",
                "route_ref": None,
                "request_mode": "preview_only",
                "response_kind": "user_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "rtds": {
            "mode": "preview_only",
            "transport": "rtds",
            "connector": "unavailable",
            "route_ref": None,
            "kind": "rtds",
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": False,
            "cache_backed": False,
            "readiness": availability_probes["rtds"]["operational_status"],
            "auth_requirement": "not_bound",
            "session_requirement": "preview_only",
            "preview_only": True,
            "gap_class": "not_bound",
            "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            "endpoint_contract": {
                "method": "PREVIEW_ONLY",
                "route_ref": None,
                "request_mode": "preview_only",
                "response_kind": "rtds_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "documented_routes": {
            "market_feed": market_feed_source,
            "user_feed": user_feed_source,
            "market_websocket": None,
            "user_websocket": None,
            "rtds": None,
        },
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "not_bound",
            "websocket_user": "not_bound",
            "rtds": "not_bound",
        },
        "session_requirements": {
            "market_feed": "none",
            "user_feed": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            "websocket_market": "preview_only",
            "websocket_user": "preview_only",
            "rtds": "preview_only",
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
        "replay_fallbacks": {
            "market_feed": "cache_fallback" if fixture_mode or surrogate_mode else "poll_snapshot_route",
            "user_feed": "cache_fallback" if (fixture_mode or surrogate_mode) and supports_positions else "poll_snapshot_route",
            "websocket_market": "no_live_binding",
            "websocket_user": "no_live_binding",
            "rtds": "no_live_binding",
        },
    }
    preview_flow = {
        "flow_id": f"polymarket:bounded_websocket_rtds_preview",
        "mode": "preview_only",
        "testable": True,
        "live_claimed": False,
        "route_refs": {
            "market_feed": market_feed_source,
            "user_feed": user_feed_source,
            "market_websocket": None,
            "user_websocket": None,
            "rtds": None,
        },
        "steps": [
            {
                "step": "resolve_routes",
                "status": "complete",
                "documented_route_refs": {
                    "market_feed": market_feed_source,
                    "user_feed": user_feed_source,
                    "market_websocket": None,
                    "user_websocket": None,
                    "rtds": None,
                },
            },
            {
                "step": "confirm_auth_and_session",
                "status": "complete",
                "auth_requirements": {
                    "market_feed": "none",
                    "user_feed": "none",
                    "websocket_market": "not_bound",
                    "websocket_user": "not_bound",
                    "rtds": "not_bound",
                },
                "session_requirements": {
                    "market_feed": "none",
                    "user_feed": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
                    "websocket_market": "preview_only",
                    "websocket_user": "preview_only",
                    "rtds": "preview_only",
                },
            },
            {
                "step": "select_preview_fallbacks",
                "status": "complete",
                "preview_targets": {
                    "market_feed": availability_probes["market_feed"]["recommended_action"],
                    "user_feed": availability_probes["user_feed"]["recommended_action"],
                    "websocket_market": availability_probes["websocket_market"]["recommended_action"],
                    "websocket_user": availability_probes["websocket_user"]["recommended_action"],
                    "rtds": availability_probes["rtds"]["recommended_action"],
                },
            },
        ],
        "bounded_channels": ["websocket_market", "websocket_user", "rtds"],
        "preview_only_channels": ["websocket_market", "websocket_user", "rtds"],
        "probe_statuses": {
            "websocket_market": availability_probes["websocket_market"]["operational_status"],
            "websocket_user": availability_probes["websocket_user"]["operational_status"],
            "rtds": availability_probes["rtds"]["operational_status"],
        },
        "expected_outcome": "preview_only_no_live_transport",
    }
    gap_summary = {
        "live_transport_supported": False,
        "live_transport_ready_count": sum(
            1
            for key in ("websocket_market", "websocket_user", "rtds")
            if availability_probes[key]["operational_status"] == "ready"
        ),
        "live_transport_not_supported_count": sum(
            1
            for key in ("websocket_market", "websocket_user", "rtds")
            if availability_probes[key]["operational_status"] == "not_supported"
        ),
        "preview_only_channel_count": sum(1 for probe in availability_probes.values() if probe.get("preview_only")),
        "cache_backed_channel_count": sum(
            1 for key in ("market_feed", "user_feed") if bool(availability_probes[key].get("cache_backed"))
        ),
        "documented_preview_routes": {
            "market_feed": market_feed_source,
            "user_feed": user_feed_source,
            "market_websocket": None,
            "user_websocket": None,
            "rtds": None,
        },
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "not_bound",
            "websocket_user": "not_bound",
            "rtds": "not_bound",
        },
        "session_requirements": {
            "market_feed": "none",
            "user_feed": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            "websocket_market": "preview_only",
            "websocket_user": "preview_only",
            "rtds": "preview_only",
        },
        "live_transport_gap_reasons": {
            "websocket_market": availability_probes["websocket_market"]["gap_reason"],
            "websocket_user": availability_probes["websocket_user"]["gap_reason"],
            "rtds": availability_probes["rtds"]["gap_reason"],
        },
        "cache_backed_gap_reasons": {
            "market_feed": availability_probes["market_feed"]["gap_reason"],
            "user_feed": availability_probes["user_feed"]["gap_reason"],
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
    }
    subscription_preview = {
        "mode": "preview_only",
        "supports_live_subscriptions": False,
        "recommended_poll_transport": transport_prefix,
        "recommended_user_transport": transport_prefix if supports_positions else "unavailable",
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "not_bound",
            "websocket_user": "not_bound",
            "rtds": "not_bound",
        },
        "session_requirements": {
            "market_feed": "none",
            "user_feed": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
            "websocket_market": "preview_only",
            "websocket_user": "preview_only",
            "rtds": "preview_only",
        },
        "channels": {
            "market_feed": {
                "topic": "polymarket:market_feed",
                "route_ref": market_feed_source,
                "status": availability_probes["market_feed"]["operational_status"],
                "subscription_capable": False,
                "recommended_action": availability_probes["market_feed"]["recommended_action"],
                "subscription_intent": "poll_snapshot",
                "auth_requirement": "none",
                "gap_class": availability_probes["market_feed"]["gap_class"],
                "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "market_snapshot",
                    "cadence_hint": "poll_on_schedule",
                },
            },
            "user_feed": {
                "topic": "polymarket:user_feed",
                "route_ref": user_feed_source,
                "status": availability_probes["user_feed"]["operational_status"],
                "subscription_capable": False,
                "recommended_action": availability_probes["user_feed"]["recommended_action"],
                "subscription_intent": "read_cache" if (fixture_mode or surrogate_mode) and supports_positions else "poll_snapshot",
                "auth_requirement": "none",
                "gap_class": availability_probes["user_feed"]["gap_class"],
                "auth_session": {
                    "auth_requirement": "none",
                    "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
                },
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "position_snapshot",
                    "cadence_hint": "poll_or_cache_read",
                },
            },
            "websocket_market": {
                "topic": "polymarket:websocket_market",
                "route_ref": None,
                "status": availability_probes["websocket_market"]["operational_status"],
                "subscription_capable": False,
                "recommended_action": availability_probes["websocket_market"]["recommended_action"],
                "subscription_intent": "preview_only",
                "auth_requirement": "not_bound",
                "gap_class": availability_probes["websocket_market"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
                "channel_spec": {
                    "delivery_mode": "preview_only",
                    "message_kind": "market_stream_preview",
                    "cadence_hint": "none",
                },
            },
            "websocket_user": {
                "topic": "polymarket:websocket_user",
                "route_ref": None,
                "status": availability_probes["websocket_user"]["operational_status"],
                "subscription_capable": False,
                "recommended_action": availability_probes["websocket_user"]["recommended_action"],
                "subscription_intent": "preview_only",
                "auth_requirement": "not_bound",
                "gap_class": availability_probes["websocket_user"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
                "channel_spec": {
                    "delivery_mode": "preview_only",
                    "message_kind": "user_stream_preview",
                    "cadence_hint": "none",
                },
            },
            "rtds": {
                "topic": "polymarket:rtds",
                "route_ref": None,
                "status": availability_probes["rtds"]["operational_status"],
                "subscription_capable": False,
                "recommended_action": availability_probes["rtds"]["recommended_action"],
                "subscription_intent": "preview_only",
                "auth_requirement": "not_bound",
                "gap_class": availability_probes["rtds"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
                "channel_spec": {
                    "delivery_mode": "preview_only",
                    "message_kind": "rtds_preview",
                    "cadence_hint": "none",
                },
            },
        },
        "channel_specs": {
            "market_feed": {
                "route_ref": market_feed_source,
                "delivery_mode": "pull",
                "message_kind": "market_snapshot",
                "auth_requirement": "none",
                "session_requirement": "none",
                "subscription_intent": "poll_snapshot",
                "preview_probe": dict(availability_probes.get("market_feed") or {}),
                "replay_fallback": dict((cache_fallbacks or {}).get("market_feed") or {}),
                "explicit_gap": "snapshot_only_no_push",
                "gap_class": availability_probes["market_feed"]["gap_class"],
                "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
            },
            "user_feed": {
                "route_ref": user_feed_source,
                "delivery_mode": "pull",
                "message_kind": "position_snapshot",
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
                "subscription_intent": "read_cache" if (fixture_mode or surrogate_mode) and supports_positions else "poll_snapshot",
                "preview_probe": dict(availability_probes.get("user_feed") or {}),
                "replay_fallback": dict((cache_fallbacks or {}).get("user_feed") or {}),
                "explicit_gap": "user_feed_proxy_cache" if (fixture_mode or surrogate_mode) and supports_positions else "no_user_feed_binding",
                "gap_class": availability_probes["user_feed"]["gap_class"],
                "auth_session": {
                    "auth_requirement": "none",
                    "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
                },
            },
            "websocket_market": {
                "route_ref": None,
                "delivery_mode": "preview_only",
                "message_kind": "market_stream_preview",
                "auth_requirement": "not_bound",
                "session_requirement": "preview_only",
                "subscription_intent": "preview_only",
                "preview_probe": dict(availability_probes.get("websocket_market") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": "live_websocket_not_bound",
                "gap_class": availability_probes["websocket_market"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            },
            "websocket_user": {
                "route_ref": None,
                "delivery_mode": "preview_only",
                "message_kind": "user_stream_preview",
                "auth_requirement": "not_bound",
                "session_requirement": "preview_only",
                "subscription_intent": "preview_only",
                "preview_probe": dict(availability_probes.get("websocket_user") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": "live_user_feed_not_bound",
                "gap_class": availability_probes["websocket_user"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            },
            "rtds": {
                "route_ref": None,
                "delivery_mode": "preview_only",
                "message_kind": "rtds_preview",
                "auth_requirement": "not_bound",
                "session_requirement": "preview_only",
                "subscription_intent": "preview_only",
                "preview_probe": dict(availability_probes.get("rtds") or {}),
                "replay_fallback": "no_live_binding",
                "explicit_gap": "rtds_not_bound",
                "gap_class": availability_probes["rtds"]["gap_class"],
                "auth_session": {"auth_requirement": "not_bound", "session_requirement": "preview_only"},
            },
        },
        "subscription_bundles": {
            "poll_snapshot_bundle": {
                "bundle_id": "polymarket:poll_snapshot_bundle",
                "channels": ["market_feed", "user_feed"],
                "route_refs": {
                    "market_feed": market_feed_source,
                    "user_feed": user_feed_source,
                },
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if (fixture_mode or surrogate_mode) and supports_positions else "none",
                "preview_only": False,
                "testable": True,
            },
            "websocket_preview_bundle": {
                "bundle_id": "polymarket:websocket_preview_bundle",
                "channels": ["websocket_market", "websocket_user"],
                "route_refs": {"market_websocket": None, "user_websocket": None},
                "auth_requirement": "not_bound",
                "session_requirement": "preview_only",
                "preview_only": True,
                "testable": True,
            },
            "rtds_preview_bundle": {
                "bundle_id": "polymarket:rtds_preview_bundle",
                "channels": ["rtds"],
                "route_refs": {"rtds": None},
                "auth_requirement": "not_bound",
                "session_requirement": "preview_only",
                "preview_only": True,
                "testable": True,
            },
        },
        "preview_flow": preview_flow,
        "auth_required_any": False,
        "channel_count": 5,
        "recommended_subscriptions": [
            {
                "channel": "market_feed",
                "intent": "poll_snapshot",
                "route_ref": market_feed_source,
                "recommended_action": availability_probes["market_feed"]["recommended_action"],
            },
            {
                "channel": "user_feed",
                "intent": "read_cache" if (fixture_mode or surrogate_mode) and supports_positions else "poll_snapshot",
                "route_ref": user_feed_source,
                "recommended_action": availability_probes["user_feed"]["recommended_action"],
            },
        ],
        "documented_channel_route_refs": {
            "market_feed": market_feed_source,
            "user_feed": user_feed_source,
            "websocket_market": None,
            "websocket_user": None,
            "rtds": None,
        },
        "gap_summary": gap_summary,
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
        "replay_fallbacks": {
            "market_feed": dict((cache_fallbacks or {}).get("market_feed") or {}),
            "user_feed": dict((cache_fallbacks or {}).get("user_feed") or {}),
            "websocket_market": "no_live_binding",
            "websocket_user": "no_live_binding",
            "rtds": "no_live_binding",
        },
    }
    probe_bundle = {
        "bundle_status": "ready",
        "probe_count": len(availability_probes),
        "ready_count": sum(
            1 for probe in availability_probes.values() if probe.get("operational_status") == "ready"
        ),
        "not_supported_count": sum(
            1 for probe in availability_probes.values() if probe.get("operational_status") == "not_supported"
        ),
        "unavailable_count": sum(
            1 for probe in availability_probes.values() if probe.get("operational_status") == "unavailable"
        ),
        "primary_path": availability_probes["market_feed"]["recommended_action"],
        "fallback_path": cache_fallbacks["market_feed"]["recommended_action"],
        "market_feed_status": availability_probes["market_feed"]["operational_status"],
        "user_feed_status": availability_probes["user_feed"]["operational_status"],
        "transport_readiness": {
            key: probe["operational_status"] for key, probe in availability_probes.items()
        },
        "gap_summary": gap_summary,
        "degraded_paths": [
            key for key, probe in availability_probes.items() if probe["operational_status"] != "ready"
        ],
        "preview_flow": preview_flow,
        "recovered_from_partial_probes": False,
        "severity_counts": {
            "info": sum(1 for probe in availability_probes.values() if probe["severity"] == "info"),
            "warning": sum(1 for probe in availability_probes.values() if probe["severity"] == "warning"),
            "error": sum(1 for probe in availability_probes.values() if probe["severity"] == "error"),
        },
        "highest_severity": "warning" if any(probe["severity"] == "warning" for probe in availability_probes.values()) else "info",
    }
    capability_summary = {
        "mode": "read_only",
        "live_claimed": False,
        "subscription_mode": "preview_only",
        "market_feed_path": availability_probes["market_feed"]["recommended_action"],
        "user_feed_path": availability_probes["user_feed"]["recommended_action"],
        "websocket_path": availability_probes["websocket_market"]["recommended_action"],
        "rtds_path": availability_probes["rtds"]["recommended_action"],
        "has_replayable_market_feed": True,
        "has_cache_fallback": fixture_mode or surrogate_mode or supports_positions,
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "not_bound",
            "websocket_user": "not_bound",
            "rtds": "not_bound",
        },
        "market_user_gap_reasons": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if (fixture_mode or surrogate_mode) and supports_positions else "user_feed_not_bound",
        ],
        "explicit_gaps": [
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
        "rtds_usefulness": {
            "status": "preview_only",
            "usable_for_live_ops": False,
            "recommended_action": availability_probes["rtds"]["recommended_action"],
        },
        "recommended_subscriptions": ["market_feed", "user_feed"],
        "documented_preview_routes": {
            "market_websocket": None,
            "user_websocket": None,
            "rtds": None,
        },
        "gap_summary": gap_summary,
        "preview_flow": preview_flow,
    }
    runbook = _market_data_runbook(
        backend_mode=backend_mode,
        ingestion_mode=ingestion_mode,
        market_feed_status=market_status,
        user_feed_status=user_status,
        supports_positions=supports_positions,
        route_refs=route_refs,
        availability_probes=availability_probes,
        cache_fallbacks=cache_fallbacks,
        subscription_preview=subscription_preview,
        probe_bundle=probe_bundle,
        capability_summary=capability_summary,
        connector_contracts=connector_contracts,
        gap_summary=gap_summary,
    )
    return MarketDataSurface(
        venue=VenueName.polymarket,
        backend_mode=backend_mode,
        ingestion_mode=ingestion_mode,
        market_feed_kind="market_snapshot_fixture" if fixture_mode else "market_snapshot_http_json",
        user_feed_kind="position_snapshot_fixture" if fixture_mode and supports_positions else ("position_snapshot_http_json" if supports_positions else "unavailable"),
        supports_market_feed=True,
        supports_user_feed=supports_positions,
        supports_events=True,
        supports_positions=supports_positions,
        supports_websocket=False,
        supports_rtds=False,
        live_streaming=False,
        websocket_status="unavailable",
        market_websocket_status="unavailable",
        user_feed_websocket_status="unavailable",
        market_feed_transport=transport_prefix,
        user_feed_transport=transport_prefix if supports_positions else "unavailable",
        market_feed_connector=market_connector,
        user_feed_connector=user_connector,
        rtds_connector="unavailable",
        market_feed_status=market_status,
        user_feed_status=user_status,
        rtds_status="unavailable",
        market_feed_replayable=True,
        user_feed_replayable=supports_positions,
        rtds_replayable=False,
        market_feed_cache_backed=fixture_mode or surrogate_mode,
        user_feed_cache_backed=(fixture_mode or surrogate_mode) and supports_positions,
        rtds_cache_backed=False,
        events_source=events_source,
        positions_source=positions_source,
        market_feed_source=market_feed_source,
        user_feed_source=user_feed_source,
        configured_endpoints={
            "events_source": events_source,
            "positions_source": positions_source,
            "market_feed_source": market_feed_source,
            "user_feed_source": user_feed_source,
        },
        route_refs=route_refs,
        availability_probes=availability_probes,
        cache_fallbacks=cache_fallbacks,
        subscription_preview=subscription_preview,
        probe_bundle=probe_bundle,
        capability_summary=capability_summary,
        connector_contracts=connector_contracts,
        summary=(
            f"Read-only Polymarket data surface from {market_feed_source} / {user_feed_source} "
            f"via {ingestion_mode}; market snapshots are replayable, user feeds are proxy/cache-backed when available, and websocket/RTDS are not implemented here."
        ),
        runbook=runbook,
        notes=notes
        or [
            "read_only_metadata_surface",
            "no_websocket_live_integration",
            "no_rtds_live_integration",
        ],
        metadata={"backend_mode": backend_mode, "read_only": True},
    )


def describe_polymarket_execution_surface(backend_mode: str | None = None) -> PolymarketExecutionSurface:
    runtime_config = _resolve_polymarket_execution_runtime_config(backend_mode)
    return PolymarketExecutionSurface(
        backend_mode=runtime_config["selected_backend_mode"],
        requested_backend_mode=runtime_config["requested_backend_mode"],
        selected_backend_mode=runtime_config["selected_backend_mode"],
        auth_scheme=runtime_config["auth_scheme"],
        auth_configured=runtime_config["auth_configured"],
        mock_transport=runtime_config["mock_transport"],
        live_execution_ready=runtime_config["runtime_ready"],
        ready_for_live_execution=runtime_config["ready_for_live_execution"],
        live_order_path=runtime_config["live_order_path"],
        bounded_order_path=runtime_config["bounded_order_path"],
        cancel_order_path=runtime_config["cancel_order_path"],
        bounded_cancel_path=runtime_config["bounded_cancel_path"],
        order_sources=dict(runtime_config["order_sources"]),
        auth_sources=list(runtime_config["auth_sources"]),
        readiness_notes=list(runtime_config["readiness_notes"]),
        missing_requirements=list(runtime_config["missing_requirements"]),
        metadata={
            "runtime_config": runtime_config,
            "execution_ready": runtime_config["runtime_ready"],
        },
    )


def describe_polymarket_order_execution_surface(backend_mode: str | None = None) -> PolymarketOrderExecutionSurface:
    runtime_config = _resolve_polymarket_execution_runtime_config(backend_mode)
    transport_mode = (
        "live"
        if runtime_config["selected_backend_mode"] == "live" and runtime_config["runtime_ready"] and not runtime_config["mock_transport"]
        else "dry_run"
    )
    return PolymarketOrderExecutionSurface(
        requested_backend_mode=runtime_config["requested_backend_mode"],
        selected_backend_mode=runtime_config["selected_backend_mode"],
        transport_mode=transport_mode,
        live_execution_ready=runtime_config["runtime_ready"],
        mock_transport=runtime_config["mock_transport"],
        live_submission_bound=False,
        place_order_path=runtime_config["live_order_path"],
        cancel_order_path=runtime_config["cancel_order_path"],
        readiness_notes=list(runtime_config["readiness_notes"]),
        missing_requirements=list(runtime_config["missing_requirements"]),
        metadata={
            "runtime_config": runtime_config,
            "execution_ready": runtime_config["runtime_ready"],
            "place_auditable": True,
            "cancel_auditable": True,
        },
    )


def describe_polymarket_resolution_policy_surface(
    market: MarketDescriptor,
    *,
    snapshot: MarketSnapshot | None = None,
) -> PolymarketResolutionPolicySurface:
    return PolymarketSurrogateClient().describe_resolution_policy_surface(market, snapshot=snapshot)


def build_polymarket_resolution_policy_completeness_report(
    markets: list[MarketDescriptor],
    *,
    metadata: dict[str, Any] | None = None,
) -> PolymarketResolutionPolicyCompletenessReport:
    return PolymarketSurrogateClient().build_resolution_policy_completeness_report(markets, metadata=metadata)


class PolymarketSurrogateClient:
    def __init__(self) -> None:
        self._markets = [
            {
                "id": "pm_demo_election",
                "eventId": "demo-election-2026",
                "venueMarketId": "pm_demo_election",
                "slug": "demo-election-market",
                "question": "Will the demo candidate win the election?",
                "description": "Synthetic market used for local testing.",
                "category": "Politics",
                "active": True,
                "closed": False,
                "resolutionSource": "https://example.com/resolution",
                "resolutionSourceUrl": "https://example.com/resolution",
                "endDate": "2030-11-05T00:00:00Z",
                "startDate": "2030-10-01T00:00:00Z",
                "outcomes": ["Yes", "No"],
                "outcomePrices": [0.58, 0.42],
                "liquidity": 25000,
                "volume": 190000,
                "volume24h": 14500,
                "clobTokenIds": ["yes_demo", "no_demo"],
            }
        ]

    def list_markets(self, *, limit: int = 20, active: bool = True, closed: bool = False) -> list[MarketDescriptor]:
        markets = [self._to_descriptor(item) for item in self._markets]
        filtered = [item for item in markets if item.active == active and item.closed == closed]
        return filtered[:limit]

    def get_market(self, *, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
        for item in self._markets:
            if market_id and item["id"] == market_id:
                return self._to_descriptor(item)
            if slug and item["slug"] == slug:
                return self._to_descriptor(item)
        raise KeyError(f"Unknown surrogate market market_id={market_id!r} slug={slug!r}")

    def get_snapshot(self, descriptor: MarketDescriptor) -> MarketSnapshot:
        raw = next(item for item in self._markets if item["id"] == descriptor.market_id)
        prices = _coerce_prices(raw.get("outcomePrices"))
        price_yes = prices[0] if prices else 0.5
        price_no = prices[1] if len(prices) > 1 else max(0.0, 1.0 - price_yes)
        trades = _extract_trades(raw)
        snapshot_ts = _snapshot_timestamp(raw, descriptor=descriptor, trades=trades)
        orderbook = _parse_orderbook(raw, fallback_yes=price_yes)
        return MarketSnapshot(
            venue=VenueName.polymarket,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            slug=descriptor.slug,
            title=descriptor.title,
            question=descriptor.question,
            status=descriptor.status,
            snapshot_ts=snapshot_ts,
            price_yes=price_yes,
            price_no=price_no,
            midpoint_yes=price_yes,
            spread_bps=35.0,
            orderbook=orderbook,
            trades=trades,
            orderbook_depth=descriptor.liquidity,
            liquidity=descriptor.liquidity,
            volume=descriptor.volume,
            resolution_source=descriptor.resolution_source,
            source_url=descriptor.source_url,
            canonical_event_id=descriptor.canonical_event_id,
            close_time=descriptor.close_time or descriptor.end_date,
            raw=raw,
        )

    def get_events(self, market_id: str | None = None, *, limit: int = 20) -> list[MarketDescriptor]:
        markets = self.list_markets(limit=limit)
        if market_id:
            markets = [market for market in markets if market.market_id == market_id or market.canonical_event_id == market_id]
        return _event_markets(markets)

    def get_positions(self, market_id: str | None = None) -> list[LedgerPosition]:
        return _load_position_records(VenueName.polymarket, market_id)

    def describe_data_surface(self) -> MarketDataSurface:
        return _market_data_surface(
            backend_mode="surrogate",
            events_source="surrogate_market_catalog",
            positions_source="local_position_cache",
            market_feed_source="surrogate_snapshot",
            user_feed_source="local_position_cache",
            transport_prefix="surrogate_snapshot",
            notes=[
                "surrogate_read_only_surface",
                "no_websocket_live_integration",
                "no_rtds_live_integration",
            ],
        )

    def describe_resolution_policy_surface(self, market: MarketDescriptor, *, snapshot: MarketSnapshot | None = None) -> PolymarketResolutionPolicySurface:
        policy_surface = describe_resolution_policy_surface(market, snapshot=snapshot)
        return PolymarketResolutionPolicySurface(
            policy_surface=policy_surface,
            summary=(
                f"policy_complete={policy_surface.policy_complete}; "
                f"policy_coherent={policy_surface.policy_coherent}; "
                f"no_trade={policy_surface.no_trade}"
            ),
            no_trade=policy_surface.no_trade,
            policy_complete=policy_surface.policy_complete,
            policy_coherent=policy_surface.policy_coherent,
            completeness_rate=policy_surface.policy_completeness_score,
            coherence_rate=policy_surface.policy_coherence_score,
            policy_status=policy_surface.status.value,
            manual_review_required=policy_surface.manual_review_required,
            official_source=policy_surface.official_source,
            official_source_url=policy_surface.official_source_url or policy_surface.source_url,
            missing_fields=list(policy_surface.missing_fields),
            required_fields_count=policy_surface.required_fields_count,
            present_fields_count=policy_surface.present_fields_count,
            metadata={
                "market_id": market.market_id,
                "snapshot_status": getattr(snapshot, "status", None).value if snapshot is not None else None,
                "official_source_url": policy_surface.official_source_url or policy_surface.source_url,
            },
        )

    def build_resolution_policy_completeness_report(
        self,
        markets: list[MarketDescriptor] | None = None,
        *,
        limit: int = 25,
        metadata: dict[str, Any] | None = None,
    ) -> PolymarketResolutionPolicyCompletenessReport:
        selected = list(markets or self.list_markets(limit=limit))
        report = build_resolution_policy_completeness_report(selected, metadata=metadata)
        return PolymarketResolutionPolicyCompletenessReport(
            report=report,
            summary=(
                f"{report.complete_count}/{report.market_count} complete; "
                f"{report.coherent_count}/{report.market_count} coherent; "
                f"{report.no_trade_count}/{report.market_count} no_trade"
            ),
            manual_review_rate=report.manual_review_rate,
            ambiguous_rate=report.ambiguous_rate,
            unavailable_rate=report.unavailable_rate,
            metadata={
                "market_count": report.market_count,
                "complete_rate": report.complete_rate,
                "coherent_rate": report.coherent_rate,
                **dict(metadata or {}),
            },
        )

    @staticmethod
    def _to_descriptor(raw: dict[str, Any]) -> MarketDescriptor:
        return _descriptor_from_gamma(raw)


class PolymarketClient:
    def __init__(
        self,
        base_url: str = GAMMA_API_BASE_URL,
        timeout_seconds: float = 10.0,
        *,
        fixtures_root: str | None = None,
        events_path: str | None = None,
        positions_path: str | None = None,
        market_feed_path: str | None = None,
        user_feed_path: str | None = None,
        market_websocket_url: str | None = None,
        user_websocket_url: str | None = None,
        rtds_url: str | None = None,
        api_key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
        gamma_auth_address: str | None = None,
        websocket_timeout_seconds: float = 10.0,
        websocket_heartbeat_seconds: float = 10.0,
        rtds_heartbeat_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._source = HttpJSONSource(self.base_url, timeout_seconds=self.timeout_seconds)
        self.fixtures_root = self._resolve_fixtures_root(fixtures_root)
        self.events_path = (events_path or os.getenv("POLYMARKET_EVENTS_PATH") or "events").strip("/")
        self.positions_path = (positions_path or os.getenv("POLYMARKET_POSITIONS_PATH") or "positions").strip("/")
        self.market_feed_path = (market_feed_path or os.getenv("POLYMARKET_MARKET_FEED_PATH") or "market-feed").strip("/")
        self.user_feed_path = (user_feed_path or os.getenv("POLYMARKET_USER_FEED_PATH") or "user-feed").strip("/")
        self.market_websocket_url = (
            market_websocket_url
            or os.getenv("POLYMARKET_MARKET_WEBSOCKET_URL")
            or POLYMARKET_MARKET_WEBSOCKET_URL
        ).strip()
        self.user_websocket_url = (
            user_websocket_url
            or os.getenv("POLYMARKET_USER_WEBSOCKET_URL")
            or POLYMARKET_USER_WEBSOCKET_URL
        ).strip()
        self.rtds_url = (rtds_url or os.getenv("POLYMARKET_RTDS_URL") or POLYMARKET_RTDS_URL).strip()
        self.websocket_timeout_seconds = float(websocket_timeout_seconds)
        self.websocket_heartbeat_seconds = float(websocket_heartbeat_seconds)
        self.rtds_heartbeat_seconds = float(rtds_heartbeat_seconds)
        self.realtime_credentials = PolymarketRealtimeCredentials(
            api_key=(api_key or os.getenv("POLYMARKET_API_KEY")),
            secret=(secret or os.getenv("POLYMARKET_API_SECRET")),
            passphrase=(passphrase or os.getenv("POLYMARKET_API_PASSPHRASE")),
            gamma_auth_address=(gamma_auth_address or os.getenv("POLYMARKET_GAMMA_AUTH_ADDRESS")),
        )

    def _resolve_realtime_credentials(
        self,
        auth: PolymarketRealtimeCredentials | dict[str, Any] | None = None,
    ) -> PolymarketRealtimeCredentials:
        if auth is None:
            return self.realtime_credentials
        if isinstance(auth, PolymarketRealtimeCredentials):
            return auth
        return PolymarketRealtimeCredentials(
            api_key=auth.get("api_key") or auth.get("apiKey"),
            secret=auth.get("secret"),
            passphrase=auth.get("passphrase"),
            gamma_auth_address=auth.get("gamma_auth_address") or auth.get("address"),
        )

    def _open_websocket_session(
        self,
        *,
        endpoint: str,
        channel: str,
        subscription_message: dict[str, Any],
        auth_requirement: str,
        session_requirement: str,
        heartbeat_interval_seconds: float,
        metadata: dict[str, Any] | None = None,
    ) -> PolymarketWebSocketSession:
        if websocket_client is None:
            raise RuntimeError("websocket-client is required for Polymarket websocket bindings.")
        if not endpoint:
            raise ValueError(f"{channel} websocket endpoint is not configured.")
        connection = websocket_client.create_connection(endpoint, timeout=self.websocket_timeout_seconds)
        connection.send(json.dumps(subscription_message))
        session = PolymarketWebSocketSession(
            endpoint=endpoint,
            channel=channel,
            subscription_message=subscription_message,
            connection=connection,
            auth_requirement=auth_requirement,
            session_requirement=session_requirement,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            metadata=dict(metadata or {}),
        )
        session.start_heartbeat()
        return session

    def build_market_websocket_subscription(
        self,
        asset_ids: list[str],
        *,
        custom_feature_enabled: bool = True,
    ) -> dict[str, Any]:
        normalized_assets = [str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()]
        if not normalized_assets:
            raise ValueError("asset_ids is required for the Polymarket market websocket.")
        return {
            "assets_ids": normalized_assets,
            "type": "market",
            "custom_feature_enabled": bool(custom_feature_enabled),
        }

    def build_user_websocket_subscription(
        self,
        market_ids: list[str],
        *,
        auth: PolymarketRealtimeCredentials | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_markets = [str(market_id).strip() for market_id in market_ids if str(market_id).strip()]
        if not normalized_markets:
            raise ValueError("market_ids is required for the Polymarket user websocket.")
        credentials = self._resolve_realtime_credentials(auth)
        if not credentials.configured:
            raise RuntimeError("Polymarket user websocket requires api_key, secret, and passphrase.")
        return {
            "type": "user",
            "markets": normalized_markets,
            "auth": credentials.user_auth_payload(),
        }

    def build_rtds_subscription(
        self,
        subscriptions: list[dict[str, Any]],
        *,
        auth: PolymarketRealtimeCredentials | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_subscriptions = [dict(subscription) for subscription in subscriptions if isinstance(subscription, dict)]
        if not normalized_subscriptions:
            raise ValueError("subscriptions is required for the Polymarket RTDS websocket.")
        credentials = self._resolve_realtime_credentials(auth)
        gamma_auth = credentials.gamma_auth_payload()
        if gamma_auth is not None:
            for subscription in normalized_subscriptions:
                subscription.setdefault("gamma_auth", gamma_auth)
        return {
            "action": "subscribe",
            "subscriptions": normalized_subscriptions,
        }

    def open_market_websocket(
        self,
        asset_ids: list[str],
        *,
        custom_feature_enabled: bool = True,
        heartbeat_interval_seconds: float | None = None,
    ) -> PolymarketWebSocketSession:
        subscription = self.build_market_websocket_subscription(
            asset_ids,
            custom_feature_enabled=custom_feature_enabled,
        )
        return self._open_websocket_session(
            endpoint=self.market_websocket_url,
            channel="websocket_market",
            subscription_message=subscription,
            auth_requirement="none",
            session_requirement="none",
            heartbeat_interval_seconds=self.websocket_heartbeat_seconds if heartbeat_interval_seconds is None else float(heartbeat_interval_seconds),
            metadata={
                "assets_ids": list(subscription["assets_ids"]),
                "custom_feature_enabled": bool(subscription["custom_feature_enabled"]),
                "subscription_kind": "market",
            },
        )

    def open_user_websocket(
        self,
        market_ids: list[str],
        *,
        auth: PolymarketRealtimeCredentials | dict[str, Any] | None = None,
        heartbeat_interval_seconds: float | None = None,
    ) -> PolymarketWebSocketSession:
        credentials = self._resolve_realtime_credentials(auth)
        subscription = self.build_user_websocket_subscription(market_ids, auth=credentials)
        return self._open_websocket_session(
            endpoint=self.user_websocket_url,
            channel="websocket_user",
            subscription_message=subscription,
            auth_requirement="required",
            session_requirement="authenticated",
            heartbeat_interval_seconds=self.websocket_heartbeat_seconds if heartbeat_interval_seconds is None else float(heartbeat_interval_seconds),
            metadata={
                "markets": list(subscription["markets"]),
                "subscription_kind": "user",
                "auth_configured": credentials.configured,
            },
        )

    def open_rtds(
        self,
        subscriptions: list[dict[str, Any]],
        *,
        auth: PolymarketRealtimeCredentials | dict[str, Any] | None = None,
        heartbeat_interval_seconds: float | None = None,
    ) -> PolymarketWebSocketSession:
        credentials = self._resolve_realtime_credentials(auth)
        subscription = self.build_rtds_subscription(subscriptions, auth=credentials)
        return self._open_websocket_session(
            endpoint=self.rtds_url,
            channel="rtds",
            subscription_message=subscription,
            auth_requirement="optional",
            session_requirement="authenticated" if credentials.gamma_auth_address else "none",
            heartbeat_interval_seconds=self.rtds_heartbeat_seconds if heartbeat_interval_seconds is None else float(heartbeat_interval_seconds),
            metadata={
                "subscription_count": len(subscription["subscriptions"]),
                "subscription_kind": "rtds",
                "gamma_auth_configured": bool(credentials.gamma_auth_address),
            },
        )

    def list_markets(self, *, limit: int = 20, active: bool = True, closed: bool = False) -> list[MarketDescriptor]:
        payload = self._fetch_json(
            "markets",
            query={
                "active": str(active).lower(),
                "closed": str(closed).lower(),
                "limit": limit,
            },
            fixture_candidates=("markets.json", "markets/index.json", "markets/list.json"),
        )
        markets = _extract_markets_from_payload(payload)
        if not markets:
            raise ValueError("Expected /markets response to contain market records.")
        filtered = [item for item in markets if item.active == active and item.closed == closed]
        return filtered[:limit]

    def get_market(self, *, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
        if market_id:
            payload = self._fetch_json(
                f"markets/{market_id}",
                fixture_candidates=(
                    f"markets/{market_id}.json",
                    f"markets/{market_id}/market.json",
                ),
            )
            return _descriptor_from_gamma(_unwrap_market_payload(payload))
        if not slug:
            raise ValueError("market_id or slug is required")
        for descriptor in self.list_markets(limit=200):
            if descriptor.slug == slug:
                return descriptor
        raise KeyError(f"No market found for slug={slug!r}")

    def get_snapshot(self, descriptor: MarketDescriptor) -> MarketSnapshot:
        raw = self._fetch_json(
            f"markets/{descriptor.market_id}",
            fixture_candidates=(
                f"markets/{descriptor.market_id}/snapshot.json",
                f"snapshots/{descriptor.market_id}.json",
                f"markets/{descriptor.market_id}.json",
            ),
        )
        raw = _unwrap_market_payload(raw)
        prices = _coerce_prices(raw.get("outcomePrices"))
        price_yes = prices[0] if prices else 0.5
        price_no = prices[1] if len(prices) > 1 else max(0.0, 1.0 - price_yes)
        trades = _extract_trades(raw)
        snapshot_ts = _snapshot_timestamp(raw, descriptor=descriptor, trades=trades)
        orderbook = _parse_orderbook(raw, fallback_yes=price_yes)
        return MarketSnapshot(
            venue=VenueName.polymarket,
            venue_type=descriptor.venue_type,
            market_id=descriptor.market_id,
            slug=descriptor.slug,
            title=descriptor.title,
            question=descriptor.question,
            status=descriptor.status,
            snapshot_ts=snapshot_ts,
            price_yes=price_yes,
            price_no=price_no,
            midpoint_yes=price_yes,
            spread_bps=0.0,
            orderbook=orderbook,
            trades=trades,
            orderbook_depth=descriptor.liquidity,
            liquidity=descriptor.liquidity,
            volume=descriptor.volume,
            resolution_source=descriptor.resolution_source,
            source_url=descriptor.source_url,
            canonical_event_id=descriptor.canonical_event_id,
            close_time=descriptor.close_time or descriptor.end_date,
            raw=raw,
        )

    def get_events(self, market_id: str | None = None, *, limit: int = 20) -> list[MarketDescriptor]:
        markets: list[MarketDescriptor] = []
        if market_id is not None:
            for path in self._candidate_market_event_paths(market_id):
                payload = self._safe_get(path)
                if payload is None:
                    continue
                markets = _extract_markets_from_payload(payload)
                if markets:
                    break
        if not markets:
            markets = self.list_markets(limit=limit)
        if market_id:
            markets = [market for market in markets if market.market_id == market_id or market.canonical_event_id == market_id]
        return _event_markets(markets)

    def get_positions(self, market_id: str | None = None) -> list[LedgerPosition]:
        positions: list[LedgerPosition] = []
        if market_id is not None:
            for path in self._candidate_positions_paths(market_id):
                payload = self._safe_get(path)
                if payload is None:
                    continue
                positions = _extract_positions_from_payload(payload, venue=VenueName.polymarket, market_id=market_id)
                if positions:
                    break
        if not positions:
            positions = _load_position_records(VenueName.polymarket, market_id)
        return positions

    def describe_data_surface(self) -> MarketDataSurface:
        surface = _market_data_surface(
            backend_mode="fixture" if self.fixtures_root is not None else "live",
            events_source=self.events_path,
            positions_source=self.positions_path,
            market_feed_source=self.market_feed_path,
            user_feed_source=self.user_feed_path,
            transport_prefix="fixture_cache" if self.fixtures_root is not None else "http_json",
            notes=[
                "read_only_fixture_surface" if self.fixtures_root is not None else "read_only_http_json_surface",
                "websocket_not_implemented_here",
                "rtds_not_implemented_here",
                "local_fixture_backing" if self.fixtures_root is not None else "configured_http_json_endpoints",
            ],
        )
        if self.fixtures_root is not None:
            surface = surface.model_copy(update={"metadata": {**dict(surface.metadata), "fixtures_root": str(self.fixtures_root)}})
        elif self.base_url.rstrip("/") == GAMMA_API_BASE_URL.rstrip("/"):
            surface = surface.model_copy(update=self._live_websocket_surface_overrides(surface))
        return surface

    def describe_resolution_policy_surface(self, market: MarketDescriptor, *, snapshot: MarketSnapshot | None = None) -> PolymarketResolutionPolicySurface:
        policy_surface = describe_resolution_policy_surface(market, snapshot=snapshot)
        return PolymarketResolutionPolicySurface(
            policy_surface=policy_surface,
            summary=(
                f"policy_complete={policy_surface.policy_complete}; "
                f"policy_coherent={policy_surface.policy_coherent}; "
                f"no_trade={policy_surface.no_trade}"
            ),
            no_trade=policy_surface.no_trade,
            policy_complete=policy_surface.policy_complete,
            policy_coherent=policy_surface.policy_coherent,
            completeness_rate=policy_surface.policy_completeness_score,
            coherence_rate=policy_surface.policy_coherence_score,
            policy_status=policy_surface.status.value,
            manual_review_required=policy_surface.manual_review_required,
            official_source=policy_surface.official_source,
            official_source_url=policy_surface.official_source_url or policy_surface.source_url,
            missing_fields=list(policy_surface.missing_fields),
            required_fields_count=policy_surface.required_fields_count,
            present_fields_count=policy_surface.present_fields_count,
            metadata={
                "market_id": market.market_id,
                "snapshot_status": getattr(snapshot, "status", None).value if snapshot is not None else None,
                "fixtures_root": str(self.fixtures_root) if self.fixtures_root is not None else None,
                "official_source_url": policy_surface.official_source_url or policy_surface.source_url,
            },
        )

    def build_resolution_policy_completeness_report(
        self,
        markets: list[MarketDescriptor] | None = None,
        *,
        limit: int = 25,
        metadata: dict[str, Any] | None = None,
    ) -> PolymarketResolutionPolicyCompletenessReport:
        selected = list(markets or self.list_markets(limit=limit))
        report = build_resolution_policy_completeness_report(selected, metadata=metadata)
        return PolymarketResolutionPolicyCompletenessReport(
            report=report,
            summary=(
                f"{report.complete_count}/{report.market_count} complete; "
                f"{report.coherent_count}/{report.market_count} coherent; "
                f"{report.no_trade_count}/{report.market_count} no_trade"
            ),
            manual_review_rate=report.manual_review_rate,
            ambiguous_rate=report.ambiguous_rate,
            unavailable_rate=report.unavailable_rate,
            metadata={
                "market_count": report.market_count,
                "complete_rate": report.complete_rate,
                "coherent_rate": report.coherent_rate,
                **dict(metadata or {}),
                "fixtures_root": str(self.fixtures_root) if self.fixtures_root is not None else None,
            },
        )

    def _live_websocket_surface_overrides(self, surface: MarketDataSurface) -> dict[str, Any]:
        credentials = self.realtime_credentials
        market_ready = bool(self.market_websocket_url)
        user_ready = bool(self.user_websocket_url and credentials.configured)
        rtds_ready = bool(self.rtds_url)

        route_refs = dict(surface.route_refs)
        route_refs.update(
            {
                "market_websocket": self.market_websocket_url,
                "user_websocket": self.user_websocket_url,
                "rtds": self.rtds_url,
            }
        )

        configured_endpoints = dict(surface.configured_endpoints)
        configured_endpoints.update(
            {
                "market_websocket_url": self.market_websocket_url,
                "user_websocket_url": self.user_websocket_url,
                "rtds_url": self.rtds_url,
            }
        )

        market_probe = {
            "status": "configured_endpoint" if market_ready else "unavailable",
            "transport": "websocket",
            "connector": self.market_websocket_url,
            "route_ref": self.market_websocket_url,
            "subscription_capable": True,
            "replayable": False,
            "cache_backed": False,
            "probe_ready": market_ready,
            "operational_status": "ready" if market_ready else "unavailable",
            "recommended_action": "open_market_websocket" if market_ready else "configure_market_websocket_url",
            "severity": "info" if market_ready else "warning",
            "gap_reason": "live_websocket_bindable" if market_ready else "missing_market_websocket_url",
            "gap_class": "live_bindable" if market_ready else "not_bound",
            "documented_route_ref": self.market_websocket_url,
            "auth_requirement": "none",
            "session_requirement": "none",
            "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
            "heartbeat_seconds": self.websocket_heartbeat_seconds,
            "subscription_message": {
                "assets_ids": [],
                "type": "market",
                "custom_feature_enabled": True,
            },
        }
        user_probe = {
            "status": "configured_endpoint" if user_ready else ("auth_required" if self.user_websocket_url else "unavailable"),
            "transport": "websocket",
            "connector": self.user_websocket_url,
            "route_ref": self.user_websocket_url,
            "subscription_capable": bool(credentials.configured),
            "replayable": False,
            "cache_backed": False,
            "probe_ready": user_ready,
            "operational_status": "ready" if user_ready else ("auth_required" if self.user_websocket_url else "unavailable"),
            "recommended_action": "open_user_websocket" if user_ready else "configure_user_websocket_auth",
            "severity": "info" if user_ready else "warning",
            "gap_reason": "live_user_websocket_bindable" if user_ready else "missing_user_websocket_credentials",
            "gap_class": "live_bindable" if user_ready else "auth_required",
            "documented_route_ref": self.user_websocket_url,
            "auth_requirement": "required",
            "session_requirement": "authenticated",
            "auth_session": {
                "auth_requirement": "required",
                "session_requirement": "authenticated",
                "auth_configured": credentials.configured,
            },
            "heartbeat_seconds": self.websocket_heartbeat_seconds,
            "subscription_message": {
                "type": "user",
                "markets": [],
                "auth": credentials.user_auth_payload() if credentials.configured else None,
            },
        }
        rtds_probe = {
            "status": "configured_endpoint" if rtds_ready else "unavailable",
            "transport": "rtds",
            "connector": self.rtds_url,
            "route_ref": self.rtds_url,
            "subscription_capable": True,
            "replayable": False,
            "cache_backed": False,
            "probe_ready": rtds_ready,
            "operational_status": "ready" if rtds_ready else "unavailable",
            "recommended_action": "open_rtds" if rtds_ready else "configure_rtds_url",
            "severity": "info" if rtds_ready else "warning",
            "gap_reason": "rtds_bindable" if rtds_ready else "missing_rtds_url",
            "gap_class": "live_bindable" if rtds_ready else "not_bound",
            "documented_route_ref": self.rtds_url,
            "auth_requirement": "optional",
            "session_requirement": "none",
            "auth_session": {"auth_requirement": "optional", "session_requirement": "none"},
            "heartbeat_seconds": self.rtds_heartbeat_seconds,
            "subscription_message": {
                "action": "subscribe",
                "subscriptions": [],
            },
        }

        availability_probes = dict(surface.availability_probes)
        availability_probes.update(
            {
                "websocket_market": market_probe,
                "websocket_user": user_probe,
                "rtds": rtds_probe,
            }
        )

        cache_fallbacks = dict(surface.cache_fallbacks)
        cache_fallbacks.update(
            {
                "websocket_market": {
                    "status": "live",
                    "recommended_action": market_probe["recommended_action"],
                    "gap_reason": market_probe["gap_reason"],
                },
                "websocket_user": {
                    "status": "live" if user_ready else "auth_required",
                    "recommended_action": user_probe["recommended_action"],
                    "gap_reason": user_probe["gap_reason"],
                },
                "rtds": {
                    "status": "live",
                    "recommended_action": rtds_probe["recommended_action"],
                    "gap_reason": rtds_probe["gap_reason"],
                },
            }
        )

        subscription_preview = {
            **dict(surface.subscription_preview),
            "mode": "live_bindable",
            "supports_live_subscriptions": True,
            "recommended_poll_transport": "websocket",
            "recommended_user_transport": "websocket" if user_ready else surface.user_feed_transport,
            "auth_requirements": {
                "market_feed": "none",
                "user_feed": "none",
                "websocket_market": "none",
                "websocket_user": "required",
                "rtds": "optional",
            },
            "session_requirements": {
                "market_feed": "none",
                "user_feed": "none" if user_ready else dict(surface.subscription_preview.get("session_requirements") or {}).get("user_feed", "none"),
                "websocket_market": "none",
                "websocket_user": "authenticated",
                "rtds": "none",
            },
            "channels": {
                **dict(surface.subscription_preview.get("channels") or {}),
                "websocket_market": {
                    "topic": "polymarket:websocket_market",
                    "route_ref": self.market_websocket_url,
                    "status": market_probe["operational_status"],
                    "subscription_capable": True,
                    "recommended_action": market_probe["recommended_action"],
                    "subscription_intent": "subscribe_market",
                    "auth_requirement": "none",
                    "gap_class": market_probe["gap_class"],
                    "auth_session": market_probe["auth_session"],
                    "channel_spec": {
                        "delivery_mode": "stream",
                        "message_kind": "market_stream",
                        "cadence_hint": "push",
                        "heartbeat_seconds": self.websocket_heartbeat_seconds,
                    },
                },
                "websocket_user": {
                    "topic": "polymarket:websocket_user",
                    "route_ref": self.user_websocket_url,
                    "status": user_probe["operational_status"],
                    "subscription_capable": user_ready,
                    "recommended_action": user_probe["recommended_action"],
                    "subscription_intent": "subscribe_user",
                    "auth_requirement": "required",
                    "gap_class": user_probe["gap_class"],
                    "auth_session": user_probe["auth_session"],
                    "channel_spec": {
                        "delivery_mode": "stream",
                        "message_kind": "user_stream",
                        "cadence_hint": "push",
                        "heartbeat_seconds": self.websocket_heartbeat_seconds,
                    },
                },
                "rtds": {
                    "topic": "polymarket:rtds",
                    "route_ref": self.rtds_url,
                    "status": rtds_probe["operational_status"],
                    "subscription_capable": True,
                    "recommended_action": rtds_probe["recommended_action"],
                    "subscription_intent": "subscribe_topic",
                    "auth_requirement": "optional",
                    "gap_class": rtds_probe["gap_class"],
                    "auth_session": rtds_probe["auth_session"],
                    "channel_spec": {
                        "delivery_mode": "stream",
                        "message_kind": "rtds_update",
                        "cadence_hint": "push",
                        "heartbeat_seconds": self.rtds_heartbeat_seconds,
                    },
                },
            },
            "channel_specs": {
                **dict(surface.subscription_preview.get("channel_specs") or {}),
                "websocket_market": {
                    "route_ref": self.market_websocket_url,
                    "delivery_mode": "stream",
                    "message_kind": "market_stream",
                    "auth_requirement": "none",
                    "session_requirement": "none",
                    "subscription_intent": "subscribe_market",
                    "preview_probe": dict(market_probe),
                    "replay_fallback": "no_live_binding",
                    "explicit_gap": None,
                    "gap_class": market_probe["gap_class"],
                    "auth_session": market_probe["auth_session"],
                },
                "websocket_user": {
                    "route_ref": self.user_websocket_url,
                    "delivery_mode": "stream",
                    "message_kind": "user_stream",
                    "auth_requirement": "required",
                    "session_requirement": "authenticated",
                    "subscription_intent": "subscribe_user",
                    "preview_probe": dict(user_probe),
                    "replay_fallback": "no_live_binding",
                    "explicit_gap": None if user_ready else "user_websocket_auth_required",
                    "gap_class": user_probe["gap_class"],
                    "auth_session": user_probe["auth_session"],
                },
                "rtds": {
                    "route_ref": self.rtds_url,
                    "delivery_mode": "stream",
                    "message_kind": "rtds_update",
                    "auth_requirement": "optional",
                    "session_requirement": "none",
                    "subscription_intent": "subscribe_topic",
                    "preview_probe": dict(rtds_probe),
                    "replay_fallback": "no_live_binding",
                    "explicit_gap": None,
                    "gap_class": rtds_probe["gap_class"],
                    "auth_session": rtds_probe["auth_session"],
                },
            },
            "subscription_bundles": {
                **dict(surface.subscription_preview.get("subscription_bundles") or {}),
                "websocket_live_bundle": {
                    "bundle_id": "polymarket:websocket_live_bundle",
                    "channels": ["websocket_market", "websocket_user"],
                    "route_refs": {
                        "market_websocket": self.market_websocket_url,
                        "user_websocket": self.user_websocket_url,
                    },
                    "auth_requirement": "required",
                    "session_requirement": "authenticated" if user_ready else "none",
                    "preview_only": False,
                    "testable": True,
                },
                "rtds_live_bundle": {
                    "bundle_id": "polymarket:rtds_live_bundle",
                    "channels": ["rtds"],
                    "route_refs": {"rtds": self.rtds_url},
                    "auth_requirement": "optional",
                    "session_requirement": "none",
                    "preview_only": False,
                    "testable": True,
                },
            },
            "preview_flow": {
                "flow_id": "polymarket:live_websocket_rtds_bindings",
                "mode": "live_bindable",
                "testable": True,
                "live_claimed": True,
                "route_refs": {
                    "market_feed": route_refs.get("market_feed"),
                    "user_feed": route_refs.get("user_feed"),
                    "market_websocket": self.market_websocket_url,
                    "user_websocket": self.user_websocket_url,
                    "rtds": self.rtds_url,
                },
                "steps": [
                    {
                        "step": "resolve_routes",
                        "status": "complete",
                        "documented_route_refs": {
                            "market_feed": route_refs.get("market_feed"),
                            "user_feed": route_refs.get("user_feed"),
                            "market_websocket": self.market_websocket_url,
                            "user_websocket": self.user_websocket_url,
                            "rtds": self.rtds_url,
                        },
                    },
                    {
                        "step": "confirm_auth_and_session",
                        "status": "complete" if user_ready else "partial",
                        "auth_requirements": {
                            "market_feed": "none",
                            "user_feed": "none",
                            "websocket_market": "none",
                            "websocket_user": "required",
                            "rtds": "optional",
                        },
                        "session_requirements": {
                            "market_feed": "none",
                            "user_feed": "none",
                            "websocket_market": "none",
                            "websocket_user": "authenticated",
                            "rtds": "none",
                        },
                    },
                    {
                        "step": "select_live_bindings",
                        "status": "complete" if market_ready and rtds_ready else "partial",
                        "live_targets": {
                            "websocket_market": market_probe["recommended_action"],
                            "websocket_user": user_probe["recommended_action"],
                            "rtds": rtds_probe["recommended_action"],
                        },
                    },
                ],
                "bounded_channels": [],
                "preview_only_channels": [],
                "probe_statuses": {
                    "websocket_market": market_probe["operational_status"],
                    "websocket_user": user_probe["operational_status"],
                    "rtds": rtds_probe["operational_status"],
                },
                "expected_outcome": "live_bindable_with_optional_user_auth" if user_ready else "live_bindable_user_auth_required",
            },
            "auth_requirements": {
                "market_feed": "none",
                "user_feed": "none",
                "websocket_market": "none",
                "websocket_user": "required",
                "rtds": "optional",
            },
            "documented_preview_routes": {
                "market_websocket": self.market_websocket_url,
                "user_websocket": self.user_websocket_url,
                "rtds": self.rtds_url,
            },
            "gap_summary": {
                **dict(surface.subscription_preview.get("gap_summary") or {}),
                "live_transport_supported_count": 3,
                "preview_only_channel_count": 0,
                "live_transport_not_supported_count": 0 if user_ready else 1,
                "documented_preview_routes": {
                    "market_websocket": self.market_websocket_url,
                    "user_websocket": self.user_websocket_url,
                    "rtds": self.rtds_url,
                },
            },
            "recommended_subscriptions": [
                {
                    "channel": "websocket_market",
                    "intent": "subscribe_market",
                    "route_ref": self.market_websocket_url,
                    "recommended_action": market_probe["recommended_action"],
                },
                {
                    "channel": "websocket_user",
                    "intent": "subscribe_user",
                    "route_ref": self.user_websocket_url,
                    "recommended_action": user_probe["recommended_action"],
                },
                {
                    "channel": "rtds",
                    "intent": "subscribe_topic",
                    "route_ref": self.rtds_url,
                    "recommended_action": rtds_probe["recommended_action"],
                },
            ],
        }

        probe_bundle = {
            **dict(surface.probe_bundle),
            "bundle_status": "ready" if market_ready and rtds_ready else "degraded",
            "primary_path": market_probe["recommended_action"],
            "fallback_path": "use_read_only_surfaces_only" if not market_ready else "open_market_websocket",
            "market_feed_status": surface.availability_probes["market_feed"]["operational_status"],
            "user_feed_status": surface.availability_probes["user_feed"]["operational_status"],
            "transport_readiness": {
                **{key: probe["operational_status"] for key, probe in surface.availability_probes.items()},
                "websocket_market": market_probe["operational_status"],
                "websocket_user": user_probe["operational_status"],
                "rtds": rtds_probe["operational_status"],
            },
            "degraded_paths": [
                key
                for key, probe in {
                    **dict(surface.availability_probes),
                    "websocket_market": market_probe,
                    "websocket_user": user_probe,
                    "rtds": rtds_probe,
                }.items()
                if probe.get("operational_status") != "ready"
            ],
            "preview_flow": dict(subscription_preview.get("preview_flow") or {}),
            "highest_severity": "warning" if not user_ready else "info",
        }

        capability_summary = {
            **dict(surface.capability_summary),
            "mode": "live_bindable",
            "live_claimed": True,
            "subscription_mode": "live_bindable",
            "market_feed_path": surface.availability_probes["market_feed"]["recommended_action"],
            "user_feed_path": surface.availability_probes["user_feed"]["recommended_action"],
            "websocket_path": market_probe["recommended_action"],
            "rtds_path": rtds_probe["recommended_action"],
            "has_replayable_market_feed": bool(surface.market_feed_replayable),
            "has_cache_fallback": bool(surface.market_feed_cache_backed or surface.user_feed_cache_backed or surface.rtds_cache_backed),
            "auth_requirements": {
                "market_feed": "none",
                "user_feed": "none",
                "websocket_market": "none",
                "websocket_user": "required",
                "rtds": "optional",
            },
            "market_user_gap_reasons": [
                "market_feed_is_snapshot_only" if surface.market_feed_transport != "websocket" else "market_feed_websocket_bound",
                "user_feed_auth_required" if not user_ready else "user_feed_websocket_bound",
            ],
            "explicit_gaps": [
                "websocket_user_auth_required" if not user_ready else "websocket_user_ready",
            ],
            "rtds_usefulness": {
                "status": "live_bindable",
                "usable_for_live_ops": True,
                "recommended_action": rtds_probe["recommended_action"],
            },
            "recommended_subscriptions": ["websocket_market", "websocket_user", "rtds"],
            "documented_preview_routes": {
                "market_websocket": self.market_websocket_url,
                "user_websocket": self.user_websocket_url,
                "rtds": self.rtds_url,
            },
            "gap_summary": {
                **dict(surface.capability_summary.get("gap_summary") or {}),
                "documented_preview_routes": {
                    "market_websocket": self.market_websocket_url,
                    "user_websocket": self.user_websocket_url,
                    "rtds": self.rtds_url,
                },
            },
            "preview_flow": dict(subscription_preview.get("preview_flow") or {}),
        }

        connector_contracts = {
            **dict(surface.connector_contracts),
            "websocket_market": {
                "mode": "live_bindable",
                "transport": "websocket",
                "connector": self.market_websocket_url,
                "route_ref": self.market_websocket_url,
                "kind": "market_stream",
                "supports_live": True,
                "supports_write": False,
                "subscription_capable": True,
                "replayable": False,
                "cache_backed": False,
                "readiness": market_probe["operational_status"],
                "auth_requirement": "none",
                "session_requirement": "none",
                "preview_only": False,
                "gap_class": market_probe["gap_class"],
                "auth_session": market_probe["auth_session"],
                "endpoint_contract": {
                    "method": "CONNECT",
                    "route_ref": self.market_websocket_url,
                    "request_mode": "subscribe",
                    "response_kind": "market_stream",
                    "read_only": True,
                    "write_capable": False,
                },
            },
            "websocket_user": {
                "mode": "live_bindable",
                "transport": "websocket",
                "connector": self.user_websocket_url,
                "route_ref": self.user_websocket_url,
                "kind": "user_stream",
                "supports_live": user_ready,
                "supports_write": False,
                "subscription_capable": user_ready,
                "replayable": False,
                "cache_backed": False,
                "readiness": user_probe["operational_status"],
                "auth_requirement": "required",
                "session_requirement": "authenticated",
                "preview_only": False,
                "gap_class": user_probe["gap_class"],
                "auth_session": user_probe["auth_session"],
                "endpoint_contract": {
                    "method": "CONNECT",
                    "route_ref": self.user_websocket_url,
                    "request_mode": "subscribe",
                    "response_kind": "user_stream",
                    "read_only": True,
                    "write_capable": False,
                },
            },
            "rtds": {
                "mode": "live_bindable",
                "transport": "rtds",
                "connector": self.rtds_url,
                "route_ref": self.rtds_url,
                "kind": "rtds",
                "supports_live": True,
                "supports_write": False,
                "subscription_capable": True,
                "replayable": False,
                "cache_backed": False,
                "readiness": rtds_probe["operational_status"],
                "auth_requirement": "optional",
                "session_requirement": "none",
                "preview_only": False,
                "gap_class": rtds_probe["gap_class"],
                "auth_session": rtds_probe["auth_session"],
                "endpoint_contract": {
                    "method": "CONNECT",
                    "route_ref": self.rtds_url,
                    "request_mode": "subscribe",
                    "response_kind": "rtds_update",
                    "read_only": True,
                    "write_capable": False,
                },
            },
        }

        runbook = dict(surface.runbook)
        runbook.update(
            {
                "runbook_id": "polymarket_live_websocket_rtds_surface",
                "summary": (
                    "Use Polymarket live websocket market/user feeds and RTDS when live bindings are configured; "
                    "user websocket requires API credentials, RTDS remains optional-auth."
                ),
                "recommended_action": "use_live_websocket_bindings",
                "status": "ready" if market_ready and rtds_ready else "partial",
                "feed_mode": "live_bindable",
                "streaming_mode": "live_websocket_rtds",
                "websocket_status": "ready" if market_ready else "unavailable",
                "rtds_status": "ready" if rtds_ready else "unavailable",
                "next_steps": [
                    "Open the market websocket with asset IDs for the market snapshot stream.",
                    "Provide API credentials before opening the user websocket.",
                    "Subscribe RTDS topics for live monitoring and latency-sensitive signals.",
                ],
                "signals": {
                    **dict(surface.runbook.get("signals") or {}),
                    "supports_websocket": True,
                    "supports_rtds": True,
                    "live_streaming": True,
                    "websocket_status": "ready" if market_ready else "unavailable",
                    "market_websocket_status": market_probe["operational_status"],
                    "user_feed_websocket_status": user_probe["operational_status"],
                    "rtds_status": rtds_probe["operational_status"],
                    "market_feed_connector": "websocket_market" if market_ready else surface.runbook.get("signals", {}).get("market_feed_connector"),
                    "user_feed_connector": "websocket_user" if user_ready else surface.runbook.get("signals", {}).get("user_feed_connector"),
                    "rtds_connector": "rtds",
                    "market_feed_replayable": False,
                    "user_feed_replayable": False,
                    "rtds_replayable": False,
                    "market_feed_cache_backed": False,
                    "user_feed_cache_backed": False,
                    "rtds_cache_backed": False,
                    "route_refs": dict(route_refs),
                    "availability_probes": dict(availability_probes),
                    "cache_fallbacks": dict(cache_fallbacks),
                    "subscription_preview": dict(subscription_preview),
                    "probe_bundle": dict(probe_bundle),
                    "capability_summary": dict(capability_summary),
                    "connector_contracts": dict(connector_contracts),
                },
            }
        )

        return {
            "backend_mode": "live",
            "ingestion_mode": "live_websocket_rtds",
            "market_feed_kind": "market_stream_websocket",
            "user_feed_kind": "user_stream_websocket" if user_ready else surface.user_feed_kind,
            "supports_websocket": True,
            "supports_rtds": True,
            "live_streaming": True,
            "websocket_status": "ready" if market_ready else "unavailable",
            "market_websocket_status": market_probe["operational_status"],
            "user_feed_websocket_status": user_probe["operational_status"],
            "market_feed_transport": "websocket",
            "user_feed_transport": "websocket" if user_ready else surface.user_feed_transport,
            "market_feed_connector": "websocket_market",
            "user_feed_connector": "websocket_user" if user_ready else surface.user_feed_connector,
            "rtds_connector": "rtds",
            "market_feed_status": market_probe["operational_status"],
            "user_feed_status": user_probe["operational_status"],
            "rtds_status": rtds_probe["operational_status"],
            "market_feed_replayable": False,
            "user_feed_replayable": False,
            "rtds_replayable": False,
            "market_feed_cache_backed": False,
            "user_feed_cache_backed": False,
            "rtds_cache_backed": False,
            "configured_endpoints": configured_endpoints,
            "route_refs": route_refs,
            "availability_probes": availability_probes,
            "cache_fallbacks": cache_fallbacks,
            "subscription_preview": subscription_preview,
            "probe_bundle": probe_bundle,
            "capability_summary": capability_summary,
            "connector_contracts": connector_contracts,
            "summary": (
                f"Live Polymarket websocket bindings available for market and RTDS; "
                f"user websocket is {'ready' if user_ready else 'auth_required'}."
            ),
            "runbook": runbook,
            "notes": [
                "live_websocket_market_bindable",
                "live_user_websocket_requires_credentials" if not user_ready else "live_user_websocket_bindable",
                "live_rtds_bindable",
            ],
            "metadata": {
                **dict(surface.metadata),
                "live_bindings": {
                    "market_websocket_url": self.market_websocket_url,
                    "user_websocket_url": self.user_websocket_url,
                    "rtds_url": self.rtds_url,
                    "user_websocket_ready": user_ready,
                    "market_websocket_ready": market_ready,
                    "rtds_ready": rtds_ready,
                },
            },
        }

    def _candidate_market_event_paths(self, market_id: str) -> list[str]:
        return [
            f"{self.events_path}/{market_id}",
            f"markets/{market_id}/events",
            f"markets/{market_id}/market-events",
            f"events/{market_id}",
        ]

    def _candidate_positions_paths(self, market_id: str) -> list[str]:
        return [
            f"{self.positions_path}/{market_id}",
            f"markets/{market_id}/positions",
            f"user/{market_id}/positions",
            f"positions/{market_id}",
        ]

    def _safe_get(self, path: str) -> Any | None:
        if self.fixtures_root is not None:
            payload = self._load_fixture_payload(path, f"{path}.json")
            if payload is not None:
                return payload
        try:
            return self._source.get(path)
        except Exception:
            return None

    def _fetch_json(self, path: str, *, query: dict[str, Any] | None = None, fixture_candidates: tuple[str, ...] = ()) -> Any:
        if self.fixtures_root is not None:
            payload = self._load_fixture_payload(*fixture_candidates, path)
            if payload is not None:
                return payload
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=query,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _resolve_fixtures_root(self, fixtures_root: str | None) -> Path | None:
        candidate = fixtures_root or os.getenv("POLYMARKET_FIXTURES_DIR")
        if candidate:
            root = Path(candidate).expanduser()
            if root.exists():
                return root
        if self.base_url.startswith("file://"):
            root = Path(self.base_url.removeprefix("file://")).expanduser()
            if root.exists():
                return root
        path_candidate = Path(self.base_url)
        if path_candidate.exists():
            return path_candidate
        return None

    def _load_fixture_payload(self, *relative_paths: str) -> Any | None:
        if self.fixtures_root is None:
            return None
        for relative_path in relative_paths:
            candidate = self.fixtures_root / relative_path
            if not candidate.exists():
                continue
            if candidate.suffix.lower() in {".jsonl", ".ndjson"}:
                lines = [line for line in candidate.read_text(encoding="utf-8").splitlines() if line.strip()]
                return [json.loads(line) for line in lines]
            return json.loads(candidate.read_text(encoding="utf-8"))
        return None


def build_polymarket_client(mode: str | None = None) -> PolymarketClient | PolymarketSurrogateClient:
    selected = (mode or os.getenv("PREDICTION_MARKETS_BACKEND", "surrogate")).strip().lower()
    if selected == "live":
        return PolymarketClient(
            base_url=os.getenv("POLYMARKET_GAMMA_BASE_URL", GAMMA_API_BASE_URL),
            timeout_seconds=float(os.getenv("POLYMARKET_TIMEOUT_SECONDS", "10")),
            fixtures_root=os.getenv("POLYMARKET_FIXTURES_DIR"),
            events_path=os.getenv("POLYMARKET_EVENTS_PATH"),
            positions_path=os.getenv("POLYMARKET_POSITIONS_PATH"),
            market_feed_path=os.getenv("POLYMARKET_MARKET_FEED_PATH"),
            user_feed_path=os.getenv("POLYMARKET_USER_FEED_PATH"),
            market_websocket_url=os.getenv("POLYMARKET_MARKET_WEBSOCKET_URL"),
            user_websocket_url=os.getenv("POLYMARKET_USER_WEBSOCKET_URL"),
            rtds_url=os.getenv("POLYMARKET_RTDS_URL"),
            api_key=os.getenv("POLYMARKET_API_KEY"),
            secret=os.getenv("POLYMARKET_API_SECRET"),
            passphrase=os.getenv("POLYMARKET_API_PASSPHRASE"),
            gamma_auth_address=os.getenv("POLYMARKET_GAMMA_AUTH_ADDRESS"),
            websocket_timeout_seconds=float(os.getenv("POLYMARKET_WEBSOCKET_TIMEOUT_SECONDS", "10")),
            websocket_heartbeat_seconds=float(os.getenv("POLYMARKET_WEBSOCKET_HEARTBEAT_SECONDS", "10")),
            rtds_heartbeat_seconds=float(os.getenv("POLYMARKET_RTDS_HEARTBEAT_SECONDS", "5")),
        )
    return PolymarketSurrogateClient()


def _market_data_runbook(
    *,
    backend_mode: str,
    ingestion_mode: str,
    market_feed_status: str,
    user_feed_status: str,
    supports_positions: bool,
    route_refs: dict[str, str],
    availability_probes: dict[str, Any],
    cache_fallbacks: dict[str, Any],
    subscription_preview: dict[str, Any],
    probe_bundle: dict[str, Any],
    capability_summary: dict[str, Any],
    connector_contracts: dict[str, Any],
    gap_summary: dict[str, Any],
) -> dict[str, Any]:
    fixture_mode = backend_mode == "fixture"
    streaming_mode = "read_only_snapshot_polling"
    return {
        "runbook_id": "polymarket_read_only_data_surface",
        "runbook_kind": "surface",
        "summary": (
            "Use Polymarket market snapshots and position caches as read-only input; "
            "websocket and RTDS are not implemented here."
        ),
        "recommended_action": "use_read_only_surfaces_only",
        "status": "ready" if supports_positions else "partial",
        "feed_mode": "read_only",
        "streaming_mode": streaming_mode,
        "websocket_status": "unavailable",
        "rtds_status": "unavailable",
        "next_steps": [
            "Poll market snapshots and positions read-only.",
            "Do not assume websocket or RTDS availability.",
            "Treat positions as a user-feed proxy, not a live user event stream.",
        ],
        "signals": {
            "backend_mode": backend_mode,
            "ingestion_mode": ingestion_mode,
            "feed_mode": "read_only",
            "streaming_mode": streaming_mode,
            "market_feed_status": market_feed_status,
            "user_feed_status": user_feed_status,
            "supports_user_feed": supports_positions,
            "supports_websocket": False,
            "supports_rtds": False,
            "live_streaming": False,
            "websocket_status": "unavailable",
            "market_websocket_status": "unavailable",
            "user_feed_websocket_status": "unavailable",
            "rtds_status": "unavailable",
            "market_feed_connector": "fixture_market_snapshot" if fixture_mode else ("surrogate_market_snapshot" if backend_mode == "surrogate" else "http_json_market_snapshot"),
            "user_feed_connector": (
                "fixture_positions_snapshot"
                if fixture_mode and supports_positions
                else ("local_position_cache" if backend_mode == "surrogate" and supports_positions else ("http_json_position_snapshot" if supports_positions else "unavailable"))
            ),
            "rtds_connector": "unavailable",
            "market_feed_replayable": True,
            "user_feed_replayable": bool(supports_positions),
            "rtds_replayable": False,
            "market_feed_cache_backed": fixture_mode or backend_mode == "surrogate",
            "user_feed_cache_backed": (fixture_mode or backend_mode == "surrogate") and bool(supports_positions),
            "rtds_cache_backed": False,
            "route_refs": dict(route_refs),
            "gap_summary": dict(gap_summary),
            "availability_probes": dict(availability_probes),
            "cache_fallbacks": dict(cache_fallbacks),
            "subscription_preview": dict(subscription_preview),
            "probe_bundle": dict(probe_bundle),
            "capability_summary": dict(capability_summary),
            "connector_contracts": dict(connector_contracts),
            "fixture_mode": fixture_mode,
        },
    }


def _descriptor_from_gamma(raw: dict[str, Any]) -> MarketDescriptor:
    return MarketDescriptor(
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        market_id=str(raw.get("id")),
        venue_market_id=str(raw.get("venueMarketId") or raw.get("venue_market_id") or raw.get("id") or ""),
        title=str(raw.get("question") or raw.get("title") or raw.get("slug") or raw.get("id") or ""),
        slug=raw.get("slug"),
        question=str(raw.get("question") or raw.get("title") or ""),
        description=str(raw.get("description") or ""),
        category=raw.get("category"),
        active=bool(raw.get("active", True)),
        closed=bool(raw.get("closed", False)),
        source_url=_first_non_empty(raw.get("sourceUrl"), raw.get("source_url"), raw.get("url"), raw.get("marketUrl")),
        canonical_event_id=_event_key(raw),
        event_id=_event_key(raw),
        resolution_source=raw.get("resolutionSource"),
        resolution_source_url=raw.get("resolutionSourceUrl") or raw.get("resolution_source_url"),
        open_time=_parse_datetime(raw.get("startDate") or raw.get("openTime") or raw.get("open_time")),
        end_date=_parse_datetime(raw.get("endDate")),
        volume_24h=_safe_float(raw.get("volume24h") or raw.get("volume_24h") or raw.get("volume24hr")),
        outcomes=_coerce_outcomes(raw.get("outcomes")),
        token_ids=_coerce_token_ids(raw.get("clobTokenIds")),
        liquidity=_safe_float(raw.get("liquidity")),
        volume=_safe_float(raw.get("volume")),
        raw=raw,
    )


def _coerce_prices(raw: Any) -> list[float]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    values: list[float] = []
    for item in raw:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    return values


def _coerce_outcomes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _coerce_token_ids(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _parse_datetime(value: Any):
    if not value:
        return None
    try:
        parsed = __import__("datetime").datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=__import__("datetime").timezone.utc)
        return parsed.astimezone(__import__("datetime").timezone.utc)
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_timestamp(
    raw: dict[str, Any],
    *,
    descriptor: MarketDescriptor,
    trades: list[TradeRecord],
):
    timestamp = _parse_datetime(raw.get("timestamp") or raw.get("updatedAt") or raw.get("observedAt") or raw.get("snapshotTs"))
    if timestamp is not None:
        return timestamp
    if trades:
        latest_trade = max((trade.timestamp for trade in trades if trade.timestamp is not None), default=None)
        if latest_trade is not None:
            return latest_trade
    return descriptor.open_time or descriptor.end_date or _utc_now()


def _parse_orderbook(raw: dict[str, Any], *, fallback_yes: float | None = None) -> MarketOrderBook | None:
    payload = (
        raw.get("orderBook")
        or raw.get("orderBooks")
        or raw.get("orderbook")
        or raw.get("order_book")
        or raw.get("book")
        or raw.get("books")
    )
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    if isinstance(payload, list):
        payload = {"bids": payload, "asks": []}
    if not isinstance(payload, dict):
        if fallback_yes is None:
            return None
        return MarketOrderBook(
            bids=[OrderBookLevel(price=max(0.0, min(1.0, fallback_yes)), size=_safe_float(raw.get("liquidity")) or 0.0)],
            asks=[OrderBookLevel(price=max(0.0, min(1.0, fallback_yes + 0.01)), size=_safe_float(raw.get("liquidity")) or 0.0)],
            source="gamma",
        )

    def _levels(side: str) -> list[OrderBookLevel]:
        raw_levels = payload.get(side) or payload.get(side.upper()) or []
        if isinstance(raw_levels, dict):
            raw_levels = raw_levels.get("levels") or raw_levels.get("items") or []
        levels: list[OrderBookLevel] = []
        if isinstance(raw_levels, list):
            for item in raw_levels:
                if not isinstance(item, dict):
                    continue
                try:
                    levels.append(
                        OrderBookLevel(
                            price=_safe_float(item.get("price")) or 0.0,
                            size=_safe_float(item.get("size") or item.get("quantity") or item.get("amount")) or 0.0,
                            metadata={k: v for k, v in item.items() if k not in {"price", "size", "quantity", "amount"}},
                        )
                    )
                except Exception:
                    continue
        return levels

    bids = _levels("bids")
    asks = _levels("asks")
    if not bids and not asks:
        return None
    return MarketOrderBook(bids=bids, asks=asks, source=str(payload.get("source") or "gamma"))


def _extract_trades(raw: dict[str, Any]) -> list[TradeRecord]:
    payload = raw.get("trades") or raw.get("recentTrades") or raw.get("trade_history") or []
    if isinstance(payload, dict):
        payload = payload.get("trades") or payload.get("items") or payload.get("data") or []
    if not isinstance(payload, list):
        return []
    records: list[TradeRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            timestamp = _parse_datetime(item.get("timestamp") or item.get("time") or item.get("createdAt") or item.get("observedAt"))
            raw_side = str(item.get("side") or item.get("direction") or "buy").strip().lower()
            side = TradeSide(raw_side) if raw_side in {member.value for member in TradeSide} else TradeSide.buy
            record = TradeRecord(
                price=_safe_float(item.get("price")) or 0.0,
                size=_safe_float(item.get("size") or item.get("quantity") or item.get("amount")) or 0.0,
                side=side,
                timestamp=timestamp or __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                metadata={k: v for k, v in item.items() if k not in {"price", "size", "quantity", "amount", "side", "direction", "timestamp", "time", "createdAt", "observedAt"}},
            )
            records.append(record)
        except Exception:
            continue
    return records


def _extract_markets_from_payload(payload: Any) -> list[MarketDescriptor]:
    raw_items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        raw_items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        for key in ("markets", "events", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = [item for item in value if isinstance(item, dict)]
                if raw_items:
                    break
        if not raw_items and any(isinstance(item, dict) for item in payload.values()):
            raw_items = [item for item in payload.values() if isinstance(item, dict)]
    descriptors: list[MarketDescriptor] = []
    for raw in raw_items:
        try:
            descriptors.append(_descriptor_from_gamma(raw))
        except Exception:
            continue
    return descriptors


def _extract_positions_from_payload(payload: Any, *, venue: VenueName, market_id: str | None = None) -> list[LedgerPosition]:
    raw_items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        raw_items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        for key in ("positions", "items", "records", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = [item for item in value if isinstance(item, dict)]
                if raw_items:
                    break
        if not raw_items and any(isinstance(item, dict) for item in payload.values()):
            raw_items = [item for item in payload.values() if isinstance(item, dict)]
    records: list[LedgerPosition] = []
    for payload_item in raw_items:
        candidate = {
            "market_id": str(payload_item.get("market_id") or market_id or ""),
            "venue": payload_item.get("venue") or venue,
            "side": payload_item.get("side") or payload_item.get("position_side") or payload_item.get("execution_side") or TradeSide.yes,
            "quantity": payload_item.get("quantity", payload_item.get("size", 0.0)),
            "entry_price": payload_item.get("entry_price", payload_item.get("price", 0.0)),
            "mark_price": payload_item.get("mark_price"),
            "unrealized_pnl": payload_item.get("unrealized_pnl"),
            "metadata": dict(payload_item.get("metadata") or {}),
        }
        try:
            records.append(LedgerPosition.model_validate(candidate))
        except Exception:
            continue
    return records


def _event_key(raw: dict[str, Any]) -> str | None:
    for key in ("eventId", "event_id", "eventSlug", "seriesSlug", "seriesId", "series_id"):
        value = raw.get(key)
        if value:
            return str(value)
    event = raw.get("event")
    if isinstance(event, dict):
        for key in ("id", "eventId", "event_id", "slug", "title"):
            value = event.get(key)
            if value:
                return str(value)
    events = raw.get("events")
    if isinstance(events, list) and events:
        first = events[0]
        if isinstance(first, dict):
            for key in ("id", "eventId", "event_id", "slug", "title"):
                value = first.get(key)
                if value:
                    return str(value)
    return None


def _unwrap_market_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    for key in ("market", "item", "data", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            return value[0]
    return payload


@dataclass
class PolymarketExecutionAdapter(BasePolymarketExecutionAdapter):
    order_submitter: Callable[[MarketExecutionOrder, dict[str, Any]], Any] | None = None
    cancel_submitter: Callable[[MarketExecutionOrder, dict[str, Any]], Any] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()

    def describe_order_execution_surface(self) -> PolymarketOrderExecutionSurface:
        return describe_polymarket_order_execution_surface(self.backend_mode)

    def place_order(
        self,
        *,
        market: MarketDescriptor,
        run_id: str,
        position_side: TradeSide = TradeSide.yes,
        execution_side: TradeSide = TradeSide.buy,
        requested_quantity: float = 0.0,
        requested_notional: float = 0.0,
        limit_price: float | None = None,
        dry_run: bool = True,
        allow_live_execution: bool = False,
        authorized: bool = True,
        compliance_approved: bool = True,
        required_scope: str = "prediction_markets:execute",
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PolymarketOrderTrace:
        runtime_config = dict(self.execution_runtime_config or _resolve_polymarket_execution_runtime_config(self.backend_mode))
        plan = self.build_execution_plan(
            market=market,
            dry_run=dry_run,
            allow_live_execution=allow_live_execution,
            authorized=authorized,
            compliance_approved=compliance_approved,
            required_scope=required_scope,
            scopes=scopes,
        )
        effective_runtime_config = {
            **runtime_config,
            "selected_backend_mode": (
                "live"
                if bool(getattr(self, "order_submitter", None)) and not dry_run
                else runtime_config.get("selected_backend_mode", self.backend_mode)
            ),
            "runtime_ready": bool(
                runtime_config.get("runtime_ready", False)
                or bool(plan.metadata.get("runtime_ready", False))
                or bool(getattr(self, "order_submitter", None))
            ),
            "ready_for_live_execution": bool(
                runtime_config.get("ready_for_live_execution", False)
                or bool(plan.metadata.get("ready_for_live_execution", False))
                or bool(getattr(self, "order_submitter", None))
            ),
            "transport_bound": bool(getattr(self, "order_submitter", None)),
        }
        transport_mode = self._resolve_transport_mode(
            dry_run=dry_run,
            runtime_config=effective_runtime_config,
            plan_allowed=plan.allowed,
        )
        now = _utc_now()
        request = MarketExecutionRequest(
            run_id=run_id,
            market=market,
            venue=market.venue,
            market_id=market.market_id,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            stake=requested_notional,
            limit_price=limit_price,
            dry_run=dry_run,
            metadata={
                **dict(metadata or {}),
                "backend_mode": self.backend_mode,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "transport_mode": transport_mode,
                "action": PolymarketOrderAction.place.value,
                "place_auditable": True,
                "cancel_auditable": True,
            },
        )
        order = MarketExecutionOrder(
            run_id=run_id,
            market_id=market.market_id,
            venue=market.venue,
            position_side=position_side,
            execution_side=execution_side,
            order_type=MarketExecutionOrderType.market,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            limit_price=limit_price,
            time_in_force="ioc",
            status="submitted" if transport_mode == "live" else "simulated",
            order_source="live" if transport_mode == "live" else "mock",
            order_path=runtime_config.get("live_order_path") or "external_live_api",
            order_cancel_path=runtime_config.get("cancel_order_path") or "external_live_cancel_api",
            order_trace_kind="external_live" if transport_mode == "live" else "local_surrogate",
            order_flow="submitted" if transport_mode == "live" else "simulated",
            metadata={
                **dict(metadata or {}),
                "backend_mode": self.backend_mode,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "transport_mode": transport_mode,
                "action": PolymarketOrderAction.place.value,
            },
        )
        lifecycle_payload = build_venue_order_lifecycle(
            order_id=order.order_id,
            execution_id=order.execution_id,
            request_metadata=dict(order.metadata or {}),
            status="submitted" if transport_mode == "live" else "simulated",
            live_execution_supported=transport_mode == "live",
            venue_order_path=runtime_config.get("live_order_path") or "external_live_api",
            venue_order_cancel_path=runtime_config.get("cancel_order_path") or "external_live_cancel_api",
        )
        order.metadata = {
            **dict(order.metadata or {}),
            "venue_order_id": lifecycle_payload.venue_order_id,
            "venue_order_status": lifecycle_payload.venue_order_status,
            "venue_order_source": lifecycle_payload.venue_order_source,
            "venue_order_submission_state": lifecycle_payload.venue_order_submission_state,
            "venue_order_ack_state": lifecycle_payload.venue_order_ack_state,
            "venue_order_cancel_state": lifecycle_payload.venue_order_cancel_state,
            "venue_order_execution_state": lifecycle_payload.venue_order_execution_state,
            "venue_order_status_history": list(lifecycle_payload.venue_order_status_history),
            "venue_order_acknowledged_at": lifecycle_payload.venue_order_acknowledged_at.isoformat() if lifecycle_payload.venue_order_acknowledged_at is not None else None,
            "venue_order_acknowledged_by": lifecycle_payload.venue_order_acknowledged_by,
            "venue_order_acknowledged_reason": lifecycle_payload.venue_order_acknowledged_reason,
            "venue_order_cancel_reason": lifecycle_payload.venue_order_cancel_reason,
            "venue_order_cancelled_at": lifecycle_payload.venue_order_cancelled_at.isoformat() if lifecycle_payload.venue_order_cancelled_at is not None else None,
            "venue_order_cancelled_by": lifecycle_payload.venue_order_cancelled_by,
            "venue_order_configured": lifecycle_payload.venue_order_configured,
            "venue_order_path": lifecycle_payload.venue_order_path,
            "venue_order_cancel_path": lifecycle_payload.venue_order_cancel_path,
            "venue_order_trace_kind": lifecycle_payload.venue_order_trace_kind,
            "venue_order_flow": lifecycle_payload.venue_order_flow,
        }
        order.status = lifecycle_payload.venue_order_status
        order.venue_order_submission_state = lifecycle_payload.venue_order_submission_state
        order.venue_order_ack_state = lifecycle_payload.venue_order_ack_state
        order.venue_order_cancel_state = lifecycle_payload.venue_order_cancel_state
        order.venue_order_execution_state = lifecycle_payload.venue_order_execution_state
        order.acknowledged_at = lifecycle_payload.venue_order_acknowledged_at
        order.acknowledged_by = lifecycle_payload.venue_order_acknowledged_by
        order.acknowledged_reason = lifecycle_payload.venue_order_acknowledged_reason

        live_submission_attempted = transport_mode == "live"
        live_submission_performed = False
        submitted_payload: dict[str, Any] | None = None
        notes: list[str] = []
        blocked_reasons = list(plan.blocked_reasons)
        if transport_mode == "live":
            if self.order_submitter is None:
                notes.append("live_transport_not_bound")
                blocked_reasons.append("live_transport_not_bound")
            else:
                try:
                    payload = self.order_submitter(order, request.model_dump(mode="json"))
                    if isinstance(payload, dict):
                        submitted_payload = payload
                    else:
                        submitted_payload = {"value": payload}
                    live_submission_performed = True
                    notes.append("live_transport_bound")
                    submitted_lifecycle_metadata = {
                        key: value
                        for key, value in submitted_payload.items()
                        if isinstance(key, str) and key.startswith("venue_order_") and value is not None
                    }
                    if submitted_lifecycle_metadata:
                        lifecycle_payload = type(lifecycle_payload).model_validate(
                            {
                                **lifecycle_payload.model_dump(mode="json"),
                                **submitted_lifecycle_metadata,
                            }
                        )
                        order.metadata.update(
                            {
                                "venue_order_id": lifecycle_payload.venue_order_id,
                                "venue_order_status": lifecycle_payload.venue_order_status,
                                "venue_order_source": lifecycle_payload.venue_order_source,
                                "venue_order_submission_state": lifecycle_payload.venue_order_submission_state,
                                "venue_order_ack_state": lifecycle_payload.venue_order_ack_state,
                                "venue_order_cancel_state": lifecycle_payload.venue_order_cancel_state,
                                "venue_order_execution_state": lifecycle_payload.venue_order_execution_state,
                                "venue_order_status_history": list(lifecycle_payload.venue_order_status_history),
                                "venue_order_acknowledged_at": lifecycle_payload.venue_order_acknowledged_at.isoformat() if lifecycle_payload.venue_order_acknowledged_at is not None else None,
                                "venue_order_acknowledged_by": lifecycle_payload.venue_order_acknowledged_by,
                                "venue_order_acknowledged_reason": lifecycle_payload.venue_order_acknowledged_reason,
                                "venue_order_cancel_reason": lifecycle_payload.venue_order_cancel_reason,
                                "venue_order_cancelled_at": lifecycle_payload.venue_order_cancelled_at.isoformat() if lifecycle_payload.venue_order_cancelled_at is not None else None,
                                "venue_order_cancelled_by": lifecycle_payload.venue_order_cancelled_by,
                                "venue_order_configured": lifecycle_payload.venue_order_configured,
                                "venue_order_path": lifecycle_payload.venue_order_path,
                                "venue_order_cancel_path": lifecycle_payload.venue_order_cancel_path,
                                "venue_order_trace_kind": lifecycle_payload.venue_order_trace_kind,
                                "venue_order_flow": lifecycle_payload.venue_order_flow,
                            }
                        )
                        order.status = lifecycle_payload.venue_order_status
                        order.venue_order_submission_state = lifecycle_payload.venue_order_submission_state
                        order.venue_order_ack_state = lifecycle_payload.venue_order_ack_state
                        order.venue_order_cancel_state = lifecycle_payload.venue_order_cancel_state
                        order.venue_order_execution_state = lifecycle_payload.venue_order_execution_state
                        order.acknowledged_at = lifecycle_payload.venue_order_acknowledged_at
                        order.acknowledged_by = lifecycle_payload.venue_order_acknowledged_by
                        order.acknowledged_reason = lifecycle_payload.venue_order_acknowledged_reason
                except Exception as exc:  # pragma: no cover - defensive path
                    notes.append(f"live_submitter_failed:{type(exc).__name__}")
                    blocked_reasons.append(f"live_submitter_failed:{type(exc).__name__}")
        elif transport_mode == "mock":
            notes.append("mock_transport_used")
        else:
            notes.append("dry_run_only")

        completed_at = _utc_now()
        order_trace_audit = _order_trace_audit_from_lifecycle(
            lifecycle_payload.model_dump(mode="json"),
            transport_mode=transport_mode,
            live_execution_ready=bool(effective_runtime_config.get("runtime_ready", False)),
            live_submission_attempted=live_submission_attempted,
            live_submission_performed=live_submission_performed,
            live_submission_bound=self.order_submitter is not None,
        )
        order.metadata["order_trace_audit"] = order_trace_audit
        return PolymarketOrderTrace(
            action=PolymarketOrderAction.place,
            requested_backend_mode=effective_runtime_config.get("requested_backend_mode", self.backend_mode),
            selected_backend_mode=effective_runtime_config.get("selected_backend_mode", self.backend_mode),
            transport_mode=transport_mode,
            live_execution_ready=bool(effective_runtime_config.get("runtime_ready", False)),
            mock_transport=bool(effective_runtime_config.get("mock_transport", False)),
            live_submission_bound=self.order_submitter is not None,
            live_submission_attempted=live_submission_attempted,
            live_submission_performed=live_submission_performed,
            dry_run=dry_run,
            market=market,
            request=request,
            order=order,
            execution_plan={
                **dict(plan.model_dump(mode="json")),
                "selected_transport_mode": transport_mode,
                "requested_backend_mode": effective_runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": effective_runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_ready": bool(effective_runtime_config.get("runtime_ready", False)),
                "ready_for_live_execution": bool(effective_runtime_config.get("ready_for_live_execution", False)),
                "mock_transport": bool(effective_runtime_config.get("mock_transport", False)),
                "live_submission_bound": self.order_submitter is not None,
                "live_submission_attempted": live_submission_attempted,
                "live_submission_performed": live_submission_performed,
                "readiness_notes": list(effective_runtime_config.get("readiness_notes", [])),
                "missing_requirements": list(effective_runtime_config.get("missing_requirements", [])),
            },
            blocked_reasons=blocked_reasons,
            notes=notes,
            venue_order_lifecycle=lifecycle_payload.model_dump(mode="json"),
            submitted_payload=submitted_payload,
            completed_at=completed_at,
            metadata={
                **dict(metadata or {}),
                "transport_mode": transport_mode,
                "requested_backend_mode": effective_runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": effective_runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_ready": bool(effective_runtime_config.get("runtime_ready", False)),
                "ready_for_live_execution": bool(effective_runtime_config.get("ready_for_live_execution", False)),
                "mock_transport": bool(effective_runtime_config.get("mock_transport", False)),
                "live_submission_bound": self.order_submitter is not None,
                "live_submission_attempted": live_submission_attempted,
                "live_submission_performed": live_submission_performed,
                "place_auditable": True,
                "cancel_auditable": True,
                "order_trace_audit": order_trace_audit,
                "live_submission_receipt": build_venue_order_submission_receipt(
                    lifecycle=lifecycle_payload.model_dump(mode="json"),
                    submitted_payload=submitted_payload,
                    transport_mode=transport_mode,
                    runtime_honest_mode=transport_mode,
                    attempted_live=live_submission_attempted,
                    live_submission_performed=live_submission_performed,
                    live_submission_phase="performed_live" if live_submission_performed else "attempted_live" if live_submission_attempted else transport_mode,
                    live_submission_bound=self.order_submitter is not None,
                    blocked_reasons=blocked_reasons,
                ),
            },
        )

    def cancel_order(
        self,
        order: MarketExecutionOrder | PolymarketOrderTrace,
        *,
        reason: str,
        cancelled_by: str = "local_surrogate",
        metadata: dict[str, Any] | None = None,
    ) -> PolymarketOrderTrace:
        runtime_config = dict(self.execution_runtime_config or _resolve_polymarket_execution_runtime_config(self.backend_mode))
        original_order = order.order if isinstance(order, PolymarketOrderTrace) else order
        base_order = MarketExecutionOrder.model_validate(original_order.model_dump(mode="json"))
        transport_mode = (
            "live"
            if runtime_config.get("selected_backend_mode", "auto") == "live"
            and runtime_config.get("runtime_ready", False)
            and not runtime_config.get("mock_transport", False)
            else "dry_run"
        )
        request = MarketExecutionRequest(
            run_id=base_order.run_id,
            market_id=base_order.market_id,
            venue=base_order.venue,
            market=MarketDescriptor(
                venue=base_order.venue,
                venue_type=VenueType.execution_equivalent,
                market_id=base_order.market_id,
                title=base_order.market_id,
                question=base_order.market_id,
                active=True,
                closed=False,
            ),
            position_side=base_order.position_side,
            execution_side=base_order.execution_side,
            requested_quantity=base_order.requested_quantity,
            requested_notional=base_order.requested_notional,
            stake=base_order.requested_notional,
            limit_price=base_order.limit_price,
            dry_run=transport_mode != "live",
            metadata={
                **dict(metadata or {}),
                "backend_mode": self.backend_mode,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "transport_mode": transport_mode,
                "action": PolymarketOrderAction.cancel.value,
                "cancel_reason": reason,
                "cancelled_by": cancelled_by,
            },
        )
        now = _utc_now()
        lifecycle_payload = build_venue_order_lifecycle(
            order_id=base_order.order_id,
            execution_id=base_order.execution_id,
            request_metadata={
                **dict(base_order.metadata or {}),
                "venue_order_status": "cancelled",
                "venue_order_acknowledged_at": now,
                "venue_order_acknowledged_by": cancelled_by,
                "venue_order_acknowledged_reason": reason,
                "venue_order_cancelled_at": now,
                "venue_order_cancelled_by": cancelled_by,
                "venue_order_cancel_reason": reason,
            },
            status="cancelled",
            cancelled_reason=reason,
            live_execution_supported=transport_mode == "live",
            venue_order_path=runtime_config.get("live_order_path") or "external_live_api",
            venue_order_cancel_path=runtime_config.get("cancel_order_path") or "external_live_cancel_api",
        )
        cancel_payload: dict[str, Any] | None = None
        live_submission_attempted = transport_mode == "live"
        live_submission_performed = False
        notes: list[str] = []
        blocked_reasons: list[str] = []
        if transport_mode == "live":
            if self.cancel_submitter is None:
                notes.append("live_cancel_transport_not_bound")
                blocked_reasons.append("live_cancel_transport_not_bound")
            else:
                try:
                    payload = self.cancel_submitter(base_order, request.model_dump(mode="json"))
                    cancel_payload = payload if isinstance(payload, dict) else {"value": payload}
                    live_submission_performed = True
                    notes.append("live_cancel_transport_bound")
                    submitted_lifecycle_metadata = {
                        key: value
                        for key, value in cancel_payload.items()
                        if isinstance(key, str) and key.startswith("venue_order_") and value is not None
                    }
                    if submitted_lifecycle_metadata:
                        lifecycle_payload = type(lifecycle_payload).model_validate(
                            {
                                **lifecycle_payload.model_dump(mode="json"),
                                **submitted_lifecycle_metadata,
                            }
                        )
                        base_order.metadata.update(
                            {
                                "venue_order_id": lifecycle_payload.venue_order_id,
                                "venue_order_status": lifecycle_payload.venue_order_status,
                                "venue_order_source": lifecycle_payload.venue_order_source,
                                "venue_order_submission_state": lifecycle_payload.venue_order_submission_state,
                                "venue_order_ack_state": lifecycle_payload.venue_order_ack_state,
                                "venue_order_cancel_state": lifecycle_payload.venue_order_cancel_state,
                                "venue_order_execution_state": lifecycle_payload.venue_order_execution_state,
                                "venue_order_status_history": list(lifecycle_payload.venue_order_status_history),
                                "venue_order_acknowledged_at": lifecycle_payload.venue_order_acknowledged_at.isoformat() if lifecycle_payload.venue_order_acknowledged_at is not None else None,
                                "venue_order_acknowledged_by": lifecycle_payload.venue_order_acknowledged_by,
                                "venue_order_acknowledged_reason": lifecycle_payload.venue_order_acknowledged_reason,
                                "venue_order_cancel_reason": lifecycle_payload.venue_order_cancel_reason,
                                "venue_order_cancelled_at": lifecycle_payload.venue_order_cancelled_at.isoformat() if lifecycle_payload.venue_order_cancelled_at is not None else None,
                                "venue_order_cancelled_by": lifecycle_payload.venue_order_cancelled_by,
                                "venue_order_configured": lifecycle_payload.venue_order_configured,
                                "venue_order_path": lifecycle_payload.venue_order_path,
                                "venue_order_cancel_path": lifecycle_payload.venue_order_cancel_path,
                                "venue_order_trace_kind": lifecycle_payload.venue_order_trace_kind,
                                "venue_order_flow": lifecycle_payload.venue_order_flow,
                            }
                        )
                        base_order.status = lifecycle_payload.venue_order_status
                        base_order.venue_order_submission_state = lifecycle_payload.venue_order_submission_state
                        base_order.venue_order_ack_state = lifecycle_payload.venue_order_ack_state
                        base_order.venue_order_cancel_state = lifecycle_payload.venue_order_cancel_state
                        base_order.venue_order_execution_state = lifecycle_payload.venue_order_execution_state
                        base_order.cancelled_at = lifecycle_payload.venue_order_cancelled_at
                        base_order.cancelled_by = lifecycle_payload.venue_order_cancelled_by
                        base_order.cancelled_reason = lifecycle_payload.venue_order_cancel_reason
                        base_order.acknowledged_at = lifecycle_payload.venue_order_acknowledged_at
                        base_order.acknowledged_by = lifecycle_payload.venue_order_acknowledged_by
                        base_order.acknowledged_reason = lifecycle_payload.venue_order_acknowledged_reason
                except Exception as exc:  # pragma: no cover - defensive path
                    notes.append(f"live_cancel_submitter_failed:{type(exc).__name__}")
                    blocked_reasons.append(f"live_cancel_submitter_failed:{type(exc).__name__}")
        else:
            notes.append("mock_cancel_trace")
        base_order.metadata = {
            **dict(base_order.metadata or {}),
            "venue_order_id": lifecycle_payload.venue_order_id,
            "venue_order_status": lifecycle_payload.venue_order_status,
            "venue_order_source": lifecycle_payload.venue_order_source,
            "venue_order_submission_state": lifecycle_payload.venue_order_submission_state,
            "venue_order_ack_state": lifecycle_payload.venue_order_ack_state,
            "venue_order_cancel_state": lifecycle_payload.venue_order_cancel_state,
            "venue_order_execution_state": lifecycle_payload.venue_order_execution_state,
            "venue_order_status_history": list(lifecycle_payload.venue_order_status_history),
            "venue_order_acknowledged_at": lifecycle_payload.venue_order_acknowledged_at.isoformat() if lifecycle_payload.venue_order_acknowledged_at is not None else None,
            "venue_order_acknowledged_by": lifecycle_payload.venue_order_acknowledged_by,
            "venue_order_acknowledged_reason": lifecycle_payload.venue_order_acknowledged_reason,
            "venue_order_cancel_reason": lifecycle_payload.venue_order_cancel_reason,
            "venue_order_cancelled_at": lifecycle_payload.venue_order_cancelled_at.isoformat() if lifecycle_payload.venue_order_cancelled_at is not None else None,
            "venue_order_cancelled_by": lifecycle_payload.venue_order_cancelled_by,
            "venue_order_configured": lifecycle_payload.venue_order_configured,
            "venue_order_path": lifecycle_payload.venue_order_path,
            "venue_order_cancel_path": lifecycle_payload.venue_order_cancel_path,
            "venue_order_trace_kind": lifecycle_payload.venue_order_trace_kind,
            "venue_order_flow": lifecycle_payload.venue_order_flow,
        }
        base_order.status = lifecycle_payload.venue_order_status
        base_order.venue_order_submission_state = lifecycle_payload.venue_order_submission_state
        base_order.venue_order_ack_state = lifecycle_payload.venue_order_ack_state
        base_order.venue_order_cancel_state = lifecycle_payload.venue_order_cancel_state
        base_order.venue_order_execution_state = lifecycle_payload.venue_order_execution_state
        base_order.cancelled_at = lifecycle_payload.venue_order_cancelled_at
        base_order.cancelled_by = lifecycle_payload.venue_order_cancelled_by
        base_order.cancelled_reason = lifecycle_payload.venue_order_cancel_reason
        base_order.acknowledged_at = lifecycle_payload.venue_order_acknowledged_at
        base_order.acknowledged_by = lifecycle_payload.venue_order_acknowledged_by
        base_order.acknowledged_reason = lifecycle_payload.venue_order_acknowledged_reason
        order_trace_audit = _order_trace_audit_from_lifecycle(
            lifecycle_payload.model_dump(mode="json"),
            transport_mode=transport_mode,
            live_execution_ready=bool(runtime_config.get("runtime_ready", False)),
            live_submission_attempted=live_submission_attempted,
            live_submission_performed=live_submission_performed,
            live_submission_bound=self.cancel_submitter is not None,
        )
        base_order.metadata["order_trace_audit"] = order_trace_audit

        return PolymarketOrderTrace(
            action=PolymarketOrderAction.cancel,
            requested_backend_mode=runtime_config.get("requested_backend_mode", self.backend_mode),
            selected_backend_mode=runtime_config.get("selected_backend_mode", self.backend_mode),
            transport_mode=transport_mode,
            live_execution_ready=bool(runtime_config.get("runtime_ready", False)),
            mock_transport=bool(runtime_config.get("mock_transport", False)),
            live_submission_bound=self.cancel_submitter is not None,
            live_submission_attempted=live_submission_attempted,
            live_submission_performed=live_submission_performed,
            dry_run=transport_mode != "live",
            market=MarketDescriptor(
                venue=base_order.venue,
                venue_type=VenueType.execution_equivalent,
                market_id=base_order.market_id,
                title=base_order.market_id,
                question=base_order.market_id,
                active=True,
                closed=False,
            ),
            request=request,
            order=base_order,
            execution_plan={
                "cancel_reason": reason,
                "transport_mode": transport_mode,
                "selected_transport_mode": transport_mode,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_ready": bool(runtime_config.get("runtime_ready", False)),
                "ready_for_live_execution": bool(runtime_config.get("ready_for_live_execution", False)),
                "mock_transport": bool(runtime_config.get("mock_transport", False)),
                "live_submission_bound": self.cancel_submitter is not None,
                "live_submission_attempted": live_submission_attempted,
                "live_submission_performed": live_submission_performed,
                "readiness_notes": list(runtime_config.get("readiness_notes", [])),
                "missing_requirements": list(runtime_config.get("missing_requirements", [])),
            },
            blocked_reasons=blocked_reasons,
            notes=notes,
            venue_order_lifecycle=lifecycle_payload.model_dump(mode="json"),
            cancelled_payload=cancel_payload,
            completed_at=now,
            metadata={
                **dict(metadata or {}),
                "transport_mode": transport_mode,
                "selected_transport_mode": transport_mode,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_ready": bool(runtime_config.get("runtime_ready", False)),
                "ready_for_live_execution": bool(runtime_config.get("ready_for_live_execution", False)),
                "mock_transport": bool(runtime_config.get("mock_transport", False)),
                "live_submission_bound": self.cancel_submitter is not None,
                "cancel_reason": reason,
                "cancelled_by": cancelled_by,
                "live_submission_attempted": live_submission_attempted,
                "live_submission_performed": live_submission_performed,
                "place_auditable": True,
                "cancel_auditable": True,
                "order_trace_audit": order_trace_audit,
                "venue_cancellation_receipt": build_venue_order_cancellation_receipt(
                    lifecycle=lifecycle_payload.model_dump(mode="json"),
                    cancelled_payload=cancel_payload,
                    transport_mode=transport_mode,
                    runtime_honest_mode=transport_mode,
                    attempted_live=live_submission_attempted,
                    live_submission_performed=live_submission_performed,
                    cancellation_performed=bool(lifecycle_payload.venue_order_cancelled_at or lifecycle_payload.venue_order_cancelled_by or lifecycle_payload.venue_order_cancel_reason),
                    cancellation_phase="performed_live" if live_submission_performed else "attempted_live" if live_submission_attempted else transport_mode,
                    live_cancellation_bound=self.cancel_submitter is not None,
                    blocked_reasons=blocked_reasons,
                ),
            },
        )

    @staticmethod
    def _resolve_transport_mode(*, dry_run: bool, runtime_config: dict[str, Any], plan_allowed: bool) -> str:
        if dry_run or not plan_allowed:
            return "dry_run"
        if runtime_config.get("mock_transport", False):
            return "dry_run"
        if runtime_config.get("selected_backend_mode", "auto") == "live" and (
            runtime_config.get("runtime_ready", False) or runtime_config.get("ready_for_live_execution", False)
        ):
            return "live"
        return "dry_run"


def build_polymarket_execution_adapter(*, backend_mode: str | None = None) -> PolymarketExecutionAdapter:
    runtime_config = _resolve_polymarket_execution_runtime_config(backend_mode)
    return PolymarketExecutionAdapter(backend_mode=backend_mode or "auto", execution_runtime_config=runtime_config)
