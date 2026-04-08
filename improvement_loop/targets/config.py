from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

from improvement_loop.memory import LoopMemoryEntryType, LoopMemoryStore
from improvement_loop.models import ImprovementRuntime
from swarm_core.harness_snapshot import RiskLevel

from ..models import ImprovementRoundRecord, LoopDecision, LoopMode, TargetDescriptor, TargetInspection
from runtime_pydanticai import RuntimeFallbackPolicy
from runtime_pydanticai.improvement import PydanticAIConfigCritic


DEFAULT_CONFIG_TARGET_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "config_target_benchmark_v1.json"
)
DEFAULT_CONFIG_TARGET_MEMORY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "improvement_targets" / "config_target_memory.db"
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


def _build_runtime_resilience_metadata(
    *,
    critic: Any,
    target_id: str,
    runtime_requested: ImprovementRuntime,
    runtime_used: ImprovementRuntime,
    fallback_used: bool,
) -> dict[str, Any]:
    runtime_resilience = getattr(critic, "runtime_resilience", None)
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
        if attr is not None and hasattr(critic, attr):
            value = getattr(critic, attr)
            if value is not None:
                return value
        return None

    resilience["target_id"] = target_id
    resilience["critic"] = "config"
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
    snapshot: ConfigTargetSnapshot,
    benchmark_suite: ConfigBenchmarkSuite,
    memory_path: str | Path | None,
    latest_round_index: int | None = None,
    round_index: int | None = None,
) -> dict[str, Any]:
    resolved_config_path = str(Path(config_path).resolve())
    resolved_benchmark_path = str(Path(benchmark_path).resolve())
    resolved_memory_path = str(Path(memory_path).resolve()) if memory_path is not None else None
    config_fingerprint = _fingerprint_file(config_path)
    benchmark_fingerprint = _fingerprint_file(benchmark_path)
    state_fingerprint = _fingerprint_json(snapshot.model_dump(mode="json"))
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
        "memory_path": resolved_memory_path,
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
        "benchmark_suite_version": benchmark_suite.suite_version,
        "snapshot_version": snapshot.version,
    }
    if latest_round_index is not None:
        target_fingerprint_source["latest_round_index"] = latest_round_index
    if round_index is not None:
        target_fingerprint_source["round_index"] = round_index
    comparability["target_fingerprint"] = _fingerprint_json(target_fingerprint_source)
    return comparability


class OrchestratorConfigSnapshot(BaseModel):
    max_stall_count: int = 3
    max_replan: int = 4
    max_steps_total: int = 50


class WorkerConfigSnapshot(BaseModel):
    default_tier: str | None = None
    auto_lint_patch: bool | None = None
    max_search_depth: int | None = None


