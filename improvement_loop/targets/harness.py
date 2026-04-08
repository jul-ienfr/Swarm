from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engines.agentsociety import AgentSocietyBenchmarkClient, AgentSocietyProcessClient
from runtime_contracts.adapter_command import EngineTarget
from improvement_loop.models import ImprovementRuntime
from simulation_adapter.service import AdapterService
from swarm_core.benchmark_suite import (
    BenchmarkProfile,
    BenchmarkSuite,
    DEFAULT_BENCHMARK_SUITE_PATH,
    resolve_benchmark_suite_path,
)
from swarm_core.harness_memory import DEFAULT_HARNESS_MEMORY_PATH, HarnessMemoryStore
from swarm_core.harness_optimizer import (
    HarnessChangeProposal,
    HarnessOptimizer,
    OptimizationMode,
    RoundDecision,
    RuleBasedHarnessCritic,
)
from swarm_core.harness_runtime import (
    DEFAULT_HARNESS_RUN_MAPPING_PATH,
    build_default_adapter_service,
    build_snapshot_from_config,
    resolve_harness_backend_mode,
)
from swarm_core.harness_snapshot import HarnessSnapshot
from runtime_pydanticai import RuntimeFallbackPolicy
from runtime_pydanticai.improvement import PydanticAIHarnessCritic

from ..models import ImprovementRoundRecord, LoopDecision, LoopMode, TargetDescriptor, TargetInspection


DEFAULT_HARNESS_TARGET_STATE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "improvement_targets" / "harness_snapshot.json"
)


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fingerprint_json(payload: Any) -> str:
    return _sha256_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    )


