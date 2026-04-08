from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .belief_state import BeliefState, belief_state_to_graph_node
from .deliberation_artifacts import DeliberationMode
from .graph_store import GraphEdge, GraphNode, GraphStore


DEFAULT_WORKBENCH_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "deliberation_workbench"
WORKBENCH_PROFILE_PIPELINE_VERSION = "v2"
WORKBENCH_DEFAULT_PARTICIPANTS = ("architect", "research", "guardian")
WORKBENCH_MAX_DERIVED_PARTICIPANTS = 6
WORKBENCH_MIN_DERIVED_PARTICIPANTS = 3

_WORKBENCH_ROLE_HINTS: list[tuple[str, set[str]]] = [
    (
        "architect",
        {
            "architect",
            "design",
            "launch",
            "rollout",
            "workflow",
            "integration",
            "system",
            "pipeline",
            "roadmap",
            "structure",
        },
    ),
    (
        "research",
        {
            "research",
            "analysis",
            "signal",
            "evidence",
            "benchmark",
            "review",
            "compare",
            "investigate",
            "study",
            "insight",
        },
    ),
    (
        "guardian",
        {
            "risk",
            "safety",
            "guard",
            "rollback",
            "compliance",
            "control",
            "reliability",
            "stability",
            "observability",
            "policy",
        },
    ),
    (
        "operator",
        {
            "ops",
            "execution",
            "deploy",
            "runtime",
            "incident",
            "monitoring",
            "latency",
            "throughput",
            "canary",
            "delivery",
        },
    ),
    (
        "market",
        {
            "market",
            "growth",
            "adoption",
            "revenue",
            "demand",
            "pricing",
            "edge",
            "alpha",
            "liquidity",
        },
    ),
    (
        "facilitator",
        {
            "facilitator",
            "moderator",
            "chair",
            "coordination",
            "synthesis",
            "committee",
        },
    ),
]


class WorkbenchStatus(str, Enum):
    draft = "draft"
    prepared = "prepared"
    persisted = "persisted"
    replayed = "replayed"


class WorkbenchArtifactKind(str, Enum):
    input = "input"
    profile = "profile"
    session = "session"
    graph = "graph"
    report = "report"
    other = "other"


class NormalizedWorkbenchInput(BaseModel):
    schema_version: str = "v1"
    topic: str
    objective: str = ""
    mode: DeliberationMode = DeliberationMode.committee
    participants: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    population_size: int = 0
    rounds: int = 0
    time_horizon: str = "7d"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkbenchPersonaProfile(BaseModel):
    schema_version: str = "v1"
    profile_id: str = Field(default_factory=lambda: f"profile_{uuid4().hex[:12]}")
    label: str
    role: str = "participant"
    stance: str = "support"
    confidence: float = 0.5
    trust: float = 0.5
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    memory_window: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence", "trust")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class WorkbenchArtifactRef(BaseModel):
    artifact_id: str
    kind: WorkbenchArtifactKind = WorkbenchArtifactKind.other
    title: str = ""
    uri: str | None = None
    content_hash: str | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkbenchSession(BaseModel):
    schema_version: str = "v1"
    workbench_id: str = Field(default_factory=lambda: f"wb_{uuid4().hex[:12]}")
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    status: WorkbenchStatus = WorkbenchStatus.draft
    input_bundle: NormalizedWorkbenchInput
    profiles: list[WorkbenchPersonaProfile] = Field(default_factory=list)
    artifacts: list[WorkbenchArtifactRef] = Field(default_factory=list)
    graph_path: str | None = None
    session_path: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def add_artifact(self, artifact: WorkbenchArtifactRef) -> None:
        self.artifacts.append(artifact)
        self.touch()


