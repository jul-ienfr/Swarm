from __future__ import annotations

from swarm_core.belief_state import BeliefState, beliefs_to_graph_payload
from swarm_core.cluster_diagnostics import diagnose_clusters
from swarm_core.deliberation_visuals import build_deliberation_visuals, build_visual_preview, render_graph_ascii, render_graph_mermaid
from swarm_core.graph_analytics import analyze_graph
from swarm_core.graph_store import GraphStore


def _build_graph(tmp_path):
    store = GraphStore(tmp_path / "graph.json", name="visual_test")
    beliefs = [
        BeliefState(agent_id="alpha", stance="support", confidence=0.8, trust=0.7, group_id="group_a"),
        BeliefState(agent_id="beta", stance="critical", confidence=0.5, trust=0.4, group_id="group_a"),
    ]
    store.merge_payload(beliefs_to_graph_payload(beliefs, include_group_nodes=True))
    return store, beliefs


def test_visual_bundle_contains_ascii_mermaid_and_cluster_table(tmp_path):
    store, beliefs = _build_graph(tmp_path)
    analytics = analyze_graph(store)
    diagnostics = diagnose_clusters(store, beliefs)
    bundle = build_deliberation_visuals(store, analytics=analytics, diagnostics=diagnostics)

    assert bundle.graph_id == store.graph_id
    assert len(bundle.artifacts) == 3
    assert any(artifact.kind == "ascii" for artifact in bundle.artifacts)
    assert any(artifact.kind == "mermaid" for artifact in bundle.artifacts)
    assert any(artifact.kind == "table" for artifact in bundle.artifacts)
    assert "TOP NODES" in bundle.artifacts[0].content
    assert "graph TD" in bundle.artifacts[1].content
    assert "cluster_id" in bundle.artifacts[2].content


def test_visual_preview_and_renderers_are_repeatable(tmp_path):
    store, beliefs = _build_graph(tmp_path)
    analytics = analyze_graph(store)
    diagnostics = diagnose_clusters(store, beliefs)

    ascii_view = render_graph_ascii(store, analytics=analytics, diagnostics=diagnostics)
    mermaid_view = render_graph_mermaid(store)
    preview = build_visual_preview(store, analytics=analytics, diagnostics=diagnostics)

    assert "DELIVERATION GRAPH" in ascii_view
    assert "graph TD" in mermaid_view
    assert preview["summary"]["node_count"] == len(store.snapshot.nodes)
    assert preview["summary"]["cluster_count"] == diagnostics.cluster_count

