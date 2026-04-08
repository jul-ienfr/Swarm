from __future__ import annotations

import os
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from statistics import mean
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from websockets.sync.client import connect as websocket_connect

from .models import LedgerPosition, MarketDescriptor, MarketSnapshot, VenueName, _safe_non_negative_float
from .paths import PredictionMarketPaths, default_prediction_market_paths
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY
from .polymarket import build_polymarket_client
from .storage import ensure_storage_layout


class StreamEventKind(str, Enum):
    snapshot = "snapshot"
    change = "change"


class MarketStreamEvent(BaseModel):
    schema_version: str = "v1"
    stream_id: str
    market_id: str
    venue: VenueName
    sequence: int
    kind: StreamEventKind = StreamEventKind.snapshot
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot: MarketSnapshot
    changed_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketStreamManifest(BaseModel):
    schema_version: str = "v1"
    stream_id: str
    market_id: str
    venue: VenueName
    market_title: str = ""
    market_slug: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    poll_count: int = 0
    event_count: int = 0
    latest_sequence: int = 0
    latest_snapshot_id: str | None = None
    latest_snapshot_path: str | None = None
    events_path: str | None = None
    snapshot_path: str | None = None
    data_surface_runbook: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class MarketStreamSummary(BaseModel):
    schema_version: str = "v1"
    stream_id: str
    market_id: str
    venue: VenueName
    market_title: str = ""
    market_slug: str | None = None
    event_count: int = 0
    poll_count: int = 0
    change_event_count: int = 0
    change_rate: float = 0.0
    latest_sequence: int = 0
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    age_seconds: float | None = None
    price_yes_start: float | None = None
    price_yes_end: float | None = None
    price_yes_change: float | None = None
    spread_bps_start: float | None = None
    spread_bps_end: float | None = None
    spread_bps_change: float | None = None
    average_price_yes: float | None = None
    average_spread_bps: float | None = None
    trend: str = "stable"
    narrative: str = ""
    changed_field_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketStreamHealth(BaseModel):
    schema_version: str = "v1"
    stream_id: str
    market_id: str
    venue: VenueName
    healthy: bool = True
    stream_status: str = "healthy"
    freshness_status: str = "fresh"
    message: str = "healthy"
    issues: list[str] = Field(default_factory=list)
    issue_count: int = 0
    maintenance_mode: bool = False
    desync_detected: bool = False
    supports_websocket: bool = False
    supports_rtds: bool = False
    websocket_status: str = "unavailable"
    rtds_status: str = "unavailable"
    market_websocket_status: str = "unavailable"
    user_feed_websocket_status: str = "unavailable"
    market_feed_status: str = "unavailable"
    user_feed_status: str = "unavailable"
    market_feed_replayable: bool = False
    user_feed_replayable: bool = False
    rtds_replayable: bool = False
    latest_sequence: int = 0
    event_count: int = 0
    poll_count: int = 0
    age_seconds: float | None = None
    latest_snapshot_id: str | None = None
    latest_snapshot_status: str | None = None
    snapshot_freshness_ms: float | None = None
    health_score: float = 1.0
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    feed_surface_degraded: bool = False
    feed_surface_degraded_reasons: list[str] = Field(default_factory=list)
    backend_mode: str = "unknown"
    last_observed_at: datetime | None = None
    feed_surface: MarketFeedSurface | None = None
    feed_surface_status: str = "read_only"
    feed_surface_summary: str = ""
    route_refs: dict[str, str] = Field(default_factory=dict)
    availability_probes: dict[str, Any] = Field(default_factory=dict)
    cache_fallbacks: dict[str, Any] = Field(default_factory=dict)
    subscription_preview: dict[str, Any] = Field(default_factory=dict)
    probe_bundle: dict[str, Any] = Field(default_factory=dict)
    capability_summary: dict[str, Any] = Field(default_factory=dict)
    connector_contracts: dict[str, Any] = Field(default_factory=dict)
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VenueHealthMonitorReport(BaseModel):
    schema_version: str = "v1"
    monitor_id: str = Field(default_factory=lambda: f"vhm_{uuid4().hex[:12]}")
    venue: VenueName | None = None
    stream_count: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    maintenance_count: int = 0
    desync_count: int = 0
    stale_count: int = 0
    avg_health_score: float | None = None
    p95_health_score: float | None = None
    latest_health: MarketStreamHealth | None = None
    recovered: bool = False
    recovery_required: bool = False
    summary: str = ""
    supports_websocket: bool = False
    supports_rtds: bool = False
    websocket_status: str = "unavailable"
    rtds_status: str = "unavailable"
    market_websocket_status: str = "unavailable"
    user_feed_websocket_status: str = "unavailable"
    market_feed_status: str = "unavailable"
    user_feed_status: str = "unavailable"
    market_feed_replayable: bool = False
    user_feed_replayable: bool = False
    rtds_replayable: bool = False
    feed_surface_status: str = "read_only"
    feed_surface_summary: str = ""
    route_refs: dict[str, str] = Field(default_factory=dict)
    availability_probes: dict[str, Any] = Field(default_factory=dict)
    cache_fallbacks: dict[str, Any] = Field(default_factory=dict)
    subscription_preview: dict[str, Any] = Field(default_factory=dict)
    probe_bundle: dict[str, Any] = Field(default_factory=dict)
    capability_summary: dict[str, Any] = Field(default_factory=dict)
    connector_contracts: dict[str, Any] = Field(default_factory=dict)
    incident_runbook: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedTransport(str, Enum):
    unknown = "unknown"
    http_json = "http_json"
    local_cache = "local_cache"
    fixture_cache = "fixture_cache"
    surrogate_snapshot = "surrogate_snapshot"
    unavailable = "unavailable"


def _env_truthy(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _normalized_optional_text(value: Any) -> str | None:
    text = " ".join(str(value).strip().split())
    return text or None


def _maybe_ws_url(value: Any) -> str | None:
    text = _normalized_optional_text(value)
    if not text:
        return None
    return text.removesuffix("/")


def _descriptor_condition_id(descriptor: MarketDescriptor) -> str:
    metadata = dict(getattr(descriptor, "metadata", {}) or {})
    raw = dict(getattr(descriptor, "raw", {}) or {})
    return _normalized_optional_text(
        metadata.get("condition_id")
        or metadata.get("conditionId")
        or raw.get("condition_id")
        or raw.get("conditionId")
        or raw.get("conditionID")
        or descriptor.canonical_event_id
        or descriptor.event_id
        or descriptor.market_id
    ) or descriptor.market_id


def _descriptor_token_ids(descriptor: MarketDescriptor) -> list[str]:
    token_ids = list(descriptor.token_ids or [])
    if token_ids:
        return token_ids
    metadata = dict(getattr(descriptor, "metadata", {}) or {})
    raw = dict(getattr(descriptor, "raw", {}) or {})
    for source in (metadata, raw):
        if not isinstance(source, dict):
            continue
        value = source.get("clobTokenIds") or source.get("token_ids") or source.get("tokenIds")
        if isinstance(value, list):
            token_ids = [str(item).strip() for item in value if _normalized_optional_text(item)]
            if token_ids:
                return token_ids
    return []


@dataclass(frozen=True)
class PolymarketLiveWebsocketBinding:
    market_websocket_url: str | None = None
    user_websocket_url: str | None = None
    rtds_url: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None
    gamma_auth_address: str | None = None
    heartbeat_seconds: float = 10.0
    open_timeout_seconds: float = 5.0
    recv_timeout_seconds: float = 5.0

    @property
    def user_auth_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    @property
    def live_enabled(self) -> bool:
        return bool(self.market_websocket_url or self.user_websocket_url or self.rtds_url)

    @classmethod
    def from_env(cls) -> "PolymarketLiveWebsocketBinding | None":
        enabled = _env_truthy("PREDICTION_MARKETS_ENABLE_LIVE_WEBSOCKETS")
        market_websocket_url = _maybe_ws_url(
            os.getenv("POLYMARKET_MARKET_WEBSOCKET_URL")
            or ( "wss://ws-subscriptions-clob.polymarket.com/ws/market" if enabled else None)
        )
        user_websocket_url = _maybe_ws_url(
            os.getenv("POLYMARKET_USER_WEBSOCKET_URL")
            or ( "wss://ws-subscriptions-clob.polymarket.com/ws/user" if enabled else None)
        )
        rtds_url = _maybe_ws_url(
            os.getenv("POLYMARKET_RTDS_URL")
            or ( "wss://ws-live-data.polymarket.com" if enabled else None)
        )
        if not enabled:
            return None
        if not any((market_websocket_url, user_websocket_url, rtds_url)):
            return None
        api_key = _normalized_optional_text(os.getenv("POLYMARKET_WS_API_KEY"))
        api_secret = _normalized_optional_text(os.getenv("POLYMARKET_WS_API_SECRET"))
        api_passphrase = _normalized_optional_text(os.getenv("POLYMARKET_WS_API_PASSPHRASE"))
        gamma_auth_address = _normalized_optional_text(
            os.getenv("POLYMARKET_RTDS_GAMMA_AUTH")
            or os.getenv("POLYMARKET_GAMMA_AUTH_ADDRESS")
            or os.getenv("POLYMARKET_WALLET_ADDRESS")
        )
        return cls(
            market_websocket_url=market_websocket_url,
            user_websocket_url=user_websocket_url,
            rtds_url=rtds_url,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            gamma_auth_address=gamma_auth_address,
            heartbeat_seconds=float(os.getenv("POLYMARKET_WEBSOCKET_HEARTBEAT_SECONDS", "10")),
            open_timeout_seconds=float(os.getenv("POLYMARKET_WEBSOCKET_OPEN_TIMEOUT_SECONDS", "5")),
            recv_timeout_seconds=float(os.getenv("POLYMARKET_WEBSOCKET_RECV_TIMEOUT_SECONDS", "5")),
        )


@dataclass(frozen=True)
class PolymarketLiveWebsocketRuntime:
    binding: PolymarketLiveWebsocketBinding

    @classmethod
    def from_env(cls) -> "PolymarketLiveWebsocketRuntime | None":
        binding = PolymarketLiveWebsocketBinding.from_env()
        if binding is None:
            return None
        return cls(binding=binding)

    def describe_live_binding(self) -> dict[str, Any]:
        binding = self.binding
        return {
            "market_websocket_url": binding.market_websocket_url,
            "user_websocket_url": binding.user_websocket_url,
            "rtds_url": binding.rtds_url,
            "user_auth_configured": binding.user_auth_configured,
            "gamma_auth_configured": bool(binding.gamma_auth_address),
            "heartbeat_seconds": binding.heartbeat_seconds,
            "open_timeout_seconds": binding.open_timeout_seconds,
            "recv_timeout_seconds": binding.recv_timeout_seconds,
            "live_enabled": binding.live_enabled,
        }

    def market_subscription_payload(self, descriptor: MarketDescriptor) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "market",
            "operation": "subscribe",
            "custom_feature_enabled": True,
            "assets_ids": _descriptor_token_ids(descriptor),
        }
        condition_id = _descriptor_condition_id(descriptor)
        if condition_id:
            payload["condition_id"] = condition_id
            payload["markets"] = [condition_id]
        return payload

    def user_subscription_payload(self, descriptor: MarketDescriptor) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "user",
            "operation": "subscribe",
            "markets": [_descriptor_condition_id(descriptor)],
        }
        if self.binding.user_auth_configured:
            payload["auth"] = {
                "apiKey": self.binding.api_key,
                "secret": self.binding.api_secret,
                "passphrase": self.binding.api_passphrase,
            }
        return payload

    def rtds_subscription_payload(
        self,
        *,
        topics: list[str] | None = None,
        message_type: str = "update",
        filters: str | None = None,
    ) -> dict[str, Any]:
        subscriptions: list[dict[str, Any]] = []
        for topic in topics or ["comments"]:
            item: dict[str, Any] = {
                "topic": topic,
                "type": message_type,
            }
            if filters:
                item["filters"] = filters
            if self.binding.gamma_auth_address:
                item["gamma_auth"] = {"address": self.binding.gamma_auth_address}
            subscriptions.append(item)
        return {
            "action": "subscribe",
            "subscriptions": subscriptions,
        }

    def _probe(self, url: str, subscription_payload: dict[str, Any], *, heartbeat_payload: str | None = "PING") -> dict[str, Any]:
        if not url:
            return {
                "status": "unavailable",
                "connected": False,
                "subscription_sent": False,
                "heartbeat_sent": False,
                "message_count": 0,
                "messages": [],
                "error": "missing_url",
            }
        try:
            with websocket_connect(
                url,
                open_timeout=self.binding.open_timeout_seconds,
                ping_interval=None,
                close_timeout=self.binding.open_timeout_seconds,
                proxy=None,
            ) as connection:
                connection.send(json.dumps(subscription_payload))
                heartbeat_sent = False
                if heartbeat_payload is not None:
                    try:
                        connection.send(heartbeat_payload)
                        heartbeat_sent = True
                    except Exception:
                        heartbeat_sent = False
                messages: list[Any] = []
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(connection.recv)
                        raw_message = future.result(timeout=self.binding.recv_timeout_seconds)
                        messages.append(_maybe_json_loads(raw_message))
                except FuturesTimeoutError:
                    pass
                except Exception as exc:
                    return {
                        "status": "degraded",
                        "connected": True,
                        "subscription_sent": True,
                        "heartbeat_sent": heartbeat_sent,
                        "message_count": len(messages),
                        "messages": messages,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                return {
                    "status": "ready",
                    "connected": True,
                    "subscription_sent": True,
                    "heartbeat_sent": heartbeat_sent,
                    "message_count": len(messages),
                    "messages": messages,
                    "subscription_payload": subscription_payload,
                }
        except Exception as exc:
            return {
                "status": "unavailable",
                "connected": False,
                "subscription_sent": False,
                "heartbeat_sent": False,
                "message_count": 0,
                "messages": [],
                "error": type(exc).__name__,
                "message": str(exc),
            }

    def probe_market(self, descriptor: MarketDescriptor) -> dict[str, Any]:
        return self._probe(self.binding.market_websocket_url or "", self.market_subscription_payload(descriptor))

    def probe_user(self, descriptor: MarketDescriptor) -> dict[str, Any]:
        return self._probe(self.binding.user_websocket_url or "", self.user_subscription_payload(descriptor))

    def probe_rtds(self, *, topics: list[str] | None = None, filters: str | None = None) -> dict[str, Any]:
        return self._probe(self.binding.rtds_url or "", self.rtds_subscription_payload(topics=topics, filters=filters))


def _maybe_json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _apply_live_websocket_binding(data: dict[str, Any]) -> dict[str, Any]:
    backend_mode = str(data.get("backend_mode", "unknown")).strip().lower()
    existing_binding = dict(data.get("live_websocket_binding") or {})
    metadata = dict(data.get("metadata") or {})
    allow_live_binding = bool(
        data.get("allow_live_websocket_binding")
        or metadata.get("allow_live_websocket_binding")
    )
    existing_live_bound = bool(
        existing_binding.get("market_websocket_url")
        or existing_binding.get("user_websocket_url")
        or existing_binding.get("rtds_url")
    )
    if backend_mode != "live" and not existing_live_bound and not allow_live_binding:
        return data
    runtime = PolymarketLiveWebsocketRuntime.from_env()
    if runtime is None:
        return data
    binding = runtime.binding
    live_binding = runtime.describe_live_binding()
    data["live_websocket_binding"] = live_binding
    data["supports_websocket"] = True
    data["supports_rtds"] = bool(binding.rtds_url)
    data["live_streaming"] = True
    data["websocket_status"] = "ready" if binding.market_websocket_url or binding.user_websocket_url or binding.rtds_url else "unavailable"
    data["market_websocket_status"] = "ready" if binding.market_websocket_url else "unavailable"
    data["user_feed_websocket_status"] = "ready" if binding.user_websocket_url and binding.user_auth_configured else ("auth_required" if binding.user_websocket_url else "unavailable")
    data["rtds_status"] = "ready" if binding.rtds_url else "unavailable"
    if binding.market_websocket_url:
        data["market_websocket_connector"] = "polymarket_market_websocket"
    if binding.user_websocket_url:
        data["user_websocket_connector"] = "polymarket_user_websocket"
    if binding.rtds_url:
        data["rtds_connector"] = "polymarket_rtds_websocket"
    configured_endpoints = dict(data.get("configured_endpoints") or {})
    if binding.market_websocket_url:
        configured_endpoints["market_websocket"] = binding.market_websocket_url
    if binding.user_websocket_url:
        configured_endpoints["user_websocket"] = binding.user_websocket_url
    if binding.rtds_url:
        configured_endpoints["rtds"] = binding.rtds_url
    data["configured_endpoints"] = configured_endpoints
    route_refs = dict(data.get("route_refs") or {})
    route_refs.update(configured_endpoints)
    data["route_refs"] = route_refs
    notes = list(data.get("notes") or [])
    for note in (
        "live_websocket_market_bound" if binding.market_websocket_url else None,
        "live_websocket_user_bound" if binding.user_websocket_url else None,
        "live_rtds_bound" if binding.rtds_url else None,
        "live_user_websocket_auth_configured" if binding.user_auth_configured else None,
    ):
        if note and note not in notes:
            notes.append(note)
    data["notes"] = notes
    metadata = dict(data.get("metadata") or {})
    metadata["live_websocket_binding"] = live_binding
    data["metadata"] = metadata
    return data


class MarketFeedSurface(BaseModel):
    schema_version: str = "v1"
    venue: VenueName
    venue_type: str | None = None
    backend_mode: str = "unknown"
    ingestion_mode: str = "read_only"
    market_feed_kind: str = "market_snapshot"
    user_feed_kind: str = "position_snapshot"
    supports_discovery: bool = False
    supports_orderbook: bool = False
    supports_trades: bool = False
    supports_execution: bool = False
    supports_paper_mode: bool = False
    supports_market_feed: bool = False
    supports_user_feed: bool = False
    supports_events: bool = False
    supports_positions: bool = False
    supports_websocket: bool = False
    supports_rtds: bool = False
    live_streaming: bool = False
    websocket_status: str = "unavailable"
    market_websocket_status: str = "unavailable"
    user_feed_websocket_status: str = "unavailable"
    api_access: list[str] = Field(default_factory=list)
    supported_order_types: list[str] = Field(default_factory=list)
    rate_limit_notes: list[str] = Field(default_factory=list)
    automation_constraints: list[str] = Field(default_factory=list)
    market_feed_transport: FeedTransport = FeedTransport.unavailable
    user_feed_transport: FeedTransport = FeedTransport.unavailable
    market_feed_connector: str = "snapshot_polling"
    user_feed_connector: str = "local_position_cache"
    rtds_connector: str = "unavailable"
    market_feed_status: str = "unavailable"
    user_feed_status: str = "unavailable"
    rtds_status: str = "unavailable"
    market_feed_replayable: bool = True
    user_feed_replayable: bool = False
    rtds_replayable: bool = False
    market_feed_cache_backed: bool = False
    user_feed_cache_backed: bool = False
    rtds_cache_backed: bool = False
    events_source: str | None = None
    positions_source: str | None = None
    market_feed_source: str | None = None
    user_feed_source: str | None = None
    configured_endpoints: dict[str, str] = Field(default_factory=dict)
    route_refs: dict[str, str] = Field(default_factory=dict)
    live_websocket_binding: dict[str, Any] = Field(default_factory=dict)
    availability_probes: dict[str, Any] = Field(default_factory=dict)
    cache_fallbacks: dict[str, Any] = Field(default_factory=dict)
    subscription_preview: dict[str, Any] = Field(default_factory=dict)
    probe_bundle: dict[str, Any] = Field(default_factory=dict)
    capability_summary: dict[str, Any] = Field(default_factory=dict)
    connector_contracts: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    runbook: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    degraded: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    metadata_completeness: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


MarketStreamHealth.model_rebuild()


class StreamCollectionPriority(str, Enum):
    request_order = "request_order"
    freshness = "freshness"
    liquidity = "liquidity"
    hybrid = "hybrid"


class StreamCollectionRequest(BaseModel):
    schema_version: str = "v1"
    request_id: str = Field(default_factory=lambda: f"streamctl_{uuid4().hex[:12]}")
    market_ids: list[str] = Field(default_factory=list)
    slugs: list[str] = Field(default_factory=list)
    stream_ids: list[str] = Field(default_factory=list)
    fanout: int = 4
    retries: int = 1
    timeout_seconds: float = 5.0
    cache_ttl_seconds: float = 60.0
    prefetch: bool = True
    backpressure_limit: int = 32
    priority_strategy: StreamCollectionPriority = StreamCollectionPriority.freshness
    poll_count: int = 1
    stale_after_seconds: float = 3600.0
    backend_mode: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamCollectionMetrics(BaseModel):
    schema_version: str = "v1"
    request_id: str
    requested_target_count: int = 0
    unique_target_count: int = 0
    duplicate_target_count: int = 0
    duplicate_target_rate: float = 0.0
    requested_market_count: int = 0
    unique_market_count: int = 0
    duplicate_market_count: int = 0
    duplicate_market_rate: float = 0.0
    market_coverage_rate: float = 0.0
    coverage_gap_count: int = 0
    coverage_gap_rate: float = 0.0
    resolved_market_rate: float = 0.0
    market_coverage_by_venue: dict[str, dict[str, Any]] = Field(default_factory=dict)
    decision_latency_budget_ms: float = 0.0
    decision_latency_p50_ms: float | None = None
    decision_latency_p95_ms: float | None = None
    snapshot_freshness_mean_ms: float | None = None
    snapshot_freshness_p95_ms: float | None = None
    health_score_mean: float | None = None
    health_score_p95: float | None = None
    degraded_mode_rate: float = 0.0
    availability_by_venue: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    cache_recovery_count: int = 0
    cache_recovery_rate: float = 0.0
    cache_hit_rate: float = 0.0
    availability_rate: float = 0.0
    latency_samples_ms: list[float] = Field(default_factory=list)
    freshness_samples_ms: list[float] = Field(default_factory=list)
    health_score_samples: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketStreamCollectionCacheEntry(BaseModel):
    schema_version: str = "v1"
    cache_key: str
    target_ref: str
    market_id: str
    venue: VenueName
    stream_id: str | None = None
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_ttl_seconds: float = 60.0
    manifest: MarketStreamManifest | None = None
    summary: MarketStreamSummary
    health: MarketStreamHealth
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamCollectionItem(BaseModel):
    schema_version: str = "v1"
    target_ref: str
    target_kind: str
    market_id: str
    venue: VenueName
    stream_id: str | None = None
    cache_key: str | None = None
    priority: float = 0.0
    cache_hit: bool = False
    attempts: int = 0
    timed_out: bool = False
    status: str = "ok"
    message: str = "ok"
    manifest: MarketStreamManifest | None = None
    summary: MarketStreamSummary | None = None
    health: MarketStreamHealth | None = None
    elapsed_ms: float | None = None
    snapshot_freshness_ms: float | None = None
    health_score: float | None = None
    metadata_gap_count: int = 0
    metadata_gap_rate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamCollectionReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"streamctl_{uuid4().hex[:12]}")
    request: StreamCollectionRequest
    total_count: int = 0
    processed_count: int = 0
    cache_hit_count: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    error_count: int = 0
    backpressure_applied: bool = False
    batch_count: int = 0
    max_workers: int = 0
    prioritized_refs: list[str] = Field(default_factory=list)
    items: list[StreamCollectionItem] = Field(default_factory=list)
    cache_hit_rate: float = 0.0
    metrics: StreamCollectionMetrics | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class MarketStreamPaths:
    root: Path

    @classmethod
    def from_prediction_paths(cls, paths: PredictionMarketPaths | None = None) -> "MarketStreamPaths":
        base = paths or default_prediction_market_paths()
        return cls(root=base.root / "streams")

    def ensure_layout(self) -> None:
        ensure_storage_layout(self.root)

    def stream_dir(self, stream_id: str) -> Path:
        return self.root / stream_id

    def manifest_path(self, stream_id: str) -> Path:
        return self.stream_dir(stream_id) / "manifest.json"

    def events_path(self, stream_id: str) -> Path:
        return self.stream_dir(stream_id) / "events.jsonl"

    def latest_snapshot_path(self, stream_id: str) -> Path:
        return self.stream_dir(stream_id) / "latest_snapshot.json"

    def descriptor_path(self, stream_id: str) -> Path:
        return self.stream_dir(stream_id) / "market.json"

    def control_dir(self) -> Path:
        return self.root / "_control"

    def collection_cache_dir(self) -> Path:
        return self.control_dir() / "collection_cache"

    def collection_cache_path(self, cache_key: str) -> Path:
        return self.collection_cache_dir() / f"{cache_key}.json"


