from __future__ import annotations

from datetime import datetime, timezone

from prediction_markets.advisor import MarketAdvisor, build_default_market_advisor
from prediction_markets.evidence_registry import EvidenceRegistry
from prediction_markets.models import (
    DecisionAction,
    DecisionPacket,
    EvidencePacket,
    MarketSnapshot,
    ResolutionPolicy,
    ResolutionStatus,
    SourceKind,
    VenueName,
)
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.replay import MarketReplayRunner


def test_advisor_persists_run_and_generates_packets(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise(
        "polymarket-fed-cut-q3-2026",
        evidence_notes=["Bullish on the macro setup", "Liquidity looks deep"],
        run_id="run_1",
    )

    assert run.forecast.market_id == "polymarket-fed-cut-q3-2026"
    assert run.recommendation.market_id == "polymarket-fed-cut-q3-2026"
    assert run.manifest.run_id == "run_1"
    assert run.manifest_path.endswith("manifest.json")
    assert run.snapshot_path.endswith("snapshot.json")
    assert run.forecast_path.endswith("forecast.json")
    assert run.recommendation_path.endswith("recommendation.json")
    assert run.decision_path.endswith("decision.json")
    assert run.execution_readiness_path.endswith("execution_readiness.json")
    assert run.report_path.endswith("report.json")
    assert run.manifest.evidence_refs
    assert run.execution_readiness.run_id == run.run_id
    assert run.manifest.execution_readiness_ref == run.execution_readiness.readiness_id
    assert run.forecast.recommendation_action.value in {"bet", "wait", "no_trade", "manual_review"}

    assert paths.run_manifest_path("run_1").exists()
    assert paths.snapshot_path("run_1").exists()
    assert paths.forecast_path("run_1").exists()
    assert paths.recommendation_path("run_1").exists()
    assert paths.decision_path("run_1").exists()
    assert paths.run_dir("run_1").joinpath("execution_readiness.json").exists()
    assert paths.report_path("run_1").exists()


def test_advisor_requires_manual_review_for_ambiguous_markets(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise("polymarket-ambiguous-geo-event", persist=False)

    assert run.resolution_guard.status in {ResolutionStatus.ambiguous, ResolutionStatus.manual_review}
    assert run.forecast.manual_review_required is True
    assert run.recommendation.action.value == "manual_review"
    assert run.forecast.metadata["resolution_status"] in {"ambiguous", "manual_review"}
    assert run.forecast.metadata["resolution_can_forecast"] is False
    assert run.forecast.metadata["resolution_reliable"] is False
    assert run.forecast.metadata["paper_eligible"] is False
    assert run.forecast.resolution_policy_missing is False
    assert run.forecast.next_review_at is not None
    assert run.forecast.next_review_at.tzinfo is not None
    assert run.forecast.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert run.recommendation.resolution_policy_missing is False
    assert run.decision.resolution_policy_missing is False
    assert run.metadata["next_review_at"].endswith("+00:00")


def test_advisor_surfaces_market_price_and_resolution_coherence(tmp_path, monkeypatch) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    market = advisor.adapter.get_market("polymarket-fed-cut-q3-2026")
    snapshot = MarketSnapshot(
        market_id=market.market_id,
        venue=market.venue,
        title=market.title,
        question=market.question or market.title,
        midpoint_yes=0.52,
        yes_price=0.52,
        market_implied_probability=0.52,
        spread_bps=80,
        liquidity=5_000.0,
        staleness_ms=0,
    )
    clear_policy = ResolutionPolicy(
        market_id=market.market_id,
        venue=market.venue,
        official_source="official resolution feed",
        status=ResolutionStatus.clear,
    )

    monkeypatch.setattr(advisor.adapter, "get_snapshot", lambda market_id: snapshot)
    monkeypatch.setattr(advisor.adapter, "get_resolution_policy", lambda market_id: clear_policy)

    run = advisor.advise(market.market_id, persist=False)

    metadata = run.forecast.metadata
    assert metadata["market_price_reference"] == 0.52
    assert metadata["market_price_reference_source"] == "market_implied_probability"
    assert metadata["market_price_gap_bps"] == round((run.forecast.fair_probability - 0.52) * 10_000.0, 2)
    assert metadata["market_price_gap_abs_bps"] == abs(metadata["market_price_gap_bps"])
    assert metadata["market_alignment"] in {"aligned", "actionable", "dislocated"}
    assert metadata["resolution_status"] == "clear"
    assert metadata["resolution_can_forecast"] is True
    assert metadata["resolution_reliable"] is True
    assert metadata["paper_eligible"] is True
    assert run.forecast.resolution_policy_missing is False
    assert run.recommendation.resolution_policy_missing is False
    assert run.decision.resolution_policy_missing is False
    assert run.execution_readiness.resolution_policy_missing is False
    assert run.recommendation.metadata["market_alignment"] == metadata["market_alignment"]
    assert run.recommendation.metadata["resolution_status"] == "clear"


def test_social_bridge_packet_enriches_context_but_market_module_decides(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    social_packet = DecisionPacket(
        run_id="social_run_1",
        market_id="polymarket-ambiguous-geo-event",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        confidence=0.98,
        summary="Social core is bullish",
        rationale="Committee consensus says yes",
        forecast_id="fcst_social_1",
        recommendation_id="mrec_social_1",
        source_packet_refs=["social_thread_1"],
        social_context_refs=["social_thread_1"],
        market_context_refs=["market_thread_1"],
        evidence_refs=["evid_social_1"],
    )

    run = advisor.advise(
        "polymarket-ambiguous-geo-event",
        decision_packet=social_packet,
        persist=False,
    )

    assert run.forecast.metadata["social_bridge"]["decision_probability"] == 0.98
    assert run.forecast.metadata["social_bridge"]["decision_action"] == "bet"
    assert run.recommendation.action == DecisionAction.manual_review
    assert run.decision.action == DecisionAction.manual_review
    assert run.forecast.resolution_policy_missing is False
    assert run.metadata["social_bridge"]["decision_probability"] == 0.98


def test_advisor_surfaces_external_reference_deltas(tmp_path, monkeypatch) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    market = advisor.adapter.get_market("polymarket-fed-cut-q3-2026")
    snapshot = MarketSnapshot(
        market_id=market.market_id,
        venue=market.venue,
        title=market.title,
        question=market.question or market.title,
        midpoint_yes=0.52,
        yes_price=0.52,
        market_implied_probability=0.52,
        spread_bps=200,
        observed_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )
    clear_policy = ResolutionPolicy(
        market_id=market.market_id,
        venue=market.venue,
        official_source="official resolution feed",
        status=ResolutionStatus.clear,
    )

    monkeypatch.setattr(advisor.adapter, "get_snapshot", lambda market_id: snapshot)
    monkeypatch.setattr(advisor.adapter, "get_resolution_policy", lambda market_id: clear_policy)

    run = advisor.advise(
        market.market_id,
        extra_evidence=[
            EvidencePacket(
                market_id=market.market_id,
                venue=market.venue,
                source_kind=SourceKind.market,
                claim="Metaculus consensus inches upward",
                summary="Metaculus consensus inches upward",
                source_url="https://www.metaculus.com/questions/forecast-123/",
                observed_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                metadata={
                    "source_name": "Metaculus",
                    "payload": {
                        "probability_yes": 0.57,
                    },
                },
            ),
            EvidencePacket(
                market_id=market.market_id,
                venue=market.venue,
                source_kind=SourceKind.market,
                claim="Manifold remains constructive",
                summary="Manifold remains constructive",
                source_url="https://manifold.markets/m/sample-market",
                observed_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
                metadata={
                    "source_name": "Manifold",
                    "payload": {
                        "forecast_probability_yes": 0.63,
                    },
                },
            ),
        ],
        persist=False,
    )

    metadata = run.forecast.metadata

    assert metadata["external_reference_count"] == 2
    assert metadata["external_reference_sources"] == ["metaculus", "manifold"]
    assert metadata["market_probability_yes_hint"] == 0.52
    assert metadata["forecast_probability_yes_hint"] == run.forecast.fair_probability
    assert metadata["market_delta_bps"] is not None
    assert metadata["forecast_delta_bps"] is not None
    assert metadata["external_references"]
    assert metadata["external_references"][0]["reference_source"] == "metaculus"
    assert metadata["external_references"][1]["reference_source"] == "manifold"
    assert metadata["external_references"][0]["market_delta_bps"] == 500.0
    assert metadata["external_references"][0]["forecast_delta_bps"] is not None
    assert run.recommendation.metadata["external_reference_count"] == 2
    assert run.decision.metadata["external_reference_count"] == 2


def test_advisor_falls_back_to_wait_or_no_trade_on_missing_market_data(tmp_path, monkeypatch) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")
    market = advisor.adapter.get_market("polymarket-fed-cut-q3-2026")
    snapshot = MarketSnapshot(
        market_id=market.market_id,
        venue=market.venue,
        title=market.title,
        question=market.question or market.title,
    )
    clear_policy = ResolutionPolicy(
        market_id=market.market_id,
        venue=market.venue,
        official_source="official resolution feed",
        status=ResolutionStatus.clear,
    )

    monkeypatch.setattr(advisor.adapter, "get_snapshot", lambda market_id: snapshot)
    monkeypatch.setattr(advisor.adapter, "get_resolution_policy", lambda market_id: clear_policy)
    monkeypatch.setattr(advisor.adapter, "get_evidence", lambda market_id: [])

    run = advisor.advise(market.market_id, persist=False)

    assert run.forecast.recommendation_action in {DecisionAction.wait, DecisionAction.no_trade}
    assert run.recommendation.action in {DecisionAction.wait, DecisionAction.no_trade}
    assert run.decision.action in {DecisionAction.wait, DecisionAction.no_trade}
    assert run.forecast.metadata["confidence_band"]["low"] <= run.forecast.metadata["confidence_band"]["high"]
    assert run.forecast.metadata["rationale_summary"]
    assert run.forecast.metadata["requires_manual_review"] is False
    assert run.forecast.metadata["scenarios"]
    assert run.recommendation.metadata["confidence_band"]["center"] == run.forecast.metadata["confidence_band"]["center"]
    assert run.decision.metadata["requires_manual_review"] is False
    assert run.metadata["confidence_band"]["center"] == run.forecast.metadata["confidence_band"]["center"]
    assert run.metadata["rationale_summary"]
    assert run.metadata["scenarios"]
    assert run.metadata["requires_manual_review"] is False


def test_advisor_exposes_research_abstention_surfaces_when_signal_is_too_weak(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise(
        "polymarket-fed-cut-q3-2026",
        extra_evidence=[
            EvidencePacket(
                market_id="polymarket-fed-cut-q3-2026",
                venue=VenueName.polymarket,
                source_kind=SourceKind.manual,
                claim="Wait for more data",
                summary="Wait for more data",
                stance="neutral",
                confidence=0.25,
                freshness_score=0.2,
                credibility_score=0.2,
                metadata={"record_fingerprint": "abstain-dup"},
            ),
            EvidencePacket(
                market_id="polymarket-fed-cut-q3-2026",
                venue=VenueName.polymarket,
                source_kind=SourceKind.manual,
                claim="Wait for more data",
                summary="Wait for more data",
                stance="neutral",
                confidence=0.25,
                freshness_score=0.2,
                credibility_score=0.2,
                metadata={"record_fingerprint": "abstain-dup"},
            ),
            EvidencePacket(
                market_id="polymarket-fed-cut-q3-2026",
                venue=VenueName.polymarket,
                source_kind=SourceKind.manual,
                claim="Wait for more data",
                summary="Wait for more data",
                stance="neutral",
                confidence=0.25,
                freshness_score=0.2,
                credibility_score=0.2,
                metadata={"record_fingerprint": "abstain-dup"},
            ),
        ],
        persist=False,
        run_id="run_abstain",
    )

    assert run.forecast.metadata["research_pipeline"]["pipeline_steps"][0]["name"] == "base_rates"
    assert run.forecast.metadata["research_pipeline"]["pipeline_steps"][-1]["name"] == "abstention"
    assert run.forecast.metadata["research_abstention_policy"]["abstain"] is True
    assert run.forecast.metadata["research_abstention_metrics"]["abstain"] is True
    assert run.forecast.metadata["research_abstention_metrics"]["applied"] is False
    assert run.forecast.metadata["research_signal_applied"] is False
    assert "research_abstained" in run.forecast.risks
    assert run.metadata["research_abstention_policy"]["abstain"] is True
    assert run.metadata["research_abstention_metrics"]["status"] == "abstain"


def test_replay_uses_persisted_evidence_and_matches_outputs(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = build_default_market_advisor(backend_mode="surrogate", base_dir=paths.root)
    run = advisor.advise("polymarket-fed-cut-q3-2026", evidence_notes=["Bullish note"], run_id="run_replay")
    evidence_registry = EvidenceRegistry(paths)
    before = len(evidence_registry.list_by_run("run_replay"))

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(run.run_id)
    after = len(evidence_registry.list_by_run("run_replay"))

    assert replay.same_forecast is True
    assert replay.same_recommendation is True
    assert replay.same_decision is True
    assert replay.same_execution_readiness is True
    assert replay.differences == []
    assert replay.original["forecast"]["recommendation_action"] == replay.replay["forecast"]["recommendation_action"]
    assert replay.original_execution_readiness is not None
    assert replay.replay_execution_readiness is not None
    assert replay.original["execution_readiness"]["route"] == replay.replay["execution_readiness"]["route"]
    assert before == after
    assert paths.replay_report_path(run.run_id).exists()
    assert replay.metadata["original_artifacts"]["forecast"]["sha256"]
    assert replay.metadata["original_artifacts"]["forecast"]["content_hash"]
    assert replay.metadata["original_artifacts"]["forecast"]["timestamp"]
    assert replay.metadata["original_artifacts"]["execution_readiness"]["sha256"]
