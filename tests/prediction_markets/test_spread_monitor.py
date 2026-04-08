from __future__ import annotations

from prediction_markets.models import (
    CrossVenueMatch,
    MarketDescriptor,
    MarketOrderBook,
    MarketSnapshot,
    MarketStatus,
    OrderBookLevel,
    TradeSide,
    VenueName,
    VenueType,
)
from prediction_markets.arbitrage_lab import ArbitrageLab, ArbitrageVerdict
from prediction_markets.spread_monitor import SpreadMonitor, SpreadOpportunityClass, SpreadOpportunityDirection


def _market(
    market_id: str,
    *,
    venue: VenueName,
    title: str,
    question: str,
    canonical_event_id: str,
    venue_type: VenueType = VenueType.execution,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=title,
        question=question,
        canonical_event_id=canonical_event_id,
        resolution_source="https://example.com/resolution",
        liquidity=50_000.0,
        status=MarketStatus.open,
    )


def _snapshot(
    market_id: str,
    *,
    venue: VenueName,
    price_yes: float,
    orderbook: MarketOrderBook | None,
    liquidity: float = 50_000.0,
    staleness_ms: int = 0,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        title=market_id,
        question="Will the cross venue spread monitor work?",
        status=MarketStatus.open,
        price_yes=price_yes,
        price_no=round(1.0 - price_yes, 6),
        midpoint_yes=price_yes,
        liquidity=liquidity,
        staleness_ms=staleness_ms,
        orderbook=orderbook,
    )


def test_spread_monitor_marks_executable_candidates() -> None:
    left = _market(
        "pm_left",
        venue=VenueName.polymarket,
        title="Will the Fed cut by Q3?",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
    )
    right = _market(
        "k_right",
        venue=VenueName.kalshi,
        title="Will the Fed cut by Q3?",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        venue_type=VenueType.reference,
    )
    left_snapshot = _snapshot(
        "pm_left",
        venue=VenueName.polymarket,
        price_yes=0.42,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.41, size=25.0)],
            asks=[OrderBookLevel(price=0.43, size=30.0), OrderBookLevel(price=0.44, size=30.0)],
        ),
    )
    right_snapshot = _snapshot(
        "k_right",
        venue=VenueName.kalshi,
        price_yes=0.58,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=0.57, size=30.0), OrderBookLevel(price=0.56, size=30.0)],
            asks=[OrderBookLevel(price=0.59, size=25.0)],
        ),
    )
    match = CrossVenueMatch(
        canonical_event_id="fed_q3_2026",
        left_market_id="pm_left",
        right_market_id="k_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.kalshi,
        similarity=0.97,
        compatible_resolution=True,
        manual_review_required=False,
        rationale="explicit test match",
    )

    report = SpreadMonitor(signal_threshold_bps=80.0, executable_threshold_bps=120.0, probe_quantity=5.0).scan(
        [left, right],
        snapshots={"pm_left": left_snapshot, "k_right": right_snapshot},
        matches=[match],
    )

    assert report.executable_count == 1
    assert report.signal_count == 0
    assert report.comparison_count == 0
    assert report.alerts

    opportunity = report.opportunities[0]
    assert opportunity.opportunity_class == SpreadOpportunityClass.executable_candidate
    assert opportunity.direction == SpreadOpportunityDirection.buy_left_sell_right
    assert opportunity.preferred_buy_market_id == "pm_left"
    assert opportunity.preferred_sell_market_id == "k_right"
    assert opportunity.comparison_state.value in {"executable_candidate", "spread_alert"}
    assert opportunity.comparison_summary
    assert opportunity.buy_fill_report is not None
    assert opportunity.sell_fill_report is not None
    assert opportunity.liquidity_supported is True
    assert opportunity.estimated_net_edge_bps is not None
    assert opportunity.estimated_net_edge_bps > 0