def _default_feed_surface(
    *,
    venue: VenueName,
    backend_mode: str | None,
    supports_events: bool,
    supports_positions: bool,
    events_source: str | None,
    positions_source: str | None,
    market_feed_source: str | None,
    user_feed_source: str | None,
) -> MarketFeedSurface:
    effective_backend = (backend_mode or "unknown").strip().lower()
    capability = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(venue)
    api_access = list(capability.api_access or capability.metadata.get("api_access", []) or [])
    supported_order_types = list(
        capability.supported_order_types or capability.metadata.get("supported_order_types", []) or []
    )
    fixture_mode = effective_backend == "fixture"
    market_transport = FeedTransport.http_json if effective_backend == "live" else (FeedTransport.fixture_cache if fixture_mode else FeedTransport.surrogate_snapshot)
    user_transport = FeedTransport.http_json if effective_backend == "live" else (FeedTransport.fixture_cache if fixture_mode else FeedTransport.local_cache)
    market_status = "configured_endpoint" if effective_backend == "live" else ("fixture_available" if fixture_mode else "local_cache")
    user_status = (
        "configured_endpoint"
        if effective_backend == "live" and supports_positions
        else ("fixture_available" if fixture_mode and supports_positions else ("local_cache" if supports_positions else "unavailable"))
    )
    market_connector = "http_json_market_snapshot" if effective_backend == "live" else ("fixture_cache" if fixture_mode else (market_feed_source or "surrogate_snapshot"))
    user_connector = (
        "http_json_position_snapshot"
        if effective_backend == "live" and supports_positions
        else ("fixture_cache" if fixture_mode and supports_positions else ((user_feed_source or positions_source or "local_position_cache") if supports_positions else "unavailable"))
    )
    runbook = _feed_surface_runbook(
        venue=venue,
        backend_mode=effective_backend,
        ingestion_mode="read_only",
        market_feed_status=market_status,
        user_feed_status=user_status,
        supports_positions=supports_positions,
        supports_events=supports_events,
        supports_discovery=capability.supports_discovery,
        supports_orderbook=capability.supports_orderbook,
        supports_trades=capability.supports_trades,
        supports_execution=capability.supports_execution,
        supports_paper_mode=capability.supports_paper_mode,
        live_websocket_binding=PolymarketLiveWebsocketBinding.from_env() if effective_backend == "live" else None,
    )
    data = {
        "venue": venue,
        "venue_type": capability.venue_type.value if capability.venue_type else None,
        "backend_mode": effective_backend,
        "ingestion_mode": "read_only",
        "market_feed_kind": "market_snapshot_http_json" if effective_backend == "live" else "market_snapshot_surrogate",
        "user_feed_kind": "position_snapshot_http_json" if supports_positions and effective_backend == "live" else ("position_snapshot_cache" if supports_positions else "unavailable"),
        "supports_discovery": capability.supports_discovery,
        "supports_orderbook": capability.supports_orderbook,
        "supports_trades": capability.supports_trades,
        "supports_execution": capability.supports_execution,
        "supports_paper_mode": capability.supports_paper_mode,
        "supports_market_feed": True,
        "supports_user_feed": bool(supports_positions),
        "supports_events": bool(supports_events),
        "supports_positions": bool(supports_positions),
        "supports_websocket": False,
        "supports_rtds": False,
        "live_streaming": False,
        "websocket_status": "unavailable",
        "market_websocket_status": "unavailable",
        "user_feed_websocket_status": "unavailable",
        "api_access": api_access,
        "supported_order_types": supported_order_types,
        "rate_limit_notes": list(capability.rate_limit_notes),
        "automation_constraints": list(capability.automation_constraints),
        "market_feed_transport": market_transport,
        "user_feed_transport": user_transport if supports_positions else FeedTransport.unavailable,
        "market_feed_connector": market_connector,
        "user_feed_connector": user_connector,
        "rtds_connector": "unavailable",
        "market_feed_status": market_status,
        "user_feed_status": user_status,
        "rtds_status": "unavailable",
        "market_feed_replayable": True,
        "user_feed_replayable": bool(supports_positions),
        "rtds_replayable": False,
        "market_feed_cache_backed": effective_backend != "live",
        "user_feed_cache_backed": effective_backend != "live" and bool(supports_positions),
        "rtds_cache_backed": False,
        "events_source": events_source or market_feed_source or "snapshot_polling",
        "positions_source": positions_source or user_feed_source or "local_position_cache",
        "market_feed_source": market_feed_source or "snapshot_polling",
        "user_feed_source": user_feed_source or ("local_position_cache" if effective_backend != "live" else "http_json"),
        "configured_endpoints": {
            "events_source": events_source or market_feed_source or "snapshot_polling",
            "positions_source": positions_source or user_feed_source or "local_position_cache",
            "market_feed_source": market_feed_source or "snapshot_polling",
            "user_feed_source": user_feed_source or ("local_position_cache" if effective_backend != "live" else "http_json"),
        },
        "summary": (
            f"Read-only market and user feed summaries from {market_feed_source or 'snapshot_polling'} / "
            f"{user_feed_source or ('local_position_cache' if effective_backend != 'live' else 'http_json')}; "
            "market snapshots are replayable, user feeds are cache-backed proxies when available, and websocket/RTDS are not implemented here."
        ),
        "runbook": runbook,
        "notes": [
            "read_only_support_only",
            "no_websocket_live_integration" if effective_backend != "live" else "no_rtds_live_integration",
        ],
        "metadata": {
            "read_only": True,
            "backend_mode": effective_backend,
            "venue_type": capability.venue_type.value if capability.venue_type else None,
            "api_access": api_access,
            "supported_order_types": supported_order_types,
            "supports_discovery": capability.supports_discovery,
            "supports_orderbook": capability.supports_orderbook,
            "supports_trades": capability.supports_trades,
            "supports_execution": capability.supports_execution,
            "supports_websocket": False,
            "supports_paper_mode": capability.supports_paper_mode,
            "rate_limit_notes": list(capability.rate_limit_notes),
            "automation_constraints": list(capability.automation_constraints),
        },
    }
    data = _apply_live_websocket_binding(data)
    data["route_refs"] = _feed_surface_route_refs(data)
    data["availability_probes"] = _feed_surface_availability_probes(data)
    data["cache_fallbacks"] = _feed_surface_cache_fallbacks(data)
    data["connector_contracts"] = _feed_surface_connector_contracts(data)
    data["subscription_preview"] = _feed_surface_subscription_preview(data)
    data["probe_bundle"] = _feed_surface_probe_bundle(data)
    data["capability_summary"] = _feed_surface_capability_summary(data)
    gap_count, gap_rate, completeness = _feed_surface_metadata_gap_count(data)
    data["metadata_gap_count"] = gap_count
    data["metadata_gap_rate"] = gap_rate
    data["metadata_completeness"] = completeness
    degraded, degraded_reasons = _feed_surface_degradation(data)
    data["degraded"] = degraded
    data["degraded_reasons"] = degraded_reasons
    runbook_signals = dict(data["runbook"].get("signals", {}))
    for key in (
        "market_websocket_status",
        "user_feed_websocket_status",
        "market_feed_status",
        "user_feed_status",
        "rtds_status",
        "market_feed_connector",
        "user_feed_connector",
        "rtds_connector",
        "market_feed_replayable",
        "user_feed_replayable",
        "rtds_replayable",
        "market_feed_cache_backed",
        "user_feed_cache_backed",
        "rtds_cache_backed",
        "route_refs",
        "availability_probes",
        "cache_fallbacks",
        "connector_contracts",
        "gap_summary",
        "subscription_preview",
        "probe_bundle",
        "capability_summary",
    ):
        runbook_signals[key] = data.get(key)
    runbook_signals["feed_surface_degraded"] = degraded
    runbook_signals["feed_surface_degraded_reasons"] = degraded_reasons
    data["runbook"]["signals"] = runbook_signals
    return MarketFeedSurface(
        **data,
    )


def _normalize_feed_surface(
    surface: Any,
    *,
    venue: VenueName,
    backend_mode: str | None,
    supports_events: bool,
    supports_positions: bool,
) -> MarketFeedSurface:
    if isinstance(surface, MarketFeedSurface):
        return surface
    data: dict[str, Any] = {}
    if hasattr(surface, "model_dump"):
        data = surface.model_dump(mode="json")
    if isinstance(surface, dict):
        data = dict(surface)
    data.setdefault("venue", venue)
    capability = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(venue)
    data.setdefault("backend_mode", backend_mode or "unknown")
    data.setdefault("ingestion_mode", "read_only")
    data.setdefault("market_feed_kind", "market_snapshot")
    data.setdefault("user_feed_kind", "position_snapshot" if supports_positions else "unavailable")
    data.setdefault("venue_type", capability.venue_type.value if capability.venue_type else None)
    data.setdefault("supports_discovery", capability.supports_discovery)
    data.setdefault("supports_orderbook", capability.supports_orderbook)
    data.setdefault("supports_trades", capability.supports_trades)
    data.setdefault("supports_execution", capability.supports_execution)
    data.setdefault("supports_paper_mode", capability.supports_paper_mode)
    data.setdefault("supports_market_feed", True)
    data.setdefault("supports_user_feed", supports_positions or bool(data.get("supports_user_feed")))
    data.setdefault("supports_events", supports_events or bool(data.get("supports_events")))
    data.setdefault("supports_positions", supports_positions or bool(data.get("supports_positions")))
    data.setdefault("supports_websocket", False)
    data.setdefault("supports_rtds", False)
    data.setdefault("live_streaming", False)
    data.setdefault("websocket_status", "unavailable")
    data.setdefault("market_websocket_status", data.get("websocket_status", "unavailable"))
    data.setdefault("user_feed_websocket_status", "unavailable")
    data.setdefault("api_access", list(capability.api_access or capability.metadata.get("api_access", []) or []))
    data.setdefault(
        "supported_order_types",
        list(capability.supported_order_types or capability.metadata.get("supported_order_types", []) or []),
    )
    data.setdefault("rate_limit_notes", list(capability.rate_limit_notes))
    data.setdefault("automation_constraints", list(capability.automation_constraints))
    backend = str(data["backend_mode"]).strip().lower()
    fixture_mode = backend == "fixture"
    data.setdefault(
        "market_feed_transport",
        FeedTransport.http_json if backend == "live" else (FeedTransport.fixture_cache if fixture_mode else FeedTransport.surrogate_snapshot),
    )
    data.setdefault(
        "user_feed_transport",
        FeedTransport.http_json if backend == "live" else (FeedTransport.fixture_cache if fixture_mode else FeedTransport.local_cache),
    )
    data.setdefault(
        "market_feed_connector",
        "http_json_market_snapshot"
        if backend == "live"
        else ("fixture_cache" if fixture_mode else str(data.get("market_feed_source") or "surrogate_snapshot")),
    )
    data.setdefault(
        "user_feed_connector",
        "http_json_position_snapshot"
        if backend == "live" and supports_positions
        else (
            "fixture_cache"
            if fixture_mode and supports_positions
            else (str(data.get("user_feed_source") or data.get("positions_source") or "local_position_cache") if supports_positions else "unavailable")
        ),
    )
    data.setdefault("rtds_connector", "unavailable")
    data.setdefault("market_feed_status", "configured_endpoint" if backend == "live" else ("fixture_available" if fixture_mode else "local_cache"))
    data.setdefault("user_feed_status", "configured_endpoint" if backend == "live" and supports_positions else ("fixture_available" if fixture_mode and supports_positions else ("local_cache" if supports_positions else "unavailable")))
    data.setdefault("rtds_status", "unavailable")
    data.setdefault("market_feed_replayable", True)
    data.setdefault("user_feed_replayable", bool(supports_positions))
    data.setdefault("rtds_replayable", False)
    data.setdefault("market_feed_cache_backed", backend != "live")
    data.setdefault("user_feed_cache_backed", backend != "live" and bool(supports_positions))
    data.setdefault("rtds_cache_backed", False)
    data.setdefault("events_source", data.get("market_feed_source") or "snapshot_polling")
    data.setdefault("positions_source", data.get("user_feed_source") or "local_position_cache")
    data.setdefault("market_feed_source", "snapshot_polling")
    data.setdefault("user_feed_source", "local_position_cache")
    data.setdefault(
        "configured_endpoints",
        {
            "events_source": data.get("events_source"),
            "positions_source": data.get("positions_source"),
            "market_feed_source": data.get("market_feed_source"),
            "user_feed_source": data.get("user_feed_source"),
        },
    )
    data = _apply_live_websocket_binding(data)
    route_refs = _feed_surface_route_refs(data)
    data.setdefault("route_refs", route_refs)
    if isinstance(data.get("route_refs"), dict):
        merged_route_refs = dict(route_refs)
        merged_route_refs.update({str(key): str(value) for key, value in dict(data.get("route_refs") or {}).items() if value is not None})
        data["route_refs"] = merged_route_refs
    probes = _feed_surface_availability_probes(data)
    data.setdefault("availability_probes", probes)
    if isinstance(data.get("availability_probes"), dict):
        merged_probes = dict(probes)
        merged_probes.update(dict(data.get("availability_probes") or {}))
        data["availability_probes"] = merged_probes
    cache_fallbacks = _feed_surface_cache_fallbacks(data)
    data.setdefault("cache_fallbacks", cache_fallbacks)
    if isinstance(data.get("cache_fallbacks"), dict):
        merged_fallbacks = dict(cache_fallbacks)
        merged_fallbacks.update(dict(data.get("cache_fallbacks") or {}))
        data["cache_fallbacks"] = merged_fallbacks
    connector_contracts = _feed_surface_connector_contracts(data)
    data.setdefault("connector_contracts", connector_contracts)
    if isinstance(data.get("connector_contracts"), dict):
        merged_contracts = dict(connector_contracts)
        merged_contracts.update(dict(data.get("connector_contracts") or {}))
        data["connector_contracts"] = merged_contracts
    subscription_preview = _feed_surface_subscription_preview(data)
    data.setdefault("subscription_preview", subscription_preview)
    if isinstance(data.get("subscription_preview"), dict):
        merged_preview = dict(subscription_preview)
        merged_preview.update(dict(data.get("subscription_preview") or {}))
        data["subscription_preview"] = merged_preview
    probe_bundle = _feed_surface_probe_bundle(data)
    data.setdefault("probe_bundle", probe_bundle)
    if isinstance(data.get("probe_bundle"), dict):
        merged_bundle = dict(probe_bundle)
        merged_bundle.update(dict(data.get("probe_bundle") or {}))
        data["probe_bundle"] = merged_bundle
    capability_summary = _feed_surface_capability_summary(data)
    data.setdefault("capability_summary", capability_summary)
    if isinstance(data.get("capability_summary"), dict):
        merged_summary = dict(capability_summary)
        merged_summary.update(dict(data.get("capability_summary") or {}))
        data["capability_summary"] = merged_summary
    data.setdefault(
        "summary",
        f"Read-only market and user feed summaries from {data.get('market_feed_source')} / {data.get('user_feed_source')}; "
        "market snapshots are replayable, user feeds are cache-backed proxies when available, and websocket/RTDS are not implemented here.",
    )
    data.setdefault("runbook", _feed_surface_runbook(
        venue=venue,
        backend_mode=str(data.get("backend_mode", "unknown")),
        ingestion_mode=str(data.get("ingestion_mode", "read_only")),
        market_feed_status=str(data.get("market_feed_status", "local_cache")),
        user_feed_status=str(data.get("user_feed_status", "local_cache")),
        supports_positions=bool(data.get("supports_positions")),
        supports_events=bool(data.get("supports_events")),
        supports_discovery=bool(data.get("supports_discovery")),
        supports_orderbook=bool(data.get("supports_orderbook")),
        supports_trades=bool(data.get("supports_trades")),
        supports_execution=bool(data.get("supports_execution")),
        supports_paper_mode=bool(data.get("supports_paper_mode")),
        live_websocket_binding=PolymarketLiveWebsocketBinding.from_env() if backend == "live" else None,
    ))
    data.setdefault("notes", ["read_only_support_only"])
    data.setdefault("metadata", {})
    gap_count, gap_rate, completeness = _feed_surface_metadata_gap_count(data)
    data.setdefault("metadata_gap_count", gap_count)
    data.setdefault("metadata_gap_rate", gap_rate)
    data.setdefault("metadata_completeness", completeness)
    degraded, degraded_reasons = _feed_surface_degradation(data)
    data.setdefault("degraded", degraded)
    data.setdefault("degraded_reasons", degraded_reasons)
    runbook = dict(data.get("runbook") or {})
    runbook_signals = dict(runbook.get("signals") or {})
    for key in (
        "market_websocket_status",
        "user_feed_websocket_status",
        "market_feed_status",
        "user_feed_status",
        "rtds_status",
        "market_feed_connector",
        "user_feed_connector",
        "rtds_connector",
        "market_feed_replayable",
        "user_feed_replayable",
        "rtds_replayable",
        "market_feed_cache_backed",
        "user_feed_cache_backed",
        "rtds_cache_backed",
        "route_refs",
        "availability_probes",
        "cache_fallbacks",
        "connector_contracts",
        "gap_summary",
        "subscription_preview",
        "probe_bundle",
        "capability_summary",
    ):
        runbook_signals[key] = data.get(key)
    runbook_signals.setdefault("feed_surface_degraded", degraded)
    runbook_signals.setdefault("feed_surface_degraded_reasons", degraded_reasons)
    runbook["signals"] = runbook_signals
    data["runbook"] = runbook
    return MarketFeedSurface.model_validate(data)


