from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
from pathlib import Path

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.cross_venue import CrossVenueIntelligence, CrossVenueOpsState, CrossVenueTaxonomy, SpreadSeverity
from prediction_markets.models import CrossVenueMatch, MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType


def _market(
    market_id: str,
    *,
    venue: VenueName,
    title: str,
    question: str,
    canonical_event_id: str | None = None,
    venue_type: VenueType = VenueType.execution,
    resolution_source: str = "https://example.com/resolution",
    source_url: str | None = None,
    open_time: datetime | None = None,
    end_date: datetime | None = None,
    resolution_date: datetime | None = None,
    liquidity: float = 1000.0,
    metadata: dict[str, object] | None = None,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=title,
        question=question,
        source_url=source_url,
        canonical_event_id=canonical_event_id,
        resolution_source=resolution_source,
        open_time=open_time,
        end_date=end_date,
        resolution_date=resolution_date,
        liquidity=liquidity,
        metadata=metadata or {},
        status=MarketStatus.open,
    )


def test_cross_venue_match_generation_and_reference_role() -> None:
    left = _market(
        "pm_a",
        venue=VenueName.polymarket,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        liquidity=80000,
    )
    right = _market(
        "k_a",
        venue=VenueName.kalshi,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        venue_type=VenueType.reference,
        liquidity=50000,
    )
    intel = CrossVenueIntelligence()
    match = intel.match_markets(left, right)
    report = intel.build_report([left, right], snapshots={})

    assert match is not None
    assert match.canonical_event_id == "fed_q3_2026"
    assert match.question_key == "cut fed q3"
    assert match.comparable_market_refs == ["pm_a", "k_a"]
    assert match.left_resolution_source == "https://example.com/resolution"
    assert match.right_resolution_source == "https://example.com/resolution"
    assert match.left_currency is None
    assert match.right_currency is None
    assert match.left_payout_currency is None
    assert match.right_payout_currency is None
    assert match.comparable_group_id == "fed_q3_2026"
    assert match.notes == []
    assert report.matches
    assert report.reference_market_ids
    assert "pm_a" in report.reference_market_ids or "k_a" in report.reference_market_ids
    assert report.comparable_groups
    assert report.comparable_groups[0].question == "Will the Fed cut by Q3?"
    assert report.comparable_groups[0].question_key == "cut fed q3"
    assert report.comparable_groups[0].comparable_market_refs in (["k_a", "pm_a"], ["pm_a", "k_a"])
    assert report.comparable_groups[0].resolution_sources == ["https://example.com/resolution"]
    assert report.comparable_groups[0].notes == []
    assert report.execution_plans == []
    assert report.ops_summary.comparable_group_count == 1
    assert report.comparisons[0].comparison_state.value in {"comparison_only", "signal_candidate", "manual_review", "spread_alert"}
    assert report.comparisons[0].taxonomy == CrossVenueTaxonomy.comparison_only
    assert report.comparisons[0].question_key == "cut fed q3"
    assert report.comparisons[0].comparable_market_refs == ["pm_a", "k_a"]
    assert report.comparisons[0].notes == []


def test_cross_venue_spread_alert_triggers_on_large_delta() -> None:
    left = _market(
        "pm_b",
        venue=VenueName.polymarket,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        liquidity=70000,
    )
    right = _market(
        "m_b",
        venue=VenueName.metaculus,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        venue_type=VenueType.reference,
        liquidity=1000,
    )
    snapshots = {
        "pm_b": MarketSnapshot(market_id="pm_b", venue=VenueName.polymarket, title="BTC", question="Will BTC trade above 120k by year end 2026?", price_yes=0.45, price_no=0.55, midpoint_yes=0.45, liquidity=70000),
        "m_b": MarketSnapshot(market_id="m_b", venue=VenueName.metaculus, title="BTC", question="Will BTC trade above 120k by year end 2026?", price_yes=0.71, price_no=0.29, midpoint_yes=0.71, liquidity=1000),
    }
    report = CrossVenueIntelligence(spread_threshold_bps=150.0).build_report([left, right], snapshots=snapshots)

    assert report.comparisons
    comparison = report.comparisons[0]
    assert comparison.spread_bps is not None
    assert comparison.spread_bps > 150.0
    assert comparison.taxonomy == CrossVenueTaxonomy.relative_value
    assert report.spread_alerts
    assert report.spread_alerts[0].severity in {SpreadSeverity.medium, SpreadSeverity.high}
    assert report.spread_alerts[0].metadata["reference_market_id"] in {"pm_b", "m_b"}


