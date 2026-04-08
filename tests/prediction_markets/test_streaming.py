from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.streaming import (
    MarketStreamEvent,
    MarketStreamHealth,
    MarketStreamer,
    StreamCollectionPriority,
    StreamCollectionRequest,
    StreamEventKind,
    monitor_venue_health,
)


class MutableSnapshotClient:
    def __init__(self) -> None:
        self.market = MarketDescriptor(
            market_id="pm_stream_test",
            venue=VenueName.polymarket,
            venue_type=VenueType.execution,
            title="Streaming market",
            question="Will the stream change?",
            slug="stream-market",
            status=MarketStatus.open,
            resolution_source="https://example.com/resolution",
            liquidity=5000.0,
            volume=12000.0,
        )
        self.price_yes = 0.55
        self.spread_bps = 120.0

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
            price_yes=self.price_yes,
            price_no=round(1.0 - self.price_yes, 6),
            midpoint_yes=self.price_yes,
            spread_bps=self.spread_bps,
            liquidity=descriptor.liquidity,
            volume=descriptor.volume,
            resolution_source=descriptor.resolution_source,
            slug=descriptor.slug,
        )

    def get_events(self, *, market_id: str | None = None, limit: int = 20) -> list[MarketDescriptor]:
        market = self.get_market(market_id=market_id)
        extra = market.model_copy(update={"market_id": f"{market.market_id}_event", "canonical_event_id": market.canonical_event_id or market.market_id})
        return [market, extra][:limit]

    def get_positions(self, *, market_id: str | None = None) -> list:
        market = self.get_market(market_id=market_id)
        return [
            {
                "market_id": market.market_id,
                "venue": market.venue.value,
                "side": "yes",
                "quantity": 2.0,
                "entry_price": self.price_yes,
                "metadata": {"source": "mutable_snapshot_client"},
            }
        ]

    def describe_data_surface(self) -> dict[str, object]:
        return {
            "venue": VenueName.polymarket.value,
            "backend_mode": "test",
            "supports_events": True,
            "supports_positions": True,
            "supports_market_feed": True,
            "supports_user_feed": True,
            "events_source": "mutable_snapshot_client",
            "positions_source": "mutable_snapshot_client",
            "market_feed_source": "mutable_snapshot_client",
            "user_feed_source": "mutable_snapshot_client",
        }


class FixtureSurfaceClient(MutableSnapshotClient):
    def describe_data_surface(self) -> dict[str, object]:
        return {
            "venue": VenueName.polymarket.value,
            "backend_mode": "fixture",
            "ingestion_mode": "read_only_fixture",
            "supports_events": True,
            "supports_positions": True,
            "supports_market_feed": True,
            "supports_user_feed": True,
            "supports_websocket": False,
            "supports_rtds": False,
            "live_streaming": False,
            "market_feed_transport": "fixture_cache",
            "user_feed_transport": "fixture_cache",
            "market_feed_status": "fixture_available",
            "user_feed_status": "fixture_available",
            "rtds_status": "unavailable",
            "events_source": "fixtures/events.json",
            "positions_source": "fixtures/positions.json",
            "market_feed_source": "fixtures/markets.json",
            "user_feed_source": "fixtures/positions.json",
            "configured_endpoints": {
                "events_source": "fixtures/events.json",
                "positions_source": "fixtures/positions.json",
                "market_feed_source": "fixtures/markets.json",
                "user_feed_source": "fixtures/positions.json",
            },
            "summary": "Read-only fixture-backed feed surface; websocket and RTDS are not implemented here.",
        }