def _feed_surface_runbook(
    *,
    venue: VenueName,
    backend_mode: str,
    ingestion_mode: str,
    market_feed_status: str,
    user_feed_status: str,
    supports_positions: bool,
    supports_events: bool,
    supports_discovery: bool = False,
    supports_orderbook: bool = False,
    supports_trades: bool = False,
    supports_execution: bool = False,
    supports_paper_mode: bool = False,
    live_websocket_binding: PolymarketLiveWebsocketBinding | None = None,
) -> dict[str, Any]:
    live_like = backend_mode == "live"
    live_bound = live_websocket_binding is not None and live_websocket_binding.live_enabled
    live_user_bound = bool(live_websocket_binding and live_websocket_binding.user_websocket_url and live_websocket_binding.user_auth_configured)
    live_rtds_bound = bool(live_websocket_binding and live_websocket_binding.rtds_url)
    status = "ready" if supports_positions or supports_events else "partial"
    if live_bound:
        status = "ready" if (supports_positions or supports_events or supports_discovery) else "partial"
    return {
        "runbook_id": f"{venue.value}_read_only_feed_surface",
        "runbook_kind": "surface",
        "summary": (
            "Poll read-only market snapshots and position caches; "
            "websocket and RTDS are not implemented here."
            if not live_bound
            else (
                "Live websocket market/user feeds and RTDS are bindable and configured; "
                "keep auth and heartbeat handling in place."
            )
        ),
        "recommended_action": "use_read_only_surfaces_only" if not live_bound else "use_live_bound_streams_with_read_only_backstops",
        "status": status,
        "feed_mode": "read_only" if not live_bound else "live_bound",
        "streaming_mode": "read_only_snapshot_polling" if not live_bound else "live_websocket_rtds",
        "websocket_status": "unavailable" if not live_bound else "ready",
        "rtds_status": "unavailable" if not live_bound else ("ready" if live_rtds_bound else "unavailable"),
        "next_steps": [
            "Use market snapshots as read-only input only.",
            "Treat user feed as position/cache data, not live order flow.",
            "Do not assume websocket or RTDS availability.",
        ]
        if not live_bound
        else [
            "Use market websocket subscriptions for live token updates.",
            "Use user websocket subscriptions only when credentials are bound.",
            "Use RTDS for live event streams and keep heartbeats running.",
        ],
        "signals": {
            "backend_mode": backend_mode,
            "ingestion_mode": ingestion_mode,
            "feed_mode": "read_only" if not live_bound else "live_bound",
            "streaming_mode": "read_only_snapshot_polling" if not live_bound else "live_websocket_rtds",
            "market_feed_status": market_feed_status,
            "user_feed_status": user_feed_status,
            "supports_discovery": supports_discovery,
            "supports_orderbook": supports_orderbook,
            "supports_trades": supports_trades,
            "supports_execution": supports_execution,
            "supports_paper_mode": supports_paper_mode,
            "supports_positions": supports_positions,
            "supports_events": supports_events,
            "supports_websocket": live_bound,
            "supports_rtds": live_rtds_bound,
            "live_streaming": live_bound,
            "live_like_backend": live_like,
            "websocket_status": "ready" if live_bound else "unavailable",
            "market_websocket_status": "ready" if live_bound and bool(live_websocket_binding and live_websocket_binding.market_websocket_url) else "unavailable",
            "user_feed_websocket_status": "ready" if live_user_bound else ("auth_required" if live_websocket_binding and live_websocket_binding.user_websocket_url else "unavailable"),
            "rtds_status": "ready" if live_rtds_bound else "unavailable",
            "market_feed_connector": "http_json_market_snapshot" if live_like else "snapshot_polling",
            "user_feed_connector": "http_json_position_snapshot" if live_like and supports_positions else ("local_position_cache" if supports_positions else "unavailable"),
            "rtds_connector": "polymarket_rtds_websocket" if live_rtds_bound else "unavailable",
            "market_feed_replayable": True,
            "user_feed_replayable": bool(supports_positions),
            "rtds_replayable": bool(live_rtds_bound),
            "market_feed_cache_backed": not live_like,
            "user_feed_cache_backed": not live_like and bool(supports_positions),
            "rtds_cache_backed": False,
            "live_websocket_binding": asdict(live_websocket_binding) if live_websocket_binding is not None else None,
        },
    }


def _feed_surface_metadata_gap_count(data: dict[str, Any]) -> tuple[int, float, float]:
    placeholder_fields: list[tuple[str, set[Any]]] = [
        ("events_source", {"snapshot_polling", "local_cache"}),
        ("positions_source", {"local_position_cache", "local_cache"}),
        ("market_feed_source", {"snapshot_polling", "local_cache"}),
        ("user_feed_source", {"local_position_cache", "local_cache"}),
        ("market_feed_transport", {FeedTransport.surrogate_snapshot, FeedTransport.local_cache, FeedTransport.unavailable}),
        ("user_feed_transport", {FeedTransport.local_cache, FeedTransport.unavailable}),
        ("market_feed_status", {"local_cache", "unavailable"}),
        ("user_feed_status", {"local_cache", "unavailable"}),
        ("rtds_status", {"unavailable"}),
    ]
    missing = 0
    for key, placeholders in placeholder_fields:
        placeholder_values = {item.value if hasattr(item, "value") else str(item) for item in placeholders}
        value = data.get(key)
        if value is None:
            missing += 1
            continue
        if isinstance(value, str) and value.strip() in placeholder_values:
            missing += 1
        elif value in placeholders or str(value) in placeholder_values:
            missing += 1
    configured_endpoints = data.get("configured_endpoints")
    if not isinstance(configured_endpoints, dict) or not configured_endpoints:
        missing += 1
    route_refs = data.get("route_refs")
    if not isinstance(route_refs, dict) or not route_refs:
        missing += 1
    availability_probes = data.get("availability_probes")
    if not isinstance(availability_probes, dict) or not availability_probes:
        missing += 1
    cache_fallbacks = data.get("cache_fallbacks")
    if not isinstance(cache_fallbacks, dict) or not cache_fallbacks:
        missing += 1
    connector_contracts = data.get("connector_contracts")
    if not isinstance(connector_contracts, dict) or not connector_contracts:
        missing += 1
    subscription_preview = data.get("subscription_preview")
    if not isinstance(subscription_preview, dict) or not subscription_preview:
        missing += 1
    probe_bundle = data.get("probe_bundle")
    if not isinstance(probe_bundle, dict) or not probe_bundle:
        missing += 1
    capability_summary = data.get("capability_summary")
    if not isinstance(capability_summary, dict) or not capability_summary:
        missing += 1
    summary = str(data.get("summary", "")).strip()
    if not summary:
        missing += 1
    runbook = data.get("runbook")
    if not isinstance(runbook, dict) or not runbook:
        missing += 1
    api_access = data.get("api_access")
    if not api_access:
        missing += 1
    supported_order_types = data.get("supported_order_types")
    if data.get("supports_execution") and not supported_order_types:
        missing += 1
    rate_limit_notes = data.get("rate_limit_notes")
    if not rate_limit_notes:
        missing += 1
    automation_constraints = data.get("automation_constraints")
    if not automation_constraints:
        missing += 1
    notes = data.get("notes")
    if not notes:
        missing += 1
    expected = 20
    rate = round(missing / expected, 3)
    completeness = round(max(0.0, 1.0 - rate), 3)
    return missing, rate, completeness


