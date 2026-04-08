from __future__ import annotations

import json
import os
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator
from urllib.error import HTTPError, URLError

import requests

from .market_execution import BoundedMarketExecutionEngine, MarketExecutionOrder, MarketExecutionRecord, MarketExecutionRequest
from .models import (
    EvidencePacket,
    LedgerPosition,
    MarketDescriptor,
    MarketOrderBook,
    MarketSnapshot,
    MarketStatus,
    MarketUniverseConfig,
    OrderBookLevel,
    ResolutionPolicy,
    ResolutionStatus,
    SourceKind,
    TradeRecord,
    TradeSide,
    VenueCapabilitiesModel,
    VenueHealthReport,
    VenueName,
    VenueType,
)
from .paths import default_prediction_market_paths
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY, VenueExecutionCapability, VenueExecutionRegistry

VenueCapabilities = VenueCapabilitiesModel


class MarketDataUnavailableError(RuntimeError):
    pass


class VenueAdapter(Protocol):
    venue: VenueName

    def describe_capabilities(self) -> VenueCapabilitiesModel: ...

    def list_markets(self, *, config: MarketUniverseConfig | None = None, limit: int | None = None) -> list[MarketDescriptor]: ...

    def get_market(self, market_id: str) -> MarketDescriptor: ...

    def get_snapshot(self, market_id: str) -> MarketSnapshot: ...

    def get_resolution_policy(self, market_id: str) -> ResolutionPolicy: ...

    def get_trades(self, market_id: str) -> list[TradeRecord]: ...

    def get_events(self, market_id: str) -> list[MarketDescriptor]: ...

    def get_positions(self, market_id: str) -> list[LedgerPosition]: ...

    def get_evidence(self, market_id: str) -> list[EvidencePacket]: ...

    def health(self) -> VenueHealthReport: ...


