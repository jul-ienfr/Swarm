from __future__ import annotations

from dataclasses import dataclass

from engines.agentsociety.adapter import AgentSocietyEngineAdapter
from runtime_contracts import EngineTarget, RunStatus, SimulationIntentV1, TaskType
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService
from swarm_core.benchmark_suite import BenchmarkExpectation, BenchmarkCase, BenchmarkSuite
from swarm_core.harness_memory import HarnessMemoryStore, MemoryEntryType
from swarm_core.harness_optimizer import HarnessOptimizer, OptimizationMode, RuleBasedHarnessCritic
from swarm_core.harness_snapshot import HarnessSnapshot


@dataclass
class SnapshotAwareStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None


@dataclass
class SnapshotAwareResult:
    summary: str
    metrics: dict[str, float]
    artifacts: list[dict]
    scenarios: list[dict]
    risks: list[dict]
    recommendations: list[dict]
    engine_version: str = "fake-optimizer-1.0"


class SnapshotAwareClient:
    def __init__(self) -> None:
        self.runs = {}
        self.counter = 0

    def create_run(self, config) -> str:
        self.counter += 1
        engine_run_id = f"as_opt_{self.counter}"
        self.runs[engine_run_id] = config
        return engine_run_id

    def get_run_status(self, engine_run_id: str):
        return SnapshotAwareStatus(status="COMPLETED", progress_pct=100.0, current_step=5)

    def get_result(self, engine_run_id: str):
        config = self.runs[engine_run_id]
        snapshot = config.extra.get("harness_snapshot", {})
        rules = snapshot.get("workflow_rules", [])
        params = snapshot.get("sampling_params", {})
        metric = 0.4
        if any("normalized fallback recommendation" in rule for rule in rules):
            metric += 0.4
        if params.get("temperature", 0.0) >= 0.3:
            metric += 0.2
        return SnapshotAwareResult(
            summary=f"score={metric:.2f}",
            metrics={"engagement_index": metric},
            artifacts=[],
            scenarios=[],
            risks=[],
            recommendations=[],
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self.runs.pop(engine_run_id, None)


class SlowClient:
    def __init__(self) -> None:
        self.runs = {}
        self.cancelled: list[str] = []
        self.counter = 0

    def create_run(self, config) -> str:
        self.counter += 1
        engine_run_id = f"as_slow_{self.counter}"
        self.runs[engine_run_id] = config
        return engine_run_id

    def get_run_status(self, engine_run_id: str):
        return SnapshotAwareStatus(status="RUNNING", progress_pct=10.0, current_step=0)

    def get_result(self, engine_run_id: str):
        raise AssertionError("get_result should not be called for a timed out benchmark")

    def cancel_run(self, engine_run_id: str) -> None:
        self.cancelled.append(engine_run_id)


def _build_suite() -> BenchmarkSuite:
    intent = SimulationIntentV1(
        task_type=TaskType.scenario_simulation,
        goal="Simulate a failing harness benchmark.",
    )
    case = BenchmarkCase(
        case_id="case_1",
        description="Single benchmark case for optimizer tests.",
        intent=intent,
        expectation=BenchmarkExpectation(
            min_score=0.9,
            metric_thresholds={"engagement_index": 1.0},
            accepted_statuses=["completed"],
        ),
    )
    return BenchmarkSuite(name="optimizer_test_suite", cases=[case])


def test_optimizer_proposes_candidate_in_suggest_only_mode(tmp_path) -> None:
    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    adapter_service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(SnapshotAwareClient(), run_store),
    )
    memory_store = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))
    optimizer = HarnessOptimizer(
        memory_store=memory_store,
        mode=OptimizationMode.suggest_only,
    )
    current_snapshot = HarnessSnapshot.baseline().model_copy(
        update={"workflow_rules": [], "sampling_params": {"temperature": 0.2}}
    )

    result = optimizer.run_optimization_round(
        benchmark_suite=_build_suite(),
        current_snapshot=current_snapshot,
        adapter_service=adapter_service,
        critic=RuleBasedHarnessCritic(),
    )

    assert result.decision.value == "propose"
    assert result.candidate_score > result.baseline_score
    assert result.applied_snapshot.version == current_snapshot.version
    assert result.candidate_snapshot.version != current_snapshot.version

    memory_entries = memory_store.list_recent()
    assert any(entry.entry_type == MemoryEntryType.decision for entry in memory_entries)


def test_optimizer_halts_after_stagnation(tmp_path) -> None:
    memory_store = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))
    for round_index in range(1, 4):
        memory_store.write_round_feedback(
            round_index=round_index,
            entry_type=MemoryEntryType.decision,
            summary=f"Round {round_index} reverted",
            details={"decision": "revert"},
            candidate_version=f"cand_{round_index}",
            applied=False,
            score_delta=0.0,
        )

    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    optimizer = HarnessOptimizer(
        memory_store=memory_store,
        mode=OptimizationMode.suggest_only,
        stagnation_limit=3,
    )

    result = optimizer.run_optimization_round(
        benchmark_suite=_build_suite(),
        current_snapshot=HarnessSnapshot.baseline(),
        adapter_service=adapter_service,
        critic=RuleBasedHarnessCritic(),
    )

    assert result.decision.value == "halt"
    assert result.halted_reason is not None


def test_optimizer_cancels_and_normalizes_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("swarm_core.harness_optimizer.time.sleep", lambda _: None)

    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    slow_client = SlowClient()
    adapter_service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(slow_client, run_store),
    )
    memory_store = HarnessMemoryStore(str(tmp_path / "harness_memory.db"))
    optimizer = HarnessOptimizer(
        memory_store=memory_store,
        mode=OptimizationMode.suggest_only,
    )
    suite = _build_suite().model_copy(
        update={
            "cases": [
                _build_suite().cases[0].model_copy(
                    update={
                        "intent": _build_suite().cases[0].intent.model_copy(
                            update={
                                "policy": _build_suite().cases[0].intent.policy.model_copy(
                                    update={"timeout_seconds": 0}
                                )
                            }
                        )
                    }
                )
            ]
        }
    )

    result = optimizer.run_optimization_round(
        benchmark_suite=suite,
        current_snapshot=HarnessSnapshot.baseline(),
        adapter_service=adapter_service,
        critic=RuleBasedHarnessCritic(),
    )

    assert result.baseline_report.outcomes[0].status == RunStatus.timed_out
    assert slow_client.cancelled
