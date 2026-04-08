from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

import pytest

from prediction_markets.additional_venues import AdditionalVenueRegistry, AdditionalVenueKind, build_additional_venue_registry
from prediction_markets.cross_venue import CrossVenueIntelligence
from prediction_markets.models import MarketDescriptor, MarketSnapshot, MarketStatus
from prediction_markets.models import MarketUniverseConfig, VenueName, VenueType


ALL_BOOTSTRAP_VENUES = [
    VenueName.manifold,
    VenueName.metaculus,
    VenueName.robinhood,
    VenueName.cryptocom,
    VenueName.omen,
    VenueName.augur,
    VenueName.opinion_trade,
]

EXECUTION_LIKE_BOOTSTRAP_VENUES = [
    VenueName.robinhood,
    VenueName.cryptocom,
    VenueName.omen,
    VenueName.augur,
]

DECENTRALIZED_EXECUTION_BOOTSTRAP_VENUES = [
    VenueName.omen,
    VenueName.augur,
]


def test_registry_exposes_expected_bootstrap_venues_and_matrix() -> None:
    registry = build_additional_venue_registry()
    matrix = registry.describe_matrix()

    assert registry.list_venues() == ALL_BOOTSTRAP_VENUES
    assert matrix.read_only_venues() == registry.list_venues()
    assert matrix.paper_capable_venues() == registry.list_venues()
    assert matrix.paper_execution_like_venues() == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert matrix.execution_capable_venues() == []
    assert matrix.positions_capable_venues() == registry.list_venues()
    assert matrix.events_capable_venues() == registry.list_venues()
    assert matrix.venues_supporting("discovery") == registry.list_venues()
    assert matrix.venues_supporting("paper_capable") == registry.list_venues()
    assert matrix.venues_supporting("execution_capable") == []
    assert all(profile.capabilities.read_only for profile in matrix.profiles)
    assert all(profile.capabilities.metadata_map["paper_capable"] for profile in matrix.profiles)
    assert all(profile.capabilities.metadata_map["events_capable"] for profile in matrix.profiles)
    assert not any(profile.capabilities.metadata_map["execution_capable"] for profile in matrix.profiles)
    assert matrix.profile(VenueName.manifold).metadata["venue_type"] == "signal"
    assert matrix.profile(VenueName.metaculus).metadata["venue_type"] == "reference"
    assert matrix.profile(VenueName.robinhood).metadata["venue_type"] == "execution"
    assert matrix.profile(VenueName.omen).metadata["venue_type"] == "execution"
    assert matrix.profile(VenueName.opinion_trade).metadata["venue_type"] == "watchlist"
    assert matrix.profile(VenueName.omen).metadata["venue_taxonomy"] == "decentralized_execution_like"
    assert matrix.profile(VenueName.augur).metadata["tradeability_class"] == "execution_bindable_dry_run"
    assert matrix.profile(VenueName.robinhood).planned_order_types == ["limit"]
    assert matrix.profile(VenueName.cryptocom).planned_order_types == ["limit"]
    assert matrix.profile(VenueName.omen).planned_order_types == ["limit"]
    assert matrix.profile(VenueName.augur).planned_order_types == ["limit"]
    assert matrix.profile(VenueName.robinhood).supported_order_types == []
    assert matrix.profile(VenueName.cryptocom).supported_order_types == []
    assert matrix.profile(VenueName.omen).supported_order_types == []
    assert matrix.profile(VenueName.augur).supported_order_types == []
    assert matrix.profile(VenueName.robinhood).metadata["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert matrix.profile(VenueName.robinhood).metadata["supported_order_types"] == []
    assert matrix.profile(VenueName.metaculus).metadata["api_access"] == [
        "catalog",
        "snapshot",
        "positions",
        "events",
        "evidence",
    ]
    assert matrix.profile(VenueName.opinion_trade).metadata["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert matrix.profile(VenueName.robinhood).capabilities.metadata_map["venue_type"] == "execution"
    assert matrix.profile(VenueName.metaculus).capabilities.metadata_map["venue_type"] == "reference"
    assert matrix.profile(VenueName.omen).capabilities.metadata_map["tradeability_class"] == "execution_bindable_dry_run"
    assert matrix.profile(VenueName.augur).capabilities.metadata_map["venue_taxonomy"] == "decentralized_execution_like"
    assert matrix.profile(VenueName.robinhood).capabilities.metadata_map["planned_order_types"] == ["limit"]
    assert matrix.profile(VenueName.omen).capabilities.metadata_map["planned_order_types"] == ["limit"]
    assert matrix.execution_blocker_codes(VenueName.metaculus) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "reference_only",
        "no_live_websocket",
        "no_trade_surface",
    ]
    assert matrix.execution_blocker_codes(VenueName.manifold) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "signal_only",
    ]
    assert matrix.execution_blocker_codes(VenueName.robinhood) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert matrix.execution_blocker_codes(VenueName.cryptocom) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert matrix.execution_blocker_codes(VenueName.omen) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert matrix.execution_blocker_codes(VenueName.augur) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert matrix.execution_blocker_codes(VenueName.opinion_trade) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "watchlist_only",
    ]
    assert matrix.profile(VenueName.manifold).capabilities.metadata_map["capability_notes"]["execution_notes"] == [
        "No live execution is permitted for signal bootstrap venues."
    ]
    assert matrix.profile(VenueName.robinhood).capabilities.metadata_map["automation_constraints"] == [
        "Read-only bootstrap profile.",
        "No live automation.",
    ]
    assert matrix.profile(VenueName.metaculus).kind == AdditionalVenueKind.reference
    assert matrix.profile(VenueName.robinhood).default_venue_type == VenueType.execution
    assert matrix.profile(VenueName.omen).default_venue_type == VenueType.execution
    assert matrix.reference_venues() == [VenueName.metaculus]
    assert matrix.execution_venues() == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert matrix.execution_bindable_venues() == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert matrix.execution_like_venues() == []
    assert matrix.signal_venues() == [VenueName.manifold, VenueName.opinion_trade]
    assert matrix.watchlist_venues() == registry.list_venues()
    assert matrix.role_classification().execution_venues == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert matrix.role_classification().reference_venues == [VenueName.metaculus]
    assert matrix.role_classification().execution_equivalent_venues == []
    assert matrix.role_classification().execution_bindable_venues == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert matrix.role_classification().execution_like_venues == []
    assert matrix.role_classification().reference_only_venues == [VenueName.metaculus]
    assert matrix.role_classification().watchlist_only_venues == [VenueName.manifold, VenueName.opinion_trade]
    assert matrix.role_classification().execution_pathway == {
        "augur": "execution_bindable_dry_run",
        "cryptocom": "execution_bindable_dry_run",
        "manifold": "signal_read_only",
        "metaculus": "reference_read_only",
        "omen": "execution_bindable_dry_run",
        "opinion_trade": "watchlist_read_only",
        "robinhood": "execution_bindable_dry_run",
    }
    assert matrix.role_classification().execution_pathway_counts == {
        "execution_bindable_dry_run": 4,
        "reference_read_only": 1,
        "signal_read_only": 1,
        "watchlist_read_only": 1,
    }
    assert matrix.role_classification().readiness_stage == {
        "augur": "bindable_ready",
        "cryptocom": "bindable_ready",
        "manifold": "paper_ready",
        "metaculus": "paper_ready",
        "omen": "bindable_ready",
        "opinion_trade": "paper_ready",
        "robinhood": "bindable_ready",
    }
    assert matrix.role_classification().readiness_stage_counts == {
        "bindable_ready": 4,
        "paper_ready": 3,
    }
    assert matrix.role_classification().required_operator_action == {
        "augur": "run_dry_run_adapter",
        "cryptocom": "run_dry_run_adapter",
        "manifold": "consume_signal_only",
        "metaculus": "consume_reference_only",
        "omen": "run_dry_run_adapter",
        "opinion_trade": "monitor_watchlist_only",
        "robinhood": "run_dry_run_adapter",
    }
    assert matrix.role_classification().required_operator_action_counts == {
        "consume_reference_only": 1,
        "consume_signal_only": 1,
        "monitor_watchlist_only": 1,
        "run_dry_run_adapter": 4,
    }
    assert matrix.role_classification().execution_role_counts == {
        "execution_bindable": 4,
        "reference_only": 1,
        "signal_only": 1,
        "watchlist_only": 1,
    }
    assert matrix.role_classification().execution_equivalent_count == 0
    assert matrix.role_classification().execution_bindable_count == 4
    assert matrix.role_classification().execution_like_count == 0
    assert matrix.role_classification().bounded_execution_equivalent_count == 0
    assert matrix.role_classification().bounded_execution_promotion_candidate_count == 4
    assert matrix.role_classification().reference_only_count == 1
    assert matrix.role_classification().watchlist_only_count == 2
    assert matrix.role_classification().venue_types["manifold"] == "signal"
    assert matrix.role_classification().venue_types["metaculus"] == "reference"
    assert matrix.role_classification().venue_types["robinhood"] == "execution"
    assert matrix.role_classification().venue_types["omen"] == "execution"
    assert matrix.role_classification().venue_types["opinion_trade"] == "watchlist"
    assert (
        matrix.role_classification().capability_notes["robinhood"]["execution"]
        == "Read-only bootstrap profile; dry-run binding is available but live execution is not."
    )
    assert matrix.role_classification().metadata["tradeability_map"]["omen"] == "execution_bindable_dry_run"
    assert matrix.role_classification().metadata["venue_taxonomy"]["augur"] == "decentralized_execution_like"
    assert matrix.role_classification().metadata["planning_buckets"]["metaculus"] == "reference-only"
    assert matrix.role_classification().metadata["planning_buckets"]["manifold"] == "watchlist"
    assert matrix.role_classification().metadata["venue_types"]["manifold"] == "signal"
    assert matrix.role_classification().metadata["execution_blocker_codes"]["metaculus"] == [
        "read_only_bootstrap",
        "execution_unsupported",
        "reference_only",
        "no_live_websocket",
        "no_trade_surface",
    ]
    assert matrix.role_classification().metadata["execution_blocker_codes"]["robinhood"] == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert registry.role_classification().signal_venues == [VenueName.manifold, VenueName.opinion_trade]
    assert registry.surface_for(VenueName.manifold).status == "bootstrap_watchlist_read_only"
    assert registry.surface_for(VenueName.metaculus).planning_bucket == "reference-only"
    assert registry.role_classification().execution_bindable_venues == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert registry.execution_like_venues() == []
    assert matrix.surface_map()["robinhood"].status == "bootstrap_execution_bindable"
    assert matrix.surface_map()["robinhood"].execution_readiness == "bootstrap_execution_bindable"
    assert matrix.surface_map()["robinhood"].execution_equivalent is False
    assert matrix.surface_map()["robinhood"].execution_role == "execution_bindable"
    assert matrix.surface_map()["robinhood"].execution_pathway == "execution_bindable_dry_run"
    assert matrix.surface_map()["robinhood"].pathway_modes == ["paper", "dry_run"]
    assert matrix.surface_map()["robinhood"].highest_actionable_mode == "dry_run"
    assert matrix.surface_map()["robinhood"].required_operator_action == "run_dry_run_adapter"
    assert matrix.surface_map()["robinhood"].readiness_stage == "bindable_ready"
    assert matrix.surface_map()["robinhood"].metadata["manual_execution_contract"]["manual_execution_mode"] == "dry_run_adapter"
    assert matrix.surface_map()["robinhood"].metadata["manual_execution_contract"]["allows_dry_run_routing"] is True
    assert matrix.surface_map()["robinhood"].metadata["manual_execution_contract"]["allows_live_order_routing"] is False
    assert matrix.surface_map()["robinhood"].metadata["manual_execution_contract"]["promotion_target_pathway"] == "bounded_execution"
    assert matrix.surface_map()["robinhood"].metadata["promotion_ladder"][0]["pathway"] == "execution_bindable_dry_run"
    assert matrix.surface_map()["robinhood"].metadata["promotion_ladder"][0]["operator_action"] == "run_dry_run_adapter"
    assert matrix.surface_map()["robinhood"].stage_summary["pathway_summary"].startswith("pathway=execution_bindable_dry_run")
    assert matrix.surface_map()["robinhood"].stage_summary["operator_summary"] == "action:run_dry_run_adapter"
    assert matrix.surface_map()["robinhood"].stage_summary["promotion_summary"].startswith("promote->bounded_execution")
    assert matrix.surface_map()["robinhood"].stage_summary["blocker_summary"] == "bounded_execution, live_execution"
    assert matrix.surface_map()["robinhood"].promotion_target_pathway == "bounded_execution"
    assert matrix.surface_map()["robinhood"].promotion_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert matrix.surface_map()["robinhood"].pathway_ladder == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert matrix.surface_map()["robinhood"].blocked_pathways == [
        "bounded_execution",
        "live_execution",
    ]
    assert matrix.surface_map()["robinhood"].next_pathway == "bounded_execution"
    assert matrix.surface_map()["robinhood"].next_pathway_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert matrix.surface_map()["robinhood"].bounded_execution_equivalent is False
    assert matrix.surface_map()["robinhood"].bounded_execution_promotion_candidate is True
    robinhood_stage_summary = matrix.surface_map()["robinhood"].stage_summary
    assert robinhood_stage_summary["execution_pathway"] == "execution_bindable_dry_run"
    assert robinhood_stage_summary["current_pathway"] == "execution_bindable_dry_run"
    assert robinhood_stage_summary["readiness_stage"] == "bindable_ready"
    assert robinhood_stage_summary["highest_actionable_mode"] == "dry_run"
    assert robinhood_stage_summary["required_operator_action"] == "run_dry_run_adapter"
    assert robinhood_stage_summary["credential_gate"] == "not_required_current_mode"
    assert robinhood_stage_summary["api_gate"] == "dry_run_order_api_available"
    assert robinhood_stage_summary["adapter_readiness"] == {
        "paper_mode_ready": True,
        "dry_run_adapter_ready": True,
        "bounded_execution_adapter_ready": False,
        "live_execution_adapter_ready": False,
        "cancel_path_ready": False,
        "fill_audit_ready": True,
        "order_ack_ready": True,
    }
    assert robinhood_stage_summary["execution_requirement_codes"] == [
        "dry_run_adapter",
        "dry_run_order_ack",
        "planned_order_types",
    ]
    assert robinhood_stage_summary["missing_requirement_codes"] == [
        "execution_api",
        "live_execution_adapter",
        "bounded_execution_adapter",
        "supported_order_types",
    ]
    assert robinhood_stage_summary["missing_requirement_count"] == 4
    assert robinhood_stage_summary["operator_checklist"] == [
        "action:run_dry_run_adapter",
        "gate:execution_api",
        "gate:live_execution_adapter",
        "gate:bounded_execution_adapter",
        "gate:supported_order_types",
        "promote:prove_bounded_execution_adapter",
        "promote:prove_cancel_order_path",
        "promote:prove_fill_audit",
        "api:dry_run_order_api_available",
    ]
    assert robinhood_stage_summary["next_pathway"] == "bounded_execution"
    assert robinhood_stage_summary["next_pathway_rules"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert robinhood_stage_summary["next_pathway_rule_count"] == 3
    assert robinhood_stage_summary["promotion_evidence_by_pathway"]["execution_bindable_dry_run"]["status"] == "current"
    assert robinhood_stage_summary["promotion_evidence_by_pathway"]["bounded_execution"]["evidence_count"] == 3
    assert robinhood_stage_summary["promotion_evidence_by_pathway"]["live_execution"]["evidence_count"] == 4
    assert robinhood_stage_summary["bounded_execution_equivalent"] is False
    assert robinhood_stage_summary["bounded_execution_promotion_candidate"] is True
    assert robinhood_stage_summary["operator_ready_now"] is True
    assert robinhood_stage_summary["pathway_ladder"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert robinhood_stage_summary["pathway_count"] == 3
    assert robinhood_stage_summary["blocked_pathways"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert robinhood_stage_summary["blocked_pathway_count"] == 2
    assert robinhood_stage_summary["remaining_pathways"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert robinhood_stage_summary["remaining_pathway_count"] == 2
    assert matrix.surface_map()["robinhood"].promotion_rules_by_pathway == {
        "bounded_execution": [
            "prove_bounded_execution_adapter",
            "prove_cancel_order_path",
            "prove_fill_audit",
        ],
        "live_execution": [
            "prove_live_execution_adapter",
            "prove_live_cancel_path",
            "prove_live_fill_audit",
            "prove_compliance_gates",
        ],
    }
    assert matrix.surface_map()["cryptocom"].execution_equivalent is False
    assert matrix.surface_map()["robinhood"].planned_order_types == ["limit"]
    assert matrix.surface_map()["cryptocom"].planned_order_types == ["limit"]
    assert matrix.surface_map()["omen"].planned_order_types == ["limit"]
    assert matrix.surface_map()["augur"].planned_order_types == ["limit"]
    assert matrix.surface_map()["robinhood"].supported_order_types == []
    assert matrix.surface_map()["cryptocom"].supported_order_types == []
    assert matrix.surface_map()["omen"].supported_order_types == []
    assert matrix.surface_map()["augur"].supported_order_types == []
    assert matrix.surface_map()["omen"].tradeability_class == "execution_bindable_dry_run"
    assert matrix.surface_map()["augur"].venue_taxonomy == "decentralized_execution_like"
    assert matrix.surface_map()["omen"].supports_market_feed is True
    assert matrix.surface_map()["robinhood"].bootstrap_tier == "tier_b"
    assert matrix.surface_map()["robinhood"].bootstrap_role == "event_contract_bootstrap"
    assert matrix.surface_map()["cryptocom"].bootstrap_role == "event_contract_bootstrap"
    assert matrix.surface_map()["omen"].bootstrap_role == "decentralized_execution_bootstrap"
    assert matrix.surface_map()["augur"].bootstrap_role == "decentralized_execution_bootstrap"
    assert matrix.surface_map()["robinhood"].runbook["runbook_id"] == "robinhood_bootstrap_execution_bindable"
    assert matrix.surface_map()["robinhood"].runbook["recommended_action"] == "run_dry_run_adapter"
    assert matrix.surface_map()["metaculus"].runbook["recommended_action"] == "consume_reference_only"
    assert matrix.surface_map()["metaculus"].role_labels == ["reference", "watchlist"]
    assert matrix.surface_map()["metaculus"].execution_equivalent is False
    assert matrix.surface_map()["metaculus"].execution_pathway == "reference_read_only"
    assert matrix.surface_map()["metaculus"].pathway_modes == ["paper"]
    assert matrix.surface_map()["metaculus"].highest_actionable_mode == "paper"
    assert matrix.surface_map()["metaculus"].required_operator_action == "consume_reference_only"
    assert matrix.surface_map()["metaculus"].readiness_stage == "paper_ready"
    assert matrix.surface_map()["metaculus"].promotion_target_pathway is None
    assert matrix.surface_map()["metaculus"].promotion_rules == []
    assert matrix.surface_map()["metaculus"].pathway_ladder == ["reference_read_only"]
    assert matrix.surface_map()["metaculus"].blocked_pathways == []
    assert matrix.surface_map()["metaculus"].promotion_rules_by_pathway == {}
    assert matrix.surface_map()["metaculus"].next_pathway is None
    assert matrix.surface_map()["metaculus"].next_pathway_rules == []
    assert matrix.surface_map()["metaculus"].bounded_execution_equivalent is False
    assert matrix.surface_map()["metaculus"].bounded_execution_promotion_candidate is False
    assert matrix.surface_map()["metaculus"].stage_summary["remaining_pathway_count"] == 0
    assert matrix.surface_map()["manifold"].execution_equivalent is False
    assert matrix.surface_map()["manifold"].execution_pathway == "signal_read_only"
    assert matrix.surface_map()["manifold"].required_operator_action == "consume_signal_only"
    assert matrix.surface_map()["opinion_trade"].execution_pathway == "watchlist_read_only"
    assert matrix.surface_map()["opinion_trade"].required_operator_action == "monitor_watchlist_only"
    assert matrix.surface_map()["robinhood"].execution_blocker_codes == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert matrix.surface_map()["metaculus"].execution_blocker_codes == [
        "read_only_bootstrap",
        "execution_unsupported",
        "reference_only",
        "no_live_websocket",
        "no_trade_surface",
    ]
    assert matrix.surface_map()["robinhood"].metadata["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert matrix.surface_map()["robinhood"].metadata["supported_order_types"] == []
    assert matrix.role_classification().metadata["manual_execution_contracts"]["robinhood"]["manual_execution_mode"] == "dry_run_adapter"
    assert matrix.role_classification().metadata["promotion_ladders"]["robinhood"][0]["pathway"] == "execution_bindable_dry_run"
    assert matrix.role_classification().metadata["promotion_ladders"]["robinhood"][0]["operator_action"] == "run_dry_run_adapter"
    assert matrix.qualifies_for(VenueName.metaculus, VenueType.reference) is True
    assert matrix.qualifies_for(VenueName.opinion_trade, VenueType.signal) is True
    assert matrix.qualifies_for(VenueName.manifold, VenueType.execution) is False
    assert matrix.venues_for_bootstrap_role("decentralized_execution_bootstrap") == DECENTRALIZED_EXECUTION_BOOTSTRAP_VENUES
    assert matrix.venues_for_taxonomy("decentralized_execution_like") == DECENTRALIZED_EXECUTION_BOOTSTRAP_VENUES
    assert matrix.bootstrap_qualified_venues() == registry.list_venues()
    assert matrix.bootstrap_tier_venues() == registry.list_venues()
    bootstrap_map = matrix.bootstrap_qualification_map()
    assert bootstrap_map["manifold"]["bootstrap_tier"] == "tier_b"
    assert bootstrap_map["manifold"]["bootstrap_role"] == "signal_bootstrap"
    assert bootstrap_map["metaculus"]["bootstrap_role"] == "reference_bootstrap"
    assert bootstrap_map["robinhood"]["bootstrap_role"] == "event_contract_bootstrap"
    assert bootstrap_map["cryptocom"]["bootstrap_role"] == "event_contract_bootstrap"
    assert bootstrap_map["omen"]["bootstrap_role"] == "decentralized_execution_bootstrap"
    assert bootstrap_map["augur"]["bootstrap_role"] == "decentralized_execution_bootstrap"
    assert bootstrap_map["opinion_trade"]["bootstrap_role"] == "watchlist_bootstrap"
    assert bootstrap_map["robinhood"]["status"] == "bootstrap_execution_bindable"
    assert bootstrap_map["robinhood"]["execution_readiness"] == "bootstrap_execution_bindable"
    assert bootstrap_map["robinhood"]["execution_equivalent"] is False
    assert bootstrap_map["omen"]["tradeability_class"] == "execution_bindable_dry_run"
    assert bootstrap_map["augur"]["venue_taxonomy"] == "decentralized_execution_like"
    assert bootstrap_map["robinhood"]["execution_blocker_codes"] == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert bootstrap_map["metaculus"]["execution_blocker_codes"] == [
        "read_only_bootstrap",
        "execution_unsupported",
        "reference_only",
        "no_live_websocket",
        "no_trade_surface",
    ]
    assert bootstrap_map["robinhood"]["planned_order_types"] == ["limit"]
    assert bootstrap_map["cryptocom"]["planned_order_types"] == ["limit"]
    assert bootstrap_map["omen"]["planned_order_types"] == ["limit"]
    assert bootstrap_map["augur"]["planned_order_types"] == ["limit"]
    assert bootstrap_map["robinhood"]["supported_order_types"] == []
    assert bootstrap_map["cryptocom"]["supported_order_types"] == []
    assert bootstrap_map["omen"]["supported_order_types"] == []
    assert bootstrap_map["augur"]["supported_order_types"] == []
    assert all(entry["read_only"] is True for entry in bootstrap_map.values())
    assert all(entry["paper_capable"] is True for entry in bootstrap_map.values())
    assert all(entry["execution_capable"] is False for entry in bootstrap_map.values())
    assert all(entry["execution_equivalent"] is False for entry in bootstrap_map.values())
    assert bootstrap_map["robinhood"]["execution_role"] == "execution_bindable"
    assert bootstrap_map["cryptocom"]["execution_role"] == "execution_bindable"
    assert bootstrap_map["omen"]["execution_role"] == "execution_bindable"
    assert bootstrap_map["augur"]["execution_role"] == "execution_bindable"
    assert bootstrap_map["robinhood"]["execution_pathway"] == "execution_bindable_dry_run"
    assert bootstrap_map["robinhood"]["pathway_modes"] == ["paper", "dry_run"]
    assert bootstrap_map["robinhood"]["highest_actionable_mode"] == "dry_run"
    assert bootstrap_map["robinhood"]["required_operator_action"] == "run_dry_run_adapter"
    assert bootstrap_map["robinhood"]["promotion_target_pathway"] == "bounded_execution"
    assert bootstrap_map["robinhood"]["promotion_rules"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert bootstrap_map["robinhood"]["pathway_ladder"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert bootstrap_map["robinhood"]["readiness_stage"] == "bindable_ready"
    assert bootstrap_map["robinhood"]["credential_gate"] == "not_required_current_mode"
    assert bootstrap_map["robinhood"]["api_gate"] == "dry_run_order_api_available"
    assert bootstrap_map["robinhood"]["missing_requirement_count"] == 4
    assert bootstrap_map["robinhood"]["operator_ready_now"] is True
    assert bootstrap_map["robinhood"]["next_pathway"] == "bounded_execution"
    assert bootstrap_map["robinhood"]["next_pathway_rules"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert bootstrap_map["robinhood"]["bounded_execution_equivalent"] is False
    assert bootstrap_map["robinhood"]["bounded_execution_promotion_candidate"] is True
    assert bootstrap_map["robinhood"]["blocked_pathways"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert bootstrap_map["metaculus"]["execution_pathway"] == "reference_read_only"
    assert bootstrap_map["metaculus"]["required_operator_action"] == "consume_reference_only"
    assert bootstrap_map["metaculus"]["promotion_target_pathway"] is None
    assert bootstrap_map["metaculus"]["promotion_rules"] == []
    assert bootstrap_map["metaculus"]["pathway_ladder"] == ["reference_read_only"]
    assert bootstrap_map["metaculus"]["blocked_pathways"] == []
    assert all(entry["positions_capable"] is True for entry in bootstrap_map.values())
    assert all(entry["events_capable"] is True for entry in bootstrap_map.values())
    assert matrix.role_classification().bootstrap_qualified_venues == registry.list_venues()
    assert matrix.role_classification().bootstrap_tier_b_count == 7
    assert matrix.role_classification().bootstrap_roles["robinhood"] == "event_contract_bootstrap"
    assert matrix.role_classification().metadata["bootstrap_tier_b_count"] == 7
    assert matrix.role_classification().metadata["bootstrap_tier_map"]["metaculus"] == "tier_b"
    assert matrix.role_classification().metadata["bootstrap_role_map"]["manifold"] == "signal_bootstrap"
    assert matrix.role_classification().metadata["bootstrap_role_groups"]["decentralized_execution_bootstrap"] == ["omen", "augur"]
    assert matrix.role_classification().metadata["planned_order_types"]["robinhood"] == ["limit"]
    assert matrix.role_classification().metadata["planned_order_types"]["cryptocom"] == ["limit"]
    assert matrix.role_classification().metadata["planned_order_types"]["omen"] == ["limit"]
    assert matrix.role_classification().metadata["planned_order_types"]["augur"] == ["limit"]
    assert matrix.role_classification().metadata["execution_role"]["robinhood"] == "execution_bindable"
    assert matrix.role_classification().metadata["execution_role"]["metaculus"] == "reference_only"
    assert matrix.role_classification().metadata["execution_pathway"]["robinhood"] == "execution_bindable_dry_run"
    assert matrix.role_classification().metadata["execution_pathway"]["metaculus"] == "reference_read_only"
    assert matrix.role_classification().metadata["execution_pathway_counts"] == {
        "execution_bindable_dry_run": 4,
        "reference_read_only": 1,
        "signal_read_only": 1,
        "watchlist_read_only": 1,
    }
    assert matrix.role_classification().metadata["credential_gate"]["robinhood"] == "not_required_current_mode"
    assert matrix.role_classification().metadata["api_gate"]["metaculus"] == "reference_only_surface"
    assert matrix.role_classification().metadata["credential_gate_counts"] == {
        "not_required_current_mode": 4,
        "read_only": 3,
    }
    assert matrix.role_classification().metadata["api_gate_counts"] == {
        "dry_run_order_api_available": 4,
        "reference_only_surface": 1,
        "signal_only_surface": 1,
        "watchlist_only_surface": 1,
    }
    assert matrix.role_classification().metadata["missing_requirement_count_by_venue"]["robinhood"] == 4
    assert matrix.role_classification().metadata["operator_ready_now"]["metaculus"] is True
    assert matrix.role_classification().metadata["operator_ready_count"] == 7
    assert matrix.role_classification().metadata["required_operator_action"]["robinhood"] == "run_dry_run_adapter"
    assert matrix.role_classification().metadata["required_operator_action"]["metaculus"] == "consume_reference_only"
    assert matrix.role_classification().metadata["required_operator_action_counts"] == {
        "consume_reference_only": 1,
        "consume_signal_only": 1,
        "monitor_watchlist_only": 1,
        "run_dry_run_adapter": 4,
    }
    assert matrix.role_classification().metadata["promotion_target_pathway"]["robinhood"] == "bounded_execution"
    assert matrix.role_classification().metadata["promotion_target_pathway"]["metaculus"] is None
    assert matrix.role_classification().metadata["promotion_rules"]["robinhood"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert matrix.role_classification().metadata["pathway_ladder"]["robinhood"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert matrix.role_classification().metadata["blocked_pathways"]["robinhood"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert matrix.role_classification().metadata["execution_role_counts"] == {
        "execution_bindable": 4,
        "reference_only": 1,
        "signal_only": 1,
        "watchlist_only": 1,
    }
    assert matrix.role_classification().metadata["execution_taxonomy_counts"] == {
        "execution_bindable": 4,
        "execution_like": 3,
    }
    assert matrix.role_classification().metadata["api_access"]["robinhood"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert matrix.role_classification().metadata["supported_order_types"]["robinhood"] == []
    assert matrix.role_classification().metadata["supported_order_types"]["cryptocom"] == []


@pytest.mark.parametrize(
    ("venue", "expected_kind", "expected_venue_type"),
    [
        (VenueName.manifold, AdditionalVenueKind.signal, VenueType.signal),
        (VenueName.metaculus, AdditionalVenueKind.reference, VenueType.reference),
        (VenueName.robinhood, AdditionalVenueKind.execution_like, VenueType.execution),
        (VenueName.cryptocom, AdditionalVenueKind.execution_like, VenueType.execution),
        (VenueName.omen, AdditionalVenueKind.execution_like, VenueType.execution),
        (VenueName.augur, AdditionalVenueKind.execution_like, VenueType.execution),
        (VenueName.opinion_trade, AdditionalVenueKind.watchlist, VenueType.watchlist),
    ],
)
def test_bootstrap_adapter_lists_markets_and_normalizes_snapshots(
    tmp_path,
    monkeypatch,
    venue: VenueName,
    expected_kind: AdditionalVenueKind,
    expected_venue_type: VenueType,
) -> None:
    registry = AdditionalVenueRegistry()
    profile = registry.get_profile(venue)
    adapter = registry.get_adapter(venue)
    markets = adapter.list_markets(limit=10)

    assert profile.kind == expected_kind
    assert profile.default_venue_type == expected_venue_type
    assert markets
    assert all(market.venue == venue for market in markets)
    assert all(market.venue_type == expected_venue_type for market in markets)

    market = markets[0]
    positions_path = tmp_path / f"{venue.value}_positions.json"
    positions_path.write_text(
        json.dumps(
            [
                {
                    "market_id": market.market_id,
                    "venue": venue.value,
                    "side": "yes",
                    "quantity": 1.25,
                    "entry_price": 0.5,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(f"{venue.value.upper()}_POSITIONS_PATH", str(positions_path))
    snapshot = adapter.get_snapshot(market.market_id)
    policy = adapter.get_resolution_policy(market.market_id)
    trades = adapter.get_trades(market.market_id)
    events = adapter.get_events(market.market_id)
    positions = adapter.get_positions(market.market_id)
    evidence = adapter.get_evidence(market.market_id)
    health = adapter.health()

    assert snapshot.market_id == market.market_id
    assert snapshot.venue == venue
    assert snapshot.market_implied_probability is not None
    assert 0.0 <= snapshot.market_implied_probability <= 1.0
    assert snapshot.orderbook is not None
    assert policy.market_id == market.market_id
    assert policy.status.value == "clear"
    assert trades and len(trades) == 2
    assert events
    assert any(event.canonical_event_id == market.canonical_event_id for event in events)
    assert positions
    assert positions[0].market_id == market.market_id
    assert evidence and all(item.venue == venue for item in evidence)
    assert health.healthy is True
    assert health.backend_mode == "bootstrap"
    assert health.details["market_count"] >= 1


def test_bootstrap_adapter_filters_and_errors_are_deterministic() -> None:
    registry = build_additional_venue_registry()
    adapter = registry.get_adapter(VenueName.metaculus)
    markets = adapter.list_markets(config=MarketUniverseConfig(venue=VenueName.metaculus, query="btc", limit=5))

    assert markets
    assert all("btc" in market.market_id.lower() or "btc" in market.title.lower() or "btc" in market.question.lower() for market in markets)

    with pytest.raises(KeyError):
        adapter.get_market("missing-market")

    with pytest.raises(KeyError):
        registry.get_adapter(VenueName.custom)


def test_bootstrap_registry_exposes_multi_role_qualification_helpers() -> None:
    registry = build_additional_venue_registry()

    assert registry.reference_venues() == [VenueName.metaculus]
    assert registry.execution_venues() == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert registry.execution_equivalent_venues() == []
    assert registry.role_classification().execution_bindable_venues == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert registry.execution_like_venues() == []
    assert registry.paper_execution_like_venues() == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert registry.signal_venues() == [VenueName.manifold, VenueName.opinion_trade]
    assert registry.watchlist_venues() == registry.list_venues()
    assert registry.read_only_venues() == registry.list_venues()
    assert registry.paper_capable_venues() == registry.list_venues()
    assert registry.execution_capable_venues() == []
    assert registry.positions_capable_venues() == registry.list_venues()
    assert registry.events_capable_venues() == registry.list_venues()
    assert registry.role_classification().execution_equivalent_venues == []
    assert registry.role_classification().execution_bindable_venues == EXECUTION_LIKE_BOOTSTRAP_VENUES
    assert registry.role_classification().execution_like_venues == []
    assert registry.role_classification().reference_only_venues == [VenueName.metaculus]
    assert registry.role_classification().watchlist_only_venues == [VenueName.manifold, VenueName.opinion_trade]
    assert registry.role_classification().execution_equivalent_count == 0
    assert registry.role_classification().execution_bindable_count == 4
    assert registry.role_classification().execution_like_count == 0
    assert registry.role_classification().reference_only_count == 1
    assert registry.role_classification().watchlist_only_count == 2
    assert registry.role_classification().venue_types["metaculus"] == "reference"
    assert registry.role_classification().venue_types["manifold"] == "signal"
    assert registry.role_classification().venue_types["opinion_trade"] == "watchlist"
    assert registry.qualifies_for(VenueName.manifold, VenueType.signal) is True
    assert registry.qualifies_for(VenueName.manifold, VenueType.reference) is False
    assert registry.venues_for_bootstrap_role("decentralized_execution_bootstrap") == DECENTRALIZED_EXECUTION_BOOTSTRAP_VENUES
    assert registry.venues_for_taxonomy("decentralized_execution_like") == DECENTRALIZED_EXECUTION_BOOTSTRAP_VENUES
    assert registry.tradeability_map()["omen"] == "execution_bindable_dry_run"
    assert registry.execution_blocker_codes(VenueName.metaculus) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "reference_only",
        "no_live_websocket",
        "no_trade_surface",
    ]
    assert registry.execution_blocker_codes(VenueName.robinhood) == [
        "read_only_bootstrap",
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
        "planned_order_types_only",
    ]
    assert registry.get_adapter(VenueName.robinhood).describe_capabilities().metadata_map["paper_capable"] is True
    assert registry.get_adapter(VenueName.robinhood).describe_capabilities().metadata_map["venue_type"] == "execution"


def test_bootstrap_tier_b_qualification_is_explicit_and_read_only() -> None:
    registry = build_additional_venue_registry()
    bootstrap_map = registry.bootstrap_qualification_map()

    assert registry.bootstrap_qualified_venues() == ALL_BOOTSTRAP_VENUES
    assert registry.bootstrap_tier_venues() == registry.bootstrap_qualified_venues()
    assert bootstrap_map["manifold"]["bootstrap_tier"] == "tier_b"
    assert bootstrap_map["manifold"]["bootstrap_role"] == "signal_bootstrap"
    assert bootstrap_map["metaculus"]["bootstrap_role"] == "reference_bootstrap"
    assert bootstrap_map["robinhood"]["bootstrap_role"] == "event_contract_bootstrap"
    assert bootstrap_map["cryptocom"]["bootstrap_role"] == "event_contract_bootstrap"
    assert bootstrap_map["omen"]["bootstrap_role"] == "decentralized_execution_bootstrap"
    assert bootstrap_map["augur"]["bootstrap_role"] == "decentralized_execution_bootstrap"
    assert bootstrap_map["opinion_trade"]["bootstrap_role"] == "watchlist_bootstrap"
    assert bootstrap_map["robinhood"]["read_only"] is True
    assert bootstrap_map["cryptocom"]["read_only"] is True
    assert bootstrap_map["omen"]["read_only"] is True
    assert bootstrap_map["augur"]["read_only"] is True
    assert bootstrap_map["manifold"]["read_only"] is True
    assert bootstrap_map["metaculus"]["read_only"] is True
    assert bootstrap_map["opinion_trade"]["read_only"] is True
    assert all(entry["execution_capable"] is False for entry in bootstrap_map.values())
    assert all(entry["execution_equivalent"] is False for entry in bootstrap_map.values())
    assert all(entry["paper_capable"] is True for entry in bootstrap_map.values())
    assert all(entry["positions_capable"] is True for entry in bootstrap_map.values())
    assert all(entry["events_capable"] is True for entry in bootstrap_map.values())
    assert bootstrap_map["robinhood"]["status"] == "bootstrap_execution_bindable"
    assert bootstrap_map["robinhood"]["execution_readiness"] == "bootstrap_execution_bindable"
    assert registry.surface_map()["robinhood"].bootstrap_role == "event_contract_bootstrap"
    assert registry.surface_map()["omen"].bootstrap_role == "decentralized_execution_bootstrap"
    assert registry.surface_map()["augur"].bootstrap_role == "decentralized_execution_bootstrap"
    assert registry.surface_map()["metaculus"].bootstrap_role == "reference_bootstrap"
    assert registry.surface_map()["opinion_trade"].bootstrap_role == "watchlist_bootstrap"
    assert registry.surface_map()["robinhood"].runbook["runbook_id"] == "robinhood_bootstrap_execution_bindable"
    assert registry.role_classification().bootstrap_tier_b_count == 7
    assert registry.role_classification().bootstrap_roles["cryptocom"] == "event_contract_bootstrap"


def test_cross_venue_routing_surface_reports_candidate_and_routes() -> None:
    left = MarketDescriptor(
        market_id="robinhood_test_event",
        venue=VenueName.robinhood,
        venue_type=VenueType.execution,
        title="Will the test event happen?",
        question="Will the test event happen?",
        slug="test-event",
        status=MarketStatus.open,
        source_url="https://example.com/left",
        canonical_event_id="test_event",
        resolution_source="https://example.com/resolution",
        volume=10_000.0,
        liquidity=5_000.0,
        outcomes=["Yes", "No"],
        token_ids=["yes_left", "no_left"],
        active=True,
        closed=False,
    )
    right = MarketDescriptor(
        market_id="metaculus_test_event",
        venue=VenueName.metaculus,
        venue_type=VenueType.reference,
        title="Will the test event happen?",
        question="Will the test event happen?",
        slug="test-event",
        status=MarketStatus.open,
        source_url="https://example.com/right",
        canonical_event_id="test_event",
        resolution_source="https://example.com/resolution",
        volume=9_000.0,
        liquidity=4_500.0,
        outcomes=["Yes", "No"],
        token_ids=["yes_right", "no_right"],
        active=True,
        closed=False,
    )
    snapshots = {
        left.market_id: MarketSnapshot(
            market_id=left.market_id,
            venue=left.venue,
            title=left.title,
            question=left.question,
            snapshot_ts=datetime(2026, 4, 8, tzinfo=timezone.utc),
            price_yes=0.60,
            price_no=0.40,
            midpoint_yes=0.60,
            market_implied_probability=0.60,
        ),
        right.market_id: MarketSnapshot(
            market_id=right.market_id,
            venue=right.venue,
            title=right.title,
            question=right.question,
            snapshot_ts=datetime(2026, 4, 8, tzinfo=timezone.utc),
            price_yes=0.595,
            price_no=0.405,
            midpoint_yes=0.595,
            market_implied_probability=0.595,
        ),
    }

    surface = CrossVenueIntelligence(venue_matrix=build_additional_venue_registry().describe_matrix()).routing_surface(
        [left, right],
        snapshots=snapshots,
    )

    assert surface.market_count == 2
    assert surface.comparable_group_count == 1
    assert surface.execution_candidate_count in {0, 1}
    assert surface.tradeable_candidate_count in {0, 1}
    assert surface.read_only_market_ids == ["robinhood_test_event", "metaculus_test_event"]
    assert surface.planning_buckets["robinhood"] == "execution-bindable"
    assert surface.planning_buckets["metaculus"] == "reference-only"
