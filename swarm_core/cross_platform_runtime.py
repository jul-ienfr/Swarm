from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .belief_state import BeliefState, dominant_stance
from .cross_platform_simulation import CrossPlatformSimulationReport, CrossPlatformSimulator
from .normalized_social_traces import (
    NormalizedSocialTrace,
    SocialTraceAggregate,
    SocialTraceKind,
    score_social_sentiment,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _preview(value: str, *, limit: int = 180) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _dedupe(values: Iterable[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _unique_platforms(platforms: Iterable[str]) -> list[str]:
    cleaned = [_text(item).lower() for item in platforms if _text(item)]
    return _dedupe(cleaned) or ["reddit", "twitter"]


def _extract_probability_like_value(payload: Any) -> float | None:
    if payload is None:
        return None
    if isinstance(payload, bool):
        return float(payload)
    if isinstance(payload, (int, float)):
        value = float(payload)
        if 0.0 <= value <= 1.0:
            return value
        if 1.0 < value <= 100.0:
            return value / 100.0
        return _clamp(value)
    if isinstance(payload, str):
        text = payload.strip().replace("%", "")
        try:
            value = float(text)
        except ValueError:
            return None
        if 0.0 <= value <= 1.0:
            return value
        if 1.0 < value <= 100.0:
            return value / 100.0
        return _clamp(value)
    return None


def _walk_numeric_candidates(payload: Any, *, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], float]]:
    candidates: list[tuple[tuple[str, ...], float]] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key).lower()
            nested_path = (*path, key_text)
            numeric = _extract_probability_like_value(value)
            if numeric is not None and key_text in {
                "probability",
                "chance",
                "likelihood",
                "price",
                "midpoint",
                "fair_value",
                "fair",
                "bias",
                "sentiment",
                "confidence",
            }:
                candidates.append((nested_path, numeric))
            candidates.extend(_walk_numeric_candidates(value, path=nested_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            candidates.extend(_walk_numeric_candidates(item, path=(*path, str(index))))
    return candidates


def _extract_market_bias(market_snapshot: Mapping[str, Any] | None) -> tuple[float | None, str | None]:
    if not market_snapshot:
        return None, None
    candidates = _walk_numeric_candidates(market_snapshot)
    if not candidates:
        return None, None
    # Prefer direct probability-ish keys over nested heuristics.
    priority = {
        "probability": 0,
        "chance": 1,
        "likelihood": 2,
        "price": 3,
        "midpoint": 4,
        "fair_value": 5,
        "fair": 6,
        "bias": 7,
        "sentiment": 8,
        "confidence": 9,
    }
    candidates.sort(key=lambda item: (priority.get(item[0][-1], 99), len(item[0])))
    path, value = candidates[0]
    return _clamp(value), ".".join(path)


class CrossPlatformOrchestrationPlan(BaseModel):
    run_id: str = Field(default_factory=lambda: f"cpr_{uuid4().hex[:10]}")
    topic: str
    objective: str = ""
    platforms: list[str] = Field(default_factory=lambda: ["reddit", "twitter"])
    rounds: int = 1
    memory_window: int = 8
    trace_limit_per_platform: int = 6
    belief_limit_per_agent: int = 6
    market_keywords: list[str] = Field(default_factory=list)
    media_keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic", "objective")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return _text(value)

    @field_validator("rounds", "memory_window", "trace_limit_per_platform", "belief_limit_per_agent")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        return max(1, int(value))

    @model_validator(mode="after")
    def _normalize(self) -> "CrossPlatformOrchestrationPlan":
        self.platforms = _unique_platforms(self.platforms)
        self.market_keywords = _dedupe(self.market_keywords)
        self.media_keywords = _dedupe(self.media_keywords)
        self.metadata = _json_safe(dict(self.metadata))
        return self

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CrossPlatformBeliefSnapshot(BaseModel):
    agent_id: str
    platform: str | None = None
    stance: str = "observing"
    confidence: float = 0.5
    trust: float = 0.5
    memory_window: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(default_factory=list)
    recent_platforms: list[str] = Field(default_factory=list)
    signal_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("confidence", "trust")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return _clamp(value)

    @model_validator(mode="after")
    def _normalize(self) -> "CrossPlatformBeliefSnapshot":
        self.agent_id = _text(self.agent_id)
        self.platform = _text(self.platform) or None
        self.stance = _text(self.stance) or "observing"
        self.memory_window = _dedupe(self.memory_window, limit=max(1, len(self.memory_window) or 6))
        self.source_trace_ids = _dedupe(self.source_trace_ids)
        self.recent_platforms = _dedupe(self.recent_platforms)
        self.metadata = _json_safe(dict(self.metadata))
        return self

    @classmethod
    def from_belief_state(cls, state: BeliefState, *, platform: str | None = None) -> "CrossPlatformBeliefSnapshot":
        return cls(
            agent_id=state.agent_id,
            platform=platform or state.metadata.get("platform"),
            stance=state.stance,
            confidence=state.confidence,
            trust=state.trust,
            memory_window=list(state.memory_window),
            metadata=dict(state.metadata),
            updated_at=state.updated_at,
        )

    def absorb_trace(self, trace: NormalizedSocialTrace, *, memory_window: int = 8) -> None:
        self.signal_count += 1
        self.source_trace_ids = _dedupe([trace.trace_id, *self.source_trace_ids], limit=12)
        self.recent_platforms = _dedupe([trace.platform, *self.recent_platforms], limit=6)
        preview = _preview(trace.content, limit=180)
        if preview:
            self.memory_window = _dedupe([preview, *self.memory_window], limit=max(1, memory_window))
        if trace.sentiment >= 0.25:
            self.confidence = _clamp(self.confidence + min(0.08, 0.03 + trace.score * 0.02))
            if self.stance in {"observing", "neutral", ""}:
                self.stance = "supportive"
        elif trace.sentiment <= -0.25:
            self.trust = _clamp(self.trust - min(0.08, 0.03 + trace.score * 0.02))
            if self.stance in {"observing", "neutral", ""}:
                self.stance = "watchful"
        else:
            self.confidence = _clamp(self.confidence + 0.01 * trace.score)
        trace_kind = trace.kind.value if isinstance(trace.kind, SocialTraceKind) else str(trace.kind)
        self.metadata.setdefault("trace_kinds", [])
        trace_kinds = self.metadata.get("trace_kinds")
        if isinstance(trace_kinds, list):
            trace_kinds[:] = _dedupe([trace_kind, *trace_kinds], limit=8)
        self.updated_at = _utc_now()

    def prompt_block(self) -> str:
        lines = [
            "[Belief snapshot]",
            f"Agent: {self.agent_id}",
            f"Platform: {self.platform or 'multi-platform'}",
            f"Stance: {self.stance}",
            f"Confidence: {self.confidence:.2f}",
            f"Trust: {self.trust:.2f}",
            f"- Memory: {' | '.join(self.memory_window[:4]) if self.memory_window else 'none yet'}",
            f"- Recent platforms: {' | '.join(self.recent_platforms[:3]) if self.recent_platforms else 'none yet'}",
            f"- Signals seen: {self.signal_count}",
        ]
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CrossPlatformActionRecord(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    platform: str
    actor_id: str = ""
    kind: str = "signal"
    stage: str = "running"
    title: str = ""
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    round_index: int | None = None
    source_trace_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _normalize(self) -> "CrossPlatformActionRecord":
        self.platform = _text(self.platform) or "unknown"
        self.actor_id = _text(self.actor_id)
        self.kind = _text(self.kind) or "signal"
        self.stage = _text(self.stage) or "running"
        self.title = _text(self.title)
        self.summary = _text(self.summary)
        self.tags = _dedupe(self.tags)
        self.details = _json_safe(dict(self.details))
        if self.round_index is not None:
            self.round_index = int(self.round_index)
        return self

    @classmethod
    def from_trace(cls, trace: NormalizedSocialTrace) -> "CrossPlatformActionRecord":
        return cls(
            platform=trace.platform,
            actor_id=trace.actor_id,
            kind=trace.kind.value,
            stage="running" if trace.kind != SocialTraceKind.intervention else "attention",
            title=_preview(trace.content, limit=80),
            summary=_preview(trace.content, limit=240),
            details={
                "content": trace.content,
                "score": trace.score,
                "sentiment": trace.sentiment,
                "thread_id": trace.thread_id,
                "group_id": trace.group_id,
            },
            tags=list(trace.tags),
            round_index=trace.round_index,
            source_trace_id=trace.trace_id,
            created_at=trace.created_at,
        )

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CrossPlatformActionLogSummary(BaseModel):
    record_count: int = 0
    platform_counts: dict[str, int] = Field(default_factory=dict)
    actor_counts: dict[str, int] = Field(default_factory=dict)
    kind_counts: dict[str, int] = Field(default_factory=dict)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    recent_actions: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    updated_at: datetime = Field(default_factory=_utc_now)

    @classmethod
    def from_traces(cls, traces: Iterable[NormalizedSocialTrace], *, summary: str | None = None) -> "CrossPlatformActionLogSummary":
        trace_list = list(traces)
        platform_counts = Counter(trace.platform for trace in trace_list)
        actor_counts = Counter(trace.actor_id for trace in trace_list if trace.actor_id)
        kind_counts = Counter(trace.kind.value for trace in trace_list)
        stage_counts = Counter("intervention" if trace.kind == SocialTraceKind.intervention else "running" for trace in trace_list)
        recent_actions = [
            {
                "platform": trace.platform,
                "actor_id": trace.actor_id,
                "kind": trace.kind.value,
                "stage": "intervention" if trace.kind == SocialTraceKind.intervention else "running",
                "summary": _preview(trace.content, limit=200),
                "round_index": trace.round_index,
                "trace_id": trace.trace_id,
            }
            for trace in trace_list[-5:]
        ]
        derived_summary = summary or (
            f"Derived from {len(trace_list)} traces across {len(platform_counts)} platforms."
            if trace_list
            else "No cross-platform actions recorded."
        )
        return cls(
            record_count=len(trace_list),
            platform_counts=dict(platform_counts),
            actor_counts=dict(actor_counts),
            kind_counts=dict(kind_counts),
            stage_counts=dict(stage_counts),
            recent_actions=recent_actions,
            summary=derived_summary,
        )


class CrossPlatformMemoryBridgeReport(BaseModel):
    topic: str = ""
    objective: str = ""
    trace_count: int = 0
    round_counts: dict[str, int] = Field(default_factory=dict)
    platform_counts: dict[str, int] = Field(default_factory=dict)
    belief_count: int = 0
    belief_summaries: dict[str, dict[str, Any]] = Field(default_factory=dict)
    recent_traces: list[dict[str, Any]] = Field(default_factory=list)
    ancient_summary: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utc_now)


class CrossPlatformMarketMediaBridgeReport(BaseModel):
    topic: str = ""
    objective: str = ""
    social_trace_aggregate: SocialTraceAggregate = Field(default_factory=SocialTraceAggregate)
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    market_bias: float | None = None
    market_bias_path: str | None = None
    social_bias: float | None = None
    alignment_score: float | None = None
    divergence_score: float | None = None
    attention_score: float = 0.0
    narrative: str = ""
    watchpoints: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class CrossPlatformOrchestrationReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"cpor_{uuid4().hex[:12]}")
    plan: CrossPlatformOrchestrationPlan
    trace_aggregate: SocialTraceAggregate = Field(default_factory=SocialTraceAggregate)
    memory_report: CrossPlatformMemoryBridgeReport
    action_report: CrossPlatformActionLogSummary
    market_media_report: CrossPlatformMarketMediaBridgeReport
    belief_count: int = 0
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class CrossPlatformActionLog:
    """Append-only JSONL log for cross-platform actions and signals."""

    def __init__(self, *, output_path: str | Path | None = None) -> None:
        self.output_path = Path(output_path) if output_path is not None else None
        self._records: list[CrossPlatformActionRecord] = []
        if self.output_path is not None:
            if self.output_path.suffix != ".jsonl":
                self.output_path = self.output_path / "cross_platform_actions.jsonl"
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._records = self._load()

    def append(self, record: CrossPlatformActionRecord) -> CrossPlatformActionRecord:
        self._records.append(record)
        self._records.sort(key=lambda item: item.created_at)
        if self.output_path is not None:
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return record

    def record_action(
        self,
        *,
        platform: str,
        actor_id: str = "",
        kind: str = "signal",
        stage: str = "running",
        title: str = "",
        summary: str = "",
        details: dict[str, Any] | None = None,
        tags: Iterable[str] | None = None,
        round_index: int | None = None,
        source_trace_id: str | None = None,
    ) -> CrossPlatformActionRecord:
        return self.append(
            CrossPlatformActionRecord(
                platform=platform,
                actor_id=actor_id,
                kind=kind,
                stage=stage,
                title=title,
                summary=summary,
                details=dict(details or {}),
                tags=list(tags or []),
                round_index=round_index,
                source_trace_id=source_trace_id,
            )
        )

    def record_trace(self, trace: NormalizedSocialTrace) -> CrossPlatformActionRecord:
        return self.record_action(
            platform=trace.platform,
            actor_id=trace.actor_id,
            kind=trace.kind.value,
            stage="intervention" if trace.kind == SocialTraceKind.intervention else "running",
            title=_preview(trace.content, limit=80),
            summary=_preview(trace.content, limit=240),
            details={
                "trace_id": trace.trace_id,
                "content": trace.content,
                "sentiment": trace.sentiment,
                "score": trace.score,
                "source_uri": trace.source_uri,
            },
            tags=trace.tags,
            round_index=trace.round_index,
            source_trace_id=trace.trace_id,
        )

    def list(
        self,
        *,
        platform: str | None = None,
        actor_id: str | None = None,
        kind: str | None = None,
        stage: str | None = None,
        limit: int | None = None,
    ) -> list[CrossPlatformActionRecord]:
        matches = list(self._records)
        if platform is not None:
            matches = [record for record in matches if record.platform == platform]
        if actor_id is not None:
            matches = [record for record in matches if record.actor_id == actor_id]
        if kind is not None:
            matches = [record for record in matches if record.kind == kind]
        if stage is not None:
            matches = [record for record in matches if record.stage == stage]
        if limit is not None:
            matches = matches[-int(limit) :]
        return matches

    def summary(self) -> CrossPlatformActionLogSummary:
        if not self._records:
            return CrossPlatformActionLogSummary(summary="No cross-platform actions recorded.")
        platform_counts = Counter(record.platform for record in self._records)
        actor_counts = Counter(record.actor_id for record in self._records if record.actor_id)
        kind_counts = Counter(record.kind for record in self._records)
        stage_counts = Counter(record.stage for record in self._records)
        recent = [record.snapshot() for record in self._records[-5:]]
        summary = (
            f"{len(self._records)} actions across {len(platform_counts)} platforms. "
            f"Top platform: {platform_counts.most_common(1)[0][0]}."
        )
        return CrossPlatformActionLogSummary(
            record_count=len(self._records),
            platform_counts=dict(platform_counts),
            actor_counts=dict(actor_counts),
            kind_counts=dict(kind_counts),
            stage_counts=dict(stage_counts),
            recent_actions=recent,
            summary=summary,
        )

    def reload(self) -> list[CrossPlatformActionRecord]:
        self._records = self._load()
        return self._records

    def _load(self) -> list[CrossPlatformActionRecord]:
        if self.output_path is None or not self.output_path.exists():
            return []
        records: list[CrossPlatformActionRecord] = []
        for raw_line in self.output_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            records.append(CrossPlatformActionRecord.model_validate_json(raw_line))
        return records


@dataclass(slots=True)
class CrossPlatformMemoryBridge:
    topic: str
    objective: str
    memory_window: int = 8
    plan_id: str | None = None
    beliefs: dict[str, CrossPlatformBeliefSnapshot] = field(default_factory=dict)
    trace_history: list[NormalizedSocialTrace] = field(default_factory=list)
    round_trace_ids: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))
    ancient_summary: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=_utc_now)

    def ingest_beliefs(self, beliefs: Iterable[BeliefState], *, platform: str | None = None) -> None:
        for state in beliefs:
            snapshot = self.beliefs.get(state.agent_id)
            if snapshot is None:
                snapshot = CrossPlatformBeliefSnapshot.from_belief_state(state, platform=platform)
                self.beliefs[state.agent_id] = snapshot
            else:
                snapshot.stance = state.stance
                snapshot.confidence = state.confidence
                snapshot.trust = state.trust
                snapshot.memory_window = _dedupe([*state.memory_window, *snapshot.memory_window], limit=8)
                snapshot.metadata.update(_json_safe(dict(state.metadata)))
                if platform and snapshot.platform is None:
                    snapshot.platform = platform
                snapshot.updated_at = _utc_now()
        self.updated_at = _utc_now()

    def ingest_trace(self, trace: NormalizedSocialTrace) -> CrossPlatformBeliefSnapshot | None:
        self.trace_history.append(trace)
        if trace.round_index is not None:
            self.round_trace_ids[int(trace.round_index)].append(trace.trace_id)
        if trace.actor_id:
            snapshot = self.beliefs.get(trace.actor_id)
            if snapshot is None:
                snapshot = CrossPlatformBeliefSnapshot(
                    agent_id=trace.actor_id,
                    platform=trace.platform,
                    stance=_infer_stance_from_trace(trace),
                    confidence=0.5,
                    trust=0.5,
                    memory_window=[],
                    source_trace_ids=[],
                    recent_platforms=[],
                )
                self.beliefs[trace.actor_id] = snapshot
            snapshot.absorb_trace(trace, memory_window=self.memory_window)
            self._compact_ancient_history()
            self.updated_at = _utc_now()
            return snapshot
        self._compact_ancient_history()
        self.updated_at = _utc_now()
        return None

    def ingest_traces(self, traces: Iterable[NormalizedSocialTrace]) -> list[CrossPlatformBeliefSnapshot | None]:
        return [self.ingest_trace(trace) for trace in traces]

    def build_agent_snapshot(self, agent_id: str) -> dict[str, Any]:
        snapshot = self.beliefs.get(agent_id)
        if snapshot is None:
            return {"agent_id": agent_id, "found": False}
        payload = snapshot.snapshot()
        payload["found"] = True
        payload["recent_trace_ids"] = list(snapshot.source_trace_ids[:8])
        payload["recent_platforms"] = list(snapshot.recent_platforms[:4])
        return payload

    def build_round_snapshot(self, round_index: int) -> dict[str, Any]:
        traces = [trace for trace in self.trace_history if trace.round_index == round_index]
        platform_counts = Counter(trace.platform for trace in traces)
        kind_counts = Counter(trace.kind.value for trace in traces)
        return {
            "topic": self.topic,
            "objective": self.objective,
            "round_index": round_index,
            "trace_count": len(traces),
            "platform_counts": dict(platform_counts),
            "kind_counts": dict(kind_counts),
            "trace_ids": [trace.trace_id for trace in traces],
            "previews": [_preview(trace.content, limit=180) for trace in traces[:5]],
            "belief_lenses": {agent_id: belief.snapshot() for agent_id, belief in self.beliefs.items()},
        }

    def build_report(self) -> CrossPlatformMemoryBridgeReport:
        platform_counts = Counter(trace.platform for trace in self.trace_history)
        round_counts = Counter(str(trace.round_index) for trace in self.trace_history if trace.round_index is not None)
        recent_traces = [
            {
                "trace_id": trace.trace_id,
                "platform": trace.platform,
                "actor_id": trace.actor_id,
                "kind": trace.kind.value,
                "round_index": trace.round_index,
                "preview": _preview(trace.content, limit=180),
                "sentiment": trace.sentiment,
                "score": trace.score,
            }
            for trace in self.trace_history[-6:]
        ]
        belief_summaries = {
            agent_id: {
                "platform": snapshot.platform,
                "stance": snapshot.stance,
                "confidence": snapshot.confidence,
                "trust": snapshot.trust,
                "memory_window": list(snapshot.memory_window[:4]),
                "source_trace_ids": list(snapshot.source_trace_ids[:4]),
                "signal_count": snapshot.signal_count,
            }
            for agent_id, snapshot in self.beliefs.items()
        }
        summary = (
            f"{len(self.trace_history)} traces across {len(platform_counts)} platforms "
            f"for {len(self.beliefs)} belief snapshots."
        )
        return CrossPlatformMemoryBridgeReport(
            topic=self.topic,
            objective=self.objective,
            trace_count=len(self.trace_history),
            round_counts=dict(round_counts),
            platform_counts=dict(platform_counts),
            belief_count=len(self.beliefs),
            belief_summaries=belief_summaries,
            recent_traces=recent_traces,
            ancient_summary=list(self.ancient_summary),
            summary=summary,
            metadata={
                "memory_window": self.memory_window,
                "round_count": len({trace.round_index for trace in self.trace_history if trace.round_index is not None}),
                "plan_id": self.plan_id,
            },
        )

    def snapshot(self) -> dict[str, Any]:
        report = self.build_report()
        return report.model_dump(mode="json")

    def _compact_ancient_history(self) -> None:
        if len(self.trace_history) <= self.memory_window:
            return
        compaction_floor = max(0, len(self.trace_history) - self.memory_window)
        older = self.trace_history[:compaction_floor]
        if not older:
            return
        recent_platforms = _dedupe((trace.platform for trace in older[-4:]), limit=4)
        recent_agents = _dedupe((trace.actor_id for trace in older[-4:] if trace.actor_id), limit=4)
        self.ancient_summary = [
            f"Compacted {len(older)} older traces.",
            f"Platforms: {' | '.join(recent_platforms) if recent_platforms else 'none'}",
            f"Agents: {' | '.join(recent_agents) if recent_agents else 'none'}",
        ]


