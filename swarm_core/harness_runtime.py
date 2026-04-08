from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from runtime_contracts.intent import EnginePreference
from runtime_pydanticai import RuntimeFallbackPolicy
from runtime_pydanticai.improvement import PydanticAIHarnessCritic
from simulation_adapter import AdapterService
from simulation_adapter.factory import (
    build_default_adapter_service as build_shared_adapter_service,
    describe_backend,
)

from .benchmark_suite import (
    BenchmarkProfile,
    BenchmarkSuite,
    DEFAULT_BENCHMARK_SUITE_PATH,
)
from .harness_memory import DEFAULT_HARNESS_MEMORY_PATH, HarnessMemoryEntry, HarnessMemoryStore
from .harness_optimizer import (
    HarnessChangeProposal,
    OptimizationMode,
    OptimizationRoundResult,
    RuleBasedHarnessCritic,
    HarnessOptimizer,
)
from .harness_snapshot import HarnessSnapshot, SkillDefinition


DEFAULT_HARNESS_RUN_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "harness_run_mappings.db"
)


class HarnessInspection(BaseModel):
    snapshot: HarnessSnapshot
    benchmark_suite: BenchmarkSuite
    memory_entries: list[HarnessMemoryEntry] = Field(default_factory=list)
    registered_engines: list[str] = Field(default_factory=list)
    registered_backends: dict[str, str] = Field(default_factory=dict)
    benchmark_profile: str = BenchmarkProfile.full.value
    backend_mode: str | None = None


class _HarnessRuntimeCriticBridge:
    def __init__(self, *, runtime: str, allow_fallback: bool) -> None:
        self.runtime = str(runtime)
        self.allow_fallback = allow_fallback
        self.runtime_used = self.runtime
        self.fallback_used = self.runtime == "legacy"
        self._rule_based = RuleBasedHarnessCritic()
        self._runtime_critic = (
            PydanticAIHarnessCritic(
                fallback_policy=RuntimeFallbackPolicy("on_error" if allow_fallback else "never"),
            )
            if self.runtime != "legacy"
            else None
        )

    def analyze_failures(self, trajectories, current_snapshot):
        if self._runtime_critic is None:
            self.runtime_used = "legacy"
            self.fallback_used = self.runtime != "legacy"
            return self._rule_based.analyze_failures(trajectories, current_snapshot)
        try:
            draft = self._runtime_critic.analyze_failures(
                current_snapshot=current_snapshot.model_dump(mode="json"),
                trajectories=[trajectory.model_dump(mode="json") for trajectory in trajectories],
            )
            self.runtime_used = str(getattr(self._runtime_critic.runtime_used, "value", self._runtime_critic.runtime_used))
            self.fallback_used = bool(getattr(self._runtime_critic, "fallback_used", False))
            return HarnessChangeProposal.model_validate(draft.model_dump())
        except Exception:
            if not self.allow_fallback:
                raise
            self.runtime_used = "legacy"
            self.fallback_used = True
            return self._rule_based.analyze_failures(trajectories, current_snapshot)


def build_snapshot_from_config(config_path: str = "config.yaml") -> HarnessSnapshot:
    with open(config_path, "r") as handle:
        config = yaml.safe_load(handle) or {}

    workers = config.get("workers", {})
    skills = {
        worker_name: SkillDefinition(
            name=worker_name,
            description=f"Worker/skill entry derived from config for {worker_name}",
            enabled=True,
            config=worker_config if isinstance(worker_config, dict) else {"value": worker_config},
        )
        for worker_name, worker_config in workers.items()
        if isinstance(worker_name, str) and worker_name != "default_max_retries"
    }

    orchestrator = config.get("orchestrator", {})
    workflow_rules = [
        f"Respect max_stall_count={orchestrator.get('max_stall_count', 3)}",
        f"Respect max_replan={orchestrator.get('max_replan', 4)}",
        f"Respect max_steps_total={orchestrator.get('max_steps_total', 50)}",
        "Do not modify engine or adapter contracts during harness optimization.",
        "Require human review for skill graph mutations.",
    ]

    return HarnessSnapshot(
        version="harness_config_snapshot_v1",
        skills=skills,
        workflow_rules=workflow_rules,
        sampling_params={"temperature": 0.2},
        metadata={
            "config_path": str(Path(config_path).resolve()),
            "engine_preference": EnginePreference.agentsociety.value,
        },
    )