def _fingerprint_file(path: str | Path | None) -> str | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class HarnessImprovementTarget:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        benchmark_path: str | None = None,
        memory_path: str | None = None,
        run_mapping_path: str | None = None,
        state_path: str | None = None,
        backend_mode: str | None = None,
        adapter_service: AdapterService | None = None,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
    ) -> None:
        self.config_path = config_path
        self.benchmark_path = benchmark_path
        self.memory_path = memory_path or str(DEFAULT_HARNESS_MEMORY_PATH)
        self.run_mapping_path = run_mapping_path or str(DEFAULT_HARNESS_RUN_MAPPING_PATH)
        self.state_path = Path(state_path or DEFAULT_HARNESS_TARGET_STATE_PATH)
        self.backend_mode = backend_mode
        self._adapter_service = adapter_service
        self._adapter_services: dict[str, AdapterService] = {}
        self.runtime = ImprovementRuntime(runtime)
        self.allow_fallback = allow_fallback

    def describe(self) -> TargetDescriptor:
        return TargetDescriptor(
            target_id="harness",
            description="Generic improvement-loop target backed by the LangGraph swarm harness snapshot and benchmark suite.",
            default_mode=LoopMode.suggest_only,
            default_runtime=self.runtime,
            metadata={
                "config_path": str(Path(self.config_path).resolve()),
                "benchmark_path": str(self._resolve_benchmark_path(BenchmarkProfile.full).resolve()),
                "memory_path": str(Path(self.memory_path).resolve()),
                "state_path": str(self.state_path.resolve()),
                "runtime": self.runtime.value,
                "allow_fallback": self.allow_fallback,
            },
        )

    def inspect(
        self,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
        benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
        backend_mode: str | None = None,
    ) -> TargetInspection:
        snapshot = self._load_current_snapshot()
        selected_profile = self._coerce_benchmark_profile(benchmark_profile)
        benchmark_suite = BenchmarkSuite.load(self.benchmark_path, profile=selected_profile)
        memory_store = HarnessMemoryStore(self.memory_path)
        latest_round_index = memory_store.get_latest_round_index()
        resolved_backend_mode = resolve_harness_backend_mode(
            benchmark_profile=selected_profile,
            backend_mode=backend_mode or self.backend_mode,
        )
        service = self._get_adapter_service(resolved_backend_mode)
        runtime = self._coerce_runtime(runtime)
        return TargetInspection(
            descriptor=self.describe(),
            current_snapshot=snapshot.model_dump(mode="json"),
            benchmark=benchmark_suite.model_dump(mode="json"),
            memory_entries=[entry.model_dump(mode="json") for entry in memory_store.list_recent(limit=20)],
            runtime_used=runtime,
            fallback_used=False,
            metadata={
                "registered_engines": [engine.value for engine in service.adapters.keys()],
                "registered_backends": {
                    engine.value: _describe_backend(adapter)
                    for engine, adapter in service.adapters.items()
                },
                "runtime_requested": runtime.value,
                "allow_fallback": allow_fallback,
                "benchmark_profile": selected_profile.value,
                "backend_mode": resolved_backend_mode,
                "comparability": _build_comparability_metadata(
                    target_id="harness",
                    target_kind="harness",
                    surface="inspection",
                    runtime_requested=runtime,
                    runtime_used=runtime,
                    fallback_used=False,
                    allow_fallback=allow_fallback,
                    config_path=self.config_path,
                    benchmark_path=self._resolve_benchmark_path(selected_profile),
                    snapshot=snapshot,
                    benchmark_suite=benchmark_suite,
                    state_path=self.state_path,
                    memory_path=self.memory_path,
                    backend_mode=resolved_backend_mode,
                    benchmark_profile=selected_profile.value,
                    latest_round_index=latest_round_index,
                ),
            },
        )

    def run_round(
        self,
        mode: LoopMode,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
        benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
        backend_mode: str | None = None,
    ) -> ImprovementRoundRecord:
        snapshot = self._load_current_snapshot()
        selected_profile = self._coerce_benchmark_profile(benchmark_profile)
        benchmark_suite = BenchmarkSuite.load(self.benchmark_path, profile=selected_profile)
        memory_store = HarnessMemoryStore(self.memory_path)
        runtime = self._coerce_runtime(runtime)
        resolved_backend_mode = resolve_harness_backend_mode(
            benchmark_profile=selected_profile,
            backend_mode=backend_mode or self.backend_mode,
        )
        critic = self._build_critic(runtime=runtime, allow_fallback=allow_fallback)
        optimizer = HarnessOptimizer(
            memory_store=memory_store,
            mode=OptimizationMode(mode.value),
        )
        result = optimizer.run_optimization_round(
            benchmark_suite=benchmark_suite,
            current_snapshot=snapshot,
            adapter_service=self._get_adapter_service(resolved_backend_mode),
            critic=critic,
        )
        if mode == LoopMode.safe_auto_apply and result.decision == RoundDecision.keep:
            self._save_snapshot(result.applied_snapshot)

        runtime_used = getattr(critic, "runtime_used", runtime)
        fallback_used = bool(getattr(critic, "fallback_used", runtime == ImprovementRuntime.legacy))

        return ImprovementRoundRecord(
            target_id=self.describe().target_id,
            round_index=result.round_index,
            mode=LoopMode(result.mode.value),
            decision=LoopDecision(result.decision.value),
            baseline_score=result.baseline_score,
            candidate_score=result.candidate_score,
            score_delta=result.score_delta,
            improvement_ratio=result.improvement_ratio,
            current_snapshot=result.current_snapshot.model_dump(mode="json"),
            candidate_snapshot=result.candidate_snapshot.model_dump(mode="json"),
            applied_snapshot=result.applied_snapshot.model_dump(mode="json"),
            proposal=result.proposal.model_dump(mode="json"),
            baseline_report=result.baseline_report.model_dump(mode="json"),
            candidate_report=result.candidate_report.model_dump(mode="json"),
            requires_human_review=result.requires_human_review,
            halted_reason=result.halted_reason,
            runtime_used=runtime_used,
            fallback_used=fallback_used,
            metadata={
                "persisted_snapshot": (
                    str(self.state_path.resolve())
                    if mode == LoopMode.safe_auto_apply and result.decision == RoundDecision.keep
                    else None
                ),
                "benchmark_profile": selected_profile.value,
                "backend_mode": resolved_backend_mode,
                "comparability": _build_comparability_metadata(
                    target_id=self.describe().target_id,
                    target_kind="harness",
                    surface="round",
                    runtime_requested=runtime,
                    runtime_used=runtime_used,
                    fallback_used=fallback_used,
                    allow_fallback=allow_fallback,
                    config_path=self.config_path,
                    benchmark_path=self._resolve_benchmark_path(selected_profile),
                    snapshot=snapshot,
                    benchmark_suite=benchmark_suite,
                    state_path=self.state_path,
                    memory_path=self.memory_path,
                    backend_mode=resolved_backend_mode,
                    benchmark_profile=selected_profile.value,
                    round_index=result.round_index,
                ),
                "runtime_resilience": _build_runtime_resilience_metadata(
                    critic=critic,
                    target_id=self.describe().target_id,
                    runtime_requested=runtime,
                    runtime_used=runtime_used,
                    fallback_used=fallback_used,
                ),
            },
        )

    def _load_current_snapshot(self) -> HarnessSnapshot:
        if self.state_path.exists():
            return HarnessSnapshot.model_validate(json.loads(self.state_path.read_text()))
        return build_snapshot_from_config(self.config_path)

    def _save_snapshot(self, snapshot: HarnessSnapshot) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(snapshot.model_dump_json(indent=2))

    def _get_adapter_service(self, backend_mode: str | None = None) -> AdapterService:
        if self._adapter_service is not None:
            return self._adapter_service
        cache_key = backend_mode or "__default__"
        if cache_key not in self._adapter_services:
            self._adapter_services[cache_key] = build_default_adapter_service(
                self.run_mapping_path,
                backend_mode=backend_mode,
            )
        return self._adapter_services[cache_key]

    def _build_critic(self, *, runtime: ImprovementRuntime, allow_fallback: bool):
        if runtime == ImprovementRuntime.legacy:
            return RuleBasedHarnessCritic()
        return _PydanticAIHarnessCriticBridge(
            runtime_critic=PydanticAIHarnessCritic(
                config_path=self.config_path,
                fallback_policy=RuntimeFallbackPolicy.on_error if allow_fallback else RuntimeFallbackPolicy.never,
            ),
            allow_fallback=allow_fallback,
        )

    @staticmethod
    def _coerce_runtime(runtime: ImprovementRuntime | str) -> ImprovementRuntime:
        return runtime if isinstance(runtime, ImprovementRuntime) else ImprovementRuntime(str(runtime))

    @staticmethod
    def _coerce_benchmark_profile(profile: BenchmarkProfile | str) -> BenchmarkProfile:
        return profile if isinstance(profile, BenchmarkProfile) else BenchmarkProfile(str(profile))

    def _resolve_benchmark_path(self, profile: BenchmarkProfile | str) -> Path:
        return resolve_benchmark_suite_path(self.benchmark_path, profile=profile)


