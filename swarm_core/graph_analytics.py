from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .graph_store import GraphEdge, GraphNode, GraphSnapshot, GraphStore


class GraphNodeScore(BaseModel):
    node_id: str
    label: str
    node_type: str = "entity"
    in_degree: int = 0
    out_degree: int = 0
    total_degree: int = 0
    weighted_in_degree: float = 0.0
    weighted_out_degree: float = 0.0
    influence_score: float = 0.0
    reach_score: float = 0.0
    cluster_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphClusterSummary(BaseModel):
    cluster_id: str
    node_ids: list[str] = Field(default_factory=list)
    edge_count: int = 0
    density: float = 0.0
    dominant_node_type: str | None = None
    average_in_degree: float = 0.0
    average_out_degree: float = 0.0
    average_influence_score: float = 0.0
    bridge_score: float = 0.0
    top_nodes: list[GraphNodeScore] = Field(default_factory=list)


class GraphAnalyticsReport(BaseModel):
    graph_id: str
    name: str = ""
    description: str = ""
    node_count: int = 0
    edge_count: int = 0
    density: float = 0.0
    component_count: int = 0
    isolated_node_count: int = 0
    node_type_counts: dict[str, int] = Field(default_factory=dict)
    relation_counts: dict[str, int] = Field(default_factory=dict)
    top_nodes: list[GraphNodeScore] = Field(default_factory=list)
    clusters: list[GraphClusterSummary] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphAnalyticsEngine:
    """Pure-Python graph analytics for deliberation workbenches and run artifacts."""

    def analyze(
        self,
        graph: GraphStore | GraphSnapshot | dict[str, Any],
        *,
        generated_at: datetime | None = None,
    ) -> GraphAnalyticsReport:
        snapshot = _coerce_snapshot(graph)
        node_by_id = {node.node_id: node for node in snapshot.nodes}
        adjacency = _build_adjacency(snapshot.edges)
        reverse_adjacency = _build_reverse_adjacency(snapshot.edges)
        node_scores = _score_nodes(snapshot.nodes, snapshot.edges, adjacency, reverse_adjacency)
        components = _connected_components(snapshot.nodes, snapshot.edges)
        clusters = [
            _build_cluster_summary(
                cluster_id=f"cluster_{index + 1}",
                node_ids=component,
                node_by_id=node_by_id,
                edges=snapshot.edges,
                node_scores=node_scores,
            )
            for index, component in enumerate(components)
        ]
        node_type_counts = Counter(node.node_type for node in snapshot.nodes)
        relation_counts = Counter(edge.relation for edge in snapshot.edges)
        isolated = sum(1 for node in snapshot.nodes if not adjacency.get(node.node_id) and not reverse_adjacency.get(node.node_id))
        density = _density(len(snapshot.nodes), len(snapshot.edges))
        top_nodes = sorted(node_scores.values(), key=_node_sort_key, reverse=True)[:10]
        return GraphAnalyticsReport(
            graph_id=snapshot.graph_id,
            name=snapshot.name,
            description=snapshot.description,
            node_count=len(snapshot.nodes),
            edge_count=len(snapshot.edges),
            density=density,
            component_count=len(components),
            isolated_node_count=isolated,
            node_type_counts=dict(sorted(node_type_counts.items())),
            relation_counts=dict(sorted(relation_counts.items())),
            top_nodes=top_nodes,
            clusters=clusters,
            generated_at=generated_at or datetime.now(timezone.utc),
            metadata=dict(snapshot.metadata),
        )


