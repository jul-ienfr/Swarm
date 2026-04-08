from __future__ import annotations

import time
from typing import Any

from runtime_contracts.adapter_command import AdapterCommand, AdapterCommandV1, EngineTarget
from runtime_contracts.adapter_result import AdapterResultV1, EngineErrorCode, NormalizedError, RunStatus
from runtime_contracts.intent import SimulationIntentV1
from runtime_langgraph.state import json_safe
from simulation_adapter.service import AdapterService
from swarm_core import RunCorrelator
from swarm_core.orchestration import get_intent_from_state, is_simulation_state


def inject_json_safe_metadata(
    state: dict[str, Any],
    *,
    current_intent: Any | None = None,
    simulation_result: Any | None = None,
) -> dict[str, Any]:
    """Attach JSON-safe mission metadata without mutating the caller state."""
    next_state = dict(state)
    task_ledger = dict(next_state.get("task_ledger", {}))
    progress_ledger = dict(next_state.get("progress_ledger", {}))

    if current_intent is not None:
        task_ledger["current_intent"] = json_safe(current_intent)
    if simulation_result is not None:
        payload = json_safe(simulation_result)
        task_ledger["simulation_result"] = payload
        progress_ledger["simulation_result"] = payload

    next_state["task_ledger"] = task_ledger
    next_state["progress_ledger"] = progress_ledger
    if current_intent is not None:
        next_state["current_intent"] = json_safe(current_intent)
    if simulation_result is not None:
        payload = json_safe(simulation_result)
        next_state["simulation_result"] = payload
        next_state["simulation_status"] = payload.get("status") if isinstance(payload, dict) else None
    return next_state


def route_initial_mission(state: dict[str, Any]) -> str:
    return "simulation_runtime" if is_simulation_state(state) else "Supervisor"


def route_simulation_progress(state: dict[str, Any]) -> str:
    raw_result = state.get("simulation_result", {})
    status_value = state.get("simulation_status") or (raw_result.get("status") if isinstance(raw_result, dict) else None)
    if not status_value:
        return "simulation_runtime"
    status = RunStatus(str(status_value))
    return "simulation_finalize" if status.is_terminal else "simulation_runtime"


def make_simulation_node(adapter_service: AdapterService, *, poll_interval_seconds: float = 1.0):
    """LangGraph node factory that routes simulation work through AdapterService only."""

    def simulation_node(state: dict[str, Any]) -> dict[str, Any]:
        intent = get_intent_from_state(state)
        if intent is None:
            return inject_json_safe_metadata(
                state,
                simulation_result=AdapterResultV1(
                    runtime_run_id="missing_intent",
                    status=RunStatus.failed,
                    errors=[
                        NormalizedError.from_code(
                            EngineErrorCode.unknown,
                            "No current intent found for simulation node.",
                        )
                    ],
                ),
            )

        runtime_run_id = state.get("simulation_run_id") or f"run_{intent.intent_id}"
        current_status = _extract_status(state)

        if current_status in {None, ""}:
            command = _build_command(intent, runtime_run_id=runtime_run_id, command=AdapterCommand.create_run)
        else:
            if current_status in {RunStatus.queued.value, RunStatus.running.value}:
                time.sleep(max(0.0, poll_interval_seconds))
            command = _build_command(intent, runtime_run_id=runtime_run_id, command=AdapterCommand.get_result)

        result = adapter_service.dispatch(command)
        next_state = inject_json_safe_metadata(
            state,
            current_intent=intent,
            simulation_result=result,
        )
        next_state["simulation_run_id"] = result.runtime_run_id
        next_state["simulation_status"] = result.status.value
        return next_state

    return simulation_node


def make_simulation_finalize_node(correlator: RunCorrelator | None = None):
    correlator = correlator or RunCorrelator()

    def simulation_finalize(state: dict[str, Any]) -> dict[str, Any]:
        intent = get_intent_from_state(state)
        raw_result = state.get("simulation_result")
        if intent is None or not raw_result:
            return state

        result = raw_result if isinstance(raw_result, AdapterResultV1) else AdapterResultV1.model_validate(raw_result)
        correlation = correlator.correlate(intent, result)
        next_state = inject_json_safe_metadata(
            state,
            current_intent=intent,
            simulation_result=result,
        )
        task_ledger = dict(next_state.get("task_ledger", {}))
        progress_ledger = dict(next_state.get("progress_ledger", {}))

        task_ledger["simulation_correlation"] = correlation
        facts = list(task_ledger.get("facts", []))
        if correlation.get("summary"):
            facts.append(f"Simulation summary: {correlation['summary']}")
        task_ledger["facts"] = facts[-20:]

        progress_ledger["step_index"] = progress_ledger.get("step_index", 0) + 1
        progress_ledger["next_speaker"] = "COMPLETE"
        progress_ledger["instruction"] = "Simulation workflow completed."
        progress_ledger["is_complete"] = True

        if result.status == RunStatus.completed:
            task_ledger["action"] = "APPLY"
        else:
            task_ledger["action"] = "ABORT"
            error_messages = [
                error.get("message", "")
                for error in correlation.get("errors", [])
                if isinstance(error, dict) and error.get("message")
            ]
            task_ledger["replan_reason"] = "; ".join(error_messages) or f"Simulation ended with status {result.status.value}."

        next_state["task_ledger"] = task_ledger
        next_state["progress_ledger"] = progress_ledger
        return next_state

    return simulation_finalize


def _build_command(
    intent: SimulationIntentV1,
    *,
    runtime_run_id: str,
    command: AdapterCommand,
) -> AdapterCommandV1:
    return AdapterCommandV1(
        command=command,
        runtime_run_id=runtime_run_id,
        engine=EngineTarget(intent.policy.engine_preference.value),
        simulation_type="society",
        brief=intent.goal,
        seed_materials={
            "documents": intent.inputs.documents,
            "entities": intent.inputs.entities,
            "environment_seed": intent.inputs.environment_seed,
        },
        parameters={
            "max_agents": intent.constraints.max_agents,
            "time_horizon": intent.constraints.time_horizon,
            "extra": intent.constraints.additional,
        },
        control={
            "timeout_seconds": intent.policy.timeout_seconds,
            "budget_max": intent.policy.budget_max,
        },
        correlation_id=intent.correlation_id,
        swarm_intent_id=intent.intent_id,
    )


def _extract_status(state: dict[str, Any]) -> str | None:
    if state.get("simulation_status"):
        return str(state["simulation_status"])
    raw_result = state.get("simulation_result", {})
    if isinstance(raw_result, dict):
        return raw_result.get("status")
    if isinstance(raw_result, AdapterResultV1):
        return raw_result.status.value
    return None