class CrossPlatformMarketMediaBridge:
    @staticmethod
    def build_report(
        traces: Iterable[NormalizedSocialTrace],
        *,
        topic: str = "",
        objective: str = "",
        market_snapshot: Mapping[str, Any] | None = None,
        market_keywords: Iterable[str] | None = None,
        media_keywords: Iterable[str] | None = None,
        attention_floor: float = 0.4,
    ) -> CrossPlatformMarketMediaBridgeReport:
        trace_list = list(traces)
        aggregate = SocialTraceAggregate(
            trace_count=len(trace_list),
            platform_counts=dict(Counter(trace.platform for trace in trace_list)),
            kind_counts=dict(Counter(trace.kind.value for trace in trace_list)),
            actor_counts=dict(Counter(trace.actor_id for trace in trace_list if trace.actor_id)),
            average_sentiment=mean(trace.sentiment for trace in trace_list) if trace_list else 0.0,
            average_score=mean(trace.score for trace in trace_list) if trace_list else 0.0,
            top_tags=[tag for tag, _ in Counter(tag for trace in trace_list for tag in trace.tags).most_common(5)],
            summary=(
                f"{len(trace_list)} traces across {len({trace.platform for trace in trace_list})} platforms."
                if trace_list
                else "No social traces recorded."
            ),
            metadata={
                "topic": topic,
                "objective": objective,
            },
        )
        market_bias, market_bias_path = _extract_market_bias(market_snapshot)
        social_bias = aggregate.average_sentiment if trace_list else None
        divergence_score = None
        alignment_score = None
        if market_bias is not None and social_bias is not None:
            divergence_score = round(abs(social_bias - market_bias), 4)
            alignment_score = round(1.0 - divergence_score, 4)
        attention_score = _clamp(
            len(trace_list) / max(1, (len(aggregate.platform_counts) or 1) * 4),
            0.0,
            1.0,
        )
        keywords = _dedupe([*(market_keywords or []), *(media_keywords or [])])
        watchpoints = _build_watchpoints(trace_list, keywords=keywords)
        recommendations = _build_recommendations(
            aggregate=aggregate,
            market_bias=market_bias,
            social_bias=social_bias,
            divergence_score=divergence_score,
            attention_score=attention_score,
            attention_floor=attention_floor,
        )
        narrative = _build_market_media_narrative(
            topic=topic,
            objective=objective,
            aggregate=aggregate,
            market_bias=market_bias,
            social_bias=social_bias,
            divergence_score=divergence_score,
            attention_score=attention_score,
        )
        return CrossPlatformMarketMediaBridgeReport(
            topic=topic,
            objective=objective,
            social_trace_aggregate=aggregate,
            market_snapshot=_json_safe(dict(market_snapshot or {})),
            market_bias=market_bias,
            market_bias_path=market_bias_path,
            social_bias=social_bias,
            alignment_score=alignment_score,
            divergence_score=divergence_score,
            attention_score=attention_score,
            narrative=narrative,
            watchpoints=watchpoints,
            recommendations=recommendations,
            metadata={
                "keyword_count": len(keywords),
                "attention_floor": attention_floor,
            },
        )