class ConfigTargetSnapshot(BaseModel):
    snapshot_version: str = "v1"
    version: str = Field(default_factory=lambda: f"config_snapshot_{uuid4().hex[:12]}")
    model_escalation_policy: bool = True
    default_max_retries: int = 5
    orchestrator: OrchestratorConfigSnapshot = Field(default_factory=OrchestratorConfigSnapshot)
    studio_dev: WorkerConfigSnapshot = Field(default_factory=WorkerConfigSnapshot)
    veille_strategique: WorkerConfigSnapshot = Field(default_factory=WorkerConfigSnapshot)
    metadata: dict[str, str] = Field(default_factory=dict)

    def clone_with(
        self,
        *,
        version: str | None = None,
        model_escalation_policy: bool | None = None,
        default_max_retries: int | None = None,
        orchestrator: OrchestratorConfigSnapshot | None = None,
        studio_dev: WorkerConfigSnapshot | None = None,
        veille_strategique: WorkerConfigSnapshot | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "ConfigTargetSnapshot":
        return ConfigTargetSnapshot(
            snapshot_version=self.snapshot_version,
            version=version or f"{self.version}_cand",
            model_escalation_policy=(
                self.model_escalation_policy if model_escalation_policy is None else model_escalation_policy
            ),
            default_max_retries=self.default_max_retries if default_max_retries is None else default_max_retries,
            orchestrator=orchestrator or self.orchestrator.model_copy(deep=True),
            studio_dev=studio_dev or self.studio_dev.model_copy(deep=True),
            veille_strategique=veille_strategique or self.veille_strategique.model_copy(deep=True),
            metadata=metadata or dict(self.metadata),
        )


class ConfigBenchmarkSignals(BaseModel):
    orchestrator_error_rate: float = 0.0
    long_horizon_complexity: float = 0.0
    retryable_failure_rate: float = 0.0
    syntax_failure_rate: float = 0.0
    search_token_pressure: float = 0.0
    search_miss_rate: float = 0.0


class ConfigBenchmarkExpectation(BaseModel):
    min_score: float = 0.8


class ConfigBenchmarkCase(BaseModel):
    case_id: str
    description: str
    weight: float = 1.0
    signals: ConfigBenchmarkSignals = Field(default_factory=ConfigBenchmarkSignals)
    expectation: ConfigBenchmarkExpectation = Field(default_factory=ConfigBenchmarkExpectation)


class ConfigBenchmarkSuite(BaseModel):
    suite_version: str = "v1"
    name: str = "default_config_target_benchmark_suite"
    metadata: dict[str, str] = Field(default_factory=dict)
    cases: list[ConfigBenchmarkCase]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ConfigBenchmarkSuite":
        suite_path = Path(path) if path else DEFAULT_CONFIG_TARGET_BENCHMARK_PATH
        return cls.model_validate(json.loads(suite_path.read_text()))


class ConfigBenchmarkOutcome(BaseModel):
    case_id: str
    score: float
    weight: float
    summary: str
    metrics: dict[str, float] = Field(default_factory=dict)


class ConfigFailureTrajectory(BaseModel):
    case_id: str
    score: float
    summary: str
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


class ConfigBenchmarkReport(BaseModel):
    suite_version: str
    snapshot_version: str
    score: float
    outcomes: list[ConfigBenchmarkOutcome] = Field(default_factory=list)
    trajectories: list[ConfigFailureTrajectory] = Field(default_factory=list)


class ConfigChangeProposal(BaseModel):
    summary: str
    rationale: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.low
    requires_human_review: bool = False
    orchestrator_updates: dict[str, int] = Field(default_factory=dict)
    studio_dev_updates: dict[str, bool] = Field(default_factory=dict)
    veille_updates: dict[str, int] = Field(default_factory=dict)
    top_level_updates: dict[str, int | bool] = Field(default_factory=dict)

    def has_changes(self) -> bool:
        return any(
            [
                self.orchestrator_updates,
                self.studio_dev_updates,
                self.veille_updates,
                self.top_level_updates,
            ]
        )


class ConfigImprovementTarget:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        benchmark_path: str | None = None,
        memory_path: str | None = None,
        keep_threshold: float = 0.02,
        stagnation_limit: int = 3,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
    ) -> None:
        self.config_path = config_path
        self.benchmark_path = benchmark_path or str(DEFAULT_CONFIG_TARGET_BENCHMARK_PATH)
        self.memory_store = LoopMemoryStore(memory_path or str(DEFAULT_CONFIG_TARGET_MEMORY_PATH))
        self.keep_threshold = keep_threshold
        self.stagnation_limit = stagnation_limit
        self.target_id = "config"
        self.runtime = ImprovementRuntime(runtime)
        self.allow_fallback = allow_fallback

    def describe(self) -> TargetDescriptor:
        return TargetDescriptor(
            target_id=self.target_id,
            description="Improves a safe, bounded subset of config.yaml using a dedicated config benchmark suite.",
            default_mode=LoopMode.suggest_only,
            default_runtime=self.runtime,
            metadata={
                "config_path": str(Path(self.config_path).resolve()),
                "benchmark_path": str(Path(self.benchmark_path).resolve()),
                "runtime": self.runtime.value,
                "allow_fallback": self.allow_fallback,
            },
        )

    def inspect(
        self,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
    ) -> TargetInspection:
        snapshot = self._load_snapshot()
        benchmark_suite = ConfigBenchmarkSuite.load(self.benchmark_path)
        runtime = self._coerce_runtime(runtime)
        latest_round_index = self.memory_store.get_latest_round_index(target_id=self.target_id)
        return TargetInspection(
            descriptor=self.describe(),
            current_snapshot=snapshot.model_dump(mode="json"),
            benchmark=benchmark_suite.model_dump(mode="json"),
            memory_entries=[
                entry.model_dump(mode="json")
                for entry in self.memory_store.list_recent(target_id=self.target_id, limit=20)
            ],
            runtime_used=runtime,
            fallback_used=False,
            metadata={
                "modifiable_fields": self._modifiable_fields(),
                "runtime_requested": runtime.value,
                "allow_fallback": allow_fallback,
                "comparability": _build_comparability_metadata(
                    target_id=self.target_id,
                    target_kind="config",
                    surface="inspection",
                    runtime_requested=runtime,
                    runtime_used=runtime,
                    fallback_used=False,
                    allow_fallback=allow_fallback,
                    config_path=self.config_path,
                    benchmark_path=self.benchmark_path,
                    snapshot=snapshot,
                    benchmark_suite=benchmark_suite,
                    memory_path=self.memory_store.db_path,
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
    ) -> ImprovementRoundRecord:
        snapshot = self._load_snapshot()
        benchmark_suite = ConfigBenchmarkSuite.load(self.benchmark_path)
        runtime = self._coerce_runtime(runtime)
        round_index = self.memory_store.get_latest_round_index(target_id=self.target_id) + 1

        if self.memory_store.consecutive_non_improvements(target_id=self.target_id, limit=self.stagnation_limit) >= self.stagnation_limit:
            record = self._build_halt_record(round_index, snapshot, benchmark_suite, mode)
            self.memory_store.write_round_feedback(
                target_id=self.target_id,
                round_index=round_index,
                entry_type=LoopMemoryEntryType.decision,
                summary=record.halted_reason or "Config optimization halted due to stagnation.",
                details={"decision": record.decision.value},
                candidate_version=snapshot.version,
                applied=False,
                score_delta=0.0,
            )
            return record

        baseline_report = self._run_benchmark(snapshot, benchmark_suite)
        critic = self._build_runtime_critic(runtime=runtime, allow_fallback=allow_fallback)
        proposal, runtime_used, fallback_used = self._propose_changes_with_runtime(
            snapshot,
            baseline_report.trajectories,
            runtime=runtime,
            allow_fallback=allow_fallback,
            critic=critic,
        )
        candidate_snapshot = self._apply_proposal(snapshot, proposal)
        candidate_report = self._run_benchmark(candidate_snapshot, benchmark_suite)

        baseline_score = baseline_report.score
        candidate_score = candidate_report.score
        score_delta = candidate_score - baseline_score
        improvement_ratio = (score_delta / baseline_score) if baseline_score > 0 else (1.0 if candidate_score > 0 else 0.0)

        if baseline_score > 0:
            keep_candidate = candidate_score >= baseline_score * (1 + self.keep_threshold)
        else:
            keep_candidate = candidate_score > 0

        if mode == LoopMode.safe_auto_apply and keep_candidate and not proposal.requires_human_review:
            decision = LoopDecision.keep
            applied_snapshot = candidate_snapshot
            applied = True
            self._write_snapshot_to_config(applied_snapshot)
        elif keep_candidate:
            decision = LoopDecision.propose
            applied_snapshot = snapshot
            applied = False
        else:
            decision = LoopDecision.revert
            applied_snapshot = snapshot
            applied = False

        self.memory_store.write_round_feedback(
            target_id=self.target_id,
            round_index=round_index,
            entry_type=LoopMemoryEntryType.benchmark,
            summary="Completed config baseline and candidate benchmark runs.",
            details={
                "baseline_score": baseline_score,
                "candidate_score": candidate_score,
                "suite_version": benchmark_suite.suite_version,
            },
            candidate_version=candidate_snapshot.version,
            applied=applied,
            score_delta=score_delta,
        )
        self.memory_store.write_round_feedback(
            target_id=self.target_id,
            round_index=round_index,
            entry_type=LoopMemoryEntryType.self_critique,
            summary=proposal.summary,
            details=proposal.model_dump(mode="json"),
            candidate_version=candidate_snapshot.version,
            applied=False,
            score_delta=score_delta,
        )
        self.memory_store.write_round_feedback(
            target_id=self.target_id,
            round_index=round_index,
            entry_type=LoopMemoryEntryType.decision,
            summary=f"Round {round_index}: {decision.value}",
            details={
                "baseline_score": baseline_score,
                "candidate_score": candidate_score,
                "improvement_ratio": improvement_ratio,
            },
            candidate_version=candidate_snapshot.version,
            applied=applied,
            score_delta=score_delta,
        )

        return ImprovementRoundRecord(
            target_id=self.target_id,
            round_index=round_index,
            mode=mode,
            decision=decision,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            score_delta=score_delta,
            improvement_ratio=improvement_ratio,
            current_snapshot=snapshot.model_dump(mode="json"),
            candidate_snapshot=candidate_snapshot.model_dump(mode="json"),
            applied_snapshot=applied_snapshot.model_dump(mode="json"),
            proposal=proposal.model_dump(mode="json"),
            baseline_report=baseline_report.model_dump(mode="json"),
            candidate_report=candidate_report.model_dump(mode="json"),
            requires_human_review=proposal.requires_human_review,
            runtime_used=runtime_used,
            fallback_used=fallback_used,
            metadata={
                "config_path": str(Path(self.config_path).resolve()),
                "comparability": _build_comparability_metadata(
                    target_id=self.target_id,
                    target_kind="config",
                    surface="round",
                    runtime_requested=runtime,
                    runtime_used=runtime_used,
                    fallback_used=fallback_used,
                    allow_fallback=allow_fallback,
                    config_path=self.config_path,
                    benchmark_path=self.benchmark_path,
                    snapshot=snapshot,
                    benchmark_suite=benchmark_suite,
                    memory_path=self.memory_store.db_path,
                    latest_round_index=round_index - 1,
                    round_index=round_index,
                ),
                "runtime_resilience": _build_runtime_resilience_metadata(
                    critic=critic,
                    target_id=self.target_id,
                    runtime_requested=runtime,
                    runtime_used=runtime_used,
                    fallback_used=fallback_used,
                ),
            },
        )

    def _load_snapshot(self) -> ConfigTargetSnapshot:
        config = self._load_config_yaml()
        workers = config.get("workers", {}) or {}
        return ConfigTargetSnapshot(
            version="config_target_snapshot_v1",
            model_escalation_policy=bool(config.get("model_escalation_policy", True)),
            default_max_retries=int(workers.get("default_max_retries", 5) or 5),
            orchestrator=OrchestratorConfigSnapshot.model_validate(config.get("orchestrator", {}) or {}),
            studio_dev=WorkerConfigSnapshot.model_validate(workers.get("studio-dev", {}) or {}),
            veille_strategique=WorkerConfigSnapshot.model_validate(workers.get("veille-strategique", {}) or {}),
            metadata={"config_path": str(Path(self.config_path).resolve())},
        )

    def _load_config_yaml(self) -> dict:
        with open(self.config_path, "r") as handle:
            return yaml.safe_load(handle) or {}

    def _write_snapshot_to_config(self, snapshot: ConfigTargetSnapshot) -> None:
        config = self._load_config_yaml()
        config["model_escalation_policy"] = snapshot.model_escalation_policy
        config.setdefault("orchestrator", {})
        config["orchestrator"]["max_stall_count"] = snapshot.orchestrator.max_stall_count
        config["orchestrator"]["max_replan"] = snapshot.orchestrator.max_replan
        config["orchestrator"]["max_steps_total"] = snapshot.orchestrator.max_steps_total
        config.setdefault("workers", {})
        config["workers"]["default_max_retries"] = snapshot.default_max_retries
        config["workers"].setdefault("studio-dev", {})
        if snapshot.studio_dev.default_tier is not None:
            config["workers"]["studio-dev"]["default_tier"] = snapshot.studio_dev.default_tier
        if snapshot.studio_dev.auto_lint_patch is not None:
            config["workers"]["studio-dev"]["auto_lint_patch"] = snapshot.studio_dev.auto_lint_patch
        config["workers"].setdefault("veille-strategique", {})
        if snapshot.veille_strategique.default_tier is not None:
            config["workers"]["veille-strategique"]["default_tier"] = snapshot.veille_strategique.default_tier
        if snapshot.veille_strategique.max_search_depth is not None:
            config["workers"]["veille-strategique"]["max_search_depth"] = snapshot.veille_strategique.max_search_depth

        with open(self.config_path, "w") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)

    def _run_benchmark(
        self,
        snapshot: ConfigTargetSnapshot,
        benchmark_suite: ConfigBenchmarkSuite,
    ) -> ConfigBenchmarkReport:
        outcomes: list[ConfigBenchmarkOutcome] = []
        trajectories: list[ConfigFailureTrajectory] = []
        weighted_scores: list[float] = []
        weights: list[float] = []

        for case in benchmark_suite.cases:
            metrics = self._evaluate_metrics(snapshot, case.signals)
            case_score = self._score_case(metrics)
            summary = ", ".join(f"{key}={value:.2f}" for key, value in metrics.items())
            outcomes.append(
                ConfigBenchmarkOutcome(
                    case_id=case.case_id,
                    score=case_score,
                    weight=case.weight,
                    summary=summary,
                    metrics=metrics,
                )
            )
            weighted_scores.append(case_score * case.weight)
            weights.append(case.weight)
            if case_score < case.expectation.min_score:
                trajectories.append(
                    ConfigFailureTrajectory(
                        case_id=case.case_id,
                        score=case_score,
                        summary=summary,
                        metrics=metrics,
                        notes=case.description,
                    )
                )

        score = sum(weighted_scores) / sum(weights) if weights else 0.0
        return ConfigBenchmarkReport(
            suite_version=benchmark_suite.suite_version,
            snapshot_version=snapshot.version,
            score=score,
            outcomes=outcomes,
            trajectories=trajectories,
        )

    def _evaluate_metrics(
        self,
        snapshot: ConfigTargetSnapshot,
        signals: ConfigBenchmarkSignals,
    ) -> dict[str, float]:
        metrics: dict[str, float] = {}
        if signals.orchestrator_error_rate > 0:
            target_stall = 4 if signals.orchestrator_error_rate >= 0.25 else 3
            target_replan = 5 if signals.orchestrator_error_rate >= 0.25 else 4
            target_steps = 60 if (signals.orchestrator_error_rate >= 0.25 or signals.long_horizon_complexity >= 0.5) else 50
            metrics["orchestrator_resilience"] = round(
                mean(
                    [
                        min(1.0, snapshot.orchestrator.max_stall_count / target_stall),
                        min(1.0, snapshot.orchestrator.max_replan / target_replan),
                        min(1.0, snapshot.orchestrator.max_steps_total / target_steps),
                    ]
                ),
                3,
            )
        if signals.retryable_failure_rate > 0:
            target_retries = 6 if signals.retryable_failure_rate >= 0.3 else 5
            metrics["retry_budget_fit"] = round(min(1.0, snapshot.default_max_retries / target_retries), 3)
        if signals.syntax_failure_rate > 0:
            metrics["coding_guardrail_fit"] = 1.0 if snapshot.studio_dev.auto_lint_patch else 0.0

        if signals.search_token_pressure > 0 or signals.search_miss_rate > 0:
            if signals.search_token_pressure >= 0.6 and signals.search_miss_rate <= 0.2:
                ideal_depth = 2
            elif signals.search_miss_rate >= 0.4 and signals.search_token_pressure <= 0.3:
                ideal_depth = 4
            else:
                ideal_depth = 3
            depth = snapshot.veille_strategique.max_search_depth or 3
            metrics["search_depth_fit"] = round(max(0.0, 1.0 - (abs(depth - ideal_depth) / 2.0)), 3)

        if not metrics:
            metrics["neutral_fit"] = 1.0
        return metrics

    @staticmethod
    def _score_case(metrics: dict[str, float]) -> float:
        return round(mean(metrics.values()) if metrics else 0.0, 3)

    def _propose_changes_with_runtime(
        self,
        snapshot: ConfigTargetSnapshot,
        trajectories: list[ConfigFailureTrajectory],
        *,
        runtime: ImprovementRuntime,
        allow_fallback: bool,
        critic: Any | None = None,
    ) -> tuple[ConfigChangeProposal, ImprovementRuntime, bool]:
        if runtime == ImprovementRuntime.legacy:
            return self._propose_changes(snapshot, trajectories), ImprovementRuntime.legacy, False

        try:
            critic = critic or self._build_runtime_critic(runtime=runtime, allow_fallback=allow_fallback)
            assert critic is not None
            draft = critic.propose(
                snapshot=snapshot.model_dump(mode="json"),
                trajectories=[trajectory.model_dump(mode="json") for trajectory in trajectories],
            )
            proposal = ConfigChangeProposal.model_validate(draft.model_dump())
            if trajectories and not proposal.has_changes():
                return self._propose_changes(snapshot, trajectories), ImprovementRuntime.legacy, True
            return proposal, self._coerce_runtime_backend(critic.runtime_used), bool(critic.fallback_used)
        except Exception:
            if not allow_fallback:
                raise
            return self._propose_changes(snapshot, trajectories), ImprovementRuntime.legacy, True

    def _build_runtime_critic(
        self,
        *,
        runtime: ImprovementRuntime,
        allow_fallback: bool,
    ) -> PydanticAIConfigCritic | None:
        if runtime == ImprovementRuntime.legacy:
            return None
        return PydanticAIConfigCritic(
            config_path=self.config_path,
            fallback_policy=RuntimeFallbackPolicy.on_error if allow_fallback else RuntimeFallbackPolicy.never,
        )

    def _propose_changes(
        self,
        snapshot: ConfigTargetSnapshot,
        trajectories: list[ConfigFailureTrajectory],
    ) -> ConfigChangeProposal:
        if not trajectories:
            return ConfigChangeProposal(summary="No config changes proposed; config benchmark is healthy.")

        rationale: list[str] = []
        orchestrator_updates: dict[str, int] = {}
        studio_dev_updates: dict[str, bool] = {}
        veille_updates: dict[str, int] = {}
        top_level_updates: dict[str, int | bool] = {}

        if any(t.metrics.get("orchestrator_resilience", 1.0) < 0.95 for t in trajectories):
            orchestrator_updates["max_stall_count"] = min(5, snapshot.orchestrator.max_stall_count + 1)
            orchestrator_updates["max_replan"] = min(6, snapshot.orchestrator.max_replan + 1)
            orchestrator_updates["max_steps_total"] = min(80, snapshot.orchestrator.max_steps_total + 10)
            rationale.append("Low orchestrator resilience suggests slightly more tolerance for replans and stalls.")

        if any(t.metrics.get("retry_budget_fit", 1.0) < 0.95 for t in trajectories):
            top_level_updates["default_max_retries"] = min(8, snapshot.default_max_retries + 1)
            rationale.append("Retry pressure suggests increasing default_max_retries within the safe range.")

        if any(t.metrics.get("coding_guardrail_fit", 1.0) < 1.0 for t in trajectories):
            studio_dev_updates["auto_lint_patch"] = True
            rationale.append("Syntax-quality pressure suggests keeping auto_lint_patch enabled.")

        depth_issues = [t.metrics.get("search_depth_fit") for t in trajectories if "search_depth_fit" in t.metrics]
        if depth_issues:
            failing_depth_case = next(
                (t for t in trajectories if "search_depth_fit" in t.metrics and t.metrics["search_depth_fit"] < 0.95),
                None,
            )
            if failing_depth_case:
                if snapshot.veille_strategique.max_search_depth is None:
                    current_depth = 3
                else:
                    current_depth = snapshot.veille_strategique.max_search_depth
                if current_depth >= 3:
                    veille_updates["max_search_depth"] = max(1, current_depth - 1)
                else:
                    veille_updates["max_search_depth"] = min(5, current_depth + 1)
                rationale.append("Search-depth pressure suggests tuning max_search_depth toward the benchmark optimum.")

        if not any([orchestrator_updates, studio_dev_updates, veille_updates, top_level_updates]):
            return ConfigChangeProposal(summary="No config changes proposed; failing trajectories were not actionable.")

        return ConfigChangeProposal(
            summary="Rule-based config critic proposes a bounded update to safe config knobs.",
            rationale=rationale,
            orchestrator_updates=orchestrator_updates,
            studio_dev_updates=studio_dev_updates,
            veille_updates=veille_updates,
            top_level_updates=top_level_updates,
            risk_level=RiskLevel.low,
            requires_human_review=False,
        )

    @staticmethod
    def _coerce_runtime(runtime: ImprovementRuntime | str) -> ImprovementRuntime:
        return runtime if isinstance(runtime, ImprovementRuntime) else ImprovementRuntime(str(runtime))

    @staticmethod
    def _coerce_runtime_backend(runtime_backend) -> ImprovementRuntime:
        return ImprovementRuntime(str(getattr(runtime_backend, "value", runtime_backend)))

    @staticmethod
    def _apply_proposal(snapshot: ConfigTargetSnapshot, proposal: ConfigChangeProposal) -> ConfigTargetSnapshot:
        orchestrator = snapshot.orchestrator.model_copy(deep=True)
        for key, value in proposal.orchestrator_updates.items():
            setattr(orchestrator, key, value)

        studio_dev = snapshot.studio_dev.model_copy(deep=True)
        for key, value in proposal.studio_dev_updates.items():
            setattr(studio_dev, key, value)

        veille = snapshot.veille_strategique.model_copy(deep=True)
        for key, value in proposal.veille_updates.items():
            setattr(veille, key, value)

        top_level = dict(proposal.top_level_updates)
        return snapshot.clone_with(
            version=f"{snapshot.version}_cand_{uuid4().hex[:6]}",
            default_max_retries=int(top_level.get("default_max_retries", snapshot.default_max_retries)),
            model_escalation_policy=bool(top_level.get("model_escalation_policy", snapshot.model_escalation_policy)),
            orchestrator=orchestrator,
            studio_dev=studio_dev,
            veille_strategique=veille,
            metadata={
                **snapshot.metadata,
                "candidate_summary": proposal.summary,
            },
        )
    def _build_halt_record(
        self,
        round_index: int,
        snapshot: ConfigTargetSnapshot,
        benchmark_suite: ConfigBenchmarkSuite,
        mode: LoopMode,
    ) -> ImprovementRoundRecord:
        empty_report = ConfigBenchmarkReport(
            suite_version=benchmark_suite.suite_version,
            snapshot_version=snapshot.version,
            score=0.0,
        )
        return ImprovementRoundRecord(
            target_id=self.target_id,
            round_index=round_index,
            mode=mode,
            decision=LoopDecision.halt,
            baseline_score=0.0,
            candidate_score=0.0,
            score_delta=0.0,
            improvement_ratio=0.0,
            current_snapshot=snapshot.model_dump(mode="json"),
            candidate_snapshot=snapshot.model_dump(mode="json"),
            applied_snapshot=snapshot.model_dump(mode="json"),
            proposal={"summary": "Optimization halted due to stagnation."},
            baseline_report=empty_report.model_dump(mode="json"),
            candidate_report=empty_report.model_dump(mode="json"),
            requires_human_review=True,
            halted_reason=(
                f"No meaningful improvement detected for {self.stagnation_limit} consecutive config rounds. "
                "Escalate to a human reviewer."
            ),
        )

    @staticmethod
    def _modifiable_fields() -> list[str]:
        return [
            "orchestrator.max_stall_count",
            "orchestrator.max_replan",
            "orchestrator.max_steps_total",
            "workers.default_max_retries",
            "workers.studio-dev.auto_lint_patch",
            "workers.veille-strategique.max_search_depth",
        ]
