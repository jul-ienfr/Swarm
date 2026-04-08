from __future__ import annotations

import json
from datetime import datetime, timezone

from prediction_markets.compat import paper_trade_market_sync
from prediction_markets.advisor import MarketAdvisor
from prediction_markets.models import (
    DecisionAction,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    ExecutionReadiness,
    ReplayReport,
    TradeSide,
    VenueName,
)
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.replay import MarketReplayRunner, build_replay_postmortem, execution_projection_signature, replay_difference_details


def test_replay_postmortem_is_standardized_and_stable(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise(
        "polymarket-fed-cut-q3-2026",
        evidence_notes=["Replay postmortem test."],
        run_id="run_replay_postmortem",
    )

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(run.run_id)
    postmortem = build_replay_postmortem(replay)

    assert postmortem.run_id == run.run_id
    assert postmortem.same_forecast is True
    assert postmortem.same_recommendation is True
    assert postmortem.same_decision is True
    assert postmortem.same_execution_readiness is True
    assert postmortem.drift_count == 0
    assert postmortem.recommendation == "ok"
    assert postmortem.metadata["original_artifacts"]["forecast"]["sha256"]
    assert replay.metadata["difference_summary"]["count"] == 0
    assert replay.metadata["difference_details"] == []


def test_replay_report_exposes_canonical_review_and_resolution_metadata(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise(
        "pm_demo_election",
        evidence_notes=["Canonical replay metadata test."],
        run_id="run_replay_metadata",
    )

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(run.run_id)

    original_forecast_meta = replay.metadata["original_artifacts"]["forecast"]
    replay_forecast_meta = replay.metadata["replay_artifacts"]["forecast"]

    assert original_forecast_meta["next_review_at"] == run.forecast.next_review_at.isoformat()
    assert replay_forecast_meta["next_review_at"] == run.forecast.next_review_at.isoformat()
    assert original_forecast_meta["resolution_policy_missing"] is False
    assert replay_forecast_meta["resolution_policy_missing"] is False
    assert replay.metadata["difference_summary"]["count"] == 0
    assert replay.metadata["difference_details"] == []


def test_replay_postmortem_surfaces_order_trace_bridge_and_execution_surface_context(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=paths.root,
    )

    report_path = paths.report_path(payload["run_id"])
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

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(payload["run_id"])
    postmortem = build_replay_postmortem(replay)
    surface_context = replay.metadata["original_report_context"]

    assert surface_context["order_trace_audit"]["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert surface_context["research_bridge"]["bundle_id"] == "rb_replay_context"
    assert surface_context["taxonomy"] == "cross_venue_signal"
    assert surface_context["execution_filter_reason_codes"] == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert surface_context["execution_surface"]["planning_bucket"] == "execution-equivalent"
    assert surface_context["execution_surface"]["execution_equivalent"] is True
    assert surface_context["execution_surface"]["execution_like"] is False
    assert "order_trace_audit_present" in postmortem.notes
    assert "research_bridge_present" in postmortem.notes
    assert "taxonomy:cross_venue_signal" in postmortem.notes
    assert "execution_filter_reason_codes_present" in postmortem.notes
    assert "execution_surface:execution-equivalent" in postmortem.notes
    assert "execution_surface_role:execution-equivalent" in postmortem.notes
    assert postmortem.metadata["surface_context"]["research_bridge"]["bundle_id"] == "rb_replay_context"


def test_replay_postmortem_surfaces_feed_surface_context(tmp_path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=paths.root,
    )

    report_path = paths.report_path(payload["run_id"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["feed_surface"] = {
        "supports_websocket": False,
        "supports_rtds": False,
        "websocket_status": "unavailable",
        "rtds_status": "unavailable",
        "market_feed_status": "fixture_available",
        "user_feed_status": "fixture_available",
        "feed_surface_status": "read_only_fixture",
        "feed_surface_summary": "Read-only fixture-backed feed surface; websocket and RTDS are not implemented here.",
        "feed_surface_degraded": True,
        "feed_surface_degraded_reasons": ["read_only_ingestion", "no_websocket_live_integration", "no_rtds_live_integration"],
        "market_feed_transport": "fixture_cache",
        "user_feed_transport": "fixture_cache",
        "live_streaming": False,
    }
    report["health_surface"] = {
        "healthy": True,
        "stream_status": "healthy",
        "freshness_status": "fresh",
        "message": "healthy",
        "supports_websocket": False,
        "supports_rtds": False,
        "websocket_status": "unavailable",
        "rtds_status": "unavailable",
        "feed_surface_status": "read_only_fixture",
        "feed_surface_summary": "Read-only fixture-backed feed surface; websocket and RTDS are not implemented here.",
        "feed_surface_degraded": True,
        "feed_surface_degraded_reasons": ["read_only_ingestion"],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(payload["run_id"])
    postmortem = build_replay_postmortem(replay)
    surface_context = replay.metadata["original_report_context"]

    assert surface_context["feed_surface"]["supports_websocket"] is False
    assert surface_context["feed_surface"]["supports_rtds"] is False
    assert surface_context["feed_surface"]["websocket_status"] == "unavailable"
    assert surface_context["feed_surface"]["feed_surface_status"] == "read_only_fixture"
    assert surface_context["feed_surface"]["feed_surface_summary"].startswith("Read-only fixture-backed feed surface")
    assert surface_context["feed_surface"]["feed_surface_degraded"] is True
    assert surface_context["health_surface"]["stream_status"] == "healthy"
    assert surface_context["health_surface"]["feed_surface_status"] == "read_only_fixture"
    assert "feed_surface_present" in postmortem.notes
    assert "feed_surface_supports_websocket" not in postmortem.notes
    assert "feed_surface_supports_rtds" not in postmortem.notes
    assert postmortem.metadata["surface_context"]["feed_surface"]["market_feed_status"] == "fixture_available"
    assert postmortem.metadata["surface_context"]["health_surface"]["freshness_status"] == "fresh"


def test_execution_projection_signature_ignores_bookkeeping_drift(tmp_path) -> None:
    payload = paper_trade_market_sync(
        slug="demo-election-market",
        backend_mode="surrogate",
        base_dir=tmp_path / "prediction_markets",
    )

    original = payload["execution_projection"]
    drifted = original.model_copy(
        update={
            "projection_id": "proj_drifted_0001",
            "readiness_ref": "ready_drifted_0001",
            "compliance_ref": "ecmp_drifted_0001",
            "capital_ref": "ledger_drifted_0001",
            "reconciliation_ref": "recon_drifted_0001",
            "health_ref": "polymarket:2026-04-08T00:00:00+00:00",
            "expires_at": original.expires_at.replace(microsecond=123000),
            "content_hash": "deadbeef",
            "metadata": {
                **dict(original.metadata),
                "anchor_at": "2026-04-08T00:00:00+00:00",
            },
        }
    )

    assert original.model_dump(mode="json") != drifted.model_dump(mode="json")
    assert execution_projection_signature(original) == execution_projection_signature(drifted)

    postmortem = build_replay_postmortem(
        ReplayReport(
            run_id=payload["run_id"],
            same_forecast=True,
            same_recommendation=True,
            same_decision=True,
            same_execution_readiness=True,
            original={"execution_projection": original.model_dump(mode="json")},
            replay={"execution_projection": drifted.model_dump(mode="json")},
            original_execution_projection=original,
            replay_execution_projection=drifted,
        )
    )

    assert postmortem.same_execution_projection is True
    assert postmortem.recommendation == "ok"


def test_replay_difference_details_are_human_readable() -> None:
    original_readiness = ExecutionReadiness(
        run_id="run_diff",
        market_id="market_diff",
        venue=VenueName.polymarket,
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=10.0,
        limit_price=0.6,
        risk_checks_passed=True,
        route="paper",
    )
    replay_readiness = original_readiness.model_copy(
        update={
            "decision_action": DecisionAction.wait,
            "side": None,
            "blocked_reasons": ["manual_review_required"],
            "route": "blocked",
        }
    )
    original_projection = ExecutionProjection(
        run_id="run_diff",
        venue=VenueName.polymarket,
        market_id="market_diff",
        requested_mode=ExecutionProjectionMode.paper,
        projected_mode=ExecutionProjectionOutcome.paper,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.shadow,
        highest_safe_requested_mode=ExecutionProjectionMode.shadow,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.paper,
        blocking_reasons=[],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
    )
    replay_projection = original_projection.model_copy(
        update={
            "projected_mode": ExecutionProjectionOutcome.shadow,
            "recommended_effective_mode": ExecutionProjectionOutcome.shadow,
            "summary": "requested paper -> projected shadow",
        }
    )

    details = replay_difference_details(
        original_forecast={
            "recommendation_action": "bet",
            "edge_after_fees_bps": 120.0,
            "next_review_at": "2026-04-08T12:00:00+00:00",
            "metadata": {"resolution_policy_missing": False},
        },
        replay_forecast={
            "recommendation_action": "wait",
            "edge_after_fees_bps": 85.0,
            "next_review_at": "2026-04-08T13:00:00+00:00",
            "metadata": {"resolution_policy_missing": True},
        },
        original_recommendation={"action": "bet"},
        replay_recommendation={"action": "wait"},
        original_decision={"action": "bet"},
        replay_decision={"action": "wait"},
        original_execution_readiness=original_readiness,
        replay_execution_readiness=replay_readiness,
        original_execution_projection=original_projection,
        replay_execution_projection=replay_projection,
    )

    fields = {item["field"] for item in details}
    assert fields.issuperset(
        {
            "recommendation_action",
            "recommendation.action",
            "decision.action",
            "execution_readiness",
            "edge_after_fees_bps",
            "execution_projection",
            "next_review_at",
            "resolution_policy_missing",
        }
    )
    assert any(item["kind"] == "signature" for item in details if item["field"] == "execution_readiness")
    assert any(item["reason"].startswith("execution projection") for item in details if item["field"] == "execution_projection")
