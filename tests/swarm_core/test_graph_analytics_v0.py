from __future__ import annotations

from datetime import datetime, timezone

from swarm_core.graph_analytics import GraphAnalyticsEngine, analyze_graph
from swarm_core.graph_store import GraphNode, GraphStore


def _build_graph(tmp_path):
    store = GraphStore(tmp_path / "graph.json", name="analytics_test")
    store.add_node(GraphNode(node_id="a", label="Alpha", node_type="persona"))
    store.add_node(GraphNode(node_id="b", label="Beta", node_type="persona"))
    store.add_node(GraphNode(node_id="c", label="Gamma", node_type="signal"))
    store.add_node(GraphNode(node_id="d", label="Delta", node_type="signal"))
    store.add_edge(source="a", target="b", relation="influences", weight=2.0)
    store.add_edge(source="a", target="c", relation="influences", weight=1.0)
    store.add_edge(source="b", target="c", relation="supports", weight=0.5)
    return store


def test_graph_analytics_report_tracks_counts_and_components(tmp_path):
    store = _build_graph(tmp_path)
    report = analyze_graph(store)

    assert report.graph_id == store.graph_id
    assert report.node_count == 4
    assert report.edge_count == 3
    assert report.component_count == 2
    assert report.isolated_node_count == 1
    assert report.node_type_counts == {"persona": 2, "signal": 2}
    assert report.relation_counts == {"influences": 2, "supports": 1}
    assert {score.node_id for score in report.top_nodes} >= {"a", "b", "c"}
    assert len(report.clusters) == 2


def test_graph_analytics_engine_is_repeatable(tmp_path):
    store = _build_graph(tmp_path)
    engine = GraphAnalyticsEngine()
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = engine.analyze(store, generated_at=timestamp)
    second = engine.analyze(store.snapshot, generated_at=timestamp)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
