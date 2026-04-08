from __future__ import annotations

from typing import Any

from runtime_contracts.adapter_result import AdapterResultV1
from runtime_contracts.intent import SimulationIntentV1


class RunCorrelator:
    """Builds a governance-friendly summary from runtime and adapter outputs."""

    def correlate(
        self,
        intent: SimulationIntentV1 | dict[str, Any],
        result: AdapterResultV1 | dict[str, Any],
    ) -> dict[str, Any]:
        intent_model = (
            intent
            if isinstance(intent, SimulationIntentV1)
            else SimulationIntentV1.model_validate(intent)
        )
        result_model = (
            result
            if isinstance(result, AdapterResultV1)
            else AdapterResultV1.model_validate(result)
        )
        return {
            "intent_id": intent_model.intent_id,
            "correlation_id": intent_model.correlation_id,
            "goal": intent_model.goal,
            "status": result_model.status.value,
            "summary": result_model.summary,
            "metrics": [metric.model_dump(mode="json") for metric in result_model.metrics],
            "artifacts": [artifact.model_dump(mode="json") for artifact in result_model.artifacts],
            "errors": [error.model_dump(mode="json") for error in result_model.errors],
        }