@dataclass(slots=True)
class CrossPlatformOrchestrator:
    plan: CrossPlatformOrchestrationPlan
    action_log: CrossPlatformActionLog | None = None
    memory_bridge: CrossPlatformMemoryBridge = field(init=False)
    _traces: list[NormalizedSocialTrace] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.memory_bridge = CrossPlatformMemoryBridge(
            topic=self.plan.topic,
            objective=self.plan.objective,
            memory_window=self.plan.memory_window,
            plan_id=self.plan.run_id,
        )

    def ingest_beliefs(self, beliefs: Iterable[BeliefState]) -> None:
        self.memory_bridge.ingest_beliefs(beliefs)

    def ingest_traces(self, traces: Iterable[NormalizedSocialTrace]) -> None:
        for trace in traces:
            self._traces.append(trace)
            self.memory_bridge.ingest_trace(trace)
            if self.action_log is not None:
                self.action_log.record_trace(trace)

    def record_action(
        self,
        *,
        platform: str,
        actor_id: str = "",
        kind: str = "signal",
        stage: str = "running",
        title: str = "",
        summary: str = "",
        details: dict[str, Any] | None = None,
        tags: Iterable[str] | None = None,
        round_index: int | None = None,
        source_trace_id: str | None = None,
    ) -> CrossPlatformActionRecord | None:
        if self.action_log is None:
            return None
        return self.action_log.record_action(
            platform=platform,
            actor_id=actor_id,
            kind=kind,
            stage=stage,
            title=title,
            summary=summary,
            details=details,
            tags=tags,
            round_index=round_index,
            source_trace_id=source_trace_id,
        )

    def build_report(self, *, market_snapshot: Mapping[str, Any] | None = None) -> CrossPlatformOrchestrationReport:
        memory_report = self.memory_bridge.build_report()
        market_media_report = CrossPlatformMarketMediaBridge.build_report(
            self._traces,
            topic=self.plan.topic,
            objective=self.plan.objective,
            market_snapshot=market_snapshot,
            market_keywords=self.plan.market_keywords,
            media_keywords=self.plan.media_keywords,
        )
        action_summary = (
            self.action_log.summary()
            if self.action_log is not None
            else CrossPlatformActionLogSummary.from_traces(
                self._traces,
                summary="Derived from traces because no persistent action log is configured.",
            )
        )
        trace_aggregate = market_media_report.social_trace_aggregate
        summary = _build_orchestration_summary(
            plan=self.plan,
            memory_report=memory_report,
            action_summary=action_summary,
            market_media_report=market_media_report,
        )
        return CrossPlatformOrchestrationReport(
            plan=self.plan,
            trace_aggregate=trace_aggregate,
            memory_report=memory_report,
            action_report=action_summary,
            market_media_report=market_media_report,
            belief_count=memory_report.belief_count,
            summary=summary,
            metadata={
                "trace_count": len(self._traces),
                "action_count": action_summary.record_count,
                "platform_count": len(self.plan.platforms),
            },
        )

    def build_from_simulation(
        self,
        simulation_report: CrossPlatformSimulationReport,
        *,
        beliefs: Iterable[BeliefState] | None = None,
        market_snapshot: Mapping[str, Any] | None = None,
    ) -> CrossPlatformOrchestrationReport:
        if beliefs is not None:
            self.ingest_beliefs(beliefs)
        self.ingest_traces(simulation_report.traces)
        return self.build_report(market_snapshot=market_snapshot)


