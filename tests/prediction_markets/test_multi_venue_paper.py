from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.cross_venue import CrossVenueIntelligenceReport
from prediction_markets.cross_venue import CrossVenueTaxonomy
from prediction_markets.models import MarketDescriptor, MarketOrderBook, MarketSnapshot, MarketStatus, OrderBookLevel, VenueName, VenueType
from prediction_markets.multi_venue_executor import MultiVenueExecutionPlan, MultiVenueExecutionReport
from prediction_markets.multi_venue_paper import MultiVenuePaperReport, build_multi_venue_paper_report


def _market(
    market_id: str,
    *,
    venue: VenueName,
    canonical_event_id: str,
    resolution_source_url: str,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=VenueType.execution,
        title="Macro market",
        question="Will the macro condition hold?",
        canonical_event_id=canonical_event_id,
        resolution_source_url=resolution_source_url,
        end_date=datetime(2026, 4, 9, tzinfo=timezone.utc),
        liquidity=25_000.0,
        status=MarketStatus.open,
        metadata={
            "currency": "USD",
            "payout_currency": "USD",
            "collateral_currency": "USD",
        },
    )


def _snapshot(
    market_id: str,
    *,
    venue: VenueName,
    price_yes: float,
    ask_price: float | None = None,
    bid_price: float | None = None,
) -> MarketSnapshot:
    asks = [OrderBookLevel(price=ask_price or round(price_yes + 0.01, 4), size=10_000.0)]
    bids = [OrderBookLevel(price=bid_price or round(price_yes - 0.01, 4), size=10_000.0)]
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        title="Macro market",
        question="Will the macro condition hold?",
        status=MarketStatus.open,
        price_yes=price_yes,
        price_no=round(1.0 - price_yes, 6),
        midpoint_yes=price_yes,
        market_implied_probability=price_yes,
        liquidity=25_000.0,
        orderbook=MarketOrderBook(bids=bids, asks=asks),
        observed_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )


