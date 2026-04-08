from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.capital_ledger import CapitalLedger, CapitalLedgerStore
from prediction_markets.live_execution import (
    ExecutionAuthContext,
    ExecutionProjectionRuntime,
    LiveExecutionEngine,
    LiveExecutionPolicy,
    LiveExecutionRequest,
    LiveExecutionStatus,
    LiveExecutionStore,
)
from prediction_markets.market_risk import MarketRiskEvaluator, RiskConstraints
from prediction_markets.execution_edge import ExecutableEdge
from prediction_markets.models import (
    DecisionAction,
    ExecutionReadiness,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    ForecastPacket,
    MarketDescriptor,
    MarketOrderBook,
    MarketRecommendationPacket,
    MarketSnapshot,
    MarketStatus,
    LedgerPosition,
    OrderBookLevel,
    TradeSide,
    VenueName,
    VenueType,
    VenueHealthReport,
)
from prediction_markets.market_execution import MarketExecutionStatus
from prediction_markets.adapters import build_execution_adapter
from prediction_markets.paper_trading import PaperTradeSimulator, PaperTradeStatus, PaperTradeSurface
from prediction_markets.portfolio_allocator import AllocationConstraints, AllocationRequest, PortfolioAllocator
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.resolution_guard import ResolutionGuardReport
from prediction_markets.models import ResolutionStatus
from prediction_markets.shadow_execution import ShadowExecutionEngine, ShadowExecutionStore


@pytest.fixture(autouse=True)
def _live_polymarket_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
    monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/tmp/live_order")
    monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/tmp/cancel_order")


def _market(*, market_id: str = "pm_live", venue: VenueName = VenueName.polymarket) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        category="macro",
        canonical_event_id=f"event_{market_id}",
        resolution_source="https://example.com/resolution",
        status=MarketStatus.open,
        liquidity=10_000.0,
    )


def _snapshot(
    market_id: str,
    *,
    venue: VenueName = VenueName.polymarket,
    liquidity: float = 10_000.0,
    depth_near_touch: float | None = None,
    staleness_ms: int = 0,
    spread_bps: float | None = 100.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        liquidity=liquidity,
        spread_bps=spread_bps,
        staleness_ms=staleness_ms,
        depth_near_touch=depth_near_touch,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=200.0)],
            asks=[OrderBookLevel(price=0.50, size=200.0)],
        ),
        market_implied_probability=0.50,
        price_yes=0.50,
        price_no=0.50,
        midpoint_yes=0.50,
    )


def _forecast(run_id: str, market_id: str) -> ForecastPacket:
    return ForecastPacket(
        run_id=run_id,
        market_id=market_id,
        venue=VenueName.polymarket,
        market_implied_probability=0.50,
        fair_probability=0.61,
        confidence_low=0.57,
        confidence_high=0.65,
        edge_bps=1100.0,
        edge_after_fees_bps=1000.0,
        recommendation_action=DecisionAction.bet,
        manual_review_required=False,
        rationale="signal",
        risks=[],
    )


def _recommendation(run_id: str, market_id: str, *, venue: VenueName = VenueName.polymarket, confidence: float = 0.9) -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id=run_id,
        forecast_id=f"forecast_{run_id}",
        market_id=market_id,
        venue=venue,
        action=DecisionAction.bet,
        side=TradeSide.yes,
        price_reference=0.50,
        edge_bps=750.0,
        confidence=confidence,
        why_now=["edge"],
        why_not_now=[],
        human_summary="execute",
    )


def _ledger(cash: float = 1_000.0) -> CapitalLedger:
    return CapitalLedger.from_cash(cash=cash, venue=VenueName.polymarket)


def _auth() -> ExecutionAuthContext:
    return ExecutionAuthContext(
        principal="tester",
        authorized=True,
        compliance_approved=True,
        jurisdiction="us",
        account_type="retail",
        automation_allowed=True,
        rate_limit_ok=True,
        tos_accepted=True,
        scopes=["prediction_markets:execute"],
    )


def _live_execution_readiness(run_id: str, market_id: str, *, size_usd: float = 25.0) -> ExecutionReadiness:
    return ExecutionReadiness(
        run_id=run_id,
        market_id=market_id,
        venue=VenueName.polymarket,
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=size_usd,
        limit_price=0.5,
        confidence=0.9,
        edge_after_fees_bps=150.0,
        risk_checks_passed=True,
        blocked_reasons=[],
        no_trade_reasons=[],
        ready_to_live=True,
        ready_to_paper=True,
        ready_to_execute=True,
        can_materialize_trade_intent=True,
        metadata={"live_gate_passed": True},
    )


