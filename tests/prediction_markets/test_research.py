from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prediction_markets.models import MarketSnapshot, PacketCompatibilityMode, SourceKind, VenueName
from prediction_markets.twitter_watcher_sidecar import TwitterWatcherSidecarBridge, TwitterWatcherSidecarBundle
from prediction_markets.worldmonitor_sidecar import WorldMonitorSidecarBridge, WorldMonitorSidecarBundle
from prediction_markets.research_asof import (
    build_as_of_benchmark_suite,
    build_forecast_evaluation,
    summarize_gate_1_benchmark_suite,
)
from prediction_markets.research import (
    ResearchBridgeBundle,
    ResearchCollector,
    ResearchFinding,
    SidecarSignalPacket,
    assess_findings_health,
    build_research_abstention_metrics,
    build_research_pipeline_surface,
    dedupe_findings,
    normalize_findings,
    findings_to_evidence,
    synthesize_research,
)


def _reference_time() -> datetime:
    return datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)


def test_research_normalizes_findings_and_scores_sources() -> None:
    reference = _reference_time()
    findings = normalize_findings(
        [
            {
                "claim": "Support is building for the outcome",
                "stance": "Long",
                "source_kind": SourceKind.official,
                "source_url": "https://example.com/official",
                "published_at": reference - timedelta(hours=1),
                "metadata": {"theme": "Macro"},
            },
            "Bearish pressure is increasing",
            ResearchFinding(
                claim="Wait for more data",
                stance="mixed",
                source_kind=SourceKind.social,
                published_at=reference - timedelta(days=3),
                raw_text="public chatter",
            ),
        ],
        market_id="market_1",
        run_id="run_1",
        reference_time=reference,
    )

    assert len(findings) == 3
    assert findings[0].stance == "bullish"
    assert findings[1].stance == "bearish"
    assert findings[2].stance == "neutral"
    assert findings[0].theme == "macro"
    assert findings[0].metadata["market_id"] == "market_1"
    assert findings[0].metadata["run_id"] == "run_1"
    assert findings[0].freshness_score > findings[2].freshness_score
    assert findings[0].credibility_score > findings[2].credibility_score
    assert findings[1].evidence_weight > 0.0


def test_research_synthesis_and_evidence_conversion() -> None:
    reference = _reference_time()
    findings = normalize_findings(
        [
            ResearchFinding(
                claim="Yes case is strengthening",
                stance="bullish",
                source_kind=SourceKind.official,
                summary="official note",
                tags=["Macro"],
                published_at=reference - timedelta(hours=2),
                confidence=0.88,
            ),
            {
                "claim": "No case remains credible",
                "stance": "bearish",
                "source_kind": SourceKind.news,
                "summary": "news note",
                "tags": ["Macro"],
                "published_at": reference - timedelta(hours=12),
                "confidence": 0.61,
            },
            {
                "text": "Waiting on more evidence",
                "source_kind": SourceKind.social,
                "published_at": reference - timedelta(days=4),
            },
        ],
        market_id="market_2",
        run_id="run_2",
        reference_time=reference,
    )

    synthesis = synthesize_research(findings, market_id="market_2", venue=VenueName.polymarket, run_id="run_2", reference_time=reference)

    assert synthesis.finding_count == 3
    assert synthesis.evidence_count == 3
    assert synthesis.bullish_count == 1
    assert synthesis.bearish_count == 1
    assert synthesis.neutral_count == 1
    assert synthesis.dominant_stance == "bullish"
    assert synthesis.net_bias > 0.0
    assert "3 findings" in synthesis.summary
    assert "themes=macro" in synthesis.summary
    assert synthesis.top_claims[0] == "Yes case is strengthening"

    evidence = ResearchCollector(venue=VenueName.polymarket).to_evidence(
        findings,
        market_id="market_2",
        run_id="run_2",
        reference_time=reference,
    )
    assert len(evidence) == 3
    assert evidence[0].market_id == "market_2"
    assert evidence[0].venue == VenueName.polymarket
    assert evidence[0].metadata["run_id"] == "run_2"
    assert evidence[0].metadata["source"] == "research_finding"
    assert evidence[0].summary
    assert evidence[0].confidence > 0.0


