from __future__ import annotations

from runtime_contracts import RunStatus
from swarm_core.benchmark_suite import BenchmarkProfile
from swarm_core.harness_runtime import build_default_adapter_service, inspect_harness, run_harness_optimization
from swarm_core.harness_optimizer import OptimizationMode


def test_harness_runtime_registers_agentsociety_surrogate_when_requested(tmp_path) -> None:
    service = build_default_adapter_service(
        str(tmp_path / "run_mappings.db"),
        backend_mode="surrogate",
    )

    assert service.adapters
    assert "agentsociety" in {engine.value for engine in service.adapters.keys()}


def test_harness_runtime_inspect_and_suggest_use_registered_engine(tmp_path) -> None:
    inspection = inspect_harness(
        benchmark_path=None,
        memory_path=str(tmp_path / "harness_memory.db"),
        adapter_service=build_default_adapter_service(
            str(tmp_path / "run_mappings.db"),
            backend_mode="surrogate",
        ),
    )
    assert "agentsociety" in inspection.registered_engines
    assert inspection.registered_backends["agentsociety"] == "surrogate"

    result = run_harness_optimization(
        benchmark_path=None,
        memory_path=str(tmp_path / "harness_memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        mode=OptimizationMode.suggest_only,
        adapter_service=build_default_adapter_service(
            str(tmp_path / "run_mappings.db"),
            backend_mode="surrogate",
        ),
    )
    statuses = {outcome.status for outcome in result.baseline_report.outcomes}
    assert statuses == {RunStatus.completed}


def test_harness_runtime_interactive_profile_defaults_to_surrogate_backend(tmp_path) -> None:
    inspection = inspect_harness(
        benchmark_profile=BenchmarkProfile.interactive,
        memory_path=str(tmp_path / "harness_memory.db"),
    )

    assert inspection.benchmark_profile == BenchmarkProfile.interactive.value
    assert inspection.benchmark_suite.suite_version == "v1-interactive"
    assert inspection.backend_mode == "surrogate"
    assert inspection.registered_backends["agentsociety"] == "surrogate"

    result = run_harness_optimization(
        benchmark_profile=BenchmarkProfile.interactive,
        memory_path=str(tmp_path / "harness_memory.db"),
        run_mapping_path=str(tmp_path / "run_mappings.db"),
        mode=OptimizationMode.suggest_only,
        runtime="legacy",
        allow_fallback=True,
    )
    assert len(result.baseline_report.outcomes) == 1
    assert {outcome.status for outcome in result.baseline_report.outcomes} == {RunStatus.completed}
