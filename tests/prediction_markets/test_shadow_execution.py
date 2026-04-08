from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.capital_ledger import CapitalLedgerStore
from prediction_markets.models import (
    DecisionAction,
    ExecutionProjection,
    ExecutionProjectionMode,
    ExecutionProjectionOutcome,
    ExecutionProjectionVerdict,
    MarketOrderBook,
    MarketRecommendationPacket,
    MarketSnapshot,
    OrderBookLevel,
    TradeSide,
    VenueName,
)
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.paper_trading import PaperTradeStatus, PaperTradeStore
from prediction_markets.shadow_execution import ShadowExecutionEngine, ShadowExecutionStore


def _shadow_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-shadow",
        venue=VenueName.polymarket,
        title="Shadow execution market",
        question="Will shadow execution persist?",
        price_yes=0.5,
        price_no=0.5,
        midpoint_yes=0.5,
        market_implied_probability=0.5,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.48, size=30.0)],
            asks=[OrderBookLevel(price=0.52, size=30.0)],
        ),
    )


def _shadow_mismatch_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-shadow",
        venue=VenueName.polymarket,
        title="Shadow execution market mismatch",
        question="Will shadow execution persist under mismatch?",
        price_yes=0.45,
        price_no=0.55,
        midpoint_yes=0.45,
        market_implied_probability=0.45,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.40, size=20.0)],
            asks=[OrderBookLevel(price=0.62, size=20.0)],
        ),
    )


def _recommendation(
    *,
    action: DecisionAction,
    side: TradeSide | None,
    confidence: float,
    price_reference: float | None = None,
) -> MarketRecommendationPacket:
    return MarketRecommendationPacket(
        run_id="shadow-run",
        forecast_id="forecast-shadow",
        market_id="pm-shadow",
        venue=VenueName.polymarket,
        action=action,
        side=side,
        price_reference=price_reference,
        confidence=confidence,
        human_summary="Shadow test recommendation",
    )


def _projection(*, run_id: str, stale: bool = False, kill_switch: bool = False) -> ExecutionProjection:
    anchor_at = datetime.now(timezone.utc) - timedelta(hours=2 if stale else 0)
    metadata = {
        "anchor_at": anchor_at.isoformat(),
        "stale_after_seconds": 60.0 if stale else 3600.0,
    }
    if kill_switch:
        metadata["kill_switch_triggered"] = True
    return ExecutionProjection(
        run_id=run_id,
        venue=VenueName.polymarket,
        market_id="pm-shadow",
        requested_mode=ExecutionProjectionMode.shadow,
        projected_mode=ExecutionProjectionOutcome.shadow,
        projection_verdict=ExecutionProjectionVerdict.ready,
        highest_safe_mode=ExecutionProjectionMode.shadow,
        highest_safe_requested_mode=ExecutionProjectionMode.shadow,
        highest_authorized_mode=ExecutionProjectionOutcome.live,
        recommended_effective_mode=ExecutionProjectionOutcome.shadow,
        blocking_reasons=["kill_switch_enabled"] if kill_switch else [],
        downgrade_reasons=[],
        manual_review_required=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        metadata=metadata,
    )


def test_shadow_execution_skips_non_bet_recommendations(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    projection = _projection(run_id="shadow-run")
    projection.persist(paths.run_dir("shadow-run") / "execution_projection.json")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths=paths)
    result = engine.run(
        _recommendation(action=DecisionAction.wait, side=None, confidence=0.2),
        _shadow_snapshot(),
        store=store,
    )

    assert result.would_trade is False
    assert result.blocked_reason == "recommendation does not call for a bet"
    assert result.paper_trade is None
    assert result.ledger_before == result.ledger_after
    assert result.risk_flags == ["no_live_trade"]
    assert result.projection_gate_valid is True
    assert result.execution_projection_id == projection.projection_id
    assert result.incident_alerts == []
    assert result.incident_runbook["runbook_id"] == "shadow_execution_ok"


def test_shadow_execution_blocks_without_projection_and_logs_incident(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths=paths)

    result = engine.run(
        _recommendation(action=DecisionAction.bet, side=TradeSide.yes, confidence=0.9),
        _shadow_snapshot(),
        persist=True,
        store=store,
    )

    assert result.would_trade is False
    assert result.blocked_reason is not None
    assert "execution projection" in result.blocked_reason.lower()
    assert result.projection_gate_valid is False
    assert "execution_projection_missing" in result.risk_flags
    assert "execution_projection_missing" in result.incident_alerts
    assert result.incident_runbook["runbook_id"] == "shadow_execution_projection_missing"
    assert (store.incident_root).exists()
    assert list(store.incident_root.glob("*.json"))