class MultiMarketSnapshotClient:
    def __init__(self, *, fail_once_for: set[str] | None = None, stale_for: set[str] | None = None) -> None:
        self.fail_once_for = set(fail_once_for or set())
        self.stale_for = set(stale_for or set())
        self.seen_failures: set[str] = set()
        self.markets = {
            "pm_low": MarketDescriptor(
                market_id="pm_low",
                venue=VenueName.polymarket,
                venue_type=VenueType.execution,
                title="Low liquidity market",
                question="Will the low market move?",
                slug="low-market",
                status=MarketStatus.open,
                liquidity=1000.0,
                volume=5000.0,
            ),
            "pm_high": MarketDescriptor(
                market_id="pm_high",
                venue=VenueName.polymarket,
                venue_type=VenueType.execution,
                title="High liquidity market",
                question="Will the high market move?",
                slug="high-market",
                status=MarketStatus.open,
                liquidity=9000.0,
                volume=40000.0,
            ),
            "pm_retry": MarketDescriptor(
                market_id="pm_retry",
                venue=VenueName.polymarket,
                venue_type=VenueType.execution,
                title="Retry market",
                question="Will retries work?",
                slug="retry-market",
                status=MarketStatus.open,
                liquidity=2500.0,
                volume=10000.0,
            ),
        }
        self.price_yes = {
            "pm_low": 0.31,
            "pm_high": 0.68,
            "pm_retry": 0.52,
        }
        self.spread_bps = {
            "pm_low": 180.0,
            "pm_high": 60.0,
            "pm_retry": 90.0,
        }
        self.call_counts: dict[str, int] = {"pm_low": 0, "pm_high": 0, "pm_retry": 0}

    def get_market(self, market_id: str | None = None, slug: str | None = None) -> MarketDescriptor:
        if market_id is not None:
            return self.markets[market_id].model_copy(deep=True)
        if slug is not None:
            for market in self.markets.values():
                if market.slug == slug:
                    return market.model_copy(deep=True)
        raise KeyError(market_id or slug)

    def get_snapshot(self, descriptor: MarketDescriptor) -> MarketSnapshot:
        market_id = descriptor.market_id
        self.call_counts[market_id] += 1
        if market_id in self.fail_once_for and market_id not in self.seen_failures:
            self.seen_failures.add(market_id)
            raise RuntimeError(f"transient failure for {market_id}")
        return MarketSnapshot(
            market_id=descriptor.market_id,
            venue=descriptor.venue,
            venue_type=descriptor.venue_type,
            title=descriptor.title,
            question=descriptor.question,
            status=descriptor.status,
            price_yes=self.price_yes[market_id],
            price_no=round(1.0 - self.price_yes[market_id], 6),
            midpoint_yes=self.price_yes[market_id],
            spread_bps=self.spread_bps[market_id],
            liquidity=descriptor.liquidity,
            volume=descriptor.volume,
            resolution_source=descriptor.resolution_source,
            slug=descriptor.slug,
            staleness_ms=4_500_000.0 if market_id in self.stale_for else None,
        )