class VenueExecutionPlan(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    adapter_name: str
    backend_mode: str = "auto"
    planning_bucket: str = "watchlist"
    dry_run_requested: bool = True
    dry_run_effective: bool = True
    live_execution_requested: bool = False
    live_execution_supported: bool = False
    bounded_execution_supported: bool = False
    market_execution_supported: bool = False
    order_audit_supported: bool = True
    fill_audit_supported: bool = True
    position_audit_supported: bool = True
    venue_order_path: str = "unknown"
    venue_order_cancel_path: str = "unknown"
    execution_mode: str = "dry_run"
    route_supported: bool = True
    auth_required: bool = True
    auth_passed: bool = False
    compliance_required: bool = True
    compliance_passed: bool = False
    credential_evidence: dict[str, Any] = Field(default_factory=dict)
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
    configuration_evidence: dict[str, Any] = Field(default_factory=dict)
    readiness_evidence: dict[str, Any] = Field(default_factory=dict)
    allowed: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueOrderLifecycle(BaseModel):
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
    venue_order_cancel_path: str = "unavailable"
    venue_order_configured: bool = False
    live_execution_supported: bool = False
    venue_order_trace_kind: str = "unavailable"
    venue_order_flow: str = "unavailable"
    metadata: dict[str, Any] = Field(default_factory=dict)


def _planning_bucket_for_venue_type(venue_type: VenueType) -> str:
    if venue_type in {VenueType.execution, VenueType.execution_equivalent}:
        return "execution-equivalent"
    if venue_type in {VenueType.reference, VenueType.reference_only}:
        return "reference-only"
    return "watchlist"


def _merge_evidence_dict(*sources: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if not source:
            continue
        for key, value in dict(source).items():
            existing = merged.get(key)
            if isinstance(existing, Mapping) and isinstance(value, Mapping):
                merged[key] = _merge_evidence_dict(existing, value)
            elif key not in merged or existing in (None, {}, [], ""):
                merged[key] = value
    return merged


def _env_truthy(*names: str) -> bool:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "mock"}:
            return True
    return False


def _env_text(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _resolve_polymarket_backend_mode(requested_backend_mode: str | None = None) -> str:
    requested = (requested_backend_mode or "auto").strip().lower() or "auto"
    if requested != "auto":
        return requested
    env_mode = _env_text("POLYMARKET_EXECUTION_BACKEND", "POLYMARKET_EXECUTION_MODE")
    if env_mode:
        return env_mode.lower()
    if _env_truthy("POLYMARKET_EXECUTION_MOCK", "POLYMARKET_MOCK_EXECUTION"):
        return "mock"
    auth_token = _env_text(
        "POLYMARKET_EXECUTION_AUTH_TOKEN",
        "POLYMARKET_AUTH_TOKEN",
        "POLYMARKET_API_KEY",
        "POLYMARKET_CLOB_API_KEY",
    )
    live_order_path = _env_text("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "POLYMARKET_ORDER_PATH")
    cancel_order_path = _env_text("POLYMARKET_EXECUTION_CANCEL_PATH", "POLYMARKET_CANCEL_PATH")
    if auth_token and live_order_path and cancel_order_path:
        return "live"
    generic_mode = _env_text("PREDICTION_MARKETS_BACKEND")
    if generic_mode:
        return generic_mode.lower()
    return "auto"


def _resolve_polymarket_execution_runtime_config(backend_mode: str | None = None) -> dict[str, Any]:
    selected_backend_mode = _resolve_polymarket_backend_mode(backend_mode)
    auth_token = _env_text(
        "POLYMARKET_EXECUTION_AUTH_TOKEN",
        "POLYMARKET_AUTH_TOKEN",
        "POLYMARKET_API_KEY",
        "POLYMARKET_CLOB_API_KEY",
    )
    live_order_path = _env_text("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "POLYMARKET_ORDER_PATH") or "external_live_api"
    bounded_order_path = _env_text("POLYMARKET_EXECUTION_BOUNDED_ORDER_PATH", "POLYMARKET_BOUNDED_ORDER_PATH") or "external_bounded_api"
    cancel_order_path = _env_text("POLYMARKET_EXECUTION_CANCEL_PATH", "POLYMARKET_CANCEL_PATH") or "external_live_cancel_api"
    bounded_cancel_path = _env_text("POLYMARKET_EXECUTION_BOUNDED_CANCEL_PATH", "POLYMARKET_BOUNDED_CANCEL_PATH") or "external_bounded_cancel_api"
    auth_scheme = _env_text("POLYMARKET_EXECUTION_AUTH_SCHEME", "POLYMARKET_AUTH_SCHEME") or "bearer"
    mock_transport = selected_backend_mode == "mock" or _env_truthy("POLYMARKET_EXECUTION_MOCK", "POLYMARKET_MOCK_EXECUTION")
    auth_configured = bool(auth_token)
    live_execution_ready = bool(
        selected_backend_mode == "live"
        and auth_configured
        and live_order_path
        and cancel_order_path
        and not mock_transport
    )
    readiness_notes: list[str] = []
    if mock_transport:
        readiness_notes.append("mock_transport_enabled")
    if not auth_configured:
        readiness_notes.append("missing_auth_token")
    if not live_order_path:
        readiness_notes.append("missing_live_order_path")
    if not cancel_order_path:
        readiness_notes.append("missing_cancel_path")
    if selected_backend_mode == "live" and not live_execution_ready:
        readiness_notes.append("live_execution_not_ready")
    missing_requirements: list[str] = []
    if selected_backend_mode != "live":
        missing_requirements.append(f"backend_mode:{selected_backend_mode}")
    if not auth_configured:
        missing_requirements.append("auth_token")
    if not live_order_path:
        missing_requirements.append("live_order_path")
    if not cancel_order_path:
        missing_requirements.append("cancel_order_path")
    if mock_transport:
        missing_requirements.append("mock_transport_disabled")
    auth_sources = [
        "POLYMARKET_EXECUTION_AUTH_TOKEN",
        "POLYMARKET_AUTH_TOKEN",
        "POLYMARKET_API_KEY",
        "POLYMARKET_CLOB_API_KEY",
    ]
    credential_evidence = {
        "schema_version": "v1",
        "auth_configured": auth_configured,
        "auth_token_present": auth_configured,
        "auth_scheme": auth_scheme,
        "auth_sources": auth_sources,
        "selected_backend_mode": selected_backend_mode,
        "mock_transport": mock_transport,
        "missing_requirements": [item for item in missing_requirements if item == "auth_token"],
    }
    configuration_evidence = {
        "schema_version": "v1",
        "live_order_path": live_order_path,
        "bounded_order_path": bounded_order_path,
        "cancel_order_path": cancel_order_path,
        "bounded_cancel_path": bounded_cancel_path,
        "order_sources": {
            "live": ["POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "POLYMARKET_ORDER_PATH"],
            "bounded": ["POLYMARKET_EXECUTION_BOUNDED_ORDER_PATH", "POLYMARKET_BOUNDED_ORDER_PATH"],
            "cancel": ["POLYMARKET_EXECUTION_CANCEL_PATH", "POLYMARKET_CANCEL_PATH"],
            "bounded_cancel": ["POLYMARKET_EXECUTION_BOUNDED_CANCEL_PATH", "POLYMARKET_BOUNDED_CANCEL_PATH"],
        },
        "selected_backend_mode": selected_backend_mode,
    }
    readiness_evidence = {
        "schema_version": "v1",
        "runtime_ready": live_execution_ready,
        "ready_for_live_execution": live_execution_ready,
        "live_execution_ready": live_execution_ready,
        "mock_transport": mock_transport,
        "readiness_notes": list(readiness_notes),
        "missing_requirements": list(missing_requirements),
    }
    return {
        "requested_backend_mode": (backend_mode or "auto").strip().lower() or "auto",
        "selected_backend_mode": selected_backend_mode,
        "auth_scheme": auth_scheme,
        "auth_configured": auth_configured,
        "auth_token_present": auth_configured,
        "mock_transport": mock_transport,
        "live_order_path": live_order_path,
        "bounded_order_path": bounded_order_path,
        "cancel_order_path": cancel_order_path,
        "bounded_cancel_path": bounded_cancel_path,
        "runtime_ready": live_execution_ready,
        "ready_for_live_execution": live_execution_ready,
        "readiness_notes": readiness_notes,
        "missing_requirements": missing_requirements,
        "auth_sources": auth_sources,
        "order_sources": configuration_evidence["order_sources"],
        "credential_evidence": credential_evidence,
        "configuration_evidence": configuration_evidence,
        "readiness_evidence": readiness_evidence,
        "blocker_summary": list(missing_requirements),
    }


class ExecutionAdapter(Protocol):
    venue: VenueName

    def describe_execution_capabilities(self) -> VenueExecutionCapability: ...

    def build_execution_plan(
        self,
        *,
        market: MarketDescriptor,
        dry_run: bool,
        allow_live_execution: bool,
        authorized: bool,
        compliance_approved: bool,
        required_scope: str,
        scopes: list[str] | None = None,
        jurisdiction: str | None = None,
        account_type: str | None = None,
        automation_allowed: bool | None = None,
        rate_limit_ok: bool | None = None,
        tos_accepted: bool | None = None,
        allowed_jurisdictions: set[str] | None = None,
        allowed_account_types: set[str] | None = None,
        require_automation_allowed: bool = False,
        require_rate_limit_ok: bool = False,
        require_tos_accepted: bool = False,
        dry_run_requires_authorization: bool = False,
        dry_run_requires_compliance: bool = False,
    ) -> VenueExecutionPlan: ...


class MarketExecutionAdapter(Protocol):
    venue: VenueName

    def describe_market_execution_capabilities(self) -> VenueExecutionCapability: ...

    def execute_bounded(self, request: MarketExecutionRequest) -> MarketExecutionRecord: ...


class ClobPlaceOrderRequest(BaseModel):
    schema_version: str = "v1"
    market: MarketDescriptor
    run_id: str
    position_side: TradeSide = TradeSide.yes
    execution_side: TradeSide = TradeSide.buy
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    limit_price: float | None = None
    dry_run: bool = True
    allow_live_execution: bool = False
    authorized: bool = True
    compliance_approved: bool = True
    required_scope: str = "prediction_markets:execute"
    scopes: list[str] = Field(default_factory=list)
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


class ClobCancelOrderRequest(BaseModel):
    schema_version: str = "v1"
    order: MarketExecutionOrder
    reason: str
    cancelled_by: str = "local_surrogate"
    metadata: dict[str, Any] = Field(default_factory=dict)


ClobCancelOrderRequest.model_rebuild()


@runtime_checkable
class VenueOrderTransport(Protocol):
    def place_order(self, *args: Any, **kwargs: Any) -> Any: ...

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class VenueOrderCallbackTransport(Protocol):
    def place_order(self, order: MarketExecutionOrder, payload: dict[str, Any]) -> Any: ...

    def cancel_order(self, order: MarketExecutionOrder, payload: dict[str, Any]) -> Any: ...



class HttpJSONSource:
    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, path: str) -> Any:
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def _capability_metadata(
    *,
    backend_mode: str,
    venue_kind: str,
    venue_type: str | None = None,
    role_labels: list[str] | None = None,
    api_access: list[str] | None = None,
    supported_order_types: list[str] | None = None,
    read_only: bool,
    paper_capable: bool,
    execution_capable: bool,
    positions_capable: bool,
    events_capable: bool,
    discovery_notes: list[str] | None = None,
    orderbook_notes: list[str] | None = None,
    trades_notes: list[str] | None = None,
    execution_notes: list[str] | None = None,
    websocket_notes: list[str] | None = None,
    paper_mode_notes: list[str] | None = None,
    automation_constraints: list[str] | None = None,
    rate_limit_notes: list[str] | None = None,
    compliance_notes: list[str] | None = None,
    venue_taxonomy: str | None = None,
    tradeability_class: str | None = None,
    execution_taxonomy: str | None = None,
) -> dict[str, Any]:
    normalized_venue_type = venue_type or venue_kind
    api_access = list(api_access or [])
    supported_order_types = list(supported_order_types or [])
    supports_orderbook = "orderbook" in api_access
    supports_trades = "trades" in api_access
    supports_positions = bool(positions_capable or "positions" in api_access)
    supports_events = bool(events_capable or "events" in api_access)
    supports_discovery = bool("catalog" in api_access or "snapshot" in api_access)
    supports_market_feed = bool(supports_orderbook or supports_trades)
    supports_user_feed = False
    supports_rtds = False
    supports_streaming = bool(supports_market_feed or supports_user_feed or supports_rtds)
    if tradeability_class is None:
        if execution_capable and not read_only:
            tradeability_class = "execution_capable"
        elif paper_capable and normalized_venue_type == "execution":
            tradeability_class = "execution_like_paper_only"
        elif paper_capable and normalized_venue_type == "reference":
            tradeability_class = "reference_paper_only"
        elif paper_capable and normalized_venue_type == "signal":
            tradeability_class = "signal_paper_only"
        elif paper_capable and normalized_venue_type == "watchlist":
            tradeability_class = "watchlist_paper_only"
        elif normalized_venue_type == "reference":
            tradeability_class = "reference_only"
        elif normalized_venue_type == "signal":
            tradeability_class = "signal_only"
        elif normalized_venue_type == "watchlist":
            tradeability_class = "watchlist_only"
        else:
            tradeability_class = "read_only"
    return {
        "backend_mode": backend_mode,
        "venue_kind": venue_kind,
        "venue_type": normalized_venue_type,
        "venue_taxonomy": venue_taxonomy or venue_kind,
        "tradeability_class": tradeability_class,
        "execution_taxonomy": execution_taxonomy or "execution_like",
        "role_labels": list(role_labels or [venue_kind]),
        "api_access": api_access,
        "supported_order_types": supported_order_types,
        "read_only": read_only,
        "paper_capable": paper_capable,
        "execution_capable": execution_capable,
        "positions_capable": positions_capable,
        "events_capable": events_capable,
        "supports_discovery": supports_discovery,
        "supports_metadata": True,
        "supports_orderbook": supports_orderbook,
        "supports_trades": supports_trades,
        "supports_positions": supports_positions,
        "supports_execution": execution_capable,
        "supports_streaming": supports_streaming,
        "supports_events": supports_events,
        "supports_market_feed": supports_market_feed,
        "supports_user_feed": supports_user_feed,
        "supports_rtds": supports_rtds,
        "supports_paper_mode": paper_capable,
        "automation_constraints": list(automation_constraints or []),
        "rate_limit_notes": list(rate_limit_notes or []),
        "capability_notes": {
            "discovery_notes": list(discovery_notes or []),
            "orderbook_notes": list(orderbook_notes or []),
            "trades_notes": list(trades_notes or []),
            "execution_notes": list(execution_notes or []),
            "api_access": list(api_access or []),
            "supported_order_types": list(supported_order_types or []),
            "websocket_notes": list(websocket_notes or []),
            "paper_mode_notes": list(paper_mode_notes or []),
            "automation_constraints": list(automation_constraints or []),
            "rate_limit_notes": list(rate_limit_notes or []),
            "compliance_notes": list(compliance_notes or []),
        },
    }


def _score_market(market: MarketDescriptor) -> float:
    score = market.clarity_score
    if market.liquidity:
        score += min(0.2, market.liquidity / 100000.0)
    if market.status == MarketStatus.open:
        score += 0.05
    return score


def _event_markets(markets: list[MarketDescriptor]) -> list[MarketDescriptor]:
    deduped: dict[str, MarketDescriptor] = {}
    for market in markets:
        key = market.canonical_event_id or market.market_id
        if key not in deduped or _score_market(market) > _score_market(deduped[key]):
            deduped[key] = market.model_copy(deep=True)
    return sorted(deduped.values(), key=_score_market, reverse=True)


def _position_cache_candidates(venue: VenueName, market_id: str | None = None) -> list[Path]:
    root = default_prediction_market_paths().root / "positions"
    candidates = [
        root / f"{venue.value}.json",
        root / f"{venue.value}.jsonl",
        root / venue.value / "positions.json",
        root / venue.value / "positions.jsonl",
    ]
    if market_id:
        candidates.extend(
            [
                root / venue.value / f"{market_id}.json",
                root / venue.value / f"{market_id}.jsonl",
            ]
        )
    return candidates


def _coerce_position_payload(raw: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("positions", "items", "records", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(isinstance(item, dict) for item in payload.values()):
            return [item for item in payload.values() if isinstance(item, dict)]
    return []


def _load_position_records(venue: VenueName, market_id: str | None = None) -> list[LedgerPosition]:
    payloads: list[dict[str, Any]] = []
    env_json = os.getenv(f"{venue.value.upper()}_POSITIONS_JSON") or os.getenv("PREDICTION_MARKETS_POSITIONS_JSON")
    if env_json:
        payloads.extend(_coerce_position_payload(env_json))
    for env_name in (f"{venue.value.upper()}_POSITIONS_PATH", "PREDICTION_MARKETS_POSITIONS_PATH"):
        env_path = os.getenv(env_name)
        if not env_path:
            continue
        path = Path(env_path)
        if path.exists():
            payloads.extend(_coerce_position_payload(path.read_text(encoding="utf-8")))
    for path in _position_cache_candidates(venue, market_id):
        if path.exists():
            payloads.extend(_coerce_position_payload(path.read_text(encoding="utf-8")))
    records: list[LedgerPosition] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if market_id and str(payload.get("market_id") or "").strip() not in {"", market_id}:
            continue
        candidate = {
            "market_id": str(payload.get("market_id") or market_id or ""),
            "venue": payload.get("venue") or venue,
            "side": payload.get("side") or payload.get("position_side") or payload.get("execution_side") or TradeSide.yes,
            "quantity": payload.get("quantity", payload.get("size", 0.0)),
            "entry_price": payload.get("entry_price", payload.get("price", 0.0)),
            "mark_price": payload.get("mark_price"),
            "unrealized_pnl": payload.get("unrealized_pnl"),
            "metadata": dict(payload.get("metadata") or {}),
        }
        try:
            records.append(LedgerPosition.model_validate(candidate))
        except Exception:
            continue
    return records


class SurrogatePolymarketAdapter:
    venue = VenueName.polymarket

    def __init__(self) -> None:
        self._markets = self._build_markets()
        self._snapshots = {item.market_id: self._build_snapshot(item) for item in self._markets}
        self._policies = {item.market_id: self._build_policy(item) for item in self._markets}

    def describe_capabilities(self) -> VenueCapabilitiesModel:
        return VenueCapabilitiesModel(
            venue=self.venue,
            discovery=True,
            metadata=True,
            orderbook=True,
            trades=True,
            positions=True,
            execution=False,
            streaming=True,
            interviews=False,
            read_only=True,
            supports_replay=True,
            metadata_map=_capability_metadata(
                backend_mode="surrogate",
                venue_kind="execution",
                venue_type="execution",
                role_labels=["execution", "watchlist"],
                api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
                supported_order_types=[],
                read_only=True,
                paper_capable=True,
                execution_capable=True,
                positions_capable=True,
                events_capable=True,
                discovery_notes=["Market discovery is available via the surrogate catalogue."],
                orderbook_notes=["Synthetic orderbook data is exposed for planning and replay."],
                trades_notes=["Synthetic trade history is exposed for audit and replay."],
                execution_notes=["No live order placement; execution is simulated only."],
                websocket_notes=["Streaming is represented by the surrogate data layer, not a live socket."],
                paper_mode_notes=["Dry-run and bounded rehearsal are supported in surrogate mode."],
                automation_constraints=["No live automation in surrogate mode.", "Authorization gates are informational only."],
                rate_limit_notes=["No live venue rate limits are consumed in surrogate mode."],
                compliance_notes=["Compliance checks are simulated for dry-run and rehearsal flows."],
            ),
        )

    def list_markets(self, *, config: MarketUniverseConfig | None = None, limit: int | None = None) -> list[MarketDescriptor]:
        markets = list(self._markets)
        config = config or MarketUniverseConfig(venue=self.venue)
        if config.active_only:
            markets = [market for market in markets if market.status == MarketStatus.open]
        if config.query:
            query = config.query.lower()
            markets = [
                market
                for market in markets
                if query in market.title.lower() or query in market.question.lower() or query in (market.slug or "").lower()
            ]
        markets = [market for market in markets if market.liquidity is None or market.liquidity >= config.min_liquidity]
        markets = [market for market in markets if market.clarity_score >= config.min_clarity_score]
        allowed_statuses = set(config.statuses)
        markets = [market for market in markets if market.status in allowed_statuses]
        deduped: dict[str, MarketDescriptor] = {}
        for market in markets:
            key = market.canonical_event_id or market.market_id
            if key not in deduped or self._score_market(market) > self._score_market(deduped[key]):
                deduped[key] = market
        markets = sorted(deduped.values(), key=self._score_market, reverse=True)
        cap = limit if limit is not None else config.limit
        return markets[:cap]

    def get_market(self, market_id: str) -> MarketDescriptor:
        for market in self._markets:
            if market.market_id == market_id:
                return market.model_copy(deep=True)
        raise MarketDataUnavailableError(f"Unknown surrogate market: {market_id}")

    def get_snapshot(self, market_id: str) -> MarketSnapshot:
        snapshot = self._snapshots.get(market_id)
        if snapshot is None:
            market = self.get_market(market_id)
            snapshot = self._build_snapshot(market)
        return snapshot.model_copy(deep=True)

    def get_resolution_policy(self, market_id: str) -> ResolutionPolicy:
        policy = self._policies.get(market_id)
        if policy is None:
            market = self.get_market(market_id)
            policy = self._build_policy(market)
        return policy.model_copy(deep=True)

    def get_trades(self, market_id: str) -> list[TradeRecord]:
        snapshot = self.get_snapshot(market_id)
        return list(snapshot.trades)

    def get_events(self, market_id: str) -> list[MarketDescriptor]:
        _ = market_id
        return _event_markets(self.list_markets())

    def get_positions(self, market_id: str) -> list[LedgerPosition]:
        return _load_position_records(self.venue, market_id)

    def get_evidence(self, market_id: str) -> list[EvidencePacket]:
        market = self.get_market(market_id)
        notes = [
            f"Official source: {market.resolution_source or 'unknown'}",
            f"Liquidity snapshot: {market.liquidity or 0.0:.0f}",
        ]
        if market.status == MarketStatus.open:
            notes.append("Market is open and suitable for analysis.")
        return [
            EvidencePacket(
                market_id=market.market_id,
                venue=self.venue,
                source_kind=SourceKind.market,
                claim=note,
                stance="neutral",
                summary=note,
                confidence=0.6,
                freshness_score=0.8,
                credibility_score=0.7,
                metadata={"source": "surrogate"},
            )
            for note in notes
        ]

    def health(self) -> VenueHealthReport:
        return VenueHealthReport(
            venue=self.venue,
            backend_mode="surrogate",
            healthy=True,
            message="surrogate available",
            details={
                "transport": "local",
                "mode": "surrogate",
                "market_count": len(self._markets),
                "capabilities": self.describe_capabilities().model_dump(mode="json"),
            },
        )

    @staticmethod
    def _score_market(market: MarketDescriptor) -> float:
        score = market.clarity_score
        if market.liquidity:
            score += min(0.25, market.liquidity / 100000.0)
        if market.status == MarketStatus.open:
            score += 0.1
        return score

    def _build_markets(self) -> list[MarketDescriptor]:
        now = datetime.now(timezone.utc)

        def _safe_month(year: int, month: int, day: int, hour: int = 0) -> datetime:
            last_day = monthrange(year, month)[1]
            return datetime(year, month, min(day, last_day), hour, tzinfo=timezone.utc)

        return [
            MarketDescriptor(
                market_id="pm_demo_election",
                venue=self.venue,
                venue_type=VenueType.execution,
                title="Demo election market",
                question="Will the demo candidate win the election?",
                slug="demo-election-market",
                status=MarketStatus.open,
                source_url="https://polymarket.com/market/demo-election-market",
                canonical_event_id="demo-election-2026",
                resolution_source="https://example.com/resolution",
                resolution_date=_safe_month(now.year + 4, 11, 5),
                close_time=_safe_month(now.year + 4, 11, 4),
                volume=190000.0,
                liquidity=25000.0,
                tags=["politics", "demo"],
                categories=["politics"],
                metadata={"clarity_hint": "high", "surrogate_slug": "demo-election-market"},
                outcomes=["Yes", "No"],
                token_ids=["yes_demo", "no_demo"],
            ),
            MarketDescriptor(
                market_id="polymarket-fed-cut-q3-2026",
                venue=self.venue,
                venue_type=VenueType.execution,
                title="Fed cuts rates by 25bps by Q3 2026",
                question="Will the Fed cut rates by 25bps by Q3 2026?",
                slug="fed-cut-q3-2026",
                status=MarketStatus.open,
                source_url="https://polymarket.com/market/fed-cut-q3-2026",
                canonical_event_id="fed_cut_2026_q3",
                resolution_source="https://www.federalreserve.gov/",
                resolution_date=_safe_month(now.year, 9 if now.month <= 9 else 12, now.day),
                close_time=_safe_month(now.year, 8 if now.month <= 8 else 12, now.day),
                volume=250000.0,
                liquidity=80000.0,
                tags=["macro", "rates"],
                categories=["economy"],
                metadata={"clarity_hint": "high"},
                outcomes=["Yes", "No"],
                token_ids=["yes_fed", "no_fed"],
            ),
            MarketDescriptor(
                market_id="polymarket-btc-above-120k-2026",
                venue=self.venue,
                venue_type=VenueType.execution,
                title="BTC above 120k by year end 2026",
                question="Will BTC trade above 120k by year end 2026?",
                slug="btc-above-120k-2026",
                status=MarketStatus.open,
                source_url="https://polymarket.com/market/btc-above-120k-2026",
                canonical_event_id="btc_120k_2026",
                resolution_source="https://www.coindesk.com/",
                resolution_date=_safe_month(now.year if now.month <= 11 else now.year + 1, 12, now.day),
                close_time=_safe_month(now.year if now.month <= 11 else now.year + 1, 11, now.day),
                volume=150000.0,
                liquidity=42000.0,
                tags=["crypto"],
                categories=["crypto"],
                outcomes=["Yes", "No"],
                token_ids=["yes_btc", "no_btc"],
            ),
            MarketDescriptor(
                market_id="polymarket-ambiguous-geo-event",
                venue=self.venue,
                venue_type=VenueType.execution,
                title="A vague geopolitical event resolves positively",
                question="Will a vaguely defined geopolitical event happen?",
                slug="ambiguous-geo-event",
                status=MarketStatus.open,
                source_url="https://polymarket.com/market/ambiguous-geo-event",
                canonical_event_id="ambiguous_geo_event",
                resolution_source="https://example.com/ambiguous-resolution",
                resolution_date=_safe_month(now.year, 12, now.day),
                close_time=_safe_month(now.year, 11, now.day),
                volume=30000.0,
                liquidity=5000.0,
                tags=["geo", "ambiguous"],
                categories=["politics"],
                metadata={"clarity_hint": "low"},
                outcomes=["Yes", "No"],
                token_ids=["yes_geo", "no_geo"],
            ),
            MarketDescriptor(
                market_id="polymarket-closed-market",
                venue=self.venue,
                venue_type=VenueType.execution,
                title="Closed historical market",
                question="A closed market kept for replay only.",
                slug="closed-historical",
                status=MarketStatus.closed,
                source_url="https://polymarket.com/market/closed-market",
                canonical_event_id="closed_market_2025",
                resolution_source="https://example.com/historical",
                resolution_date=now,
                close_time=now,
                volume=1000.0,
                liquidity=100.0,
                tags=["historical"],
                categories=["reference"],
                outcomes=["Yes", "No"],
                token_ids=["yes_closed", "no_closed"],
            ),
        ]

    def _build_snapshot(self, market: MarketDescriptor) -> MarketSnapshot:
        if market.market_id == "polymarket-fed-cut-q3-2026":
            bids = [OrderBookLevel(price=0.56, size=1000), OrderBookLevel(price=0.58, size=1500)]
            asks = [OrderBookLevel(price=0.61, size=1200), OrderBookLevel(price=0.63, size=800)]
            trades = [TradeRecord(price=0.59, size=250, side=TradeSide.buy)]
        elif market.market_id == "polymarket-btc-above-120k-2026":
            bids = [OrderBookLevel(price=0.37, size=900), OrderBookLevel(price=0.39, size=700)]
            asks = [OrderBookLevel(price=0.43, size=800), OrderBookLevel(price=0.46, size=500)]
            trades = [TradeRecord(price=0.41, size=100, side=TradeSide.buy)]
        elif market.market_id == "polymarket-ambiguous-geo-event":
            bids = [OrderBookLevel(price=0.48, size=300), OrderBookLevel(price=0.49, size=200)]
            asks = [OrderBookLevel(price=0.51, size=250), OrderBookLevel(price=0.52, size=150)]
            trades = [TradeRecord(price=0.5, size=25, side=TradeSide.buy)]
        else:
            bids = [OrderBookLevel(price=0.5, size=100)]
            asks = [OrderBookLevel(price=0.51, size=100)]
            trades = [TradeRecord(price=0.5, size=10, side=TradeSide.buy)]
        return MarketSnapshot(
            market_id=market.market_id,
            venue=market.venue,
            venue_type=market.venue_type,
            title=market.title,
            question=market.question,
            status=market.status,
            orderbook=MarketOrderBook(bids=bids, asks=asks, source="surrogate"),
            trades=trades,
            volume=market.volume,
            liquidity=market.liquidity,
            open_interest=(market.liquidity or 0.0) * 1.8,
            close_time=market.close_time,
            resolution_source=market.resolution_source,
            source_url=market.source_url,
            canonical_event_id=market.canonical_event_id,
            staleness_ms=2500 if market.market_id != "polymarket-ambiguous-geo-event" else 15000,
            tags=list(market.tags),
            metadata={"backend_mode": "surrogate"},
        )

    def _build_policy(self, market: MarketDescriptor) -> ResolutionPolicy:
        if market.market_id == "polymarket-ambiguous-geo-event":
            return ResolutionPolicy(
                market_id=market.market_id,
                venue=market.venue,
                official_source=market.resolution_source or "",
                source_url=market.resolution_source,
                resolution_rules=[
                    "Ambiguous geopolitical phrasing requires official resolution review.",
                    "Treat the question as manual review only.",
                ],
                ambiguity_flags=["ambiguous_entity", "broad_event_definition"],
                manual_review_required=True,
                status=ResolutionStatus.ambiguous,
                metadata={"backend_mode": "surrogate"},
            )
        return ResolutionPolicy(
            market_id=market.market_id,
            venue=market.venue,
            official_source=market.resolution_source or "official source",
            source_url=market.resolution_source,
            resolution_rules=[
                "Use the official source stated in the market details.",
                "Resolve according to the explicit yes/no condition of the market.",
            ],
            ambiguity_flags=[],
            manual_review_required=False,
            status=ResolutionStatus.clear,
            metadata={"backend_mode": "surrogate"},
        )


class HttpPolymarketAdapter:
    venue = VenueName.polymarket

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._source = HttpJSONSource(base_url, timeout_seconds=timeout_seconds)

    def describe_capabilities(self) -> VenueCapabilitiesModel:
        return VenueCapabilitiesModel(
            venue=self.venue,
            discovery=True,
            metadata=True,
            orderbook=True,
            trades=True,
            positions=True,
            execution=False,
            streaming=False,
            interviews=False,
            read_only=True,
            supports_replay=True,
            metadata_map=_capability_metadata(
                backend_mode="live-http",
                venue_kind="execution",
                venue_type="execution",
                role_labels=["execution", "watchlist"],
                api_access=["catalog", "snapshot", "orderbook", "trades", "positions", "events", "evidence"],
                supported_order_types=[],
                read_only=True,
                paper_capable=True,
                execution_capable=True,
                positions_capable=True,
                events_capable=True,
                discovery_notes=["Discovery is exposed by the HTTP adapter through the market catalog."],
                orderbook_notes=["Orderbook snapshots are fetched from the live HTTP source."],
                trades_notes=["Trade history is fetched from the live HTTP source when available."],
                execution_notes=["The HTTP adapter does not place orders; execution remains external."],
                websocket_notes=["No websocket transport is provided by the HTTP adapter."],
                paper_mode_notes=["Paper planning is supported via snapshot and catalog reads."],
                automation_constraints=["No live order placement through the HTTP adapter."],
                rate_limit_notes=["Honor upstream HTTP API limits and back off on 429 responses."],
                compliance_notes=["Live routing still requires downstream authorization and compliance approval."],
            ),
        )

    def list_markets(self, *, config: MarketUniverseConfig | None = None, limit: int | None = None) -> list[MarketDescriptor]:
        config = config or MarketUniverseConfig(venue=self.venue)
        data = self._source.get("markets")
        if not isinstance(data, list):
            raise MarketDataUnavailableError("Expected /markets response to be a list.")
        markets = [self._descriptor_from_gamma(item) for item in data]
        if config.active_only:
            markets = [market for market in markets if market.active and not market.closed]
        if config.query:
            query = config.query.lower()
            markets = [
                market
                for market in markets
                if query in market.title.lower() or query in market.question.lower() or query in (market.slug or "").lower()
            ]
        markets = [market for market in markets if market.liquidity is None or market.liquidity >= config.min_liquidity]
        markets = [market for market in markets if market.clarity_score >= config.min_clarity_score]
        markets = [market for market in markets if market.status in set(config.statuses)]
        cap = limit if limit is not None else config.limit
        return markets[:cap]

    def get_market(self, market_id: str) -> MarketDescriptor:
        return self._descriptor_from_gamma(self._source.get(f"markets/{market_id}"))

    def get_snapshot(self, market_id: str) -> MarketSnapshot:
        raw = self._source.get(f"markets/{market_id}")
        descriptor = self._descriptor_from_gamma(raw)
        prices = self._coerce_prices(raw.get("outcomePrices"))
        price_yes = prices[0] if prices else 0.5
        price_no = prices[1] if len(prices) > 1 else max(0.0, 1.0 - price_yes)
        orderbook = MarketOrderBook(
            bids=[OrderBookLevel(price=price_yes, size=100.0)],
            asks=[OrderBookLevel(price=min(0.999, price_yes + 0.01), size=100.0)],
            source="gamma",
        )
        return MarketSnapshot(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            title=descriptor.title,
            question=descriptor.question,
            status=descriptor.status,
            orderbook=orderbook,
            trades=[],
            volume=descriptor.volume,
            liquidity=descriptor.liquidity,
            open_interest=descriptor.liquidity,
            close_time=descriptor.close_time,
            resolution_source=descriptor.resolution_source,
            source_url=descriptor.source_url,
            canonical_event_id=descriptor.canonical_event_id,
            market_implied_probability=price_yes,
            fair_probability_hint=price_yes,
            spread_bps=orderbook.spread_bps,
            staleness_ms=0,
            tags=list(descriptor.tags),
            metadata={"backend_mode": "live-http", "raw": raw},
        )

    def get_resolution_policy(self, market_id: str) -> ResolutionPolicy:
        descriptor = self.get_market(market_id)
        return ResolutionPolicy(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            official_source=descriptor.resolution_source or "official source",
            source_url=descriptor.resolution_source,
            resolution_rules=[
                "Use the official source stated in the market details.",
                "Resolve according to the explicit yes/no condition of the market.",
            ],
            ambiguity_flags=[],
            manual_review_required=False,
            status=ResolutionStatus.clear,
            metadata={"backend_mode": "live-http"},
        )

    def get_trades(self, market_id: str) -> list[TradeRecord]:
        return []

    def get_events(self, market_id: str) -> list[MarketDescriptor]:
        _ = market_id
        return _event_markets(self.list_markets())

    def get_positions(self, market_id: str) -> list[LedgerPosition]:
        return _load_position_records(self.venue, market_id)

    def get_evidence(self, market_id: str) -> list[EvidencePacket]:
        descriptor = self.get_market(market_id)
        return [
            EvidencePacket(
                market_id=descriptor.market_id,
                venue=descriptor.venue,
                source_kind=SourceKind.official,
                claim=f"Market source: {descriptor.source_url or 'unknown'}",
                stance="neutral",
                summary=descriptor.question,
                source_url=descriptor.source_url,
                confidence=0.85,
                freshness_score=0.9,
                credibility_score=0.9,
                metadata={"backend_mode": "live-http"},
            )
        ]

    def health(self) -> VenueHealthReport:
        return VenueHealthReport(
            venue=self.venue,
            backend_mode="live",
            healthy=True,
            message="live available",
            details={
                "transport": "http",
                "mode": "live",
                "base_url": self.base_url,
                "capabilities": self.describe_capabilities().model_dump(mode="json"),
            },
        )

    @staticmethod
    def _descriptor_from_gamma(raw: dict[str, Any]) -> MarketDescriptor:
        return MarketDescriptor(
            venue=VenueName.polymarket,
            venue_type=VenueType.execution,
            market_id=str(raw.get("id")),
            slug=raw.get("slug"),
            title=str(raw.get("title") or raw.get("question") or ""),
            question=str(raw.get("question") or raw.get("title") or ""),
            description=str(raw.get("description") or ""),
            category=raw.get("category"),
            active=bool(raw.get("active", True)),
            closed=bool(raw.get("closed", False)),
            status=MarketStatus.closed if bool(raw.get("closed", False)) else MarketStatus.open,
            resolution_source=raw.get("resolutionSource"),
            resolution_date=HttpPolymarketAdapter._parse_datetime(raw.get("endDate")),
            close_time=HttpPolymarketAdapter._parse_datetime(raw.get("endDate")),
            outcomes=HttpPolymarketAdapter._coerce_list(raw.get("outcomes")),
            token_ids=HttpPolymarketAdapter._coerce_list(raw.get("clobTokenIds")),
            liquidity=HttpPolymarketAdapter._safe_float(raw.get("liquidity")),
            volume=HttpPolymarketAdapter._safe_float(raw.get("volume")),
            raw=raw,
        )

    @staticmethod
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

    @staticmethod
    def _coerce_list(raw: Any) -> list[str]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return []

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


@dataclass
class PolymarketAdapter:
    backend_mode: str = "auto"
    base_url: str | None = None
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        self._surrogate = SurrogatePolymarketAdapter()
        self._live: HttpPolymarketAdapter | None = None
        if self.base_url is None:
            self.base_url = os.getenv("POLYMARKET_GAMMA_BASE_URL") or os.getenv("POLYMARKET_BASE_URL")
        selected = (self.backend_mode or "auto").strip().lower()
        if selected == "live" and self.base_url:
            self._live = HttpPolymarketAdapter(self.base_url, timeout_seconds=self.timeout_seconds)
        elif selected == "auto" and self.base_url:
            try:
                candidate = HttpPolymarketAdapter(self.base_url, timeout_seconds=self.timeout_seconds)
                candidate.describe_capabilities()
                self._live = candidate
            except Exception:
                self._live = None

    @property
    def venue(self) -> VenueName:
        return VenueName.polymarket

    def describe_capabilities(self) -> VenueCapabilitiesModel:
        adapter = self._live if self._live is not None else self._surrogate
        return adapter.describe_capabilities()

    def list_markets(self, *, config: MarketUniverseConfig | None = None, limit: int | None = None) -> list[MarketDescriptor]:
        return self._with_fallback(lambda adapter: adapter.list_markets(config=config, limit=limit))

    def get_market(self, market_id: str) -> MarketDescriptor:
        return self._with_fallback(lambda adapter: adapter.get_market(market_id))

    def get_snapshot(self, market_id: str) -> MarketSnapshot:
        return self._with_fallback(lambda adapter: adapter.get_snapshot(market_id))

    def get_resolution_policy(self, market_id: str) -> ResolutionPolicy:
        return self._with_fallback(lambda adapter: adapter.get_resolution_policy(market_id))

    def get_trades(self, market_id: str) -> list[TradeRecord]:
        return self._with_fallback(lambda adapter: adapter.get_trades(market_id))

    def get_events(self, market_id: str) -> list[MarketDescriptor]:
        return self._with_fallback(lambda adapter: adapter.get_events(market_id))

    def get_positions(self, market_id: str) -> list[LedgerPosition]:
        return self._with_fallback(lambda adapter: adapter.get_positions(market_id))

    def get_evidence(self, market_id: str) -> list[EvidencePacket]:
        return self._with_fallback(lambda adapter: adapter.get_evidence(market_id))

    def health(self) -> VenueHealthReport:
        if self._live is not None:
            try:
                capabilities = self._live.describe_capabilities()
                return VenueHealthReport(
                    venue=self.venue,
                    backend_mode="live",
                    healthy=True,
                    message="live available",
                    details={
                        "transport": "http",
                        "mode": "live",
                        "base_url": self.base_url,
                        "fallback": None,
                        "capabilities": capabilities.model_dump(mode="json"),
                    },
                )
            except Exception as exc:
                return VenueHealthReport(
                    venue=self.venue,
                    backend_mode="live",
                    healthy=False,
                    message=str(exc),
                    details={
                        "fallback": "surrogate",
                        "transport": "http",
                        "mode": "live",
                        "base_url": self.base_url,
                        "issues": ["api_error"],
                        "error_type": type(exc).__name__,
                    },
                )
        health = self._surrogate.health()
        health.details.setdefault("fallback", "surrogate")
        return health

    def _with_fallback(self, fn):
        if self._live is not None:
            try:
                return fn(self._live)
            except (HTTPError, URLError, MarketDataUnavailableError, KeyError, ValueError):
                pass
            except Exception:
                pass
        return fn(self._surrogate)


@dataclass
class VenueExecutionAdapterBase:
    venue: VenueName
    backend_mode: str = "auto"
    execution_registry: VenueExecutionRegistry = field(default_factory=lambda: DEFAULT_VENUE_EXECUTION_REGISTRY)

    def describe_execution_capabilities(self) -> VenueExecutionCapability:
        return self.execution_registry.capability_for(self.venue).model_copy(deep=True)

    def build_execution_plan(
        self,
        *,
        market: MarketDescriptor,
        dry_run: bool,
        allow_live_execution: bool,
        authorized: bool,
        compliance_approved: bool,
        required_scope: str,
        scopes: list[str] | None = None,
        jurisdiction: str | None = None,
        account_type: str | None = None,
        automation_allowed: bool | None = None,
        rate_limit_ok: bool | None = None,
        tos_accepted: bool | None = None,
        allowed_jurisdictions: set[str] | None = None,
        allowed_account_types: set[str] | None = None,
        require_automation_allowed: bool = False,
        require_rate_limit_ok: bool = False,
        require_tos_accepted: bool = False,
        dry_run_requires_authorization: bool = False,
        dry_run_requires_compliance: bool = False,
    ) -> VenueExecutionPlan:
        capability = self.describe_execution_capabilities()
        scopes = list(scopes or [])
        dry_run_effective = bool(dry_run or not allow_live_execution or not capability.live_execution_supported)
        live_execution_requested = not dry_run
        bounded_execution_supported = bool(capability.bounded_execution_supported)
        market_execution_supported = bool(capability.market_execution_supported)
        auth_required = dry_run_requires_authorization if dry_run else capability.live_requires_authorization
        compliance_required = dry_run_requires_compliance if dry_run else capability.live_requires_compliance
        auth_passed = (not auth_required) or authorized
        if auth_required and required_scope and required_scope not in scopes:
            auth_passed = False
        compliance_passed = (not compliance_required) or compliance_approved
        allowed_jurisdictions = set(allowed_jurisdictions or set())
        allowed_account_types = set(allowed_account_types or set())
        venue_allowed_jurisdictions = set(capability.allowed_jurisdictions)
        venue_allowed_account_types = set(capability.allowed_account_types)
        effective_jurisdictions = allowed_jurisdictions or venue_allowed_jurisdictions
        effective_account_types = allowed_account_types or venue_allowed_account_types
        jurisdiction_required = bool(effective_jurisdictions)
        account_type_required = bool(effective_account_types)
        automation_required = bool(require_automation_allowed)
        rate_limit_required = bool(require_rate_limit_ok)
        tos_required = bool(require_tos_accepted)
        automation_value = capability.automation_allowed if automation_allowed is None else bool(automation_allowed)
        rate_limit_value = True if rate_limit_ok is None else bool(rate_limit_ok)
        tos_value = True if tos_accepted is None else bool(tos_accepted)
        jurisdiction_passed = True
        if jurisdiction_required:
            jurisdiction_passed = jurisdiction is not None and str(jurisdiction).strip().lower() in {item.strip().lower() for item in effective_jurisdictions}
        account_type_passed = True
        if account_type_required:
            account_type_passed = account_type is not None and str(account_type).strip().lower() in {item.strip().lower() for item in effective_account_types}
        automation_passed = (not automation_required) or automation_value
        rate_limit_passed = (not rate_limit_required) or rate_limit_value
        tos_passed = (not tos_required) or tos_value

        blocked_reasons: list[str] = []
        if not capability.route_supported:
            blocked_reasons.append(f"route_not_supported:{market.venue.value}")
        if market.venue_type not in {VenueType.execution, VenueType.execution_equivalent}:
            blocked_reasons.append(f"non_execution_venue_type:{market.venue_type.value}")
        if dry_run and not capability.dry_run_supported:
            blocked_reasons.append(f"dry_run_unsupported:{market.venue.value}")
        if live_execution_requested and not capability.live_execution_supported:
            blocked_reasons.append(f"live_execution_unsupported:{market.venue.value}")
        if live_execution_requested and not allow_live_execution:
            blocked_reasons.append("live_execution_disabled")
        if auth_required and not authorized:
            blocked_reasons.append("authorization_failed")
        if auth_required and required_scope and required_scope not in scopes:
            blocked_reasons.append(f"missing_scope:{required_scope}")
        if compliance_required and not compliance_approved:
            blocked_reasons.append("compliance_failed")
        if jurisdiction_required and not jurisdiction_passed:
            blocked_reasons.append("jurisdiction_not_allowed")
        if account_type_required and not account_type_passed:
            blocked_reasons.append("account_type_not_allowed")
        if automation_required and not automation_passed:
            blocked_reasons.append("automation_not_allowed")
        if rate_limit_required and not rate_limit_passed:
            blocked_reasons.append("rate_limit_exceeded")
        if tos_required and not tos_passed:
            blocked_reasons.append("tos_not_accepted")

        allowed = not blocked_reasons
        selected_order_path = (
            capability.bounded_order_path
            if dry_run_effective
            else capability.live_order_path
        ) or capability.live_order_path or capability.bounded_order_path or "unavailable"
        selected_cancel_path = (
            capability.cancel_order_path
            if (capability.live_execution_supported or capability.bounded_execution_supported or capability.market_execution_supported)
            else "unavailable"
        ) or capability.cancel_order_path or capability.bounded_order_path or "unavailable"
        return VenueExecutionPlan(
            venue=market.venue,
            adapter_name=capability.adapter_name,
            backend_mode=self.backend_mode,
            planning_bucket=_planning_bucket_for_venue_type(market.venue_type),
            dry_run_requested=dry_run,
            dry_run_effective=dry_run_effective,
            live_execution_requested=live_execution_requested,
            live_execution_supported=capability.live_execution_supported,
            bounded_execution_supported=bounded_execution_supported,
            market_execution_supported=market_execution_supported,
            order_audit_supported=True,
            fill_audit_supported=True,
            position_audit_supported=True,
            execution_mode=capability.mode_for(dry_run=dry_run, allow_live_execution=allow_live_execution, bounded_execution=bounded_execution_supported),
            route_supported=capability.route_supported,
            auth_required=auth_required,
            auth_passed=auth_passed,
            compliance_required=compliance_required,
            compliance_passed=compliance_passed,
            credential_evidence={
                "schema_version": "v1",
                "auth_required": auth_required,
                "auth_passed": auth_passed,
                "compliance_required": compliance_required,
                "compliance_passed": compliance_passed,
                "required_scope": required_scope,
                "scopes": list(scopes),
                "jurisdiction": jurisdiction,
                "account_type": account_type,
                "automation_allowed": automation_value,
                "rate_limit_ok": rate_limit_value,
                "tos_accepted": tos_value,
            },
            jurisdiction_required=jurisdiction_required,
            jurisdiction_passed=jurisdiction_passed,
            account_type_required=account_type_required,
            account_type_passed=account_type_passed,
            automation_required=automation_required,
            automation_passed=automation_passed,
            rate_limit_required=rate_limit_required,
            rate_limit_passed=rate_limit_passed,
            tos_required=tos_required,
            tos_passed=tos_passed,
            configuration_evidence={
                "schema_version": "v1",
                "venue_order_path": selected_order_path,
                "venue_order_cancel_path": selected_cancel_path,
                "order_paths": {
                    "live": capability.live_order_path,
                    "bounded": capability.bounded_order_path,
                    "cancel": capability.cancel_order_path,
                },
                "market_id": market.market_id,
                "market_slug": market.slug,
                "market_venue_type": market.venue_type.value,
            },
            readiness_evidence={
                "schema_version": "v1",
                "dry_run_requested": dry_run,
                "dry_run_effective": dry_run_effective,
                "live_execution_requested": live_execution_requested,
                "live_execution_supported": capability.live_execution_supported,
                "bounded_execution_supported": bounded_execution_supported,
                "market_execution_supported": market_execution_supported,
                "allowed": allowed,
                "blocked_reasons": list(blocked_reasons),
            },
            venue_order_path=selected_order_path,
            venue_order_cancel_path=selected_cancel_path,
            allowed=allowed,
            blocked_reasons=blocked_reasons,
            metadata={
                "capability": capability.model_dump(mode="json"),
                "market_venue_type": market.venue_type.value,
                "market_id": market.market_id,
                "market_slug": market.slug,
                "jurisdiction": jurisdiction,
                "account_type": account_type,
                "automation_allowed": automation_value,
                "rate_limit_ok": rate_limit_value,
                "tos_accepted": tos_value,
                "planning_bucket": _planning_bucket_for_venue_type(market.venue_type),
                "order_paths": {
                    "live": capability.live_order_path,
                    "bounded": capability.bounded_order_path,
                    "cancel": capability.cancel_order_path,
                },
                "selected_order_path": selected_order_path,
                "selected_cancel_path": selected_cancel_path,
            },
        )


@dataclass
class PolymarketExecutionAdapter(VenueExecutionAdapterBase):
    venue: VenueName = VenueName.polymarket
    execution_runtime_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        runtime_config = dict(self.execution_runtime_config or _resolve_polymarket_execution_runtime_config(self.backend_mode))
        self.execution_runtime_config = runtime_config
        self.backend_mode = runtime_config.get("selected_backend_mode", self.backend_mode)

    def describe_execution_capabilities(self) -> VenueExecutionCapability:
        capability = super().describe_execution_capabilities()
        runtime_config = dict(self.execution_runtime_config or _resolve_polymarket_execution_runtime_config(self.backend_mode))
        metadata = {
            **dict(capability.metadata),
            "execution_runtime_config": runtime_config,
            "credential_evidence": dict(runtime_config.get("credential_evidence") or {}),
            "configuration_evidence": dict(runtime_config.get("configuration_evidence") or {}),
            "readiness_evidence": dict(runtime_config.get("readiness_evidence") or {}),
            "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
            "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
            "runtime_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
            "runtime_ready": runtime_config.get("runtime_ready", False),
            "ready_for_live_execution": runtime_config.get("ready_for_live_execution", False),
            "mock_transport": runtime_config.get("mock_transport", False),
            "auth_configured": runtime_config.get("auth_configured", False),
            "auth_scheme": runtime_config.get("auth_scheme", "bearer"),
            "missing_requirements": list(runtime_config.get("missing_requirements", [])),
            "order_paths": {
                "live": runtime_config.get("live_order_path", capability.live_order_path),
                "bounded": runtime_config.get("bounded_order_path", capability.bounded_order_path),
                "cancel": runtime_config.get("cancel_order_path", capability.cancel_order_path),
                "bounded_cancel": runtime_config.get("bounded_cancel_path"),
            },
            "readiness_notes": list(runtime_config.get("readiness_notes", [])),
        }
        return capability.model_copy(
            update={
                "live_order_path": runtime_config.get("live_order_path") or capability.live_order_path,
                "bounded_order_path": runtime_config.get("bounded_order_path") or capability.bounded_order_path,
                "cancel_order_path": runtime_config.get("cancel_order_path") or capability.cancel_order_path,
                "metadata": metadata,
            }
        )

    def build_execution_plan(
        self,
        *,
        market: MarketDescriptor,
        dry_run: bool,
        allow_live_execution: bool,
        authorized: bool,
        compliance_approved: bool,
        required_scope: str,
        scopes: list[str] | None = None,
        jurisdiction: str | None = None,
        account_type: str | None = None,
        automation_allowed: bool | None = None,
        rate_limit_ok: bool | None = None,
        tos_accepted: bool | None = None,
        allowed_jurisdictions: set[str] | None = None,
        allowed_account_types: set[str] | None = None,
        require_automation_allowed: bool = False,
        require_rate_limit_ok: bool = False,
        require_tos_accepted: bool = False,
        dry_run_requires_authorization: bool = False,
        dry_run_requires_compliance: bool = False,
    ) -> VenueExecutionPlan:
        plan = super().build_execution_plan(
            market=market,
            dry_run=dry_run,
            allow_live_execution=allow_live_execution,
            authorized=authorized,
            compliance_approved=compliance_approved,
            required_scope=required_scope,
            scopes=scopes,
            jurisdiction=jurisdiction,
            account_type=account_type,
            automation_allowed=automation_allowed,
            rate_limit_ok=rate_limit_ok,
            tos_accepted=tos_accepted,
            allowed_jurisdictions=allowed_jurisdictions,
            allowed_account_types=allowed_account_types,
            require_automation_allowed=require_automation_allowed,
            require_rate_limit_ok=require_rate_limit_ok,
            require_tos_accepted=require_tos_accepted,
            dry_run_requires_authorization=dry_run_requires_authorization,
            dry_run_requires_compliance=dry_run_requires_compliance,
        )
        runtime_config = dict(self.execution_runtime_config or _resolve_polymarket_execution_runtime_config(self.backend_mode))
        live_transport_bound = bool(getattr(self, "order_submitter", None))
        live_cancellation_bound = bool(getattr(self, "cancel_submitter", None))
        transport_bound = bool(live_transport_bound and live_cancellation_bound)
        base_credential_evidence = dict(plan.credential_evidence or {})
        base_configuration_evidence = dict(plan.configuration_evidence or {})
        base_readiness_evidence = dict(plan.readiness_evidence or {})
        runtime_ready = bool(
            runtime_config.get("runtime_ready", False)
            or runtime_config.get("ready_for_live_execution", False)
            or live_transport_bound
        )
        ready_for_live_execution = bool(runtime_config.get("ready_for_live_execution", False) or live_transport_bound)
        credential_evidence = _merge_evidence_dict(
            plan.credential_evidence,
            runtime_config.get("credential_evidence"),
            {
                "auth_passed": plan.auth_passed,
                "compliance_passed": plan.compliance_passed,
                "live_transport_bound": live_transport_bound,
                "live_cancellation_bound": live_cancellation_bound,
                "transport_bound": transport_bound,
            },
        )
        for key, value in {
            "live_transport_bound": live_transport_bound,
            "live_cancellation_bound": live_cancellation_bound,
            "transport_bound": transport_bound,
        }.items():
            if key not in base_credential_evidence:
                credential_evidence[key] = value
        configuration_evidence = _merge_evidence_dict(
            base_configuration_evidence,
            runtime_config.get("configuration_evidence"),
            {
                "venue_order_path": runtime_config.get("live_order_path") or plan.venue_order_path,
                "venue_order_cancel_path": runtime_config.get("cancel_order_path") or plan.venue_order_cancel_path,
            },
        )
        readiness_evidence = _merge_evidence_dict(
            base_readiness_evidence,
            runtime_config.get("readiness_evidence"),
            {
                "allowed": bool(plan.allowed),
                "live_execution_supported": plan.live_execution_supported,
                "bounded_execution_supported": plan.bounded_execution_supported,
                "market_execution_supported": plan.market_execution_supported,
                "live_transport_bound": live_transport_bound,
                "live_cancellation_bound": live_cancellation_bound,
                "transport_bound": transport_bound,
                "runtime_ready": runtime_ready,
                "ready_for_live_execution": ready_for_live_execution,
            },
        )
        for key, value in {
            "live_transport_bound": live_transport_bound,
            "live_cancellation_bound": live_cancellation_bound,
            "transport_bound": transport_bound,
            "runtime_ready": runtime_ready,
            "ready_for_live_execution": ready_for_live_execution,
        }.items():
            if key not in base_readiness_evidence:
                readiness_evidence[key] = value
        runtime_metadata = _merge_evidence_dict(
            plan.metadata,
            {
                "execution_runtime_config": runtime_config,
                "credential_evidence": credential_evidence,
                "configuration_evidence": configuration_evidence,
                "readiness_evidence": readiness_evidence,
                "requested_backend_mode": runtime_config.get("requested_backend_mode", self.backend_mode),
                "selected_backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "runtime_ready": runtime_ready,
                "ready_for_live_execution": ready_for_live_execution,
                "mock_transport": runtime_config.get("mock_transport", False),
                "auth_configured": runtime_config.get("auth_configured", False),
                "auth_scheme": runtime_config.get("auth_scheme", "bearer"),
                "missing_requirements": list(runtime_config.get("missing_requirements", [])),
                "readiness_notes": list(runtime_config.get("readiness_notes", [])),
                "order_sources": runtime_config.get("order_sources", {}),
                "transport_bound": transport_bound,
                "live_transport_bound": live_transport_bound,
                "cancellation_bound": live_cancellation_bound,
            },
        )
        runtime_blocked = bool((not dry_run) and not ready_for_live_execution)
        blocked_reasons = list(plan.blocked_reasons)
        if runtime_blocked and "polymarket_live_not_ready" not in blocked_reasons:
            blocked_reasons.append("polymarket_live_not_ready")
        if runtime_blocked:
            for item in runtime_config.get("missing_requirements", []):
                reason = f"polymarket_missing:{item}"
                if reason not in blocked_reasons:
                    blocked_reasons.append(reason)
        return plan.model_copy(
            update={
                "backend_mode": runtime_config.get("selected_backend_mode", self.backend_mode),
                "venue_order_path": runtime_config.get("live_order_path") or plan.venue_order_path,
                "venue_order_cancel_path": runtime_config.get("cancel_order_path") or plan.venue_order_cancel_path,
                "allowed": plan.allowed and not runtime_blocked,
                "blocked_reasons": blocked_reasons,
                "credential_evidence": credential_evidence,
                "configuration_evidence": configuration_evidence,
                "readiness_evidence": readiness_evidence,
                "metadata": {**runtime_metadata, "runtime_blocked": runtime_blocked},
            }
        )

    def _venue_transport(self) -> VenueOrderTransport:
        from .polymarket import PolymarketExecutionAdapter as VenuePolymarketExecutionAdapter

        return VenuePolymarketExecutionAdapter(
            backend_mode=self.backend_mode,
            order_submitter=getattr(self, "order_submitter", None),
            cancel_submitter=getattr(self, "cancel_submitter", None),
        )

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        request = _coerce_clob_place_order_request(*args, **kwargs)
        return self._venue_transport().place_order(
            market=request.market,
            run_id=request.run_id,
            position_side=request.position_side,
            execution_side=request.execution_side,
            requested_quantity=request.requested_quantity,
            requested_notional=request.requested_notional,
            limit_price=request.limit_price,
            dry_run=request.dry_run,
            allow_live_execution=request.allow_live_execution,
            authorized=request.authorized,
            compliance_approved=request.compliance_approved,
            required_scope=request.required_scope,
            scopes=list(request.scopes),
            metadata=dict(request.metadata),
        )

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        request = _coerce_clob_cancel_order_request(*args, **kwargs)
        return self._venue_transport().cancel_order(
            request.order,
            reason=request.reason,
            cancelled_by=request.cancelled_by,
            metadata=dict(request.metadata),
        )


@dataclass
class KalshiExecutionAdapter(VenueExecutionAdapterBase):
    venue: VenueName = VenueName.kalshi


@dataclass
class GenericExecutionAdapter(VenueExecutionAdapterBase):
    pass


def build_execution_adapter(venue: VenueName, *, backend_mode: str = "auto") -> ExecutionAdapter:
    if venue == VenueName.polymarket:
        return PolymarketExecutionAdapter(backend_mode=backend_mode)
    if venue == VenueName.kalshi:
        return KalshiExecutionAdapter(backend_mode=backend_mode)
    return GenericExecutionAdapter(venue=venue, backend_mode=backend_mode)


def bind_venue_order_transport(
    adapter: Any,
    *,
    transport: VenueOrderCallbackTransport | None = None,
    order_submitter: Callable[[MarketExecutionOrder, dict[str, Any]], Any] | None = None,
    cancel_submitter: Callable[[MarketExecutionOrder, dict[str, Any]], Any] | None = None,
    submission_receipt_builder: Callable[[MarketExecutionOrder, dict[str, Any]], dict[str, Any]] | None = None,
    cancellation_receipt_builder: Callable[[MarketExecutionOrder, dict[str, Any]], dict[str, Any]] | None = None,
) -> Any:
    """Attach optional live order callbacks to an execution adapter.

    The helper is intentionally permissive so live orchestration can keep a
    single binding path across Polymarket/Kalshi-style adapters without
    depending on a concrete subclass.
    """

    resolved_order_submitter = order_submitter
    resolved_cancel_submitter = cancel_submitter
    if transport is not None:
        resolved_order_submitter = resolved_order_submitter or transport.place_order
        resolved_cancel_submitter = resolved_cancel_submitter or transport.cancel_order

    if resolved_order_submitter is not None:
        setattr(adapter, "order_submitter", resolved_order_submitter)
    if resolved_cancel_submitter is not None:
        setattr(adapter, "cancel_submitter", resolved_cancel_submitter)
    if submission_receipt_builder is not None:
        setattr(adapter, "submission_receipt_builder", submission_receipt_builder)
    if cancellation_receipt_builder is not None:
        setattr(adapter, "cancellation_receipt_builder", cancellation_receipt_builder)
    setattr(adapter, "venue_live_submission_bound", bool(resolved_order_submitter))
    setattr(adapter, "venue_live_cancellation_bound", bool(resolved_cancel_submitter))
    return adapter


def build_venue_order_submission_receipt(
    *,
    lifecycle: VenueOrderLifecycle | Mapping[str, Any],
    submitted_payload: Any | None = None,
    transport_mode: str = "dry_run",
    runtime_honest_mode: str = "dry_run",
    attempted_live: bool = False,
    live_submission_performed: bool = False,
    live_submission_phase: str = "dry_run",
    submission_error_type: str | None = None,
    live_submission_bound: bool = False,
    blocked_reasons: Iterable[str] | None = None,
) -> dict[str, Any]:
    lifecycle_payload = lifecycle.model_dump(mode="json") if isinstance(lifecycle, VenueOrderLifecycle) else dict(lifecycle)
    history = list(lifecycle_payload.get("venue_order_status_history") or [])
    submitted_payload_hash = None
    if submitted_payload is not None:
        try:
            submitted_payload_hash = _stable_content_hash(submitted_payload)[:12]
        except Exception:  # pragma: no cover - defensive hashing
            submitted_payload_hash = None
    return {
        "schema_version": "v1",
        "receipt_source": "venue_order_submission",
        "transport_mode": transport_mode,
        "runtime_honest_mode": runtime_honest_mode,
        "attempted_live": bool(attempted_live),
        "live_submission_performed": bool(live_submission_performed),
        "live_submission_phase": live_submission_phase,
        "submission_error_type": submission_error_type,
        "venue_live_submission_bound": bool(live_submission_bound),
        "operator_bound": bool(live_submission_bound),
        "venue_order_id": lifecycle_payload.get("venue_order_id"),
        "venue_order_status": lifecycle_payload.get("venue_order_status"),
        "venue_order_source": lifecycle_payload.get("venue_order_source"),
        "venue_order_submission_state": lifecycle_payload.get("venue_order_submission_state", "simulated"),
        "venue_order_ack_state": lifecycle_payload.get("venue_order_ack_state", "not_acknowledged"),
        "venue_order_cancel_state": lifecycle_payload.get("venue_order_cancel_state", "not_cancelled"),
        "venue_order_execution_state": lifecycle_payload.get("venue_order_execution_state", "simulated"),
        "venue_order_trace_kind": lifecycle_payload.get("venue_order_trace_kind"),
        "venue_order_path": lifecycle_payload.get("venue_order_path"),
        "venue_order_ack_path": lifecycle_payload.get("venue_order_ack_path"),
        "venue_order_cancel_path": lifecycle_payload.get("venue_order_cancel_path"),
        "venue_order_status_history": history,
        "submitted_payload_present": submitted_payload is not None,
        "submitted_payload_hash": submitted_payload_hash,
        "acknowledged": bool(
            lifecycle_payload.get("venue_order_acknowledged_at")
            or lifecycle_payload.get("venue_order_acknowledged_by")
            or lifecycle_payload.get("venue_order_acknowledged_reason")
            or "acknowledged" in history
        ),
        "cancel_observed": bool(
            lifecycle_payload.get("venue_order_cancelled_at")
            or lifecycle_payload.get("venue_order_cancelled_by")
            or lifecycle_payload.get("venue_order_cancel_reason")
            or "cancelled" in history
        ),
        "blocked_reasons": list(blocked_reasons or []),
    }


def build_venue_order_cancellation_receipt(
    *,
    lifecycle: VenueOrderLifecycle | Mapping[str, Any],
    cancelled_payload: Any | None = None,
    transport_mode: str = "dry_run",
    runtime_honest_mode: str = "dry_run",
    attempted_live: bool = False,
    live_submission_performed: bool = False,
    cancellation_performed: bool = False,
    cancellation_phase: str = "dry_run",
    cancellation_error_type: str | None = None,
    live_cancellation_bound: bool = False,
    blocked_reasons: Iterable[str] | None = None,
) -> dict[str, Any]:
    lifecycle_payload = lifecycle.model_dump(mode="json") if isinstance(lifecycle, VenueOrderLifecycle) else dict(lifecycle)
    history = list(lifecycle_payload.get("venue_order_status_history") or [])
    cancelled_payload_hash = None
    if cancelled_payload is not None:
        try:
            cancelled_payload_hash = _stable_content_hash(cancelled_payload)[:12]
        except Exception:  # pragma: no cover - defensive hashing
            cancelled_payload_hash = None
    return {
        "schema_version": "v1",
        "receipt_source": "venue_order_cancellation",
        "transport_mode": transport_mode,
        "runtime_honest_mode": runtime_honest_mode,
        "attempted_live": bool(attempted_live),
        "live_submission_performed": bool(live_submission_performed),
        "cancellation_performed": bool(cancellation_performed),
        "cancellation_phase": cancellation_phase,
        "cancellation_error_type": cancellation_error_type,
        "venue_live_cancellation_bound": bool(live_cancellation_bound),
        "operator_bound": bool(live_cancellation_bound),
        "venue_order_id": lifecycle_payload.get("venue_order_id"),
        "venue_order_status": lifecycle_payload.get("venue_order_status"),
        "venue_order_source": lifecycle_payload.get("venue_order_source"),
        "venue_order_submission_state": lifecycle_payload.get("venue_order_submission_state", "simulated"),
        "venue_order_ack_state": lifecycle_payload.get("venue_order_ack_state", "not_acknowledged"),
        "venue_order_cancel_state": lifecycle_payload.get("venue_order_cancel_state", "not_cancelled"),
        "venue_order_execution_state": lifecycle_payload.get("venue_order_execution_state", "simulated"),
        "venue_order_trace_kind": lifecycle_payload.get("venue_order_trace_kind"),
        "venue_order_path": lifecycle_payload.get("venue_order_path"),
        "venue_order_ack_path": lifecycle_payload.get("venue_order_ack_path"),
        "venue_order_cancel_path": lifecycle_payload.get("venue_order_cancel_path"),
        "venue_order_status_history": history,
        "cancelled_payload_present": cancelled_payload is not None,
        "cancelled_payload_hash": cancelled_payload_hash,
        "cancel_observed": bool(
            lifecycle_payload.get("venue_order_cancelled_at")
            or lifecycle_payload.get("venue_order_cancelled_by")
            or lifecycle_payload.get("venue_order_cancel_reason")
            or "cancelled" in history
        ),
        "acknowledged": bool(
            lifecycle_payload.get("venue_order_acknowledged_at")
            or lifecycle_payload.get("venue_order_acknowledged_by")
            or lifecycle_payload.get("venue_order_acknowledged_reason")
            or "acknowledged" in history
        ),
        "blocked_reasons": list(blocked_reasons or []),
    }


def _coerce_clob_place_order_request(*args: Any, **kwargs: Any) -> ClobPlaceOrderRequest:
    if len(args) > 1:
        raise TypeError("place_order accepts either one structured request or keyword fields")
    if args:
        if kwargs:
            raise TypeError("place_order does not accept both a structured request and keyword fields")
        request = args[0]
        if isinstance(request, ClobPlaceOrderRequest):
            return request
        raise TypeError("place_order positional argument must be a ClobPlaceOrderRequest")
    return ClobPlaceOrderRequest.model_validate(kwargs)


def _coerce_clob_cancel_order_request(*args: Any, **kwargs: Any) -> ClobCancelOrderRequest:
    if len(args) > 1:
        raise TypeError("cancel_order accepts either one structured request or one order plus keyword fields")
    if args:
        request = args[0]
        if isinstance(request, ClobCancelOrderRequest):
            if kwargs:
                raise TypeError("cancel_order does not accept keyword fields with a structured request")
            return request
        if isinstance(request, MarketExecutionOrder):
            return ClobCancelOrderRequest.model_validate(
                {
                    "order": request,
                    **kwargs,
                }
            )
        raise TypeError("cancel_order positional argument must be a ClobCancelOrderRequest or MarketExecutionOrder")
    return ClobCancelOrderRequest.model_validate(kwargs)


@dataclass
class VenueMarketExecutionAdapterBase:
    venue: VenueName
    backend_mode: str = "auto"
    execution_registry: VenueExecutionRegistry = field(default_factory=lambda: DEFAULT_VENUE_EXECUTION_REGISTRY)
    execution_engine: BoundedMarketExecutionEngine = field(default_factory=BoundedMarketExecutionEngine)

    def describe_market_execution_capabilities(self) -> VenueExecutionCapability:
        return self.execution_registry.capability_for(self.venue).model_copy(deep=True)

    def execute_bounded(self, request: MarketExecutionRequest) -> MarketExecutionRecord:
        capability = self.describe_market_execution_capabilities()
        record = self.execution_engine.execute(
            request,
            capability=capability.model_dump(mode="json"),
            execution_plan={"backend_mode": self.backend_mode, "venue": self.venue.value},
        )
        lifecycle = build_venue_order_lifecycle(
            order_id=record.order.order_id,
            execution_id=record.execution_id,
            request_metadata=dict(request.metadata or {}),
            status=getattr(record.status, "value", str(record.status)),
            cancelled_reason=record.cancelled_reason,
            live_execution_supported=bool(capability.live_execution_supported),
            venue_order_path=capability.bounded_order_path or capability.live_order_path or "unavailable",
            venue_order_cancel_path=capability.cancel_order_path or capability.bounded_order_path or capability.live_order_path or "unavailable",
        )
        _apply_venue_order_lifecycle(record, lifecycle)
        return record


@dataclass
class PolymarketMarketExecutionAdapter(VenueMarketExecutionAdapterBase):
    venue: VenueName = VenueName.polymarket


@dataclass
class KalshiMarketExecutionAdapter(VenueMarketExecutionAdapterBase):
    venue: VenueName = VenueName.kalshi


def build_market_execution_adapter(venue: VenueName, *, backend_mode: str = "auto") -> MarketExecutionAdapter:
    if venue == VenueName.polymarket:
        return PolymarketMarketExecutionAdapter(backend_mode=backend_mode)
    if venue == VenueName.kalshi:
        return KalshiMarketExecutionAdapter(backend_mode=backend_mode)
    return VenueMarketExecutionAdapterBase(venue=venue, backend_mode=backend_mode)


def build_venue_order_lifecycle(
    *,
    order_id: str,
    execution_id: str,
    request_metadata: dict[str, Any] | None = None,
    status: str | None = None,
    acknowledged_at: datetime | str | None = None,
    acknowledged_by: str | None = None,
    acknowledged_reason: str | None = None,
    cancelled_reason: str | None = None,
    live_execution_supported: bool = False,
    venue_order_path: str | None = None,
    venue_order_cancel_path: str | None = None,
) -> VenueOrderLifecycle:
    metadata = dict(request_metadata or {})
    explicit_id = _first_text(metadata, "venue_order_id", "external_order_id", "venue_external_order_id", "order_reference")
    explicit_source = _first_text(metadata, "venue_order_source", "order_source")
    explicit_history = _parse_status_history(metadata)
    explicit_acknowledged_at = _coerce_datetime(
        metadata.get("venue_order_acknowledged_at")
        or metadata.get("acknowledged_at")
        or acknowledged_at
    )
    explicit_acknowledged_by = _first_text(metadata, "venue_order_acknowledged_by", "acknowledged_by") or acknowledged_by
    explicit_acknowledged_reason = _first_text(
        metadata,
        "venue_order_acknowledged_reason",
        "acknowledged_reason",
    ) or acknowledged_reason
    explicit_cancelled_at = _coerce_datetime(
        metadata.get("venue_order_cancelled_at")
        or metadata.get("cancelled_at")
    )
    explicit_cancelled_by = _first_text(metadata, "venue_order_cancelled_by", "cancelled_by")
    explicit_order_path = venue_order_path or _first_text(metadata, "venue_order_path", "order_path")
    explicit_cancel_path = venue_order_cancel_path or _first_text(metadata, "venue_order_cancel_path", "order_cancel_path")
    configured = explicit_id is not None
    if configured and explicit_source in {None, "", "paper_trade_simulator", "live_execution_projection", "local_surrogate"}:
        explicit_source = "external"
    elif not configured and explicit_source in {"paper_trade_simulator", "live_execution_projection"}:
        explicit_source = "local_surrogate"
    venue_order_id = explicit_id or f"venue_{execution_id}_{order_id}"
    requested_status = _first_text(metadata, "venue_order_status") or status or ("submitted" if live_execution_supported else "simulated")
    requested_status = requested_status.lower()
    if cancelled_reason:
        venue_order_status = "cancelled"
    elif requested_status in {"submitted", "acknowledged", "filled", "partial", "rejected", "cancelled"}:
        venue_order_status = requested_status
    else:
        venue_order_status = "simulated"
    if explicit_history:
        status_history = _normalize_status_history(explicit_history)
        if requested_status not in {"submitted", "simulated", "unavailable"} and requested_status not in status_history:
            status_history.append(requested_status)
        venue_order_status = status_history[-1]
    else:
        if venue_order_status == "submitted" and (
            explicit_acknowledged_at is not None
            or explicit_acknowledged_by is not None
            or explicit_acknowledged_reason is not None
        ):
            venue_order_status = "acknowledged"
        if venue_order_status == "submitted":
            status_history = ["submitted"]
        elif venue_order_status == "acknowledged":
            status_history = ["submitted", "acknowledged"]
        elif venue_order_status in {"filled", "partial", "rejected", "cancelled"}:
            status_history = ["submitted", "acknowledged", venue_order_status]
        else:
            status_history = [venue_order_status]
    if venue_order_status in {"acknowledged", "filled", "partial", "rejected", "cancelled"} and explicit_acknowledged_at is None:
        explicit_acknowledged_at = datetime.now(timezone.utc).replace(microsecond=0)
    if venue_order_status in {"filled", "partial", "rejected", "cancelled"} and not explicit_acknowledged_by:
        explicit_acknowledged_by = explicit_source or ("external" if configured else "local_surrogate")
    if venue_order_status in {"filled", "partial", "rejected", "cancelled"} and not explicit_acknowledged_reason:
        explicit_acknowledged_reason = cancelled_reason or venue_order_status
    if venue_order_status == "cancelled" and explicit_cancelled_at is None:
        explicit_cancelled_at = explicit_acknowledged_at
    if venue_order_status == "cancelled" and not explicit_cancelled_by:
        explicit_cancelled_by = explicit_acknowledged_by or explicit_source or ("external" if configured else "local_surrogate")
    venue_order_submission_state = "venue_submitted" if venue_order_status != "simulated" and (configured or live_execution_supported) else "simulated"
    venue_order_ack_state = (
        "venue_acknowledged"
        if any(
            [
                explicit_acknowledged_at is not None,
                explicit_acknowledged_by is not None,
                explicit_acknowledged_reason is not None,
                "acknowledged" in status_history,
                venue_order_status in {"acknowledged", "filled", "partial", "rejected", "cancelled"},
            ]
        )
        else "not_acknowledged"
    )
    venue_order_cancel_state = (
        "venue_cancelled"
        if any(
            [
                cancelled_reason is not None,
                explicit_cancelled_at is not None,
                explicit_cancelled_by is not None,
                venue_order_status == "cancelled",
                "cancelled" in status_history,
            ]
        )
        else "not_cancelled"
    )
    if venue_order_cancel_state == "venue_cancelled":
        venue_order_execution_state = "venue_cancelled"
    elif venue_order_ack_state == "venue_acknowledged":
        venue_order_execution_state = "venue_acknowledged"
    elif venue_order_submission_state == "venue_submitted":
        venue_order_execution_state = "venue_submitted"
    else:
        venue_order_execution_state = "simulated"
    trace_kind = _venue_order_trace_kind(configured=configured, live_execution_supported=live_execution_supported)
    venue_order_source = explicit_source or ("external" if configured else "local_surrogate")
    return VenueOrderLifecycle(
        venue_order_id=venue_order_id,
        venue_order_status=venue_order_status,
        venue_order_source=venue_order_source,
        venue_order_submission_state=venue_order_submission_state,
        venue_order_ack_state=venue_order_ack_state,
        venue_order_cancel_state=venue_order_cancel_state,
        venue_order_execution_state=venue_order_execution_state,
        venue_order_status_history=status_history,
        venue_order_acknowledged_at=explicit_acknowledged_at,
        venue_order_acknowledged_by=explicit_acknowledged_by,
        venue_order_acknowledged_reason=explicit_acknowledged_reason,
        venue_order_cancel_reason=cancelled_reason,
        venue_order_cancelled_at=explicit_cancelled_at,
        venue_order_cancelled_by=explicit_cancelled_by,
        venue_order_path=explicit_order_path or ("external_live_api" if live_execution_supported else "external_bounded_api"),
        venue_order_cancel_path=explicit_cancel_path or ("external_live_cancel_api" if live_execution_supported else "external_bounded_cancel_api"),
        venue_order_configured=configured,
        live_execution_supported=live_execution_supported,
        venue_order_trace_kind=trace_kind,
        venue_order_flow="->".join(status_history),
        metadata={
            **metadata,
            "order_id": order_id,
            "execution_id": execution_id,
            "venue_order_configured": configured,
            "venue_order_submission_state": venue_order_submission_state,
            "venue_order_ack_state": venue_order_ack_state,
            "venue_order_cancel_state": venue_order_cancel_state,
            "venue_order_execution_state": venue_order_execution_state,
            "venue_order_status_history": list(status_history),
            "venue_order_flow": "->".join(status_history),
            "venue_order_trace_kind": trace_kind,
            "venue_order_path": explicit_order_path or ("external_live_api" if live_execution_supported else "external_bounded_api"),
            "venue_order_cancel_path": explicit_cancel_path or ("external_live_cancel_api" if live_execution_supported else "external_bounded_cancel_api"),
        },
    )


def _apply_venue_order_lifecycle(record: MarketExecutionRecord, lifecycle: VenueOrderLifecycle) -> None:
    record.order.metadata = {
        **dict(record.order.metadata or {}),
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
        "venue_order_configured": lifecycle.venue_order_configured,
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
        "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
        "venue_order_flow": lifecycle.venue_order_flow,
    }
    record.order.status = lifecycle.venue_order_status
    record.order.acknowledged_at = lifecycle.venue_order_acknowledged_at
    record.order.acknowledged_by = lifecycle.venue_order_acknowledged_by
    record.order.acknowledged_reason = lifecycle.venue_order_acknowledged_reason
    record.order.cancelled_at = lifecycle.venue_order_cancelled_at
    record.order.cancelled_by = lifecycle.venue_order_cancelled_by
    record.order.cancelled_reason = lifecycle.venue_order_cancel_reason
    record.metadata = {
        **dict(record.metadata or {}),
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
        "venue_order_configured": lifecycle.venue_order_configured,
        "venue_order_path": lifecycle.venue_order_path,
        "venue_order_cancel_path": lifecycle.venue_order_cancel_path,
        "venue_order_trace_kind": lifecycle.venue_order_trace_kind,
        "venue_order_flow": lifecycle.venue_order_flow,
        "venue_order_lifecycle": lifecycle.model_dump(mode="json"),
    }


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _parse_status_history(metadata: dict[str, Any]) -> list[str]:
    raw_history = metadata.get("venue_order_status_history") or metadata.get("status_history") or metadata.get("order_status_history")
    if raw_history is None:
        return []
    if isinstance(raw_history, str):
        candidates = raw_history.replace(";", ",").split(",")
    elif isinstance(raw_history, (list, tuple, set, frozenset)):
        candidates = list(raw_history)
    else:
        candidates = [raw_history]
    history: list[str] = []
    for candidate in candidates:
        text = str(candidate).strip().lower()
        if text and text not in history:
            history.append(text)
    return history


def _normalize_status_history(history: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in history:
        text = str(value).strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    if not normalized:
        return []
    if normalized[0] != "submitted" and normalized[0] != "simulated":
        normalized.insert(0, "submitted")
    return normalized


def _venue_order_trace_kind(*, configured: bool, live_execution_supported: bool) -> str:
    if configured and live_execution_supported:
        return "external_live"
    if configured and not live_execution_supported:
        return "external_surrogate"
    if not configured and live_execution_supported:
        return "local_live"
    return "local_surrogate"
