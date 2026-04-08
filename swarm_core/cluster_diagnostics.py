from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .belief_state import BeliefState, load_belief_states_from_graph, summarise_belief_group
from .graph_analytics import GraphAnalyticsEngine, GraphClusterSummary
from .graph_store import GraphSnapshot, GraphStore


class ClusterDiagnostic(BaseModel):
    cluster_id: str
    node_ids: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    dominant_node_type: str | None = None
    dominant_stance: str | None = None
    average_confidence: float = 0.0
    average_trust: float = 0.0
    dissent_ratio: float = 0.0
    bridge_score: float = 0.0
    density: float = 0.0
    top_labels: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterDiagnosticsReport(BaseModel):
    graph_id: str
    cluster_count: int = 0
    cross_cluster_edges: int = 0
    orphan_node_count: int = 0
    diagnostics: list[ClusterDiagnostic] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterDiagnosticsEngine:
    def __init__(self) -> None:
        self._graph_analytics = GraphAnalyticsEngine()

    def diagnose(
        self,
        graph: GraphStore | GraphSnapshot | dict[str, Any],
        beliefs: Iterable[BeliefState] | None = None,
        *,
        generated_at: datetime | None = None,
    ) -> ClusterDiagnosticsReport:
        snapshot = _coerce_snapshot(graph)
        analytics = self._graph_analytics.analyze(snapshot)
        belief_list = list(beliefs if beliefs is not None else load_belief_states_from_graph(_coerce_store(snapshot)))
        belief_by_id = {belief.agent_id: belief for belief in belief_list}
        groups = _group_beliefs(belief_list)
        cluster_diagnostics: list[ClusterDiagnostic] = []

        for cluster in analytics.clusters:
            cluster_beliefs = [belief_by_id[node_id] for node_id in cluster.node_ids if node_id in belief_by_id]
            summary = summarise_belief_group(cluster_beliefs, group_id=_dominant_group_id(cluster_beliefs, fallback=cluster.cluster_id))
            dominant_node_type = cluster.dominant_node_type
            dissent_ratio = _dissent_ratio(cluster_beliefs, summary.dominant_stance)
            top_labels = [node.label for node in cluster.top_nodes[:5]]
            notes = _build_notes(cluster, dissent_ratio, cluster_beliefs)
            cluster_diagnostics.append(
                ClusterDiagnostic(
                    cluster_id=cluster.cluster_id,
                    node_ids=list(cluster.node_ids),
                    node_count=len(cluster.node_ids),
                    edge_count=cluster.edge_count,
                    dominant_node_type=dominant_node_type,
                    dominant_stance=summary.dominant_stance,
                    average_confidence=summary.average_confidence,
                    average_trust=summary.average_trust,
                    dissent_ratio=dissent_ratio,
                    bridge_score=cluster.bridge_score,
                    density=cluster.density,
                    top_labels=top_labels,
                    notes=notes,
                    metadata={
                        "group_id": summary.group_id,
                        "memory_tokens": summary.memory_tokens,
                        "stance_counts": summary.stance_counts,
                    },
                )
            )

        cross_cluster_edges = _cross_cluster_edges(snapshot, cluster_diagnostics)
        orphan_node_count = analytics.isolated_node_count
        recommendations = _recommendations(cluster_diagnostics, cross_cluster_edges, orphan_node_count)
        return ClusterDiagnosticsReport(
            graph_id=snapshot.graph_id,
            cluster_count=len(cluster_diagnostics),
            cross_cluster_edges=cross_cluster_edges,
            orphan_node_count=orphan_node_count,
            diagnostics=cluster_diagnostics,
            recommendations=recommendations,
            generated_at=generated_at or datetime.now(timezone.utc),
            metadata={
                "node_type_counts": analytics.node_type_counts,
                "relation_counts": analytics.relation_counts,
                "group_count": len(groups),
            },
        )