def normalize_workbench_input(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    population_size: int | None = None,
    rounds: int | None = None,
    time_horizon: str = "7d",
    metadata: dict[str, Any] | None = None,
) -> NormalizedWorkbenchInput:
    resolved_mode = mode if isinstance(mode, DeliberationMode) else DeliberationMode(str(mode))
    return NormalizedWorkbenchInput(
        topic=topic,
        objective=objective or "",
        mode=resolved_mode,
        participants=_clean_string_items(participants or []),
        documents=_clean_string_items(documents or []),
        entities=list(entities or []),
        interventions=_clean_string_items(interventions or []),
        population_size=max(0, int(population_size or 0)),
        rounds=max(0, int(rounds or 0)),
        time_horizon=time_horizon,
        metadata=dict(metadata or {}),
    )


def generate_persona_profiles(bundle: NormalizedWorkbenchInput) -> list[WorkbenchPersonaProfile]:
    profiles: list[WorkbenchPersonaProfile] = []
    participants, participant_source, signal_keywords = _derive_participants(bundle)
    signal_count = len(signal_keywords)
    evidence_pool = _build_evidence_pool(bundle, signal_keywords)

    for index, participant in enumerate(participants, start=1):
        role = _infer_role(participant, signal_keywords)
        stance = _infer_stance(participant, bundle, signal_keywords)
        confidence = _score_confidence(participant, bundle, signal_keywords, participant_source, evidence_pool)
        trust = _score_trust(participant, bundle, signal_keywords, participant_source, evidence_pool)
        memory_window = _build_memory_window(bundle, participant, participant_source, signal_keywords)
        profiles.append(
            WorkbenchPersonaProfile(
                label=participant,
                role=role,
                stance=stance,
                confidence=confidence,
                trust=trust,
                summary=_build_profile_summary(
                    participant,
                    bundle,
                    role=role,
                    stance=stance,
                    participant_source=participant_source,
                    signal_keywords=signal_keywords,
                ),
                evidence=evidence_pool[:5],
                memory_window=memory_window,
                metadata={
                    "index": index,
                    "mode": bundle.mode.value,
                    "population_size": bundle.population_size,
                    "rounds": bundle.rounds,
                    "source": "normalized_workbench",
                    "participant_source": participant_source,
                    "signal_count": signal_count,
                    "signal_keywords": signal_keywords[:5],
                    "profile_generation_version": WORKBENCH_PROFILE_PIPELINE_VERSION,
                },
            )
        )

    return profiles


def build_workbench_session(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    population_size: int | None = None,
    rounds: int | None = None,
    time_horizon: str = "7d",
    metadata: dict[str, Any] | None = None,
) -> WorkbenchSession:
    bundle = normalize_workbench_input(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        metadata=metadata,
    )
    profiles = generate_persona_profiles(bundle)
    participant_source = profiles[0].metadata.get("participant_source", "unknown") if profiles else "unknown"
    signal_keywords = profiles[0].metadata.get("signal_keywords", []) if profiles else []
    session = WorkbenchSession(
        input_bundle=bundle,
        profiles=profiles,
        status=WorkbenchStatus.prepared,
        summary=_build_session_summary(
            bundle,
            profiles,
            participant_source=participant_source,
            signal_keywords=signal_keywords if isinstance(signal_keywords, list) else [],
        ),
        metadata={
            "profile_count": len(profiles),
            "document_count": len(bundle.documents),
            "intervention_count": len(bundle.interventions),
            "entity_count": len(bundle.entities),
            "participant_source": participant_source,
            "participant_count": len(profiles),
            "signal_keywords": signal_keywords if isinstance(signal_keywords, list) else [],
            "profile_generation_version": WORKBENCH_PROFILE_PIPELINE_VERSION,
            "source": "deliberation_workbench",
        },
    )
    return session


