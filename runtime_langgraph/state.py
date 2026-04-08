from __future__ import annotations

from enum import Enum
from typing import Any

from runtime_contracts.intent import EnginePreference, SimulationIntentV1, TaskType
from swarm_core.intake import SwarmIntake


def json_safe(value: Any) -> Any:
    """Recursively convert common runtime objects into JSON-safe data."""

    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, SimulationIntentV1):
        return value.model_dump(mode="json")
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return json_safe(vars(value))
    return str(value)


def build_initial_state(
    goal: str,
    thread_id: str = "default_mission",
    source: str = "cli",
    *,
    task_type: TaskType = TaskType.analysis,
    max_agents: int = 1000,
    time_horizon: str = "7d",
    budget_max: float = 10,
    timeout_seconds: int = 1800,
    engine_preference: EnginePreference = EnginePreference.agentsociety,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    variables: dict[str, Any] | None = None,
    environment_seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a backward-compatible mission state with JSON-safe intent metadata."""
    intent = SwarmIntake().accept(
        goal=goal,
        task_type=task_type,
        inputs={
            "documents": documents or [],
            "entities": entities or [],
            "variables": variables or {},
            "environment_seed": environment_seed or {},
        },
        constraints={
            "max_agents": max_agents,
            "time_horizon": time_horizon,
        },
        policy={
            "budget_max": budget_max,
            "timeout_seconds": timeout_seconds,
            "engine_preference": engine_preference,
        },
        context={"source": source, "metadata": {"thread_id": thread_id}},
    )
    intent_payload = json_safe(intent)

    return {
        "task_ledger": {
            "goal": goal,
            "plan": [],
            "facts": [],
            "replanning_count": 0,
            "action": "CONTINUE",
            "current_intent": intent_payload,
            "simulation_result": None,
        },
        "progress_ledger": {
            "step_index": 0,
            "is_complete": False,
            "is_stuck": False,
            "stall_count": 0,
            "next_speaker": "",
            "instruction": "",
            "simulation_result": None,
        },
        "current_intent": intent_payload,
        "simulation_result": {},
        "swarm_correlation": {
            "intent_id": intent_payload["intent_id"],
            "correlation_id": intent_payload["correlation_id"],
            "thread_id": thread_id,
        },
        "simulation_run_id": "",
        "simulation_status": "",
        "workers_output": [],
        "tokens_used_total": 0,
    }


def build_resume_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def build_status_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}