def build_cross_platform_orchestration_report(
    plan: CrossPlatformOrchestrationPlan,
    *,
    beliefs: Iterable[BeliefState] | None = None,
    traces: Iterable[NormalizedSocialTrace] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    action_log: CrossPlatformActionLog | None = None,
) -> CrossPlatformOrchestrationReport:
    orchestrator = CrossPlatformOrchestrator(plan=plan, action_log=action_log)
    if beliefs is not None:
        orchestrator.ingest_beliefs(beliefs)
    if traces is not None:
        orchestrator.ingest_traces(traces)
    return orchestrator.build_report(market_snapshot=market_snapshot)


def build_cross_platform_orchestration_report_from_simulation(
    plan: CrossPlatformOrchestrationPlan,
    simulation_report: CrossPlatformSimulationReport,
    *,
    beliefs: Iterable[BeliefState] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    action_log: CrossPlatformActionLog | None = None,
) -> CrossPlatformOrchestrationReport:
    orchestrator = CrossPlatformOrchestrator(plan=plan, action_log=action_log)
    return orchestrator.build_from_simulation(
        simulation_report,
        beliefs=beliefs,
        market_snapshot=market_snapshot,
    )


def _infer_stance_from_trace(trace: NormalizedSocialTrace) -> str:
    if trace.sentiment >= 0.25:
        return "supportive"
    if trace.sentiment <= -0.25:
        return "skeptical"
    if trace.kind == SocialTraceKind.intervention:
        return "watchful"
    content = trace.content.lower()
    if "risk" in content or "delay" in content or "concern" in content:
        return "watchful"
    return "observing"


