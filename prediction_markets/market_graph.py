from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

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


class GraphRelationKind(str, Enum):
    same_event = "same_event"
    same_question = "same_question"
    same_topic = "same_topic"
    reference = "reference"
    comparison = "comparison"


class ComparableMarketGroup(BaseModel):
    schema_version: str = "v1"
    group_id: str = Field(default_factory=lambda: f"cmpgrp_{uuid4().hex[:12]}")
    canonical_event_id: str
    question_key: str
    question: str = ""
    relation_kind: GraphRelationKind = GraphRelationKind.same_topic
    market_ids: list[str] = Field(default_factory=list)
    comparable_market_refs: list[str] = Field(default_factory=list)
    venues: list[str] = Field(default_factory=list)
    venue_types: list[str] = Field(default_factory=list)
    reference_market_ids: list[str] = Field(default_factory=list)
    comparison_market_ids: list[str] = Field(default_factory=list)
    parent_market_ids: list[str] = Field(default_factory=list)
    child_market_ids: list[str] = Field(default_factory=list)
    parent_child_pairs: list[dict[str, Any]] = Field(default_factory=list)
    natural_hedge_market_ids: list[str] = Field(default_factory=list)
    natural_hedge_pairs: list[dict[str, Any]] = Field(default_factory=list)
    resolution_sources: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)
    payout_currencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
    compatible_resolution: bool = False
    compatible_currency: bool = False
    compatible_payout: bool = False
    match_count: int = 0
    duplicate_market_count: int = 0
    duplicate_market_rate: float = 0.0
    desalignment_count: int = 0
    desalignment_rate: float = 0.0
    desalignment_dimensions: list[str] = Field(default_factory=list)
    narrative_risk_flags: list[str] = Field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVenueMatchRejection(BaseModel):
    schema_version: str = "v1"
    rejection_id: str = Field(default_factory=lambda: f"cvrej_{uuid4().hex[:12]}")
    left_market_id: str
    right_market_id: str
    left_venue: VenueName
    right_venue: VenueName
    canonical_event_id: str
    question_left: str = ""
    question_right: str = ""
    question_key: str = ""
    similarity: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketGraphNode(BaseModel):
    schema_version: str = "v1"
    node_id: str
    market_id: str
    venue: VenueName
    venue_type: VenueType
    title: str
    question: str
    canonical_event_id: str | None = None
    status: str = "unknown"
    role: str = "comparison"
    clarity_score: float = 0.0
    liquidity: float | None = None
    price_yes: float | None = None
    snapshot_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketGraphEdge(BaseModel):
    schema_version: str = "v1"
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: GraphRelationKind
    similarity: float = 0.0
    compatible_resolution: bool = False
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketGraph(BaseModel):
    schema_version: str = "v1"
    graph_id: str = Field(default_factory=lambda: f"mgraph_{uuid4().hex[:12]}")
    nodes: list[MarketGraphNode] = Field(default_factory=list)
    edges: list[MarketGraphEdge] = Field(default_factory=list)
    matches: list[CrossVenueMatch] = Field(default_factory=list)
    rejected_matches: list[CrossVenueMatchRejection] = Field(default_factory=list)
    comparable_groups: list[ComparableMarketGroup] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def nodes_by_market_id(self) -> dict[str, MarketGraphNode]:
        return {node.market_id: node for node in self.nodes}

    def edges_for_market(self, market_id: str) -> list[MarketGraphEdge]:
        node_id = None
        for node in self.nodes:
            if node.market_id == market_id:
                node_id = node.node_id
                break
        if node_id is None:
            return []
        return [edge for edge in self.edges if edge.source_node_id == node_id or edge.target_node_id == node_id]

    def comparable_group_for_market(self, market_id: str) -> ComparableMarketGroup | None:
        for group in self.comparable_groups:
            if market_id in group.market_ids:
                return group
        return None

    def comparable_group_index(self) -> dict[str, ComparableMarketGroup]:
        index: dict[str, ComparableMarketGroup] = {}
        for group in self.comparable_groups:
            for market_id in group.market_ids:
                index[market_id] = group
        return index