def _build_comparability_metadata(
    *,
    target_id: str,
    target_kind: str,
    surface: str,
    runtime_requested: ImprovementRuntime,
    runtime_used: ImprovementRuntime,
    fallback_used: bool,
    allow_fallback: bool,
    config_path: str | Path,
    benchmark_path: str | Path,
    snapshot: HarnessSnapshot,
    benchmark_suite: BenchmarkSuite,
    state_path: str | Path | None,
    memory_path: str | Path | None,
    backend_mode: str | None,
    benchmark_profile: str | None,
    latest_round_index: int | None = None,
    round_index: int | None = None,
) -> dict[str, Any]:
    resolved_config_path = str(Path(config_path).resolve())
    resolved_benchmark_path = str(Path(benchmark_path).resolve())
    resolved_state_path = str(Path(state_path).resolve()) if state_path is not None else None
    resolved_memory_path = str(Path(memory_path).resolve()) if memory_path is not None else None
    config_fingerprint = _fingerprint_file(config_path)
    benchmark_fingerprint = _fingerprint_file(benchmark_path)
    state_fingerprint = _fingerprint_file(state_path) or _fingerprint_json(snapshot.model_dump(mode="json"))
    memory_fingerprint = _fingerprint_file(memory_path)
    comparability: dict[str, Any] = {
        "target_id": target_id,
        "target_kind": target_kind,
        "surface": surface,
        "runtime_requested": runtime_requested.value,
        "runtime_used": runtime_used.value,
        "runtime_match": runtime_requested.value == runtime_used.value,
        "fallback_used": fallback_used,
        "allow_fallback": allow_fallback,
        "config_path": resolved_config_path,
        "benchmark_path": resolved_benchmark_path,
        "state_path": resolved_state_path,
        "memory_path": resolved_memory_path,
        "backend_mode": backend_mode,
        "benchmark_profile": benchmark_profile,
        "benchmark_suite_version": benchmark_suite.suite_version,
        "snapshot_version": snapshot.version,
        "config_fingerprint": config_fingerprint,
        "benchmark_fingerprint": benchmark_fingerprint,
        "state_fingerprint": state_fingerprint,
        "memory_fingerprint": memory_fingerprint,
    }
    if latest_round_index is not None:
        comparability["latest_round_index"] = latest_round_index
    if round_index is not None:
        comparability["round_index"] = round_index
    target_fingerprint_source = {
        "target_id": target_id,
        "target_kind": target_kind,
        "surface": surface,
        "runtime_requested": runtime_requested.value,
        "runtime_used": runtime_used.value,
        "runtime_match": runtime_requested.value == runtime_used.value,
        "fallback_used": fallback_used,
        "allow_fallback": allow_fallback,
        "config_fingerprint": config_fingerprint,
        "benchmark_fingerprint": benchmark_fingerprint,
        "state_fingerprint": state_fingerprint,
        "memory_fingerprint": memory_fingerprint,
        "backend_mode": backend_mode,
        "benchmark_profile": benchmark_profile,
        "snapshot_version": snapshot.version,
        "benchmark_suite_version": benchmark_suite.suite_version,
    }
    if latest_round_index is not None:
        target_fingerprint_source["latest_round_index"] = latest_round_index
    if round_index is not None:
        target_fingerprint_source["round_index"] = round_index
    comparability["target_fingerprint"] = _fingerprint_json(target_fingerprint_source)
    return comparability