def persist_workbench_session(
    session: WorkbenchSession,
    *,
    output_dir: str | Path | None = None,
    write_graph: bool = True,
) -> WorkbenchSession:
    base_dir = Path(output_dir or DEFAULT_WORKBENCH_OUTPUT_DIR) / session.workbench_id
    base_dir.mkdir(parents=True, exist_ok=True)

    input_path = base_dir / "input.json"
    profiles_path = base_dir / "profiles.json"
    session_path = base_dir / "session.json"
    artifacts_path = base_dir / "artifacts.json"
    graph_path = base_dir / "graph.json"

    input_path.write_text(session.input_bundle.model_dump_json(indent=2), encoding="utf-8")
    profiles_path.write_text(
        json.dumps([profile.model_dump(mode="json") for profile in session.profiles], indent=2),
        encoding="utf-8",
    )

    artifacts: list[WorkbenchArtifactRef] = [
        WorkbenchArtifactRef(
            artifact_id=f"artifact_input_{session.workbench_id}",
            kind=WorkbenchArtifactKind.input,
            title="normalized_input",
            uri=str(input_path),
            content_hash=_sha256_text(input_path.read_text(encoding="utf-8")),
            content_type="application/json",
        ),
        WorkbenchArtifactRef(
            artifact_id=f"artifact_profiles_{session.workbench_id}",
            kind=WorkbenchArtifactKind.profile,
            title="persona_profiles",
            uri=str(profiles_path),
            content_hash=_sha256_text(profiles_path.read_text(encoding="utf-8")),
            content_type="application/json",
        ),
    ]

    graph_store = GraphStore(graph_path, name="deliberation_workbench", description=f"Workbench for {session.workbench_id}")
    for profile in session.profiles:
        graph_store.add_node(
            GraphNode(
                node_id=profile.profile_id,
                label=profile.label,
                node_type="persona",
                properties={
                    "role": profile.role,
                    "stance": profile.stance,
                    "confidence": profile.confidence,
                    "trust": profile.trust,
                    "summary": profile.summary,
                    "evidence": list(profile.evidence),
                },
                metadata=dict(profile.metadata),
            )
        )
    for profile in session.profiles:
        for evidence_index, evidence in enumerate(profile.evidence[:3], start=1):
            evidence_node_id = f"evidence_{profile.profile_id}_{evidence_index}"
            graph_store.add_node(
                GraphNode(
                    node_id=evidence_node_id,
                    label=evidence[:80],
                    node_type="evidence",
                    properties={"text": evidence, "profile_id": profile.profile_id},
                )
            )
            graph_store.add_edge(
                source=profile.profile_id,
                target=evidence_node_id,
                relation="grounded_by",
                weight=0.8,
            )
    if write_graph:
        saved_graph_path = graph_store.save(graph_path)
        session.graph_path = str(saved_graph_path)
        artifacts.append(
            WorkbenchArtifactRef(
                artifact_id=f"artifact_graph_{session.workbench_id}",
                kind=WorkbenchArtifactKind.graph,
                title="persona_graph",
                uri=str(saved_graph_path),
                content_hash=_sha256_text(saved_graph_path.read_text(encoding="utf-8")),
                content_type="application/json",
            )
        )

    session.status = WorkbenchStatus.persisted
    session.session_path = str(session_path)
    session.add_artifact(artifacts[0])
    session.add_artifact(artifacts[1])
    if write_graph:
        session.add_artifact(artifacts[2])
    session.metadata.update(
        {
            "input_path": str(input_path),
            "profiles_path": str(profiles_path),
            "artifacts_path": str(artifacts_path),
            "graph_path": session.graph_path,
        }
    )
    session_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    artifacts_path.write_text(
        json.dumps([artifact.model_dump(mode="json") for artifact in session.artifacts], indent=2),
        encoding="utf-8",
    )
    return session


def load_workbench_session(path: str | Path) -> WorkbenchSession:
    return WorkbenchSession.model_validate_json(Path(path).read_text(encoding="utf-8"))


def workbench_directory(
    *,
    output_dir: str | Path | None = None,
    workbench_id: str,
) -> Path:
    return Path(output_dir or DEFAULT_WORKBENCH_OUTPUT_DIR) / workbench_id