@dataclass
class MarketGraphBuilder:
    similarity_threshold: float = 0.58
    relation_threshold: float = 0.45

    def build(
        self,
        markets: list[MarketDescriptor],
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
    ) -> MarketGraph:
        snapshots = snapshots or {}
        nodes = [self._build_node(market, snapshots.get(market.market_id)) for market in markets]
        edges: list[MarketGraphEdge] = []
        matches: list[CrossVenueMatch] = []
        rejected_matches: list[CrossVenueMatchRejection] = []

        for left, right in combinations(nodes, 2):
            if left.market_id == right.market_id:
                continue
            similarity, rationale = self._score_pair(left, right)
            rejection_reasons = self._rejection_reasons(left, right, similarity)
            if rejection_reasons:
                rejected_matches.append(self._build_rejection(left, right, similarity=similarity, rationale=rationale, reason_codes=rejection_reasons))
                continue
            if similarity < self.relation_threshold:
                continue
            relation = self._relation_kind(left, right, similarity)
            edges.append(
                MarketGraphEdge(
                    edge_id=f"edge_{uuid4().hex[:12]}",
                    source_node_id=left.node_id,
                    target_node_id=right.node_id,
                    relation=relation,
                    similarity=similarity,
                    compatible_resolution=self._compatible_resolution(left, right),
                    rationale=rationale,
                    metadata={
                        "left_market_id": left.market_id,
                        "right_market_id": right.market_id,
                    },
                )
            )
            if left.venue != right.venue and similarity >= self.similarity_threshold:
                matches.append(self._build_match(left, right, similarity=similarity, rationale=rationale))

        reference_map = self._select_references(nodes, snapshots)
        for node in nodes:
            if node.market_id in reference_map:
                node.role = "reference"
                node.metadata["reference_rank"] = reference_map[node.market_id]

        comparable_groups = self._build_comparable_groups(nodes, matches)
        group_index = {market_id: group.group_id for group in comparable_groups for market_id in group.market_ids}
        for node in nodes:
            if node.market_id in group_index:
                node.metadata["comparable_group_id"] = group_index[node.market_id]

        for edge in edges:
            left = next(node for node in nodes if node.node_id == edge.source_node_id)
            right = next(node for node in nodes if node.node_id == edge.target_node_id)
            if left.role == "reference" or right.role == "reference":
                edge.metadata["reference_bridge"] = True

        grouped_market_ids = sorted({market_id for group in comparable_groups for market_id in group.market_ids})
        duplicate_market_count = sum(max(0, len(group.market_ids) - 1) for group in comparable_groups)
        duplicate_market_rate = round(duplicate_market_count / max(1, len(nodes)), 6)
        parent_market_count = len({market_id for group in comparable_groups for market_id in group.parent_market_ids})
        child_market_count = len({market_id for group in comparable_groups for market_id in group.child_market_ids})
        natural_hedge_market_count = len({market_id for group in comparable_groups for market_id in group.natural_hedge_market_ids})
        parent_child_pair_count = sum(len(group.parent_child_pairs) for group in comparable_groups)
        natural_hedge_pair_count = sum(len(group.natural_hedge_pairs) for group in comparable_groups)
        family_relation_group_count = sum(
            1
            for group in comparable_groups
            if group.parent_child_pairs or group.natural_hedge_pairs
        )
        desaligned_match_count = sum(1 for match in matches if self._match_alignment_gap_count(match) > 0)
        desaligned_group_count = sum(1 for group in comparable_groups if group.desalignment_count > 0)
        duplicate_group_count = sum(1 for group in comparable_groups if group.duplicate_market_count > 0)
        average_duplicate_group_size = round(
            sum(len(group.market_ids) for group in comparable_groups) / max(1, len(comparable_groups)),
            6,
        ) if comparable_groups else 0.0
        rejection_reason_counts = dict(sorted(Counter(
            reason
            for rejection in rejected_matches
            for reason in rejection.reason_codes
        ).items()))
        mismatch_reason_counts = dict(sorted(Counter(
            note
            for match in matches
            for note in match.notes
        ).items()))
        match_desalignment_dimension_counts = dict(sorted(Counter(
            dimension
            for match in matches
            for dimension in self._match_alignment_dimensions(match)
        ).items()))
        group_desalignment_dimension_counts = dict(sorted(Counter(
            dimension
            for group in comparable_groups
            for dimension in group.desalignment_dimensions
        ).items()))

        return MarketGraph(
            nodes=nodes,
            edges=edges,
            matches=matches,
            rejected_matches=rejected_matches,
            comparable_groups=comparable_groups,
            metadata={
                "market_count": len(markets),
                "match_count": len(matches),
                "rejected_match_count": len(rejected_matches),
                "grouped_market_count": len(grouped_market_ids),
                "grouped_market_coverage_rate": round(len(grouped_market_ids) / max(1, len(nodes)), 6),
                "ungrouped_market_count": max(0, len(nodes) - len(grouped_market_ids)),
                "duplicate_market_count": duplicate_market_count,
                "duplicate_market_rate": duplicate_market_rate,
                "duplicate_group_count": duplicate_group_count,
                "average_duplicate_group_size": average_duplicate_group_size,
                "parent_market_count": parent_market_count,
                "child_market_count": child_market_count,
                "parent_child_pair_count": parent_child_pair_count,
                "natural_hedge_market_count": natural_hedge_market_count,
                "natural_hedge_pair_count": natural_hedge_pair_count,
                "family_relation_group_count": family_relation_group_count,
                "desaligned_match_count": desaligned_match_count,
                "desaligned_match_rate": round(desaligned_match_count / max(1, len(matches)), 6),
                "desaligned_group_count": desaligned_group_count,
                "desaligned_group_rate": round(desaligned_group_count / max(1, len(comparable_groups)), 6),
                "rejection_reason_counts": rejection_reason_counts,
                "mismatch_reason_counts": mismatch_reason_counts,
                "match_desalignment_dimension_counts": match_desalignment_dimension_counts,
                "group_desalignment_dimension_counts": group_desalignment_dimension_counts,
                "mapper_precision": round(len(matches) / max(1, len(matches) + len(rejected_matches)), 6),
                "false_match_rate": round(len(rejected_matches) / max(1, len(matches) + len(rejected_matches)), 6),
                "min_cross_venue_similarity_score": round(
                    min(
                        [match.similarity for match in matches] + [rejection.similarity for rejection in rejected_matches],
                        default=0.0,
                    ),
                    6,
                ),
                "comparable_group_count": len(comparable_groups),
                "relation_threshold": self.relation_threshold,
                "similarity_threshold": self.similarity_threshold,
            },
        )

    def _build_node(self, market: MarketDescriptor, snapshot: MarketSnapshot | None) -> MarketGraphNode:
        return MarketGraphNode(
            node_id=f"node_{market.market_id}",
            market_id=market.market_id,
            venue=market.venue,
            venue_type=market.venue_type,
            title=market.title,
            question=market.question or market.title,
            canonical_event_id=market.canonical_event_id,
            status=market.status.value if hasattr(market.status, "value") else str(market.status),
            clarity_score=market.clarity_score,
            liquidity=market.liquidity,
            price_yes=None if snapshot is None else snapshot.price_yes,
            snapshot_id=None if snapshot is None else snapshot.snapshot_id,
            metadata={
                "categories": list(market.categories),
                "tags": list(market.tags),
                "outcomes": list(market.outcomes),
                "source_url": market.source_url,
                "resolution_source": market.resolution_source,
                "question_key": self._question_key(market.question or market.title),
                "question_token_count": len(self._question_tokens(market.question or market.title)),
                "specificity_score": self._question_specificity_score(market.question or market.title, market),
                "hedge_profile": self._hedge_profile(market.question or market.title),
                "open_time": market.open_time.isoformat() if market.open_time is not None else None,
                "close_time": (market.close_time or market.end_date).isoformat() if (market.close_time or market.end_date) is not None else None,
                "end_date": market.end_date.isoformat() if market.end_date is not None else None,
                "resolution_date": market.resolution_date.isoformat() if market.resolution_date is not None else None,
                "timebox_start": market.open_time.isoformat() if market.open_time is not None else None,
                "timebox_end": (market.close_time or market.end_date).isoformat() if (market.close_time or market.end_date) is not None else None,
                "cutoff_at": (market.resolution_date or market.close_time or market.end_date).isoformat()
                if (market.resolution_date or market.close_time or market.end_date) is not None
                else None,
                "timezone": self._market_timezone_hint(market),
                "currency": self._market_currency(market),
                "collateral_currency": self._market_currency(market),
                "payout_currency": self._market_payout_currency(market),
                "role_hint": "reference" if market.venue_type == VenueType.reference else "comparison",
            },
        )

    def _build_match(self, left: MarketGraphNode, right: MarketGraphNode, *, similarity: float, rationale: str) -> CrossVenueMatch:
        canonical_event_id = left.canonical_event_id or right.canonical_event_id or self._canonical_question(left.question, right.question)
        timing_score, timing_notes, timing_metadata = self._timing_compatibility(left, right)
        return CrossVenueMatch(
            canonical_event_id=canonical_event_id,
            left_market_id=left.market_id,
            right_market_id=right.market_id,
            left_venue=left.venue,
            right_venue=right.venue,
            question_left=left.question,
            question_right=right.question,
            question_key=self._question_key(left.question, right.question),
            left_resolution_source=left.metadata.get("resolution_source"),
            right_resolution_source=right.metadata.get("resolution_source"),
            left_currency=_normalized_text(left.metadata.get("currency") or left.metadata.get("collateral_currency") or "") or None,
            right_currency=_normalized_text(right.metadata.get("currency") or right.metadata.get("collateral_currency") or "") or None,
            left_payout_currency=_normalized_text(left.metadata.get("payout_currency") or left.metadata.get("currency") or "") or None,
            right_payout_currency=_normalized_text(right.metadata.get("payout_currency") or right.metadata.get("currency") or "") or None,
            resolution_compatibility_score=1.0 if self._compatible_resolution(left, right) else 0.0,
            payout_compatibility_score=1.0 if self._compatible_payout(left, right) else 0.0,
            currency_compatibility_score=1.0 if self._compatible_currency(left, right) else 0.0,
            similarity=similarity,
            compatible_resolution=self._compatible_resolution(left, right),
            manual_review_required=not self._compatible_resolution(left, right) or similarity < 0.8 or timing_score < 1.0 or bool(timing_notes),
            comparable_group_id=self._comparable_group_id(left, right),
            comparable_market_refs=[left.market_id, right.market_id],
            notes=self._match_notes(left, right, timing_notes=timing_notes),
            rationale=rationale,
            metadata={
                "left_title": left.title,
                "right_title": right.title,
                "left_role": left.role,
                "right_role": right.role,
                "question_key": self._question_key(left.question, right.question),
                "left_resolution_source": left.metadata.get("resolution_source"),
                "right_resolution_source": right.metadata.get("resolution_source"),
                "left_currency": left.metadata.get("currency") or left.metadata.get("collateral_currency"),
                "right_currency": right.metadata.get("currency") or right.metadata.get("collateral_currency"),
                "left_payout_currency": left.metadata.get("payout_currency") or left.metadata.get("currency"),
                "right_payout_currency": right.metadata.get("payout_currency") or right.metadata.get("currency"),
                "timing_compatibility_score": timing_score,
                "timing_mismatch_reasons": list(timing_notes),
                "timing": timing_metadata,
            },
        )

    def _build_rejection(
        self,
        left: MarketGraphNode,
        right: MarketGraphNode,
        *,
        similarity: float,
        rationale: str,
        reason_codes: list[str],
    ) -> CrossVenueMatchRejection:
        canonical_event_id = left.canonical_event_id or right.canonical_event_id or self._canonical_question(left.question, right.question)
        return CrossVenueMatchRejection(
            canonical_event_id=canonical_event_id,
            left_market_id=left.market_id,
            right_market_id=right.market_id,
            left_venue=left.venue,
            right_venue=right.venue,
            question_left=left.question,
            question_right=right.question,
            question_key=self._question_key(left.question, right.question),
            similarity=similarity,
            reason_codes=list(dict.fromkeys(reason_codes)),
            rationale=rationale,
            metadata={
                "left_title": left.title,
                "right_title": right.title,
                "left_role": left.role,
                "right_role": right.role,
                "left_resolution_source": left.metadata.get("resolution_source"),
                "right_resolution_source": right.metadata.get("resolution_source"),
                "left_currency": left.metadata.get("currency") or left.metadata.get("collateral_currency"),
                "right_currency": right.metadata.get("currency") or right.metadata.get("collateral_currency"),
                "left_payout_currency": left.metadata.get("payout_currency") or left.metadata.get("currency"),
                "right_payout_currency": right.metadata.get("payout_currency") or right.metadata.get("currency"),
            },
        )

    def _build_comparable_groups(
        self,
        nodes: list[MarketGraphNode],
        matches: list[CrossVenueMatch],
    ) -> list[ComparableMarketGroup]:
        buckets: dict[str, list[MarketGraphNode]] = {}
        for node in nodes:
            key = node.canonical_event_id or self._canonical_question(node.question, node.title)
            buckets.setdefault(key, []).append(node)

        match_index: dict[str, list[CrossVenueMatch]] = {}
        for match in matches:
            match_index.setdefault(match.canonical_event_id, []).append(match)

        groups: list[ComparableMarketGroup] = []
        for canonical_event_id in sorted(buckets):
            group_nodes = sorted(buckets[canonical_event_id], key=lambda node: (node.venue.value, node.market_id))
            if len(group_nodes) < 2:
                continue
            if not match_index.get(canonical_event_id) and not any(node.canonical_event_id for node in group_nodes):
                continue
            question_key = self._question_key(group_nodes[0].question)
            relation_kind = self._relation_kind_for_group(group_nodes)
            reference_market_ids = [node.market_id for node in group_nodes if node.role == "reference"]
            comparison_market_ids = [node.market_id for node in group_nodes if node.role != "reference"]
            parent_market_ids, child_market_ids, parent_child_pairs = self._parent_child_relations(group_nodes)
            natural_hedge_market_ids, natural_hedge_pairs = self._natural_hedge_relations(group_nodes)
            for node in group_nodes:
                if node.market_id in parent_market_ids and node.market_id in child_market_ids:
                    family_role = "bridge"
                elif node.market_id in parent_market_ids:
                    family_role = "parent"
                elif node.market_id in child_market_ids:
                    family_role = "child"
                elif node.market_id in natural_hedge_market_ids:
                    family_role = "hedge"
                else:
                    family_role = "peer"
                node.metadata["family_role"] = family_role
                node.metadata["natural_hedge_role"] = "hedge" if node.market_id in natural_hedge_market_ids else "peer"
                node.metadata["family_relation_flags"] = sorted(
                    flag
                    for flag, market_ids in (
                        ("parent", parent_market_ids),
                        ("child", child_market_ids),
                        ("hedge", natural_hedge_market_ids),
                    )
                    if node.market_id in market_ids
                )
            compatible_resolution = self._group_compatible_resolution(group_nodes)
            timing_notes, timing_metadata = self._group_timing_profile(group_nodes)
            manual_review_required = self._group_manual_review_required(
                group_nodes,
                match_index.get(canonical_event_id, []),
                timing_notes=timing_notes,
            )
            narrative_risk_flags = self._group_narrative_risk_flags(
                group_nodes,
                compatible_resolution,
                manual_review_required,
                timing_notes=timing_notes,
            )
            group_notes = self._group_notes(
                group_nodes,
                compatible_resolution,
                manual_review_required,
                timing_notes=timing_notes,
            )
            duplicate_market_count = max(0, len(group_nodes) - 1)
            desalignment_dimensions = self._alignment_dimensions_from_notes(group_notes)
            desalignment_count = len(desalignment_dimensions)
            groups.append(
                ComparableMarketGroup(
                    canonical_event_id=canonical_event_id,
                    question_key=question_key,
                    relation_kind=relation_kind,
                    market_ids=[node.market_id for node in group_nodes],
                    comparable_market_refs=[node.market_id for node in group_nodes],
                    question=group_nodes[0].question,
                    venues=sorted({node.venue.value for node in group_nodes}),
                    venue_types=[node.venue_type.value for node in sorted(group_nodes, key=lambda node: (node.venue_type.value, node.venue.value, node.market_id))],
                    reference_market_ids=reference_market_ids,
                    comparison_market_ids=comparison_market_ids,
                    parent_market_ids=parent_market_ids,
                    child_market_ids=child_market_ids,
                    parent_child_pairs=parent_child_pairs,
                    natural_hedge_market_ids=natural_hedge_market_ids,
                    natural_hedge_pairs=natural_hedge_pairs,
                    resolution_sources=sorted(
                        {
                            str(node.metadata.get("resolution_source") or "").strip().lower()
                            for node in group_nodes
                            if str(node.metadata.get("resolution_source") or "").strip()
                        }
                    ),
                    currencies=sorted(
                        {
                            _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
                            for node in group_nodes
                            if _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
                        }
                    ),
                    payout_currencies=sorted(
                        {
                            _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
                            for node in group_nodes
                            if _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
                        }
                    ),
                    notes=group_notes,
                    manual_review_required=manual_review_required,
                    compatible_resolution=compatible_resolution,
                    compatible_currency=self._group_compatible_currency(group_nodes),
                    compatible_payout=self._group_compatible_payout(group_nodes),
                    match_count=len(match_index.get(canonical_event_id, [])),
                    duplicate_market_count=duplicate_market_count,
                    duplicate_market_rate=round(duplicate_market_count / max(1, len(group_nodes)), 6),
                    desalignment_count=desalignment_count,
                    desalignment_rate=round(desalignment_count / 4.0, 6),
                    desalignment_dimensions=desalignment_dimensions,
                    narrative_risk_flags=narrative_risk_flags,
                    rationale=self._group_rationale(
                        group_nodes,
                        relation_kind,
                        compatible_resolution,
                        manual_review_required,
                        parent_child_pairs=parent_child_pairs,
                        natural_hedge_pairs=natural_hedge_pairs,
                        timing_notes=timing_notes,
                    ),
                    metadata={
                        "node_count": len(group_nodes),
                        "reference_count": len(reference_market_ids),
                        "comparison_count": len(comparison_market_ids),
                        "parent_market_count": len(parent_market_ids),
                        "child_market_count": len(child_market_ids),
                        "parent_child_pair_count": len(parent_child_pairs),
                        "natural_hedge_market_count": len(natural_hedge_market_ids),
                        "natural_hedge_pair_count": len(natural_hedge_pairs),
                        "question_key": question_key,
                        "duplicate_market_count": duplicate_market_count,
                        "duplicate_market_rate": round(duplicate_market_count / max(1, len(group_nodes)), 6),
                        "desalignment_count": desalignment_count,
                        "desalignment_rate": round(desalignment_count / 4.0, 6),
                        "desalignment_dimensions": desalignment_dimensions,
                        "resolution_sources": sorted(
                            {
                                str(node.metadata.get("resolution_source") or "").strip().lower()
                                for node in group_nodes
                                if str(node.metadata.get("resolution_source") or "").strip()
                            }
                        ),
                        "currencies": sorted(
                            {
                                _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
                                for node in group_nodes
                                if _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
                            }
                        ),
                        "payout_currencies": sorted(
                            {
                                _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
                                for node in group_nodes
                                if _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
                            }
                        ),
                        "notes": group_notes,
                        "timing": timing_metadata,
                        "timing_mismatch_reasons": list(timing_notes),
                    },
                )
            )
        return groups

    @staticmethod
    def _market_currency(market: MarketDescriptor) -> str | None:
        return _metadata_string(market, "currency", "collateral_currency", "quote_currency")

    @staticmethod
    def _market_payout_currency(market: MarketDescriptor) -> str | None:
        return _metadata_string(market, "payout_currency", "currency", "collateral_currency", "quote_currency")

    @staticmethod
    def _market_timezone_hint(market: MarketDescriptor) -> str | None:
        return _first_non_empty(
            market.metadata.get("timezone"),
            market.metadata.get("time_zone"),
            market.metadata.get("tz"),
            market.metadata.get("market_timezone"),
            market.metadata.get("listing_timezone"),
            market.raw.get("timezone"),
            market.raw.get("time_zone"),
            market.raw.get("tz"),
            market.raw.get("market_timezone"),
            market.raw.get("listing_timezone"),
        )

    @staticmethod
    def _relation_kind_for_group(nodes: list[MarketGraphNode]) -> GraphRelationKind:
        if len(nodes) <= 1:
            return GraphRelationKind.same_topic
        canonical_ids = {node.canonical_event_id for node in nodes if node.canonical_event_id}
        if len(canonical_ids) == 1 and len(canonical_ids) == len([node for node in nodes if node.canonical_event_id]):
            return GraphRelationKind.same_event
        question_keys = {MarketGraphBuilder._question_key(node.question) for node in nodes}
        if len(question_keys) == 1:
            return GraphRelationKind.same_question
        return GraphRelationKind.same_topic

    @staticmethod
    def _group_compatible_resolution(nodes: list[MarketGraphNode]) -> bool:
        if len(nodes) <= 1:
            return False
        sources = {str(node.metadata.get("resolution_source") or "").strip().lower() for node in nodes}
        sources.discard("")
        return len(sources) == 1

    @staticmethod
    def _group_manual_review_required(
        nodes: list[MarketGraphNode],
        matches: list[CrossVenueMatch],
        *,
        timing_notes: list[str] | None = None,
    ) -> bool:
        if any(match.manual_review_required for match in matches):
            return True
        if len(nodes) <= 1:
            return False
        if timing_notes is None:
            timing_notes, _ = MarketGraphBuilder._group_timing_profile(nodes)
        return not MarketGraphBuilder._group_compatible_resolution(nodes) or bool(timing_notes)

    @staticmethod
    def _group_parent_child_pairs(nodes: list[MarketGraphNode]) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []
        for left, right in combinations(nodes, 2):
            relation = MarketGraphBuilder._parent_child_relation(left, right)
            if relation is not None:
                pairs.append(relation)
        return sorted(
            pairs,
            key=lambda item: (
                item["parent_market_id"],
                item["child_market_id"],
                item["specificity_gap"],
            ),
        )

    @staticmethod
    def _parent_child_relations(nodes: list[MarketGraphNode]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        pairs = MarketGraphBuilder._group_parent_child_pairs(nodes)
        parent_market_ids = sorted({pair["parent_market_id"] for pair in pairs})
        child_market_ids = sorted({pair["child_market_id"] for pair in pairs})
        return parent_market_ids, child_market_ids, pairs

    @staticmethod
    def _parent_child_relation(left: MarketGraphNode, right: MarketGraphNode) -> dict[str, Any] | None:
        left_tokens = MarketGraphBuilder._question_tokens(left.question or left.title)
        right_tokens = MarketGraphBuilder._question_tokens(right.question or right.title)
        if not left_tokens or not right_tokens or left_tokens == right_tokens:
            return None
        if left_tokens < right_tokens:
            parent, child = left, right
            parent_tokens, child_tokens = left_tokens, right_tokens
        elif right_tokens < left_tokens:
            parent, child = right, left
            parent_tokens, child_tokens = right_tokens, left_tokens
        else:
            return None
        shared_tokens = sorted(parent_tokens & child_tokens)
        if not shared_tokens:
            return None
        parent_score = MarketGraphBuilder._question_specificity_score(parent.question or parent.title, parent)
        child_score = MarketGraphBuilder._question_specificity_score(child.question or child.title, child)
        return {
            "parent_market_id": parent.market_id,
            "child_market_id": child.market_id,
            "shared_tokens": shared_tokens,
            "specificity_gap": round(child_score - parent_score, 6),
        }

    @staticmethod
    def _group_natural_hedge_pairs(nodes: list[MarketGraphNode]) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []
        for left, right in combinations(nodes, 2):
            relation = MarketGraphBuilder._natural_hedge_relation(left, right)
            if relation is not None:
                pairs.append(relation)
        return sorted(
            pairs,
            key=lambda item: (
                item["left_market_id"],
                item["right_market_id"],
                item["hedge_kind"],
            ),
        )

    @staticmethod
    def _natural_hedge_relations(nodes: list[MarketGraphNode]) -> tuple[list[str], list[dict[str, Any]]]:
        pairs = MarketGraphBuilder._group_natural_hedge_pairs(nodes)
        market_ids = sorted({pair["left_market_id"] for pair in pairs} | {pair["right_market_id"] for pair in pairs})
        return market_ids, pairs

    @staticmethod
    def _natural_hedge_relation(left: MarketGraphNode, right: MarketGraphNode) -> dict[str, Any] | None:
        shared_tokens = sorted(
            MarketGraphBuilder._question_tokens(left.question or left.title)
            & MarketGraphBuilder._question_tokens(right.question or right.title)
        )
        if len(shared_tokens) < 2:
            return None
        left_profile = MarketGraphBuilder._hedge_profile(left.question or left.title)
        right_profile = MarketGraphBuilder._hedge_profile(right.question or right.title)
        hedge_kind = MarketGraphBuilder._hedge_kind(left_profile["kind"], right_profile["kind"])
        if hedge_kind is None:
            return None
        return {
            "left_market_id": left.market_id,
            "right_market_id": right.market_id,
            "hedge_kind": hedge_kind,
            "shared_tokens": shared_tokens,
            "left_signal": left_profile["kind"],
            "right_signal": right_profile["kind"],
        }

    @staticmethod
    def _hedge_kind(left_kind: str, right_kind: str) -> str | None:
        kinds = {left_kind, right_kind}
        if kinds == {"neutral"}:
            return None
        if kinds == {"upside", "downside"}:
            return "complementary"
        if kinds == {"neutral", "negated"}:
            return "inverse"
        if "negated" in kinds and kinds != {"negated"}:
            return "inverse"
        return None

    @staticmethod
    def _hedge_profile(question: str) -> dict[str, Any]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in question)
        tokens = [token for token in cleaned.split() if token]
        negation_markers = {
            "not",
            "no",
            "never",
            "without",
            "fail",
            "fails",
            "failed",
            "failing",
            "miss",
            "misses",
            "missed",
        }
        downside_markers = {
            "drop",
            "drops",
            "dropped",
            "decline",
            "declines",
            "declined",
            "fall",
            "falls",
            "fell",
            "down",
            "decrease",
            "decreases",
            "decreased",
            "lower",
            "lowers",
            "lowered",
            "under",
            "below",
            "lose",
            "loses",
            "lost",
            "reject",
            "rejects",
            "reduce",
            "reduces",
            "reduced",
            "less",
        }
        positive_markers = {
            "above",
            "over",
            "greater",
            "more",
            "increase",
            "increases",
            "increased",
            "rise",
            "rises",
            "risen",
            "up",
            "higher",
            "gain",
            "gains",
            "gained",
            "win",
            "wins",
            "won",
            "approve",
            "approves",
            "approved",
            "pass",
            "passes",
            "passed",
            "launch",
            "launches",
            "launched",
            "adopt",
            "adopts",
            "adopted",
            "exceed",
            "exceeds",
            "exceeded",
        }
        has_negation = any(token in negation_markers for token in tokens)
        has_downside = any(token in downside_markers for token in tokens)
        has_positive = any(token in positive_markers for token in tokens)
        if has_negation and (has_positive or has_downside):
            kind = "mixed"
        elif has_negation:
            kind = "negated"
        elif has_positive and has_downside:
            kind = "mixed"
        elif has_positive:
            kind = "upside"
        elif has_downside:
            kind = "downside"
        else:
            kind = "neutral"
        return {
            "kind": kind,
            "tokens": tokens,
        }

    @staticmethod
    def _question_specificity_score(question: str, node: MarketGraphNode | None = None) -> float:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in question)
        tokens = cleaned.split()
        content_tokens = MarketGraphBuilder._question_tokens(question)
        temporal_markers = {
            "q1",
            "q2",
            "q3",
            "q4",
            "week",
            "month",
            "quarter",
            "year",
            "annual",
            "annually",
            "december",
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "2024",
            "2025",
            "2026",
            "2027",
            "2028",
            "2029",
            "2030",
        }
        temporal_score = sum(1 for token in tokens if token in temporal_markers or any(ch.isdigit() for ch in token))
        tag_count = 0
        if node is not None:
            tag_count = len(node.metadata.get("tags", [])) + len(node.metadata.get("categories", []))
        return round(len(content_tokens) + 0.2 * temporal_score + 0.1 * tag_count, 6)

    @staticmethod
    def _group_narrative_risk_flags(
        nodes: list[MarketGraphNode],
        compatible_resolution: bool,
        manual_review_required: bool,
        timing_notes: list[str],
    ) -> list[str]:
        flags: list[str] = []
        if manual_review_required:
            flags.append("manual_review_required")
        if not compatible_resolution and len(nodes) > 1:
            flags.append("resolution_mismatch")
        if timing_notes:
            flags.extend(timing_notes)
        if len(nodes) > 1 and all(node.role != "reference" for node in nodes):
            flags.append("no_reference_market")
        if len(nodes) > 1 and any(node.canonical_event_id is None for node in nodes):
            flags.append("canonical_event_missing")
        return flags

    @staticmethod
    def _match_notes(left: MarketGraphNode, right: MarketGraphNode, *, timing_notes: list[str] | None = None) -> list[str]:
        notes: list[str] = []
        if left.question != right.question:
            notes.append("question_normalized")
        if not MarketGraphBuilder._compatible_resolution(left, right):
            notes.append("resolution_mismatch")
        if not MarketGraphBuilder._compatible_currency(left, right):
            notes.append("currency_mismatch")
        if not MarketGraphBuilder._compatible_payout(left, right):
            notes.append("payout_currency_mismatch")
        if left.canonical_event_id != right.canonical_event_id:
            notes.append("canonical_event_inferred")
        if timing_notes:
            notes.extend(timing_notes)
        return list(dict.fromkeys(notes))

    @staticmethod
    def _alignment_gap_count(notes: list[str] | None) -> int:
        return len(MarketGraphBuilder._alignment_dimensions_from_notes(notes))

    @staticmethod
    def _alignment_dimensions_from_notes(notes: list[str] | None) -> list[str]:
        tokens = set(notes or [])
        dimensions: list[str] = []
        if any(token in {"resolution_mismatch", "resolution_source_mismatch"} for token in tokens):
            dimensions.append("resolution")
        if "currency_mismatch" in tokens:
            dimensions.append("currency")
        if "payout_currency_mismatch" in tokens:
            dimensions.append("payout")
        if any(token.startswith(("timebox_", "cutoff_", "timezone_")) for token in tokens):
            dimensions.append("timing")
        return dimensions

    @classmethod
    def _match_alignment_gap_count(cls, match: CrossVenueMatch) -> int:
        return len(cls._match_alignment_dimensions(match))

    @classmethod
    def _match_alignment_dimensions(cls, match: CrossVenueMatch) -> list[str]:
        notes = set(match.notes or [])
        dimensions: list[str] = []
        if match.left_resolution_source and match.right_resolution_source and not match.compatible_resolution:
            dimensions.append("resolution")
        if match.left_currency and match.right_currency and match.left_currency != match.right_currency:
            dimensions.append("currency")
        if (
                match.left_payout_currency
                and match.right_payout_currency
                and match.left_payout_currency != match.right_payout_currency
            ):
            dimensions.append("payout")
        if any(token.startswith(("timebox_", "cutoff_", "timezone_")) for token in notes):
            dimensions.append("timing")
        return dimensions

    @staticmethod
    def _comparable_group_id(left: MarketGraphNode, right: MarketGraphNode) -> str | None:
        return (
            left.metadata.get("comparable_group_id")
            or right.metadata.get("comparable_group_id")
            or left.canonical_event_id
            or right.canonical_event_id
        )

    @staticmethod
    def _compatible_currency(left: MarketGraphNode, right: MarketGraphNode) -> bool:
        left_currency = _normalized_text(left.metadata.get("currency") or left.metadata.get("collateral_currency") or "")
        right_currency = _normalized_text(right.metadata.get("currency") or right.metadata.get("collateral_currency") or "")
        return bool(left_currency and right_currency and left_currency == right_currency)

    @staticmethod
    def _compatible_payout(left: MarketGraphNode, right: MarketGraphNode) -> bool:
        left_currency = _normalized_text(left.metadata.get("payout_currency") or left.metadata.get("currency") or "")
        right_currency = _normalized_text(right.metadata.get("payout_currency") or right.metadata.get("currency") or "")
        return bool(left_currency and right_currency and left_currency == right_currency)

    @staticmethod
    def _group_notes(
        nodes: list[MarketGraphNode],
        compatible_resolution: bool,
        manual_review_required: bool,
        *,
        timing_notes: list[str] | None = None,
    ) -> list[str]:
        notes: list[str] = []
        if manual_review_required:
            notes.append("manual_review_required")
        if not compatible_resolution and len(nodes) > 1:
            notes.append("resolution_source_mismatch")
        currencies = {
            _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
            for node in nodes
            if _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
        }
        payout_currencies = {
            _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
            for node in nodes
            if _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
        }
        if len(currencies) > 1:
            notes.append("currency_mismatch")
        if len(payout_currencies) > 1:
            notes.append("payout_currency_mismatch")
        if timing_notes:
            notes.extend(timing_notes)
        return notes

    @staticmethod
    def _group_timing_profile(nodes: list[MarketGraphNode]) -> tuple[list[str], dict[str, Any]]:
        profiles = [MarketGraphBuilder._timing_context(node) for node in nodes]
        timing_notes: list[str] = []
        timing_metadata: dict[str, Any] = {}
        for key, note in (
            ("timebox_start", "timebox_mismatch"),
            ("timebox_end", "timebox_mismatch"),
            ("cutoff_at", "cutoff_mismatch"),
            ("timezone", "timezone_mismatch"),
        ):
            values = MarketGraphBuilder._profile_values(profiles, key)
            timing_metadata[f"{key}_values"] = values
            present_values = [value for value in values if value is not None]
            if len(present_values) > 1:
                timing_notes.append(note)
            elif present_values and len(present_values) != len(profiles):
                timing_notes.append(f"{note.split('_')[0]}_missing")
            elif not present_values and len(profiles) > 1:
                timing_metadata[f"{key}_missing"] = True
        return list(dict.fromkeys(timing_notes)), timing_metadata

    @staticmethod
    def _timing_context(source: Any) -> dict[str, str | None]:
        metadata = getattr(source, "metadata", {}) or {}
        raw = getattr(source, "raw", {}) or {}

        def _extract(names: tuple[str, ...]) -> Any:
            for name in names:
                value = getattr(source, name, None)
                if value not in (None, ""):
                    return value
                if isinstance(metadata, dict):
                    value = metadata.get(name)
                    if value not in (None, ""):
                        return value
                if isinstance(raw, dict):
                    value = raw.get(name)
                    if value not in (None, ""):
                        return value
            return None

        def _stringify(value: Any) -> str | None:
            if value is None or value == "":
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            text = _normalized_text(value)
            return text or None

        open_time = _stringify(_extract(("open_time", "openTime", "startDate", "start_time", "timebox_start")))
        close_time = _stringify(_extract(("close_time", "end_date", "endDate", "end_time", "timebox_end")))
        cutoff_at = _stringify(_extract(("resolution_date", "cutoff_at", "cutoff", "resolutionDate")))
        if cutoff_at is None:
            cutoff_at = close_time
        timezone_hint = _stringify(_extract(("timezone", "time_zone", "tz", "market_timezone", "listing_timezone", "timebox_timezone")))
        return {
            "timebox_start": open_time,
            "timebox_end": close_time,
            "cutoff_at": cutoff_at,
            "timezone": timezone_hint,
        }

    @staticmethod
    def _unique_profile_values(profiles: list[dict[str, str | None]], key: str) -> list[str]:
        values = [profile.get(key) for profile in profiles if profile.get(key)]
        return sorted(dict.fromkeys(str(value) for value in values))

    @staticmethod
    def _profile_values(profiles: list[dict[str, str | None]], key: str) -> list[str | None]:
        return sorted(
            dict.fromkeys(profile.get(key) for profile in profiles),
            key=lambda value: "" if value is None else str(value),
        )

    @classmethod
    def _timing_compatibility(cls, left: Any, right: Any) -> tuple[float, list[str], dict[str, Any]]:
        left_context = cls._timing_context(left)
        right_context = cls._timing_context(right)
        notes: list[str] = []
        scores: list[float] = []

        def _score_dimension(key: str, note_prefix: str) -> None:
            left_value = left_context.get(key)
            right_value = right_context.get(key)
            if left_value and right_value:
                if left_value == right_value:
                    scores.append(1.0)
                    return
                scores.append(0.0)
                notes.append(f"{note_prefix}_mismatch")
                return
            if left_value is None and right_value is None:
                scores.append(1.0)
                return
            scores.append(0.5)
            notes.append(f"{note_prefix}_missing")

        _score_dimension("timebox_start", "timebox")
        _score_dimension("timebox_end", "timebox")
        _score_dimension("cutoff_at", "cutoff")
        _score_dimension("timezone", "timezone")
        score = round(sum(scores) / max(1, len(scores)), 6)
        metadata = {
            "left": left_context,
            "right": right_context,
            "scores": {
                "timebox_start": scores[0] if len(scores) > 0 else 0.0,
                "timebox_end": scores[1] if len(scores) > 1 else 0.0,
                "cutoff": scores[2] if len(scores) > 2 else 0.0,
                "timezone": scores[3] if len(scores) > 3 else 0.0,
            },
        }
        return score, list(dict.fromkeys(notes)), metadata

    @staticmethod
    def _group_compatible_currency(nodes: list[MarketGraphNode]) -> bool:
        currencies = {
            _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
            for node in nodes
            if _normalized_text(node.metadata.get("currency") or node.metadata.get("collateral_currency") or "")
        }
        return len(currencies) <= 1

    @staticmethod
    def _group_compatible_payout(nodes: list[MarketGraphNode]) -> bool:
        payout_currencies = {
            _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
            for node in nodes
            if _normalized_text(node.metadata.get("payout_currency") or node.metadata.get("currency") or "")
        }
        return len(payout_currencies) <= 1

    @staticmethod
    def _group_rationale(
        nodes: list[MarketGraphNode],
        relation_kind: GraphRelationKind,
        compatible_resolution: bool,
        manual_review_required: bool,
        *,
        parent_child_pairs: list[dict[str, Any]] | None = None,
        natural_hedge_pairs: list[dict[str, Any]] | None = None,
        timing_notes: list[str] | None = None,
    ) -> str:
        venue_bits = ", ".join(sorted({node.venue.value for node in nodes}))
        parts = [
            f"relation={relation_kind.value}",
            f"venues=[{venue_bits}]",
            "compatible_resolution=yes" if compatible_resolution else "compatible_resolution=no",
        ]
        if parent_child_pairs:
            parts.append(f"parent_child_pairs={len(parent_child_pairs)}")
        if natural_hedge_pairs:
            parts.append(f"natural_hedge_pairs={len(natural_hedge_pairs)}")
        if manual_review_required:
            parts.append("manual_review_required=yes")
        if timing_notes:
            parts.append("timing=" + ",".join(timing_notes))
        return "; ".join(parts)

    def _select_references(
        self,
        nodes: list[MarketGraphNode],
        snapshots: dict[str, MarketSnapshot],
    ) -> dict[str, int]:
        buckets: dict[str, list[MarketGraphNode]] = {}
        for node in nodes:
            key = node.canonical_event_id or self._question_key(node.question)
            buckets.setdefault(key, []).append(node)
        reference_map: dict[str, int] = {}
        for group in buckets.values():
            ranked = sorted(group, key=lambda node: self._reference_score(node, snapshots.get(node.market_id)), reverse=True)
            if ranked:
                reference_map[ranked[0].market_id] = 1
                for index, node in enumerate(ranked[1:], start=2):
                    reference_map.setdefault(node.market_id, index)
        return reference_map

    @staticmethod
    def _reference_score(node: MarketGraphNode, snapshot: MarketSnapshot | None) -> float:
        score = node.clarity_score
        if node.venue_type == VenueType.reference:
            score += 0.35
        if node.venue_type == VenueType.execution:
            score += 0.15
        if node.liquidity:
            score += min(0.25, node.liquidity / 100000.0)
        if snapshot and snapshot.orderbook and snapshot.orderbook.spread_bps is not None:
            score += max(0.0, 0.1 - min(0.1, snapshot.orderbook.spread_bps / 10000.0))
        return score

    def _score_pair(self, left: MarketGraphNode, right: MarketGraphNode) -> tuple[float, str]:
        if left.canonical_event_id and right.canonical_event_id and left.canonical_event_id == right.canonical_event_id:
            return 1.0, f"Shared canonical_event_id={left.canonical_event_id}"

        left_tokens = self._pair_tokens(left)
        right_tokens = self._pair_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0, "Insufficient question overlap"

        intersection = left_tokens & right_tokens
        union = left_tokens | right_tokens
        jaccard = len(intersection) / max(1, len(union))
        venue_bonus = 0.08 if left.venue != right.venue else 0.0
        topic_bonus = 0.06 if self._same_topic(left, right) else 0.0
        resolution_bonus = 0.08 if self._compatible_resolution(left, right) else 0.0
        clarity_bonus = min(0.1, (left.clarity_score + right.clarity_score) / 20.0)
        similarity = min(1.0, jaccard + venue_bonus + topic_bonus + resolution_bonus + clarity_bonus)
        rationale = (
            f"question_jaccard={jaccard:.3f}, venue_bonus={venue_bonus:.2f}, "
            f"topic_bonus={topic_bonus:.2f}, overlap_tokens={len(intersection)}"
        )
        return similarity, rationale

    @staticmethod
    def _relation_kind(left: MarketGraphNode, right: MarketGraphNode, similarity: float) -> GraphRelationKind:
        if left.canonical_event_id and right.canonical_event_id and left.canonical_event_id == right.canonical_event_id:
            return GraphRelationKind.same_event
        if similarity >= 0.8:
            return GraphRelationKind.same_question
        return GraphRelationKind.same_topic

    @staticmethod
    def _compatible_resolution(left: MarketGraphNode, right: MarketGraphNode) -> bool:
        left_source = left.metadata.get("resolution_source")
        right_source = right.metadata.get("resolution_source")
        if left_source and right_source:
            return str(left_source).strip().lower() == str(right_source).strip().lower()
        return False

    @staticmethod
    def _pair_tokens(node: MarketGraphNode) -> set[str]:
        tokens = set(MarketGraphBuilder._question_tokens(node.question))
        if len(tokens) < 2:
            tokens |= MarketGraphBuilder._question_tokens(node.title)
        return tokens

    def _rejection_reasons(self, left: MarketGraphNode, right: MarketGraphNode, similarity: float) -> list[str]:
        reasons: list[str] = []
        if left.venue == right.venue:
            reasons.append("same_venue")
        if left.canonical_event_id and right.canonical_event_id and left.canonical_event_id != right.canonical_event_id:
            reasons.append("canonical_event_mismatch")
        left_tokens = self._pair_tokens(left)
        right_tokens = self._pair_tokens(right)
        overlap = left_tokens & right_tokens
        if not overlap:
            reasons.append("insufficient_question_overlap")
        elif len(overlap) == 1 and max(len(left_tokens), len(right_tokens)) >= 6:
            reasons.append("sparse_anchor_overlap")
        timing_reasons = self._timing_rejection_reasons(left, right, similarity)
        if timing_reasons:
            reasons.extend(timing_reasons)
        if similarity < self.relation_threshold:
            reasons.append(f"similarity_below_threshold:{similarity:.3f}")
        if (
            not left.canonical_event_id
            and not right.canonical_event_id
            and not self._same_topic(left, right)
            and len(overlap) < 2
        ):
            reasons.append("topic_mismatch")
        return list(dict.fromkeys(reasons))

    def _timing_rejection_reasons(self, left: MarketGraphNode, right: MarketGraphNode, similarity: float) -> list[str]:
        left_context = self._timing_context(left)
        right_context = self._timing_context(right)
        reasons: list[str] = []
        mismatch_count = 0
        for key, reason in (
            ("timebox_start", "timebox_mismatch"),
            ("timebox_end", "timebox_mismatch"),
            ("cutoff_at", "cutoff_mismatch"),
            ("timezone", "timezone_mismatch"),
        ):
            left_value = left_context.get(key)
            right_value = right_context.get(key)
            if left_value and right_value and left_value != right_value:
                mismatch_count += 1
                reasons.append(reason)
        if (
            mismatch_count
            and not (left.canonical_event_id and right.canonical_event_id and left.canonical_event_id == right.canonical_event_id)
            and similarity < max(self.relation_threshold + 0.15, 0.75)
        ):
            reasons.append("timing_mismatch")
            return list(dict.fromkeys(reasons))
        return []

    @staticmethod
    def _same_topic(left: MarketGraphNode, right: MarketGraphNode) -> bool:
        left_topics = set(left.metadata.get("tags", [])) | set(left.metadata.get("categories", []))
        right_topics = set(right.metadata.get("tags", [])) | set(right.metadata.get("categories", []))
        return bool(left_topics & right_topics)

    @staticmethod
    def _question_key(*questions: str) -> str:
        tokens: set[str] = set()
        for question in questions:
            tokens |= MarketGraphBuilder._question_tokens(question)
        return " ".join(sorted(tokens))

    @staticmethod
    def _canonical_question(*questions: str) -> str:
        tokens: list[str] = []
        for question in questions:
            tokens.extend(sorted(MarketGraphBuilder._question_tokens(question)))
        return "q_" + "_".join(tokens[:8]) if tokens else "q_unknown"

    @staticmethod
    def _question_tokens(question: str) -> set[str]:
        stopwords = {
            "will",
            "the",
            "a",
            "an",
            "by",
            "in",
            "on",
            "of",
            "for",
            "to",
            "be",
            "is",
            "are",
            "does",
            "do",
            "did",
            "this",
            "that",
            "it",
            "happen",
            "happens",
            "occur",
            "occur?",
            "market",
            "above",
            "below",
            "than",
        }
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in question)
        tokens = {token for token in cleaned.split() if token and token not in stopwords}
        return tokens