def _build_watchpoints(traces: list[NormalizedSocialTrace], *, keywords: list[str]) -> list[str]:
    watchpoints: list[str] = []
    if not traces:
        return watchpoints
    all_text = " ".join(trace.content.lower() for trace in traces)
    for keyword in keywords[:8]:
        if keyword and keyword.lower() in all_text:
            watchpoints.append(f"Keyword watch: {keyword}")
    sentiment = mean(trace.sentiment for trace in traces)
    if sentiment <= -0.25:
        watchpoints.append("Downside tone persists across social traces.")
    elif sentiment >= 0.25:
        watchpoints.append("Social tone is constructive and supportive.")
    if any(trace.kind == SocialTraceKind.intervention for trace in traces):
        watchpoints.append("Intervention traces indicate an explicit gate or correction.")
    return _dedupe(watchpoints, limit=6)


def _build_recommendations(
    *,
    aggregate: SocialTraceAggregate,
    market_bias: float | None,
    social_bias: float | None,
    divergence_score: float | None,
    attention_score: float,
    attention_floor: float,
) -> list[str]:
    recommendations: list[str] = []
    if divergence_score is not None and divergence_score >= 0.25:
        recommendations.append("Reconcile market and media readings before sizing exposure.")
    if attention_score < attention_floor:
        recommendations.append("Insufficient attention density: wait for more cross-platform confirmation.")
    if aggregate.trace_count and aggregate.average_sentiment <= -0.25:
        recommendations.append("Treat the signal as defensive until sentiment stabilises.")
    elif aggregate.trace_count and aggregate.average_sentiment >= 0.25:
        recommendations.append("Use the social signal as supportive evidence, not sole authority.")
    if market_bias is None or social_bias is None:
        recommendations.append("Missing market or social anchor: keep the bridge advisory only.")
    return _dedupe(recommendations, limit=5)