def _build_runtime_resilience_metadata(
    *,
    critic: Any,
    target_id: str,
    runtime_requested: ImprovementRuntime,
    runtime_used: ImprovementRuntime,
    fallback_used: bool,
) -> dict[str, Any]:
    source = getattr(critic, "runtime_critic", critic)
    runtime_resilience = getattr(source, "runtime_resilience", None)
    if hasattr(runtime_resilience, "model_dump"):
        runtime_resilience = runtime_resilience.model_dump(mode="json")
    elif hasattr(runtime_resilience, "dict"):
        runtime_resilience = runtime_resilience.dict()
    resilience: dict[str, Any] = {}

    def _pick(key: str, *fallback_keys: str, attr: str | None = None) -> Any:
        if isinstance(runtime_resilience, dict):
            for candidate in (key, *fallback_keys):
                if candidate in runtime_resilience and runtime_resilience[candidate] is not None:
                    return runtime_resilience[candidate]
        if attr is not None and hasattr(source, attr):
            value = getattr(source, attr)
            if value is not None:
                return value
        return None

    resilience["target_id"] = target_id
    resilience["critic"] = "harness"
    resilience["runtime_requested"] = runtime_requested.value
    resilience["runtime_used"] = runtime_used.value
    runtime_match = runtime_requested.value == runtime_used.value
    resilience["runtime_match"] = runtime_match
    resilience["fallback_used"] = fallback_used

    source_status = _pick("status")
    attempt_count = _pick("attempt_count", attr="last_attempt_count")
    retry_count = _pick("retry_count", attr="last_retry_count")
    retry_reasons = _pick("retry_reasons", attr="last_retry_reasons")
    runtime_error = _pick("runtime_error", "error", attr="last_error")
    runtime_error_category = _pick(
        "runtime_error_category",
        "error_category",
        attr="last_error_category",
    )
    runtime_error_retryable = _pick(
        "runtime_error_retryable",
        "error_retryable",
        attr="last_error_retryable",
    )
    fallback_mode = _pick("fallback_mode", attr="last_fallback_mode")
    backoff_total_seconds = _pick("backoff_total_seconds", attr="last_backoff_total_seconds")
    retry_budget_exhausted = _pick("retry_budget_exhausted", attr="last_retry_budget_exhausted")
    immediate_fallback = _pick("immediate_fallback", attr="last_immediate_fallback")
    diagnostics = _pick("diagnostics", attr="last_diagnostics")
    score = _pick("score")

    if fallback_mode is None and fallback_used and not runtime_match and runtime_error is None:
        fallback_mode = "post_validation_fallback"

    status = "healthy"
    if fallback_used or not runtime_match or runtime_error:
        status = "degraded"
    elif retry_count or backoff_total_seconds:
        status = "guarded"
    elif source_status in {"guarded", "degraded"}:
        status = source_status
    resilience["status"] = status
    if attempt_count is not None:
        resilience["attempt_count"] = int(attempt_count)
    if retry_count is not None:
        resilience["retry_count"] = int(retry_count)
    if retry_reasons:
        resilience["retry_reasons"] = list(retry_reasons)
    if runtime_error is not None:
        resilience["runtime_error"] = runtime_error
    if runtime_error_category is not None:
        resilience["runtime_error_category"] = runtime_error_category
    if runtime_error_retryable is not None:
        resilience["runtime_error_retryable"] = bool(runtime_error_retryable)
    if fallback_mode is not None:
        resilience["fallback_mode"] = fallback_mode
    if backoff_total_seconds is not None:
        resilience["backoff_total_seconds"] = float(backoff_total_seconds)
    if retry_budget_exhausted is not None:
        resilience["retry_budget_exhausted"] = bool(retry_budget_exhausted)
    if immediate_fallback is not None:
        resilience["immediate_fallback"] = bool(immediate_fallback)
    if diagnostics:
        resilience["diagnostics"] = list(diagnostics)
    if score is None:
        score = 1.0
        if retry_count:
            score -= min(0.15, 0.05 * int(retry_count))
        if fallback_used or not runtime_match:
            score -= 0.2
        if retry_budget_exhausted:
            score -= 0.08
        if immediate_fallback:
            score -= 0.05
        if runtime_error and not fallback_used:
            score -= 0.04
        score = max(0.0, min(1.0, score))
    resilience["score"] = round(float(score), 3)

    summary_parts = [
        status,
        f"attempts={int(attempt_count or 0)}",
        f"retries={int(retry_count or 0)}",
        f"runtime={runtime_used.value}",
    ]
    if not runtime_match:
        summary_parts.append(f"requested={runtime_requested.value}")
    if fallback_used:
        summary_parts.append("fallback=yes")
    if fallback_mode:
        summary_parts.append(f"mode={fallback_mode}")
    if runtime_error_category:
        summary_parts.append(f"error={runtime_error_category}")
    elif runtime_error:
        summary_parts.append("error=present")
    if backoff_total_seconds:
        summary_parts.append(f"backoff={float(backoff_total_seconds):.3f}s")
    if diagnostics:
        summary_parts.append(f"diagnostics={len(diagnostics)}")
    resilience["summary"] = " | ".join(summary_parts)
    return resilience


