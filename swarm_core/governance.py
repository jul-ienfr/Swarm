from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GovernanceDecision:
    task_ledger: dict[str, Any]
    progress_ledger: dict[str, Any]
    should_short_circuit: bool = False


class GovernanceEngine:
    """Pure governance checks extracted from the supervisor's outer loop."""

    def __init__(
        self,
        *,
        max_stall_count: int = 3,
        max_replan: int = 4,
        max_steps_total: int = 50,
    ) -> None:
        self.max_stall_count = max_stall_count
        self.max_replan = max_replan
        self.max_steps_total = max_steps_total

    def evaluate(
        self,
        task_ledger: dict[str, Any] | None,
        progress_ledger: dict[str, Any] | None,
    ) -> GovernanceDecision:
        task = dict(task_ledger or {})
        progress = dict(progress_ledger or {})

        if task.get("action") == "REPLAN":
            task["action"] = "CONTINUE"

        stall_count = progress.get("stall_count", 0)
        step_index = progress.get("step_index", 0)
        replanning_count = task.get("replanning_count", 0)

        if step_index >= self.max_steps_total:
            task["action"] = "ABORT"
            task["replan_reason"] = "MAX_STEPS_TOTAL exceeded."
            progress["is_complete"] = True
            return GovernanceDecision(task, progress, should_short_circuit=True)

        if stall_count >= self.max_stall_count:
            if replanning_count >= self.max_replan:
                task["action"] = "ABORT"
                task["replan_reason"] = "Max replan count exceeded. Aborting mission."
                progress["is_complete"] = True
                return GovernanceDecision(task, progress, should_short_circuit=True)

            task["action"] = "REPLAN"
            task["replan_reason"] = "Max stall count exceeded. Agents are stuck."
            task["replanning_count"] = replanning_count + 1
            progress["stall_count"] = 0
            return GovernanceDecision(task, progress, should_short_circuit=True)

        return GovernanceDecision(task, progress, should_short_circuit=False)
