from __future__ import annotations

from typing import Any

from runtime_contracts.intent import (
    IntentConstraints,
    IntentContext,
    IntentInputs,
    IntentPolicy,
    SimulationIntentV1,
    TaskType,
)


class SwarmIntake:
    """Normalizes raw mission requests into the v1 Swarm -> Runtime contract."""

    def accept(
        self,
        *,
        goal: str,
        task_type: TaskType = TaskType.analysis,
        inputs: IntentInputs | dict[str, Any] | None = None,
        constraints: IntentConstraints | dict[str, Any] | None = None,
        policy: IntentPolicy | dict[str, Any] | None = None,
        requested_outputs: list[str] | None = None,
        context: IntentContext | dict[str, Any] | None = None,
    ) -> SimulationIntentV1:
        return SimulationIntentV1(
            task_type=task_type,
            goal=goal,
            inputs=self._coerce(inputs, IntentInputs),
            constraints=self._coerce(constraints, IntentConstraints),
            policy=self._coerce(policy, IntentPolicy),
            requested_outputs=requested_outputs or ["summary", "metrics", "artifacts"],
            context=self._coerce(context, IntentContext),
        )

    @staticmethod
    def _coerce(value: Any, model_type):
        if value is None:
            return model_type()
        if isinstance(value, model_type):
            return value
        return model_type.model_validate(value)
