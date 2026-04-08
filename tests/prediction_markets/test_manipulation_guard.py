from __future__ import annotations

from prediction_markets.manipulation_guard import ManipulationGuard, ManipulationGuardSeverity
from prediction_markets.market_comment_intel import (
    CommentSentimentLabel,
    CommentSentimentSummary,
    MarketCommentIntelReport,
    NarrativeSignal,
)
from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType
from prediction_markets.streaming import MarketStreamHealth, MarketStreamSummary


def _market(*, market_id: str, liquidity: float = 50_000.0, source_url: str = "https://example.com/market") -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        resolution_source="https://example.com/resolution",
        source_url=source_url,
        liquidity=liquidity,
    )


def _snapshot(
    market_id: str,
    *,
    liquidity: float = 50_000.0,
    spread_bps: float = 90.0,
    staleness_ms: int = 1_000,
    implied_probability: float = 0.51,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title=f"Market {market_id}",
        question=f"Question {market_id}",
        status=MarketStatus.open,
        liquidity=liquidity,
        spread_bps=spread_bps,
        staleness_ms=staleness_ms,
        market_implied_probability=implied_probability,
        price_yes=implied_probability,
        price_no=round(1.0 - implied_probability, 6),
        midpoint_yes=implied_probability,
    )


def _report(
    *,
    market_id: str,
    comment_count: int,
    author_count: int,
    label: CommentSentimentLabel,
    score: float,
    confidence: float,
    bullish_share: float,
    bearish_share: float,
    neutral_share: float,
    dominant_strength: float,
    counter_narratives: list[NarrativeSignal] | None = None,
) -> MarketCommentIntelReport:
    return MarketCommentIntelReport(
        market_id=market_id,
        venue=VenueName.polymarket,
        market_title=f"Market {market_id}",
        market_question=f"Question {market_id}",
        comment_count=comment_count,
        author_count=author_count,
        source_kind_counts={"social": comment_count},
        sentiment=CommentSentimentSummary(
            score=score,
            label=label,
            confidence=confidence,
            bullish_comment_share=bullish_share,
            bearish_comment_share=bearish_share,
            neutral_comment_share=neutral_share,
            positive_term_hits=4,
            negative_term_hits=1,
            representative_terms=["signal", "market"],
            signal_notes=["deterministic"],
        ),
        dominant_narrative=NarrativeSignal(
            direction=label,
            title=f"{label.value} narrative",
            summary="narrative",
            strength=dominant_strength,
            keywords=["signal", "market"],
            comment_ids=[f"c{i}" for i in range(comment_count)],
        ),
        counter_narratives=counter_narratives or [],
        top_terms=["signal", "market"],
        narrative_summary="deterministic narrative summary",
        comment_ids=[f"c{i}" for i in range(comment_count)],
        sample_comments=[f"comment {i}" for i in range(min(3, comment_count))],
    )


def _stream_summary(
    *,
    stream_id: str,
    market_id: str,
    trend: str,
    event_count: int,
    change_rate: float,
) -> MarketStreamSummary:
    return MarketStreamSummary(
        stream_id=stream_id,
        market_id=market_id,
        venue=VenueName.polymarket,
        market_title=f"Market {market_id}",
        event_count=event_count,
        poll_count=event_count,
        change_event_count=max(0, event_count - 1),
        change_rate=change_rate,
        latest_sequence=event_count,
        price_yes_start=0.5,
        price_yes_end=0.5,
        price_yes_change=0.0,
        spread_bps_start=90.0,
        spread_bps_end=90.0,
        spread_bps_change=0.0,
        average_price_yes=0.5,
        average_spread_bps=90.0,
        trend=trend,
        narrative=f"{trend} stream",
        changed_field_counts={"price_yes": max(0, event_count - 1)},
    )


