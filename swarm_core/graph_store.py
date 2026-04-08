from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    node_id: str
    label: str
    node_type: str = "entity"
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphEdge(BaseModel):
    edge_id: str = Field(default_factory=lambda: f"edge_{uuid4().hex[:12]}")
    source: str
    target: str
    relation: str = "related_to"
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphSnapshot(BaseModel):
    graph_id: str = Field(default_factory=lambda: f"graph_{uuid4().hex[:12]}")
    name: str = "local_graph"
    description: str = ""
    version: str = "v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class GraphStore:
    def __init__(
        self,
        path: str | Path,
        *,
        name: str = "local_graph",
        description: str = "",
        version: str = "v1",
    ) -> None:
        self.path = Path(path)
        self.name = name
        self.description = description
        self.version = version
        self._snapshot = self._load_or_initialize()

    @classmethod
    def load(cls, path: str | Path) -> "GraphStore":
        return cls(path)

    @property
    def snapshot(self) -> GraphSnapshot:
        return self._snapshot

    @property
    def graph_id(self) -> str:
        return self._snapshot.graph_id

    def add_node(
        self,
        node: GraphNode | None = None,
        *,
        node_id: str | None = None,
        label: str | None = None,
        node_type: str = "entity",
        properties: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphNode:
        resolved = node or GraphNode(
            node_id=node_id or f"node_{uuid4().hex[:12]}",
            label=label or node_id or "node",
            node_type=node_type,
            properties=properties or {},
            metadata=metadata or {},
        )
        self._upsert_node(resolved)
        return resolved

    def add_edge(
        self,
        edge: GraphEdge | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        relation: str = "related_to",
        weight: float = 1.0,
        properties: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdge:
        if edge is not None:
            resolved = edge
        else:
            if source is None or target is None:
                raise ValueError("source and target are required when edge is not provided")
            resolved = GraphEdge(
                source=source,
                target=target,
                relation=relation,
                weight=weight,
                properties=properties or {},
                metadata=metadata or {},
            )
        self._snapshot.edges.append(resolved)
        self._snapshot.touch()
        return resolved

    def upsert_belief_graph_payload(self, payload: dict[str, Any]) -> None:
        self.merge_payload(payload)

    def add_edge_from_payload(self, payload: dict[str, Any]) -> GraphEdge:
        resolved = GraphEdge.model_validate(payload)
        self._snapshot.edges.append(resolved)
        self._snapshot.touch()
        return resolved

    def get_node(self, node_id: str) -> GraphNode | None:
        for node in self._snapshot.nodes:
            if node.node_id == node_id:
                return node
        return None

    def find_nodes(
        self,
        *,
        node_type: str | None = None,
        label_contains: str | None = None,
        predicate: Callable[[GraphNode], bool] | None = None,
    ) -> list[GraphNode]:
        matches: list[GraphNode] = []
        needle = label_contains.lower() if label_contains else None
        for node in self._snapshot.nodes:
            if node_type is not None and node.node_type != node_type:
                continue
            if needle is not None and needle not in node.label.lower():
                continue
            if predicate is not None and not predicate(node):
                continue
            matches.append(node)
        return matches

    def neighbors(self, node_id: str, *, direction: str = "both") -> list[GraphNode]:
        node_ids: set[str] = set()
        for edge in self._snapshot.edges:
            if direction in {"both", "out"} and edge.source == node_id:
                node_ids.add(edge.target)
            if direction in {"both", "in"} and edge.target == node_id:
                node_ids.add(edge.source)
        return [node for node in self._snapshot.nodes if node.node_id in node_ids]

    def replace(self, snapshot: GraphSnapshot) -> None:
        self._snapshot = snapshot
        self._snapshot.touch()

    def merge_payload(self, payload: dict[str, Any]) -> None:
        for raw_node in payload.get("nodes", []):
            self.add_node(GraphNode.model_validate(raw_node))
        for raw_edge in payload.get("edges", []):
            self.add_edge(
                GraphEdge.model_validate(raw_edge),
                source=str(raw_edge.get("source")),
                target=str(raw_edge.get("target")),
            )

    def to_dict(self) -> dict[str, Any]:
        return self._snapshot.model_dump(mode="json")

    def save(self, path: str | Path | None = None) -> Path:
        target_path = self._resolve_path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._snapshot.model_dump_json(indent=2)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(target_path.parent), encoding="utf-8") as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        temp_path.replace(target_path)
        return target_path

    def reload(self) -> GraphSnapshot:
        self._snapshot = self._load_or_initialize()
        return self._snapshot

    def _upsert_node(self, node: GraphNode) -> None:
        replaced = False
        next_nodes: list[GraphNode] = []
        for existing in self._snapshot.nodes:
            if existing.node_id == node.node_id:
                next_nodes.append(
                    node.model_copy(update={"created_at": existing.created_at, "updated_at": datetime.now(timezone.utc)})
                )
                replaced = True
            else:
                next_nodes.append(existing)
        if not replaced:
            next_nodes.append(node)
        self._snapshot.nodes = next_nodes
        self._snapshot.touch()

    def _load_or_initialize(self) -> GraphSnapshot:
        if not self._resolve_path().exists():
            return GraphSnapshot(name=self.name, description=self.description, version=self.version)
        return GraphSnapshot.model_validate_json(self._resolve_path().read_text(encoding="utf-8"))

    def _resolve_path(self, path: str | Path | None = None) -> Path:
        candidate = Path(path) if path is not None else self.path
        if candidate.suffix:
            return candidate
        return candidate / "graph.json"


def graph_payload_to_snapshot(
    payload: dict[str, Any],
    *,
    graph_id: str | None = None,
    name: str = "local_graph",
    description: str = "",
    version: str = "v1",
) -> GraphSnapshot:
    return GraphSnapshot(
        graph_id=graph_id or str(payload.get("graph_id") or f"graph_{uuid4().hex[:12]}"),
        name=name,
        description=str(payload.get("description", description) or description),
        version=str(payload.get("version", version) or version),
        nodes=[GraphNode.model_validate(node) for node in payload.get("nodes", [])],
        edges=[GraphEdge.model_validate(edge) for edge in payload.get("edges", [])],
        metadata=dict(payload.get("metadata", {})),
    )


def snapshot_to_graph_payload(snapshot: GraphSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")


def save_graph_payload(path: str | Path, payload: dict[str, Any]) -> Path:
    store = GraphStore(path)
    store.replace(graph_payload_to_snapshot(payload))
    return store.save(path)
