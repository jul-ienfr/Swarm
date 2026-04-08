from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from prediction_markets import MarketDescriptor, MarketStatus, MarketUniverse, MarketUniverseConfig, PolymarketAdapter, VenueName, VenueType


def test_surrogate_adapter_exposes_read_only_capabilities() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    capabilities = adapter.describe_capabilities()
    health = adapter.health()

    assert capabilities.venue == VenueName.polymarket
    assert capabilities.discovery is True
    assert capabilities.read_only is True
    assert capabilities.execution is False
    assert capabilities.positions is True
    assert capabilities.metadata_map["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert capabilities.metadata_map["supported_order_types"] == []
    assert capabilities.metadata_map["paper_capable"] is True
    assert capabilities.metadata_map["execution_capable"] is True
    assert capabilities.metadata_map["events_capable"] is True
    assert health.healthy is True
    assert health.backend_mode == "surrogate"


def test_surrogate_adapter_lists_and_fetches_markets() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    markets = adapter.list_markets(limit=10)
    snapshot = adapter.get_snapshot(markets[0].market_id)

    assert markets
    assert all(market.venue == VenueName.polymarket for market in markets)
    assert markets[0].venue_market_id == markets[0].market_id
    assert markets[0].event_id == markets[0].canonical_event_id
    assert snapshot.market_implied_probability is not None
    assert 0.0 <= snapshot.market_implied_probability <= 1.0
    assert snapshot.orderbook is not None
    assert snapshot.snapshot_ts.isoformat().endswith("+00:00")
    assert snapshot.best_bid_yes is not None
    assert snapshot.best_ask_yes is not None
    assert snapshot.mid_probability is not None
    assert snapshot.depth_near_touch is not None
    assert snapshot.last_trade_price is not None


def test_surrogate_adapter_exposes_events_and_positions(tmp_path, monkeypatch) -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.list_markets(limit=1)[0]
    events = adapter.get_events(market.market_id)

    positions_path = tmp_path / "positions.json"
    positions_path.write_text(
        json.dumps(
            [
                {
                    "market_id": market.market_id,
                    "venue": VenueName.polymarket.value,
                    "side": "yes",
                    "quantity": 3.5,
                    "entry_price": 0.58,
                    "metadata": {"source": "fixture"},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POLYMARKET_POSITIONS_PATH", str(positions_path))
    positions = adapter.get_positions(market.market_id)

    assert events
    assert any(event.market_id == market.market_id for event in events)
    assert positions
    assert positions[0].market_id == market.market_id
    assert positions[0].quantity == 3.5
    assert positions[0].metadata["source"] == "fixture"


def test_market_universe_filters_and_ranks() -> None:
    universe = MarketUniverse(adapter=PolymarketAdapter(backend_mode="surrogate"))
    result = universe.discover(MarketUniverseConfig(query="BTC", venue=VenueName.polymarket, limit=5))

    assert result.venue == VenueName.polymarket
    assert result.markets
    assert any("btc" in market.market_id.lower() for market in result.markets)
    assert all(market.status in {MarketStatus.open, MarketStatus.resolved} for market in result.markets)


def test_market_universe_exposes_events_and_positions() -> None:
    universe = MarketUniverse(adapter=PolymarketAdapter(backend_mode="surrogate"))
    result = universe.discover(MarketUniverseConfig(venue=VenueName.polymarket, limit=1))
    market = result.markets[0]

    events = universe.events(market.market_id)
    positions = universe.positions(market.market_id)
    surface = universe.describe_data_surface()

    assert events
    assert any(event.market_id == market.market_id for event in events)
    assert events[0].venue_market_id == events[0].market_id
    assert positions is not None
    assert surface["supports_events"] is True
    assert surface["supports_positions"] is True
    assert surface["supports_discovery"] is True
    assert surface["supports_orderbook"] is True
    assert surface["supports_trades"] is True
    assert surface["supports_execution"] is False
    assert surface["supports_websocket"] is False
    assert surface["supports_rtds"] is False
    assert surface["websocket_status"] == "unavailable"
    assert surface["rtds_status"] == "unavailable"
    assert surface["market_websocket_status"] == "unavailable"
    assert surface["user_feed_websocket_status"] == "unavailable"
    assert surface["market_feed_status"] == "surrogate_available"
    assert surface["user_feed_status"] == "local_cache"
    assert surface["market_feed_connector"] == "surrogate_market_snapshot"
    assert surface["user_feed_connector"] == "local_position_cache"
    assert surface["rtds_connector"] == "unavailable"
    assert surface["market_feed_replayable"] is True
    assert surface["user_feed_replayable"] is True
    assert surface["rtds_replayable"] is False
    assert surface["market_feed_transport"] == "surrogate_snapshot"
    assert surface["user_feed_transport"] == "local_cache"
    assert surface["events_source"] == "surrogate_market_catalog"
    assert surface["positions_source"] == "local_position_cache"
    assert surface["market_feed_source"] == "surrogate_snapshot"
    assert surface["user_feed_source"] == "local_position_cache"
    assert surface["configured_endpoints"]["market_feed_source"] == "surrogate_snapshot"
    assert surface["route_refs"]["market_feed"] == "surrogate_snapshot"
    assert surface["availability_probes"]["market_feed"]["transport"] == "surrogate_snapshot"
    assert surface["availability_probes"]["market_feed"]["connector"] == "surrogate_market_snapshot"
    assert surface["availability_probes"]["market_feed"]["probe_ready"] is True
    assert surface["availability_probes"]["market_feed"]["operational_status"] == "ready"
    assert surface["availability_probes"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface["availability_probes"]["market_feed"]["severity"] == "info"
    assert surface["availability_probes"]["user_feed"]["status"] == "local_cache"
    assert surface["cache_fallbacks"]["market_feed"]["status"] == "ready"
    assert surface["cache_fallbacks"]["market_feed"]["recommended_action"] == "use_cache_fallback"
    assert surface["cache_fallbacks"]["user_feed"]["status"] == "ready"
    assert surface["cache_fallbacks"]["rtds"]["status"] == "not_configured"
    assert surface["subscription_preview"]["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface["subscription_preview"]["documented_channel_route_refs"]["rtds"] is None
    assert surface["subscription_preview"]["preview_flow"]["testable"] is True
    assert surface["subscription_preview"]["subscription_bundles"]["websocket_preview_bundle"]["preview_only"] is True
    assert surface["subscription_preview"]["channel_specs"]["websocket_market"]["explicit_gap"] == "live_websocket_not_bound"
    assert surface["subscription_preview"]["gap_summary"]["preview_only_channel_count"] == 3
    assert surface["probe_bundle"]["primary_path"] == "use_cache_backed_snapshot"
    assert surface["probe_bundle"]["preview_flow"]["expected_outcome"] == "preview_only_no_live_transport"
    assert surface["probe_bundle"]["transport_readiness"]["websocket_market"] == "not_supported"
    assert surface["probe_bundle"]["highest_severity"] == "info"
    assert surface["probe_bundle"]["gap_summary"]["live_transport_not_supported_count"] == 3
    assert surface["capability_summary"]["subscription_mode"] == "preview_only"
    assert surface["capability_summary"]["auth_requirements"]["market_feed"] == "none"
    assert surface["capability_summary"]["rtds_usefulness"]["status"] == "preview_only"
    assert surface["capability_summary"]["preview_flow"]["flow_id"].endswith("bounded_websocket_rtds_preview")
    assert surface["gap_summary"]["documented_preview_routes"]["market_websocket"] is None
    assert surface["connector_contracts"]["market_feed"]["mode"] == "read_only"
    assert surface["connector_contracts"]["market_feed"]["endpoint_contract"]["method"] == "GET"
    assert surface["connector_contracts"]["user_feed"]["session_requirement"] == "local_cache_context"
    assert surface["supports_paper_mode"] is True
    assert surface["live_streaming"] is False
    assert surface["feed_surface_status"] == "read_only"
    assert surface["feed_surface_degraded"] is True
    assert "read_only_ingestion" in surface["feed_surface_degraded_reasons"]
    assert surface["venue_type"] == "execution"
    assert surface["api_access"] == [
        "catalog",
        "snapshot",
        "events",
        "evidence",
        "orderbook",
        "trades",
        "positions",
        "orders",
        "cancel",
    ]
    assert surface["supported_order_types"] == ["limit"]
    assert surface["rate_limit_notes"]
    assert surface["automation_constraints"]
    assert surface["execution_equivalent"] is True
    assert surface["execution_like"] is False
    assert surface["paper_capable"] is True
    assert surface["execution_capable"] is True
    assert surface["feed_surface"]["supports_discovery"] is True
    assert surface["feed_surface"]["supports_paper_mode"] is True
    assert surface["feed_surface"]["supports_execution"] is False
    assert surface["feed_surface"]["supports_execution"] is False
    assert surface["feed_surface"]["websocket_status"] == "unavailable"
    assert surface["feed_surface"]["rtds_status"] == "unavailable"
    assert surface["feed_surface"]["market_websocket_status"] == "unavailable"
    assert surface["feed_surface"]["user_feed_websocket_status"] == "unavailable"
    assert surface["feed_surface"]["market_feed_replayable"] is True
    assert surface["feed_surface"]["user_feed_replayable"] is True
    assert surface["feed_surface"]["rtds_replayable"] is False
    assert surface["feed_surface"]["route_refs"]["market_feed"] == "surrogate_snapshot"
    assert surface["feed_surface"]["availability_probes"]["market_feed"]["connector"] == "surrogate_market_snapshot"
    assert surface["feed_surface"]["availability_probes"]["websocket_market"]["operational_status"] == "not_supported"
    assert surface["feed_surface"]["cache_fallbacks"]["user_feed"]["status"] == "ready"
    assert surface["feed_surface"]["subscription_preview"]["channels"]["user_feed"]["recommended_action"] == "read_user_feed_cache"
    assert surface["feed_surface"]["subscription_preview"]["preview_flow"]["testable"] is True
    assert surface["feed_surface"]["probe_bundle"]["bundle_status"] == "ready"
    assert surface["feed_surface"]["probe_bundle"]["preview_flow"]["probe_statuses"]["rtds"] == "not_supported"
    assert surface["feed_surface"]["connector_contracts"]["websocket_market"]["mode"] == "preview_only"
    assert surface["feed_surface"]["connector_contracts"]["websocket_market"]["endpoint_contract"]["method"] == "PREVIEW_ONLY"
    assert surface["feed_surface"]["degraded"] is True
    assert surface["coverage_report"]["venue_count"] >= 6
    assert surface["availability_by_venue"]["polymarket"]["status"] == "live"
    assert surface["registry_coverage"]["execution_capable_count"] == 2
    assert surface["registry_coverage"]["metadata_gap_rate"] >= 0.0
    assert surface["registry_coverage"]["execution_surface_rate"] > 0.0


def test_market_universe_exposes_health_surface() -> None:
    universe = MarketUniverse(adapter=PolymarketAdapter(backend_mode="surrogate"))

    health_surface = universe.describe_health_surface()

    assert health_surface["venue"] == "polymarket"
    assert health_surface["backend_mode"] == "surrogate"
    assert health_surface["supports_websocket"] is False
    assert health_surface["supports_rtds"] is False
    assert health_surface["websocket_status"] == "unavailable"
    assert health_surface["rtds_status"] == "unavailable"
    assert health_surface["market_websocket_status"] == "unavailable"
    assert health_surface["user_feed_websocket_status"] == "unavailable"
    assert health_surface["market_feed_status"] == "surrogate_available"
    assert health_surface["user_feed_status"] == "local_cache"
    assert health_surface["market_feed_replayable"] is True
    assert health_surface["user_feed_replayable"] is True
    assert health_surface["rtds_replayable"] is False
    assert health_surface["market_feed_connector"] == "surrogate_market_snapshot"
    assert health_surface["user_feed_connector"] == "local_position_cache"
    assert health_surface["rtds_connector"] == "unavailable"
    assert health_surface["route_refs"]["market_feed"] == "surrogate_snapshot"
    assert health_surface["availability_probes"]["market_feed"]["transport"] == "surrogate_snapshot"
    assert health_surface["availability_probes"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert health_surface["cache_fallbacks"]["user_feed"]["status"] == "ready"
    assert health_surface["subscription_preview"]["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert health_surface["subscription_preview"]["preview_flow"]["testable"] is True
    assert health_surface["probe_bundle"]["primary_path"] == "use_cache_backed_snapshot"
    assert health_surface["probe_bundle"]["preview_flow"]["expected_outcome"] == "preview_only_no_live_transport"
    assert health_surface["probe_bundle"]["transport_readiness"]["rtds"] == "not_supported"
    assert health_surface["probe_bundle"]["highest_severity"] == "info"
    assert health_surface["gap_summary"]["preview_only_channel_count"] == 3
    assert health_surface["capability_summary"]["market_feed_path"] == "use_cache_backed_snapshot"
    assert health_surface["capability_summary"]["documented_preview_routes"]["market_websocket"] is None
    assert health_surface["capability_summary"]["preview_flow"]["flow_id"].endswith("bounded_websocket_rtds_preview")
    assert health_surface["connector_contracts"]["user_feed"]["mode"] == "read_only"
    assert health_surface["feed_surface_status"] == "read_only"
    assert health_surface["feed_surface_degraded"] is True
    assert "read_only_ingestion" in health_surface["feed_surface_degraded_reasons"]
    assert health_surface["execution_equivalent"] is True
    assert health_surface["execution_capable"] is True
    assert health_surface["paper_capable"] is True
    assert health_surface["read_only"] is False
    assert isinstance(health_surface["feed_surface_summary"], str)
    assert health_surface["rate_limit_notes"]
    assert health_surface["automation_constraints"]


def test_market_universe_propagates_live_websocket_and_rtds_surfaces() -> None:
    class LiveSurfaceAdapter:
        backend_mode = "live"

        def describe_capabilities(self):
            return SimpleNamespace(
                venue=VenueName.polymarket,
                discovery=True,
                read_only=False,
                execution=False,
                positions=True,
                orderbook=True,
                trades=True,
                metadata_map={
                    "backend_mode": "live",
                    "api_access": [
                        "catalog",
                        "snapshot",
                        "orderbook",
                        "trades",
                        "positions",
                        "events",
                        "evidence",
                    ],
                    "supported_order_types": ["limit"],
                },
                supported_order_types=["limit"],
                rate_limit_notes=["live websocket bound"],
                automation_constraints=[],
            )

        def describe_data_surface(self):
            return {
                "venue": VenueName.polymarket.value,
                "venue_type": "execution",
                "backend_mode": "live",
                "ingestion_mode": "live_streaming",
                "supports_discovery": True,
                "supports_orderbook": True,
                "supports_trades": True,
                "supports_execution": True,
                "supports_paper_mode": True,
                "supports_market_feed": True,
                "supports_user_feed": True,
                "supports_events": True,
                "supports_positions": True,
                "supports_websocket": True,
                "supports_rtds": True,
                "live_streaming": True,
                "market_feed_status": "configured_endpoint",
                "user_feed_status": "configured_endpoint",
                "market_websocket_status": "configured_endpoint",
                "user_feed_websocket_status": "configured_endpoint",
                "rtds_status": "configured_endpoint",
                "market_feed_transport": "websocket",
                "user_feed_transport": "websocket",
                "market_feed_connector": "live_market_websocket",
                "user_feed_connector": "live_user_websocket",
                "rtds_connector": "live_rtds",
                "market_feed_replayable": False,
                "user_feed_replayable": False,
                "rtds_replayable": False,
                "market_feed_cache_backed": False,
                "user_feed_cache_backed": False,
                "rtds_cache_backed": False,
                "events_source": "markets",
                "positions_source": "positions",
                "market_feed_source": "market-feed",
                "user_feed_source": "user-feed",
                "configured_endpoints": {
                    "events_source": "markets",
                    "positions_source": "positions",
                    "market_feed_source": "market-feed",
                    "user_feed_source": "user-feed",
                },
                "route_refs": {
                    "market_feed": "market-feed",
                    "user_feed": "user-feed",
                    "market_websocket": "wss://ws-subscriptions-clob.polymarket.com/ws/market",
                    "user_websocket": "wss://ws-subscriptions-clob.polymarket.com/ws/user",
                    "rtds": "wss://ws-live-data.polymarket.com",
                },
            }

    universe = MarketUniverse(adapter=LiveSurfaceAdapter())
    surface = universe.describe_data_surface()
    health_surface = universe.describe_health_surface()

    assert surface["supports_websocket"] is True
    assert surface["supports_rtds"] is True
    assert surface["market_websocket_status"] == "configured_endpoint"
    assert surface["user_feed_websocket_status"] == "configured_endpoint"
    assert surface["rtds_status"] == "configured_endpoint"
    assert surface["availability_probes"]["websocket_market"]["operational_status"] == "ready"
    assert surface["availability_probes"]["websocket_user"]["operational_status"] == "ready"
    assert surface["availability_probes"]["rtds"]["operational_status"] == "ready"
    assert surface["connector_contracts"]["websocket_market"]["mode"] == "live_bound"
    assert surface["connector_contracts"]["websocket_user"]["mode"] == "live_bound"
    assert surface["connector_contracts"]["rtds"]["mode"] == "live_bound"
    assert surface["subscription_preview"]["mode"] == "live_bound"
    assert surface["subscription_preview"]["supports_live_subscriptions"] is True
    assert "websocket_market_not_bound" not in surface["gap_summary"]["explicit_gaps"]
    assert "websocket_user_not_bound" not in surface["gap_summary"]["explicit_gaps"]
    assert "rtds_not_bound" not in surface["gap_summary"]["explicit_gaps"]
    assert health_surface["supports_websocket"] is True
    assert health_surface["supports_rtds"] is True
    assert health_surface["market_websocket_status"] == "configured_endpoint"
    assert health_surface["user_feed_websocket_status"] == "configured_endpoint"


def test_market_universe_deduplicates_quasi_duplicate_markets_without_canonical_ids() -> None:
    class DuplicateAdapter:
        def list_markets(self, config=None, limit: int = 25):
            return [
                MarketDescriptor(
                    market_id="dup_a",
                    venue=VenueName.polymarket,
                    venue_type=VenueType.execution,
                    title="Will BTC trade above 120k by year end 2026?",
                    question="Will BTC trade above 120k by year end 2026?",
                    resolution_source="https://example.com/resolution",
                    liquidity=1000.0,
                    status=MarketStatus.open,
                ),
                MarketDescriptor(
                    market_id="dup_b",
                    venue=VenueName.polymarket,
                    venue_type=VenueType.execution,
                    title="Will BTC trade above 120k by year end 2026?",
                    question="Will BTC trade above 120k by year end 2026?",
                    resolution_source="https://example.com/resolution",
                    liquidity=500.0,
                    status=MarketStatus.open,
                ),
                MarketDescriptor(
                    market_id="unique_c",
                    venue=VenueName.polymarket,
                    venue_type=VenueType.execution,
                    title="Will unemployment rise in 2026?",
                    question="Will unemployment rise in 2026?",
                    resolution_source="https://example.com/resolution",
                    liquidity=700.0,
                    status=MarketStatus.open,
                ),
            ][:limit]

    universe = MarketUniverse(adapter=DuplicateAdapter())
    result = universe.discover(MarketUniverseConfig(venue=VenueName.polymarket, limit=25))

    assert [market.market_id for market in result.markets] == ["dup_a", "unique_c"]
    assert result.metadata["dedupe_group_count"] == 2
    assert "dup_b" in result.metadata["deduplicated_market_ids"]
    assert result.metadata["input_count"] == 3
    assert result.metadata["eligible_market_count"] == 3
    assert result.metadata["kept_count"] == 2
    assert result.metadata["kept_rate"] == pytest.approx(2 / 3, rel=1e-6)
    assert result.metadata["coverage_gap_count"] == 1
    assert result.metadata["coverage_gap_rate"] == pytest.approx(1 / 3, rel=1e-6)
    assert result.metadata["duplicate_market_count"] == 1
    assert result.metadata["duplicate_market_rate"] == pytest.approx(1 / 3, rel=1e-6)
    assert result.metadata["duplicate_group_count"] == 1
    assert result.metadata["max_dedupe_group_size"] == 2
    assert result.metadata["coverage_after_dedupe_rate"] == pytest.approx(2 / 3, rel=1e-6)
    assert result.metadata["dedupe_rate"] > 0.0
