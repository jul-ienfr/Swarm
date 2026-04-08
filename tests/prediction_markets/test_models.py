from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.models import (
    AdvisorArchitectureStage,
    AdvisorArchitectureSurface,
    CapitalLedgerSnapshot,
    CrossVenueMatch,
    DecisionAction,
    DecisionPacket,
    EvidencePacket,
    ForecastPacket,
    ForecastComparisonSurface,
    LedgerPosition,
    MarketDescriptor,
    MarketOrderBook,
    MarketRecommendationAction,
    MarketRecommendationPacket,
    MarketSnapshot,
    MarketStatus,
    MarketUniverseConfig,
    MarketUniverseResult,
    OrderBookLevel,
    ResolutionPolicy,
    ResolutionStatus,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    RunManifest,
    SchemaVersion,
    TradeRecord,
    TradeIntent,
    TradeSide,
    VenueCapabilities,
    VenueCapabilitiesModel,
    VenueName,
    VenueType,
)
from prediction_markets.models import ExecutionReadiness, PacketCompatibilityMode
from prediction_markets.models import VenueHealthReport


def test_snapshot_derives_midpoint_and_spread() -> None:
    orderbook = MarketOrderBook(
        bids=[OrderBookLevel(price=0.45, size=10)],
        asks=[OrderBookLevel(price=0.55, size=12)],
        source="test",
        timestamp=datetime(2026, 4, 8, 0, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    snapshot = MarketSnapshot(
        market_id="pm_test",
        venue=VenueName.polymarket,
        title="Test market",
        question="Will it happen?",
        orderbook=orderbook,
        trades=[
            TradeRecord(
                price=0.49,
                size=1.0,
                side=TradeSide.buy,
                timestamp=datetime(2026, 4, 8, 0, 5, tzinfo=timezone(timedelta(hours=2))),
            ),
            TradeRecord(
                price=0.51,
                size=1.5,
                side=TradeSide.sell,
                timestamp=datetime(2026, 4, 8, 0, 10, tzinfo=timezone(timedelta(hours=2))),
            ),
        ],
        liquidity=1000,
    )

    assert snapshot.market_implied_probability == pytest.approx(0.5)
    assert snapshot.price_yes == pytest.approx(0.5)
    assert snapshot.price_no == pytest.approx(0.5)
    assert snapshot.midpoint_yes == pytest.approx(0.5)
    assert snapshot.mid_probability == pytest.approx(0.5)
    assert snapshot.best_bid_yes == pytest.approx(0.45)
    assert snapshot.best_ask_yes == pytest.approx(0.55)
    assert snapshot.best_bid_no == pytest.approx(0.45)
    assert snapshot.best_ask_no == pytest.approx(0.55)
    assert snapshot.depth_near_touch == pytest.approx(22.0)
    assert snapshot.last_trade_price == pytest.approx(0.51)
    assert snapshot.last_trade_ts.isoformat() == "2026-04-07T22:10:00+00:00"
    assert snapshot.snapshot_ts.isoformat().endswith("+00:00")
    assert snapshot.spread_bps == pytest.approx(1000.0)
    assert snapshot.staleness_ms == 0


def test_descriptor_clarity_and_aliases() -> None:
    descriptor = MarketDescriptor(
        market_id="pm_test",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution_equivalent,
        title="Test market",
        question="Will it happen?",
        venue_market_id="pm_venue_market_id",
        event_id="event_1",
        canonical_event_id="event_1",
        open_time="2026-04-08T00:00:00+02:00",
        end_date="2026-04-09T00:00:00+02:00",
        resolution_source="https://example.com",
        resolution_source_url="https://example.com/resolution",
        liquidity=1000,
        volume_24h=12345.5,
        status=MarketStatus.open,
    )

    assert descriptor.clarity_score > 0.6
    assert descriptor.active is True
    assert descriptor.closed is False
    assert descriptor.venue_market_id == "pm_venue_market_id"
    assert descriptor.event_id == "event_1"
    assert descriptor.canonical_event_id == "event_1"
    assert descriptor.open_time.isoformat() == "2026-04-07T22:00:00+00:00"
    assert descriptor.end_date.isoformat() == "2026-04-08T22:00:00+00:00"
    assert descriptor.resolution_source_url == "https://example.com/resolution"
    assert descriptor.volume_24h == pytest.approx(12345.5)
    assert VenueCapabilities is VenueCapabilitiesModel
    assert MarketRecommendationAction is DecisionAction


def test_venue_health_and_capabilities_models_normalize_inputs() -> None:
    capabilities = VenueCapabilitiesModel(
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=True,
        interviews=False,
        read_only=True,
        supports_replay=True,
        rate_limit_notes=[" back off when polling "],
        automation_constraints=[" authorization required "],
        metadata_map={"supports_user_feed": True, "supports_rtds": False},
    )
    health = VenueHealthReport(
        venue=VenueName.polymarket,
        backend_mode=" LIVE ",
        healthy=False,
        message="  degraded link  ",
        checked_at="2026-04-08T00:00:00+02:00",
        details=[("status", "degraded")],
    )

    assert capabilities.metadata_map["venue_type"] == "execution"
    assert capabilities.metadata_map["supports_discovery"] is True
    assert capabilities.metadata_map["supports_user_feed"] is True
    assert capabilities.rate_limit_notes == ["back off when polling"]
    assert capabilities.automation_constraints == ["authorization required"]
    assert health.backend_mode == "live"
    assert health.message == "degraded link"
    assert health.checked_at.isoformat() == "2026-04-07T22:00:00+00:00"
    assert health.details == {"status": "degraded"}


def test_venue_capabilities_surface_exposes_canonical_and_legacy_fields() -> None:
    capabilities = VenueCapabilitiesModel(
        venue=VenueName.polymarket,
        venue_type="execution",
        discovery=True,
        metadata=True,
        orderbook=True,
        trades=True,
        positions=True,
        execution=False,
        streaming=True,
        supports_paper_mode=True,
        metadata_map={"supports_events": True, "supports_user_feed": True},
        rate_limit_notes=[" back off when polling "],
        automation_constraints=[" authorization required "],
    )

    assert capabilities.venue_type == VenueType.execution
    assert capabilities.discovery is True
    assert capabilities.metadata is True
    assert capabilities.orderbook is True
    assert capabilities.trades is True
    assert capabilities.positions is True
    assert capabilities.execution is False
    assert capabilities.streaming is True
    assert capabilities.supports_discovery is True
    assert capabilities.supports_metadata is True
    assert capabilities.supports_orderbook is True
    assert capabilities.supports_trades is True
    assert capabilities.supports_positions is True
    assert capabilities.supports_execution is False
    assert capabilities.supports_streaming is True
    assert capabilities.supports_paper_mode is True
    assert capabilities.supports_events is True
    assert capabilities.supports_user_feed is True
    assert capabilities.rate_limit_notes == ["back off when polling"]
    assert capabilities.automation_constraints == ["authorization required"]
    assert capabilities.metadata_map["venue_type"] == "execution"
    assert capabilities.metadata_map["supports_discovery"] is True
    assert capabilities.metadata_map["discovery"] is True
    assert capabilities.metadata_map["supports_events"] is True


def test_forecast_recommendation_and_ledger_models() -> None:
    forecast = ForecastPacket(
        run_id="run_1",
        market_id="pm_test",
        venue=VenueName.polymarket,
        market_implied_probability=0.48,
        fair_probability=0.57,
        confidence_low=0.45,
        confidence_high=0.64,
        edge_bps=900.0,
        edge_after_fees_bps=700.0,
    )
    recommendation = MarketRecommendationPacket(
        run_id="run_1",
        forecast_id=forecast.forecast_id,
        market_id="pm_test",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.48,
        edge_bps=700.0,
        confidence=0.8,
    )
    decision = DecisionPacket(
        run_id="run_1",
        market_id="pm_test",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        confidence=0.8,
    )
    trade_intent = TradeIntent(
        run_id="run_1",
        venue=VenueName.polymarket,
        market_id="pm_test",
        side=TradeSide.yes,
        size_usd=25.0,
        forecast_ref=forecast.forecast_id,
        recommendation_ref=recommendation.recommendation_id,
        risk_checks_passed=True,
    )
    ledger = CapitalLedgerSnapshot(
        venue=VenueName.polymarket,
        cash=100.0,
        reserved_cash=25.0,
        positions=[LedgerPosition(market_id="pm_test", venue=VenueName.polymarket, side=TradeSide.yes, quantity=2, entry_price=0.48)],
    )

    assert forecast.recommendation_action == DecisionAction.wait
    assert forecast.next_review_at is not None
    assert forecast.next_review_at.tzinfo is not None
    assert forecast.resolution_policy_missing is True
    assert recommendation.side == TradeSide.yes
    assert recommendation.next_review_at is not None
    assert recommendation.resolution_policy_missing is True
    assert recommendation.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert decision.action == DecisionAction.bet
    assert decision.next_review_at is not None
    assert decision.resolution_policy_missing is True
    assert decision.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert trade_intent.risk_checks_passed is True
    assert ledger.equity == pytest.approx(75.0)


def test_forecast_packet_and_comparison_surface_capture_social_bridge_fields() -> None:
    forecast = ForecastPacket(
        run_id="run_social",
        market_id="pm_test",
        venue=VenueName.polymarket,
        market_implied_probability=0.44,
        fair_probability=0.52,
        confidence_low=0.4,
        confidence_high=0.64,
        edge_bps=800.0,
        edge_after_fees_bps=620.0,
        metadata={
            "social_bridge_used": True,
            "social_bridge_probability": 0.61,
            "social_bridge_delta_bps": 900.0,
            "social_bridge_mode": "decision",
        },
    )
    comparison = ForecastComparisonSurface(
        run_id="run_social",
        market_id="pm_test",
        venue=VenueName.polymarket,
        social_core_used=True,
        base_probability_estimate=0.47,
        social_probability_estimate=0.61,
        base_edge_after_fees_bps=450.0,
        social_edge_after_fees_bps=730.0,
        social_bridge_probability=0.61,
        social_bridge_delta_bps=1400.0,
        social_bridge_refs=["social_thread_1"],
    )

    assert forecast.social_bridge_used is True
    assert forecast.social_bridge_probability == pytest.approx(0.61)
    assert forecast.social_bridge_delta_bps == pytest.approx(900.0)
    assert forecast.social_bridge_mode == "decision"
    assert comparison.probability_delta == pytest.approx(0.14)
    assert comparison.edge_after_fees_delta_bps == pytest.approx(280.0)
    assert comparison.social_bridge_refs == ["social_thread_1"]


def test_execution_readiness_materializes_trade_intent_and_persists(tmp_path) -> None:
    readiness = ExecutionReadiness(
        run_id="run_ready",
        market_id="pm_ready",
        venue=VenueName.polymarket,
        decision_id="dec_1",
        forecast_id="fcst_1",
        recommendation_id="mrec_1",
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=18.0,
        limit_price=0.43,
        max_slippage_bps=120.0,
        confidence=0.82,
        edge_after_fees_bps=225.0,
        risk_checks_passed=True,
        blocked_reasons=[],
        no_trade_reasons=[],
        metadata={"live_gate_passed": False},
    )

    trade_intent = TradeIntent.from_execution_readiness(
        readiness,
        intent_id="intent_ready",
        time_in_force="gtc",
        metadata={"source": "unit-test"},
    )

    persisted = readiness.persist(tmp_path / "execution_readiness.json")
    loaded = ExecutionReadiness.load(persisted)

    assert readiness.can_materialize_trade_intent is True
    assert readiness.ready_to_execute is True
    assert readiness.ready_to_paper is True
    assert readiness.ready_to_live is False
    assert readiness.route == "paper"
    assert trade_intent.run_id == readiness.run_id
    assert trade_intent.forecast_ref == readiness.forecast_id
    assert trade_intent.recommendation_ref == readiness.recommendation_id
    assert trade_intent.metadata["execution_readiness_id"] == readiness.readiness_id
    assert loaded.readiness_id == readiness.readiness_id
    assert loaded.content_hash


def test_bridge_packets_are_versioned_and_persistable(tmp_path) -> None:
    forecast = ForecastPacket(
        run_id="run_bridge",
        market_id="pm_bridge",
        venue=VenueName.polymarket,
        question="Will bridge packets roundtrip?",
        topic="bridge_contracts",
        objective="Validate plan-aligned packet fields",
        market_implied_probability=0.41,
        fair_probability=0.53,
        confidence_low=0.38,
        confidence_high=0.61,
        edge_bps=1200.0,
        edge_after_fees_bps=1000.0,
        correlation_id="corr_bridge",
        probability_estimate=0.53,
        confidence_band={"low": 0.38, "high": 0.61, "center": 0.53},
        scenarios=["upside", "downside"],
        recommendation="bet",
        rationale_summary="Forecast favors the upside",
        artifacts=["evidence:1"],
        mode_used="advisor",
        engine_used="rule_based_v1",
        runtime_used={"backend_mode": "surrogate"},
        forecast_ts=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
        source_bundle_id="bundle_1",
        social_context_refs=["social-1"],
        market_context_refs=["pm_bridge", "snap_1"],
        resolution_policy_ref="policy:bridge",
        comparable_market_refs=["pm_bridge_compare"],
        requires_manual_review=True,
    )
    recommendation = MarketRecommendationPacket(
        run_id="run_bridge",
        forecast_id=forecast.forecast_id,
        market_id="pm_bridge",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.41,
        edge_bps=1000.0,
        confidence=0.9,
        question="Will bridge packets roundtrip?",
        topic="bridge_contracts",
        objective="Validate plan-aligned packet fields",
        correlation_id="corr_bridge",
        probability_estimate=0.53,
        confidence_band={"low": 0.38, "high": 0.61, "center": 0.53},
        scenarios=["upside", "downside"],
        risks=["snapshot_unreliable"],
        recommendation="bet",
        rationale_summary="Recommendation aligns with forecast",
        artifacts=["evidence:1", "evidence:2"],
        mode_used="advisor",
        engine_used="rule_based_v1",
        runtime_used={"backend_mode": "surrogate"},
        forecast_ts=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
        resolution_policy_ref="policy:bridge",
        comparable_market_refs=["pm_bridge_compare"],
        requires_manual_review=True,
        source_bundle_id="bundle_1",
        source_packet_refs=[forecast.forecast_id],
        social_context_refs=["social-1"],
        market_context_refs=["pm_bridge", "snap_1"],
    )
    decision = DecisionPacket(
        run_id="run_bridge",
        market_id="pm_bridge",
        venue=VenueName.polymarket,
        action=DecisionAction.bet,
        confidence=0.88,
        probability_estimate=0.53,
        question="Will bridge packets roundtrip?",
        topic="bridge_contracts",
        objective="Validate plan-aligned packet fields",
        correlation_id="corr_bridge",
        confidence_band={"low": 0.38, "high": 0.61, "center": 0.53},
        scenarios=["upside", "downside"],
        risks=["snapshot_unreliable"],
        recommendation="bet",
        rationale_summary="Decision aligns with recommendation",
        artifacts=["evidence:1", "evidence:2", "evidence:3"],
        mode_used="advisor",
        engine_used="rule_based_v1",
        runtime_used={"backend_mode": "surrogate"},
        forecast_ts=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
        resolution_policy_ref="policy:bridge",
        comparable_market_refs=["pm_bridge_compare"],
        requires_manual_review=True,
        forecast_id=forecast.forecast_id,
        recommendation_id=recommendation.recommendation_id,
        source_bundle_id="bundle_1",
        source_packet_refs=[forecast.forecast_id, recommendation.recommendation_id],
        social_context_refs=["social-1"],
        market_context_refs=["pm_bridge", "snap_1"],
    )
    trade_intent = TradeIntent(
        run_id="run_bridge",
        venue=VenueName.polymarket,
        market_id="pm_bridge",
        side=TradeSide.yes,
        size_usd=42.0,
        limit_price=0.41,
        forecast_ref=forecast.forecast_id,
        recommendation_ref=recommendation.recommendation_id,
        risk_checks_passed=True,
    )

    forecast_path = forecast.persist(tmp_path / "forecast.json")
    recommendation_path = recommendation.persist(tmp_path / "recommendation.json")
    decision_path = decision.persist(tmp_path / "decision.json")
    trade_intent_path = trade_intent.persist(tmp_path / "trade_intent.json")

    loaded_forecast = ForecastPacket.load(forecast_path)
    loaded_recommendation = MarketRecommendationPacket.load(recommendation_path)
    loaded_decision = DecisionPacket.load(decision_path)
    loaded_trade_intent = TradeIntent.load(trade_intent_path)

    assert loaded_forecast.packet_version == "1.0.0"
    assert loaded_forecast.packet_kind == "forecast"
    assert loaded_forecast.market_only_compatible is True
    assert loaded_forecast.compatibility_mode == PacketCompatibilityMode.market_only
    assert loaded_forecast.contract_id == "v1:forecast:1.0.0:market_only"
    assert loaded_forecast.question == "Will bridge packets roundtrip?"
    assert loaded_forecast.topic == "bridge_contracts"
    assert loaded_forecast.objective == "Validate plan-aligned packet fields"
    assert loaded_forecast.correlation_id == "corr_bridge"
    assert loaded_forecast.probability_estimate == pytest.approx(0.53)
    assert loaded_forecast.confidence_band == {"low": 0.38, "high": 0.61, "center": 0.53}
    assert loaded_forecast.scenarios == ["upside", "downside"]
    assert loaded_forecast.recommendation == "bet"
    assert loaded_forecast.rationale_summary == "Forecast favors the upside"
    assert loaded_forecast.artifacts == ["evidence:1"]
    assert loaded_forecast.mode_used == "advisor"
    assert loaded_forecast.engine_used == "rule_based_v1"
    assert loaded_forecast.runtime_used == {"backend_mode": "surrogate"}
    assert loaded_forecast.forecast_ts.isoformat() == "2026-04-08T09:00:00+00:00"
    assert loaded_forecast.resolution_policy_ref == "policy:bridge"
    assert loaded_forecast.comparable_market_refs == ["pm_bridge_compare"]
    assert loaded_forecast.requires_manual_review is True
    assert loaded_forecast.surface()["created_at"].endswith(("Z", "+00:00"))
    assert loaded_forecast.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert loaded_forecast.surface()["packet_kind"] == "forecast"
    assert loaded_recommendation.packet_kind == "recommendation"
    assert loaded_recommendation.contract_id == "v1:recommendation:1.0.0:market_only"
    assert loaded_recommendation.source_packet_refs == [forecast.forecast_id]
    assert loaded_recommendation.question == "Will bridge packets roundtrip?"
    assert loaded_recommendation.topic == "bridge_contracts"
    assert loaded_recommendation.objective == "Validate plan-aligned packet fields"
    assert loaded_recommendation.correlation_id == "corr_bridge"
    assert loaded_recommendation.probability_estimate == pytest.approx(0.53)
    assert loaded_recommendation.confidence_band == {"low": 0.38, "high": 0.61, "center": 0.53}
    assert loaded_recommendation.scenarios == ["upside", "downside"]
    assert loaded_recommendation.risks == ["snapshot_unreliable"]
    assert loaded_recommendation.recommendation == "bet"
    assert loaded_recommendation.rationale_summary == "Recommendation aligns with forecast"
    assert loaded_recommendation.artifacts == ["evidence:1", "evidence:2"]
    assert loaded_recommendation.mode_used == "advisor"
    assert loaded_recommendation.engine_used == "rule_based_v1"
    assert loaded_recommendation.runtime_used == {"backend_mode": "surrogate"}
    assert loaded_recommendation.forecast_ts.isoformat() == "2026-04-08T09:00:00+00:00"
    assert loaded_recommendation.resolution_policy_ref == "policy:bridge"
    assert loaded_recommendation.comparable_market_refs == ["pm_bridge_compare"]
    assert loaded_recommendation.requires_manual_review is True
    assert loaded_recommendation.surface()["created_at"].endswith(("Z", "+00:00"))
    assert loaded_recommendation.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert loaded_recommendation.surface()["packet_version"] == "1.0.0"
    assert loaded_decision.packet_kind == "decision"
    assert loaded_decision.contract_id == "v1:decision:1.0.0:market_only"
    assert loaded_decision.forecast_id == forecast.forecast_id
    assert loaded_forecast.contract_surface()["contract_id"] == loaded_forecast.contract_id
    assert loaded_recommendation.contract_surface()["contract_id"] == loaded_recommendation.contract_id
    assert loaded_decision.contract_surface()["contract_id"] == loaded_decision.contract_id
    assert loaded_decision.recommendation_id == recommendation.recommendation_id
    assert loaded_decision.source_packet_refs == [forecast.forecast_id, recommendation.recommendation_id]
    assert loaded_decision.market_only_compatible is True
    assert loaded_decision.question == "Will bridge packets roundtrip?"
    assert loaded_decision.topic == "bridge_contracts"
    assert loaded_decision.objective == "Validate plan-aligned packet fields"
    assert loaded_decision.correlation_id == "corr_bridge"
    assert loaded_decision.probability_estimate == pytest.approx(0.53)
    assert loaded_decision.confidence_band == {"low": 0.38, "high": 0.61, "center": 0.53}
    assert loaded_decision.scenarios == ["upside", "downside"]
    assert loaded_decision.risks == ["snapshot_unreliable"]
    assert loaded_decision.recommendation == "bet"
    assert loaded_decision.rationale_summary == "Decision aligns with recommendation"
    assert loaded_decision.artifacts == ["evidence:1", "evidence:2", "evidence:3"]
    assert loaded_decision.mode_used == "advisor"
    assert loaded_decision.engine_used == "rule_based_v1"
    assert loaded_decision.runtime_used == {"backend_mode": "surrogate"}
    assert loaded_decision.forecast_ts.isoformat() == "2026-04-08T09:00:00+00:00"
    assert loaded_decision.resolution_policy_ref == "policy:bridge"
    assert loaded_decision.comparable_market_refs == ["pm_bridge_compare"]
    assert loaded_decision.requires_manual_review is True
    assert loaded_decision.surface()["created_at"].endswith(("Z", "+00:00"))
    assert loaded_decision.surface()["next_review_at"].endswith(("Z", "+00:00"))
    assert loaded_decision.surface()["compatibility_mode"] == "market_only"
    assert loaded_forecast.content_hash
    assert loaded_recommendation.content_hash
    assert loaded_decision.content_hash


def test_advisor_architecture_surface_round_trips_and_derives_stage_order(tmp_path) -> None:
    architecture = AdvisorArchitectureSurface(
        run_id="run_architecture",
        venue=VenueName.polymarket,
        market_id="pm_architecture",
        backend_mode="surrogate",
        social_bridge_state="available",
        research_bridge_state="available",
        packet_contracts={
            "forecast": {"contract_id": "v1:forecast:1.0.0:market_only", "packet_kind": "forecast"},
            "recommendation": {"contract_id": "v1:recommendation:1.0.0:market_only", "packet_kind": "recommendation"},
            "decision": {"contract_id": "v1:decision:1.0.0:market_only", "packet_kind": "decision"},
        },
        packet_refs={
            "forecast": "fcst_architecture",
            "recommendation": "mrec_architecture",
            "decision": "dec_architecture",
        },
        stages=[
            AdvisorArchitectureStage(
                stage_id="run_architecture:forecast_packet",
                stage_kind="forecast_packet",
                role="forecast",
                status="ready",
                input_refs=["snapshot_architecture"],
                output_refs=["fcst_architecture"],
                contract_ids=["v1:forecast:1.0.0:market_only"],
                summary="Forecast packet emitted.",
            ),
            AdvisorArchitectureStage(
                stage_id="run_architecture:recommendation_packet",
                stage_kind="recommendation_packet",
                role="recommendation",
                status="degraded",
                input_refs=["fcst_architecture"],
                output_refs=["mrec_architecture"],
                contract_ids=["v1:recommendation:1.0.0:market_only"],
                summary="Recommendation packet emitted.",
            ),
        ],
        metadata={"market_title": "Architecture market"},
    )

    persisted = architecture.persist(tmp_path / "advisor_architecture.json")
    loaded = AdvisorArchitectureSurface.load(persisted)

    assert architecture.architecture_id == "run_architecture:advisor_architecture"
    assert architecture.stage_order == ["forecast_packet", "recommendation_packet"]
    assert loaded.architecture_id == architecture.architecture_id
    assert loaded.stage_order == architecture.stage_order
    assert loaded.packet_contracts["forecast"]["contract_id"] == "v1:forecast:1.0.0:market_only"
    assert loaded.stages[1].status == "degraded"
    assert "Reference advisor architecture" in loaded.summary


def test_run_manifest_and_execution_projection_refs_round_trip() -> None:
    manifest = RunManifest(
        venue=VenueName.polymarket,
        market_id="pm_roundtrip",
        mode="paper",
        execution_readiness_ref="ready_1",
        execution_compliance_ref="comp_1",
        execution_projection_ref="proj_1",
        capital_ref="ledger_1",
        reconciliation_ref="recon_1",
        health_ref="polymarket:2026-04-08T00:00:00+00:00",
    )
    projection = ExecutionProjection(
        run_id="run_1",
        venue=VenueName.polymarket,
        market_id="pm_roundtrip",
        requested_mode=ExecutionProjectionMode.paper,
        projected_mode=ExecutionProjectionOutcome.paper,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_authorized_mode=ExecutionProjectionOutcome.paper,
        readiness_ref="ready_1",
        compliance_ref="comp_1",
        capital_ref="ledger_1",
        reconciliation_ref="recon_1",
        health_ref="polymarket:2026-04-08T00:00:00+00:00",
        expires_at=datetime.now(timezone.utc),
    )

    loaded_manifest = RunManifest.model_validate_json(manifest.model_dump_json())
    loaded_projection = ExecutionProjection.model_validate_json(projection.model_dump_json())

    assert loaded_manifest.execution_readiness_ref == "ready_1"
    assert loaded_manifest.execution_compliance_ref == "comp_1"
    assert loaded_manifest.execution_projection_ref == "proj_1"
    assert loaded_manifest.capital_ref == "ledger_1"
    assert loaded_manifest.reconciliation_ref == "recon_1"
    assert loaded_manifest.health_ref == "polymarket:2026-04-08T00:00:00+00:00"
    assert loaded_projection.readiness_ref == "ready_1"
    assert loaded_projection.compliance_ref == "comp_1"
    assert loaded_projection.capital_ref == "ledger_1"
    assert loaded_projection.reconciliation_ref == "recon_1"
    assert loaded_projection.health_ref == "polymarket:2026-04-08T00:00:00+00:00"


def test_timestamp_aliases_and_source_refs_are_accepted() -> None:
    snapshot = MarketSnapshot.model_validate(
        {
            "market_id": "pm_snapshot_alias",
            "venue": VenueName.polymarket,
            "question": "Will aliases work?",
            "timestamp": "2026-04-08T00:00:00+00:00",
            "snapshot_ts": "2026-04-08T00:00:00+00:00",
            "orderbook": {
                "bids": [{"price": 0.4, "size": 10}],
                "asks": [{"price": 0.6, "size": 12}],
                "source": "raw_source",
            },
            "trades": [
                {"price": 0.41, "size": 1.0, "side": "buy", "timestamp": "2026-04-08T00:01:00+00:00"},
            ],
            "raw": {"source": "raw_source", "sources": ["raw_source", "feed_source"]},
            "metadata": {"source": "metadata_source"},
        }
    )
    policy = ResolutionPolicy.model_validate(
        {
            "market_id": "pm_snapshot_alias",
            "venue": VenueName.polymarket,
            "official_source": "https://example.com/resolution",
            "source_url": "https://example.com/resolution-policy",
            "timestamp": "2026-04-08T00:00:00+00:00",
            "rule_text": "Use the official source as stated.",
            "resolution_authority": "Federal Reserve",
            "next_review_at": "2026-04-08T02:00:00+02:00",
            "metadata": {"sources": ["policy_source"]},
        }
    )
    forecast = ForecastPacket.model_validate(
        {
            "run_id": "run_alias",
            "market_id": "pm_snapshot_alias",
            "venue": VenueName.polymarket,
            "market_implied_probability": 0.4,
            "fair_probability": 0.5,
            "confidence_low": 0.35,
            "confidence_high": 0.55,
            "edge_bps": 1000.0,
            "edge_after_fees_bps": 900.0,
            "timestamp": "2026-04-08T00:00:00+00:00",
        }
    )

    assert snapshot.observed_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert snapshot.snapshot_ts.isoformat() == "2026-04-08T00:00:00+00:00"
    assert snapshot.best_bid_yes == pytest.approx(0.4)
    assert snapshot.best_ask_yes == pytest.approx(0.6)
    assert snapshot.mid_probability == pytest.approx(0.5)
    assert snapshot.depth_near_touch == pytest.approx(22.0)
    assert snapshot.last_trade_price == pytest.approx(0.41)
    assert snapshot.last_trade_ts.isoformat() == "2026-04-08T00:01:00+00:00"
    assert snapshot.source_refs == ["raw_source", "feed_source", "metadata_source"]
    assert snapshot.content_hash
    assert policy.cached_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert policy.last_verified_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert policy.rule_text == "Use the official source as stated."
    assert policy.official_source_url == "https://example.com/resolution-policy"
    assert policy.resolution_authority == "Federal Reserve"
    assert policy.next_review_at is not None
    assert policy.next_review_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert policy.source_refs == [
        "https://example.com/resolution",
        "https://example.com/resolution-policy",
        "policy_source",
    ]
    assert policy.content_hash
    assert forecast.created_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert forecast.next_review_at is not None
    assert forecast.next_review_at.isoformat() == "2026-04-08T00:00:00+00:00"
    assert forecast.metadata["resolution_policy_missing"] is True
    assert forecast.resolution_policy_missing is True
    assert forecast.content_hash


def test_resolution_policy_and_forecast_packet_normalize_naive_review_times() -> None:
    policy = ResolutionPolicy(
        market_id="pm_naive_policy",
        venue=VenueName.polymarket,
        official_source="https://example.com/resolution",
        source_url="https://example.com/resolution-policy",
        rule_text="Use the official source as stated.",
        resolution_authority="Federal Reserve",
        next_review_at=datetime(2026, 4, 8, 2, 0),
    )
    forecast = ForecastPacket(
        run_id="run_naive_policy",
        market_id="pm_naive_policy",
        venue=VenueName.polymarket,
        market_implied_probability=0.4,
        fair_probability=0.5,
        confidence_low=0.35,
        confidence_high=0.55,
        edge_bps=1000.0,
        edge_after_fees_bps=900.0,
        next_review_at=datetime(2026, 4, 8, 2, 0),
        metadata={"resolution_policy_missing": True},
    )

    assert policy.next_review_at is not None
    assert policy.next_review_at.isoformat() == "2026-04-08T02:00:00+00:00"
    assert policy.content_hash
    assert forecast.next_review_at is not None
    assert forecast.next_review_at.isoformat() == "2026-04-08T02:00:00+00:00"
    assert forecast.requires_manual_review is True
    assert forecast.resolution_policy_missing is True
    assert forecast.metadata["resolution_policy_missing"] is True
    assert forecast.content_hash


def test_execution_projection_normalizes_expiry_and_is_stale_with_naive_inputs() -> None:
    projection = ExecutionProjection(
        run_id="run_projection_naive",
        venue=VenueName.polymarket,
        market_id="pm_projection_naive",
        requested_mode=ExecutionProjectionMode.paper,
        projected_mode=ExecutionProjectionOutcome.paper,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_authorized_mode=ExecutionProjectionOutcome.paper,
        expires_at=datetime(2026, 4, 8, 12, 30),
        metadata={
            "anchor_at": "2026-04-08T12:00:00",
            "stale_after_seconds": 300.0,
        },
    )

    assert projection.expires_at.tzinfo is not None
    assert projection.expires_at.isoformat() == "2026-04-08T12:30:00+00:00"
    assert projection.is_expired(datetime(2026, 4, 8, 12, 29)) is False
    assert projection.is_expired(datetime(2026, 4, 8, 12, 31)) is True
    assert projection.is_stale(datetime(2026, 4, 8, 12, 4), stale_after_seconds=300.0) is False
    assert projection.is_stale(datetime(2026, 4, 8, 12, 6), stale_after_seconds=300.0) is True
    assert projection.content_hash


def test_cross_venue_match_normalizes_question_currency_and_notes() -> None:
    match = CrossVenueMatch(
        canonical_event_id="event_1",
        left_market_id="left",
        right_market_id="right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.kalshi,
        question_left="  Will  BTC   rise? ",
        question_right="Will BTC rise?",
        question_key="  Will BTC rise? ",
        left_resolution_source=" https://example.com/resolution ",
        right_resolution_source="https://example.com/resolution",
        left_currency=" usd ",
        right_currency="USD",
        left_payout_currency="usd",
        right_payout_currency=" usd ",
        resolution_compatibility_score=0.0,
        payout_compatibility_score=0.0,
        currency_compatibility_score=0.0,
        comparable_market_refs=[" left ", "right", "left"],
        notes=[" note ", "note", ""],
        compatible_resolution=True,
    )

    assert match.question_left == "Will BTC rise?"
    assert match.question_right == "Will BTC rise?"
    assert match.question_key == "Will BTC rise?"
    assert match.left_resolution_source == "https://example.com/resolution"
    assert match.right_resolution_source == "https://example.com/resolution"
    assert match.left_currency == "usd"
    assert match.right_currency == "USD"
    assert match.left_payout_currency == "usd"
    assert match.right_payout_currency == "usd"
    assert match.resolution_compatibility_score == pytest.approx(1.0)
    assert match.comparable_market_refs == ["left", "right"]
    assert match.notes == ["note"]


def test_manifest_and_enums_validate() -> None:
    manifest = RunManifest(
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        market_id="pm_test",
        mode="advise",
        inputs={"hello": "world"},
    )
    assert manifest.schema_version == "v1"
    assert isinstance(manifest.created_at, datetime)
    assert manifest.created_at.tzinfo is not None
    assert SchemaVersion.__args__ == ("v1",)
    assert ResolutionStatus.clear.value == "clear"
    assert TradeRecord(price=0.5, size=1.0, side=TradeSide.buy).price == pytest.approx(0.5)


def test_universe_result_model_roundtrip() -> None:
    config = MarketUniverseConfig(venue=VenueName.polymarket, query="fed", limit=5)
    result = MarketUniverseResult(venue=VenueName.polymarket, config=config, markets=[], filtered_out=[])
    payload = result.model_dump(mode="json")

    assert payload["venue"] == "polymarket"
    assert payload["config"]["query"] == "fed"
    assert payload["markets"] == []
