from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .graph_analytics import GraphAnalyticsEngine, GraphAnalyticsReport
from .graph_store import GraphEdge, GraphNode, GraphSnapshot, GraphStore


class GraphBackendKind(str, Enum):
    local = "local"
    neo4j = "neo4j"


class GraphBackendStatus(str, Enum):
    ready = "ready"
    exported = "exported"
    query_bundle = "query_bundle"


class Neo4jCypherStatement(BaseModel):
    purpose: str
    cypher: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Neo4jQueryBundle(BaseModel):
    graph_id: str
    graph_name: str = ""
    node_count: int = 0
    edge_count: int = 0
    statements: list[Neo4jCypherStatement] = Field(default_factory=list)
    analysis_queries: list[Neo4jCypherStatement] = Field(default_factory=list)
    node_labels: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class GraphBackendExportResult(BaseModel):
    backend: GraphBackendKind = GraphBackendKind.local
    status: GraphBackendStatus = GraphBackendStatus.ready
    graph_id: str
    graph_name: str = ""
    node_count: int = 0
    edge_count: int = 0
    analytics: GraphAnalyticsReport | None = None
    query_bundle: Neo4jQueryBundle | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Neo4jConnectionConfig(BaseModel):
    uri: str
    username: str
    password: str
    database: str | None = None


class Neo4jExecutionResult(BaseModel):
    graph_id: str
    executed_statements: int = 0
    executed_analysis_queries: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)


class GraphBackendAdapter:
    """Bounded graph backend adapter that keeps the local GraphStore as source of truth."""

    def __init__(self, graph: GraphStore | GraphSnapshot | dict[str, Any]) -> None:
        self._snapshot = _coerce_snapshot(graph)
        self._analytics_engine = GraphAnalyticsEngine()

    @property
    def snapshot(self) -> GraphSnapshot:
        return self._snapshot

    def analytics(self) -> GraphAnalyticsReport:
        return self._analytics_engine.analyze(self._snapshot)

    def export(self) -> GraphBackendExportResult:
        analytics = self.analytics()
        return GraphBackendExportResult(
            backend=GraphBackendKind.local,
            status=GraphBackendStatus.exported,
            graph_id=self._snapshot.graph_id,
            graph_name=self._snapshot.name,
            node_count=len(self._snapshot.nodes),
            edge_count=len(self._snapshot.edges),
            analytics=analytics,
            metadata={
                "description": self._snapshot.description,
                "version": self._snapshot.version,
            },
        )

    def build_neo4j_query_bundle(self, *, limit: int | None = None) -> Neo4jQueryBundle:
        return build_neo4j_query_bundle(self._snapshot, limit=limit)


class Neo4jFriendlyGraphBackendAdapter(GraphBackendAdapter):
    def export(self) -> GraphBackendExportResult:
        bundle = self.build_neo4j_query_bundle()
        return GraphBackendExportResult(
            backend=GraphBackendKind.neo4j,
            status=GraphBackendStatus.query_bundle,
            graph_id=self._snapshot.graph_id,
            graph_name=self._snapshot.name,
            node_count=bundle.node_count,
            edge_count=bundle.edge_count,
            analytics=self.analytics(),
            query_bundle=bundle,
            metadata={
                "description": self._snapshot.description,
                "version": self._snapshot.version,
                "note": "cypher bundle only; no live neo4j dependency required",
            },
        )

    def execute_live(
        self,
        config: Neo4jConnectionConfig,
        *,
        include_analysis: bool = False,
        limit: int | None = None,
    ) -> Neo4jExecutionResult:
        bundle = self.build_neo4j_query_bundle(limit=limit)
        try:
            from neo4j import GraphDatabase
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("neo4j driver is not installed.") from exc

        auth = (config.username, config.password)
        driver = GraphDatabase.driver(config.uri, auth=auth)
        executed_statements = 0
        executed_analysis = 0
        try:
            with driver.session(database=config.database) as session:
                for statement in bundle.statements:
                    session.run(statement.cypher, statement.parameters)
                    executed_statements += 1
                if include_analysis:
                    for statement in bundle.analysis_queries:
                        list(session.run(statement.cypher, statement.parameters))
                        executed_analysis += 1
        finally:  # pragma: no branch
            driver.close()
        return Neo4jExecutionResult(
            graph_id=bundle.graph_id,
            executed_statements=executed_statements,
            executed_analysis_queries=executed_analysis,
            summary={
                "node_count": bundle.node_count,
                "edge_count": bundle.edge_count,
                "database": config.database,
                "uri": config.uri,
            },
        )


