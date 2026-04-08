from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from engines.agentsociety.adapter import AgentSocietyEngineAdapter
from runtime_contracts import (
    AdapterCommand,
    AdapterCommandV1,
    EngineErrorCode,
    EngineTarget,
    RunStatus,
)
from runtime_langgraph.nodes import make_simulation_node
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService


@dataclass
class FakeStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None
    message: str | None = None


@dataclass
class FakeResult:
    summary: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = "fake-1.0"


@dataclass
class FakeRunRecord:
    engine_run_id: str
    status: RunStatus = RunStatus.queued
    summary: str = ""


class FakeAgentSocietyClient:
    def __init__(self) -> None:
        self.runs: dict[str, FakeRunRecord] = {}
        self.cancelled: list[str] = []
        self.next_run_id = 1

    def create_run(self, config) -> str:
        engine_run_id = f"as_run_{self.next_run_id}"
        self.next_run_id += 1
        self.runs[engine_run_id] = FakeRunRecord(
            engine_run_id=engine_run_id,
            status=RunStatus.queued,
            summary=f"created:{config.run_id}",
        )
        return engine_run_id

    def get_run_status(self, engine_run_id: str) -> FakeStatus:
        record = self.runs[engine_run_id]
        if record.status == RunStatus.queued:
            record.status = RunStatus.running
        elif record.status == RunStatus.running:
            record.status = RunStatus.completed
        progress = 75.0 if record.status == RunStatus.running else 100.0 if record.status.is_terminal else 0.0
        return FakeStatus(
            status=record.status.value.upper(),
            progress_pct=progress,
            current_step=4,
        )

    def get_result(self, engine_run_id: str) -> FakeResult:
        record = self.runs[engine_run_id]
        record.status = RunStatus.completed
        return FakeResult(
            summary=record.summary,
            metrics={"engagement_index": 0.81},
            artifacts=[
                {
                    "name": "report",
                    "type": "report",
                    "path": "report.json",
                    "content_type": "application/json",
                }
            ],
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self.cancelled.append(engine_run_id)
        self.runs[engine_run_id].status = RunStatus.cancelled


@pytest.fixture()
def adapter_service(tmp_path: Path) -> tuple[AdapterService, FakeAgentSocietyClient, RunMappingStore]:
    client = FakeAgentSocietyClient()
    store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    service = AdapterService(store=store)
    service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(client, store, artifact_base="engine://agentsociety"),
    )
    return service, client, store


def test_agentsociety_adapter_round_trip(
    adapter_service: tuple[AdapterService, FakeAgentSocietyClient, RunMappingStore],
) -> None:
    service, client, store = adapter_service
    command = AdapterCommandV1(
        command=AdapterCommand.create_run,
        engine=EngineTarget.agentsociety,
        runtime_run_id="run_1",
        swarm_intent_id="intent_1",
        brief="Assess a social market shock",
    )

    created = service.dispatch(command)
    assert created.status == RunStatus.queued
    assert created.engine_run_id == "as_run_1"
    assert created.engine_meta.engine == "agentsociety"

    mapping = store.get_by_runtime_run_id("run_1")
    assert mapping is not None
    assert mapping.engine_run_id == "as_run_1"
    assert mapping.status == RunStatus.queued

    status_result = service.dispatch(command.model_copy(update={"command": AdapterCommand.get_status}))
    assert status_result.status == RunStatus.running
    assert status_result.progress is not None
    assert status_result.progress.percent_complete == 75.0

    result = service.dispatch(command.model_copy(update={"command": AdapterCommand.get_result}))
    assert result.status == RunStatus.completed
    assert result.summary.startswith("created:")
    assert result.metrics[0].name == "engagement_index"
    assert result.artifacts[0].uri.startswith("engine://agentsociety/")
    assert result.is_terminal

    cancelled = service.dispatch(command.model_copy(update={"command": AdapterCommand.cancel_run}))
    assert cancelled.status == RunStatus.cancelled
    assert client.cancelled == ["as_run_1"]


def test_version_mismatch_is_normalized_with_real_service(
    adapter_service: tuple[AdapterService, FakeAgentSocietyClient, RunMappingStore],
) -> None:
    service, _, _ = adapter_service
    bad = AdapterCommandV1(
        adapter_version="v99",
        command=AdapterCommand.create_run,
        engine=EngineTarget.agentsociety,
        runtime_run_id="run_2",
    )

    result = service.dispatch(bad)

    assert result.status == RunStatus.failed
    assert result.errors
    assert result.errors[0].error_code == EngineErrorCode.version_mismatch
    assert result.errors[0].retryable is False


def test_simulation_node_stores_json_safe_result(
    adapter_service: tuple[AdapterService, FakeAgentSocietyClient, RunMappingStore],
) -> None:
    service, _, _ = adapter_service
    node = make_simulation_node(service)
    state = {
        "current_intent": {
            "intent_version": "v1",
            "swarm_version": "v1",
            "intent_id": "intent_sim_1",
            "task_type": "scenario_simulation",
            "goal": "Simulate a city-scale shock",
            "inputs": {"documents": [], "entities": [], "variables": {}, "environment_seed": {}},
            "constraints": {"max_agents": 1000, "time_horizon": "7d", "additional": {}},
            "policy": {
                "budget_max": 10,
                "timeout_seconds": 1800,
                "engine_preference": "agentsociety",
                "priority": 5,
            },
            "requested_outputs": ["summary", "metrics", "artifacts"],
            "context": {"user_id": None, "tenant_id": None, "source": "test", "metadata": {}},
            "correlation_id": "corr_test_1",
        },
        "task_ledger": {},
        "progress_ledger": {},
    }

    next_state = node(state)

    assert next_state["simulation_run_id"] == "run_intent_sim_1"
    assert next_state["simulation_status"] == RunStatus.queued.value
    assert isinstance(next_state["simulation_result"], dict)
    assert next_state["simulation_result"]["status"] == RunStatus.queued.value
