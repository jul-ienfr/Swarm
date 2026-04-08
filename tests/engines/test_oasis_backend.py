from __future__ import annotations

from runtime_contracts.adapter_command import AdapterCommand, AdapterCommandV1, EngineTarget
from runtime_contracts.adapter_result import RunStatus
from simulation_adapter.factory import build_default_adapter_service


def test_oasis_surrogate_backend_is_registered_and_callable() -> None:
    service = build_default_adapter_service(backend_mode="surrogate")

    create = service.dispatch(
        AdapterCommandV1(
            command=AdapterCommand.create_run,
            engine=EngineTarget.oasis,
            runtime_run_id="oasis_run_1",
            brief="Assess the social reaction to a staged rollout.",
        )
    )
    assert create.engine_meta.engine == "oasis"
    assert create.engine_run_id is not None
    assert create.status == RunStatus.queued

    status = service.dispatch(
        AdapterCommandV1(
            command=AdapterCommand.get_status,
            engine=EngineTarget.oasis,
            runtime_run_id="oasis_run_1",
        )
    )
    assert status.status == RunStatus.completed
    assert status.engine_meta.engine == "oasis"

    result = service.dispatch(
        AdapterCommandV1(
            command=AdapterCommand.get_result,
            engine=EngineTarget.oasis,
            runtime_run_id="oasis_run_1",
        )
    )
    assert result.status == RunStatus.completed
    assert result.engine_meta.engine == "oasis"
    assert "engagement_index" in {metric.name for metric in result.metrics}
    assert result.artifacts

    cancelled = service.dispatch(
        AdapterCommandV1(
            command=AdapterCommand.cancel_run,
            engine=EngineTarget.oasis,
            runtime_run_id="oasis_run_1",
        )
    )
    assert cancelled.status == RunStatus.cancelled
