from __future__ import annotations

from enum import Enum
from statistics import mean
import time
from typing import Protocol
from uuid import uuid4

from observability import log_structured_event
from pydantic import BaseModel, Field

from runtime_contracts.adapter_command import AdapterCommand, AdapterCommandV1
from runtime_contracts.adapter_result import AdapterResultV1, EngineErrorCode, EngineMeta, NormalizedError, RunStatus
from runtime_contracts.intent import SimulationIntentV1
from simulation_adapter.service import AdapterService

from .benchmark_suite import BenchmarkCase, BenchmarkSuite
from .harness_memory import DEFAULT_HARNESS_MEMORY_PATH, HarnessMemoryStore, MemoryEntryType
from .harness_snapshot import HarnessSnapshot, RiskLevel, SkillDefinition


class OptimizationMode(str, Enum):
    suggest_only = "suggest_only"
    safe_auto_apply = "safe_auto_apply"


class RoundDecision(str, Enum):
    keep = "keep"
    revert = "revert"
    propose = "propose"
    halt = "halt"


class FailureTrajectory(BaseModel):
    case_id: str
    status: RunStatus
    score: float
    summary: str | None = None
    errors: list[dict] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


class BenchmarkOutcome(BaseModel):
    case_id: str
    score: float
    weight: float
    status: RunStatus
    runtime_run_id: str
    summary: str | None = None
    errors: list[dict] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class BenchmarkReport(BaseModel):
    suite_version: str
    snapshot_version: str
    score: float
    outcomes: list[BenchmarkOutcome] = Field(default_factory=list)
    trajectories: list[FailureTrajectory] = Field(default_factory=list)


class HarnessChangeProposal(BaseModel):
    summary: str
    rationale: list[str] = Field(default_factory=list)
    workflow_rules_to_add: list[str] = Field(default_factory=list)
    workflow_rules_to_remove: list[str] = Field(default_factory=list)
    sampling_param_overrides: dict[str, float] = Field(default_factory=dict)
    skill_updates: dict[str, SkillDefinition] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.low
    requires_human_review: bool = False

    def has_changes(self) -> bool:
        return any(
            [
                self.workflow_rules_to_add,
                self.workflow_rules_to_remove,
                self.sampling_param_overrides,
                self.skill_updates,
            ]
        )


class OptimizationRoundResult(BaseModel):
    round_index: int
    decision: RoundDecision
    mode: OptimizationMode
    baseline_score: float
    candidate_score: float
    score_delta: float
    improvement_ratio: float
    current_snapshot: HarnessSnapshot
    candidate_snapshot: HarnessSnapshot
    applied_snapshot: HarnessSnapshot
    proposal: HarnessChangeProposal
    baseline_report: BenchmarkReport
    candidate_report: BenchmarkReport
    requires_human_review: bool = False
    halted_reason: str | None = None
    runtime_requested: str = "pydanticai"
    runtime_used: str = "pydanticai"
    fallback_used: bool = False
    metadata: dict = Field(default_factory=dict)


class HarnessCritic(Protocol):
    def analyze_failures(
        self,
        trajectories: list[FailureTrajectory],
        current_snapshot: HarnessSnapshot,
    ) -> HarnessChangeProposal: ...


class RuleBasedHarnessCritic:
    """Deterministic critic used as a safe default and for tests."""

    def analyze_failures(
        self,
        trajectories: list[FailureTrajectory],
        current_snapshot: HarnessSnapshot,
    ) -> HarnessChangeProposal:
        if not trajectories:
            return HarnessChangeProposal(
                summary="No harness changes proposed; benchmark suite is healthy.",
            )

        workflow_rules_to_add: list[str] = []
        sampling_param_overrides: dict[str, float] = {}
        rationale = []

        if any(t.status in {RunStatus.failed, RunStatus.engine_unavailable} for t in trajectories):
            workflow_rules_to_add.append(
                "When an engine is unavailable, produce a normalized fallback recommendation instead of retrying blindly."
            )
            rationale.append("Several benchmark cases failed due to hard failures or engine unavailability.")

        low_scores = [t for t in trajectories if t.score < 0.85]
        if low_scores:
            sampling_param_overrides["temperature"] = min(
                0.8,
                max(current_snapshot.sampling_params.get("temperature", 0.2), 0.3),
            )
            rationale.append("Low benchmark scores suggest the harness needs broader exploration.")

        return HarnessChangeProposal(
            summary="Rule-based critic suggests safer fallback handling and calibrated sampling.",
            rationale=rationale,
            workflow_rules_to_add=workflow_rules_to_add,
            sampling_param_overrides=sampling_param_overrides,
            risk_level=RiskLevel.low,
            requires_human_review=False,
        )


