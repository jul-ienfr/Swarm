from __future__ import annotations

import hashlib
import json
import time
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from observability import log_structured_event
from runtime_contracts.adapter_command import (
    AdapterCommand,
    AdapterCommandV1,
    ControlParams,
    EngineTarget,
    ProgressGranularity,
    SeedMaterials,
    SimulationParameters,
)
from runtime_contracts.adapter_result import AdapterResultV1, EngineErrorCode, NormalizedError, RunStatus
from runtime_contracts.intent import EnginePreference
from simulation_adapter.factory import build_default_adapter_service
from simulation_adapter.service import AdapterService

from .deliberation_artifacts import (
    DeliberationArtifact,
    DeliberationArtifactKind,
    DeliberationMode,
    DeliberationProvenanceItem,
    DeliberationProvenanceKind,
    DeliberationRunManifest,
)
from .deliberation_benchmark import (
    DeliberationBenchmarkOutcome,
    DeliberationBenchmarkReport,
    DeliberationBenchmarkSuite,
)
from .deliberation_replay import DeliberationReplayEventKind, DeliberationReplayManifest
from .deliberation_stability import DeliberationStabilitySummary
from .belief_state import (
    BeliefGroupSummary,
    BeliefState,
    attach_belief_states_to_graph,
    summarise_belief_group,
)
from .deliberation_contracts import (
    BeliefStateSnapshot,
    DeliberationReport,
    DeliberationRequest,
    ParticipantProfile,
    SocialTraceBundle,
    belief_state_snapshot_from_state,
    participant_profile_from_source,
    social_trace_bundles_from_traces,
)
from .belief_evolution import BeliefEvolutionEngine
from .adaptive_fidelity import AdaptiveFidelityPlanner, FidelityRequest
from .cluster_diagnostics import diagnose_clusters
from .cost_latency_control import BudgetLimits, BudgetRequest, CostLatencyController
from .cross_platform_simulation import CrossPlatformSimulator
from .deliberation_visuals import build_deliberation_visuals
from .deliberation_workbench_tasks import build_default_workbench_task_plan
from .deliberation_workbench import (
    WorkbenchSession,
    WorkbenchPersonaProfile,
    build_workbench_session,
    persist_workbench_session,
    profile_to_belief_state,
    profiles_to_graph_payload,
)
from .graph_analytics import analyze_graph
from .graph_backend_adapter import Neo4jFriendlyGraphBackendAdapter
from .graph_store import GraphStore
from .intervention_lab import InterventionLab
from .normalized_social_traces import NormalizedSocialTraceStore
from .profile_generation_pipeline import ProfileGenerationPipeline, ProfileGenerationRequest
from .profile_quality_guard import ProfileQualityGuard
from .provenance_registry import ProvenanceKind, ProvenanceRegistry
from .run_health_monitor import RunHealthMonitor
from .safety_policy import SafetyPolicyEngine, SafetyRequest
from .scenario_judge import ScenarioCandidate, ScenarioJudge
from .strategy_meeting import StrategyMeetingClusterSummary, StrategyMeetingResult, run_strategy_meeting_sync


DEFAULT_DELIBERATION_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "deliberations"
DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "deliberation_suite_v1.json"
)
DEFAULT_DELIBERATION_POLL_INTERVAL_SECONDS = 1.0


class DeliberationStatus(str, Enum):
    completed = "completed"
    partial = "partial"
    failed = "failed"


class DeliberationClusterSummary(BaseModel):
    cluster_index: int
    participants: list[str] = Field(default_factory=list)
    summary: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    confidence_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationJudgeScores(BaseModel):
    coherence: float = 0.0
    diversity: float = 0.0
    actionability: float = 0.0
    explainability: float = 0.0
    overall: float = 0.0


class DeliberationEngineSnapshot(BaseModel):
    engine: str
    status: DeliberationStatus
    summary: str = ""
    confidence_level: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    scenarios_count: int = 0
    recommendations_count: int = 0
    uncertainty_points: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationEnsembleReport(BaseModel):
    primary_engine: str | None = None
    compared_engines: list[str] = Field(default_factory=list)
    convergence_score: float = 0.0
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    engine_snapshots: list[DeliberationEngineSnapshot] = Field(default_factory=list)


class DeliberationDecisionPacket(BaseModel):
    mode_used: DeliberationMode
    runtime_used: str | None = None
    runtime_resilience: dict[str, Any] | None = None
    engine_used: str | None = None
    probability_estimate: float | None = None
    confidence_band: list[float] = Field(default_factory=list)
    recommendation: str | None = None
    rationale_summary: str = ""
    quality_score: float | None = None
    confidence_score: float | None = None
    dissent_turn_count: int | None = None
    meeting_quality_summary: str = ""
    artifacts: list[str] = Field(default_factory=list)