def test_live_execution_blocks_on_kill_switch(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=True,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_kill",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_kill", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.kill_switch_triggered is True
    assert "kill_switch_enabled" in (record.blocked_reason or "")
    assert record.paper_trade is None
    assert record.execution_projection is not None
    assert record.execution_projection.projection_verdict.value == "blocked"
    assert record.market_execution is not None
    assert record.market_execution.status == MarketExecutionStatus.cancelled
    assert record.market_execution.cancelled_reason is not None
    assert record.market_execution.order.acknowledged_at is not None
    assert record.market_execution.order.acknowledged_by == "live_execution_projection"
    assert record.venue_order_source == "local_surrogate"
    assert record.venue_order_status == "cancelled"
    assert record.venue_order_id is not None
    assert record.market_execution.order.metadata["venue_order_id"] == record.venue_order_id
    assert record.market_execution.execution_projection_ref == record.execution_projection.projection_id
    assert record.ledger_after.cash == record.ledger_before.cash
    assert (paths.root / "live_executions" / f"{record.execution_id}.json").exists()


def test_live_execution_requires_human_approval_before_live(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            dry_run_enabled=False,
            allow_live_execution=True,
            require_human_approval_before_live=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_human_gate",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_human_gate", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.projection_verdict == "blocked"
    assert "human_approval_required_before_live" in (record.blocked_reason or "")
    assert "human_approval_required_before_live" in record.no_trade_reasons
    assert record.runtime_guard["human_approval_required"] is True
    assert record.runtime_guard["human_approval_passed"] is False
    assert record.runtime_guard["incident_runbook"]["runbook_id"] == "human_approval_required_before_live"
    assert record.execution_projection is not None
    assert record.execution_projection.manual_review_required is True
    assert record.execution_projection.metadata["human_approval_required_before_live"] is True
    assert record.execution_projection.metadata["human_approval_passed"] is False
    assert record.metadata["approval_gate"]["required"] is True
    assert record.metadata["approval_gate"]["passed"] is False


def test_live_execution_blocks_when_capital_is_frozen_and_audits_runtime_guard(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    ledger = _ledger().current_snapshot()
    ledger.metadata["capital_frozen"] = True
    ledger.metadata["capital_freeze_reason"] = "manual_hold"
    request = LiveExecutionRequest(
        run_id="run_capital_freeze",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_capital_freeze", "pm_live"),
        ledger=ledger,
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.kill_switch_triggered is False
    assert record.runtime_guard["capital_frozen"] is True
    assert "capital_frozen" in record.runtime_guard["blocked_reasons"]
    assert "capital_freeze_reason:manual_hold" in record.runtime_guard["blocked_reasons"]
    assert "capital_frozen" in (record.blocked_reason or "")
    assert "capital_freeze_reason:manual_hold" in (record.blocked_reason or "")
    assert record.market_execution is not None
    assert record.market_execution.status == MarketExecutionStatus.cancelled
    assert record.market_execution.runtime_guard["capital_frozen"] is True
    assert record.market_execution.runtime_guard["incident_summary"].startswith("blocked=")
    assert record.execution_projection.metadata["runtime_guard"]["capital_frozen"] is True


def test_live_execution_blocks_on_open_reconciliation_drift_before_it_is_critical(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    ledger = _ledger().current_snapshot()
    request = LiveExecutionRequest(
        run_id="run_recon_open_drift",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_recon_open_drift", "pm_live"),
        ledger=ledger,
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
        reconciliation_drift_usd=0.25,
        metadata={
            "max_reconciliation_drift_usd": 10.0,
        },
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.runtime_guard["capital_frozen"] is True
    assert "reconciliation_open_drift" in record.runtime_guard["blocked_reasons"]
    assert "reconciliation_drift_usd:0.250000" in record.runtime_guard["reconciliation_reasons"]
    assert "reconciliation_open_drift" in (record.blocked_reason or "")
    assert record.market_execution is not None
    assert record.market_execution.status == MarketExecutionStatus.cancelled
    assert record.market_execution.runtime_guard["capital_frozen"] is True
    assert record.execution_projection.metadata["capital_available"] == pytest.approx(0.0)
    assert record.execution_projection.metadata["capital_control_state"]["capital_frozen"] is True


def test_live_execution_enforces_capital_position_and_loss_caps(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            min_free_cash_buffer_pct=0.2,
            per_venue_balance_cap_usd=900.0,
            max_market_exposure_usd=10.0,
            max_open_positions=1,
            max_daily_loss_usd=25.0,
        )
    )
    ledger = _ledger().current_snapshot().model_copy(
        update={
            "positions": [
                LedgerPosition(
                    market_id="pm_existing",
                    venue=VenueName.polymarket,
                    side=TradeSide.yes,
                    quantity=5.0,
                    entry_price=0.5,
                )
            ],
            "metadata": {**_ledger().current_snapshot().metadata, "daily_loss_usd": 50.0},
        }
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_caps_guard",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_caps_guard", "pm_live"),
            ledger=ledger,
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.loss_cap_triggered is True
    assert record.loss_cap_reason == "daily_loss_cap_exceeded:50.00/25.00"
    assert "max_open_positions_exceeded" in " ".join(record.no_trade_reasons)
    assert "max_daily_loss_usd_exceeded" in " ".join(record.no_trade_reasons)
    assert record.execution_projection is not None
    assert record.execution_projection.metadata["capital_control_state"]["capital_frozen"] is True
    assert record.execution_projection.metadata["capital_control_state"]["min_free_cash_buffer_pct"] == pytest.approx(0.2)
    assert record.execution_projection.metadata["capital_control_state"]["per_venue_balance_cap_usd"] == pytest.approx(900.0)
    assert record.execution_projection.metadata["capital_control_state"]["max_market_exposure_usd"] == pytest.approx(10.0)
    assert record.execution_projection.metadata["capital_control_state"]["max_open_positions"] == 1
    assert record.execution_projection.metadata["capital_control_state"]["max_daily_loss_usd"] == pytest.approx(25.0)


def test_execution_projection_downgrades_when_venue_is_degraded() -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    market = _market()
    ledger = _ledger().current_snapshot()
    readiness = _live_execution_readiness("run_projection", "pm_live")
    execution_plan = build_execution_adapter(VenueName.polymarket).build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )
    projection = engine.projection_runtime.project(
        run_id="run_projection",
        market=market,
        requested_mode="live",
        readiness=readiness,
        execution_plan=execution_plan,
        ledger_before=ledger,
        reconciliation_drift_usd=0.0,
        venue_health=VenueHealthReport(
            venue=VenueName.polymarket,
            backend_mode="live",
            healthy=False,
            message="degraded link",
            details={"degraded_mode": True},
        ),
    )

    assert projection.projection_verdict.value == "degraded"
    assert projection.projected_mode.value == "shadow"
    assert projection.highest_safe_mode == projection.highest_safe_requested_mode
    assert projection.highest_safe_mode.value == "shadow"
    assert projection.highest_authorized_mode.value in {"paper", "shadow", "live"}


def test_live_execution_downgrades_to_dry_run_when_venue_is_degraded(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_venue_degraded",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_venue_degraded", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            execution_readiness=_live_execution_readiness("run_venue_degraded", "pm_live"),
            venue_health=VenueHealthReport(
                venue=VenueName.polymarket,
                backend_mode="live",
                healthy=False,
                message="degraded link",
                checked_at=datetime.now(timezone.utc).replace(microsecond=0),
                details={"degraded_mode": True},
            ),
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.dry_run
    assert record.dry_run is True
    assert record.live_allowed is False
    assert record.execution_projection is not None
    assert record.execution_projection.projection_verdict.value == "degraded"
    assert record.execution_projection.projected_mode.value == "shadow"
    assert "projection_downgraded_to_shadow" in record.execution_reasons
    assert record.market_execution is not None
    assert record.market_execution.mode.value == "bounded_dry_run"
    assert record.market_execution.live_execution_status == "dry_run"
    assert record.ledger_after.cash == record.ledger_before.cash
    assert record.ledger_after.equity == record.ledger_before.equity
    assert record.live_preflight_passed is False
    assert record.attempted_live is False
    assert record.live_submission_phase == "preflight_blocked"
    assert record.metadata["live_preflight_passed"] is False
    assert record.metadata["attempted_live"] is False
    assert record.metadata["live_submission_phase"] == "preflight_blocked"
    assert record.metadata["order_trace_audit"]["transport_mode"] == "dry_run"
    assert record.metadata["order_trace_audit"]["live_preflight_passed"] is False
    assert record.metadata["order_trace_audit"]["attempted_live"] is False
    assert record.metadata["order_trace_audit"]["live_submission_phase"] == "preflight_blocked"
    assert record.metadata["order_trace_audit"]["venue_order_trace_kind"] in {"local_surrogate", "local_live", "external_live"}
    assert record.market_execution.live_preflight_passed is False
    assert record.market_execution.attempted_live is False
    assert record.market_execution.live_submission_phase == "preflight_blocked"
    assert record.market_execution.metadata["order_trace_audit"] == record.metadata["order_trace_audit"]


def test_live_execution_downgrades_to_shadow_when_capital_transfer_latency_is_too_high(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            max_capital_transfer_latency_ms=10_000.0,
        )
    )
    ledger = _ledger().current_snapshot().model_copy(
        update={
            "positions": [
                LedgerPosition(
                    market_id="pm_existing_a",
                    venue=VenueName.polymarket,
                    side=TradeSide.yes,
                    quantity=5.0,
                    entry_price=0.5,
                ),
                LedgerPosition(
                    market_id="pm_existing_b",
                    venue=VenueName.kalshi,
                    side=TradeSide.no,
                    quantity=4.0,
                    entry_price=0.6,
                ),
            ]
        }
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_latency_gate",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_latency_gate", "pm_live"),
            ledger=ledger,
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.dry_run
    assert record.live_allowed is False
    assert record.execution_projection is not None
    assert record.execution_projection.projected_mode.value == "shadow"
    assert "capital_transfer_latency_exceeded" in " ".join(record.execution_reasons)
    assert record.metadata["capital_transfer_latency_estimate_ms"] > record.metadata["max_capital_transfer_latency_ms"]


def test_live_execution_blocks_live_until_enough_resolved_markets_exist(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            min_resolved_markets_for_live=3,
        )
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_resolved_markets_gate",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_resolved_markets_gate", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            metadata={"resolved_markets_count": 1},
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.dry_run
    assert record.live_allowed is False
    assert record.execution_projection is not None
    assert record.execution_projection.projected_mode.value == "shadow"
    assert "resolved_markets_below_minimum" in " ".join(record.execution_reasons)
    assert record.metadata["resolved_markets_count"] == 1
    assert record.metadata["min_resolved_markets_for_live"] == 3


def test_live_execution_requires_manual_review_category_match_before_live(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            manual_review_categories=["capital"],
        )
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_manual_review_category",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_manual_review_category", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            metadata={"manual_review_category": "capital"},
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.dry_run
    assert record.live_allowed is False
    assert record.execution_projection is not None
    assert record.execution_projection.projected_mode.value == "paper"
    assert record.execution_projection.manual_review_required is False
    assert "manual_review_category:capital" in " ".join(record.execution_reasons)
    assert "capital" in record.metadata["manual_review_categories"]
    assert record.execution_projection.metadata["manual_review_category_match"] == ["capital"]


def test_live_execution_blocks_live_when_supplied_projection_hits_degraded_venue(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    projection = ExecutionProjection(
        run_id="run_projection_guard",
        venue=VenueName.polymarket,
        market_id="pm_live",
        requested_mode=ExecutionProjectionMode.live,
        projected_mode=ExecutionProjectionOutcome.live,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.live,
        highest_safe_requested_mode=ExecutionProjectionMode.live,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.live,
        blocking_reasons=[],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1),
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_projection_guard",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_projection_guard", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            execution_readiness=_live_execution_readiness("run_projection_guard", "pm_live"),
            execution_projection=projection,
            venue_health=VenueHealthReport(
                venue=VenueName.polymarket,
                backend_mode="live",
                healthy=False,
                message="degraded link",
                checked_at=datetime.now(timezone.utc).replace(microsecond=0),
                details={"degraded_mode": True},
            ),
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.dry_run
    assert record.dry_run is True
    assert record.live_allowed is False
    assert record.execution_projection is not None
    assert record.execution_projection.projection_verdict == ExecutionProjectionVerdict.ready
    assert record.execution_projection.projected_mode == ExecutionProjectionOutcome.live
    assert "venue_health_degraded" in " ".join(record.execution_reasons)
    assert record.metadata["venue_health_live_allowed"] is False
    assert record.metadata["venue_health_live_reason"].startswith("venue_health_degraded")
    assert record.market_execution is not None
    assert record.market_execution.mode.value == "bounded_dry_run"
    assert record.market_execution.live_execution_status == "dry_run"


@pytest.mark.parametrize(
    ("requested_mode", "expected_projected_mode"),
    [
        ("paper", "paper"),
        ("shadow", "shadow"),
        ("live", "live"),
    ],
)
def test_execution_projection_runtime_is_deterministic_and_respects_mode_bounds(
    requested_mode: str,
    expected_projected_mode: str,
) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    market = _market()
    ledger = _ledger().current_snapshot().model_copy(
        update={"updated_at": datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)}
    )
    readiness = ExecutionReadiness(
        run_id="run_projection_bounds",
        market_id="pm_live",
        venue=VenueName.polymarket,
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=25.0,
        limit_price=0.5,
        confidence=0.9,
        edge_after_fees_bps=150.0,
        risk_checks_passed=True,
        blocked_reasons=[],
        no_trade_reasons=[],
        ready_to_live=True,
        ready_to_paper=True,
        ready_to_execute=True,
        can_materialize_trade_intent=True,
        metadata={"live_gate_passed": True},
    )
    execution_plan = build_execution_adapter(VenueName.polymarket).build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )
    assert execution_plan.venue_order_path == "/tmp/live_order"
    assert execution_plan.venue_order_cancel_path == "/tmp/cancel_order"
    venue_health = VenueHealthReport(
        venue=VenueName.polymarket,
        backend_mode="live",
        healthy=True,
        message="healthy",
        checked_at=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc),
        details={},
    )
    request_metadata = {"anchor_at": "2026-04-08T12:00:00+00:00"}

    first = engine.projection_runtime.project(
        run_id="run_projection_bounds",
        market=market,
        requested_mode=requested_mode,
        readiness=readiness,
        execution_plan=execution_plan,
        ledger_before=ledger,
        request_metadata=request_metadata,
        reconciliation_drift_usd=0.0,
        venue_health=venue_health,
    )
    second = engine.projection_runtime.project(
        run_id="run_projection_bounds",
        market=market,
        requested_mode=requested_mode,
        readiness=readiness,
        execution_plan=execution_plan,
        ledger_before=ledger,
        request_metadata=request_metadata,
        reconciliation_drift_usd=0.0,
        venue_health=venue_health,
    )

    assert first.requested_mode.value == requested_mode
    assert first.projected_mode.value == expected_projected_mode
    assert first.projection_verdict.value == "ready"
    assert first.projection_id == second.projection_id
    assert first.content_hash == second.content_hash
    assert first.expires_at == second.expires_at
    assert first.metadata["projection_anchor_at"] == "2026-04-08T12:00:00+00:00"


@pytest.mark.parametrize(
    ("ledger_metadata", "reconciliation_drift_usd", "venue_health", "expected_projected_mode", "expected_verdict", "expected_capital_frozen"),
    [
        ({"capital_frozen": True}, 0.0, VenueHealthReport(venue=VenueName.polymarket, backend_mode="live", healthy=True, message="healthy", checked_at=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc), details={}), "blocked", "blocked", True),
        ({}, 0.25, VenueHealthReport(venue=VenueName.polymarket, backend_mode="live", healthy=True, message="healthy", checked_at=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc), details={}), "blocked", "blocked", True),
        ({}, 0.0, VenueHealthReport(venue=VenueName.polymarket, backend_mode="live", healthy=False, message="service unavailable", checked_at=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc), details={}), "blocked", "blocked", False),
        ({}, 0.0, VenueHealthReport(venue=VenueName.polymarket, backend_mode="live", healthy=False, message="degraded link", checked_at=datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc), details={"degraded_mode": True}), "shadow", "degraded", False),
    ],
)
def test_execution_projection_runtime_invalidates_on_capital_reconciliation_or_venue_health_drift(
    ledger_metadata: dict[str, object],
    reconciliation_drift_usd: float,
    venue_health: VenueHealthReport,
    expected_projected_mode: str,
    expected_verdict: str,
    expected_capital_frozen: bool,
) -> None:
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    market = _market()
    readiness = ExecutionReadiness(
        run_id="run_projection_drift",
        market_id="pm_live",
        venue=VenueName.polymarket,
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=25.0,
        limit_price=0.5,
        confidence=0.9,
        edge_after_fees_bps=150.0,
        risk_checks_passed=True,
        blocked_reasons=[],
        no_trade_reasons=[],
        ready_to_live=True,
        ready_to_paper=True,
        ready_to_execute=True,
        can_materialize_trade_intent=True,
        metadata={"live_gate_passed": True},
    )
    ledger = _ledger().current_snapshot().model_copy(
        update={
            "updated_at": datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc),
            "metadata": {**_ledger().current_snapshot().metadata, **ledger_metadata},
        }
    )
    execution_plan = build_execution_adapter(VenueName.polymarket).build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )

    projection = engine.projection_runtime.project(
        run_id="run_projection_drift",
        market=market,
        requested_mode="live",
        readiness=readiness,
        execution_plan=execution_plan,
        ledger_before=ledger,
        request_metadata={"anchor_at": "2026-04-08T12:00:00+00:00"},
        reconciliation_drift_usd=reconciliation_drift_usd,
        venue_health=venue_health,
    )

    assert projection.projected_mode.value == expected_projected_mode
    assert projection.projection_verdict.value == expected_verdict
    assert projection.metadata["capital_control_state"]["capital_frozen"] is expected_capital_frozen
    assert projection.metadata["venue_health_healthy"] is venue_health.healthy


