from __future__ import annotations

from pathlib import Path

from swarm_core.deliberation import DeliberationCoordinator, DeliberationMode
from swarm_core.deliberation_interview import interview_deliberation_sync, list_deliberation_targets


class FakeAdapterService:
    def __init__(self) -> None:
        self._status_calls = 0

    def dispatch(self, command):
        from runtime_contracts.adapter_command import AdapterCommand
        from runtime_contracts.adapter_result import (
            AdapterResultV1,
            EngineMeta,
            NormalizedArtifact,
            NormalizedMetric,
            RunStatus,
        )

        if command.command == AdapterCommand.create_run:
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_interview",
                status=RunStatus.queued,
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        if command.command == AdapterCommand.get_status:
            self._status_calls += 1
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_interview",
                status=RunStatus.completed,
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        if command.command == AdapterCommand.get_result:
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_interview",
                status=RunStatus.completed,
                summary="Population reaction stabilizes around a cautious rollout.",
                metrics=[NormalizedMetric(name="engagement_index", value=0.73, unit="index")],
                scenarios=[{"scenario_id": "baseline", "description": "Cautious adoption."}],
                risks=[{"risk": "trust_dip", "detail": "Confidence drops if messaging is inconsistent."}],
                recommendations=[{"action": "sequence_release", "detail": "Roll out in phases."}],
                artifacts=[
                    NormalizedArtifact(
                        name="engine-report",
                        artifact_type="report",
                        uri="engine://agentsociety/demo/report.json",
                        content_type="application/json",
                    )
                ],
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        raise AssertionError(f"Unexpected command: {command.command}")


def _persisted_simulation(tmp_path: Path):
    coordinator = DeliberationCoordinator(output_dir=tmp_path, adapter_service=FakeAdapterService())
    return coordinator.run(
        topic="How will the population react to a staged release?",
        objective="Estimate social reaction to a staged release.",
        mode=DeliberationMode.simulation,
        documents=["Doc A", "Doc B"],
        entities=[{"segment": "early-adopters"}],
        interventions=["Inject a surprise outage on day 2."],
        population_size=250,
        rounds=2,
        persist=True,
    )


def test_list_deliberation_targets_returns_overview_group_and_agents(tmp_path: Path) -> None:
    result = _persisted_simulation(tmp_path)

    targets = list_deliberation_targets(result.deliberation_id, output_dir=tmp_path)

    target_ids = {item.target_id for item in targets}
    assert "overview" in target_ids
    assert any(item.target_type.value == "group" for item in targets)
    assert any(item.target_type.value == "agent" for item in targets)


def test_interview_deliberation_supports_overview_group_and_agent(tmp_path: Path) -> None:
    result = _persisted_simulation(tmp_path)
    targets = list_deliberation_targets(result.deliberation_id, output_dir=tmp_path)
    agent_target = next(item for item in targets if item.target_type.value == "agent")
    group_target = next(item for item in targets if item.target_type.value == "group")

    overview = interview_deliberation_sync(
        result.deliberation_id,
        question="What happened overall?",
        output_dir=tmp_path,
    )
    group = interview_deliberation_sync(
        result.deliberation_id,
        question="What does this group believe?",
        target_id=group_target.target_id,
        output_dir=tmp_path,
    )
    agent = interview_deliberation_sync(
        result.deliberation_id,
        question="What does this agent remember?",
        target_id=agent_target.target_id,
        output_dir=tmp_path,
    )

    assert overview.target_type.value == "overview"
    assert "Population reaction" in overview.answer
    assert group.target_type.value == "group"
    assert group.metadata["agent_count"] >= 1
    assert agent.target_type.value == "agent"
    assert agent.stance is not None
    assert agent.confidence is not None