def _feed_surface_route_refs(data: dict[str, Any]) -> dict[str, str]:
    route_refs: dict[str, str] = {}
    for route_key, source_key in (
        ("events", "events_source"),
        ("positions", "positions_source"),
        ("market_feed", "market_feed_source"),
        ("user_feed", "user_feed_source"),
        ("market_websocket", "market_websocket_source"),
        ("user_websocket", "user_websocket_source"),
        ("rtds", "rtds_source"),
    ):
        value = data.get(source_key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            route_refs[route_key] = text
    configured = data.get("configured_endpoints")
    if isinstance(configured, dict):
        for key, value in configured.items():
            if value is None:
                continue
            text = str(value).strip()
            if text:
                route_refs.setdefault(str(key), text)
    return route_refs


def _feed_surface_transport_name(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    text = str(value or "").strip()
    return text or "unavailable"


def _feed_surface_gap_summary(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or _feed_surface_route_refs(data))
    probes = dict(data.get("availability_probes") or _feed_surface_availability_probes(data))
    contracts = dict(data.get("connector_contracts") or _feed_surface_connector_contracts(data))
    channel_specs = dict(data.get("channel_specs") or {})
    preview_channels = dict(data.get("subscription_preview", {}).get("channels") or {})
    if not preview_channels:
        preview_channels = {
            key: value
            for key, value in channel_specs.items()
            if str(dict(value or {}).get("delivery_mode", "")).strip() == "preview_only"
        }
    live_channels = ("websocket_market", "websocket_user", "rtds")
    cache_channels = ("market_feed", "user_feed")
    return {
        "live_transport_supported": bool(data.get("supports_websocket", False) or data.get("supports_rtds", False)),
        "live_transport_ready_count": sum(
            1 for channel in live_channels if str(dict(probes.get(channel) or {}).get("operational_status", "unavailable")) == "ready"
        ),
        "live_transport_not_supported_count": sum(
            1 for channel in live_channels if str(dict(probes.get(channel) or {}).get("operational_status", "unavailable")) == "not_supported"
        ),
        "preview_only_channel_count": sum(
            1
            for channel in preview_channels.values()
            if str(dict(dict(channel or {}).get("channel_spec") or {}).get("delivery_mode", "")).strip() == "preview_only"
        ),
        "cache_backed_channel_count": sum(1 for channel in cache_channels if bool(dict(probes.get(channel) or {}).get("cache_backed", False))),
        "documented_preview_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "live_transport_gap_reasons": {
            channel: dict(probes.get(channel) or {}).get("gap_reason")
            for channel in live_channels
        },
        "cache_backed_gap_reasons": {
            channel: dict(probes.get(channel) or {}).get("gap_reason")
            for channel in cache_channels
        },
        "explicit_gaps": list(data.get("explicit_gaps") or [dict(spec or {}).get("explicit_gap") for spec in channel_specs.values() if dict(spec or {}).get("explicit_gap")]),
    }


def _feed_probe_ready(status: str, *, route_ref: str | None, supported: bool = True) -> bool:
    if not supported:
        return False
    return status in {"configured_endpoint", "endpoint_configured", "fixture_available", "surrogate_available", "local_cache"} and bool(route_ref)


def _feed_probe_operational_status(status: str, *, probe_ready: bool, supported: bool = True) -> str:
    if probe_ready:
        return "ready"
    if not supported:
        return "not_supported"
    if status in {"degraded", "stale", "maintenance"}:
        return "degraded"
    return "unavailable"


def _feed_probe_recommended_action(
    *,
    probe_name: str,
    transport: str,
    cache_backed: bool,
    operational_status: str,
) -> str:
    if operational_status == "ready":
        if probe_name == "websocket_market":
            return "open_live_websocket"
        if probe_name == "websocket_user":
            return "open_live_websocket"
        if probe_name == "rtds":
            return "open_live_rtds"
        if probe_name == "user_feed" and cache_backed:
            return "read_user_feed_cache"
        if cache_backed:
            return "use_cache_backed_snapshot"
        if transport == "http_json":
            return "poll_http_snapshot"
        return "poll_snapshot_route"
    if probe_name.startswith("websocket"):
        return "do_not_assume_live_websocket"
    if probe_name == "rtds":
        return "do_not_assume_rtds"
    return "use_cache_fallback" if cache_backed else "treat_as_unavailable"


def _feed_probe_severity(*, probe_name: str, operational_status: str) -> str:
    if operational_status == "ready":
        return "info"
    if operational_status == "degraded":
        return "warning"
    if operational_status == "not_supported":
        return "info"
    if probe_name == "market_feed":
        return "error"
    if probe_name == "user_feed":
        return "warning"
    return "info"


def _feed_probe_gap_reason(*, probe_name: str, cache_backed: bool) -> str:
    if probe_name == "market_feed":
        return "snapshot_only_no_push" if cache_backed else "poll_only_surface"
    if probe_name == "user_feed":
        return "user_feed_proxy_cache" if cache_backed else "no_user_feed_binding"
    if probe_name == "websocket_market":
        return "live_websocket_not_bound"
    if probe_name == "websocket_user":
        return "live_user_feed_not_bound"
    return "rtds_not_bound"


def _feed_surface_availability_probes(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or {})
    live_binding = dict(data.get("live_websocket_binding") or {})
    market_feed_status = str(data.get("market_feed_status", "unavailable"))
    market_feed_transport = _feed_surface_transport_name(data.get("market_feed_transport"))
    market_feed_route = route_refs.get("market_feed")
    market_feed_cache_backed = bool(data.get("market_feed_cache_backed", False))
    market_feed_probe_ready = _feed_probe_ready(market_feed_status, route_ref=market_feed_route)
    market_feed_operational_status = _feed_probe_operational_status(market_feed_status, probe_ready=market_feed_probe_ready)

    user_feed_status = str(data.get("user_feed_status", "unavailable"))
    user_feed_transport = _feed_surface_transport_name(data.get("user_feed_transport"))
    user_feed_route = route_refs.get("user_feed")
    user_feed_cache_backed = bool(data.get("user_feed_cache_backed", False))
    user_feed_probe_ready = _feed_probe_ready(user_feed_status, route_ref=user_feed_route)
    user_feed_operational_status = _feed_probe_operational_status(user_feed_status, probe_ready=user_feed_probe_ready)

    websocket_market_status = str(data.get("market_websocket_status", data.get("websocket_status", "unavailable")))
    websocket_market_route = route_refs.get("market_websocket")
    websocket_market_live_bound = bool(live_binding.get("market_websocket_url"))
    websocket_market_supported = bool(data.get("supports_websocket", False) or websocket_market_live_bound)
    websocket_market_probe_ready = _feed_probe_ready(
        "configured_endpoint" if websocket_market_live_bound else websocket_market_status,
        route_ref=websocket_market_route,
        supported=websocket_market_supported,
    )
    websocket_market_operational_status = _feed_probe_operational_status(
        websocket_market_status,
        probe_ready=websocket_market_probe_ready,
        supported=websocket_market_supported,
    )

    websocket_user_status = str(data.get("user_feed_websocket_status", "unavailable"))
    websocket_user_live_bound = bool(live_binding.get("user_websocket_url"))
    websocket_user_auth_configured = bool(live_binding.get("user_auth_configured", False))
    websocket_user_route = route_refs.get("user_websocket")
    websocket_user_supported = bool(data.get("supports_websocket", False) or websocket_user_live_bound)
    websocket_user_probe_ready = _feed_probe_ready(
        "configured_endpoint" if websocket_user_live_bound and websocket_user_auth_configured else websocket_user_status,
        route_ref=websocket_user_route,
        supported=websocket_user_supported,
    )
    websocket_user_operational_status = _feed_probe_operational_status(
        "configured_endpoint" if websocket_user_live_bound and websocket_user_auth_configured else websocket_user_status,
        probe_ready=websocket_user_probe_ready,
        supported=websocket_user_supported,
    )
    if websocket_user_live_bound and not websocket_user_auth_configured:
        websocket_user_operational_status = "unavailable"

    rtds_status = str(data.get("rtds_status", "unavailable"))
    rtds_route = route_refs.get("rtds")
    rtds_cache_backed = bool(data.get("rtds_cache_backed", False))
    rtds_live_bound = bool(live_binding.get("rtds_url"))
    rtds_supported = bool(data.get("supports_rtds", False) or rtds_live_bound)
    rtds_probe_ready = _feed_probe_ready(
        "configured_endpoint" if rtds_live_bound else rtds_status,
        route_ref=rtds_route,
        supported=rtds_supported,
    )
    rtds_operational_status = _feed_probe_operational_status(
        rtds_status,
        probe_ready=rtds_probe_ready,
        supported=rtds_supported,
    )

    return {
        "market_feed": {
            "status": market_feed_status,
            "transport": market_feed_transport,
            "connector": str(data.get("market_feed_connector", "unavailable")),
            "route_ref": market_feed_route,
            "replayable": bool(data.get("market_feed_replayable", True)),
            "cache_backed": market_feed_cache_backed,
            "probe_ready": market_feed_probe_ready,
            "operational_status": market_feed_operational_status,
            "recommended_action": _feed_probe_recommended_action(
                probe_name="market_feed",
                transport=market_feed_transport,
                cache_backed=market_feed_cache_backed,
                operational_status=market_feed_operational_status,
            ),
            "severity": _feed_probe_severity(probe_name="market_feed", operational_status=market_feed_operational_status),
            "gap_reason": _feed_probe_gap_reason(probe_name="market_feed", cache_backed=market_feed_cache_backed),
            "documented_route_ref": market_feed_route,
            "auth_requirement": "none",
            "session_requirement": "none",
            "subscription_capable": False,
            "preview_only": False,
            "gap_class": "snapshot_only" if market_feed_cache_backed else "poll_only_surface",
        },
        "user_feed": {
            "status": user_feed_status,
            "transport": user_feed_transport,
            "connector": str(data.get("user_feed_connector", "unavailable")),
            "route_ref": user_feed_route,
            "replayable": bool(data.get("user_feed_replayable", False)),
            "cache_backed": user_feed_cache_backed,
            "probe_ready": user_feed_probe_ready,
            "operational_status": user_feed_operational_status,
            "recommended_action": _feed_probe_recommended_action(
                probe_name="user_feed",
                transport=user_feed_transport,
                cache_backed=user_feed_cache_backed,
                operational_status=user_feed_operational_status,
            ),
            "severity": _feed_probe_severity(probe_name="user_feed", operational_status=user_feed_operational_status),
            "gap_reason": _feed_probe_gap_reason(probe_name="user_feed", cache_backed=user_feed_cache_backed),
            "documented_route_ref": user_feed_route,
            "auth_requirement": "none",
            "session_requirement": "local_cache_context" if user_feed_cache_backed else "none",
            "subscription_capable": False,
            "preview_only": False,
            "gap_class": "cache_proxy" if user_feed_cache_backed else "user_feed_not_bound",
        },
        "websocket_market": {
            "status": websocket_market_status,
            "transport": "websocket",
            "connector": str(data.get("market_websocket_connector", "unavailable")),
            "route_ref": websocket_market_route,
            "replayable": False,
            "cache_backed": False,
            "supported": websocket_market_supported,
            "probe_ready": websocket_market_probe_ready,
            "operational_status": websocket_market_operational_status,
            "recommended_action": _feed_probe_recommended_action(
                probe_name="websocket_market",
                transport="websocket",
                cache_backed=False,
                operational_status=websocket_market_operational_status,
            ),
            "severity": _feed_probe_severity(probe_name="websocket_market", operational_status=websocket_market_operational_status),
            "gap_reason": "live_websocket_bound" if websocket_market_live_bound else _feed_probe_gap_reason(probe_name="websocket_market", cache_backed=False),
            "documented_route_ref": websocket_market_route,
            "auth_requirement": "none",
            "session_requirement": "live_socket" if websocket_market_live_bound else "preview_only",
            "subscription_capable": bool(websocket_market_live_bound),
            "preview_only": not websocket_market_live_bound,
            "gap_class": "live_bound" if websocket_market_live_bound else "not_bound",
        },
        "websocket_user": {
            "status": websocket_user_status,
            "transport": "websocket",
            "connector": str(data.get("user_websocket_connector", "unavailable")),
            "route_ref": websocket_user_route,
            "replayable": False,
            "cache_backed": False,
            "supported": websocket_user_supported,
            "probe_ready": websocket_user_probe_ready,
            "operational_status": websocket_user_operational_status,
            "recommended_action": _feed_probe_recommended_action(
                probe_name="websocket_user",
                transport="websocket",
                cache_backed=False,
                operational_status=websocket_user_operational_status,
            ),
            "severity": _feed_probe_severity(probe_name="websocket_user", operational_status=websocket_user_operational_status),
            "gap_reason": "live_user_websocket_bound" if websocket_user_live_bound and websocket_user_auth_configured else ("user_websocket_auth_required" if websocket_user_live_bound else _feed_probe_gap_reason(probe_name="websocket_user", cache_backed=False)),
            "documented_route_ref": websocket_user_route,
            "auth_requirement": "api_credentials" if websocket_user_auth_configured else "api_credentials_required",
            "session_requirement": "live_socket" if websocket_user_live_bound and websocket_user_auth_configured else "preview_only",
            "subscription_capable": bool(websocket_user_live_bound and websocket_user_auth_configured),
            "preview_only": not (websocket_user_live_bound and websocket_user_auth_configured),
            "gap_class": "live_bound" if websocket_user_live_bound and websocket_user_auth_configured else ("auth_required" if websocket_user_live_bound else "not_bound"),
        },
        "rtds": {
            "status": rtds_status,
            "transport": "rtds",
            "connector": str(data.get("rtds_connector", "unavailable")),
            "route_ref": rtds_route,
            "replayable": bool(data.get("rtds_replayable", False)),
            "cache_backed": rtds_cache_backed,
            "supported": rtds_supported,
            "probe_ready": rtds_probe_ready,
            "operational_status": rtds_operational_status,
            "recommended_action": _feed_probe_recommended_action(
                probe_name="rtds",
                transport="rtds",
                cache_backed=rtds_cache_backed,
                operational_status=rtds_operational_status,
            ),
            "severity": _feed_probe_severity(probe_name="rtds", operational_status=rtds_operational_status),
            "gap_reason": "live_rtds_bound" if rtds_live_bound else _feed_probe_gap_reason(probe_name="rtds", cache_backed=rtds_cache_backed),
            "documented_route_ref": rtds_route,
            "auth_requirement": "gamma_auth" if rtds_live_bound else "not_bound",
            "session_requirement": "live_socket" if rtds_live_bound else "preview_only",
            "subscription_capable": bool(rtds_live_bound),
            "preview_only": not rtds_live_bound,
            "gap_class": "live_bound" if rtds_live_bound else "not_bound",
        },
    }


def _feed_surface_cache_fallbacks(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or {})
    return {
        "market_feed": {
            "status": "ready" if bool(data.get("market_feed_cache_backed", False)) else "not_configured",
            "connector": str(data.get("market_feed_connector", "unavailable")),
            "route_ref": route_refs.get("market_feed"),
            "replayable": bool(data.get("market_feed_replayable", True)),
            "cache_backed": bool(data.get("market_feed_cache_backed", False)),
            "operational_status": "ready" if bool(data.get("market_feed_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(data.get("market_feed_cache_backed", False)) else "no_cache_fallback",
        },
        "user_feed": {
            "status": "ready" if bool(data.get("user_feed_cache_backed", False)) else "not_configured",
            "connector": str(data.get("user_feed_connector", "unavailable")),
            "route_ref": route_refs.get("user_feed"),
            "replayable": bool(data.get("user_feed_replayable", False)),
            "cache_backed": bool(data.get("user_feed_cache_backed", False)),
            "operational_status": "ready" if bool(data.get("user_feed_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(data.get("user_feed_cache_backed", False)) else "no_cache_fallback",
        },
        "rtds": {
            "status": "ready" if bool(data.get("rtds_cache_backed", False)) else "not_configured",
            "connector": str(data.get("rtds_connector", "unavailable")),
            "route_ref": route_refs.get("rtds"),
            "replayable": bool(data.get("rtds_replayable", False)),
            "cache_backed": bool(data.get("rtds_cache_backed", False)),
            "operational_status": "ready" if bool(data.get("rtds_cache_backed", False)) else "not_configured",
            "recommended_action": "use_cache_fallback" if bool(data.get("rtds_cache_backed", False)) else "no_cache_fallback",
        },
    }


def _feed_surface_connector_contracts(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or {})
    supports_websocket = bool(data.get("supports_websocket", False))
    supports_rtds = bool(data.get("supports_rtds", False))
    live_binding = dict(data.get("live_websocket_binding") or {})
    live_market_bound = bool(live_binding.get("market_websocket_url"))
    live_user_bound = bool(live_binding.get("user_websocket_url"))
    live_user_auth_configured = bool(live_binding.get("user_auth_configured", False))
    live_rtds_bound = bool(live_binding.get("rtds_url"))
    probes = dict(data.get("availability_probes") or {})
    return {
        "market_feed": {
            "mode": "read_only",
            "transport": _feed_surface_transport_name(data.get("market_feed_transport")),
            "connector": str(data.get("market_feed_connector", "unavailable")),
            "route_ref": route_refs.get("market_feed"),
            "kind": str(data.get("market_feed_kind", "market_snapshot")),
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": bool(data.get("market_feed_replayable", True)),
            "cache_backed": bool(data.get("market_feed_cache_backed", False)),
            "readiness": dict(probes.get("market_feed") or {}).get("operational_status", "unavailable"),
            "auth_requirement": "none",
            "session_requirement": "none",
            "preview_only": False,
            "gap_class": "snapshot_only" if bool(data.get("market_feed_cache_backed", False)) else "poll_only_surface",
            "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
            "endpoint_contract": {
                "method": "GET",
                "route_ref": route_refs.get("market_feed"),
                "request_mode": "pull",
                "response_kind": "market_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "user_feed": {
            "mode": "read_only",
            "transport": _feed_surface_transport_name(data.get("user_feed_transport")),
            "connector": str(data.get("user_feed_connector", "unavailable")),
            "route_ref": route_refs.get("user_feed"),
            "kind": str(data.get("user_feed_kind", "position_snapshot")),
            "supports_live": False,
            "supports_write": False,
            "subscription_capable": False,
            "replayable": bool(data.get("user_feed_replayable", False)),
            "cache_backed": bool(data.get("user_feed_cache_backed", False)),
            "readiness": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
            "auth_requirement": "none",
            "session_requirement": "local_cache_context" if bool(data.get("user_feed_cache_backed", False)) else "none",
            "preview_only": False,
            "gap_class": "cache_proxy" if bool(data.get("user_feed_cache_backed", False)) else "user_feed_not_bound",
            "auth_session": {
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if bool(data.get("user_feed_cache_backed", False)) else "none",
            },
            "endpoint_contract": {
                "method": "GET",
                "route_ref": route_refs.get("user_feed"),
                "request_mode": "pull",
                "response_kind": "position_snapshot",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_market": {
            "mode": "live_bound" if live_market_bound else "preview_only",
            "transport": "websocket",
            "connector": str(data.get("market_websocket_connector", "unavailable")),
            "route_ref": route_refs.get("market_websocket"),
            "kind": "market_stream",
            "supports_live": bool(live_market_bound),
            "supports_write": False,
            "subscription_capable": bool(live_market_bound),
            "replayable": False,
            "cache_backed": False,
            "readiness": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "none",
            "session_requirement": "live_socket" if live_market_bound else "preview_only",
            "preview_only": not live_market_bound,
            "gap_class": "live_bound" if live_market_bound else "not_bound",
            "auth_session": {"auth_requirement": "none", "session_requirement": "live_socket" if live_market_bound else "preview_only"},
            "endpoint_contract": {
                "method": "SUBSCRIBE" if live_market_bound else "PREVIEW_ONLY",
                "route_ref": route_refs.get("market_websocket"),
                "request_mode": "live_subscribe" if live_market_bound else "preview_only",
                "response_kind": "market_stream" if live_market_bound else "market_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "websocket_user": {
            "mode": "live_bound" if live_user_bound and live_user_auth_configured else "preview_only",
            "transport": "websocket",
            "connector": str(data.get("user_websocket_connector", "unavailable")),
            "route_ref": route_refs.get("user_websocket"),
            "kind": "user_stream",
            "supports_live": bool(live_user_bound and live_user_auth_configured),
            "supports_write": False,
            "subscription_capable": bool(live_user_bound and live_user_auth_configured),
            "replayable": False,
            "cache_backed": False,
            "readiness": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "api_credentials" if live_user_auth_configured else "api_credentials_required",
            "session_requirement": "live_socket" if live_user_bound and live_user_auth_configured else "preview_only",
            "preview_only": not (live_user_bound and live_user_auth_configured),
            "gap_class": "live_bound" if live_user_bound and live_user_auth_configured else ("auth_required" if live_user_bound else "not_bound"),
            "auth_session": {"auth_requirement": "api_credentials" if live_user_auth_configured else "api_credentials_required", "session_requirement": "live_socket" if live_user_bound and live_user_auth_configured else "preview_only"},
            "endpoint_contract": {
                "method": "SUBSCRIBE" if live_user_bound and live_user_auth_configured else "PREVIEW_ONLY",
                "route_ref": route_refs.get("user_websocket"),
                "request_mode": "live_subscribe" if live_user_bound and live_user_auth_configured else "preview_only",
                "response_kind": "user_stream" if live_user_bound and live_user_auth_configured else "user_stream_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "rtds": {
            "mode": "live_bound" if live_rtds_bound else "preview_only",
            "transport": "rtds",
            "connector": str(data.get("rtds_connector", "unavailable")),
            "route_ref": route_refs.get("rtds"),
            "kind": "rtds",
            "supports_live": bool(live_rtds_bound),
            "supports_write": False,
            "subscription_capable": bool(live_rtds_bound),
            "replayable": bool(data.get("rtds_replayable", False)),
            "cache_backed": bool(data.get("rtds_cache_backed", False)),
            "readiness": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
            "auth_requirement": "gamma_auth" if live_rtds_bound else "not_bound",
            "session_requirement": "live_socket" if live_rtds_bound else "preview_only",
            "preview_only": not live_rtds_bound,
            "gap_class": "live_bound" if live_rtds_bound else "not_bound",
            "auth_session": {"auth_requirement": "gamma_auth" if live_rtds_bound else "not_bound", "session_requirement": "live_socket" if live_rtds_bound else "preview_only"},
            "endpoint_contract": {
                "method": "SUBSCRIBE" if live_rtds_bound else "PREVIEW_ONLY",
                "route_ref": route_refs.get("rtds"),
                "request_mode": "live_subscribe" if live_rtds_bound else "preview_only",
                "response_kind": "rtds_stream" if live_rtds_bound else "rtds_preview",
                "read_only": True,
                "write_capable": False,
            },
        },
        "documented_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "none" if live_market_bound else "not_bound",
            "websocket_user": "api_credentials" if live_user_auth_configured else ("api_credentials_required" if live_user_bound else "not_bound"),
            "rtds": "gamma_auth" if live_rtds_bound else "not_bound",
        },
        "session_requirements": {
            "market_feed": "none",
            "user_feed": "local_cache_context" if bool(data.get("user_feed_cache_backed", False)) else "none",
            "websocket_market": "live_socket" if live_market_bound else "preview_only",
            "websocket_user": "live_socket" if live_user_bound and live_user_auth_configured else "preview_only",
            "rtds": "live_socket" if live_rtds_bound else "preview_only",
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(data.get("user_feed_cache_backed", False)) else "user_feed_not_bound",
        ]
        + ([] if live_market_bound else ["websocket_market_not_bound"])
        + ([] if live_user_bound and live_user_auth_configured else (["websocket_user_not_bound"] if not live_user_bound else ["websocket_user_auth_required"]))
        + ([] if live_rtds_bound else ["rtds_not_bound"]),
        "replay_fallbacks": {
            "market_feed": "cache_fallback" if bool(data.get("market_feed_cache_backed", False)) else "poll_snapshot_route",
            "user_feed": "cache_fallback" if bool(data.get("user_feed_cache_backed", False)) else "poll_snapshot_route",
            "websocket_market": "live_socket" if live_market_bound else "no_live_binding",
            "websocket_user": "live_socket" if live_user_bound and live_user_auth_configured else "no_live_binding",
            "rtds": "live_socket" if live_rtds_bound else "no_live_binding",
        },
    }


def _feed_surface_preview_flow(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or {})
    probes = dict(data.get("availability_probes") or {})
    contracts = dict(data.get("connector_contracts") or {})
    venue_obj = data.get("venue")
    venue_name = venue_obj.value if isinstance(venue_obj, VenueName) else str(venue_obj or "venue")
    live_binding = dict(data.get("live_websocket_binding") or {})
    live_bound = bool(live_binding.get("market_websocket_url") or live_binding.get("user_websocket_url") or live_binding.get("rtds_url"))
    return {
        "flow_id": f"{venue_name}:{'live_websocket_rtds' if live_bound else 'bounded_websocket_rtds_preview'}",
        "mode": "live_bound" if live_bound else "preview_only",
        "testable": True,
        "live_claimed": live_bound,
        "route_refs": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "steps": [
            {
                "step": "resolve_routes",
                "status": "complete",
                "documented_route_refs": {
                    "market_feed": route_refs.get("market_feed"),
                    "user_feed": route_refs.get("user_feed"),
                    "market_websocket": route_refs.get("market_websocket"),
                    "user_websocket": route_refs.get("user_websocket"),
                    "rtds": route_refs.get("rtds"),
                },
            },
            {
                "step": "confirm_auth_and_session",
                "status": "complete",
                "auth_requirements": dict(contracts.get("auth_requirements") or {}),
                "session_requirements": dict(contracts.get("session_requirements") or {}),
            },
            {
                "step": "select_preview_fallbacks",
                "status": "complete",
                "preview_targets": {
                    "market_feed": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
                    "user_feed": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
                    "websocket_market": dict(probes.get("websocket_market") or {}).get("recommended_action", "do_not_assume_live_websocket"),
                    "websocket_user": dict(probes.get("websocket_user") or {}).get("recommended_action", "do_not_assume_live_websocket"),
                    "rtds": dict(probes.get("rtds") or {}).get("recommended_action", "do_not_assume_rtds"),
                },
            },
        ],
        "bounded_channels": ["websocket_market", "websocket_user", "rtds"],
        "preview_only_channels": [] if live_bound else ["websocket_market", "websocket_user", "rtds"],
        "probe_statuses": {
            "websocket_market": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
            "websocket_user": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
            "rtds": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
        },
        "expected_outcome": "live_bound_transport" if live_bound else "preview_only_no_live_transport",
    }


def _feed_surface_subscription_preview(data: dict[str, Any]) -> dict[str, Any]:
    route_refs = dict(data.get("route_refs") or {})
    probes = dict(data.get("availability_probes") or {})
    contracts = dict(data.get("connector_contracts") or {})
    preview_flow = _feed_surface_preview_flow(data)
    live_binding = dict(data.get("live_websocket_binding") or {})
    live_bound = bool(live_binding.get("market_websocket_url") or live_binding.get("user_websocket_url") or live_binding.get("rtds_url"))
    gap_summary = {
        "live_transport_supported": bool(data.get("supports_websocket", False) or data.get("supports_rtds", False)),
        "live_transport_ready_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "ready"
        ),
        "live_transport_not_supported_count": sum(
            1 for key in ("websocket_market", "websocket_user", "rtds") if dict(probes.get(key) or {}).get("operational_status") == "not_supported"
        ),
        "preview_only_channel_count": 0 if live_bound else 3,
        "cache_backed_channel_count": sum(
            1 for key in ("market_feed", "user_feed") if bool(dict(probes.get(key) or {}).get("cache_backed", False))
        ),
        "documented_preview_routes": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "market_websocket": route_refs.get("market_websocket"),
            "user_websocket": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "live_transport_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("websocket_market", "websocket_user", "rtds")
        },
        "cache_backed_gap_reasons": {
            key: dict(probes.get(key) or {}).get("gap_reason")
            for key in ("market_feed", "user_feed")
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(dict(probes.get("user_feed") or {}).get("cache_backed", False)) else "user_feed_not_bound",
        ]
        + ([] if live_bound else ["websocket_market_not_bound", "websocket_user_not_bound", "rtds_not_bound"]),
    }
    gap_summary["explicit_gaps"] = [gap for gap in gap_summary["explicit_gaps"] if gap]
    recommended_subscriptions = [
        {
            "channel": key,
            "intent": channel.get("subscription_intent"),
            "route_ref": channel.get("route_ref"),
            "recommended_action": channel.get("recommended_action"),
        }
        for key, channel in {
            "market_feed": {
                "subscription_intent": "poll_snapshot",
                "route_ref": route_refs.get("market_feed"),
                "recommended_action": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
            },
            "user_feed": {
                "subscription_intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "route_ref": route_refs.get("user_feed"),
                "recommended_action": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
            },
            "websocket_market": {
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "route_ref": route_refs.get("market_websocket"),
                "recommended_action": "open_live_websocket" if live_bound else "do_not_assume_live_websocket",
            },
            "websocket_user": {
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "route_ref": route_refs.get("user_websocket"),
                "recommended_action": "open_live_websocket" if live_bound else "do_not_assume_live_websocket",
            },
            "rtds": {
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "route_ref": route_refs.get("rtds"),
                "recommended_action": "open_live_rtds" if live_bound else "do_not_assume_rtds",
            },
        }.items()
    ]
    return {
        "mode": "live_bound" if live_bound else "preview_only",
        "supports_live_subscriptions": live_bound,
        "recommended_poll_transport": _feed_surface_transport_name(data.get("market_feed_transport")),
        "recommended_user_transport": _feed_surface_transport_name(data.get("user_feed_transport")),
        "auth_requirements": dict(contracts.get("auth_requirements") or {}),
        "session_requirements": dict(contracts.get("session_requirements") or {}),
        "channels": {
            "market_feed": {
                "topic": f"{data.get('venue', 'venue')}:market_feed",
                "route_ref": route_refs.get("market_feed"),
                "status": dict(probes.get("market_feed") or {}).get("operational_status", "unavailable"),
                "subscription_capable": False,
                "recommended_action": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
                "subscription_intent": "poll_snapshot",
                "auth_requirement": "none",
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "market_snapshot",
                    "cadence_hint": "poll_on_schedule",
                },
            },
            "user_feed": {
                "topic": f"{data.get('venue', 'venue')}:user_feed",
                "route_ref": route_refs.get("user_feed"),
                "status": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
                "subscription_capable": False,
                "recommended_action": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
                "subscription_intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "auth_requirement": "none",
                "channel_spec": {
                    "delivery_mode": "pull",
                    "message_kind": "position_snapshot",
                    "cadence_hint": "poll_or_cache_read",
                },
            },
            "websocket_market": {
                "topic": f"{data.get('venue', 'venue')}:websocket_market",
                "route_ref": route_refs.get("market_websocket"),
                "status": dict(probes.get("websocket_market") or {}).get("operational_status", "not_supported"),
                "subscription_capable": live_bound,
                "recommended_action": "open_live_websocket" if live_bound else "do_not_assume_live_websocket",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "auth_requirement": "none",
                "channel_spec": {
                    "delivery_mode": "push" if live_bound else "preview_only",
                    "message_kind": "market_stream" if live_bound else "market_stream_preview",
                    "cadence_hint": "heartbeat_10s" if live_bound else "none",
                },
            },
            "websocket_user": {
                "topic": f"{data.get('venue', 'venue')}:websocket_user",
                "route_ref": route_refs.get("user_websocket"),
                "status": dict(probes.get("websocket_user") or {}).get("operational_status", "not_supported"),
                "subscription_capable": live_bound and bool(probes.get("websocket_user")),
                "recommended_action": "open_live_websocket" if live_bound else "do_not_assume_live_websocket",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "auth_requirement": "api_credentials" if live_bound else "not_bound",
                "channel_spec": {
                    "delivery_mode": "push" if live_bound else "preview_only",
                    "message_kind": "user_stream" if live_bound else "user_stream_preview",
                    "cadence_hint": "heartbeat_10s" if live_bound else "none",
                },
            },
            "rtds": {
                "topic": f"{data.get('venue', 'venue')}:rtds",
                "route_ref": route_refs.get("rtds"),
                "status": dict(probes.get("rtds") or {}).get("operational_status", "not_supported"),
                "subscription_capable": live_bound,
                "recommended_action": "open_live_rtds" if live_bound else "do_not_assume_rtds",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "auth_requirement": "gamma_auth" if live_bound else "not_bound",
                "channel_spec": {
                    "delivery_mode": "push" if live_bound else "preview_only",
                    "message_kind": "rtds_stream" if live_bound else "rtds_preview",
                    "cadence_hint": "heartbeat_5s" if live_bound else "none",
                },
            },
        },
        "channel_specs": {
            "market_feed": {
                "route_ref": route_refs.get("market_feed"),
                "delivery_mode": "pull",
                "message_kind": "market_snapshot",
                "auth_requirement": "none",
                "session_requirement": "none",
                "subscription_intent": "poll_snapshot",
                "preview_probe": dict(probes.get("market_feed") or {}),
                "replay_fallback": dict((data.get("cache_fallbacks") or {}).get("market_feed") or {}),
                "explicit_gap": "snapshot_only_no_push",
                "gap_class": dict(probes.get("market_feed") or {}).get("gap_class"),
                "auth_session": {"auth_requirement": "none", "session_requirement": "none"},
            },
            "user_feed": {
                "route_ref": route_refs.get("user_feed"),
                "delivery_mode": "pull",
                "message_kind": "position_snapshot",
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if bool(contracts.get("user_feed", {}).get("cache_backed", False)) else "none",
                "subscription_intent": "read_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "poll_snapshot",
                "preview_probe": dict(probes.get("user_feed") or {}),
                "replay_fallback": dict((data.get("cache_fallbacks") or {}).get("user_feed") or {}),
                "explicit_gap": "user_feed_proxy_cache" if dict(probes.get("user_feed") or {}).get("cache_backed") else "no_user_feed_binding",
                "gap_class": dict(probes.get("user_feed") or {}).get("gap_class"),
                "auth_session": {
                    "auth_requirement": "none",
                    "session_requirement": "local_cache_context" if bool(contracts.get("user_feed", {}).get("cache_backed", False)) else "none",
                },
            },
            "websocket_market": {
                "route_ref": route_refs.get("market_websocket"),
                "delivery_mode": "push" if live_bound else "preview_only",
                "message_kind": "market_stream" if live_bound else "market_stream_preview",
                "auth_requirement": "none",
                "session_requirement": "live_socket" if live_bound else "preview_only",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "preview_probe": dict(probes.get("websocket_market") or {}),
                "replay_fallback": "live_socket" if live_bound else "no_live_binding",
                "explicit_gap": None if live_bound else "live_websocket_not_bound",
                "gap_class": dict(probes.get("websocket_market") or {}).get("gap_class"),
                "auth_session": {"auth_requirement": "none", "session_requirement": "live_socket" if live_bound else "preview_only"},
            },
            "websocket_user": {
                "route_ref": route_refs.get("user_websocket"),
                "delivery_mode": "push" if live_bound else "preview_only",
                "message_kind": "user_stream" if live_bound else "user_stream_preview",
                "auth_requirement": "api_credentials" if live_bound else "not_bound",
                "session_requirement": "live_socket" if live_bound else "preview_only",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "preview_probe": dict(probes.get("websocket_user") or {}),
                "replay_fallback": "live_socket" if live_bound else "no_live_binding",
                "explicit_gap": None if live_bound else "live_user_feed_not_bound",
                "gap_class": dict(probes.get("websocket_user") or {}).get("gap_class"),
                "auth_session": {"auth_requirement": "api_credentials" if live_bound else "not_bound", "session_requirement": "live_socket" if live_bound else "preview_only"},
            },
            "rtds": {
                "route_ref": route_refs.get("rtds"),
                "delivery_mode": "push" if live_bound else "preview_only",
                "message_kind": "rtds_stream" if live_bound else "rtds_preview",
                "auth_requirement": "gamma_auth" if live_bound else "not_bound",
                "session_requirement": "live_socket" if live_bound else "preview_only",
                "subscription_intent": "live_subscribe" if live_bound else "preview_only",
                "preview_probe": dict(probes.get("rtds") or {}),
                "replay_fallback": "live_socket" if live_bound else "no_live_binding",
                "explicit_gap": None if live_bound else "rtds_not_bound",
                "gap_class": dict(probes.get("rtds") or {}).get("gap_class"),
                "auth_session": {"auth_requirement": "gamma_auth" if live_bound else "not_bound", "session_requirement": "live_socket" if live_bound else "preview_only"},
            },
        },
        "subscription_bundles": {
            "poll_snapshot_bundle": {
                "bundle_id": f"{data.get('venue', 'venue')}:poll_snapshot_bundle",
                "channels": ["market_feed", "user_feed"],
                "route_refs": {
                    "market_feed": route_refs.get("market_feed"),
                    "user_feed": route_refs.get("user_feed"),
                },
                "auth_requirement": "none",
                "session_requirement": "local_cache_context" if bool(contracts.get("user_feed", {}).get("cache_backed", False)) else "none",
                "preview_only": False,
                "testable": True,
            },
            "websocket_preview_bundle": {
                "bundle_id": f"{data.get('venue', 'venue')}:websocket_live_bundle" if live_bound else f"{data.get('venue', 'venue')}:websocket_preview_bundle",
                "channels": ["websocket_market", "websocket_user"],
                "route_refs": {
                    "market_websocket": route_refs.get("market_websocket"),
                    "user_websocket": route_refs.get("user_websocket"),
                },
                "auth_requirement": "api_credentials" if live_bound else "not_bound",
                "session_requirement": "live_socket" if live_bound else "preview_only",
                "preview_only": not live_bound,
                "testable": True,
            },
            "rtds_preview_bundle": {
                "bundle_id": f"{data.get('venue', 'venue')}:rtds_live_bundle" if live_bound else f"{data.get('venue', 'venue')}:rtds_preview_bundle",
                "channels": ["rtds"],
                "route_refs": {"rtds": route_refs.get("rtds")},
                "auth_requirement": "gamma_auth" if live_bound else "not_bound",
                "session_requirement": "live_socket" if live_bound else "preview_only",
                "preview_only": not live_bound,
                "testable": True,
            },
        },
        "preview_flow": preview_flow,
        "gap_summary": gap_summary,
        "auth_required_any": False,
        "channel_count": 5,
        "recommended_subscriptions": recommended_subscriptions,
        "documented_channel_route_refs": {
            "market_feed": route_refs.get("market_feed"),
            "user_feed": route_refs.get("user_feed"),
            "websocket_market": route_refs.get("market_websocket"),
            "websocket_user": route_refs.get("user_websocket"),
            "rtds": route_refs.get("rtds"),
        },
        "explicit_gaps": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if dict(probes.get("user_feed") or {}).get("cache_backed") else "user_feed_not_bound",
        ]
        + ([] if live_bound else ["websocket_market_not_bound", "websocket_user_not_bound", "rtds_not_bound"]),
        "replay_fallbacks": {
            "market_feed": dict((data.get("cache_fallbacks") or {}).get("market_feed") or {}),
            "user_feed": dict((data.get("cache_fallbacks") or {}).get("user_feed") or {}),
            "websocket_market": "live_socket" if live_bound else "no_live_binding",
            "websocket_user": "live_socket" if live_bound else "no_live_binding",
            "rtds": "live_socket" if live_bound else "no_live_binding",
        },
    }


def _feed_surface_probe_bundle(data: dict[str, Any]) -> dict[str, Any]:
    probes = dict(data.get("availability_probes") or {})
    cache_fallbacks = dict(data.get("cache_fallbacks") or {})
    preview_flow = dict((data.get("subscription_preview") or {}).get("preview_flow") or _feed_surface_preview_flow(data))
    operational_statuses = [str(dict(probe or {}).get("operational_status", "unavailable")) for probe in probes.values()]
    severity_counts = {"info": 0, "warning": 0, "error": 0}
    for probe in probes.values():
        severity = str(dict(probe or {}).get("severity", "info"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    ready_count = sum(status == "ready" for status in operational_statuses)
    not_supported_count = sum(status == "not_supported" for status in operational_statuses)
    unavailable_count = sum(status == "unavailable" for status in operational_statuses)
    primary_probe = dict(probes.get("market_feed") or {})
    fallback_probe = dict(cache_fallbacks.get("market_feed") or {})
    return {
        "bundle_status": "ready" if ready_count else "degraded",
        "probe_count": len(probes),
        "ready_count": ready_count,
        "not_supported_count": not_supported_count,
        "unavailable_count": unavailable_count,
        "primary_path": primary_probe.get("recommended_action", "poll_snapshot_route"),
        "fallback_path": fallback_probe.get("recommended_action", "no_cache_fallback"),
        "market_feed_status": primary_probe.get("operational_status", "unavailable"),
        "user_feed_status": dict(probes.get("user_feed") or {}).get("operational_status", "unavailable"),
        "transport_readiness": {
            key: dict(probe or {}).get("operational_status", "unavailable")
            for key, probe in probes.items()
        },
        "degraded_paths": [
            key
            for key, probe in probes.items()
            if dict(probe or {}).get("operational_status", "unavailable") != "ready"
        ],
        "preview_flow": preview_flow,
        "gap_summary": _feed_surface_gap_summary(data),
        "recovered_from_partial_probes": bool(data.get("recovered_from_partial_probes", False)),
        "severity_counts": severity_counts,
        "highest_severity": "error" if severity_counts.get("error") else ("warning" if severity_counts.get("warning") else "info"),
    }


def _feed_surface_capability_summary(data: dict[str, Any]) -> dict[str, Any]:
    probes = dict(data.get("availability_probes") or {})
    preview_flow = dict((data.get("subscription_preview") or {}).get("preview_flow") or _feed_surface_preview_flow(data))
    return {
        "mode": "live_bound" if bool(data.get("live_websocket_binding")) else "read_only",
        "live_claimed": bool(data.get("live_websocket_binding")),
        "subscription_mode": "live_bound" if bool(data.get("live_websocket_binding")) else "preview_only",
        "market_feed_path": dict(probes.get("market_feed") or {}).get("recommended_action", "poll_snapshot_route"),
        "user_feed_path": dict(probes.get("user_feed") or {}).get("recommended_action", "treat_as_unavailable"),
        "websocket_path": dict(probes.get("websocket_market") or {}).get("recommended_action", "open_live_websocket" if bool(data.get("live_websocket_binding")) else "do_not_assume_live_websocket"),
        "rtds_path": dict(probes.get("rtds") or {}).get("recommended_action", "open_live_rtds" if bool(data.get("live_websocket_binding")) else "do_not_assume_rtds"),
        "has_replayable_market_feed": bool(data.get("market_feed_replayable", True)),
        "has_cache_fallback": bool(data.get("market_feed_cache_backed", False) or data.get("user_feed_cache_backed", False)),
        "auth_requirements": {
            "market_feed": "none",
            "user_feed": "none",
            "websocket_market": "none" if bool(data.get("live_websocket_binding")) else "not_bound",
            "websocket_user": "api_credentials" if bool(data.get("live_websocket_binding")) else "not_bound",
            "rtds": "gamma_auth" if bool(data.get("live_websocket_binding")) else "not_bound",
        },
        "market_user_gap_reasons": [
            "market_feed_is_snapshot_only",
            "user_feed_is_cache_proxy" if bool(data.get("user_feed_cache_backed", False)) else "user_feed_not_bound",
        ],
        "explicit_gaps": [] if bool(data.get("live_websocket_binding")) else [
            "websocket_market_not_bound",
            "websocket_user_not_bound",
            "rtds_not_bound",
        ],
        "rtds_usefulness": {
            "status": "live_bound" if bool(data.get("live_websocket_binding")) else "preview_only",
            "usable_for_live_ops": bool(data.get("live_websocket_binding")),
            "recommended_action": dict(probes.get("rtds") or {}).get("recommended_action", "open_live_rtds" if bool(data.get("live_websocket_binding")) else "do_not_assume_rtds"),
        },
        "gap_summary": _feed_surface_gap_summary(data),
        "recommended_subscriptions": [
            "market_feed",
            "user_feed",
        ]
        + (["websocket_market", "websocket_user", "rtds"] if bool(data.get("live_websocket_binding")) else []),
        "documented_preview_routes": {
            "market_websocket": dict(data.get("route_refs") or {}).get("market_websocket"),
            "user_websocket": dict(data.get("route_refs") or {}).get("user_websocket"),
            "rtds": dict(data.get("route_refs") or {}).get("rtds"),
        },
        "preview_flow": preview_flow,
    }


def _feed_surface_degradation(data: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    ingestion_mode = str(data.get("ingestion_mode", "")).strip().lower()
    if ingestion_mode.startswith("read_only"):
        reasons.append("read_only_ingestion")
    if not bool(data.get("supports_websocket", False)):
        reasons.append("no_websocket_live_integration")
    if not bool(data.get("supports_rtds", False)):
        reasons.append("no_rtds_live_integration")
    metadata_gap_rate = _safe_non_negative_float(data.get("metadata_gap_rate")) or 0.0
    if metadata_gap_rate > 0:
        reasons.append("metadata_gap")
    if str(data.get("market_feed_status", "")).strip().lower() in {"local_cache", "unavailable"}:
        reasons.append("market_feed_degraded")
    if str(data.get("user_feed_status", "")).strip().lower() in {"local_cache", "unavailable"}:
        reasons.append("user_feed_degraded")
    if not bool(data.get("supports_market_feed", False)):
        reasons.append("market_feed_unavailable")
    if not bool(data.get("supports_user_feed", False)):
        reasons.append("user_feed_unavailable")
    return bool(reasons), list(dict.fromkeys(reasons))


def _health_score(
    *,
    healthy: bool,
    stream_status: str,
    freshness_status: str,
    issue_count: int,
    maintenance_mode: bool,
    desync_detected: bool,
) -> float:
    score = 1.0
    if not healthy:
        score -= 0.2
    if maintenance_mode:
        score -= 0.35
    if desync_detected:
        score -= 0.25
    if freshness_status == "warm":
        score -= 0.08
    elif freshness_status == "stale":
        score -= 0.25
    elif freshness_status == "maintenance":
        score -= 0.3
    if stream_status == "degraded":
        score -= 0.1
    elif stream_status == "desynced":
        score -= 0.18
    score -= min(0.2, 0.03 * max(0, issue_count))
    return round(max(0.0, min(1.0, score)), 3)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if percentile <= 0:
        return round(min(values), 3)
    if percentile >= 100:
        return round(max(values), 3)
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    weight = rank - lower
    value = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(value, 3)


def _manifest_feed_surface(
    manifest: MarketStreamManifest,
    *,
    venue: VenueName,
    backend_mode: str | None,
    supports_events: bool,
    supports_positions: bool,
) -> MarketFeedSurface:
    surface = manifest.metadata.get("data_surface")
    if surface is not None:
        return _normalize_feed_surface(
            surface,
            venue=venue,
            backend_mode=backend_mode or str(manifest.metadata.get("backend_mode", "unknown")),
            supports_events=supports_events,
            supports_positions=supports_positions,
        )
    return _default_feed_surface(
        venue=venue,
        backend_mode=backend_mode or str(manifest.metadata.get("backend_mode", "unknown")),
        supports_events=supports_events,
        supports_positions=supports_positions,
        events_source="snapshot_polling",
        positions_source="local_position_cache",
        market_feed_source="snapshot_polling",
        user_feed_source="local_position_cache",
    )


def _health_runbook(
    *,
    manifest: MarketStreamManifest,
    feed_surface: MarketFeedSurface,
    issues: list[str],
    maintenance_mode: bool,
    desync_detected: bool,
) -> dict[str, Any]:
    if maintenance_mode:
        return {
            "runbook_id": "stream_maintenance",
            "runbook_kind": "incident",
            "summary": "Stream is in maintenance mode.",
            "recommended_action": "stay_read_only",
            "status": "blocked",
            "next_steps": [
                "Keep the stream read-only while maintenance is active.",
                "Do not infer live state from the feed surface.",
            ],
            "signals": {
                "issues": list(issues),
                "maintenance_mode": True,
                "desync_detected": desync_detected,
                "feed_surface_status": feed_surface.ingestion_mode,
                "feed_surface_summary": feed_surface.summary,
                "feed_surface_degraded": feed_surface.degraded,
                "feed_surface_degraded_reasons": list(feed_surface.degraded_reasons),
            },
        }
    if "stream_stale" in issues or "snapshot_stale" in issues:
        return {
            "runbook_id": "stream_stale",
            "runbook_kind": "incident",
            "summary": "Stream data is stale and should be refreshed before use.",
            "recommended_action": "refresh_snapshot",
            "status": "blocked" if desync_detected else "degraded",
            "next_steps": [
                "Poll a fresh market snapshot.",
                "Check source freshness and cache age.",
                "Keep the surface read-only until the stream recovers.",
            ],
            "signals": {
                "issues": list(issues),
                "maintenance_mode": False,
                "desync_detected": desync_detected,
                "latest_sequence": manifest.latest_sequence,
                "feed_surface_status": feed_surface.ingestion_mode,
                "feed_surface_degraded": feed_surface.degraded,
                "feed_surface_degraded_reasons": list(feed_surface.degraded_reasons),
            },
        }
    if desync_detected:
        return {
            "runbook_id": "stream_desync",
            "runbook_kind": "incident",
            "summary": "Manifest and event sequence are out of sync.",
            "recommended_action": "rebuild_stream_manifest",
            "status": "blocked",
            "next_steps": [
                "Rebuild the manifest from the latest canonical snapshot.",
                "Compare observed snapshot ids and event counts.",
                "Use only read-only data until the stream is realigned.",
            ],
            "signals": {
                "issues": list(issues),
                "maintenance_mode": False,
                "desync_detected": True,
                "latest_sequence": manifest.latest_sequence,
                "feed_surface_status": feed_surface.ingestion_mode,
                "feed_surface_degraded": feed_surface.degraded,
                "feed_surface_degraded_reasons": list(feed_surface.degraded_reasons),
            },
        }
    return {
        "runbook_id": "stream_health_ok",
        "runbook_kind": "ok",
        "summary": "Stream is healthy and read-only data surfaces are consistent.",
        "recommended_action": "continue_polling",
        "status": "ready",
        "next_steps": [
            "Continue polling snapshots and cache-backed user positions.",
            "Keep websocket/RTDS expectations disabled unless a client explicitly supports them.",
        ],
            "signals": {
                "issues": list(issues),
                "maintenance_mode": False,
                "desync_detected": False,
                "feed_surface_status": feed_surface.ingestion_mode,
                "feed_surface_degraded": feed_surface.degraded,
                "feed_surface_degraded_reasons": list(feed_surface.degraded_reasons),
            },
        }


class MarketStreamingStore:
    def __init__(self, paths: MarketStreamPaths | PredictionMarketPaths | None = None) -> None:
        if isinstance(paths, PredictionMarketPaths):
            self.paths = MarketStreamPaths.from_prediction_paths(paths)
        else:
            self.paths = paths or MarketStreamPaths.from_prediction_paths()
        self.paths.ensure_layout()

    def create_manifest(self, descriptor: MarketDescriptor, *, stream_id: str | None = None) -> MarketStreamManifest:
        manifest = MarketStreamManifest(
            stream_id=stream_id or self.new_stream_id(descriptor.market_id),
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            market_title=descriptor.title,
            market_slug=descriptor.slug,
        )
        self.save_manifest(manifest)
        self.save_descriptor(manifest.stream_id, descriptor)
        return manifest

    def load_manifest(self, stream_id: str) -> MarketStreamManifest:
        return MarketStreamManifest.model_validate_json(self.paths.manifest_path(stream_id).read_text(encoding="utf-8"))

    def save_manifest(self, manifest: MarketStreamManifest) -> Path:
        stream_dir = self.paths.stream_dir(manifest.stream_id)
        stream_dir.mkdir(parents=True, exist_ok=True)
        path = self.paths.manifest_path(manifest.stream_id)
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_descriptor(self, stream_id: str, descriptor: MarketDescriptor) -> Path:
        path = self.paths.descriptor_path(stream_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(descriptor.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_descriptor(self, stream_id: str) -> MarketDescriptor:
        return MarketDescriptor.model_validate_json(self.paths.descriptor_path(stream_id).read_text(encoding="utf-8"))

    def append_event(self, event: MarketStreamEvent) -> MarketStreamEvent:
        stream_dir = self.paths.stream_dir(event.stream_id)
        stream_dir.mkdir(parents=True, exist_ok=True)
        event_path = self.paths.events_path(event.stream_id)
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json())
            handle.write("\n")
        self.save_snapshot(event.stream_id, event.snapshot)
        self._update_manifest(event)
        return event

    def load_events(self, stream_id: str) -> list[MarketStreamEvent]:
        event_path = self.paths.events_path(stream_id)
        if not event_path.exists():
            return []
        events: list[MarketStreamEvent] = []
        for line in event_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(MarketStreamEvent.model_validate_json(line))
        return events

    def load_latest_snapshot(self, stream_id: str) -> MarketSnapshot | None:
        path = self.paths.latest_snapshot_path(stream_id)
        if not path.exists():
            return None
        return MarketSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def save_snapshot(self, stream_id: str, snapshot: MarketSnapshot) -> Path:
        path = self.paths.latest_snapshot_path(stream_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        return path

    def list_manifests(self) -> list[MarketStreamManifest]:
        if not self.paths.root.exists():
            return []
        manifests: list[MarketStreamManifest] = []
        for path in sorted(self.paths.root.glob("*/manifest.json")):
            manifests.append(MarketStreamManifest.model_validate_json(path.read_text(encoding="utf-8")))
        return manifests

    def find_manifests(
        self,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        venue: VenueName | None = None,
    ) -> list[MarketStreamManifest]:
        manifests = self.list_manifests()
        if market_id is not None:
            manifests = [manifest for manifest in manifests if manifest.market_id == market_id]
        if slug is not None:
            manifests = [manifest for manifest in manifests if manifest.market_slug == slug]
        if venue is not None:
            manifests = [manifest for manifest in manifests if manifest.venue == venue]
        return manifests

    def find_latest_manifest(
        self,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        venue: VenueName | None = None,
    ) -> MarketStreamManifest | None:
        manifests = self.find_manifests(market_id=market_id, slug=slug, venue=venue)
        if not manifests:
            return None
        return max(manifests, key=lambda manifest: (manifest.updated_at, manifest.created_at, manifest.latest_sequence))

    def load_collection_cache(self, cache_key: str, *, cache_ttl_seconds: float) -> MarketStreamCollectionCacheEntry | None:
        path = self.paths.collection_cache_path(cache_key)
        if not path.exists():
            return None
        entry = MarketStreamCollectionCacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
        age_seconds = _age_seconds(entry.cached_at)
        if age_seconds is None or age_seconds > cache_ttl_seconds:
            return None
        return entry

    def save_collection_cache(self, entry: MarketStreamCollectionCacheEntry) -> Path:
        path = self.paths.collection_cache_path(entry.cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return path

    def summarize_stream(self, stream_id: str) -> MarketStreamSummary:
        manifest = self.load_manifest(stream_id)
        events = self.load_events(stream_id)
        if not events:
            return MarketStreamSummary(
                stream_id=stream_id,
                market_id=manifest.market_id,
                venue=manifest.venue,
                market_title=manifest.market_title,
                market_slug=manifest.market_slug,
                event_count=0,
                poll_count=manifest.poll_count,
                latest_sequence=manifest.latest_sequence,
                narrative="No events recorded yet.",
                metadata=dict(manifest.metadata),
            )

        first_event = events[0]
        last_event = events[-1]
        price_yes_values = [event.snapshot.price_yes for event in events if event.snapshot.price_yes is not None]
        spread_values = [event.snapshot.spread_bps for event in events if event.snapshot.spread_bps is not None]
        change_events = [event for event in events if event.kind == StreamEventKind.change]
        changed_field_counts = Counter(field for event in change_events for field in event.changed_fields)
        age_seconds = _age_seconds(last_event.observed_at)
        price_yes_start = first_event.snapshot.price_yes
        price_yes_end = last_event.snapshot.price_yes
        spread_bps_start = first_event.snapshot.spread_bps
        spread_bps_end = last_event.snapshot.spread_bps
        price_yes_change = None
        if price_yes_start is not None and price_yes_end is not None:
            price_yes_change = round(price_yes_end - price_yes_start, 6)
        spread_bps_change = None
        if spread_bps_start is not None and spread_bps_end is not None:
            spread_bps_change = round(spread_bps_end - spread_bps_start, 2)

        trend = "stable"
        if price_yes_change is not None:
            if price_yes_change >= 0.03:
                trend = "bullish"
            elif price_yes_change <= -0.03:
                trend = "bearish"

        narrative = _build_stream_narrative(
            market_title=manifest.market_title or manifest.market_id,
            trend=trend,
            price_yes_change=price_yes_change,
            spread_bps_change=spread_bps_change,
            change_count=len(change_events),
            event_count=len(events),
        )
        return MarketStreamSummary(
            stream_id=stream_id,
            market_id=manifest.market_id,
            venue=manifest.venue,
            market_title=manifest.market_title,
            market_slug=manifest.market_slug,
            event_count=len(events),
            poll_count=manifest.poll_count,
            change_event_count=len(change_events),
            change_rate=round(len(change_events) / max(1, len(events) - 1), 3),
            latest_sequence=manifest.latest_sequence,
            first_observed_at=first_event.observed_at,
            last_observed_at=last_event.observed_at,
            age_seconds=age_seconds,
            price_yes_start=price_yes_start,
            price_yes_end=price_yes_end,
            price_yes_change=price_yes_change,
            spread_bps_start=spread_bps_start,
            spread_bps_end=spread_bps_end,
            spread_bps_change=spread_bps_change,
            average_price_yes=round(mean(price_yes_values), 6) if price_yes_values else None,
            average_spread_bps=round(mean(spread_values), 2) if spread_values else None,
            trend=trend,
            narrative=narrative,
            changed_field_counts=dict(sorted(changed_field_counts.items())),
            metadata=dict(manifest.metadata),
        )

    def health_report(self, stream_id: str, *, stale_after_seconds: float = 3600.0) -> MarketStreamHealth:
        manifest = self.load_manifest(stream_id)
        events = self.load_events(stream_id)
        feed_surface = _manifest_feed_surface(
            manifest,
            venue=manifest.venue,
            backend_mode=str(manifest.metadata.get("backend_mode", "unknown")),
            supports_events=True,
            supports_positions=True,
        )
        maintenance_mode = bool(
            manifest.metadata.get("maintenance_mode")
            or manifest.metadata.get("stream_maintenance")
            or manifest.metadata.get("venue_maintenance")
        )
        if not events:
            freshness_status = "maintenance" if maintenance_mode else "empty"
            issues = ["no_events"]
            if maintenance_mode:
                issues.append("maintenance_mode")
            incident_runbook = _health_runbook(
                manifest=manifest,
                feed_surface=feed_surface,
                issues=issues,
                maintenance_mode=maintenance_mode,
                desync_detected=False,
            )
            return MarketStreamHealth(
                stream_id=stream_id,
                market_id=manifest.market_id,
                venue=manifest.venue,
                healthy=False,
                stream_status="maintenance" if maintenance_mode else "degraded",
                freshness_status=freshness_status,
                message="Stream is in maintenance mode." if maintenance_mode else "No stream events recorded yet.",
                issues=issues,
                issue_count=len(issues),
                maintenance_mode=maintenance_mode,
                desync_detected=False,
                supports_websocket=bool(feed_surface.supports_websocket),
                supports_rtds=bool(feed_surface.supports_rtds),
                websocket_status=str(feed_surface.websocket_status),
                rtds_status=str(feed_surface.rtds_status),
                market_websocket_status=str(feed_surface.market_websocket_status),
                user_feed_websocket_status=str(feed_surface.user_feed_websocket_status),
                market_feed_status=str(feed_surface.market_feed_status),
                user_feed_status=str(feed_surface.user_feed_status),
                market_feed_replayable=bool(feed_surface.market_feed_replayable),
                user_feed_replayable=bool(feed_surface.user_feed_replayable),
                rtds_replayable=bool(feed_surface.rtds_replayable),
                latest_sequence=manifest.latest_sequence,
                event_count=0,
                poll_count=manifest.poll_count,
                snapshot_freshness_ms=None,
                health_score=_health_score(
                    healthy=False,
                    stream_status="maintenance" if maintenance_mode else "degraded",
                    freshness_status=freshness_status,
                    issue_count=len(issues),
                    maintenance_mode=maintenance_mode,
                    desync_detected=False,
                ),
                metadata_gap_count=feed_surface.metadata_gap_count,
                metadata_gap_rate=feed_surface.metadata_gap_rate,
                feed_surface_degraded=feed_surface.degraded,
                feed_surface_degraded_reasons=list(feed_surface.degraded_reasons),
                backend_mode=str(manifest.metadata.get("backend_mode", "unknown")),
                latest_snapshot_id=manifest.latest_snapshot_id,
                latest_snapshot_status=None,
                feed_surface=feed_surface,
                feed_surface_status=feed_surface.ingestion_mode,
                feed_surface_summary=feed_surface.summary,
                route_refs=dict(feed_surface.route_refs),
                availability_probes=dict(feed_surface.availability_probes),
                cache_fallbacks=dict(feed_surface.cache_fallbacks),
                subscription_preview=dict(feed_surface.subscription_preview),
                probe_bundle=dict(feed_surface.probe_bundle),
                capability_summary=dict(feed_surface.capability_summary),
                connector_contracts=dict(feed_surface.connector_contracts),
                incident_runbook=incident_runbook,
                metadata=dict(manifest.metadata),
            )

        last_event = events[-1]
        age_seconds = _age_seconds(last_event.observed_at)
        issues: list[str] = []
        freshness_status = "fresh"
        stream_status = "healthy"
        if age_seconds is not None and age_seconds > stale_after_seconds:
            issues.append("stream_stale")
            freshness_status = "stale"
            stream_status = "degraded"
        elif age_seconds is not None and age_seconds > stale_after_seconds / 2.0:
            freshness_status = "warm"
        if maintenance_mode:
            issues.append("maintenance_mode")
            freshness_status = "maintenance"
            stream_status = "maintenance"
        if manifest.event_count != len(events):
            issues.append("manifest_event_mismatch")
        if manifest.latest_sequence != events[-1].sequence:
            issues.append("sequence_mismatch")
        if last_event.snapshot.market_id != manifest.market_id:
            issues.append("snapshot_market_mismatch")
        if last_event.snapshot.staleness_ms is not None and last_event.snapshot.staleness_ms > stale_after_seconds * 1000.0:
            issues.append("snapshot_stale")
            freshness_status = "stale"
            stream_status = "degraded"
        if last_event.snapshot.status.value in {"cancelled"}:
            issues.append("market_cancelled")
        desync_detected = any(issue in {"manifest_event_mismatch", "sequence_mismatch", "snapshot_market_mismatch"} for issue in issues)
        if desync_detected and stream_status == "healthy":
            stream_status = "desynced"
        healthy = not issues and not maintenance_mode
        message = "healthy" if healthy else "; ".join(sorted(set(issues)))
        snapshot_freshness_ms = last_event.snapshot.staleness_ms
        if snapshot_freshness_ms is None and age_seconds is not None:
            snapshot_freshness_ms = round(age_seconds * 1000.0, 3)
        health_score = _health_score(
            healthy=healthy,
            stream_status=stream_status,
            freshness_status=freshness_status,
            issue_count=len(set(issues)),
            maintenance_mode=maintenance_mode,
            desync_detected=desync_detected,
        )
        incident_runbook = _health_runbook(
            manifest=manifest,
            feed_surface=feed_surface,
            issues=issues,
            maintenance_mode=maintenance_mode,
            desync_detected=desync_detected,
        )
        return MarketStreamHealth(
            stream_id=stream_id,
            market_id=manifest.market_id,
            venue=manifest.venue,
            healthy=healthy,
            stream_status=stream_status,
            freshness_status=freshness_status,
            message=message,
            issues=sorted(set(issues)),
            issue_count=len(set(issues)),
            maintenance_mode=maintenance_mode,
            desync_detected=desync_detected,
            supports_websocket=bool(feed_surface.supports_websocket),
            supports_rtds=bool(feed_surface.supports_rtds),
            websocket_status=str(feed_surface.websocket_status),
            rtds_status=str(feed_surface.rtds_status),
            market_websocket_status=str(feed_surface.market_websocket_status),
            user_feed_websocket_status=str(feed_surface.user_feed_websocket_status),
            market_feed_status=str(feed_surface.market_feed_status),
            user_feed_status=str(feed_surface.user_feed_status),
            market_feed_replayable=bool(feed_surface.market_feed_replayable),
            user_feed_replayable=bool(feed_surface.user_feed_replayable),
            rtds_replayable=bool(feed_surface.rtds_replayable),
            latest_sequence=manifest.latest_sequence,
            event_count=len(events),
            poll_count=manifest.poll_count,
            age_seconds=age_seconds,
            latest_snapshot_id=manifest.latest_snapshot_id,
            latest_snapshot_status=last_event.snapshot.status.value,
            snapshot_freshness_ms=snapshot_freshness_ms,
            health_score=health_score,
            metadata_gap_count=feed_surface.metadata_gap_count,
            metadata_gap_rate=feed_surface.metadata_gap_rate,
            feed_surface_degraded=feed_surface.degraded,
            feed_surface_degraded_reasons=list(feed_surface.degraded_reasons),
            backend_mode=str(manifest.metadata.get("backend_mode", "unknown")),
            last_observed_at=last_event.observed_at,
            feed_surface=feed_surface,
            feed_surface_status=feed_surface.ingestion_mode,
            feed_surface_summary=feed_surface.summary,
            route_refs=dict(feed_surface.route_refs),
            availability_probes=dict(feed_surface.availability_probes),
            cache_fallbacks=dict(feed_surface.cache_fallbacks),
            subscription_preview=dict(feed_surface.subscription_preview),
            probe_bundle=dict(feed_surface.probe_bundle),
            capability_summary=dict(feed_surface.capability_summary),
            connector_contracts=dict(feed_surface.connector_contracts),
            incident_runbook=incident_runbook,
            metadata=dict(manifest.metadata),
        )

    def _update_manifest(self, event: MarketStreamEvent) -> None:
        manifest = self.load_manifest(event.stream_id)
        manifest.poll_count += 1
        manifest.event_count += 1
        manifest.latest_sequence = event.sequence
        manifest.latest_snapshot_id = event.snapshot.snapshot_id
        manifest.latest_snapshot_path = str(self.paths.latest_snapshot_path(event.stream_id))
        manifest.events_path = str(self.paths.events_path(event.stream_id))
        manifest.snapshot_path = str(self.paths.latest_snapshot_path(event.stream_id))
        manifest.touch()
        self.save_manifest(manifest)

    @staticmethod
    def new_stream_id(market_id: str) -> str:
        return f"stream_{market_id}_{uuid4().hex[:8]}"


def _snapshot_diff(previous: MarketSnapshot | None, current: MarketSnapshot) -> list[str]:
    if previous is None:
        return []
    previous_data = previous.model_dump(mode="json")
    current_data = current.model_dump(mode="json")
    fields = [
        "market_implied_probability",
        "fair_probability_hint",
        "price_yes",
        "price_no",
        "midpoint_yes",
        "spread_bps",
        "liquidity",
        "volume",
        "status",
        "staleness_ms",
    ]
    diffs = [field for field in fields if previous_data.get(field) != current_data.get(field)]
    if previous.orderbook is None and current.orderbook is not None:
        diffs.append("orderbook")
    elif previous.orderbook is not None and current.orderbook is None:
        diffs.append("orderbook")
    return diffs


def _get_market(client: Any, *, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
    if market_id is not None:
        try:
            return client.get_market(market_id=market_id)
        except TypeError:
            return client.get_market(market_id)
    if slug is not None:
        return client.get_market(slug=slug)
    raise ValueError("market_id or slug is required")


def _get_snapshot(client: Any, descriptor: MarketDescriptor) -> MarketSnapshot:
    try:
        return client.get_snapshot(descriptor)
    except TypeError:
        return client.get_snapshot(descriptor.market_id)


@dataclass
class MarketStreamSession:
    store: MarketStreamingStore
    descriptor: MarketDescriptor
    client: Any
    manifest: MarketStreamManifest

    @property
    def stream_id(self) -> str:
        return self.manifest.stream_id

    def poll_once(self) -> MarketStreamEvent:
        previous = self.store.load_latest_snapshot(self.stream_id)
        snapshot = _get_snapshot(self.client, self.descriptor)
        changed_fields = _snapshot_diff(previous, snapshot)
        event = MarketStreamEvent(
            stream_id=self.stream_id,
            market_id=self.descriptor.market_id,
            venue=self.descriptor.venue,
            sequence=self.manifest.latest_sequence + 1,
            kind=StreamEventKind.snapshot if previous is None else (StreamEventKind.change if changed_fields else StreamEventKind.snapshot),
            snapshot=snapshot,
            changed_fields=changed_fields,
            metadata={
                "market_slug": self.descriptor.slug,
                "market_title": self.descriptor.title,
            },
        )
        self.store.append_event(event)
        self.manifest = self.store.load_manifest(self.stream_id)
        return event

    def poll_many(self, count: int = 1) -> list[MarketStreamEvent]:
        return [self.poll_once() for _ in range(max(0, count))]

    def load_events(self) -> list[MarketStreamEvent]:
        return self.store.load_events(self.stream_id)

    def events(self, *, limit: int = 20) -> list[MarketDescriptor]:
        surface = self.describe_feed_surface()
        if not surface.supports_events:
            return []
        if hasattr(self.client, "get_events"):
            try:
                items = list(self.client.get_events(market_id=self.descriptor.market_id, limit=limit))
            except TypeError:
                items = list(self.client.get_events(self.descriptor.market_id))
            return [item if isinstance(item, MarketDescriptor) else MarketDescriptor.model_validate(item) for item in items]
        return []

    def positions(self) -> list[LedgerPosition]:
        surface = self.describe_feed_surface()
        if not surface.supports_positions:
            return []
        if hasattr(self.client, "get_positions"):
            try:
                items = list(self.client.get_positions(market_id=self.descriptor.market_id))
            except TypeError:
                items = list(self.client.get_positions(self.descriptor.market_id))
            return [item if isinstance(item, LedgerPosition) else LedgerPosition.model_validate(item) for item in items]
        return []

    def summarize(self) -> MarketStreamSummary:
        return self.store.summarize_stream(self.stream_id)

    def health(self, *, stale_after_seconds: float = 3600.0) -> MarketStreamHealth:
        return self.store.health_report(self.stream_id, stale_after_seconds=stale_after_seconds)

    def describe_feed_surface(self) -> MarketFeedSurface:
        if hasattr(self.client, "describe_data_surface"):
            try:
                surface = self.client.describe_data_surface()
                return _normalize_feed_surface(
                    surface,
                    venue=self.descriptor.venue,
                    backend_mode=self.manifest.metadata.get("backend_mode", "unknown"),
                    supports_events=hasattr(self.client, "get_events"),
                    supports_positions=hasattr(self.client, "get_positions"),
                )
            except Exception:
                pass
        return _default_feed_surface(
            venue=self.descriptor.venue,
            backend_mode=self.manifest.metadata.get("backend_mode", "unknown"),
            supports_events=hasattr(self.client, "get_events"),
            supports_positions=hasattr(self.client, "get_positions"),
            events_source="snapshot_polling",
            positions_source="local_position_cache",
            market_feed_source="snapshot_polling",
            user_feed_source="local_position_cache",
        )


@dataclass(frozen=True)
class _StreamCollectionTarget:
    ref_kind: str
    ref_value: str
    request_index: int
    priority_score: float
    cache_key: str
    cache_label: str
    market_id: str | None = None
    slug: str | None = None
    stream_id: str | None = None


@dataclass
class MarketStreamCollector:
    streamer: MarketStreamer

    def collect(self, request: StreamCollectionRequest) -> StreamCollectionReport:
        store = self.streamer.store
        assert store is not None
        started_at = datetime.now(timezone.utc)
        monotonic_start = time.monotonic()
        targets = self._build_targets(request)
        prioritized_targets = self._prioritize_targets(targets, request)
        prioritized_refs = [target.cache_label for target in prioritized_targets]
        max_workers = max(1, min(request.fanout, len(prioritized_targets)))
        backpressure_applied = len(prioritized_targets) > max_workers or len(prioritized_targets) > request.backpressure_limit
        batch_count = max(1, (len(prioritized_targets) + max_workers - 1) // max_workers)
        results: dict[str, StreamCollectionItem] = {}
        cache_hit_count = 0
        retry_count = 0
        timeout_count = 0
        error_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._collect_target, target, request) for target in prioritized_targets]
            for target, future in zip(prioritized_targets, futures, strict=False):
                try:
                    item = future.result(timeout=max(0.001, request.timeout_seconds))
                except FuturesTimeoutError:
                    timeout_count += 1
                    item = self._timeout_item(target, request, elapsed_ms=request.timeout_seconds * 1000.0)
                except Exception as exc:
                    error_count += 1
                    item = self._error_item(target, request, exc, elapsed_ms=request.timeout_seconds * 1000.0)
                retry_count += max(0, item.attempts - 1)
                if item.cache_hit:
                    cache_hit_count += 1
                if item.status == "error":
                    error_count += 1
                results[target.cache_label] = item
        ordered_items = [results[target.cache_label] for target in prioritized_targets if target.cache_label in results]
        elapsed_ms = round((time.monotonic() - monotonic_start) * 1000.0, 3)
        processed_count = len(ordered_items)
        cache_hit_rate = round(cache_hit_count / processed_count, 3) if processed_count else 0.0
        latency_samples_ms = [item.elapsed_ms for item in ordered_items if item.elapsed_ms is not None]
        freshness_samples_ms = [item.snapshot_freshness_ms for item in ordered_items if item.snapshot_freshness_ms is not None]
        health_score_samples = [item.health_score for item in ordered_items if item.health_score is not None]
        degraded_count = sum(1 for item in ordered_items if item.health is not None and item.health.stream_status != "healthy")
        available_count = sum(1 for item in ordered_items if item.status in {"ok", "cache_hit"} and not item.timed_out)
        retry_recovery_count = sum(1 for item in ordered_items if item.status == "ok" and item.attempts > 1 and not item.cache_hit)
        metadata_gap_count = sum(item.metadata_gap_count for item in ordered_items)
        requested_target_count = len(ordered_items)
        unique_target_count = len({item.target_ref for item in ordered_items})
        duplicate_target_count = max(0, requested_target_count - unique_target_count)
        requested_market_ids = [item.market_id for item in ordered_items if item.market_id]
        unique_market_ids = list(dict.fromkeys(requested_market_ids))
        duplicate_market_count = max(0, len(requested_market_ids) - len(unique_market_ids))
        requested_market_count = len(requested_market_ids)
        coverage_gap_count = max(0, requested_market_count - len(unique_market_ids))
        venue_totals: Counter[str] = Counter(item.venue.value for item in ordered_items)
        venue_available: Counter[str] = Counter(
            item.venue.value for item in ordered_items if item.status in {"ok", "cache_hit"} and not item.timed_out
        )
        venue_degraded: Counter[str] = Counter(
            item.venue.value for item in ordered_items if item.health is not None and item.health.stream_status != "healthy"
        )
        venue_market_totals: dict[str, list[str]] = {}
        for item in ordered_items:
            venue_market_totals.setdefault(item.venue.value, [])
            if item.market_id:
                venue_market_totals[item.venue.value].append(item.market_id)
        availability_by_venue = {
            venue: {
                "requested": venue_totals[venue],
                "available": venue_available.get(venue, 0),
                "availability_rate": round(venue_available.get(venue, 0) / max(1, venue_totals[venue]), 3),
                "degraded_rate": round(venue_degraded.get(venue, 0) / max(1, venue_totals[venue]), 3),
            }
            for venue in sorted(venue_totals)
        }
        market_coverage_by_venue = {
            venue: {
                "requested_market_count": len(market_ids),
                "unique_market_count": len(set(market_ids)),
                "duplicate_market_count": max(0, len(market_ids) - len(set(market_ids))),
                "duplicate_market_rate": round(max(0, len(market_ids) - len(set(market_ids))) / max(1, len(market_ids)), 6),
                "market_coverage_rate": round(len(set(market_ids)) / max(1, len(market_ids)), 6),
            }
            for venue, market_ids in sorted(venue_market_totals.items())
        }
        return StreamCollectionReport(
            request=request,
            total_count=len(prioritized_targets),
            processed_count=processed_count,
            cache_hit_count=cache_hit_count,
            retry_count=retry_count,
            timeout_count=timeout_count,
            error_count=error_count,
            backpressure_applied=backpressure_applied,
            batch_count=batch_count,
            max_workers=max_workers,
            prioritized_refs=prioritized_refs,
            items=ordered_items,
            cache_hit_rate=cache_hit_rate,
            metrics=StreamCollectionMetrics(
                request_id=request.request_id,
                requested_target_count=requested_target_count,
                unique_target_count=unique_target_count,
                duplicate_target_count=duplicate_target_count,
                duplicate_target_rate=round(duplicate_target_count / max(1, requested_target_count), 6),
                requested_market_count=len(requested_market_ids),
                unique_market_count=len(unique_market_ids),
                duplicate_market_count=duplicate_market_count,
                duplicate_market_rate=round(duplicate_market_count / max(1, len(requested_market_ids)), 6),
                market_coverage_rate=round(len(unique_market_ids) / max(1, len(requested_market_ids)), 6),
                coverage_gap_count=coverage_gap_count,
                coverage_gap_rate=round(coverage_gap_count / max(1, len(requested_market_ids)), 6),
                resolved_market_rate=round(len(requested_market_ids) / max(1, requested_target_count), 6),
                market_coverage_by_venue=market_coverage_by_venue,
                decision_latency_budget_ms=round(request.timeout_seconds * 1000.0, 3),
                decision_latency_p50_ms=_percentile(latency_samples_ms, 50),
                decision_latency_p95_ms=_percentile(latency_samples_ms, 95),
                snapshot_freshness_mean_ms=round(mean(freshness_samples_ms), 3) if freshness_samples_ms else None,
                snapshot_freshness_p95_ms=_percentile(freshness_samples_ms, 95),
                health_score_mean=round(mean(health_score_samples), 3) if health_score_samples else None,
                health_score_p95=_percentile(health_score_samples, 95),
                degraded_mode_rate=round(degraded_count / processed_count, 3) if processed_count else 0.0,
                availability_by_venue=availability_by_venue,
                metadata_gap_count=metadata_gap_count,
                metadata_gap_rate=round(metadata_gap_count / max(1, processed_count), 3),
                cache_recovery_count=retry_recovery_count,
                cache_recovery_rate=round(retry_recovery_count / max(1, processed_count), 3),
                cache_hit_rate=cache_hit_rate,
                availability_rate=round(available_count / processed_count, 3) if processed_count else 0.0,
                latency_samples_ms=latency_samples_ms,
                freshness_samples_ms=freshness_samples_ms,
                health_score_samples=health_score_samples,
                metadata={
                    "request_timeout_seconds": request.timeout_seconds,
                    "stale_after_seconds": request.stale_after_seconds,
                    "budget_capture_ms": round(request.timeout_seconds * 1000.0, 3),
                    "cache_recovery_count": retry_recovery_count,
                    "degraded_count": degraded_count,
                },
            ),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            elapsed_ms=elapsed_ms,
            metadata={
                "fanout": request.fanout,
                "retries": request.retries,
                "timeout_seconds": request.timeout_seconds,
                "cache_ttl_seconds": request.cache_ttl_seconds,
                "prefetch": request.prefetch,
                "priority_strategy": request.priority_strategy.value,
                "backpressure_limit": request.backpressure_limit,
                "backend_mode": request.backend_mode,
            },
        )

    def _build_targets(self, request: StreamCollectionRequest) -> list[_StreamCollectionTarget]:
        targets: list[_StreamCollectionTarget] = []
        for index, market_id in enumerate(request.market_ids):
            targets.append(self._make_target("market_id", market_id, index=index, request=request))
        offset = len(targets)
        for index, slug in enumerate(request.slugs, start=offset):
            targets.append(self._make_target("slug", slug, index=index, request=request))
        offset = len(targets)
        for index, stream_id in enumerate(request.stream_ids, start=offset):
            targets.append(self._make_target("stream_id", stream_id, index=index, request=request))
        return targets

    def _make_target(self, ref_kind: str, ref_value: str, *, index: int, request: StreamCollectionRequest) -> _StreamCollectionTarget:
        cache_key = self._cache_key(request=request, ref_kind=ref_kind, ref_value=ref_value)
        priority_score = self._priority_score(ref_kind=ref_kind, ref_value=ref_value, request=request, index=index, cache_key=cache_key)
        return _StreamCollectionTarget(
            ref_kind=ref_kind,
            ref_value=ref_value,
            request_index=index,
            priority_score=priority_score,
            cache_key=cache_key,
            cache_label=f"{ref_kind}:{ref_value}",
            market_id=ref_value if ref_kind == "market_id" else None,
            slug=ref_value if ref_kind == "slug" else None,
            stream_id=ref_value if ref_kind == "stream_id" else None,
        )

    def _prioritize_targets(self, targets: list[_StreamCollectionTarget], request: StreamCollectionRequest) -> list[_StreamCollectionTarget]:
        if request.priority_strategy == StreamCollectionPriority.request_order:
            return list(targets)
        return sorted(targets, key=lambda target: (-target.priority_score, target.request_index))

    def _priority_score(
        self,
        *,
        ref_kind: str,
        ref_value: str,
        request: StreamCollectionRequest,
        index: int,
        cache_key: str,
    ) -> float:
        store = self.streamer.store
        assert store is not None
        if request.priority_strategy == StreamCollectionPriority.request_order:
            return float(-index)
        cache_entry = store.load_collection_cache(cache_key, cache_ttl_seconds=request.cache_ttl_seconds) if request.prefetch else None
        if request.priority_strategy == StreamCollectionPriority.freshness:
            if cache_entry is not None and cache_entry.health.age_seconds is not None:
                return float(cache_entry.health.age_seconds)
            if ref_kind == "stream_id":
                try:
                    session = self.streamer.load(ref_value)
                    health = session.health(stale_after_seconds=request.stale_after_seconds)
                    if health.age_seconds is not None:
                        return float(health.age_seconds)
                except Exception:
                    return 1_000_000.0
            return 1_000_000.0
        if request.priority_strategy == StreamCollectionPriority.liquidity:
            descriptor = self._descriptor_for_target(ref_kind, ref_value)
            return float(descriptor.liquidity or 0.0) if descriptor is not None else 0.0
        # hybrid
        freshness_score = 0.0
        if cache_entry is not None and cache_entry.health.age_seconds is not None:
            freshness_score = float(cache_entry.health.age_seconds)
        else:
            freshness_score = 500_000.0
        liquidity_score = 0.0
        descriptor = self._descriptor_for_target(ref_kind, ref_value)
        if descriptor is not None and descriptor.liquidity is not None:
            liquidity_score = float(descriptor.liquidity) / 10.0
        return freshness_score + liquidity_score

    def _descriptor_for_target(self, ref_kind: str, ref_value: str) -> MarketDescriptor | None:
        try:
            if ref_kind == "stream_id":
                session = self.streamer.load(ref_value)
                return session.descriptor
            if ref_kind == "market_id":
                return self.streamer.client.get_market(market_id=ref_value)
            if ref_kind == "slug":
                return self.streamer.client.get_market(slug=ref_value)
        except Exception:
            return None
        return None

    def _resolve_session(self, target: _StreamCollectionTarget, request: StreamCollectionRequest) -> MarketStreamSession:
        if target.stream_id is not None:
            return self.streamer.load(target.stream_id)
        latest_manifest = self.streamer.store.find_latest_manifest(market_id=target.market_id, slug=target.slug)
        if latest_manifest is not None:
            return self.streamer.load(latest_manifest.stream_id)
        return self.streamer.open(market_id=target.market_id, slug=target.slug)

    def _collect_target(self, target: _StreamCollectionTarget, request: StreamCollectionRequest) -> StreamCollectionItem:
        store = self.streamer.store
        assert store is not None
        started_at = time.monotonic()
        cache_entry = store.load_collection_cache(target.cache_key, cache_ttl_seconds=request.cache_ttl_seconds) if request.prefetch else None
        if cache_entry is not None:
            return StreamCollectionItem(
                target_ref=target.cache_label,
                target_kind=target.ref_kind,
                market_id=cache_entry.market_id,
                venue=cache_entry.venue,
                stream_id=cache_entry.stream_id,
                cache_key=target.cache_key,
                priority=target.priority_score,
                cache_hit=True,
                attempts=1,
                status="cache_hit",
                message="served from cache",
                manifest=cache_entry.manifest,
                summary=cache_entry.summary,
                health=cache_entry.health,
                elapsed_ms=round((time.monotonic() - started_at) * 1000.0, 3),
                snapshot_freshness_ms=cache_entry.health.snapshot_freshness_ms,
                health_score=cache_entry.health.health_score,
                metadata_gap_count=cache_entry.health.metadata_gap_count,
                metadata_gap_rate=cache_entry.health.metadata_gap_rate,
                metadata={
                    "cache_ttl_seconds": cache_entry.cache_ttl_seconds,
                    "cached_at": cache_entry.cached_at,
                    "backend_mode": request.backend_mode,
                },
            )

        last_error: Exception | None = None
        attempts = 0
        for attempt in range(request.retries + 1):
            attempts = attempt + 1
            try:
                session = self._resolve_session(target, request)
                if request.poll_count > 0:
                    session.poll_many(count=max(1, request.poll_count))
                summary = session.summarize()
                health = session.health(stale_after_seconds=request.stale_after_seconds)
                manifest = store.load_manifest(session.stream_id)
                descriptor = session.descriptor
                cache_entry = MarketStreamCollectionCacheEntry(
                    cache_key=target.cache_key,
                    target_ref=target.cache_label,
                    market_id=descriptor.market_id,
                    venue=descriptor.venue,
                    stream_id=session.stream_id,
                    cache_ttl_seconds=request.cache_ttl_seconds,
                    manifest=manifest,
                    summary=summary,
                    health=health,
                    metadata={
                        "backend_mode": request.backend_mode,
                        "poll_count": request.poll_count,
                        "priority_strategy": request.priority_strategy.value,
                    },
                )
                store.save_collection_cache(cache_entry)
                return StreamCollectionItem(
                    target_ref=target.cache_label,
                    target_kind=target.ref_kind,
                    market_id=descriptor.market_id,
                    venue=descriptor.venue,
                    stream_id=session.stream_id,
                    cache_key=target.cache_key,
                    priority=target.priority_score,
                    cache_hit=False,
                    attempts=attempts,
                    status="ok",
                    message="collected",
                    manifest=manifest,
                    summary=summary,
                    health=health,
                    elapsed_ms=round((time.monotonic() - started_at) * 1000.0, 3),
                    snapshot_freshness_ms=health.snapshot_freshness_ms,
                    health_score=health.health_score,
                    metadata_gap_count=health.metadata_gap_count,
                    metadata_gap_rate=health.metadata_gap_rate,
                    metadata={
                        "backend_mode": request.backend_mode,
                        "poll_count": request.poll_count,
                        "priority_strategy": request.priority_strategy.value,
                    },
                )
            except Exception as exc:
                last_error = exc
                if attempt < request.retries:
                    time.sleep(min(0.25 * (attempt + 1), 1.0))
                    continue
                break
        return self._error_item(
            target,
            request,
            last_error or RuntimeError("stream collection failed"),
            attempts=attempts,
            elapsed_ms=round((time.monotonic() - started_at) * 1000.0, 3),
        )

    def _timeout_item(self, target: _StreamCollectionTarget, request: StreamCollectionRequest, *, elapsed_ms: float | None = None) -> StreamCollectionItem:
        return StreamCollectionItem(
            target_ref=target.cache_label,
            target_kind=target.ref_kind,
            market_id=target.market_id or target.ref_value,
            venue=VenueName.polymarket,
            stream_id=target.stream_id,
            cache_key=target.cache_key,
            priority=target.priority_score,
            cache_hit=False,
            attempts=request.retries + 1,
            timed_out=True,
            status="timeout",
            message=f"Timed out after {request.timeout_seconds:.3f}s",
            elapsed_ms=elapsed_ms,
            metadata={"timeout_seconds": request.timeout_seconds, "backend_mode": request.backend_mode},
        )

    def _error_item(
        self,
        target: _StreamCollectionTarget,
        request: StreamCollectionRequest,
        exc: Exception,
        *,
        attempts: int | None = None,
        elapsed_ms: float | None = None,
    ) -> StreamCollectionItem:
        return StreamCollectionItem(
            target_ref=target.cache_label,
            target_kind=target.ref_kind,
            market_id=target.market_id or target.ref_value,
            venue=VenueName.polymarket,
            stream_id=target.stream_id,
            cache_key=target.cache_key,
            priority=target.priority_score,
            cache_hit=False,
            attempts=attempts or request.retries + 1,
            status="error",
            message=str(exc),
            elapsed_ms=elapsed_ms,
            metadata={"backend_mode": request.backend_mode, "error_type": type(exc).__name__},
        )

    @staticmethod
    def _cache_key(*, request: StreamCollectionRequest, ref_kind: str, ref_value: str) -> str:
        raw = f"{request.backend_mode or 'auto'}::{ref_kind}::{ref_value}"
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw).strip("_") or f"cache_{uuid4().hex[:12]}"


@dataclass
class MarketStreamer:
    client: Any | None = None
    backend_mode: str | None = None
    paths: MarketStreamPaths | PredictionMarketPaths | None = None
    store: MarketStreamingStore | None = None

    def __post_init__(self) -> None:
        self.client = self.client or build_polymarket_client(self.backend_mode)
        self.store = self.store or MarketStreamingStore(self.paths)

    def open(
        self,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        stream_id: str | None = None,
    ) -> MarketStreamSession:
        descriptor = _get_market(self.client, market_id=market_id, slug=slug)
        manifest = self.store.create_manifest(descriptor, stream_id=stream_id)
        if hasattr(self.client, "describe_data_surface"):
            try:
                feed_surface = self.client.describe_data_surface()
            except Exception:
                feed_surface = None
            if feed_surface is not None:
                normalized_surface = _normalize_feed_surface(
                    feed_surface,
                    venue=descriptor.venue,
                    backend_mode=self.backend_mode or "unknown",
                    supports_events=hasattr(self.client, "get_events"),
                    supports_positions=hasattr(self.client, "get_positions"),
                )
                manifest.metadata["data_surface"] = normalized_surface.model_dump(mode="json")
                manifest.data_surface_runbook = dict(normalized_surface.runbook)
                self.store.save_manifest(manifest)
        return MarketStreamSession(store=self.store, descriptor=descriptor, client=self.client, manifest=manifest)

    def load(self, stream_id: str) -> MarketStreamSession:
        manifest = self.store.load_manifest(stream_id)
        descriptor = self.store.load_descriptor(stream_id)
        return MarketStreamSession(store=self.store, descriptor=descriptor, client=self.client, manifest=manifest)

    def load_or_open(
        self,
        *,
        market_id: str | None = None,
        slug: str | None = None,
        stream_id: str | None = None,
    ) -> MarketStreamSession:
        if stream_id is not None:
            return self.load(stream_id)
        manifest = self.store.find_latest_manifest(market_id=market_id, slug=slug)
        if manifest is not None:
            return self.load(manifest.stream_id)
        return self.open(market_id=market_id, slug=slug)

    def list_streams(self) -> list[MarketStreamManifest]:
        return self.store.list_manifests()

    def summarize(self, stream_id: str) -> MarketStreamSummary:
        return self.store.summarize_stream(stream_id)

    def health(self, stream_id: str, *, stale_after_seconds: float = 3600.0) -> MarketStreamHealth:
        return self.store.health_report(stream_id, stale_after_seconds=stale_after_seconds)

    def collect(self, request: StreamCollectionRequest) -> StreamCollectionReport:
        return MarketStreamCollector(self).collect(request)


def monitor_venue_health(
    health_reports: Sequence[MarketStreamHealth] | MarketStreamHealth,
    *,
    venue: VenueName | None = None,
    metadata: dict[str, Any] | None = None,
) -> VenueHealthMonitorReport:
    report_list = [health_reports] if isinstance(health_reports, MarketStreamHealth) else list(health_reports)
    if not report_list:
        return VenueHealthMonitorReport(
            venue=venue,
            summary="reports=0; status=empty",
            metadata=dict(metadata or {}),
        )

    latest_health = report_list[-1]
    venue = venue or latest_health.venue
    healthy_count = sum(1 for report in report_list if report.healthy)
    degraded_count = sum(1 for report in report_list if not report.healthy)
    maintenance_count = sum(1 for report in report_list if report.maintenance_mode or report.freshness_status == "maintenance" or report.incident_runbook.get("runbook_id") == "stream_maintenance")
    desync_count = sum(1 for report in report_list if report.desync_detected or report.freshness_status == "desync" or "sequence_mismatch" in report.issues)
    stale_count = sum(1 for report in report_list if report.freshness_status == "stale" or "stream_stale" in report.issues)
    health_scores = [report.health_score for report in report_list]
    avg_health_score = mean(health_scores) if health_scores else None
    p95_health_score = _percentile(health_scores, 95) if health_scores else None
    recovery_required = (
        not latest_health.healthy
        or latest_health.maintenance_mode
        or latest_health.desync_detected
        or latest_health.freshness_status in {"stale", "maintenance", "desync"}
    )
    recovered = latest_health.healthy and any(not report.healthy for report in report_list[:-1])
    incident_runbook = _venue_health_monitor_runbook(latest_health, recovered=recovered, recovery_required=recovery_required)
    existing_market_probe = dict((latest_health.availability_probes or {}).get("market_feed") or {})
    existing_user_probe = dict((latest_health.availability_probes or {}).get("user_feed") or {})
    existing_rtds_probe = dict((latest_health.availability_probes or {}).get("rtds") or {})
    existing_market_fallback = dict((latest_health.cache_fallbacks or {}).get("market_feed") or {})
    existing_user_fallback = dict((latest_health.cache_fallbacks or {}).get("user_feed") or {})
    existing_rtds_fallback = dict((latest_health.cache_fallbacks or {}).get("rtds") or {})
    recovered_from_partial_probes = any(
        not {"probe_ready", "operational_status", "recommended_action"}.issubset(set(probe.keys()))
        for probe in (existing_market_probe, existing_user_probe, existing_rtds_probe)
        if probe
    ) or any(
        not {"operational_status", "recommended_action"}.issubset(set(fallback.keys()))
        for fallback in (existing_market_fallback, existing_user_fallback, existing_rtds_fallback)
        if fallback
    )
    probe_context = {
        "route_refs": dict(latest_health.route_refs),
        "market_feed_status": latest_health.market_feed_status,
        "user_feed_status": latest_health.user_feed_status,
        "market_feed_transport": latest_health.feed_surface.market_feed_transport if latest_health.feed_surface is not None else existing_market_probe.get("transport", "unavailable"),
        "user_feed_transport": latest_health.feed_surface.user_feed_transport if latest_health.feed_surface is not None else existing_user_probe.get("transport", "unavailable"),
        "market_feed_connector": latest_health.feed_surface.market_feed_connector if latest_health.feed_surface is not None else existing_market_probe.get("connector", "unavailable"),
        "user_feed_connector": latest_health.feed_surface.user_feed_connector if latest_health.feed_surface is not None else existing_user_probe.get("connector", "unavailable"),
        "rtds_connector": latest_health.feed_surface.rtds_connector if latest_health.feed_surface is not None else existing_rtds_probe.get("connector", "unavailable"),
        "market_feed_replayable": latest_health.market_feed_replayable,
        "user_feed_replayable": latest_health.user_feed_replayable,
        "rtds_replayable": latest_health.rtds_replayable,
        "market_feed_cache_backed": latest_health.feed_surface.market_feed_cache_backed if latest_health.feed_surface is not None else bool(existing_market_probe.get("cache_backed", existing_market_fallback.get("status") == "ready")),
        "user_feed_cache_backed": latest_health.feed_surface.user_feed_cache_backed if latest_health.feed_surface is not None else bool(existing_user_probe.get("cache_backed", existing_user_fallback.get("status") == "ready")),
        "rtds_cache_backed": latest_health.feed_surface.rtds_cache_backed if latest_health.feed_surface is not None else bool(existing_rtds_probe.get("cache_backed", existing_rtds_fallback.get("status") == "ready")),
        "market_websocket_status": latest_health.market_websocket_status,
        "user_feed_websocket_status": latest_health.user_feed_websocket_status,
        "websocket_status": latest_health.websocket_status,
        "rtds_status": latest_health.rtds_status,
        "supports_websocket": latest_health.supports_websocket,
        "supports_rtds": latest_health.supports_rtds,
    }
    normalized_probes = _feed_surface_availability_probes(probe_context)
    if isinstance(latest_health.availability_probes, dict):
        for key, value in latest_health.availability_probes.items():
            if isinstance(value, dict) and isinstance(normalized_probes.get(key), dict):
                merged_probe = dict(normalized_probes[key])
                merged_probe.update(value)
                normalized_probes[key] = merged_probe
            else:
                normalized_probes[key] = value
    normalized_fallbacks = _feed_surface_cache_fallbacks(probe_context)
    if isinstance(latest_health.cache_fallbacks, dict):
        for key, value in latest_health.cache_fallbacks.items():
            if isinstance(value, dict) and isinstance(normalized_fallbacks.get(key), dict):
                merged_fallback = dict(normalized_fallbacks[key])
                merged_fallback.update(value)
                normalized_fallbacks[key] = merged_fallback
            else:
                normalized_fallbacks[key] = value
    normalized_connector_contracts = _feed_surface_connector_contracts(
        {
            **probe_context,
            "availability_probes": normalized_probes,
            "cache_fallbacks": normalized_fallbacks,
        }
    )
    if isinstance(latest_health.connector_contracts, dict):
        for key, value in latest_health.connector_contracts.items():
            if isinstance(value, dict) and isinstance(normalized_connector_contracts.get(key), dict):
                merged_contract = dict(normalized_connector_contracts[key])
                merged_contract.update(value)
                normalized_connector_contracts[key] = merged_contract
            else:
                normalized_connector_contracts[key] = value
    normalized_subscription_preview = _feed_surface_subscription_preview(
        {
            **probe_context,
            "venue": latest_health.venue.value,
            "availability_probes": normalized_probes,
            "cache_fallbacks": normalized_fallbacks,
        }
    )
    if isinstance(latest_health.subscription_preview, dict):
        merged_preview = dict(normalized_subscription_preview)
        merged_preview.update(latest_health.subscription_preview)
        normalized_subscription_preview = merged_preview
    normalized_probe_bundle = _feed_surface_probe_bundle(
        {
            **probe_context,
            "availability_probes": normalized_probes,
            "cache_fallbacks": normalized_fallbacks,
            "subscription_preview": normalized_subscription_preview,
            "recovered_from_partial_probes": recovered_from_partial_probes,
        }
    )
    if isinstance(latest_health.probe_bundle, dict):
        merged_bundle = dict(normalized_probe_bundle)
        merged_bundle.update(latest_health.probe_bundle)
        normalized_probe_bundle = merged_bundle
    normalized_capability_summary = _feed_surface_capability_summary(
        {
            **probe_context,
            "availability_probes": normalized_probes,
            "cache_fallbacks": normalized_fallbacks,
            "subscription_preview": normalized_subscription_preview,
            "probe_bundle": normalized_probe_bundle,
        }
    )
    if isinstance(latest_health.capability_summary, dict):
        merged_summary = dict(normalized_capability_summary)
        merged_summary.update(latest_health.capability_summary)
        normalized_capability_summary = merged_summary
    summary = (
        f"reports={len(report_list)}; healthy={healthy_count}; degraded={degraded_count}; maintenance={maintenance_count}; "
        f"desync={desync_count}; stale={stale_count}; latest={latest_health.stream_status}; recovery_required={recovery_required}; "
        f"recovered={recovered}"
    )
    return VenueHealthMonitorReport(
        venue=venue,
        stream_count=len(report_list),
        healthy_count=healthy_count,
        degraded_count=degraded_count,
        maintenance_count=maintenance_count,
        desync_count=desync_count,
        stale_count=stale_count,
        avg_health_score=avg_health_score,
        p95_health_score=p95_health_score,
        latest_health=latest_health,
        recovered=recovered,
        recovery_required=recovery_required,
        summary=summary,
        supports_websocket=bool(latest_health.supports_websocket),
        supports_rtds=bool(latest_health.supports_rtds),
        websocket_status=latest_health.websocket_status,
        rtds_status=latest_health.rtds_status,
        market_websocket_status=latest_health.market_websocket_status,
        user_feed_websocket_status=latest_health.user_feed_websocket_status,
        market_feed_status=latest_health.market_feed_status,
        user_feed_status=latest_health.user_feed_status,
        market_feed_replayable=latest_health.market_feed_replayable,
        user_feed_replayable=latest_health.user_feed_replayable,
        rtds_replayable=latest_health.rtds_replayable,
        feed_surface_status=latest_health.feed_surface_status,
        feed_surface_summary=latest_health.feed_surface_summary,
        route_refs=dict(latest_health.route_refs),
        availability_probes=normalized_probes,
        cache_fallbacks=normalized_fallbacks,
        subscription_preview=normalized_subscription_preview,
        probe_bundle=normalized_probe_bundle,
        capability_summary=normalized_capability_summary,
        connector_contracts=normalized_connector_contracts,
        incident_runbook=incident_runbook,
        metadata={
            **dict(metadata or {}),
            "stream_ids": [report.stream_id for report in report_list],
            "market_ids": [report.market_id for report in report_list],
            "health_statuses": [report.stream_status for report in report_list],
        },
    )


def open_market_stream(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    client: Any | None = None,
    backend_mode: str | None = None,
    paths: MarketStreamPaths | PredictionMarketPaths | None = None,
    stream_id: str | None = None,
) -> MarketStreamSession:
    streamer = MarketStreamer(client=client, backend_mode=backend_mode, paths=paths)
    return streamer.open(market_id=market_id, slug=slug, stream_id=stream_id)


def collect_market_streams(
    *,
    market_ids: list[str] | None = None,
    slugs: list[str] | None = None,
    stream_ids: list[str] | None = None,
    fanout: int = 4,
    retries: int = 1,
    timeout_seconds: float = 5.0,
    cache_ttl_seconds: float = 60.0,
    prefetch: bool = True,
    backpressure_limit: int = 32,
    priority_strategy: StreamCollectionPriority = StreamCollectionPriority.freshness,
    poll_count: int = 1,
    stale_after_seconds: float = 3600.0,
    client: Any | None = None,
    backend_mode: str | None = None,
    paths: MarketStreamPaths | PredictionMarketPaths | None = None,
) -> StreamCollectionReport:
    streamer = MarketStreamer(client=client, backend_mode=backend_mode, paths=paths)
    request = StreamCollectionRequest(
        market_ids=list(market_ids or []),
        slugs=list(slugs or []),
        stream_ids=list(stream_ids or []),
        fanout=fanout,
        retries=retries,
        timeout_seconds=timeout_seconds,
        cache_ttl_seconds=cache_ttl_seconds,
        prefetch=prefetch,
        backpressure_limit=backpressure_limit,
        priority_strategy=priority_strategy,
        poll_count=poll_count,
        stale_after_seconds=stale_after_seconds,
        backend_mode=backend_mode,
    )
    return streamer.collect(request)


def _age_seconds(observed_at: datetime) -> float | None:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return round(max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds()), 3)


def _build_stream_narrative(
    *,
    market_title: str,
    trend: str,
    price_yes_change: float | None,
    spread_bps_change: float | None,
    change_count: int,
    event_count: int,
) -> str:
    delta_bits: list[str] = []
    if price_yes_change is not None:
        delta_bits.append(f"price_yes_change={price_yes_change:+.3f}")
    if spread_bps_change is not None:
        delta_bits.append(f"spread_bps_change={spread_bps_change:+.2f}")
    if not delta_bits:
        delta_bits.append("no_price_or_spread_delta")
    return (
        f"{market_title}: {trend} stream with {change_count}/{event_count} change events; "
        + ", ".join(delta_bits)
    )


def _venue_health_monitor_runbook(
    latest_health: MarketStreamHealth,
    *,
    recovered: bool,
    recovery_required: bool,
) -> dict[str, Any]:
    if not recovery_required:
        return {
            "runbook_id": "venue_health_ok",
            "runbook_kind": "state",
            "summary": "Venue stream health is stable and fresh.",
            "recommended_action": "continue_shadow",
            "owner": "operator",
            "priority": "low",
            "status": "ok",
            "trigger_reasons": [],
            "next_steps": [
                "Keep polling the venue stream on schedule.",
                "Continue recording health and freshness metrics.",
            ],
            "signals": {
                "recovered": recovered,
                "healthy": latest_health.healthy,
                "freshness_status": latest_health.freshness_status,
                "feed_surface_degraded": latest_health.feed_surface_degraded,
                "feed_surface_degraded_reasons": list(latest_health.feed_surface_degraded_reasons),
            },
        }

    trigger_reasons = list(dict.fromkeys([*latest_health.issues, latest_health.incident_runbook.get("runbook_id", "")]))
    trigger_reasons = [reason for reason in trigger_reasons if reason]
    return {
        "runbook_id": "venue_health_degraded",
        "runbook_kind": "incident" if latest_health.maintenance_mode or latest_health.desync_detected else "degraded_mode",
        "summary": "Venue stream health needs attention; keep the system observable and avoid live assumptions.",
        "recommended_action": "hold_live_actions",
        "owner": "operator",
        "priority": "high" if latest_health.maintenance_mode or latest_health.desync_detected else "medium",
        "status": "blocked" if latest_health.maintenance_mode or latest_health.desync_detected else "degraded",
        "trigger_reasons": trigger_reasons,
        "next_steps": [
            "Review the latest stream health issues and freshness status.",
            "Wait for a fresh poll and a stable sequence before resuming confidence.",
            "If the stream desynced, rebuild the snapshot and re-check freshness.",
        ],
        "signals": {
            "recovered": recovered,
            "healthy": latest_health.healthy,
            "maintenance_mode": latest_health.maintenance_mode,
            "desync_detected": latest_health.desync_detected,
            "freshness_status": latest_health.freshness_status,
            "feed_surface_degraded": latest_health.feed_surface_degraded,
            "feed_surface_degraded_reasons": list(latest_health.feed_surface_degraded_reasons),
        },
    }
