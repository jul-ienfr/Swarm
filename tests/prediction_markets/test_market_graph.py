from __future__ import annotations

from datetime import datetime, timezone

from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType
from prediction_markets.market_graph import GraphRelationKind, MarketGraphBuilder


def _market(
    market_id: str,
    *,
    venue: VenueName,
    title: str,
    question: str,
    canonical_event_id: str | None = None,
    venue_type: VenueType = VenueType.execution,
    resolution_source: str = "https://example.com/resolution",
    open_time: datetime | None = None,
    end_date: datetime | None = None,
    resolution_date: datetime | None = None,
    liquidity: float = 1000.0,
    status: MarketStatus = MarketStatus.open,
    metadata: dict[str, object] | None = None,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=title,
        question=question,
        canonical_event_id=canonical_event_id,
        resolution_source=resolution_source,
        open_time=open_time,
        end_date=end_date,
        resolution_date=resolution_date,
        liquidity=liquidity,
        status=status,
        metadata=metadata or {},
    )


def test_market_graph_links_same_event_across_venues() -> None:
    markets = [
        _market(
            "pm_1",
            venue=VenueName.polymarket,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            canonical_event_id="fed_q3_2026",
            venue_type=VenueType.execution,
            liquidity=80000,
        ),
        _market(
            "k_1",
            venue=VenueName.kalshi,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            canonical_event_id="fed_q3_2026",
            venue_type=VenueType.execution,
            liquidity=50000,
        ),
    ]
    graph = MarketGraphBuilder().build(markets)

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert len(graph.matches) == 1
    assert len(graph.comparable_groups) == 1
    assert graph.edges[0].relation == GraphRelationKind.same_event
    assert graph.matches[0].canonical_event_id == "fed_q3_2026"
    assert graph.matches[0].question_key == "cut fed q3"
    assert graph.matches[0].comparable_market_refs == ["pm_1", "k_1"]
    assert "currency_mismatch" in graph.matches[0].notes
    assert "payout_currency_mismatch" in graph.matches[0].notes
    assert graph.nodes_by_market_id()["pm_1"].role == "reference"
    assert graph.comparable_groups[0].canonical_event_id == "fed_q3_2026"
    assert graph.comparable_groups[0].question == "Will the Fed cut by Q3?"
    assert graph.comparable_groups[0].question_key == "cut fed q3"
    assert graph.comparable_groups[0].comparable_market_refs == ["k_1", "pm_1"]
    assert graph.comparable_groups[0].reference_market_ids
    assert graph.comparable_groups[0].resolution_sources == ["https://example.com/resolution"]
    assert graph.comparable_groups[0].notes == []
    assert graph.comparable_groups[0].compatible_resolution is True
    assert graph.comparable_groups[0].compatible_currency is True
    assert graph.comparable_groups[0].compatible_payout is True
    assert graph.comparable_groups[0].duplicate_market_count == 1
    assert graph.comparable_groups[0].duplicate_market_rate == 0.5
    assert graph.comparable_groups[0].desalignment_count == 0
    assert graph.comparable_groups[0].desalignment_rate == 0.0
    assert graph.comparable_groups[0].desalignment_dimensions == []
    assert graph.metadata["comparable_group_count"] == 1
    assert graph.metadata["grouped_market_count"] == 2
    assert graph.metadata["grouped_market_coverage_rate"] == 1.0
    assert graph.metadata["duplicate_market_count"] == 1
    assert graph.metadata["duplicate_market_rate"] == 0.5
    assert graph.metadata["duplicate_group_count"] == 1
    assert graph.metadata["average_duplicate_group_size"] == 2.0
    assert graph.metadata["desaligned_match_count"] == 0
    assert graph.metadata["desaligned_group_count"] == 0
    assert graph.metadata["match_desalignment_dimension_counts"] == {}
    assert graph.metadata["group_desalignment_dimension_counts"] == {}


