from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .graph_store import GraphEdge, GraphNode, GraphStore


class BeliefState(BaseModel):
    agent_id: str
    stance: str
    confidence: float = 0.5
    trust: float = 0.5
    memory_window: list[str] = Field(default_factory=list)
    group_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence", "trust")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _sanitize_memory(self) -> "BeliefState":
        self.memory_window = _normalize_memory_window(self.memory_window)
        return self

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def add_memory(self, item: str, *, max_items: int = 12) -> None:
        self.memory_window = _normalize_memory_window([*self.memory_window, item], max_items=max_items)
        self.touch()

    def update_stance(self, stance: str, *, confidence: float | None = None, trust: float | None = None) -> None:
        self.stance = stance
        if confidence is not None:
            self.confidence = max(0.0, min(1.0, float(confidence)))
        if trust is not None:
            self.trust = max(0.0, min(1.0, float(trust)))
        self.touch()

    def decay(self, *, confidence_delta: float = 0.05, trust_delta: float = 0.03) -> None:
        self.confidence = max(0.0, self.confidence - confidence_delta)
        self.trust = max(0.0, self.trust - trust_delta)
        self.touch()


class BeliefGroupSummary(BaseModel):
    group_id: str | None = None
    agent_count: int = 0
    average_confidence: float = 0.0
    average_trust: float = 0.0
    stance_counts: dict[str, int] = Field(default_factory=dict)
    dominant_stance: str | None = None
    memory_tokens: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _normalize_memory_window(items: Iterable[str], *, max_items: int = 12) -> list[str]:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if max_items <= 0:
        return cleaned
    return cleaned[-max_items:]


def belief_state_to_graph_node(state: BeliefState) -> GraphNode:
    return GraphNode(
        node_id=state.agent_id,
        label=state.agent_id,
        node_type="belief",
        properties={
            "stance": state.stance,
            "confidence": state.confidence,
            "trust": state.trust,
            "memory_window": list(state.memory_window),
            "group_id": state.group_id,
        },
        metadata=state.metadata,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def belief_state_from_graph_node(node: GraphNode) -> BeliefState:
    properties = dict(node.properties)
    return BeliefState(
        agent_id=node.node_id,
        stance=str(properties.get("stance", "")),
        confidence=_safe_float(properties.get("confidence"), default=0.5),
        trust=_safe_float(properties.get("trust"), default=0.5),
        memory_window=list(properties.get("memory_window", []) or []),
        group_id=properties.get("group_id"),
        metadata=dict(node.metadata),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def belief_state_membership_edge(state: BeliefState, *, group_node_id: str | None = None) -> GraphEdge | None:
    if not state.group_id:
        return None
    target = group_node_id or f"group:{state.group_id}"
    return GraphEdge(
        edge_id=f"edge_{uuid4().hex[:12]}",
        source=state.agent_id,
        target=target,
        relation="member_of",
        properties={
            "stance": state.stance,
            "confidence": state.confidence,
            "trust": state.trust,
        },
    )


def belief_states_to_graph_payload(
    states: Iterable[BeliefState],
    *,
    include_group_nodes: bool = True,
) -> dict[str, Any]:
    states = list(states)
    nodes = [belief_state_to_graph_node(state) for state in states]
    edges: list[GraphEdge] = []
    groups: dict[str, list[BeliefState]] = defaultdict(list)
    for state in states:
        if state.group_id:
            groups[state.group_id].append(state)
            edge = belief_state_membership_edge(state)
            if edge is not None:
                edges.append(edge)

    if include_group_nodes:
        for group_id, members in groups.items():
            dominant = dominant_stance(members)
            nodes.append(
                GraphNode(
                    node_id=f"group:{group_id}",
                    label=group_id,
                    node_type="belief_group",
                    properties={
                        "group_id": group_id,
                        "agent_count": len(members),
                        "dominant_stance": dominant,
                    },
                )
            )

    return {
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "edges": [edge.model_dump(mode="json") for edge in edges],
        "metadata": {
            "belief_state_count": len(states),
            "group_count": len(groups),
        },
    }


def load_belief_states_from_graph(store: GraphStore) -> list[BeliefState]:
    return [belief_state_from_graph_node(node) for node in store.find_nodes(node_type="belief")]


def dominant_stance(states: Iterable[BeliefState]) -> str | None:
    states = list(states)
    if not states:
        return None
    counts: dict[str, int] = defaultdict(int)
    for state in states:
        counts[state.stance] += 1
    return max(counts, key=counts.get)


def summarise_belief_group(states: Iterable[BeliefState], *, group_id: str | None = None) -> BeliefGroupSummary:
    states = list(states)
    if not states:
        return BeliefGroupSummary(group_id=group_id)
    stance_counts: dict[str, int] = defaultdict(int)
    for state in states:
        stance_counts[state.stance] += 1
    return BeliefGroupSummary(
        group_id=group_id or states[0].group_id,
        agent_count=len(states),
        average_confidence=mean(state.confidence for state in states),
        average_trust=mean(state.trust for state in states),
        stance_counts=dict(sorted(stance_counts.items())),
        dominant_stance=dominant_stance(states),
        memory_tokens=sum(len(state.memory_window) for state in states),
    )


def attach_belief_states_to_graph(
    store: GraphStore,
    states: Iterable[BeliefState],
    *,
    include_group_nodes: bool = True,
) -> GraphStore:
    payload = beliefs_to_graph_payload(states, include_group_nodes=include_group_nodes)
    store.merge_payload(payload)
    return store


def beliefs_to_graph_payload(
    states: Iterable[BeliefState],
    *,
    include_group_nodes: bool = True,
) -> dict[str, Any]:
    return belief_states_to_graph_payload(states, include_group_nodes=include_group_nodes)


def _safe_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
