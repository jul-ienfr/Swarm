from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .cross_venue import (
    CrossVenueExecutionCandidate,
    CrossVenueExecutionPlan,
    CrossVenueIntelligence,
    CrossVenueIntelligenceReport,
    CrossVenueTaxonomy,
)
from .execution_edge import (
    ArbPlan,
    ExecutableEdge,
    MarketEquivalenceProof,
    MarketEquivalenceProofStatus,
    assess_market_equivalence,
    build_arb_plan,
    derive_executable_edge,
)
from .market_graph import ComparableMarketGroup, MarketGraphBuilder
from .models import MarketDescriptor, MarketSnapshot, VenueName, _stable_content_hash, _normalized_text, _utc_now


class MultiVenueExecutionSurface(BaseModel):
    schema_version: str = "v1"
    report_id: str | None = None
    market_count: int = 0
    comparable_group_count: int = 0
    parent_child_relation_group_count: int = 0
    natural_hedge_relation_group_count: int = 0
    family_relation_group_count: int = 0
    execution_candidate_count: int = 0
    execution_plan_count: int = 0
    tradeable_plan_count: int = 0
    execution_equivalent_plan_count: int = 0
    execution_like_plan_count: int = 0
    execution_routes: dict[str, int] = Field(default_factory=dict)
    execution_role_counts: dict[str, int] = Field(default_factory=dict)
    execution_roles_by_market_id: dict[str, str] = Field(default_factory=dict)
    execution_pathway_counts: dict[str, int] = Field(default_factory=dict)
    execution_pathways_by_market_id: dict[str, str] = Field(default_factory=dict)
    readiness_stages_by_market_id: dict[str, str] = Field(default_factory=dict)
    readiness_stage_counts: dict[str, int] = Field(default_factory=dict)
    highest_actionable_modes_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    required_operator_actions_by_market_id: dict[str, str] = Field(default_factory=dict)
    required_operator_action_counts: dict[str, int] = Field(default_factory=dict)
    next_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    next_pathway_counts: dict[str, int] = Field(default_factory=dict)
    next_pathway_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    bounded_execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    bounded_execution_equivalent_count: int = 0
    bounded_execution_promotion_candidate_market_ids: list[str] = Field(default_factory=list)
    bounded_execution_promotion_candidate_count: int = 0
    stage_summaries_by_market_id: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pathway_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    operator_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    promotion_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    blocker_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    promotion_target_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    promotion_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    pathway_ladders_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    blocked_pathways_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    execution_blocker_codes_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    tradeable_market_ids: list[str] = Field(default_factory=list)
    read_only_market_ids: list[str] = Field(default_factory=list)
    reference_market_ids: list[str] = Field(default_factory=list)
    signal_market_ids: list[str] = Field(default_factory=list)
    execution_market_ids: list[str] = Field(default_factory=list)
    execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    execution_like_market_ids: list[str] = Field(default_factory=list)
    parent_market_ids: list[str] = Field(default_factory=list)
    child_market_ids: list[str] = Field(default_factory=list)
    natural_hedge_market_ids: list[str] = Field(default_factory=list)
    comparison_only_plan_count: int = 0
    relative_value_plan_count: int = 0
    cross_venue_signal_plan_count: int = 0
    true_arbitrage_plan_count: int = 0
    legging_risk_plan_count: int = 0
    hedge_completion_ready_plan_count: int = 0
    parent_child_pair_count: int = 0
    natural_hedge_pair_count: int = 0
    max_unhedged_leg_ms_max: int = 0
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    execution_filter_reason_code_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultiVenueExecutionPlan(BaseModel):
    schema_version: str = "v1"
    execution_plan_id: str = Field(default_factory=lambda: f"mvplan_{uuid4().hex[:12]}")
    candidate_id: str
    comparison_id: str
    canonical_event_id: str
    market_ids: list[str] = Field(default_factory=list)
    read_only_market_ids: list[str] = Field(default_factory=list)
    reference_market_ids: list[str] = Field(default_factory=list)
    signal_market_ids: list[str] = Field(default_factory=list)
    execution_market_ids: list[str] = Field(default_factory=list)
    execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    execution_like_market_ids: list[str] = Field(default_factory=list)
    parent_market_ids: list[str] = Field(default_factory=list)
    child_market_ids: list[str] = Field(default_factory=list)
    natural_hedge_market_ids: list[str] = Field(default_factory=list)
    venue_roles: dict[str, list[str]] = Field(default_factory=dict)
    route: str = "comparison_only"
    tradeable: bool = False
    manual_review_required: bool = True
    max_unhedged_leg_ms: int = 0
    hedge_completion_ratio: float = 0.0
    hedge_completion_ready: bool = False
    parent_child_pair_count: int = 0
    natural_hedge_pair_count: int = 0
    family_relation_group_count: int = 0
    legging_risk_reasons: list[str] = Field(default_factory=list)
    taxonomy: CrossVenueTaxonomy = CrossVenueTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    execution_roles_by_market_id: dict[str, str] = Field(default_factory=dict)
    execution_pathways_by_market_id: dict[str, str] = Field(default_factory=dict)
    readiness_stages_by_market_id: dict[str, str] = Field(default_factory=dict)
    highest_actionable_modes_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    required_operator_actions_by_market_id: dict[str, str] = Field(default_factory=dict)
    next_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    next_pathway_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    bounded_execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    bounded_execution_promotion_candidate_market_ids: list[str] = Field(default_factory=list)
    stage_summaries_by_market_id: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pathway_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    operator_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    promotion_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    blocker_summaries_by_market_id: dict[str, str] = Field(default_factory=dict)
    promotion_target_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    promotion_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    pathway_ladders_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    blocked_pathways_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    execution_blocker_codes_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    preferred_execution_pathway: str | None = None
    preferred_execution_mode: str | None = None
    preferred_operator_action: str | None = None
    preferred_promotion_target_pathway: str | None = None
    preferred_execution_selection_reason: str = ""
    preferred_pathway_summary: str = ""
    preferred_operator_summary: str = ""
    preferred_promotion_summary: str = ""
    preferred_blocker_summary: str = ""
    preferred_execution_summary: str = ""
    preferred_execution_capability_summary: str = ""
    preferred_execution_market_id: str | None = None
    preferred_execution_venue: VenueName | None = None
    cross_venue_plan: CrossVenueExecutionPlan | None = None
    proof: MarketEquivalenceProof | None = None
    executable_edge: ExecutableEdge | None = None
    arb_plan: ArbPlan | None = None
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "MultiVenueExecutionPlan":
        self.candidate_id = _normalized_text(self.candidate_id)
        self.comparison_id = _normalized_text(self.comparison_id)
        self.canonical_event_id = _normalized_text(self.canonical_event_id)
        self.market_ids = _dedupe(self.market_ids)
        self.read_only_market_ids = _dedupe(self.read_only_market_ids)
        self.reference_market_ids = _dedupe(self.reference_market_ids)
        self.signal_market_ids = _dedupe(self.signal_market_ids)
        self.execution_market_ids = _dedupe(self.execution_market_ids)
        self.execution_equivalent_market_ids = _dedupe(self.execution_equivalent_market_ids)
        self.execution_like_market_ids = _dedupe(self.execution_like_market_ids)
        self.parent_market_ids = _dedupe(self.parent_market_ids)
        self.child_market_ids = _dedupe(self.child_market_ids)
        self.natural_hedge_market_ids = _dedupe(self.natural_hedge_market_ids)
        self.route = _normalized_text(self.route) or "comparison_only"
        self.execution_filter_reason_codes = _dedupe(self.execution_filter_reason_codes)
        if self.cross_venue_plan is not None:
            self.tradeable = bool(self.tradeable or self.cross_venue_plan.tradeable)
            self.manual_review_required = bool(self.manual_review_required or not self.cross_venue_plan.tradeable)
            if self.taxonomy == CrossVenueTaxonomy.comparison_only:
                self.taxonomy = self.cross_venue_plan.taxonomy
            self.execution_filter_reason_codes = _dedupe([
                *self.execution_filter_reason_codes,
                *self.cross_venue_plan.execution_filter_reason_codes,
            ])
            if not self.venue_roles:
                self.venue_roles = dict(self.cross_venue_plan.venue_roles)
            if not self.execution_equivalent_market_ids:
                self.execution_equivalent_market_ids = list(self.cross_venue_plan.execution_equivalent_market_ids)
            if not self.execution_like_market_ids:
                self.execution_like_market_ids = list(self.cross_venue_plan.execution_like_market_ids)
            if not self.execution_roles_by_market_id:
                self.execution_roles_by_market_id = dict(
                    getattr(self.cross_venue_plan, "execution_roles_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("execution_roles_by_market_id", {})
                )
            if not self.execution_pathways_by_market_id:
                self.execution_pathways_by_market_id = dict(
                    getattr(self.cross_venue_plan, "execution_pathways_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("execution_pathways_by_market_id", {})
                )
            if not self.readiness_stages_by_market_id:
                self.readiness_stages_by_market_id = dict(
                    getattr(self.cross_venue_plan, "readiness_stages_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("readiness_stages_by_market_id", {})
                )
            if not self.highest_actionable_modes_by_market_id:
                self.highest_actionable_modes_by_market_id = dict(
                    getattr(self.cross_venue_plan, "highest_actionable_modes_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("highest_actionable_modes_by_market_id", {})
                )
            if not self.required_operator_actions_by_market_id:
                self.required_operator_actions_by_market_id = dict(
                    getattr(self.cross_venue_plan, "required_operator_actions_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("required_operator_actions_by_market_id", {})
                )
            if not self.next_pathways_by_market_id:
                self.next_pathways_by_market_id = dict(
                    getattr(self.cross_venue_plan, "next_pathways_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("next_pathways_by_market_id", {})
                )
            if not self.next_pathway_rules_by_market_id:
                self.next_pathway_rules_by_market_id = {
                    key: list(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "next_pathway_rules_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("next_pathway_rules_by_market_id", {})
                    ).items()
                }
            if not self.bounded_execution_equivalent_market_ids:
                self.bounded_execution_equivalent_market_ids = list(
                    getattr(self.cross_venue_plan, "bounded_execution_equivalent_market_ids", [])
                    or self.cross_venue_plan.metadata.get("bounded_execution_equivalent_market_ids", [])
                )
            if not self.bounded_execution_promotion_candidate_market_ids:
                self.bounded_execution_promotion_candidate_market_ids = list(
                    getattr(self.cross_venue_plan, "bounded_execution_promotion_candidate_market_ids", [])
                    or self.cross_venue_plan.metadata.get("bounded_execution_promotion_candidate_market_ids", [])
                )
            if not self.stage_summaries_by_market_id:
                self.stage_summaries_by_market_id = {
                    key: dict(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "stage_summaries_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("stage_summaries_by_market_id", {})
                    ).items()
                }
            if not self.promotion_target_pathways_by_market_id:
                self.promotion_target_pathways_by_market_id = dict(
                    getattr(self.cross_venue_plan, "promotion_target_pathways_by_market_id", {})
                    or self.cross_venue_plan.metadata.get("promotion_target_pathways_by_market_id", {})
                )
            if not self.promotion_rules_by_market_id:
                self.promotion_rules_by_market_id = {
                    key: list(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "promotion_rules_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("promotion_rules_by_market_id", {})
                    ).items()
                }
            if not self.pathway_ladders_by_market_id:
                self.pathway_ladders_by_market_id = {
                    key: list(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "pathway_ladders_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("pathway_ladders_by_market_id", {})
                    ).items()
                }
            if not self.blocked_pathways_by_market_id:
                self.blocked_pathways_by_market_id = {
                    key: list(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "blocked_pathways_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("blocked_pathways_by_market_id", {})
                    ).items()
                }
            if not self.execution_blocker_codes_by_market_id:
                self.execution_blocker_codes_by_market_id = {
                    key: list(value)
                    for key, value in (
                        getattr(self.cross_venue_plan, "execution_blocker_codes_by_market_id", {})
                        or self.cross_venue_plan.metadata.get("execution_blocker_codes_by_market_id", {})
                    ).items()
                }
            if self.preferred_execution_pathway is None:
                self.preferred_execution_pathway = getattr(self.cross_venue_plan, "preferred_execution_pathway", None) or self.cross_venue_plan.metadata.get("preferred_execution_pathway")
            if self.preferred_execution_mode is None:
                self.preferred_execution_mode = getattr(self.cross_venue_plan, "preferred_execution_mode", None) or self.cross_venue_plan.metadata.get("preferred_execution_mode")
            if self.preferred_operator_action is None:
                self.preferred_operator_action = getattr(self.cross_venue_plan, "preferred_operator_action", None) or self.cross_venue_plan.metadata.get("preferred_operator_action")
            if self.preferred_promotion_target_pathway is None:
                self.preferred_promotion_target_pathway = getattr(self.cross_venue_plan, "preferred_promotion_target_pathway", None) or self.cross_venue_plan.metadata.get("preferred_promotion_target_pathway")
        if self.proof is not None:
            self.manual_review_required = bool(self.manual_review_required or self.proof.manual_review_required)
        if self.executable_edge is not None:
            self.tradeable = bool(self.tradeable and self.executable_edge.executable)
            self.manual_review_required = bool(self.manual_review_required or not self.executable_edge.executable)
        if self.arb_plan is not None:
            self.tradeable = bool(self.tradeable and self.arb_plan.executable)
            self.manual_review_required = bool(self.manual_review_required or not self.arb_plan.executable)
            self.max_unhedged_leg_ms = max(self.max_unhedged_leg_ms, self.arb_plan.max_unhedged_leg_ms)
            self.hedge_completion_ratio = max(self.hedge_completion_ratio, self.arb_plan.hedge_completion_ratio)
            self.hedge_completion_ready = bool(self.hedge_completion_ready or self.arb_plan.hedge_completion_ready)
            self.legging_risk_reasons = _dedupe([*self.legging_risk_reasons, *self.arb_plan.legging_risk_reasons])
        if not self.execution_roles_by_market_id:
            role_market_ids = _dedupe([
                *self.market_ids,
                *self.read_only_market_ids,
                *self.reference_market_ids,
                *self.signal_market_ids,
            ])
            for market_id in role_market_ids:
                role = "watchlist"
                if market_id in self.execution_equivalent_market_ids:
                    role = "execution_equivalent"
                elif market_id in self.execution_like_market_ids:
                    role = "execution_bindable"
                elif market_id in self.reference_market_ids:
                    role = "reference_only"
                elif market_id in self.signal_market_ids:
                    role = "signal_only"
                self.execution_roles_by_market_id[market_id] = role
        if not self.execution_pathways_by_market_id:
            for market_id, role in self.execution_roles_by_market_id.items():
                if role == "execution_equivalent":
                    pathway = "bounded_execution"
                elif role == "execution_bindable":
                    pathway = "execution_bindable_dry_run"
                elif role == "reference_only":
                    pathway = "reference_read_only"
                elif role == "signal_only":
                    pathway = "signal_read_only"
                else:
                    pathway = "watchlist_read_only"
                self.execution_pathways_by_market_id[market_id] = pathway
        if not self.readiness_stages_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                stage = "read_only"
                if pathway == "live_execution":
                    stage = "live_ready"
                elif pathway == "bounded_execution":
                    stage = "bounded_ready"
                elif pathway == "execution_bindable_dry_run":
                    stage = "bindable_ready"
                elif pathway in {"execution_like_dry_run", "dry_run_only"}:
                    stage = "dry_run_ready"
                elif pathway == "execution_like_paper_only":
                    stage = "paper_ready"
                self.readiness_stages_by_market_id[market_id] = stage
        if not self.highest_actionable_modes_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                highest_mode = None
                if pathway == "live_execution":
                    highest_mode = "live"
                elif pathway == "bounded_execution":
                    highest_mode = "bounded_live"
                elif pathway == "execution_bindable_dry_run":
                    highest_mode = "dry_run"
                elif pathway in {"execution_like_dry_run", "dry_run_only"}:
                    highest_mode = "dry_run"
                elif pathway == "execution_like_paper_only":
                    highest_mode = "paper"
                self.highest_actionable_modes_by_market_id[market_id] = highest_mode
        if not self.required_operator_actions_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                required_action = "no_order_routing"
                if pathway == "live_execution":
                    required_action = "route_live_orders"
                elif pathway == "bounded_execution":
                    required_action = "route_bounded_orders"
                elif pathway == "execution_bindable_dry_run":
                    required_action = "run_dry_run_adapter"
                elif pathway in {"execution_like_dry_run", "dry_run_only"}:
                    required_action = "run_dry_run_adapter"
                elif pathway == "execution_like_paper_only":
                    required_action = "paper_trade_only"
                elif pathway == "reference_read_only":
                    required_action = "consume_reference_only"
                elif pathway == "signal_read_only":
                    required_action = "consume_signal_only"
                elif pathway == "watchlist_read_only":
                    required_action = "monitor_watchlist_only"
                self.required_operator_actions_by_market_id[market_id] = required_action
        if not self.promotion_target_pathways_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                promotion_target_pathway = None
                if pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only", "dry_run_only"}:
                    promotion_target_pathway = "bounded_execution"
                elif pathway == "bounded_execution":
                    promotion_target_pathway = "live_execution"
                self.promotion_target_pathways_by_market_id[market_id] = promotion_target_pathway
        if not self.promotion_rules_by_market_id:
            for market_id, promotion_target_pathway in self.promotion_target_pathways_by_market_id.items():
                promotion_rules: list[str] = []
                if promotion_target_pathway == "bounded_execution":
                    promotion_rules = [
                        "prove_bounded_execution_adapter",
                        "prove_cancel_order_path",
                        "prove_fill_audit",
                    ]
                elif promotion_target_pathway == "live_execution":
                    promotion_rules = [
                        "prove_live_execution_adapter",
                        "prove_live_cancel_path",
                        "prove_live_fill_audit",
                        "prove_compliance_gates",
                    ]
                self.promotion_rules_by_market_id[market_id] = promotion_rules
        if not self.pathway_ladders_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                if pathway == "live_execution":
                    ladder = ["live_execution"]
                elif pathway == "bounded_execution":
                    ladder = ["bounded_execution", "live_execution"]
                elif pathway == "execution_bindable_dry_run":
                    ladder = ["execution_bindable_dry_run", "bounded_execution", "live_execution"]
                elif pathway in {"execution_like_dry_run", "dry_run_only"}:
                    ladder = ["execution_bindable_dry_run", "bounded_execution", "live_execution"]
                elif pathway == "execution_like_paper_only":
                    ladder = ["execution_like_paper_only", "execution_bindable_dry_run", "bounded_execution", "live_execution"]
                else:
                    ladder = [pathway]
                self.pathway_ladders_by_market_id[market_id] = ladder
        if not self.blocked_pathways_by_market_id:
            for market_id, ladder in self.pathway_ladders_by_market_id.items():
                self.blocked_pathways_by_market_id[market_id] = list(ladder[1:])
        for market_id in self.execution_pathways_by_market_id:
            if market_id not in self.next_pathways_by_market_id:
                blocked_pathways = self.blocked_pathways_by_market_id.get(market_id, [])
                self.next_pathways_by_market_id[market_id] = blocked_pathways[0] if blocked_pathways else None
        if not self.execution_blocker_codes_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                blockers: list[str] = []
                if pathway == "bounded_execution":
                    blockers.append("no_live_execution_adapter")
                elif pathway == "execution_bindable_dry_run":
                    blockers.extend(["execution_bindable_only", "no_live_execution_adapter", "no_bounded_execution_adapter"])
                elif pathway == "execution_like_dry_run":
                    blockers.extend(["execution_bindable_only", "no_live_execution_adapter"])
                elif pathway == "reference_read_only":
                    blockers.append("reference_only")
                elif pathway == "signal_read_only":
                    blockers.append("signal_only")
                elif pathway == "watchlist_read_only":
                    blockers.append("watchlist_only")
                self.execution_blocker_codes_by_market_id[market_id] = blockers
        for market_id, next_pathway in self.next_pathways_by_market_id.items():
            if market_id in self.next_pathway_rules_by_market_id:
                continue
            rules: list[str] = []
            if next_pathway and self.promotion_target_pathways_by_market_id.get(market_id) == next_pathway:
                rules = list(self.promotion_rules_by_market_id.get(market_id, []))
            self.next_pathway_rules_by_market_id[market_id] = rules
        if not self.bounded_execution_equivalent_market_ids:
            self.bounded_execution_equivalent_market_ids = _dedupe(
                market_id
                for market_id, pathway in self.execution_pathways_by_market_id.items()
                if pathway in {"bounded_execution", "live_execution"}
            )
        if not self.bounded_execution_promotion_candidate_market_ids:
            self.bounded_execution_promotion_candidate_market_ids = _dedupe(
                market_id
                for market_id, blocked_pathways in self.blocked_pathways_by_market_id.items()
                if market_id not in self.bounded_execution_equivalent_market_ids and "bounded_execution" in blocked_pathways
            )
        if not self.stage_summaries_by_market_id:
            for market_id, pathway in self.execution_pathways_by_market_id.items():
                blocked_pathways = list(self.blocked_pathways_by_market_id.get(market_id, []))
                next_pathway_rules = list(self.next_pathway_rules_by_market_id.get(market_id, []))
                if pathway == "live_execution":
                    credential_gate = "live_credentials_required"
                    api_gate = "order_api_available"
                elif pathway == "bounded_execution":
                    credential_gate = "bounded_credentials_required"
                    api_gate = "order_api_available"
                elif pathway == "execution_bindable_dry_run":
                    credential_gate = "not_required_current_mode"
                    api_gate = "dry_run_order_api_available"
                elif pathway in {"execution_like_dry_run", "dry_run_only"}:
                    credential_gate = "not_required_current_mode"
                    api_gate = "dry_run_order_api_missing"
                elif pathway == "execution_like_paper_only":
                    credential_gate = "paper_only_mode"
                    api_gate = "planning_only_no_order_api"
                elif pathway == "reference_read_only":
                    credential_gate = "read_only"
                    api_gate = "reference_only_surface"
                elif pathway == "signal_read_only":
                    credential_gate = "read_only"
                    api_gate = "signal_only_surface"
                else:
                    credential_gate = "read_only"
                    api_gate = "watchlist_only_surface"
                missing_requirement_codes = list(dict.fromkeys(
                    {
                        "execution_bindable_only": "dry_run_adapter",
                        "execution_like_paper_only": "dry_run_adapter",
                        "no_live_execution_adapter": "live_execution_adapter",
                        "no_bounded_execution_adapter": "bounded_execution_adapter",
                        "planned_order_types_only": "supported_order_types",
                        "reference_only": "reference_surface",
                        "signal_only": "signal_surface",
                        "watchlist_only": "watchlist_surface",
                    }.get(code, code)
                    for code in self.execution_blocker_codes_by_market_id.get(market_id, [])
                ))
                promotion_evidence_by_pathway = {}
                current_pathway = pathway
                for ladder_pathway in self.pathway_ladders_by_market_id.get(market_id, []):
                    required_evidence = list(
                        next_pathway_rules
                        if ladder_pathway == self.next_pathways_by_market_id.get(market_id)
                        else []
                    )
                    status = "current" if ladder_pathway == current_pathway else "blocked"
                    promotion_evidence_by_pathway[ladder_pathway] = {
                        "status": status,
                        "required_evidence": required_evidence,
                        "missing_evidence": list(required_evidence if status == "blocked" else []),
                        "evidence_count": len(required_evidence),
                    }
                self.stage_summaries_by_market_id[market_id] = {
                    "execution_pathway": pathway,
                    "current_pathway": pathway,
                    "readiness_stage": self.readiness_stages_by_market_id.get(market_id, "read_only"),
                    "highest_actionable_mode": self.highest_actionable_modes_by_market_id.get(market_id),
                    "required_operator_action": self.required_operator_actions_by_market_id.get(market_id, "no_order_routing"),
                    "credential_gate": credential_gate,
                    "api_gate": api_gate,
                    "adapter_readiness": {
                        "paper_mode_ready": pathway in {"execution_bindable_dry_run", "execution_like_paper_only"} or self.highest_actionable_modes_by_market_id.get(market_id) == "paper",
                        "dry_run_adapter_ready": pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"},
                        "bounded_execution_adapter_ready": pathway == "bounded_execution",
                        "live_execution_adapter_ready": pathway == "live_execution",
                        "cancel_path_ready": pathway in {"bounded_execution", "live_execution"},
                        "fill_audit_ready": pathway in {"bounded_execution", "live_execution"},
                        "order_ack_ready": pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "dry_run_only"},
                    },
                    "execution_requirement_codes": list(self.promotion_rules_by_market_id.get(market_id, [])),
                    "missing_requirement_codes": missing_requirement_codes,
                    "missing_requirement_count": len(missing_requirement_codes),
                    "operator_checklist": list(dict.fromkeys(
                        [f"action:{self.required_operator_actions_by_market_id.get(market_id, 'no_order_routing')}"]
                        + [f"gate:{code}" for code in missing_requirement_codes]
                        + [f"promote:{rule}" for rule in next_pathway_rules]
                        + [f"api:{api_gate}"]
                    )),
                    "next_pathway": self.next_pathways_by_market_id.get(market_id),
                    "next_pathway_rules": list(self.next_pathway_rules_by_market_id.get(market_id, [])),
                    "next_pathway_rule_count": len(self.next_pathway_rules_by_market_id.get(market_id, [])),
                    "promotion_evidence_by_pathway": promotion_evidence_by_pathway,
                    "bounded_execution_equivalent": market_id in self.bounded_execution_equivalent_market_ids,
                    "bounded_execution_promotion_candidate": market_id in self.bounded_execution_promotion_candidate_market_ids,
                    "operator_ready_now": self.highest_actionable_modes_by_market_id.get(market_id) is not None,
                    "pathway_ladder": list(self.pathway_ladders_by_market_id.get(market_id, [])),
                    "pathway_count": len(self.pathway_ladders_by_market_id.get(market_id, [])),
                    "blocked_pathways": list(self.blocked_pathways_by_market_id.get(market_id, [])),
                    "blocked_pathway_count": len(self.blocked_pathways_by_market_id.get(market_id, [])),
                    "remaining_pathways": list(self.blocked_pathways_by_market_id.get(market_id, [])),
                    "remaining_pathway_count": len(self.blocked_pathways_by_market_id.get(market_id, [])),
                }
        if self.preferred_execution_pathway is None and self.preferred_execution_market_id:
            self.preferred_execution_pathway = self.execution_pathways_by_market_id.get(self.preferred_execution_market_id)
        if self.preferred_execution_mode is None and self.preferred_execution_market_id:
            self.preferred_execution_mode = self.highest_actionable_modes_by_market_id.get(self.preferred_execution_market_id)
        if self.preferred_operator_action is None and self.preferred_execution_market_id:
            self.preferred_operator_action = self.required_operator_actions_by_market_id.get(self.preferred_execution_market_id)
        if self.preferred_promotion_target_pathway is None and self.preferred_execution_market_id:
            self.preferred_promotion_target_pathway = self.promotion_target_pathways_by_market_id.get(self.preferred_execution_market_id)
        preferred_is_equivalent = bool(
            self.preferred_execution_market_id
            and self.preferred_execution_market_id in self.execution_equivalent_market_ids
        )
        if self.cross_venue_plan is not None and self.execution_like_market_ids and not preferred_is_equivalent:
            self.tradeable = False
            self.manual_review_required = True
        if not self.rationale:
            self.rationale = _plan_rationale(self)
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "MultiVenueExecutionPlan":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class MultiVenueExecutionReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"mvrept_{uuid4().hex[:12]}")
    market_count: int = 0
    cross_venue_report: CrossVenueIntelligenceReport
    plans: list[MultiVenueExecutionPlan] = Field(default_factory=list)
    proofs: list[MarketEquivalenceProof] = Field(default_factory=list)
    executable_edges: list[ExecutableEdge] = Field(default_factory=list)
    arb_plans: list[ArbPlan] = Field(default_factory=list)
    surface: MultiVenueExecutionSurface = Field(default_factory=MultiVenueExecutionSurface)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @property
    def tradeable_plans(self) -> list[MultiVenueExecutionPlan]:
        return [plan for plan in self.plans if plan.tradeable]

    @model_validator(mode="after")
    def _normalize(self) -> "MultiVenueExecutionReport":
        self.market_count = max(0, int(self.market_count))
        self.plans = [plan.model_copy() for plan in self.plans]
        self.proofs = [proof.model_copy() for proof in self.proofs]
        self.executable_edges = [edge.model_copy() for edge in self.executable_edges]
        self.arb_plans = [plan.model_copy() for plan in self.arb_plans]
        self.surface = self._build_surface()
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def _build_surface(self) -> MultiVenueExecutionSurface:
        execution_routes: dict[str, int] = {}
        tradeable_market_ids: list[str] = []
        read_only_market_ids: list[str] = []
        reference_market_ids: list[str] = []
        signal_market_ids: list[str] = []
        execution_market_ids: list[str] = []
        execution_equivalent_market_ids: list[str] = []
        execution_like_market_ids: list[str] = []
        execution_roles_by_market_id: dict[str, str] = {}
        execution_pathways_by_market_id: dict[str, str] = {}
        readiness_stages_by_market_id: dict[str, str] = {}
        highest_actionable_modes_by_market_id: dict[str, str | None] = {}
        required_operator_actions_by_market_id: dict[str, str] = {}
        next_pathways_by_market_id: dict[str, str | None] = {}
        next_pathway_rules_by_market_id: dict[str, list[str]] = {}
        bounded_execution_equivalent_market_ids: list[str] = []
        bounded_execution_promotion_candidate_market_ids: list[str] = []
        stage_summaries_by_market_id: dict[str, dict[str, Any]] = {}
        pathway_summaries_by_market_id: dict[str, str] = {}
        operator_summaries_by_market_id: dict[str, str] = {}
        promotion_summaries_by_market_id: dict[str, str] = {}
        blocker_summaries_by_market_id: dict[str, str] = {}
        credential_gates_by_market_id: dict[str, str] = {}
        api_gates_by_market_id: dict[str, str] = {}
        missing_requirement_counts_by_market_id: dict[str, int] = {}
        readiness_scores_by_market_id: dict[str, int] = {}
        operator_checklists_by_market_id: dict[str, list[str]] = {}
        promotion_evidence_by_market_id: dict[str, dict[str, dict[str, Any]]] = {}
        execution_blocker_codes_by_market_id: dict[str, list[str]] = {}
        promotion_target_pathways_by_market_id: dict[str, str | None] = {}
        promotion_rules_by_market_id: dict[str, list[str]] = {}
        pathway_ladders_by_market_id: dict[str, list[str]] = {}
        blocked_pathways_by_market_id: dict[str, list[str]] = {}
        manual_execution_contracts_by_market_id: dict[str, dict[str, Any]] = {}
        promotion_ladders_by_market_id: dict[str, list[dict[str, Any]]] = {}
        multi_leg_blocker_code_counts: dict[str, int] = {}
        parent_market_ids: list[str] = []
        child_market_ids: list[str] = []
        natural_hedge_market_ids: list[str] = []
        comparison_only_plan_count = 0
        relative_value_plan_count = 0
        cross_venue_signal_plan_count = 0
        true_arbitrage_plan_count = 0
        legging_risk_plan_count = 0
        hedge_completion_ready_plan_count = 0
        parent_child_pair_count = 0
        natural_hedge_pair_count = 0
        parent_child_relation_group_count = 0
        natural_hedge_relation_group_count = 0
        family_relation_group_count = 0
        max_unhedged_leg_ms_max = 0
        execution_equivalent_plan_count = 0
        execution_like_plan_count = 0
        execution_filter_reason_code_counts: dict[str, int] = {}
        execution_filter_reason_codes: list[str] = []
        preferred_execution_semantics_counts: dict[str, int] = {}
        preferred_execution_selection_reason_counts: dict[str, int] = {}
        mixed_execution_semantics_counts: dict[str, int] = {}
        survivability_hint_counts: dict[str, int] = {}
        legging_risk_tier_counts: dict[str, int] = {}
        for plan in self.plans:
            execution_routes[plan.route] = execution_routes.get(plan.route, 0) + 1
            if plan.taxonomy == CrossVenueTaxonomy.comparison_only:
                comparison_only_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.relative_value:
                relative_value_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.cross_venue_signal:
                cross_venue_signal_plan_count += 1
            elif plan.taxonomy == CrossVenueTaxonomy.true_arbitrage:
                true_arbitrage_plan_count += 1
            execution_filter_reason_codes.extend(plan.execution_filter_reason_codes)
            for reason_code in plan.execution_filter_reason_codes:
                execution_filter_reason_code_counts[reason_code] = execution_filter_reason_code_counts.get(reason_code, 0) + 1
            tradeable_market_ids.extend(plan.execution_market_ids if plan.tradeable else [])
            read_only_market_ids.extend(plan.read_only_market_ids)
            reference_market_ids.extend(plan.reference_market_ids)
            signal_market_ids.extend(plan.signal_market_ids)
            execution_market_ids.extend(plan.execution_market_ids)
            execution_equivalent_market_ids.extend(plan.execution_equivalent_market_ids)
            execution_like_market_ids.extend(plan.execution_like_market_ids)
            if plan.execution_equivalent_market_ids:
                execution_equivalent_plan_count += 1
            if plan.execution_like_market_ids:
                execution_like_plan_count += 1
            if plan.execution_roles_by_market_id:
                execution_roles_by_market_id.update(plan.execution_roles_by_market_id)
            else:
                plan_role_market_ids = _dedupe([
                    *plan.market_ids,
                    *plan.reference_market_ids,
                    *plan.signal_market_ids,
                ])
                for market_id in plan_role_market_ids:
                    role = "watchlist"
                    if market_id in plan.execution_equivalent_market_ids:
                        role = "execution_equivalent"
                    elif market_id in plan.execution_like_market_ids:
                        role = "execution_bindable"
                    elif market_id in plan.reference_market_ids:
                        role = "reference_only"
                    elif market_id in plan.signal_market_ids:
                        role = "signal_only"
                    execution_roles_by_market_id[market_id] = role
            if plan.execution_pathways_by_market_id:
                execution_pathways_by_market_id.update(plan.execution_pathways_by_market_id)
            if plan.readiness_stages_by_market_id:
                readiness_stages_by_market_id.update(plan.readiness_stages_by_market_id)
            if plan.highest_actionable_modes_by_market_id:
                highest_actionable_modes_by_market_id.update(plan.highest_actionable_modes_by_market_id)
            if plan.required_operator_actions_by_market_id:
                required_operator_actions_by_market_id.update(plan.required_operator_actions_by_market_id)
            if plan.next_pathways_by_market_id:
                next_pathways_by_market_id.update(plan.next_pathways_by_market_id)
            if plan.next_pathway_rules_by_market_id:
                next_pathway_rules_by_market_id.update({
                    market_id: list(rules)
                    for market_id, rules in plan.next_pathway_rules_by_market_id.items()
                })
            bounded_execution_equivalent_market_ids.extend(plan.bounded_execution_equivalent_market_ids)
            bounded_execution_promotion_candidate_market_ids.extend(plan.bounded_execution_promotion_candidate_market_ids)
            if plan.stage_summaries_by_market_id:
                stage_summaries_by_market_id.update({
                    market_id: dict(summary)
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                pathway_summaries_by_market_id.update({
                    market_id: str(summary.get("pathway_summary", ""))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                operator_summaries_by_market_id.update({
                    market_id: str(summary.get("operator_summary", ""))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                promotion_summaries_by_market_id.update({
                    market_id: str(summary.get("promotion_summary", ""))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                blocker_summaries_by_market_id.update({
                    market_id: str(summary.get("blocker_summary", ""))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                manual_execution_contracts_by_market_id.update({
                    market_id: dict(summary.get("manual_execution_contract", {}))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                promotion_ladders_by_market_id.update({
                    market_id: [dict(step) for step in summary.get("promotion_ladder", [])]
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                credential_gates_by_market_id.update({
                    market_id: str(summary.get("credential_gate", "read_only"))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                api_gates_by_market_id.update({
                    market_id: str(summary.get("api_gate", "watchlist_only_surface"))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                missing_requirement_counts_by_market_id.update({
                    market_id: int(summary.get("missing_requirement_count", 0))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                readiness_scores_by_market_id.update({
                    market_id: {
                        "read_only": 0,
                        "paper_ready": 1,
                        "bindable_ready": 2,
                        "dry_run_ready": 3,
                        "bounded_ready": 4,
                        "live_ready": 5,
                    }.get(str(summary.get("readiness_stage", "read_only")), 0)
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                operator_checklists_by_market_id.update({
                    market_id: list(summary.get("operator_checklist", []))
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
                promotion_evidence_by_market_id.update({
                    market_id: {
                        pathway: dict(evidence)
                        for pathway, evidence in summary.get("promotion_evidence_by_pathway", {}).items()
                    }
                    for market_id, summary in plan.stage_summaries_by_market_id.items()
                })
            if plan.promotion_target_pathways_by_market_id:
                promotion_target_pathways_by_market_id.update(plan.promotion_target_pathways_by_market_id)
            if plan.promotion_rules_by_market_id:
                promotion_rules_by_market_id.update({
                    market_id: list(rules)
                    for market_id, rules in plan.promotion_rules_by_market_id.items()
                })
            if plan.pathway_ladders_by_market_id:
                pathway_ladders_by_market_id.update({
                    market_id: list(ladder)
                    for market_id, ladder in plan.pathway_ladders_by_market_id.items()
                })
            if plan.blocked_pathways_by_market_id:
                blocked_pathways_by_market_id.update({
                    market_id: list(pathways)
                    for market_id, pathways in plan.blocked_pathways_by_market_id.items()
                })
            if plan.execution_blocker_codes_by_market_id:
                execution_blocker_codes_by_market_id.update({
                    market_id: list(codes)
                    for market_id, codes in plan.execution_blocker_codes_by_market_id.items()
                })
            if plan.arb_plan is not None:
                max_unhedged_leg_ms_max = max(max_unhedged_leg_ms_max, plan.arb_plan.max_unhedged_leg_ms)
                if plan.arb_plan.legging_risk_reasons:
                    legging_risk_plan_count += 1
                if plan.arb_plan.hedge_completion_ready:
                    hedge_completion_ready_plan_count += 1
            preferred_execution_semantics = str(plan.metadata.get("preferred_execution_semantics") or "").strip()
            if preferred_execution_semantics:
                preferred_execution_semantics_counts[preferred_execution_semantics] = (
                    preferred_execution_semantics_counts.get(preferred_execution_semantics, 0) + 1
                )
            preferred_execution_selection_reason = str(plan.metadata.get("preferred_execution_selection_reason") or "").strip()
            if preferred_execution_selection_reason:
                preferred_execution_selection_reason_counts[preferred_execution_selection_reason] = (
                    preferred_execution_selection_reason_counts.get(preferred_execution_selection_reason, 0) + 1
                )
            mixed_execution_semantics = str(plan.metadata.get("mixed_execution_semantics") or "").strip()
            if mixed_execution_semantics:
                mixed_execution_semantics_counts[mixed_execution_semantics] = (
                    mixed_execution_semantics_counts.get(mixed_execution_semantics, 0) + 1
                )
            survivability_hint = str(plan.metadata.get("survivability_hint") or "").strip()
            if survivability_hint:
                survivability_hint_counts[survivability_hint] = (
                    survivability_hint_counts.get(survivability_hint, 0) + 1
                )
            legging_risk_tier = str(plan.metadata.get("legging_risk_tier") or "").strip()
            if legging_risk_tier:
                legging_risk_tier_counts[legging_risk_tier] = (
                    legging_risk_tier_counts.get(legging_risk_tier, 0) + 1
                )
            for code in plan.metadata.get("multi_leg_blocker_codes", []):
                multi_leg_blocker_code_counts[str(code)] = multi_leg_blocker_code_counts.get(str(code), 0) + 1
            parent_market_ids.extend(plan.parent_market_ids)
            child_market_ids.extend(plan.child_market_ids)
            natural_hedge_market_ids.extend(plan.natural_hedge_market_ids)
            parent_child_pair_count += int(plan.parent_child_pair_count)
            natural_hedge_pair_count += int(plan.natural_hedge_pair_count)
            if plan.parent_child_pair_count:
                parent_child_relation_group_count += 1
            if plan.natural_hedge_pair_count:
                natural_hedge_relation_group_count += 1
            if plan.parent_child_pair_count or plan.natural_hedge_pair_count:
                family_relation_group_count += 1
        metadata_parent_market_ids = self.metadata.get("parent_market_ids", [])
        metadata_child_market_ids = self.metadata.get("child_market_ids", [])
        metadata_natural_hedge_market_ids = self.metadata.get("natural_hedge_market_ids", [])
        execution_role_counts = {
            role: sum(1 for value in execution_roles_by_market_id.values() if value == role)
            for role in sorted({*execution_roles_by_market_id.values()})
        }
        execution_pathway_counts = {
            pathway: sum(1 for value in execution_pathways_by_market_id.values() if value == pathway)
            for pathway in sorted({*execution_pathways_by_market_id.values()})
        }
        readiness_stage_counts = {
            stage: sum(1 for value in readiness_stages_by_market_id.values() if value == stage)
            for stage in sorted({*readiness_stages_by_market_id.values()})
        }
        required_operator_action_counts = {
            action: sum(1 for value in required_operator_actions_by_market_id.values() if value == action)
            for action in sorted({*required_operator_actions_by_market_id.values()})
        }
        next_pathway_counts = {
            pathway: sum(1 for value in next_pathways_by_market_id.values() if value == pathway)
            for pathway in sorted({value for value in next_pathways_by_market_id.values() if value})
        }
        bounded_execution_equivalent_market_ids = _dedupe(bounded_execution_equivalent_market_ids)
        bounded_execution_promotion_candidate_market_ids = _dedupe(bounded_execution_promotion_candidate_market_ids)
        return MultiVenueExecutionSurface(
            report_id=self.report_id,
            market_count=self.market_count,
            comparable_group_count=self.cross_venue_report.metadata.get("comparable_group_count", len(self.cross_venue_report.comparable_groups)),
            parent_child_relation_group_count=int(self.metadata.get("parent_child_relation_group_count", parent_child_relation_group_count)),
            natural_hedge_relation_group_count=int(self.metadata.get("natural_hedge_relation_group_count", natural_hedge_relation_group_count)),
            family_relation_group_count=int(self.metadata.get("family_relation_group_count", family_relation_group_count)),
            execution_candidate_count=len(self.cross_venue_report.execution_candidates),
            execution_plan_count=len(self.plans),
            tradeable_plan_count=len(self.tradeable_plans),
            execution_equivalent_plan_count=execution_equivalent_plan_count,
            execution_like_plan_count=execution_like_plan_count,
            execution_routes={key: value for key, value in sorted(execution_routes.items())},
            execution_role_counts=execution_role_counts,
            execution_roles_by_market_id={key: value for key, value in sorted(execution_roles_by_market_id.items())},
            execution_pathway_counts=execution_pathway_counts,
            execution_pathways_by_market_id={key: value for key, value in sorted(execution_pathways_by_market_id.items())},
            readiness_stages_by_market_id={key: value for key, value in sorted(readiness_stages_by_market_id.items())},
            readiness_stage_counts=readiness_stage_counts,
            highest_actionable_modes_by_market_id={key: value for key, value in sorted(highest_actionable_modes_by_market_id.items())},
            required_operator_actions_by_market_id={key: value for key, value in sorted(required_operator_actions_by_market_id.items())},
            required_operator_action_counts=required_operator_action_counts,
            next_pathways_by_market_id={key: value for key, value in sorted(next_pathways_by_market_id.items())},
            next_pathway_counts=next_pathway_counts,
            next_pathway_rules_by_market_id={key: list(value) for key, value in sorted(next_pathway_rules_by_market_id.items())},
            bounded_execution_equivalent_market_ids=bounded_execution_equivalent_market_ids,
            bounded_execution_equivalent_count=len(bounded_execution_equivalent_market_ids),
            bounded_execution_promotion_candidate_market_ids=bounded_execution_promotion_candidate_market_ids,
            bounded_execution_promotion_candidate_count=len(bounded_execution_promotion_candidate_market_ids),
            stage_summaries_by_market_id={key: dict(value) for key, value in sorted(stage_summaries_by_market_id.items())},
            pathway_summaries_by_market_id={key: value for key, value in sorted(pathway_summaries_by_market_id.items())},
            operator_summaries_by_market_id={key: value for key, value in sorted(operator_summaries_by_market_id.items())},
            promotion_summaries_by_market_id={key: value for key, value in sorted(promotion_summaries_by_market_id.items())},
            blocker_summaries_by_market_id={key: value for key, value in sorted(blocker_summaries_by_market_id.items())},
            promotion_target_pathways_by_market_id={key: value for key, value in sorted(promotion_target_pathways_by_market_id.items())},
            promotion_rules_by_market_id={key: list(value) for key, value in sorted(promotion_rules_by_market_id.items())},
            pathway_ladders_by_market_id={key: list(value) for key, value in sorted(pathway_ladders_by_market_id.items())},
            blocked_pathways_by_market_id={key: list(value) for key, value in sorted(blocked_pathways_by_market_id.items())},
            execution_blocker_codes_by_market_id={
                key: list(value)
                for key, value in sorted(execution_blocker_codes_by_market_id.items())
            },
            tradeable_market_ids=_dedupe(tradeable_market_ids),
            read_only_market_ids=_dedupe(read_only_market_ids or self.cross_venue_report.reference_market_ids),
            reference_market_ids=_dedupe(reference_market_ids or self.cross_venue_report.reference_market_ids),
            signal_market_ids=_dedupe(signal_market_ids),
            execution_market_ids=_dedupe(execution_market_ids),
            execution_equivalent_market_ids=_dedupe(execution_equivalent_market_ids),
            execution_like_market_ids=_dedupe(execution_like_market_ids),
            parent_market_ids=_dedupe(parent_market_ids or metadata_parent_market_ids),
            child_market_ids=_dedupe(child_market_ids or metadata_child_market_ids),
            natural_hedge_market_ids=_dedupe(natural_hedge_market_ids or metadata_natural_hedge_market_ids),
            comparison_only_plan_count=comparison_only_plan_count,
            relative_value_plan_count=relative_value_plan_count,
            cross_venue_signal_plan_count=cross_venue_signal_plan_count,
            true_arbitrage_plan_count=true_arbitrage_plan_count,
            legging_risk_plan_count=legging_risk_plan_count,
            hedge_completion_ready_plan_count=hedge_completion_ready_plan_count,
            parent_child_pair_count=int(self.metadata.get("parent_child_pair_count", parent_child_pair_count)),
            natural_hedge_pair_count=int(self.metadata.get("natural_hedge_pair_count", natural_hedge_pair_count)),
            max_unhedged_leg_ms_max=max_unhedged_leg_ms_max,
            execution_filter_reason_codes=_dedupe(execution_filter_reason_codes),
            execution_filter_reason_code_counts={key: value for key, value in sorted(execution_filter_reason_code_counts.items())},
            metadata={
                "cross_venue_report_id": self.cross_venue_report.report_id,
                "execution_candidate_count": len(self.cross_venue_report.execution_candidates),
                "execution_plan_count": len(self.plans),
                "tradeable_plan_count": len(self.tradeable_plans),
                "execution_equivalent_plan_count": execution_equivalent_plan_count,
                "execution_like_plan_count": execution_like_plan_count,
                "execution_role_counts": execution_role_counts,
                "execution_pathway_counts": execution_pathway_counts,
                "readiness_stages_by_market_id": {key: value for key, value in sorted(readiness_stages_by_market_id.items())},
                "readiness_stage_counts": readiness_stage_counts,
                "highest_actionable_modes_by_market_id": {key: value for key, value in sorted(highest_actionable_modes_by_market_id.items())},
                "required_operator_actions_by_market_id": {key: value for key, value in sorted(required_operator_actions_by_market_id.items())},
                "required_operator_action_counts": required_operator_action_counts,
                "next_pathways_by_market_id": {key: value for key, value in sorted(next_pathways_by_market_id.items())},
                "next_pathway_counts": next_pathway_counts,
                "next_pathway_rules_by_market_id": {
                    key: list(value)
                    for key, value in sorted(next_pathway_rules_by_market_id.items())
                },
                "bounded_execution_equivalent_market_ids": list(bounded_execution_equivalent_market_ids),
                "bounded_execution_equivalent_count": len(bounded_execution_equivalent_market_ids),
                "bounded_execution_promotion_candidate_market_ids": list(bounded_execution_promotion_candidate_market_ids),
                "bounded_execution_promotion_candidate_count": len(bounded_execution_promotion_candidate_market_ids),
                "stage_summaries_by_market_id": {
                    key: dict(value)
                    for key, value in sorted(stage_summaries_by_market_id.items())
                },
                "pathway_summaries_by_market_id": {
                    key: value
                    for key, value in sorted(pathway_summaries_by_market_id.items())
                },
                "operator_summaries_by_market_id": {
                    key: value
                    for key, value in sorted(operator_summaries_by_market_id.items())
                },
                "promotion_summaries_by_market_id": {
                    key: value
                    for key, value in sorted(promotion_summaries_by_market_id.items())
                },
                "blocker_summaries_by_market_id": {
                    key: value
                    for key, value in sorted(blocker_summaries_by_market_id.items())
                },
                "manual_execution_contracts_by_market_id": {
                    key: dict(value)
                    for key, value in sorted(manual_execution_contracts_by_market_id.items())
                },
                "promotion_ladders_by_market_id": {
                    key: [dict(step) for step in value]
                    for key, value in sorted(promotion_ladders_by_market_id.items())
                },
                "credential_gates_by_market_id": {
                    key: value for key, value in sorted(credential_gates_by_market_id.items())
                },
                "api_gates_by_market_id": {
                    key: value for key, value in sorted(api_gates_by_market_id.items())
                },
                "missing_requirement_counts_by_market_id": {
                    key: value
                    for key, value in sorted(missing_requirement_counts_by_market_id.items())
                },
                "missing_requirement_market_count": sum(
                    1 for value in missing_requirement_counts_by_market_id.values() if value > 0
                ),
                "readiness_scores_by_market_id": {
                    key: value
                    for key, value in sorted(readiness_scores_by_market_id.items())
                },
                "operator_checklists_by_market_id": {
                    key: list(value)
                    for key, value in sorted(operator_checklists_by_market_id.items())
                },
                "promotion_evidence_by_market_id": {
                    key: {
                        pathway: dict(evidence)
                        for pathway, evidence in value.items()
                    }
                    for key, value in sorted(promotion_evidence_by_market_id.items())
                },
                "credential_gate_counts": {
                    gate: sum(1 for value in credential_gates_by_market_id.values() if value == gate)
                    for gate in sorted(set(credential_gates_by_market_id.values()))
                },
                "api_gate_counts": {
                    gate: sum(1 for value in api_gates_by_market_id.values() if value == gate)
                    for gate in sorted(set(api_gates_by_market_id.values()))
                },
                "operator_ready_market_count": sum(
                    1
                    for summary in stage_summaries_by_market_id.values()
                    if summary.get("operator_ready_now", False)
                ),
                "promotion_target_pathways_by_market_id": {key: value for key, value in sorted(promotion_target_pathways_by_market_id.items())},
                "promotion_rules_by_market_id": {key: list(value) for key, value in sorted(promotion_rules_by_market_id.items())},
                "pathway_ladders_by_market_id": {key: list(value) for key, value in sorted(pathway_ladders_by_market_id.items())},
                "blocked_pathways_by_market_id": {key: list(value) for key, value in sorted(blocked_pathways_by_market_id.items())},
                "comparison_only_plan_count": comparison_only_plan_count,
                "relative_value_plan_count": relative_value_plan_count,
                "cross_venue_signal_plan_count": cross_venue_signal_plan_count,
                "true_arbitrage_plan_count": true_arbitrage_plan_count,
                "reference_market_ids": _dedupe(reference_market_ids or self.cross_venue_report.reference_market_ids),
                "tradeable_market_ids": _dedupe(tradeable_market_ids),
                "execution_equivalent_market_ids": _dedupe(execution_equivalent_market_ids),
                "execution_like_market_ids": _dedupe(execution_like_market_ids),
                "execution_roles_by_market_id": {key: value for key, value in sorted(execution_roles_by_market_id.items())},
                "execution_pathways_by_market_id": {key: value for key, value in sorted(execution_pathways_by_market_id.items())},
                "execution_blocker_codes_by_market_id": {
                    key: list(value)
                    for key, value in sorted(execution_blocker_codes_by_market_id.items())
                },
                "execution_filter_reason_codes": _dedupe(execution_filter_reason_codes),
                "execution_filter_reason_code_counts": {key: value for key, value in sorted(execution_filter_reason_code_counts.items())},
                "legging_risk_plan_count": legging_risk_plan_count,
                "hedge_completion_ready_plan_count": hedge_completion_ready_plan_count,
                "parent_market_ids": _dedupe(parent_market_ids or metadata_parent_market_ids),
                "child_market_ids": _dedupe(child_market_ids or metadata_child_market_ids),
                "natural_hedge_market_ids": _dedupe(natural_hedge_market_ids or metadata_natural_hedge_market_ids),
                "parent_child_pair_count": int(self.metadata.get("parent_child_pair_count", parent_child_pair_count)),
                "natural_hedge_pair_count": int(self.metadata.get("natural_hedge_pair_count", natural_hedge_pair_count)),
                "parent_child_relation_group_count": int(self.metadata.get("parent_child_relation_group_count", parent_child_relation_group_count)),
                "natural_hedge_relation_group_count": int(self.metadata.get("natural_hedge_relation_group_count", natural_hedge_relation_group_count)),
                "family_relation_group_count": int(self.metadata.get("family_relation_group_count", family_relation_group_count)),
                "max_unhedged_leg_ms_max": max_unhedged_leg_ms_max,
                "preferred_execution_semantics_counts": dict(sorted(preferred_execution_semantics_counts.items())),
                "preferred_execution_selection_reason_counts": dict(sorted(preferred_execution_selection_reason_counts.items())),
                "mixed_execution_semantics_counts": dict(sorted(mixed_execution_semantics_counts.items())),
                "survivability_hint_counts": dict(sorted(survivability_hint_counts.items())),
                "legging_risk_tier_counts": dict(sorted(legging_risk_tier_counts.items())),
                "multi_leg_blocker_code_counts": dict(sorted(multi_leg_blocker_code_counts.items())),
            },
        )

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "MultiVenueExecutionReport":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


@dataclass
class MultiVenueExecutor:
    cross_venue_intelligence: CrossVenueIntelligence = field(default_factory=CrossVenueIntelligence)
    target_notional_usd: float = 1000.0
    fee_bps: float = 20.0
    slippage_bps: float = 10.0
    hedge_risk_bps: float = 10.0
    confidence_floor: float = 0.5
    max_unhedged_leg_ms: int = 2500

    def build_report(
        self,
        markets: Sequence[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        target_notional_usd: float | None = None,
    ) -> MultiVenueExecutionReport:
        market_list = list(markets)
        snapshot_map = dict(snapshots or {})
        market_graph = MarketGraphBuilder().build(market_list, snapshots=snapshot_map)
        graph_group_index = market_graph.comparable_group_index()
        cross_report = self.cross_venue_intelligence.build_report(market_list, snapshots=snapshot_map)
        market_lookup = {market.market_id: market for market in market_list}
        match_lookup = {
            (match.left_market_id, match.right_market_id): match
            for match in cross_report.matches
        }
        graph_relation_summary = _relation_summary_from_groups(market_graph.comparable_groups)

        plans: list[MultiVenueExecutionPlan] = []
        proofs: list[MarketEquivalenceProof] = []
        executable_edges: list[ExecutableEdge] = []
        arb_plans: list[ArbPlan] = []
        notional = float(target_notional_usd if target_notional_usd is not None else self.target_notional_usd)
        stage_summaries_by_market_id: dict[str, dict[str, Any]] = {}
        pathway_summaries_by_market_id: dict[str, str] = {}
        operator_summaries_by_market_id: dict[str, str] = {}
        promotion_summaries_by_market_id: dict[str, str] = {}
        blocker_summaries_by_market_id: dict[str, str] = {}

        for candidate in cross_report.execution_candidates:
            comparison = _comparison_for(cross_report, candidate.comparison_id)
            if comparison is None:
                continue
            left = market_lookup.get(comparison.left_market_id)
            right = market_lookup.get(comparison.right_market_id)
            if left is None or right is None:
                continue
            match = match_lookup.get((left.market_id, right.market_id)) or match_lookup.get((right.market_id, left.market_id))
            proof = assess_market_equivalence(left, right, match=match)
            spread_bps = float(comparison.spread_bps or 0.0)
            confidence = max(self.confidence_floor, min(1.0, float(comparison.metadata.get("similarity", 0.75))))
            preferred_market_id = candidate.preferred_execution_market_id or left.market_id
            counterparty_market_id = right.market_id if preferred_market_id == left.market_id else left.market_id
            edge = derive_executable_edge(
                proof,
                market_ref=preferred_market_id,
                counterparty_market_ref=counterparty_market_id,
                raw_edge_bps=spread_bps,
                fees_bps=self.fee_bps,
                slippage_bps=self.slippage_bps,
                hedge_risk_bps=self.hedge_risk_bps,
                confidence=confidence,
            )
            arb_plan = build_arb_plan(
                proof,
                edge,
                market_a=left,
                market_b=right,
                target_notional_usd=notional,
                max_unhedged_leg_ms=self.max_unhedged_leg_ms,
            )
            cross_plan = _plan_for_candidate(cross_report.execution_plans, candidate.candidate_id)
            execution_equivalent_market_ids = list(cross_plan.execution_equivalent_market_ids if cross_plan is not None else [])
            execution_like_market_ids = list(cross_plan.execution_like_market_ids if cross_plan is not None else [])
            execution_roles_by_market_id = dict(getattr(cross_plan, "execution_roles_by_market_id", {}) if cross_plan is not None else {})
            execution_pathways_by_market_id = dict(getattr(cross_plan, "execution_pathways_by_market_id", {}) if cross_plan is not None else {})
            readiness_stages_by_market_id = dict(getattr(cross_plan, "readiness_stages_by_market_id", {}) if cross_plan is not None else {})
            highest_actionable_modes_by_market_id = dict(getattr(cross_plan, "highest_actionable_modes_by_market_id", {}) if cross_plan is not None else {})
            required_operator_actions_by_market_id = dict(getattr(cross_plan, "required_operator_actions_by_market_id", {}) if cross_plan is not None else {})
            next_pathways_by_market_id = dict(getattr(cross_plan, "next_pathways_by_market_id", {}) if cross_plan is not None else {})
            next_pathway_rules_by_market_id = {
                key: list(value)
                for key, value in (getattr(cross_plan, "next_pathway_rules_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            bounded_execution_equivalent_market_ids = list(getattr(cross_plan, "bounded_execution_equivalent_market_ids", []) if cross_plan is not None else [])
            bounded_execution_promotion_candidate_market_ids = list(
                getattr(cross_plan, "bounded_execution_promotion_candidate_market_ids", []) if cross_plan is not None else []
            )
            stage_summaries_by_market_id = {
                key: dict(value)
                for key, value in (getattr(cross_plan, "stage_summaries_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            promotion_target_pathways_by_market_id = dict(getattr(cross_plan, "promotion_target_pathways_by_market_id", {}) if cross_plan is not None else {})
            promotion_rules_by_market_id = {
                key: list(value)
                for key, value in (getattr(cross_plan, "promotion_rules_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            pathway_ladders_by_market_id = {
                key: list(value)
                for key, value in (getattr(cross_plan, "pathway_ladders_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            blocked_pathways_by_market_id = {
                key: list(value)
                for key, value in (getattr(cross_plan, "blocked_pathways_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            execution_blocker_codes_by_market_id = {
                key: list(value)
                for key, value in (getattr(cross_plan, "execution_blocker_codes_by_market_id", {}) if cross_plan is not None else {}).items()
            }
            if not execution_roles_by_market_id:
                for market_id in _dedupe([
                    *candidate.market_ids,
                    *candidate.reference_market_ids,
                    *candidate.signal_market_ids,
                    *(cross_plan.read_only_market_ids if cross_plan is not None else []),
                    *(cross_plan.reference_only_market_ids if cross_plan is not None else []),
                    *(cross_plan.watchlist_market_ids if cross_plan is not None else []),
                ]):
                    if market_id in execution_equivalent_market_ids:
                        role = "execution_equivalent"
                    elif market_id in execution_like_market_ids:
                        role = "execution_like"
                    elif market_id in candidate.reference_market_ids:
                        role = "reference_only"
                    elif market_id in candidate.signal_market_ids:
                        role = "signal_only"
                    else:
                        role = "watchlist"
                    execution_roles_by_market_id[market_id] = role
            if not execution_pathways_by_market_id:
                execution_pathways_by_market_id = {
                    key: value
                    for key, value in candidate.execution_pathways_by_market_id.items()
                }
            if not highest_actionable_modes_by_market_id:
                highest_actionable_modes_by_market_id = {
                    key: value
                    for key, value in candidate.highest_actionable_modes_by_market_id.items()
                    if value is not None
                }
            if not required_operator_actions_by_market_id:
                required_operator_actions_by_market_id = {
                    key: value
                    for key, value in candidate.required_operator_actions_by_market_id.items()
                }
            if not readiness_stages_by_market_id:
                readiness_stages_by_market_id = {
                    key: value
                    for key, value in candidate.readiness_stages_by_market_id.items()
                }
            if not next_pathways_by_market_id:
                next_pathways_by_market_id = {
                    key: value
                    for key, value in candidate.next_pathways_by_market_id.items()
                }
            if not next_pathway_rules_by_market_id:
                next_pathway_rules_by_market_id = {
                    key: list(value)
                    for key, value in candidate.next_pathway_rules_by_market_id.items()
                }
            if not bounded_execution_equivalent_market_ids:
                bounded_execution_equivalent_market_ids = list(candidate.bounded_execution_equivalent_market_ids)
            if not bounded_execution_promotion_candidate_market_ids:
                bounded_execution_promotion_candidate_market_ids = list(candidate.bounded_execution_promotion_candidate_market_ids)
            if not stage_summaries_by_market_id:
                stage_summaries_by_market_id = {
                    key: dict(value)
                    for key, value in candidate.stage_summaries_by_market_id.items()
                }
            if not pathway_summaries_by_market_id:
                pathway_summaries_by_market_id = {
                    key: str(value.get("pathway_summary", ""))
                    for key, value in candidate.stage_summaries_by_market_id.items()
                }
            if not operator_summaries_by_market_id:
                operator_summaries_by_market_id = {
                    key: str(value.get("operator_summary", ""))
                    for key, value in candidate.stage_summaries_by_market_id.items()
                }
            if not promotion_summaries_by_market_id:
                promotion_summaries_by_market_id = {
                    key: str(value.get("promotion_summary", ""))
                    for key, value in candidate.stage_summaries_by_market_id.items()
                }
            if not blocker_summaries_by_market_id:
                blocker_summaries_by_market_id = {
                    key: str(value.get("blocker_summary", ""))
                    for key, value in candidate.stage_summaries_by_market_id.items()
                }
            if not promotion_target_pathways_by_market_id:
                promotion_target_pathways_by_market_id = {
                    key: value
                    for key, value in candidate.promotion_target_pathways_by_market_id.items()
                }
            if not promotion_rules_by_market_id:
                promotion_rules_by_market_id = {
                    key: list(value)
                    for key, value in candidate.promotion_rules_by_market_id.items()
                }
            if not pathway_ladders_by_market_id:
                pathway_ladders_by_market_id = {
                    key: list(value)
                    for key, value in candidate.pathway_ladders_by_market_id.items()
                }
            if not blocked_pathways_by_market_id:
                blocked_pathways_by_market_id = {
                    key: list(value)
                    for key, value in candidate.blocked_pathways_by_market_id.items()
                }
            if not execution_blocker_codes_by_market_id:
                execution_blocker_codes_by_market_id = {
                    key: list(value)
                    for key, value in candidate.execution_blocker_codes_by_market_id.items()
                }
            relation_context = _relation_context_for_markets(graph_group_index, candidate.market_ids)
            preferred_is_equivalent = bool(preferred_market_id in execution_equivalent_market_ids)
            mixed_execution_semantics = str(candidate.metadata.get("mixed_execution_semantics") or "")
            base_survivability_hint = str(candidate.metadata.get("survivability_hint") or "")
            legging_risk_tier = _legging_risk_tier(
                max_unhedged_leg_ms=arb_plan.max_unhedged_leg_ms,
                hedge_completion_ratio=arb_plan.hedge_completion_ratio,
                hedge_completion_ready=arb_plan.hedge_completion_ready,
                legging_risk_reasons=arb_plan.legging_risk_reasons,
            )
            survivability_hint = _plan_survivability_hint(
                base_hint=base_survivability_hint,
                tradeable=bool(
                    candidate.tradeable
                    and proof.proof_status == MarketEquivalenceProofStatus.proven
                    and edge.executable
                    and arb_plan.executable
                    and preferred_is_equivalent
                ),
                legging_risk_tier=legging_risk_tier,
                hedge_completion_ready=arb_plan.hedge_completion_ready,
            )
            multi_leg_operator_checklist = _build_multi_leg_operator_checklist(
                base_checklist=candidate.metadata.get("multi_leg_operator_checklist", []),
                max_unhedged_leg_ms=arb_plan.max_unhedged_leg_ms,
                hedge_completion_ratio=arb_plan.hedge_completion_ratio,
                hedge_completion_ready=arb_plan.hedge_completion_ready,
                legging_risk_tier=legging_risk_tier,
            )
            multi_leg_blocker_codes = _build_multi_leg_blocker_codes(
                base_codes=candidate.metadata.get("multi_leg_blocker_codes", []),
                legging_risk_reasons=arb_plan.legging_risk_reasons,
                hedge_completion_ready=arb_plan.hedge_completion_ready,
                tradeable=bool(
                    candidate.tradeable
                    and proof.proof_status == MarketEquivalenceProofStatus.proven
                    and edge.executable
                    and arb_plan.executable
                    and preferred_is_equivalent
                ),
                legging_risk_tier=legging_risk_tier,
            )
            survivability_summary = {
                "mixed_execution_semantics": mixed_execution_semantics,
                "survivability_hint": survivability_hint,
                "legging_risk_tier": legging_risk_tier,
                "max_unhedged_leg_ms": arb_plan.max_unhedged_leg_ms,
                "hedge_completion_ratio": arb_plan.hedge_completion_ratio,
                "hedge_completion_ready": arb_plan.hedge_completion_ready,
                "secondary_leg_count": max(0, len(candidate.market_ids) - 1),
                "bounded_leg_count": sum(1 for value in readiness_stages_by_market_id.values() if value == "bounded_ready"),
                "bindable_leg_count": sum(1 for value in readiness_stages_by_market_id.values() if value == "bindable_ready"),
                "dry_run_leg_count": sum(1 for value in readiness_stages_by_market_id.values() if value == "dry_run_ready"),
                "blocked_leg_count": sum(
                    1
                    for value in candidate.metadata.get("missing_requirement_counts_by_market_id", {}).values()
                    if int(value) > 0
                ),
            }
            plan = MultiVenueExecutionPlan(
                candidate_id=candidate.candidate_id,
                comparison_id=candidate.comparison_id,
                canonical_event_id=candidate.canonical_event_id,
                market_ids=list(candidate.market_ids),
                read_only_market_ids=list(dict.fromkeys([*candidate.reference_market_ids])),
                reference_market_ids=list(candidate.reference_market_ids),
                signal_market_ids=list(candidate.signal_market_ids),
                execution_market_ids=_dedupe(
                    [
                        *(cross_plan.execution_market_ids if cross_plan is not None else []),
                        *(cross_plan.execution_equivalent_market_ids if cross_plan is not None else []),
                    ]
                    or [preferred_market_id, counterparty_market_id]
                ),
                execution_equivalent_market_ids=execution_equivalent_market_ids,
                execution_like_market_ids=execution_like_market_ids,
                execution_roles_by_market_id=dict(execution_roles_by_market_id),
                execution_pathways_by_market_id=dict(execution_pathways_by_market_id),
                readiness_stages_by_market_id=dict(readiness_stages_by_market_id),
                highest_actionable_modes_by_market_id=dict(highest_actionable_modes_by_market_id),
                required_operator_actions_by_market_id=dict(required_operator_actions_by_market_id),
                next_pathways_by_market_id=dict(next_pathways_by_market_id),
                next_pathway_rules_by_market_id={
                    key: list(value)
                    for key, value in next_pathway_rules_by_market_id.items()
                },
                bounded_execution_equivalent_market_ids=list(bounded_execution_equivalent_market_ids),
                bounded_execution_promotion_candidate_market_ids=list(bounded_execution_promotion_candidate_market_ids),
                stage_summaries_by_market_id={
                    key: dict(value)
                    for key, value in stage_summaries_by_market_id.items()
                },
                pathway_summaries_by_market_id={key: value for key, value in pathway_summaries_by_market_id.items()},
                operator_summaries_by_market_id={key: value for key, value in operator_summaries_by_market_id.items()},
                promotion_summaries_by_market_id={key: value for key, value in promotion_summaries_by_market_id.items()},
                blocker_summaries_by_market_id={key: value for key, value in blocker_summaries_by_market_id.items()},
                promotion_target_pathways_by_market_id=dict(promotion_target_pathways_by_market_id),
                promotion_rules_by_market_id={key: list(value) for key, value in promotion_rules_by_market_id.items()},
                pathway_ladders_by_market_id={key: list(value) for key, value in pathway_ladders_by_market_id.items()},
                blocked_pathways_by_market_id={key: list(value) for key, value in blocked_pathways_by_market_id.items()},
                execution_blocker_codes_by_market_id={
                    key: list(value)
                    for key, value in execution_blocker_codes_by_market_id.items()
                },
                preferred_execution_pathway=candidate.preferred_execution_pathway,
                preferred_execution_mode=candidate.preferred_execution_mode,
                preferred_operator_action=candidate.preferred_operator_action,
                preferred_promotion_target_pathway=candidate.preferred_promotion_target_pathway,
                preferred_execution_selection_reason=str(candidate.metadata.get("preferred_execution_selection_reason") or ""),
                preferred_pathway_summary=str(candidate.metadata.get("preferred_pathway_summary") or ""),
                preferred_operator_summary=str(candidate.metadata.get("preferred_operator_summary") or ""),
                preferred_promotion_summary=str(candidate.metadata.get("preferred_promotion_summary") or ""),
                preferred_blocker_summary=str(candidate.metadata.get("preferred_blocker_summary") or ""),
                preferred_execution_summary=str(candidate.metadata.get("preferred_execution_summary") or ""),
                preferred_execution_capability_summary=str(candidate.metadata.get("preferred_execution_capability_summary") or ""),
                parent_market_ids=relation_context["parent_market_ids"],
                child_market_ids=relation_context["child_market_ids"],
                natural_hedge_market_ids=relation_context["natural_hedge_market_ids"],
                venue_roles=dict(candidate.venue_roles),
                route=candidate.execution_route,
                tradeable=bool(
                    candidate.tradeable
                    and proof.proof_status == MarketEquivalenceProofStatus.proven
                    and edge.executable
                    and arb_plan.executable
                    and preferred_is_equivalent
                ),
                manual_review_required=bool(not candidate.tradeable or proof.manual_review_required or edge.manual_review_required or arb_plan.manual_review_required),
                preferred_execution_market_id=preferred_market_id,
                preferred_execution_venue=market_lookup.get(preferred_market_id, left).venue if market_lookup.get(preferred_market_id, left) else left.venue,
                cross_venue_plan=cross_plan,
                proof=proof,
                executable_edge=edge,
                arb_plan=arb_plan,
                max_unhedged_leg_ms=arb_plan.max_unhedged_leg_ms,
                hedge_completion_ratio=arb_plan.hedge_completion_ratio,
                hedge_completion_ready=arb_plan.hedge_completion_ready,
                parent_child_pair_count=relation_context["parent_child_pair_count"],
                natural_hedge_pair_count=relation_context["natural_hedge_pair_count"],
                family_relation_group_count=relation_context["family_relation_group_count"],
                legging_risk_reasons=list(arb_plan.legging_risk_reasons),
                rationale=_plan_rationale_from_inputs(candidate, proof, edge, arb_plan),
                metadata={
                    "spread_bps": spread_bps,
                    "confidence": confidence,
                    "tradeable": bool(candidate.tradeable),
                    "comparison_state": candidate.comparison_state.value,
                    "cross_venue_plan_id": cross_plan.plan_id if cross_plan is not None else None,
                    "max_unhedged_leg_ms": arb_plan.max_unhedged_leg_ms,
                    "hedge_completion_ratio": arb_plan.hedge_completion_ratio,
                    "hedge_completion_ready": arb_plan.hedge_completion_ready,
                    "legging_risk_reasons": list(arb_plan.legging_risk_reasons),
                    "preferred_execution_is_equivalent": preferred_is_equivalent,
                    "execution_equivalent_market_ids": execution_equivalent_market_ids,
                    "execution_like_market_ids": execution_like_market_ids,
                    "execution_roles_by_market_id": {**execution_roles_by_market_id},
                    "execution_pathways_by_market_id": {**execution_pathways_by_market_id},
                    "readiness_stages_by_market_id": {**readiness_stages_by_market_id},
                    "highest_actionable_modes_by_market_id": {**highest_actionable_modes_by_market_id},
                    "required_operator_actions_by_market_id": {**required_operator_actions_by_market_id},
                    "next_pathways_by_market_id": {**next_pathways_by_market_id},
                    "next_pathway_rules_by_market_id": {
                        key: list(value)
                        for key, value in next_pathway_rules_by_market_id.items()
                    },
                    "bounded_execution_equivalent_market_ids": list(bounded_execution_equivalent_market_ids),
                    "bounded_execution_equivalent_count": len(bounded_execution_equivalent_market_ids),
                    "bounded_execution_promotion_candidate_market_ids": list(bounded_execution_promotion_candidate_market_ids),
                    "bounded_execution_promotion_candidate_count": len(bounded_execution_promotion_candidate_market_ids),
                    "stage_summaries_by_market_id": {
                        key: dict(value)
                        for key, value in stage_summaries_by_market_id.items()
                    },
                    "credential_gates_by_market_id": dict(candidate.metadata.get("credential_gates_by_market_id", {})),
                    "api_gates_by_market_id": dict(candidate.metadata.get("api_gates_by_market_id", {})),
                    "missing_requirement_counts_by_market_id": dict(candidate.metadata.get("missing_requirement_counts_by_market_id", {})),
                    "missing_requirement_market_count": sum(
                        1
                        for value in candidate.metadata.get("missing_requirement_counts_by_market_id", {}).values()
                        if int(value) > 0
                    ),
                    "readiness_scores_by_market_id": dict(candidate.metadata.get("readiness_scores_by_market_id", {})),
                    "operator_checklists_by_market_id": {
                        key: list(value)
                        for key, value in candidate.metadata.get("operator_checklists_by_market_id", {}).items()
                    },
                    "promotion_evidence_by_market_id": {
                        market_id: {
                            pathway: dict(evidence)
                            for pathway, evidence in value.items()
                        }
                        for market_id, value in candidate.metadata.get("promotion_evidence_by_market_id", {}).items()
                    },
                    "preferred_execution_semantics": candidate.metadata.get("preferred_execution_semantics"),
                    "preferred_execution_selection_reason": candidate.metadata.get("preferred_execution_selection_reason"),
                    "preferred_pathway_summary": candidate.metadata.get("preferred_pathway_summary"),
                    "preferred_operator_summary": candidate.metadata.get("preferred_operator_summary"),
                    "preferred_promotion_summary": candidate.metadata.get("preferred_promotion_summary"),
                    "preferred_blocker_summary": candidate.metadata.get("preferred_blocker_summary"),
                    "preferred_execution_summary": candidate.metadata.get("preferred_execution_summary"),
                    "preferred_execution_capability_summary": candidate.metadata.get("preferred_execution_capability_summary"),
                    "mixed_execution_semantics": mixed_execution_semantics,
                    "survivability_hint": survivability_hint,
                    "survivability_by_market_id": dict(candidate.metadata.get("survivability_by_market_id", {})),
                    "requirement_gap_summary_by_market_id": {
                        market_id: dict(value)
                        for market_id, value in candidate.metadata.get("requirement_gap_summary_by_market_id", {}).items()
                    },
                    "multi_leg_operator_checklist": list(multi_leg_operator_checklist),
                    "multi_leg_blocker_codes": list(multi_leg_blocker_codes),
                    "legging_risk_tier": legging_risk_tier,
                    "survivability_summary": survivability_summary,
                    "promotion_target_pathways_by_market_id": {**promotion_target_pathways_by_market_id},
                    "promotion_rules_by_market_id": {
                        key: list(value)
                        for key, value in promotion_rules_by_market_id.items()
                    },
                    "pathway_ladders_by_market_id": {
                        key: list(value)
                        for key, value in pathway_ladders_by_market_id.items()
                    },
                    "blocked_pathways_by_market_id": {
                        key: list(value)
                        for key, value in blocked_pathways_by_market_id.items()
                    },
                    "execution_blocker_codes_by_market_id": {
                        key: list(value)
                        for key, value in execution_blocker_codes_by_market_id.items()
                    },
                    "preferred_execution_pathway": candidate.preferred_execution_pathway,
                    "preferred_execution_mode": candidate.preferred_execution_mode,
                    "preferred_operator_action": candidate.preferred_operator_action,
                    "preferred_promotion_target_pathway": candidate.preferred_promotion_target_pathway,
                    "parent_market_ids": relation_context["parent_market_ids"],
                    "child_market_ids": relation_context["child_market_ids"],
                    "natural_hedge_market_ids": relation_context["natural_hedge_market_ids"],
                    "parent_child_pair_count": relation_context["parent_child_pair_count"],
                    "natural_hedge_pair_count": relation_context["natural_hedge_pair_count"],
                    "parent_child_relation_group_count": relation_context["parent_child_relation_group_count"],
                    "natural_hedge_relation_group_count": relation_context["natural_hedge_relation_group_count"],
                    "family_relation_group_count": relation_context["family_relation_group_count"],
                    "family_relation_kind": relation_context["family_relation_kind"],
                },
            )
            plans.append(plan)
            proofs.append(proof)
            executable_edges.append(edge)
            arb_plans.append(arb_plan)

        return MultiVenueExecutionReport(
            market_count=len(market_list),
            cross_venue_report=cross_report,
            plans=plans,
            proofs=proofs,
            executable_edges=executable_edges,
            arb_plans=arb_plans,
            metadata={
                "market_count": len(market_list),
                "cross_venue_report_id": cross_report.report_id,
                "candidate_count": len(cross_report.execution_candidates),
                "tradeable_plan_count": len([plan for plan in plans if plan.tradeable]),
                "execution_equivalent_plan_count": len([plan for plan in plans if plan.execution_equivalent_market_ids]),
                "execution_like_plan_count": len([plan for plan in plans if plan.execution_like_market_ids]),
                "execution_bindable_plan_count": len([
                    plan
                    for plan in plans
                    if any(stage == "bindable_ready" for stage in plan.readiness_stages_by_market_id.values())
                ]),
                "legging_risk_plan_count": len([plan for plan in plans if plan.legging_risk_reasons]),
                "hedge_completion_ready_plan_count": len([plan for plan in plans if plan.hedge_completion_ready]),
                "max_unhedged_leg_ms_max": max([plan.max_unhedged_leg_ms for plan in plans], default=0),
                "execution_equivalent_market_ids": _dedupe([market_id for plan in plans for market_id in plan.execution_equivalent_market_ids]),
                "execution_like_market_ids": _dedupe([market_id for plan in plans for market_id in plan.execution_like_market_ids]),
                "execution_bindable_market_ids": _dedupe([
                    market_id
                    for plan in plans
                    for market_id, stage in plan.readiness_stages_by_market_id.items()
                    if stage == "bindable_ready"
                ]),
                "execution_roles_by_market_id": {
                    key: value for plan in plans for key, value in plan.execution_roles_by_market_id.items()
                },
                "execution_pathways_by_market_id": {
                    key: value for plan in plans for key, value in plan.execution_pathways_by_market_id.items()
                },
                "readiness_stages_by_market_id": {
                    key: value for plan in plans for key, value in plan.readiness_stages_by_market_id.items()
                },
                "readiness_stage_counts": {
                    stage: sum(
                        1
                        for plan in plans
                        for value in plan.readiness_stages_by_market_id.values()
                        if value == stage
                    )
                    for stage in sorted({
                        value
                        for plan in plans
                        for value in plan.readiness_stages_by_market_id.values()
                    })
                },
                "highest_actionable_modes_by_market_id": {
                    key: value
                    for plan in plans
                    for key, value in plan.highest_actionable_modes_by_market_id.items()
                },
                "required_operator_actions_by_market_id": {
                    key: value
                    for plan in plans
                    for key, value in plan.required_operator_actions_by_market_id.items()
                },
                "next_pathways_by_market_id": {
                    key: value
                    for plan in plans
                    for key, value in plan.next_pathways_by_market_id.items()
                },
                "next_pathway_counts": {
                    pathway: sum(
                        1
                        for plan in plans
                        for value in plan.next_pathways_by_market_id.values()
                        if value == pathway
                    )
                    for pathway in sorted({
                        value
                        for plan in plans
                        for value in plan.next_pathways_by_market_id.values()
                        if value
                    })
                },
                "next_pathway_rules_by_market_id": {
                    key: list(value)
                    for plan in plans
                    for key, value in plan.next_pathway_rules_by_market_id.items()
                },
                "bounded_execution_equivalent_market_ids": _dedupe(
                    market_id
                    for plan in plans
                    for market_id in plan.bounded_execution_equivalent_market_ids
                ),
                "bounded_execution_equivalent_count": len(_dedupe(
                    market_id
                    for plan in plans
                    for market_id in plan.bounded_execution_equivalent_market_ids
                )),
                "bounded_execution_promotion_candidate_market_ids": _dedupe(
                    market_id
                    for plan in plans
                    for market_id in plan.bounded_execution_promotion_candidate_market_ids
                ),
                "bounded_execution_promotion_candidate_count": len(_dedupe(
                    market_id
                    for plan in plans
                    for market_id in plan.bounded_execution_promotion_candidate_market_ids
                )),
                "stage_summaries_by_market_id": {
                    key: dict(value)
                    for plan in plans
                    for key, value in plan.stage_summaries_by_market_id.items()
                },
                "promotion_target_pathways_by_market_id": {
                    key: value
                    for plan in plans
                    for key, value in plan.promotion_target_pathways_by_market_id.items()
                },
                "promotion_rules_by_market_id": {
                    key: list(value)
                    for plan in plans
                    for key, value in plan.promotion_rules_by_market_id.items()
                },
                "pathway_ladders_by_market_id": {
                    key: list(value)
                    for plan in plans
                    for key, value in plan.pathway_ladders_by_market_id.items()
                },
                "blocked_pathways_by_market_id": {
                    key: list(value)
                    for plan in plans
                    for key, value in plan.blocked_pathways_by_market_id.items()
                },
                "execution_blocker_codes_by_market_id": {
                    key: list(value)
                    for plan in plans
                    for key, value in plan.execution_blocker_codes_by_market_id.items()
                },
                **graph_relation_summary,
            },
        )

    def execution_surface(
        self,
        markets: Sequence[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> MultiVenueExecutionSurface:
        return self.build_report(markets, snapshots=snapshots).surface

    def build_paper_report(
        self,
        markets: Sequence[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        target_notional_usd: float | None = None,
        paper_simulator: Any | None = None,
    ) -> Any:
        from .multi_venue_paper import build_multi_venue_paper_report

        return build_multi_venue_paper_report(
            markets,
            snapshots=snapshots,
            target_notional_usd=target_notional_usd,
            paper_simulator=paper_simulator,
        )


def build_multi_venue_execution_report(
    markets: Sequence[MarketDescriptor],
    *,
    snapshots: dict[str, MarketSnapshot] | None = None,
    cross_venue_intelligence: CrossVenueIntelligence | None = None,
    target_notional_usd: float = 1000.0,
    fee_bps: float = 20.0,
    slippage_bps: float = 10.0,
    hedge_risk_bps: float = 10.0,
    confidence_floor: float = 0.5,
) -> MultiVenueExecutionReport:
    executor = MultiVenueExecutor(
        cross_venue_intelligence=cross_venue_intelligence or CrossVenueIntelligence(),
        target_notional_usd=target_notional_usd,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        hedge_risk_bps=hedge_risk_bps,
        confidence_floor=confidence_floor,
    )
    return executor.build_report(markets, snapshots=snapshots)


def build_multi_venue_paper_report(
    markets: Sequence[MarketDescriptor],
    *,
    snapshots: dict[str, MarketSnapshot] | None = None,
    target_notional_usd: float | None = None,
    paper_simulator: Any | None = None,
) -> Any:
    from .multi_venue_paper import build_multi_venue_paper_report as _build_multi_venue_paper_report

    return _build_multi_venue_paper_report(
        markets,
        snapshots=snapshots,
        target_notional_usd=target_notional_usd,
        paper_simulator=paper_simulator,
    )


def _comparison_for(report: CrossVenueIntelligenceReport, comparison_id: str) -> Any | None:
    for comparison in report.comparisons:
        if comparison.comparison_id == comparison_id:
            return comparison
    return None


def _plan_for_candidate(
    plans: Iterable[CrossVenueExecutionPlan],
    candidate_id: str,
) -> CrossVenueExecutionPlan | None:
    for plan in plans:
        if plan.candidate_id == candidate_id:
            return plan
    return None


def _relation_context_for_markets(
    group_index: dict[str, ComparableMarketGroup],
    market_ids: Sequence[str],
) -> dict[str, Any]:
    groups: list[ComparableMarketGroup] = []
    seen_group_ids: set[str] = set()
    for market_id in market_ids:
        group = group_index.get(market_id)
        if group is None or group.group_id in seen_group_ids:
            continue
        seen_group_ids.add(group.group_id)
        groups.append(group)
    return _relation_summary_from_groups(groups)


def _relation_summary_from_groups(groups: Sequence[ComparableMarketGroup]) -> dict[str, Any]:
    parent_market_ids: list[str] = []
    child_market_ids: list[str] = []
    natural_hedge_market_ids: list[str] = []
    parent_child_pair_count = 0
    natural_hedge_pair_count = 0
    parent_child_relation_group_count = 0
    natural_hedge_relation_group_count = 0
    family_relation_group_count = 0
    for group in groups:
        has_parent_child = bool(group.parent_child_pairs)
        has_natural_hedge = bool(group.natural_hedge_pairs)
        if has_parent_child:
            parent_child_relation_group_count += 1
            parent_child_pair_count += len(group.parent_child_pairs)
            parent_market_ids.extend(group.parent_market_ids)
            child_market_ids.extend(group.child_market_ids)
        if has_natural_hedge:
            natural_hedge_relation_group_count += 1
            natural_hedge_pair_count += len(group.natural_hedge_pairs)
            natural_hedge_market_ids.extend(group.natural_hedge_market_ids)
        if has_parent_child or has_natural_hedge:
            family_relation_group_count += 1
    if parent_child_relation_group_count and not natural_hedge_relation_group_count:
        family_relation_kind = "parent_child"
    elif natural_hedge_relation_group_count and not parent_child_relation_group_count:
        family_relation_kind = "natural_hedge"
    elif family_relation_group_count:
        family_relation_kind = "mixed"
    else:
        family_relation_kind = "none"
    return {
        "parent_market_ids": _dedupe(parent_market_ids),
        "child_market_ids": _dedupe(child_market_ids),
        "natural_hedge_market_ids": _dedupe(natural_hedge_market_ids),
        "parent_child_pair_count": parent_child_pair_count,
        "natural_hedge_pair_count": natural_hedge_pair_count,
        "parent_child_relation_group_count": parent_child_relation_group_count,
        "natural_hedge_relation_group_count": natural_hedge_relation_group_count,
        "family_relation_group_count": family_relation_group_count,
        "family_relation_kind": family_relation_kind,
    }


def _plan_rationale_from_inputs(
    candidate: CrossVenueExecutionCandidate,
    proof: MarketEquivalenceProof,
    edge: ExecutableEdge,
    arb_plan: ArbPlan,
) -> str:
    parts = [
        f"route={candidate.execution_route}",
        f"proof={proof.proof_status.value}",
        f"edge_bps={edge.executable_edge_bps:.2f}",
        f"arb_capital={arb_plan.required_capital_usd:.2f}",
    ]
    if candidate.tradeable:
        parts.append("tradeable")
    if candidate.signal_market_ids:
        parts.append(f"signal_markets={','.join(candidate.signal_market_ids[:3])}")
    if candidate.reference_market_ids:
        parts.append(f"reference_markets={','.join(candidate.reference_market_ids[:3])}")
    if arb_plan.legging_risk_reasons:
        parts.append(f"legging_risk={','.join(arb_plan.legging_risk_reasons[:3])}")
    return " | ".join(parts)


def _legging_risk_tier(
    *,
    max_unhedged_leg_ms: int,
    hedge_completion_ratio: float,
    hedge_completion_ready: bool,
    legging_risk_reasons: Sequence[str],
) -> str:
    if max_unhedged_leg_ms >= 5000 or hedge_completion_ratio < 0.5:
        return "high"
    if legging_risk_reasons or not hedge_completion_ready or max_unhedged_leg_ms > 1500:
        return "medium"
    return "low"


def _plan_survivability_hint(
    *,
    base_hint: str,
    tradeable: bool,
    legging_risk_tier: str,
    hedge_completion_ready: bool,
) -> str:
    if not tradeable:
        return base_hint or "manual_review_before_multi_leg"
    if legging_risk_tier == "low" and hedge_completion_ready:
        return "multi_leg_survivable"
    if legging_risk_tier in {"medium", "high"}:
        return "survivable_with_monitoring"
    return base_hint or "survivable_with_monitoring"


def _build_multi_leg_operator_checklist(
    *,
    base_checklist: Sequence[str],
    max_unhedged_leg_ms: int,
    hedge_completion_ratio: float,
    hedge_completion_ready: bool,
    legging_risk_tier: str,
) -> list[str]:
    checklist = list(base_checklist)
    checklist.extend(
        [
            f"hedge:max_unhedged_leg_ms:{max_unhedged_leg_ms}",
            f"hedge:completion_ratio:{hedge_completion_ratio:.3f}",
            f"hedge:completion_ready:{str(bool(hedge_completion_ready)).lower()}",
            f"hedge:legging_risk_tier:{legging_risk_tier}",
        ]
    )
    return list(dict.fromkeys(str(item) for item in checklist if str(item)))


def _build_multi_leg_blocker_codes(
    *,
    base_codes: Sequence[str],
    legging_risk_reasons: Sequence[str],
    hedge_completion_ready: bool,
    tradeable: bool,
    legging_risk_tier: str,
) -> list[str]:
    codes = [str(code) for code in base_codes if str(code)]
    if not hedge_completion_ready:
        codes.append("hedge_completion_not_ready")
    if not tradeable:
        codes.append("multi_leg_not_tradeable")
    if legging_risk_tier == "high":
        codes.append("high_legging_risk")
    elif legging_risk_tier == "medium":
        codes.append("medium_legging_risk")
    codes.extend(str(reason) for reason in legging_risk_reasons if str(reason))
    return list(dict.fromkeys(codes))


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(_normalized_text(item) for item in items if _normalized_text(item)))


__all__ = [
    "MultiVenueExecutionPlan",
    "MultiVenueExecutionReport",
    "MultiVenueExecutionSurface",
    "MultiVenueExecutor",
    "build_multi_venue_execution_report",
    "build_multi_venue_paper_report",
]