class DeliberationResult(BaseModel):
    deliberation_id: str
    topic: str
    objective: str
    mode: DeliberationMode
    status: DeliberationStatus
    runtime_requested: str = "pydanticai"
    runtime_used: str | None = None
    fallback_used: bool = False
    runtime_resilience: dict[str, Any] | None = None
    engine_requested: str | None = None
    engine_used: str | None = None
    participants: list[str] = Field(default_factory=list)
    requested_max_agents: int = 0
    population_size: int = 0
    time_horizon: str = "7d"
    rounds_requested: int = 0
    rounds_completed: int = 0
    summary: str = ""
    final_strategy: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    scenarios: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    confidence_level: float = 0.0
    uncertainty_points: list[str] = Field(default_factory=list)
    cluster_summaries: list[DeliberationClusterSummary] = Field(default_factory=list)
    sensitivity_factors: list[str] = Field(default_factory=list)
    belief_states: list[BeliefState] = Field(default_factory=list)
    belief_group_summaries: list[BeliefGroupSummary] = Field(default_factory=list)
    artifacts: list[DeliberationArtifact] = Field(default_factory=list)
    provenance: list[DeliberationProvenanceItem] = Field(default_factory=list)
    benchmark_report: DeliberationBenchmarkReport | None = None
    stability_summary: DeliberationStabilitySummary | None = None
    ensemble_report: DeliberationEnsembleReport | None = None
    judge_scores: DeliberationJudgeScores = Field(default_factory=DeliberationJudgeScores)
    decision_packet: DeliberationDecisionPacket | None = None
    request: DeliberationRequest | None = None
    report: DeliberationReport | None = None
    participant_profiles: list[ParticipantProfile] = Field(default_factory=list)
    belief_state_snapshots: list[BeliefStateSnapshot] = Field(default_factory=list)
    social_trace_bundles: list[SocialTraceBundle] = Field(default_factory=list)
    scenario_judgement: dict[str, Any] | None = None
    social_trace_summary: dict[str, Any] | None = None
    graph_analytics: dict[str, Any] | None = None
    cluster_diagnostics: dict[str, Any] | None = None
    run_health: dict[str, Any] | None = None
    profile_quality: dict[str, Any] | None = None
    intervention_report: dict[str, Any] | None = None
    replay_id: str | None = None
    replay_path: str | None = None
    manifest_path: str | None = None
    graph_path: str | None = None
    persisted_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationCoordinator:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        output_dir: str | Path | None = None,
        adapter_service: AdapterService | None = None,
        backend_mode: str | None = None,
        poll_interval_seconds: float = DEFAULT_DELIBERATION_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.config_path = config_path
        self.output_dir = Path(output_dir or DEFAULT_DELIBERATION_OUTPUT_DIR)
        self.adapter_service = adapter_service or build_default_adapter_service(backend_mode=backend_mode)
        self.backend_mode = backend_mode
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)

    def run(
        self,
        *,
        topic: str,
        objective: str | None = None,
        mode: DeliberationMode | str = DeliberationMode.committee,
        participants: list[str] | None = None,
        documents: list[str] | None = None,
        entities: list[Any] | None = None,
        interventions: list[str] | None = None,
        max_agents: int = 6,
        population_size: int | None = None,
        rounds: int = 2,
        time_horizon: str = "7d",
        persist: bool = True,
        runtime: str = "pydanticai",
        allow_fallback: bool = True,
        engine_preference: EnginePreference | str = EnginePreference.agentsociety,
        ensemble_engines: list[EnginePreference | str] | None = None,
        budget_max: float = 10.0,
        timeout_seconds: int = 1800,
        benchmark_path: str | None = None,
        stability_runs: int = 1,
        client: Any | None = None,
    ) -> DeliberationResult:
        selected_mode = _normalize_mode(mode)
        selected_runtime = _normalize_runtime(runtime)
        selected_engine = _normalize_engine_preference(engine_preference)
        selected_ensemble_engines = _normalize_engine_preferences(ensemble_engines, primary=selected_engine)
        run_id = f"delib_{uuid4().hex[:12]}"
        resolved_objective = objective or f"Define the best strategy for: {topic}"
        resolved_documents = [item for item in (documents or []) if item]
        resolved_entities = list(entities or [])
        resolved_interventions = [item for item in (interventions or []) if item]
        initial_population = _resolve_population_size(
            mode=selected_mode,
            population_size=population_size,
            max_agents=max_agents,
            participants=participants or [],
            documents=resolved_documents,
        )
        fidelity_plan = AdaptiveFidelityPlanner().plan(
            FidelityRequest(
                goal=resolved_objective,
                requested_population=initial_population,
                requested_rounds=rounds,
                time_budget_seconds=float(timeout_seconds),
                cost_budget_units=float(budget_max),
                quality_priority=0.9 if selected_mode == DeliberationMode.hybrid else 0.7,
            )
        )
        budget_report = CostLatencyController().evaluate(
            BudgetRequest(
                requested_agents=fidelity_plan.population_size,
                requested_rounds=fidelity_plan.rounds,
                requested_parallelism=fidelity_plan.parallelism,
                estimated_cost_units=fidelity_plan.estimated_cost_units,
                estimated_latency_seconds=fidelity_plan.estimated_latency_seconds,
            ),
            BudgetLimits(
                cost_units=float(budget_max),
                latency_seconds=float(timeout_seconds),
                max_agents=1000,
                max_rounds=8,
                max_parallelism=16,
            ),
        )
        resolved_population = budget_report.adjusted_agents
        rounds = budget_report.adjusted_rounds
        safety_result = SafetyPolicyEngine().evaluate(
            SafetyRequest(
                topic=topic,
                documents=tuple(resolved_documents),
                population_size=resolved_population,
                rounds=rounds,
                parallelism=budget_report.adjusted_parallelism,
                provenance_count=len(resolved_documents) + len(resolved_interventions),
            )
        )

        run_dir = self.output_dir / run_id
        deliberation_request = DeliberationRequest(
            topic=topic,
            objective=resolved_objective,
            mode=selected_mode,
            documents=resolved_documents,
            participants=participants or [],
            population_size=resolved_population,
            rounds=rounds,
            time_horizon=time_horizon,
            engine_preference=selected_engine.value,
            entities=resolved_entities,
            interventions=resolved_interventions,
            metadata={
                "runtime": selected_runtime,
                "allow_fallback": allow_fallback,
                "ensemble_engines": [engine.value for engine in selected_ensemble_engines],
                "budget_max": budget_max,
                "timeout_seconds": timeout_seconds,
                "backend_mode": self.backend_mode,
            },
        )
        manifest_seed = _build_manifest_seed(
            topic=topic,
            objective=resolved_objective,
            participants=participants or [],
            documents=resolved_documents,
            entities=resolved_entities,
            interventions=resolved_interventions,
        )
        manifest = DeliberationRunManifest(
            run_id=run_id,
            topic=topic,
            objective=resolved_objective,
            mode=selected_mode,
            seed=manifest_seed,
            profile_version="profile_generation_pipeline_v1",
            graph_version="graph_store_v1",
            inputs={
                "topic": topic,
                "objective": resolved_objective,
                "mode": selected_mode.value,
                "participants": participants or [],
                "documents": resolved_documents,
                "entities": resolved_entities,
                "interventions": resolved_interventions,
                "max_agents": max_agents,
                "population_size": resolved_population,
                "rounds": rounds,
                "time_horizon": time_horizon,
                "runtime": selected_runtime,
                "allow_fallback": allow_fallback,
                "engine_preference": selected_engine.value,
                "ensemble_engines": [engine.value for engine in selected_ensemble_engines],
                "budget_max": budget_max,
                "timeout_seconds": timeout_seconds,
                "backend_mode": self.backend_mode,
            },
            metadata={
                "adaptive_fidelity": {
                    **fidelity_plan.to_dict(),
                    "requested_population_size": population_size,
                    "resolved_population_size": resolved_population,
                    "documents_count": len(resolved_documents),
                },
                "budget_control": {
                    "decision": budget_report.decision.value,
                    "allowed": budget_report.allowed,
                    "adjusted_agents": budget_report.adjusted_agents,
                    "adjusted_rounds": budget_report.adjusted_rounds,
                    "adjusted_parallelism": budget_report.adjusted_parallelism,
                    "adjusted_cost_units": budget_report.adjusted_cost_units,
                    "adjusted_latency_seconds": budget_report.adjusted_latency_seconds,
                    "reasons": budget_report.reasons,
                },
                "safety_policy": {
                    "decision": safety_result.decision.value,
                    "allowed": safety_result.allowed,
                    "findings": [
                        {
                            "code": finding.code,
                            "severity": finding.severity.value,
                            "message": finding.message,
                            "field": finding.field,
                        }
                        for finding in safety_result.findings
                    ],
                },
            },
        )
        replay = DeliberationReplayManifest(source_run_id=run_id, source_manifest_id=run_id)
        replay.append_event(
            kind=DeliberationReplayEventKind.start,
            payload={
                "mode": selected_mode.value,
                "runtime_requested": selected_runtime,
                "engine_requested": selected_engine.value,
            },
        )

        provenance_registry = ProvenanceRegistry((run_dir / "provenance_registry.json") if persist else None)
        for index, document in enumerate(resolved_documents, start=1):
            item = DeliberationProvenanceItem(
                provenance_id=f"prov_doc_{index}",
                kind=DeliberationProvenanceKind.source,
                title=f"document_{index}",
                content=document[:4000],
                confidence=0.8,
            )
            manifest.add_provenance(item)
            provenance_registry.record(
                run_id=run_id,
                kind=ProvenanceKind.document,
                subject_id=item.provenance_id,
                source=item.title,
                details={"content": item.content},
            )
        for index, intervention in enumerate(resolved_interventions, start=1):
            item = DeliberationProvenanceItem(
                provenance_id=f"prov_intervention_{index}",
                kind=DeliberationProvenanceKind.signal,
                title=f"intervention_{index}",
                content=intervention,
                confidence=0.75,
            )
            manifest.add_provenance(item)
            provenance_registry.record(
                run_id=run_id,
                kind=ProvenanceKind.trace,
                subject_id=item.provenance_id,
                source=item.title,
                details={"content": item.content},
            )

        graph_payload = _build_graph_payload(
            topic=topic,
            objective=resolved_objective,
            participants=participants or [],
            documents=resolved_documents,
            entities=resolved_entities,
            interventions=resolved_interventions,
            population_size=resolved_population,
        )
        workbench_session = build_workbench_session(
            topic=topic,
            objective=resolved_objective,
            mode=selected_mode,
            participants=participants or [],
            documents=resolved_documents,
            entities=resolved_entities,
            interventions=resolved_interventions,
            population_size=resolved_population,
            rounds=rounds,
            time_horizon=time_horizon,
            metadata={
                "engine_preference": selected_engine.value,
                "ensemble_engines": [engine.value for engine in selected_ensemble_engines],
                "fidelity_mode": fidelity_plan.mode.value,
            },
        )
        profile_pipeline = ProfileGenerationPipeline()
        profile_report = profile_pipeline.run(
            ProfileGenerationRequest(
                topic=topic,
                objective=resolved_objective,
                participants=participants or [],
                documents=resolved_documents,
                entities=resolved_entities,
                interventions=resolved_interventions,
                target_profiles=min(max(3, resolved_population if selected_mode != DeliberationMode.committee else max_agents), 32),
                max_profiles=min(max(3, resolved_population if selected_mode != DeliberationMode.committee else max_agents), 64),
            )
        )
        workbench_session.profiles = [_persona_profile_to_workbench(profile) for profile in profile_report.profiles]
        workbench_session.summary = profile_report.summary
        workbench_session.metadata.update(
            {
                "profile_pipeline_request_id": profile_report.request_id,
                "profile_pipeline_version": "v1",
                "profile_keywords": profile_report.top_keywords,
            }
        )
        graph_payload = _merge_graph_payloads(graph_payload, profiles_to_graph_payload(workbench_session.profiles))
        profile_quality = ProfileQualityGuard().evaluate(
            [
                {
                    "id": profile.profile_id,
                    "name": profile.label,
                    "summary": profile.summary,
                    "confidence": profile.confidence,
                    "stance": profile.stance,
                    "sources": profile.evidence,
                }
                for profile in workbench_session.profiles
            ]
        )

        if selected_mode == DeliberationMode.committee:
            result = self._run_committee(
                run_id=run_id,
                topic=topic,
                objective=resolved_objective,
                participants=participants or [],
                max_agents=max_agents,
                rounds=rounds,
                runtime=selected_runtime,
                allow_fallback=allow_fallback,
                persist=False,
                client=client,
            )
        elif selected_mode == DeliberationMode.simulation:
            result = self._run_simulation(
                run_id=run_id,
                topic=topic,
                objective=resolved_objective,
                documents=resolved_documents,
                entities=resolved_entities,
                interventions=resolved_interventions,
                population_size=resolved_population,
                rounds=rounds,
                time_horizon=time_horizon,
                engine_preference=selected_engine,
                ensemble_engines=selected_ensemble_engines,
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
            )
        else:
            result = self._run_hybrid(
                run_id=run_id,
                topic=topic,
                objective=resolved_objective,
                participants=participants or [],
                documents=resolved_documents,
                entities=resolved_entities,
                interventions=resolved_interventions,
                max_agents=max_agents,
                population_size=resolved_population,
                rounds=rounds,
                time_horizon=time_horizon,
                runtime=selected_runtime,
                allow_fallback=allow_fallback,
                engine_preference=selected_engine,
                ensemble_engines=selected_ensemble_engines,
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
                client=client,
            )

        if result.deliberation_id != run_id:
            result.metadata.setdefault("source_deliberation_id", result.deliberation_id)
            result.deliberation_id = run_id
        result.request = deliberation_request
        runtime_resilience = _result_runtime_resilience(result)
        if runtime_resilience is not None:
            result.runtime_resilience = runtime_resilience
            result.metadata.setdefault("runtime_resilience", runtime_resilience)

        manifest.metadata.update(
            {
                "status": result.status.value,
                "runtime_requested": result.runtime_requested,
                "runtime_used": result.runtime_used,
                "fallback_used": result.fallback_used,
                "engine_requested": result.engine_requested,
                "engine_used": result.engine_used,
                "confidence_level": result.confidence_level,
            }
        )
        manifest.status = result.status.value
        manifest.engine_used = result.engine_used
        manifest.add_provenance(
            DeliberationProvenanceItem(
                provenance_id="prov_decision_1",
                kind=DeliberationProvenanceKind.decision,
                title="deliberation_outcome",
                content=result.summary or result.final_strategy,
                confidence=result.confidence_level or None,
                metadata={
                    "status": result.status.value,
                    "mode": result.mode.value,
                },
            )
        )

        benchmark_suite = _load_benchmark_suite(benchmark_path)
        if benchmark_suite is not None:
            result.benchmark_report = _evaluate_deliberation(result, benchmark_suite)

        if stability_runs > 1:
            scores = [result.judge_scores.overall or result.confidence_level or 0.0]
            for _ in range(stability_runs - 1):
                rerun = self.run(
                    topic=topic,
                    objective=resolved_objective,
                    mode=selected_mode,
                    participants=participants,
                    documents=resolved_documents,
                    entities=resolved_entities,
                    interventions=resolved_interventions,
                    max_agents=max_agents,
                    population_size=resolved_population,
                    rounds=rounds,
                    time_horizon=time_horizon,
                    persist=False,
                    runtime=selected_runtime,
                    allow_fallback=allow_fallback,
                    engine_preference=selected_engine,
                    budget_max=budget_max,
                    timeout_seconds=timeout_seconds,
                    benchmark_path=benchmark_path,
                    stability_runs=1,
                    client=client,
                )
                scores.append(rerun.judge_scores.overall or rerun.confidence_level or 0.0)
            result.stability_summary = DeliberationStabilitySummary.from_scores(
                scores,
                minimum_sample_count=3 if selected_mode != DeliberationMode.committee else 2,
                metadata={"mode": selected_mode.value, "run_id": run_id},
            )
            result.sensitivity_factors = _build_sensitivity_factors(result, result.stability_summary)

        initial_belief_states = _derive_belief_states(
            result=result,
            participants=participants or [],
            entities=resolved_entities,
            documents=resolved_documents,
            interventions=resolved_interventions,
            workbench_session=workbench_session,
        )
        trace_report = CrossPlatformSimulator().simulate(
            topic=topic,
            summary=result.summary or result.final_strategy or topic,
            beliefs=initial_belief_states,
            platforms=_resolve_platforms(selected_mode, result.engine_used),
            rounds=max(1, rounds),
            interventions=resolved_interventions,
        )
        trace_rounds = _group_traces_by_round(trace_report.traces, rounds=max(1, trace_report.rounds))
        evolution = BeliefEvolutionEngine(run_id=run_id, metadata={"mode": selected_mode.value}).run(
            initial_belief_states,
            round_count=max(1, trace_report.rounds),
            trace_rounds=trace_rounds,
        )
        result.belief_states = evolution.final_states
        result.belief_group_summaries = evolution.final_group_summaries
        result.metadata.setdefault(
            "belief_groups",
            [summary.model_dump(mode="json") for summary in result.belief_group_summaries],
        )
        result.metadata["workbench_id"] = workbench_session.workbench_id
        result.metadata["profile_count"] = len(workbench_session.profiles)
        result.metadata["belief_evolution"] = {
            "rounds_completed": evolution.rounds_completed,
            "metrics": evolution.metrics,
            "summary": evolution.summary,
        }
        result.profile_quality = profile_quality.to_dict()
        result.participant_profiles = [participant_profile_from_source(profile) for profile in workbench_session.profiles]

        result.provenance = list(manifest.provenance)
        result.profile_quality = profile_quality.to_dict()

        trace_store = NormalizedSocialTraceStore(run_dir / "social_traces.json")
        recorded_traces = trace_store.extend(trace_report.traces)
        trace_aggregate = trace_store.aggregate()
        result.social_trace_summary = trace_aggregate.model_dump(mode="json")
        result.social_trace_bundles = social_trace_bundles_from_traces(run_id=run_id, traces=recorded_traces)
        result.belief_state_snapshots = _belief_state_snapshots_from_evolution(run_id=run_id, evolution=evolution)

        scenario_judge_report = _run_scenario_judge(
            topic=topic,
            result=result,
        )
        result.scenario_judgement = scenario_judge_report
        if scenario_judge_report:
            result.judge_scores.overall = max(
                result.judge_scores.overall,
                float(scenario_judge_report.get("average_score", result.judge_scores.overall)),
            )

        intervention_report = None
        if resolved_interventions:
            baseline_trace_report = CrossPlatformSimulator().simulate(
                topic=topic,
                summary=result.summary or result.final_strategy or topic,
                beliefs=initial_belief_states,
                platforms=_resolve_platforms(selected_mode, result.engine_used),
                rounds=max(1, rounds),
                interventions=[],
            )
            intervention_report = InterventionLab().compare(
                before_beliefs=initial_belief_states,
                after_beliefs=result.belief_states,
                before_traces=baseline_trace_report.traces,
                after_traces=recorded_traces,
                interventions=resolved_interventions,
            ).model_dump(mode="json")
            result.intervention_report = intervention_report

        result.report = DeliberationReport(
            summary=result.summary,
            scenarios=result.scenarios,
            risks=result.risks,
            recommendations=result.recommendations,
            metrics=result.metrics,
            cluster_summaries=[summary.model_dump(mode="json") for summary in result.cluster_summaries],
            confidence_level=result.confidence_level,
            uncertainty_points=result.uncertainty_points,
            dissent_points=result.dissent_points,
            final_strategy=result.final_strategy,
            consensus_points=result.consensus_points,
            next_actions=result.next_actions,
            sensitivity_factors=result.sensitivity_factors,
            metadata={
                "mode": result.mode.value,
                "status": result.status.value,
                "engine_used": result.engine_used,
                "runtime_used": result.runtime_used,
            },
        )

        if persist:
            run_dir.mkdir(parents=True, exist_ok=True)
            persisted_workbench = persist_workbench_session(workbench_session, output_dir=run_dir / "workbench")
            result.metadata["workbench_session_path"] = persisted_workbench.session_path
            task_plan = build_default_workbench_task_plan(workbench_id=workbench_session.workbench_id)
            task_plan_path = task_plan.save(run_dir / "workbench" / "tasks.json")
            request_path = run_dir / "request.json"
            participant_profiles_path = run_dir / "participant_profiles.json"
            belief_snapshots_path = run_dir / "belief_state_snapshots.json"
            social_trace_bundles_path = run_dir / "social_trace_bundle.json"
            report_path = run_dir / "deliberation_report.json"
            request_path.write_text(result.request.model_dump_json(indent=2), encoding="utf-8")
            participant_profiles_path.write_text(json.dumps([profile.model_dump(mode="json") for profile in result.participant_profiles], indent=2), encoding="utf-8")
            belief_snapshots_path.write_text(json.dumps([snapshot.model_dump(mode="json") for snapshot in result.belief_state_snapshots], indent=2), encoding="utf-8")
            social_trace_bundles_path.write_text(json.dumps([bundle.model_dump(mode="json") for bundle in result.social_trace_bundles], indent=2), encoding="utf-8")
            report_path.write_text(result.report.model_dump_json(indent=2), encoding="utf-8")
            for ref_path in [request_path, participant_profiles_path, belief_snapshots_path, social_trace_bundles_path, report_path]:
                manifest.add_input_ref(str(ref_path))
            task_artifact = DeliberationArtifact(
                artifact_id=f"artifact_tasks_{run_id}",
                kind=DeliberationArtifactKind.other,
                title="workbench_tasks",
                uri=str(task_plan_path),
                content_hash=_sha256_text(task_plan_path.read_text(encoding="utf-8")),
                content_type="application/json",
            )
            manifest.add_artifact(task_artifact)
            result.artifacts.append(task_artifact)
            for artifact_id, title, artifact_path, kind in [
                (f"artifact_request_{run_id}", "deliberation_request", request_path, DeliberationArtifactKind.input),
                (f"artifact_participants_{run_id}", "participant_profiles", participant_profiles_path, DeliberationArtifactKind.profile),
                (f"artifact_belief_snapshots_{run_id}", "belief_state_snapshots", belief_snapshots_path, DeliberationArtifactKind.summary),
                (f"artifact_trace_bundle_{run_id}", "social_trace_bundle", social_trace_bundles_path, DeliberationArtifactKind.trace),
                (f"artifact_deliberation_report_{run_id}", "deliberation_report", report_path, DeliberationArtifactKind.report),
            ]:
                artifact = DeliberationArtifact(
                    artifact_id=artifact_id,
                    kind=kind,
                    title=title,
                    uri=str(artifact_path),
                    content_hash=_sha256_text(artifact_path.read_text(encoding="utf-8")),
                    content_type="application/json",
                )
                manifest.add_artifact(artifact)
                result.artifacts.append(artifact)
            for artifact in persisted_workbench.artifacts:
                kind = DeliberationArtifactKind.other
                if artifact.kind.value == "input":
                    kind = DeliberationArtifactKind.input
                elif artifact.kind.value == "profile":
                    kind = DeliberationArtifactKind.profile
                elif artifact.kind.value == "graph":
                    kind = DeliberationArtifactKind.graph
                deliberation_artifact = DeliberationArtifact(
                    artifact_id=artifact.artifact_id,
                    kind=kind,
                    title=artifact.title,
                    uri=artifact.uri,
                    content_hash=artifact.content_hash,
                    content_type=artifact.content_type,
                    metadata=artifact.metadata,
                )
                manifest.add_artifact(deliberation_artifact)
                result.artifacts.append(deliberation_artifact)
            graph_path = run_dir / "graph.json"
            store = GraphStore(
                graph_path,
                name="deliberation_graph",
                description=f"Graph for {selected_mode.value} deliberation {run_id}",
            )
            store.merge_payload(graph_payload)
            attach_belief_states_to_graph(store, result.belief_states)
            saved_graph_path = store.save(graph_path)
            result.graph_path = str(saved_graph_path)
            graph_hash = _sha256_text(saved_graph_path.read_text(encoding="utf-8"))
            graph_artifact = DeliberationArtifact(
                artifact_id=f"artifact_graph_{run_id}",
                kind=DeliberationArtifactKind.graph,
                title="graph_payload",
                uri=str(saved_graph_path),
                content_hash=graph_hash,
                content_type="application/json",
                provenance_ids=[item.provenance_id for item in manifest.provenance],
            )
            manifest.add_artifact(graph_artifact)
            result.artifacts.append(graph_artifact)
            analytics_report = analyze_graph(store)
            diagnostics_report = diagnose_clusters(store, result.belief_states)
            visual_bundle = build_deliberation_visuals(store, analytics=analytics_report, diagnostics=diagnostics_report)
            neo4j_bundle = Neo4jFriendlyGraphBackendAdapter(store).export()
            analytics_path = run_dir / "graph_analytics.json"
            diagnostics_path = run_dir / "cluster_diagnostics.json"
            visuals_path = run_dir / "visuals.json"
            neo4j_path = run_dir / "neo4j_query_bundle.json"
            analytics_path.write_text(analytics_report.model_dump_json(indent=2), encoding="utf-8")
            diagnostics_path.write_text(diagnostics_report.model_dump_json(indent=2), encoding="utf-8")
            visuals_path.write_text(visual_bundle.model_dump_json(indent=2), encoding="utf-8")
            neo4j_path.write_text(neo4j_bundle.model_dump_json(indent=2), encoding="utf-8")
            result.graph_analytics = analytics_report.model_dump(mode="json")
            result.cluster_diagnostics = diagnostics_report.model_dump(mode="json")
            for title, artifact_path in [
                ("graph_analytics", analytics_path),
                ("cluster_diagnostics", diagnostics_path),
                ("visuals", visuals_path),
                ("neo4j_query_bundle", neo4j_path),
            ]:
                kind = DeliberationArtifactKind.visual if title == "visuals" else DeliberationArtifactKind.other
                artifact = DeliberationArtifact(
                    artifact_id=f"artifact_{title}_{run_id}",
                    kind=kind,
                    title=title,
                    uri=str(artifact_path),
                    content_hash=_sha256_text(artifact_path.read_text(encoding="utf-8")),
                    content_type="application/json",
                )
                manifest.add_artifact(artifact)
                result.artifacts.append(artifact)
            trace_store_path = trace_store.save(run_dir / "social_traces.json")
            trace_artifact = DeliberationArtifact(
                artifact_id=f"artifact_social_traces_{run_id}",
                kind=DeliberationArtifactKind.trace,
                title="social_traces",
                uri=str(trace_store_path),
                content_hash=_sha256_text(trace_store_path.read_text(encoding="utf-8")),
                content_type="application/json",
            )
            manifest.add_artifact(trace_artifact)
            result.artifacts.append(trace_artifact)
            provenance_path = run_dir / "provenance_registry.json"
            provenance_registry.save()
            if provenance_path.exists():
                prov_artifact = DeliberationArtifact(
                    artifact_id=f"artifact_provenance_{run_id}",
                    kind=DeliberationArtifactKind.other,
                    title="provenance_registry",
                    uri=str(provenance_path),
                    content_hash=_sha256_text(provenance_path.read_text(encoding="utf-8")),
                    content_type="application/json",
                )
                manifest.add_artifact(prov_artifact)
                result.artifacts.append(prov_artifact)
            replay.append_event(
                kind=DeliberationReplayEventKind.artifact,
                payload={"kind": "graph", "uri": str(saved_graph_path)},
            )
            manifest_path = run_dir / "manifest.json"
            replay_path = run_dir / "replay.json"
            result_path = run_dir / "result.json"

            if result.benchmark_report is not None:
                benchmark_path_out = run_dir / "benchmark_report.json"
                benchmark_path_out.write_text(result.benchmark_report.model_dump_json(indent=2), encoding="utf-8")
                benchmark_artifact = DeliberationArtifact(
                    artifact_id=f"artifact_benchmark_{run_id}",
                    kind=DeliberationArtifactKind.benchmark,
                    title="benchmark_report",
                    uri=str(benchmark_path_out),
                    content_hash=_sha256_text(benchmark_path_out.read_text(encoding="utf-8")),
                    content_type="application/json",
                )
                manifest.add_artifact(benchmark_artifact)
                result.artifacts.append(benchmark_artifact)

            manifest.refresh_refs()
            manifest.save(manifest_path)
            replay.append_event(
                kind=DeliberationReplayEventKind.decision,
                payload={
                    "status": result.status.value,
                    "summary": result.summary,
                    "final_strategy": result.final_strategy,
                },
            )
            replay.save(replay_path)
            result.replay_id = replay.replay_id
            result.replay_path = str(replay_path)
            result.manifest_path = str(manifest_path)
            report_artifact = DeliberationArtifact(
                artifact_id=f"artifact_report_{run_id}",
                kind=DeliberationArtifactKind.report,
                title="deliberation_result",
                uri=str(result_path),
                content_type="application/json",
            )
            result.artifacts.append(report_artifact)
            result.persisted_path = str(result_path)
        else:
            result.graph_analytics = result.graph_analytics or {}
            result.cluster_diagnostics = result.cluster_diagnostics or {}
        meeting_quality = dict(result.metadata.get("meeting_quality") or {})
        runtime_resilience = _result_runtime_resilience(result)
        result.decision_packet = DeliberationDecisionPacket(
            mode_used=result.mode,
            runtime_used=result.runtime_used,
            runtime_resilience=runtime_resilience,
            engine_used=result.engine_used,
            probability_estimate=_estimate_probability(result),
            confidence_band=_confidence_band(result.confidence_level),
            recommendation=_pick_recommendation(result),
            rationale_summary=result.summary or result.final_strategy,
            quality_score=meeting_quality.get("quality_score"),
            confidence_score=meeting_quality.get("confidence_score"),
            dissent_turn_count=meeting_quality.get("dissent_turn_count"),
            meeting_quality_summary=str(meeting_quality.get("summary", "")),
            artifacts=[artifact.uri or "" for artifact in result.artifacts if artifact.uri],
        )
        quality_warnings = _build_quality_warnings(
            result=result,
            profile_quality=profile_quality.to_dict(),
            stability_summary=result.stability_summary,
            comparability=_build_comparability_metadata(
                result=result,
                profile_quality=profile_quality.to_dict(),
                stability_summary=result.stability_summary,
                benchmark_suite_loaded=benchmark_suite is not None,
                manifest_seed=manifest_seed,
                workbench_session=workbench_session,
            ),
        )
        run_health = RunHealthMonitor(required_artifacts=("report",)).evaluate(
            run_id=run_id,
            present_artifacts=[artifact.title for artifact in result.artifacts] + (["report"] if result.summary or result.final_strategy else []),
            elapsed_seconds=float(fidelity_plan.estimated_latency_seconds),
            timeout_seconds=float(timeout_seconds),
            retries=1 if result.fallback_used else 0,
            errors=len(result.uncertainty_points),
            warnings=len(quality_warnings),
            budget_exceeded=not budget_report.allowed,
        )
        result.run_health = {
            "status": run_health.status.value,
            "score": run_health.score,
            "issues": [
                {"code": issue.code, "message": issue.message, "severity": issue.severity}
                for issue in run_health.issues
            ],
            "suggestions": run_health.suggestions,
        }
        result.metadata.update(
            {
                "adaptive_fidelity": fidelity_plan.to_dict(),
                "budget_control": {
                    "decision": budget_report.decision.value,
                    "reasons": budget_report.reasons,
                    "adjusted_agents": budget_report.adjusted_agents,
                    "adjusted_rounds": budget_report.adjusted_rounds,
                    "adjusted_parallelism": budget_report.adjusted_parallelism,
                },
                "safety_policy": {
                    "decision": safety_result.decision.value,
                    "allowed": safety_result.allowed,
                },
                "run_health": result.run_health,
                "profile_quality": result.profile_quality,
                "scenario_judgement": result.scenario_judgement,
                "intervention_report": result.intervention_report,
                "quality_warnings": quality_warnings,
                "comparability": _build_comparability_metadata(
                    result=result,
                    profile_quality=result.profile_quality,
                    stability_summary=result.stability_summary,
                    benchmark_suite_loaded=benchmark_suite is not None,
                    manifest_seed=manifest_seed,
                    workbench_session=workbench_session,
                ),
            }
        )
        if persist:
            result_path = Path(result.persisted_path or "")
            result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            report_artifact = result.artifacts[-1]
            report_artifact.content_hash = _sha256_text(result_path.read_text(encoding="utf-8"))
            manifest.add_artifact(report_artifact)
            manifest.refresh_refs()
            manifest.save(manifest_path)
            result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        log_structured_event(
            "swarm_core.deliberation",
            "info",
            "deliberation_completed",
            deliberation_id=result.deliberation_id,
            mode=result.mode.value,
            status=result.status.value,
            runtime_requested=result.runtime_requested,
            runtime_used=result.runtime_used,
            engine_requested=result.engine_requested,
            engine_used=result.engine_used,
            fallback_used=result.fallback_used,
        )
        return result

    def load_result(self, deliberation_id: str) -> DeliberationResult:
        result_path = self.output_dir / deliberation_id / "result.json"
        return DeliberationResult.model_validate_json(result_path.read_text(encoding="utf-8"))

    def replay(self, deliberation_id: str, *, persist: bool = True, client: Any | None = None) -> DeliberationResult:
        manifest_path = self.output_dir / deliberation_id / "manifest.json"
        manifest = DeliberationRunManifest.load(manifest_path)
        payload = manifest.inputs
        return self.run(
            topic=str(payload.get("topic", manifest.topic)),
            objective=str(payload.get("objective", manifest.objective)),
            mode=manifest.mode,
            participants=list(payload.get("participants", [])),
            documents=list(payload.get("documents", [])),
            entities=list(payload.get("entities", [])),
            interventions=list(payload.get("interventions", [])),
            max_agents=int(payload.get("max_agents", 6) or 6),
            population_size=int(payload.get("population_size", 0) or 0) or None,
            rounds=int(payload.get("rounds", 2) or 2),
            time_horizon=str(payload.get("time_horizon", "7d")),
            persist=persist,
            runtime=str(payload.get("runtime", "pydanticai")),
            allow_fallback=bool(payload.get("allow_fallback", True)),
            engine_preference=str(payload.get("engine_preference", EnginePreference.agentsociety.value)),
            ensemble_engines=list(payload.get("ensemble_engines", [])),
            budget_max=float(payload.get("budget_max", 10.0) or 10.0),
            timeout_seconds=int(payload.get("timeout_seconds", 1800) or 1800),
            benchmark_path=None,
            stability_runs=1,
            client=client,
        )

    def _run_committee(
        self,
        *,
        run_id: str,
        topic: str,
        objective: str,
        participants: list[str],
        max_agents: int,
        rounds: int,
        runtime: str,
        allow_fallback: bool,
        persist: bool,
        client: Any | None,
    ) -> DeliberationResult:
        selected_runtime = _normalize_runtime(runtime)
        fallback_used = False
        runtime_used = selected_runtime
        runtime_error = None
        try:
            meeting = run_strategy_meeting_sync(
                topic=topic,
                objective=objective,
                participants=participants,
                max_agents=max_agents,
                rounds=rounds,
                persist=persist,
                config_path=self.config_path,
                runtime=selected_runtime,
                allow_fallback=allow_fallback,
                client=client,
            )
        except Exception as exc:
            if selected_runtime != "pydanticai" or not allow_fallback:
                raise
            meeting = run_strategy_meeting_sync(
                topic=topic,
                objective=objective,
                participants=participants,
                max_agents=max_agents,
                rounds=rounds,
                persist=persist,
                config_path=self.config_path,
                runtime="legacy",
                allow_fallback=True,
                client=client,
            )
            fallback_used = True
            runtime_used = "legacy"
            runtime_error = str(exc)
        return _committee_result_to_deliberation(
            run_id=run_id,
            topic=topic,
            objective=objective,
            meeting=meeting,
            runtime_requested=selected_runtime,
            runtime_used=runtime_used,
            fallback_used=fallback_used,
            runtime_error=runtime_error,
        )

    def _run_simulation(
        self,
        *,
        run_id: str,
        topic: str,
        objective: str,
        documents: list[str],
        entities: list[Any],
        interventions: list[str],
        population_size: int,
        rounds: int,
        time_horizon: str,
        engine_preference: EnginePreference,
        ensemble_engines: list[EnginePreference] | None,
        budget_max: float,
        timeout_seconds: int,
    ) -> DeliberationResult:
        selected_engines = ensemble_engines or [engine_preference]
        snapshots: list[DeliberationEngineSnapshot] = []
        metric_deltas: dict[str, float] = {}
        primary_result: DeliberationResult | None = None
        primary_snapshot: DeliberationEngineSnapshot | None = None

        for engine_choice in selected_engines:
            engine = EngineTarget(engine_choice.value)
            engine_run_id = f"{run_id}_{engine.value}"
            single_result = self._run_single_simulation_engine(
                run_id=engine_run_id,
                topic=topic,
                objective=objective,
                documents=documents,
                entities=entities,
                interventions=interventions,
                population_size=population_size,
                rounds=rounds,
                time_horizon=time_horizon,
                engine=engine,
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
            )
            snapshot = DeliberationEngineSnapshot(
                engine=engine.value,
                status=single_result.status,
                summary=single_result.summary,
                confidence_level=single_result.confidence_level,
                metrics=single_result.metrics,
                scenarios_count=len(single_result.scenarios),
                recommendations_count=len(single_result.recommendations),
                uncertainty_points=single_result.uncertainty_points,
                metadata={"run_id": single_result.deliberation_id},
            )
            snapshots.append(snapshot)
            if engine_choice == engine_preference:
                primary_result = single_result
                primary_snapshot = snapshot

        if primary_result is None:
            primary_result = snapshots and self._run_single_simulation_engine(
                run_id=f"{run_id}_{selected_engines[0].value}",
                topic=topic,
                objective=objective,
                documents=documents,
                entities=entities,
                interventions=interventions,
                population_size=population_size,
                rounds=rounds,
                time_horizon=time_horizon,
                engine=EngineTarget(selected_engines[0].value),
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
            )
            primary_snapshot = snapshots[0] if snapshots else None
        assert primary_result is not None

        if primary_snapshot is not None:
            for snapshot in snapshots:
                if snapshot.engine == primary_snapshot.engine:
                    continue
                shared_metric_names = set(primary_snapshot.metrics) & set(snapshot.metrics)
                for name in shared_metric_names:
                    metric_deltas[f"{primary_snapshot.engine}_vs_{snapshot.engine}:{name}"] = round(
                        primary_snapshot.metrics[name] - snapshot.metrics[name], 6
                    )
        primary_result.ensemble_report = _build_ensemble_report(
            primary_engine=engine_preference.value,
            snapshots=snapshots,
            metric_deltas=metric_deltas,
        )
        return primary_result

    def _run_single_simulation_engine(
        self,
        *,
        run_id: str,
        topic: str,
        objective: str,
        documents: list[str],
        entities: list[Any],
        interventions: list[str],
        population_size: int,
        rounds: int,
        time_horizon: str,
        engine: EngineTarget,
        budget_max: float,
        timeout_seconds: int,
    ) -> DeliberationResult:
        runtime_run_id = f"run_{run_id}"
        correlation_id = f"corr_{uuid4().hex[:12]}"
        create_command = AdapterCommandV1(
            command=AdapterCommand.create_run,
            runtime_run_id=runtime_run_id,
            engine=engine,
            brief=objective,
            control=ControlParams(
                timeout_seconds=timeout_seconds,
                budget_max=budget_max,
                progress_granularity=ProgressGranularity.fine,
            ),
            seed_materials=SeedMaterials(
                documents=documents,
                entities=entities,
                environment_seed={
                    "topic": topic,
                    "objective": objective,
                    "interventions": interventions,
                    "platforms": ["reddit", "twitter"] if engine == EngineTarget.oasis else ["society"],
                },
            ),
            parameters=SimulationParameters(
                max_agents=population_size,
                population_size=population_size,
                rounds=rounds,
                time_horizon=time_horizon,
                extra={
                    "topic": topic,
                    "objective": objective,
                    "interventions": interventions,
                    "timeout_seconds": timeout_seconds,
                    "platforms": ["reddit", "twitter"] if engine == EngineTarget.oasis else ["society"],
                },
            ),
            correlation_id=correlation_id,
            swarm_intent_id=f"intent_{run_id}",
        )
        initial = self.adapter_service.dispatch(create_command)
        terminal = self._wait_for_terminal(
            runtime_run_id=runtime_run_id,
            engine=engine,
            correlation_id=correlation_id,
            timeout_seconds=timeout_seconds,
        ) if not initial.is_terminal else initial
        if terminal.status == RunStatus.completed:
            final_result = self.adapter_service.dispatch(
                AdapterCommandV1(
                    command=AdapterCommand.get_result,
                    runtime_run_id=runtime_run_id,
                    engine=engine,
                    correlation_id=correlation_id,
                    swarm_intent_id=f"intent_{run_id}",
                )
            )
        else:
            final_result = terminal
        return _simulation_result_to_deliberation(
            run_id=run_id,
            topic=topic,
            objective=objective,
            runtime_requested="langgraph",
            engine_requested=engine.value,
            adapter_result=final_result,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
        )

    def _run_hybrid(
        self,
        *,
        run_id: str,
        topic: str,
        objective: str,
        participants: list[str],
        documents: list[str],
        entities: list[Any],
        interventions: list[str],
        max_agents: int,
        population_size: int,
        rounds: int,
        time_horizon: str,
        runtime: str,
        allow_fallback: bool,
        engine_preference: EnginePreference,
        ensemble_engines: list[EnginePreference] | None,
        budget_max: float,
        timeout_seconds: int,
        client: Any | None,
    ) -> DeliberationResult:
        simulation = self._run_simulation(
            run_id=f"{run_id}_sim",
            topic=topic,
            objective=objective,
            documents=documents,
            entities=entities,
            interventions=interventions,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            engine_preference=engine_preference,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
        )
        committee_topic = topic
        committee_objective = (
            f"{objective}\n\n"
            f"Simulation summary:\n{simulation.summary or 'No simulation summary available.'}\n\n"
            f"Risks:\n{_render_lines(simulation.risks)}\n\n"
            f"Recommendations:\n{_render_lines(simulation.recommendations)}"
        )
        committee = self._run_committee(
            run_id=f"{run_id}_committee",
            topic=committee_topic,
            objective=committee_objective,
            participants=participants,
            max_agents=max_agents,
            rounds=rounds,
            runtime=runtime,
            allow_fallback=allow_fallback,
            persist=False,
            client=client,
        )
        status = DeliberationStatus.completed
        if simulation.status != DeliberationStatus.completed or committee.status != DeliberationStatus.completed:
            status = DeliberationStatus.partial
        if simulation.status == DeliberationStatus.failed and committee.status == DeliberationStatus.failed:
            status = DeliberationStatus.failed

        confidence_level = min(1.0, (simulation.confidence_level * 0.55) + (committee.confidence_level * 0.45))
        judge_scores = _judge_result(
            summary=simulation.summary,
            scenarios=simulation.scenarios,
            recommendations=committee.next_actions or simulation.recommendations,
            artifacts_count=len(simulation.artifacts) + len(committee.artifacts),
            dissent_count=len(committee.dissent_points),
        )
        return DeliberationResult(
            deliberation_id=run_id,
            topic=topic,
            objective=objective,
            mode=DeliberationMode.hybrid,
            status=status,
            runtime_requested=committee.runtime_requested,
            runtime_used=committee.runtime_used,
            fallback_used=committee.fallback_used,
            runtime_resilience=_result_runtime_resilience(committee),
            engine_requested=simulation.engine_requested,
            engine_used=simulation.engine_used,
            participants=committee.participants,
            requested_max_agents=max_agents,
            population_size=population_size,
            time_horizon=time_horizon,
            rounds_requested=rounds,
            rounds_completed=max(simulation.rounds_completed, committee.rounds_completed),
            summary=simulation.summary,
            final_strategy=committee.final_strategy or committee.summary,
            consensus_points=committee.consensus_points,
            dissent_points=list(dict.fromkeys(committee.dissent_points + simulation.uncertainty_points)),
            next_actions=committee.next_actions or [str(item) for item in simulation.recommendations[:5]],
            scenarios=simulation.scenarios,
            risks=simulation.risks,
            recommendations=simulation.recommendations,
            metrics=simulation.metrics,
            confidence_level=confidence_level,
            uncertainty_points=list(dict.fromkeys(simulation.uncertainty_points + committee.dissent_points)),
            cluster_summaries=committee.cluster_summaries,
            sensitivity_factors=list(dict.fromkeys(simulation.sensitivity_factors + committee.dissent_points[:3])),
            artifacts=list(simulation.artifacts) + list(committee.artifacts),
            provenance=list(simulation.provenance) + list(committee.provenance),
            judge_scores=judge_scores,
            ensemble_report=simulation.ensemble_report,
            metadata={
                "simulation_status": simulation.status.value,
                "committee_status": committee.status.value,
                "simulation_runtime": simulation.runtime_used,
                "committee_runtime": committee.runtime_used,
                "committee_meeting_id": committee.metadata.get("meeting_id"),
                "simulation_backend_mode": self.backend_mode,
                "meeting_quality": committee.metadata.get("meeting_quality"),
                "runtime_resilience": _result_runtime_resilience(committee),
            },
        )

    def _wait_for_terminal(
        self,
        *,
        runtime_run_id: str,
        engine: EngineTarget,
        correlation_id: str,
        timeout_seconds: int,
    ) -> AdapterResultV1:
        deadline = time.monotonic() + timeout_seconds
        last_result = AdapterResultV1(runtime_run_id=runtime_run_id, status=RunStatus.queued)
        while time.monotonic() < deadline:
            status_result = self.adapter_service.dispatch(
                AdapterCommandV1(
                    command=AdapterCommand.get_status,
                    runtime_run_id=runtime_run_id,
                    engine=engine,
                    correlation_id=correlation_id,
                )
            )
            last_result = status_result
            if status_result.is_terminal:
                return status_result
            time.sleep(self.poll_interval_seconds)

        cancel_result = self.adapter_service.dispatch(
            AdapterCommandV1(
                command=AdapterCommand.cancel_run,
                runtime_run_id=runtime_run_id,
                engine=engine,
                correlation_id=correlation_id,
            )
        )
        if cancel_result.status == RunStatus.cancelled:
            return AdapterResultV1(
                runtime_run_id=runtime_run_id,
                engine_run_id=cancel_result.engine_run_id,
                status=RunStatus.timed_out,
                errors=cancel_result.errors
                or [
                    NormalizedError.from_code(
                        EngineErrorCode.timeout,
                        "Deliberation timed out while waiting for the simulation engine.",
                    )
                ],
                correlation_id=correlation_id,
            )
        return last_result


