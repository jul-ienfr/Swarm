from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class ObservabilityEventType(str, Enum):
    llm_call = "llm_call"
    agent_decision = "agent_decision"
    round_boundary = "round_boundary"
    graph_build = "graph_build"
    graph_ner = "graph_ner"
    memory_compaction = "memory_compaction"
    report = "report"
    tool_result = "tool_result"
    system = "system"
    error = "error"


OBSERVABILITY_TAXONOMY: dict[str, tuple[str, ...]] = {
    "runtime": ("system", "error", "tool_result"),
    "simulation": ("llm_call", "agent_decision", "round_boundary", "memory_compaction"),
    "graph": ("graph_build", "graph_ner"),
    "reporting": ("report",),
}

ALL_OBSERVABILITY_EVENT_TYPES = tuple(
    sorted({event_type for types in OBSERVABILITY_TAXONOMY.values() for event_type in types})
)

_PROMPT_FIELDS = {"prompt", "prompts", "response", "responses", "messages", "input", "output", "completion"}
_TRUTHY = {"1", "true", "yes", "on", "full", "preview"}
_FULL = {"full", "all"}
_OFF = {"0", "false", "no", "off", "disabled"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event_type(value: str | ObservabilityEventType) -> str:
    if isinstance(value, ObservabilityEventType):
        return value.value
    text = str(value or "").strip()
    if not text:
        raise ValueError("event_type cannot be empty")
    if text not in ALL_OBSERVABILITY_EVENT_TYPES:
        raise ValueError(f"Unsupported observability event type: {text!r}")
    return text


def event_type_group(event_type: str | ObservabilityEventType) -> str | None:
    normalized = normalize_event_type(event_type)
    for group_name, members in OBSERVABILITY_TAXONOMY.items():
        if normalized in members:
            return group_name
    return None


@dataclass(slots=True, frozen=True)
class PromptLoggingPolicy:
    mode: str = "off"
    preview_chars: int = 240
    redaction_token: str = "[redacted]"

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    @property
    def full(self) -> bool:
        return self.mode == "full"

    @property
    def preview(self) -> bool:
        return self.mode == "preview"


def resolve_prompt_logging_policy(env: Mapping[str, str] | None = None) -> PromptLoggingPolicy:
    source = env or os.environ
    raw_mode = str(source.get("MIROSHARK_LOG_PROMPTS_MODE") or "").strip().lower()
    raw_flag = str(source.get("MIROSHARK_LOG_PROMPTS") or "").strip().lower()

    preview_chars = 240
    raw_preview_chars = str(source.get("MIROSHARK_LOG_PROMPTS_PREVIEW_CHARS") or "").strip()
    if raw_preview_chars:
        try:
            preview_chars = max(1, int(raw_preview_chars))
        except ValueError:
            preview_chars = 240

    mode = "off"
    if raw_mode in _OFF or raw_flag in _OFF:
        mode = "off"
    elif raw_mode in _FULL or raw_flag in _FULL:
        mode = "full"
    elif raw_mode in _TRUTHY or raw_flag in _TRUTHY:
        mode = "preview"

    return PromptLoggingPolicy(mode=mode, preview_chars=preview_chars)


def _preview_text(value: Any, *, limit: int) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}…"
    return value


def _sanitize_value(value: Any, *, policy: PromptLoggingPolicy) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _PROMPT_FIELDS:
                if not policy.enabled:
                    sanitized[key] = policy.redaction_token
                elif policy.full:
                    sanitized[key] = _sanitize_value(nested, policy=policy)
                else:
                    sanitized[key] = _preview_text(nested, limit=policy.preview_chars)
                continue
            sanitized[key] = _sanitize_value(nested, policy=policy)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item, policy=policy) for item in value]
    if isinstance(value, str) and policy.preview:
        return _preview_text(value, limit=policy.preview_chars)
    return value


def _contains_prompt_like_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).strip().lower() in _PROMPT_FIELDS:
                return True
            if _contains_prompt_like_value(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_prompt_like_value(item) for item in value)
    return False


@dataclass(slots=True)
class ObservabilityEvent:
    event_type: str | ObservabilityEventType
    source: str
    message: str
    timestamp: str = field(default_factory=utc_now_iso)
    simulation_id: str | None = None
    agent_id: str | None = None
    round_index: int | None = None
    platform: str | None = None
    prompt: str | None = None
    response: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self, *, policy: PromptLoggingPolicy | None = None) -> dict[str, Any]:
        prompt_policy = policy or resolve_prompt_logging_policy()
        record: dict[str, Any] = {
            "event_type": normalize_event_type(self.event_type),
            "source": self.source,
            "message": self.message,
            "timestamp": self.timestamp,
            "data": _sanitize_value(self.data, policy=prompt_policy),
            "tags": list(self.tags),
        }
        if self.simulation_id is not None:
            record["simulation_id"] = self.simulation_id
        if self.agent_id is not None:
            record["agent_id"] = self.agent_id
        if self.round_index is not None:
            record["round_index"] = self.round_index
        if self.platform is not None:
            record["platform"] = self.platform
        if self.metadata:
            record["metadata"] = _sanitize_value(self.metadata, policy=prompt_policy)

        if prompt_policy.enabled:
            if self.prompt is not None:
                record["prompt"] = self.prompt if prompt_policy.full else _preview_text(self.prompt, limit=prompt_policy.preview_chars)
            if self.response is not None:
                record["response"] = self.response if prompt_policy.full else _preview_text(self.response, limit=prompt_policy.preview_chars)
            record["prompt_logging_mode"] = prompt_policy.mode
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ObservabilityEvent":
        known = dict(record)
        event_type = known.pop("event_type")
        source = str(known.pop("source", "system"))
        message = str(known.pop("message", ""))
        timestamp = str(known.pop("timestamp", utc_now_iso()))
        prompt = known.pop("prompt", None)
        response = known.pop("response", None)
        simulation_id = known.pop("simulation_id", None)
        agent_id = known.pop("agent_id", None)
        round_index = known.pop("round_index", None)
        platform = known.pop("platform", None)
        raw_tags = known.pop("tags", [])
        tags = list(raw_tags) if isinstance(raw_tags, (list, tuple, set)) else []
        data = known.pop("data", {})
        metadata = known.pop("metadata", {})
        if not isinstance(data, dict):
            data = {"value": data}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return cls(
            event_type=event_type,
            source=source,
            message=message,
            timestamp=timestamp,
            simulation_id=simulation_id,
            agent_id=agent_id,
            round_index=round_index,
            platform=platform,
            prompt=prompt,
            response=response,
            data=data,
            tags=tags,
            metadata=metadata,
        )


