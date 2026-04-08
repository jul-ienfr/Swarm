from __future__ import annotations

import json
from pathlib import Path

from prediction_markets.models import SourceKind, VenueName
from prediction_markets.twitter_watcher_sidecar import SidecarHealthStatus, SidecarPayloadKind, TwitterWatcherSidecarBridge
from prediction_markets.research import ResearchBridgeBundle


def test_twitter_watcher_sidecar_parses_json_payload_and_adds_metadata(tmp_path: Path) -> None:
    json_path = tmp_path / "twitter_watcher.json"
    json_path.write_text(
        json.dumps(
            {
                "tweets": [
                    {
                        "tweet_id": "t-1",
                        "text": "Bullish support keeps improving.",
                        "author": "alice",
                        "market_id": "mkt-1",
                        "event_id": "evt-1",
                        "question": "Will support keep improving?",
                        "created_at": "2026-04-08T00:00:00+00:00",
                        "hashtags": ["Polymarket", "Rates"],
                        "like_count": 42,
                        "retweet_count": 5,
                        "url": "https://x.com/alice/status/t-1",
                    },
                    {
                        "id": "t-2",
                        "body": "This looks weak and bearish.",
                        "username": "bob",
                        "market_id": "mkt-2",
                        "event_id": "evt-2",
                        "question": "Will weakness persist?",
                        "source_kind": "social",
                        "reply_count": 3,
                        "source_url": "https://x.com/bob/status/t-2",
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    bundle = TwitterWatcherSidecarBridge().ingest(
        json_path,
        market_id="twitter_market",
        venue=VenueName.polymarket,
        run_id="run-twitter",
    )

    assert bundle.payload_kind is SidecarPayloadKind.json
    assert bundle.record_count == 2
    assert bundle.parsed_count == 2
    assert bundle.health.status is SidecarHealthStatus.healthy
    assert bundle.health.error_count == 0
    assert bundle.health.healthy is True
    assert len(bundle.findings) == 2
    assert len(bundle.evidence) == 2
    assert len(bundle.clusters) == 2
    assert bundle.clusters[0].cluster_id
    assert bundle.clusters[0].finding_refs
    assert bundle.linkage.linkage_id
    assert "market:twitter_market" in bundle.linkage.market_refs
    assert "market:mkt-1" in bundle.linkage.market_refs
    assert "event:evt-1" in bundle.linkage.event_refs
    assert bundle.deep_artifacts["clusters"]
    assert bundle.deep_artifacts["linkage"]
    assert bundle.findings[0].source_kind is SourceKind.social
    assert bundle.findings[0].metadata["author"] == "alice"
    assert bundle.findings[0].metadata["tweet_id"] == "t-1"
    assert "market:twitter_market" in bundle.findings[0].metadata["market_refs"]
    assert "event:evt-1" in bundle.findings[0].metadata["event_refs"]
    assert bundle.findings[0].metadata["cluster_key"]
    assert bundle.findings[0].metadata["source_path"] == str(json_path)
    assert bundle.findings[0].tags
    assert bundle.signal_packets[0].signal_id
    assert bundle.signal_packets[0].evidence_id == bundle.evidence[0].evidence_id
    assert bundle.signal_packets[0].classification == "signal"
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
    assert bundle.evidence[0].metadata["source"] == "twitter_watcher"
    assert "tweet:t-1" in bundle.evidence[0].provenance_refs
    assert "author:alice" in bundle.evidence[0].provenance_refs
    assert bundle.evidence[0].source_url == "https://x.com/alice/status/t-1"
    assert bundle.metadata["source_type"] == "twitter_watcher_sidecar"
    assert bundle.evidence[0].metadata["artifact_refs"]
    assert bundle.evidence[0].summary


def test_twitter_watcher_sidecar_deduplicates_records_and_reports_alerts() -> None:
    bundle = TwitterWatcherSidecarBridge().ingest(
        [
            {
                "tweet_id": "t-dup-1",
                "text": "Bullish support keeps improving.",
                "author": "alice",
                "hashtags": ["Polymarket", "Rates"],
                "url": "https://x.com/alice/status/t-dup-1",
            },
            {
                "tweet_id": "t-dup-1",
                "text": "Bullish support keeps improving.",
                "author": "alice",
                "hashtags": ["Polymarket", "Rates"],
                "url": "https://x.com/alice/status/t-dup-1",
            },
            {
                "id": "t-2",
                "body": "This looks weak and bearish.",
                "username": "bob",
                "source_kind": "social",
                "source_url": "https://x.com/bob/status/t-2",
            },
        ],
        market_id="twitter_market",
        venue=VenueName.polymarket,
        run_id="run-twitter",
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


def test_twitter_watcher_sidecar_reclassifies_degraded_signals_as_signal_only() -> None:
    bundle = TwitterWatcherSidecarBridge().ingest(
        [
            "Bullish support keeps improving.",
            "Bearish pressure is fading.",
        ],
        market_id="twitter_market",
        venue=VenueName.polymarket,
        run_id="run-twitter",
    )

    research_bundle = TwitterWatcherSidecarBridge().to_research_bundle(
        [
            "Bullish support keeps improving.",
            "Bearish pressure is fading.",
        ],
        market_id="twitter_market",
        venue=VenueName.polymarket,
        run_id="run-twitter",
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
    assert "market:twitter_market" in research_bundle.artifact_refs
