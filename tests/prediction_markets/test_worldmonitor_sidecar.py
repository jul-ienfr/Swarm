from __future__ import annotations

from pathlib import Path

from prediction_markets.models import SourceKind, VenueName
from prediction_markets.worldmonitor_sidecar import SidecarHealthStatus, SidecarPayloadKind, WorldMonitorSidecarBridge
from prediction_markets.research import ResearchBridgeBundle


def test_worldmonitor_sidecar_parses_ndjson_and_preserves_provenance(tmp_path: Path) -> None:
    ndjson_path = tmp_path / "worldmonitor.ndjson"
    ndjson_path.write_text(
        "\n".join(
            [
                '{"event_id":"wm-1","title":"Storm intensifies","summary":"Severe weather event","source_kind":"news","source_url":"https://example.com/storm","published_at":"2026-04-08T00:00:00+00:00","tags":["weather","risk"],"market_id":"world_market","question":"Will weather intensify?","confidence":0.9}',
                "this is not json",
                '{"event_id":"wm-2","content":"Energy grid pressure rising","layer":"news","url":"https://example.com/grid","metadata":{"region":"EU"},"market_id":"world_market","question":"Will grid pressure rise?","score":0.7}',
            ]
        ),
        encoding="utf-8",
    )

    bundle = WorldMonitorSidecarBridge().ingest(
        ndjson_path,
        market_id="world_market",
        venue=VenueName.polymarket,
        run_id="run-worldmonitor",
    )

    assert bundle.payload_kind is SidecarPayloadKind.ndjson
    assert bundle.record_count == 2
    assert bundle.parsed_count == 2
    assert bundle.health.status is SidecarHealthStatus.degraded
    assert bundle.health.error_count == 1
    assert bundle.health.healthy is True
    assert len(bundle.findings) == 2
    assert len(bundle.evidence) == 2
    assert len(bundle.clusters) == 2
    assert bundle.clusters[0].cluster_id
    assert bundle.linkage.linkage_id
    assert "market:world_market" in bundle.linkage.market_refs
    assert bundle.linkage.event_refs
    assert bundle.deep_artifacts["clusters"]
    assert bundle.deep_artifacts["linkage"]
    assert bundle.findings[0].source_kind is SourceKind.news
    assert bundle.findings[0].metadata["source"] == "worldmonitor"
    assert bundle.findings[0].metadata["record_id"] == "wm-1"
    assert "market:world_market" in bundle.findings[0].metadata["market_refs"]
    assert "event:wm-1" in bundle.findings[0].metadata["event_refs"]
    assert bundle.findings[0].metadata["cluster_key"]
    assert bundle.findings[0].metadata["source_path"] == str(ndjson_path)
    assert bundle.signal_packets[0].signal_id
    assert bundle.signal_packets[0].evidence_id == bundle.evidence[0].evidence_id
    assert bundle.signal_packets[0].classification == "signal-only"
    assert bundle.signal_packets[0].provenance_refs
    assert bundle.metadata["signal_packet_count"] == 2
    assert bundle.artifact_refs
    assert bundle.provenance_refs
    assert bundle.metadata["cluster_count"] == 2
    assert bundle.metadata["cluster_refs"]
    assert bundle.metadata["deep_artifact_refs"]
    assert bundle.metadata["deep_artifacts"]["clusters"]
    assert bundle.observed_at.tzinfo is not None
    assert bundle.freshness_score > 0.0
    assert bundle.content_hash
    assert bundle.metadata["content_hash"] == bundle.content_hash
    assert bundle.evidence[0].metadata["source"] == "worldmonitor"
    assert str(ndjson_path) in bundle.evidence[0].provenance_refs
    assert "record:wm-1" in bundle.evidence[0].provenance_refs
    assert str(ndjson_path) in bundle.artifact_refs
    assert bundle.evidence[0].metadata["artifact_refs"]
    assert bundle.evidence[0].summary
    assert bundle.metadata["source_type"] == "worldmonitor_sidecar"


def test_worldmonitor_sidecar_deduplicates_records_and_reports_alerts() -> None:
    source = [
        {
            "event_id": "wm-dup-1",
            "title": "Storm intensifies",
            "summary": "Severe weather event",
            "source_kind": "news",
            "source_url": "https://example.com/storm",
            "stance": "bullish",
        },
        {
            "event_id": "wm-dup-1",
            "title": "Storm intensifies",
            "summary": "Severe weather event",
            "source_kind": "news",
            "source_url": "https://example.com/storm",
            "stance": "bullish",
        },
        {
            "event_id": "wm-2",
            "content": "Energy grid pressure rising",
            "layer": "news",
            "url": "https://example.com/grid",
            "stance": "bearish",
        },
    ]

    bundle = WorldMonitorSidecarBridge().ingest(
        source,
        market_id="world_market",
        venue=VenueName.polymarket,
        run_id="run-worldmonitor",
    )

    assert bundle.record_count == 3
    assert bundle.parsed_count == 2
    assert bundle.health.status is SidecarHealthStatus.degraded
    assert bundle.health.duplicate_count == 1
    assert bundle.health.alerts == ["duplicate_records_dropped"]
    assert bundle.health.completeness_score < 1.0
    assert bundle.findings[0].metadata["record_fingerprint"]
    assert bundle.metadata["runtime"]["duplicate_count"] == 1
    assert bundle.metadata["alerts"] == ["duplicate_records_dropped"]
    assert bundle.evidence[0].metadata["duplicate_count"] == 1
    assert bundle.artifact_refs
    assert bundle.content_hash


def test_worldmonitor_sidecar_reclassifies_degraded_signals_as_signal_only() -> None:
    bundle = WorldMonitorSidecarBridge().ingest(
        [
            {"event_id": "wm-1", "title": "Storm intensifies", "summary": "Severe weather event"},
            {"event_id": "wm-2", "content": "Energy grid pressure rising"},
        ],
        market_id="world_market",
        venue=VenueName.polymarket,
        run_id="run-worldmonitor",
    )

    research_bundle = WorldMonitorSidecarBridge().to_research_bundle(
        [
            {"event_id": "wm-1", "title": "Storm intensifies", "summary": "Severe weather event"},
            {"event_id": "wm-2", "content": "Energy grid pressure rising"},
        ],
        market_id="world_market",
        venue=VenueName.polymarket,
        run_id="run-worldmonitor",
    )

    assert bundle.metadata["classification"] == "signal-only"
    assert bundle.metadata["signal_only"] is True
    assert bundle.signal_packets[0].classification == "signal-only"
    assert bundle.signal_packets[0].signal_only is True
    assert bundle.findings[0].metadata["classification"] == "signal-only"
    assert bundle.evidence[0].metadata["classification"] == "signal-only"
    assert bundle.deep_artifacts["clusters"]
    assert bundle.linkage.cluster_refs
    assert isinstance(research_bundle, ResearchBridgeBundle)
    assert research_bundle.classification == "signal-only"
    assert research_bundle.metadata["classification"] == "signal-only"
    assert research_bundle.signal_packets
    assert research_bundle.signal_packets[0].classification == "signal-only"
    assert research_bundle.metadata["clusters"]
    assert research_bundle.metadata["linkage"]
    assert research_bundle.metadata["deep_artifact_refs"]
    assert "market:world_market" in research_bundle.artifact_refs