def test_live_execution_blocks_when_projection_is_expired_at_action_time(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    market = _market()
    ledger = _ledger().current_snapshot()
    readiness = ExecutionReadiness(
        run_id="run_projection_expired",
        market_id="pm_live",
        venue=VenueName.polymarket,
        decision_action=DecisionAction.bet,
        side=TradeSide.yes,
        size_usd=25.0,
        limit_price=0.5,
        confidence=0.9,
        edge_after_fees_bps=150.0,
        risk_checks_passed=True,
        blocked_reasons=[],
        no_trade_reasons=[],
        metadata={"live_gate_passed": True},
    )
    execution_plan = build_execution_adapter(VenueName.polymarket).build_execution_plan(
        market=market,
        dry_run=False,
        allow_live_execution=True,
        authorized=True,
        compliance_approved=True,
        required_scope="prediction_markets:execute",
        scopes=["prediction_markets:execute"],
    )
    expired_projection = engine.projection_runtime.project(
        run_id="run_projection_expired",
        market=market,
        requested_mode="live",
        readiness=readiness,
        execution_plan=execution_plan,
        ledger_before=ledger,
        reconciliation_drift_usd=0.0,
    ).model_copy(update={"expires_at": datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1)})

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_projection_expired",
            market=market,
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_projection_expired", "pm_live"),
            ledger=ledger,
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            execution_projection=expired_projection,
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.execution_projection is not None
    assert record.action_time_guard["projection_valid"] is False
    assert "execution_projection_expired" in record.action_time_guard["blocked_reasons"]
    assert "execution_projection_expired" in (record.blocked_reason or "")
    assert "execution_projection_expired" in (record.market_execution.cancelled_reason or "")


