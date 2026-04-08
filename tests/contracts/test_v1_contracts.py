from __future__ import annotations

import pytest
from pydantic import ValidationError

from runtime_contracts import (
    AdapterCommand,
    AdapterCommandV1,
    AdapterResultV1,
    ControlParams,
    EngineErrorCode,
    EnginePreference,
    EngineTarget,
    IntentPolicy,
    NormalizedError,
    NormalizedMetric,
    ProgressGranularity,
    RunStatus,
    SimulationIntentV1,
    TaskType,
)
from engines.agentsociety.translator import AgentSocietyTranslator
from simulation_adapter.contracts import command_to_request
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService


def test_simulation_intent_v1_defaults_and_json_dump() -> None:
    intent = SimulationIntentV1(task_type=TaskType.scenario_simulation, goal="Simulate market reaction")

    assert intent.intent_version == "v1"
    assert intent.swarm_version == "v1"
    assert intent.goal == "Simulate market reaction"
    assert intent.policy.engine_preference == EnginePreference.agentsociety
    assert intent.requested_outputs == ["summary", "metrics", "artifacts"]

    dumped = intent.model_dump(mode="json")
    assert dumped["task_type"] == TaskType.scenario_simulation.value
    assert dumped["policy"]["engine_preference"] == EnginePreference.agentsociety.value
    assert dumped["correlation_id"].startswith("corr_")


def test_simulation_intent_v1_rejects_unknown_task_type_and_engine() -> None:
    with pytest.raises(ValidationError):
        SimulationIntentV1(task_type="free_text_task", goal="Test")

    with pytest.raises(ValidationError):
        SimulationIntentV1(
            task_type=TaskType.analysis,
            goal="Test",
            policy={"engine_preference": "unknown_engine_xyz"},
        )


def test_adapter_command_v1_validates_control_and_engine() -> None:
    command = AdapterCommandV1(
        command=AdapterCommand.create_run,
        engine=EngineTarget.agentsociety,
        control=ControlParams(
            timeout_seconds=120,
            budget_max=1.5,
            progress_granularity=ProgressGranularity.fine,
        ),
    )

    assert command.adapter_version == "v1"
    assert command.engine == EngineTarget.agentsociety
    assert command.control.progress_granularity == ProgressGranularity.fine

    with pytest.raises(ValidationError):
        AdapterCommandV1(command=AdapterCommand.create_run, engine="unknown_engine")

    with pytest.raises(ValidationError):
        AdapterCommandV1(
            command=AdapterCommand.create_run,
            engine=EngineTarget.mesa,
            control={"progress_granularity": "not-a-real-value"},
        )


def test_adapter_result_v1_terminal_states_and_normalized_types() -> None:
    terminal_statuses = [
        RunStatus.completed,
        RunStatus.failed,
        RunStatus.cancelled,
        RunStatus.timed_out,
        RunStatus.engine_unavailable,
    ]
    for status in terminal_statuses:
        result = AdapterResultV1(runtime_run_id="run_1", status=status)
        assert result.is_terminal

    for status in [RunStatus.queued, RunStatus.running]:
        result = AdapterResultV1(runtime_run_id="run_1", status=status)
        assert not result.is_terminal

    result = AdapterResultV1(
        runtime_run_id="run_1",
        engine_run_id="engine_1",
        status=RunStatus.completed,
        summary="ok",
        metrics=[NormalizedMetric(name="engagement_index", value=0.73, unit="index", tags={"segment": "retail"})],
        errors=[NormalizedError.from_code(EngineErrorCode.unknown, "placeholder")],
    )
    dumped = result.model_dump(mode="json")

    assert dumped["metrics"][0]["name"] == "engagement_index"
    assert dumped["metrics"][0]["value"] == 0.73
    assert dumped["errors"][0]["error_code"] == EngineErrorCode.unknown.value
    assert dumped["status"] == RunStatus.completed.value


def test_adapter_service_version_mismatch_is_normalized(tmp_path) -> None:
    service = AdapterService(store=RunMappingStore(str(tmp_path / "mappings.db")))

    result = service.dispatch(
        AdapterCommandV1(
            adapter_version="v99",
            command=AdapterCommand.create_run,
            engine=EngineTarget.agentsociety,
            runtime_run_id="run_bad_version",
        )
    )

    assert result.status == RunStatus.failed
    assert result.errors[0].error_code == EngineErrorCode.version_mismatch


def test_translator_propagates_runtime_control_params() -> None:
    command = AdapterCommandV1(
        command=AdapterCommand.create_run,
        engine=EngineTarget.agentsociety,
        runtime_run_id="run_translate_control",
        control=ControlParams(
            timeout_seconds=123,
            budget_max=7.5,
            progress_granularity=ProgressGranularity.fine,
        ),
        parameters={
            "max_agents": 3,
            "time_horizon": "0.5d",
            "extra": {"ticks_per_step": 60},
        },
    )
    request = command_to_request(command)
    translated = AgentSocietyTranslator().translate(request)

    assert translated.extra["timeout_seconds"] == 123
    assert translated.extra["budget_max"] == 7.5
    assert translated.extra["progress_granularity"] == "fine"
    assert translated.extra["ticks_per_step"] == 60
