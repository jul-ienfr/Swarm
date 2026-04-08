from __future__ import annotations

from prediction_markets.arbitrage_lab import ArbitrageLab, ArbitrageTaxonomy, ArbitrageVerdict, assess_arbitrage
from prediction_markets.models import (
    CrossVenueMatch,
    MarketDescriptor,
    MarketOrderBook,
    MarketSnapshot,
    MarketStatus,
    OrderBookLevel,
    VenueName,
    VenueType,
)


def _market(
    market_id: str,
    *,
    venue: VenueName,
    question: str,
    canonical_event_id: str,
    venue_type: VenueType = VenueType.execution,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=question,
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
    bid: float,
    ask: float,
    bid_size: float = 30.0,
    ask_size: float = 30.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        title=market_id,
        question="Will arbitrage lab classify correctly?",
        status=MarketStatus.open,
        price_yes=price_yes,
        price_no=round(1.0 - price_yes, 6),
        midpoint_yes=price_yes,
        liquidity=50_000.0,
        orderbook=MarketOrderBook(
            bids=[OrderBookLevel(price=bid, size=bid_size)],
            asks=[OrderBookLevel(price=ask, size=ask_size)],
        ),
    )


def test_assess_arbitrage_returns_executable_candidate_for_strong_spread() -> None:
    markets = [
        _market("pm_left", venue=VenueName.polymarket, question="Will rates be cut?", canonical_event_id="rates_cut"),
        _market(
            "k_right",
            venue=VenueName.kalshi,
            question="Will rates be cut?",
            canonical_event_id="rates_cut",
            venue_type=VenueType.reference,
        ),
    ]
    snapshots = {
        "pm_left": _snapshot("pm_left", venue=VenueName.polymarket, price_yes=0.42, bid=0.41, ask=0.43),
        "k_right": _snapshot("k_right", venue=VenueName.kalshi, price_yes=0.58, bid=0.57, ask=0.59),
    }
    matches = [
        CrossVenueMatch(
            canonical_event_id="rates_cut",
            left_market_id="pm_left",
            right_market_id="k_right",
            left_venue=VenueName.polymarket,
            right_venue=VenueName.kalshi,
            similarity=0.98,
            compatible_resolution=True,
            manual_review_required=False,
            rationale="same question",
        )
    ]

    report = assess_arbitrage(markets, snapshots=snapshots, matches=matches, lab=ArbitrageLab(probe_quantity=5.0, fee_bps=0.0))

    assert report.executable_count == 1
    assert report.legging_risk_count == 1
    assert report.hedge_completion_ready_count == 1
    assert report.average_hedge_completion_ratio > 0.0
    assert report.spread_capture_rate == 1.0
    assert report.true_arbitrage_taxonomy_count == 1
    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.executable_candidate
    assert assessment.execution_ready is True
    assert assessment.taxonomy == ArbitrageTaxonomy.true_arbitrage
    assert assessment.execution_filter_reason_codes == []
    assert assessment.plan is not None
    assert assessment.plan.net_edge_bps > 0
    assert assessment.plan.taxonomy == ArbitrageTaxonomy.true_arbitrage
    assert assessment.plan.execution_filter_reason_codes == []
    assert assessment.comparison_state in {"executable_candidate", "spread_alert"}
    assert hasattr(assessment.plan, "comparable_group_id")
    assert assessment.legging_risk is True
    assert assessment.hedge_completion_ratio > 0.0
    assert "unhedged_leg_window:2500" in assessment.legging_risk_reasons


def test_arbitrage_lab_downgrades_to_signal_when_leg_reports_are_weak() -> None:
    markets = [
        _market("pm_left", venue=VenueName.polymarket, question="Will BTC rise?", canonical_event_id="btc_rise"),
        _market(
            "m_right",
            venue=VenueName.metaculus,
            question="Will BTC rise?",
            canonical_event_id="btc_rise",
            venue_type=VenueType.reference,
        ),
    ]
    snapshots = {
        "pm_left": _snapshot("pm_left", venue=VenueName.polymarket, price_yes=0.43, bid=0.42, ask=0.44, bid_size=1.0, ask_size=1.0),
        "m_right": _snapshot("m_right", venue=VenueName.metaculus, price_yes=0.58, bid=0.57, ask=0.59, bid_size=1.0, ask_size=1.0),
    }
    matches = [
        CrossVenueMatch(
            canonical_event_id="btc_rise",
            left_market_id="pm_left",
            right_market_id="m_right",
            left_venue=VenueName.polymarket,
            right_venue=VenueName.metaculus,
            similarity=0.95,
            compatible_resolution=True,
            manual_review_required=False,
            rationale="same question",
        )
    ]

    report = assess_arbitrage(markets, snapshots=snapshots, matches=matches, lab=ArbitrageLab(probe_quantity=5.0, fee_bps=0.0))

    assert report.signal_count == 1
    assert report.spread_capture_rate == 0.0
    assert report.relative_value_taxonomy_count == 1
    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.signal_only
    assert assessment.execution_ready is False
    assert assessment.taxonomy == ArbitrageTaxonomy.relative_value
    assert assessment.plan is not None
    assert "insufficient_liquidity" in assessment.reason_codes or "net_edge_below_threshold" in assessment.reason_codes
    assert assessment.narrative_risk_flags is not None
    assert assessment.legging_risk is True
    assert assessment.hedge_completion_ratio < 1.0
    assert "hedge_completion_incomplete" in assessment.legging_risk_reasons or "hedge_completion_below_threshold" in assessment.legging_risk_reasons