def test_market_graph_groups_similar_questions_without_canonical_event_id() -> None:
    markets = [
        _market(
            "pm_2",
            venue=VenueName.polymarket,
            title="BTC above 120k by year end 2026",
            question="Will BTC trade above 120k by year end 2026?",
            canonical_event_id=None,
            liquidity=70000,
        ),
        _market(
            "m_2",
            venue=VenueName.metaculus,
            title="BTC above 120k by year end 2026",
            question="Will BTC trade above 120k by year end 2026?",
            canonical_event_id=None,
            venue_type=VenueType.reference,
            liquidity=1000,
        ),
    ]
    snapshots = {
        "pm_2": MarketSnapshot(market_id="pm_2", venue=VenueName.polymarket, title="BTC", question="Will BTC trade above 120k by year end 2026?", price_yes=0.57, price_no=0.43, midpoint_yes=0.57, liquidity=70000),
        "m_2": MarketSnapshot(market_id="m_2", venue=VenueName.metaculus, title="BTC", question="Will BTC trade above 120k by year end 2026?", price_yes=0.61, price_no=0.39, midpoint_yes=0.61, liquidity=1000),
    }
    graph = MarketGraphBuilder().build(markets, snapshots=snapshots)

    assert len(graph.matches) == 1
    assert len(graph.comparable_groups) == 1
    match = graph.matches[0]
    assert match.similarity >= 0.8
    assert match.compatible_resolution is False or match.compatible_resolution is True
    assert match.question_key == "120k 2026 btc end trade year"
    assert match.comparable_market_refs == ["pm_2", "m_2"]
    assert "currency_mismatch" in match.notes
    assert "payout_currency_mismatch" in match.notes
    assert graph.edges[0].relation in {GraphRelationKind.same_question, GraphRelationKind.same_topic}
    assert graph.comparable_groups[0].narrative_risk_flags
    assert graph.comparable_groups[0].question_key == "120k 2026 btc end trade year"
    assert graph.comparable_groups[0].comparable_market_refs == ["m_2", "pm_2"]
    assert graph.comparable_groups[0].resolution_sources == ["https://example.com/resolution"]
    assert graph.comparable_groups[0].currencies == []
    assert graph.comparable_groups[0].payout_currencies == []
    assert graph.comparable_groups[0].desalignment_count >= 0
    assert graph.metadata["duplicate_market_count"] == 1
    assert graph.metadata["grouped_market_count"] == 2


def test_market_graph_rejects_sparse_false_match_and_keeps_groups_empty() -> None:
    markets = [
        _market(
            "pm_fake_1",
            venue=VenueName.polymarket,
            title="Will BTC break 100k?",
            question="Will BTC break 100k in 2026?",
            canonical_event_id=None,
            liquidity=50000,
        ),
        _market(
            "m_fake_2",
            venue=VenueName.metaculus,
            title="US inflation outlook",
            question="Will inflation fall below 3% in 2026?",
            canonical_event_id=None,
            venue_type=VenueType.reference,
            liquidity=1000,
        ),
    ]
    graph = MarketGraphBuilder().build(markets)

    assert graph.matches == []
    assert len(graph.rejected_matches) == 1
    rejection = graph.rejected_matches[0]
    assert rejection.reason_codes
    assert "insufficient_question_overlap" in rejection.reason_codes or "similarity_below_threshold" in " ".join(rejection.reason_codes)
    assert "topic_mismatch" in rejection.reason_codes or "sparse_anchor_overlap" in rejection.reason_codes
    assert graph.comparable_groups == []
    assert graph.metadata["rejected_match_count"] == 1
    assert graph.metadata["mapper_precision"] == 0.0
    assert graph.metadata["false_match_rate"] == 1.0
    assert graph.metadata["min_cross_venue_similarity_score"] < 1.0
    assert graph.metadata["rejection_reason_counts"]


def test_market_graph_rejects_timing_mismatched_false_match() -> None:
    left = _market(
        "pm_timing_false",
        venue=VenueName.polymarket,
        title="Will the merger close this quarter?",
        question="Will the merger close this quarter?",
        canonical_event_id=None,
        open_time=datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        metadata={"timezone": "America/New_York"},
    )
    right = _market(
        "m_timing_false",
        venue=VenueName.metaculus,
        title="Will the merger close in 2027?",
        question="Will the merger close in 2027?",
        canonical_event_id=None,
        venue_type=VenueType.reference,
        open_time=datetime(2027, 1, 7, 9, 0, tzinfo=timezone.utc),
        end_date=datetime(2027, 1, 9, 17, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2027, 1, 9, 17, 0, tzinfo=timezone.utc),
        metadata={"timezone": "UTC"},
    )

    graph = MarketGraphBuilder().build([left, right])

    assert graph.matches == []
    assert len(graph.rejected_matches) == 1
    rejection = graph.rejected_matches[0]
    assert "timing_mismatch" in rejection.reason_codes or "timebox_mismatch" in rejection.reason_codes
    assert graph.comparable_groups == []
    assert graph.metadata["rejected_match_count"] == 1


def test_market_graph_flags_timing_mismatches_explicitly() -> None:
    left = _market(
        "pm_timing_a",
        venue=VenueName.polymarket,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        open_time=datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        metadata={"timezone": "America/New_York"},
    )
    right = _market(
        "k_timing_b",
        venue=VenueName.kalshi,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        venue_type=VenueType.reference,
        open_time=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 4, 10, 17, 0, tzinfo=timezone.utc),
        metadata={"timezone": "UTC"},
    )

    graph = MarketGraphBuilder().build([left, right])

    assert len(graph.matches) == 1
    match = graph.matches[0]
    assert match.manual_review_required is True
    assert match.metadata["timing_compatibility_score"] < 1.0
    assert "timebox_mismatch" in match.notes
    assert "cutoff_mismatch" in match.notes
    assert "timezone_mismatch" in match.notes
    assert graph.comparable_groups[0].manual_review_required is True
    assert "timebox_mismatch" in graph.comparable_groups[0].notes
    assert "cutoff_mismatch" in graph.comparable_groups[0].notes
    assert "timezone_mismatch" in graph.comparable_groups[0].notes
    assert graph.comparable_groups[0].desalignment_count >= 1
    assert graph.comparable_groups[0].desalignment_rate > 0.0
    assert "timing" in graph.comparable_groups[0].desalignment_dimensions
    assert graph.metadata["desaligned_match_count"] == 1
    assert graph.metadata["desaligned_match_rate"] == 1.0
    assert graph.metadata["desaligned_group_count"] == 1
    assert graph.metadata["desaligned_group_rate"] == 1.0
    assert graph.metadata["mismatch_reason_counts"]["timebox_mismatch"] >= 1
    assert graph.metadata["match_desalignment_dimension_counts"]["timing"] >= 1
    assert graph.metadata["group_desalignment_dimension_counts"]["timing"] >= 1