class HarnessOptimizer:
    def __init__(
        self,
        *,
        memory_store: HarnessMemoryStore | None = None,
        keep_threshold: float = 0.02,
        stagnation_limit: int = 3,
        mode: OptimizationMode = OptimizationMode.suggest_only,
    ) -> None:
        self.memory_store = memory_store or HarnessMemoryStore(str(DEFAULT_HARNESS_MEMORY_PATH))
        self.keep_threshold = keep_threshold
        self.stagnation_limit = stagnation_limit
        self.mode = mode
        self.suggest_only = mode == OptimizationMode.suggest_only

    def run_optimization_round(
        self,
        benchmark_suite: BenchmarkSuite | list[SimulationIntentV1],
        current_snapshot: HarnessSnapshot,
        adapter_service: AdapterService,
        critic: HarnessCritic | None = None,
    ) -> OptimizationRoundResult:
        benchmark_suite = self._coerce_suite(benchmark_suite)
        round_index = self.memory_store.get_latest_round_index() + 1
        if self.memory_store.consecutive_non_improvements(self.stagnation_limit) >= self.stagnation_limit:
            halted = self._build_halt_result(round_index, benchmark_suite, current_snapshot)
            self.memory_store.write_round_feedback(
                round_index=round_index,
                entry_type=MemoryEntryType.decision,
                summary=halted.halted_reason or "Harness optimization halted due to stagnation.",
                details={"decision": halted.decision.value},
                candidate_version=current_snapshot.version,
                applied=False,
                score_delta=0.0,
            )
            return halted

        critic = critic or RuleBasedHarnessCritic()
        baseline_report = self._run_benchmark(benchmark_suite, current_snapshot, adapter_service, round_index, "baseline")
        proposal = critic.analyze_failures(baseline_report.trajectories, current_snapshot)
        candidate_snapshot = self._apply_proposed_changes(current_snapshot, proposal)
        candidate_report = self._run_benchmark(
            benchmark_suite,
            candidate_snapshot,
            adapter_service,
            round_index,
            "candidate",
        )

        baseline_score = baseline_report.score
        candidate_score = candidate_report.score
        score_delta = candidate_score - baseline_score
        improvement_ratio = 0.0
        if baseline_score > 0:
            improvement_ratio = score_delta / baseline_score
        elif candidate_score > 0:
            improvement_ratio = 1.0

        if baseline_score > 0:
            keep_candidate = candidate_score >= baseline_score * (1 + self.keep_threshold)
        else:
            keep_candidate = candidate_score > 0
        requires_human_review = proposal.requires_human_review or self._proposal_requires_human_review(proposal)

        if self.mode == OptimizationMode.safe_auto_apply and keep_candidate and not requires_human_review:
            decision = RoundDecision.keep
            applied_snapshot = candidate_snapshot
            applied = True
        elif keep_candidate:
            decision = RoundDecision.propose
            applied_snapshot = current_snapshot
            applied = False
        else:
            decision = RoundDecision.revert
            applied_snapshot = current_snapshot
            applied = False

        self.memory_store.write_round_feedback(
            round_index=round_index,
            entry_type=MemoryEntryType.benchmark,
            summary="Completed baseline and candidate benchmark runs.",
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
            round_index=round_index,
            entry_type=MemoryEntryType.self_critique,
            summary=proposal.summary,
            details={
                "rationale": proposal.rationale,
                "workflow_rules_to_add": proposal.workflow_rules_to_add,
                "workflow_rules_to_remove": proposal.workflow_rules_to_remove,
                "sampling_param_overrides": proposal.sampling_param_overrides,
                "requires_human_review": requires_human_review,
            },
            candidate_version=candidate_snapshot.version,
            applied=False,
            score_delta=score_delta,
        )
        self.memory_store.write_round_feedback(
            round_index=round_index,
            entry_type=MemoryEntryType.decision,
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

        return OptimizationRoundResult(
            round_index=round_index,
            decision=decision,
            mode=self.mode,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            score_delta=score_delta,
            improvement_ratio=improvement_ratio,
            current_snapshot=current_snapshot,
            candidate_snapshot=candidate_snapshot,
            applied_snapshot=applied_snapshot,
            proposal=proposal,
            baseline_report=baseline_report,
            candidate_report=candidate_report,
            requires_human_review=requires_human_review,
        )

    def _build_halt_result(
        self,
        round_index: int,
        benchmark_suite: BenchmarkSuite,
        current_snapshot: HarnessSnapshot,
    ) -> OptimizationRoundResult:
        empty_report = BenchmarkReport(
            suite_version=benchmark_suite.suite_version,
            snapshot_version=current_snapshot.version,
            score=0.0,
        )
        proposal = HarnessChangeProposal(summary="Optimization halted due to stagnation.")
        return OptimizationRoundResult(
            round_index=round_index,
            decision=RoundDecision.halt,
            mode=self.mode,
            baseline_score=0.0,
            candidate_score=0.0,
            score_delta=0.0,
            improvement_ratio=0.0,
            current_snapshot=current_snapshot,
            candidate_snapshot=current_snapshot,
            applied_snapshot=current_snapshot,
            proposal=proposal,
            baseline_report=empty_report,
            candidate_report=empty_report,
            requires_human_review=True,
            halted_reason=(
                f"No meaningful improvement detected for {self.stagnation_limit} consecutive rounds. "
                "Escalate to a human reviewer."
            ),
        )

    @staticmethod
    def _coerce_suite(
        benchmark_suite: BenchmarkSuite | list[SimulationIntentV1],
    ) -> BenchmarkSuite:
        if isinstance(benchmark_suite, BenchmarkSuite):
            return benchmark_suite
        cases = []
        for index, intent in enumerate(benchmark_suite):
            cases.append(
                BenchmarkCase(
                    case_id=f"intent_case_{index + 1}",
                    description=intent.goal,
                    intent=intent,
                )
            )
        return BenchmarkSuite(cases=cases)

    def _run_benchmark(
        self,
        benchmark_suite: BenchmarkSuite,
        snapshot: HarnessSnapshot,
        adapter_service: AdapterService,
        round_index: int,
        label: str,
    ) -> BenchmarkReport:
        outcomes: list[BenchmarkOutcome] = []
        trajectories: list[FailureTrajectory] = []
        weighted_scores: list[float] = []
        weights: list[float] = []

        for case in benchmark_suite.cases:
            runtime_run_id = f"bench_{round_index}_{label}_{case.case_id}_{uuid4().hex[:6]}"
            result = self._execute_case(case, snapshot, adapter_service, runtime_run_id)
            outcome_score = self._score_case(case, result)
            outcome = BenchmarkOutcome(
                case_id=case.case_id,
                score=outcome_score,
                weight=case.weight,
                status=result.status,
                runtime_run_id=runtime_run_id,
                summary=result.summary,
                errors=[error.model_dump(mode="json") for error in result.errors],
                metrics={metric.name: metric.value for metric in result.metrics},
            )
            outcomes.append(outcome)
            weighted_scores.append(outcome_score * case.weight)
            weights.append(case.weight)

            if result.status.value not in case.expectation.accepted_statuses or outcome_score < case.expectation.min_score:
                trajectories.append(
                    FailureTrajectory(
                        case_id=case.case_id,
                        status=result.status,
                        score=outcome_score,
                        summary=result.summary,
                        errors=[error.model_dump(mode="json") for error in result.errors],
                        metrics={metric.name: metric.value for metric in result.metrics},
                        notes=case.description,
                    )
                )

        score = sum(weighted_scores) / sum(weights) if weights else 0.0
        return BenchmarkReport(
            suite_version=benchmark_suite.suite_version,
            snapshot_version=snapshot.version,
            score=score,
            outcomes=outcomes,
            trajectories=trajectories,
        )

    def _execute_case(
        self,
        case: BenchmarkCase,
        snapshot: HarnessSnapshot,
        adapter_service: AdapterService,
        runtime_run_id: str,
    ) -> AdapterResultV1:
        create_command = AdapterCommandV1(
            command=AdapterCommand.create_run,
            runtime_run_id=runtime_run_id,
            engine=case.intent.policy.engine_preference.value,
            simulation_type="society",
            brief=case.intent.goal,
            seed_materials={
                "documents": case.intent.inputs.documents,
                "entities": case.intent.inputs.entities,
                "environment_seed": case.intent.inputs.environment_seed,
            },
            parameters={
                "max_agents": case.intent.constraints.max_agents,
                "time_horizon": case.intent.constraints.time_horizon,
                "extra": {
                    "intent_variables": case.intent.inputs.variables,
                    "harness_snapshot": {
                        "version": snapshot.version,
                        "workflow_rules": snapshot.workflow_rules,
                        "sampling_params": snapshot.sampling_params,
                    },
                },
            },
            control={
                "timeout_seconds": case.intent.policy.timeout_seconds,
                "budget_max": case.intent.policy.budget_max,
            },
            correlation_id=case.intent.correlation_id,
            swarm_intent_id=case.intent.intent_id,
        )
        created = adapter_service.dispatch(create_command)
        if created.status.is_terminal and created.status != RunStatus.completed:
            return created

        deadline = time.monotonic() + max(5, case.intent.policy.timeout_seconds)
        status = created
        while time.monotonic() < deadline:
            status = adapter_service.dispatch(
                create_command.model_copy(update={"command": AdapterCommand.get_status})
            )
            if status.status == RunStatus.completed:
                return adapter_service.dispatch(
                    create_command.model_copy(update={"command": AdapterCommand.get_result})
                )
            if status.status.is_terminal:
                return status
            time.sleep(2)

        cancel_result = adapter_service.dispatch(
            create_command.model_copy(update={"command": AdapterCommand.cancel_run})
        )
        log_structured_event(
            "swarm_core.harness_optimizer",
            "warning",
            "benchmark_case_timed_out",
            case_id=case.case_id,
            runtime_run_id=runtime_run_id,
            engine=case.intent.policy.engine_preference.value,
            timeout_seconds=case.intent.policy.timeout_seconds,
            correlation_id=case.intent.correlation_id,
            cancel_status=cancel_result.status.value,
        )
        return AdapterResultV1(
            runtime_run_id=runtime_run_id,
            engine_run_id=cancel_result.engine_run_id or created.engine_run_id,
            status=RunStatus.timed_out,
            summary=f"Benchmark case '{case.case_id}' exceeded timeout_seconds={case.intent.policy.timeout_seconds}.",
            engine_meta=EngineMeta(
                engine=case.intent.policy.engine_preference.value,
                adapter_version=create_command.adapter_version,
            ),
            correlation_id=case.intent.correlation_id,
            errors=[
                NormalizedError.from_code(
                    EngineErrorCode.timeout,
                    f"Benchmark case '{case.case_id}' exceeded timeout_seconds={case.intent.policy.timeout_seconds}.",
                    retryable=True,
                    detail={"case_id": case.case_id},
                )
            ],
            progress=status.progress,
        )

    @staticmethod
    def _score_case(case: BenchmarkCase, result: AdapterResultV1) -> float:
        status_score = 1.0 if result.status == RunStatus.completed else 0.0
        metrics_map = {metric.name: metric.value for metric in result.metrics}

        if case.expectation.metric_thresholds:
            metric_scores = [
                min(1.0, metrics_map.get(name, 0.0) / threshold)
                for name, threshold in case.expectation.metric_thresholds.items()
                if threshold > 0
            ]
            metric_score = mean(metric_scores) if metric_scores else 0.0
        else:
            metric_score = mean([min(1.0, max(0.0, value)) for value in metrics_map.values()]) if metrics_map else status_score

        error_penalty = 0.2 if result.errors else 0.0
        score = max(0.0, min(1.0, (0.6 * status_score) + (0.4 * metric_score) - error_penalty))
        return score

    @staticmethod
    def _proposal_requires_human_review(proposal: HarnessChangeProposal) -> bool:
        return bool(proposal.skill_updates) or proposal.risk_level in {RiskLevel.medium, RiskLevel.high}

    @staticmethod
    def _apply_proposed_changes(
        current_snapshot: HarnessSnapshot,
        proposal: HarnessChangeProposal,
    ) -> HarnessSnapshot:
        next_rules = [rule for rule in current_snapshot.workflow_rules if rule not in proposal.workflow_rules_to_remove]
        for rule in proposal.workflow_rules_to_add:
            if rule not in next_rules:
                next_rules.append(rule)

        next_sampling_params = dict(current_snapshot.sampling_params)
        next_sampling_params.update(proposal.sampling_param_overrides)

        next_skills = {name: skill.model_copy(deep=True) for name, skill in current_snapshot.skills.items()}
        next_skills.update({name: skill.model_copy(deep=True) for name, skill in proposal.skill_updates.items()})

        return current_snapshot.clone_with(
            version=f"{current_snapshot.version}_cand_{uuid4().hex[:6]}",
            workflow_rules=next_rules,
            sampling_params=next_sampling_params,
            skills=next_skills,
            metadata={
                **current_snapshot.metadata,
                "candidate_summary": proposal.summary,
            },
        )