def test_live_execution_blocks_when_resolution_guard_is_not_clear(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    resolution_guard = ResolutionGuardReport(
        market_id="pm_live",
        venue=VenueName.polymarket.value,
        policy_id="respol_manual",
        approved=False,
        can_forecast=False,
        manual_review_required=True,
        reasons=["missing_official_source"],
        ambiguity_flags=["missing_official_source"],
        official_source=None,
        status=ResolutionStatus.manual_review,
        metadata={"source_url": "https://example.com/resolution"},
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_resolution_guard",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_resolution_guard", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            resolution_guard=resolution_guard,
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.action_time_guard["resolution_guard_valid"] is False
    assert "resolution_guard_not_approved" in record.action_time_guard["blocked_reasons"]
    assert "resolution_guard_manual_review_required" in record.action_time_guard["blocked_reasons"]
    assert "resolution_guard_status:manual_review" in record.action_time_guard["blocked_reasons"]
    assert "resolution_guard_not_approved" in (record.blocked_reason or "")
    assert "resolution_guard_not_approved" in (record.market_execution.cancelled_reason or "")


def test_live_execution_blocks_on_thresholds_and_explicit_resolution_compatibility_reasons(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    resolution_guard = ResolutionGuardReport(
        market_id="pm_live",
        venue=VenueName.polymarket.value,
        policy_id="respol_thresholds",
        approved=True,
        can_forecast=True,
        manual_review_required=False,
        reasons=[],
        ambiguity_flags=[],
        official_source="https://example.com/resolution",
        status=ResolutionStatus.clear,
        policy_completeness_score=0.45,
        policy_coherence_score=0.40,
        metadata={
            "resolution_compatibility_score": 0.45,
            "payout_compatibility_score": 0.50,
            "currency_compatibility_score": 0.55,
        },
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_thresholds",
            market=_market(),
            snapshot=_snapshot(
                "pm_live",
                liquidity=500.0,
                depth_near_touch=12.0,
                staleness_ms=150_000,
            ),
            recommendation=_recommendation("run_thresholds", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            resolution_guard=resolution_guard,
            metadata={
                "snapshot_ttl_ms": 90_000,
                "min_liquidity_usd": 1_000.0,
                "min_depth_near_touch": 18.0,
                "min_edge_after_fees_bps": 35.0,
                "min_resolution_compatibility_score": 0.60,
                "min_payout_compatibility_score": 0.70,
                "min_currency_compatibility_score": 0.70,
            },
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.runtime_guard["verdict"] == "blocked"
    assert "snapshot_stale:150000/90000" in record.runtime_guard["blocked_reasons"]
    assert "liquidity_below_minimum:500.00/1000.00" in record.runtime_guard["blocked_reasons"]
    assert "depth_near_touch_below_minimum:12.00/18.00" in record.runtime_guard["blocked_reasons"]
    assert "resolution_compatibility_below_minimum:0.450/0.600" in record.runtime_guard["blocked_reasons"]
    assert "payout_compatibility_below_minimum:0.500/0.700" in record.runtime_guard["blocked_reasons"]
    assert "currency_compatibility_below_minimum:0.550/0.700" in record.runtime_guard["blocked_reasons"]
    assert record.action_time_guard["resolution_guard_valid"] is False
    assert "resolution_policy_completeness_below_minimum:0.450/0.600" in record.action_time_guard["blocked_reasons"]
    assert "resolution_policy_coherence_below_minimum:0.400/0.600" in record.action_time_guard["blocked_reasons"]
    assert "resolution_payout_compatibility_below_minimum:0.500/0.700" in record.action_time_guard["blocked_reasons"]
    assert "resolution_currency_compatibility_below_minimum:0.550/0.700" in record.action_time_guard["blocked_reasons"]
    assert "snapshot_stale:150000/90000" in (record.blocked_reason or "")
    assert "resolution_policy_completeness_below_minimum" in (record.blocked_reason or "")


def test_live_execution_blocks_when_executable_edge_is_expired(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    executable_edge = ExecutableEdge(
        market_ref="pm_live",
        raw_edge_bps=420.0,
        fees_bps=20.0,
        slippage_bps=10.0,
        hedge_risk_bps=10.0,
        confidence=0.9,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1),
        manual_review_required=False,
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_edge_guard",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_edge_guard", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            executable_edge=executable_edge,
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.action_time_guard["executable_edge_valid"] is False
    assert "executable_edge_expired" in record.action_time_guard["blocked_reasons"]
    assert "executable_edge_expired" in (record.blocked_reason or "")
    assert "executable_edge_expired" in (record.market_execution.cancelled_reason or "")


def test_live_execution_blocks_when_edge_disappears_after_fees_and_slippage(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    executable_edge = ExecutableEdge(
        market_ref="pm_live",
        raw_edge_bps=35.0,
        fees_bps=20.0,
        slippage_bps=15.0,
        hedge_risk_bps=5.0,
        confidence=0.9,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=5),
        manual_review_required=False,
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_edge_after_fees",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_edge_after_fees", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=25.0,
            requested_mode="live",
            executable_edge=executable_edge,
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert record.status == LiveExecutionStatus.blocked
    assert record.action_time_guard["executable_edge_valid"] is False
    assert "executable_edge_non_positive" in record.action_time_guard["blocked_reasons"]
    assert "executable_edge_not_executable" in record.action_time_guard["blocked_reasons"]
    assert "executable_edge_non_positive" in (record.blocked_reason or "")
    assert "executable_edge_non_positive" in (record.market_execution.cancelled_reason or "")


def test_live_execution_blocks_on_reconciliation_drift_metadata_and_records_incident(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_recon_drift",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_recon_drift", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
        metadata={
            "reconciliation_drift_usd": 2.5,
            "max_reconciliation_drift_usd": 1.0,
        },
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.runtime_guard["verdict"] == "blocked"
    assert "reconciliation_drift_exceeded:2.500000/1.000000" in record.runtime_guard["blocked_reasons"]
    assert "reconciliation_drift_exceeded:2.500000/1.000000" in (record.blocked_reason or "")
    assert record.runtime_guard["incident_summary"].startswith("blocked=")
    assert "reconciliation_drift_usd:2.500000" in record.runtime_guard["reconciliation_reasons"]
    assert record.market_execution is not None
    assert record.market_execution.runtime_guard["blocked_reasons"]


def test_live_execution_blocks_when_venue_is_not_allowed(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_venue",
        market=_market(venue=VenueName.kalshi),
        snapshot=_snapshot("pm_live", venue=VenueName.kalshi),
        recommendation=_recommendation("run_venue", "pm_live", venue=VenueName.kalshi),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.venue_allowed is False
    assert "venue_not_allowed" in (record.blocked_reason or "")


def test_live_execution_propagates_explicit_venue_order_id_from_metadata(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=True,
            allow_live_execution=False,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_venue_order_id",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_venue_order_id", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        dry_run=True,
        metadata={"venue_order_id": "external_venue_order_001"},
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.dry_run
    assert record.venue_order_source == "external"
    assert record.venue_order_id == "external_venue_order_001"
    assert record.venue_order_status in {"filled", "partial", "rejected", "simulated"}
    assert record.market_execution is not None
    assert record.market_execution.order.metadata["venue_order_id"] == "external_venue_order_001"
    assert record.market_execution.order.metadata["venue_order_source"] == "external"


def test_live_execution_preserves_external_order_lifecycle_trace_on_blocked_path(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=True,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_external_trace",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_external_trace", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        requested_mode="live",
        metadata={
            "venue_order_id": "external_venue_order_002",
            "venue_order_source": "external",
            "venue_order_status_history": ["submitted", "acknowledged", "cancelled"],
            "venue_order_acknowledged_at": "2026-04-08T12:10:00+00:00",
            "venue_order_acknowledged_by": "venue_api",
            "venue_order_acknowledged_reason": "user_cancelled",
            "venue_order_cancel_reason": "user_cancelled",
            "venue_order_cancelled_at": "2026-04-08T12:11:00+00:00",
            "venue_order_cancelled_by": "venue_api",
        },
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.venue_order_source == "external"
    assert record.venue_order_trace_kind == "external_live"
    assert record.venue_order_flow == "submitted->acknowledged->cancelled"
    assert record.venue_order_status_history == ["submitted", "acknowledged", "cancelled"]
    assert record.venue_order_acknowledged_at is not None
    assert record.venue_order_acknowledged_by == "venue_api"
    assert record.venue_order_acknowledged_reason == "user_cancelled"
    assert record.venue_order_cancelled_by == "venue_api"
    assert record.market_execution is not None
    assert record.market_execution.order.status == "cancelled"
    assert record.market_execution.order.acknowledged_by == "venue_api"
    assert record.market_execution.order.cancelled_by == "venue_api"
    assert record.market_execution.order.metadata["venue_order_trace_kind"] == "external_live"
    assert record.market_execution.metadata["venue_order_flow"] == "submitted->acknowledged->cancelled"
    assert (paths.root / "live_executions" / f"{record.execution_id}.json").exists()


def test_live_execution_blocks_on_realized_loss_cap(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    ledger = _ledger().current_snapshot()
    ledger.realized_pnl = -60.0
    ledger.equity = 940.0
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            max_realized_loss=50.0,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_loss_cap",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_loss_cap", "pm_live"),
        ledger=ledger,
        auth=_auth(),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.loss_cap_triggered is True
    assert "realized_loss_cap_exceeded" in (record.loss_cap_reason or "")
    assert "realized_loss_cap_exceeded" in (record.blocked_reason or "")
    assert record.paper_trade is None


def test_live_execution_blocks_on_drawdown_cap(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    ledger = _ledger().current_snapshot()
    ledger.equity = 950.0
    ledger.metadata["equity_high_watermark"] = 1200.0
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            max_drawdown_abs=200.0,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_drawdown_cap",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_drawdown_cap", "pm_live"),
        ledger=ledger,
        auth=_auth(),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.loss_cap_triggered is True
    assert "drawdown_cap_exceeded" in (record.loss_cap_reason or "")
    assert "drawdown_cap_exceeded" in (record.blocked_reason or "")
    assert record.paper_trade is None


def test_live_execution_blocks_without_auth_and_compliance(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_auth",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_auth", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=ExecutionAuthContext(principal="tester", authorized=False, compliance_approved=False, scopes=[]),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.auth_passed is False
    assert record.compliance_passed is False
    assert "authorization_failed" in (record.blocked_reason or "")
    assert "compliance_failed" in (record.blocked_reason or "")


def test_live_execution_blocks_on_jurisdiction_account_and_automation_constraints(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            allowed_jurisdictions={"us"},
            allowed_account_types={"retail"},
            require_automation_allowed=True,
            require_rate_limit_ok=True,
            require_tos_accepted=True,
        )
    )
    request = LiveExecutionRequest(
        run_id="run_compliance_gate",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_compliance_gate", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=ExecutionAuthContext(
            principal="tester",
            authorized=True,
            compliance_approved=True,
            jurisdiction="fr",
            account_type="demo",
            automation_allowed=False,
            rate_limit_ok=False,
            tos_accepted=False,
            scopes=["prediction_markets:execute"],
        ),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.jurisdiction_required is True
    assert record.account_type_required is True
    assert record.automation_required is True
    assert record.rate_limit_required is True
    assert record.tos_required is True
    assert record.jurisdiction_passed is False
    assert record.account_type_passed is False
    assert record.automation_passed is False
    assert record.rate_limit_passed is False
    assert record.tos_passed is False
    assert "jurisdiction_not_allowed" in (record.blocked_reason or "")
    assert "account_type_not_allowed" in (record.blocked_reason or "")
    assert "automation_not_allowed" in (record.blocked_reason or "")
    assert "rate_limit_exceeded" in (record.blocked_reason or "")
    assert "tos_not_accepted" in (record.blocked_reason or "")


def test_live_execution_dry_run_can_skip_live_authorization(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=True,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_dry_unauth",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_dry_unauth", "pm_live"),
        ledger=_ledger().current_snapshot(),
        auth=ExecutionAuthContext(principal="tester", authorized=False, compliance_approved=False, scopes=[]),
        dry_run=True,
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.dry_run
    assert record.dry_run is True
    assert record.auth_required is False
    assert record.compliance_required is False
    assert record.auth_passed is True
    assert record.compliance_passed is True
    assert record.execution_adapter == "polymarket_execution_adapter"
    assert record.execution_plan["dry_run_requested"] is True
    assert record.execution_plan["allowed"] is True
    assert record.market_execution is not None
    assert record.market_execution.mode.value == "bounded_dry_run"
    assert record.market_execution.live_execution_status == "dry_run"
    assert record.market_execution.metadata["live_execution_status"] == "dry_run"
    assert record.market_execution.positions
    assert record.market_execution.execution_projection_ref == record.execution_projection.projection_id


def test_live_execution_blocks_live_kalshi_when_live_execution_is_unsupported(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    capability = build_execution_adapter(VenueName.kalshi).describe_execution_capabilities()
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket, VenueName.kalshi},
        )
    )
    request = LiveExecutionRequest(
        run_id="run_kalshi_live",
        market=_market(market_id="kalshi_live", venue=VenueName.kalshi),
        snapshot=_snapshot("kalshi_live", venue=VenueName.kalshi),
        recommendation=_recommendation("run_kalshi_live", "kalshi_live", venue=VenueName.kalshi),
        ledger=_ledger().current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
        dry_run=False,
    )

    record = engine.execute(request, persist=False, store=LiveExecutionStore(paths))

    assert record.status == LiveExecutionStatus.blocked
    assert record.live_allowed is False
    assert record.execution_adapter == "kalshi_execution_adapter"
    assert capability.metadata["order_paths"]["bounded"] == "external_bounded_api"
    assert capability.metadata["order_paths"]["cancel"] == "external_bounded_cancel_api"
    assert record.execution_plan["live_execution_supported"] is False
    assert record.execution_plan["venue_order_path"] == "external_bounded_api"
    assert record.execution_plan["venue_order_cancel_path"] == "external_bounded_cancel_api"
    assert record.venue_order_path == "external_bounded_api"
    assert record.venue_order_cancel_path == "external_bounded_cancel_api"
    assert "live_execution_unsupported:kalshi" in (record.blocked_reason or "")


def test_live_execution_dry_run_persists_record_without_mutating_ledger(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=True,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        )
    )
    ledger = _ledger()
    request = LiveExecutionRequest(
        run_id="run_dry",
        market=_market(),
        snapshot=_snapshot("pm_live"),
        recommendation=_recommendation("run_dry", "pm_live"),
        ledger=ledger.current_snapshot(),
        auth=_auth(),
        requested_stake=25.0,
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths), ledger_store=CapitalLedgerStore(base_dir=paths.root))

    assert record.status == LiveExecutionStatus.dry_run
    assert record.dry_run is True
    assert record.paper_trade is not None
    assert record.ledger_after.cash == record.ledger_before.cash
    assert record.ledger_after.equity == record.ledger_before.equity
    assert record.executed_stake > 0.0
    assert (paths.root / "live_executions" / f"{record.execution_id}.json").exists()
    assert (paths.root / "paper_trades" / f"{record.paper_trade.trade_id}.json").exists()
    assert (paths.root / "capital_ledger" / f"{record.ledger_after.snapshot_id}.json").exists()


def test_paper_trade_postmortem_reclassifies_stale_snapshot_as_no_trade() -> None:
    simulator = PaperTradeSimulator()
    snapshot = _snapshot("pm_stale", staleness_ms=300_000)

    simulation = simulator.simulate(
        snapshot,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        stake=25.0,
        run_id="run_stale_paper",
    )

    postmortem = simulation.postmortem()
    surface = PaperTradeSurface.from_simulations([simulation], report_id="surface_stale")

    assert simulation.status == PaperTradeStatus.skipped
    assert simulation.metadata["stale_blocked"] is True
    assert postmortem.no_trade_zone is True
    assert postmortem.recommendation == "no_trade"
    assert "stale_blocked" in postmortem.notes
    assert "snapshot_stale" in postmortem.notes
    assert surface.no_trade_zone_count == 1
    assert surface.stale_block_count == 1
    assert surface.no_trade_zone_rate == 1.0


def test_shadow_execution_records_paper_shadow_divergence_when_paper_is_stale_but_shadow_is_tradeable(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths)
    snapshot = _snapshot("pm_shadow", staleness_ms=300_000, spread_bps=80.0)
    recommendation = _recommendation("run_shadow_divergence", "pm_shadow", confidence=0.88)
    projection = ExecutionProjection(
        run_id="run_shadow_divergence",
        venue=VenueName.polymarket,
        market_id="pm_shadow",
        requested_mode=ExecutionProjectionMode.shadow,
        projected_mode=ExecutionProjectionOutcome.shadow,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.shadow,
        highest_safe_requested_mode=ExecutionProjectionMode.shadow,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.shadow,
        blocking_reasons=[],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1),
    )

    result = engine.run(
        recommendation,
        snapshot,
        execution_projection=projection,
        persist=True,
        store=store,
    )

    divergence = result.metadata["paper_shadow_divergence"]

    assert result.would_trade is True
    assert result.paper_trade is not None
    assert result.paper_trade.status == PaperTradeStatus.skipped
    assert divergence["divergence_class"] == "paper_no_trade_shadow_tradeable"
    assert divergence["paper_no_trade_zone"] is True
    assert divergence["paper_recommendation"] == "no_trade"
    assert divergence["paper_trade_status"] == "skipped"
    assert divergence["shadow_eligible"] is True
    assert "paper_shadow_divergence:paper_no_trade_shadow_tradeable" in result.risk_flags
    assert "paper_shadow_divergence:paper_no_trade_shadow_tradeable" in result.incident_alerts
    assert "divergence=paper_no_trade_shadow_tradeable" in result.incident_summary
    assert result.metadata["paper_trade_postmortem"]["no_trade_zone"] is True
    assert result.metadata["paper_trade_postmortem"]["recommendation"] == "no_trade"
    assert any(store.incident_root.glob("*.json"))
    assert (store.root / f"{result.shadow_id}.json").exists()
    assert (paths.paper_trades_dir / f"{result.paper_trade.trade_id}.json").exists()


def test_live_execution_live_path_projects_ledger_and_persists(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            max_stake=200.0,
            max_fraction_of_equity=0.15,
        )
    )
    market = _market()
    snapshot = _snapshot("pm_live")
    forecast = _forecast("run_live", "pm_live")
    recommendation = _recommendation("run_live", "pm_live", confidence=0.92)
    ledger = _ledger(cash=1_000.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger.current_snapshot(),
        run_id="run_live",
    )
    allocation = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    ).allocate(
        request=AllocationRequest(
            run_id="run_live",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=ledger.current_snapshot(),
    )

    request = LiveExecutionRequest(
        run_id="run_live",
        market=market,
        snapshot=snapshot,
        recommendation=recommendation,
        ledger=ledger.current_snapshot(),
        risk_report=risk,
        auth=_auth(),
        requested_stake=allocation.recommended_stake,
        requested_mode="live",
        execution_readiness=_live_execution_readiness("run_live", "pm_live", size_usd=allocation.recommended_stake),
        metadata={"allocation_id": allocation.allocation_id},
    )

    record = engine.execute(request, persist=True, store=LiveExecutionStore(paths))

    assert record.status in {LiveExecutionStatus.filled, LiveExecutionStatus.partial}
    assert record.dry_run is False
    assert record.paper_trade is not None
    assert record.market_execution is not None
    assert record.market_execution.mode.value == "bounded_live"
    assert record.market_execution.live_execution_status == record.status.value
    assert record.market_execution.positions
    assert record.market_execution.execution_projection_ref == record.execution_projection.projection_id
    assert record.ledger_change is not None
    assert record.ledger_after.cash < record.ledger_before.cash
    assert record.ledger_after.positions
    assert record.blocked_reason is None
    assert record.allocation_id == allocation.allocation_id

    loaded_record = LiveExecutionStore(paths).load(record.execution_id)
    loaded_ledger = CapitalLedgerStore(base_dir=paths.root).load_snapshot(record.ledger_after.snapshot_id)
    assert loaded_record.execution_id == record.execution_id
    assert loaded_ledger.snapshot_id == record.ledger_after.snapshot_id


def test_live_execution_live_path_uses_bound_polymarket_transport_and_audits_external_trace(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    submitted_calls: list[tuple[object, object]] = []

    def _submit_order(order, payload):  # noqa: ANN001
        submitted_calls.append((order, payload))
        return {
            "venue_order_id": "external_venue_order_live_001",
            "venue_order_source": "external",
            "venue_order_status": "submitted",
            "venue_order_status_history": ["submitted", "acknowledged"],
            "venue_order_acknowledged_at": "2026-04-08T12:00:00+00:00",
            "venue_order_acknowledged_by": "polymarket_api",
            "venue_order_acknowledged_reason": "submitted",
            "venue_order_path": "external_live_api",
            "venue_order_cancel_path": "external_live_cancel_api",
            "venue_order_trace_kind": "external_live",
            "venue_order_flow": "submitted->acknowledged",
        }

    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
            max_stake=200.0,
            max_fraction_of_equity=0.15,
        ),
        venue_order_submitters={VenueName.polymarket: _submit_order},
    )
    market = _market()
    snapshot = _snapshot("pm_live")
    forecast = _forecast("run_live_submit", "pm_live")
    recommendation = _recommendation("run_live_submit", "pm_live", confidence=0.92)
    ledger = _ledger(cash=1_000.0)
    risk = MarketRiskEvaluator(
        constraints=RiskConstraints(
            min_edge_bps=35.0,
            min_confidence=0.55,
            max_position_fraction_of_equity=0.2,
            max_theme_fraction_of_equity=0.2,
            max_correlation_fraction_of_equity=0.2,
        )
    ).assess(
        market=market,
        snapshot=snapshot,
        forecast=forecast,
        recommendation=recommendation,
        ledger=ledger.current_snapshot(),
        run_id="run_live_submit",
    )
    allocation = PortfolioAllocator(
        constraints=AllocationConstraints(
            max_portfolio_fraction_of_equity=0.15,
            min_trade_notional=5.0,
            kelly_scale=0.5,
            liquidity_target=25_000.0,
        )
    ).allocate(
        request=AllocationRequest(
            run_id="run_live_submit",
            market=market,
            snapshot=snapshot,
            forecast=forecast,
            recommendation=recommendation,
            risk_report=risk,
        ),
        ledger=ledger.current_snapshot(),
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_live_submit",
            market=market,
            snapshot=snapshot,
            recommendation=recommendation,
            ledger=ledger.current_snapshot(),
            risk_report=risk,
            auth=_auth(),
            requested_stake=allocation.recommended_stake,
            requested_mode="live",
            execution_readiness=_live_execution_readiness("run_live_submit", "pm_live", size_usd=allocation.recommended_stake),
            metadata={"allocation_id": allocation.allocation_id},
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert submitted_calls
    submitted_order, submitted_payload = submitted_calls[0]
    assert getattr(submitted_order, "market_id", None) == "pm_live"
    assert submitted_payload["metadata"]["allow_live_execution"] is True
    assert submitted_payload["metadata"]["dry_run"] is False
    assert submitted_payload["metadata"]["live_transport_bound"] is True
    assert record.status in {LiveExecutionStatus.filled, LiveExecutionStatus.partial}
    assert record.dry_run is False
    assert record.venue_order_source == "external"
    assert record.venue_order_id == "external_venue_order_live_001"
    assert record.venue_order_trace_kind == "external_live"
    assert record.venue_order_flow == "submitted->acknowledged"
    assert record.venue_submission_state == "venue_submitted"
    assert record.venue_ack_state == "venue_acknowledged"
    assert record.venue_execution_state == "venue_acknowledged"
    assert record.venue_order_ack_path == record.metadata["venue_order_path"]
    assert record.live_preflight_passed is True
    assert record.metadata["live_route_allowed"] is True
    assert record.attempted_live is True
    assert record.live_submission_performed is True
    assert record.live_submission_phase == "performed_live"
    assert record.venue_live_submission_bound is True
    assert record.operator_bound is True
    assert record.live_runtime_honest_mode == "live"
    assert record.live_submission_failed is None
    assert record.live_acknowledged is True
    assert record.live_cancel_observed is False
    assert record.live_submission_receipt["transport_mode"] == "live"
    assert record.live_submission_receipt["runtime_honest_mode"] == "live"
    assert record.live_submission_receipt["live_route_allowed"] is True
    assert record.live_submission_receipt["acknowledged"] is True
    assert record.live_submission_receipt["cancel_observed"] is False
    assert record.venue_submission_receipt["venue_order_submission_state"] == "venue_submitted"
    assert record.venue_submission_receipt["acknowledged"] is True
    assert record.venue_cancellation_receipt["venue_order_cancel_state"] == "not_cancelled"
    assert record.live_transport_readiness["transport_bound"] is True
    assert record.live_transport_readiness["operator_bound"] is True
    assert record.live_transport_readiness["transport_callable"] is True
    assert record.live_transport_readiness["transport_mode"] == "live"
    assert record.venue_live_configuration_snapshot["runtime_ready"] is True
    assert record.live_auth_compliance_evidence["auth_passed"] is True
    assert record.live_auth_compliance_evidence["compliance_passed"] is True
    assert record.live_route_evidence["selected_order_source"] == "external"
    assert record.live_route_evidence["live_route_allowed"] is True
    assert record.live_route_evidence["selected_order_path"] == record.metadata["venue_order_path"]
    assert record.selected_live_path_receipt["selected_transport_mode"] == "live"
    assert record.selected_live_path_receipt["live_route_allowed"] is True
    assert record.order_trace_artifacts["live_submission_receipt"]["acknowledged"] is True
    assert record.live_attempt_timeline["phase_history"][0] == "preflight_ready"
    assert record.live_attempt_timeline["attempted_at"] is not None
    assert record.live_attempt_timeline["acknowledged"] is True
    assert record.live_blocker_snapshot["is_blocked"] is False
    assert record.live_blocker_snapshot["operator_bound"] is True
    assert record.live_blocker_snapshot["live_available"] is True
    assert record.live_blocker_snapshot["route_state"] == "available"
    assert record.selected_live_path_audit["selected_live_path_receipt"]["selected_transport_mode"] == "live"
    assert record.live_lifecycle_snapshot["venue_order_trace_kind"] == "external_live"
    assert record.metadata["venue_live_submission_bound"] is True
    assert record.metadata["operator_bound"] is True
    assert record.metadata["live_route_allowed"] is True
    assert record.metadata["live_preflight_passed"] is True
    assert record.metadata["attempted_live"] is True
    assert record.metadata["venue_live_submission_performed"] is True
    assert record.metadata["live_submission_phase"] == "performed_live"
    assert record.metadata["order_trace_audit"]["transport_mode"] == "live"
    assert record.metadata["order_trace_audit"]["live_route_allowed"] is True
    assert record.metadata["order_trace_audit"]["attempted_live"] is True
    assert record.metadata["order_trace_audit"]["live_submission_performed"] is True
    assert record.metadata["order_trace_audit"]["live_submission_phase"] == "performed_live"
    assert record.metadata["order_trace_audit"]["venue_order_ack_path"] == record.metadata["venue_order_path"]
    assert record.market_execution is not None
    assert record.market_execution.venue_order_ack_path == record.metadata["venue_order_path"]
    assert record.market_execution.live_preflight_passed is True
    assert record.market_execution.attempted_live is True
    assert record.market_execution.live_submission_performed is True
    assert record.market_execution.live_submission_phase == "performed_live"
    assert record.market_execution.metadata["live_route_allowed"] is True
    assert record.market_execution.venue_live_submission_bound is True
    assert record.market_execution.operator_bound is True
    assert record.market_execution.live_runtime_honest_mode == "live"
    assert record.market_execution.live_submission_failed is None
    assert record.market_execution.live_acknowledged is True
    assert record.market_execution.live_cancel_observed is False
    assert record.market_execution.order.metadata["venue_order_source"] == "external"
    assert record.market_execution.order.metadata["venue_order_trace_kind"] == "external_live"
    assert record.market_execution.order.metadata["venue_order_ack_path"] == record.market_execution.order.metadata["venue_order_path"]
    assert record.market_execution.metadata["venue_order_lifecycle"]["venue_order_trace_kind"] == "external_live"
    assert record.market_execution.venue_submission_state == "venue_submitted"
    assert record.market_execution.venue_execution_state == "venue_acknowledged"


def test_live_execution_live_path_records_failed_attempt_without_false_live_claim(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    submitted_calls: list[tuple[object, object]] = []

    def _submit_order(order, payload):  # noqa: ANN001
        submitted_calls.append((order, payload))
        raise RuntimeError("venue unavailable")

    engine = LiveExecutionEngine(
        policy=LiveExecutionPolicy(
            kill_switch_enabled=False,
            dry_run_enabled=False,
            allow_live_execution=True,
            allowed_venues={VenueName.polymarket},
        ),
        venue_order_submitters={VenueName.polymarket: _submit_order},
    )

    record = engine.execute(
        LiveExecutionRequest(
            run_id="run_live_failed",
            market=_market(),
            snapshot=_snapshot("pm_live"),
            recommendation=_recommendation("run_live_failed", "pm_live"),
            ledger=_ledger().current_snapshot(),
            auth=_auth(),
            requested_stake=15.0,
            requested_mode="live",
            execution_readiness=_live_execution_readiness("run_live_failed", "pm_live", size_usd=15.0),
        ),
        persist=False,
        store=LiveExecutionStore(paths),
    )

    assert submitted_calls
    assert record.dry_run is False
    assert record.live_preflight_passed is True
    assert record.metadata["live_route_allowed"] is True
    assert record.attempted_live is True
    assert record.live_submission_performed is False
    assert record.live_submission_phase == "attempted_live_failed"
    assert record.venue_live_submission_bound is True
    assert record.operator_bound is True
    assert record.live_runtime_honest_mode == "live"
    assert record.live_submission_failed == "RuntimeError"
    assert record.live_submission_receipt["submission_error_type"] == "RuntimeError"
    assert record.live_submission_receipt["live_route_allowed"] is True
    assert record.live_submission_receipt["attempted_live"] is True
    assert record.live_submission_receipt["live_submission_performed"] is False
    assert record.live_submission_receipt["runtime_honest_mode"] == "live"
    assert record.live_submission_receipt["operator_bound"] is True
    assert record.live_transport_readiness["live_submission_phase"] == "attempted_live_failed"
    assert record.live_auth_compliance_evidence["auth_passed"] is True
    assert record.live_route_evidence["live_submission_failed"] == "RuntimeError"
    assert record.live_route_evidence["live_route_allowed"] is True
    assert record.selected_live_path_receipt["submission_error_type"] == "RuntimeError"
    assert record.selected_live_path_receipt["live_route_allowed"] is True
    assert record.selected_live_path_receipt["operator_bound"] is True
    assert record.order_trace_artifacts["live_submission_receipt"]["submission_error_type"] == "RuntimeError"
    assert record.live_attempt_timeline["phase_history"][-1] == "attempted_live_failed"
    assert record.live_attempt_timeline["failed_at"] is not None
    assert record.live_blocker_snapshot["blocked_reason_summary"]
    assert any("RuntimeError" in reason for reason in record.live_blocker_snapshot["transport_failures"])
    assert record.selected_live_path_audit["selected_live_path_receipt"]["submission_error_type"] == "RuntimeError"
    assert record.live_lifecycle_snapshot["submission_error_type"] == "RuntimeError"
    assert record.metadata["order_trace_audit"]["attempted_live"] is True
    assert record.metadata["order_trace_audit"]["operator_bound"] is True
    assert record.metadata["order_trace_audit"]["live_route_allowed"] is True
    assert record.metadata["order_trace_audit"]["live_submission_performed"] is False
    assert record.metadata["order_trace_audit"]["transport_mode"] == "live"
    assert record.metadata["order_trace_audit"]["submission_error_type"] == "RuntimeError"
    assert record.market_execution is not None
    assert record.market_execution.attempted_live is True
    assert record.market_execution.live_submission_performed is False
    assert record.market_execution.live_submission_phase == "attempted_live_failed"
    assert record.market_execution.metadata["live_route_allowed"] is True
    assert record.market_execution.operator_bound is True
    assert record.market_execution.live_submission_failed == "RuntimeError"
