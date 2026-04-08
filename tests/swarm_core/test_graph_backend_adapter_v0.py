from __future__ import annotations

from swarm_core.graph_backend_adapter import (
    GraphBackendAdapter,
    GraphBackendKind,
    Neo4jFriendlyGraphBackendAdapter,
    build_advanced_neo4j_queries,
    build_neo4j_query_bundle,
)
from swarm_core.graph_store import GraphNode, GraphStore


def _build_graph(tmp_path):
    store = GraphStore(tmp_path / "graph.json", name="backend_test")
    store.add_node(GraphNode(node_id="agent_1", label="Agent One", node_type="persona"))
    store.add_node(GraphNode(node_id="signal_1", label="Signal One", node_type="signal"))
    store.add_edge(source="agent_1", target="signal_1", relation="grounded_by", weight=0.9)
    return store


def test_local_backend_export_returns_analytics(tmp_path):
    store = _build_graph(tmp_path)
    adapter = GraphBackendAdapter(store)
    result = adapter.export()

    assert result.backend == GraphBackendKind.local
    assert result.node_count == 2
    assert result.edge_count == 1
    assert result.analytics is not None
    assert result.analytics.node_count == 2


def test_neo4j_query_bundle_is_sanitized_and_structured(tmp_path):
    store = _build_graph(tmp_path)
    bundle = build_neo4j_query_bundle(store)

    assert bundle.graph_id == store.graph_id
    assert bundle.node_count == 2
    assert bundle.edge_count == 1
    assert bundle.relationship_types == ["GROUNDED_BY"]
    assert any(statement.purpose == "upsert_node" for statement in bundle.statements)
    assert any(statement.purpose == "upsert_edge" for statement in bundle.statements)
    assert any(statement.purpose == "top_influencers" for statement in bundle.analysis_queries)
    assert "MERGE (n:PERSONA" in bundle.statements[0].cypher


def test_neo4j_friendly_export_returns_query_bundle(tmp_path):
    store = _build_graph(tmp_path)
    adapter = Neo4jFriendlyGraphBackendAdapter(store)
    result = adapter.export()

    assert result.backend == GraphBackendKind.neo4j
    assert result.query_bundle is not None
    assert result.query_bundle.node_count == 2
    assert result.metadata["note"].startswith("cypher bundle")


def test_advanced_neo4j_queries_cover_common_diagnostics():
    queries = build_advanced_neo4j_queries("graph_demo")

    assert len(queries) >= 3
    assert {query.purpose for query in queries} >= {"top_influencers", "bridge_candidates", "community_scan"}