def test_research_tracks_external_references_and_deltas() -> None:
    reference = _reference_time()
    snapshot = MarketSnapshot(
        market_id="market_external_refs",
        venue=VenueName.polymarket,
        title="Will the external refs align?",
        question="Will the external refs align?",
        midpoint_yes=0.52,
        yes_price=0.52,
    )
    findings = normalize_findings(
        [
            ResearchFinding(
                claim="Metaculus consensus points upward",
                stance="bullish",
                source_kind=SourceKind.market,
                source_name="Metaculus",
                source_url="https://www.metaculus.com/questions/forecast-123/",
                published_at=reference - timedelta(hours=2),
                metadata={
                    "payload": {
                        "probability_yes": 0.57,
                    },
                },
            ),
            ResearchFinding(
                claim="Manifold traders keep a positive price",
                stance="bullish",
                source_kind=SourceKind.market,
                source_name="Manifold",
                source_url="https://manifold.markets/m/sample-market",
                published_at=reference - timedelta(hours=1),
                metadata={
                    "payload": {
                        "forecast_probability_yes": 0.63,
                    },
                },
            ),
        ],
        market_id="market_external_refs",
        run_id="run_external_refs",
        reference_time=reference,
    )

    synthesis = synthesize_research(
        findings,
        market_id="market_external_refs",
        venue=VenueName.polymarket,
        run_id="run_external_refs",
        reference_time=reference,
        snapshot=snapshot,
        forecast_probability_yes=0.61,
    )

    assert synthesis.external_reference_count == 2
    assert [reference.reference_source for reference in synthesis.external_references] == [
        "metaculus",
        "manifold",
    ]
    assert synthesis.market_probability_yes_hint == 0.52
    assert synthesis.forecast_probability_yes_hint == 0.61
    assert synthesis.market_delta_bps == 800.0
    assert synthesis.forecast_delta_bps == -100.0
    assert synthesis.external_references[0].market_delta_bps == 500.0
    assert synthesis.external_references[0].forecast_delta_bps == -400.0
    assert synthesis.external_references[1].market_delta_bps == 1100.0
    assert synthesis.external_references[1].forecast_delta_bps == 200.0


def test_research_collector_from_notes_remains_compatible() -> None:
    collector = ResearchCollector(venue=VenueName.polymarket)
    evidence = collector.from_notes(
        market_id="market_3",
        notes=[
            "Bullish momentum is visible",
            "Waiting for confirmation",
            "Bearish pressure is fading",
        ],
        run_id="run_3",
    )

    assert len(evidence) == 3
    assert evidence[0].stance == "bullish"
    assert evidence[1].stance == "neutral"
    assert evidence[2].stance == "bearish"
    assert all(item.metadata["run_id"] == "run_3" for item in evidence)
    assert all(item.metadata["source"] == "research_notes" for item in evidence)


def test_research_bridge_bundle_is_versioned_and_persistable(tmp_path) -> None:
    collector = ResearchCollector(venue=VenueName.polymarket)
    bundle = collector.bridge_bundle(
        [
            "Bullish signal from social chatter",
            "Bearish caveat remains",
        ],
        market_id="market_bridge",
        run_id="run_bridge",
        social_context_refs=["tweet-1", "post-2"],
        packet_refs={"forecast": "fcst_1"},
    )

    path = bundle.persist(tmp_path / "bridge_bundle.json")
    loaded = ResearchBridgeBundle.load(path)

    assert loaded.bundle_id == bundle.bundle_id
    assert loaded.packet_version == "1.0.0"
    assert loaded.bundle_contract_id == "v1:research_bridge:1.0.0:social_bridge:signal"
    assert loaded.compatibility_mode == PacketCompatibilityMode.social_bridge
    assert loaded.market_only_compatible is True
    assert loaded.synthesis is not None
    assert loaded.synthesis.finding_count == 2
    assert loaded.signal_packets
    assert isinstance(loaded.signal_packets[0], SidecarSignalPacket)
    assert loaded.signal_packets[0].signal_only is False
    assert loaded.signal_packets[0].evidence_id
    assert loaded.signal_packets[0].provenance_refs
    assert loaded.signal_packets[0].artifact_refs
    assert loaded.signal_packets[0].content_hash
    assert loaded.provenance_refs
    assert loaded.evidence_refs
    assert loaded.social_context_refs == ["tweet-1", "post-2"]
    assert loaded.artifact_refs
    assert loaded.freshness_score > 0.0
    assert loaded.provenance_bundle is not None
    assert loaded.provenance_bundle.content_hash
    assert loaded.provenance_bundle.freshness_score > 0.0
    assert loaded.metadata["provenance_bundle_content_hash"] == loaded.provenance_bundle.content_hash
    assert loaded.metadata["provenance_bundle_freshness_score"] == loaded.provenance_bundle.freshness_score
    assert loaded.metadata["bundle_contract_id"] == loaded.bundle_contract_id
    assert loaded.content_hash
    assert loaded.metadata["content_hash"]
    assert loaded.metadata["content_hash"] != loaded.content_hash
    assert loaded.pipeline is not None
    assert loaded.abstention_policy is not None
    assert loaded.metadata["pipeline_summary"] == loaded.pipeline.pipeline_summary
    assert loaded.metadata["public_metrics"]["abstain"] is False
    assert loaded.metadata["abstention_metrics"]["status"] == "proceed"
    assert loaded.metadata["abstention_metrics"]["applied"] is False