def test_shadow_execution_runs_paper_trade_and_persists(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    projection = _projection(run_id="shadow-run")
    projection.persist(paths.run_dir("shadow-run") / "execution_projection.json")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths=paths)

    result = engine.run(
        _recommendation(
            action=DecisionAction.bet,
            side=TradeSide.yes,
            confidence=0.9,
            price_reference=0.55,
        ),
        _shadow_snapshot(),
        persist=True,
        store=store,
    )

    assert result.would_trade is True
    assert result.blocked_reason is None
    assert result.paper_trade is not None
    assert result.paper_trade.status is PaperTradeStatus.filled
    assert result.slippage_fit_status in {"fit", "partial_fit", "synthetic_reference"}
    assert result.microstructure_fit_status in {"fit", "partial_fit", "synthetic_reference"}
    assert result.market_fit_status in {"fit", "partial_fit", "synthetic_reference"}
    assert result.market_fit_score >= 0.0
    assert result.market_fit_report is not None
    assert result.market_fit_report["shadow_eligible"] is True
    assert result.metadata["paper_trade_postmortem"]["fill_rate"] == pytest.approx(result.paper_trade.postmortem().fill_rate)
    assert result.metadata["paper_trade_postmortem"]["stale_blocked"] is False
    assert "filled" in result.metadata["paper_trade_postmortem"]["notes"]
    assert result.metadata["market_fit_status"] == result.market_fit_status
    assert result.metadata["market_fit_report"]["shadow_eligible"] is True
    assert result.ledger_change is not None
    assert result.ledger_after.cash < result.ledger_before.cash
    assert result.risk_flags == []
    assert result.ledger_after.positions
    assert result.projection_gate_valid is True
    assert result.execution_projection_id == projection.projection_id
    assert result.incident_runbook["runbook_id"] == "shadow_execution_ok"

    shadow_path = store.root / f"{result.shadow_id}.json"
    paper_path = paths.paper_trades_dir / f"{result.paper_trade.trade_id}.json"
    ledger_path = paths.root / "capital_ledger" / f"{result.ledger_after.snapshot_id}.json"

    assert shadow_path.exists()
    assert paper_path.exists()
    assert ledger_path.exists()

    loaded = store.load(result.shadow_id)
    assert loaded.shadow_id == result.shadow_id
    assert loaded.paper_trade is not None
    assert loaded.paper_trade.trade_id == result.paper_trade.trade_id
    assert loaded.ledger_after.cash == pytest.approx(result.ledger_after.cash)

    loaded_paper_trade = PaperTradeStore(paths=paths).load(result.paper_trade.trade_id)
    loaded_ledger = CapitalLedgerStore(base_dir=paths.root).load_snapshot(result.ledger_after.snapshot_id)
    assert loaded_paper_trade.trade_id == result.paper_trade.trade_id
    assert loaded_ledger.snapshot_id == result.ledger_after.snapshot_id


def test_shadow_execution_blocks_when_market_fit_fails_and_logs_incident(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    projection = _projection(run_id="shadow-run")
    projection.persist(paths.run_dir("shadow-run") / "execution_projection.json")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths=paths)

    result = engine.run(
        _recommendation(
            action=DecisionAction.bet,
            side=TradeSide.yes,
            confidence=0.9,
            price_reference=0.45,
        ),
        _shadow_mismatch_snapshot(),
        persist=True,
        store=store,
    )

    assert result.would_trade is False
    assert result.blocked_reason == "shadow simulator does not match market"
    assert result.projection_gate_valid is True
    assert result.slippage_fit_status == "no_liquidity"
    assert result.microstructure_fit_status == "rejected"
    assert result.market_fit_status == "mismatch"
    assert result.market_fit_score == 0.0
    assert "no_liquidity" in result.market_fit_reasons
    assert "rejected" in result.market_fit_reasons
    assert "market_fit_mismatch" in result.risk_flags
    assert result.incident_runbook["runbook_id"] == "shadow_execution_market_fit_mismatch"
    assert "shadow_simulator_market_fit_mismatch" in result.incident_alerts
    assert result.ledger_before == result.ledger_after
    assert result.paper_trade is None
    assert result.market_fit_report is not None
    assert result.market_fit_report["shadow_eligible"] is False
    assert result.metadata["market_fit_status"] == "mismatch"
    assert result.metadata["market_fit_report"]["shadow_eligible"] is False
    assert (store.incident_root).exists()
    assert list(store.incident_root.glob("*.json"))


def test_shadow_execution_blocks_on_stale_projection_and_logs_incident(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    projection = _projection(run_id="shadow-run", stale=True)
    projection.persist(paths.run_dir("shadow-run") / "execution_projection.json")
    engine = ShadowExecutionEngine(starting_cash=500.0, default_stake=10.0)
    store = ShadowExecutionStore(paths=paths)

    result = engine.run(
        _recommendation(action=DecisionAction.bet, side=TradeSide.yes, confidence=0.9),
        _shadow_snapshot(),
        persist=True,
        store=store,
    )

    assert result.would_trade is False
    assert result.projection_gate_valid is False
    assert "execution_projection_stale" in result.risk_flags
    assert "stale_data" in result.incident_alerts
    assert result.incident_runbook["runbook_id"] == "shadow_execution_projection_stale"
    loaded_incident = next(store.incident_root.glob("*.json"))
    assert loaded_incident.exists()