def test_stream_session_persists_initial_snapshot(tmp_path: Path) -> None:
    streamer = MarketStreamer(client=MutableSnapshotClient(), paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(market_id="pm_stream_test")

    event = session.poll_once()
    loaded_events = session.load_events()
    manifest = streamer.store.load_manifest(session.stream_id)

    assert event.kind == StreamEventKind.snapshot
    assert event.sequence == 1
    assert event.changed_fields == []
    assert isinstance(event, MarketStreamEvent)
    assert loaded_events and loaded_events[0].snapshot.market_id == "pm_stream_test"
    assert manifest.poll_count == 1
    assert manifest.event_count == 1
    assert Path(manifest.events_path).exists()
    assert Path(manifest.snapshot_path).exists()


def test_stream_session_detects_changes_and_reloads(tmp_path: Path) -> None:
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(slug="stream-market")

    first = session.poll_once()
    client.price_yes = 0.63
    client.spread_bps = 80.0
    second = session.poll_once()

    reloaded = streamer.load(session.stream_id)
    events = reloaded.load_events()
    manifest = streamer.store.load_manifest(session.stream_id)

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.kind == StreamEventKind.change
    assert "price_yes" in second.changed_fields
    assert "spread_bps" in second.changed_fields
    assert len(events) == 2
    assert events[-1].snapshot.price_yes == 0.63
    assert manifest.latest_sequence == 2
    assert manifest.event_count == 2
    assert manifest.latest_snapshot_id == events[-1].snapshot.snapshot_id


def test_streamer_lists_manifests(tmp_path: Path) -> None:
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(market_id="pm_stream_test")
    session.poll_once()

    manifests = streamer.list_streams()

    assert manifests
    assert manifests[0].market_id == "pm_stream_test"
    assert manifests[0].market_slug == "stream-market"


def test_stream_collection_reports_ops_metrics(tmp_path: Path) -> None:
    client = MultiMarketSnapshotClient(fail_once_for={"pm_retry"}, stale_for={"pm_low"})
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    request = StreamCollectionRequest(
        market_ids=["pm_low", "pm_high", "pm_retry"],
        fanout=3,
        retries=1,
        timeout_seconds=2.0,
        cache_ttl_seconds=120.0,
        prefetch=True,
        poll_count=1,
        stale_after_seconds=3600.0,
    )

    first = streamer.collect(request)
    second = streamer.collect(request)

    assert first.metrics is not None
    assert first.metrics.decision_latency_budget_ms == 2000.0
    assert first.metrics.decision_latency_p50_ms is not None
    assert first.metrics.decision_latency_p95_ms is not None
    assert first.metrics.snapshot_freshness_mean_ms is not None
    assert first.metrics.snapshot_freshness_p95_ms is not None
    assert first.metrics.health_score_mean is not None
    assert first.metrics.health_score_p95 is not None
    assert first.metrics.degraded_mode_rate == pytest.approx(1 / 3, rel=1e-3)
    assert first.metrics.cache_recovery_count == 1
    assert first.metrics.cache_hit_rate == 0.0
    assert first.metrics.availability_rate == 1.0
    assert first.metrics.availability_by_venue["polymarket"]["requested"] == 3
    assert first.metrics.availability_by_venue["polymarket"]["available"] == 3
    assert first.metrics.availability_by_venue["polymarket"]["availability_rate"] == 1.0
    assert first.metrics.metadata_gap_count >= 1
    assert first.metrics.metadata_gap_rate > 0.0
    assert all(sample is not None for sample in first.metrics.latency_samples_ms)
    assert all(sample is not None for sample in first.metrics.freshness_samples_ms)
    assert all(sample is not None for sample in first.metrics.health_score_samples)
    assert second.cache_hit_count == 3
    assert second.cache_hit_rate == 1.0
    assert second.metrics is not None
    assert second.metrics.cache_hit_rate == 1.0
    assert second.metrics.cache_recovery_count == 0
    assert second.metrics.degraded_mode_rate == pytest.approx(1 / 3, rel=1e-3)
    assert second.metrics.availability_by_venue["polymarket"]["availability_rate"] == 1.0


def test_stream_summary_and_health_are_richer(tmp_path: Path) -> None:
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(market_id="pm_stream_test")
    session.poll_once()
    client.price_yes = 0.63
    client.spread_bps = 80.0
    session.poll_once()

    summary = session.summarize()
    health = session.health()

    assert summary.event_count == 2
    assert summary.change_event_count == 1
    assert summary.change_rate == 1.0
    assert summary.trend == "bullish"
    assert summary.price_yes_change == 0.08
    assert summary.spread_bps_change == -40.0
    assert summary.narrative
    assert summary.changed_field_counts["price_yes"] == 1
    assert summary.changed_field_counts["spread_bps"] == 1

    assert health.healthy is True
    assert health.freshness_status in {"fresh", "warm"}
    assert health.latest_sequence == 2
    assert health.event_count == 2
    assert health.message == "healthy"


def test_stream_session_exposes_events_positions_and_feed_surface(tmp_path: Path) -> None:
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(market_id="pm_stream_test")

    events = session.events()
    positions = session.positions()
    surface = session.describe_feed_surface()
    manifest = streamer.store.load_manifest(session.stream_id)

    assert events
    assert events[0].market_id == "pm_stream_test"
    assert positions
    assert positions[0].market_id == "pm_stream_test"
    assert surface.supports_events is True
    assert surface.supports_positions is True
    assert surface.supports_discovery is True
    assert surface.supports_orderbook is True
    assert surface.supports_trades is True
    assert surface.supports_execution is True
    if surface.websocket_status == "ready":
        assert surface.market_websocket_status == "ready"
        assert surface.user_feed_websocket_status == "ready"
        assert surface.rtds_status == "ready"
    else:
        assert surface.websocket_status == "unavailable"
        assert surface.market_websocket_status == "unavailable"
        assert surface.user_feed_websocket_status == "unavailable"
    assert surface.supports_paper_mode is True
    assert surface.market_feed_kind == "market_snapshot"
    assert surface.user_feed_kind == "position_snapshot"
    assert surface.market_feed_connector == "mutable_snapshot_client"
    assert surface.user_feed_connector == "mutable_snapshot_client"
    if surface.websocket_status == "ready":
        assert surface.rtds_connector != "unavailable"
    else:
        assert surface.rtds_connector == "unavailable"
    assert surface.market_feed_replayable is True
    assert surface.user_feed_replayable is True
    assert surface.rtds_replayable is False
    assert surface.market_feed_cache_backed is True
    assert surface.user_feed_cache_backed is True
    assert surface.route_refs["events"] == "mutable_snapshot_client"
    assert surface.route_refs["market_feed"] == "mutable_snapshot_client"
    assert surface.availability_probes["market_feed"]["connector"] == "mutable_snapshot_client"
    assert surface.availability_probes["market_feed"]["transport"] == "surrogate_snapshot"
    assert surface.availability_probes["market_feed"]["cache_backed"] is True
    assert surface.availability_probes["market_feed"]["probe_ready"] is True
    assert surface.availability_probes["market_feed"]["operational_status"] == "ready"
    assert surface.availability_probes["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface.availability_probes["market_feed"]["severity"] == "info"
    assert surface.availability_probes["market_feed"]["gap_reason"] == "snapshot_only_no_push"
    assert surface.availability_probes["websocket_market"]["status"] == "unavailable"
    assert surface.availability_probes["websocket_market"]["operational_status"] == "not_supported"
    assert surface.availability_probes["websocket_market"]["recommended_action"] == "do_not_assume_live_websocket"
    assert surface.availability_probes["websocket_market"]["documented_route_ref"] is None
    assert surface.availability_probes["websocket_market"]["gap_class"] == "not_bound"
    assert surface.availability_probes["user_feed"]["gap_class"] == "cache_proxy"
    assert surface.cache_fallbacks["market_feed"]["status"] == "ready"
    assert surface.cache_fallbacks["market_feed"]["operational_status"] == "ready"
    assert surface.cache_fallbacks["market_feed"]["recommended_action"] == "use_cache_fallback"
    assert surface.cache_fallbacks["user_feed"]["status"] == "ready"
    assert surface.cache_fallbacks["rtds"]["status"] == "not_configured"
    assert surface.subscription_preview["mode"] == "preview_only"
    assert surface.subscription_preview["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface.subscription_preview["channels"]["market_feed"]["subscription_intent"] == "poll_snapshot"
    assert surface.subscription_preview["channels"]["market_feed"]["channel_spec"]["delivery_mode"] == "pull"
    assert surface.subscription_preview["channel_specs"]["websocket_market"]["explicit_gap"] == "live_websocket_not_bound"
    assert surface.subscription_preview["channel_specs"]["websocket_market"]["gap_class"] == "not_bound"
    assert surface.subscription_preview["subscription_bundles"]["websocket_preview_bundle"]["preview_only"] is True
    assert surface.subscription_preview["preview_flow"]["testable"] is True
    assert surface.subscription_preview["preview_flow"]["expected_outcome"] == "preview_only_no_live_transport"
    assert surface.subscription_preview["gap_summary"]["preview_only_channel_count"] == 3
    assert surface.subscription_preview["recommended_subscriptions"][0]["channel"] == "market_feed"
    assert surface.subscription_preview["documented_channel_route_refs"]["websocket_market"] is None
    assert surface.subscription_preview["explicit_gaps"][-1] == "rtds_not_bound"
    assert surface.probe_bundle["bundle_status"] == "ready"
    assert surface.probe_bundle["primary_path"] == "use_cache_backed_snapshot"
    assert surface.probe_bundle["transport_readiness"]["websocket_market"] == "not_supported"
    assert surface.probe_bundle["preview_flow"]["probe_statuses"]["rtds"] == "not_supported"
    assert "websocket_market" in surface.probe_bundle["degraded_paths"]
    assert surface.probe_bundle["highest_severity"] == "info"
    assert surface.probe_bundle["gap_summary"]["live_transport_not_supported_count"] == 3
    assert surface.capability_summary["subscription_mode"] == "preview_only"
    assert surface.capability_summary["auth_requirements"]["market_feed"] == "none"
    assert "user_feed_is_cache_proxy" in surface.capability_summary["market_user_gap_reasons"]
    assert surface.capability_summary["rtds_usefulness"]["status"] == "preview_only"
    assert surface.capability_summary["preview_flow"]["flow_id"].endswith("bounded_websocket_rtds_preview")
    assert surface.capability_summary["gap_summary"]["documented_preview_routes"]["rtds"] is None
    assert surface.connector_contracts["market_feed"]["mode"] == "read_only"
    assert surface.connector_contracts["market_feed"]["endpoint_contract"]["method"] == "GET"
    assert surface.connector_contracts["websocket_market"]["auth_session"]["session_requirement"] == "preview_only"
    assert surface.connector_contracts["websocket_market"]["mode"] == "preview_only"
    assert surface.connector_contracts["user_feed"]["session_requirement"] == "local_cache_context"
    assert surface.market_feed_source == "mutable_snapshot_client"
    assert surface.venue_type == "execution"
    assert surface.api_access == [
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
    assert surface.supported_order_types == ["limit"]
    assert surface.rate_limit_notes
    assert surface.automation_constraints
    assert surface.degraded is True
    assert "read_only_ingestion" in surface.degraded_reasons
    if manifest.data_surface_runbook["feed_mode"] == "live_bound":
        assert manifest.data_surface_runbook["streaming_mode"] == "live_websocket_rtds"
        assert manifest.data_surface_runbook["signals"]["rtds_status"] == "ready"
    else:
        assert manifest.data_surface_runbook["feed_mode"] == "read_only"
        assert manifest.data_surface_runbook["streaming_mode"] == "read_only_snapshot_polling"
        assert manifest.data_surface_runbook["signals"]["rtds_status"] == "unavailable"
    assert manifest.data_surface_runbook["signals"]["market_feed_connector"] == "mutable_snapshot_client"
    assert manifest.data_surface_runbook["signals"]["user_feed_connector"] == "mutable_snapshot_client"
    assert manifest.data_surface_runbook["signals"]["market_feed_replayable"] is True
    assert manifest.data_surface_runbook["signals"]["user_feed_replayable"] is True
    assert manifest.data_surface_runbook["signals"]["route_refs"]["market_feed"] == "mutable_snapshot_client"
    assert manifest.data_surface_runbook["signals"]["availability_probes"]["market_feed"]["connector"] == "mutable_snapshot_client"
    assert manifest.data_surface_runbook["signals"]["cache_fallbacks"]["market_feed"]["status"] == "ready"
    assert manifest.data_surface_runbook["signals"]["subscription_preview"]["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert manifest.data_surface_runbook["signals"]["probe_bundle"]["primary_path"] == "use_cache_backed_snapshot"
    assert manifest.data_surface_runbook["signals"]["connector_contracts"]["market_feed"]["mode"] == "read_only"
    assert manifest.data_surface_runbook["signals"]["connector_contracts"]["market_feed"]["endpoint_contract"]["response_kind"] == "market_snapshot"
    assert manifest.data_surface_runbook["signals"]["feed_surface_degraded"] is True
    assert "read_only_ingestion" in manifest.data_surface_runbook["signals"]["feed_surface_degraded_reasons"]
    assert manifest.metadata["data_surface"]["supports_market_feed"] is True
    if manifest.metadata["data_surface"]["market_websocket_status"] == "ready":
        assert manifest.metadata["data_surface"]["user_feed_websocket_status"] == "ready"
    else:
        assert manifest.metadata["data_surface"]["market_websocket_status"] == "unavailable"
        assert manifest.metadata["data_surface"]["user_feed_websocket_status"] == "unavailable"
    assert manifest.metadata["data_surface"]["market_feed_connector"] == "mutable_snapshot_client"
    assert manifest.metadata["data_surface"]["user_feed_connector"] == "mutable_snapshot_client"
    assert manifest.metadata["data_surface"]["market_feed_replayable"] is True
    assert manifest.metadata["data_surface"]["user_feed_replayable"] is True
    assert manifest.metadata["data_surface"]["route_refs"]["market_feed"] == "mutable_snapshot_client"
    assert manifest.metadata["data_surface"]["availability_probes"]["user_feed"]["connector"] == "mutable_snapshot_client"
    assert manifest.metadata["data_surface"]["cache_fallbacks"]["rtds"]["status"] == "not_configured"
    assert manifest.metadata["data_surface"]["subscription_preview"]["channels"]["websocket_market"]["status"] == "not_supported"
    assert manifest.metadata["data_surface"]["probe_bundle"]["probe_count"] == 5
    assert manifest.metadata["data_surface"]["capability_summary"]["market_feed_path"] == "use_cache_backed_snapshot"
    assert manifest.metadata["data_surface"]["capability_summary"]["documented_preview_routes"]["rtds"] is None
    assert manifest.metadata["data_surface"]["connector_contracts"]["user_feed"]["mode"] == "read_only"
    assert manifest.metadata["data_surface"]["supports_discovery"] is True
    assert manifest.metadata["data_surface"]["supports_orderbook"] is True
    assert manifest.metadata["data_surface"]["supports_trades"] is True
    assert manifest.metadata["data_surface"]["supports_execution"] is True
    assert manifest.metadata["data_surface"]["supports_paper_mode"] is True
    assert manifest.data_surface_runbook["runbook_id"] == "polymarket_read_only_feed_surface"
    if manifest.metadata["data_surface"]["market_websocket_status"] == "ready":
        assert manifest.data_surface_runbook["signals"]["supports_websocket"] is True
    else:
        assert manifest.data_surface_runbook["signals"]["supports_websocket"] is False


def test_stream_session_preserves_read_only_feed_summary_and_status(tmp_path: Path) -> None:
    client = FixtureSurfaceClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))
    session = streamer.open(market_id="pm_stream_test")

    session.poll_once()
    surface = session.describe_feed_surface()
    health = session.health()
    manifest = streamer.store.load_manifest(session.stream_id)

    assert surface.ingestion_mode == "read_only_fixture"
    assert surface.market_feed_status == "fixture_available"
    assert surface.user_feed_status == "fixture_available"
    assert surface.summary.startswith("Read-only fixture-backed feed surface")
    if surface.websocket_status == "ready":
        assert surface.market_websocket_status == "ready"
        assert surface.user_feed_websocket_status == "ready"
        assert surface.rtds_status == "ready"
    else:
        assert surface.websocket_status == "unavailable"
        assert surface.market_websocket_status == "unavailable"
        assert surface.user_feed_websocket_status == "unavailable"
    assert surface.market_feed_connector == "fixture_cache"
    assert surface.user_feed_connector == "fixture_cache"
    assert surface.market_feed_replayable is True
    assert surface.user_feed_replayable is True
    assert surface.market_feed_cache_backed is True
    assert surface.user_feed_cache_backed is True
    assert surface.route_refs["market_feed"] == "fixtures/markets.json"
    assert surface.route_refs["user_feed"] == "fixtures/positions.json"
    assert surface.availability_probes["market_feed"]["transport"] == "fixture_cache"
    assert surface.availability_probes["market_feed"]["status"] == "fixture_available"
    assert surface.availability_probes["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert surface.cache_fallbacks["market_feed"]["status"] == "ready"
    assert surface.cache_fallbacks["user_feed"]["status"] == "ready"
    assert surface.cache_fallbacks["user_feed"]["recommended_action"] == "use_cache_fallback"
    assert surface.subscription_preview["channels"]["market_feed"]["status"] == "ready"
    assert surface.subscription_preview["subscription_bundles"]["poll_snapshot_bundle"]["testable"] is True
    assert surface.subscription_preview["preview_flow"]["route_refs"]["market_feed"] == "fixtures/markets.json"
    assert surface.subscription_preview["gap_summary"]["cache_backed_channel_count"] == 2
    assert surface.probe_bundle["fallback_path"] == "use_cache_fallback"
    assert surface.capability_summary["has_cache_fallback"] is True
    assert surface.capability_summary["auth_requirements"]["websocket_market"] == "not_bound"
    assert surface.connector_contracts["market_feed"]["transport"] == "fixture_cache"
    assert manifest.metadata["data_surface"]["summary"].startswith("Read-only fixture-backed feed surface")
    assert manifest.metadata["data_surface"]["supports_discovery"] is True
    assert manifest.metadata["data_surface"]["supports_orderbook"] is True
    assert manifest.metadata["data_surface"]["supports_trades"] is True
    assert manifest.metadata["data_surface"]["supports_execution"] is True
    assert manifest.metadata["data_surface"]["supports_paper_mode"] is True
    assert manifest.data_surface_runbook["runbook_id"] == "polymarket_read_only_feed_surface"
    assert manifest.data_surface_runbook["signals"]["ingestion_mode"] == "read_only_fixture"
    if manifest.data_surface_runbook["signals"]["feed_mode"] == "live_bound":
        assert manifest.data_surface_runbook["signals"]["streaming_mode"] == "live_websocket_rtds"
        assert manifest.data_surface_runbook["signals"]["rtds_status"] == "ready"
        assert manifest.data_surface_runbook["signals"]["supports_websocket"] is True
    else:
        assert manifest.data_surface_runbook["signals"]["feed_mode"] == "read_only"
        assert manifest.data_surface_runbook["signals"]["streaming_mode"] == "read_only_snapshot_polling"
        assert manifest.data_surface_runbook["signals"]["rtds_status"] == "unavailable"
        assert manifest.data_surface_runbook["signals"]["supports_websocket"] is False
    assert manifest.data_surface_runbook["signals"]["market_feed_connector"] == "fixture_cache"
    assert manifest.data_surface_runbook["signals"]["user_feed_connector"] == "fixture_cache"
    assert manifest.data_surface_runbook["signals"]["market_feed_cache_backed"] is True
    assert manifest.data_surface_runbook["signals"]["user_feed_cache_backed"] is True
    assert manifest.data_surface_runbook["signals"]["route_refs"]["market_feed"] == "fixtures/markets.json"
    assert manifest.data_surface_runbook["signals"]["availability_probes"]["market_feed"]["status"] == "fixture_available"
    assert manifest.data_surface_runbook["signals"]["cache_fallbacks"]["user_feed"]["status"] == "ready"
    assert manifest.data_surface_runbook["signals"]["feed_surface_degraded"] is True
    assert "read_only_ingestion" in manifest.data_surface_runbook["signals"]["feed_surface_degraded_reasons"]
    assert health.feed_surface_status == "read_only_fixture"
    assert health.feed_surface_summary.startswith("Read-only fixture-backed feed surface")
    assert health.feed_surface is not None
    assert health.feed_surface.supports_discovery is True
    assert health.feed_surface.supports_orderbook is True
    assert health.feed_surface.supports_trades is True
    assert health.feed_surface.supports_execution is True
    assert health.feed_surface.supports_paper_mode is True
    if health.feed_surface is not None and health.feed_surface.websocket_status == "ready":
        assert health.websocket_status == "ready"
        assert health.rtds_status == "ready"
        assert health.market_websocket_status == "ready"
        assert health.user_feed_websocket_status == "ready"
    else:
        assert health.websocket_status == "unavailable"
        assert health.rtds_status == "unavailable"
        assert health.market_websocket_status == "unavailable"
        assert health.user_feed_websocket_status == "unavailable"
    assert health.market_feed_status == "fixture_available"
    assert health.user_feed_status == "fixture_available"
    assert health.market_feed_replayable is True
    assert health.user_feed_replayable is True
    assert health.rtds_replayable is False
    assert health.route_refs["market_feed"] == "fixtures/markets.json"
    assert health.availability_probes["market_feed"]["connector"] == "fixture_cache"
    assert health.availability_probes["market_feed"]["operational_status"] == "ready"
    assert health.cache_fallbacks["market_feed"]["status"] == "ready"
    assert health.subscription_preview["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert health.probe_bundle["bundle_status"] == "ready"
    assert health.capability_summary["market_feed_path"] == "use_cache_backed_snapshot"
    assert health.connector_contracts["market_feed"]["mode"] == "read_only"
    assert health.connector_contracts["market_feed"]["endpoint_contract"]["route_ref"] == "fixtures/markets.json"
    assert health.probe_bundle["highest_severity"] == "info"
    assert health.feed_surface.degraded is True
    assert "read_only_ingestion" in health.feed_surface.degraded_reasons
    assert health.feed_surface_degraded is True
    assert "read_only_ingestion" in health.feed_surface_degraded_reasons


def test_stream_health_detects_stale_and_desync_and_maintenance(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=paths)
    session = streamer.open(market_id="pm_stream_test")
    session.poll_once()

    events_path = paths.root / "streams" / session.stream_id / "events.jsonl"
    event_payload = json.loads(events_path.read_text(encoding="utf-8").splitlines()[-1])
    event_payload["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    events_path.write_text(json.dumps(event_payload) + "\n", encoding="utf-8")

    manifest = streamer.store.load_manifest(session.stream_id)
    manifest.metadata["maintenance_mode"] = True
    manifest.latest_sequence += 1
    streamer.store.save_manifest(manifest)

    health = session.health(stale_after_seconds=60.0)

    assert health.healthy is False
    assert health.maintenance_mode is True
    assert health.desync_detected is True
    assert health.freshness_status in {"maintenance", "stale"}
    assert "maintenance_mode" in health.issues
    assert "stream_stale" in health.issues or "sequence_mismatch" in health.issues
    assert health.feed_surface is not None
    assert health.incident_runbook["runbook_id"] in {"stream_maintenance", "stream_stale", "stream_desync"}


def test_stream_health_recovers_after_maintenance_and_fresh_poll(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    client = MutableSnapshotClient()
    streamer = MarketStreamer(client=client, paths=paths)
    session = streamer.open(market_id="pm_stream_test")

    session.poll_once()
    manifest = streamer.store.load_manifest(session.stream_id)
    manifest.metadata["maintenance_mode"] = True
    streamer.store.save_manifest(manifest)

    maintenance_health = session.health(stale_after_seconds=60.0)
    assert maintenance_health.healthy is False
    assert maintenance_health.maintenance_mode is True
    assert maintenance_health.incident_runbook["runbook_id"] == "stream_maintenance"

    manifest = streamer.store.load_manifest(session.stream_id)
    manifest.metadata["maintenance_mode"] = False
    streamer.store.save_manifest(manifest)

    client.price_yes = 0.61
    client.spread_bps = 88.0
    session.poll_once()

    recovered_health = session.health(stale_after_seconds=60.0)
    assert recovered_health.healthy is True
    assert recovered_health.maintenance_mode is False
    assert recovered_health.desync_detected is False
    assert recovered_health.incident_runbook["runbook_id"] == "stream_health_ok"
    assert recovered_health.feed_surface_status == "read_only"
    assert recovered_health.message == "healthy"


def test_stream_collection_uses_cache_fanout_and_priority(tmp_path: Path) -> None:
    client = MultiMarketSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))

    request = StreamCollectionRequest(
        market_ids=["pm_low", "pm_high"],
        fanout=1,
        retries=1,
        timeout_seconds=1.0,
        cache_ttl_seconds=60.0,
        prefetch=False,
        backpressure_limit=1,
        priority_strategy=StreamCollectionPriority.liquidity,
        poll_count=1,
    )

    first_report = streamer.collect(request)
    second_report = streamer.collect(request.model_copy(update={"prefetch": True}))

    assert first_report.total_count == 2
    assert first_report.batch_count == 2
    assert first_report.backpressure_applied is True
    assert first_report.cache_hit_count == 0
    assert first_report.prioritized_refs[0] == "market_id:pm_high"
    assert first_report.items[0].market_id == "pm_high"

    assert second_report.cache_hit_count == 2
    assert second_report.cache_hit_rate == 1.0
    assert all(item.cache_hit for item in second_report.items)


def test_stream_collection_reports_duplicate_market_coverage_metrics(tmp_path: Path) -> None:
    client = MultiMarketSnapshotClient()
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))

    request = StreamCollectionRequest(
        market_ids=["pm_high", "pm_high"],
        slugs=["retry-market"],
        fanout=2,
        retries=0,
        timeout_seconds=1.0,
        cache_ttl_seconds=60.0,
        prefetch=False,
        poll_count=1,
    )

    report = streamer.collect(request)

    assert report.metrics is not None
    assert report.metrics.requested_target_count == 3
    assert report.metrics.unique_target_count == 2
    assert report.metrics.duplicate_target_count == 1
    assert report.metrics.duplicate_target_rate == pytest.approx(1 / 3, rel=1e-6)
    assert report.metrics.requested_market_count == 3
    assert report.metrics.unique_market_count == 2
    assert report.metrics.duplicate_market_count == 1
    assert report.metrics.duplicate_market_rate == pytest.approx(1 / 3, rel=1e-6)
    assert report.metrics.coverage_gap_count == 1
    assert report.metrics.coverage_gap_rate == pytest.approx(1 / 3, rel=1e-6)
    assert report.metrics.resolved_market_rate == 1.0
    assert report.metrics.market_coverage_rate == pytest.approx(2 / 3, rel=1e-6)
    assert report.metrics.market_coverage_by_venue["polymarket"]["requested_market_count"] == 3
    assert report.metrics.market_coverage_by_venue["polymarket"]["unique_market_count"] == 2
    assert report.metrics.market_coverage_by_venue["polymarket"]["duplicate_market_count"] == 1


def test_stream_collection_retries_on_transient_failure(tmp_path: Path) -> None:
    client = MultiMarketSnapshotClient(fail_once_for={"pm_retry"})
    streamer = MarketStreamer(client=client, paths=PredictionMarketPaths(root=tmp_path / "prediction_markets"))

    report = streamer.collect(
        StreamCollectionRequest(
            market_ids=["pm_retry"],
            fanout=2,
            retries=1,
            timeout_seconds=1.0,
            cache_ttl_seconds=60.0,
            prefetch=False,
            priority_strategy=StreamCollectionPriority.request_order,
            poll_count=1,
        )
    )

    assert report.retry_count == 1
    assert report.error_count == 0
    assert report.items[0].attempts == 2
    assert report.items[0].status == "ok"


def test_venue_health_monitor_reports_recovery_after_incident() -> None:
    incident = MarketStreamHealth(
        stream_id="stream_incident",
        market_id="pm_health",
        venue=VenueName.polymarket,
        healthy=False,
        stream_status="maintenance",
        freshness_status="maintenance",
        message="maintenance mode",
        issues=["maintenance_mode"],
        issue_count=1,
        maintenance_mode=True,
        desync_detected=False,
        supports_websocket=True,
        supports_rtds=False,
        websocket_status="degraded",
        rtds_status="unavailable",
        market_websocket_status="degraded",
        user_feed_websocket_status="unavailable",
        market_feed_status="fixture_available",
        user_feed_status="fixture_available",
        market_feed_replayable=True,
        user_feed_replayable=True,
        rtds_replayable=False,
        route_refs={"market_feed": "fixtures/markets.json", "user_feed": "fixtures/positions.json"},
        availability_probes={
            "market_feed": {"status": "fixture_available", "connector": "fixture_cache", "transport": "fixture_cache", "route_ref": "fixtures/markets.json"},
            "user_feed": {"status": "fixture_available", "connector": "fixture_cache", "transport": "fixture_cache", "route_ref": "fixtures/positions.json"},
        },
        cache_fallbacks={
            "market_feed": {"status": "ready", "connector": "fixture_cache", "route_ref": "fixtures/markets.json"},
            "user_feed": {"status": "ready", "connector": "fixture_cache", "route_ref": "fixtures/positions.json"},
        },
        feed_surface_status="read_only_fixture",
        feed_surface_summary="Read-only fixture-backed feed surface; websocket and RTDS are not implemented here.",
        health_score=0.25,
    )
    recovered = incident.model_copy(
        update={
            "stream_id": "stream_recovered",
            "healthy": True,
            "stream_status": "healthy",
            "freshness_status": "fresh",
            "message": "healthy",
            "issues": [],
            "issue_count": 0,
            "maintenance_mode": False,
            "desync_detected": False,
            "health_score": 0.98,
        }
    )

    report = monitor_venue_health([incident, recovered])

    assert report.stream_count == 2
    assert report.healthy_count == 1
    assert report.degraded_count == 1
    assert report.maintenance_count == 1
    assert report.recovery_required is False
    assert report.recovered is True
    assert report.latest_health is not None
    assert report.latest_health.stream_id == "stream_recovered"
    assert report.supports_websocket is True
    assert report.supports_rtds is False
    assert report.websocket_status == "degraded"
    assert report.rtds_status == "unavailable"
    assert report.market_websocket_status == "degraded"
    assert report.user_feed_websocket_status == "unavailable"
    assert report.market_feed_status == "fixture_available"
    assert report.user_feed_status == "fixture_available"
    assert report.market_feed_replayable is True
    assert report.user_feed_replayable is True
    assert report.rtds_replayable is False
    assert report.route_refs["market_feed"] == "fixtures/markets.json"
    assert report.availability_probes["market_feed"]["connector"] == "fixture_cache"
    assert report.availability_probes["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert report.cache_fallbacks["market_feed"]["status"] == "ready"
    assert report.subscription_preview["channels"]["market_feed"]["recommended_action"] == "use_cache_backed_snapshot"
    assert report.subscription_preview["preview_flow"]["testable"] is True
    assert report.probe_bundle["primary_path"] == "use_cache_backed_snapshot"
    assert report.probe_bundle["preview_flow"]["expected_outcome"] == "preview_only_no_live_transport"
    assert report.probe_bundle["recovered_from_partial_probes"] is True
    assert report.probe_bundle["highest_severity"] == "warning"
    assert report.capability_summary["market_feed_path"] == "use_cache_backed_snapshot"
    assert report.connector_contracts["market_feed"]["mode"] == "read_only"
    assert report.feed_surface_status == "read_only_fixture"
    assert report.feed_surface_summary.startswith("Read-only fixture-backed feed surface")
    assert report.incident_runbook["runbook_id"] == "venue_health_ok"
    assert report.avg_health_score == pytest.approx((0.25 + 0.98) / 2, rel=1e-6)
    assert report.p95_health_score == pytest.approx(0.944, rel=1e-6)
    assert report.summary.startswith("reports=2; healthy=1; degraded=1; maintenance=1")
