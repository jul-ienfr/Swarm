from __future__ import annotations

from datetime import datetime, timezone

from swarm_core.belief_state import BeliefState, beliefs_to_graph_payload
from swarm_core.cluster_diagnostics import ClusterDiagnosticsEngine, diagnose_clusters
from swarm_core.graph_store import GraphStore


def _build_graph(tmp_path):
    store = GraphStore(tmp_path / "graph.json", name="cluster_test")
    beliefs = [
        BeliefState(agent_id="alpha", stance="support", confidence=0.8, trust=0.7, group_id="group_a"),
        BeliefState(agent_id="beta", stance="support", confidence=0.7, trust=0.6, group_id="group_a"),
        BeliefState(agent_id="gamma", stance="critical", confidence=0.4, trust=0.5, group_id="group_a"),
        BeliefState(agent_id="delta", stance="support", confidence=0.9, trust=0.9, group_id="group_b"),
    ]
    store.merge_payload(beliefs_to_graph_payload(beliefs, include_group_nodes=True))
    return store, beliefs


def test_cluster_diagnostics_reports_dissent_and_recommendations(tmp_path):
    store, beliefs = _build_graph(tmp_path)
    report = diagnose_clusters(store, beliefs)

    assert report.graph_id == store.graph_id
    assert report.cluster_count >= 2
    assert report.orphan_node_count == 0
    assert report.diagnostics
    first = report.diagnostics[0]
    assert first.dissent_ratio >= 0.0
    assert any(item.startswith("mediate_cluster") or item.startswith("raise_confidence") for item in report.recommendations)


def test_cluster_diagnostics_engine_is_deterministic(tmp_path):
    store, beliefs = _build_graph(tmp_path)
    engine = ClusterDiagnosticsEngine()
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = engine.diagnose(store, beliefs, generated_at=timestamp)
    second = engine.diagnose(store.snapshot, beliefs, generated_at=timestamp)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