def diagnose_clusters(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    beliefs: Iterable[BeliefState] | None = None,
    *,
    generated_at: datetime | None = None,
) -> ClusterDiagnosticsReport:
    return ClusterDiagnosticsEngine().diagnose(graph, beliefs, generated_at=generated_at)


def summarize_cluster_diagnostics(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    beliefs: Iterable[BeliefState] | None = None,
) -> dict[str, Any]:
    return diagnose_clusters(graph, beliefs).model_dump(mode="json")


def _coerce_snapshot(graph: GraphStore | GraphSnapshot | dict[str, Any]) -> GraphSnapshot:
    if isinstance(graph, GraphStore):
        return graph.snapshot
    if isinstance(graph, GraphSnapshot):
        return graph
    return GraphSnapshot.model_validate(graph)


def _coerce_store(snapshot: GraphSnapshot) -> GraphStore:
    store = GraphStore.__new__(GraphStore)
    store.path = None  # type: ignore[attr-defined]
    store.name = snapshot.name
    store.description = snapshot.description
    store.version = snapshot.version
    store._snapshot = snapshot  # type: ignore[attr-defined]
    return store


def _group_beliefs(beliefs: Iterable[BeliefState]) -> dict[str, list[BeliefState]]:
    grouped: dict[str, list[BeliefState]] = defaultdict(list)
    for belief in beliefs:
        key = belief.group_id or "ungrouped"
        grouped[key].append(belief)
    return grouped


def _dominant_group_id(beliefs: Iterable[BeliefState], *, fallback: str) -> str:
    beliefs = list(beliefs)
    if not beliefs:
        return fallback
    counts = Counter(belief.group_id or fallback for belief in beliefs)
    return max(counts, key=counts.get)


def _dissent_ratio(beliefs: Iterable[BeliefState], dominant_stance: str | None) -> float:
    beliefs = list(beliefs)
    if not beliefs:
        return 0.0
    if dominant_stance is None:
        return 0.0
    dissent = sum(1 for belief in beliefs if belief.stance != dominant_stance)
    return dissent / len(beliefs)


def _build_notes(cluster: GraphClusterSummary, dissent_ratio: float, beliefs: Iterable[BeliefState]) -> list[str]:
    notes: list[str] = []
    if cluster.bridge_score > 1.0:
        notes.append("high_bridge_activity")
    if dissent_ratio > 0.33:
        notes.append("strong_dissent")
    if cluster.average_influence_score < 0.25:
        notes.append("low_influence_cluster")
    if beliefs and not cluster.top_nodes:
        notes.append("no_top_nodes")
    return notes


def _cross_cluster_edges(snapshot: GraphSnapshot, diagnostics: Iterable[ClusterDiagnostic]) -> int:
    node_to_cluster: dict[str, str] = {}
    for diagnostic in diagnostics:
        for node_id in diagnostic.node_ids:
            node_to_cluster[node_id] = diagnostic.cluster_id
    return sum(
        1
        for edge in snapshot.edges
        if node_to_cluster.get(edge.source) != node_to_cluster.get(edge.target)
    )


def _recommendations(
    diagnostics: Iterable[ClusterDiagnostic],
    cross_cluster_edges: int,
    orphan_node_count: int,
) -> list[str]:
    diagnostics = list(diagnostics)
    recommendations: list[str] = []
    if orphan_node_count:
        recommendations.append("connect_orphan_nodes")
    if cross_cluster_edges:
        recommendations.append("trace_cross_cluster_flows")
    for diagnostic in diagnostics:
        if diagnostic.dissent_ratio > 0.33:
            recommendations.append(f"mediate_cluster:{diagnostic.cluster_id}")
        if diagnostic.average_confidence < 0.45:
            recommendations.append(f"raise_confidence:{diagnostic.cluster_id}")
        if diagnostic.bridge_score > 1.0:
            recommendations.append(f"inspect_bridges:{diagnostic.cluster_id}")
    if not recommendations:
        recommendations.append("cluster_state_stable")
    return _dedupe(recommendations)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
