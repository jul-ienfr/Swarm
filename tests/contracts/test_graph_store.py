from __future__ import annotations

from pathlib import Path

import pytest

from swarm_core.belief_state import (
    BeliefState,
    attach_belief_states_to_graph,
    belief_state_from_graph_node,
    belief_state_to_graph_node,
    belief_states_to_graph_payload,
    dominant_stance,
    load_belief_states_from_graph,
    summarise_belief_group,
)
from swarm_core.graph_store import GraphStore, graph_payload_to_snapshot, snapshot_to_graph_payload


def test_graph_store_roundtrip_and_neighbors(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "graph.json", name="deliberation_graph", description="local graph")
    store.add_node(node_id="agent_a", label="Agent A", node_type="belief", properties={"stance": "support"})
    store.add_node(node_id="agent_b", label="Agent B", node_type="belief", properties={"stance": "oppose"})
    store.add_edge(source="agent_a", target="agent_b", relation="influences", weight=0.8)

    saved_path = store.save()
    loaded = GraphStore.load(saved_path)

    assert loaded.graph_id == store.graph_id
    assert loaded.get_node("agent_a").properties["stance"] == "support"
    assert loaded.neighbors("agent_a")[0].node_id == "agent_b"
    assert loaded.find_nodes(node_type="belief", label_contains="Agent")

    payload = snapshot_to_graph_payload(loaded.snapshot)
    snapshot = graph_payload_to_snapshot(payload)
    assert snapshot.graph_id == loaded.graph_id
    assert snapshot.nodes[0].node_id == "agent_a"


def test_belief_state_roundtrip_and_graph_attachment(tmp_path: Path) -> None:
    state = BeliefState(
        agent_id="agent_1",
        stance="support",
        confidence=1.2,
        trust=-0.2,
        memory_window=["first", "second", "third"],
        group_id="group_alpha",
        metadata={"source": "manual"},
    )
    peer = BeliefState(
        agent_id="agent_2",
        stance="support",
        confidence=0.9,
        trust=0.7,
        memory_window=["alpha", "beta"],
        group_id="group_alpha",
        metadata={"source": "manual"},
    )
    state.add_memory("fourth", max_items=3)

    node = belief_state_to_graph_node(state)
    restored = belief_state_from_graph_node(node)

    assert restored.agent_id == "agent_1"
    assert restored.confidence == 1.0
    assert restored.trust == 0.0
    assert restored.memory_window == ["second", "third", "fourth"]

    payload = belief_states_to_graph_payload([state, peer], include_group_nodes=True)
    assert payload["metadata"]["belief_state_count"] == 2
    assert payload["metadata"]["group_count"] == 1
    assert any(node["node_type"] == "belief_group" for node in payload["nodes"])
    assert dominant_stance([state, peer]) == "support"

    store = GraphStore(tmp_path / "belief_graph.json")
    attach_belief_states_to_graph(store, [state, peer])
    store.save()
    loaded_states = load_belief_states_from_graph(store)

    assert len(loaded_states) == 2
    assert all(item.group_id == "group_alpha" for item in loaded_states)
    summary = summarise_belief_group(loaded_states, group_id="group_alpha")
    assert summary.group_id == "group_alpha"
    assert summary.agent_count == 2
    assert summary.dominant_stance == "support"
    assert summary.average_confidence == pytest.approx(0.95)