class _PydanticAIHarnessCriticBridge:
    def __init__(self, *, runtime_critic: PydanticAIHarnessCritic, allow_fallback: bool) -> None:
        self.runtime_critic = runtime_critic
        self.allow_fallback = allow_fallback
        self.runtime_used: ImprovementRuntime = ImprovementRuntime.pydanticai
        self.fallback_used: bool = False

    def analyze_failures(self, trajectories, current_snapshot):
        try:
            draft = self.runtime_critic.analyze_failures(
                current_snapshot=current_snapshot.model_dump(mode="json"),
                trajectories=[trajectory.model_dump(mode="json") for trajectory in trajectories],
            )
            proposal = HarnessChangeProposal.model_validate(
                {
                    "summary": draft.summary,
                    "rationale": draft.rationale,
                    "workflow_rules_to_add": draft.workflow_rules_to_add,
                    "workflow_rules_to_remove": draft.workflow_rules_to_remove,
                    "sampling_param_overrides": draft.sampling_param_overrides,
                    "risk_level": draft.risk_level,
                    "requires_human_review": draft.requires_human_review,
                }
            )
            if trajectories and not proposal.has_changes():
                self.runtime_used = ImprovementRuntime.legacy
                self.fallback_used = True
                return RuleBasedHarnessCritic().analyze_failures(trajectories, current_snapshot)
            self.runtime_used = ImprovementRuntime(
                str(getattr(self.runtime_critic.runtime_used, "value", self.runtime_critic.runtime_used))
            )
            self.fallback_used = bool(self.runtime_critic.fallback_used)
            return proposal
        except Exception:
            if not self.allow_fallback:
                raise
            self.runtime_used = ImprovementRuntime.legacy
            self.fallback_used = True
            return RuleBasedHarnessCritic().analyze_failures(trajectories, current_snapshot)


def _describe_backend(adapter) -> str:
    client = getattr(adapter, "_client", None)
    if isinstance(client, AgentSocietyBenchmarkClient):
        return "surrogate"
    if isinstance(client, AgentSocietyProcessClient):
        return "live"
    return type(client).__name__ if client is not None else "unknown"