def load_deliberation_result(
    deliberation_id: str,
    *,
    output_dir: str | Path | None = None,
) -> DeliberationResult:
    coordinator = DeliberationCoordinator(output_dir=output_dir)
    return coordinator.load_result(deliberation_id)


def run_deliberation_sync(
    *,
    topic: str,
    objective: str | None = None,
    mode: DeliberationMode | str = DeliberationMode.committee,
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str = "pydanticai",
    allow_fallback: bool = True,
    engine_preference: EnginePreference | str = EnginePreference.agentsociety,
    ensemble_engines: list[EnginePreference | str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str | None = None,
    stability_runs: int = 1,
    output_dir: str | Path | None = None,
    backend_mode: str | None = None,
    client: Any | None = None,
) -> DeliberationResult:
    coordinator = DeliberationCoordinator(
        config_path=config_path,
        output_dir=output_dir,
        backend_mode=backend_mode,
    )
    return coordinator.run(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        persist=persist,
        runtime=runtime,
        allow_fallback=allow_fallback,
        engine_preference=engine_preference,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        stability_runs=stability_runs,
        client=client,
    )


def replay_deliberation_sync(
    deliberation_id: str,
    *,
    persist: bool = True,
    output_dir: str | Path | None = None,
    backend_mode: str | None = None,
    client: Any | None = None,
) -> DeliberationResult:
    coordinator = DeliberationCoordinator(output_dir=output_dir, backend_mode=backend_mode)
    return coordinator.replay(deliberation_id, persist=persist, client=client)


def _normalize_mode(mode: DeliberationMode | str) -> DeliberationMode:
    if isinstance(mode, DeliberationMode):
        return mode
    return DeliberationMode(str(mode).strip().lower())


def _normalize_runtime(runtime: str) -> str:
    candidate = str(runtime).strip().lower()
    if candidate == "legacy":
        return "legacy"
    return "pydanticai"


def _normalize_engine_preference(engine_preference: EnginePreference | str) -> EnginePreference:
    if isinstance(engine_preference, EnginePreference):
        return engine_preference
    return EnginePreference(str(engine_preference).strip().lower())


def _normalize_engine_preferences(
    engine_preferences: list[EnginePreference | str] | None,
    *,
    primary: EnginePreference,
) -> list[EnginePreference]:
    normalized = [primary]
    for item in engine_preferences or []:
        candidate = _normalize_engine_preference(item)
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _resolve_population_size(
    *,
    mode: DeliberationMode,
    population_size: int | None,
    max_agents: int,
    participants: list[str],
    documents: list[str],
) -> int:
    if mode == DeliberationMode.committee:
        return max(2, min(max_agents, len(participants) or max_agents))
    base = int(population_size or max_agents or 100)
    if len(documents) >= 5 and base < 250:
        return 250
    return max(32, base)


def _build_graph_payload(
    *,
    topic: str,
    objective: str,
    participants: list[str],
    documents: list[str],
    entities: list[Any],
    interventions: list[str],
    population_size: int,
) -> dict[str, Any]:
    nodes = [{"node_id": "topic", "label": topic, "node_type": "topic"}]
    nodes.extend(
        {"node_id": f"participant_{index}", "label": participant, "node_type": "participant"}
        for index, participant in enumerate(participants, start=1)
    )
    nodes.extend(
        {"node_id": f"document_{index}", "label": document[:120], "node_type": "document"}
        for index, document in enumerate(documents, start=1)
    )
    nodes.extend(
        {"node_id": f"entity_{index}", "label": json.dumps(entity, sort_keys=True)[:120], "node_type": "entity"}
        for index, entity in enumerate(entities, start=1)
    )
    nodes.extend(
        {"node_id": f"intervention_{index}", "label": intervention[:120], "node_type": "intervention"}
        for index, intervention in enumerate(interventions, start=1)
    )
    edges = []
    for node in nodes[1:]:
        edges.append({"source": "topic", "target": node["node_id"], "relation": "informs"})
    return {
        "topic": topic,
        "objective": objective,
        "population_size": population_size,
        "nodes": nodes,
        "edges": edges,
    }


def _merge_graph_payloads(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    nodes = list(base.get("nodes", []))
    seen_node_ids = {str(node.get("node_id")) for node in nodes}
    for node in extra.get("nodes", []):
        node_id = str(node.get("node_id"))
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        nodes.append(node)
    edges = list(base.get("edges", []))
    seen_edges = {(str(edge.get("source")), str(edge.get("target")), str(edge.get("relation"))) for edge in edges}
    for edge in extra.get("edges", []):
        key = (str(edge.get("source")), str(edge.get("target")), str(edge.get("relation")))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(edge)
    merged = dict(base)
    merged["nodes"] = nodes
    merged["edges"] = edges
    merged["metadata"] = {
        **dict(base.get("metadata", {})),
        **dict(extra.get("metadata", {})),
    }
    return merged


def _meeting_runtime_resilience(meeting: StrategyMeetingResult) -> dict[str, Any] | None:
    resilience = meeting.metadata.get("runtime_resilience") if isinstance(meeting.metadata, dict) else None
    if isinstance(resilience, dict):
        return dict(resilience)
    return None


def _result_runtime_resilience(result: DeliberationResult) -> dict[str, Any] | None:
    if isinstance(result.runtime_resilience, dict):
        return dict(result.runtime_resilience)
    resilience = result.metadata.get("runtime_resilience") if isinstance(result.metadata, dict) else None
    if isinstance(resilience, dict):
        return dict(resilience)
    return None


def _committee_result_to_deliberation(
    *,
    run_id: str,
    topic: str,
    objective: str,
    meeting: StrategyMeetingResult,
    runtime_requested: str,
    runtime_used: str,
    fallback_used: bool,
    runtime_error: str | None,
) -> DeliberationResult:
    runtime_resilience = _meeting_runtime_resilience(meeting)
    meeting_metadata = dict(meeting.metadata or {}) if isinstance(meeting.metadata, dict) else {}
    meeting_fallback_used = bool(
        fallback_used
        or meeting_metadata.get("fallback_used")
        or (runtime_resilience.get("degraded_runtime_used") if runtime_resilience else None)
    )
    meeting_degraded_runtime_used = (
        str(
            meeting_metadata.get("degraded_runtime_used")
            or (runtime_resilience.get("degraded_runtime_used") if runtime_resilience else "")
        ).strip()
        or None
    )
    decision_degraded = bool(
        meeting_metadata.get("decision_degraded")
        or meeting_fallback_used
        or meeting_degraded_runtime_used
        or (runtime_resilience.get("degraded_mode") if runtime_resilience else False)
    )
    cluster_summaries = [
        DeliberationClusterSummary(
            cluster_index=summary.cluster_index,
            participants=summary.participants,
            summary=summary.summary,
            consensus_points=summary.consensus_points,
            dissent_points=summary.dissent_points,
            next_actions=summary.next_actions,
            quality_score=summary.quality_score,
            confidence_score=summary.confidence_score,
            metadata=summary.metadata,
        )
        for summary in meeting.cluster_summaries
    ]
    judge_scores = _judge_result(
        summary=meeting.strategy,
        scenarios=[],
        recommendations=meeting.next_actions,
        artifacts_count=1 if meeting.persisted_path else 0,
        dissent_count=len(meeting.dissent_points),
    )
    status = DeliberationStatus.completed
    if meeting.status.value == "partial":
        status = DeliberationStatus.partial
    elif meeting.status.value == "failed":
        status = DeliberationStatus.failed
    result = DeliberationResult(
        deliberation_id=run_id,
        topic=topic,
        objective=objective,
        mode=DeliberationMode.committee,
        status=status,
        runtime_requested=runtime_requested,
        runtime_used=runtime_used,
        fallback_used=meeting_fallback_used,
        runtime_resilience=runtime_resilience,
        engine_requested=None,
        engine_used=None,
        participants=meeting.participants,
        requested_max_agents=meeting.requested_max_agents,
        population_size=len(meeting.participants),
        rounds_requested=meeting.requested_rounds,
        rounds_completed=meeting.rounds_completed,
        summary=meeting.strategy,
        final_strategy=meeting.strategy,
        consensus_points=meeting.consensus_points,
        dissent_points=meeting.dissent_points,
        next_actions=meeting.next_actions,
        confidence_level=max(meeting.confidence_score, judge_scores.overall),
        uncertainty_points=list(dict.fromkeys(meeting.dissent_points)),
        cluster_summaries=cluster_summaries,
        sensitivity_factors=list(dict.fromkeys(meeting.dissent_points[:3])),
        judge_scores=judge_scores,
        metadata={
            **meeting.metadata,
            "meeting_id": meeting.meeting_id,
            "runtime_error": runtime_error,
            "runtime_resilience": runtime_resilience,
            "fallback_used": meeting_fallback_used,
            "degraded_runtime_used": meeting_degraded_runtime_used,
            "meeting_degraded_runtime_used": meeting_degraded_runtime_used,
            "decision_degraded": decision_degraded,
            "routing_mode": meeting.routing_mode,
            "meeting_quality": _build_meeting_quality_metadata(
                quality_score=meeting.quality_score,
                confidence_score=meeting.confidence_score,
                dissent_turn_count=meeting.dissent_turn_count,
                rounds_completed=meeting.rounds_completed,
                routing_mode=meeting.routing_mode,
                hierarchical=meeting.hierarchical,
                cluster_count=len(meeting.cluster_summaries),
                round_phases=list(meeting.round_phases),
            ),
        },
    )
    return result


def _simulation_result_to_deliberation(
    *,
    run_id: str,
    topic: str,
    objective: str,
    runtime_requested: str,
    engine_requested: str,
    adapter_result: AdapterResultV1,
    population_size: int,
    rounds: int,
    time_horizon: str,
) -> DeliberationResult:
    status = DeliberationStatus.completed
    if adapter_result.status in {RunStatus.failed, RunStatus.engine_unavailable, RunStatus.timed_out}:
        status = DeliberationStatus.failed
    elif adapter_result.status in {RunStatus.cancelled}:
        status = DeliberationStatus.partial
    metrics = {metric.name: metric.value for metric in adapter_result.metrics}
    uncertainty_points = [str(risk) for risk in adapter_result.risks[:5]]
    uncertainty_points.extend(error.message for error in adapter_result.errors[:5])
    judge_scores = _judge_result(
        summary=adapter_result.summary or "",
        scenarios=adapter_result.scenarios,
        recommendations=adapter_result.recommendations,
        artifacts_count=len(adapter_result.artifacts),
        dissent_count=len(adapter_result.errors),
    )
    confidence = max(
        0.0,
        min(
            1.0,
            (0.3 if status == DeliberationStatus.completed else 0.1)
            + (0.15 if adapter_result.summary else 0.0)
            + min(0.3, 0.05 * len(adapter_result.scenarios))
            + min(0.15, 0.03 * len(adapter_result.recommendations))
            + min(0.1, 0.02 * len(adapter_result.artifacts))
            - min(0.2, 0.05 * len(adapter_result.errors)),
        ),
    )
    sensitivity_factors = list(metrics.keys())[:5]
    if adapter_result.progress and adapter_result.progress.message:
        sensitivity_factors.append(adapter_result.progress.message)
    result = DeliberationResult(
        deliberation_id=run_id,
        topic=topic,
        objective=objective,
        mode=DeliberationMode.simulation,
        status=status,
        runtime_requested=runtime_requested,
        runtime_used="langgraph",
        engine_requested=engine_requested,
        engine_used=adapter_result.engine_meta.engine or engine_requested,
        participants=[],
        requested_max_agents=population_size,
        population_size=population_size,
        time_horizon=time_horizon,
        rounds_requested=rounds,
        rounds_completed=rounds if adapter_result.status == RunStatus.completed else 0,
        summary=adapter_result.summary or "",
        scenarios=adapter_result.scenarios,
        risks=adapter_result.risks,
        recommendations=adapter_result.recommendations,
        metrics=metrics,
        confidence_level=max(confidence, judge_scores.overall),
        uncertainty_points=list(dict.fromkeys(uncertainty_points)),
        sensitivity_factors=sensitivity_factors,
        judge_scores=judge_scores,
        metadata={
            "adapter_status": adapter_result.status.value,
            "engine_run_id": adapter_result.engine_run_id,
            "errors": [error.model_dump(mode="json") for error in adapter_result.errors],
            "artifacts": [artifact.model_dump(mode="json") for artifact in adapter_result.artifacts],
        },
    )
    result.artifacts.extend(
        DeliberationArtifact(
            artifact_id=f"artifact_engine_{index}",
            kind=DeliberationArtifactKind.other,
            title=artifact.name,
            uri=artifact.uri,
            content_type=artifact.content_type,
        )
        for index, artifact in enumerate(adapter_result.artifacts, start=1)
    )
    return result


def _judge_result(
    *,
    summary: str,
    scenarios: list[Any],
    recommendations: list[Any],
    artifacts_count: int,
    dissent_count: int,
) -> DeliberationJudgeScores:
    coherence = min(1.0, 0.2 + (0.25 if summary else 0.0) + min(0.25, len(str(summary)) / 800))
    diversity = min(1.0, 0.15 + 0.18 * min(3, len(scenarios)))
    actionability = min(1.0, 0.15 + 0.2 * min(3, len(recommendations)))
    explainability = min(1.0, 0.15 + 0.08 * artifacts_count + (0.1 if summary else 0.0) - min(0.2, 0.04 * dissent_count))
    overall = max(0.0, min(1.0, (coherence + diversity + actionability + explainability) / 4))
    return DeliberationJudgeScores(
        coherence=coherence,
        diversity=diversity,
        actionability=actionability,
        explainability=explainability,
        overall=overall,
    )


def _persona_profile_to_workbench(profile) -> WorkbenchPersonaProfile:
    return WorkbenchPersonaProfile(
        profile_id=profile.profile_id,
        label=profile.label,
        role=profile.role.value if hasattr(profile.role, "value") else str(profile.role),
        stance=profile.stance.value if hasattr(profile.stance, "value") else str(profile.stance),
        confidence=profile.confidence,
        trust=profile.trust,
        summary=profile.summary,
        evidence=list(profile.evidence),
        memory_window=list(profile.memory_window),
        metadata={**dict(profile.metadata), "keywords": list(getattr(profile, "keywords", []))},
    )


def _resolve_platforms(mode: DeliberationMode, engine_used: str | None) -> list[str]:
    if engine_used == EngineTarget.oasis.value:
        return ["twitter", "reddit", "forum"]
    if mode == DeliberationMode.committee:
        return ["committee", "forum"]
    return ["society", "reddit", "twitter"]


def _group_traces_by_round(traces, *, rounds: int) -> list[list[Any]]:
    grouped: list[list[Any]] = [[] for _ in range(max(1, rounds))]
    for trace in traces:
        index = int(trace.round_index or 0)
        index = max(0, min(len(grouped) - 1, index))
        grouped[index].append(trace)
    return grouped


def _run_scenario_judge(*, topic: str, result: DeliberationResult) -> dict[str, Any] | None:
    candidates: list[ScenarioCandidate] = []
    for index, scenario in enumerate(result.scenarios[:6], start=1):
        if isinstance(scenario, dict):
            title = str(scenario.get("title") or scenario.get("scenario_id") or f"scenario_{index}")
            thesis = str(
                scenario.get("description")
                or scenario.get("summary")
                or scenario.get("thesis")
                or result.summary
                or title
            )
        else:
            title = f"scenario_{index}"
            thesis = str(scenario)
        candidates.append(
            ScenarioCandidate(
                title=title,
                topic=topic,
                thesis=thesis,
                evidence=[item.title for item in result.provenance[:3]],
                risks=[str(item) for item in result.risks[:3]],
                actions=[str(item) for item in result.next_actions[:3] or result.recommendations[:3]],
                confidence=result.confidence_level,
                impact=min(1.0, 0.4 + (0.1 * index)),
            )
        )
    if not candidates and (result.summary or result.final_strategy):
        candidates.append(
            ScenarioCandidate(
                title="summary_candidate",
                topic=topic,
                thesis=result.summary or result.final_strategy,
                evidence=[item.title for item in result.provenance[:3]],
                risks=[str(item) for item in result.risks[:3]],
                actions=[str(item) for item in result.next_actions[:3]],
                confidence=result.confidence_level,
                impact=0.6,
            )
        )
    if not candidates:
        return None
    report = ScenarioJudge().judge(candidates, topic=topic)
    return report.model_dump(mode="json")


def _belief_state_snapshots_from_evolution(*, run_id: str, evolution: BeliefEvolutionEngine | Any) -> list[BeliefStateSnapshot]:
    snapshots: list[BeliefStateSnapshot] = []
    for round_snapshot in getattr(evolution, "snapshots", []) or []:
        tick = int(getattr(round_snapshot, "round_index", 0) or 0)
        for state in getattr(round_snapshot, "states", []) or []:
            snapshots.append(belief_state_snapshot_from_state(run_id=run_id, state=state, tick=tick))
    return snapshots


def _build_manifest_seed(
    *,
    topic: str,
    objective: str,
    participants: list[str],
    documents: list[str],
    entities: list[Any],
    interventions: list[str],
) -> dict[str, Any]:
    payload = {
        "topic": topic,
        "objective": objective,
        "participants": participants,
        "documents": documents,
        "entities": entities,
        "interventions": interventions,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return {
        "input_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "participants_hash": hashlib.sha256(json.dumps(participants, sort_keys=True).encode("utf-8")).hexdigest(),
        "documents_hash": hashlib.sha256(json.dumps(documents, sort_keys=True).encode("utf-8")).hexdigest(),
        "entities_hash": _stable_hash_value(entities),
        "interventions_hash": _stable_hash_value(interventions),
    }


def _load_benchmark_suite(benchmark_path: str | None) -> DeliberationBenchmarkSuite | None:
    candidate_path = Path(benchmark_path or DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH)
    if not candidate_path.exists():
        return None
    return DeliberationBenchmarkSuite.load(candidate_path)


def _evaluate_deliberation(
    result: DeliberationResult,
    suite: DeliberationBenchmarkSuite,
) -> DeliberationBenchmarkReport:
    scalar_metrics = _collect_result_metrics(result)
    outcomes: list[DeliberationBenchmarkOutcome] = []
    for case in suite.cases:
        if case.mode != result.mode:
            continue
        matched = 0
        for expectation in case.expectations:
            if expectation.matches(scalar_metrics.get(expectation.metric)):
                matched += 1
        total = len(case.expectations) or 1
        score = matched / total
        outcomes.append(
            DeliberationBenchmarkOutcome(
                case_id=case.case_id,
                passed=matched == total,
                score=score,
                metrics=scalar_metrics,
                notes=case.description,
                artifact_ids=[artifact.artifact_id for artifact in result.artifacts],
            )
        )
    return DeliberationBenchmarkReport.from_outcomes(
        suite_id=suite.suite_id,
        run_id=result.deliberation_id,
        outcomes=outcomes,
        metadata={"mode": result.mode.value},
    )


def _collect_result_metrics(result: DeliberationResult) -> dict[str, float]:
    payload = dict(result.metrics)
    payload.update(
        {
            "confidence_level": result.confidence_level,
            "quality_score": result.judge_scores.overall,
            "profile_quality_score": float((result.profile_quality or {}).get("overall_score", 0.0) or 0.0),
            "scenarios_count": float(len(result.scenarios)),
            "recommendations_count": float(len(result.recommendations) or len(result.next_actions)),
            "cluster_count": float(len(result.cluster_summaries)),
            "status_completed": 1.0 if result.status == DeliberationStatus.completed else 0.0,
            "has_final_strategy": 1.0 if bool(result.final_strategy) else 0.0,
            "fallback_used": 1.0 if result.fallback_used else 0.0,
        }
    )
    if result.stability_summary is not None:
        payload["stability_sample_sufficient"] = 1.0 if result.stability_summary.sample_sufficient else 0.0
        payload["stability_dispersion_gate_passed"] = 1.0 if result.stability_summary.dispersion_gate_passed else 0.0
    return payload


def _build_sensitivity_factors(
    result: DeliberationResult,
    stability_summary: DeliberationStabilitySummary,
) -> list[str]:
    factors = list(result.sensitivity_factors)
    if getattr(stability_summary, "sample_sufficient", True) is False:
        factors.append("stability_sample_count_insufficient")
    if getattr(stability_summary, "dispersion_gate_passed", True) is False:
        factors.append("stability_dispersion_gate_failed")
    if not stability_summary.stable:
        factors.append("stability_variance_above_threshold")
    if stability_summary.coefficient_of_variation > 0.1:
        factors.append("coefficient_of_variation_high")
    if result.fallback_used:
        factors.append("runtime_fallback_used")
    return list(dict.fromkeys(factors))


def _build_comparability_metadata(
    *,
    result: DeliberationResult,
    profile_quality: dict[str, Any] | None,
    stability_summary: DeliberationStabilitySummary | None,
    benchmark_suite_loaded: bool,
    manifest_seed: dict[str, Any] | None = None,
    workbench_session: WorkbenchSession | None = None,
) -> dict[str, Any]:
    profile_quality = profile_quality or {}
    manifest_seed = manifest_seed or {}
    issue_codes = sorted(
        {
            str(issue.get("code", "")).strip()
            for issue in list(profile_quality.get("issues", []) if profile_quality else [])
            if isinstance(issue, dict) and str(issue.get("code", "")).strip()
        }
    )
    profile_count = int(result.metadata.get("profile_count") or len(result.participant_profiles) or 0)
    belief_group_count = len(result.belief_group_summaries)
    meeting_quality = dict(result.metadata.get("meeting_quality") or {})
    runtime_resilience = _result_runtime_resilience(result)
    request = result.request
    request_metadata = dict(getattr(request, "metadata", {}) or {})
    workbench_input = workbench_session.input_bundle.model_dump(mode="json") if workbench_session is not None else None
    if isinstance(workbench_input, dict):
        workbench_input = dict(workbench_input)
        workbench_input.pop("created_at", None)
    artifact_descriptors = [
        {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind.value if hasattr(artifact.kind, "value") else str(artifact.kind),
            "title": artifact.title,
            "content_hash": artifact.content_hash,
        }
        for artifact in result.artifacts
    ]
    runtime_identity = {
        "runtime_requested": result.runtime_requested,
        "runtime_used": result.runtime_used,
        "runtime_backend": request_metadata.get("runtime") or result.runtime_used or result.runtime_requested,
        "backend_mode": request_metadata.get("backend_mode"),
        "engine_requested": result.engine_requested,
        "engine_used": result.engine_used,
        "engine_preference": request.engine_preference if request is not None else None,
        "model_name": result.metadata.get("model_name") or request_metadata.get("model_name"),
        "provider": result.metadata.get("provider") or request_metadata.get("provider"),
    }
    workbench_identity = {
        "workbench_input_hash": _stable_hash_value(workbench_input) if workbench_input is not None else None,
        "profile_pipeline_request_id": request_metadata.get("profile_pipeline_request_id")
        or (workbench_session.metadata.get("profile_pipeline_request_id") if workbench_session is not None else None),
        "profile_pipeline_version": request_metadata.get("profile_pipeline_version")
        or (workbench_session.metadata.get("profile_pipeline_version") if workbench_session is not None else None),
        "profile_keywords": request_metadata.get("profile_keywords")
        or (workbench_session.metadata.get("profile_keywords") if workbench_session is not None else None),
        "workbench_profile_count": len(workbench_session.profiles) if workbench_session is not None else 0,
        "artifact_keys": [f"{item['kind']}:{item['title'] or item['artifact_id']}" for item in artifact_descriptors],
    }
    comparative: dict[str, Any] = {
        "mode": result.mode.value,
        "runtime_requested": result.runtime_requested,
        "runtime_used": result.runtime_used,
        "runtime_match": bool(result.runtime_used is None or result.runtime_requested == result.runtime_used),
        "fallback_used": result.fallback_used,
        "degraded_runtime_used": result.metadata.get("degraded_runtime_used"),
        "meeting_degraded_runtime_used": result.metadata.get("degraded_runtime_used"),
        "decision_degraded": bool(result.metadata.get("decision_degraded")),
        "engine_requested": result.engine_requested,
        "engine_used": result.engine_used,
        "engine_match": bool(result.engine_used is None or result.engine_requested == result.engine_used),
        "requested_max_agents": result.requested_max_agents,
        "population_size": result.population_size,
        "rounds_requested": result.rounds_requested,
        "rounds_completed": result.rounds_completed,
        "participant_count": len(result.participants),
        "profile_count": profile_count,
        "belief_group_count": belief_group_count,
        "cluster_count": len(result.cluster_summaries),
        "scenario_count": len(result.scenarios),
        "recommendation_count": len(result.recommendations) or len(result.next_actions),
        "profile_quality_overall": float(profile_quality.get("overall_score", 0.0) or 0.0),
        "profile_quality_passed": bool(profile_quality.get("passed", False)),
        "profile_quality_coverage": float(profile_quality.get("coverage", 0.0) or 0.0),
        "profile_quality_grounding": float(profile_quality.get("grounding", 0.0) or 0.0),
        "profile_quality_diversity": float(profile_quality.get("diversity", 0.0) or 0.0),
        "profile_quality_stance_diversity": float(profile_quality.get("stance_diversity", 0.0) or 0.0),
        "profile_quality_role_diversity": float(profile_quality.get("role_diversity", 0.0) or 0.0),
        "profile_quality_consistency": float(profile_quality.get("consistency", 0.0) or 0.0),
        "profile_quality_label_quality": float(profile_quality.get("label_quality", 0.0) or 0.0),
        "profile_quality_issue_codes": issue_codes,
        "benchmark_suite_loaded": benchmark_suite_loaded,
        "benchmark_report_available": result.benchmark_report is not None,
        "meeting_quality_score": None,
        "meeting_confidence_score": None,
        "meeting_dissent_turn_count": None,
        "meeting_quality_summary": "",
        "meeting_runtime_resilience": runtime_resilience,
        "meeting_runtime_resilience_status": runtime_resilience.get("status") if runtime_resilience else None,
        "meeting_runtime_resilience_score": runtime_resilience.get("score") if runtime_resilience else None,
        "meeting_runtime_resilience_degraded_mode": runtime_resilience.get("degraded_mode") if runtime_resilience else None,
        "meeting_runtime_resilience_degraded_runtime_used": runtime_resilience.get("degraded_runtime_used") if runtime_resilience else None,
        "meeting_cluster_runtime_diagnostic_count": int(result.metadata.get("cluster_runtime_diagnostic_count") or 0),
        "meeting_cluster_fallback_count": int(result.metadata.get("cluster_fallback_count") or 0),
        "meeting_cluster_error_categories": list(result.metadata.get("cluster_error_categories") or []),
        "meeting_routing_mode": str(result.metadata.get("routing_mode") or ""),
        "meeting_hierarchical": bool(result.metadata.get("hierarchical", False)),
        "meeting_cluster_count": int(result.metadata.get("cluster_count") or len(result.cluster_summaries) or 0),
        "input_hash": manifest_seed.get("input_hash")
        or _stable_hash_value(
            {
                "topic": result.topic,
                "objective": result.objective,
                "participants": result.participants,
                "documents": list(getattr(request, "documents", []) if request is not None else result.metadata.get("documents", [])),
                "entities": list(getattr(request, "entities", []) if request is not None else result.metadata.get("entities", [])),
                "interventions": list(
                    getattr(request, "interventions", []) if request is not None else result.metadata.get("interventions", [])
                ),
            }
        ),
        "participants_hash": manifest_seed.get("participants_hash")
        or _stable_hash_value(list(getattr(request, "participants", result.participants)) if request is not None else result.participants),
        "documents_hash": manifest_seed.get("documents_hash")
        or _stable_hash_value(list(getattr(request, "documents", [])) if request is not None else []),
        "entities_hash": manifest_seed.get("entities_hash")
        or _stable_hash_value(list(getattr(request, "entities", [])) if request is not None else []),
        "interventions_hash": manifest_seed.get("interventions_hash")
        or _stable_hash_value(list(getattr(request, "interventions", [])) if request is not None else []),
        "workbench_input_hash": workbench_identity["workbench_input_hash"],
        "artifact_keys": workbench_identity["artifact_keys"],
        "artifact_hashes": {
            item["artifact_id"]: item["content_hash"]
            for item in artifact_descriptors
            if item["content_hash"]
        },
        "runtime_identity": runtime_identity,
        "workbench_identity": workbench_identity,
        "stability_sample_count": None,
        "stability_minimum_sample_count": None,
        "stability_sample_sufficient": None,
        "stability_dispersion_gate_passed": None,
        "stability_stable": None,
        "stability_threshold": None,
        "stability_mean_score": None,
        "stability_std_dev": None,
        "stability_score_spread": None,
        "stability_coefficient_of_variation": None,
        "stability_assessment_flags": [],
        "stability_notes": "",
        "stability_sample_ratio": None,
    }
    if meeting_quality:
        comparative.update(
            {
                "meeting_quality_score": meeting_quality.get("quality_score"),
                "meeting_confidence_score": meeting_quality.get("confidence_score"),
                "meeting_dissent_turn_count": meeting_quality.get("dissent_turn_count"),
                "meeting_quality_summary": str(meeting_quality.get("summary", "")),
                "meeting_routing_mode": str(meeting_quality.get("routing_mode") or comparative["meeting_routing_mode"]),
                "meeting_hierarchical": bool(meeting_quality.get("hierarchical", comparative["meeting_hierarchical"])),
                "meeting_cluster_count": int(meeting_quality.get("cluster_count") or comparative["meeting_cluster_count"] or 0),
            }
        )
    if stability_summary is not None:
        comparative.update(
            {
                "stability_sample_count": stability_summary.sample_count,
                "stability_minimum_sample_count": stability_summary.minimum_sample_count,
                "stability_sample_sufficient": stability_summary.sample_sufficient,
                "stability_dispersion_gate_passed": stability_summary.dispersion_gate_passed,
                "stability_stable": stability_summary.stable,
                "stability_threshold": stability_summary.threshold,
                "stability_mean_score": stability_summary.mean_score,
                "stability_std_dev": stability_summary.std_dev,
                "stability_score_spread": stability_summary.score_spread,
                "stability_coefficient_of_variation": stability_summary.coefficient_of_variation,
                "stability_assessment_flags": list(stability_summary.assessment_flags),
                "stability_notes": stability_summary.notes,
                "stability_sample_ratio": round(
                    stability_summary.sample_count / max(1, stability_summary.minimum_sample_count),
                    3,
                ),
            }
        )
    return comparative


def _build_quality_warnings(
    *,
    result: DeliberationResult,
    profile_quality: dict[str, Any] | None,
    stability_summary: DeliberationStabilitySummary | None,
    comparability: dict[str, Any] | None = None,
) -> list[str]:
    warnings: list[str] = []
    profile_quality = profile_quality or {}
    comparability = comparability or {}
    issue_codes = {
        str(issue.get("code", "")).strip()
        for issue in list(profile_quality.get("issues", []) if profile_quality else [])
        if isinstance(issue, dict)
    }
    if result.fallback_used:
        warnings.append(
            f"runtime_fallback_used: requested={result.runtime_requested} used={result.runtime_used}"
        )
    if result.runtime_requested and result.runtime_used and result.runtime_requested != result.runtime_used:
        warnings.append(
            f"runtime_mismatch: requested={result.runtime_requested} used={result.runtime_used}"
        )
    if result.engine_requested and result.engine_used and result.engine_requested != result.engine_used:
        warnings.append(
            f"engine_mismatch: requested={result.engine_requested} used={result.engine_used}"
        )
    if profile_quality and not bool(profile_quality.get("passed", False)):
        warnings.append(
            "profile_quality_below_threshold: "
            f"overall={float(profile_quality.get('overall_score', 0.0) or 0.0):.3f} "
            f"passed={bool(profile_quality.get('passed', False))}"
        )
    profile_diversity = float(comparability.get("profile_quality_diversity", profile_quality.get("diversity", 0.0)) or 0.0)
    stance_diversity = float(
        comparability.get("profile_quality_stance_diversity", profile_quality.get("stance_diversity", 0.0)) or 0.0
    )
    role_diversity = float(comparability.get("profile_quality_role_diversity", profile_quality.get("role_diversity", 0.0)) or 0.0)
    if profile_quality and (
        issue_codes & {"diversity_low", "stance_diversity_low", "role_diversity_low"} or min(
            profile_diversity,
            stance_diversity,
            role_diversity,
        ) < 0.35
    ):
        warnings.append(
            "profile_diversity_low: "
            f"diversity={profile_diversity:.3f} "
            f"stance={stance_diversity:.3f} "
            f"role={role_diversity:.3f}"
        )
    if stability_summary is not None:
        sample_count = int(comparability.get("stability_sample_count", stability_summary.sample_count) or stability_summary.sample_count)
        minimum_sample_count = int(
            comparability.get("stability_minimum_sample_count", stability_summary.minimum_sample_count)
            or stability_summary.minimum_sample_count
        )
        if bool(comparability.get("stability_sample_sufficient", stability_summary.sample_sufficient)) is False:
            warnings.append(f"stability_sample_count_insufficient: {sample_count}/{minimum_sample_count}")
        if bool(comparability.get("stability_dispersion_gate_passed", stability_summary.dispersion_gate_passed)) is False:
            warnings.append(
                "stability_dispersion_gate_failed: "
                f"std_dev={stability_summary.std_dev:.4f} "
                f"spread={stability_summary.score_spread:.4f} "
                f"threshold={stability_summary.threshold:.4f}"
            )
        if bool(comparability.get("stability_stable", stability_summary.stable)) is False:
            warnings.append(
                "stability_not_confirmed: "
                f"sample_sufficient={stability_summary.sample_sufficient} "
                f"dispersion_gate_passed={stability_summary.dispersion_gate_passed}"
            )
    return list(dict.fromkeys(warnings))


def _build_meeting_quality_metadata(
    *,
    quality_score: float | None,
    confidence_score: float | None,
    dissent_turn_count: int | None,
    rounds_completed: int | None,
    routing_mode: str | None,
    hierarchical: bool | None,
    cluster_count: int | None = None,
    round_phases: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "quality_score": quality_score,
        "confidence_score": confidence_score,
        "dissent_turn_count": dissent_turn_count,
        "rounds_completed": rounds_completed,
        "routing_mode": routing_mode,
        "hierarchical": hierarchical,
        "cluster_count": cluster_count,
        "round_phases": list(round_phases or []),
        "summary": _meeting_quality_summary(
            quality_score=quality_score,
            confidence_score=confidence_score,
            dissent_turn_count=dissent_turn_count,
            rounds_completed=rounds_completed,
            routing_mode=routing_mode,
            hierarchical=hierarchical,
            cluster_count=cluster_count,
        ),
    }


def _meeting_quality_summary(
    *,
    quality_score: float | None,
    confidence_score: float | None,
    dissent_turn_count: int | None,
    rounds_completed: int | None,
    routing_mode: str | None,
    hierarchical: bool | None,
    cluster_count: int | None = None,
) -> str:
    parts: list[str] = []
    if quality_score is not None:
        parts.append(f"quality={quality_score:.3f}")
    if confidence_score is not None:
        parts.append(f"confidence={confidence_score:.3f}")
    if dissent_turn_count is not None:
        parts.append(f"dissent_turns={dissent_turn_count}")
    if rounds_completed is not None:
        parts.append(f"rounds={rounds_completed}")
    if routing_mode:
        parts.append(f"routing={routing_mode}")
    if hierarchical is not None:
        parts.append(f"hierarchical={hierarchical}")
    if cluster_count is not None:
        parts.append(f"clusters={cluster_count}")
    return "; ".join(parts)


def _derive_belief_states(
    *,
    result: DeliberationResult,
    participants: list[str],
    entities: list[Any],
    documents: list[str],
    interventions: list[str],
    workbench_session: WorkbenchSession | None = None,
) -> list[BeliefState]:
    if workbench_session and workbench_session.profiles:
        states = [_profile_belief_state(profile, result) for profile in workbench_session.profiles]
        if states:
            return states
    seeds: list[str] = list(participants)
    if not seeds:
        for index, entity in enumerate(entities[:8], start=1):
            if isinstance(entity, dict):
                seeds.append(str(entity.get("name") or entity.get("segment") or f"entity_{index}"))
            else:
                seeds.append(str(entity))
    if not seeds:
        derived_count = max(2, min(6, result.population_size // 64 or 2))
        seeds = [f"segment_{index}" for index in range(1, derived_count + 1)]

    confidence_floor = max(0.25, min(0.95, result.confidence_level or 0.5))
    trust_floor = max(0.2, min(0.95, result.judge_scores.explainability or 0.5))
    memory_tokens = [item[:120] for item in [*documents[:3], *interventions[:3], result.summary[:120]] if item]
    states: list[BeliefState] = []
    for index, seed in enumerate(seeds, start=1):
        group_id = f"cluster_{((index - 1) % max(1, min(4, len(seeds)))) + 1}"
        stance = "support"
        if result.uncertainty_points and index == len(seeds):
            stance = "skeptical"
        elif result.mode == DeliberationMode.simulation and index % 3 == 0:
            stance = "wait_and_see"
        states.append(
            BeliefState(
                agent_id=seed.replace(" ", "_").lower(),
                stance=stance,
                confidence=max(0.0, min(1.0, confidence_floor - (0.04 * ((index - 1) % 3)))),
                trust=max(0.0, min(1.0, trust_floor - (0.03 * ((index - 1) % 2)))),
                memory_window=memory_tokens,
                group_id=group_id,
                metadata={
                    "mode": result.mode.value,
                    "engine": result.engine_used,
                    "source": "derived",
                },
            )
        )
    return states


def _profile_belief_state(profile, result: DeliberationResult) -> BeliefState:
    state = profile_to_belief_state(profile)
    if result.summary:
        state.add_memory(result.summary, max_items=12)
    if result.uncertainty_points:
        state.metadata["uncertainty_points"] = list(result.uncertainty_points[:3])
    state.metadata["engine"] = result.engine_used
    state.metadata["mode"] = result.mode.value
    return state


def _summarise_belief_groups(states: list[BeliefState]) -> list[BeliefGroupSummary]:
    groups: dict[str | None, list[BeliefState]] = {}
    for state in states:
        groups.setdefault(state.group_id, []).append(state)
    return [summarise_belief_group(group_states, group_id=group_id) for group_id, group_states in groups.items()]


def _estimate_probability(result: DeliberationResult) -> float | None:
    if result.mode == DeliberationMode.committee:
        return None
    if "engagement_index" in result.metrics:
        return max(0.0, min(1.0, result.metrics["engagement_index"]))
    return max(0.0, min(1.0, result.confidence_level))


def _confidence_band(confidence_level: float) -> list[float]:
    lower = max(0.0, confidence_level - 0.15)
    upper = min(1.0, confidence_level + 0.15)
    return [round(lower, 3), round(upper, 3)]


def _pick_recommendation(result: DeliberationResult) -> str | None:
    if result.next_actions:
        return result.next_actions[0]
    if result.recommendations:
        return str(result.recommendations[0])
    if result.final_strategy:
        return result.final_strategy
    return result.summary or None


def _build_ensemble_report(
    *,
    primary_engine: str,
    snapshots: list[DeliberationEngineSnapshot],
    metric_deltas: dict[str, float],
) -> DeliberationEnsembleReport | None:
    if len(snapshots) <= 1:
        return None
    notes: list[str] = []
    convergence_components: list[float] = []
    for delta in metric_deltas.values():
        convergence_components.append(max(0.0, 1.0 - min(1.0, abs(delta))))
    for snapshot in snapshots:
        notes.append(
            f"{snapshot.engine}: status={snapshot.status.value}, confidence={snapshot.confidence_level:.3f}, "
            f"scenarios={snapshot.scenarios_count}"
        )
    convergence_score = sum(convergence_components) / len(convergence_components) if convergence_components else 1.0
    return DeliberationEnsembleReport(
        primary_engine=primary_engine,
        compared_engines=[snapshot.engine for snapshot in snapshots],
        convergence_score=round(convergence_score, 6),
        metric_deltas=metric_deltas,
        notes=notes,
        engine_snapshots=snapshots,
    )


def _render_lines(values: list[Any]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {value}" for value in values[:8])


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_hash_value(value: Any) -> str:
    return _sha256_text(json.dumps(value, sort_keys=True, default=str))
