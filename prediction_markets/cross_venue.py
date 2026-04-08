from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .additional_venues import DEFAULT_ADDITIONAL_VENUE_MATRIX, VenueCapabilityMatrix
from .market_graph import ComparableMarketGroup, CrossVenueMatchRejection, MarketGraph, MarketGraphBuilder
from .models import (
    CrossVenueMatch,
    MarketDescriptor,
    MarketSnapshot,
    VenueName,
    VenueType,
    _first_non_empty,
    _metadata_string,
    _normalized_text,
)
from .registry import DEFAULT_VENUE_EXECUTION_REGISTRY, VenueExecutionRegistry, VenueRoleClassification


class SpreadSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class CrossVenueOpsState(str, Enum):
    comparison_only = "comparison_only"
    manual_review = "manual_review"
    signal_only = "signal_only"
    executable_candidate = "executable_candidate"
    signal_candidate = "signal_candidate"
    spread_alert = "spread_alert"


class CrossVenueTaxonomy(str, Enum):
    comparison_only = "comparison_only"
    relative_value = "relative_value"
    cross_venue_signal = "cross_venue_signal"
    true_arbitrage = "true_arbitrage"


class CrossVenueComparison(BaseModel):
    schema_version: str = "v1"
    comparison_id: str = Field(default_factory=lambda: f"cvcomp_{uuid4().hex[:12]}")
    left_market_id: str
    right_market_id: str
    left_venue: VenueName
    right_venue: VenueName
    canonical_event_id: str
    question_left: str = ""
    question_right: str = ""
    question_key: str = ""
    left_resolution_source: str | None = None
    right_resolution_source: str | None = None
    left_currency: str | None = None
    right_currency: str | None = None
    left_payout_currency: str | None = None
    right_payout_currency: str | None = None
    resolution_compatibility_score: float = 0.0
    payout_compatibility_score: float = 0.0
    currency_compatibility_score: float = 0.0
    timing_compatibility_score: float = 0.0
    left_probability: float | None = None
    right_probability: float | None = None
    probability_delta: float | None = None
    spread_bps: float | None = None
    compatible_resolution: bool = False
    reference_market_id: str | None = None
    comparison_market_id: str | None = None
    comparable_group_id: str | None = None
    comparable_market_refs: list[str] = Field(default_factory=list)
    classification: str = "signal-only"
    taxonomy: CrossVenueTaxonomy = CrossVenueTaxonomy.comparison_only
    rationale: str = ""
    comparison_state: CrossVenueOpsState = CrossVenueOpsState.comparison_only
    narrative_risk_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueSpreadAlert(BaseModel):
    schema_version: str = "v1"
    alert_id: str = Field(default_factory=lambda: f"cvspread_{uuid4().hex[:12]}")
    comparison_id: str
    severity: SpreadSeverity = SpreadSeverity.low
    spread_bps: float
    threshold_bps: float
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueExecutionCandidate(BaseModel):
    schema_version: str = "v1"
    candidate_id: str = Field(default_factory=lambda: f"cvec_{uuid4().hex[:12]}")
    comparison_id: str
    canonical_event_id: str
    market_ids: list[str] = Field(default_factory=list)
    venue_roles: dict[str, list[str]] = Field(default_factory=dict)
    preferred_execution_market_id: str | None = None
    preferred_execution_venue: VenueName | None = None
    signal_market_ids: list[str] = Field(default_factory=list)
    reference_market_ids: list[str] = Field(default_factory=list)
    comparable_group_id: str | None = None
    comparison_state: CrossVenueOpsState = CrossVenueOpsState.comparison_only
    execution_route: str = "comparison_only"
    tradeable: bool = False
    spread_bps: float | None = None
    classification: str = "signal-only"
    taxonomy: CrossVenueTaxonomy = CrossVenueTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    preferred_execution_pathway: str | None = None
    preferred_execution_mode: str | None = None
    preferred_operator_action: str | None = None
    preferred_promotion_target_pathway: str | None = None
    preferred_execution_selection_reason: str = ""
    pathway_summary: str = ""
    operator_summary: str = ""
    promotion_summary: str = ""
    blocker_summary: str = ""
    preferred_execution_summary: str = ""
    preferred_execution_capability_summary: str = ""
    execution_pathways_by_market_id: dict[str, str] = Field(default_factory=dict)
    readiness_stages_by_market_id: dict[str, str] = Field(default_factory=dict)
    highest_actionable_modes_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    required_operator_actions_by_market_id: dict[str, str] = Field(default_factory=dict)
    next_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    next_pathway_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    bounded_execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    bounded_execution_promotion_candidate_market_ids: list[str] = Field(default_factory=list)
    stage_summaries_by_market_id: dict[str, dict[str, Any]] = Field(default_factory=dict)
    promotion_target_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    promotion_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    pathway_ladders_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    blocked_pathways_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    execution_blocker_codes_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueExecutionPlanLeg(BaseModel):
    schema_version: str = "v1"
    leg_id: str = Field(default_factory=lambda: f"cvleg_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    venue_roles: list[str] = Field(default_factory=list)
    planning_bucket: str = "watchlist"
    execution_role: str = "watchlist"
    execution_pathway: str = "read_only"
    readiness_stage: str = "read_only"
    highest_actionable_mode: str | None = None
    required_operator_action: str = "no_order_routing"
    next_pathway: str | None = None
    next_pathway_rules: list[str] = Field(default_factory=list)
    bounded_execution_equivalent: bool = False
    bounded_execution_promotion_candidate: bool = False
    stage_summary: dict[str, Any] = Field(default_factory=dict)
    promotion_target_pathway: str | None = None
    promotion_rules: list[str] = Field(default_factory=list)
    pathway_ladder: list[str] = Field(default_factory=list)
    blocked_pathways: list[str] = Field(default_factory=list)
    execution_blocker_codes: list[str] = Field(default_factory=list)
    tradeable: bool = False
    read_only: bool = True
    preferred_execution: bool = False
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueExecutionPlan(BaseModel):
    schema_version: str = "v1"
    plan_id: str = Field(default_factory=lambda: f"cvplan_{uuid4().hex[:12]}")
    candidate_id: str
    comparison_id: str
    canonical_event_id: str
    market_ids: list[str] = Field(default_factory=list)
    read_only_market_ids: list[str] = Field(default_factory=list)
    venue_roles: dict[str, list[str]] = Field(default_factory=dict)
    reference_market_ids: list[str] = Field(default_factory=list)
    signal_market_ids: list[str] = Field(default_factory=list)
    execution_equivalent_market_ids: list[str] = Field(default_factory=list)
    execution_like_market_ids: list[str] = Field(default_factory=list)
    reference_only_market_ids: list[str] = Field(default_factory=list)
    watchlist_market_ids: list[str] = Field(default_factory=list)
    execution_market_ids: list[str] = Field(default_factory=list)
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
    promotion_target_pathways_by_market_id: dict[str, str | None] = Field(default_factory=dict)
    promotion_rules_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    pathway_ladders_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    blocked_pathways_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    execution_blocker_codes_by_market_id: dict[str, list[str]] = Field(default_factory=dict)
    comparable_group_id: str | None = None
    comparison_state: CrossVenueOpsState = CrossVenueOpsState.comparison_only
    execution_route: str = "comparison_only"
    tradeable: bool = False
    manual_review_required: bool = False
    spread_bps: float | None = None
    classification: str = "signal-only"
    taxonomy: CrossVenueTaxonomy = CrossVenueTaxonomy.comparison_only
    execution_filter_reason_codes: list[str] = Field(default_factory=list)
    preferred_execution_pathway: str | None = None
    preferred_execution_mode: str | None = None
    preferred_operator_action: str | None = None
    preferred_promotion_target_pathway: str | None = None
    preferred_execution_selection_reason: str = ""
    pathway_summary: str = ""
    operator_summary: str = ""
    promotion_summary: str = ""
    blocker_summary: str = ""
    preferred_execution_summary: str = ""
    preferred_execution_capability_summary: str = ""
    rationale: str = ""
    legs: list[CrossVenueExecutionPlanLeg] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueQualificationSummary(BaseModel):
    schema_version: str = "v1"
    venue_roles: dict[str, list[str]] = Field(default_factory=dict)
    role_venues: dict[str, list[str]] = Field(default_factory=dict)
    role_counts: dict[str, int] = Field(default_factory=dict)


class CrossVenueOpsSummary(BaseModel):
    schema_version: str = "v1"
    comparison_only_count: int = 0
    manual_review_count: int = 0
    signal_candidate_count: int = 0
    executable_candidate_count: int = 0
    spread_alert_count: int = 0
    comparable_group_count: int = 0
    reference_market_count: int = 0
    manual_review_group_count: int = 0
    comparison_only_group_count: int = 0
    narrative_risk_count: int = 0
    reason_counts: dict[str, int] = Field(default_factory=dict)


class CrossVenueRoutingSurface(BaseModel):
    schema_version: str = "v1"
    report_id: str | None = None
    market_count: int = 0
    comparable_group_count: int = 0
    execution_candidate_count: int = 0
    execution_plan_count: int = 0
    tradeable_candidate_count: int = 0
    manual_review_count: int = 0
    comparison_only_count: int = 0
    signal_candidate_count: int = 0
    spread_alert_count: int = 0
    signal_only_market_ids: list[str] = Field(default_factory=list)
    tradeable_market_ids: list[str] = Field(default_factory=list)
    arbitrage_candidate_market_ids: list[str] = Field(default_factory=list)
    read_only_market_ids: list[str] = Field(default_factory=list)
    classification_by_market_id: dict[str, str] = Field(default_factory=dict)
    classification_counts: dict[str, int] = Field(default_factory=dict)
    comparison_classification_counts: dict[str, int] = Field(default_factory=dict)
    compared_market_count: int = 0
    grouped_market_count: int = 0
    grouped_market_coverage_rate: float = 0.0
    comparable_market_coverage_rate: float = 0.0
    unmatched_market_count: int = 0
    duplicate_market_count: int = 0
    duplicate_market_rate: float = 0.0
    duplicate_group_count: int = 0
    average_duplicate_group_size: float = 0.0
    desaligned_comparison_count: int = 0
    desaligned_comparison_rate: float = 0.0
    desaligned_group_count: int = 0
    desaligned_group_rate: float = 0.0
    manual_review_due_to_alignment_count: int = 0
    manual_review_due_to_alignment_rate: float = 0.0
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    mismatch_reason_counts: dict[str, int] = Field(default_factory=dict)
    match_desalignment_dimension_counts: dict[str, int] = Field(default_factory=dict)
    group_desalignment_dimension_counts: dict[str, int] = Field(default_factory=dict)
    mapper_precision: float = 0.0
    false_match_rate: float = 0.0
    false_match_count: int = 0
    spread_capture_rate: float = 0.0
    min_cross_venue_similarity_score: float = 0.0
    execution_routes: dict[str, int] = Field(default_factory=dict)
    planning_buckets: dict[str, str] = Field(default_factory=dict)
    comparison_states: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueIntelligenceReport(BaseModel):
    schema_version: str = "v1"
    report_id: str = Field(default_factory=lambda: f"cvrpt_{uuid4().hex[:12]}")
    matches: list[CrossVenueMatch] = Field(default_factory=list)
    rejected_matches: list[CrossVenueMatchRejection] = Field(default_factory=list)
    comparisons: list[CrossVenueComparison] = Field(default_factory=list)
    execution_candidates: list[CrossVenueExecutionCandidate] = Field(default_factory=list)
    execution_plans: list[CrossVenueExecutionPlan] = Field(default_factory=list)
    spread_alerts: list[CrossVenueSpreadAlert] = Field(default_factory=list)
    comparable_groups: list[ComparableMarketGroup] = Field(default_factory=list)
    reference_market_ids: list[str] = Field(default_factory=list)
    qualification_summary: CrossVenueQualificationSummary = Field(default_factory=CrossVenueQualificationSummary)
    venue_role_classification: VenueRoleClassification = Field(default_factory=VenueRoleClassification)
    ops_summary: CrossVenueOpsSummary = Field(default_factory=CrossVenueOpsSummary)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class CrossVenueIntelligence:
    match_threshold: float = 0.6
    spread_threshold_bps: float = 80.0
    min_resolution_compatibility_score: float = 1.0
    min_payout_compatibility_score: float = 1.0
    min_currency_compatibility_score: float = 1.0
    graph_builder: MarketGraphBuilder = field(default_factory=MarketGraphBuilder)
    venue_matrix: VenueCapabilityMatrix = field(default_factory=lambda: DEFAULT_ADDITIONAL_VENUE_MATRIX)
    execution_registry: VenueExecutionRegistry = field(default_factory=lambda: DEFAULT_VENUE_EXECUTION_REGISTRY)

    def build_matches(self, markets: list[MarketDescriptor]) -> list[CrossVenueMatch]:
        graph = self.graph_builder.build(markets)
        return list(graph.matches)

    def build_comparisons(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        graph: MarketGraph | None = None,
    ) -> list[CrossVenueComparison]:
        snapshots = snapshots or {}
        comparisons: list[CrossVenueComparison] = []
        matches = self.build_matches(markets)
        group_by_market_id = graph.comparable_group_index() if graph is not None else {}
        for match in matches:
            left = self._get_market(markets, match.left_market_id)
            right = self._get_market(markets, match.right_market_id)
            left_snapshot = snapshots.get(left.market_id)
            right_snapshot = snapshots.get(right.market_id)
            timing_score, timing_notes, timing_metadata = MarketGraphBuilder._timing_compatibility(left, right)
            left_probability = self._probability(left_snapshot)
            right_probability = self._probability(right_snapshot)
            probability_delta = None
            spread_bps = None
            if left_probability is not None and right_probability is not None:
                probability_delta = round(left_probability - right_probability, 6)
                spread_bps = round(abs(probability_delta) * 10000.0, 2)
            reference_id, comparison_id = self._reference_pair(left, right)
            comparable_group_id = None
            group = group_by_market_id.get(left.market_id) or group_by_market_id.get(right.market_id)
            if group is not None:
                comparable_group_id = group.group_id
            question_key = self._market_question_key(left, right)
            left_resolution_source = self._market_resolution_source(left)
            right_resolution_source = self._market_resolution_source(right)
            left_currency = self._market_currency(left)
            right_currency = self._market_currency(right)
            left_payout_currency = self._market_payout_currency(left)
            right_payout_currency = self._market_payout_currency(right)
            notes = self._comparison_notes(
                left=left,
                right=right,
                compatible_resolution=match.compatible_resolution,
                left_currency=left_currency,
                right_currency=right_currency,
                left_payout_currency=left_payout_currency,
                right_payout_currency=right_payout_currency,
                timing_notes=timing_notes,
            )
            narrative_risk_flags = self._narrative_risk_flags(
                match,
                left,
                right,
                spread_bps,
                timing_notes=timing_notes,
            )
            comparison_state = self._comparison_state(
                match,
                spread_bps,
                timing_compatibility_score=timing_score,
                narrative_risk_flags=narrative_risk_flags,
            )
            taxonomy = self._comparison_taxonomy(comparison_state, spread_bps)
            comparisons.append(
                CrossVenueComparison(
                    left_market_id=left.market_id,
                    right_market_id=right.market_id,
                    left_venue=left.venue,
                    right_venue=right.venue,
                    canonical_event_id=match.canonical_event_id,
                    question_left=left.question,
                    question_right=right.question,
                    question_key=question_key,
                    left_resolution_source=left_resolution_source,
                    right_resolution_source=right_resolution_source,
                    left_currency=left_currency,
                    right_currency=right_currency,
                    left_payout_currency=left_payout_currency,
                    right_payout_currency=right_payout_currency,
                    resolution_compatibility_score=1.0 if match.compatible_resolution else 0.0,
                    payout_compatibility_score=1.0 if self._compatible_payout(left, right) else 0.0,
                    currency_compatibility_score=1.0 if self._compatible_currency(left, right) else 0.0,
                    timing_compatibility_score=timing_score,
                    left_probability=left_probability,
                    right_probability=right_probability,
                    probability_delta=probability_delta,
                    spread_bps=spread_bps,
                    compatible_resolution=match.compatible_resolution,
                    reference_market_id=reference_id,
                    comparison_market_id=comparison_id,
                    comparable_group_id=comparable_group_id,
                    comparable_market_refs=[left.market_id, right.market_id],
                    classification=self._comparison_classification(comparison_state, spread_bps),
                    taxonomy=taxonomy,
                    rationale=match.rationale,
                    comparison_state=comparison_state,
                    narrative_risk_flags=narrative_risk_flags,
                    notes=notes,
                    metadata={
                        "match_id": match.match_id,
                        "similarity": match.similarity,
                        "manual_review_required": match.manual_review_required,
                        "left_roles": self._market_roles(left),
                        "right_roles": self._market_roles(right),
                        "comparable_group_id": comparable_group_id,
                        "question_key": question_key,
                        "left_resolution_source": left_resolution_source,
                        "right_resolution_source": right_resolution_source,
                        "left_currency": left_currency,
                        "right_currency": right_currency,
                        "left_payout_currency": left_payout_currency,
                        "right_payout_currency": right_payout_currency,
                        "timing_compatibility_score": timing_score,
                        "timing_mismatch_reasons": list(timing_notes),
                        "timing": timing_metadata,
                        "min_resolution_compatibility_score": self.min_resolution_compatibility_score,
                        "min_payout_compatibility_score": self.min_payout_compatibility_score,
                        "min_currency_compatibility_score": self.min_currency_compatibility_score,
                        "comparison_state": comparison_state.value,
                        "classification": self._comparison_classification(comparison_state, spread_bps),
                        "taxonomy": taxonomy.value,
                        "narrative_risk_flags": narrative_risk_flags,
                        "notes": notes,
                    },
                )
            )
        return comparisons

    def build_report(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> CrossVenueIntelligenceReport:
        snapshots = snapshots or {}
        graph = self.graph_builder.build(markets, snapshots=snapshots)
        comparisons = self.build_comparisons(markets, snapshots=snapshots, graph=graph)
        execution_candidates: list[CrossVenueExecutionCandidate] = []
        execution_plans: list[CrossVenueExecutionPlan] = []
        spread_alerts: list[CrossVenueSpreadAlert] = []
        reference_market_ids = [node.market_id for node in graph.nodes if node.role == "reference"]
        qualification_summary = self._qualification_summary(markets)
        venue_role_classification = self._venue_role_classification()
        comparable_groups = list(graph.comparable_groups)
        rejected_matches = list(graph.rejected_matches)

        for comparison in comparisons:
            candidate = self._execution_candidate_for(comparison, markets)
            if candidate is not None:
                execution_candidates.append(candidate)
                execution_plans.append(self._execution_plan_for(candidate, markets))
            if comparison.spread_bps is None:
                continue
            if comparison.spread_bps < self.spread_threshold_bps:
                continue
            severity = self._severity_for_spread(comparison.spread_bps)
            spread_alerts.append(
                CrossVenueSpreadAlert(
                    comparison_id=comparison.comparison_id,
                    severity=severity,
                    spread_bps=comparison.spread_bps,
                    threshold_bps=self.spread_threshold_bps,
                    message=(
                        f"Cross-venue spread {comparison.spread_bps:.2f} bps "
                        f"exceeds threshold {self.spread_threshold_bps:.2f} bps."
                    ),
                    metadata={
                        "left_market_id": comparison.left_market_id,
                        "right_market_id": comparison.right_market_id,
                        "reference_market_id": comparison.reference_market_id,
                    },
                )
            )

        ops_summary = self._ops_summary(
            comparisons=comparisons,
            execution_candidates=execution_candidates,
            spread_alerts=spread_alerts,
            comparable_groups=comparable_groups,
            reference_market_ids=reference_market_ids,
        )
        comparison_classification_counts = self._comparison_classification_counts(comparisons)
        comparison_taxonomy_counts = self._comparison_taxonomy_counts(comparisons)
        candidate_taxonomy_counts = self._candidate_taxonomy_counts(execution_candidates)
        plan_taxonomy_counts = self._plan_taxonomy_counts(execution_plans)
        mapper_precision = round(len(graph.matches) / max(1, len(graph.matches) + len(rejected_matches)), 6)
        false_match_rate = round(len(rejected_matches) / max(1, len(graph.matches) + len(rejected_matches)), 6)
        min_cross_venue_similarity_score = round(
            min(
                [match.similarity for match in graph.matches] + [rejection.similarity for rejection in rejected_matches],
                default=0.0,
            ),
            6,
        )
        compared_market_ids = sorted(
            {
                market_id
                for comparison in comparisons
                for market_id in (comparison.left_market_id, comparison.right_market_id)
            }
        )
        comparable_market_coverage_rate = round(len(compared_market_ids) / max(1, len(markets)), 6)
        duplicate_market_count = int(graph.metadata.get("duplicate_market_count", 0))
        duplicate_market_rate = float(graph.metadata.get("duplicate_market_rate", 0.0))
        desaligned_comparison_count = sum(
            1
            for comparison in comparisons
            if self._comparison_alignment_gap_count(comparison) > 0
        )
        manual_review_due_to_alignment_count = sum(
            1
            for comparison in comparisons
            if comparison.comparison_state == CrossVenueOpsState.manual_review
            and self._comparison_alignment_gap_count(comparison) > 0
        )
        desaligned_group_count = sum(
            1
            for group in comparable_groups
            if int(getattr(group, "desalignment_count", 0) or group.metadata.get("desalignment_count", 0)) > 0
        )

        return CrossVenueIntelligenceReport(
            matches=graph.matches,
            rejected_matches=rejected_matches,
            comparisons=comparisons,
            execution_candidates=execution_candidates,
            execution_plans=execution_plans,
            spread_alerts=spread_alerts,
            comparable_groups=comparable_groups,
            reference_market_ids=reference_market_ids,
            qualification_summary=qualification_summary,
            venue_role_classification=venue_role_classification,
            ops_summary=ops_summary,
            # Timing alignment is now surfaced explicitly at report level.
            metadata={
                "market_count": len(markets),
                "match_threshold": self.match_threshold,
                "spread_threshold_bps": self.spread_threshold_bps,
                "min_resolution_compatibility_score": self.min_resolution_compatibility_score,
                "min_payout_compatibility_score": self.min_payout_compatibility_score,
                "min_currency_compatibility_score": self.min_currency_compatibility_score,
                "compatibility_thresholds": {
                    "resolution": self.min_resolution_compatibility_score,
                    "payout": self.min_payout_compatibility_score,
                    "currency": self.min_currency_compatibility_score,
                },
                "rejected_match_count": len(rejected_matches),
                "matched_pair_count": len(graph.matches),
                "mapper_precision": mapper_precision,
                "false_match_rate": false_match_rate,
                "false_match_count": len(rejected_matches),
                "min_cross_venue_similarity_score": min_cross_venue_similarity_score,
                "venue_roles": qualification_summary.venue_roles,
                "role_counts": qualification_summary.role_counts,
                "planning_buckets": venue_role_classification.metadata.get("planning_buckets", {}),
                "execution_equivalent_venues": [venue.value for venue in venue_role_classification.execution_equivalent_venues],
                "execution_bindable_venues": [venue.value for venue in venue_role_classification.execution_bindable_venues],
                "execution_like_venues": [venue.value for venue in venue_role_classification.execution_like_venues],
                "reference_only_venues": [venue.value for venue in venue_role_classification.reference_only_venues],
                "watchlist_only_venues": [venue.value for venue in venue_role_classification.watchlist_only_venues],
                "execution_equivalent_count": len(venue_role_classification.execution_equivalent_venues),
                "execution_bindable_count": len(venue_role_classification.execution_bindable_venues),
                "execution_like_count": len(venue_role_classification.execution_like_venues),
                "reference_only_count": len(venue_role_classification.reference_only_venues),
                "watchlist_only_count": len(venue_role_classification.watchlist_only_venues),
                "execution_taxonomy_counts": venue_role_classification.metadata.get("execution_taxonomy_counts", {}),
                "comparable_group_count": len(comparable_groups),
                "comparison_state_counts": ops_summary.reason_counts,
                "comparison_classification_counts": comparison_classification_counts,
                "comparison_taxonomy_counts": comparison_taxonomy_counts,
                "candidate_taxonomy_counts": candidate_taxonomy_counts,
                "plan_taxonomy_counts": plan_taxonomy_counts,
                "compared_market_count": len(compared_market_ids),
                "grouped_market_count": int(graph.metadata.get("grouped_market_count", 0)),
                "grouped_market_coverage_rate": float(graph.metadata.get("grouped_market_coverage_rate", 0.0)),
                "comparable_market_coverage_rate": comparable_market_coverage_rate,
                "unmatched_market_count": max(0, len(markets) - len(compared_market_ids)),
                "duplicate_market_count": duplicate_market_count,
                "duplicate_market_rate": duplicate_market_rate,
                "duplicate_group_count": int(graph.metadata.get("duplicate_group_count", 0)),
                "average_duplicate_group_size": float(graph.metadata.get("average_duplicate_group_size", 0.0)),
                "desaligned_comparison_count": desaligned_comparison_count,
                "desaligned_comparison_rate": round(desaligned_comparison_count / max(1, len(comparisons)), 6),
                "desaligned_group_count": desaligned_group_count,
                "desaligned_group_rate": round(desaligned_group_count / max(1, len(comparable_groups)), 6),
                "manual_review_due_to_alignment_count": manual_review_due_to_alignment_count,
                "manual_review_due_to_alignment_rate": round(manual_review_due_to_alignment_count / max(1, len(comparisons)), 6),
                "rejection_reason_counts": dict(graph.metadata.get("rejection_reason_counts", {})),
                "mismatch_reason_counts": dict(graph.metadata.get("mismatch_reason_counts", {})),
                "match_desalignment_dimension_counts": dict(graph.metadata.get("match_desalignment_dimension_counts", {})),
                "group_desalignment_dimension_counts": dict(graph.metadata.get("group_desalignment_dimension_counts", {})),
                "execution_candidate_count": len(execution_candidates),
                "execution_plan_count": len(execution_plans),
                "timing_mismatch_count": sum(1 for comparison in comparisons if comparison.timing_compatibility_score < 1.0),
                "timing_compatibility_average": round(
                    sum(comparison.timing_compatibility_score for comparison in comparisons) / max(1, len(comparisons)),
                    6,
                ),
                "classification_counts": self._classification_counts(comparisons),
                "spread_capture_rate": self._spread_capture_rate(comparisons, execution_candidates),
                "venue_role_classification": venue_role_classification.model_dump(mode="json"),
            },
        )

    def routing_surface(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> CrossVenueRoutingSurface:
        report = self.build_report(markets, snapshots=snapshots)
        execution_routes: dict[str, int] = {}
        classification_by_market_id: dict[str, str] = {}
        read_only_market_ids: list[str] = []
        for comparison in report.comparisons:
            for market_id in (comparison.left_market_id, comparison.right_market_id):
                previous = classification_by_market_id.get(market_id)
                classification_by_market_id[market_id] = self._merge_classification(previous, comparison.classification)
        for plan in report.execution_plans:
            execution_routes[plan.execution_route] = execution_routes.get(plan.execution_route, 0) + 1
            read_only_market_ids.extend(plan.read_only_market_ids)
            classification = plan.classification or self._plan_classification_from_state(plan.comparison_state, plan.spread_bps)
            for market_id in plan.market_ids:
                previous = classification_by_market_id.get(market_id)
                classification_by_market_id[market_id] = self._merge_classification(previous, classification)
        tradeable_market_ids = [market_id for market_id, classification in classification_by_market_id.items() if classification in {"tradeable", "arbitrage-candidate"}]
        arbitrage_candidate_market_ids = [market_id for market_id, classification in classification_by_market_id.items() if classification == "arbitrage-candidate"]
        signal_only_market_ids = [market_id for market_id, classification in classification_by_market_id.items() if classification == "signal-only"]
        classification_counts: dict[str, int] = {}
        for classification in classification_by_market_id.values():
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
        comparison_classification_counts = dict(report.metadata.get("comparison_classification_counts", {}))
        spread_capture_rate = float(report.metadata.get("spread_capture_rate", 0.0))
        return CrossVenueRoutingSurface(
            report_id=report.report_id,
            market_count=report.metadata.get("market_count", len(markets)),
            comparable_group_count=len(report.comparable_groups),
            execution_candidate_count=len(report.execution_candidates),
            execution_plan_count=len(report.execution_plans),
            tradeable_candidate_count=sum(1 for candidate in report.execution_candidates if candidate.tradeable),
            manual_review_count=report.ops_summary.manual_review_count,
            comparison_only_count=report.ops_summary.comparison_only_count,
            signal_candidate_count=report.ops_summary.signal_candidate_count,
            spread_alert_count=report.ops_summary.spread_alert_count,
            signal_only_market_ids=list(dict.fromkeys(signal_only_market_ids)),
            tradeable_market_ids=list(dict.fromkeys(tradeable_market_ids)),
            arbitrage_candidate_market_ids=list(dict.fromkeys(arbitrage_candidate_market_ids)),
            read_only_market_ids=list(dict.fromkeys(read_only_market_ids or report.reference_market_ids)),
            classification_by_market_id={key: classification_by_market_id[key] for key in sorted(classification_by_market_id)},
            classification_counts={key: value for key, value in sorted(classification_counts.items())},
            comparison_classification_counts={key: value for key, value in sorted(comparison_classification_counts.items())},
            compared_market_count=int(report.metadata.get("compared_market_count", 0)),
            grouped_market_count=int(report.metadata.get("grouped_market_count", 0)),
            grouped_market_coverage_rate=float(report.metadata.get("grouped_market_coverage_rate", 0.0)),
            comparable_market_coverage_rate=float(report.metadata.get("comparable_market_coverage_rate", 0.0)),
            unmatched_market_count=int(report.metadata.get("unmatched_market_count", 0)),
            duplicate_market_count=int(report.metadata.get("duplicate_market_count", 0)),
            duplicate_market_rate=float(report.metadata.get("duplicate_market_rate", 0.0)),
            duplicate_group_count=int(report.metadata.get("duplicate_group_count", 0)),
            average_duplicate_group_size=float(report.metadata.get("average_duplicate_group_size", 0.0)),
            desaligned_comparison_count=int(report.metadata.get("desaligned_comparison_count", 0)),
            desaligned_comparison_rate=float(report.metadata.get("desaligned_comparison_rate", 0.0)),
            desaligned_group_count=int(report.metadata.get("desaligned_group_count", 0)),
            desaligned_group_rate=float(report.metadata.get("desaligned_group_rate", 0.0)),
            manual_review_due_to_alignment_count=int(report.metadata.get("manual_review_due_to_alignment_count", 0)),
            manual_review_due_to_alignment_rate=float(report.metadata.get("manual_review_due_to_alignment_rate", 0.0)),
            rejection_reason_counts=dict(report.metadata.get("rejection_reason_counts", {})),
            mismatch_reason_counts=dict(report.metadata.get("mismatch_reason_counts", {})),
            match_desalignment_dimension_counts=dict(report.metadata.get("match_desalignment_dimension_counts", {})),
            group_desalignment_dimension_counts=dict(report.metadata.get("group_desalignment_dimension_counts", {})),
            mapper_precision=float(report.metadata.get("mapper_precision", 0.0)),
            false_match_rate=float(report.metadata.get("false_match_rate", 0.0)),
            false_match_count=int(report.metadata.get("false_match_count", 0)),
            spread_capture_rate=spread_capture_rate,
            min_cross_venue_similarity_score=float(report.metadata.get("min_cross_venue_similarity_score", 0.0)),
            execution_routes={key: value for key, value in sorted(execution_routes.items())},
            planning_buckets=dict(report.metadata.get("planning_buckets", {})),
            comparison_states={key: value for key, value in sorted(report.ops_summary.reason_counts.items())},
            metadata={
            "match_threshold": self.match_threshold,
            "spread_threshold_bps": self.spread_threshold_bps,
            "min_resolution_compatibility_score": self.min_resolution_compatibility_score,
            "min_payout_compatibility_score": self.min_payout_compatibility_score,
            "min_currency_compatibility_score": self.min_currency_compatibility_score,
            "compatibility_thresholds": {
                "resolution": self.min_resolution_compatibility_score,
                "payout": self.min_payout_compatibility_score,
                "currency": self.min_currency_compatibility_score,
            },
            "execution_candidate_count": len(report.execution_candidates),
            "execution_plan_count": len(report.execution_plans),
            "reference_market_count": len(report.reference_market_ids),
                "compared_market_count": int(report.metadata.get("compared_market_count", 0)),
                "grouped_market_count": int(report.metadata.get("grouped_market_count", 0)),
                "grouped_market_coverage_rate": float(report.metadata.get("grouped_market_coverage_rate", 0.0)),
                "comparable_market_coverage_rate": float(report.metadata.get("comparable_market_coverage_rate", 0.0)),
                "duplicate_market_count": int(report.metadata.get("duplicate_market_count", 0)),
                "duplicate_market_rate": float(report.metadata.get("duplicate_market_rate", 0.0)),
                "duplicate_group_count": int(report.metadata.get("duplicate_group_count", 0)),
                "average_duplicate_group_size": float(report.metadata.get("average_duplicate_group_size", 0.0)),
                "desaligned_comparison_count": int(report.metadata.get("desaligned_comparison_count", 0)),
                "desaligned_comparison_rate": float(report.metadata.get("desaligned_comparison_rate", 0.0)),
                "desaligned_group_count": int(report.metadata.get("desaligned_group_count", 0)),
                "desaligned_group_rate": float(report.metadata.get("desaligned_group_rate", 0.0)),
                "manual_review_due_to_alignment_count": int(report.metadata.get("manual_review_due_to_alignment_count", 0)),
                "manual_review_due_to_alignment_rate": float(report.metadata.get("manual_review_due_to_alignment_rate", 0.0)),
                "timing_mismatch_count": report.metadata.get("timing_mismatch_count", 0),
                "timing_compatibility_average": report.metadata.get("timing_compatibility_average", 0.0),
                "mapper_precision": float(report.metadata.get("mapper_precision", 0.0)),
                "false_match_rate": float(report.metadata.get("false_match_rate", 0.0)),
                "false_match_count": int(report.metadata.get("false_match_count", 0)),
                "rejection_reason_counts": dict(report.metadata.get("rejection_reason_counts", {})),
                "mismatch_reason_counts": dict(report.metadata.get("mismatch_reason_counts", {})),
                "match_desalignment_dimension_counts": dict(report.metadata.get("match_desalignment_dimension_counts", {})),
                "group_desalignment_dimension_counts": dict(report.metadata.get("group_desalignment_dimension_counts", {})),
                "min_cross_venue_similarity_score": float(report.metadata.get("min_cross_venue_similarity_score", 0.0)),
                "venue_role_classification": report.venue_role_classification.model_dump(mode="json"),
                "spread_capture_rate": spread_capture_rate,
                "classification_counts": {key: value for key, value in sorted(classification_counts.items())},
                "comparison_classification_counts": {key: value for key, value in sorted(comparison_classification_counts.items())},
            },
        )

    def cross_venue_mapper(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> CrossVenueRoutingSurface:
        return self.routing_surface(markets, snapshots=snapshots)

    def _comparison_state(
        self,
        match: CrossVenueMatch,
        spread_bps: float | None,
        *,
        timing_compatibility_score: float,
        narrative_risk_flags: list[str] | None = None,
    ) -> CrossVenueOpsState:
        narrative_risk_flags = narrative_risk_flags or []
        currency_known = bool(match.left_currency and match.right_currency)
        payout_known = bool(match.left_payout_currency and match.right_payout_currency)
        if (
            match.manual_review_required
            or not match.compatible_resolution
            or (match.resolution_compatibility_score < self.min_resolution_compatibility_score)
            or (currency_known and match.currency_compatibility_score < self.min_currency_compatibility_score)
            or (payout_known and match.payout_compatibility_score < self.min_payout_compatibility_score)
            or timing_compatibility_score < 1.0
            or any(flag in {"narrative_only", "weak_question_alignment", "watchlist_only", "no_canonical_event"} for flag in narrative_risk_flags)
        ):
            return CrossVenueOpsState.manual_review
        if spread_bps is None:
            return CrossVenueOpsState.comparison_only
        if spread_bps >= self.spread_threshold_bps:
            return CrossVenueOpsState.spread_alert
        return CrossVenueOpsState.signal_candidate

    @staticmethod
    def _comparison_classification(
        comparison_state: CrossVenueOpsState,
        spread_bps: float | None,
    ) -> str:
        if comparison_state == CrossVenueOpsState.spread_alert:
            return "arbitrage-candidate"
        if comparison_state == CrossVenueOpsState.signal_candidate:
            return "tradeable" if spread_bps is not None else "signal-only"
        return "signal-only"

    @staticmethod
    def _comparison_taxonomy(
        comparison_state: CrossVenueOpsState,
        spread_bps: float | None,
    ) -> CrossVenueTaxonomy:
        if spread_bps is None or comparison_state == CrossVenueOpsState.comparison_only:
            return CrossVenueTaxonomy.comparison_only
        return CrossVenueTaxonomy.relative_value

    def _candidate_classification(self, comparison: CrossVenueComparison, *, tradeable: bool) -> str:
        if not tradeable:
            return "signal-only"
        if comparison.spread_bps is not None and comparison.spread_bps >= self.spread_threshold_bps and comparison.comparison_state == CrossVenueOpsState.spread_alert:
            return "arbitrage-candidate"
        return "tradeable"

    @staticmethod
    def _candidate_taxonomy(
        comparison: CrossVenueComparison,
        *,
        tradeable: bool,
        preferred_is_equivalent: bool,
        execution_filter_reason_codes: list[str],
    ) -> CrossVenueTaxonomy:
        if tradeable and preferred_is_equivalent and not execution_filter_reason_codes:
            return CrossVenueTaxonomy.true_arbitrage
        if comparison.spread_bps is None or comparison.comparison_state == CrossVenueOpsState.comparison_only:
            return CrossVenueTaxonomy.comparison_only
        if preferred_is_equivalent and set(execution_filter_reason_codes).issubset({"relative_value_not_tradeable", "not_true_arbitrage"}):
            return CrossVenueTaxonomy.relative_value
        return CrossVenueTaxonomy.cross_venue_signal

    def _plan_classification(self, candidate: CrossVenueExecutionCandidate, *, tradeable: bool) -> str:
        if not tradeable:
            return "signal-only"
        if candidate.spread_bps is not None and candidate.spread_bps >= self.spread_threshold_bps:
            return "arbitrage-candidate"
        return "tradeable"

    @staticmethod
    def _plan_taxonomy(
        candidate: CrossVenueExecutionCandidate,
        *,
        tradeable: bool,
        manual_review_required: bool,
        preferred_is_equivalent: bool,
        execution_filter_reason_codes: list[str],
    ) -> CrossVenueTaxonomy:
        if tradeable and not manual_review_required and not execution_filter_reason_codes:
            return CrossVenueTaxonomy.true_arbitrage
        if candidate.spread_bps is None or candidate.comparison_state == CrossVenueOpsState.comparison_only:
            return CrossVenueTaxonomy.comparison_only
        if (
            preferred_is_equivalent
            and not manual_review_required
            and set(execution_filter_reason_codes).issubset({"relative_value_not_tradeable", "not_true_arbitrage"})
        ):
            return CrossVenueTaxonomy.relative_value
        if execution_filter_reason_codes or manual_review_required or not tradeable:
            return CrossVenueTaxonomy.cross_venue_signal
        return CrossVenueTaxonomy.relative_value

    @staticmethod
    def _execution_filter_reason_codes(
        comparison: CrossVenueComparison,
        *,
        left_execution_capable: bool,
        right_execution_capable: bool,
        preferred_is_equivalent: bool,
        preferred_is_bindable: bool,
        preferred_is_execution_like: bool,
        tradeable: bool,
        execution_route: str,
    ) -> list[str]:
        reasons: list[str] = []
        if comparison.comparison_state == CrossVenueOpsState.manual_review:
            reasons.append("manual_review_required")
        if comparison.spread_bps is None:
            reasons.append("missing_probability")
        if comparison.timing_compatibility_score < 1.0:
            reasons.append("timing_mismatch")
        for note in comparison.notes:
            if note in {"resolution_mismatch", "resolution_source_mismatch", "currency_mismatch", "payout_currency_mismatch"}:
                reasons.append(note)
            elif note.startswith(("timebox_", "cutoff_", "timezone_")):
                reasons.append("timing_mismatch")
        if not left_execution_capable or not right_execution_capable:
            reasons.append("execution_unavailable")
        if preferred_is_bindable and not preferred_is_equivalent:
            reasons.append("execution_bindable_venue")
        if preferred_is_execution_like and not preferred_is_equivalent:
            reasons.append("execution_like_venue")
        if execution_route == "comparison_only":
            reasons.append("no_execution_route")
        if not tradeable:
            if comparison.spread_bps is not None:
                reasons.append("relative_value_not_tradeable" if preferred_is_equivalent else "spread_signal_not_tradeable")
            reasons.append("not_true_arbitrage")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _plan_classification_from_state(comparison_state: CrossVenueOpsState, spread_bps: float | None) -> str:
        if comparison_state == CrossVenueOpsState.spread_alert:
            return "arbitrage-candidate"
        if comparison_state == CrossVenueOpsState.signal_candidate:
            return "tradeable" if spread_bps is not None else "signal-only"
        return "signal-only"

    @staticmethod
    def _merge_classification(existing: str | None, incoming: str) -> str:
        rank = {
            "signal-only": 0,
            "tradeable": 1,
            "arbitrage-candidate": 2,
        }
        if existing is None:
            return incoming
        return incoming if rank.get(incoming, 0) >= rank.get(existing, 0) else existing

    @staticmethod
    def _classification_counts(comparisons: list[CrossVenueComparison]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for comparison in comparisons:
            counts[comparison.classification] = counts.get(comparison.classification, 0) + 1
        return counts

    @staticmethod
    def _comparison_classification_counts(comparisons: list[CrossVenueComparison]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for comparison in comparisons:
            key = comparison.classification
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _comparison_taxonomy_counts(comparisons: list[CrossVenueComparison]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for comparison in comparisons:
            key = comparison.taxonomy.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _candidate_taxonomy_counts(candidates: list[CrossVenueExecutionCandidate]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in candidates:
            key = candidate.taxonomy.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _plan_taxonomy_counts(plans: list[CrossVenueExecutionPlan]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for plan in plans:
            key = plan.taxonomy.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _comparison_alignment_gap_count(comparison: CrossVenueComparison) -> int:
        notes = set(comparison.notes or [])
        dimensions = {
            "resolution": any(token in {"resolution_mismatch", "resolution_source_mismatch"} for token in notes),
            "currency": "currency_mismatch" in notes,
            "payout": "payout_currency_mismatch" in notes,
            "timing": any(token.startswith(("timebox_", "cutoff_", "timezone_")) for token in notes),
        }
        return sum(1 for value in dimensions.values() if value)

    @staticmethod
    def _spread_capture_rate(
        comparisons: list[CrossVenueComparison],
        execution_candidates: list[CrossVenueExecutionCandidate],
    ) -> float:
        spreadable_count = sum(
            1
            for comparison in comparisons
            if comparison.comparison_state in {CrossVenueOpsState.signal_candidate, CrossVenueOpsState.spread_alert}
        )
        return round(len(execution_candidates) / max(1, spreadable_count), 6)

    @staticmethod
    def _narrative_risk_flags(
        match: CrossVenueMatch,
        left: MarketDescriptor,
        right: MarketDescriptor,
        spread_bps: float | None,
        *,
        timing_notes: list[str],
    ) -> list[str]:
        flags: list[str] = []
        if match.manual_review_required:
            flags.append("manual_review_required")
        if not match.compatible_resolution:
            flags.append("resolution_mismatch")
        if timing_notes:
            flags.extend(timing_notes)
        if spread_bps is None:
            flags.append("missing_probability")
        elif (
            (spread_bps >= 50.0 and match.similarity < 0.85)
            or (spread_bps >= 20.0 and not match.compatible_resolution)
            or (match.canonical_event_id is None and match.similarity < 0.9)
        ):
            flags.append("narrative_only")
        elif spread_bps < 20.0 and match.similarity < 0.7:
            flags.append("weak_question_alignment")
        if left.canonical_event_id is None and right.canonical_event_id is None:
            flags.append("no_canonical_event")
        if left.venue_type == VenueType.watchlist and right.venue_type == VenueType.watchlist:
            flags.append("watchlist_only")
        return list(dict.fromkeys(flags))

    @staticmethod
    def _ops_summary(
        *,
        comparisons: list[CrossVenueComparison],
        execution_candidates: list[CrossVenueExecutionCandidate],
        spread_alerts: list[CrossVenueSpreadAlert],
        comparable_groups: list[ComparableMarketGroup],
        reference_market_ids: list[str],
    ) -> CrossVenueOpsSummary:
        comparison_only_count = sum(1 for comparison in comparisons if comparison.comparison_state == CrossVenueOpsState.comparison_only)
        manual_review_count = sum(1 for comparison in comparisons if comparison.comparison_state == CrossVenueOpsState.manual_review)
        signal_candidate_count = sum(1 for comparison in comparisons if comparison.comparison_state == CrossVenueOpsState.signal_candidate)
        executable_candidate_count = len(execution_candidates)
        spread_alert_count = len(spread_alerts)
        manual_review_group_count = sum(1 for group in comparable_groups if group.manual_review_required)
        comparison_only_group_count = sum(
            1
            for group in comparable_groups
            if not group.manual_review_required and group.match_count <= 1 and len(group.market_ids) <= 1
        )
        narrative_risk_count = sum(len(group.narrative_risk_flags) for group in comparable_groups)
        reason_counts: dict[str, int] = {
            CrossVenueOpsState.comparison_only.value: comparison_only_count,
            CrossVenueOpsState.manual_review.value: manual_review_count,
            CrossVenueOpsState.signal_candidate.value: signal_candidate_count,
            CrossVenueOpsState.executable_candidate.value: executable_candidate_count,
            CrossVenueOpsState.spread_alert.value: spread_alert_count,
        }
        return CrossVenueOpsSummary(
            comparison_only_count=comparison_only_count,
            manual_review_count=manual_review_count,
            signal_candidate_count=signal_candidate_count,
            executable_candidate_count=executable_candidate_count,
            spread_alert_count=spread_alert_count,
            comparable_group_count=len(comparable_groups),
            reference_market_count=len(reference_market_ids),
            manual_review_group_count=manual_review_group_count,
            comparison_only_group_count=comparison_only_group_count,
            narrative_risk_count=narrative_risk_count,
            reason_counts=reason_counts,
        )

    def match_markets(
        self,
        left: MarketDescriptor,
        right: MarketDescriptor,
        *,
        left_snapshot: MarketSnapshot | None = None,
        right_snapshot: MarketSnapshot | None = None,
    ) -> CrossVenueMatch | None:
        if left.venue == right.venue:
            return None
        similarity, rationale = self.graph_builder._score_pair(
            self.graph_builder._build_node(left, left_snapshot),
            self.graph_builder._build_node(right, right_snapshot),
        )
        if similarity < self.match_threshold:
            return None
        question_key = self._market_question_key(left, right)
        left_resolution_source = self._market_resolution_source(left)
        right_resolution_source = self._market_resolution_source(right)
        left_currency = self._market_currency(left)
        right_currency = self._market_currency(right)
        left_payout_currency = self._market_payout_currency(left)
        right_payout_currency = self._market_payout_currency(right)
        timing_score, timing_notes, timing_metadata = MarketGraphBuilder._timing_compatibility(left, right)
        return CrossVenueMatch(
            canonical_event_id=left.canonical_event_id or right.canonical_event_id or self._canonical_event_id(left, right),
            left_market_id=left.market_id,
            right_market_id=right.market_id,
            left_venue=left.venue,
            right_venue=right.venue,
            question_left=left.question,
            question_right=right.question,
            question_key=question_key,
            left_resolution_source=left_resolution_source,
            right_resolution_source=right_resolution_source,
            left_currency=left_currency,
            right_currency=right_currency,
            left_payout_currency=left_payout_currency,
            right_payout_currency=right_payout_currency,
            resolution_compatibility_score=1.0 if self._compatible_resolution(left, right) else 0.0,
            payout_compatibility_score=1.0 if self._compatible_payout(left, right) else 0.0,
            currency_compatibility_score=1.0 if self._compatible_currency(left, right) else 0.0,
            similarity=similarity,
            compatible_resolution=self._compatible_resolution(left, right),
            manual_review_required=not self._compatible_resolution(left, right) or similarity < 0.8 or timing_score < 1.0 or bool(timing_notes),
            comparable_group_id=self._comparable_group_id_from_markets(left, right),
            comparable_market_refs=[left.market_id, right.market_id],
            notes=self._comparison_notes(
                left=left,
                right=right,
                compatible_resolution=self._compatible_resolution(left, right),
                left_currency=left_currency,
                right_currency=right_currency,
                left_payout_currency=left_payout_currency,
                right_payout_currency=right_payout_currency,
                timing_notes=timing_notes,
            ),
            rationale=rationale,
            metadata={
                "left_title": left.title,
                "right_title": right.title,
                "left_roles": self._market_roles(left),
                "right_roles": self._market_roles(right),
                "question_key": question_key,
                "left_resolution_source": left_resolution_source,
                "right_resolution_source": right_resolution_source,
                "left_currency": left_currency,
                "right_currency": right_currency,
                "left_payout_currency": left_payout_currency,
                "right_payout_currency": right_payout_currency,
                "timing_compatibility_score": timing_score,
                "timing_mismatch_reasons": list(timing_notes),
                "timing": timing_metadata,
            },
        )

    def _execution_candidate_for(
        self,
        comparison: CrossVenueComparison,
        markets: list[MarketDescriptor],
    ) -> CrossVenueExecutionCandidate | None:
        if comparison.comparison_state not in {
            CrossVenueOpsState.signal_candidate,
            CrossVenueOpsState.spread_alert,
        }:
            return None
        left = self._get_market(markets, comparison.left_market_id)
        right = self._get_market(markets, comparison.right_market_id)
        left_execution = self._execution_capable(left.venue)
        right_execution = self._execution_capable(right.venue)
        if not left_execution or not right_execution:
            return None
        left_surface = self.execution_registry.execution_surface(left.venue)
        right_surface = self.execution_registry.execution_surface(right.venue)
        preferred = max(
            (left, right),
            key=self._preference_rank_for_market,
        )
        alternate = right if preferred.market_id == left.market_id else left
        preferred_surface = self.execution_registry.execution_surface(preferred.venue)
        preferred_is_equivalent = bool(preferred_surface.execution_equivalent)
        preferred_is_bindable = bool(preferred_surface.execution_taxonomy == "execution_bindable" or preferred_surface.execution_readiness == "bindable_ready")
        preferred_is_execution_like = bool(preferred_surface.execution_like and not preferred_surface.execution_equivalent)
        preferred_selection_reason = self._preferred_execution_selection_reason(preferred, alternate)
        execution_pathways_by_market_id = {
            left.market_id: self._execution_pathway_for_venue(left.venue),
            right.market_id: self._execution_pathway_for_venue(right.venue),
        }
        readiness_stages_by_market_id = {
            left.market_id: self._readiness_stage_for_venue(left.venue),
            right.market_id: self._readiness_stage_for_venue(right.venue),
        }
        highest_actionable_modes_by_market_id = {
            left.market_id: self._highest_actionable_mode_for_venue(left.venue),
            right.market_id: self._highest_actionable_mode_for_venue(right.venue),
        }
        required_operator_actions_by_market_id = {
            left.market_id: self._required_operator_action_for_venue(left.venue),
            right.market_id: self._required_operator_action_for_venue(right.venue),
        }
        next_pathways_by_market_id = {
            left.market_id: self._next_pathway_for_venue(left.venue),
            right.market_id: self._next_pathway_for_venue(right.venue),
        }
        next_pathway_rules_by_market_id = {
            left.market_id: self._next_pathway_rules_for_venue(left.venue),
            right.market_id: self._next_pathway_rules_for_venue(right.venue),
        }
        bounded_execution_equivalent_market_ids = [
            market.market_id
            for market in (left, right)
            if self._bounded_execution_equivalent_for_venue(market.venue)
        ]
        bounded_execution_promotion_candidate_market_ids = [
            market.market_id
            for market in (left, right)
            if self._bounded_execution_promotion_candidate_for_venue(market.venue)
        ]
        stage_summaries_by_market_id = {
            left.market_id: self._stage_summary_for_venue(left.venue),
            right.market_id: self._stage_summary_for_venue(right.venue),
        }
        credential_gates_by_market_id = {
            left.market_id: self._credential_gate_for_venue(left.venue),
            right.market_id: self._credential_gate_for_venue(right.venue),
        }
        api_gates_by_market_id = {
            left.market_id: self._api_gate_for_venue(left.venue),
            right.market_id: self._api_gate_for_venue(right.venue),
        }
        missing_requirement_counts_by_market_id = {
            left.market_id: len(self._missing_requirement_codes_for_venue(left.venue)),
            right.market_id: len(self._missing_requirement_codes_for_venue(right.venue)),
        }
        readiness_scores_by_market_id = {
            left.market_id: self._readiness_rank(readiness_stages_by_market_id[left.market_id]),
            right.market_id: self._readiness_rank(readiness_stages_by_market_id[right.market_id]),
        }
        operator_checklists_by_market_id = {
            left.market_id: self._operator_checklist_for_venue(left.venue),
            right.market_id: self._operator_checklist_for_venue(right.venue),
        }
        promotion_evidence_by_market_id = {
            left.market_id: self._promotion_evidence_for_venue(left.venue),
            right.market_id: self._promotion_evidence_for_venue(right.venue),
        }
        promotion_target_pathways_by_market_id = {
            left.market_id: self._promotion_target_pathway_for_venue(left.venue),
            right.market_id: self._promotion_target_pathway_for_venue(right.venue),
        }
        preferred_execution_pathway = execution_pathways_by_market_id.get(preferred.market_id)
        preferred_execution_mode = highest_actionable_modes_by_market_id.get(preferred.market_id)
        preferred_operator_action = required_operator_actions_by_market_id.get(preferred.market_id)
        preferred_promotion_target_pathway = promotion_target_pathways_by_market_id.get(preferred.market_id)
        preferred_stage_summary = dict(stage_summaries_by_market_id.get(preferred.market_id, {}))
        preferred_pathway_summary = str(preferred_stage_summary.get("pathway_summary", ""))
        preferred_operator_summary = str(preferred_stage_summary.get("operator_summary", ""))
        preferred_promotion_summary = str(preferred_stage_summary.get("promotion_summary", ""))
        preferred_blocker_summary = str(preferred_stage_summary.get("blocker_summary", ""))
        preferred_execution_summary = " | ".join(
            item
            for item in [
                f"pathway={preferred_execution_pathway or 'read_only'}",
                f"mode={preferred_execution_mode or 'none'}",
                f"action={preferred_operator_action or 'no_order_routing'}",
                f"selection={preferred_selection_reason}",
            ]
            if item
        )
        preferred_execution_capability_summary = " | ".join(
            item
            for item in [
                f"taxonomy={preferred_surface.execution_taxonomy}",
                f"readiness={self._readiness_stage_for_venue(preferred.venue)}",
                f"role={'execution_equivalent' if preferred_is_equivalent else 'execution_bindable' if preferred_is_bindable else 'execution_like' if preferred_is_execution_like else 'read_only'}",
                f"operator={preferred_operator_action or 'no_order_routing'}",
            ]
            if item
        )
        readiness_stage_counts = {
            stage: sum(1 for value in readiness_stages_by_market_id.values() if value == stage)
            for stage in sorted({*readiness_stages_by_market_id.values()})
        }
        next_pathway_counts = {
            pathway: sum(1 for value in next_pathways_by_market_id.values() if value == pathway)
            for pathway in sorted({value for value in next_pathways_by_market_id.values() if value})
        }
        promotion_rules_by_market_id = {
            left.market_id: self._promotion_rules_for_venue(left.venue),
            right.market_id: self._promotion_rules_for_venue(right.venue),
        }
        pathway_ladders_by_market_id = {
            left.market_id: self._pathway_ladder_for_venue(left.venue),
            right.market_id: self._pathway_ladder_for_venue(right.venue),
        }
        blocked_pathways_by_market_id = {
            left.market_id: self._blocked_pathways_for_venue(left.venue),
            right.market_id: self._blocked_pathways_for_venue(right.venue),
        }
        execution_blocker_codes_by_market_id = {
            left.market_id: self._execution_blocker_codes_for_venue(left.venue),
            right.market_id: self._execution_blocker_codes_for_venue(right.venue),
        }
        preferred_execution_semantics = self._preferred_execution_semantics_for_pathway(preferred_execution_pathway)
        mixed_execution_semantics = self._mixed_execution_semantics(execution_pathways_by_market_id)
        survivability_by_market_id = {
            market_id: self._survivability_semantics_for_summary(summary)
            for market_id, summary in stage_summaries_by_market_id.items()
        }
        requirement_gap_summary_by_market_id = {
            market_id: {
                "missing_requirement_count": int(summary.get("missing_requirement_count", 0)),
                "blocked_pathway_count": int(summary.get("blocked_pathway_count", 0)),
                "next_pathway": next_pathways_by_market_id.get(market_id),
                "highest_actionable_mode": highest_actionable_modes_by_market_id.get(market_id),
            }
            for market_id, summary in stage_summaries_by_market_id.items()
        }
        signal_market_ids = [market.market_id for market in (left, right) if self._signal_capable(market.venue)]
        reference_market_ids = [market.market_id for market in (left, right) if self._reference_capable(market.venue)]
        candidate_tradeable = bool(
            preferred.market_id in {left.market_id, right.market_id}
            and self._execution_capable(preferred.venue)
            and preferred_is_equivalent
        )
        execution_filter_reason_codes = self._execution_filter_reason_codes(
            comparison,
            left_execution_capable=left_execution,
            right_execution_capable=right_execution,
            preferred_is_equivalent=preferred_is_equivalent,
            preferred_is_bindable=preferred_is_bindable,
            preferred_is_execution_like=preferred_is_execution_like,
            tradeable=candidate_tradeable,
            execution_route=self._execution_route(preferred, left, right),
        )
        taxonomy = self._candidate_taxonomy(
            comparison,
            tradeable=candidate_tradeable,
            preferred_is_equivalent=preferred_is_equivalent,
            execution_filter_reason_codes=execution_filter_reason_codes,
        )
        survivability_hint = self._survivability_hint(
            tradeable=candidate_tradeable,
            preferred_execution_semantics=preferred_execution_semantics,
            mixed_execution_semantics=mixed_execution_semantics,
            readiness_stages_by_market_id=readiness_stages_by_market_id,
            missing_requirement_counts_by_market_id=missing_requirement_counts_by_market_id,
        )
        multi_leg_operator_checklist = self._multi_leg_operator_checklist(
            preferred_market_id=preferred.market_id,
            preferred_operator_action=preferred_operator_action,
            mixed_execution_semantics=mixed_execution_semantics,
            survivability_hint=survivability_hint,
            operator_checklists_by_market_id=operator_checklists_by_market_id,
            next_pathways_by_market_id=next_pathways_by_market_id,
        )
        multi_leg_blocker_codes = self._multi_leg_blocker_codes(
            execution_filter_reason_codes=execution_filter_reason_codes,
            execution_blocker_codes_by_market_id=execution_blocker_codes_by_market_id,
            next_pathways_by_market_id=next_pathways_by_market_id,
            missing_requirement_counts_by_market_id=missing_requirement_counts_by_market_id,
            execution_pathways_by_market_id=execution_pathways_by_market_id,
            preferred_market_id=preferred.market_id,
            readiness_stages_by_market_id=readiness_stages_by_market_id,
        )
        return CrossVenueExecutionCandidate(
            comparison_id=comparison.comparison_id,
            canonical_event_id=comparison.canonical_event_id,
            market_ids=[left.market_id, right.market_id],
            venue_roles={
                left.venue.value: self._market_roles(left),
                right.venue.value: self._market_roles(right),
            },
            preferred_execution_market_id=preferred.market_id if self._execution_capable(preferred.venue) else None,
            preferred_execution_venue=preferred.venue if self._execution_capable(preferred.venue) else None,
            signal_market_ids=signal_market_ids,
            reference_market_ids=reference_market_ids,
            comparable_group_id=comparison.metadata.get("comparable_group_id"),
            comparison_state=comparison.comparison_state,
            execution_route=self._execution_route(preferred, left, right),
            tradeable=candidate_tradeable,
            spread_bps=comparison.spread_bps,
            classification=self._candidate_classification(
                comparison,
                tradeable=candidate_tradeable,
            ),
            taxonomy=taxonomy,
            execution_filter_reason_codes=execution_filter_reason_codes,
            preferred_execution_pathway=preferred_execution_pathway,
            preferred_execution_mode=preferred_execution_mode,
            preferred_operator_action=preferred_operator_action,
            preferred_promotion_target_pathway=preferred_promotion_target_pathway,
            preferred_execution_selection_reason=preferred_selection_reason,
            pathway_summary=preferred_pathway_summary,
            operator_summary=preferred_operator_summary,
            promotion_summary=preferred_promotion_summary,
            blocker_summary=preferred_blocker_summary,
            preferred_execution_summary=preferred_execution_summary,
            preferred_execution_capability_summary=preferred_execution_capability_summary,
            execution_pathways_by_market_id=execution_pathways_by_market_id,
            readiness_stages_by_market_id=readiness_stages_by_market_id,
            highest_actionable_modes_by_market_id=highest_actionable_modes_by_market_id,
            required_operator_actions_by_market_id=required_operator_actions_by_market_id,
            next_pathways_by_market_id=next_pathways_by_market_id,
            next_pathway_rules_by_market_id=next_pathway_rules_by_market_id,
            bounded_execution_equivalent_market_ids=bounded_execution_equivalent_market_ids,
            bounded_execution_promotion_candidate_market_ids=bounded_execution_promotion_candidate_market_ids,
            stage_summaries_by_market_id=stage_summaries_by_market_id,
            promotion_target_pathways_by_market_id=promotion_target_pathways_by_market_id,
            promotion_rules_by_market_id=promotion_rules_by_market_id,
            pathway_ladders_by_market_id=pathway_ladders_by_market_id,
            blocked_pathways_by_market_id=blocked_pathways_by_market_id,
            execution_blocker_codes_by_market_id=execution_blocker_codes_by_market_id,
            rationale=comparison.rationale,
            metadata={
                "comparison_state": comparison.comparison_state.value,
                "classification": self._candidate_classification(
                    comparison,
                    tradeable=candidate_tradeable,
                ),
                "taxonomy": taxonomy.value,
                "preferred_execution_taxonomy": preferred_surface.execution_taxonomy,
                "preferred_is_bindable": preferred_is_bindable,
                "left_market_id": left.market_id,
                "right_market_id": right.market_id,
                "left_execution_capable": left_execution,
                "right_execution_capable": right_execution,
                "preferred_execution_is_equivalent": preferred_is_equivalent,
                "preferred_execution_is_bindable": preferred_is_bindable,
                "preferred_execution_is_execution_like": preferred_is_execution_like,
                "preferred_execution_pathway": preferred_execution_pathway,
                "preferred_execution_mode": preferred_execution_mode,
                "preferred_operator_action": preferred_operator_action,
                "preferred_promotion_target_pathway": preferred_promotion_target_pathway,
                "preferred_pathway_summary": preferred_pathway_summary,
                "preferred_operator_summary": preferred_operator_summary,
                "preferred_promotion_summary": preferred_promotion_summary,
                "preferred_blocker_summary": preferred_blocker_summary,
                "preferred_execution_summary": preferred_execution_summary,
                "preferred_execution_capability_summary": preferred_execution_capability_summary,
                "preferred_execution_semantics": preferred_execution_semantics,
                "preferred_execution_selection_reason": preferred_selection_reason,
                "mixed_execution_semantics": mixed_execution_semantics,
                "survivability_hint": survivability_hint,
                "survivability_by_market_id": dict(survivability_by_market_id),
                "requirement_gap_summary_by_market_id": {
                    market_id: dict(summary)
                    for market_id, summary in requirement_gap_summary_by_market_id.items()
                },
                "multi_leg_operator_checklist": list(multi_leg_operator_checklist),
                "multi_leg_blocker_codes": list(multi_leg_blocker_codes),
                "execution_pathways_by_market_id": dict(execution_pathways_by_market_id),
                "readiness_stages_by_market_id": dict(readiness_stages_by_market_id),
                "credential_gates_by_market_id": dict(credential_gates_by_market_id),
                "api_gates_by_market_id": dict(api_gates_by_market_id),
                "missing_requirement_counts_by_market_id": dict(missing_requirement_counts_by_market_id),
                "readiness_scores_by_market_id": dict(readiness_scores_by_market_id),
                "operator_checklists_by_market_id": {
                    market_id: list(checklist)
                    for market_id, checklist in operator_checklists_by_market_id.items()
                },
                "promotion_evidence_by_market_id": {
                    market_id: {
                        key: dict(value)
                        for key, value in evidence.items()
                    }
                    for market_id, evidence in promotion_evidence_by_market_id.items()
                },
                "highest_actionable_modes_by_market_id": dict(highest_actionable_modes_by_market_id),
                "required_operator_actions_by_market_id": dict(required_operator_actions_by_market_id),
                "next_pathways_by_market_id": dict(next_pathways_by_market_id),
                "next_pathway_rules_by_market_id": {
                    market_id: list(rules)
                    for market_id, rules in next_pathway_rules_by_market_id.items()
                },
                "readiness_stage_counts": dict(readiness_stage_counts),
                "next_pathway_counts": dict(next_pathway_counts),
                "bounded_execution_equivalent_market_ids": list(bounded_execution_equivalent_market_ids),
                "bounded_execution_equivalent_count": len(bounded_execution_equivalent_market_ids),
                "bounded_execution_promotion_candidate_market_ids": list(bounded_execution_promotion_candidate_market_ids),
                "bounded_execution_promotion_candidate_count": len(bounded_execution_promotion_candidate_market_ids),
                "stage_summaries_by_market_id": {
                    market_id: dict(summary)
                    for market_id, summary in stage_summaries_by_market_id.items()
                },
                "promotion_target_pathways_by_market_id": dict(promotion_target_pathways_by_market_id),
                "promotion_rules_by_market_id": {
                    market_id: list(rules)
                    for market_id, rules in promotion_rules_by_market_id.items()
                },
                "pathway_ladders_by_market_id": {
                    market_id: list(ladder)
                    for market_id, ladder in pathway_ladders_by_market_id.items()
                },
                "blocked_pathways_by_market_id": {
                    market_id: list(pathways)
                    for market_id, pathways in blocked_pathways_by_market_id.items()
                },
                "execution_blocker_codes_by_market_id": {
                    market_id: list(codes)
                    for market_id, codes in execution_blocker_codes_by_market_id.items()
                },
                "execution_filter_reason_codes": execution_filter_reason_codes,
                "question_key": comparison.question_key,
                "left_resolution_source": comparison.left_resolution_source,
                "right_resolution_source": comparison.right_resolution_source,
                "left_currency": comparison.left_currency,
                "right_currency": comparison.right_currency,
                "left_payout_currency": comparison.left_payout_currency,
                "right_payout_currency": comparison.right_payout_currency,
                "timing_compatibility_score": comparison.timing_compatibility_score,
                "timing_mismatch_reasons": list(comparison.metadata.get("timing_mismatch_reasons", [])),
                "timing": comparison.metadata.get("timing", {}),
                "notes": list(comparison.notes),
            },
        )

    def _execution_plan_for(
        self,
        candidate: CrossVenueExecutionCandidate,
        markets: list[MarketDescriptor],
    ) -> CrossVenueExecutionPlan:
        execution_market_ids = [candidate.preferred_execution_market_id] if candidate.preferred_execution_market_id else []
        execution_market_ids = [market_id for market_id in execution_market_ids if market_id is not None]
        comparison_state = candidate.comparison_state
        route = candidate.execution_route
        tradeable = candidate.tradeable and bool(execution_market_ids)
        classification = self._plan_classification(candidate, tradeable=tradeable)
        manual_review_required = bool(comparison_state == CrossVenueOpsState.manual_review or not tradeable)
        execution_filter_reason_codes = list(dict.fromkeys([
            *candidate.execution_filter_reason_codes,
            *(
                ["manual_review_required"]
                if manual_review_required and "manual_review_required" not in candidate.execution_filter_reason_codes
                else []
            ),
            *(
                ["no_execution_market"]
                if not execution_market_ids and "no_execution_market" not in candidate.execution_filter_reason_codes
                else []
            ),
        ]))
        taxonomy = self._plan_taxonomy(
            candidate,
            tradeable=tradeable,
            manual_review_required=manual_review_required,
            preferred_is_equivalent=bool(candidate.preferred_execution_market_id in candidate.bounded_execution_equivalent_market_ids),
            execution_filter_reason_codes=execution_filter_reason_codes,
        )
        market_lookup = {market.market_id: market for market in markets}
        legs: list[CrossVenueExecutionPlanLeg] = []
        execution_equivalent_market_ids: list[str] = []
        execution_like_market_ids: list[str] = []
        reference_only_market_ids: list[str] = []
        watchlist_market_ids: list[str] = []
        execution_roles_by_market_id: dict[str, str] = {}
        execution_pathways_by_market_id: dict[str, str] = {}
        readiness_stages_by_market_id: dict[str, str] = {}
        highest_actionable_modes_by_market_id: dict[str, str | None] = {}
        required_operator_actions_by_market_id: dict[str, str] = {}
        next_pathways_by_market_id: dict[str, str | None] = {}
        next_pathway_rules_by_market_id: dict[str, list[str]] = {}
        bounded_execution_promotion_candidate_market_ids: list[str] = []
        stage_summaries_by_market_id: dict[str, dict[str, Any]] = {}
        promotion_target_pathways_by_market_id: dict[str, str | None] = {}
        promotion_rules_by_market_id: dict[str, list[str]] = {}
        pathway_ladders_by_market_id: dict[str, list[str]] = {}
        blocked_pathways_by_market_id: dict[str, list[str]] = {}
        execution_blocker_codes_by_market_id: dict[str, list[str]] = {}
        bounded_execution_equivalent_market_ids: list[str] = []
        for market_id in list(dict.fromkeys([*candidate.market_ids, *candidate.reference_market_ids, *candidate.signal_market_ids])):
            market = market_lookup.get(market_id)
            if market is None:
                continue
            planning_bucket = self._planning_bucket_for_market(market)
            execution_pathway = candidate.execution_pathways_by_market_id.get(market_id, self._execution_pathway_for_venue(market.venue))
            readiness_stage = candidate.readiness_stages_by_market_id.get(market_id, self._readiness_stage_for_venue(market.venue))
            highest_actionable_mode = candidate.highest_actionable_modes_by_market_id.get(market_id, self._highest_actionable_mode_for_venue(market.venue))
            required_operator_action = candidate.required_operator_actions_by_market_id.get(market_id, self._required_operator_action_for_venue(market.venue))
            next_pathway = candidate.next_pathways_by_market_id.get(market_id, self._next_pathway_for_venue(market.venue))
            next_pathway_rules = candidate.next_pathway_rules_by_market_id.get(market_id, self._next_pathway_rules_for_venue(market.venue))
            promotion_target_pathway = candidate.promotion_target_pathways_by_market_id.get(market_id, self._promotion_target_pathway_for_venue(market.venue))
            promotion_rules = candidate.promotion_rules_by_market_id.get(market_id, self._promotion_rules_for_venue(market.venue))
            pathway_ladder = candidate.pathway_ladders_by_market_id.get(market_id, self._pathway_ladder_for_venue(market.venue))
            blocked_pathways = candidate.blocked_pathways_by_market_id.get(market_id, self._blocked_pathways_for_venue(market.venue))
            bounded_execution_equivalent = market_id in candidate.bounded_execution_equivalent_market_ids or self._bounded_execution_equivalent_for_venue(market.venue)
            bounded_execution_promotion_candidate = market_id in candidate.bounded_execution_promotion_candidate_market_ids or self._bounded_execution_promotion_candidate_for_venue(market.venue)
            stage_summary = candidate.stage_summaries_by_market_id.get(market_id, self._stage_summary_for_venue(market.venue))
            execution_blocker_codes = candidate.execution_blocker_codes_by_market_id.get(market_id, self._execution_blocker_codes_for_venue(market.venue))
            if planning_bucket == "execution-equivalent":
                execution_role = "execution_equivalent"
            elif planning_bucket == "execution-bindable":
                execution_role = "execution_bindable"
            elif planning_bucket == "execution-like":
                execution_role = "execution_like"
            elif planning_bucket == "reference-only":
                execution_role = "reference_only"
            else:
                execution_role = "watchlist"
            if planning_bucket == "execution-equivalent":
                execution_equivalent_market_ids.append(market_id)
            elif planning_bucket == "execution-bindable":
                execution_like_market_ids.append(market_id)
            elif planning_bucket == "execution-like":
                execution_like_market_ids.append(market_id)
            elif planning_bucket == "reference-only":
                reference_only_market_ids.append(market_id)
            else:
                watchlist_market_ids.append(market_id)
            execution_roles_by_market_id[market_id] = execution_role
            execution_pathways_by_market_id[market_id] = execution_pathway
            readiness_stages_by_market_id[market_id] = readiness_stage
            highest_actionable_modes_by_market_id[market_id] = highest_actionable_mode
            required_operator_actions_by_market_id[market_id] = required_operator_action
            next_pathways_by_market_id[market_id] = next_pathway
            next_pathway_rules_by_market_id[market_id] = list(next_pathway_rules)
            promotion_target_pathways_by_market_id[market_id] = promotion_target_pathway
            promotion_rules_by_market_id[market_id] = list(promotion_rules)
            pathway_ladders_by_market_id[market_id] = list(pathway_ladder)
            blocked_pathways_by_market_id[market_id] = list(blocked_pathways)
            stage_summaries_by_market_id[market_id] = dict(stage_summary)
            if bounded_execution_equivalent and market_id not in bounded_execution_equivalent_market_ids:
                bounded_execution_equivalent_market_ids.append(market_id)
            if bounded_execution_promotion_candidate and market_id not in bounded_execution_promotion_candidate_market_ids:
                bounded_execution_promotion_candidate_market_ids.append(market_id)
            execution_blocker_codes_by_market_id[market_id] = list(execution_blocker_codes)
            legs.append(
                CrossVenueExecutionPlanLeg(
                    market_id=market_id,
                    venue=market.venue,
                    venue_roles=self._market_roles(market),
                    planning_bucket=planning_bucket,
                    execution_role=execution_role,
                    execution_pathway=execution_pathway,
                    readiness_stage=readiness_stage,
                    highest_actionable_mode=highest_actionable_mode,
                    required_operator_action=required_operator_action,
                    next_pathway=next_pathway,
                    next_pathway_rules=list(next_pathway_rules),
                    bounded_execution_equivalent=bounded_execution_equivalent,
                    bounded_execution_promotion_candidate=bounded_execution_promotion_candidate,
                    stage_summary=dict(stage_summary),
                    promotion_target_pathway=promotion_target_pathway,
                    promotion_rules=list(promotion_rules),
                    pathway_ladder=list(pathway_ladder),
                    blocked_pathways=list(blocked_pathways),
                    execution_blocker_codes=list(execution_blocker_codes),
                    tradeable=market_id in execution_market_ids and tradeable,
                    read_only=True,
                    preferred_execution=market_id in execution_market_ids,
                    rationale=candidate.rationale,
                    metadata={
                        "comparison_id": candidate.comparison_id,
                        "candidate_id": candidate.candidate_id,
                        "comparison_state": comparison_state.value,
                        "execution_route": route,
                        "timing_compatibility_score": candidate.metadata.get("timing_compatibility_score"),
                        "timing_mismatch_reasons": list(candidate.metadata.get("timing_mismatch_reasons", [])),
                        "timing": candidate.metadata.get("timing", {}),
                    },
                )
            )
        return CrossVenueExecutionPlan(
            candidate_id=candidate.candidate_id,
            comparison_id=candidate.comparison_id,
            canonical_event_id=candidate.canonical_event_id,
            market_ids=list(candidate.market_ids),
            read_only_market_ids=list(candidate.market_ids),
            venue_roles={key: list(value) for key, value in candidate.venue_roles.items()},
            reference_market_ids=list(candidate.reference_market_ids),
            signal_market_ids=list(candidate.signal_market_ids),
            execution_equivalent_market_ids=execution_equivalent_market_ids,
            execution_like_market_ids=execution_like_market_ids,
            execution_roles_by_market_id=execution_roles_by_market_id,
            execution_pathways_by_market_id=execution_pathways_by_market_id,
            readiness_stages_by_market_id=readiness_stages_by_market_id,
            highest_actionable_modes_by_market_id=highest_actionable_modes_by_market_id,
            required_operator_actions_by_market_id=required_operator_actions_by_market_id,
            next_pathways_by_market_id=next_pathways_by_market_id,
            next_pathway_rules_by_market_id=next_pathway_rules_by_market_id,
            bounded_execution_equivalent_market_ids=list(bounded_execution_equivalent_market_ids),
            bounded_execution_promotion_candidate_market_ids=bounded_execution_promotion_candidate_market_ids,
            stage_summaries_by_market_id=stage_summaries_by_market_id,
            promotion_target_pathways_by_market_id=promotion_target_pathways_by_market_id,
            promotion_rules_by_market_id=promotion_rules_by_market_id,
            pathway_ladders_by_market_id=pathway_ladders_by_market_id,
            blocked_pathways_by_market_id=blocked_pathways_by_market_id,
            execution_blocker_codes_by_market_id=execution_blocker_codes_by_market_id,
            reference_only_market_ids=reference_only_market_ids,
            watchlist_market_ids=watchlist_market_ids,
            execution_market_ids=execution_market_ids,
            comparable_group_id=candidate.comparable_group_id,
            comparison_state=comparison_state,
            execution_route=route,
            tradeable=bool(tradeable and candidate.preferred_execution_market_id in execution_equivalent_market_ids),
            manual_review_required=manual_review_required,
            spread_bps=candidate.spread_bps,
            classification=classification,
            taxonomy=taxonomy,
            execution_filter_reason_codes=execution_filter_reason_codes,
            preferred_execution_pathway=candidate.preferred_execution_pathway,
            preferred_execution_mode=candidate.preferred_execution_mode,
            preferred_operator_action=candidate.preferred_operator_action,
            preferred_promotion_target_pathway=candidate.preferred_promotion_target_pathway,
            preferred_execution_selection_reason=candidate.preferred_execution_selection_reason,
            pathway_summary=candidate.pathway_summary,
            operator_summary=candidate.operator_summary,
            promotion_summary=candidate.promotion_summary,
            blocker_summary=candidate.blocker_summary,
            preferred_execution_summary=candidate.preferred_execution_summary,
            preferred_execution_capability_summary=candidate.preferred_execution_capability_summary,
            rationale=candidate.rationale,
            legs=legs,
            metadata={
                **dict(candidate.metadata),
                "candidate_state": comparison_state.value,
                "tradeable": bool(tradeable and candidate.preferred_execution_market_id in execution_equivalent_market_ids),
                "classification": classification,
                "taxonomy": taxonomy.value,
                "execution_filter_reason_codes": execution_filter_reason_codes,
                "planning_buckets": {leg.market_id: leg.planning_bucket for leg in legs},
                "read_only_market_ids": list(candidate.market_ids),
                "comparable_market_refs": list(candidate.market_ids),
                "execution_equivalent_market_ids": list(execution_equivalent_market_ids),
                "execution_like_market_ids": list(execution_like_market_ids),
                "execution_roles_by_market_id": dict(execution_roles_by_market_id),
                "execution_pathways_by_market_id": dict(execution_pathways_by_market_id),
                "readiness_stages_by_market_id": dict(readiness_stages_by_market_id),
                "highest_actionable_modes_by_market_id": dict(highest_actionable_modes_by_market_id),
                "required_operator_actions_by_market_id": dict(required_operator_actions_by_market_id),
                "next_pathways_by_market_id": dict(next_pathways_by_market_id),
                "next_pathway_rules_by_market_id": {
                    market_id: list(rules)
                    for market_id, rules in next_pathway_rules_by_market_id.items()
                },
                "bounded_execution_equivalent_market_ids": list(bounded_execution_equivalent_market_ids),
                "bounded_execution_equivalent_count": len(bounded_execution_equivalent_market_ids),
                "bounded_execution_promotion_candidate_market_ids": list(bounded_execution_promotion_candidate_market_ids),
                "bounded_execution_promotion_candidate_count": len(bounded_execution_promotion_candidate_market_ids),
                "readiness_stage_counts": {
                    stage: sum(1 for value in readiness_stages_by_market_id.values() if value == stage)
                    for stage in sorted({*readiness_stages_by_market_id.values()})
                },
                "next_pathway_counts": {
                    pathway: sum(1 for value in next_pathways_by_market_id.values() if value == pathway)
                    for pathway in sorted({value for value in next_pathways_by_market_id.values() if value})
                },
                "stage_summaries_by_market_id": {
                    market_id: dict(summary)
                    for market_id, summary in stage_summaries_by_market_id.items()
                },
                "promotion_target_pathways_by_market_id": dict(promotion_target_pathways_by_market_id),
                "promotion_rules_by_market_id": {
                    market_id: list(rules)
                    for market_id, rules in promotion_rules_by_market_id.items()
                },
                "pathway_ladders_by_market_id": {
                    market_id: list(ladder)
                    for market_id, ladder in pathway_ladders_by_market_id.items()
                },
                "blocked_pathways_by_market_id": {
                    market_id: list(pathways)
                    for market_id, pathways in blocked_pathways_by_market_id.items()
                },
                "execution_blocker_codes_by_market_id": {
                    market_id: list(codes)
                    for market_id, codes in execution_blocker_codes_by_market_id.items()
                },
                "preferred_execution_pathway": candidate.preferred_execution_pathway,
                "preferred_execution_mode": candidate.preferred_execution_mode,
                "preferred_operator_action": candidate.preferred_operator_action,
                "preferred_promotion_target_pathway": candidate.preferred_promotion_target_pathway,
                "preferred_execution_selection_reason": candidate.preferred_execution_selection_reason,
                "preferred_pathway_summary": candidate.pathway_summary,
                "preferred_operator_summary": candidate.operator_summary,
                "preferred_promotion_summary": candidate.promotion_summary,
                "preferred_blocker_summary": candidate.blocker_summary,
                "preferred_execution_summary": candidate.preferred_execution_summary,
                "preferred_execution_capability_summary": candidate.preferred_execution_capability_summary,
                "preferred_execution_is_equivalent": candidate.preferred_execution_market_id in execution_equivalent_market_ids,
                "manual_review_required": manual_review_required,
            },
        )

    def _execution_capable(self, venue: VenueName) -> bool:
        return self.execution_registry.is_execution_capable(venue) or self.venue_matrix.qualifies_for(venue, VenueType.execution)

    @staticmethod
    def _execution_route(preferred: MarketDescriptor, left: MarketDescriptor, right: MarketDescriptor) -> str:
        if preferred.market_id == left.market_id:
            return "left_preferred"
        if preferred.market_id == right.market_id:
            return "right_preferred"
        return "comparison_only"

    def _signal_capable(self, venue: VenueName) -> bool:
        return self.execution_registry.qualifies_for(venue, VenueType.signal) or self.venue_matrix.qualifies_for(venue, VenueType.signal)

    def _reference_capable(self, venue: VenueName) -> bool:
        return self.execution_registry.qualifies_for(venue, VenueType.reference) or self.venue_matrix.qualifies_for(venue, VenueType.reference)

    def _execution_pathway_for_venue(self, venue: VenueName) -> str:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.execution_pathway
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is not None:
            return matrix_surface.execution_pathway
        return registry_surface.execution_pathway or "read_only"

    def _execution_blocker_codes_for_venue(self, venue: VenueName) -> list[str]:
        registry_surface = self.execution_registry.execution_surface(venue)
        registry_codes = list(registry_surface.execution_blocker_codes)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_codes
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_codes
        return list(matrix_surface.execution_blocker_codes)

    def _highest_actionable_mode_for_venue(self, venue: VenueName) -> str | None:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.highest_actionable_mode
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_surface.highest_actionable_mode
        return matrix_surface.highest_actionable_mode

    def _readiness_stage_for_venue(self, venue: VenueName) -> str:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.readiness_stage
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_surface.readiness_stage
        return matrix_surface.readiness_stage

    def _required_operator_action_for_venue(self, venue: VenueName) -> str:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.required_operator_action
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_surface.required_operator_action
        return matrix_surface.required_operator_action

    def _next_pathway_for_venue(self, venue: VenueName) -> str | None:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.next_pathway
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_surface.next_pathway
        return matrix_surface.next_pathway

    def _next_pathway_rules_for_venue(self, venue: VenueName) -> list[str]:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return list(registry_surface.next_pathway_rules)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return list(registry_surface.next_pathway_rules)
        return list(matrix_surface.next_pathway_rules)

    def _promotion_target_pathway_for_venue(self, venue: VenueName) -> str | None:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return registry_surface.promotion_target_pathway
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return registry_surface.promotion_target_pathway
        return matrix_surface.promotion_target_pathway

    def _promotion_rules_for_venue(self, venue: VenueName) -> list[str]:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return list(registry_surface.promotion_rules)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return list(registry_surface.promotion_rules)
        return list(matrix_surface.promotion_rules)

    def _pathway_ladder_for_venue(self, venue: VenueName) -> list[str]:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return list(registry_surface.pathway_ladder)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return list(registry_surface.pathway_ladder)
        return list(matrix_surface.pathway_ladder)

    def _blocked_pathways_for_venue(self, venue: VenueName) -> list[str]:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return list(registry_surface.blocked_pathways)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return list(registry_surface.blocked_pathways)
        return list(matrix_surface.blocked_pathways)

    def _bounded_execution_equivalent_for_venue(self, venue: VenueName) -> bool:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return bool(registry_surface.bounded_execution_equivalent)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return bool(registry_surface.bounded_execution_equivalent)
        return bool(matrix_surface.bounded_execution_equivalent)

    def _bounded_execution_promotion_candidate_for_venue(self, venue: VenueName) -> bool:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return bool(registry_surface.bounded_execution_promotion_candidate)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return bool(registry_surface.bounded_execution_promotion_candidate)
        return bool(matrix_surface.bounded_execution_promotion_candidate)

    def _stage_summary_for_venue(self, venue: VenueName) -> dict[str, Any]:
        registry_surface = self.execution_registry.execution_surface(venue)
        if registry_surface.execution_pathway and registry_surface.execution_pathway != "read_only":
            return dict(registry_surface.stage_summary)
        matrix_surface = self.venue_matrix.surface_for(venue)
        if matrix_surface is None:
            return dict(registry_surface.stage_summary)
        return dict(matrix_surface.stage_summary)

    def _credential_gate_for_venue(self, venue: VenueName) -> str:
        return str(self._stage_summary_for_venue(venue).get("credential_gate", "read_only"))

    def _api_gate_for_venue(self, venue: VenueName) -> str:
        return str(self._stage_summary_for_venue(venue).get("api_gate", "watchlist_only_surface"))

    def _missing_requirement_codes_for_venue(self, venue: VenueName) -> list[str]:
        return list(self._stage_summary_for_venue(venue).get("missing_requirement_codes", []))

    def _operator_checklist_for_venue(self, venue: VenueName) -> list[str]:
        return list(self._stage_summary_for_venue(venue).get("operator_checklist", []))

    def _promotion_evidence_for_venue(self, venue: VenueName) -> dict[str, dict[str, Any]]:
        evidence = self._stage_summary_for_venue(venue).get("promotion_evidence_by_pathway", {})
        return {
            key: dict(value)
            for key, value in dict(evidence).items()
        }

    @staticmethod
    def _readiness_rank(stage: str) -> int:
        return {
            "read_only": 0,
            "paper_ready": 1,
            "bindable_ready": 2,
            "dry_run_ready": 3,
            "bounded_ready": 4,
            "live_ready": 5,
        }.get(stage, 0)

    def _preference_rank_for_market(self, market: MarketDescriptor) -> tuple[int, int, int, int, int, float, float]:
        stage_summary = self._stage_summary_for_venue(market.venue)
        missing_requirement_count = len(stage_summary.get("missing_requirement_codes", []))
        blocked_pathway_count = len(stage_summary.get("blocked_pathways", []))
        requirement_count = len(stage_summary.get("execution_requirement_codes", []))
        return (
            1 if self._execution_capable(market.venue) else 0,
            1 if self._bounded_execution_equivalent_for_venue(market.venue) else 0,
            self._readiness_rank(self._readiness_stage_for_venue(market.venue)),
            -missing_requirement_count,
            -blocked_pathway_count - requirement_count,
            float(market.clarity_score),
            float(market.liquidity or 0.0),
        )

    def _preferred_execution_selection_reason(
        self,
        preferred: MarketDescriptor,
        alternate: MarketDescriptor,
    ) -> str:
        preferred_stage = self._readiness_stage_for_venue(preferred.venue)
        alternate_stage = self._readiness_stage_for_venue(alternate.venue)
        if self._bounded_execution_equivalent_for_venue(preferred.venue) != self._bounded_execution_equivalent_for_venue(alternate.venue):
            return "bounded_execution_equivalent_priority"
        if self._readiness_rank(preferred_stage) != self._readiness_rank(alternate_stage):
            return "higher_readiness_stage"
        if len(self._missing_requirement_codes_for_venue(preferred.venue)) != len(self._missing_requirement_codes_for_venue(alternate.venue)):
            return "fewer_missing_requirements"
        if len(self._blocked_pathways_for_venue(preferred.venue)) != len(self._blocked_pathways_for_venue(alternate.venue)):
            return "fewer_blocked_pathways"
        if float(preferred.clarity_score) != float(alternate.clarity_score):
            return "higher_clarity_score"
        if float(preferred.liquidity or 0.0) != float(alternate.liquidity or 0.0):
            return "higher_liquidity"
        return "stable_tie_break"

    def _preferred_execution_semantics_for_pathway(self, pathway: str | None) -> str:
        if pathway == "live_execution":
            return "live_candidate"
        if pathway == "bounded_execution":
            return "bounded_candidate"
        if pathway == "execution_bindable_dry_run":
            return "execution_bindable_candidate"
        if pathway in {"execution_like_dry_run", "execution_like_paper_only", "dry_run_only"}:
            return "execution_like_candidate"
        if pathway == "reference_read_only":
            return "reference_candidate"
        if pathway == "signal_read_only":
            return "signal_candidate"
        return "watchlist_candidate"

    @staticmethod
    def _pathway_category(pathway: str | None) -> str:
        if pathway == "live_execution":
            return "live"
        if pathway == "bounded_execution":
            return "bounded"
        if pathway == "execution_bindable_dry_run":
            return "bindable"
        if pathway in {"execution_like_dry_run", "dry_run_only"}:
            return "dry_run"
        if pathway == "execution_like_paper_only":
            return "paper"
        if pathway in {"reference_read_only", "signal_read_only", "watchlist_read_only", "read_only"}:
            return "read_only"
        return "unknown"

    def _mixed_execution_semantics(self, execution_pathways_by_market_id: dict[str, str]) -> str:
        categories = {
            self._pathway_category(pathway)
            for pathway in execution_pathways_by_market_id.values()
        }
        if categories == {"live"}:
            return "all_live_ready"
        if categories == {"bounded"}:
            return "all_bounded_ready"
        if categories == {"live", "bounded"}:
            return "mixed_live_and_bounded"
        if categories == {"bindable"}:
            return "all_bindable_ready"
        if categories == {"bindable", "bounded"}:
            return "bindable_and_bounded"
        if categories == {"dry_run"}:
            return "all_dry_run_ready"
        if categories == {"paper"}:
            return "all_paper_only"
        if categories <= {"live", "bounded", "bindable", "dry_run"} and "bindable" in categories:
            return "mixed_actionable_and_bindable"
        if categories <= {"live", "bounded", "bindable", "dry_run", "paper"} and {"paper", "dry_run"} & categories:
            return "mixed_progressive_pathways"
        if categories == {"read_only"}:
            return "read_only_only"
        return "mixed_read_only_and_actionable"

    @staticmethod
    def _survivability_semantics_for_summary(summary: dict[str, Any]) -> str:
        readiness_stage = str(summary.get("readiness_stage", "read_only"))
        execution_pathway = str(summary.get("execution_pathway", "read_only"))
        if readiness_stage == "live_ready":
            return "leg_live_ready"
        if readiness_stage == "bounded_ready":
            return "leg_bounded_ready"
        if readiness_stage == "bindable_ready":
            return "leg_bindable_ready"
        if readiness_stage == "dry_run_ready":
            return "leg_dry_run_only"
        if readiness_stage == "paper_ready" and execution_pathway == "execution_like_paper_only":
            return "leg_paper_only"
        if readiness_stage == "paper_ready":
            return "leg_observer_only"
        return "leg_read_only"

    @staticmethod
    def _survivability_hint(
        *,
        tradeable: bool,
        preferred_execution_semantics: str,
        mixed_execution_semantics: str,
        readiness_stages_by_market_id: dict[str, str],
        missing_requirement_counts_by_market_id: dict[str, int],
    ) -> str:
        if tradeable and mixed_execution_semantics == "mixed_live_and_bounded":
            return "survivable_with_bounded_fallback"
        if tradeable and preferred_execution_semantics == "live_candidate":
            return "survivable_live_primary"
        if tradeable and preferred_execution_semantics == "bounded_candidate":
            return "bounded_primary_requires_supervision"
        if preferred_execution_semantics == "execution_bindable_candidate":
            return "bindable_only_no_real_hedge"
        if preferred_execution_semantics == "execution_like_candidate":
            return "dry_run_only_no_real_hedge"
        if any(int(value) > 0 for value in missing_requirement_counts_by_market_id.values()):
            return "promotion_blocked_before_real_hedge"
        if any(stage != "read_only" for stage in readiness_stages_by_market_id.values()):
            return "manual_review_before_multi_leg"
        return "comparison_only_no_execution_path"

    @staticmethod
    def _multi_leg_operator_checklist(
        *,
        preferred_market_id: str,
        preferred_operator_action: str | None,
        mixed_execution_semantics: str,
        survivability_hint: str,
        operator_checklists_by_market_id: dict[str, list[str]],
        next_pathways_by_market_id: dict[str, str | None],
    ) -> list[str]:
        checklist: list[str] = []
        if preferred_operator_action:
            checklist.append(f"preferred:{preferred_market_id}:{preferred_operator_action}")
        checklist.append(f"semantics:{mixed_execution_semantics}")
        checklist.append(f"survivability:{survivability_hint}")
        for market_id in sorted(operator_checklists_by_market_id):
            for item in operator_checklists_by_market_id[market_id]:
                checklist.append(f"{market_id}:{item}")
            next_pathway = next_pathways_by_market_id.get(market_id)
            if next_pathway:
                checklist.append(f"{market_id}:next_pathway:{next_pathway}")
        return list(dict.fromkeys(checklist))

    @staticmethod
    def _multi_leg_blocker_codes(
        *,
        execution_filter_reason_codes: list[str],
        execution_blocker_codes_by_market_id: dict[str, list[str]],
        next_pathways_by_market_id: dict[str, str | None],
        missing_requirement_counts_by_market_id: dict[str, int],
        execution_pathways_by_market_id: dict[str, str],
        preferred_market_id: str,
        readiness_stages_by_market_id: dict[str, str],
    ) -> list[str]:
        codes = list(execution_filter_reason_codes)
        for blocker_codes in execution_blocker_codes_by_market_id.values():
            codes.extend(blocker_codes)
        if any(int(value) > 0 for value in missing_requirement_counts_by_market_id.values()):
            codes.append("multi_leg_missing_requirements")
        if any(value for value in next_pathways_by_market_id.values()):
            codes.append("multi_leg_promotion_pending")
        if any(pathway in {"execution_bindable_dry_run", "execution_like_dry_run", "execution_like_paper_only"} for pathway in execution_pathways_by_market_id.values()):
            codes.append("multi_leg_non_live_leg_present")
        if any(
            market_id != preferred_market_id and readiness_stage != "live_ready"
            for market_id, readiness_stage in readiness_stages_by_market_id.items()
        ):
            codes.append("secondary_leg_not_live_ready")
        if any(pathway.endswith("read_only") for pathway in execution_pathways_by_market_id.values()):
            codes.append("read_only_leg_present")
        return list(dict.fromkeys(code for code in codes if code))

    @staticmethod
    def _market_question_key(left: MarketDescriptor, right: MarketDescriptor) -> str:
        return MarketGraphBuilder._question_key(left.question or left.title, right.question or right.title)

    @staticmethod
    def _market_resolution_source(market: MarketDescriptor) -> str | None:
        return _first_non_empty(
            market.resolution_source,
            market.metadata.get("resolution_source"),
            market.metadata.get("official_source"),
            market.metadata.get("source_url"),
            market.raw.get("resolution_source"),
            market.raw.get("official_source"),
            market.raw.get("source_url"),
        )

    @staticmethod
    def _market_currency(market: MarketDescriptor) -> str | None:
        return _first_non_empty(
            market.metadata.get("currency"),
            market.metadata.get("collateral_currency"),
            market.raw.get("currency"),
            market.raw.get("collateral_currency"),
        )

    @staticmethod
    def _market_payout_currency(market: MarketDescriptor) -> str | None:
        return _first_non_empty(
            market.metadata.get("payout_currency"),
            market.metadata.get("currency"),
            market.metadata.get("collateral_currency"),
            market.raw.get("payout_currency"),
            market.raw.get("currency"),
            market.raw.get("collateral_currency"),
        )

    @staticmethod
    def _compatible_currency(left: MarketDescriptor, right: MarketDescriptor) -> bool:
        left_currency = CrossVenueIntelligence._market_currency(left)
        right_currency = CrossVenueIntelligence._market_currency(right)
        return bool(left_currency and right_currency and left_currency == right_currency)

    @staticmethod
    def _compatible_payout(left: MarketDescriptor, right: MarketDescriptor) -> bool:
        left_currency = CrossVenueIntelligence._market_payout_currency(left)
        right_currency = CrossVenueIntelligence._market_payout_currency(right)
        return bool(left_currency and right_currency and left_currency == right_currency)

    @staticmethod
    def _comparison_notes(
        *,
        left: MarketDescriptor,
        right: MarketDescriptor,
        compatible_resolution: bool,
        left_currency: str | None,
        right_currency: str | None,
        left_payout_currency: str | None,
        right_payout_currency: str | None,
        timing_notes: list[str] | None = None,
    ) -> list[str]:
        notes: list[str] = []
        if left.question != right.question:
            notes.append("question_normalized")
        if not compatible_resolution:
            notes.append("resolution_mismatch")
        if left_currency and right_currency and left_currency != right_currency:
            notes.append("currency_mismatch")
        if left_payout_currency and right_payout_currency and left_payout_currency != right_payout_currency:
            notes.append("payout_currency_mismatch")
        if left.canonical_event_id != right.canonical_event_id:
            notes.append("canonical_event_inferred")
        if timing_notes:
            notes.extend(timing_notes)
        return list(dict.fromkeys(notes))

    @staticmethod
    def _comparable_group_id_from_markets(left: MarketDescriptor, right: MarketDescriptor) -> str | None:
        return left.canonical_event_id or right.canonical_event_id or CrossVenueIntelligence._market_question_key(left, right) or None

    @staticmethod
    def _get_market(markets: list[MarketDescriptor], market_id: str) -> MarketDescriptor:
        for market in markets:
            if market.market_id == market_id:
                return market
        raise KeyError(market_id)

    @staticmethod
    def _probability(snapshot: MarketSnapshot | None) -> float | None:
        if snapshot is None:
            return None
        for candidate in (snapshot.market_implied_probability, snapshot.fair_probability_hint, snapshot.midpoint_yes, snapshot.price_yes):
            if candidate is not None:
                return max(0.0, min(1.0, float(candidate)))
        return None

    @staticmethod
    def _reference_pair(left: MarketDescriptor, right: MarketDescriptor) -> tuple[str | None, str | None]:
        left_priority = CrossVenueIntelligence._role_priority(left)
        right_priority = CrossVenueIntelligence._role_priority(right)
        if left_priority > right_priority:
            return left.market_id, right.market_id
        if right_priority > left_priority:
            return right.market_id, left.market_id
        if left.clarity_score >= right.clarity_score:
            return left.market_id, right.market_id
        return right.market_id, left.market_id

    @staticmethod
    def _compatible_resolution(left: MarketDescriptor, right: MarketDescriptor) -> bool:
        left_source = (left.resolution_source or "").strip().lower()
        right_source = (right.resolution_source or "").strip().lower()
        if not left_source or not right_source:
            return False
        return left_source == right_source

    @staticmethod
    def _canonical_event_id(left: MarketDescriptor, right: MarketDescriptor) -> str:
        tokens = sorted(MarketGraphBuilder._question_tokens(left.question or left.title) | MarketGraphBuilder._question_tokens(right.question or right.title))
        return "cv_" + "_".join(tokens[:8]) if tokens else f"cv_{left.market_id}_{right.market_id}"

    @staticmethod
    def _question_key(*questions: str) -> str:
        tokens: set[str] = set()
        for question in questions:
            tokens |= MarketGraphBuilder._question_tokens(question)
        return " ".join(sorted(tokens))

    @staticmethod
    def _severity_for_spread(spread_bps: float) -> SpreadSeverity:
        if spread_bps >= 200:
            return SpreadSeverity.high
        if spread_bps >= 120:
            return SpreadSeverity.medium
        return SpreadSeverity.low

    def _qualification_summary(self, markets: list[MarketDescriptor]) -> CrossVenueQualificationSummary:
        venue_roles: dict[str, list[str]] = {}
        role_venues: dict[str, list[str]] = {}
        role_counts: dict[str, int] = {}

        for market in markets:
            roles = self._market_roles(market)
            venue_roles[market.venue.value] = roles
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1
                role_venues.setdefault(role, [])
                if market.venue.value not in role_venues[role]:
                    role_venues[role].append(market.venue.value)

        for venues in role_venues.values():
            venues.sort()

        return CrossVenueQualificationSummary(
            venue_roles=venue_roles,
            role_venues=role_venues,
            role_counts={key: value for key, value in sorted(role_counts.items())},
        )

    def _venue_role_classification(self) -> VenueRoleClassification:
        execution_classification = self.execution_registry.role_classification()
        matrix_classification = self.venue_matrix.role_classification()
        venue_roles = dict(matrix_classification.venue_roles)
        role_venues = dict(matrix_classification.role_venues)
        role_counts = dict(matrix_classification.role_counts)
        for role, venues in execution_classification.role_venues.items():
            merged = role_venues.setdefault(role, [])
            for venue in venues:
                if venue not in merged:
                    merged.append(venue)
            merged.sort()
        for role, count in execution_classification.role_counts.items():
            role_counts[role] = max(role_counts.get(role, 0), count)
        execution_equivalent_venues = list(
            dict.fromkeys(
                list(execution_classification.execution_equivalent_venues)
                + list(matrix_classification.execution_equivalent_venues)
            )
        )
        execution_bindable_venues = list(
            dict.fromkeys(
                list(getattr(execution_classification, "execution_bindable_venues", []))
                + list(getattr(matrix_classification, "execution_bindable_venues", []))
            )
        )
        matrix_venue_taxonomy = dict(getattr(matrix_classification, "metadata", {}).get("venue_taxonomy", {}))
        matrix_execution_like_venues = [
            venue
            for venue in list(getattr(matrix_classification, "execution_like_venues", []))
            if matrix_venue_taxonomy.get(venue.value) != "decentralized_execution_like"
            and venue not in execution_bindable_venues
        ]
        execution_like_venues = list(
            dict.fromkeys(
                list(getattr(execution_classification, "execution_like_venues", []))
                + matrix_execution_like_venues
            )
        )
        reference_only_venues = list(
            dict.fromkeys(
                list(execution_classification.reference_only_venues)
                + list(matrix_classification.reference_only_venues)
            )
        )
        watchlist_only_venues = list(
            dict.fromkeys(
                list(execution_classification.watchlist_only_venues)
                + list(matrix_classification.watchlist_only_venues)
            )
        )
        planning_buckets = {
            venue.value: "execution-equivalent" for venue in execution_equivalent_venues
        }
        planning_buckets.update({venue.value: "execution-bindable" for venue in execution_bindable_venues})
        planning_buckets.update({venue.value: "execution-like" for venue in execution_like_venues})
        planning_buckets.update({venue.value: "reference-only" for venue in reference_only_venues})
        planning_buckets.update({venue.value: "watchlist" for venue in watchlist_only_venues})
        return VenueRoleClassification(
            venue_roles=venue_roles,
            role_venues=role_venues,
            role_counts={key: value for key, value in sorted(role_counts.items())},
            execution_equivalent_venues=execution_equivalent_venues,
            execution_bindable_venues=execution_bindable_venues,
            execution_like_venues=execution_like_venues,
            reference_only_venues=reference_only_venues,
            watchlist_only_venues=watchlist_only_venues,
            execution_venues=execution_classification.execution_venues,
            reference_venues=matrix_classification.reference_venues,
            signal_venues=matrix_classification.signal_venues,
            watchlist_venues=matrix_classification.watchlist_venues,
            read_only_venues=matrix_classification.read_only_venues,
            paper_capable_venues=execution_classification.paper_capable_venues,
            execution_capable_venues=execution_classification.execution_capable_venues,
            metadata={
                "execution_registry_count": len(self.execution_registry.capabilities),
                "additional_venue_count": len(self.venue_matrix.profiles),
                "execution_equivalent_count": len(execution_classification.execution_equivalent_venues),
                "execution_bindable_count": len(execution_bindable_venues),
                "execution_like_count": len(execution_like_venues),
                "reference_only_count": len(execution_classification.reference_only_venues),
                "watchlist_only_count": len(execution_classification.watchlist_only_venues),
                "planning_buckets": planning_buckets,
                "execution_taxonomy": {
                    **{
                        venue.value: "execution_equivalent"
                        for venue in execution_equivalent_venues
                    },
                    **{
                        venue.value: "execution_bindable"
                        for venue in execution_bindable_venues
                    },
                    **{
                        venue.value: "execution_like"
                        for venue in execution_like_venues
                    },
                    **{
                        venue.value: "reference_only"
                        for venue in reference_only_venues
                    },
                    **{
                        venue.value: "watchlist"
                        for venue in watchlist_only_venues
                    },
                },
            },
        )

    def _market_roles(self, market: MarketDescriptor) -> list[str]:
        profile = self.venue_matrix.profile(market.venue)
        roles = set()
        if profile is not None:
            roles.update(profile.role_labels())
        roles.add(market.venue_type.value)
        return [role.value for role in _ordered_venue_types({VenueType(role) for role in roles})]

    def _planning_bucket_for_market(self, market: MarketDescriptor) -> str:
        execution_surface = self.execution_registry.execution_surface(market.venue)
        if execution_surface.execution_equivalent:
            return "execution-equivalent"
        if execution_surface.execution_taxonomy == "execution_bindable" or execution_surface.execution_readiness == "bindable_ready":
            return "execution-bindable"
        if execution_surface.execution_like:
            return "execution-like"
        roles = {VenueType(role) for role in CrossVenueIntelligence._raw_market_roles(market)}
        if VenueType.reference in roles or market.venue_type == VenueType.reference:
            return "reference-only"
        return "watchlist"

    @staticmethod
    def _role_priority(market: MarketDescriptor) -> tuple[int, float, float]:
        roles = {VenueType(role) for role in CrossVenueIntelligence._raw_market_roles(market)}
        score = 0
        if VenueType.reference in roles or market.venue_type == VenueType.reference:
            score = 4
        elif VenueType.execution in roles or market.venue_type == VenueType.execution:
            score = 3
        elif VenueType.signal in roles or market.venue_type == VenueType.signal:
            score = 2
        elif VenueType.watchlist in roles or market.venue_type == VenueType.watchlist:
            score = 1
        return score, market.clarity_score, float(market.liquidity or 0.0)

    @staticmethod
    def _raw_market_roles(market: MarketDescriptor) -> list[str]:
        roles = [market.venue_type.value]
        profile = DEFAULT_ADDITIONAL_VENUE_MATRIX.profile(market.venue)
        if profile is not None:
            roles.extend(profile.role_labels())
        return list(dict.fromkeys(roles))


def _ordered_venue_types(values: set[VenueType]) -> list[VenueType]:
    rank = {
        VenueType.reference: 0,
        VenueType.execution: 1,
        VenueType.signal: 2,
        VenueType.watchlist: 3,
        VenueType.experimental: 4,
    }
    return sorted(values, key=lambda item: (rank.get(item, 99), item.value))