def test_cross_venue_reports_role_qualification_summary() -> None:
    left = _market(
        "m_ref",
        venue=VenueName.metaculus,
        title="Rates stay high",
        question="Will rates stay high into 2026?",
        canonical_event_id="rates_2026",
        venue_type=VenueType.reference,
        liquidity=5000,
    )
    right = _market(
        "m_sig",
        venue=VenueName.manifold,
        title="Rates stay high",
        question="Will rates stay high into 2026?",
        canonical_event_id="rates_2026",
        venue_type=VenueType.signal,
        liquidity=2000,
    )
    snapshots = {
        "pm_time_a": MarketSnapshot(
            market_id="pm_time_a",
            venue=VenueName.polymarket,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.50,
            price_no=0.50,
            midpoint_yes=0.50,
            liquidity=1000,
        ),
        "k_time_b": MarketSnapshot(
            market_id="k_time_b",
            venue=VenueName.kalshi,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.50,
            price_no=0.50,
            midpoint_yes=0.50,
            liquidity=1000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert report.qualification_summary.venue_roles["metaculus"] == ["reference", "watchlist"]
    assert report.qualification_summary.venue_roles["manifold"] == ["signal", "watchlist"]
    assert report.qualification_summary.role_venues["reference"] == ["metaculus"]
    assert report.qualification_summary.role_venues["signal"] == ["manifold"]
    assert report.qualification_summary.role_counts["watchlist"] == 2
    assert report.comparisons[0].metadata["left_roles"] == ["reference", "watchlist"]
    assert report.comparisons[0].metadata["right_roles"] == ["signal", "watchlist"]
    assert report.comparisons[0].taxonomy == CrossVenueTaxonomy.comparison_only
    assert report.ops_summary.manual_review_count >= 0
    assert report.comparisons[0].narrative_risk_flags is not None
    assert report.venue_role_classification.role_venues["reference"] == ["metaculus"]
    assert report.venue_role_classification.role_venues["signal"] == ["manifold", "opinion_trade"]
    assert report.venue_role_classification.execution_equivalent_venues == [
        VenueName.polymarket,
        VenueName.kalshi,
    ]
    assert VenueName.robinhood in report.venue_role_classification.execution_bindable_venues
    assert VenueName.cryptocom in report.venue_role_classification.execution_bindable_venues
    assert report.venue_role_classification.execution_like_venues == []
    assert report.venue_role_classification.reference_only_venues == [VenueName.metaculus]
    assert report.venue_role_classification.watchlist_only_venues == [VenueName.manifold, VenueName.opinion_trade]
    assert report.metadata["execution_equivalent_count"] == 2
    assert report.metadata["execution_bindable_count"] == len(report.venue_role_classification.execution_bindable_venues)
    assert report.metadata["execution_like_count"] == len(report.venue_role_classification.execution_like_venues)
    assert report.metadata["reference_only_count"] == 1
    assert report.metadata["watchlist_only_count"] == 2
    assert report.metadata["planning_buckets"]["metaculus"] == "reference-only"
    assert report.metadata["planning_buckets"]["manifold"] == "watchlist"
    assert report.metadata["planning_buckets"]["robinhood"] == "execution-bindable"
    assert report.metadata["venue_role_classification"]["role_counts"]["watchlist"] >= 2


def test_cross_venue_builds_execution_candidates_for_execution_venues() -> None:
    left = _market(
        "pm_exec",
        venue=VenueName.polymarket,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        liquidity=70000,
    )
    right = _market(
        "k_exec",
        venue=VenueName.kalshi,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        liquidity=60000,
    )

    snapshots = {
        "pm_exec": MarketSnapshot(
            market_id="pm_exec",
            venue=VenueName.polymarket,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.62,
            price_no=0.38,
            midpoint_yes=0.62,
            liquidity=70000,
        ),
        "k_exec": MarketSnapshot(
            market_id="k_exec",
            venue=VenueName.kalshi,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.62,
            price_no=0.38,
            midpoint_yes=0.62,
            liquidity=60000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert report.comparisons
    assert report.comparisons[0].comparison_state.value == "signal_candidate"
    assert report.comparisons[0].classification == "tradeable"
    assert report.comparisons[0].taxonomy == CrossVenueTaxonomy.relative_value
    assert report.execution_candidates
    candidate = report.execution_candidates[0]
    assert candidate.taxonomy == CrossVenueTaxonomy.true_arbitrage
    assert candidate.preferred_execution_venue == VenueName.polymarket
    assert candidate.preferred_execution_pathway == "live_execution"
    assert candidate.preferred_execution_mode == "live"
    assert candidate.preferred_operator_action == "route_live_orders"
    assert candidate.preferred_promotion_target_pathway is None
    assert candidate.preferred_execution_selection_reason == "higher_readiness_stage"
    assert candidate.pathway_summary.startswith("pathway=live_execution")
    assert candidate.operator_summary == "action=route_live_orders | credentials=live_credentials_required | api=order_api_available"
    assert candidate.promotion_summary.startswith("promote->none")
    assert candidate.blocker_summary == "none"
    assert "selection=higher_readiness_stage" in candidate.preferred_execution_summary
    assert "taxonomy=execution_ready" in candidate.preferred_execution_capability_summary
    assert candidate.execution_pathways_by_market_id == {
        "k_exec": "bounded_execution",
        "pm_exec": "live_execution",
    }
    assert candidate.readiness_stages_by_market_id == {
        "k_exec": "bounded_ready",
        "pm_exec": "live_ready",
    }
    assert candidate.highest_actionable_modes_by_market_id == {
        "k_exec": "bounded_live",
        "pm_exec": "live",
    }
    assert candidate.required_operator_actions_by_market_id == {
        "k_exec": "route_bounded_orders",
        "pm_exec": "route_live_orders",
    }
    assert candidate.next_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert candidate.next_pathway_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert set(candidate.bounded_execution_equivalent_market_ids) == {"k_exec", "pm_exec"}
    assert candidate.bounded_execution_promotion_candidate_market_ids == []
    assert candidate.stage_summaries_by_market_id["k_exec"]["remaining_pathway_count"] == 1
    assert candidate.stage_summaries_by_market_id["pm_exec"]["remaining_pathway_count"] == 0
    assert candidate.metadata["readiness_stage_counts"] == {
        "bounded_ready": 1,
        "live_ready": 1,
    }
    assert candidate.metadata["preferred_execution_semantics"] == "live_candidate"
    assert candidate.metadata["preferred_execution_selection_reason"] == "higher_readiness_stage"
    assert candidate.metadata["mixed_execution_semantics"] == "mixed_live_and_bounded"
    assert candidate.metadata["survivability_hint"] == "survivable_with_bounded_fallback"
    assert candidate.metadata["survivability_by_market_id"] == {
        "k_exec": "leg_bounded_ready",
        "pm_exec": "leg_live_ready",
    }
    assert candidate.metadata["requirement_gap_summary_by_market_id"] == {
        "k_exec": {
            "missing_requirement_count": 1,
            "blocked_pathway_count": 1,
            "next_pathway": "live_execution",
            "highest_actionable_mode": "bounded_live",
        },
        "pm_exec": {
            "missing_requirement_count": 0,
            "blocked_pathway_count": 0,
            "next_pathway": None,
            "highest_actionable_mode": "live",
        },
    }
    assert candidate.metadata["credential_gates_by_market_id"] == {
        "k_exec": "bounded_credentials_required",
        "pm_exec": "live_credentials_required",
    }
    assert candidate.metadata["api_gates_by_market_id"] == {
        "k_exec": "order_api_available",
        "pm_exec": "order_api_available",
    }
    assert candidate.metadata["missing_requirement_counts_by_market_id"] == {
        "k_exec": 1,
        "pm_exec": 0,
    }
    assert candidate.metadata["readiness_scores_by_market_id"] == {
        "k_exec": 4,
        "pm_exec": 5,
    }
    assert candidate.metadata["operator_checklists_by_market_id"]["pm_exec"] == [
        "action:route_live_orders",
        "credentials:live_credentials_required",
        "api:order_api_available",
    ]
    assert candidate.metadata["operator_checklists_by_market_id"]["k_exec"] == [
        "action:route_bounded_orders",
        "gate:live_execution_adapter",
        "promote:prove_live_execution_adapter",
        "promote:prove_live_cancel_path",
        "promote:prove_live_fill_audit",
        "promote:prove_compliance_gates",
        "credentials:bounded_credentials_required",
        "api:order_api_available",
    ]
    assert candidate.metadata["multi_leg_operator_checklist"] == [
        "preferred:pm_exec:route_live_orders",
        "semantics:mixed_live_and_bounded",
        "survivability:survivable_with_bounded_fallback",
        "k_exec:action:route_bounded_orders",
        "k_exec:gate:live_execution_adapter",
        "k_exec:promote:prove_live_execution_adapter",
        "k_exec:promote:prove_live_cancel_path",
        "k_exec:promote:prove_live_fill_audit",
        "k_exec:promote:prove_compliance_gates",
        "k_exec:credentials:bounded_credentials_required",
        "k_exec:api:order_api_available",
        "k_exec:next_pathway:live_execution",
        "pm_exec:action:route_live_orders",
        "pm_exec:credentials:live_credentials_required",
        "pm_exec:api:order_api_available",
    ]
    assert candidate.metadata["multi_leg_blocker_codes"] == [
        "no_live_execution_adapter",
        "multi_leg_missing_requirements",
        "multi_leg_promotion_pending",
        "secondary_leg_not_live_ready",
    ]
    assert candidate.metadata["promotion_evidence_by_market_id"]["pm_exec"]["live_execution"]["status"] == "current"
    assert candidate.metadata["promotion_evidence_by_market_id"]["k_exec"]["live_execution"]["evidence_count"] == 4
    assert candidate.metadata["bounded_execution_equivalent_count"] == 2
    assert candidate.metadata["bounded_execution_promotion_candidate_count"] == 0
    assert candidate.promotion_target_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert candidate.promotion_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert candidate.pathway_ladders_by_market_id == {
        "k_exec": ["bounded_execution", "live_execution"],
        "pm_exec": ["live_execution"],
    }
    assert candidate.blocked_pathways_by_market_id == {
        "k_exec": ["live_execution"],
        "pm_exec": [],
    }
    assert candidate.execution_blocker_codes_by_market_id == {
        "k_exec": ["no_live_execution_adapter"],
        "pm_exec": [],
    }
    assert report.execution_plans[0].execution_roles_by_market_id == {
        "k_exec": "execution_equivalent",
        "pm_exec": "execution_equivalent",
    }
    assert report.execution_plans[0].execution_pathways_by_market_id == {
        "k_exec": "bounded_execution",
        "pm_exec": "live_execution",
    }
    assert report.execution_plans[0].readiness_stages_by_market_id == {
        "k_exec": "bounded_ready",
        "pm_exec": "live_ready",
    }
    assert report.execution_plans[0].preferred_execution_pathway in {"live_execution", "bounded_execution"}
    assert report.execution_plans[0].preferred_execution_mode == "live"
    assert report.execution_plans[0].preferred_operator_action == "route_live_orders"
    assert report.execution_plans[0].preferred_promotion_target_pathway is None
    assert report.execution_plans[0].preferred_execution_selection_reason == "higher_readiness_stage"
    assert report.execution_plans[0].pathway_summary.startswith("pathway=live_execution")
    assert report.execution_plans[0].operator_summary == "action=route_live_orders | credentials=live_credentials_required | api=order_api_available"
    assert report.execution_plans[0].promotion_summary.startswith("promote->none")
    assert report.execution_plans[0].blocker_summary == "none"
    assert "selection=higher_readiness_stage" in report.execution_plans[0].preferred_execution_summary
    assert "taxonomy=execution_ready" in report.execution_plans[0].preferred_execution_capability_summary
    assert report.execution_plans[0].highest_actionable_modes_by_market_id == {
        "k_exec": "bounded_live",
        "pm_exec": "live",
    }
    assert report.execution_plans[0].required_operator_actions_by_market_id == {
        "k_exec": "route_bounded_orders",
        "pm_exec": "route_live_orders",
    }
    assert report.execution_plans[0].next_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert report.execution_plans[0].next_pathway_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert set(report.execution_plans[0].bounded_execution_equivalent_market_ids) == {"k_exec", "pm_exec"}
    assert report.execution_plans[0].bounded_execution_promotion_candidate_market_ids == []
    assert report.execution_plans[0].promotion_target_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert report.execution_plans[0].promotion_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert report.execution_plans[0].pathway_ladders_by_market_id == {
        "k_exec": ["bounded_execution", "live_execution"],
        "pm_exec": ["live_execution"],
    }
    assert report.execution_plans[0].blocked_pathways_by_market_id == {
        "k_exec": ["live_execution"],
        "pm_exec": [],
    }
    assert report.execution_plans[0].legs[0].execution_role == "execution_equivalent"
    assert {leg.required_operator_action for leg in report.execution_plans[0].legs} == {
        "route_bounded_orders",
        "route_live_orders",
    }
    assert {leg.readiness_stage for leg in report.execution_plans[0].legs} == {
        "bounded_ready",
        "live_ready",
    }
    assert {leg.next_pathway for leg in report.execution_plans[0].legs} == {
        None,
        "live_execution",
    }
    assert {tuple(leg.pathway_ladder) for leg in report.execution_plans[0].legs} == {
        ("bounded_execution", "live_execution"),
        ("live_execution",),
    }
    assert report.execution_plans[0].metadata["preferred_execution_semantics"] == "live_candidate"
    assert report.execution_plans[0].metadata["preferred_execution_selection_reason"] == "higher_readiness_stage"
    assert report.execution_plans[0].metadata["mixed_execution_semantics"] == "mixed_live_and_bounded"
    assert report.execution_plans[0].metadata["survivability_hint"] == "survivable_with_bounded_fallback"
    assert report.execution_plans[0].metadata["multi_leg_blocker_codes"] == [
        "no_live_execution_adapter",
        "multi_leg_missing_requirements",
        "multi_leg_promotion_pending",
        "secondary_leg_not_live_ready",
    ]
    assert report.execution_plans[0].metadata["credential_gates_by_market_id"] == {
        "k_exec": "bounded_credentials_required",
        "pm_exec": "live_credentials_required",
    }
    assert report.execution_plans[0].metadata["missing_requirement_counts_by_market_id"] == {
        "k_exec": 1,
        "pm_exec": 0,
    }


def test_cross_venue_separates_relative_value_from_spread_signals() -> None:
    intel = CrossVenueIntelligence()
    comparison = types.SimpleNamespace(
        spread_bps=42.0,
        comparison_state=CrossVenueOpsState.signal_candidate,
        timing_compatibility_score=1.0,
        notes=[],
    )

    reasons = intel._execution_filter_reason_codes(
        comparison,
        left_execution_capable=True,
        right_execution_capable=True,
        preferred_is_equivalent=True,
        preferred_is_bindable=False,
        preferred_is_execution_like=False,
        tradeable=False,
        execution_route="left_preferred",
    )
    candidate_taxonomy = intel._candidate_taxonomy(
        comparison,
        tradeable=False,
        preferred_is_equivalent=True,
        execution_filter_reason_codes=reasons,
    )
    plan_taxonomy = intel._plan_taxonomy(
        types.SimpleNamespace(spread_bps=42.0, comparison_state=CrossVenueOpsState.signal_candidate),
        tradeable=False,
        manual_review_required=False,
        preferred_is_equivalent=True,
        execution_filter_reason_codes=reasons,
    )

    assert "relative_value_not_tradeable" in reasons
    assert candidate_taxonomy == CrossVenueTaxonomy.relative_value
    assert plan_taxonomy == CrossVenueTaxonomy.relative_value


def test_cross_venue_canonical_compatibility_thresholds_gate_and_surface_metadata() -> None:
    left = _market(
        "pm_thr",
        venue=VenueName.polymarket,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        metadata={"currency": "USD", "payout_currency": "USD"},
    )
    right = _market(
        "k_thr",
        venue=VenueName.kalshi,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        metadata={"currency": "USD", "payout_currency": "USD"},
    )
    match = CrossVenueMatch(
        canonical_event_id="btc_120k_2026",
        left_market_id="pm_thr",
        right_market_id="k_thr",
        left_venue=VenueName.polymarket,
        right_venue=VenueName.kalshi,
        resolution_compatibility_score=0.8,
        payout_compatibility_score=0.9,
        currency_compatibility_score=0.9,
        compatible_resolution=True,
        manual_review_required=False,
    )

    default_intel = CrossVenueIntelligence()
    assert default_intel._comparison_state(match, 12.0, timing_compatibility_score=1.0) == CrossVenueOpsState.manual_review

    relaxed_intel = CrossVenueIntelligence(
        min_resolution_compatibility_score=0.75,
        min_payout_compatibility_score=0.8,
        min_currency_compatibility_score=0.8,
        spread_threshold_bps=500.0,
    )
    assert relaxed_intel._comparison_state(match, 12.0, timing_compatibility_score=1.0) == CrossVenueOpsState.signal_candidate

    snapshots = {
        "pm_thr": MarketSnapshot(
            market_id="pm_thr",
            venue=VenueName.polymarket,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.62,
            price_no=0.38,
            midpoint_yes=0.62,
            liquidity=70000,
        ),
        "k_thr": MarketSnapshot(
            market_id="k_thr",
            venue=VenueName.kalshi,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.60,
            price_no=0.40,
            midpoint_yes=0.60,
            liquidity=60000,
        ),
    }

    report = relaxed_intel.build_report([left, right], snapshots=snapshots)
    comparison = report.comparisons[0]
    assert comparison.metadata["min_resolution_compatibility_score"] == 0.75
    assert comparison.metadata["min_payout_compatibility_score"] == 0.8
    assert comparison.metadata["min_currency_compatibility_score"] == 0.8
    assert report.metadata["min_resolution_compatibility_score"] == 0.75
    assert report.metadata["min_payout_compatibility_score"] == 0.8
    assert report.metadata["min_currency_compatibility_score"] == 0.8
    assert report.metadata["compatibility_thresholds"] == {
        "resolution": 0.75,
        "payout": 0.8,
        "currency": 0.8,
    }

    surface = relaxed_intel.routing_surface([left, right], snapshots=snapshots)
    assert surface.metadata["min_resolution_compatibility_score"] == 0.75
    assert surface.metadata["min_payout_compatibility_score"] == 0.8
    assert surface.metadata["min_currency_compatibility_score"] == 0.8
    assert surface.metadata["compatibility_thresholds"] == {
        "resolution": 0.75,
        "payout": 0.8,
        "currency": 0.8,
    }
    assert report.execution_candidates
    candidate = report.execution_candidates[0]
    assert candidate.execution_filter_reason_codes == []
    assert candidate.preferred_execution_venue in {VenueName.polymarket, VenueName.kalshi}
    assert candidate.preferred_execution_market_id in {"pm_thr", "k_thr"}
    assert candidate.metadata["left_execution_capable"] is True
    assert candidate.metadata["right_execution_capable"] is True
    assert candidate.tradeable is True
    assert candidate.classification == "tradeable"
    assert candidate.execution_route in {"left_preferred", "right_preferred"}
    assert candidate.comparable_group_id is None or isinstance(candidate.comparable_group_id, str)
    assert candidate.metadata["question_key"] == "120k 2026 btc end trade year"
    assert candidate.metadata["left_resolution_source"] == "https://example.com/resolution"
    assert candidate.metadata["right_resolution_source"] == "https://example.com/resolution"
    assert candidate.metadata["left_currency"] == "USD"
    assert candidate.metadata["right_currency"] == "USD"
    assert candidate.metadata["notes"] == []
    assert report.execution_plans
    plan = report.execution_plans[0]
    assert plan.candidate_id == candidate.candidate_id
    assert plan.tradeable is True
    assert plan.classification == "tradeable"
    assert plan.taxonomy == CrossVenueTaxonomy.true_arbitrage
    assert plan.execution_filter_reason_codes == []
    assert plan.execution_route in {"left_preferred", "right_preferred"}
    assert plan.execution_market_ids
    assert plan.execution_roles_by_market_id == {
        "k_thr": "execution_equivalent",
        "pm_thr": "execution_equivalent",
    }
    assert plan.read_only_market_ids == ["pm_thr", "k_thr"]
    assert all(leg.read_only is True for leg in plan.legs)
    assert all(leg.planning_bucket == "execution-equivalent" for leg in plan.legs)
    assert all(leg.execution_role == "execution_equivalent" for leg in plan.legs)
    assert set(plan.execution_equivalent_market_ids) == {"pm_thr", "k_thr"}
    assert plan.reference_only_market_ids == []
    assert plan.watchlist_market_ids == []


def test_cross_venue_execution_like_venues_keep_pathways_and_blockers_explicit() -> None:
    left = _market(
        "rh_exec_like",
        venue=VenueName.robinhood,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_exec_like",
        liquidity=25000,
    )
    right = _market(
        "cc_exec_like",
        venue=VenueName.cryptocom,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_exec_like",
        liquidity=22000,
    )
    snapshots = {
        "rh_exec_like": MarketSnapshot(
            market_id="rh_exec_like",
            venue=VenueName.robinhood,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.61,
            price_no=0.39,
            midpoint_yes=0.61,
            liquidity=25000,
        ),
        "cc_exec_like": MarketSnapshot(
            market_id="cc_exec_like",
            venue=VenueName.cryptocom,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.612,
            price_no=0.388,
            midpoint_yes=0.612,
            liquidity=22000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert len(report.execution_candidates) == 1
    assert len(report.execution_plans) == 1
    assert report.ops_summary.manual_review_count == 0
    assert report.metadata["execution_candidate_count"] == 1
    assert report.metadata["execution_plan_count"] == 1
    assert report.metadata["comparison_classification_counts"] == {"tradeable": 1}
    assert report.metadata["execution_bindable_count"] == 4
    assert report.metadata["execution_like_count"] == 0
    assert report.metadata["planning_buckets"]["robinhood"] == "execution-bindable"
    assert report.metadata["planning_buckets"]["cryptocom"] == "execution-bindable"
    assert report.execution_candidates[0].taxonomy == CrossVenueTaxonomy.cross_venue_signal
    assert report.execution_plans[0].taxonomy == CrossVenueTaxonomy.cross_venue_signal
    assert report.execution_plans[0].tradeable is False
    assert report.venue_role_classification.execution_bindable_venues
    assert VenueName.robinhood in report.venue_role_classification.execution_bindable_venues
    assert VenueName.cryptocom in report.venue_role_classification.execution_bindable_venues
    assert report.venue_role_classification.execution_like_venues == []
    assert report.execution_plans[0].preferred_execution_pathway == "execution_bindable_dry_run"
    assert report.execution_plans[0].preferred_execution_mode == "dry_run"
    assert report.execution_plans[0].preferred_operator_action == "run_dry_run_adapter"
    assert report.ops_summary.executable_candidate_count == 1
    assert report.ops_summary.reason_counts["executable_candidate"] == 1
    assert report.metadata["execution_candidate_count"] == 1
    assert report.metadata["execution_plan_count"] == 1
    assert report.metadata["compared_market_count"] == 2
    assert report.metadata["grouped_market_count"] == 2
    assert report.metadata["grouped_market_coverage_rate"] == 1.0
    assert report.metadata["comparable_market_coverage_rate"] == 1.0
    assert report.metadata["duplicate_market_count"] == 1
    assert report.metadata["duplicate_market_rate"] == 0.5
    assert report.metadata["duplicate_group_count"] == 1
    assert report.metadata["average_duplicate_group_size"] == 2.0
    assert report.metadata["desaligned_comparison_count"] == 0
    assert report.metadata["desaligned_group_count"] == 0
    assert report.metadata["manual_review_due_to_alignment_count"] == 0
    assert report.metadata["match_desalignment_dimension_counts"] == {}
    assert report.metadata["group_desalignment_dimension_counts"] == {}
    assert report.metadata["mapper_precision"] == 1.0
    assert report.metadata["false_match_rate"] == 0.0
    assert report.metadata["min_cross_venue_similarity_score"] == 1.0
    assert report.metadata["comparison_classification_counts"]["tradeable"] == 1


def test_cross_venue_demotes_execution_like_only_pair_to_signal_only() -> None:
    left = _market(
        "rh_exec_like",
        venue=VenueName.robinhood,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        source_url="https://robinhood.com/markets/btc-120k-2026",
        liquidity=120000,
    )
    right = _market(
        "cr_exec_like",
        venue=VenueName.cryptocom,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        source_url="https://crypto.com/markets/btc-120k-2026",
        liquidity=110000,
    )
    snapshots = {
        "rh_exec_like": MarketSnapshot(
            market_id="rh_exec_like",
            venue=VenueName.robinhood,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.62,
            price_no=0.38,
            midpoint_yes=0.62,
            liquidity=120000,
        ),
        "cr_exec_like": MarketSnapshot(
            market_id="cr_exec_like",
            venue=VenueName.cryptocom,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.62,
            price_no=0.38,
            midpoint_yes=0.62,
            liquidity=110000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert len(report.execution_candidates) == 1
    assert len(report.execution_plans) == 1
    assert report.ops_summary.manual_review_count == 0
    assert report.metadata["execution_candidate_count"] == 1
    assert report.metadata["execution_plan_count"] == 1
    assert report.metadata["comparison_classification_counts"] == {"tradeable": 1}
    assert report.metadata["planning_buckets"]["robinhood"] == "execution-bindable"
    assert report.metadata["planning_buckets"]["cryptocom"] == "execution-bindable"
    assert report.execution_candidates[0].taxonomy == CrossVenueTaxonomy.cross_venue_signal
    assert report.execution_plans[0].taxonomy == CrossVenueTaxonomy.cross_venue_signal
    assert report.execution_plans[0].tradeable is False
    assert report.execution_plans[0].preferred_execution_pathway == "execution_bindable_dry_run"
    assert report.execution_plans[0].preferred_execution_mode == "dry_run"
    assert report.execution_plans[0].preferred_operator_action == "run_dry_run_adapter"


def test_cross_venue_demotes_narrative_spread_to_manual_review() -> None:
    left = _market(
        "pm_narrative",
        venue=VenueName.polymarket,
        title="Inflation below 3%",
        question="Will inflation fall below 3% in 2026?",
        liquidity=50000,
        canonical_event_id=None,
    )
    right = _market(
        "m_narrative",
        venue=VenueName.metaculus,
        title="Inflation below 4%",
        question="Will inflation fall below 4% in 2026?",
        liquidity=1000,
        venue_type=VenueType.reference,
        canonical_event_id=None,
    )
    snapshots = {
        "pm_narrative": MarketSnapshot(
            market_id="pm_narrative",
            venue=VenueName.polymarket,
            title="Inflation below 3%",
            question="Will inflation fall below 3% in 2026?",
            price_yes=0.82,
            price_no=0.18,
            midpoint_yes=0.82,
            liquidity=50000,
        ),
        "m_narrative": MarketSnapshot(
            market_id="m_narrative",
            venue=VenueName.metaculus,
            title="Inflation below 4%",
            question="Will inflation fall below 4% in 2026?",
            price_yes=0.18,
            price_no=0.82,
            midpoint_yes=0.18,
            liquidity=1000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert report.comparisons
    comparison = report.comparisons[0]
    assert comparison.classification == "signal-only"
    assert comparison.taxonomy == CrossVenueTaxonomy.relative_value
    assert comparison.comparison_state == CrossVenueOpsState.manual_review
    assert "narrative_only" in comparison.narrative_risk_flags
    assert report.execution_candidates == []
    assert report.metadata["comparison_classification_counts"]["signal-only"] == 1
    assert report.metadata["false_match_rate"] == 0.0
    surface = CrossVenueIntelligence().cross_venue_mapper([left, right], snapshots=snapshots)
    assert surface.classification_counts["signal-only"] == 2
    assert surface.comparison_classification_counts["signal-only"] == 1
    assert surface.mapper_precision == 1.0
    assert surface.false_match_rate == 0.0
    assert surface.spread_capture_rate == 0.0


def test_cross_venue_rejects_false_spreads_with_incompatible_economic_signals() -> None:
    left = _market(
        "pm_bad",
        venue=VenueName.polymarket,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        liquidity=70000,
        metadata={"currency": "USDC", "payout_currency": "USDC"},
    )
    right = _market(
        "k_bad",
        venue=VenueName.kalshi,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        liquidity=60000,
        metadata={"currency": "USD", "payout_currency": "USD"},
    )

    snapshots = {
        "pm_bad": MarketSnapshot(
            market_id="pm_bad",
            venue=VenueName.polymarket,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.60,
            price_no=0.40,
            midpoint_yes=0.60,
            liquidity=70000,
        ),
        "k_bad": MarketSnapshot(
            market_id="k_bad",
            venue=VenueName.kalshi,
            title="BTC above 120k",
            question="Will BTC trade above 120k by year end 2026?",
            price_yes=0.60,
            price_no=0.40,
            midpoint_yes=0.60,
            liquidity=60000,
        ),
    }

    report = CrossVenueIntelligence().build_report([left, right], snapshots=snapshots)

    assert report.rejected_matches == []
    assert report.comparisons
    comparison = report.comparisons[0]
    assert comparison.comparison_state == CrossVenueOpsState.manual_review
    assert comparison.taxonomy == CrossVenueTaxonomy.relative_value
    assert comparison.currency_compatibility_score == 0.0
    assert comparison.payout_compatibility_score == 0.0
    assert report.execution_candidates == []
    assert report.execution_plans == []


def test_cross_venue_flags_timezone_mismatch_as_manual_review() -> None:
    left = _market(
        "pm_time_a",
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
        "k_time_b",
        venue=VenueName.kalshi,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        venue_type=VenueType.execution,
        open_time=datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc),
        metadata={"timezone": "UTC"},
    )

    report = CrossVenueIntelligence().build_report([left, right], snapshots={})

    assert report.comparisons
    comparison = report.comparisons[0]
    assert comparison.timing_compatibility_score < 1.0
    assert comparison.comparison_state == CrossVenueOpsState.manual_review
    assert comparison.taxonomy == CrossVenueTaxonomy.comparison_only
    assert "timezone_mismatch" in comparison.notes
    assert report.execution_candidates == []
    assert report.execution_plans == []
    assert report.metadata["timing_mismatch_count"] == 1
    assert report.metadata["timing_compatibility_average"] < 1.0
    assert report.metadata["desaligned_comparison_count"] == 1
    assert report.metadata["desaligned_comparison_rate"] == 1.0
    assert report.metadata["desaligned_group_count"] == 1
    assert report.metadata["desaligned_group_rate"] == 1.0
    assert report.metadata["manual_review_due_to_alignment_count"] == 1
    assert report.metadata["manual_review_due_to_alignment_rate"] == 1.0
    assert report.metadata["mismatch_reason_counts"]["timezone_mismatch"] >= 1
    assert report.metadata["match_desalignment_dimension_counts"]["timing"] >= 1
    assert report.metadata["group_desalignment_dimension_counts"]["timing"] >= 1