def analyze_graph(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> GraphAnalyticsReport:
    return GraphAnalyticsEngine().analyze(graph, generated_at=generated_at)


def summarize_graph(graph: GraphStore | GraphSnapshot | dict[str, Any]) -> dict[str, Any]:
    report = analyze_graph(graph)
    return report.model_dump(mode="json")


def _coerce_snapshot(graph: GraphStore | GraphSnapshot | dict[str, Any]) -> GraphSnapshot:
    if isinstance(graph, GraphStore):
        return graph.snapshot
    if isinstance(graph, GraphSnapshot):
        return graph
    return GraphSnapshot.model_validate(graph)


def _build_adjacency(edges: Iterable[GraphEdge]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
    return adjacency


def _build_reverse_adjacency(edges: Iterable[GraphEdge]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        reverse[edge.target].add(edge.source)
    return reverse


def _score_nodes(
    nodes: Iterable[GraphNode],
    edges: Iterable[GraphEdge],
    adjacency: dict[str, set[str]],
    reverse_adjacency: dict[str, set[str]],
) -> dict[str, GraphNodeScore]:
    edge_list = list(edges)
    node_scores: dict[str, GraphNodeScore] = {}
    total_edge_weight = sum(max(0.0, float(edge.weight)) for edge in edge_list) or 1.0
    outgoing_weight: dict[str, float] = defaultdict(float)
    incoming_weight: dict[str, float] = defaultdict(float)
    for edge in edge_list:
        outgoing_weight[edge.source] += max(0.0, float(edge.weight))
        incoming_weight[edge.target] += max(0.0, float(edge.weight))

    for node in nodes:
        out_degree = len(adjacency.get(node.node_id, set()))
        in_degree = len(reverse_adjacency.get(node.node_id, set()))
        total_degree = in_degree + out_degree
        weighted_out = outgoing_weight.get(node.node_id, 0.0)
        weighted_in = incoming_weight.get(node.node_id, 0.0)
        influence_score = (weighted_in + weighted_out + total_degree) / max(1.0, total_edge_weight)
        reach_score = (out_degree + weighted_out + 1.0) / (in_degree + 1.0)
        node_scores[node.node_id] = GraphNodeScore(
            node_id=node.node_id,
            label=node.label,
            node_type=node.node_type,
            in_degree=in_degree,
            out_degree=out_degree,
            total_degree=total_degree,
            weighted_in_degree=weighted_in,
            weighted_out_degree=weighted_out,
            influence_score=influence_score,
            reach_score=reach_score,
            metadata=dict(node.metadata),
        )
    return node_scores


def _connected_components(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        adjacency.setdefault(node.node_id, set())
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    remaining = set(adjacency)
    components: list[list[str]] = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current not in remaining and current != seed and current in component:
                continue
            if current in component:
                continue
            component.append(current)
            neighbors = adjacency.get(current, set())
            for neighbor in neighbors:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda component: (-len(component), component))


def _build_cluster_summary(
    *,
    cluster_id: str,
    node_ids: list[str],
    node_by_id: dict[str, GraphNode],
    edges: Iterable[GraphEdge],
    node_scores: dict[str, GraphNodeScore],
) -> GraphClusterSummary:
    node_id_set = set(node_ids)
    cluster_nodes = [node_by_id[node_id] for node_id in node_ids if node_id in node_by_id]
    cluster_scores = [node_scores[node_id] for node_id in node_ids if node_id in node_scores]
    cluster_edges = [edge for edge in edges if edge.source in node_id_set and edge.target in node_id_set]
    outgoing_cut = sum(1 for edge in edges if edge.source in node_id_set and edge.target not in node_id_set)
    incoming_cut = sum(1 for edge in edges if edge.target in node_id_set and edge.source not in node_id_set)
    edge_count = len(cluster_edges)
    possible_edges = max(1, len(cluster_nodes) * max(0, len(cluster_nodes) - 1))
    dominant_node_type = _dominant_value(node.node_type for node in cluster_nodes)
    average_in_degree = _mean(score.in_degree for score in cluster_scores)
    average_out_degree = _mean(score.out_degree for score in cluster_scores)
    average_influence_score = _mean(score.influence_score for score in cluster_scores)
    bridge_score = (outgoing_cut + incoming_cut) / max(1, len(cluster_nodes))
    top_nodes = sorted(cluster_scores, key=_node_sort_key, reverse=True)[:5]
    return GraphClusterSummary(
        cluster_id=cluster_id,
        node_ids=list(node_ids),
        edge_count=edge_count,
        density=edge_count / possible_edges,
        dominant_node_type=dominant_node_type,
        average_in_degree=average_in_degree,
        average_out_degree=average_out_degree,
        average_influence_score=average_influence_score,
        bridge_score=bridge_score,
        top_nodes=top_nodes,
    )


def _dominant_value(values: Iterable[str]) -> str | None:
    counter = Counter(value for value in values if value)
    if not counter:
        return None
    return max(counter, key=counter.get)


def _mean(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return sum(items) / len(items)


def _density(node_count: int, edge_count: int) -> float:
    if node_count <= 1:
        return 0.0
    return edge_count / float(node_count * (node_count - 1))


def _node_sort_key(score: GraphNodeScore) -> tuple[float, float, float, str]:
    return (score.influence_score, float(score.total_degree), score.weighted_out_degree + score.weighted_in_degree, score.label.lower())