def profiles_to_graph_payload(profiles: Iterable[WorkbenchPersonaProfile]) -> dict[str, Any]:
    nodes = [profile_to_graph_node(profile) for profile in profiles]
    edges: list[GraphEdge] = []
    for profile in profiles:
        for evidence_index, evidence in enumerate(profile.evidence[:3], start=1):
            evidence_node_id = f"evidence_{profile.profile_id}_{evidence_index}"
            nodes.append(
                GraphNode(
                    node_id=evidence_node_id,
                    label=evidence[:80],
                    node_type="evidence",
                    properties={"text": evidence, "profile_id": profile.profile_id},
                )
            )
            edges.append(
                GraphEdge(
                    source=profile.profile_id,
                    target=evidence_node_id,
                    relation="grounded_by",
                    weight=0.8,
                )
            )
    return {
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "edges": [edge.model_dump(mode="json") for edge in edges],
        "metadata": {"profile_count": len(profiles)},
    }


def profile_to_graph_node(profile: WorkbenchPersonaProfile) -> GraphNode:
    return GraphNode(
        node_id=profile.profile_id,
        label=profile.label,
        node_type="persona",
        properties={
            "role": profile.role,
            "stance": profile.stance,
            "confidence": profile.confidence,
            "trust": profile.trust,
            "summary": profile.summary,
            "evidence": list(profile.evidence),
            "memory_window": list(profile.memory_window),
        },
        metadata=dict(profile.metadata),
        created_at=profile.created_at,
    )


def profile_to_belief_state(profile: WorkbenchPersonaProfile) -> BeliefState:
    return BeliefState(
        agent_id=profile.profile_id,
        stance=profile.stance,
        confidence=profile.confidence,
        trust=profile.trust,
        memory_window=list(profile.memory_window),
        group_id=str(profile.metadata.get("group_id") or "workbench"),
        metadata={
            **dict(profile.metadata),
            "summary": profile.summary,
            "evidence": list(profile.evidence),
            "role": profile.role,
        },
    )


def _build_session_summary(
    bundle: NormalizedWorkbenchInput,
    profiles: list[WorkbenchPersonaProfile],
    *,
    participant_source: str,
    signal_keywords: list[str],
) -> str:
    participant_labels = ", ".join(profile.label for profile in profiles[:5]) if profiles else "none"
    signal_text = ", ".join(signal_keywords[:4]) if signal_keywords else "none"
    return (
        f"Workbench for '{bundle.topic}' in mode {bundle.mode.value} "
        f"with {len(profiles)} profiles from {participant_source}. "
        f"Participants: {participant_labels}. Signals: {signal_text}."
    )


def _build_profile_summary(
    label: str,
    bundle: NormalizedWorkbenchInput,
    *,
    role: str,
    stance: str,
    participant_source: str,
    signal_keywords: list[str],
) -> str:
    document_signal = _best_signal(bundle.documents)
    intervention_signal = _best_signal(bundle.interventions)
    keyword_text = ", ".join(signal_keywords[:4]) if signal_keywords else "none"
    origin_text = "explicit participant" if participant_source == "explicit" else "derived participant"
    return (
        f"{label} is a {role} persona for '{bundle.topic}' with a {stance} stance. "
        f"Origin: {origin_text}. "
        f"Primary signals: {keyword_text}. "
        f"Document signal: {document_signal or 'none'}"
        + (f"; intervention signal: {intervention_signal}" if intervention_signal else "")
    )


def _build_memory_window(
    bundle: NormalizedWorkbenchInput,
    label: str,
    participant_source: str,
    signal_keywords: list[str],
) -> list[str]:
    window = [bundle.topic]
    if bundle.objective:
        window.append(bundle.objective)
    window.extend(bundle.documents[:2])
    window.extend(bundle.interventions[:2])
    window.extend(signal_keywords[:2])
    window.append(f"profile:{label}")
    window.append(f"source:{participant_source}")
    return _dedupe_and_trim(window, limit=8)


def _derive_participants(bundle: NormalizedWorkbenchInput) -> tuple[list[str], str, list[str]]:
    explicit = _clean_string_items(bundle.participants)
    if explicit:
        signal_keywords = _collect_signal_keywords(bundle)
        return explicit, "explicit", signal_keywords

    signal_keywords = _collect_signal_keywords(bundle)
    labels = _build_derived_participants(signal_keywords)
    if not labels:
        labels = list(WORKBENCH_DEFAULT_PARTICIPANTS)
        participant_source = "fallback"
    else:
        participant_source = "derived"
    return labels, participant_source, signal_keywords


