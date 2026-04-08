from __future__ import annotations

from typing import Any

from langgraph.types import Send

from ledger_state import SupervisorState
from swarm_core.agent_registry import SwarmAgentRegistry
from swarm_core.orchestration import SwarmExecutionErrorHandler, SwarmSupervisorService


class SupervisorNode:
    """Thin LangGraph wrapper around Swarm Core orchestration."""

    def __init__(self, config_path: str = "config.yaml"):
        self.service = SwarmSupervisorService(config_path=config_path)

    def execute(self, state: SupervisorState) -> dict[str, Any]:
        return self.service.execute(state)


class ErrorHandlerNode:
    """Thin LangGraph wrapper around Swarm Core execution-error policy."""

    def __init__(self, config_path: str = "config.yaml"):
        self.service = SwarmExecutionErrorHandler()

    def execute(self, state: SupervisorState) -> dict[str, Any]:
        return self.service.execute(state)


def route_worker_output(state: SupervisorState) -> str:
    recent_outputs = state.get("workers_output", [])
    if recent_outputs:
        last_output = recent_outputs[-1]
        if not last_output.get("success", True):
            return "ErrorHandler"
    return "Supervisor"


def route_supervisor_decision(state: SupervisorState):
    task_ledger = state.get("task_ledger", {})
    progress_ledger = state.get("progress_ledger", {})

    if task_ledger.get("action") in ["REPLAN", "ABORT"]:
        return "__end__"
    if progress_ledger.get("is_complete"):
        return "__end__"

    assignments = progress_ledger.get("assignments", [])
    valid_workers = {worker.lower() for worker in SwarmAgentRegistry().get_valid_worker_names()}

    sends = []
    for assignment in assignments:
        speaker = str(assignment.get("speaker", "")).strip().lower()
        if speaker in valid_workers:
            local_state = {key: value for key, value in state.items()}
            local_state["progress_ledger"] = {
                **progress_ledger,
                "instruction": assignment.get("instruction", ""),
            }
            sends.append(Send(speaker, local_state))

    if sends:
        return sends
    return "Supervisor"
