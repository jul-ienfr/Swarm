from __future__ import annotations

from pathlib import Path
from typing import Any

from engines.agentsociety.adapter import AgentSocietyEngineAdapter
from runtime_contracts import AdapterCommand, AdapterCommandV1, EngineErrorCode, EngineTarget, RunStatus
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService


class UnavailableClient:
    def create_run(self, config: Any) -> str:
        raise ConnectionError("AgentSociety unavailable")


def test_engine_unavailable_returns_normalized_failure(tmp_path: Path) -> None:
    store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    service = AdapterService(store=store)
    service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(UnavailableClient(), store),
    )

    result = service.dispatch(
        AdapterCommandV1(
            command=AdapterCommand.create_run,
            engine=EngineTarget.agentsociety,
            runtime_run_id="run_unavailable",
            swarm_intent_id="intent_unavailable",
        )
    )

    assert result.status == RunStatus.engine_unavailable
    assert result.errors[0].error_code == EngineErrorCode.engine_unavailable
    assert result.errors[0].retryable is True
    mapping = store.get_by_runtime_run_id("run_unavailable")
    assert mapping is not None
    assert mapping.status == RunStatus.engine_unavailable
