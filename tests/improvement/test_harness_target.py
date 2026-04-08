from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engines.agentsociety.adapter import AgentSocietyEngineAdapter
from improvement_loop import ImprovementRuntime, LoopMode
from improvement_loop.targets.harness import HarnessImprovementTarget
from runtime_contracts import EngineTarget, SimulationIntentV1, TaskType
from simulation_adapter.mapping_store import RunMappingStore
from simulation_adapter.service import AdapterService
from swarm_core.benchmark_suite import BenchmarkCase, BenchmarkExpectation, BenchmarkProfile, BenchmarkSuite
from swarm_core.harness_optimizer import HarnessChangeProposal
from swarm_core.harness_snapshot import RiskLevel


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
    engine_version: str = "fake-target-1.0"


class SnapshotAwareClient:
    def __init__(self) -> None:
        self.runs = {}
        self.counter = 0

    def create_run(self, config) -> str:
        self.counter += 1
        engine_run_id = f"as_target_{self.counter}"
        self.runs[engine_run_id] = config
        return engine_run_id

    def get_run_status(self, engine_run_id: str):
        return SnapshotAwareStatus(status="COMPLETED", progress_pct=100.0, current_step=3)

    def get_result(self, engine_run_id: str):
        config = self.runs[engine_run_id]
        snapshot = config.extra.get("harness_snapshot", {})
        params = snapshot.get("sampling_params", {})
        metric = 0.4
        if params.get("temperature", 0.0) >= 0.3:
            metric += 0.4
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


class ResilientHarnessCritic:
    def __init__(self, *args, **kwargs) -> None:
        self.runtime_used = ImprovementRuntime.pydanticai
        self.fallback_used = False
        self.last_attempt_count = 2
        self.last_retry_count = 1
        self.last_retry_reasons = ["timeout_error"]
        self.last_error = None
        self.last_error_category = None
        self.last_error_retryable = None
        self.last_fallback_mode = "structured_success"
        self.last_backoff_total_seconds = 0.15
        self.runtime_resilience = {
            "status": "guarded",
            "attempt_count": 2,
            "retry_count": 1,
            "retry_reasons": ["timeout_error"],
            "fallback_used": False,
            "fallback_mode": "structured_success",
            "backoff_total_seconds": 0.15,
            "diagnostics": ["retryable_timeout"],
        }

    def analyze_failures(self, trajectories, current_snapshot):
        return HarnessChangeProposal(
            summary="Structured critic keeps the candidate but records resilience diagnostics.",
            rationale=["retryable timeout was recovered"],
            workflow_rules_to_add=[
                "Prefer structured retry escalation only after one backoff."
            ],
            sampling_param_overrides={"temperature": 0.35},
            risk_level=RiskLevel.low,
            requires_human_review=False,
        )


class NoopHarnessCritic:
    def __init__(self, *args, **kwargs) -> None:
        self.runtime_used = ImprovementRuntime.pydanticai
        self.fallback_used = False
        self.last_attempt_count = 1
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_error = None
        self.last_error_category = None
        self.last_error_retryable = None
        self.last_fallback_mode = None
        self.runtime_resilience = {
            "status": "healthy",
            "attempt_count": 1,
            "retry_count": 0,
            "fallback_used": False,
            "summary": "healthy | attempts=1 | retries=0 | runtime=pydanticai",
        }

    def analyze_failures(self, trajectories, current_snapshot):
        return HarnessChangeProposal(
            summary="Structured critic found no bounded harness change worth applying.",
            rationale=["No safe harness delta was justified."],
            risk_level=RiskLevel.low,
            requires_human_review=False,
        )


def _build_temp_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "workers:",
                "  demo-worker:",
                "    default_tier: openclaw_gateway",
                "orchestrator:",
                "  max_stall_count: 3",
                "  max_replan: 4",
                "  max_steps_total: 50",
            ]
        )
    )


def _build_suite(path: Path) -> None:
    intent = SimulationIntentV1(
        task_type=TaskType.scenario_simulation,
        goal="Improve the persisted harness target.",
    )
    suite = BenchmarkSuite(
        name="target_test_suite",
        cases=[
            BenchmarkCase(
                case_id="case_1",
                description="Single benchmark case for generic target persistence.",
                intent=intent,
                expectation=BenchmarkExpectation(
                    min_score=0.9,
                    metric_thresholds={"engagement_index": 1.0},
                    accepted_statuses=["completed"],
                ),
            )
        ],
    )
    suite.save(path)


def test_harness_target_inspect_reports_surrogate_backend(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    target = HarnessImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        state_path=str(tmp_path / "snapshot.json"),
        backend_mode="surrogate",
    )

    inspection = target.inspect()
    comparability = inspection.metadata["comparability"]

    assert inspection.descriptor.target_id == "harness"
    assert inspection.metadata["registered_backends"]["agentsociety"] == "surrogate"
    assert comparability["target_id"] == "harness"
    assert comparability["target_kind"] == "harness"
    assert comparability["surface"] == "inspection"
    assert comparability["benchmark_profile"] == BenchmarkProfile.full.value
    assert comparability["backend_mode"] == "surrogate"
    assert comparability["runtime_match"] is True
    assert comparability["latest_round_index"] == 0
    assert isinstance(comparability["state_fingerprint"], str) and len(comparability["state_fingerprint"]) == 64