def _infer_role(label: str, signal_keywords: list[str]) -> str:
    tokens = set(_tokenize(label) + signal_keywords)
    if tokens & {"safety", "risk", "moderation", "guard", "rollback", "compliance"}:
        return "guardian"
    if tokens & {"research", "analysis", "intel", "signal", "evidence", "benchmark", "review"}:
        return "analyst"
    if tokens & {"architect", "design", "product", "launch", "rollout", "workflow", "integration"}:
        return "architect"
    if tokens & {"ops", "operator", "execution", "deployment", "monitoring", "runtime", "delivery"}:
        return "operator"
    if tokens & {"growth", "market", "adoption", "revenue", "demand", "pricing", "edge"}:
        return "market"
    if tokens & {"facilitator", "moderator", "chair", "synthesis", "coordination"}:
        return "facilitator"
    return "participant"


def _infer_stance(label: str, bundle: NormalizedWorkbenchInput, signal_keywords: list[str]) -> str:
    tokens = set(_tokenize(label) + signal_keywords)
    if tokens & {"critic", "safety", "risk", "guard", "rollback", "compliance"}:
        return "critical"
    if tokens & {"cautious", "stability", "stable", "safe", "reliability", "observability"}:
        return "cautious"
    if tokens & {"expansion", "growth", "adoption", "market", "revenue"}:
        return "expansion"
    if bundle.mode == DeliberationMode.hybrid:
        return "support"
    if bundle.interventions:
        return "cautious"
    return "support"


def _score_confidence(
    label: str,
    bundle: NormalizedWorkbenchInput,
    signal_keywords: list[str],
    participant_source: str,
    evidence_pool: list[str],
) -> float:
    base = 0.42
    if any(token in label.lower() for token in ["architect", "research", "guardian", "operator", "market"]):
        base += 0.08
    if participant_source == "explicit":
        base += 0.12
    elif participant_source == "derived":
        base += 0.06
    base += min(0.14, 0.018 * len(bundle.documents))
    base += min(0.08, 0.015 * len(bundle.interventions))
    base += min(0.12, 0.015 * len(signal_keywords))
    base += min(0.08, 0.01 * len(evidence_pool))
    return max(0.0, min(1.0, base))


def _score_trust(
    label: str,
    bundle: NormalizedWorkbenchInput,
    signal_keywords: list[str],
    participant_source: str,
    evidence_pool: list[str],
) -> float:
    base = 0.34
    if bundle.mode == DeliberationMode.committee:
        base += 0.1
    if any(token in label.lower() for token in ["safety", "research", "guardian", "analyst"]):
        base += 0.05
    if participant_source == "explicit":
        base += 0.08
    elif participant_source == "derived":
        base += 0.04
    base += min(0.08, 0.012 * len(bundle.documents))
    base += min(0.06, 0.01 * len(signal_keywords))
    base += min(0.06, 0.008 * len(evidence_pool))
    return max(0.0, min(1.0, base))


def _collect_signal_keywords(bundle: NormalizedWorkbenchInput, *, limit: int = 10) -> list[str]:
    values = [
        bundle.topic,
        bundle.objective,
        *bundle.documents,
        *bundle.interventions,
        *[json.dumps(entity, sort_keys=True, default=str) for entity in bundle.entities],
    ]
    return _top_tokens(values, limit=limit)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9_]+", str(text).lower())


def _build_evidence_pool(bundle: NormalizedWorkbenchInput, signal_keywords: list[str]) -> list[str]:
    evidence_pool = [
        *bundle.documents,
        *bundle.interventions,
        *[json.dumps(entity, sort_keys=True, default=str) for entity in bundle.entities],
        *signal_keywords,
    ]
    return _dedupe_and_trim(evidence_pool, limit=8)


