from __future__ import annotations

import json

import pytest

from prediction_markets.advisor import build_default_market_advisor
from prediction_markets.evidence_registry import EvidenceRegistry
from prediction_markets.models import DecisionAction, DecisionPacket, EvidencePacket, TradeSide, VenueName
from prediction_markets.compat import (
    additional_venues_catalog_sync,
    evidence_registry_audit_sync,
    analyze_market_comments_sync,
    advise_market_sync,
    assess_market_arbitrage_sync,
    assess_market_risk_sync,
    build_market_graph_sync,
    cross_venue_intelligence_sync,
    guard_market_manipulation_sync,
    ingest_twitter_watcher_sidecar_sync,
    ingest_worldmonitor_sidecar_sync,
    forecast_market_sync,
    market_data_surface_sync,
    market_health_surface_sync,
    live_execute_market_sync,
    load_research_bridge_bundle,
    load_market_packet_bundle,
    market_events_sync,
    market_positions_sync,
    multi_venue_execution_sync,
    multi_venue_paper_sync,
    open_market_stream_sync,
    monitor_market_spreads_sync,
    paper_trade_market_sync,
    reconcile_market_run_sync,
    research_market_sync,
    replay_market_run_sync,
    replay_market_postmortem_sync,
    simulate_market_slippage_sync,
    simulate_microstructure_lab_sync,
    shadow_trade_market_sync,
)
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.research import ResearchCollector
from prediction_markets.replay import MarketReplayRunner, build_replay_postmortem, execution_projection_signature


def test_assess_market_risk_sync_persists_extended_artifacts(tmp_path) -> None:
    payload = assess_market_risk_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=tmp_path / "prediction_markets",
    )

    assert payload["risk_report"].market_id == "pm_demo_election"
    assert payload["allocation"].market_id == "pm_demo_election"
    assert payload["trade_intent"].market_id == "pm_demo_election"
    assert payload["trade_intent_guard"].intent_id == payload["trade_intent"].intent_id
    assert payload["trade_intent"].metadata["trade_intent_guard_id"] == payload["trade_intent_guard"].guard_id
    assert payload["manifest"].mode == "risk"
    assert "risk_report" in payload["manifest"].artifact_paths
    assert "allocation" in payload["manifest"].artifact_paths
    assert "trade_intent" in payload["manifest"].artifact_paths
    assert "trade_intent_guard" in payload["manifest"].artifact_paths


def test_shadow_trade_market_sync_returns_shadow_execution(tmp_path) -> None:
    payload = shadow_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=tmp_path / "prediction_markets",
    )

    assert payload["shadow_execution"].market_id == "pm_demo_election"
    assert payload["trade_intent"].market_id == "pm_demo_election"
    assert payload["execution_readiness"].market_id == "pm_demo_election"
    assert payload["execution_projection"].market_id == "pm_demo_election"
    assert payload["manifest"].execution_readiness_ref == payload["execution_readiness"].readiness_id
    assert payload["manifest"].execution_projection_ref == payload["execution_projection"].projection_id
    assert payload["manifest"].capital_ref == payload["capital_ledger_before"].snapshot_id
    assert payload["manifest"].reconciliation_ref == payload["execution_projection"].reconciliation_ref
    assert payload["manifest"].health_ref == payload["execution_projection"].health_ref
    assert payload["shadow_postmortem"]["shadow_id"] == payload["shadow_execution"].shadow_id
    assert "paper_trade_postmortem" in payload["shadow_postmortem"]
    assert payload["manifest"].mode == "shadow"
    assert "shadow_execution" in payload["manifest"].artifact_paths
    assert "trade_intent" in payload["manifest"].artifact_paths
    assert "execution_readiness" in payload["manifest"].artifact_paths
    assert "execution_projection" in payload["manifest"].artifact_paths