def test_sidecar_bundles_rehydrate_research_bundle_without_execution_signals(tmp_path) -> None:
    reference = _reference_time()

    worldmonitor_bundle = WorldMonitorSidecarBridge().ingest(
        [
            {
                "claim": "Macro risk is rising",
                "source_kind": SourceKind.news.value,
                "source_url": "https://example.com/worldmonitor",
                "market_refs": ["market_sidecar"],
                "event_refs": ["event-1"],
                "topics": ["Macro"],
            }
        ],
        market_id="market_sidecar",
        run_id="run_sidecar",
        reference_time=reference,
    )
    worldmonitor_path = worldmonitor_bundle.persist(tmp_path / "worldmonitor_sidecar.json")
    worldmonitor_loaded = WorldMonitorSidecarBundle.load(worldmonitor_path)
    worldmonitor_rehydrated = worldmonitor_loaded.rehydrate_research_bundle(reference_time=reference)

    assert worldmonitor_loaded.content_hash == worldmonitor_bundle.content_hash
    assert worldmonitor_rehydrated.market_id == "market_sidecar"
    assert worldmonitor_rehydrated.metadata["rehydrated_from_sidecar_bundle"] is True
    assert worldmonitor_rehydrated.metadata["sidecar_bundle_content_hash"] == worldmonitor_bundle.content_hash
    assert worldmonitor_rehydrated.source_bundle_content_hash == worldmonitor_bundle.content_hash
    assert worldmonitor_rehydrated.source_bundle_refs
    assert worldmonitor_bundle.content_hash in worldmonitor_rehydrated.source_bundle_refs
    assert worldmonitor_rehydrated.metadata["linked_market_refs"] == ["market:market_sidecar"]
    assert worldmonitor_rehydrated.artifact_refs
    assert worldmonitor_rehydrated.provenance_refs
    assert "execution_status" not in worldmonitor_rehydrated.metadata
    assert "trade_intent" not in worldmonitor_rehydrated.metadata

    twitter_bundle = TwitterWatcherSidecarBridge().ingest(
        [
            {
                "claim": "Social consensus is turning bullish",
                "tweet_id": "tweet-1",
                "author": "curie",
                "market_refs": ["market_sidecar"],
                "event_refs": ["event-1"],
                "hashtags": ["#macro"],
            }
        ],
        market_id="market_sidecar",
        run_id="run_sidecar",
        reference_time=reference,
    )
    twitter_path = twitter_bundle.persist(tmp_path / "twitter_watcher_sidecar.json")
    twitter_loaded = TwitterWatcherSidecarBundle.load(twitter_path)
    twitter_rehydrated = twitter_loaded.rehydrate_research_bundle(reference_time=reference)

    assert twitter_loaded.content_hash == twitter_bundle.content_hash
    assert twitter_rehydrated.market_id == "market_sidecar"
    assert twitter_rehydrated.metadata["rehydrated_from_sidecar_bundle"] is True
    assert twitter_rehydrated.metadata["sidecar_bundle_content_hash"] == twitter_bundle.content_hash
    assert twitter_rehydrated.source_bundle_content_hash == twitter_bundle.content_hash
    assert twitter_rehydrated.source_bundle_refs
    assert twitter_bundle.content_hash in twitter_rehydrated.source_bundle_refs
    assert twitter_rehydrated.metadata["linked_market_refs"] == ["market:market_sidecar"]
    assert twitter_rehydrated.artifact_refs
    assert twitter_rehydrated.provenance_refs
    assert twitter_rehydrated.provenance_bundle is not None
    assert twitter_rehydrated.metadata["provenance_bundle_content_hash"] == twitter_rehydrated.provenance_bundle.content_hash
    assert "execution_status" not in twitter_rehydrated.metadata
    assert "trade_intent" not in twitter_rehydrated.metadata