def test_arbitrage_lab_classifies_shallow_execution_pairs_as_relative_value() -> None:
    markets = [
        _market("pm_left", venue=VenueName.polymarket, question="Will rates be cut?", canonical_event_id="rates_cut"),
        _market(
            "k_right",
            venue=VenueName.kalshi,
            question="Will rates be cut?",
            canonical_event_id="rates_cut",
            venue_type=VenueType.execution,
        ),
    ]
    snapshots = {
        "pm_left": _snapshot("pm_left", venue=VenueName.polymarket, price_yes=0.43, bid=0.42, ask=0.44, bid_size=1.0, ask_size=1.0),
        "k_right": _snapshot("k_right", venue=VenueName.kalshi, price_yes=0.58, bid=0.57, ask=0.59, bid_size=1.0, ask_size=1.0),
    }
    matches = [
        CrossVenueMatch(
            canonical_event_id="rates_cut",
            left_market_id="pm_left",
            right_market_id="k_right",
            left_venue=VenueName.polymarket,
            right_venue=VenueName.kalshi,
            similarity=0.98,
            compatible_resolution=True,
            manual_review_required=False,
            rationale="same question",
        )
    ]

    report = assess_arbitrage(markets, snapshots=snapshots, matches=matches, lab=ArbitrageLab(probe_quantity=5.0, fee_bps=0.0))

    assert report.relative_value_taxonomy_count == 1
    assert report.cross_venue_signal_taxonomy_count == 0
    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.signal_only
    assert assessment.execution_ready is False
    assert assessment.taxonomy == ArbitrageTaxonomy.relative_value
    assert assessment.plan is not None
    assert assessment.plan.taxonomy == ArbitrageTaxonomy.relative_value
    assert {"partial_fill", "hedge_completion_incomplete", "hedge_completion_below_threshold"} & set(assessment.reason_codes)
    assert assessment.legging_risk is True


def test_arbitrage_lab_counts_invalidated_arbitrage_when_net_edge_breaks_threshold() -> None:
    markets = [
        _market("pm_left", venue=VenueName.polymarket, question="Will energy prices rise?", canonical_event_id="energy_rise"),
        _market(
            "k_right",
            venue=VenueName.kalshi,
            question="Will energy prices rise?",
            canonical_event_id="energy_rise",
            venue_type=VenueType.reference,
        ),
    ]
    snapshots = {
        "pm_left": _snapshot("pm_left", venue=VenueName.polymarket, price_yes=0.45, bid=0.44, ask=0.46, bid_size=50.0, ask_size=50.0),
        "k_right": _snapshot("k_right", venue=VenueName.kalshi, price_yes=0.55, bid=0.54, ask=0.56, bid_size=50.0, ask_size=50.0),
    }
    matches = [
        CrossVenueMatch(
            canonical_event_id="energy_rise",
            left_market_id="pm_left",
            right_market_id="k_right",
            left_venue=VenueName.polymarket,
            right_venue=VenueName.kalshi,
            similarity=0.98,
            compatible_resolution=True,
            manual_review_required=False,
            rationale="same question",
        )
    ]

    report = assess_arbitrage(
        markets,
        snapshots=snapshots,
        matches=matches,
        lab=ArbitrageLab(probe_quantity=5.0, fee_bps=0.0, min_net_edge_bps=2000.0),
    )

    assert report.detected_arbitrage_count == 1
    assert report.invalidated_arbitrage_count == 1
    assert report.invalidated_arbitrage_rate == 1.0
    assert report.spread_capture_rate == 0.0
    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.signal_only
    assert assessment.execution_ready is False
    assert assessment.taxonomy == ArbitrageTaxonomy.relative_value
    assert "net_edge_below_threshold" in assessment.reason_codes


def test_arbitrage_lab_demotes_execution_like_venues_to_manual_review() -> None:
    markets = [
        _market("rh_left", venue=VenueName.robinhood, question="Will AI beats human?", canonical_event_id="ai_beats"),
        _market(
            "pm_right",
            venue=VenueName.polymarket,
            question="Will AI beats human?",
            canonical_event_id="ai_beats",
            venue_type=VenueType.reference,
        ),
    ]
    snapshots = {
        "rh_left": _snapshot("rh_left", venue=VenueName.robinhood, price_yes=0.40, bid=0.39, ask=0.41, bid_size=20.0, ask_size=20.0),
        "pm_right": _snapshot("pm_right", venue=VenueName.polymarket, price_yes=0.60, bid=0.59, ask=0.61, bid_size=20.0, ask_size=20.0),
    }
    matches = [
        CrossVenueMatch(
            canonical_event_id="ai_beats",
            left_market_id="rh_left",
            right_market_id="pm_right",
            left_venue=VenueName.robinhood,
            right_venue=VenueName.polymarket,
            similarity=0.96,
            compatible_resolution=True,
            manual_review_required=False,
            rationale="same question",
        )
    ]

    report = assess_arbitrage(markets, snapshots=snapshots, matches=matches, lab=ArbitrageLab(probe_quantity=5.0, fee_bps=0.0))

    assert report.signal_count == 1
    assert report.executable_count == 0
    assert report.manual_review_count == 1
    assert report.cross_venue_signal_taxonomy_count == 1
    assessment = report.assessments[0]
    assert assessment.verdict == ArbitrageVerdict.signal_only
    assert assessment.execution_ready is False
    assert assessment.taxonomy == ArbitrageTaxonomy.cross_venue_signal
    assert "execution_like_venue" in assessment.reason_codes
    assert assessment.legging_risk is True
    assert "execution_like_venue" in assessment.legging_risk_reasons
    assert assessment.plan is not None
    assert "execution_like_venue" in assessment.plan.reason_codes
    assert assessment.plan.taxonomy == ArbitrageTaxonomy.cross_venue_signal
    assert "execution_like_venue" in assessment.plan.execution_filter_reason_codes
