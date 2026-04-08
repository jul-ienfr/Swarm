from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.evidence_registry import EvidenceRegistry
from prediction_markets.models import EvidencePacket, MarketDescriptor, RunManifest, VenueName, VenueType
from prediction_markets.paths import PredictionMarketPaths
from prediction_markets.research import ResearchCollector
from prediction_markets.registry import DEFAULT_VENUE_EXECUTION_REGISTRY, RunRegistry, RunRegistryStore


def test_paths_create_expected_layout(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    paths.ensure_layout()

    assert paths.market_catalog_dir.exists()
    assert paths.orderbooks_dir.exists()
    assert paths.trades_dir.exists()
    assert paths.resolution_dir.exists()
    assert paths.evidence_dir.exists()
    assert paths.runs_dir.exists()
    assert paths.reports_dir.exists()
    assert paths.benchmarks_dir.exists()
    assert paths.replay_dir.exists()
    assert paths.run_manifest_path("run_1").name == "manifest.json"
    assert paths.replay_report_path("run_1").name == "report.json"


def test_run_registry_roundtrip(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    paths.ensure_layout()
    store = RunRegistryStore(paths)
    manifest = RunManifest(
        run_id="run_1",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        market_id="pm_test",
        mode="advise",
        inputs={"market_id": "pm_test"},
    )
    manifest_path = paths.run_manifest_path(manifest.run_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    entry = store.record_manifest(manifest, manifest_path=manifest_path)
    loaded = store.get_manifest("run_1")
    listed = store.list_manifests()
    registry = RunRegistry.load(paths.registry_path)

    assert entry.run_id == "run_1"
    assert loaded.run_id == "run_1"
    assert listed[0].run_id == "run_1"
    assert registry.get("run_1") is not None


def test_run_registry_indexes_latest_entries(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    paths.ensure_layout()
    registry = RunRegistry()
    manifest = RunManifest(
        run_id="run_2",
        venue=VenueName.polymarket,
        venue_type=VenueType.execution,
        market_id="pm_test",
        mode="advise",
    )
    manifest_path = paths.run_manifest_path(manifest.run_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    registry.record(manifest, manifest_path=manifest_path)
    assert registry.get("run_2") is not None


def test_execution_registry_distinguishes_polymarket_and_kalshi() -> None:
    polymarket = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(VenueName.polymarket)
    kalshi = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(VenueName.kalshi)
    robinhood = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(VenueName.robinhood)
    metaculus = DEFAULT_VENUE_EXECUTION_REGISTRY.capability_for(VenueName.metaculus)

    assert polymarket.route_supported is True
    assert polymarket.dry_run_supported is True
    assert polymarket.live_execution_supported is True
    assert polymarket.bounded_execution_supported is True
    assert polymarket.venue_type == VenueType.execution
    assert polymarket.qualifies_for(VenueType.execution) is True
    assert kalshi.route_supported is True
    assert kalshi.dry_run_supported is True
    assert kalshi.live_execution_supported is False
    assert kalshi.bounded_execution_supported is True
    assert kalshi.venue_type == VenueType.execution
    assert robinhood.route_supported is True
    assert robinhood.live_execution_supported is False
    assert robinhood.venue_type == VenueType.execution
    assert robinhood.qualifies_for(VenueType.execution) is True
    assert metaculus.route_supported is False
    assert metaculus.venue_type == VenueType.reference
    assert metaculus.qualifies_for(VenueType.reference) is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).status == "live"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).status == "bounded_live"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.metaculus).status == "read_only"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).execution_equivalent is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).execution_equivalent is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).execution_role == "execution_equivalent"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).execution_role == "execution_bindable"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).execution_pathway == "live_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).pathway_modes == ["dry_run", "bounded_live", "live"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).highest_actionable_mode == "live"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).readiness_stage == "live_ready"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).required_operator_action == "route_live_orders"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).stage_summary["credential_gate"] == "live_credentials_required"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).stage_summary["api_gate"] == "order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).stage_summary["missing_requirement_count"] == 0
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).stage_summary["operator_ready_now"] is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).promotion_target_pathway is None
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).promotion_rules == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).pathway_ladder == ["live_execution"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).blocked_pathways == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).next_pathway is None
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).next_pathway_rules == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).bounded_execution_equivalent is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).bounded_execution_promotion_candidate is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).execution_blocker_codes == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).execution_pathway == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).pathway_modes == ["dry_run", "bounded_live"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).highest_actionable_mode == "bounded_live"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).readiness_stage == "bounded_ready"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).required_operator_action == "route_bounded_orders"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).stage_summary["credential_gate"] == "bounded_credentials_required"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).stage_summary["api_gate"] == "order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).stage_summary["missing_requirement_count"] == 1
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).stage_summary["operator_ready_now"] is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).promotion_target_pathway == "live_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).promotion_rules == [
        "prove_live_execution_adapter",
        "prove_live_cancel_path",
        "prove_live_fill_audit",
        "prove_compliance_gates",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).pathway_ladder == [
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).blocked_pathways == [
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).next_pathway == "live_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).next_pathway_rules == [
        "prove_live_execution_adapter",
        "prove_live_cancel_path",
        "prove_live_fill_audit",
        "prove_compliance_gates",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).bounded_execution_equivalent is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).bounded_execution_promotion_candidate is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).execution_blocker_codes == ["no_live_execution_adapter"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).execution_pathway == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).pathway_modes == ["paper", "dry_run"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).highest_actionable_mode == "dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).readiness_stage == "bindable_ready"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).required_operator_action == "run_dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["manual_execution_contract"]["manual_execution_mode"] == "dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["manual_execution_contract"]["allows_dry_run_routing"] is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["promotion_ladder"][0]["pathway"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).stage_summary["credential_gate"] == "not_required_current_mode"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).stage_summary["api_gate"] == "dry_run_order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).pathway_summary.startswith("pathway=execution_bindable_dry_run")
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).operator_summary == "action=run_dry_run_adapter | credentials=not_required_current_mode | api=dry_run_order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).promotion_summary.startswith("promote->bounded_execution")
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).blocker_summary == "execution_unsupported, execution_bindable_only, no_live_execution_adapter, no_bounded_execution_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).stage_summary["missing_requirement_count"] == 3
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).stage_summary["operator_ready_now"] is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).promotion_target_pathway == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).promotion_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).pathway_ladder == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).blocked_pathways == [
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).next_pathway == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).next_pathway_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).bounded_execution_equivalent is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).bounded_execution_promotion_candidate is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).execution_blocker_codes == [
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["manual_execution_contract"]["manual_execution_mode"] == "dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["promotion_ladder"][0]["operator_action"] == "run_dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["pathway_summary"].startswith("pathway=execution_bindable_dry_run")
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["operator_summary"] == "action=run_dry_run_adapter | credentials=not_required_current_mode | api=dry_run_order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).api_access == polymarket.api_access
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supported_order_types == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).metadata["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).rate_limit_notes == polymarket.rate_limit_notes
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).automation_constraints == polymarket.automation_constraints
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).execution_equivalent is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).execution_like is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.cryptocom).execution_equivalent is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.metaculus).execution_equivalent is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).mode_preview["live"] == "live"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).mode_preview["bounded"] == "bounded_live"
    assert polymarket.metadata["venue_type"] == "execution"
    assert kalshi.metadata["venue_type"] == "execution"
    assert robinhood.metadata["venue_type"] == "execution"
    assert metaculus.metadata["venue_type"] == "reference"
    assert polymarket.api_access == [
        "catalog",
        "snapshot",
        "events",
        "evidence",
        "orderbook",
        "trades",
        "positions",
        "orders",
        "cancel",
    ]
    assert polymarket.supported_order_types == ["limit"]
    assert polymarket.metadata["planned_order_types"] == ["limit"]
    assert polymarket.rate_limit_notes == ["Follow venue-specific rate limits and back off on feed or order traffic."]
    assert polymarket.automation_constraints == [
        "Authorization required for live routing.",
        "Compliance approval required for live routing.",
        "Respect venue rate limits.",
    ]
    assert polymarket.metadata["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
        "orders",
        "cancel",
    ]
    assert polymarket.metadata["supported_order_types"] == ["limit"]
    assert polymarket.metadata["order_paths"] == {
        "live": "external_live_api",
        "bounded": "external_bounded_api",
        "cancel": "external_live_cancel_api",
    }
    assert robinhood.metadata["api_access"] == [
        "catalog",
        "snapshot",
        "orderbook",
        "trades",
        "positions",
        "events",
        "evidence",
    ]
    assert robinhood.metadata["supported_order_types"] == []
    assert robinhood.metadata["planned_order_types"] == ["limit"]
    assert robinhood.metadata["mockable_execution_like"] is True
    assert metaculus.metadata["api_access"] == ["catalog", "snapshot", "events", "evidence"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).metadata["supported_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["supported_order_types"] == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["execution_role"] == "execution_bindable"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["execution_pathway"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["required_operator_action"] == "run_dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["promotion_target_pathway"] == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["pathway_ladder"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.kalshi).metadata["execution_blocker_codes"] == [
        "no_live_execution_adapter"
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["cryptocom"]["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["execution_role"] == "execution_bindable"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["metaculus"]["execution_role"] == "reference_only"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["execution_pathway"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["pathway_modes"] == ["paper", "dry_run"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["highest_actionable_mode"] == "dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["required_operator_action"] == "run_dry_run_adapter"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["credential_gate"] == "not_required_current_mode"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["api_gate"] == "dry_run_order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["missing_requirement_count"] == 3
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["operator_ready_now"] is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["promotion_target_pathway"] == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["promotion_rules"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["pathway_ladder"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["blocked_pathways"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["execution_blocker_codes"] == [
        "execution_unsupported",
        "execution_bindable_only",
        "no_live_execution_adapter",
        "no_bounded_execution_adapter",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["metaculus"]["execution_pathway"] == "reference_read_only"
    assert polymarket.metadata["capability_notes"]["execution_notes"] == [
        "Live execution is allowed when authorization and compliance pass."
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).metadata["order_paths"] == {
        "live": "external_live_api",
        "bounded": "external_bounded_api",
        "cancel": "external_live_cancel_api",
    }
    assert kalshi.metadata["capability_notes"]["execution_notes"] == [
        "Bounded execution is supported; live execution is not enabled here."
    ]
    assert metaculus.metadata["capability_notes"]["orderbook_notes"] == [
        "No orderbook is exposed for reference-only venues."
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_discovery is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_orderbook is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_trades is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_execution is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_websocket is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.polymarket).supports_paper_mode is True
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_venues() == [
        VenueName.polymarket,
        VenueName.kalshi,
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.reference_venues() == [VenueName.metaculus]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.signal_venues() == [VenueName.manifold, VenueName.opinion_trade]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.read_only_venues() == [VenueName.metaculus, VenueName.manifold, VenueName.opinion_trade]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_equivalent_venues() == [
        VenueName.polymarket,
        VenueName.kalshi,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_bindable_venues() == [
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_like_venues() == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.cryptocom).metadata["planned_order_types"] == ["limit"]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.paper_execution_like_venues() == [
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.venues_for_bootstrap_role("event_contract_bootstrap") == [
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.tradeability_map()["robinhood"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.tradeability_map()["cryptocom"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_bindable_venues == [
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_like_venues == []
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_role["polymarket"] == "execution_equivalent"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_role["robinhood"] == "execution_bindable"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_pathway["polymarket"] == "live_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_pathway["kalshi"] == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_pathway["robinhood"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_pathway["metaculus"] == "reference_read_only"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().readiness_stage == {
        "cryptocom": "bindable_ready",
        "kalshi": "bounded_ready",
        "manifold": "read_only",
        "metaculus": "read_only",
        "opinion_trade": "read_only",
        "polymarket": "live_ready",
        "robinhood": "bindable_ready",
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().readiness_stage_counts == {
        "bounded_ready": 1,
        "bindable_ready": 2,
        "live_ready": 1,
        "read_only": 3,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().required_operator_action == {
        "cryptocom": "run_dry_run_adapter",
        "kalshi": "route_bounded_orders",
        "manifold": "consume_signal_only",
        "metaculus": "consume_reference_only",
        "opinion_trade": "monitor_watchlist_only",
        "polymarket": "route_live_orders",
        "robinhood": "run_dry_run_adapter",
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_role_counts == {
        "execution_equivalent": 2,
        "execution_bindable": 2,
        "reference_only": 1,
        "signal_only": 1,
        "watchlist_only": 1,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_pathway_counts == {
        "bounded_execution": 1,
        "execution_bindable_dry_run": 2,
        "live_execution": 1,
        "reference_read_only": 1,
        "signal_read_only": 1,
        "watchlist_read_only": 1,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().required_operator_action_counts == {
        "consume_reference_only": 1,
        "consume_signal_only": 1,
        "monitor_watchlist_only": 1,
        "route_bounded_orders": 1,
        "route_live_orders": 1,
        "run_dry_run_adapter": 2,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["promotion_target_pathway"]["polymarket"] is None
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["promotion_target_pathway"]["kalshi"] == "live_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["promotion_target_pathway"]["robinhood"] == "bounded_execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["credential_gate"]["polymarket"] == "live_credentials_required"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["api_gate"]["robinhood"] == "dry_run_order_api_available"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["credential_gate_counts"] == {
        "bounded_credentials_required": 1,
        "live_credentials_required": 1,
        "not_required_current_mode": 2,
        "read_only": 3,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["api_gate_counts"] == {
        "dry_run_order_api_available": 2,
        "order_api_available": 2,
        "reference_only_surface": 1,
        "signal_only_surface": 1,
        "watchlist_only_surface": 1,
    }
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["missing_requirement_count_by_venue"]["kalshi"] == 1
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["operator_ready_now"]["metaculus"] is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["operator_ready_count"] == 4
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["promotion_rules"]["robinhood"] == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["pathway_ladder"]["robinhood"] == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().metadata["blocked_pathways"]["kalshi"] == [
        "live_execution",
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.reference_only_venues() == [VenueName.metaculus]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.watchlist_only_venues() == [VenueName.manifold, VenueName.opinion_trade]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_equivalent_count == 2
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_like_count == 0
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().execution_bindable_count == 2
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().bounded_execution_equivalent_count == 2
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().bounded_execution_promotion_candidate_count == 2
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().reference_only_count == 1
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().watchlist_only_count == 2
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().venue_types["polymarket"] == "execution"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().venue_types["metaculus"] == "reference"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.role_classification().venue_types["manifold"] == "signal"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.paper_capable_venues() == [
        VenueName.polymarket,
        VenueName.kalshi,
        VenueName.robinhood,
        VenueName.cryptocom,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_capable_venues() == [
        VenueName.polymarket,
        VenueName.kalshi,
    ]
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["robinhood"]["execution_equivalent"] is False
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.bootstrap_qualification_map()["cryptocom"]["execution_equivalent"] is False
    coverage = DEFAULT_VENUE_EXECUTION_REGISTRY.coverage_report()
    assert coverage.venue_count >= 6
    assert coverage.execution_capable_count == 2
    assert coverage.paper_capable_count >= 4
    assert coverage.degraded_venue_count >= 1
    assert 0.0 <= coverage.degraded_venue_rate <= 1.0
    assert coverage.metadata_gap_count >= 0
    assert 0.0 <= coverage.metadata_gap_rate <= 1.0
    assert coverage.execution_surface_rate == pytest.approx(2 / coverage.venue_count, rel=1e-3)
    assert coverage.availability_by_venue["polymarket"].required_operator_action == "route_live_orders"
    assert coverage.availability_by_venue["polymarket"].readiness_stage == "live_ready"
    assert coverage.availability_by_venue["polymarket"].stage_summary["remaining_pathway_count"] == 0
    assert coverage.availability_by_venue["robinhood"].required_operator_action == "run_dry_run_adapter"
    assert coverage.availability_by_venue["robinhood"].readiness_stage == "bindable_ready"
    assert coverage.availability_by_venue["robinhood"].promotion_target_pathway == "bounded_execution"
    assert coverage.availability_by_venue["robinhood"].promotion_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert coverage.availability_by_venue["robinhood"].pathway_ladder == [
        "execution_bindable_dry_run",
        "bounded_execution",
        "live_execution",
    ]
    assert coverage.availability_by_venue["robinhood"].blocked_pathways == [
        "bounded_execution",
        "live_execution",
    ]
    assert coverage.availability_by_venue["robinhood"].next_pathway == "bounded_execution"
    assert coverage.availability_by_venue["robinhood"].next_pathway_rules == [
        "prove_bounded_execution_adapter",
        "prove_cancel_order_path",
        "prove_fill_audit",
    ]
    assert coverage.availability_by_venue["robinhood"].bounded_execution_equivalent is False
    assert coverage.availability_by_venue["robinhood"].bounded_execution_promotion_candidate is True
    assert coverage.availability_by_venue["robinhood"].stage_summary["next_pathway_rule_count"] == 3
    assert coverage.metadata["required_operator_action_counts"] == {
        "consume_reference_only": 1,
        "consume_signal_only": 1,
        "monitor_watchlist_only": 1,
        "route_bounded_orders": 1,
        "route_live_orders": 1,
        "run_dry_run_adapter": 2,
    }
    assert coverage.metadata["credential_gate_counts"] == {
        "bounded_credentials_required": 1,
        "live_credentials_required": 1,
        "not_required_current_mode": 2,
        "read_only": 3,
    }
    assert coverage.metadata["api_gate_counts"] == {
        "dry_run_order_api_available": 2,
        "order_api_available": 2,
        "reference_only_surface": 1,
        "signal_only_surface": 1,
        "watchlist_only_surface": 1,
    }
    assert coverage.metadata["missing_requirement_count_by_venue"] == {
        "cryptocom": 3,
        "kalshi": 1,
        "manifold": 2,
        "metaculus": 2,
        "opinion_trade": 2,
        "polymarket": 0,
        "robinhood": 3,
    }
    assert coverage.metadata["promotion_target_pathway"]["robinhood"] == "bounded_execution"
    assert coverage.metadata["pathway_ladder"]["kalshi"] == [
        "bounded_execution",
        "live_execution",
    ]
    assert coverage.metadata["readiness_stage_counts"] == {
        "bounded_ready": 1,
        "bindable_ready": 2,
        "live_ready": 1,
        "read_only": 3,
    }
    assert coverage.availability_by_venue["polymarket"].status == "live"
    assert coverage.availability_by_venue["polymarket"].availability_score > 0.0
    assert coverage.availability_by_venue["metaculus"].execution_readiness == "reference_only"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["tradeability_class"] == "execution_bindable_dry_run"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.robinhood).metadata["venue_taxonomy"] == "event_contract_bootstrap"
    assert DEFAULT_VENUE_EXECUTION_REGISTRY.execution_surface(VenueName.metaculus).metadata["tradeability_class"] == "reference_only"


def test_execution_registry_exposes_tier_b_bootstrap_roles_without_live_support() -> None:
    registry = DEFAULT_VENUE_EXECUTION_REGISTRY
    bootstrap_map = registry.bootstrap_qualification_map()

    assert registry.bootstrap_qualified_venues() == [
        VenueName.robinhood,
        VenueName.cryptocom,
        VenueName.metaculus,
        VenueName.manifold,
        VenueName.opinion_trade,
    ]
    assert registry.bootstrap_tier_venues() == registry.bootstrap_qualified_venues()
    assert bootstrap_map["robinhood"]["bootstrap_tier"] == "tier_b"
    assert bootstrap_map["robinhood"]["bootstrap_role"] == "event_contract_bootstrap"


def test_execution_registry_materializes_canonical_venue_capabilities() -> None:
    registry = DEFAULT_VENUE_EXECUTION_REGISTRY
    bootstrap_map = registry.bootstrap_qualification_map()
    capabilities = DEFAULT_VENUE_EXECUTION_REGISTRY.canonical_capabilities(VenueName.polymarket)
    robinhood_capabilities = DEFAULT_VENUE_EXECUTION_REGISTRY.canonical_capabilities(VenueName.robinhood)

    assert capabilities.venue == VenueName.polymarket
    assert capabilities.venue_type == VenueType.execution
    assert capabilities.supports_discovery is True
    assert capabilities.supports_orderbook is True
    assert capabilities.supports_trades is True
    assert capabilities.supports_positions is True
    assert capabilities.supports_execution is True
    assert capabilities.supports_paper_mode is True
    assert capabilities.supports_events is True
    assert capabilities.supports_market_feed is True
    assert capabilities.supports_replay is True
    assert capabilities.rate_limit_notes == [
        "Follow venue-specific rate limits and back off on feed or order traffic."
    ]
    assert capabilities.automation_constraints == [
        "Authorization required for live routing.",
        "Compliance approval required for live routing.",
        "Respect venue rate limits.",
    ]
    assert capabilities.metadata_map["venue_type"] == "execution"
    assert capabilities.metadata_map["supports_positions"] is True
    assert capabilities.metadata_map["supports_events"] is True
    assert robinhood_capabilities.metadata_map["tradeability_class"] == "execution_bindable_dry_run"
    assert robinhood_capabilities.metadata_map["venue_taxonomy"] == "event_contract_bootstrap"
    assert robinhood_capabilities.metadata_map["supports_market_feed"] is True
    assert robinhood_capabilities.metadata_map["supports_user_feed"] is False
    assert robinhood_capabilities.metadata_map["supports_rtds"] is False
    assert robinhood_capabilities.metadata_map["supports_paper_mode"] is True
    assert bootstrap_map["cryptocom"]["bootstrap_role"] == "event_contract_bootstrap"
    assert bootstrap_map["metaculus"]["bootstrap_role"] == "reference_bootstrap"
    assert bootstrap_map["manifold"]["bootstrap_role"] == "signal_bootstrap"
    assert bootstrap_map["opinion_trade"]["bootstrap_role"] == "watchlist_bootstrap"
    assert bootstrap_map["robinhood"]["tradeability_class"] == "execution_bindable_dry_run"
    assert bootstrap_map["cryptocom"]["tradeability_class"] == "execution_bindable_dry_run"
    assert bootstrap_map["metaculus"]["tradeability_class"] == "reference_only"
    assert bootstrap_map["manifold"]["tradeability_class"] == "signal_only"
    assert bootstrap_map["robinhood"]["venue_taxonomy"] == "event_contract_bootstrap"
    assert bootstrap_map["metaculus"]["venue_taxonomy"] == "reference_bootstrap"
    assert bootstrap_map["robinhood"]["execution_equivalent"] is False
    assert bootstrap_map["cryptocom"]["execution_equivalent"] is False
    assert bootstrap_map["robinhood"]["execution_readiness"] == "bindable_ready"
    assert bootstrap_map["robinhood"]["live_execution_supported"] is False
    assert bootstrap_map["cryptocom"]["live_execution_supported"] is False
    assert bootstrap_map["metaculus"]["live_execution_supported"] is False
    assert bootstrap_map["manifold"]["live_execution_supported"] is False
    assert bootstrap_map["opinion_trade"]["live_execution_supported"] is False
    assert bootstrap_map["robinhood"]["paper_capable"] is True
    assert bootstrap_map["cryptocom"]["paper_capable"] is True
    assert bootstrap_map["metaculus"]["paper_capable"] is False
    assert bootstrap_map["manifold"]["paper_capable"] is False
    assert bootstrap_map["opinion_trade"]["paper_capable"] is False
    assert registry.execution_surface(VenueName.robinhood).bootstrap_tier == "tier_b"
    assert registry.execution_surface(VenueName.robinhood).bootstrap_role == "event_contract_bootstrap"
    assert registry.execution_surface(VenueName.metaculus).bootstrap_role == "reference_bootstrap"
    assert registry.execution_surface(VenueName.manifold).bootstrap_role == "signal_bootstrap"
    assert registry.execution_surface(VenueName.opinion_trade).bootstrap_role == "watchlist_bootstrap"


def test_evidence_registry_records_runtime_metadata_and_audit(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    collector = ResearchCollector(venue=VenueName.polymarket)
    evidence = collector.from_notes(
        market_id="pm_test",
        notes=["Bullish signal for registry"],
        run_id="run_registry",
    )[0]

    registry = EvidenceRegistry(paths)
    registry.add(evidence)
    index = registry.load_index()
    audit = registry.audit()

    assert index.entries[0].content_hash
    assert index.entries[0].stored_at is not None
    assert index.entries[0].size_bytes > 0
    assert registry.list_by_content_hash(index.entries[0].content_hash or "")[0].evidence_id == evidence.evidence_id
    assert audit.healthy is True
    assert audit.total_entries == 1
    assert audit.markets == ["pm_test"]


def test_evidence_registry_accepts_canonical_provenance_bundle_metadata(tmp_path: Path) -> None:
    paths = PredictionMarketPaths(root=tmp_path / "prediction_markets")
    collector = ResearchCollector(venue=VenueName.polymarket)
    bundle = collector.bridge_bundle(
        ["Bullish signal for provenance"],
        market_id="pm_provenance",
        run_id="run_provenance",
        social_context_refs=["ctx-1"],
        packet_refs={"forecast": "fcst_1"},
    )
    evidence = collector.from_notes(
        market_id="pm_provenance",
        notes=["Bullish signal for provenance"],
        run_id="run_provenance",
    )[0]
    evidence = EvidencePacket.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "metadata": {
                **evidence.metadata,
                "provenance_bundle": bundle.provenance_bundle.model_dump(mode="json") if bundle.provenance_bundle is not None else None,
                "provenance_bundle_content_hash": bundle.provenance_bundle.content_hash if bundle.provenance_bundle is not None else "",
            },
        }
    )

    registry = EvidenceRegistry(paths)
    registry.add(evidence)
    audit = registry.audit()

    assert audit.healthy is True
    assert audit.provenance_bundle_hash_mismatches == []