def test_manipulation_guard_allows_clean_market_context() -> None:
    market = _market(market_id="pm_guard_clean")
    snapshot = _snapshot("pm_guard_clean", spread_bps=72.0, staleness_ms=900, implied_probability=0.52)
    comment_report = _report(
        market_id="pm_guard_clean",
        comment_count=6,
        author_count=6,
        label=CommentSentimentLabel.neutral,
        score=0.04,
        confidence=0.32,
        bullish_share=0.34,
        bearish_share=0.33,
        neutral_share=0.33,
        dominant_strength=0.24,
        counter_narratives=[
            NarrativeSignal(
                direction=CommentSentimentLabel.bearish,
                title="counter",
                summary="counter",
                strength=0.2,
                keywords=["counter"],
                comment_ids=["c1"],
            )
        ],
    )
    stream_summary = _stream_summary(stream_id="stream_clean", market_id="pm_guard_clean", trend="stable", event_count=5, change_rate=0.2)
    stream_health = MarketStreamHealth(
        stream_id="stream_clean",
        market_id="pm_guard_clean",
        venue=VenueName.polymarket,
        healthy=True,
        freshness_status="fresh",
        message="healthy",
        issues=[],
        latest_sequence=5,
        event_count=5,
        poll_count=5,
        age_seconds=42.0,
        backend_mode="live",
    )

    report = ManipulationGuard().evaluate(
        market,
        snapshot,
        comment_report=comment_report,
        stream_summary=stream_summary,
        stream_health=stream_health,
    )

    assert report.severity == ManipulationGuardSeverity.low
    assert report.can_trade is True
    assert report.signal_only is False
    assert report.risk_flags == []
    assert report.comment_count == 6
    assert report.author_count == 6
    assert report.stream_event_count == 5
    assert report.reasons == ["context_balanced"]


def test_manipulation_guard_flags_comment_burst_and_narrative_mismatch() -> None:
    market = _market(market_id="pm_guard_manipulated", liquidity=8_000.0)
    snapshot = _snapshot(
        "pm_guard_manipulated",
        liquidity=8_000.0,
        spread_bps=210.0,
        staleness_ms=4_000,
        implied_probability=0.39,
    )
    comment_report = _report(
        market_id="pm_guard_manipulated",
        comment_count=9,
        author_count=2,
        label=CommentSentimentLabel.bullish,
        score=0.91,
        confidence=0.94,
        bullish_share=0.92,
        bearish_share=0.04,
        neutral_share=0.04,
        dominant_strength=0.95,
    )
    stream_summary = _stream_summary(
        stream_id="stream_manipulated",
        market_id="pm_guard_manipulated",
        trend="bearish",
        event_count=3,
        change_rate=0.5,
    )
    stream_health = MarketStreamHealth(
        stream_id="stream_manipulated",
        market_id="pm_guard_manipulated",
        venue=VenueName.polymarket,
        healthy=True,
        freshness_status="fresh",
        message="healthy",
        issues=[],
        latest_sequence=3,
        event_count=3,
        poll_count=3,
        age_seconds=18.0,
        backend_mode="live",
    )

    report = ManipulationGuard().evaluate(
        market,
        snapshot,
        comment_report=comment_report,
        stream_summary=stream_summary,
        stream_health=stream_health,
    )

    assert report.severity in {ManipulationGuardSeverity.high, ManipulationGuardSeverity.critical}
    assert report.can_trade is False
    assert report.signal_only is True
    assert "low_author_diversity" in report.risk_flags
    assert "comment_burst" in report.risk_flags
    assert "one_sided_comments" in report.risk_flags
    assert "narrative_mismatch" in report.risk_flags
    assert any(reason.startswith("comment_to_author_ratio=") for reason in report.reasons)


def test_manipulation_guard_blocks_stale_and_inconsistent_stream_context() -> None:
    market = _market(market_id="pm_guard_stale")
    snapshot = _snapshot("pm_guard_stale", spread_bps=100.0, staleness_ms=240_000, implied_probability=0.53)
    stream_summary = _stream_summary(stream_id="stream_stale", market_id="pm_guard_stale", trend="stable", event_count=1, change_rate=0.0)
    stream_health = MarketStreamHealth(
        stream_id="stream_stale",
        market_id="pm_guard_stale",
        venue=VenueName.polymarket,
        healthy=False,
        freshness_status="stale",
        message="sequence mismatch",
        issues=["sequence_mismatch", "manifest_event_mismatch"],
        latest_sequence=1,
        event_count=1,
        poll_count=1,
        age_seconds=7_200.0,
        backend_mode="live",
    )

    report = ManipulationGuard().evaluate(
        market,
        snapshot,
        stream_summary=stream_summary,
        stream_health=stream_health,
    )

    assert report.severity in {ManipulationGuardSeverity.high, ManipulationGuardSeverity.critical}
    assert report.can_trade is False
    assert report.signal_only is True
    assert "stale_snapshot" in report.risk_flags
    assert "stream_unhealthy" in report.risk_flags
    assert "stream_stale" in report.risk_flags
    assert "stream_inconsistent" in report.risk_flags
    assert any(reason.startswith("snapshot_staleness_ms=") for reason in report.reasons)