def test_spread_monitor_marks_signal_only_when_liquidity_is_insufficient() -> None:
    left = _market(
        "pm_signal_left",
        venue=VenueName.polymarket,
        title="Will BTC be above 120k?",
        question="Will BTC be above 120k?",
        canonical_event_id="btc_120k_2026",
    )
    right = _market(
        "m_signal_right",
        venue=VenueName.metaculus,
        title="Will BTC be above 120k?",
        question="Will BTC be above 120k?",
        canonical_event_id="btc_120k_2026",
        venue_type=VenueType.reference,
    )
    match = CrossVenueMatch(
        canonical_event_id="btc_120k_2026",
        left_market_id="pm_signal_left",
        right_market_id="m_signal_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.metaculus,
        similarity=0.95,
        compatible_resolution=True,
        manual_review_required=False,
        rationale="explicit test match",
    )
    report = SpreadMonitor(signal_threshold_bps=80.0, executable_threshold_bps=120.0, probe_quantity=5.0).scan(
        [left, right],
        snapshots={
            "pm_signal_left": _snapshot(
                "pm_signal_left",
                venue=VenueName.polymarket,
                price_yes=0.42,
                orderbook=MarketOrderBook(bids=[OrderBookLevel(price=0.41, size=1.0)], asks=[OrderBookLevel(price=0.43, size=1.0)]),
            ),
            "m_signal_right": _snapshot(
                "m_signal_right",
                venue=VenueName.metaculus,
                price_yes=0.58,
                orderbook=MarketOrderBook(bids=[OrderBookLevel(price=0.57, size=1.0)], asks=[OrderBookLevel(price=0.59, size=1.0)]),
            ),
        },
        matches=[match],
    )

    opportunity = report.opportunities[0]
    assert opportunity.opportunity_class == SpreadOpportunityClass.signal_only
    assert opportunity.buy_fill_report is not None
    assert opportunity.sell_fill_report is not None
    assert opportunity.liquidity_supported is False
    assert "insufficient_liquidity" in opportunity.reason_codes
    assert opportunity.narrative_risk_flags
    assert report.manual_review_count >= 0


def test_spread_monitor_marks_comparison_only_below_signal_threshold() -> None:
    left = _market(
        "pm_compare_left",
        venue=VenueName.polymarket,
        title="Will the rate stay above 5?",
        question="Will the rate stay above 5?",
        canonical_event_id="rate_5_2026",
    )
    right = _market(
        "m_compare_right",
        venue=VenueName.metaculus,
        title="Will the rate stay above 5?",
        question="Will the rate stay above 5?",
        canonical_event_id="rate_5_2026",
        venue_type=VenueType.reference,
    )
    match = CrossVenueMatch(
        canonical_event_id="rate_5_2026",
        left_market_id="pm_compare_left",
        right_market_id="m_compare_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.metaculus,
        similarity=0.93,
        compatible_resolution=True,
        manual_review_required=False,
        rationale="explicit test match",
    )
    report = SpreadMonitor(signal_threshold_bps=80.0).scan(
        [left, right],
        snapshots={
            "pm_compare_left": _snapshot("pm_compare_left", venue=VenueName.polymarket, price_yes=0.497, orderbook=None),
            "m_compare_right": _snapshot("m_compare_right", venue=VenueName.metaculus, price_yes=0.503, orderbook=None),
        },
        matches=[match],
    )

    opportunity = report.opportunities[0]
    assert opportunity.opportunity_class == SpreadOpportunityClass.comparison_only
    assert "spread_below_signal_threshold" in opportunity.reason_codes
    assert opportunity.preferred_buy_market_id is None or opportunity.preferred_buy_market_id in {"pm_compare_left", "m_compare_right"}
    assert opportunity.comparison_state.value == "comparison_only"
    assert opportunity.comparison_summary


def test_spread_monitor_downgrades_narrative_only_spread_to_signal_only_and_manual_review() -> None:
    left = _market(
        "pm_narrative_left",
        venue=VenueName.polymarket,
        title="Will the merger close this quarter?",
        question="Will the merger close this quarter?",
        canonical_event_id="merger_q2_2026",
    )
    right = _market(
        "k_narrative_right",
        venue=VenueName.kalshi,
        title="Will the merger close this quarter?",
        question="Will the merger close this quarter?",
        canonical_event_id="merger_q2_2026",
        venue_type=VenueType.reference,
    )
    match = CrossVenueMatch(
        canonical_event_id="merger_q2_2026",
        left_market_id="pm_narrative_left",
        right_market_id="k_narrative_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.kalshi,
        similarity=0.53,
        compatible_resolution=True,
        manual_review_required=False,
        rationale="suspicious narrative spread",
    )
    report = SpreadMonitor(signal_threshold_bps=80.0, executable_threshold_bps=120.0, probe_quantity=5.0).scan(
        [left, right],
        snapshots={
            "pm_narrative_left": _snapshot(
                "pm_narrative_left",
                venue=VenueName.polymarket,
                price_yes=0.82,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.81, size=100.0)],
                    asks=[OrderBookLevel(price=0.83, size=100.0)],
                ),
            ),
            "k_narrative_right": _snapshot(
                "k_narrative_right",
                venue=VenueName.kalshi,
                price_yes=0.18,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.17, size=100.0)],
                    asks=[OrderBookLevel(price=0.19, size=100.0)],
                ),
            ),
        },
        matches=[match],
    )

    opportunity = report.opportunities[0]
    assert report.signal_count == 1
    assert report.executable_count == 0
    assert report.manual_review_count == 1
    assert opportunity.opportunity_class == SpreadOpportunityClass.signal_only
    assert opportunity.manual_review_required is True
    assert opportunity.comparison_state.value == "manual_review"
    assert "narrative_spread_only" in opportunity.reason_codes
    assert "narrative_only" in opportunity.narrative_risk_flags