@dataclass(slots=True)
class ObservabilityStats:
    total_events: int
    counts_by_type: dict[str, int] = field(default_factory=dict)
    counts_by_source: dict[str, int] = field(default_factory=dict)
    counts_by_group: dict[str, int] = field(default_factory=dict)
    llm_call_count: int = 0
    agent_decision_count: int = 0
    error_count: int = 0
    prompt_event_count: int = 0
    full_prompt_count: int = 0
    preview_prompt_count: int = 0
    malformed_lines: int = 0
    latest_timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_observability_stats(
    events: Iterable[ObservabilityEvent | Mapping[str, Any]],
    *,
    malformed_lines: int = 0,
) -> ObservabilityStats:
    counts_by_type: dict[str, int] = {}
    counts_by_source: dict[str, int] = {}
    counts_by_group: dict[str, int] = {}
    llm_call_count = 0
    agent_decision_count = 0
    error_count = 0
    prompt_event_count = 0
    full_prompt_count = 0
    preview_prompt_count = 0
    latest_timestamp: str | None = None
    total_events = 0

    for raw_event in events:
        event = raw_event if isinstance(raw_event, ObservabilityEvent) else ObservabilityEvent.from_record(raw_event)
        total_events += 1
        event_type = normalize_event_type(event.event_type)
        counts_by_type[event_type] = counts_by_type.get(event_type, 0) + 1
        counts_by_source[event.source] = counts_by_source.get(event.source, 0) + 1
        group = event_type_group(event_type)
        if group is not None:
            counts_by_group[group] = counts_by_group.get(group, 0) + 1

        if event_type == ObservabilityEventType.llm_call.value:
            llm_call_count += 1
        elif event_type == ObservabilityEventType.agent_decision.value:
            agent_decision_count += 1
        elif event_type == ObservabilityEventType.error.value:
            error_count += 1

        prompt_payload_present = (
            event.prompt is not None
            or event.response is not None
            or _contains_prompt_like_value(event.data)
            or _contains_prompt_like_value(event.metadata)
        )
        if prompt_payload_present:
            prompt_event_count += 1
            if event.prompt is not None and event.response is not None:
                full_prompt_count += 1
            else:
                preview_prompt_count += 1

        if latest_timestamp is None or event.timestamp > latest_timestamp:
            latest_timestamp = event.timestamp

    return ObservabilityStats(
        total_events=total_events,
        counts_by_type=dict(sorted(counts_by_type.items())),
        counts_by_source=dict(sorted(counts_by_source.items())),
        counts_by_group=dict(sorted(counts_by_group.items())),
        llm_call_count=llm_call_count,
        agent_decision_count=agent_decision_count,
        error_count=error_count,
        prompt_event_count=prompt_event_count,
        full_prompt_count=full_prompt_count,
        preview_prompt_count=preview_prompt_count,
        malformed_lines=malformed_lines,
        latest_timestamp=latest_timestamp,
    )


@dataclass(slots=True)
class ObservabilityEventStore:
    path: Path
    prompt_policy: PromptLoggingPolicy = field(default_factory=resolve_prompt_logging_policy)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ObservabilityEvent) -> dict[str, Any]:
        record = event.to_record(policy=self.prompt_policy)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record

    def load_events(self) -> tuple[list[ObservabilityEvent], int]:
        if not self.path.exists():
            return [], 0

        events: list[ObservabilityEvent] = []
        malformed_lines = 0
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        events.append(ObservabilityEvent.from_record(parsed))
                    else:
                        malformed_lines += 1
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    malformed_lines += 1
        return events, malformed_lines

    def stats(self) -> ObservabilityStats:
        events, malformed_lines = self.load_events()
        return build_observability_stats(events, malformed_lines=malformed_lines)


def describe_observability_taxonomy() -> dict[str, Any]:
    return {
        "groups": {group: list(types) for group, types in OBSERVABILITY_TAXONOMY.items()},
        "all_types": list(ALL_OBSERVABILITY_EVENT_TYPES),
    }


def redact_event_for_prompt_policy(
    event: ObservabilityEvent,
    *,
    policy: PromptLoggingPolicy | None = None,
) -> dict[str, Any]:
    return event.to_record(policy=policy or resolve_prompt_logging_policy())


__all__ = [
    "ALL_OBSERVABILITY_EVENT_TYPES",
    "OBSERVABILITY_TAXONOMY",
    "ObservabilityEvent",
    "ObservabilityEventStore",
    "ObservabilityEventType",
    "ObservabilityStats",
    "PromptLoggingPolicy",
    "build_observability_stats",
    "describe_observability_taxonomy",
    "event_type_group",
    "normalize_event_type",
    "redact_event_for_prompt_policy",
    "resolve_prompt_logging_policy",
]
