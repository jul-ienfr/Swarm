from __future__ import annotations

from pathlib import Path

from prediction_markets import (
    DecisionAction,
    MarketAdvisor,
    MarketReplayRunner,
    PolymarketAdapter,
    PredictionMarketPaths,
    ResolutionGuard,
    ResolutionStatus,
)


def test_resolution_guard_flags_missing_resolution_source() -> None:
    adapter = PolymarketAdapter(backend_mode="surrogate")
    market = adapter.get_market("polymarket-ambiguous-geo-event")
    report = ResolutionGuard().evaluate(market, policy=adapter.get_resolution_policy(market.market_id))

    assert report.can_forecast is False
    assert "ambiguous_entity" in report.ambiguity_flags
    assert report.status in {ResolutionStatus.ambiguous, ResolutionStatus.manual_review}


def test_polymarket_surrogate_client_lists_and_fetches_markets() -> None:
    client = PolymarketAdapter(backend_mode="surrogate")

    markets = client.list_markets()
    descriptor = client.get_market("polymarket-fed-cut-q3-2026")
    snapshot = client.get_snapshot(descriptor.market_id)

    assert markets
    assert descriptor.market_id == "polymarket-fed-cut-q3-2026"
    assert snapshot.market_implied_probability is not None
    assert snapshot.question == descriptor.question


def test_prediction_market_advisor_persists_and_replays(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    run = advisor.advise(
        "polymarket-fed-cut-q3-2026",
        evidence_notes=["Polling trend improved this week."],
        persist=True,
    )

    assert run.forecast.market_id == "polymarket-fed-cut-q3-2026"
    assert run.recommendation.action in {
        DecisionAction.bet,
        DecisionAction.wait,
        DecisionAction.no_trade,
        DecisionAction.manual_review,
    }

    replay = MarketReplayRunner(advisor=advisor, paths=paths).replay(run.run_id)
    assert replay.same_forecast is True
    assert replay.same_recommendation is True
    assert replay.same_decision is True


def test_prediction_market_paper_trade_creates_record(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    advisor = MarketAdvisor(paths=paths, backend_mode="surrogate")

    payload = advisor.paper_trade(
        "polymarket-fed-cut-q3-2026",
        evidence_notes=["Short note."],
        stake=25.0,
        persist=True,
    )

    assert payload["paper_trade"]["size"] == 25.0
    assert payload["paper_trade"]["market_id"] == "polymarket-fed-cut-q3-2026"
    assert (paths.paper_trades_dir / f"{payload['paper_trade']['trade_id']}.json").exists()
