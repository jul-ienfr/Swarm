from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .cluster_diagnostics import ClusterDiagnostic, ClusterDiagnosticsReport
from .graph_analytics import GraphAnalyticsReport, GraphClusterSummary, GraphNodeScore
from .graph_store import GraphEdge, GraphNode, GraphSnapshot, GraphStore


class DeliberationVisualArtifactKind(str):
    ascii = "ascii"
    mermaid = "mermaid"
    table = "table"
    json = "json"


class DeliberationVisualArtifact(BaseModel):
    artifact_id: str
    kind: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliberationVisualBundle(BaseModel):
    graph_id: str
    title: str = ""
    artifacts: list[DeliberationVisualArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_deliberation_visuals(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    *,
    analytics: GraphAnalyticsReport | None = None,
    diagnostics: ClusterDiagnosticsReport | None = None,
    max_nodes: int = 25,
    max_edges: int = 40,
) -> DeliberationVisualBundle:
    snapshot = _coerce_snapshot(graph)
    analytics = analytics or GraphAnalyticsReport(
        graph_id=snapshot.graph_id,
        name=snapshot.name,
        description=snapshot.description,
    )
    diagnostics = diagnostics or ClusterDiagnosticsReport(graph_id=snapshot.graph_id)
    artifacts = [
        DeliberationVisualArtifact(
            artifact_id=f"visual_ascii_{snapshot.graph_id}",
            kind=DeliberationVisualArtifactKind.ascii,
            title="graph_ascii_summary",
            content=render_graph_ascii(snapshot, analytics=analytics, diagnostics=diagnostics, max_nodes=max_nodes),
        ),
        DeliberationVisualArtifact(
            artifact_id=f"visual_mermaid_{snapshot.graph_id}",
            kind=DeliberationVisualArtifactKind.mermaid,
            title="graph_mermaid",
            content=render_graph_mermaid(snapshot, max_nodes=max_nodes, max_edges=max_edges),
        ),
        DeliberationVisualArtifact(
            artifact_id=f"visual_table_{snapshot.graph_id}",
            kind=DeliberationVisualArtifactKind.table,
            title="cluster_table",
            content=render_cluster_table(diagnostics),
        ),
    ]
    return DeliberationVisualBundle(
        graph_id=snapshot.graph_id,
        title=snapshot.name or "deliberation_visuals",
        artifacts=artifacts,
        metadata={
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
            "cluster_count": diagnostics.cluster_count,
        },
    )


def render_graph_ascii(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    *,
    analytics: GraphAnalyticsReport | None = None,
    diagnostics: ClusterDiagnosticsReport | None = None,
    max_nodes: int = 25,
) -> str:
    snapshot = _coerce_snapshot(graph)
    analytics = analytics or GraphAnalyticsReport(graph_id=snapshot.graph_id)
    diagnostics = diagnostics or ClusterDiagnosticsReport(graph_id=snapshot.graph_id)
    lines: list[str] = [
        f"DELIVERATION GRAPH: {snapshot.name} ({snapshot.graph_id})",
        f"nodes={len(snapshot.nodes)} edges={len(snapshot.edges)} density={analytics.density:.3f}",
        f"clusters={diagnostics.cluster_count} orphan_nodes={diagnostics.orphan_node_count}",
        "",
        "TOP NODES",
    ]
    for score in analytics.top_nodes[:max_nodes]:
        lines.append(_format_node_score(score))
    if diagnostics.diagnostics:
        lines.extend(["", "CLUSTERS"])
        for diagnostic in diagnostics.diagnostics[:max_nodes]:
            lines.append(_format_cluster_diagnostic(diagnostic))
    return "\n".join(lines)


def render_graph_mermaid(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    *,
    max_nodes: int = 25,
    max_edges: int = 40,
) -> str:
    snapshot = _coerce_snapshot(graph)
    nodes = snapshot.nodes[:max_nodes]
    allowed_ids = {node.node_id for node in nodes}
    edges = [edge for edge in snapshot.edges if edge.source in allowed_ids and edge.target in allowed_ids][:max_edges]
    lines = ["graph TD"]
    for node in nodes:
        lines.append(f'    {_safe_mermaid_id(node.node_id)}["{_escape_mermaid(node.label)}"]')
    for edge in edges:
        lines.append(
            f"    {_safe_mermaid_id(edge.source)} -->|{_escape_mermaid(edge.relation)}| {_safe_mermaid_id(edge.target)}"
        )
    return "\n".join(lines)


def render_cluster_table(diagnostics: ClusterDiagnosticsReport) -> str:
    lines = [
        "cluster_id | nodes | edges | dominant_type | dominant_stance | conf | trust | dissent | bridge",
        "--- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---:",
    ]
    for cluster in diagnostics.diagnostics:
        lines.append(
            f"{cluster.cluster_id} | {cluster.node_count} | {cluster.edge_count} | "
            f"{cluster.dominant_node_type or '-'} | {cluster.dominant_stance or '-'} | "
            f"{cluster.average_confidence:.2f} | {cluster.average_trust:.2f} | {cluster.dissent_ratio:.2f} | {cluster.bridge_score:.2f}"
        )
    if len(lines) == 2:
        lines.append("no_clusters | 0 | 0 | - | - | 0.00 | 0.00 | 0.00 | 0.00")
    return "\n".join(lines)


def build_visual_preview(
    graph: GraphStore | GraphSnapshot | dict[str, Any],
    *,
    analytics: GraphAnalyticsReport | None = None,
    diagnostics: ClusterDiagnosticsReport | None = None,
) -> dict[str, Any]:
    snapshot = _coerce_snapshot(graph)
    analytics = analytics or GraphAnalyticsReport(graph_id=snapshot.graph_id)
    diagnostics = diagnostics or ClusterDiagnosticsReport(graph_id=snapshot.graph_id)
    return {
        "graph_id": snapshot.graph_id,
        "graph_name": snapshot.name,
        "ascii": render_graph_ascii(snapshot, analytics=analytics, diagnostics=diagnostics),
        "mermaid": render_graph_mermaid(snapshot),
        "cluster_table": render_cluster_table(diagnostics),
        "summary": {
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
            "cluster_count": diagnostics.cluster_count,
            "top_node_ids": [score.node_id for score in analytics.top_nodes[:5]],
        },
    }


def _coerce_snapshot(graph: GraphStore | GraphSnapshot | dict[str, Any]) -> GraphSnapshot:
    if isinstance(graph, GraphStore):
        return graph.snapshot
    if isinstance(graph, GraphSnapshot):
        return graph
    return GraphSnapshot.model_validate(graph)


def _format_node_score(score: GraphNodeScore) -> str:
    return (
        f"- {score.node_id} [{score.node_type}] degree={score.total_degree} "
        f"inf={score.influence_score:.3f} reach={score.reach_score:.3f}"
    )


def _format_cluster_diagnostic(diagnostic: ClusterDiagnostic) -> str:
    return (
        f"- {diagnostic.cluster_id}: nodes={diagnostic.node_count} "
        f"dissent={diagnostic.dissent_ratio:.2f} bridge={diagnostic.bridge_score:.2f} "
        f"dominant={diagnostic.dominant_stance or '-'}"
    )


def _safe_mermaid_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)
    if not cleaned:
        cleaned = "node"
    if cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _escape_mermaid(value: str) -> str:
    return str(value).replace('"', "'")