def test_research_pipeline_surface_exposes_base_rates_retrieval_and_abstention() -> None:
    reference = _reference_time()
    pipeline = build_research_pipeline_surface(
        [
            {
                "claim": "Official guidance points to a higher chance of yes",
                "stance": "bullish",
                "source_kind": SourceKind.official,
                "source_url": "https://example.com/official-yes",
                "published_at": reference - timedelta(hours=1),
                "confidence": 0.88,
                "metadata": {"record_fingerprint": "dup-1"},
            },
            {
                "claim": "Official guidance points to a higher chance of yes",
                "stance": "bullish",
                "source_kind": SourceKind.official,
                "source_url": "https://example.com/official-yes",
                "published_at": reference - timedelta(hours=1),
                "confidence": 0.88,
                "metadata": {"record_fingerprint": "dup-1"},
            },
            {
                "claim": "News flow still leaves room for a no outcome",
                "stance": "bearish",
                "source_kind": SourceKind.news,
                "source_url": "https://example.com/news-no",
                "published_at": reference - timedelta(hours=6),
                "confidence": 0.67,
            },
        ],
        market_id="market_pipeline",
        run_id="run_pipeline",
        reference_time=reference,
        retrieval_policy="test_inputs",
        input_count=3,
        evidence_count=3,
        applied=True,
    )

    abstention_metrics = build_research_abstention_metrics(pipeline, applied=True)

    assert [step["name"] for step in pipeline.pipeline_steps] == ["base_rates", "retrieval", "synthesis", "abstention"]
    assert pipeline.base_rates.finding_count == 2
    assert pipeline.retrieval.input_count == 3
    assert pipeline.retrieval.deduplicated_count == 2
    assert pipeline.retrieval.duplicate_count == 1
    assert pipeline.retrieval.duplicate_rate > 0.0
    assert pipeline.synthesis is not None
    assert pipeline.abstention_policy.abstain is False
    assert pipeline.public_metrics["abstain"] is False
    assert 0.0 <= pipeline.base_rates.estimated_base_rate_yes <= 1.0
    assert abstention_metrics["status"] == "proceed"
    assert abstention_metrics["applied"] is True
    assert abstention_metrics["estimated_base_rate_yes"] == pipeline.base_rates.estimated_base_rate_yes


def test_research_pipeline_surface_abstains_when_inputs_are_empty() -> None:
    pipeline = build_research_pipeline_surface(
        [],
        market_id="market_empty",
        run_id="run_empty",
        retrieval_policy="no_inputs",
        input_count=0,
        evidence_count=0,
        applied=False,
    )

    abstention_metrics = build_research_abstention_metrics(pipeline, applied=False)

    assert pipeline.pipeline_steps[0]["name"] == "base_rates"
    assert pipeline.pipeline_steps[-1]["name"] == "abstention"
    assert pipeline.abstention_policy.abstain is True
    assert pipeline.abstention_policy.status == "abstain"
    assert "no_research_findings" in pipeline.abstention_policy.reason_codes
    assert pipeline.public_metrics["abstention_score"] >= 0.5
    assert abstention_metrics["abstain"] is True
    assert abstention_metrics["applied"] is False
    assert abstention_metrics["status"] == "abstain"