def test_spread_monitor_forces_manual_review_when_match_requires_it() -> None:
    left = _market(
        "pm_review_left",
        venue=VenueName.polymarket,
        title="Will the policy pass this week?",
        question="Will the policy pass this week?",
        canonical_event_id="policy_week_2026",
    )
    right = _market(
        "m_review_right",
        venue=VenueName.metaculus,
        title="Will the policy pass this week?",
        question="Will the policy pass this week?",
        canonical_event_id="policy_week_2026",
        venue_type=VenueType.reference,
    )
    match = CrossVenueMatch(
        canonical_event_id="policy_week_2026",
        left_market_id="pm_review_left",
        right_market_id="m_review_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.metaculus,
        similarity=0.96,
        compatible_resolution=True,
        manual_review_required=True,
        rationale="explicit manual review test",
    )
    report = SpreadMonitor(signal_threshold_bps=80.0, executable_threshold_bps=120.0, probe_quantity=5.0).scan(
        [left, right],
        snapshots={
            "pm_review_left": _snapshot(
                "pm_review_left",
                venue=VenueName.polymarket,
                price_yes=0.78,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.77, size=100.0)],
                    asks=[OrderBookLevel(price=0.79, size=100.0)],
                ),
            ),
            "m_review_right": _snapshot(
                "m_review_right",
                venue=VenueName.metaculus,
                price_yes=0.22,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.21, size=100.0)],
                    asks=[OrderBookLevel(price=0.23, size=100.0)],
                ),
            ),
        },
        matches=[match],
    )

    opportunity = report.opportunities[0]
    assert report.manual_review_count == 1
    assert opportunity.opportunity_class == SpreadOpportunityClass.signal_only
    assert opportunity.manual_review_required is True
    assert opportunity.comparison_state.value == "manual_review"
    assert "manual_review_required" in opportunity.reason_codes
    assert "narrative_spread_only" not in opportunity.reason_codes
    assert report.executable_count == 0


def test_arbitrage_lab_downgrades_narrative_only_spread_to_signal_only() -> None:
    left = _market(
        "pm_arb_left",
        venue=VenueName.polymarket,
        title="Will the merger close this quarter?",
        question="Will the merger close this quarter?",
        canonical_event_id="merger_q2_2026",
    )
    right = _market(
        "k_arb_right",
        venue=VenueName.kalshi,
        title="Will the merger close this quarter?",
        question="Will the merger close this quarter?",
        canonical_event_id="merger_q2_2026",
        venue_type=VenueType.reference,
    )
    match = CrossVenueMatch(
        canonical_event_id="merger_q2_2026",
        left_market_id="pm_arb_left",
        right_market_id="k_arb_right",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.kalshi,
        similarity=0.53,
        compatible_resolution=True,
        manual_review_required=False,
        rationale="suspicious narrative spread",
    )
    report = ArbitrageLab(min_net_edge_bps=1.0, probe_quantity=5.0).assess(
        [left, right],
        snapshots={
            "pm_arb_left": _snapshot(
                "pm_arb_left",
                venue=VenueName.polymarket,
                price_yes=0.82,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.81, size=100.0)],
                    asks=[OrderBookLevel(price=0.83, size=100.0)],
                ),
            ),
            "k_arb_right": _snapshot(
                "k_arb_right",
                venue=VenueName.kalshi,
                price_yes=0.18,
                orderbook=MarketOrderBook(
                    bids=[OrderBookLevel(price=0.17, size=100.0)],
                    asks=[OrderBookLevel(price=0.19, size=100.0)],
                ),
            ),
        },
        matches=[match],
    )

    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.signal_only
    assert assessment.execution_ready is False
    assert "narrative_spread_only" in assessment.reason_codes
    assert assessment.comparison_state == "manual_review"
