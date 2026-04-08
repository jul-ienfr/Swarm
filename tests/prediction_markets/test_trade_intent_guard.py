from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_markets.models import (
    DecisionAction,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    ExecutionReadiness,
    MarketSnapshot,
    MarketStatus,
    TradeIntent,
    TradeSide,
    VenueHealthReport,
    VenueName,
    VenueType,
)
from prediction_markets.trade_intent_guard import (
    TradeIntentGuard,
    TradeIntentGuardVerdict,
    evaluate_trade_intent_guard,
)


def _snapshot(
    *,
    staleness_ms: int = 0,
    liquidity: float = 10_000.0,
    depth_near_touch: float | None = None,
    spread_bps: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm_guard",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Market pm_guard",
        question="Will the event happen?",
        status=MarketStatus.open,
        liquidity=liquidity,
        staleness_ms=staleness_ms,
        depth_near_touch=depth_near_touch,
        spread_bps=spread_bps,
        market_implied_probability=0.50,
        price_yes=0.50,
        price_no=0.50,
        midpoint_yes=0.50,
    )


def _trade_intent(
    *,
    manual_review_required: bool = False,
    risk_checks_passed: bool = True,
    no_trade_reasons: list[str] | None = None,
) -> TradeIntent:
    return TradeIntent(
        run_id="run_guard",
        venue=VenueName.polymarket,
        market_id="pm_guard",
        side=TradeSide.yes,
        size_usd=25.0,
        limit_price=0.50,
        max_slippage_bps=100.0,
        risk_checks_passed=risk_checks_passed,
        manual_review_required=manual_review_required,
        no_trade_reasons=list(no_trade_reasons or []),
        metadata={"source": "forecast"},
    )


def _projection(
    *,
    verdict: ExecutionProjectionVerdict = ExecutionProjectionVerdict.ready,
    projected_mode: ExecutionProjectionOutcome = ExecutionProjectionOutcome.live,
    manual_review_required: bool = False,
    blocking_reasons: list[str] | None = None,
    downgrade_reasons: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> ExecutionProjection:
    return ExecutionProjection(
        run_id="run_guard",
        venue=VenueName.polymarket,
        market_id="pm_guard",
        requested_mode=ExecutionProjectionMode.live,
        projected_mode=projected_mode,
        projection_verdict=verdict,
        highest_safe_mode=ExecutionProjectionMode.live,
        highest_safe_requested_mode=ExecutionProjectionMode.live,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=projected_mode,
        blocking_reasons=list(blocking_reasons or []),
        downgrade_reasons=list(downgrade_reasons or []),
        manual_review_required=manual_review_required,
        expires_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
        metadata=dict(metadata or {}),
    )


def _readiness(
    *,
    manual_review_required: bool = False,
    risk_checks_passed: bool = True,
    route: str = "paper",
    blocked_reasons: list[str] | None = None,
    no_trade_reasons: list[str] | None = None,
) -> ExecutionReadiness:
    return ExecutionReadiness(
        run_id="run_guard",
        market_id="pm_guard",
        venue=VenueName.polymarket,
        decision_action=DecisionAction.wait if route == "blocked" else DecisionAction.bet,
        side=TradeSide.yes if route != "blocked" else None,
        size_usd=25.0 if route != "blocked" else 0.0,
        limit_price=0.50 if route != "blocked" else None,
        confidence=0.90,
        edge_after_fees_bps=150.0,
        risk_checks_passed=risk_checks_passed,
        manual_review_required=manual_review_required,
        ready_to_execute=route != "blocked",
        ready_to_paper=route != "blocked",
        ready_to_live=False,
        can_materialize_trade_intent=route != "blocked" and risk_checks_passed and not manual_review_required,
        blocked_reasons=list(blocked_reasons or []),
        no_trade_reasons=list(no_trade_reasons or []),
        route=route,
        metadata={"live_gate_passed": True},
    )


def test_trade_intent_guard_allows_clean_intent_and_annotates_metadata() -> None:
    report = evaluate_trade_intent_guard(
        _trade_intent(),
        snapshot=_snapshot(),
        edge_after_fees_bps=125.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=True,
            message="healthy",
        ),
        projection=_projection(),
    )

    assert report.verdict == TradeIntentGuardVerdict.allowed
    assert report.can_execute is True
    assert report.blocked_reasons == []
    assert report.warning_reasons == []
    assert report.summary == "trade_intent_guard_ok"
    assert report.guarded_trade_intent.metadata["trade_intent_guard_verdict"] == "allowed"
    assert report.guarded_trade_intent.metadata["trade_intent_guard_id"] == report.guard_id
    assert report.guarded_trade_intent.no_trade_reasons == []


def test_trade_intent_guard_blocks_on_stale_snapshot() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(staleness_ms=180_001),
        edge_after_fees_bps=125.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=True,
            message="healthy",
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert report.can_execute is False
    assert any(reason.startswith("snapshot_stale:") for reason in report.blocked_reasons)
    assert report.manual_review_required is True
    assert any(reason.startswith("snapshot_stale:") for reason in report.guarded_trade_intent.no_trade_reasons)
    assert report.guarded_trade_intent.metadata["trade_intent_guard_verdict"] == "blocked"


def test_trade_intent_guard_blocks_on_manual_review() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(manual_review_required=True),
        snapshot=_snapshot(),
        edge_after_fees_bps=125.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=True,
            message="healthy",
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert "trade_intent_manual_review_required" in report.blocked_reasons
    assert report.manual_review_required is True


