from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


DEFAULT_SOCIAL_TRACE_PATH = Path(__file__).resolve().parent.parent / "data" / "social_traces.json"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in str(text).lower().replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = str(item).strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


class SocialTraceKind(str, Enum):
    post = "post"
    reply = "reply"
    quote = "quote"
    comment = "comment"
    signal = "signal"
    intervention = "intervention"
    summary = "summary"
    belief_shift = "belief_shift"
    action = "action"
    report = "report"


class NormalizedSocialTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:12]}")
    platform: str
    actor_id: str = ""
    kind: SocialTraceKind = SocialTraceKind.signal
    content: str = ""
    target_id: str | None = None
    thread_id: str | None = None
    group_id: str | None = None
    round_index: int | None = None
    sentiment: float = 0.0
    score: float = 0.5
    tags: list[str] = Field(default_factory=list)
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("sentiment")
    @classmethod
    def _clamp_sentiment(cls, value: float) -> float:
        return _clamp(value, -1.0, 1.0)

    @field_validator("score")
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return _clamp(value, 0.0, 1.0)


class SocialTraceAggregate(BaseModel):
    trace_count: int = 0
    platform_counts: dict[str, int] = Field(default_factory=dict)
    kind_counts: dict[str, int] = Field(default_factory=dict)
    actor_counts: dict[str, int] = Field(default_factory=dict)
    average_sentiment: float = 0.0
    average_score: float = 0.0
    top_tags: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedSocialTraceStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_SOCIAL_TRACE_PATH)
        if self.path.suffix != ".json":
            self.path = self.path / "social_traces.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._traces: list[NormalizedSocialTrace] = self._load()

    def append(self, trace: NormalizedSocialTrace) -> NormalizedSocialTrace:
        self._traces.append(trace)
        self._traces.sort(key=lambda item: item.created_at)
        self.save()
        return trace

    def extend(self, traces: Iterable[NormalizedSocialTrace]) -> list[NormalizedSocialTrace]:
        recorded = [self.append(trace) for trace in traces]
        return recorded

    def list(
        self,
        *,
        platform: str | None = None,
        actor_id: str | None = None,
        kind: SocialTraceKind | str | None = None,
        limit: int | None = None,
    ) -> list[NormalizedSocialTrace]:
        matches = list(self._traces)
        if platform is not None:
            matches = [trace for trace in matches if trace.platform == platform]
        if actor_id is not None:
            matches = [trace for trace in matches if trace.actor_id == actor_id]
        if kind is not None:
            resolved = kind if isinstance(kind, SocialTraceKind) else SocialTraceKind(str(kind))
            matches = [trace for trace in matches if trace.kind == resolved]
        if limit is not None:
            matches = matches[-int(limit) :]
        return matches

    def search(self, query: str, *, limit: int = 5) -> list[NormalizedSocialTrace]:
        terms = set(_tokenize(query))
        if not terms:
            return self.list(limit=limit)
        scored: list[tuple[float, NormalizedSocialTrace]] = []
        for trace in self._traces:
            haystack = set(_tokenize(trace.content)) | set(_tokenize(trace.platform)) | set(_tokenize(trace.actor_id))
            haystack |= set(trace.tags)
            overlap = len(terms & haystack)
            if overlap == 0:
                continue
            score = overlap + abs(trace.sentiment) + trace.score
            scored.append((score, trace))
        scored.sort(key=lambda item: (item[0], item[1].created_at.timestamp()), reverse=True)
        return [trace for _, trace in scored[:limit]]

    def aggregate(self) -> SocialTraceAggregate:
        if not self._traces:
            return SocialTraceAggregate(summary="No social traces recorded.")
        platform_counts = Counter(trace.platform for trace in self._traces)
        kind_counts = Counter(trace.kind.value for trace in self._traces)
        actor_counts = Counter(trace.actor_id for trace in self._traces if trace.actor_id)
        tag_counts = Counter(tag for trace in self._traces for tag in trace.tags)
        summary = (
            f"{len(self._traces)} traces across {len(platform_counts)} platforms. "
            f"Top platform: {platform_counts.most_common(1)[0][0]}."
        )
        return SocialTraceAggregate(
            trace_count=len(self._traces),
            platform_counts=dict(platform_counts),
            kind_counts=dict(kind_counts),
            actor_counts=dict(actor_counts),
            average_sentiment=mean(trace.sentiment for trace in self._traces),
            average_score=mean(trace.score for trace in self._traces),
            top_tags=[tag for tag, _ in tag_counts.most_common(5)],
            summary=summary,
        )

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps([trace.model_dump(mode="json") for trace in self._traces], indent=2),
            encoding="utf-8",
        )
        return target

    def reload(self) -> list[NormalizedSocialTrace]:
        self._traces = self._load()
        return self._traces

    def _load(self) -> list[NormalizedSocialTrace]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [NormalizedSocialTrace.model_validate(item) for item in payload]


