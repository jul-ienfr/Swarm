from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .deliberation_artifacts import DeliberationMode
from .normalized_social_traces import NormalizedSocialTrace, SocialTraceKind


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeliberationRequest(BaseModel):
    schema_version: str = "v1"
    topic: str
    objective: str = ""
    mode: DeliberationMode = DeliberationMode.committee
    documents: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    population_size: int = 0
    rounds: int = 0
    time_horizon: str = "7d"
    engine_preference: str = ""
    entities: list[Any] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("population_size", "rounds")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        return max(0, int(value))


class ParticipantProfile(BaseModel):
    profile_id: str
    persona_summary: str
    belief_seed: dict[str, Any] = Field(default_factory=dict)
    group_id: str | None = None
    grounding_refs: list[str] = Field(default_factory=list)
    confidence_prior: float = 0.5
    label: str = ""
    role: str = "participant"
    stance: str = "support"
    trust_prior: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence_prior", "trust_prior")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class BeliefStateSnapshot(BaseModel):
    run_id: str
    agent_id: str
    tick: int
    stance: str
    confidence: float = 0.5
    trust_map: dict[str, float] = Field(default_factory=dict)
    memory_window: list[str] = Field(default_factory=list)
    group_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=_utc_now)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class SocialTraceBundle(BaseModel):
    bundle_id: str = Field(default_factory=lambda: f"trace_bundle_{uuid4().hex[:12]}")
    run_id: str
    platform: str
    posts: list[dict[str, Any]] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    reactions: list[dict[str, Any]] = Field(default_factory=list)
    follow_events: list[dict[str, Any]] = Field(default_factory=list)
    trace_quality_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationReport(BaseModel):
    schema_version: str = "v1"
    summary: str = ""
    scenarios: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    cluster_summaries: list[dict[str, Any]] = Field(default_factory=list)
    confidence_level: float = 0.0
    uncertainty_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    final_strategy: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    sensitivity_factors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence_level")
    @classmethod
    def _clamp_unit_interval(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


def participant_profile_from_source(profile: Any) -> ParticipantProfile:
    evidence = list(getattr(profile, "evidence", []) or [])
    summary = str(getattr(profile, "summary", "") or getattr(profile, "label", "") or "")
    confidence = float(getattr(profile, "confidence", 0.5) or 0.5)
    trust = float(getattr(profile, "trust", 0.5) or 0.5)
    stance = str(getattr(profile, "stance", "support"))
    if hasattr(getattr(profile, "stance", None), "value"):
        stance = str(profile.stance.value)
    role = str(getattr(profile, "role", "participant"))
    if hasattr(getattr(profile, "role", None), "value"):
        role = str(profile.role.value)
    return ParticipantProfile(
        profile_id=str(getattr(profile, "profile_id", f"profile_{uuid4().hex[:12]}")),
        persona_summary=summary,
        belief_seed={
            "stance": stance,
            "confidence": confidence,
            "trust": trust,
            "memory_window": list(getattr(profile, "memory_window", []) or []),
        },
        group_id=getattr(profile, "metadata", {}).get("group_id") if isinstance(getattr(profile, "metadata", {}), dict) else None,
        grounding_refs=evidence,
        confidence_prior=confidence,
        label=str(getattr(profile, "label", "")),
        role=role,
        stance=stance,
        trust_prior=trust,
        metadata=dict(getattr(profile, "metadata", {}) or {}),
    )


def belief_state_snapshot_from_state(
    *,
    run_id: str,
    state: Any,
    tick: int,
) -> BeliefStateSnapshot:
    trust = float(getattr(state, "trust", 0.5) or 0.5)
    group_id = getattr(state, "group_id", None)
    trust_map = {"global": trust}
    if group_id:
        trust_map[str(group_id)] = trust
    metadata = dict(getattr(state, "metadata", {}) or {})
    if group_id is not None:
        metadata.setdefault("group_id", group_id)
    return BeliefStateSnapshot(
        run_id=run_id,
        agent_id=str(getattr(state, "agent_id", "")),
        tick=max(0, int(tick)),
        stance=str(getattr(state, "stance", "")),
        confidence=float(getattr(state, "confidence", 0.5) or 0.5),
        trust_map=trust_map,
        memory_window=list(getattr(state, "memory_window", []) or []),
        group_id=group_id,
        metadata=metadata,
    )


def social_trace_bundles_from_traces(
    *,
    run_id: str,
    traces: Iterable[NormalizedSocialTrace],
) -> list[SocialTraceBundle]:
    grouped: dict[str, list[NormalizedSocialTrace]] = defaultdict(list)
    for trace in traces:
        grouped[trace.platform].append(trace)
    bundles: list[SocialTraceBundle] = []
    for platform, items in sorted(grouped.items()):
        posts: list[dict[str, Any]] = []
        comments: list[dict[str, Any]] = []
        reactions: list[dict[str, Any]] = []
        follow_events: list[dict[str, Any]] = []
        flags: list[str] = []
        for trace in items:
            payload = trace.model_dump(mode="json")
            if trace.kind in {SocialTraceKind.post, SocialTraceKind.signal, SocialTraceKind.summary, SocialTraceKind.report, SocialTraceKind.action}:
                posts.append(payload)
            elif trace.kind in {SocialTraceKind.comment, SocialTraceKind.reply}:
                comments.append(payload)
            elif trace.kind in {SocialTraceKind.quote, SocialTraceKind.belief_shift}:
                reactions.append(payload)
            elif trace.kind == SocialTraceKind.intervention:
                follow_events.append(payload)
            else:
                posts.append(payload)
        if not posts:
            flags.append("posts_missing")
        if not comments:
            flags.append("comments_missing")
        if not reactions:
            flags.append("reactions_missing")
        if not follow_events:
            flags.append("follow_events_missing")
        bundles.append(
            SocialTraceBundle(
                run_id=run_id,
                platform=platform,
                posts=posts,
                comments=comments,
                reactions=reactions,
                follow_events=follow_events,
                trace_quality_flags=flags,
                metadata={"trace_count": len(items)},
            )
        )
    return bundles