def test_trade_intent_guard_blocks_on_no_edge() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(),
        edge_after_fees_bps=0.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=True,
            message="healthy",
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert any(reason.startswith("non_positive_edge_after_fees_bps:") for reason in report.blocked_reasons)
    assert report.can_execute is False


def test_trade_intent_guard_annotates_degraded_venue_health_without_blocking() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(),
        edge_after_fees_bps=125.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=False,
            message="degraded link",
            details={"degraded_mode": True},
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.annotated
    assert report.can_execute is True
    assert report.blocked_reasons == []
    assert any(reason.startswith("venue_degraded:") for reason in report.warning_reasons)
    assert report.venue_health_status == "degraded"
    assert report.guarded_trade_intent.metadata["trade_intent_guard_verdict"] == "annotated"


def test_trade_intent_guard_blocks_on_readiness_not_materializable() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(),
        edge_after_fees_bps=125.0,
        readiness=_readiness(
            manual_review_required=True,
            risk_checks_passed=False,
            route="blocked",
            blocked_reasons=["decision_action=wait"],
            no_trade_reasons=["decision_action=wait"],
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert "readiness_manual_review_required" in report.blocked_reasons
    assert "readiness_not_materializable" in report.blocked_reasons
    assert report.readiness_route == "blocked"
    assert report.manual_review_required is True


def test_trade_intent_guard_blocks_on_projection_blocked() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(),
        edge_after_fees_bps=125.0,
        projection=_projection(
            verdict=ExecutionProjectionVerdict.blocked,
            projected_mode=ExecutionProjectionOutcome.shadow,
            manual_review_required=True,
            blocking_reasons=["live_gate_not_passed"],
            downgrade_reasons=["live_downgraded_to_shadow"],
        ),
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert report.projection_verdict == ExecutionProjectionVerdict.blocked.value
    assert "projection_manual_review_required" in report.blocked_reasons
    assert any(reason.startswith("live_gate_not_passed") for reason in report.blocked_reasons)
    assert "projection_downgraded:shadow" in report.warning_reasons


def test_trade_intent_guard_blocks_on_risk_thresholds_and_resolution_metadata() -> None:
    report = TradeIntentGuard().evaluate(
        _trade_intent(),
        snapshot=_snapshot(staleness_ms=150_001, liquidity=500.0, depth_near_touch=12.0),
        edge_after_fees_bps=30.0,
        projection=_projection(
            metadata={
                "action_time_guard": {
                    "resolution_guard_valid": False,
                    "resolution_guard_approved": False,
                    "resolution_guard_manual_review_required": True,
                    "resolution_guard_status": "manual_review",
                    "resolution_guard": {
                        "blocked_reasons": [
                            "resolution_guard_not_approved",
                            "resolution_guard_manual_review_required",
                            "resolution_policy_completeness_below_minimum:0.450/0.600",
                            "resolution_policy_coherence_below_minimum:0.400/0.600",
                        ],
                        "degraded_reasons": [],
                    },
                    "resolution_guard_policy_completeness_score": 0.45,
                    "resolution_guard_policy_coherence_score": 0.40,
                    "resolution_guard_payout_compatibility_score": 0.50,
                    "resolution_guard_currency_compatibility_score": 0.55,
                },
            }
        ),
        metadata={
            "snapshot_ttl_ms": 90_000,
            "min_liquidity_usd": 1_000.0,
            "snapshot_liquidity_usd": 500.0,
            "min_depth_near_touch": 18.0,
            "snapshot_depth_near_touch": 12.0,
            "min_edge_after_fees_bps": 35.0,
            "min_resolution_compatibility_score": 0.60,
            "min_payout_compatibility_score": 0.70,
            "min_currency_compatibility_score": 0.70,
            "resolution_compatibility_score": 0.45,
            "payout_compatibility_score": 0.50,
            "currency_compatibility_score": 0.55,
        },
    )

    assert report.verdict == TradeIntentGuardVerdict.blocked
    assert "snapshot_stale:150001/90000" in report.blocked_reasons
    assert "liquidity_below_minimum:500.00/1000.00" in report.blocked_reasons
    assert "depth_near_touch_below_minimum:12.00/18.00" in report.blocked_reasons
    assert "edge_after_fees_below_minimum:30.000/35.000" in report.blocked_reasons
    assert "resolution_guard_not_valid" in report.blocked_reasons
    assert "resolution_guard_not_approved" in report.blocked_reasons
    assert "resolution_guard_manual_review_required" in report.blocked_reasons
    assert any(reason.startswith("resolution_policy_completeness_below_minimum") for reason in report.blocked_reasons)
    assert any(reason.startswith("resolution_policy_coherence_below_minimum") for reason in report.blocked_reasons)
    assert any(reason.startswith("resolution_payout_compatibility_below_minimum") for reason in report.blocked_reasons)
    assert any(reason.startswith("resolution_currency_compatibility_below_minimum") for reason in report.blocked_reasons)
    assert report.metadata["trade_intent_guard_min_liquidity_usd"] == pytest.approx(1_000.0)
    assert report.metadata["trade_intent_guard_min_depth_near_touch"] == pytest.approx(18.0)
    assert report.metadata["trade_intent_guard_min_edge_after_fees_bps"] == pytest.approx(35.0)
    assert report.metadata["trade_intent_guard_resolution_threshold"] == pytest.approx(0.60)