def build_neo4j_query_bundle(graph: GraphStore | GraphSnapshot | dict[str, Any], *, limit: int | None = None) -> Neo4jQueryBundle:
    snapshot = _coerce_snapshot(graph)
    nodes = list(snapshot.nodes)
    edges = list(snapshot.edges)
    if limit is not None and limit >= 0:
        nodes = nodes[:limit]
        node_ids = {node.node_id for node in nodes}
        edges = [edge for edge in edges if edge.source in node_ids and edge.target in node_ids]
    statements: list[Neo4jCypherStatement] = []
    node_labels = sorted({ _cypher_label(node.node_type) for node in nodes })
    relation_types = sorted({_cypher_label(edge.relation) for edge in edges})

    for node in nodes:
        statements.append(
            Neo4jCypherStatement(
                purpose="upsert_node",
                cypher=(
                    f"MERGE (n:{_cypher_label(node.node_type)} {{node_id: $node_id}}) "
                    f"SET n.label = $label, n.properties = $properties, n.metadata = $metadata, "
                    f"n.updated_at = datetime($updated_at), n.created_at = coalesce(n.created_at, datetime($created_at))"
                ),
                parameters={
                    "node_id": node.node_id,
                    "label": node.label,
                    "properties": _jsonable(node.properties),
                    "metadata": _jsonable(node.metadata),
                    "created_at": _datetime_to_iso(node.created_at),
                    "updated_at": _datetime_to_iso(node.updated_at),
                },
            )
        )

    for edge in edges:
        statements.append(
            Neo4jCypherStatement(
                purpose="upsert_edge",
                cypher=(
                    f"MATCH (source {{node_id: $source_id}}), (target {{node_id: $target_id}}) "
                    f"MERGE (source)-[r:{_cypher_label(edge.relation)} {{edge_id: $edge_id}}]->(target) "
                    f"SET r.weight = $weight, r.properties = $properties, r.metadata = $metadata, "
                    f"r.created_at = datetime($created_at)"
                ),
                parameters={
                    "edge_id": edge.edge_id,
                    "source_id": edge.source,
                    "target_id": edge.target,
                    "weight": edge.weight,
                    "properties": _jsonable(edge.properties),
                    "metadata": _jsonable(edge.metadata),
                    "created_at": _datetime_to_iso(edge.created_at),
                },
            )
        )

    summary = {
        "graph_id": snapshot.graph_id,
        "graph_name": snapshot.name,
        "description": snapshot.description,
        "node_types": sorted({node.node_type for node in nodes}),
        "relation_types": sorted({edge.relation for edge in edges}),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    analysis_queries = build_advanced_neo4j_queries(snapshot.graph_id)
    return Neo4jQueryBundle(
        graph_id=snapshot.graph_id,
        graph_name=snapshot.name,
        node_count=len(nodes),
        edge_count=len(edges),
        statements=statements,
        analysis_queries=analysis_queries,
        node_labels=node_labels,
        relationship_types=relation_types,
        summary=summary,
    )


def build_advanced_neo4j_queries(graph_id: str) -> list[Neo4jCypherStatement]:
    return [
        Neo4jCypherStatement(
            purpose="top_influencers",
            cypher=(
                "MATCH (n) "
                "RETURN n.node_id AS node_id, size((n)--()) AS degree "
                "ORDER BY degree DESC LIMIT 10"
            ),
            parameters={"graph_id": graph_id},
        ),
        Neo4jCypherStatement(
            purpose="bridge_candidates",
            cypher=(
                "MATCH (a)-[r]->(b) "
                "WHERE a.node_id <> b.node_id "
                "RETURN a.node_id AS source, b.node_id AS target, type(r) AS relation "
                "LIMIT 25"
            ),
            parameters={"graph_id": graph_id},
        ),
        Neo4jCypherStatement(
            purpose="community_scan",
            cypher=(
                "MATCH (n) "
                "RETURN labels(n) AS labels, count(*) AS count "
                "ORDER BY count DESC"
            ),
            parameters={"graph_id": graph_id},
        ),
    ]


def _coerce_snapshot(graph: GraphStore | GraphSnapshot | dict[str, Any]) -> GraphSnapshot:
    if isinstance(graph, GraphStore):
        return graph.snapshot
    if isinstance(graph, GraphSnapshot):
        return graph
    return GraphSnapshot.model_validate(graph)


def _cypher_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "entity").strip())
    cleaned = cleaned.strip("_") or "entity"
    if not cleaned[0].isalpha():
        cleaned = f"E_{cleaned}"
    return cleaned.upper()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _datetime_to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