def test_market_graph_links_parent_child_markets() -> None:
    parent = _market(
        "pm_parent",
        venue=VenueName.polymarket,
        title="Will the Fed cut rates in 2026?",
        question="Will the Fed cut rates in 2026?",
        canonical_event_id="fed_cut_2026",
        liquidity=90000,
    )
    child = _market(
        "k_child",
        venue=VenueName.kalshi,
        title="Will the Fed cut rates by Q3 2026?",
        question="Will the Fed cut rates by Q3 2026?",
        canonical_event_id="fed_cut_2026",
        liquidity=45000,
    )

    graph = MarketGraphBuilder().build([parent, child])

    assert len(graph.comparable_groups) == 1
    group = graph.comparable_groups[0]
    assert group.parent_market_ids == ["pm_parent"]
    assert group.child_market_ids == ["k_child"]
    assert group.parent_child_pairs == [
        {
            "parent_market_id": "pm_parent",
            "child_market_id": "k_child",
            "shared_tokens": ["2026", "cut", "fed", "rates"],
            "specificity_gap": 1.2,
        }
    ]
    assert group.natural_hedge_market_ids == []
    assert group.natural_hedge_pairs == []
    assert group.metadata["parent_market_count"] == 1
    assert group.metadata["child_market_count"] == 1
    assert group.metadata["parent_child_pair_count"] == 1
    assert graph.metadata["parent_market_count"] == 1
    assert graph.metadata["child_market_count"] == 1
    assert graph.metadata["parent_child_pair_count"] == 1
    assert graph.nodes_by_market_id()["pm_parent"].metadata["family_role"] == "parent"
    assert graph.nodes_by_market_id()["k_child"].metadata["family_role"] == "child"
    assert graph.nodes_by_market_id()["pm_parent"].metadata["natural_hedge_role"] == "peer"
    assert graph.nodes_by_market_id()["k_child"].metadata["natural_hedge_role"] == "peer"
    assert "parent_child_pairs=1" in group.rationale


def test_market_graph_detects_natural_hedge_pairs() -> None:
    left = _market(
        "pm_up",
        venue=VenueName.polymarket,
        title="Will BTC trade above 120k by year end 2026?",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id=None,
        liquidity=60000,
    )
    right = _market(
        "m_down",
        venue=VenueName.metaculus,
        title="Will BTC trade below 120k by year end 2026?",
        question="Will BTC trade below 120k by year end 2026?",
        canonical_event_id=None,
        venue_type=VenueType.reference,
        liquidity=1200,
    )

    graph = MarketGraphBuilder().build([left, right])

    assert len(graph.comparable_groups) == 1
    group = graph.comparable_groups[0]
    assert group.relation_kind in {GraphRelationKind.same_question, GraphRelationKind.same_topic}
    assert group.parent_market_ids == []
    assert group.child_market_ids == []
    assert group.parent_child_pairs == []
    assert group.natural_hedge_market_ids == ["m_down", "pm_up"]
    assert group.natural_hedge_pairs == [
        {
            "left_market_id": "m_down",
            "right_market_id": "pm_up",
            "hedge_kind": "complementary",
            "shared_tokens": ["120k", "2026", "btc", "end", "trade", "year"],
            "left_signal": "downside",
            "right_signal": "upside",
        }
    ]
    assert group.metadata["natural_hedge_market_count"] == 2
    assert group.metadata["natural_hedge_pair_count"] == 1
    assert graph.metadata["natural_hedge_market_count"] == 2
    assert graph.metadata["natural_hedge_pair_count"] == 1
    assert graph.nodes_by_market_id()["pm_up"].metadata["family_role"] == "hedge"
    assert graph.nodes_by_market_id()["m_down"].metadata["family_role"] == "hedge"
    assert graph.nodes_by_market_id()["pm_up"].metadata["natural_hedge_role"] == "hedge"
    assert graph.nodes_by_market_id()["m_down"].metadata["natural_hedge_role"] == "hedge"
    assert "natural_hedge_pairs=1" in group.rationale
