from __future__ import annotations

from pathlib import Path

import pytest

from swarm_core.observability import (
    ALL_OBSERVABILITY_EVENT_TYPES,
    OBSERVABILITY_TAXONOMY,
    ObservabilityEvent,
    ObservabilityEventStore,
    ObservabilityEventType,
    build_observability_stats,
    describe_observability_taxonomy,
    event_type_group,
    normalize_event_type,
    resolve_prompt_logging_policy,
)


def test_observability_taxonomy_covers_runtime_and_simulation_signals() -> None:
    taxonomy = describe_observability_taxonomy()

    assert "runtime" in taxonomy["groups"]
    assert "simulation" in taxonomy["groups"]
    assert "llm_call" in taxonomy["all_types"]
    assert "agent_decision" in taxonomy["all_types"]
    assert "error" in taxonomy["all_types"]
    assert ALL_OBSERVABILITY_EVENT_TYPES == tuple(sorted(ALL_OBSERVABILITY_EVENT_TYPES))
    assert set(OBSERVABILITY_TAXONOMY["runtime"]).issubset(set(ALL_OBSERVABILITY_EVENT_TYPES))
    assert event_type_group("llm_call") == "simulation"
    assert event_type_group(ObservabilityEventType.error) == "runtime"


def test_prompt_logging_policy_resolves_preview_and_full_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIROSHARK_LOG_PROMPTS", "true")
    monkeypatch.delenv("MIROSHARK_LOG_PROMPTS_MODE", raising=False)
    policy = resolve_prompt_logging_policy()
    assert policy.enabled is True
    assert policy.preview is True
    assert policy.full is False

    monkeypatch.setenv("MIROSHARK_LOG_PROMPTS_MODE", "full")
    policy = resolve_prompt_logging_policy()
    assert policy.enabled is True
    assert policy.full is True

    monkeypatch.setenv("MIROSHARK_LOG_PROMPTS", "0")
    monkeypatch.delenv("MIROSHARK_LOG_PROMPTS_MODE", raising=False)
    policy = resolve_prompt_logging_policy()
    assert policy.enabled is False
    assert policy.mode == "off"


def test_event_store_roundtrip_and_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIROSHARK_LOG_PROMPTS", "full")
    store = ObservabilityEventStore(tmp_path / "events.jsonl")

    first = ObservabilityEvent(
        event_type=ObservabilityEventType.llm_call,
        source="meeting_facilitator",
        message="prompt dispatched",
        simulation_id="sim-001",
        agent_id="agent-1",
        round_index=2,
        platform="polymarket",
        prompt="Draft a concise thesis about edge after fees and slippage.",
        response="Use the no-trade baseline unless the shadow path survives costs.",
        data={
            "latency_ms": 42,
            "prompt": "internal prompt should stay visible in full mode",
            "nested": {"response": "nested answer"},
        },
        tags=["analysis", "debug"],
        metadata={"model": "gpt-5.4-mini"},
    )
    second = ObservabilityEvent(
        event_type="agent_decision",
        source="meeting_agent",
        message="decision recorded",
        simulation_id="sim-001",
        agent_id="agent-2",
        round_index=2,
        data={"decision": "no_trade"},
    )
    third = ObservabilityEvent(
        event_type="error",
        source="runtime",
        message="provider timeout",
        data={"prompt": "should remain visible in full mode"},
    )

    first_record = store.append(first)
    second_record = store.append(second)
    store.append(third)
    store.path.write_text(store.path.read_text(encoding="utf-8") + "{not-json}\n", encoding="utf-8")

    events, malformed_lines = store.load_events()
    stats = store.stats()

    assert malformed_lines == 1
    assert len(events) == 3
    assert stats.total_events == 3
    assert stats.llm_call_count == 1
    assert stats.agent_decision_count == 1
    assert stats.error_count == 1
    assert stats.counts_by_type["llm_call"] == 1
    assert stats.counts_by_source["meeting_facilitator"] == 1
    assert stats.counts_by_group["runtime"] == 1
    assert stats.counts_by_group["simulation"] == 2
    assert stats.prompt_event_count == 2
    assert stats.full_prompt_count == 1
    assert stats.preview_prompt_count == 1
    assert stats.latest_timestamp is not None

    assert first_record["prompt"] == first.prompt
    assert first_record["response"] == first.response
    assert first_record["data"]["prompt"] == "internal prompt should stay visible in full mode"
    assert second_record["message"] == "decision recorded"

    round_trip = ObservabilityEvent.from_record(first_record)
    assert round_trip.prompt == first.prompt
    assert round_trip.response == first.response
    assert round_trip.tags == first.tags
    assert round_trip.metadata == first.metadata


def test_event_store_redacts_prompt_fields_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIROSHARK_LOG_PROMPTS", "0")
    store = ObservabilityEventStore(tmp_path / "events.jsonl")

    event = ObservabilityEvent(
        event_type="graph_build",
        source="graph_worker",
        message="graph built",
        prompt="Build the knowledge graph from the seed docs.",
        response="Graph build completed.",
        data={"prompt": "nested prompt value", "notes": ["retain", "shape"]},
    )
    record = store.append(event)

    assert "prompt" not in record
    assert "response" not in record
    assert record["data"]["prompt"] == "[redacted]"
    assert record["data"]["notes"] == ["retain", "shape"]

    loaded, malformed_lines = store.load_events()
    assert malformed_lines == 0
    assert loaded[0].prompt is None
    assert loaded[0].response is None


def test_normalize_event_type_rejects_unknown_values() -> None:
    assert normalize_event_type("system") == "system"
    with pytest.raises(ValueError):
        normalize_event_type("unknown_event")