def build_default_adapter_service(
    run_mapping_path: str | None = None,
    *,
    backend_mode: str | None = None,
) -> AdapterService:
    return build_shared_adapter_service(
        run_mapping_path or str(DEFAULT_HARNESS_RUN_MAPPING_PATH),
        backend_mode=backend_mode,
    )


def resolve_harness_backend_mode(
    *,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    backend_mode: str | None = None,
) -> str | None:
    if backend_mode:
        return backend_mode
    selected = benchmark_profile if isinstance(benchmark_profile, BenchmarkProfile) else BenchmarkProfile(str(benchmark_profile))
    if selected == BenchmarkProfile.interactive:
        return "surrogate"
    return None


def inspect_harness(
    *,
    config_path: str = "config.yaml",
    benchmark_path: str | None = None,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    memory_path: str | None = None,
    backend_mode: str | None = None,
    adapter_service: AdapterService | None = None,
) -> HarnessInspection:
    memory_store = HarnessMemoryStore(memory_path or str(DEFAULT_HARNESS_MEMORY_PATH))
    selected_profile = benchmark_profile if isinstance(benchmark_profile, BenchmarkProfile) else BenchmarkProfile(str(benchmark_profile))
    resolved_backend_mode = resolve_harness_backend_mode(
        benchmark_profile=selected_profile,
        backend_mode=backend_mode,
    )
    service = adapter_service or build_default_adapter_service(backend_mode=resolved_backend_mode)
    return HarnessInspection(
        snapshot=build_snapshot_from_config(config_path),
        benchmark_suite=BenchmarkSuite.load(benchmark_path, profile=selected_profile),
        memory_entries=memory_store.list_recent(limit=20),
        registered_engines=[engine.value for engine in service.adapters.keys()],
        registered_backends={
            engine.value: describe_backend(adapter)
            for engine, adapter in service.adapters.items()
        },
        benchmark_profile=selected_profile.value,
        backend_mode=resolved_backend_mode,
    )


def run_harness_optimization(
    *,
    config_path: str = "config.yaml",
    benchmark_path: str | None = None,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    memory_path: str | None = None,
    run_mapping_path: str | None = None,
    mode: OptimizationMode = OptimizationMode.suggest_only,
    adapter_service: AdapterService | None = None,
    backend_mode: str | None = None,
    runtime: str = "pydanticai",
    allow_fallback: bool = True,
) -> OptimizationRoundResult:
    memory_store = HarnessMemoryStore(memory_path or str(DEFAULT_HARNESS_MEMORY_PATH))
    optimizer = HarnessOptimizer(memory_store=memory_store, mode=mode)
    critic = _HarnessRuntimeCriticBridge(runtime=runtime, allow_fallback=allow_fallback)
    selected_profile = benchmark_profile if isinstance(benchmark_profile, BenchmarkProfile) else BenchmarkProfile(str(benchmark_profile))
    resolved_backend_mode = resolve_harness_backend_mode(
        benchmark_profile=selected_profile,
        backend_mode=backend_mode,
    )
    service = adapter_service or build_default_adapter_service(
        run_mapping_path,
        backend_mode=resolved_backend_mode,
    )
    result = optimizer.run_optimization_round(
        benchmark_suite=BenchmarkSuite.load(benchmark_path, profile=selected_profile),
        current_snapshot=build_snapshot_from_config(config_path),
        adapter_service=service,
        critic=critic,
    )
    result.runtime_requested = runtime
    result.runtime_used = critic.runtime_used
    result.fallback_used = critic.fallback_used
    result.metadata["benchmark_profile"] = selected_profile.value
    result.metadata["backend_mode"] = resolved_backend_mode
    return result
