from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.cross_venue import CrossVenueTaxonomy
from prediction_markets.cross_venue import CrossVenueIntelligence
from prediction_markets.execution_edge import MarketEquivalenceProofStatus
from prediction_markets.multi_venue_executor import (
    MultiVenueExecutionPlan,
    MultiVenueExecutionReport,
    MultiVenueExecutor,
    build_multi_venue_execution_report,
)
from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus, VenueName, VenueType


def _market(
    market_id: str,
    *,
    venue: VenueName,
    venue_type: VenueType,
    title: str,
    question: str,
    canonical_event_id: str,
    resolution_source_url: str,
    end_date: datetime,
    liquidity: float,
) -> MarketDescriptor:
    return MarketDescriptor(
        market_id=market_id,
        venue=venue,
        venue_type=venue_type,
        title=title,
        question=question,
        canonical_event_id=canonical_event_id,
        resolution_source_url=resolution_source_url,
        end_date=end_date,
        liquidity=liquidity,
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
    title: str,
    question: str,
    price_yes: float,
    liquidity: float,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        venue=venue,
        title=title,
        question=question,
        price_yes=price_yes,
        price_no=round(1.0 - price_yes, 6),
        midpoint_yes=price_yes,
        market_implied_probability=price_yes,
        liquidity=liquidity,
        observed_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )


def test_multi_venue_executor_builds_tradeable_plan_and_surface() -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    polymarket = _market(
        "pm_exec",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=80000.0,
    )
    kalshi = _market(
        "k_exec",
        venue=VenueName.kalshi,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=65000.0,
    )
    metaculus = _market(
        "m_ref",
        venue=VenueName.metaculus,
        venue_type=VenueType.reference,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=5000.0,
    )
    snapshots = {
        "pm_exec": _snapshot(
            "pm_exec",
            venue=VenueName.polymarket,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.620,
            liquidity=80000.0,
        ),
        "k_exec": _snapshot(
            "k_exec",
            venue=VenueName.kalshi,
            title="Fed cuts by Q3",
            question="Will the Fed cut by Q3?",
            price_yes=0.626,
            liquidity=65000.0,
        ),
    }

    report = MultiVenueExecutor(
        target_notional_usd=1500.0,
        fee_bps=20.0,
        slippage_bps=10.0,
        hedge_risk_bps=10.0,
        confidence_floor=0.6,
    ).build_report([polymarket, kalshi, metaculus], snapshots=snapshots)

    assert report.market_count == 3
    assert report.cross_venue_report.execution_candidates
    assert report.cross_venue_report.ops_summary.executable_candidate_count == 1
    assert report.surface.execution_candidate_count == 1
    assert report.surface.execution_plan_count == 1
    assert report.surface.tradeable_plan_count == 1
    assert report.surface.true_arbitrage_plan_count == 1
    assert report.surface.comparison_only_plan_count == 0
    assert report.surface.relative_value_plan_count == 0
    assert report.surface.cross_venue_signal_plan_count == 0
    assert report.surface.legging_risk_plan_count == 1
    assert report.surface.hedge_completion_ready_plan_count == 0
    assert report.surface.max_unhedged_leg_ms_max == 2500
    assert report.surface.execution_role_counts == {
        "execution_equivalent": 2,
    }
    assert report.surface.execution_roles_by_market_id == {
        "k_exec": "execution_equivalent",
        "pm_exec": "execution_equivalent",
    }
    assert report.surface.execution_pathway_counts == {
        "bounded_execution": 1,
        "live_execution": 1,
    }
    assert report.surface.execution_pathways_by_market_id == {
        "k_exec": "bounded_execution",
        "pm_exec": "live_execution",
    }
    assert report.surface.readiness_stages_by_market_id == {
        "k_exec": "bounded_ready",
        "pm_exec": "live_ready",
    }
    assert report.surface.readiness_stage_counts == {
        "bounded_ready": 1,
        "live_ready": 1,
    }
    assert report.surface.highest_actionable_modes_by_market_id == {
        "k_exec": "bounded_live",
        "pm_exec": "live",
    }
    assert report.surface.required_operator_actions_by_market_id == {
        "k_exec": "route_bounded_orders",
        "pm_exec": "route_live_orders",
    }
    assert report.surface.required_operator_action_counts == {
        "route_bounded_orders": 1,
        "route_live_orders": 1,
    }
    assert report.surface.next_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert report.surface.next_pathway_counts == {
        "live_execution": 1,
    }
    assert report.surface.next_pathway_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert set(report.surface.bounded_execution_equivalent_market_ids) == {"k_exec", "pm_exec"}
    assert report.surface.bounded_execution_equivalent_count == 2
    assert report.surface.bounded_execution_promotion_candidate_market_ids == []
    assert report.surface.bounded_execution_promotion_candidate_count == 0
    assert report.surface.stage_summaries_by_market_id["k_exec"]["remaining_pathway_count"] == 1
    assert report.surface.stage_summaries_by_market_id["pm_exec"]["remaining_pathway_count"] == 0
    assert report.surface.pathway_summaries_by_market_id["k_exec"].startswith("pathway=bounded_execution")
    assert report.surface.pathway_summaries_by_market_id["pm_exec"].startswith("pathway=live_execution")
    assert report.surface.operator_summaries_by_market_id["k_exec"] == "action=route_bounded_orders | credentials=bounded_credentials_required | api=order_api_available"
    assert report.surface.operator_summaries_by_market_id["pm_exec"] == "action=route_live_orders | credentials=live_credentials_required | api=order_api_available"
    assert report.surface.promotion_summaries_by_market_id["k_exec"] == "promote->live_execution | rules=4 | current_mode=bounded_live"
    assert report.surface.blocker_summaries_by_market_id["pm_exec"] == "none"
    assert report.surface.promotion_target_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert report.surface.promotion_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert report.surface.pathway_ladders_by_market_id == {
        "k_exec": ["bounded_execution", "live_execution"],
        "pm_exec": ["live_execution"],
    }
    assert report.surface.blocked_pathways_by_market_id == {
        "k_exec": ["live_execution"],
        "pm_exec": [],
    }
    assert report.surface.execution_blocker_codes_by_market_id == {
        "k_exec": ["no_live_execution_adapter"],
        "pm_exec": [],
    }
    assert report.surface.pathway_summaries_by_market_id == {
        "k_exec": "pathway=bounded_execution | readiness=bounded_ready | next=live_execution | blocked=live_execution",
        "pm_exec": "pathway=live_execution | readiness=live_ready | next=none | blocked=none",
    }
    assert report.surface.operator_summaries_by_market_id == {
        "k_exec": "action=route_bounded_orders | credentials=bounded_credentials_required | api=order_api_available",
        "pm_exec": "action=route_live_orders | credentials=live_credentials_required | api=order_api_available",
    }
    assert report.surface.promotion_summaries_by_market_id == {
        "k_exec": "promote->live_execution | rules=4 | current_mode=bounded_live",
        "pm_exec": "promote->none | rules=0 | current_mode=live",
    }
    assert report.surface.blocker_summaries_by_market_id == {
        "k_exec": "no_live_execution_adapter",
        "pm_exec": "none",
    }
    assert report.surface.metadata["credential_gates_by_market_id"] == {
        "k_exec": "bounded_credentials_required",
        "pm_exec": "live_credentials_required",
    }
    assert report.surface.metadata["api_gates_by_market_id"] == {
        "k_exec": "order_api_available",
        "pm_exec": "order_api_available",
    }
    assert report.surface.metadata["missing_requirement_counts_by_market_id"] == {
        "k_exec": 1,
        "pm_exec": 0,
    }
    assert report.surface.metadata["missing_requirement_market_count"] == 1
    assert report.surface.metadata["readiness_scores_by_market_id"] == {
        "k_exec": 4,
        "pm_exec": 5,
    }
    assert report.surface.metadata["operator_checklists_by_market_id"]["pm_exec"] == [
        "action:route_live_orders",
        "credentials:live_credentials_required",
        "api:order_api_available",
    ]
    assert report.surface.metadata["promotion_evidence_by_market_id"]["k_exec"]["live_execution"]["evidence_count"] == 4
    assert report.surface.metadata["manual_execution_contracts_by_market_id"]["k_exec"]["manual_execution_mode"] == "bounded"
    assert report.surface.metadata["manual_execution_contracts_by_market_id"]["pm_exec"]["manual_execution_mode"] == "live"
    assert report.surface.metadata["promotion_ladders_by_market_id"]["k_exec"][0]["pathway"] == "bounded_execution"
    assert report.surface.metadata["promotion_ladders_by_market_id"]["pm_exec"][0]["pathway"] == "live_execution"
    assert report.surface.metadata["credential_gate_counts"] == {
        "bounded_credentials_required": 1,
        "live_credentials_required": 1,
    }
    assert report.surface.metadata["api_gate_counts"] == {
        "order_api_available": 2,
    }
    assert report.surface.metadata["operator_ready_market_count"] == 2
    assert report.surface.metadata["preferred_execution_semantics_counts"] == {
        "live_candidate": 1,
    }
    assert report.surface.metadata["preferred_execution_selection_reason_counts"] == {
        "higher_readiness_stage": 1,
    }
    assert report.surface.metadata["mixed_execution_semantics_counts"] == {
        "mixed_live_and_bounded": 1,
    }
    assert report.surface.metadata["survivability_hint_counts"] == {
        "survivable_with_monitoring": 1,
    }
    assert report.surface.metadata["legging_risk_tier_counts"] == {
        "medium": 1,
    }
    assert report.surface.metadata["multi_leg_blocker_code_counts"] == {
        "hedge_completion_not_ready": 1,
        "medium_legging_risk": 1,
        "multi_leg_missing_requirements": 1,
        "multi_leg_promotion_pending": 1,
        "no_live_execution_adapter": 1,
        "secondary_leg_not_live_ready": 1,
        "unhedged_leg_window:2500": 1,
    }
    assert report.surface.execution_filter_reason_codes == []
    assert report.surface.execution_filter_reason_code_counts == {}
    assert set(report.surface.tradeable_market_ids) == {"pm_exec", "k_exec"}
    assert "m_ref" in report.surface.reference_market_ids
    assert set(report.surface.read_only_market_ids) == {"pm_exec", "k_exec", "m_ref"}

    plan = report.plans[0]
    assert plan.tradeable is True
    assert plan.manual_review_required is False
    assert plan.taxonomy == CrossVenueTaxonomy.true_arbitrage
    assert plan.execution_filter_reason_codes == []
    assert plan.proof is not None
    assert plan.proof.proof_status == MarketEquivalenceProofStatus.proven
    assert plan.executable_edge is not None
    assert plan.executable_edge.executable is True
    assert plan.arb_plan is not None
    assert plan.arb_plan.executable is True
    assert plan.arb_plan.legging_risk is True
    assert plan.arb_plan.hedge_completion_ready is False
    assert "unhedged_leg_window:2500" in plan.arb_plan.legging_risk_reasons
    assert plan.cross_venue_plan is not None
    assert set(plan.execution_market_ids) == {"pm_exec", "k_exec"}
    assert plan.execution_roles_by_market_id == {
        "k_exec": "execution_equivalent",
        "pm_exec": "execution_equivalent",
    }
    assert plan.execution_pathways_by_market_id == {
        "k_exec": "bounded_execution",
        "pm_exec": "live_execution",
    }
    assert plan.readiness_stages_by_market_id == {
        "k_exec": "bounded_ready",
        "pm_exec": "live_ready",
    }
    assert plan.highest_actionable_modes_by_market_id == {
        "k_exec": "bounded_live",
        "pm_exec": "live",
    }
    assert plan.required_operator_actions_by_market_id == {
        "k_exec": "route_bounded_orders",
        "pm_exec": "route_live_orders",
    }
    assert plan.next_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert plan.next_pathway_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert set(plan.bounded_execution_equivalent_market_ids) == {"k_exec", "pm_exec"}
    assert plan.bounded_execution_promotion_candidate_market_ids == []
    assert plan.stage_summaries_by_market_id["k_exec"]["next_pathway"] == "live_execution"
    assert plan.promotion_target_pathways_by_market_id == {
        "k_exec": "live_execution",
        "pm_exec": None,
    }
    assert plan.promotion_rules_by_market_id == {
        "k_exec": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
        "pm_exec": [],
    }
    assert plan.pathway_ladders_by_market_id == {
        "k_exec": ["bounded_execution", "live_execution"],
        "pm_exec": ["live_execution"],
    }
    assert plan.blocked_pathways_by_market_id == {
        "k_exec": ["live_execution"],
        "pm_exec": [],
    }
    assert plan.execution_blocker_codes_by_market_id == {
        "k_exec": ["no_live_execution_adapter"],
        "pm_exec": [],
    }
    assert plan.pathway_summaries_by_market_id == {
        "k_exec": "pathway=bounded_execution | readiness=bounded_ready | next=live_execution | blocked=live_execution",
        "pm_exec": "pathway=live_execution | readiness=live_ready | next=none | blocked=none",
    }
    assert plan.operator_summaries_by_market_id == {
        "k_exec": "action=route_bounded_orders | credentials=bounded_credentials_required | api=order_api_available",
        "pm_exec": "action=route_live_orders | credentials=live_credentials_required | api=order_api_available",
    }
    assert plan.promotion_summaries_by_market_id == {
        "k_exec": "promote->live_execution | rules=4 | current_mode=bounded_live",
        "pm_exec": "promote->none | rules=0 | current_mode=live",
    }
    assert plan.blocker_summaries_by_market_id == {
        "k_exec": "no_live_execution_adapter",
        "pm_exec": "none",
    }
    assert plan.preferred_execution_pathway == "live_execution"
    assert plan.preferred_execution_mode == "live"
    assert plan.preferred_operator_action == "route_live_orders"
    assert plan.preferred_promotion_target_pathway is None
    assert plan.preferred_execution_selection_reason == "higher_readiness_stage"
    assert plan.preferred_pathway_summary.startswith("pathway=live_execution")
    assert plan.preferred_operator_summary == "action=route_live_orders | credentials=live_credentials_required | api=order_api_available"
    assert plan.preferred_promotion_summary.startswith("promote->none")
    assert plan.preferred_blocker_summary == "none"
    assert "selection=higher_readiness_stage" in plan.preferred_execution_summary
    assert "taxonomy=execution_ready" in plan.preferred_execution_capability_summary
    assert plan.preferred_execution_market_id == "pm_exec"
    assert plan.preferred_execution_venue == VenueName.polymarket
    assert plan.metadata["preferred_execution_semantics"] == "live_candidate"
    assert plan.metadata["preferred_execution_selection_reason"] == "higher_readiness_stage"
    assert plan.metadata["mixed_execution_semantics"] == "mixed_live_and_bounded"
    assert plan.metadata["survivability_hint"] == "survivable_with_monitoring"
    assert plan.metadata["survivability_by_market_id"] == {
        "k_exec": "leg_bounded_ready",
        "pm_exec": "leg_live_ready",
    }
    assert plan.metadata["requirement_gap_summary_by_market_id"] == {
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
    assert plan.metadata["credential_gates_by_market_id"] == {
        "k_exec": "bounded_credentials_required",
        "pm_exec": "live_credentials_required",
    }
    assert plan.metadata["api_gates_by_market_id"] == {
        "k_exec": "order_api_available",
        "pm_exec": "order_api_available",
    }
    assert plan.metadata["missing_requirement_counts_by_market_id"] == {
        "k_exec": 1,
        "pm_exec": 0,
    }
    assert plan.metadata["missing_requirement_market_count"] == 1
    assert plan.metadata["readiness_scores_by_market_id"] == {
        "k_exec": 4,
        "pm_exec": 5,
    }
    assert plan.metadata["operator_checklists_by_market_id"]["k_exec"] == [
        "action:route_bounded_orders",
        "gate:live_execution_adapter",
        "promote:prove_live_execution_adapter",
        "promote:prove_live_cancel_path",
        "promote:prove_live_fill_audit",
        "promote:prove_compliance_gates",
        "credentials:bounded_credentials_required",
        "api:order_api_available",
    ]
    assert plan.metadata["promotion_evidence_by_market_id"]["pm_exec"]["live_execution"]["status"] == "current"
    assert plan.metadata["multi_leg_operator_checklist"] == [
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
        "hedge:max_unhedged_leg_ms:2500",
        "hedge:completion_ratio:1.000",
        "hedge:completion_ready:false",
        "hedge:legging_risk_tier:medium",
    ]
    assert plan.metadata["multi_leg_blocker_codes"] == [
        "no_live_execution_adapter",
        "multi_leg_missing_requirements",
        "multi_leg_promotion_pending",
        "secondary_leg_not_live_ready",
        "hedge_completion_not_ready",
        "medium_legging_risk",
        "unhedged_leg_window:2500",
    ]
    assert plan.metadata["legging_risk_tier"] == "medium"
    assert plan.metadata["survivability_summary"] == {
        "mixed_execution_semantics": "mixed_live_and_bounded",
        "survivability_hint": "survivable_with_monitoring",
        "legging_risk_tier": "medium",
        "max_unhedged_leg_ms": 2500,
        "hedge_completion_ratio": 1.0,
        "hedge_completion_ready": False,
        "secondary_leg_count": 1,
        "bounded_leg_count": 1,
        "bindable_leg_count": 0,
        "dry_run_leg_count": 0,
        "blocked_leg_count": 1,
    }
    assert report.tradeable_plans == [plan]
    assert report.surface.execution_routes in ({"left_preferred": 1}, {"right_preferred": 1})
    assert report.plans[0].rationale
    assert report.plans[0].legging_risk_reasons
    assert report.plans[0].content_hash
    assert report.content_hash


def test_multi_venue_executor_roundtrips_persisted_report(tmp_path) -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    left = _market(
        "pm_exec",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=70000.0,
    )
    right = _market(
        "k_exec",
        venue=VenueName.kalshi,
        venue_type=VenueType.execution,
        title="BTC above 120k",
        question="Will BTC trade above 120k by year end 2026?",
        canonical_event_id="btc_120k_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=60000.0,
    )
    report = build_multi_venue_execution_report(
        [left, right],
        snapshots={
            "pm_exec": _snapshot(
                "pm_exec",
                venue=VenueName.polymarket,
                title="BTC above 120k",
                question="Will BTC trade above 120k by year end 2026?",
                price_yes=0.55,
                liquidity=70000.0,
            ),
            "k_exec": _snapshot(
                "k_exec",
                venue=VenueName.kalshi,
                title="BTC above 120k",
                question="Will BTC trade above 120k by year end 2026?",
                price_yes=0.556,
                liquidity=60000.0,
            ),
        },
    )

    persisted = report.persist(tmp_path / "multi_venue_report.json")
    loaded = MultiVenueExecutionReport.load(persisted)

    assert loaded.content_hash == report.content_hash
    assert loaded.report_id == report.report_id
    assert loaded.cross_venue_report.report_id == report.cross_venue_report.report_id
    assert loaded.surface.tradeable_plan_count == report.surface.tradeable_plan_count == 1
    assert loaded.surface.true_arbitrage_plan_count == report.surface.true_arbitrage_plan_count == 1
    assert loaded.surface.execution_filter_reason_codes == report.surface.execution_filter_reason_codes == []
    assert loaded.plans[0].content_hash == report.plans[0].content_hash
    assert loaded.plans[0].taxonomy == report.plans[0].taxonomy == CrossVenueTaxonomy.true_arbitrage
    assert loaded.plans[0].proof is not None
    assert loaded.plans[0].proof.content_hash == report.plans[0].proof.content_hash
    assert loaded.plans[0].executable_edge is not None
    assert loaded.plans[0].executable_edge.content_hash == report.plans[0].executable_edge.content_hash
    assert loaded.plans[0].arb_plan is not None
    assert loaded.plans[0].arb_plan.content_hash == report.plans[0].arb_plan.content_hash
    assert loaded.plans[0].execution_roles_by_market_id == report.plans[0].execution_roles_by_market_id
    assert loaded.plans[0].execution_pathways_by_market_id == report.plans[0].execution_pathways_by_market_id
    assert loaded.plans[0].readiness_stages_by_market_id == report.plans[0].readiness_stages_by_market_id
    assert loaded.plans[0].highest_actionable_modes_by_market_id == report.plans[0].highest_actionable_modes_by_market_id
    assert loaded.plans[0].required_operator_actions_by_market_id == report.plans[0].required_operator_actions_by_market_id
    assert loaded.plans[0].next_pathways_by_market_id == report.plans[0].next_pathways_by_market_id
    assert loaded.plans[0].next_pathway_rules_by_market_id == report.plans[0].next_pathway_rules_by_market_id
    assert loaded.plans[0].bounded_execution_equivalent_market_ids == report.plans[0].bounded_execution_equivalent_market_ids
    assert loaded.plans[0].bounded_execution_promotion_candidate_market_ids == report.plans[0].bounded_execution_promotion_candidate_market_ids
    assert loaded.plans[0].stage_summaries_by_market_id == report.plans[0].stage_summaries_by_market_id
    assert loaded.plans[0].promotion_target_pathways_by_market_id == report.plans[0].promotion_target_pathways_by_market_id
    assert loaded.plans[0].promotion_rules_by_market_id == report.plans[0].promotion_rules_by_market_id
    assert loaded.plans[0].pathway_ladders_by_market_id == report.plans[0].pathway_ladders_by_market_id
    assert loaded.plans[0].blocked_pathways_by_market_id == report.plans[0].blocked_pathways_by_market_id
    assert loaded.plans[0].execution_blocker_codes_by_market_id == report.plans[0].execution_blocker_codes_by_market_id


def test_multi_venue_execution_report_surfaces_taxonomy_and_filter_codes() -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    left = _market(
        "pm_signal",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Signal pair",
        question="Will the signal pair move?",
        canonical_event_id="signal_pair_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=50000.0,
    )
    right = _market(
        "k_signal",
        venue=VenueName.kalshi,
        venue_type=VenueType.execution,
        title="Signal pair",
        question="Will the signal pair move?",
        canonical_event_id="signal_pair_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=45000.0,
    )
    cross_report = build_multi_venue_execution_report([left, right]).cross_venue_report
    execution_report = MultiVenueExecutionReport(
        cross_venue_report=cross_report,
        market_count=2,
        plans=[
            MultiVenueExecutionPlan(
                candidate_id="candidate_signal",
                comparison_id="comparison_signal",
                canonical_event_id="event_signal",
                market_ids=["m1", "m2"],
                execution_market_ids=["m1"],
                execution_like_market_ids=["m1"],
                route="cross_venue_signal",
                tradeable=False,
                manual_review_required=True,
                taxonomy=CrossVenueTaxonomy.cross_venue_signal,
                execution_filter_reason_codes=["execution_like_venue", "manual_review_required", "execution_like_venue"],
                rationale="manual_signal_plan",
            )
        ],
    )

    assert execution_report.surface.cross_venue_signal_plan_count == 1
    assert execution_report.surface.true_arbitrage_plan_count == 0
    assert execution_report.surface.execution_role_counts == {
        "execution_bindable": 1,
        "watchlist": 1,
    }
    assert execution_report.surface.execution_pathway_counts == {
        "execution_bindable_dry_run": 1,
        "watchlist_read_only": 1,
    }
    assert execution_report.surface.readiness_stages_by_market_id == {
        "m1": "bindable_ready",
        "m2": "read_only",
    }
    assert execution_report.surface.readiness_stage_counts == {
        "bindable_ready": 1,
        "read_only": 1,
    }
    assert execution_report.surface.highest_actionable_modes_by_market_id == {
        "m1": "dry_run",
        "m2": None,
    }
    assert execution_report.surface.required_operator_actions_by_market_id == {
        "m1": "run_dry_run_adapter",
        "m2": "monitor_watchlist_only",
    }
    assert execution_report.surface.required_operator_action_counts == {
        "monitor_watchlist_only": 1,
        "run_dry_run_adapter": 1,
    }
    assert execution_report.surface.next_pathways_by_market_id == {
        "m1": "bounded_execution",
        "m2": None,
    }
    assert execution_report.surface.next_pathway_counts == {
        "bounded_execution": 1,
    }
    assert execution_report.surface.next_pathway_rules_by_market_id == {
        "m1": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "m2": [],
    }
    assert execution_report.surface.bounded_execution_equivalent_market_ids == []
    assert execution_report.surface.bounded_execution_promotion_candidate_market_ids == ["m1"]
    assert execution_report.surface.bounded_execution_promotion_candidate_count == 1
    assert execution_report.surface.promotion_target_pathways_by_market_id == {
        "m1": "bounded_execution",
        "m2": None,
    }
    assert execution_report.surface.promotion_rules_by_market_id == {
        "m1": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "m2": [],
    }
    assert execution_report.surface.pathway_ladders_by_market_id == {
        "m1": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
        "m2": ["watchlist_read_only"],
    }
    assert execution_report.surface.blocked_pathways_by_market_id == {
        "m1": ["bounded_execution", "live_execution"],
        "m2": [],
    }
    assert execution_report.plans[0].execution_roles_by_market_id == {
        "m1": "execution_bindable",
        "m2": "watchlist",
    }
    assert execution_report.plans[0].execution_pathways_by_market_id == {
        "m1": "execution_bindable_dry_run",
        "m2": "watchlist_read_only",
    }
    assert execution_report.plans[0].readiness_stages_by_market_id == {
        "m1": "bindable_ready",
        "m2": "read_only",
    }
    assert execution_report.plans[0].highest_actionable_modes_by_market_id == {
        "m1": "dry_run",
        "m2": None,
    }
    assert execution_report.plans[0].required_operator_actions_by_market_id == {
        "m1": "run_dry_run_adapter",
        "m2": "monitor_watchlist_only",
    }
    assert execution_report.plans[0].next_pathways_by_market_id == {
        "m1": "bounded_execution",
        "m2": None,
    }
    assert execution_report.plans[0].next_pathway_rules_by_market_id == {
        "m1": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "m2": [],
    }
    assert execution_report.plans[0].bounded_execution_equivalent_market_ids == []
    assert execution_report.plans[0].bounded_execution_promotion_candidate_market_ids == ["m1"]
    assert execution_report.plans[0].promotion_target_pathways_by_market_id == {
        "m1": "bounded_execution",
        "m2": None,
    }
    assert execution_report.plans[0].promotion_rules_by_market_id == {
        "m1": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "m2": [],
    }
    assert execution_report.plans[0].pathway_ladders_by_market_id == {
        "m1": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
        "m2": ["watchlist_read_only"],
    }
    assert execution_report.plans[0].blocked_pathways_by_market_id == {
        "m1": ["bounded_execution", "live_execution"],
        "m2": [],
    }
    assert execution_report.plans[0].execution_blocker_codes_by_market_id == {
        "m1": ["execution_bindable_only", "no_live_execution_adapter", "no_bounded_execution_adapter"],
        "m2": ["watchlist_only"],
    }
    assert execution_report.surface.execution_filter_reason_codes == [
        "execution_like_venue",
        "manual_review_required",
    ]
    assert execution_report.surface.execution_filter_reason_code_counts == {
        "execution_like_venue": 1,
        "manual_review_required": 1,
    }


def test_multi_venue_executor_surfaces_execution_like_additional_venues_without_overstating_tradeability() -> None:
    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    robinhood = _market(
        "rh_exec_like",
        venue=VenueName.robinhood,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_exec_like",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=25000.0,
    )
    cryptocom = _market(
        "cc_exec_like",
        venue=VenueName.cryptocom,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3",
        question="Will the Fed cut by Q3?",
        canonical_event_id="fed_q3_exec_like",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=22000.0,
    )

    report = build_multi_venue_execution_report(
        [robinhood, cryptocom],
        snapshots={
            "rh_exec_like": _snapshot(
                "rh_exec_like",
                venue=VenueName.robinhood,
                title="Fed cuts by Q3",
                question="Will the Fed cut by Q3?",
                price_yes=0.61,
                liquidity=25000.0,
            ),
            "cc_exec_like": _snapshot(
                "cc_exec_like",
                venue=VenueName.cryptocom,
                title="Fed cuts by Q3",
                question="Will the Fed cut by Q3?",
                price_yes=0.612,
                liquidity=22000.0,
            ),
        },
    )

    assert report.plans
    plan = report.plans[0]
    assert plan.tradeable is False
    assert plan.manual_review_required is True
    assert report.surface.execution_like_plan_count == 1
    assert report.surface.tradeable_plan_count == 0
    assert report.surface.execution_pathway_counts == {
        "execution_bindable_dry_run": 2,
    }
    assert report.surface.readiness_stages_by_market_id == {
        "cc_exec_like": "bindable_ready",
        "rh_exec_like": "bindable_ready",
    }
    assert report.surface.readiness_stage_counts == {
        "bindable_ready": 2,
    }
    assert report.surface.highest_actionable_modes_by_market_id == {
        "cc_exec_like": "dry_run",
        "rh_exec_like": "dry_run",
    }
    assert report.surface.required_operator_actions_by_market_id == {
        "cc_exec_like": "run_dry_run_adapter",
        "rh_exec_like": "run_dry_run_adapter",
    }
    assert report.surface.required_operator_action_counts == {
        "run_dry_run_adapter": 2,
    }
    assert report.surface.next_pathways_by_market_id == {
        "cc_exec_like": "bounded_execution",
        "rh_exec_like": "bounded_execution",
    }
    assert report.surface.next_pathway_counts == {
        "bounded_execution": 2,
    }
    assert report.surface.next_pathway_rules_by_market_id == {
        "cc_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "rh_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
    }
    assert report.surface.bounded_execution_equivalent_market_ids == []
    assert set(report.surface.bounded_execution_promotion_candidate_market_ids) == {
        "cc_exec_like",
        "rh_exec_like",
    }
    assert report.surface.bounded_execution_promotion_candidate_count == 2
    assert report.surface.promotion_target_pathways_by_market_id == {
        "cc_exec_like": "bounded_execution",
        "rh_exec_like": "bounded_execution",
    }
    assert report.surface.promotion_rules_by_market_id == {
        "cc_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "rh_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
    }
    assert report.surface.pathway_ladders_by_market_id == {
        "cc_exec_like": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
        "rh_exec_like": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
    }
    assert report.surface.blocked_pathways_by_market_id == {
        "cc_exec_like": ["bounded_execution", "live_execution"],
        "rh_exec_like": ["bounded_execution", "live_execution"],
    }
    assert plan.execution_pathways_by_market_id == {
        "cc_exec_like": "execution_bindable_dry_run",
        "rh_exec_like": "execution_bindable_dry_run",
    }
    assert plan.readiness_stages_by_market_id == {
        "cc_exec_like": "bindable_ready",
        "rh_exec_like": "bindable_ready",
    }
    assert plan.highest_actionable_modes_by_market_id == {
        "cc_exec_like": "dry_run",
        "rh_exec_like": "dry_run",
    }
    assert plan.required_operator_actions_by_market_id == {
        "cc_exec_like": "run_dry_run_adapter",
        "rh_exec_like": "run_dry_run_adapter",
    }
    assert plan.next_pathways_by_market_id == {
        "cc_exec_like": "bounded_execution",
        "rh_exec_like": "bounded_execution",
    }
    assert plan.next_pathway_rules_by_market_id == {
        "cc_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "rh_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
    }
    assert plan.bounded_execution_equivalent_market_ids == []
    assert set(plan.bounded_execution_promotion_candidate_market_ids) == {
        "cc_exec_like",
        "rh_exec_like",
    }
    assert plan.promotion_target_pathways_by_market_id == {
        "cc_exec_like": "bounded_execution",
        "rh_exec_like": "bounded_execution",
    }
    assert plan.promotion_rules_by_market_id == {
        "cc_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "rh_exec_like": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
    }
    assert plan.pathway_ladders_by_market_id == {
        "cc_exec_like": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
        "rh_exec_like": ["execution_bindable_dry_run", "bounded_execution", "live_execution"],
    }
    assert plan.blocked_pathways_by_market_id == {
        "cc_exec_like": ["bounded_execution", "live_execution"],
        "rh_exec_like": ["bounded_execution", "live_execution"],
    }
    assert plan.execution_blocker_codes_by_market_id == {
        "cc_exec_like": [
            "execution_unsupported",
            "execution_bindable_only",
            "no_live_execution_adapter",
            "no_bounded_execution_adapter",
        ],
        "rh_exec_like": [
            "execution_unsupported",
            "execution_bindable_only",
            "no_live_execution_adapter",
            "no_bounded_execution_adapter",
        ],
    }
    assert plan.preferred_execution_pathway == "execution_bindable_dry_run"
    assert plan.preferred_execution_mode == "dry_run"
    assert plan.preferred_operator_action == "run_dry_run_adapter"
    assert plan.preferred_promotion_target_pathway == "bounded_execution"
    assert "execution_bindable_venue" in plan.execution_filter_reason_codes


def test_multi_venue_executor_surfaces_parent_child_and_natural_hedge_relations() -> None:
    from prediction_markets.cross_venue import CrossVenueIntelligence

    end_date = datetime(2026, 4, 9, 0, 0, tzinfo=timezone.utc)
    parent = _market(
        "pm_parent",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3 2026",
        question="Will the Fed cut rates by Q3 2026?",
        canonical_event_id="fed_family_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=70000.0,
    )
    child = _market(
        "k_child",
        venue=VenueName.kalshi,
        venue_type=VenueType.execution,
        title="Fed cuts by Q3 2026 soon",
        question="Will the Fed cut rates by Q3 2026 soon?",
        canonical_event_id="fed_family_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=65000.0,
    )
    hedge_up = _market(
        "pm_up",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        title="BTC above 120k by year end 2026",
        question="Will BTC rise above 120k by year end 2026?",
        canonical_event_id="btc_hedge_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=60000.0,
    )
    hedge_down = _market(
        "m_down",
        venue=VenueName.kalshi,
        venue_type=VenueType.execution,
        title="BTC below 120k by year end 2026",
        question="Will BTC fall below 120k by year end 2026?",
        canonical_event_id="btc_hedge_2026",
        resolution_source_url="https://example.com/resolution",
        end_date=end_date,
        liquidity=1000.0,
    )
    snapshots = {
        "pm_parent": _snapshot(
            "pm_parent",
            venue=VenueName.polymarket,
            title="Fed cuts by Q3 2026",
            question="Will the Fed cut rates by Q3 2026?",
            price_yes=0.61,
            liquidity=70000.0,
        ),
        "k_child": _snapshot(
            "k_child",
            venue=VenueName.kalshi,
            title="Fed cuts by Q3 2026 soon",
            question="Will the Fed cut rates by Q3 2026 soon?",
            price_yes=0.58,
            liquidity=65000.0,
        ),
        "pm_up": _snapshot(
            "pm_up",
            venue=VenueName.polymarket,
            title="BTC above 120k by year end 2026",
            question="Will BTC rise above 120k by year end 2026?",
            price_yes=0.64,
            liquidity=60000.0,
        ),
        "m_down": _snapshot(
            "m_down",
            venue=VenueName.kalshi,
            title="BTC below 120k by year end 2026",
            question="Will BTC fall below 120k by year end 2026?",
            price_yes=0.29,
            liquidity=1000.0,
        ),
    }

    report = build_multi_venue_execution_report(
        [parent, child, hedge_up, hedge_down],
        snapshots=snapshots,
        cross_venue_intelligence=CrossVenueIntelligence(spread_threshold_bps=500.0),
    )

    assert report.surface.parent_child_relation_group_count == 1
    assert report.surface.natural_hedge_relation_group_count == 1
    assert report.surface.family_relation_group_count == 2
    assert report.surface.parent_child_pair_count == 1
    assert report.surface.natural_hedge_pair_count == 1
    assert set(report.surface.parent_market_ids) == {"pm_parent"}
    assert set(report.surface.child_market_ids) == {"k_child"}
    assert set(report.surface.natural_hedge_market_ids) == {"pm_up", "m_down"}
    assert report.metadata["parent_child_pair_count"] == 1
    assert report.metadata["natural_hedge_pair_count"] == 1
    assert report.metadata["parent_child_relation_group_count"] == 1
    assert report.metadata["natural_hedge_relation_group_count"] == 1
    assert report.metadata["family_relation_group_count"] == 2
    assert report.metadata["family_relation_kind"] == "mixed"
