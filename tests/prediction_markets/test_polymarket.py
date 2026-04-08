from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from prediction_markets.models import MarketDescriptor, MarketStatus, TradeSide, VenueName, VenueType
from prediction_markets.models import ResolutionPolicy, ResolutionStatus
from prediction_markets.polymarket import (
    PolymarketOrderAction,
    PolymarketClient,
    build_polymarket_execution_adapter,
    build_polymarket_resolution_policy_completeness_report,
    describe_polymarket_execution_surface,
    describe_polymarket_order_execution_surface,
    describe_polymarket_resolution_policy_surface,
)
from prediction_markets.resolution_guard import describe_resolution_policy_surface as describe_resolution_policy_surface_guard


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeWebSocketConnection:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.sent_messages: list[str] = []
        self.closed = False

    def send(self, message: str) -> None:
        self.sent_messages.append(message)

    def recv(self) -> str:
        return self.sent_messages[-1] if self.sent_messages else ""

    def close(self) -> None:
        self.closed = True


def test_polymarket_client_parses_events_positions_and_feed_surface(monkeypatch) -> None:
    def fake_get(url: str, params=None, timeout: float | None = None, **kwargs):  # noqa: ANN001
        if url.endswith("/markets"):
            return FakeResponse(
                [
                    {
                        "id": "pm_test_market",
                        "venueMarketId": "pm_test_market",
                        "eventId": "pm_test_event",
                        "slug": "test-market",
                        "question": "Will the test market resolve?",
                        "description": "Test market",
                        "category": "tests",
                        "active": True,
                        "closed": False,
                        "resolutionSource": "https://example.com/resolution",
                        "resolutionSourceUrl": "https://example.com/resolution",
                        "startDate": "2026-04-07T22:00:00+00:00",
                        "endDate": "2030-01-01T00:00:00Z",
                        "outcomes": ["Yes", "No"],
                        "outcomePrices": [0.61, 0.39],
                        "liquidity": 12345,
                        "volume": 54321,
                        "volume24h": 4321,
                        "clobTokenIds": ["yes_test", "no_test"],
                    }
                ]
            )
        if url.endswith("/markets/pm_test_market"):
            return FakeResponse(
                {
                    "id": "pm_test_market",
                    "venueMarketId": "pm_test_market",
                    "eventId": "pm_test_event",
                    "slug": "test-market",
                    "question": "Will the test market resolve?",
                    "description": "Test market",
                    "category": "tests",
                    "active": True,
                    "closed": False,
                    "resolutionSource": "https://example.com/resolution",
                    "resolutionSourceUrl": "https://example.com/resolution",
                    "startDate": "2026-04-07T22:00:00+00:00",
                    "endDate": "2030-01-01T00:00:00Z",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.61, 0.39],
                    "liquidity": 12345,
                    "volume": 54321,
                    "volume24h": 4321,
                    "orderBook": {
                        "source": "gamma",
                        "bids": [
                            {"price": 0.57, "size": 900},
                            {"price": 0.56, "size": 500},
                        ],
                        "asks": [
                            {"price": 0.63, "size": 700},
                            {"price": 0.64, "size": 400},
                        ],
                    },
                    "trades": [
                        {"price": 0.59, "size": 100, "side": "buy", "timestamp": "2026-04-08T00:01:00+00:00"},
                        {"price": 0.62, "size": 50, "side": "sell", "timestamp": "2026-04-08T00:03:00+00:00"},
                    ],
                    "timestamp": "2026-04-08T00:05:00+00:00",
                    "clobTokenIds": ["yes_test", "no_test"],
                }
            )
        if url.endswith("/events/pm_test_market"):
            return FakeResponse(
                {
                    "events": [
                        {
                            "id": "pm_test_market",
                            "venueMarketId": "pm_test_market",
                            "eventId": "pm_test_event",
                            "slug": "test-market",
                            "question": "Will the test market resolve?",
                            "description": "Test market",
                            "category": "tests",
                            "active": True,
                            "closed": False,
                            "resolutionSource": "https://example.com/resolution",
                            "resolutionSourceUrl": "https://example.com/resolution",
                            "startDate": "2026-04-07T22:00:00+00:00",
                            "endDate": "2030-01-01T00:00:00Z",
                            "outcomes": ["Yes", "No"],
                            "outcomePrices": [0.61, 0.39],
                            "liquidity": 12345,
                            "volume": 54321,
                            "volume24h": 4321,
                            "clobTokenIds": ["yes_test", "no_test"],
                        }
                    ]
                }
            )
        if url.endswith("/positions/pm_test_market"):
            return FakeResponse(
                {
                    "positions": [
                        {
                            "market_id": "pm_test_market",
                            "venue": "polymarket",
                            "side": "yes",
                            "quantity": 2.5,
                            "entry_price": 0.61,
                            "metadata": {"source": "api"},
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("prediction_markets.polymarket.requests.get", fake_get)

    client = PolymarketClient(
        base_url="https://example.com",
        events_path="events",
        positions_path="positions",
        market_feed_path="market-feed",
        user_feed_path="user-feed",
    )

    markets = client.list_markets(limit=5)
    events = client.get_events(market_id="pm_test_market")
    positions = client.get_positions(market_id="pm_test_market")
    surface = client.describe_data_surface()

    assert markets and markets[0].market_id == "pm_test_market"
    assert markets[0].venue_market_id == "pm_test_market"
    assert markets[0].event_id == "pm_test_event"
    assert markets[0].open_time.isoformat() == "2026-04-07T22:00:00+00:00"
    assert markets[0].end_date.isoformat() == "2030-01-01T00:00:00+00:00"
    assert markets[0].volume_24h == pytest.approx(4321.0)
    assert events and events[0].market_id == "pm_test_market"
    assert positions and positions[0].market_id == "pm_test_market"
    assert events[0].venue_market_id == "pm_test_market"
    assert surface.supports_events is True
    assert surface.supports_positions is True
    assert surface.market_feed_kind == "market_snapshot_http_json"
    assert surface.user_feed_kind == "position_snapshot_http_json"
    assert surface.market_feed_connector == "http_json_market_snapshot"
    assert surface.user_feed_connector == "http_json_position_snapshot"
    assert surface.market_feed_replayable is True
    assert surface.user_feed_replayable is True
    assert surface.market_feed_cache_backed is False
    assert surface.user_feed_cache_backed is False
    assert surface.route_refs["events"] == "events"
    assert surface.route_refs["market_feed"] == "market-feed"
    assert surface.availability_probes["market_feed"]["transport"] == "http_json"
    assert surface.availability_probes["market_feed"]["connector"] == "http_json_market_snapshot"
    assert surface.availability_probes["market_feed"]["probe_ready"] is True
    assert surface.availability_probes["market_feed"]["recommended_action"] == "poll_http_snapshot"
    assert surface.availability_probes["market_feed"]["severity"] == "info"
    assert surface.availability_probes["market_feed"]["gap_reason"] == "poll_only_surface"
    assert surface.availability_probes["market_feed"]["gap_class"] == "poll_only_surface"
    assert surface.cache_fallbacks["market_feed"]["status"] == "not_configured"
    assert surface.cache_fallbacks["market_feed"]["recommended_action"] == "no_cache_fallback"
    assert surface.cache_fallbacks["user_feed"]["status"] == "not_configured"
    assert surface.subscription_preview["channels"]["market_feed"]["recommended_action"] == "poll_http_snapshot"
    assert surface.subscription_preview["channels"]["market_feed"]["subscription_intent"] == "poll_snapshot"
    assert surface.subscription_preview["channels"]["market_feed"]["channel_spec"]["message_kind"] == "market_snapshot"
    assert surface.subscription_preview["preview_flow"]["testable"] is True
    assert surface.subscription_preview["recommended_subscriptions"][0]["channel"] == "market_feed"
    assert surface.probe_bundle["primary_path"] == "poll_http_snapshot"
    assert surface.probe_bundle["highest_severity"] == "info"
    assert surface.capability_summary["market_feed_path"] == "poll_http_snapshot"
    assert surface.capability_summary["auth_requirements"]["user_feed"] == "none"
    assert surface.connector_contracts["market_feed"]["mode"] == "read_only"
    assert surface.connector_contracts["market_feed"]["endpoint_contract"]["method"] == "GET"
    assert surface.connector_contracts["user_feed"]["session_requirement"] == "none"
    assert surface.events_source == "events"
    assert surface.positions_source == "positions"
    assert surface.market_feed_transport == "http_json"
    assert surface.runbook["runbook_id"] == "polymarket_read_only_data_surface"
    assert surface.runbook["feed_mode"] == "read_only"
    assert surface.runbook["streaming_mode"] == "read_only_snapshot_polling"
    assert surface.runbook["signals"]["market_feed_connector"] == "http_json_market_snapshot"
    assert surface.runbook["signals"]["user_feed_connector"] == "http_json_position_snapshot"
    assert surface.runbook["signals"]["market_feed_replayable"] is True
    assert surface.runbook["signals"]["user_feed_replayable"] is True
    assert surface.runbook["signals"]["route_refs"]["market_feed"] == "market-feed"
    assert surface.runbook["signals"]["availability_probes"]["market_feed"]["status"] == "endpoint_configured"
    assert surface.runbook["signals"]["availability_probes"]["market_feed"]["recommended_action"] == "poll_http_snapshot"
    assert surface.runbook["signals"]["cache_fallbacks"]["market_feed"]["status"] == "not_configured"
    assert surface.runbook["signals"]["subscription_preview"]["channels"]["market_feed"]["recommended_action"] == "poll_http_snapshot"
    assert surface.runbook["signals"]["probe_bundle"]["primary_path"] == "poll_http_snapshot"
    assert surface.runbook["signals"]["connector_contracts"]["market_feed"]["mode"] == "read_only"
    assert surface.runbook["signals"]["connector_contracts"]["market_feed"]["endpoint_contract"]["response_kind"] == "market_snapshot"
    assert surface.runbook["signals"]["gap_summary"]["live_transport_not_supported_count"] == 3
    snapshot = client.get_snapshot(markets[0])
    assert snapshot.snapshot_ts.isoformat() == "2026-04-08T00:05:00+00:00"
    assert snapshot.best_bid_yes == pytest.approx(0.57)
    assert snapshot.best_ask_yes == pytest.approx(0.63)
    assert snapshot.best_bid_no == pytest.approx(0.37)
    assert snapshot.best_ask_no == pytest.approx(0.43)
    assert snapshot.mid_probability == pytest.approx(0.6)
    assert snapshot.depth_near_touch == pytest.approx(1600.0)
    assert snapshot.last_trade_price == pytest.approx(0.62)
    assert snapshot.last_trade_ts.isoformat() == "2026-04-08T00:03:00+00:00"


def test_polymarket_client_live_websocket_bindings_and_rtds(monkeypatch) -> None:
    connections: list[FakeWebSocketConnection] = []

    def fake_create_connection(endpoint: str, timeout: float | None = None):  # noqa: ANN001
        connection = FakeWebSocketConnection(endpoint)
        connections.append(connection)
        return connection

    monkeypatch.setattr(
        "prediction_markets.polymarket.websocket_client",
        SimpleNamespace(create_connection=fake_create_connection),
    )

    client = PolymarketClient(
        base_url="https://gamma-api.polymarket.com",
        market_websocket_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        user_websocket_url="wss://ws-subscriptions-clob.polymarket.com/ws/user",
        rtds_url="wss://ws-live-data.polymarket.com",
        api_key="api-key",
        secret="api-secret",
        passphrase="api-passphrase",
        gamma_auth_address="0xabc123",
        websocket_heartbeat_seconds=0.0,
        rtds_heartbeat_seconds=0.0,
    )

    surface = client.describe_data_surface()
    market_session = client.open_market_websocket(["asset-1", "asset-2"], heartbeat_interval_seconds=0.0)
    user_session = client.open_user_websocket(["market-1"], heartbeat_interval_seconds=0.0)
    rtds_session = client.open_rtds(
        [{"topic": "crypto_prices", "type": "update", "filters": "solusdt"}],
        heartbeat_interval_seconds=0.0,
    )

    assert surface.supports_websocket is True
    assert surface.supports_rtds is True
    assert surface.market_websocket_status == "ready"
    assert surface.user_feed_websocket_status == "ready"
    assert surface.rtds_status == "ready"
    assert surface.live_streaming is True
    assert surface.route_refs["market_websocket"] == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    assert surface.route_refs["user_websocket"] == "wss://ws-subscriptions-clob.polymarket.com/ws/user"
    assert surface.route_refs["rtds"] == "wss://ws-live-data.polymarket.com"
    assert surface.connector_contracts["websocket_market"]["mode"] == "live_bindable"
    assert surface.connector_contracts["websocket_user"]["auth_requirement"] == "required"
    assert surface.connector_contracts["rtds"]["auth_requirement"] == "optional"
    assert surface.subscription_preview["mode"] == "live_bindable"
    assert surface.subscription_preview["channels"]["websocket_market"]["subscription_capable"] is True
    assert surface.subscription_preview["channels"]["websocket_user"]["subscription_capable"] is True
    assert surface.subscription_preview["channels"]["rtds"]["subscription_capable"] is True
    assert surface.subscription_preview["preview_flow"]["expected_outcome"] == "live_bindable_with_optional_user_auth"

    market_payload = json.loads(connections[0].sent_messages[0])
    user_payload = json.loads(connections[1].sent_messages[0])
    rtds_payload = json.loads(connections[2].sent_messages[0])

    assert market_session.endpoint.endswith("/ws/market")
    assert market_payload["type"] == "market"
    assert market_payload["assets_ids"] == ["asset-1", "asset-2"]
    assert market_payload["custom_feature_enabled"] is True
    assert user_session.endpoint.endswith("/ws/user")
    assert user_payload["type"] == "user"
    assert user_payload["markets"] == ["market-1"]
    assert user_payload["auth"]["apiKey"] == "api-key"
    assert user_payload["auth"]["passphrase"] == "api-passphrase"
    assert rtds_session.endpoint.endswith("/ws-live-data.polymarket.com")
    assert rtds_payload["action"] == "subscribe"
    assert rtds_payload["subscriptions"][0]["topic"] == "crypto_prices"
    assert rtds_payload["subscriptions"][0]["gamma_auth"]["address"] == "0xabc123"

    market_session.close()
    user_session.close()
    rtds_session.close()


def test_polymarket_user_websocket_requires_credentials() -> None:
    client = PolymarketClient(base_url="https://gamma-api.polymarket.com")

    with pytest.raises(RuntimeError, match="requires api_key, secret, and passphrase"):
        client.open_user_websocket(["market-1"], heartbeat_interval_seconds=0.0)


def test_polymarket_client_uses_local_fixtures_when_configured(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    (fixtures / "markets").mkdir(parents=True)
    (fixtures / "snapshots").mkdir(parents=True)
    (fixtures / "events").mkdir(parents=True)
    (fixtures / "positions").mkdir(parents=True)

    market = {
        "id": "pm_fixture_market",
        "venueMarketId": "pm_fixture_market",
        "eventId": "pm_fixture_event",
        "slug": "fixture-market",
        "question": "Will the fixture market resolve?",
        "description": "Fixture-backed market",
        "category": "tests",
        "active": True,
        "closed": False,
        "resolutionSource": "https://example.com/resolution",
        "resolutionSourceUrl": "https://example.com/resolution",
        "startDate": "2026-04-07T22:00:00+00:00",
        "endDate": "2030-01-01T00:00:00Z",
        "outcomes": ["Yes", "No"],
        "outcomePrices": [0.64, 0.36],
        "liquidity": 23456,
        "volume": 65432,
        "volume24h": 5432,
        "orderBook": {
            "source": "fixture",
            "bids": [{"price": 0.62, "size": 800}],
            "asks": [{"price": 0.66, "size": 600}],
        },
        "trades": [
            {"price": 0.63, "size": 80, "side": "buy", "timestamp": "2026-04-08T00:01:00+00:00"},
        ],
        "timestamp": "2026-04-08T00:05:00+00:00",
        "clobTokenIds": ["yes_fixture", "no_fixture"],
    }
    (fixtures / "markets.json").write_text(json.dumps([market]), encoding="utf-8")
    (fixtures / "markets" / "pm_fixture_market.json").write_text(json.dumps(market), encoding="utf-8")
    (fixtures / "snapshots" / "pm_fixture_market.json").write_text(json.dumps(market), encoding="utf-8")
    (fixtures / "events" / "pm_fixture_market.json").write_text(
        json.dumps({"events": [market]}),
        encoding="utf-8",
    )
    (fixtures / "positions" / "pm_fixture_market.json").write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "market_id": "pm_fixture_market",
                        "venue": "polymarket",
                        "side": "yes",
                        "quantity": 1.5,
                        "entry_price": 0.64,
                        "metadata": {"source": "fixture"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    client = PolymarketClient(
        base_url="https://example.com",
        fixtures_root=str(fixtures),
        events_path="events",
        positions_path="positions",
        market_feed_path="market-feed",
        user_feed_path="user-feed",
    )

    markets = client.list_markets(limit=5)
    fetched_market = client.get_market(market_id="pm_fixture_market")
    events = client.get_events(market_id="pm_fixture_market")
    positions = client.get_positions(market_id="pm_fixture_market")
    surface = client.describe_data_surface()
    snapshot = client.get_snapshot(fetched_market)

    assert markets and markets[0].market_id == "pm_fixture_market"
    assert fetched_market.slug == "fixture-market"
    assert events and events[0].market_id == "pm_fixture_market"
    assert positions and positions[0].market_id == "pm_fixture_market"
    assert snapshot.snapshot_ts.isoformat() == "2026-04-08T00:05:00+00:00"
    assert surface.backend_mode == "fixture"
    assert surface.ingestion_mode == "read_only_fixture"
    assert surface.market_feed_status == "fixture_available"
    assert surface.user_feed_status == "fixture_available"
    if surface.websocket_status == "ready":
        assert surface.market_websocket_status == "ready"
        assert surface.user_feed_websocket_status == "ready"
        assert surface.rtds_status == "ready"
    else:
        assert surface.rtds_status == "unavailable"
        assert surface.websocket_status == "unavailable"
        assert surface.market_websocket_status == "unavailable"
        assert surface.user_feed_websocket_status == "unavailable"
    assert surface.market_feed_connector == "fixture_market_snapshot"
    assert surface.user_feed_connector == "fixture_positions_snapshot"
    assert surface.market_feed_replayable is True
    assert surface.user_feed_replayable is True
    assert surface.rtds_replayable is False
    assert surface.market_feed_cache_backed is True
    assert surface.user_feed_cache_backed is True
    assert surface.route_refs["market_feed"] == "market-feed"
    assert surface.route_refs["user_feed"] == "user-feed"
    assert surface.availability_probes["market_feed"]["transport"] == "fixture_cache"
    assert surface.availability_probes["market_feed"]["status"] == "fixture_available"
    assert surface.availability_probes["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface.cache_fallbacks["market_feed"]["status"] == "ready"
    assert surface.cache_fallbacks["market_feed"]["recommended_action"] == "use_cache_fallback"
    assert surface.cache_fallbacks["user_feed"]["status"] == "ready"
    assert surface.subscription_preview["channels"]["market_feed"]["status"] == "ready"
    assert surface.subscription_preview["subscription_bundles"]["poll_snapshot_bundle"]["testable"] is True
    assert surface.subscription_preview["preview_flow"]["route_refs"]["market_feed"] == "market-feed"
    assert surface.subscription_preview["gap_summary"]["cache_backed_channel_count"] == 2
    assert surface.probe_bundle["fallback_path"] == "use_cache_fallback"
    assert "websocket_market" in surface.probe_bundle["degraded_paths"]
    assert surface.probe_bundle["highest_severity"] == "info"
    assert surface.probe_bundle["gap_summary"]["documented_preview_routes"]["rtds"] is None
    assert surface.capability_summary["has_cache_fallback"] is True
    assert surface.capability_summary["documented_preview_routes"]["rtds"] is None
    assert surface.capability_summary["gap_summary"]["documented_preview_routes"]["rtds"] is None
    assert "user_feed_is_cache_proxy" in surface.capability_summary["market_user_gap_reasons"]
    assert surface.capability_summary["preview_flow"]["testable"] is True
    assert surface.connector_contracts["market_feed"]["transport"] == "fixture_cache"
    assert surface.connector_contracts["market_feed"]["endpoint_contract"]["route_ref"] == "market-feed"
    assert surface.connector_contracts["user_feed"]["session_requirement"] == "local_cache_context"
    assert surface.connector_contracts["websocket_market"]["gap_class"] == "not_bound"
    assert surface.market_feed_kind == "market_snapshot_fixture"
    assert surface.user_feed_kind == "position_snapshot_fixture"
    assert surface.summary
    assert surface.runbook["runbook_id"] == "polymarket_read_only_data_surface"
    assert surface.runbook["signals"]["fixture_mode"] is True
    assert surface.runbook["signals"]["feed_mode"] == "read_only"
    assert surface.runbook["signals"]["market_feed_connector"] == "fixture_market_snapshot"
    assert surface.runbook["signals"]["user_feed_connector"] == "fixture_positions_snapshot"
    assert surface.runbook["signals"]["market_feed_cache_backed"] is True
    assert surface.runbook["signals"]["user_feed_cache_backed"] is True
    assert surface.runbook["signals"]["route_refs"]["market_feed"] == "market-feed"
    assert surface.runbook["signals"]["availability_probes"]["market_feed"]["connector"] == "fixture_market_snapshot"
    assert surface.runbook["signals"]["availability_probes"]["market_feed"]["operational_status"] == "ready"
    assert surface.runbook["signals"]["cache_fallbacks"]["user_feed"]["status"] == "ready"
    assert surface.runbook["signals"]["subscription_preview"]["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface.runbook["signals"]["probe_bundle"]["bundle_status"] == "ready"
    assert surface.runbook["signals"]["probe_bundle"]["preview_flow"]["expected_outcome"] == "preview_only_no_live_transport"
    assert surface.runbook["signals"]["capability_summary"]["market_feed_path"] == "use_cache_backed_snapshot"
    assert surface.runbook["signals"]["connector_contracts"]["market_feed"]["mode"] == "read_only"
    assert surface.runbook["signals"]["subscription_preview"]["channels"]["user_feed"]["auth_requirement"] == "none"
    assert surface.configured_endpoints["market_feed_source"] == "market-feed"


def test_polymarket_client_normalizes_nested_event_and_resolution_metadata(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    (fixtures / "markets").mkdir(parents=True)

    market = {
        "id": "pm_nested_market",
        "venueMarketId": "pm_nested_market",
        "event": {
            "id": "pm_nested_event",
            "slug": "nested-event",
            "title": "Nested event title",
        },
        "slug": "nested-market",
        "title": "Nested market title",
        "question": "Will the nested payload resolve?",
        "description": "Payload with nested event data.",
        "category": "tests",
        "active": True,
        "closed": False,
        "sourceUrl": "https://example.com/market",
        "resolutionSource": "https://example.com/resolution",
        "endDate": "2031-01-01T00:00:00Z",
        "outcomes": ["Yes", "No"],
        "outcomePrices": [0.72, 0.28],
        "liquidity": 34567,
        "volume": 76543,
        "volume24h": 6543,
        "orderBook": {
            "source": "fixture",
            "bids": [{"price": 0.7, "size": 500}],
            "asks": [{"price": 0.74, "size": 300}],
        },
        "trades": [
            {"price": 0.71, "size": 42, "side": "buy", "timestamp": "2030-12-31T23:55:00Z"},
        ],
        "clobTokenIds": ["yes_nested", "no_nested"],
    }
    (fixtures / "markets.json").write_text(json.dumps([market]), encoding="utf-8")
    (fixtures / "markets" / "pm_nested_market.json").write_text(json.dumps(market), encoding="utf-8")

    client = PolymarketClient(
        base_url="https://example.com",
        fixtures_root=str(fixtures),
        events_path="events",
        positions_path="positions",
        market_feed_path="market-feed",
        user_feed_path="user-feed",
    )

    fetched_market = client.get_market(market_id="pm_nested_market")
    events = client.get_events(market_id="pm_nested_event")
    snapshot = client.get_snapshot(fetched_market)

    assert fetched_market.market_id == "pm_nested_market"
    assert fetched_market.venue_market_id == "pm_nested_market"
    assert fetched_market.canonical_event_id == "pm_nested_event"
    assert fetched_market.event_id == "pm_nested_event"
    assert fetched_market.source_url == "https://example.com/market"
    assert fetched_market.resolution_source_url == "https://example.com/resolution"
    assert fetched_market.resolution_source == "https://example.com/resolution"
    assert fetched_market.status is MarketStatus.open
    assert fetched_market.end_date.isoformat() == "2031-01-01T00:00:00+00:00"
    assert events and events[0].canonical_event_id == "pm_nested_event"
    assert events[0].market_id == "pm_nested_market"
    assert snapshot.canonical_event_id == "pm_nested_event"
    assert snapshot.source_url == "https://example.com/market"
    assert snapshot.resolution_source == "https://example.com/resolution"
    assert snapshot.status is MarketStatus.open
    assert snapshot.venue_type == VenueType.execution
    assert snapshot.close_time.isoformat() == "2031-01-01T00:00:00+00:00"
    assert snapshot.snapshot_ts.isoformat() == "2030-12-31T23:55:00+00:00"
    assert snapshot.orderbook is not None
    assert snapshot.best_bid_yes == pytest.approx(0.7)
    assert snapshot.best_ask_yes == pytest.approx(0.74)
    assert snapshot.last_trade_price == pytest.approx(0.71)


def test_polymarket_client_falls_back_to_latest_trade_timestamp_and_market_url_alias(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    (fixtures / "markets").mkdir(parents=True)

    market = {
        "id": "pm_trade_ts_market",
        "venueMarketId": "pm_trade_ts_market",
        "eventSlug": "trade-ts-event",
        "slug": "trade-ts-market",
        "title": "Trade timestamp market",
        "question": "Will the latest trade timestamp be used?",
        "description": "Market with only trade history timestamp.",
        "category": "tests",
        "active": True,
        "closed": False,
        "marketUrl": "https://example.com/market-ts",
        "resolutionSource": "https://example.com/resolution-ts",
        "resolution_source_url": "https://example.com/resolution-ts",
        "startDate": "2032-01-01T00:00:00Z",
        "endDate": "2032-12-31T00:00:00Z",
        "outcomes": ["Yes", "No"],
        "outcomePrices": [0.44, 0.56],
        "liquidity": 45678,
        "volume": 87654,
        "volume24h": 7654,
        "orderBook": {
            "source": "fixture",
            "bids": [{"price": 0.42, "size": 1000}],
            "asks": [{"price": 0.46, "size": 800}],
        },
        "recentTrades": {
            "items": [
                {"price": 0.43, "size": 10, "side": "buy", "time": "2032-12-30T23:59:00Z"},
                {"price": 0.45, "size": 5, "side": "sell", "createdAt": "2032-12-31T00:01:00Z"},
            ]
        },
        "clobTokenIds": ["yes_trade_ts", "no_trade_ts"],
    }
    (fixtures / "markets.json").write_text(json.dumps([market]), encoding="utf-8")
    (fixtures / "markets" / "pm_trade_ts_market.json").write_text(json.dumps(market), encoding="utf-8")

    client = PolymarketClient(
        base_url="https://example.com",
        fixtures_root=str(fixtures),
        events_path="events",
        positions_path="positions",
        market_feed_path="market-feed",
        user_feed_path="user-feed",
    )

    fetched_market = client.get_market(market_id="pm_trade_ts_market")
    snapshot = client.get_snapshot(fetched_market)

    assert fetched_market.canonical_event_id == "trade-ts-event"
    assert fetched_market.source_url == "https://example.com/market-ts"
    assert fetched_market.resolution_source_url == "https://example.com/resolution-ts"
    assert snapshot.snapshot_ts.isoformat() == "2032-12-31T00:01:00+00:00"
    assert snapshot.source_url == "https://example.com/market-ts"
    assert snapshot.canonical_event_id == "trade-ts-event"
    assert snapshot.orderbook is not None
    assert snapshot.last_trade_price == pytest.approx(0.45)


def test_polymarket_client_accepts_wrapped_market_payloads_and_orderbook_aliases(monkeypatch) -> None:
    def fake_get(url: str, params=None, timeout: float | None = None, **kwargs):  # noqa: ANN001
        if url.endswith("/markets"):
            return FakeResponse(
                {
                    "markets": [
                        {
                            "id": "pm_wrapped_market",
                            "venueMarketId": "pm_wrapped_market",
                            "event": {"id": "pm_wrapped_event", "slug": "wrapped-event"},
                            "slug": "wrapped-market",
                            "question": "Will the wrapped market resolve?",
                            "active": True,
                            "closed": False,
                            "marketUrl": "https://example.com/wrapped-market",
                            "resolutionSource": "https://example.com/wrapped-resolution",
                            "startDate": "2026-04-08T00:00:00Z",
                            "endDate": "2033-01-01T00:00:00Z",
                            "outcomes": ["Yes", "No"],
                            "outcomePrices": [0.67, 0.33],
                            "liquidity": 11111,
                            "volume": 22222,
                            "volume24h": 3333,
                            "clobTokenIds": ["yes_wrapped", "no_wrapped"],
                        }
                    ]
                }
            )
        if url.endswith("/markets/pm_wrapped_market"):
            return FakeResponse(
                {
                    "market": {
                        "id": "pm_wrapped_market",
                        "venueMarketId": "pm_wrapped_market",
                        "event": {"id": "pm_wrapped_event", "slug": "wrapped-event"},
                        "slug": "wrapped-market",
                        "question": "Will the wrapped market resolve?",
                        "active": True,
                        "closed": False,
                        "marketUrl": "https://example.com/wrapped-market",
                        "resolutionSource": "https://example.com/wrapped-resolution",
                        "startDate": "2026-04-08T00:00:00Z",
                        "endDate": "2033-01-01T00:00:00Z",
                        "outcomes": ["Yes", "No"],
                        "outcomePrices": [0.67, 0.33],
                        "liquidity": 11111,
                        "volume": 22222,
                        "volume24h": 3333,
                        "book": {
                            "source": "wrapped",
                            "bids": [{"price": 0.66, "size": 1200}],
                            "asks": [{"price": 0.68, "size": 900}],
                        },
                        "recentTrades": {
                            "items": [
                                {"price": 0.67, "size": 50, "side": "buy", "createdAt": "2026-04-08T00:10:00Z"}
                            ]
                        },
                        "clobTokenIds": ["yes_wrapped", "no_wrapped"],
                    }
                }
            )
        raise AssertionError(f"unexpected URL {url!r}")

    monkeypatch.setattr("prediction_markets.polymarket.requests.get", fake_get)

    client = PolymarketClient(
        base_url="https://example.com",
        events_path="events",
        positions_path="positions",
        market_feed_path="market-feed",
        user_feed_path="user-feed",
    )

    markets = client.list_markets(limit=10)
    fetched = client.get_market(market_id="pm_wrapped_market")
    snapshot = client.get_snapshot(fetched)

    assert markets and markets[0].market_id == "pm_wrapped_market"
    assert markets[0].canonical_event_id == "pm_wrapped_event"
    assert markets[0].source_url == "https://example.com/wrapped-market"
    assert markets[0].resolution_source == "https://example.com/wrapped-resolution"
    assert snapshot.orderbook is not None
    assert snapshot.best_bid_yes == pytest.approx(0.66)
    assert snapshot.best_ask_yes == pytest.approx(0.68)
    assert snapshot.last_trade_price == pytest.approx(0.67)
    assert snapshot.canonical_event_id == "pm_wrapped_event"
    assert snapshot.snapshot_ts.isoformat() == "2026-04-08T00:10:00+00:00"


def test_polymarket_execution_surface_tracks_mock_mode_and_missing_auth(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "mock")
    monkeypatch.setenv("POLYMARKET_EXECUTION_MOCK", "1")

    surface = describe_polymarket_execution_surface()
    adapter = build_polymarket_execution_adapter()
    capability = adapter.describe_execution_capabilities()

    assert surface.backend_mode == "mock"
    assert surface.requested_backend_mode == "auto"
    assert surface.selected_backend_mode == "mock"
    assert surface.mock_transport is True
    assert surface.live_execution_ready is False
    assert surface.ready_for_live_execution is False
    assert "missing_auth_token" in surface.readiness_notes
    assert "backend_mode:mock" in surface.missing_requirements
    assert "auth_token" in surface.missing_requirements
    assert adapter.backend_mode == "mock"
    assert adapter.execution_runtime_config["requested_backend_mode"] == "auto"
    assert adapter.execution_runtime_config["selected_backend_mode"] == "mock"
    assert capability.metadata["runtime_mode"] == "mock"
    assert capability.metadata["requested_backend_mode"] == "auto"
    assert capability.metadata["selected_backend_mode"] == "mock"
    assert capability.metadata["mock_transport"] is True
    assert capability.metadata["ready_for_live_execution"] is False
    assert "backend_mode:mock" in capability.metadata["missing_requirements"]


def test_polymarket_execution_surface_tracks_auto_to_live_mode(monkeypatch) -> None:
    monkeypatch.delenv("POLYMARKET_EXECUTION_BACKEND", raising=False)
    monkeypatch.delenv("POLYMARKET_EXECUTION_MOCK", raising=False)
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/tmp/live_order")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/tmp/cancel_order")

    surface = describe_polymarket_execution_surface()
    adapter = build_polymarket_execution_adapter()
    capability = adapter.describe_execution_capabilities()

    assert surface.backend_mode == "live"
    assert surface.requested_backend_mode == "auto"
    assert surface.selected_backend_mode == "live"
    assert surface.mock_transport is False
    assert surface.live_execution_ready is True
    assert surface.ready_for_live_execution is True
    assert surface.readiness_notes == []
    assert surface.missing_requirements == []
    assert adapter.backend_mode == "live"
    assert adapter.execution_runtime_config["requested_backend_mode"] == "auto"
    assert adapter.execution_runtime_config["selected_backend_mode"] == "live"
    assert capability.metadata["runtime_mode"] == "live"
    assert capability.metadata["requested_backend_mode"] == "auto"
    assert capability.metadata["selected_backend_mode"] == "live"
    assert capability.metadata["ready_for_live_execution"] is True


def test_polymarket_order_execution_surface_tracks_live_and_mock_transports(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "mock")
    monkeypatch.setenv("POLYMARKET_EXECUTION_MOCK", "1")

    mock_surface = describe_polymarket_order_execution_surface()
    mock_adapter = build_polymarket_execution_adapter()

    monkeypatch.delenv("POLYMARKET_EXECUTION_BACKEND", raising=False)
    monkeypatch.delenv("POLYMARKET_EXECUTION_MOCK", raising=False)
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/tmp/live_order")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/tmp/cancel_order")

    live_surface = describe_polymarket_order_execution_surface()
    live_adapter = build_polymarket_execution_adapter()

    assert mock_surface.selected_backend_mode == "mock"
    assert mock_surface.transport_mode == "dry_run"
    assert mock_surface.place_auditable is True
    assert mock_surface.cancel_auditable is True
    assert mock_adapter.describe_order_execution_surface().selected_backend_mode == "mock"
    assert live_surface.selected_backend_mode == "live"
    assert live_surface.transport_mode == "live"
    assert live_surface.live_execution_ready is True
    assert live_surface.mock_transport is False
    assert live_surface.place_order_path == "/tmp/live_order"
    assert live_surface.cancel_order_path == "/tmp/cancel_order"
    assert live_adapter.describe_order_execution_surface().transport_mode == "live"


def test_polymarket_execution_adapter_blocks_live_when_runtime_is_not_ready(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "mock")
    monkeypatch.setenv("POLYMARKET_EXECUTION_MOCK", "1")

    adapter = build_polymarket_execution_adapter()
    market = MarketDescriptor(
        market_id="pm_mock_market",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Mock market",
        question="Will the mock runtime block live execution?",
        status=MarketStatus.open,
    )

    plan = adapter.build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )

    assert plan.allowed is False
    assert "polymarket_live_not_ready" in plan.blocked_reasons
    assert "polymarket_missing:backend_mode:mock" in plan.blocked_reasons
    assert plan.metadata["runtime_ready"] is False
    assert plan.metadata["runtime_blocked"] is True
    assert plan.metadata["ready_for_live_execution"] is False


def test_polymarket_execution_adapter_place_order_audits_mock_transport(monkeypatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "mock")
    monkeypatch.setenv("POLYMARKET_EXECUTION_MOCK", "1")

    adapter = build_polymarket_execution_adapter()
    market = MarketDescriptor(
        market_id="pm_place_mock",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Mock place",
        question="Will the mock place trace be audit-safe?",
        status=MarketStatus.open,
    )

    trace = adapter.place_order(
        market=market,
        run_id="run_place_mock",
        requested_quantity=2.0,
        requested_notional=20.0,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
        metadata={"source": "unit_test"},
    )

    assert trace.action is PolymarketOrderAction.place
    assert trace.transport_mode == "dry_run"
    assert trace.live_submission_bound is False
    assert trace.live_submission_attempted is False
    assert trace.live_submission_performed is False
    assert trace.order.status == "simulated"
    assert trace.order.metadata["venue_order_flow"] == "simulated"
    assert trace.request.metadata["source"] == "unit_test"
    assert "dry_run_only" in trace.notes
    assert trace.venue_order_lifecycle["venue_order_status"] == "simulated"


def test_polymarket_execution_adapter_place_and_cancel_with_injected_live_submitters(monkeypatch) -> None:
    monkeypatch.delenv("POLYMARKET_EXECUTION_BACKEND", raising=False)
    monkeypatch.delenv("POLYMARKET_EXECUTION_MOCK", raising=False)
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/tmp/live_order")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/tmp/cancel_order")

    placed_calls: list[dict[str, object]] = []
    cancelled_calls: list[dict[str, object]] = []

    def _submit_order(order, payload):  # noqa: ANN001
        placed_calls.append({"order_id": order.order_id, "payload": payload})
        return {"venue_order_id": f"venue_{order.order_id}", "status": "submitted"}

    def _cancel_order(order, payload):  # noqa: ANN001
        cancelled_calls.append({"order_id": order.order_id, "payload": payload})
        return {"venue_order_id": f"venue_{order.order_id}", "status": "cancelled"}

    adapter = build_polymarket_execution_adapter()
    adapter.order_submitter = _submit_order
    adapter.cancel_submitter = _cancel_order

    market = MarketDescriptor(
        market_id="pm_place_live",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Live place",
        question="Will the live submitter be called?",
        status=MarketStatus.open,
    )

    place_trace = adapter.place_order(
        market=market,
        run_id="run_place_live",
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        requested_quantity=1.5,
        requested_notional=15.0,
        limit_price=0.63,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
        metadata={"source": "unit_test_live"},
    )

    cancel_trace = adapter.cancel_order(
        place_trace,
        reason="manual_cancel",
        cancelled_by="unit_test",
        metadata={"source": "unit_test_live"},
    )

    assert placed_calls and placed_calls[0]["order_id"] == place_trace.order.order_id
    assert place_trace.action is PolymarketOrderAction.place
    assert place_trace.transport_mode == "live"
    assert place_trace.live_submission_bound is True
    assert place_trace.live_submission_attempted is True
    assert place_trace.live_submission_performed is True
    assert place_trace.dry_run is False
    assert place_trace.submitted_payload == {"venue_order_id": f"venue_{place_trace.order.order_id}", "status": "submitted"}
    assert place_trace.order.status == "submitted"
    assert place_trace.order.metadata["venue_order_trace_kind"] in {"local_live", "external_live"}
    assert place_trace.metadata["order_trace_audit"]["venue_order_status"] == "submitted"
    assert place_trace.order.metadata["order_trace_audit"] == place_trace.metadata["order_trace_audit"]
    assert place_trace.execution_plan["selected_backend_mode"] == "live"
    assert place_trace.execution_plan["selected_transport_mode"] == "live"
    assert place_trace.execution_plan["live_submission_bound"] is True
    assert cancelled_calls and cancelled_calls[0]["order_id"] == place_trace.order.order_id
    assert cancel_trace.action is PolymarketOrderAction.cancel
    assert cancel_trace.transport_mode == "live"
    assert cancel_trace.live_submission_bound is True
    assert cancel_trace.live_submission_attempted is True
    assert cancel_trace.live_submission_performed is True
    assert cancel_trace.dry_run is False
    assert cancel_trace.cancelled_payload == {"venue_order_id": f"venue_{place_trace.order.order_id}", "status": "cancelled"}
    assert cancel_trace.order.status == "cancelled"
    assert cancel_trace.order.cancelled_reason == "manual_cancel"
    assert cancel_trace.order.metadata["venue_order_status"] == "cancelled"
    assert cancel_trace.metadata["order_trace_audit"]["venue_order_status"] == "cancelled"
    assert cancel_trace.order.metadata["order_trace_audit"] == cancel_trace.metadata["order_trace_audit"]
    assert cancel_trace.execution_plan["selected_backend_mode"] == "live"
    assert cancel_trace.execution_plan["selected_transport_mode"] == "live"
    assert cancel_trace.execution_plan["live_submission_bound"] is True


def test_polymarket_resolution_policy_surfaces_block_missing_or_ambiguous_policies() -> None:
    client = PolymarketClient(base_url="https://example.com", fixtures_root=None)
    market = MarketDescriptor(
        market_id="pm_policy_demo",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Will the event happen eventually?",
        question="Will the event happen eventually?",
        description="Ambiguous synthetic market",
        category="tests",
        active=True,
        closed=False,
        source_url="",
        canonical_event_id="pm_policy_demo",
        event_id="pm_policy_demo",
        resolution_source="",
        resolution_source_url=None,
    )

    surface = client.describe_resolution_policy_surface(market)
    surface_via_module = describe_polymarket_resolution_policy_surface(market)
    report = build_polymarket_resolution_policy_completeness_report([market])

    assert surface.no_trade is True
    assert surface.policy_complete is False
    assert surface.policy_coherent is False
    assert surface.completeness_rate < 1.0
    assert surface.coherence_rate < 1.0
    assert surface.policy_status in {"ambiguous", "manual_review", "unavailable"}
    assert surface.manual_review_required is True
    assert surface.official_source_url is None
    assert "official_source" in surface.missing_fields
    assert surface.required_fields_count >= 1
    assert 0 <= surface.present_fields_count < surface.required_fields_count
    assert surface.content_hash
    assert surface_via_module.policy_surface.market_id == surface.policy_surface.market_id
    assert surface_via_module.policy_surface.policy_complete == surface.policy_surface.policy_complete
    assert surface_via_module.policy_surface.policy_coherent == surface.policy_surface.policy_coherent
    assert surface_via_module.policy_surface.no_trade == surface.policy_surface.no_trade
    assert report.report.market_count == 1
    assert report.report.complete_count == 0
    assert report.report.no_trade_count == 1
    assert report.report.complete_rate == pytest.approx(0.0)
    assert report.report.coherent_rate == pytest.approx(0.0)
    assert report.manual_review_rate == pytest.approx(report.report.manual_review_rate)
    assert report.ambiguous_rate == pytest.approx(report.report.ambiguous_rate)
    assert report.unavailable_rate == pytest.approx(report.report.unavailable_rate)
    assert report.content_hash


def test_polymarket_resolution_policy_surface_tracks_missing_policy_as_no_trade() -> None:
    client = PolymarketClient(base_url="https://example.com", fixtures_root=None)
    market = MarketDescriptor(
        market_id="pm_policy_missing_demo",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Will the event happen eventually?",
        question="Will the event happen eventually?",
        description="Ambiguous synthetic market without a resolution source",
        category="tests",
        active=True,
        closed=False,
        source_url="",
        canonical_event_id="pm_policy_missing_demo",
        event_id="pm_policy_missing_demo",
        resolution_source="",
        resolution_source_url=None,
    )

    surface = client.describe_resolution_policy_surface(market)
    surface_via_module = describe_polymarket_resolution_policy_surface(market)
    report = build_polymarket_resolution_policy_completeness_report([market])

    assert surface.no_trade is True
    assert surface.policy_complete is False
    assert surface.policy_coherent is False
    assert surface.completeness_rate < 1.0
    assert surface.coherence_rate < 1.0
    assert surface.content_hash
    assert surface.policy_surface.no_trade is True
    assert "missing_official_source" in surface.policy_surface.completeness_flags
    assert surface.official_source_url is None
    assert surface.manual_review_required is True
    assert surface.policy_surface.policy_complete is False
    assert surface.policy_surface.policy_coherent is False
    assert "missing_resolution_source" in surface.policy_surface.ambiguity_flags or "ambiguous_language" in surface.policy_surface.ambiguity_flags
    assert surface_via_module.policy_surface.market_id == surface.policy_surface.market_id
    assert surface_via_module.policy_surface.policy_complete == surface.policy_surface.policy_complete
    assert surface_via_module.policy_surface.policy_coherent == surface.policy_surface.policy_coherent
    assert surface_via_module.policy_surface.no_trade == surface.policy_surface.no_trade
    assert report.report.market_count == 1
    assert report.report.policy_count == 1
    assert report.report.complete_count == 0
    assert report.report.coherent_count == 0
    assert report.report.no_trade_count == 1
    assert report.report.complete_rate == pytest.approx(0.0)
    assert report.report.coherent_rate == pytest.approx(0.0)
    assert report.report.mean_policy_completeness_score < 1.0
    assert report.report.mean_policy_coherence_score < 1.0
    assert report.summary
    assert report.manual_review_rate == pytest.approx(report.report.manual_review_rate)
    assert report.content_hash


def test_polymarket_resolution_policy_surface_forces_manual_review_when_policy_is_clear_but_incomplete() -> None:
    market = MarketDescriptor(
        market_id="pm_policy_low_completeness_demo",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Will the event happen?",
        question="Will the event happen?",
        description="Synthetic market with a clear-but-incomplete resolution policy",
        category="tests",
        active=True,
        closed=False,
        source_url="https://example.com/market",
        resolution_source="https://example.com/resolution",
        resolution_source_url="https://example.com/resolution",
        canonical_event_id="pm_policy_low_completeness_demo",
        event_id="pm_policy_low_completeness_demo",
    )
    policy = ResolutionPolicy(
        market_id=market.market_id,
        venue=VenueName.polymarket,
        official_source="https://example.com/resolution",
        source_url="https://example.com/resolution",
        manual_review_required=True,
        status=ResolutionStatus.clear,
    )

    surface = describe_resolution_policy_surface_guard(market, policy=policy)
    surface_via_module = describe_polymarket_resolution_policy_surface(market)

    assert surface.policy_completeness_score <= 0.6
    assert surface.policy_coherence_score < 0.6
    assert surface.approved is False
    assert surface.can_forecast is False
    assert surface.manual_review_required is True
    assert surface.no_trade is True
    assert surface.status == ResolutionStatus.manual_review
    assert surface.policy_complete is False
    assert surface.policy_coherent is False
    assert "resolution_policy_incomplete" in surface.reasons
    assert "policy_completeness_below_forecast_threshold" in surface.completeness_flags
    assert "policy_coherence_below_forecast_threshold" in surface.coherence_flags
    assert surface_via_module.policy_surface.market_id == market.market_id
