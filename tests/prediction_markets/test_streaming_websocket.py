from __future__ import annotations

import json
import socket
import threading
from contextlib import contextmanager
from pathlib import Path

from websockets.sync.server import serve

from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.streaming import MarketStreamer, PolymarketLiveWebsocketBinding, PolymarketLiveWebsocketRuntime


class LiveBindingClient:
    def __init__(self) -> None:
        self.market = MarketDescriptor(
            market_id="pm_live_websocket",
            venue=VenueName.polymarket,
            venue_type=VenueType.execution,
            title="Live websocket market",
            question="Will the websocket binding be live?",
            slug="live-websocket-market",
            status=MarketStatus.open,
            resolution_source="https://example.com/resolution",
            token_ids=["yes_live", "no_live"],
            metadata={"condition_id": "cond_live_websocket"},
        )

    def get_market(self, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
        return self.market.model_copy(deep=True)

    def get_snapshot(self, descriptor: MarketDescriptor) -> MarketSnapshot:
        return MarketSnapshot(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            title=descriptor.title,
            question=descriptor.question,
            status=descriptor.status,
            price_yes=0.61,
            price_no=0.39,
            midpoint_yes=0.61,
            spread_bps=42.0,
            liquidity=5000.0,
            volume=12000.0,
            resolution_source=descriptor.resolution_source,
            slug=descriptor.slug,
        )

    def get_positions(self, market_id: str | None = None) -> list[dict[str, object]]:
        return [{"market_id": self.market.market_id, "venue": self.market.venue.value, "quantity": 1.0}]

    def describe_data_surface(self) -> dict[str, object]:
        return {
            "venue": VenueName.polymarket.value,
            "backend_mode": "fixture",
            "allow_live_websocket_binding": True,
            "ingestion_mode": "read_only_fixture",
            "supports_events": True,
            "supports_positions": True,
            "supports_market_feed": True,
            "supports_user_feed": True,
            "supports_websocket": False,
            "supports_rtds": False,
            "market_feed_transport": "fixture_cache",
            "user_feed_transport": "fixture_cache",
            "market_feed_status": "fixture_available",
            "user_feed_status": "fixture_available",
            "rtds_status": "unavailable",
            "events_source": "fixtures/events.json",
            "positions_source": "fixtures/positions.json",
            "market_feed_source": "fixtures/markets.json",
            "user_feed_source": "fixtures/positions.json",
            "summary": "Read-only fixture-backed feed surface.",
        }


@contextmanager
def websocket_test_server(handler):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    server = serve(handler, sock=sock, ping_interval=None, close_timeout=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"ws://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        sock.close()


def _echo_ack_server(expected_channel: str, seen_messages: list[dict[str, object]], expected_keys: set[str]):
    def handler(connection) -> None:
        subscription = json.loads(connection.recv())
        seen_messages.append(subscription)
        assert expected_keys.issubset(set(subscription))
        connection.send(json.dumps({"type": "ack", "channel": expected_channel}))
        try:
            _ = connection.recv()
        except Exception:
            pass

    return handler


def test_polymarket_live_websocket_runtime_probes_market_user_and_rtds() -> None:
    market_seen: list[dict[str, object]] = []
    user_seen: list[dict[str, object]] = []
    rtds_seen: list[dict[str, object]] = []
    client = LiveBindingClient()
    with websocket_test_server(_echo_ack_server("market", market_seen, {"type", "operation", "assets_ids"})) as market_url:
        with websocket_test_server(_echo_ack_server("user", user_seen, {"type", "operation", "markets", "auth"})) as user_url:
            with websocket_test_server(_echo_ack_server("rtds", rtds_seen, {"action", "subscriptions"})) as rtds_url:
                binding = PolymarketLiveWebsocketBinding(
                    market_websocket_url=market_url,
                    user_websocket_url=user_url,
                    rtds_url=rtds_url,
                    api_key="api-key",
                    api_secret="api-secret",
                    api_passphrase="api-passphrase",
                    gamma_auth_address="0xabc123",
                    open_timeout_seconds=2.0,
                    recv_timeout_seconds=2.0,
                )
                runtime = PolymarketLiveWebsocketRuntime(binding=binding)

                market_probe = runtime.probe_market(client.get_market())
                user_probe = runtime.probe_user(client.get_market())
                rtds_probe = runtime.probe_rtds(topics=["comments"], filters="market_id=pm_live_websocket")

    assert market_probe["status"] == "ready"
    assert market_probe["connected"] is True
    assert market_probe["subscription_sent"] is True
    assert market_probe["messages"][0]["type"] == "ack"
    assert market_seen[0]["assets_ids"] == ["yes_live", "no_live"]
    assert market_seen[0]["condition_id"] == "cond_live_websocket"

    assert user_probe["status"] == "ready"
    assert user_probe["connected"] is True
    assert user_probe["subscription_sent"] is True
    assert user_probe["messages"][0]["channel"] == "user"
    assert user_seen[0]["auth"]["apiKey"] == "api-key"
    assert user_seen[0]["markets"] == ["cond_live_websocket"]

    assert rtds_probe["status"] == "ready"
    assert rtds_probe["connected"] is True
    assert rtds_probe["subscription_sent"] is True
    assert rtds_probe["messages"][0]["channel"] == "rtds"
    assert rtds_seen[0]["subscriptions"][0]["topic"] == "comments"
    assert rtds_seen[0]["subscriptions"][0]["gamma_auth"]["address"] == "0xabc123"


def test_streamer_exposes_live_websocket_surface_when_bound(tmp_path: Path, monkeypatch) -> None:
    with websocket_test_server(_echo_ack_server("market", [], {"type", "operation", "assets_ids"})) as market_url:
        with websocket_test_server(_echo_ack_server("user", [], {"type", "operation", "markets", "auth"})) as user_url:
            with websocket_test_server(_echo_ack_server("rtds", [], {"action", "subscriptions"})) as rtds_url:
                monkeypatch.setenv("POLYMARKET_MARKET_WEBSOCKET_URL", market_url)
                monkeypatch.setenv("POLYMARKET_USER_WEBSOCKET_URL", user_url)
                monkeypatch.setenv("POLYMARKET_RTDS_URL", rtds_url)
                monkeypatch.setenv("PREDICTION_MARKETS_ENABLE_LIVE_WEBSOCKETS", "1")
                monkeypatch.setenv("POLYMARKET_WS_API_KEY", "api-key")
                monkeypatch.setenv("POLYMARKET_WS_API_SECRET", "api-secret")
                monkeypatch.setenv("POLYMARKET_WS_API_PASSPHRASE", "api-passphrase")
                monkeypatch.setenv("POLYMARKET_RTDS_GAMMA_AUTH", "0xabc123")
                streamer = MarketStreamer(client=LiveBindingClient(), paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
                session = streamer.open(market_id="pm_live_websocket")

    surface = session.describe_feed_surface()
    health = session.health()

    assert surface.websocket_status == "ready"
    assert surface.market_websocket_status == "ready"
    assert surface.user_feed_websocket_status == "ready"
    assert surface.rtds_status == "ready"
    assert surface.route_refs["market_websocket"].startswith("ws://127.0.0.1:")
    assert surface.route_refs["user_websocket"].startswith("ws://127.0.0.1:")
    assert surface.route_refs["rtds"].startswith("ws://127.0.0.1:")
    if surface.availability_probes["websocket_market"]["operational_status"] == "ready":
        assert surface.availability_probes["websocket_market"]["recommended_action"] == "open_live_websocket"
    else:
        assert surface.availability_probes["websocket_market"]["operational_status"] == "not_supported"
    if surface.availability_probes["websocket_user"]["operational_status"] == "ready":
        assert surface.availability_probes["websocket_user"]["recommended_action"] == "open_live_websocket"
    else:
        assert surface.availability_probes["websocket_user"]["operational_status"] == "not_supported"
    if surface.availability_probes["rtds"]["operational_status"] == "ready":
        assert surface.availability_probes["rtds"]["recommended_action"] == "open_live_rtds"
    else:
        assert surface.availability_probes["rtds"]["operational_status"] == "not_supported"
    assert surface.connector_contracts["websocket_market"]["mode"] in {"live_bound", "preview_only"}
    assert surface.connector_contracts["websocket_market"]["endpoint_contract"]["method"] in {"SUBSCRIBE", "PREVIEW_ONLY"}
    assert surface.connector_contracts["websocket_user"]["mode"] in {"live_bound", "preview_only"}
    assert surface.connector_contracts["rtds"]["mode"] in {"live_bound", "preview_only"}
    assert surface.subscription_preview["mode"] in {"live_bound", "preview_only"}
    assert surface.subscription_preview["supports_live_subscriptions"] in {True, False}
    assert surface.subscription_preview["channels"]["websocket_market"]["channel_spec"]["delivery_mode"] in {"push", "preview_only"}
    assert surface.subscription_preview["channels"]["websocket_user"]["channel_spec"]["delivery_mode"] in {"push", "preview_only"}
    assert surface.subscription_preview["channels"]["rtds"]["channel_spec"]["delivery_mode"] in {"push", "preview_only"}
    assert surface.subscription_preview["explicit_gaps"] == ["market_feed_is_snapshot_only", "user_feed_is_cache_proxy"]
    assert surface.subscription_preview.get("preview_only_channels", []) == []
    assert surface.capability_summary["mode"] in {"live_bound", "preview_only"}
    assert surface.capability_summary["live_claimed"] in {True, False}
    assert surface.capability_summary["subscription_mode"] in {"live_bound", "preview_only"}
    assert surface.capability_summary["rtds_usefulness"]["usable_for_live_ops"] in {True, False}
    assert health.websocket_status == "ready"
    assert health.rtds_status == "ready"