def _build_market_media_narrative(
    *,
    topic: str,
    objective: str,
    aggregate: SocialTraceAggregate,
    market_bias: float | None,
    social_bias: float | None,
    divergence_score: float | None,
    attention_score: float,
) -> str:
    parts = [
        f"Cross-platform view for {topic or 'the topic'}",
        f"objective: {objective or 'none'}",
        f"{aggregate.trace_count} traces across {len(aggregate.platform_counts)} platforms",
    ]
    if market_bias is not None:
        parts.append(f"market_bias={market_bias:.2f}")
    if social_bias is not None:
        parts.append(f"social_bias={social_bias:.2f}")
    if divergence_score is not None:
        parts.append(f"divergence={divergence_score:.2f}")
    parts.append(f"attention={attention_score:.2f}")
    return ". ".join(parts) + "."


def _build_orchestration_summary(
    *,
    plan: CrossPlatformOrchestrationPlan,
    memory_report: CrossPlatformMemoryBridgeReport,
    action_summary: CrossPlatformActionLogSummary,
    market_media_report: CrossPlatformMarketMediaBridgeReport,
) -> str:
    parts = [
        f"Plan {plan.run_id} on {plan.topic}",
        f"{memory_report.trace_count} traces / {memory_report.belief_count} belief snapshots",
        f"{action_summary.record_count} logged actions",
    ]
    if market_media_report.alignment_score is not None:
        parts.append(f"alignment={market_media_report.alignment_score:.2f}")
    elif market_media_report.social_bias is not None:
        parts.append(f"social_bias={market_media_report.social_bias:.2f}")
    if memory_report.ancient_summary:
        parts.append("ancient memory compacted")
    return "; ".join(parts)