def infer_trace_kind(content: str) -> SocialTraceKind:
    lowered = str(content).lower()
    if "intervention" in lowered:
        return SocialTraceKind.intervention
    if "reply" in lowered:
        return SocialTraceKind.reply
    if "quote" in lowered:
        return SocialTraceKind.quote
    if "summary" in lowered:
        return SocialTraceKind.summary
    if "belief" in lowered or "stance" in lowered:
        return SocialTraceKind.belief_shift
    if "action" in lowered:
        return SocialTraceKind.action
    if "report" in lowered:
        return SocialTraceKind.report
    if "comment" in lowered:
        return SocialTraceKind.comment
    return SocialTraceKind.post


def score_social_sentiment(text: str) -> float:
    lowered = str(text).lower()
    positive = {
        "support",
        "good",
        "strong",
        "adopt",
        "confident",
        "stable",
        "positive",
        "win",
        "favorable",
        "cautious rollout",
    }
    negative = {
        "risk",
        "delay",
        "outage",
        "fail",
        "uncertain",
        "weak",
        "negative",
        "loss",
        "disrupt",
        "panic",
    }
    score = 0.0
    for token in positive:
        if token in lowered:
            score += 0.25
    for token in negative:
        if token in lowered:
            score -= 0.2
    return _clamp(score, -1.0, 1.0)


def infer_trace_tags(content: str, *, platform: str | None = None, kind: SocialTraceKind | None = None) -> list[str]:
    tags: list[str] = []
    if platform:
        tags.append(str(platform).lower())
    if kind:
        tags.append(kind.value)
    tags.extend(_tokenize(content))
    return _unique(tags)[:8]


def normalize_social_trace(
    raw: dict[str, Any] | str,
    *,
    platform: str,
    actor_id: str = "",
    kind: SocialTraceKind | str | None = None,
    target_id: str | None = None,
    thread_id: str | None = None,
    group_id: str | None = None,
    round_index: int | None = None,
    score: float | None = None,
    sentiment: float | None = None,
    tags: Iterable[str] | None = None,
    source_uri: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedSocialTrace:
    payload = dict(raw) if isinstance(raw, dict) else {"content": str(raw)}
    content = str(payload.get("content", payload.get("text", raw if isinstance(raw, str) else "")))
    resolved_kind = kind if isinstance(kind, SocialTraceKind) else SocialTraceKind(str(kind)) if kind else infer_trace_kind(content)
    resolved_score = score if score is not None else payload.get("score", payload.get("salience", 0.5))
    resolved_sentiment = sentiment if sentiment is not None else payload.get("sentiment", score_social_sentiment(content))
    resolved_tags = _unique([*(tags or []), *payload.get("tags", []), *infer_trace_tags(content, platform=platform, kind=resolved_kind)])
    return NormalizedSocialTrace(
        platform=platform,
        actor_id=actor_id or str(payload.get("actor_id", "")),
        kind=resolved_kind,
        content=content,
        target_id=target_id if target_id is not None else payload.get("target_id"),
        thread_id=thread_id if thread_id is not None else payload.get("thread_id"),
        group_id=group_id if group_id is not None else payload.get("group_id"),
        round_index=round_index if round_index is not None else payload.get("round_index"),
        score=float(resolved_score),
        sentiment=float(resolved_sentiment),
        tags=resolved_tags,
        source_uri=source_uri if source_uri is not None else payload.get("source_uri"),
        metadata=dict(metadata or payload.get("metadata", {})),
        created_at=payload.get("created_at", datetime.now(timezone.utc)),
    )


def normalize_social_traces(
    traces: Iterable[dict[str, Any] | str],
    *,
    platform: str,
    actor_id: str = "",
    kind: SocialTraceKind | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[NormalizedSocialTrace]:
    return [
        normalize_social_trace(item, platform=platform, actor_id=actor_id, kind=kind, metadata=metadata)
        for item in traces
    ]
