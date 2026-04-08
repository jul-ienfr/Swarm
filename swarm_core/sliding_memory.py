from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


DEFAULT_SLIDING_MEMORY_PATH = Path(__file__).resolve().parent.parent / "data" / "sliding_memory"
DEFAULT_SLIDING_MEMORY_CAPACITY = 12


def _clamp_capacity(value: int) -> int:
    return max(0, int(value))


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in str(text).lower().replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _unique_tags(tags: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        cleaned = str(tag).strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


class SlidingMemoryEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: f"mem_{uuid4().hex[:12]}")
    actor_id: str = ""
    topic: str = ""
    text: str
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("score")
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return float(value)


class SlidingMemorySummary(BaseModel):
    window_id: str
    owner_id: str = ""
    capacity: int = DEFAULT_SLIDING_MEMORY_CAPACITY
    entry_count: int = 0
    average_score: float = 0.0
    top_tags: list[str] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SlidingMemoryWindow(BaseModel):
    window_id: str = Field(default_factory=lambda: f"window_{uuid4().hex[:12]}")
    owner_id: str = ""
    capacity: int = DEFAULT_SLIDING_MEMORY_CAPACITY
    entries: list[SlidingMemoryEntry] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("capacity")
    @classmethod
    def _normalize_capacity(cls, value: int) -> int:
        return _clamp_capacity(value)

    def add_entry(self, entry: SlidingMemoryEntry) -> SlidingMemoryEntry:
        self.entries.append(entry)
        self.compact()
        self.touch()
        return entry

    def add_text(
        self,
        text: str,
        *,
        score: float = 0.0,
        topic: str = "",
        tags: Iterable[str] | None = None,
        actor_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SlidingMemoryEntry:
        entry = SlidingMemoryEntry(
            actor_id=actor_id or self.owner_id,
            topic=topic,
            text=text,
            score=score,
            tags=_unique_tags(tags or []),
            metadata=dict(metadata or {}),
        )
        return self.add_entry(entry)

    def compact(self) -> "SlidingMemoryWindow":
        if self.capacity <= 0:
            self.entries = []
            self.summary = ""
            self.touch()
            return self
        ranked = sorted(
            self.entries,
            key=lambda entry: (float(entry.score), entry.created_at.timestamp(), entry.entry_id),
            reverse=True,
        )[: self.capacity]
        ranked.sort(key=lambda entry: entry.created_at)
        self.entries = ranked
        self.summary = self._render_summary()
        self.touch()
        return self

    def search(self, query: str, *, limit: int = 5) -> list[SlidingMemoryEntry]:
        terms = set(_tokenize(query))
        if not terms:
            return self.entries[-limit:]
        scored: list[tuple[float, SlidingMemoryEntry]] = []
        for entry in self.entries:
            haystack = set(_tokenize(entry.text)) | set(_tokenize(entry.topic)) | set(entry.tags)
            overlap = len(terms & haystack)
            if overlap == 0:
                continue
            score = overlap + max(0.0, float(entry.score))
            scored.append((score, entry))
        scored.sort(key=lambda item: (item[0], item[1].created_at.timestamp()), reverse=True)
        return [entry for _, entry in scored[:limit]]

    def snapshot(self) -> SlidingMemorySummary:
        return SlidingMemorySummary(
            window_id=self.window_id,
            owner_id=self.owner_id,
            capacity=self.capacity,
            entry_count=len(self.entries),
            average_score=mean([float(entry.score) for entry in self.entries]) if self.entries else 0.0,
            top_tags=self.top_tags(),
            summary=self.summary or self._render_summary(),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=dict(self.metadata),
        )

    def top_tags(self, *, limit: int = 5) -> list[str]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            for tag in entry.tags:
                counts[tag] = counts.get(tag, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [tag for tag, _ in ranked[:limit]]

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "SlidingMemoryWindow":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def _render_summary(self) -> str:
        if not self.entries:
            return f"Sliding memory window {self.window_id} is empty."
        top_entries = sorted(
            self.entries,
            key=lambda entry: (float(entry.score), entry.created_at.timestamp(), entry.entry_id),
            reverse=True,
        )[:3]
        joined = " | ".join(entry.text for entry in top_entries)
        return f"Sliding memory window {self.window_id} retains {len(self.entries)} items. Top signals: {joined}"


class SlidingMemoryEngine:
    def __init__(
        self,
        *,
        owner_id: str = "",
        capacity: int = DEFAULT_SLIDING_MEMORY_CAPACITY,
        window_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.window = SlidingMemoryWindow(
            window_id=window_id or f"window_{uuid4().hex[:12]}",
            owner_id=owner_id,
            capacity=capacity,
            metadata=dict(metadata or {}),
        )

    def record(
        self,
        text: str,
        *,
        score: float = 0.0,
        topic: str = "",
        tags: Iterable[str] | None = None,
        actor_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SlidingMemoryEntry:
        return self.window.add_text(
            text,
            score=score,
            topic=topic,
            tags=tags,
            actor_id=actor_id or self.window.owner_id,
            metadata=metadata,
        )

    def extend(self, entries: Iterable[SlidingMemoryEntry | str]) -> SlidingMemoryWindow:
        for entry in entries:
            if isinstance(entry, SlidingMemoryEntry):
                self.window.add_entry(entry)
            else:
                self.record(str(entry))
        return self.window

    def compact(self) -> SlidingMemoryWindow:
        return self.window.compact()

    def search(self, query: str, *, limit: int = 5) -> list[SlidingMemoryEntry]:
        return self.window.search(query, limit=limit)

    def snapshot(self) -> SlidingMemoryWindow:
        return self.window.model_copy(deep=True)

    def save(self, path: str | Path) -> Path:
        return self.window.save(path)

    @classmethod
    def load(cls, path: str | Path) -> "SlidingMemoryEngine":
        window = SlidingMemoryWindow.load(path)
        engine = cls(owner_id=window.owner_id, capacity=window.capacity, window_id=window.window_id, metadata=window.metadata)
        engine.window = window
        return engine


def compact_memory_texts(
    texts: Iterable[str],
    *,
    capacity: int = DEFAULT_SLIDING_MEMORY_CAPACITY,
) -> list[str]:
    engine = SlidingMemoryEngine(capacity=capacity)
    engine.extend(texts)
    engine.compact()
    return [entry.text for entry in engine.window.entries]