def test_comment_graph_cross_venue_and_stream_syncs_work(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "prediction_markets"
    monkeypatch.setattr(
        "prediction_markets.streaming._feed_surface_runbook",
        lambda *args, **kwargs: {"runbook_id": "test_runbook", "summary": "patched"},
    )

    comment_payload = analyze_market_comments_sync(
        slug="demo-election-market",
        comments=["Bullish update", "Risk remains elevated"],
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    graph_payload = build_market_graph_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    cross_payload = cross_venue_intelligence_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    stream_payload = open_market_stream_sync(
        slug="demo-election-market",
        poll_count=2,
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert comment_payload["comment_intel"].comment_count == 2
    assert graph_payload["market_graph"].nodes
    assert cross_payload["cross_venue"].metadata["market_count"] >= 1
    assert stream_payload["stream_summary"].event_count == 2
    assert stream_payload["stream_health"].healthy is True


def test_market_data_and_health_surface_syncs_expose_websocket_and_rtds_contracts() -> None:
    data_payload = market_data_surface_sync(backend_mode="surrogate")
    health_payload = market_health_surface_sync(backend_mode="surrogate")

    assert data_payload["market_data_surface"]["supports_websocket"] is False
    assert data_payload["market_data_surface"]["supports_rtds"] is False
    assert data_payload["market_data_surface"]["feed_surface"]["supports_websocket"] is False
    assert data_payload["market_data_surface"]["feed_surface"]["supports_rtds"] is False
    assert data_payload["market_health_surface"]["feed_surface"]["supports_websocket"] is False
    assert data_payload["market_health_surface"]["feed_surface"]["supports_rtds"] is False
    assert health_payload["market_health_surface"]["supports_websocket"] is False
    assert health_payload["market_health_surface"]["supports_rtds"] is False


def test_multi_venue_execution_sync_builds_persisted_report(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = multi_venue_execution_sync(
        slug="demo-election-market",
        include_additional_venues=True,
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["manifest"].mode == "multi_venue_execution"
    assert payload["multi_venue_execution"].market_count >= 1
    assert payload["multi_venue_execution"].cross_venue_report.report_id == payload["cross_venue"].report_id
    assert payload["additional_venues_matrix"] is not None
    assert "multi_venue_execution" in payload["manifest"].artifact_paths
    assert "cross_venue" in payload["manifest"].artifact_paths


def test_multi_venue_paper_sync_builds_persisted_report(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = multi_venue_paper_sync(
        slug="demo-election-market",
        include_additional_venues=True,
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["manifest"].mode == "multi_venue_paper"
    assert payload["multi_venue_execution"].market_count >= 1
    assert payload["multi_venue_paper"].market_count >= 1
    assert payload["multi_venue_paper"].report_id
    assert payload["multi_venue_paper"].surface.plan_count >= 0
    assert "multi_venue_paper" in payload["manifest"].artifact_paths
    assert "multi_venue_execution" in payload["manifest"].artifact_paths


def test_research_slippage_and_manipulation_guard_syncs_work(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "prediction_markets"
    monkeypatch.setattr(
        "prediction_markets.streaming._feed_surface_runbook",
        lambda *args, **kwargs: {"runbook_id": "test_runbook", "summary": "patched"},
    )

    research_payload = research_market_sync(
        slug="demo-election-market",
        evidence_inputs=["Bullish catalyst", "Bearish risk remains"],
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    slippage_payload = simulate_market_slippage_sync(
        slug="demo-election-market",
        requested_notional=12.0,
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    guard_payload = guard_market_manipulation_sync(
        slug="demo-election-market",
        evidence_inputs=["Official source remains clear"],
        comments=["This looks fine", "Balanced take"],
        poll_count=1,
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert research_payload["research_synthesis"].finding_count == 2
    assert research_payload["manifest"].mode == "research"
    assert slippage_payload["slippage_report"].market_id == "pm_demo_election"
    assert slippage_payload["manifest"].mode == "slippage"
    assert slippage_payload["slippage_postmortem"].report_id == slippage_payload["slippage_report"].report_id
    assert guard_payload["manipulation_guard"].market_id == "pm_demo_election"
    assert guard_payload["manifest"].mode == "manipulation_guard"


def test_microstructure_sync_and_replay_surface_postmortem(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = simulate_microstructure_lab_sync(
        slug="demo-election-market",
        requested_quantity=1.5,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["microstructure_report"].market_id == "pm_demo_election"
    assert payload["microstructure_postmortem"].report_id == payload["microstructure_report"].report_id
    assert payload["manifest"].mode == "microstructure"
    assert "microstructure_report" in payload["manifest"].artifact_paths
    assert "microstructure_postmortem" in payload["manifest"].artifact_paths

    replay_payload = replay_market_run_sync(payload["run_id"], base_dir=base_dir)
    assert replay_payload["microstructure_postmortem"]["report_id"] == payload["microstructure_report"].report_id


def test_research_market_sync_exposes_bridge_and_registry_audit(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = research_market_sync(
        slug="demo-election-market",
        evidence_inputs=["Bullish catalyst from official source", "Bearish risk remains"],
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["research_bridge"] is not None
    assert payload["research_bridge"].market_id == "pm_demo_election"
    assert payload["research_bridge"].evidence_refs
    assert payload["research_bridge"].provenance_refs
    assert payload["research_bridge"].artifact_refs
    assert payload["research_pipeline"].pipeline_steps[0]["name"] == "base_rates"
    assert payload["research_pipeline"].pipeline_steps[-1]["name"] == "abstention"
    assert payload["research_abstention_policy"].status == "proceed"
    assert payload["research_abstention_metrics"]["status"] == "proceed"
    assert payload["manifest"].metadata["research_abstention_metrics"]["status"] == "proceed"

    loaded = load_research_bridge_bundle(base_dir, payload["run_id"])
    assert loaded.bundle_id == payload["research_bridge"].bundle_id
    assert loaded.content_hash == payload["research_bridge"].content_hash
    assert loaded.metadata["abstention_metrics"]["status"] == "proceed"

    audit_payload = evidence_registry_audit_sync(run_id=payload["run_id"], base_dir=base_dir)
    assert audit_payload["audit"].healthy is True
    assert audit_payload["audit"].total_entries >= 1
    assert audit_payload["run_evidence"]


def test_evidence_registry_audit_flags_tampered_sidecar_metadata(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    paths = PredictionMarketPaths(root=base_dir)
    registry = EvidenceRegistry(paths)
    collector = ResearchCollector(venue=VenueName.polymarket)
    evidence = collector.from_notes(
        market_id="pm_tamper",
        notes=["Bullish signal for registry audit"],
        run_id="run_tamper",
    )[0]
    registry.add(evidence)

    evidence_path = paths.evidence_path(evidence.evidence_id, evidence.market_id)
    packet = EvidencePacket.model_validate_json(evidence_path.read_text(encoding="utf-8"))
    packet.metadata["artifact_refs"] = ["tampered:artifact"]
    evidence_path.write_text(packet.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    audit = registry.audit()

    assert audit.healthy is False
    assert evidence.evidence_id in audit.content_hash_mismatches
    assert evidence.evidence_id in audit.artifact_ref_mismatches
    assert "content_hash_mismatches" in audit.issues
    assert "artifact_ref_mismatches" in audit.issues


def test_advise_market_sync_records_social_bridge_runbook_when_missing(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = advise_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["social_bridge"] is None
    assert payload["social_bridge_state"] == "unavailable"
    assert payload["social_bridge_runbook"]["runbook_id"] == "social_bridge_unavailable"
    assert payload["manifest"].metadata["social_bridge_state"] == "unavailable"
    assert payload["manifest"].metadata["social_bridge_runbook"]["runbook_id"] == "social_bridge_unavailable"
    assert "social_bridge_runbook" in payload["manifest"].artifact_paths


def test_advise_market_sync_surfaces_review_and_resolution_flags_publicly(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = advise_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    surface = payload["surface_enrichment"]
    packet_surface = payload["packet_bundle"]["surface_enrichment"]
    manifest_surface = payload["manifest"].metadata["surface_enrichment"]

    assert surface["next_review_at"]
    assert surface["next_review_at"].endswith(("Z", "+00:00"))
    assert surface["resolution_policy_missing"] is False
    assert surface["requires_manual_review"] is False
    assert packet_surface["next_review_at"] == surface["next_review_at"]
    assert packet_surface["resolution_policy_missing"] is False
    assert manifest_surface["next_review_at"] == surface["next_review_at"]
    assert manifest_surface["resolution_policy_missing"] is False
    assert payload["forecast"].metadata["next_review_at"] == surface["next_review_at"]
    assert payload["forecast"].metadata["resolution_policy_missing"] is False

    replay_payload = replay_market_run_sync(payload["run_id"], base_dir=base_dir)
    assert replay_payload["surface_enrichment"]["next_review_at"] == surface["next_review_at"]
    assert replay_payload["surface_enrichment"]["resolution_policy_missing"] is False
    assert replay_payload["surface_enrichment"]["requires_manual_review"] is False

    postmortem_payload = replay_market_postmortem_sync(payload["run_id"], base_dir=base_dir)
    assert postmortem_payload["surface_enrichment"]["next_review_at"] == surface["next_review_at"]
    assert postmortem_payload["surface_enrichment"]["resolution_policy_missing"] is False


def test_advise_market_sync_exposes_research_abstention_metrics_when_inputs_are_too_weak(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = advise_market_sync(
        slug="demo-election-market",
        evidence_inputs=[
            "Wait for more data",
            "Wait for more data",
            "Wait for more data",
        ],
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["research_pipeline"].pipeline_steps[0]["name"] == "base_rates"
    assert payload["research_abstention_policy"].abstain is True
    assert payload["research_abstention_metrics"]["abstain"] is True
    assert payload["research_abstention_metrics"]["applied"] is False
    assert payload["forecast"].metadata["research_signal_applied"] is False
    assert payload["forecast"].metadata["research_abstention_metrics"]["status"] == "abstain"


def test_bridge_packet_bundle_is_persisted_and_reloadable(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = assess_market_risk_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    bundle = payload["packet_bundle"]
    assert bundle["schema_version"] == "v1"
    assert bundle["packet_version"] == "1.0.0"
    assert bundle["forecast"]["packet_kind"] == "forecast"
    assert bundle["recommendation"]["packet_kind"] == "recommendation"
    assert bundle["decision"]["packet_kind"] == "decision"
    assert bundle["advisor_architecture"]["architecture_kind"] == "reference_agentic"
    assert bundle["advisor_architecture"]["stage_order"] == [
        "market_context",
        "resolution_guard",
        "research_bridge",
        "forecast_packet",
        "recommendation_packet",
        "decision_packet",
        "execution_readiness",
    ]
    assert payload["forecast"].packet_version == "1.0.0"
    assert payload["decision"].forecast_id == payload["forecast"].forecast_id
    assert payload["advisor_architecture"].architecture_id == f'{payload["run_id"]}:advisor_architecture'
    assert payload["advisor_architecture"].packet_contracts["forecast"]["contract_id"] == payload["forecast"].contract_id

    loaded = load_market_packet_bundle(base_dir, payload["run_id"])
    assert loaded["forecast"].packet_kind == "forecast"
    assert loaded["recommendation"].source_packet_refs == [payload["forecast"].forecast_id]
    assert loaded["decision"].recommendation_id == payload["recommendation"].recommendation_id

    replay_payload = replay_market_run_sync(payload["run_id"], base_dir=base_dir)
    assert replay_payload["packet_bundle"]["forecast"]["forecast_id"] == payload["forecast"].forecast_id
    assert replay_payload["packet_bundle"]["recommendation"]["recommendation_id"] == payload["recommendation"].recommendation_id
    assert replay_payload["packet_bundle"]["decision"]["decision_id"] == payload["decision"].decision_id
    assert replay_payload["packet_bundle"]["advisor_architecture"]["architecture_id"] == payload["advisor_architecture"].architecture_id
    assert replay_payload["advisor_architecture"].architecture_id == payload["advisor_architecture"].architecture_id
    assert replay_payload["packet_bundle"]["surface_enrichment"]["next_review_at"] == payload["packet_bundle"]["surface_enrichment"]["next_review_at"]


def test_advise_market_sync_exposes_social_bridge_packet(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    social_packet = DecisionPacket(
        run_id="social_run_2",
        market_id="pm_demo_election",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        confidence=0.96,
        summary="Social core thinks this is a bet",
        rationale="External committee sees upside",
        forecast_id="fcst_social_2",
        recommendation_id="mrec_social_2",
        source_packet_refs=["social_thread_2"],
        social_context_refs=["social_thread_2"],
        market_context_refs=["market_thread_2"],
        evidence_refs=["evid_social_2"],
    )

    payload = advise_market_sync(
        market_id="pm_demo_election",
        decision_packet=social_packet,
        backend_mode="surrogate",
        base_dir=base_dir,
        persist=False,
    )

    assert payload["social_bridge"]["decision_probability"] == 0.96
    assert payload["social_bridge"]["contract_id"] == "v1:decision:1.0.0:market_only"
    assert payload["social_bridge"]["packet_contract"]["contract_id"] == payload["social_bridge"]["contract_id"]
    assert payload["social_bridge"]["packet_contract"]["packet_kind"] == "decision"
    assert payload["forecast"].metadata["social_bridge"]["decision_action"] == "bet"
    assert payload["forecast"].metadata["confidence_band"]["low"] <= payload["forecast"].metadata["confidence_band"]["high"]
    assert payload["forecast"].metadata["rationale_summary"]
    assert payload["forecast"].metadata["scenarios"]
    assert payload["forecast"].social_bridge_used is False
    assert payload["recommendation"].metadata["risks"]
    assert isinstance(payload["recommendation"].metadata["requires_manual_review"], bool)
    assert payload["recommendation"].social_bridge_used is False
    assert isinstance(payload["decision"].metadata["requires_manual_review"], bool)
    assert payload["decision"].social_bridge_used is False
    assert payload["decision"].action == payload["recommendation"].action
    assert payload["forecast"].probability_estimate == pytest.approx(payload["forecast"].fair_probability)
    assert payload["forecast"].confidence_band["center"] == pytest.approx(payload["forecast"].fair_probability)
    assert payload["forecast"].rationale_summary
    assert payload["forecast"].scenarios
    assert payload["forecast"].artifacts == payload["forecast"].evidence_refs
    assert payload["forecast"].mode_used == payload["forecast"].compatibility_mode.value
    assert payload["forecast"].resolution_policy_ref == payload["forecast"].resolution_policy_id
    assert payload["recommendation"].probability_estimate == pytest.approx(payload["forecast"].fair_probability)
    assert payload["recommendation"].confidence_band["center"] == pytest.approx(payload["forecast"].fair_probability)
    assert payload["recommendation"].rationale_summary
    assert payload["recommendation"].scenarios
    assert payload["recommendation"].artifacts == payload["recommendation"].artifact_refs
    assert payload["recommendation"].mode_used == payload["recommendation"].compatibility_mode.value
    assert payload["decision"].probability_estimate == pytest.approx(payload["forecast"].fair_probability)
    assert payload["decision"].confidence_band["center"] == pytest.approx(payload["forecast"].fair_probability)
    assert payload["decision"].rationale_summary
    assert payload["decision"].scenarios
    assert payload["decision"].artifacts == payload["decision"].evidence_refs
    assert payload["decision"].mode_used == payload["decision"].compatibility_mode.value
    assert payload["manifest"].metadata["social_bridge"]["decision_probability"] == 0.96
    assert payload["manifest"].metadata["surface_enrichment"]["confidence_band"]["center"] == payload["forecast"].metadata["confidence_band"]["center"]
    assert payload["advisor_architecture"].social_bridge_state == "available"
    assert payload["advisor_architecture"].packet_refs["forecast"] == payload["forecast"].forecast_id
    assert payload["advisor_architecture"].packet_contracts["decision"]["contract_id"] == payload["decision"].contract_id
    assert payload["packet_bundle"]["advisor_architecture"]["social_bridge_state"] == "available"
    assert payload["manifest"].metadata["advisor_architecture"]["architecture_id"] == payload["advisor_architecture"].architecture_id


def test_forecast_market_sync_compares_baseline_and_social_core(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    social_packet = DecisionPacket(
        run_id="social_run_3",
        market_id="pm_demo_election",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        confidence=0.91,
        summary="Social core prefers the long side",
        rationale="Committee sees upside",
        forecast_id="fcst_social_3",
        recommendation_id="mrec_social_3",
        source_packet_refs=["social_thread_3"],
        social_context_refs=["social_thread_3"],
        market_context_refs=["market_thread_3"],
        evidence_refs=["evid_social_3"],
    )

    payload = forecast_market_sync(
        market_id="pm_demo_election",
        decision_packet=social_packet,
        use_social_core=True,
        backend_mode="surrogate",
        base_dir=base_dir,
        persist=False,
    )

    comparison = payload["comparison"]
    assert comparison.social_core_used is True
    assert comparison.base_forecast_id == payload["baseline_forecast"].forecast_id
    assert comparison.social_forecast_id == payload["social_forecast"].forecast_id
    assert comparison.base_probability_estimate == pytest.approx(payload["baseline_forecast"].fair_probability)
    assert comparison.social_probability_estimate == pytest.approx(payload["social_forecast"].fair_probability)
    assert comparison.probability_delta == pytest.approx(
        payload["social_forecast"].fair_probability - payload["baseline_forecast"].fair_probability
    )
    assert comparison.social_bridge_probability == pytest.approx(0.91)
    assert payload["baseline_forecast"].social_bridge_used is False
    assert payload["social_forecast"].social_bridge_used is True
    assert payload["social_forecast"].social_bridge_probability == pytest.approx(0.91)
    assert payload["social_forecast"].social_bridge_mode == "decision"
    assert payload["social_forecast"].fair_probability != pytest.approx(payload["baseline_forecast"].fair_probability)


def test_reconcile_market_run_sync_uses_persisted_shadow_artifacts(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    shadow_payload = shadow_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    payload = reconcile_market_run_sync(
        shadow_payload["run_id"],
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert payload["reconciliation"].run_id == shadow_payload["run_id"]
    assert payload["reconciliation"].market_id == "pm_demo_election"
    assert payload["manifest"].artifact_paths["reconciliation"].endswith("reconciliation.json")


def test_live_execute_market_sync_human_approval_gate_is_exposed(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"

    payload = live_execute_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
        persist=True,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        require_human_approval_before_live=True,
    )

    runtime_guard = payload["live_execution"].runtime_guard
    assert payload["live_execution"].metadata["human_approval_required_before_live"] is True
    assert runtime_guard["incident_runbook"]["runbook_id"] in {
        "human_approval_required_before_live",
        "manipulation_suspicion",
    }
    assert payload["live_execution"].metadata["incident_runbook"]["runbook_id"] in {
        "human_approval_required_before_live",
        "manipulation_suspicion",
    }
    assert payload["order_trace_audit"]["live_execution_status"] == payload["live_execution"].status.value
    assert payload["order_trace_audit"]["transport_mode"] == "dry_run"
    assert payload["market_execution"].metadata["order_trace_audit"] == payload["order_trace_audit"]
    assert payload["live_execution"].metadata["order_trace_audit"] == payload["order_trace_audit"]
    assert payload["manifest"].metadata["order_trace_audit"] == payload["order_trace_audit"]
    assert payload["manifest"].artifact_paths["live_execution"].endswith("live_execution.json")


def test_live_spread_arbitrage_sidecars_and_venues_syncs_work(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    worldmonitor_path = tmp_path / "worldmonitor.ndjson"
    worldmonitor_path.write_text(
        '{"event_id":"wm-1","title":"Storm intensifies","summary":"Weather risk rising","source_url":"https://example.com/storm"}\n',
        encoding="utf-8",
    )
    twitter_path = tmp_path / "twitter.json"
    twitter_path.write_text(
        '{"tweets":[{"tweet_id":"t-1","text":"Bullish support is building","author":"alice","url":"https://x.com/alice/status/t-1"}]}',
        encoding="utf-8",
    )

    live_payload = live_execute_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
        dry_run=True,
        allow_live_execution=False,
        authorized=True,
        compliance_approved=True,
        principal="tester",
        scopes=["prediction_markets:execute"],
    )
    spread_payload = monitor_market_spreads_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    arbitrage_payload = assess_market_arbitrage_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    world_payload = ingest_worldmonitor_sidecar_sync(
        str(worldmonitor_path),
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    twitter_payload = ingest_twitter_watcher_sidecar_sync(
        str(twitter_path),
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    venues_payload = additional_venues_catalog_sync(
        query="btc",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert live_payload["live_execution"].market_id == "pm_demo_election"
    assert live_payload["market_execution"].market_id == "pm_demo_election"
    assert live_payload["trade_intent"].market_id == "pm_demo_election"
    assert live_payload["manifest"].mode == "live_execution"
    assert "trade_intent" in live_payload["manifest"].artifact_paths
    assert "market_execution" in live_payload["manifest"].artifact_paths
    assert spread_payload["spread_monitor"].comparison_count >= 0
    assert spread_payload["manifest"].mode == "spread_monitor"
    assert arbitrage_payload["arbitrage_lab"].comparison_count >= 0
    assert arbitrage_payload["manifest"].mode == "arbitrage_lab"
    assert world_payload["worldmonitor_sidecar"].parsed_count == 1
    assert world_payload["manifest"].mode == "worldmonitor_sidecar"
    assert twitter_payload["twitter_watcher_sidecar"].parsed_count == 1
    assert twitter_payload["manifest"].mode == "twitter_watcher_sidecar"
    assert venues_payload["additional_venues_matrix"].profiles
    assert venues_payload["manifest"].mode == "additional_venues"


def test_market_events_and_positions_syncs_work(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "prediction_markets"
    positions_path = tmp_path / "positions.json"
    positions_path.write_text(
        '[{"market_id":"pm_demo_election","venue":"polymarket","side":"yes","quantity":2.5,"entry_price":0.58,"metadata":{"source":"fixture"}}]',
        encoding="utf-8",
    )
    monkeypatch.setenv("POLYMARKET_POSITIONS_PATH", str(positions_path))

    events_payload = market_events_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    positions_payload = market_positions_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    assert events_payload["market_events"]
    assert events_payload["manifest"].mode == "events"
    assert "market_events" in events_payload["manifest"].artifact_paths
    assert positions_payload["market_positions"]
    assert positions_payload["market_positions"][0].market_id == "pm_demo_election"
    assert positions_payload["manifest"].mode == "positions"
    assert "market_positions" in positions_payload["manifest"].artifact_paths


def test_paper_trade_sync_includes_execution_projection(tmp_path) -> None:
    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=tmp_path / "prediction_markets",
    )

    assert payload["execution_readiness"].market_id == "pm_demo_election"
    assert payload["execution_projection"].market_id == "pm_demo_election"
    assert payload["trade_intent"].metadata["execution_readiness_id"] == payload["execution_readiness"].readiness_id
    assert payload["trade_intent"].metadata["execution_projection_id"] == payload["execution_projection"].projection_id
    assert payload["manifest"].execution_readiness_ref == payload["execution_readiness"].readiness_id
    assert payload["manifest"].execution_projection_ref == payload["execution_projection"].projection_id
    assert payload["manifest"].capital_ref == payload["capital_ledger_before"].snapshot_id
    assert payload["manifest"].reconciliation_ref == payload["execution_projection"].reconciliation_ref
    assert payload["manifest"].health_ref == payload["execution_projection"].health_ref
    assert "execution_readiness" in payload["manifest"].artifact_paths
    assert "execution_projection" in payload["manifest"].artifact_paths


def test_paper_trade_sync_blocks_on_unreliable_snapshot_or_resolution(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    import prediction_markets.compat as compat

    class _FakeReport:
        def __init__(self) -> None:
            self.snapshot = SimpleNamespace(status=SimpleNamespace(value="open"), staleness_ms=240_000)
            self.resolution_guard = SimpleNamespace(
                approved=False,
                manual_review_required=True,
                can_forecast=False,
                official_source=None,
            )
            self.execution_readiness = SimpleNamespace(
                can_materialize_trade_intent=False,
                manual_review_required=True,
                blocked_reasons=["resolution_guard_not_clear"],
                no_trade_reasons=["resolution_guard_not_clear"],
            )

        def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
            return {
                "run_id": "paper_guard_run",
                "market_id": "pm_demo_election",
                "snapshot": {"status": "open", "staleness_ms": 240_000},
                "resolution_guard": {
                    "approved": False,
                    "manual_review_required": True,
                    "can_forecast": False,
                    "official_source": None,
                },
                "execution_readiness": {
                    "can_materialize_trade_intent": False,
                    "manual_review_required": True,
                    "blocked_reasons": ["resolution_guard_not_clear"],
                    "no_trade_reasons": ["resolution_guard_not_clear"],
                },
            }

    monkeypatch.setattr(compat.PredictionMarketAdvisor, "advise", lambda self, **kwargs: _FakeReport())

    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=tmp_path / "prediction_markets",
    )

    assert payload["paper_trade"] is None
    assert payload["paper_trade_blocked"] is True
    assert "resolution_guard_not_approved" in payload["paper_trade_blocked_reasons"]
    assert "resolution_guard_manual_review_required" in payload["paper_trade_blocked_reasons"]
    assert "snapshot_stale:240000" in payload["paper_trade_blocked_reasons"]
    assert payload["paper_trade_guard"]["paper_trade_allowed"] is False
    assert payload["paper_trade_guard"]["paper_trade_runbook"]["runbook_id"] == "paper_trade_unreliable_inputs"


def test_replay_exposes_original_execution_projection(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "prediction_markets"
    paper_payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )
    advisor = build_default_market_advisor(backend_mode="surrogate", base_dir=base_dir)
    original_get_market = advisor.adapter.get_market

    def _get_market(market_id: str):  # noqa: ANN001
        if market_id == paper_payload["descriptor"].market_id:
            return paper_payload["descriptor"]
        return original_get_market(market_id)

    monkeypatch.setattr(advisor.adapter, "get_market", _get_market)

    replay = MarketReplayRunner(advisor=advisor).replay(paper_payload["run_id"])

    assert replay.original_execution_projection is not None
    assert replay.original_execution_projection.projection_id == paper_payload["execution_projection"].projection_id
    assert replay.original["execution_projection"]["projection_id"] == paper_payload["execution_projection"].projection_id
    assert replay.metadata["original_artifacts"]["execution_projection"]["sha256"]
    assert execution_projection_signature(replay.original_execution_projection) == execution_projection_signature(
        paper_payload["execution_projection"]
    )
    assert build_replay_postmortem(replay).same_execution_projection is True


def test_replay_market_postmortem_sync_surfaces_order_trace_and_research_bridge_context(tmp_path) -> None:
    base_dir = tmp_path / "prediction_markets"
    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=base_dir,
    )

    report_path = base_dir / "runs" / payload["run_id"] / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["order_trace_audit"] = {
        "schema_version": "v1",
        "venue_order_status": "cancelled",
        "venue_order_flow": "submitted->acknowledged->cancelled",
        "transport_mode": "dry_run",
        "place_auditable": True,
        "cancel_auditable": True,
        "venue_order_trace_kind": "local_live",
    }
    report["research_bridge"] = {
        "bundle_id": "rb_replay_context",
        "content_hash": "sha256:replay-context",
        "status": "proceed",
    }
    report["market_execution"] = {
        "capability": {
            "execution_equivalent": True,
            "execution_like": False,
            "supports_execution": True,
            "supports_paper_mode": True,
            "metadata": {
                "planning_bucket": "execution-equivalent",
                "tradeability_class": "live_execution",
                "venue_taxonomy": "execution",
            },
        },
        "execution_plan": {
            "metadata": {
                "planning_bucket": "execution-equivalent",
            }
        },
    }
    report["taxonomy"] = "cross_venue_signal"
    report["execution_filter_reason_codes"] = ["execution_like_venue", "manual_review_required"]
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    MarketReplayRunner(
        advisor=build_default_market_advisor(backend_mode="surrogate", base_dir=base_dir),
        paths=PredictionMarketPaths(root=base_dir),
    ).replay(payload["run_id"])
    replay_payload = replay_market_run_sync(payload["run_id"], base_dir=base_dir)
    postmortem_payload = replay_market_postmortem_sync(payload["run_id"], base_dir=base_dir)

    assert postmortem_payload["exists"] is True
    assert replay_payload["packet_bundle"]["forecast"]["packet_kind"] == "forecast"
    assert replay_payload["packet_bundle"]["recommendation"]["packet_kind"] == "recommendation"
    assert replay_payload["packet_bundle"]["decision"]["packet_kind"] == "decision"
    assert replay_payload["order_trace_audit"]["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert postmortem_payload["order_trace_audit"]["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert postmortem_payload["packet_bundle"]["decision"]["packet_kind"] == "decision"
    assert replay_payload["report_surface_context"]["taxonomy"] == "cross_venue_signal"
    assert replay_payload["report_surface_context"]["execution_filter_reason_codes"] == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert postmortem_payload["report_surface_context"]["taxonomy"] == "cross_venue_signal"
    assert postmortem_payload["report_surface_context"]["execution_filter_reason_codes"] == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert postmortem_payload["replay_postmortem"].metadata["surface_context"]["order_trace_audit"]["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert postmortem_payload["replay_postmortem"].metadata["surface_context"]["research_bridge"]["bundle_id"] == "rb_replay_context"
    assert postmortem_payload["replay_postmortem"].metadata["surface_context"]["taxonomy"] == "cross_venue_signal"
    assert postmortem_payload["replay_postmortem"].metadata["surface_context"]["execution_filter_reason_codes"] == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert "order_trace_audit_present" in postmortem_payload["replay_postmortem"].notes
    assert "research_bridge_present" in postmortem_payload["replay_postmortem"].notes
    assert "taxonomy:cross_venue_signal" in postmortem_payload["replay_postmortem"].notes
    assert "execution_filter_reason_codes_present" in postmortem_payload["replay_postmortem"].notes
    assert "execution_surface:execution-equivalent" in postmortem_payload["replay_postmortem"].notes


def test_replay_postmortem_sync_exposes_deterministic_summary(monkeypatch) -> None:
    fake_payload = {
        "run_id": "demo-run",
        "replay_postmortem": {"run_id": "demo-run", "recommendation": "ok", "drift_count": 0},
        "replay_report": {"run_id": "demo-run", "same_forecast": True},
        "replay_report_path": "/tmp/demo-run/replay_report.json",
    }
    monkeypatch.setattr("prediction_markets.compat.replay_market_run_sync", lambda run_id, **kwargs: fake_payload)

    payload = replay_market_postmortem_sync("demo-run")

    assert payload["exists"] is True
    assert payload["replay_postmortem"]["recommendation"] == "ok"
    assert payload["replay_report_path"].endswith("replay_report.json")