def test_multi_venue_paper_report_simulates_tradeable_and_manual_review_plans() -> None:
    markets = [
        _market("pm_trade", venue=VenueName.polymarket, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("k_trade", venue=VenueName.kalshi, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("m_ref_trade", venue=VenueName.metaculus, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
    ]
    execution_report = MultiVenueExecutionReport(
        cross_venue_report=CrossVenueIntelligenceReport(),
        market_count=3,
        plans=[
            MultiVenueExecutionPlan(
                candidate_id="manual_candidate",
                comparison_id="manual_comparison",
                canonical_event_id="event_trade",
                market_ids=["pm_trade", "k_trade"],
                execution_market_ids=["pm_trade", "k_trade"],
                route="manual_review",
                tradeable=False,
                manual_review_required=True,
                taxonomy=CrossVenueTaxonomy.cross_venue_signal,
                execution_filter_reason_codes=["execution_like_venue", "manual_review_required"],
                rationale="manual_review_multi_venue_paper",
            )
        ],
    )

    paper_report = build_multi_venue_paper_report(
        markets,
        execution_report=execution_report,
        snapshots={
            "pm_trade": _snapshot("pm_trade", venue=VenueName.polymarket, price_yes=0.54, ask_price=0.56, bid_price=0.53),
        },
        target_notional_usd=1500.0,
    )

    assert isinstance(paper_report, MultiVenuePaperReport)
    assert paper_report.market_count == 3
    assert paper_report.surface.plan_count == 1
    assert paper_report.surface.tradeable_plan_count == 0
    assert paper_report.surface.manual_review_plan_count == 1
    assert paper_report.surface.simulated_plan_count == 1
    assert paper_report.surface.legging_risk_count == 1
    assert paper_report.surface.cross_venue_signal_plan_count == 1
    assert paper_report.surface.true_arbitrage_plan_count == 0
    assert paper_report.surface.execution_filter_reason_codes == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert paper_report.surface.execution_filter_reason_code_counts == {
        "execution_like_venue": 1,
        "manual_review_required": 1,
    }
    assert paper_report.surface.rejected_leg_rate >= 0.0
    assert paper_report.surface.missing_snapshot_leg_count == 1
    assert paper_report.surface.covered_leg_count == 1
    assert paper_report.surface.no_trade_leg_count == 1
    assert paper_report.surface.no_trade_leg_rate == pytest.approx(0.5)
    assert paper_report.surface.total_fees_usd > 0.0
    assert paper_report.surface.total_allocated_notional_usd > 0.0
    assert paper_report.surface.fill_rate >= 0.0
    assert paper_report.surface.partial_fill_rate >= 0.0
    assert paper_report.surface.stale_block_rate == pytest.approx(0.0)
    assert paper_report.surface.hedge_completion_rate >= 0.0
    assert paper_report.surface.legging_loss_usd >= 0.0
    assert paper_report.surface.spread_mean_bps is not None
    assert paper_report.surface.net_pnl_usd == paper_report.net_pnl_usd
    assert set(paper_report.surface.paper_status_counts).issuperset({"filled"})

    plan = paper_report.plan_results[0]

    assert plan.paper_simulated is True
    assert plan.manual_review_required is True
    assert plan.taxonomy == CrossVenueTaxonomy.cross_venue_signal
    assert plan.execution_filter_reason_codes == ["execution_like_venue", "manual_review_required"]
    assert plan.snapshot_coverage == 0.5
    assert plan.legging_risk is True
    assert set(plan.legging_risk_reasons).issuperset({"snapshot_missing", "manual_review_required"})
    assert len(plan.legs) == 2
    assert sum(1 for leg in plan.legs if leg.snapshot_available) == 1
    assert sum(1 for leg in plan.legs if leg.paper_trade_status.value == "skipped") == 1
    assert sum(1 for leg in plan.legs if leg.paper_trade_status.value in {"filled", "partial"}) == 1
    assert plan.gross_pnl_usd != 0.0 or plan.net_pnl_usd != 0.0
    assert plan.fill_rate >= 0.0
    assert plan.partial_fill_rate >= 0.0
    assert plan.stale_block_rate == pytest.approx(0.0)
    assert plan.legs[1].paper_trade is not None
    assert plan.legs[1].paper_trade.postmortem().no_trade_zone is True
    assert plan.hedge_completion_rate >= 0.0
    assert plan.legging_loss_usd >= 0.0
    assert plan.legs[0].spread_bps is not None or plan.legs[1].spread_bps is not None


def test_multi_venue_paper_report_roundtrips_persistence(tmp_path: Path) -> None:
    markets = [
        _market("pm_trade", venue=VenueName.polymarket, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("k_trade", venue=VenueName.kalshi, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("m_ref_trade", venue=VenueName.metaculus, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
    ]
    execution_report = MultiVenueExecutionReport(
        cross_venue_report=CrossVenueIntelligenceReport(),
        market_count=3,
        plans=[
            MultiVenueExecutionPlan(
                candidate_id="manual_candidate",
                comparison_id="manual_comparison",
                canonical_event_id="event_trade",
                market_ids=["pm_trade", "k_trade"],
                execution_market_ids=["pm_trade", "k_trade"],
                route="manual_review",
                tradeable=False,
                manual_review_required=True,
                taxonomy=CrossVenueTaxonomy.cross_venue_signal,
                execution_filter_reason_codes=["execution_like_venue"],
                rationale="manual_review_multi_venue_paper",
            )
        ],
    )
    report = build_multi_venue_paper_report(
        markets,
        execution_report=execution_report,
        snapshots={
            "pm_trade": _snapshot("pm_trade", venue=VenueName.polymarket, price_yes=0.54, ask_price=0.56, bid_price=0.53),
            "k_trade": _snapshot("k_trade", venue=VenueName.kalshi, price_yes=0.55, ask_price=0.56, bid_price=0.54),
        },
        target_notional_usd=500.0,
    )

    persisted = report.persist(tmp_path / "paper_report.json")
    loaded = MultiVenuePaperReport.load(persisted)

    assert persisted.exists()
    assert loaded.content_hash == report.content_hash
    assert loaded.report_id == report.report_id
    assert loaded.surface.total_fees_usd == report.surface.total_fees_usd
    assert loaded.surface.cross_venue_signal_plan_count == report.surface.cross_venue_signal_plan_count == 1
    assert loaded.surface.execution_filter_reason_codes == report.surface.execution_filter_reason_codes == ["execution_like_venue"]
    assert loaded.plan_results[0].content_hash == report.plan_results[0].content_hash
    assert loaded.plan_results[0].taxonomy == report.plan_results[0].taxonomy == CrossVenueTaxonomy.cross_venue_signal


def test_multi_venue_paper_report_marks_missing_snapshot_leg_as_skipped() -> None:
    execution_report = MultiVenueExecutionReport(
        cross_venue_report=CrossVenueIntelligenceReport(),
        market_count=2,
        plans=[
            MultiVenueExecutionPlan(
                candidate_id="manual_candidate",
                comparison_id="manual_comparison",
                canonical_event_id="manual_event",
                market_ids=["pm_leg", "k_leg"],
                execution_market_ids=["pm_leg", "k_leg"],
                route="manual_review",
                tradeable=False,
                manual_review_required=True,
                taxonomy=CrossVenueTaxonomy.cross_venue_signal,
                execution_filter_reason_codes=["manual_review_required"],
                rationale="manual_review_multi_venue_paper",
            )
        ],
    )
    report = build_multi_venue_paper_report(
        execution_report=execution_report,
        snapshots={
            "pm_leg": _snapshot("pm_leg", venue=VenueName.polymarket, price_yes=0.55, ask_price=0.56, bid_price=0.54),
        },
        target_notional_usd=250.0,
    )

    assert report.plan_count == 1
    assert report.surface.missing_snapshot_leg_count == 1
    assert report.surface.covered_leg_count == 1
    assert report.surface.no_trade_leg_count == 1
    assert report.surface.no_trade_leg_rate == pytest.approx(0.5)
    assert report.surface.paper_status_counts["filled"] == 1
    assert report.surface.paper_status_counts["skipped"] == 1
    assert report.plan_results[0].snapshot_coverage == 0.5
    assert report.plan_results[0].legging_risk is True
    assert set(report.plan_results[0].legging_risk_reasons).issuperset({"snapshot_missing", "manual_review_required"})


def test_multi_venue_paper_report_surfaces_stale_blocks_and_persist_roundtrip(tmp_path: Path) -> None:
    markets = [
        _market("pm_trade", venue=VenueName.polymarket, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("k_trade", venue=VenueName.kalshi, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
        _market("m_ref_trade", venue=VenueName.metaculus, canonical_event_id="event_trade", resolution_source_url="https://example.com/resolution"),
    ]
    execution_report = MultiVenueExecutionReport(
        cross_venue_report=CrossVenueIntelligenceReport(),
        market_count=3,
        plans=[
            MultiVenueExecutionPlan(
                candidate_id="manual_candidate",
                comparison_id="manual_comparison",
                canonical_event_id="event_trade",
                market_ids=["pm_trade", "k_trade"],
                execution_market_ids=["pm_trade", "k_trade"],
                route="manual_review",
                tradeable=False,
                manual_review_required=True,
                rationale="manual_review_multi_venue_paper",
            )
        ],
    )
    report = build_multi_venue_paper_report(
        markets,
        execution_report=execution_report,
        snapshots={
            "pm_trade": _snapshot("pm_trade", venue=VenueName.polymarket, price_yes=0.54, ask_price=0.56, bid_price=0.53),
            "k_trade": _snapshot("k_trade", venue=VenueName.kalshi, price_yes=0.55, ask_price=0.56, bid_price=0.54).model_copy(update={"staleness_ms": 240_000}),
        },
        target_notional_usd=1000.0,
    )

    persisted = report.persist(tmp_path / "multi_venue_paper_report.json")
    loaded = MultiVenuePaperReport.load(persisted)

    assert report.plan_count == 1
    assert report.surface.stale_block_count == 1
    assert report.surface.stale_block_rate == pytest.approx(0.5)
    assert report.surface.no_trade_leg_count == 1
    assert report.surface.no_trade_leg_rate == pytest.approx(0.5)
    assert report.plan_results[0].stale_block_count == 1
    assert report.plan_results[0].stale_block_rate == pytest.approx(0.5)
    assert report.plan_results[0].fill_rate < 1.0
    assert report.plan_results[0].partial_fill_rate == pytest.approx(0.0)
    assert report.plan_results[0].legging_loss_usd >= 0.0
    assert report.surface.hedge_completion_rate == pytest.approx(report.plan_results[0].hedge_completion_rate)
    assert loaded.surface.stale_block_rate == pytest.approx(report.surface.stale_block_rate)
    assert loaded.content_hash == report.content_hash