def test_harness_target_safe_auto_apply_persists_snapshot(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    state_path = tmp_path / "snapshot.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    adapter_service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(SnapshotAwareClient(), run_store),
    )

    target = HarnessImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        state_path=str(state_path),
        adapter_service=adapter_service,
    )

    record = target.run_round(LoopMode.safe_auto_apply)
    comparability = record.metadata["comparability"]

    assert record.decision == "keep"
    assert state_path.exists()
    assert comparability["surface"] == "round"
    assert comparability["round_index"] == record.round_index
    assert comparability["state_path"] == str(state_path.resolve())
    assert comparability["benchmark_profile"] == BenchmarkProfile.full.value

    inspection = target.inspect()
    assert inspection.current_snapshot["version"] == record.applied_snapshot["version"]
    assert inspection.current_snapshot["sampling_params"]["temperature"] == 0.3


def test_harness_target_interactive_profile_uses_surrogate_backend(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _build_temp_config(config_path)

    target = HarnessImprovementTarget(
        config_path=str(config_path),
        memory_path=str(tmp_path / "memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        state_path=str(tmp_path / "snapshot.json"),
    )

    inspection = target.inspect(benchmark_profile=BenchmarkProfile.interactive)
    assert inspection.metadata["benchmark_profile"] == BenchmarkProfile.interactive.value
    assert inspection.metadata["backend_mode"] == "surrogate"
    assert inspection.metadata["registered_backends"]["agentsociety"] == "surrogate"
    assert inspection.benchmark["suite_version"] == "v1-interactive"

    record = target.run_round(
        LoopMode.suggest_only,
        runtime="legacy",
        benchmark_profile=BenchmarkProfile.interactive,
    )
    comparability = record.metadata["comparability"]
    assert record.metadata["benchmark_profile"] == BenchmarkProfile.interactive.value
    assert record.metadata["backend_mode"] == "surrogate"
    assert len(record.baseline_report["outcomes"]) == 1
    assert comparability["benchmark_profile"] == BenchmarkProfile.interactive.value
    assert comparability["backend_mode"] == "surrogate"
    assert comparability["runtime_requested"] == ImprovementRuntime.legacy.value
    assert comparability["runtime_used"] == ImprovementRuntime.legacy.value
    assert comparability["runtime_match"] is True


def test_harness_target_propagates_runtime_resilience_metadata(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    adapter_service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(SnapshotAwareClient(), run_store),
    )

    monkeypatch.setattr("improvement_loop.targets.harness.PydanticAIHarnessCritic", ResilientHarnessCritic)

    target = HarnessImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        state_path=str(tmp_path / "snapshot.json"),
        adapter_service=adapter_service,
    )

    record = target.run_round(LoopMode.suggest_only, runtime=ImprovementRuntime.pydanticai)
    resilience = record.metadata["runtime_resilience"]
    comparability = record.metadata["comparability"]

    assert resilience["critic"] == "harness"
    assert resilience["status"] == "guarded"
    assert resilience["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert resilience["runtime_used"] == ImprovementRuntime.pydanticai.value
    assert resilience["runtime_match"] is True
    assert resilience["attempt_count"] == 2
    assert resilience["retry_count"] == 1
    assert resilience["diagnostics"] == ["retryable_timeout"]
    assert "guarded" in resilience["summary"]
    assert "retries=1" in resilience["summary"]
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_match"] is True
    assert comparability["fallback_used"] is False


def test_harness_target_marks_post_validation_fallback_as_degraded(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    run_store = RunMappingStore(str(tmp_path / "run_mappings.db"))
    adapter_service = AdapterService(store=run_store)
    adapter_service.register_engine(
        EngineTarget.agentsociety,
        AgentSocietyEngineAdapter(SnapshotAwareClient(), run_store),
    )

    monkeypatch.setattr("improvement_loop.targets.harness.PydanticAIHarnessCritic", NoopHarnessCritic)

    target = HarnessImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        state_path=str(tmp_path / "snapshot.json"),
        adapter_service=adapter_service,
    )

    record = target.run_round(LoopMode.suggest_only, runtime=ImprovementRuntime.pydanticai)
    resilience = record.metadata["runtime_resilience"]
    comparability = record.metadata["comparability"]

    assert record.runtime_used == ImprovementRuntime.legacy
    assert record.fallback_used is True
    assert resilience["status"] == "degraded"
    assert resilience["score"] == 0.8
    assert resilience["runtime_match"] is False
    assert resilience["fallback_mode"] == "post_validation_fallback"
    assert "requested=pydanticai" in resilience["summary"]
    assert "runtime=legacy" in resilience["summary"]
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] == ImprovementRuntime.legacy.value
    assert comparability["runtime_match"] is False
    assert comparability["fallback_used"] is True
