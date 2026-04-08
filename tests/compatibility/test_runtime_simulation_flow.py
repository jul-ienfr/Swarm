from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engines.agentsociety.adapter import AgentSocietyEngineAdapter
from runtime_contracts import EnginePreference, EngineTarget, RunStatus, TaskType
from runtime_langgraph.nodes import make_simulation_finalize_node, make_simulation_node, route_initial_mission, route_simulation_progress
from runtime_langgraph.state import build_initial_state
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService


@dataclass
class FakeStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None


@dataclass
class FakeResult:
    summary: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = "fake-runtime-1.0"


class FakeSimulationClient:
    def __init__(self) -> None:
        self.next_id = 1
        self.statuses: dict[str, list[str]] = {}

    def create_run(self, config) -> str:
        engine_run_id = f"as_runtime_{self.next_id}"
        self.next_id += 1
        self.statuses[engine_run_id] = ["RUNNING", "COMPLETED"]
        return engine_run_id

    def get_run_status(self, engine_run_id: str):
        current = self.statuses[engine_run_id][0]
        if len(self.statuses[engine_run_id]) > 1:
            self.statuses[engine_run_id] = self.statuses[engine_run_id][1:]
        return FakeStatus(status=current, progress_pct=50.0 if current == "RUNNING" else 100.0, current_step=4)

    def get_result(self, engine_run_id: str):
        return FakeResult(
            summary=f"strategy synthesized for {engine_run_id}",
            metrics={"engagement_index": 0.92},
            artifacts=[{"name": "report", "type": "report", "path": "report.json"}],
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self.statuses[engine_run_id] = ["CANCELLED"]


def _build_service(tmp_path: Path) -> AdapterService:
    client = FakeSimulationClient()
    store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    service = AdapterService(store=store)
    service.register_engine(EngineTarget.agentsociety, AgentSocietyEngineAdapter(client, store, artifact_base="engine://agentsociety"))
    return service


def test_build_initial_state_supports_structured_simulation_intents() -> None:
    state = build_initial_state(
        goal="Simulate a market response",
        thread_id="thread_sim",
        source="cli",
        task_type=TaskType.scenario_simulation,
        max_agents=2500,
        time_horizon="30d",
        budget_max=42,
        timeout_seconds=900,
        engine_preference=EnginePreference.agentsociety,
    )

    intent = state["current_intent"]
    assert intent["task_type"] == "scenario_simulation"
    assert intent["constraints"]["max_agents"] == 2500
    assert intent["constraints"]["time_horizon"] == "30d"
    assert intent["policy"]["engine_preference"] == "agentsociety"
    assert route_initial_mission(state) == "simulation_runtime"


def test_simulation_runtime_path_reaches_finalize_and_marks_complete(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    simulation_node = make_simulation_node(service, poll_interval_seconds=0.0)
    finalize_node = make_simulation_finalize_node()

    state = build_initial_state(
        goal="Simulate the system shock",
        task_type=TaskType.scenario_simulation,
        engine_preference=EnginePreference.agentsociety,
    )

    first = simulation_node(state)
    assert first["simulation_status"] == RunStatus.queued.value
    assert route_simulation_progress(first) == "simulation_runtime"

    second = simulation_node(first)
    assert second["simulation_status"] == RunStatus.running.value
    assert route_simulation_progress(second) == "simulation_runtime"

    third = simulation_node(second)
    assert third["simulation_status"] == RunStatus.completed.value
    assert route_simulation_progress(third) == "simulation_finalize"

    finalized = finalize_node(third)
    assert finalized["progress_ledger"]["is_complete"] is True
    assert finalized["task_ledger"]["action"] == "APPLY"
    assert finalized["task_ledger"]["simulation_correlation"]["status"] == RunStatus.completed.value
    assert finalized["simulation_result"]["status"] == RunStatus.completed.value