def _build_derived_participants(signal_keywords: list[str]) -> list[str]:
    if not signal_keywords:
        return []

    derived: list[str] = []
    used_stems: set[str] = set()
    role_order = [role for role, _hints in _WORKBENCH_ROLE_HINTS]
    target_count = max(WORKBENCH_MIN_DERIVED_PARTICIPANTS, min(WORKBENCH_MAX_DERIVED_PARTICIPANTS, len(signal_keywords)))

    for index, role in enumerate(role_order):
        if len(derived) >= target_count:
            break
        token = _select_signal_token(role, signal_keywords, used_stems, index)
        label = _compose_label(role, token, index)
        stem = _label_stem(label)
        if stem in used_stems:
            continue
        used_stems.add(stem)
        derived.append(label)

    if len(derived) < target_count:
        for index, token in enumerate(signal_keywords):
            if len(derived) >= target_count:
                break
            role = role_order[index % len(role_order)]
            label = _compose_label(role, token, index + len(derived))
            stem = _label_stem(label)
            if stem in used_stems:
                continue
            used_stems.add(stem)
            derived.append(label)

    return derived[:target_count]


def _select_signal_token(role: str, signal_keywords: list[str], used_stems: set[str], index: int) -> str:
    hints = next((hints for hint_role, hints in _WORKBENCH_ROLE_HINTS if hint_role == role), set())
    for token in signal_keywords:
        stem = _label_stem(token)
        if stem in used_stems:
            continue
        if token in hints:
            return token
    for offset in range(len(signal_keywords)):
        token = signal_keywords[(index + offset) % len(signal_keywords)]
        stem = _label_stem(token)
        if stem not in used_stems:
            return token
    return role


def _compose_label(role: str, token: str, index: int) -> str:
    stem = _label_stem(token)
    if not stem or stem == role:
        return f"{role}_{index + 1:02d}"
    if stem.startswith(f"{role}_"):
        return stem
    return f"{role}_{stem}"


def _label_stem(value: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return stem


def _extract_tokens(values: Iterable[str]) -> list[str]:
    tokens: list[str] = []
    for value in values:
        tokens.extend(_tokenize(value))
    return [token for token in tokens if token not in _STOPWORDS]


def _top_tokens(values: Iterable[str], *, limit: int = 8) -> list[str]:
    counts = Counter(_extract_tokens(values))
    return [token for token, _ in counts.most_common(limit)]


def _best_signal(values: list[str]) -> str | None:
    tokens = _top_tokens(values, limit=1)
    return tokens[0] if tokens else None


def _dedupe_and_trim(items: Iterable[str], *, limit: int = 8) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned[:limit]


def _clean_string_items(items: Iterable[str]) -> list[str]:
    return _dedupe_and_trim(items, limit=512)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "dans",
    "de",
    "des",
    "du",
    "d",
    "e",
    "en",
    "est",
    "et",
    "il",
    "ils",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "leurs",
    "l",
    "mais",
    "mes",
    "mon",
    "nos",
    "notre",
    "nous",
    "on",
    "ou",
    "par",
    "pas",
    "pour",
    "que",
    "qui",
    "se",
    "ses",
    "sur",
    "ta",
    "te",
    "tes",
    "toi",
    "ton",
    "tu",
    "un",
    "une",
    "vos",
    "votre",
    "vous",
    "y",
    "aussi",
    "comme",
    "plus",
    "sans",
    "tout",
    "tous",
    "toute",
    "toutes",
    "topic",
    "objective",
    "plan",
    "plans",
    "pattern",
    "patterns",
    "integration",
    "integrer",
    "integree",
    "externe",
    "externes",
    "prediction",
    "markets",
    "prediction_markets",
    "revue",
    "multi",
    "agents",
    "systeme",
    "local",
    "locale",
    "and",
    "are",
    "best",
    "can",
    "choose",
    "for",
    "from",
    "generate",
    "into",
    "graph",
    "how",
    "interview",
    "need",
    "needed",
    "mode",
    "none",
    "our",
    "overall",
    "persona",
    "personas",
    "please",
    "smoke",
    "the",
    "this",
    "us",
    "we",
    "what",
    "when",
    "where",
    "that",
    "should",
    "want",
    "wants",
    "would",
    "with",
    "what",
    "will",
    "when",
    "your",
    "about",
    "topic",
    "objective",
}