def test_research_dedup_and_health_summary_are_stable() -> None:
    reference = _reference_time()
    findings, duplicate_count, duplicate_fingerprints = dedupe_findings(
        [
            {
                "claim": "Bullish support is building",
                "stance": "bullish",
                "source_kind": SourceKind.social,
                "source_url": "https://x.com/example/status/1",
                "published_at": reference,
                "metadata": {"record_fingerprint": "abc123"},
            },
            {
                "claim": "Bullish support is building",
                "stance": "bullish",
                "source_kind": SourceKind.social,
                "source_url": "https://x.com/example/status/1",
                "published_at": reference,
                "metadata": {"record_fingerprint": "abc123"},
            },
        ],
        market_id="market_4",
        run_id="run_4",
        reference_time=reference,
    )

    health = assess_findings_health(findings, duplicate_count=duplicate_count)
    evidence = findings_to_evidence(
        findings,
        market_id="market_4",
        run_id="run_4",
        reference_time=reference,
        deduplicate=True,
        duplicate_count=duplicate_count,
    )

    assert len(findings) == 1
    assert duplicate_count == 1
    assert duplicate_fingerprints
    assert health.status == "degraded"
    assert health.duplicate_count == 1
    assert health.alerts == ["duplicate_records_dropped"]
    assert evidence[0].metadata["duplicate_count"] == 1


def test_research_asof_gate_one_manifest_normalizes_plan_labels_and_exposes_promotion_context() -> None:
    cutoff = _reference_time()
    findings = normalize_findings(
        [
            ResearchFinding(
                claim="Base evidence lands before cutoff",
                stance="bullish",
                source_kind=SourceKind.official,
                published_at=cutoff - timedelta(hours=2),
            ),
            ResearchFinding(
                claim="Late signal should be excluded",
                stance="bearish",
                source_kind=SourceKind.news,
                published_at=cutoff + timedelta(hours=1),
            ),
        ],
        market_id="market_gate_one",
        run_id="run_gate_one",
        reference_time=cutoff,
    )
    evaluations = [
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_gate_one",
            forecast_probability=0.54,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=3),
            model_family="market_only_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_gate_one",
            forecast_probability=0.66,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=3),
            model_family="forecast_only_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_gate_one",
            forecast_probability=0.72,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=3),
            model_family="decision_packet_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q1",
            market_id="market_gate_one",
            forecast_probability=0.78,
            resolved_outcome=True,
            cutoff_at=cutoff - timedelta(hours=3),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
        build_forecast_evaluation(
            question_id="q2",
            market_id="market_gate_one",
            forecast_probability=0.21,
            resolved_outcome=False,
            cutoff_at=cutoff + timedelta(hours=2),
            model_family="ensemble_model",
            market_family="macro",
            horizon_bucket="30d",
        ),
    ]

    suite = build_as_of_benchmark_suite(
        findings,
        evaluations,
        market_id="market_gate_one",
        as_of=cutoff,
        venue=VenueName.polymarket,
        market_family="macro",
        horizon_bucket="30d",
        family_labels={
            "market_only_model": "market only",
            "forecast_only_model": "forecast pur",
            "decision_packet_model": "forecast + DecisionPacket",
            "ensemble_model": "ensemble",
        },
        metadata={"source": "unit-test"},
    )
    manifest = summarize_gate_1_benchmark_suite(suite)

    assert suite.contamination_free is True
    assert suite.excluded_future_finding_count == 1
    assert suite.excluded_future_evaluation_count == 1
    assert suite.calibration_snapshot is not None
    assert {summary.family_role for summary in suite.family_summaries} == {
        "market-only",
        "forecast-only",
        "DecisionPacket-assisted",
        "ensemble",
    }
    assert manifest["promotion_ready"] is True
    assert manifest["required_categories"] == [
        "market-only",
        "forecast-only",
        "DecisionPacket-assisted",
        "ensemble",
    ]
    assert manifest["present_categories"] == [
        "DecisionPacket-assisted",
        "ensemble",
        "forecast-only",
        "market-only",
    ]
    assert manifest["comparator_count"] == 4
    assert manifest["comparator_manifest"][0]["gate_1_category"] == "market-only"
    assert manifest["comparator_manifest"][0]["promotion_ready"] is True
    assert manifest["comparator_manifest"][1]["family_label"] == "forecast pur"
    assert manifest["comparator_manifest"][2]["family_label"] == "forecast + DecisionPacket"
    assert manifest["comparator_manifest"][3]["family_label"] == "ensemble"
    assert manifest["market_only_baseline_probability"] is not None
