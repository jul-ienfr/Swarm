from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
import re
from pathlib import Path
from typing import Any
from uuid import uuid4
import unicodedata

from pydantic import BaseModel, Field

from openclaw_client import OpenClawClient
from runtime_pydanticai import (
    MeetingRoundSummary,
    MeetingSynthesisDraft,
    MeetingTurnDraft,
    PydanticAIStrategyMeetingRuntime,
    RuntimeBackend,
    RuntimeFallbackPolicy,
)
from .meeting_memory import MeetingEventLogger, MeetingMemory


DEFAULT_STRATEGY_MEETING_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "strategy_meetings"
)
MAX_STRATEGY_MEETING_PARTICIPANTS = 32
MAX_STRATEGY_MEETING_ROUNDS = 3
DEFAULT_STRATEGY_MEETING_CLUSTER_SIZE = 8
DEFAULT_FORCED_DISSENT_PER_CLUSTER = 1
ROUND_PHASE_INDEPENDENT = "independent"
ROUND_PHASE_CRITIQUE = "critique"
ROUND_PHASE_SYNTHESIS = "synthesis"
CRITIQUE_FOCI = (
    "hidden assumptions and evidence gaps",
    "execution bottlenecks and rollback readiness",
    "cost, latency, and operational load",
    "safety, compliance, and blast radius",
    "measurement gaps and decision thresholds",
)
_MEETING_POINT_TRIVIAL_PREFIXES = (
    "we should",
    "we need to",
    "need to",
    "should",
    "must",
    "please",
    "let's",
    "lets",
    "consider",
    "recommend",
    "recommend to",
    "ensure",
    "make sure to",
    "prioritize",
    "prioritise",
    "focus on",
)
_MEETING_POINT_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "the",
    "their",
    "this",
    "that",
    "to",
    "we",
    "with",
    "you",
    "your",
}
_ANALYTICAL_MEETING_TERMS = (
    "probability",
    "gain",
    "profit",
    "expected value",
    "edge",
    "confidence",
    "calibration",
    "arbitrage",
    "spread",
    "no-trade",
    "no trade",
    "compare",
    "comparison",
    "versus",
    "ranking",
    "baseline",
    "optimiz",
    "live durable",
)


@dataclass(frozen=True, slots=True)
class _MeetingRoleTemplate:
    key: str
    core_duty: str
    evidence_focus: tuple[str, ...]
    critique_focus: tuple[str, ...]
    synthesis_focus: tuple[str, ...]


_MEETING_ROLE_TEMPLATES: tuple[tuple[tuple[str, ...], _MeetingRoleTemplate], ...] = (
    (
        ("architect", "strategy"),
        _MeetingRoleTemplate(
            key="architect",
            core_duty="Own coherence, sequencing, and decision gates. Prefer crisp structure over narrative breadth.",
            evidence_focus=("decision gates", "dependencies", "rollback path"),
            critique_focus=("missing assumptions", "hidden coupling", "implicit gates"),
            synthesis_focus=("preferred path", "promotion gate", "rollback trigger"),
        ),
    ),
    (
        ("product", "business", "growth", "pm"),
        _MeetingRoleTemplate(
            key="product",
            core_duty="Own actionable tradeoffs, rollout pressure, and what makes the decision operationally useful.",
            evidence_focus=("user-facing impact", "sequencing", "ownership"),
            critique_focus=("unclear ownership", "hand-off gaps", "unrealistic sequencing"),
            synthesis_focus=("owners", "first ship unit", "operator hand-off"),
        ),
    ),
    (
        ("risk", "safety", "governance", "compliance", "resolution"),
        _MeetingRoleTemplate(
            key="risk",
            core_duty="Own kill criteria, failure containment, and unresolved safety constraints.",
            evidence_focus=("kill criteria", "blast radius", "policy blockers"),
            critique_focus=("unbounded downside", "missing safeguards", "policy gap"),
            synthesis_focus=("safe gate", "halt condition", "blocked path"),
        ),
    ),
    (
        ("market", "microstructure", "latency"),
        _MeetingRoleTemplate(
            key="market",
            core_duty="Own execution realism, freshness budgets, fill risk, and edge decay.",
            evidence_focus=("fill realism", "freshness budget", "venue behavior"),
            critique_focus=("stale data risk", "slippage", "edge decay"),
            synthesis_focus=("execution gate", "venue assumptions", "freshness limit"),
        ),
    ),
    (
        ("portfolio", "capital", "allocator", "treasury"),
        _MeetingRoleTemplate(
            key="capital",
            core_duty="Own sizing, capital lock, inventory exposure, and portfolio survivability.",
            evidence_focus=("capital lock", "inventory risk", "position survivability"),
            critique_focus=("over-sizing", "correlated loss", "capital starvation"),
            synthesis_focus=("size cap", "reservation rule", "portfolio guardrail"),
        ),
    ),
    (
        ("research", "prediction", "forecast"),
        _MeetingRoleTemplate(
            key="research",
            core_duty="Own evidence quality, calibration, and out-of-sample plausibility.",
            evidence_focus=("calibration", "sample quality", "base rates"),
            critique_focus=("overfitting", "weak evidence", "unsupported confidence"),
            synthesis_focus=("validation gate", "proof burden", "falsification test"),
        ),
    ),
    (
        ("ops", "orchestrator", "infra", "qa"),
        _MeetingRoleTemplate(
            key="ops",
            core_duty="Own observability, rollback readiness, and operator-facing clarity.",
            evidence_focus=("alerts", "runbooks", "rollback readiness"),
            critique_focus=("blind spots", "recovery gaps", "unclear runbooks"),
            synthesis_focus=("monitoring", "runbook owner", "rollback trigger"),
        ),
    ),
)


class StrategyMeetingStatus(str, Enum):
    completed = "completed"
    partial = "partial"
    failed = "failed"


class StrategyMeetingTurn(BaseModel):
    round_index: int
    phase: str = ROUND_PHASE_INDEPENDENT
    phase_role: str = "participant"
    speaker: str
    instruction: str
    content: str = ""
    success: bool = False
    error: str | None = None
    tokens_used: int = 0
    role: str = "participant"
    cluster_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyMeetingSynthesis(BaseModel):
    strategy: str
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class StrategyMeetingClusterSummary(BaseModel):
    cluster_index: int
    participants: list[str] = Field(default_factory=list)
    rounds_completed: int = 0
    round_phases: list[str] = Field(default_factory=list)
    round_durations_ms: list[float] = Field(default_factory=list)
    transcript: list[StrategyMeetingTurn] = Field(default_factory=list)
    summary: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    confidence_score: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyMeetingResult(BaseModel):
    meeting_id: str
    topic: str
    objective: str
    status: StrategyMeetingStatus
    requested_participants: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    requested_max_agents: int = 0
    max_participants: int = MAX_STRATEGY_MEETING_PARTICIPANTS
    requested_rounds: int = 0
    rounds_completed: int = 0
    round_phases: list[str] = Field(default_factory=list)
    round_durations_ms: list[float] = Field(default_factory=list)
    transcript: list[StrategyMeetingTurn] = Field(default_factory=list)
    summary: str = ""
    strategy: str = ""
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    hierarchical: bool = False
    routing_mode: str = "committee"
    cluster_size: int = 0
    cluster_summaries: list[StrategyMeetingClusterSummary] = Field(default_factory=list)
    forced_dissent_participants: list[str] = Field(default_factory=list)
    runtime_used: str | None = None
    fallback_used: bool = False
    quality_score: float = 0.0
    confidence_score: float = 0.0
    duration_ms: float = 0.0
    phase_counts: dict[str, int] = Field(default_factory=dict)
    role_counts: dict[str, int] = Field(default_factory=dict)
    dissent_turn_count: int = 0
    degraded_runtime_used: str | None = None
    decision_degraded: bool = False
    persisted_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class _MeetingRuntimeProtocol:
    runtime_used: RuntimeBackend = RuntimeBackend.pydanticai
    last_fallback_used: bool = False
    last_fallback_mode: str | None = None
    last_error: str | None = None
    last_error_category: str | None = None
    last_error_retryable: bool | None = None
    last_attempt_count: int = 0
    last_retry_count: int = 0
    last_retry_reasons: list[str] = []
    last_backoff_schedule: list[dict[str, Any]] = []
    last_backoff_total_seconds: float = 0.0
    last_retry_budget_exhausted: bool = False
    last_immediate_fallback: bool = False

    def generate_turn(
        self,
        *,
        participant: str,
        round_index: int,
        phase: str,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
        critique_focus: str | None = None,
    ) -> MeetingTurnDraft: ...

    def summarize_round(
        self,
        *,
        topic: str,
        objective: str,
        round_index: int,
        phase: str,
        turns: list[MeetingTurnDraft],
        prior_summary: str,
    ) -> MeetingRoundSummary: ...

    def synthesize_meeting(
        self,
        *,
        topic: str,
        objective: str,
        participants: list[str],
        phase: str,
        turns: list[MeetingTurnDraft],
        summary: str,
    ) -> MeetingSynthesisDraft: ...


class StrategyMeetingCoordinator:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        client: OpenClawClient | Any | None = None,
        output_dir: str | Path | None = None,
        max_participants: int = MAX_STRATEGY_MEETING_PARTICIPANTS,
        cluster_size: int = DEFAULT_STRATEGY_MEETING_CLUSTER_SIZE,
        forced_dissent_per_cluster: int = DEFAULT_FORCED_DISSENT_PER_CLUSTER,
        parallelism_limit: int = 8,
        runtime: str = "pydanticai",
        allow_fallback: bool = True,
        model_name: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.client = client
        self.output_dir = Path(output_dir or DEFAULT_STRATEGY_MEETING_OUTPUT_DIR)
        self.max_participants = max(2, min(max_participants, MAX_STRATEGY_MEETING_PARTICIPANTS))
        self.cluster_size = max(2, min(cluster_size, self.max_participants))
        self.forced_dissent_per_cluster = max(0, forced_dissent_per_cluster)
        self.parallelism_limit = max(1, parallelism_limit)
        self.runtime_name = runtime
        self.allow_fallback = allow_fallback
        self.model_name = model_name
        self._runtime = self._build_runtime()

    def run_meeting(
        self,
        *,
        topic: str,
        objective: str | None = None,
        participants: list[str] | None = None,
        max_agents: int = 6,
        rounds: int = 2,
        persist: bool = True,
    ) -> StrategyMeetingResult:
        meeting_id = f"meeting_{uuid4().hex[:10]}"
        event_logger = MeetingEventLogger(output_dir=self.output_dir, meeting_id=meeting_id)
        event_logger.log(
            action="meeting_start",
            stage="pending",
            details={
                "topic": topic,
                "objective": objective or f"Define the best strategy for: {topic}",
                "requested_participants": participants or [],
                "max_agents": max_agents,
                "rounds": rounds,
                "runtime": self.runtime_name,
                "allow_fallback": self.allow_fallback,
            },
        )
        resolved_participants = self._resolve_participants(participants, max_agents=max_agents)
        effective_rounds = max(1, min(rounds, MAX_STRATEGY_MEETING_ROUNDS))
        meeting_objective = objective or f"Define the best strategy for: {topic}"
        hierarchical = self._should_use_hierarchical(resolved_participants)

        if hierarchical:
            return self._run_hierarchical_meeting(
                event_logger=event_logger,
                meeting_id=meeting_id,
                topic=topic,
                objective=meeting_objective,
                requested_participants=participants or [],
                resolved_participants=resolved_participants,
                requested_max_agents=max_agents,
                requested_rounds=rounds,
                effective_rounds=effective_rounds,
                persist=persist,
            )

        return self._run_flat_meeting(
            event_logger=event_logger,
            meeting_id=meeting_id,
            topic=topic,
            objective=meeting_objective,
            requested_participants=participants or [],
            resolved_participants=resolved_participants,
            requested_max_agents=max_agents,
            requested_rounds=rounds,
            effective_rounds=effective_rounds,
            persist=persist,
        )

    def _run_flat_meeting(
        self,
        *,
        event_logger: MeetingEventLogger,
        meeting_id: str,
        topic: str,
        objective: str,
        requested_participants: list[str],
        resolved_participants: list[str],
        requested_max_agents: int,
        requested_rounds: int,
        effective_rounds: int,
        persist: bool,
    ) -> StrategyMeetingResult:
        started_at = time.perf_counter()
        meeting_memory = MeetingMemory(topic=topic, objective=objective)
        transcript: list[StrategyMeetingTurn] = []
        round_summary = ""
        round_phases: list[str] = []
        round_durations_ms: list[float] = []
        round_runtime_diagnostics: list[dict[str, Any]] = []
        round_reports: list[dict[str, Any]] = []

        for round_index in range(1, effective_rounds + 1):
            phase = _round_phase(round_index, effective_rounds)
            round_started = time.perf_counter()
            round_memory_context = _build_round_context(
                base_context=meeting_memory.build_global_context(current_round=round_index),
                round_reports=round_reports,
                current_round=round_index,
            )
            event_logger.log_preflight_context(
                current_round=round_index,
                context=round_memory_context,
                snapshot={
                    "meeting_memory": meeting_memory.snapshot(),
                    "round_reports": round_reports[-2:],
                },
            )
            turns = self._run_round(
                round_index=round_index,
                phase=phase,
                topic=topic,
                objective=objective,
                participants=resolved_participants,
                prior_summary=round_memory_context,
                meeting_memory=meeting_memory,
                event_logger=event_logger,
                round_reports=round_reports,
            )
            transcript.extend(turns)
            turn_drafts = [self._turn_to_draft(turn) for turn in turns]
            summary_draft = self._runtime.summarize_round(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                turns=turn_drafts,
                prior_summary=round_summary,
            )
            summary_draft = _enrich_round_summary(
                summary_draft,
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                prior_summary=round_summary,
                turns=turn_drafts,
            )
            round_runtime_diagnostics.append(
                _runtime_diagnostics(self._runtime, stage=f"round_{round_index}_summary")
            )
            round_summary = summary_draft.summary
            round_report = build_round_report(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                prior_summary=round_memory_context,
                current_points=_collect_meeting_points(turn_drafts),
                summary_text=round_summary,
            )
            round_reports.append(round_report)
            meeting_memory.record_round(
                round_index=round_index,
                phase=phase,
                turns=turns,
                round_summary=round_summary,
            )
            event_logger.log_round_summary(round_index=round_index, phase=phase, summary=round_summary)
            round_snapshot = meeting_memory.build_round_snapshot(round_index=round_index)
            round_snapshot["round_report"] = round_report
            event_logger.log_round_snapshot(round_snapshot=round_snapshot)
            round_phases.append(phase)
            round_durations_ms.append(round((time.perf_counter() - round_started) * 1000.0, 3))

        synthesis = self._runtime.synthesize_meeting(
            topic=topic,
            objective=objective,
            participants=resolved_participants,
            phase=_round_phase(effective_rounds, effective_rounds),
            turns=[self._turn_to_draft(turn) for turn in transcript],
            summary=round_summary,
        )
        final_runtime_diagnostics = _runtime_diagnostics(self._runtime, stage="final_synthesis")
        synthesis = _enrich_meeting_synthesis(
            synthesis,
            topic=topic,
            objective=objective,
            summary=round_summary,
            turns=[self._turn_to_draft(turn) for turn in transcript],
            runtime_resilience=None,
        )
        event_logger.log_final_synthesis(
            strategy=synthesis.strategy,
            consensus_points=list(synthesis.consensus_points),
            dissent_points=list(synthesis.dissent_points),
            next_actions=list(synthesis.next_actions),
        )
        success_count = len([turn for turn in transcript if turn.success])
        result = self._assemble_result(
            meeting_id=meeting_id,
            topic=topic,
            objective=objective,
            requested_participants=requested_participants,
            resolved_participants=resolved_participants,
            requested_max_agents=requested_max_agents,
            requested_rounds=requested_rounds,
            effective_rounds=effective_rounds,
            transcript=transcript,
            synthesis=synthesis,
            cluster_summaries=[],
            forced_dissent_participants=[],
            hierarchical=False,
            persist=persist,
            cluster_size=0,
            routing_mode="committee",
            round_summary=round_summary,
            success_count=success_count,
            total_units=len(transcript),
            round_phases=round_phases,
            round_durations_ms=round_durations_ms,
            duration_ms=round((time.perf_counter() - started_at) * 1000.0, 3),
            round_runtime_diagnostics=round_runtime_diagnostics,
            final_runtime_diagnostics=final_runtime_diagnostics,
        )
        result.metadata["meeting_memory"] = meeting_memory.snapshot()
        result.metadata["agent_log_path"] = str(event_logger.log_path)
        result.metadata["round_reports"] = round_reports
        meeting_report = build_meeting_report(
            topic=topic,
            objective=objective,
            round_reports=round_reports,
            strategy=result.strategy,
            consensus_points=result.consensus_points,
            dissent_points=result.dissent_points,
            next_actions=result.next_actions,
            runtime_resilience=result.metadata.get("runtime_resilience"),
            analytical_run=bool(result.metadata.get("analytical_run")),
            analytical_rerun_required=bool(result.metadata.get("analytical_rerun_required")),
        )
        result.metadata["meeting_report"] = meeting_report
        event_logger.log_meeting_report(report=meeting_report)
        if persist and result.persisted_path:
            Path(result.persisted_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def _run_hierarchical_meeting(
        self,
        *,
        event_logger: MeetingEventLogger,
        meeting_id: str,
        topic: str,
        objective: str,
        requested_participants: list[str],
        resolved_participants: list[str],
        requested_max_agents: int,
        requested_rounds: int,
        effective_rounds: int,
        persist: bool,
    ) -> StrategyMeetingResult:
        started_at = time.perf_counter()
        top_level_memory = MeetingMemory(topic=topic, objective=objective)
        clusters = self._chunk_participants(resolved_participants, self.cluster_size)
        cluster_summaries: list[StrategyMeetingClusterSummary] = []
        top_level_transcript: list[StrategyMeetingTurn] = []
        forced_dissent_participants: list[str] = []
        cluster_headlines: list[MeetingTurnDraft] = []
        cluster_synthesis_summary = ""
        round_phases: list[str] = []
        round_durations_ms: list[float] = []
        round_reports: list[dict[str, Any]] = []

        for cluster_index, cluster_participants in enumerate(clusters):
            cluster_started = time.perf_counter()
            cluster_summary = self._run_cluster_meeting(
                event_logger=event_logger,
                cluster_index=cluster_index,
                topic=topic,
                objective=objective,
                participants=cluster_participants,
                effective_rounds=effective_rounds,
            )
            cluster_summaries.append(cluster_summary)
            round_phases.append("cluster_aggregation")
            round_durations_ms.append(cluster_summary.duration_ms or round((time.perf_counter() - cluster_started) * 1000.0, 3))
            forced_dissent_participants.extend(
                [item for item in cluster_summary.metadata.get("forced_dissent_participants", []) if isinstance(item, str)]
            )
            cluster_headlines.append(self._cluster_summary_to_draft(cluster_summary))
            top_level_transcript.append(
                StrategyMeetingTurn(
                    round_index=cluster_summary.rounds_completed or 1,
                    phase="cluster_aggregation",
                    phase_role="synthesizer",
                    speaker=f"cluster_{cluster_index}",
                    instruction=f"Summarize cluster {cluster_index} findings for the final committee.",
                    content=cluster_summary.summary,
                    success=True,
                    tokens_used=0,
                    role="cluster_summary",
                    cluster_index=cluster_index,
                    metadata={
                        "cluster_index": cluster_index,
                        "participants": cluster_participants,
                        "quality_score": cluster_summary.quality_score,
                        "confidence_score": cluster_summary.confidence_score,
                    },
                )
            )

        synthesis_started = time.perf_counter()
        final_synthesis = self._runtime.synthesize_meeting(
            topic=topic,
            objective=objective,
            participants=[f"cluster_{summary.cluster_index}" for summary in cluster_summaries],
            phase="final_decision",
            turns=cluster_headlines,
            summary="\n".join(summary.summary for summary in cluster_summaries if summary.summary).strip(),
        )
        synthesis = _enrich_meeting_synthesis(
            final_synthesis,
            topic=topic,
            objective=objective,
            summary="\n".join(summary.summary for summary in cluster_summaries if summary.summary).strip(),
            turns=cluster_headlines,
            runtime_resilience=None,
        )
        cluster_synthesis_summary = _format_memory_snapshot(
            topic=topic,
            objective=objective,
            phase="final_decision",
            round_index=effective_rounds + 1,
            prior_summary="\n".join(summary.summary for summary in cluster_summaries if summary.summary).strip(),
            turn_points=_collect_meeting_points(cluster_headlines),
        )
        final_round_report = build_round_report(
            topic=topic,
            objective=objective,
            round_index=effective_rounds + 1,
            phase="final_decision",
            prior_summary="\n".join(summary.summary for summary in cluster_summaries if summary.summary).strip(),
            current_points=_collect_meeting_points(cluster_headlines),
            summary_text=cluster_synthesis_summary,
        )
        round_reports.append(final_round_report)
        top_level_memory.record_round(
            round_index=effective_rounds + 1,
            phase="final_decision",
            turns=top_level_transcript,
            round_summary=cluster_synthesis_summary,
        )
        event_logger.log_final_synthesis(
            strategy=synthesis.strategy,
            consensus_points=list(synthesis.consensus_points),
            dissent_points=list(synthesis.dissent_points),
            next_actions=list(synthesis.next_actions),
        )
        final_round_snapshot = top_level_memory.build_round_snapshot(round_index=effective_rounds + 1)
        final_round_snapshot["round_report"] = final_round_report
        event_logger.log_round_snapshot(round_snapshot=final_round_snapshot)
        final_runtime_diagnostics = _runtime_diagnostics(self._runtime, stage="final_decision")
        round_phases.append("final_decision")
        round_durations_ms.append(round((time.perf_counter() - synthesis_started) * 1000.0, 3))
        top_level_transcript.append(
            StrategyMeetingTurn(
                round_index=effective_rounds + 1,
                phase="final_decision",
                phase_role="chair",
                speaker="chair",
                instruction="Produce the final synthesis across cluster summaries.",
                content=synthesis.strategy,
                success=True,
                tokens_used=0,
                role="final_synthesis",
                metadata={
                    "cluster_count": len(cluster_summaries),
                },
            )
        )
        transcript_success_count = len([turn for turn in top_level_transcript if turn.success])
        cluster_success_count = len([summary for summary in cluster_summaries if summary.quality_score > 0.0])
        success_count = transcript_success_count + cluster_success_count
        result = self._assemble_result(
            meeting_id=meeting_id,
            topic=topic,
            objective=objective,
            requested_participants=requested_participants,
            resolved_participants=resolved_participants,
            requested_max_agents=requested_max_agents,
            requested_rounds=requested_rounds,
            effective_rounds=effective_rounds,
            transcript=top_level_transcript,
            synthesis=synthesis,
            cluster_summaries=cluster_summaries,
            forced_dissent_participants=list(dict.fromkeys(forced_dissent_participants)),
            hierarchical=True,
            persist=persist,
            cluster_size=self.cluster_size,
            routing_mode="hierarchical",
            round_summary=cluster_synthesis_summary,
            success_count=success_count,
            total_units=len(top_level_transcript) + len(cluster_summaries),
            round_phases=round_phases,
            round_durations_ms=round_durations_ms,
            duration_ms=round((time.perf_counter() - started_at) * 1000.0, 3),
            round_runtime_diagnostics=[],
            final_runtime_diagnostics=final_runtime_diagnostics,
        )
        result.metadata["meeting_memory"] = top_level_memory.snapshot()
        result.metadata["agent_log_path"] = str(event_logger.log_path)
        result.metadata["round_reports"] = round_reports
        meeting_report = build_meeting_report(
            topic=topic,
            objective=objective,
            round_reports=round_reports,
            strategy=result.strategy,
            consensus_points=result.consensus_points,
            dissent_points=result.dissent_points,
            next_actions=result.next_actions,
            runtime_resilience=result.metadata.get("runtime_resilience"),
            analytical_run=bool(result.metadata.get("analytical_run")),
            analytical_rerun_required=bool(result.metadata.get("analytical_rerun_required")),
        )
        result.metadata["meeting_report"] = meeting_report
        event_logger.log_meeting_report(report=meeting_report)
        if persist and result.persisted_path:
            Path(result.persisted_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def load_meeting(self, meeting_id: str) -> StrategyMeetingResult:
        artifact_path = self.output_dir / f"{meeting_id}.json"
        return StrategyMeetingResult.model_validate_json(artifact_path.read_text(encoding="utf-8"))

    def _assemble_result(
        self,
        *,
        meeting_id: str,
        topic: str,
        objective: str,
        requested_participants: list[str],
        resolved_participants: list[str],
        requested_max_agents: int,
        requested_rounds: int,
        effective_rounds: int,
        transcript: list[StrategyMeetingTurn],
        synthesis: MeetingSynthesisDraft,
        cluster_summaries: list[StrategyMeetingClusterSummary],
        forced_dissent_participants: list[str],
        hierarchical: bool,
        persist: bool,
        cluster_size: int,
        routing_mode: str,
        round_summary: str,
        success_count: int,
        total_units: int,
        round_phases: list[str],
        round_durations_ms: list[float],
        duration_ms: float,
        round_runtime_diagnostics: list[dict[str, Any]],
        final_runtime_diagnostics: dict[str, Any],
    ) -> StrategyMeetingResult:
        status = self._derive_status(transcript, cluster_summaries=cluster_summaries)
        phase_counts = dict(Counter(turn.phase for turn in transcript if getattr(turn, "phase", "")))
        role_counts = dict(Counter(turn.phase_role for turn in transcript if getattr(turn, "phase_role", "")))
        dissent_turn_count = len([turn for turn in transcript if turn.phase_role in {"critic", "red_team"}])
        turn_runtime_diagnostics = [
            dict(turn.metadata.get("runtime_diagnostics", {}))
            for turn in transcript
            if isinstance(turn.metadata, dict) and isinstance(turn.metadata.get("runtime_diagnostics"), dict)
        ]
        turn_retry_count = sum(int(item.get("runtime_retry_count", 0) or 0) for item in turn_runtime_diagnostics)
        turn_fallback_count = sum(1 for item in turn_runtime_diagnostics if bool(item.get("fallback_used")))
        cluster_runtime_diagnostics = _cluster_runtime_diagnostics(cluster_summaries)
        cluster_fallback_count = sum(1 for item in cluster_runtime_diagnostics if bool(item.get("fallback_used")))
        cluster_error_categories = list(
            dict.fromkeys(
                str(item.get("runtime_error_category")).strip()
                for item in cluster_runtime_diagnostics
                if str(item.get("runtime_error_category") or "").strip()
            )
        )
        runtime_used = self._runtime.runtime_used.value
        meeting_fallback_used = bool(
            turn_fallback_count
            or cluster_fallback_count
            or any(bool(item.get("fallback_used")) for item in round_runtime_diagnostics)
            or bool(final_runtime_diagnostics.get("fallback_used"))
            or bool(getattr(self._runtime, "last_fallback_used", False))
        )
        runtime_resilience = _runtime_resilience_summary(
            status=status,
            metadata={
                "runtime_requested": self.runtime_name,
                "runtime_used": runtime_used,
                "runtime_fallback_mode": getattr(self._runtime, "last_fallback_mode", None),
            },
            turn_runtime_diagnostics=turn_runtime_diagnostics,
            round_runtime_diagnostics=round_runtime_diagnostics,
            final_runtime_diagnostics=final_runtime_diagnostics,
        )
        degraded_runtime_used = _meeting_degraded_runtime_used(
            runtime_requested=self.runtime_name,
            runtime_used=runtime_used,
            runtime_resilience=runtime_resilience,
            fallback_used=meeting_fallback_used,
        )
        decision_degraded = bool(
            runtime_resilience.get("degraded_mode")
            or meeting_fallback_used
            or degraded_runtime_used
            or cluster_fallback_count
        )
        analytical_run = _is_analytical_meeting(topic=topic, objective=objective)
        analytical_rerun_required = bool(analytical_run and decision_degraded)
        turn_error_categories = list(
            dict.fromkeys(
                str(item.get("runtime_error_category")).strip()
                for item in turn_runtime_diagnostics
                if str(item.get("runtime_error_category") or "").strip()
            )
        )
        quality_score, confidence_score = self._score_meeting(
            success_count=success_count,
            total_units=total_units,
            dissent_count=dissent_turn_count,
            cluster_count=len(cluster_summaries),
            round_phases=round_phases,
            requested_rounds=requested_rounds,
            rounds_completed=effective_rounds,
        )
        round_timeline = _build_round_timeline(
            transcript=transcript,
            round_phases=round_phases,
            round_durations_ms=round_durations_ms,
            round_runtime_diagnostics=round_runtime_diagnostics,
            final_runtime_diagnostics=final_runtime_diagnostics,
        )
        phase_metadata = {
            "phase_sequence": list(round_phases),
            "distinct_phases": list(dict.fromkeys(round_phases)),
            "phase_count": len(round_phases),
            "timeline_event_count": len(round_timeline),
        }
        structured_round_summary = round_summary.strip() or _format_memory_snapshot(
            topic=topic,
            objective=objective,
            phase=round_phases[-1] if round_phases else ROUND_PHASE_INDEPENDENT,
            round_index=effective_rounds,
            prior_summary="",
            turn_points=_collect_meeting_points([self._turn_to_draft(turn) for turn in transcript]),
        )
        consensus_points = _dedupe_meeting_points(synthesis.consensus_points)
        dissent_points = _dedupe_meeting_points(synthesis.dissent_points)
        next_actions = _dedupe_meeting_points(synthesis.next_actions)
        if analytical_rerun_required:
            next_actions = _dedupe_meeting_points(
                [
                    *next_actions,
                    "Re-run this analysis on the structured runtime before trusting quantitative conclusions.",
                    "Keep the current output advisory-only until the structured synthesis completes without degradation.",
                ]
            )
        structured_strategy = _format_final_strategy(
            topic=topic,
            objective=objective,
            raw_strategy=synthesis.strategy,
            consensus_points=consensus_points,
            dissent_points=dissent_points,
            next_actions=next_actions,
            runtime_resilience=runtime_resilience,
            round_summary=structured_round_summary,
            analytical_run=analytical_run,
            analytical_rerun_required=analytical_rerun_required,
        )
        result = StrategyMeetingResult(
            meeting_id=meeting_id,
            topic=topic,
            objective=objective,
            status=status,
            requested_participants=requested_participants,
            participants=resolved_participants,
            requested_max_agents=requested_max_agents,
            max_participants=self.max_participants,
            requested_rounds=requested_rounds,
            rounds_completed=effective_rounds,
            round_phases=round_phases,
            round_durations_ms=round_durations_ms,
            transcript=transcript,
            summary=structured_round_summary,
            strategy=structured_strategy,
            consensus_points=consensus_points,
            dissent_points=dissent_points,
            next_actions=next_actions,
            hierarchical=hierarchical,
            routing_mode=routing_mode,
            cluster_size=cluster_size,
            cluster_summaries=cluster_summaries,
            forced_dissent_participants=forced_dissent_participants,
            runtime_used=runtime_used,
            fallback_used=meeting_fallback_used,
            quality_score=quality_score,
            confidence_score=confidence_score,
            duration_ms=duration_ms,
            phase_counts=phase_counts,
            role_counts=role_counts,
            dissent_turn_count=dissent_turn_count,
            degraded_runtime_used=degraded_runtime_used,
            decision_degraded=decision_degraded,
            metadata={
                "cap_applied": requested_max_agents > self.max_participants or len(resolved_participants) == self.max_participants,
                "parallelism_limit": min(self.parallelism_limit, len(resolved_participants)),
                "success_count": success_count,
                "failure_count": total_units - success_count,
                "runtime_used": runtime_used,
                "fallback_used": meeting_fallback_used,
                "degraded_runtime_used": degraded_runtime_used,
                "meeting_degraded_runtime_used": degraded_runtime_used,
                "decision_degraded": decision_degraded,
                "analytical_run": analytical_run,
                "analytical_rerun_required": analytical_rerun_required,
                "runtime_error": self._runtime.last_error,
                "runtime_error_category": self._runtime.last_error_category,
                "runtime_attempt_count": self._runtime.last_attempt_count,
                "runtime_retry_count": self._runtime.last_retry_count,
                "runtime_retry_reasons": list(getattr(self._runtime, "last_retry_reasons", []) or []),
                "hierarchical": hierarchical,
                "routing_mode": routing_mode,
                "cluster_size": cluster_size,
                "cluster_count": len(cluster_summaries),
                "cluster_summaries": [summary.model_dump(mode="json") for summary in cluster_summaries],
                "forced_dissent_participants": forced_dissent_participants,
                "cluster_runtime_diagnostic_count": len(cluster_runtime_diagnostics),
                "cluster_fallback_count": cluster_fallback_count,
                "cluster_error_categories": cluster_error_categories,
                "quality_score": quality_score,
                "confidence_score": confidence_score,
                "round_summary": structured_round_summary,
                "round_summary_raw": round_summary,
                "strategy_raw": synthesis.strategy,
                "total_units": total_units,
                "round_phases": round_phases,
                "round_durations_ms": round_durations_ms,
                "duration_ms": duration_ms,
                "phase_counts": phase_counts,
                "role_counts": role_counts,
                "phase_metadata": phase_metadata,
                "round_timeline": round_timeline,
                "dissent_turn_count": dissent_turn_count,
                "turn_runtime_diagnostics": turn_runtime_diagnostics,
                "turn_retry_count": turn_retry_count,
                "turn_fallback_count": turn_fallback_count,
                "turn_error_categories": turn_error_categories,
                "round_runtime_diagnostics": round_runtime_diagnostics,
                "final_runtime_diagnostics": final_runtime_diagnostics,
                "comparability": _build_strategy_meeting_comparability_metadata(
                    runtime=self._runtime,
                    runtime_requested=self.runtime_name,
                    fallback_model_name=self.model_name,
                    fallback_used=meeting_fallback_used,
                    runtime_resilience=runtime_resilience,
                    degraded_runtime_used=degraded_runtime_used,
                    meeting_degraded_runtime_used=degraded_runtime_used,
                    decision_degraded=decision_degraded,
                    cluster_runtime_diagnostic_count=len(cluster_runtime_diagnostics),
                    cluster_fallback_count=cluster_fallback_count,
                    cluster_error_categories=cluster_error_categories,
                    hierarchical=hierarchical,
                    routing_mode=routing_mode,
                    topic=topic,
                    objective=objective,
                    requested_participants=requested_participants,
                    resolved_participants=resolved_participants,
                    requested_max_agents=requested_max_agents,
                    requested_rounds=requested_rounds,
                    effective_rounds=effective_rounds,
                    cluster_size=cluster_size,
                    cluster_count=len(cluster_summaries),
                    phase_count=len(round_phases),
                    analytical_run=analytical_run,
                    analytical_rerun_required=analytical_rerun_required,
                ),
            },
        )
        result.metadata["runtime_resilience"] = runtime_resilience
        if persist:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = self.output_dir / f"{meeting_id}.json"
            artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            result.persisted_path = str(artifact_path)
        return result

    def _run_cluster_meeting(
        self,
        *,
        event_logger: MeetingEventLogger,
        cluster_index: int,
        topic: str,
        objective: str,
        participants: list[str],
        effective_rounds: int,
    ) -> StrategyMeetingClusterSummary:
        started_at = time.perf_counter()
        meeting_memory = MeetingMemory(topic=topic, objective=objective)
        transcript: list[StrategyMeetingTurn] = []
        round_summary = ""
        forced_dissent_participants: list[str] = []
        round_phases: list[str] = []
        round_durations_ms: list[float] = []
        round_runtime_diagnostics: list[dict[str, Any]] = []
        round_reports: list[dict[str, Any]] = []

        for round_index in range(1, effective_rounds + 1):
            phase = _round_phase(round_index, effective_rounds)
            round_started = time.perf_counter()
            round_memory_context = _build_round_context(
                base_context=meeting_memory.build_global_context(current_round=round_index),
                round_reports=round_reports,
                current_round=round_index,
            )
            event_logger.log_preflight_context(
                current_round=round_index,
                context=round_memory_context,
                snapshot={
                    "cluster_index": cluster_index,
                    "meeting_memory": meeting_memory.snapshot(),
                    "round_reports": round_reports[-2:],
                },
            )
            turns = self._run_round(
                round_index=round_index,
                phase=phase,
                topic=topic,
                objective=objective,
                participants=participants,
                prior_summary=round_memory_context,
                meeting_memory=meeting_memory,
                event_logger=event_logger,
                round_reports=round_reports,
            )
            dissent_turns = []
            if phase == ROUND_PHASE_CRITIQUE and self.forced_dissent_per_cluster > 0:
                dissent_turns = self._run_forced_dissent(
                    cluster_index=cluster_index,
                    round_index=round_index,
                    topic=topic,
                    objective=objective,
                    participants=participants,
                    prior_summary=round_summary,
                )
                forced_dissent_participants.extend(turn.speaker for turn in dissent_turns)
            all_turns = turns + dissent_turns
            transcript.extend(all_turns)
            turn_drafts = [self._turn_to_draft(turn) for turn in all_turns]
            summary_draft = self._runtime.summarize_round(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                turns=turn_drafts,
                prior_summary=round_summary,
            )
            summary_draft = _enrich_round_summary(
                summary_draft,
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                prior_summary=round_summary,
                turns=turn_drafts,
            )
            round_runtime_diagnostics.append(
                _runtime_diagnostics(self._runtime, stage=f"cluster_{cluster_index}_round_{round_index}_summary")
            )
            round_summary = summary_draft.summary
            round_report = build_round_report(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                prior_summary=round_memory_context,
                current_points=_collect_meeting_points(turn_drafts),
                summary_text=round_summary,
            )
            round_reports.append(round_report)
            meeting_memory.record_round(
                round_index=round_index,
                phase=phase,
                turns=all_turns,
                round_summary=round_summary,
            )
            event_logger.log_round_summary(round_index=round_index, phase=phase, summary=round_summary)
            round_snapshot = meeting_memory.build_round_snapshot(round_index=round_index)
            round_snapshot["cluster_index"] = cluster_index
            round_snapshot["round_report"] = round_report
            event_logger.log_round_snapshot(round_snapshot=round_snapshot)
            round_phases.append(phase)
            round_durations_ms.append(round((time.perf_counter() - round_started) * 1000.0, 3))

        synthesis = self._runtime.synthesize_meeting(
            topic=topic,
            objective=objective,
            participants=participants,
            phase=_round_phase(effective_rounds, effective_rounds),
            turns=[self._turn_to_draft(turn) for turn in transcript],
            summary=round_summary,
        )
        synthesis = _enrich_meeting_synthesis(
            synthesis,
            topic=topic,
            objective=objective,
            summary=round_summary,
            turns=[self._turn_to_draft(turn) for turn in transcript],
            runtime_resilience=None,
        )
        final_runtime_diagnostics = _runtime_diagnostics(
            self._runtime,
            stage=f"cluster_{cluster_index}_final_synthesis",
        )
        success_count = len([turn for turn in transcript if turn.success])
        quality_score, confidence_score = self._score_meeting(
            success_count=success_count,
            total_units=len(transcript),
            dissent_count=len([turn for turn in transcript if turn.phase_role in {"critic", "red_team"}]),
            cluster_count=1,
            round_phases=round_phases,
            requested_rounds=effective_rounds,
            rounds_completed=effective_rounds,
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
        return StrategyMeetingClusterSummary(
            cluster_index=cluster_index,
            participants=participants,
            rounds_completed=effective_rounds,
            round_phases=round_phases,
            round_durations_ms=round_durations_ms,
            transcript=transcript,
            summary=round_summary or synthesis.strategy,
            consensus_points=_dedupe_meeting_points(synthesis.consensus_points),
            dissent_points=_dedupe_meeting_points(synthesis.dissent_points),
            next_actions=_dedupe_meeting_points(synthesis.next_actions),
            quality_score=quality_score,
            confidence_score=confidence_score,
            duration_ms=duration_ms,
            metadata={
                "success_count": success_count,
                "failure_count": len(transcript) - success_count,
                "round_summary": round_summary,
                "forced_dissent_participants": forced_dissent_participants,
                "round_phases": round_phases,
                "round_durations_ms": round_durations_ms,
                "duration_ms": duration_ms,
                "phase_counts": dict(Counter(turn.phase for turn in transcript if getattr(turn, "phase", ""))),
                "role_counts": dict(Counter(turn.phase_role for turn in transcript if getattr(turn, "phase_role", ""))),
                "dissent_turn_count": len([turn for turn in transcript if turn.phase_role in {"critic", "red_team"}]),
                "round_runtime_diagnostics": round_runtime_diagnostics,
                "final_runtime_diagnostics": final_runtime_diagnostics,
                "round_reports": round_reports,
                "meeting_memory": meeting_memory.snapshot(),
                "agent_log_path": str(event_logger.log_path),
            },
        )

    def _run_forced_dissent(
        self,
        *,
        cluster_index: int,
        round_index: int,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
    ) -> list[StrategyMeetingTurn]:
        dissent_turns: list[StrategyMeetingTurn] = []
        for dissent_index in range(self.forced_dissent_per_cluster):
            speaker = f"red_team_{cluster_index}_{dissent_index}"
            critique_focus = _critique_focus_for_speaker(
                participant=speaker,
                participants=participants,
                round_index=round_index,
                dissent_index=dissent_index,
                cluster_index=cluster_index,
            )
            dissent_objective = (
                f"Red-team the current strategy for cluster {cluster_index}. "
                f"Identify failure modes, hidden assumptions, and rollback criteria. "
                f"Critique focus: {critique_focus}. Base objective: {objective}"
            )
            draft = self._runtime.generate_turn(
                participant=speaker,
                round_index=round_index,
                phase=ROUND_PHASE_CRITIQUE,
                topic=topic,
                objective=dissent_objective,
                participants=participants,
                prior_summary=prior_summary,
                critique_focus=critique_focus,
            )
            draft = _enrich_turn_draft(
                draft,
                participant=speaker,
                round_index=round_index,
                phase=ROUND_PHASE_CRITIQUE,
                topic=topic,
                objective=dissent_objective,
                prior_summary=prior_summary,
                critique_focus=critique_focus,
            )
            dissent_turns.append(
                StrategyMeetingTurn(
                    round_index=round_index,
                    phase=ROUND_PHASE_CRITIQUE,
                    phase_role="red_team",
                    speaker=speaker,
                    instruction=_build_red_team_instruction(
                        participant=speaker,
                        round_index=round_index,
                        topic=topic,
                        objective=dissent_objective,
                        participants=participants,
                        prior_summary=prior_summary,
                        cluster_index=cluster_index,
                        critique_focus=critique_focus,
                    ),
                    content=draft.to_content(),
                    success=True,
                    error=None,
                    tokens_used=0,
                    role="red_team",
                    cluster_index=cluster_index,
                    metadata={
                        "runtime_used": self._runtime.runtime_used.value,
                        "fallback_used": self._runtime.last_fallback_used,
                        "runtime_diagnostics": _runtime_diagnostics(
                            self._runtime,
                            stage=f"red_team_cluster_{cluster_index}",
                        ),
                        "draft": draft.model_dump(mode="json"),
                        "phase": ROUND_PHASE_CRITIQUE,
                        "phase_role": "red_team",
                        "critique_focus": critique_focus,
                        "timeline_anchor": f"round_{round_index}:{ROUND_PHASE_CRITIQUE}:{speaker}",
                        "simulation_trace_style": "report_agent",
                    },
                )
            )
        return dissent_turns

    def _should_use_hierarchical(self, participants: list[str]) -> bool:
        return len(participants) > self.cluster_size

    @staticmethod
    def _chunk_participants(participants: list[str], chunk_size: int) -> list[list[str]]:
        return [participants[index : index + chunk_size] for index in range(0, len(participants), chunk_size)]

    @staticmethod
    def _cluster_summary_to_draft(summary: StrategyMeetingClusterSummary) -> MeetingTurnDraft:
        return MeetingTurnDraft(
            thesis=summary.summary or f"Cluster {summary.cluster_index} summary",
            recommended_actions=summary.next_actions[:3],
            key_risks=summary.dissent_points[:3],
            disagreements=summary.dissent_points[:3],
            closing_note=(
                f"Cluster {summary.cluster_index} quality={summary.quality_score:.2f}, "
                f"confidence={summary.confidence_score:.2f}"
            ),
        )

    @staticmethod
    def _derive_status(
        transcript: list[StrategyMeetingTurn],
        *,
        cluster_summaries: list[StrategyMeetingClusterSummary],
    ) -> StrategyMeetingStatus:
        if not transcript and not cluster_summaries:
            return StrategyMeetingStatus.failed
        transcript_success = all(turn.success for turn in transcript) if transcript else True
        cluster_success = all(summary.quality_score > 0.0 for summary in cluster_summaries) if cluster_summaries else True
        any_success = any(turn.success for turn in transcript) or any(
            summary.quality_score > 0.0 for summary in cluster_summaries
        )
        if not any_success:
            return StrategyMeetingStatus.failed
        if transcript_success and cluster_success:
            return StrategyMeetingStatus.completed
        if any_success:
            return StrategyMeetingStatus.partial
        return StrategyMeetingStatus.failed

    @staticmethod
    def _score_meeting(
        *,
        success_count: int,
        total_units: int,
        dissent_count: int,
        cluster_count: int,
        round_phases: list[str],
        requested_rounds: int,
        rounds_completed: int,
    ) -> tuple[float, float]:
        if total_units <= 0:
            return 0.0, 0.0
        success_ratio = success_count / total_units
        dissent_signal = min(0.03, (dissent_count / max(1, total_units)) * 0.03)
        cluster_bonus = min(0.05, cluster_count * 0.02)
        phase_progress = min(1.0, rounds_completed / max(1, requested_rounds))
        phase_diversity = min(1.0, len(set(round_phases)) / 3.0) if round_phases else 0.0
        final_phase = round_phases[-1] if round_phases else ""
        decision_readiness = _phase_readiness_score(final_phase)
        structure_score = 0.18 + 0.34 * success_ratio + 0.12 * phase_progress + 0.10 * phase_diversity
        usefulness_multiplier = 0.55 + 0.45 * decision_readiness
        quality_score = max(
            0.0,
            min(
                1.0,
                (structure_score * usefulness_multiplier)
                + (0.10 * decision_readiness)
                + dissent_signal
                + cluster_bonus,
            ),
        )
        confidence_score = max(
            0.0,
            min(
                1.0,
                (
                    (0.16 + 0.40 * success_ratio + 0.08 * phase_progress + 0.06 * phase_diversity)
                    * (0.60 + 0.40 * decision_readiness)
                )
                + (0.06 * decision_readiness)
                + min(0.02, dissent_signal / 2)
                + min(0.03, cluster_bonus / 2),
            ),
        )
        return quality_score, confidence_score

    def _build_runtime(self):
        if self.runtime_name == "legacy":
            return PydanticAIStrategyMeetingRuntime(
                config_path=self.config_path,
                fallback_policy=RuntimeFallbackPolicy("always"),
                model_name=self.model_name,
                legacy_client=self.client,
            )
        fallback_policy = RuntimeFallbackPolicy("on_error" if self.allow_fallback else "never")
        return PydanticAIStrategyMeetingRuntime(
            config_path=self.config_path,
            fallback_policy=fallback_policy,
            model_name=self.model_name,
            legacy_client=self.client,
        )

    def _resolve_participants(self, participants: list[str] | None, *, max_agents: int) -> list[str]:
        requested = [participant.strip() for participant in (participants or []) if participant and participant.strip()]
        if requested:
            deduped = list(dict.fromkeys(requested))
        else:
            deduped = self._discover_available_agents()
        if not deduped:
            deduped = ["architect"]
        effective_cap = max(2, min(max_agents, self.max_participants))
        return deduped[:effective_cap]

    @staticmethod
    def _discover_available_agents() -> list[str]:
        agents_dir = Path("/home/jul/.openclaw/agents")
        if not agents_dir.exists():
            return []
        return sorted(
            entry.name
            for entry in agents_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    def _run_round(
        self,
        *,
        round_index: int,
        phase: str,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
        meeting_memory: MeetingMemory,
        event_logger: MeetingEventLogger,
        round_reports: list[dict[str, Any]],
    ) -> list[StrategyMeetingTurn]:
        turns: list[StrategyMeetingTurn] = []
        max_workers = min(self.parallelism_limit, len(participants))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._ask_participant,
                    participant,
                    round_index=round_index,
                    phase=phase,
                    topic=topic,
                    objective=objective,
                    participants=participants,
                    prior_summary=prior_summary,
                    meeting_memory=meeting_memory,
                    event_logger=event_logger,
                    round_reports=round_reports,
                ): participant
                for participant in participants
            }
            for future in as_completed(futures):
                turns.append(future.result())
        turns.sort(key=lambda turn: participants.index(turn.speaker))
        return turns

    def _ask_participant(
        self,
        participant: str,
        *,
        round_index: int,
        phase: str,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
        meeting_memory: MeetingMemory,
        event_logger: MeetingEventLogger,
        round_reports: list[dict[str, Any]],
    ) -> StrategyMeetingTurn:
        critique_focus = (
            _critique_focus_for_speaker(
                participant=participant,
                participants=participants,
                round_index=round_index,
            )
            if phase == ROUND_PHASE_CRITIQUE
            else None
        )
        participant_memory = meeting_memory.build_participant_context(
            participant=participant,
            phase=phase,
            current_round=round_index,
        )
        participant_memory = _build_round_context(
            base_context=participant_memory,
            round_reports=round_reports,
            current_round=round_index,
            participant=participant,
        )
        instruction = _build_participant_instruction(
            participant=participant,
            round_index=round_index,
            phase=phase,
            topic=topic,
            objective=objective,
            participants=participants,
            prior_summary=participant_memory,
            critique_focus=critique_focus,
        )
        draft = self._runtime.generate_turn(
            participant=participant,
            round_index=round_index,
            phase=phase,
            topic=topic,
            objective=objective,
            participants=participants,
            prior_summary=participant_memory,
            critique_focus=critique_focus,
        )
        draft = _enrich_turn_draft(
            draft,
            participant=participant,
            round_index=round_index,
            phase=phase,
            topic=topic,
            objective=objective,
            prior_summary=participant_memory,
            critique_focus=critique_focus,
        )
        turn = StrategyMeetingTurn(
            round_index=round_index,
            phase=phase,
            phase_role="critic" if phase == ROUND_PHASE_CRITIQUE else "participant",
            speaker=participant,
            instruction=instruction,
            content=draft.to_content(),
            success=True,
            error=None,
            tokens_used=0,
            metadata={
                "runtime_used": self._runtime.runtime_used.value,
                "fallback_used": self._runtime.last_fallback_used,
                "runtime_diagnostics": _runtime_diagnostics(self._runtime, stage=f"turn_{phase}"),
                "draft": draft.model_dump(mode="json"),
                "phase": phase,
                "phase_role": "critic" if phase == ROUND_PHASE_CRITIQUE else "participant",
                "critique_focus": critique_focus,
                "participant_memory": participant_memory,
                "timeline_anchor": f"round_{round_index}:{phase}:{participant}",
                "simulation_trace_style": "report_agent",
            },
        )
        event_logger.log_turn(
            participant=participant,
            round_index=round_index,
            phase=phase,
            content=turn.content,
            metadata=dict(turn.metadata),
        )
        return turn

    @staticmethod
    def _turn_to_draft(turn: StrategyMeetingTurn) -> MeetingTurnDraft:
        metadata_draft = turn.metadata.get("draft") if isinstance(turn.metadata, dict) else None
        if isinstance(metadata_draft, dict):
            try:
                return MeetingTurnDraft.model_validate(metadata_draft)
            except Exception:
                pass
        parsed = _parse_turn_content(turn.content)
        if parsed.thesis:
            return parsed
        content = turn.content.strip()
        if content.startswith("Thesis: "):
            content = content.removeprefix("Thesis: ").strip()
        return MeetingTurnDraft(thesis=content or turn.instruction, closing_note=None)


def _build_participant_instruction(
    *,
    participant: str,
    round_index: int,
    phase: str,
    topic: str,
    objective: str,
    participants: list[str],
    prior_summary: str,
    critique_focus: str | None = None,
) -> str:
    summary_block = prior_summary or "No prior summary yet. Give an independent first-pass strategy."
    phase_block = _phase_guidance(phase)
    critique_focus_block = f"Critique focus: {critique_focus}\n" if critique_focus and phase == ROUND_PHASE_CRITIQUE else ""
    role_grounding_block = _participant_role_grounding(
        participant=participant,
        topic=topic,
        objective=objective,
        phase=phase,
        critique_focus=critique_focus,
    )
    memory_discipline_block = _memory_discipline_guidance(prior_summary)
    return (
        f"You are participating in a structured strategy meeting as agent '{participant}'.\n"
        f"Topic: {topic}\n"
        f"Objective: {objective}\n"
        f"Participants: {', '.join(participants)}\n"
        f"Round: {round_index}\n"
        f"Phase: {phase}\n"
        f"Role grounding: {role_grounding_block}\n"
        f"{critique_focus_block}"
        "Current meeting memory:\n"
        f"{summary_block}\n\n"
        f"Memory discipline: {memory_discipline_block}\n"
        f"{phase_block}\n"
        "Respond in four sections and keep them concrete:\n"
        "1. Thesis\n"
        "2. Recommended actions\n"
        "3. Key risks\n"
        "4. Disagreements or tradeoffs\n"
        "Do not write a generic paragraph; anchor the answer in the topic, the objective, and the prior memory.\n"
        "Do not silently drop earlier named risks or disagreements."
    )


def _build_red_team_instruction(
    *,
    participant: str,
    round_index: int,
    topic: str,
    objective: str,
    participants: list[str],
    prior_summary: str,
    cluster_index: int,
    critique_focus: str | None = None,
) -> str:
    summary_block = prior_summary or "No prior summary yet."
    critique_focus_block = f"Critique focus: {critique_focus}\n" if critique_focus else ""
    role_grounding_block = _participant_role_grounding(
        participant=participant,
        topic=topic,
        objective=objective,
        phase=ROUND_PHASE_CRITIQUE,
        critique_focus=critique_focus,
    )
    memory_discipline_block = _memory_discipline_guidance(prior_summary)
    return (
        f"You are the red-team challenger '{participant}' for cluster {cluster_index}.\n"
        f"Topic: {topic}\n"
        f"Objective: {objective}\n"
        f"Participants: {', '.join(participants)}\n"
        f"Round: {round_index}\n"
        f"Phase: critique\n"
        f"Role grounding: {role_grounding_block}\n"
        f"{critique_focus_block}"
        "Current meeting memory:\n"
        f"{summary_block}\n\n"
        f"Memory discipline: {memory_discipline_block}\n"
        "Your job is to attack the current strategy.\n"
        "Respond with:\n"
        "1. Failure modes\n"
        "2. Hidden assumptions\n"
        "3. Rollback criteria\n"
        "4. What would prove this strategy wrong\n"
        "Be concise but adversarial, and tie each objection back to the requested critique focus."
    )


def _participant_role_grounding(
    *,
    participant: str,
    topic: str,
    objective: str,
    phase: str,
    critique_focus: str | None = None,
) -> str:
    template = _meeting_role_template_for_participant(
        participant=participant,
        phase=phase,
        critique_focus=critique_focus,
    )
    phase_key = phase.strip().lower()
    if phase_key == ROUND_PHASE_CRITIQUE:
        phase_focus = template.critique_focus
    elif phase_key == ROUND_PHASE_SYNTHESIS:
        phase_focus = template.synthesis_focus
    else:
        phase_focus = template.evidence_focus
    return (
        f"{template.core_duty} "
        f"Preserve evidence around {', '.join(template.evidence_focus[:3])}. "
        f"In this phase, emphasize {', '.join(phase_focus[:3])}. "
        f"Keep the response anchored to {topic} and {objective}."
    )


def _meeting_role_template_for_participant(
    *,
    participant: str,
    phase: str,
    critique_focus: str | None = None,
) -> _MeetingRoleTemplate:
    role = participant.strip().lower()
    if "red" in role:
        return _MeetingRoleTemplate(
            key="red_team",
            core_duty=(
                "Attack weak assumptions and keep the falsification test visible. "
                f"Focus on {critique_focus or 'the sharpest unresolved risk'}."
            ),
            evidence_focus=("counterexamples", "failure proofs", "rollback triggers"),
            critique_focus=("falsification test", "hidden dependency", "what breaks first"),
            synthesis_focus=("residual risk", "required guardrail", "do-not-ignore objection"),
        )
    for match_tokens, template in _MEETING_ROLE_TEMPLATES:
        if any(token in role for token in match_tokens):
            return template
    phase_key = phase.strip().lower()
    if phase_key == ROUND_PHASE_CRITIQUE:
        phase_focus = ("weak assumption", "failure mode", "missing gate")
    elif phase_key == ROUND_PHASE_SYNTHESIS:
        phase_focus = ("recommended path", "tradeoff", "next gate")
    else:
        phase_focus = ("initial thesis", "main risk", "next test")
    return _MeetingRoleTemplate(
        key="generalist",
        core_duty="Stay grounded in the topic and objective. Make the decision more explicit, testable, and reversible.",
        evidence_focus=phase_focus,
        critique_focus=phase_focus,
        synthesis_focus=phase_focus,
    )


def _memory_discipline_guidance(prior_summary: str) -> str:
    points = _extract_memory_points(prior_summary)
    lines: list[str] = []
    if points["options"]:
        lines.append(f"keep the strongest options visible: {'; '.join(points['options'][:2])}")
    if points["risks"]:
        lines.append(f"carry forward the sharpest risks: {'; '.join(points['risks'][:2])}")
    if points["disagreements"]:
        lines.append(f"do not erase these disagreements: {'; '.join(points['disagreements'][:2])}")
    if not lines:
        return "Establish named options, risks, and disagreements so the next round can reuse them explicitly."
    return " | ".join(lines)


def _build_round_context(
    *,
    base_context: str,
    round_reports: list[dict[str, Any]],
    current_round: int,
    participant: str | None = None,
) -> str:
    if not round_reports:
        return base_context
    relevant_reports = [report for report in round_reports if int(report.get("round_index", 0) or 0) < current_round][-2:]
    if not relevant_reports:
        return base_context
    report_lines = ["[Structured round timeline]"]
    for report in relevant_reports:
        headline = str(report.get("headline") or "no headline").strip()
        decision_gate = str(report.get("decision_gate") or "no explicit gate").strip()
        report_lines.append(
            f"- Round {report.get('round_index', '?')} ({report.get('phase', 'unknown')}): {headline}"
        )
        report_lines.append(f"  Gate: {decision_gate}")
        persistent = report.get("persistent")
        if isinstance(persistent, dict):
            if persistent.get("options"):
                report_lines.append(f"  Options: {' | '.join(list(persistent['options'])[:2])}")
            if persistent.get("risks"):
                report_lines.append(f"  Risks: {' | '.join(list(persistent['risks'])[:2])}")
            if persistent.get("disagreements"):
                report_lines.append(f"  Disagreements: {' | '.join(list(persistent['disagreements'])[:2])}")
    if participant:
        report_lines.append(f"[Participant trace]\n- Agent: {participant}")
    return "\n\n".join(section for section in (base_context, "\n".join(report_lines)) if section.strip())


def _round_phase(round_index: int, total_rounds: int) -> str:
    if total_rounds <= 1 or round_index <= 1:
        return ROUND_PHASE_INDEPENDENT
    if round_index >= total_rounds:
        return ROUND_PHASE_SYNTHESIS
    return ROUND_PHASE_CRITIQUE


def _phase_guidance(phase: str) -> str:
    phase_key = phase.strip().lower()
    if phase_key == ROUND_PHASE_CRITIQUE:
        return (
            "Phase guidance: challenge the current line. Name at least one concrete disagreement, failure mode, "
            "or missing assumption, and keep the objection visible in the next summary."
        )
    if phase_key == ROUND_PHASE_SYNTHESIS:
        return (
            "Phase guidance: converge to a decision. State the tradeoffs, the recommended path, the rollout gates, "
            "and the strongest unresolved dissent that must stay on the watchlist."
        )
    return (
        "Phase guidance: give an independent first pass. Focus on your own judgment, evidence, initial risks, "
        "and the two assumptions you most want to test next."
    )


def _critique_focus_for_speaker(
    *,
    participant: str,
    participants: list[str],
    round_index: int,
    dissent_index: int = 0,
    cluster_index: int = 0,
) -> str:
    if not participants:
        return CRITIQUE_FOCI[0]
    try:
        participant_index = participants.index(participant)
    except ValueError:
        participant_index = len(participant)
    lens_index = (participant_index + round_index + dissent_index + cluster_index) % len(CRITIQUE_FOCI)
    return CRITIQUE_FOCI[lens_index]


def _parse_turn_content(content: str) -> MeetingTurnDraft:
    text = content.strip()
    if not text:
        return MeetingTurnDraft(thesis="")

    section_order = ("thesis", "recommended_actions", "key_risks", "disagreements", "closing_note")
    sections: dict[str, list[str]] = {name: [] for name in section_order}
    current_section: str | None = None
    saw_section = False

    def append_line(section: str, line: str) -> None:
        if line:
            sections[section].append(line)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        matched_section = None
        for candidate in section_order:
            label = candidate.replace("_", " ")
            if lower.startswith(f"{label}:"):
                matched_section = candidate
                remainder = line[len(label) + 1 :].strip()
                saw_section = True
                current_section = matched_section
                if remainder:
                    append_line(matched_section, remainder)
                break
        if matched_section is not None:
            continue

        if line.startswith(("- ", "* ", "• ")):
            target = current_section or "thesis"
            append_line(target, line[2:].strip())
            continue

        target = current_section or "thesis"
        append_line(target, line)

    thesis = " ".join(sections["thesis"]).strip()
    recommended_actions = sections["recommended_actions"]
    key_risks = sections["key_risks"]
    disagreements = sections["disagreements"]
    closing_note = " ".join(sections["closing_note"]).strip() or None

    if not saw_section and not any([recommended_actions, key_risks, disagreements, closing_note]):
        return MeetingTurnDraft(thesis=text, closing_note=None)

    return MeetingTurnDraft(
        thesis=thesis or text,
        recommended_actions=recommended_actions,
        key_risks=key_risks,
        disagreements=disagreements,
        closing_note=closing_note,
    )


def _runtime_diagnostics(runtime: _MeetingRuntimeProtocol, *, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "runtime_used": runtime.runtime_used.value,
        "fallback_used": bool(getattr(runtime, "last_fallback_used", False)),
        "runtime_fallback_mode": getattr(runtime, "last_fallback_mode", None),
        "runtime_error": getattr(runtime, "last_error", None),
        "runtime_error_category": getattr(runtime, "last_error_category", None),
        "runtime_error_retryable": getattr(runtime, "last_error_retryable", None),
        "runtime_attempt_count": int(getattr(runtime, "last_attempt_count", 0) or 0),
        "runtime_retry_count": int(getattr(runtime, "last_retry_count", 0) or 0),
        "runtime_retry_reasons": list(getattr(runtime, "last_retry_reasons", []) or []),
        "runtime_backoff_schedule": list(getattr(runtime, "last_backoff_schedule", []) or []),
        "runtime_backoff_total_seconds": float(getattr(runtime, "last_backoff_total_seconds", 0.0) or 0.0),
        "runtime_retry_budget_exhausted": bool(getattr(runtime, "last_retry_budget_exhausted", False)),
        "runtime_immediate_fallback": bool(getattr(runtime, "last_immediate_fallback", False)),
    }


def _runtime_resilience_summary(
    *,
    status: StrategyMeetingStatus,
    metadata: dict[str, Any],
    turn_runtime_diagnostics: list[dict[str, Any]],
    round_runtime_diagnostics: list[dict[str, Any]],
    final_runtime_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    stage_groups: list[tuple[str, list[dict[str, Any]]]] = [
        ("turn", turn_runtime_diagnostics),
        ("round", round_runtime_diagnostics),
        ("final", [final_runtime_diagnostics] if final_runtime_diagnostics else []),
    ]
    stage_counts = {stage: len(diagnostics) for stage, diagnostics in stage_groups}
    stages_present = [stage for stage, diagnostics in stage_groups if diagnostics]
    selected_stage, selected_diagnostics = next(
        ((stage, diagnostics) for stage, diagnostics in stage_groups if diagnostics),
        ("none", []),
    )
    selected_diagnostic_count = len(selected_diagnostics)

    runtime_attempt_count = sum(_coerce_runtime_int(diag.get("runtime_attempt_count")) for diag in selected_diagnostics)
    runtime_retry_count = sum(_coerce_runtime_int(diag.get("runtime_retry_count")) for diag in selected_diagnostics)
    fallback_count = sum(1 for diag in selected_diagnostics if bool(diag.get("fallback_used")))
    runtime_error_count = sum(1 for diag in selected_diagnostics if _has_text(diag.get("runtime_error")))
    backoff_total_seconds = round(
        sum(float(diag.get("runtime_backoff_total_seconds", 0.0) or 0.0) for diag in selected_diagnostics),
        3,
    )
    backoff_event_count = sum(len(list(diag.get("runtime_backoff_schedule") or [])) for diag in selected_diagnostics)
    retry_reasons = _collect_unique_text_values(
        reason
        for diag in selected_diagnostics
        for reason in (diag.get("runtime_retry_reasons") or [])
    )
    fallback_modes = _collect_unique_text_values(
        diag.get("runtime_fallback_mode")
        for diag in stage_groups_diagnostics(stage_groups)
    )
    error_categories = _collect_unique_text_values(
        diag.get("runtime_error_category")
        for diag in stage_groups_diagnostics(stage_groups)
    )
    retry_budget_exhausted = any(bool(diag.get("runtime_retry_budget_exhausted")) for diag in selected_diagnostics)
    immediate_fallback = any(bool(diag.get("runtime_immediate_fallback")) for diag in selected_diagnostics)
    fallback_mode = _normalize_optional_text(metadata.get("runtime_fallback_mode"))
    runtime_requested = _normalize_optional_text(metadata.get("runtime_requested"))
    runtime_used = _normalize_optional_text(metadata.get("runtime_used"))
    degraded_runtime_used = None
    if runtime_requested != RuntimeBackend.legacy.value and (
        fallback_count > 0
        or runtime_error_count > 0
        or retry_budget_exhausted
        or immediate_fallback
    ):
        degraded_runtime_used = RuntimeBackend.legacy.value
    runtime_match = bool(
        runtime_requested is None
        or runtime_used is None
        or runtime_requested == runtime_used
        or fallback_mode == "policy_always"
    )
    degraded_reasons: list[str] = []
    if status != StrategyMeetingStatus.completed:
        degraded_reasons.append(f"status:{status.value}")
    if fallback_count > 0:
        degraded_reasons.append("fallback_used")
    if runtime_error_count > 0:
        degraded_reasons.append("runtime_error")
    if error_categories:
        degraded_reasons.append("runtime_error_category")
    if not runtime_match:
        degraded_reasons.append("runtime_mismatch")
    if retry_budget_exhausted:
        degraded_reasons.append("retry_budget_exhausted")
    if immediate_fallback:
        degraded_reasons.append("immediate_fallback")

    resilience_status = "healthy"
    if degraded_reasons:
        resilience_status = "degraded"
    elif runtime_retry_count > 0 or backoff_total_seconds > 0:
        resilience_status = "guarded"

    resilience_penalty = 0.0
    resilience_penalty += min(0.2, round(runtime_retry_count / max(1, runtime_attempt_count), 3) * 0.2)
    resilience_penalty += min(0.35, round(fallback_count / max(1, selected_diagnostic_count), 3) * 0.35)
    resilience_penalty += min(0.15, runtime_error_count * 0.05)
    resilience_penalty += 0.1 if not runtime_match else 0.0
    resilience_penalty += 0.05 if status != StrategyMeetingStatus.completed else 0.0
    resilience_score = round(max(0.0, 1.0 - resilience_penalty), 3)

    summary_parts = [resilience_status]
    if runtime_retry_count:
        summary_parts.append(f"retries={runtime_retry_count}")
    if fallback_count:
        summary_parts.append(f"fallbacks={fallback_count}")
    if backoff_total_seconds:
        summary_parts.append(f"backoff={backoff_total_seconds:.3f}s")
    if error_categories:
        summary_parts.append(f"errors={','.join(error_categories[:2])}")

    return {
        "status": resilience_status,
        "score": resilience_score,
        "summary": " | ".join(summary_parts),
        "meeting_status": status.value,
        "runtime_requested": runtime_requested,
        "runtime_used": runtime_used,
        "runtime_match": runtime_match,
        "degraded_runtime_used": degraded_runtime_used,
        "degraded_mode": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "stage_count": len(stages_present),
        "stages_present": stages_present,
        "stage_counts": stage_counts,
        "source_stage": selected_stage,
        "diagnostic_count": selected_diagnostic_count,
        "attempt_count": runtime_attempt_count,
        "retry_count": runtime_retry_count,
        "retry_rate": round(runtime_retry_count / max(1, runtime_attempt_count), 3),
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / max(1, selected_diagnostic_count), 3),
        "fallback_modes": fallback_modes,
        "backoff_event_count": backoff_event_count,
        "backoff_total_seconds": backoff_total_seconds,
        "retry_budget_exhausted": retry_budget_exhausted,
        "immediate_fallback": immediate_fallback,
        "runtime_error_count": runtime_error_count,
        "error_categories": error_categories,
        "error_category_count": len(error_categories),
        "retry_reasons": retry_reasons,
        "retry_reason_count": len(retry_reasons),
    }


def _cluster_runtime_diagnostics(cluster_summaries: list[StrategyMeetingClusterSummary]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for summary in cluster_summaries:
        for turn in summary.transcript:
            if isinstance(turn.metadata, dict) and isinstance(turn.metadata.get("runtime_diagnostics"), dict):
                diagnostics.append(dict(turn.metadata["runtime_diagnostics"]))
        if isinstance(summary.metadata, dict):
            for key in ("round_runtime_diagnostics", "final_runtime_diagnostics"):
                payload = summary.metadata.get(key)
                if isinstance(payload, dict):
                    diagnostics.append(dict(payload))
                elif isinstance(payload, list):
                    diagnostics.extend(dict(item) for item in payload if isinstance(item, dict))
    return diagnostics


def _meeting_degraded_runtime_used(
    *,
    runtime_requested: str,
    runtime_used: str | None,
    runtime_resilience: dict[str, Any] | None,
    fallback_used: bool,
) -> str | None:
    requested = _normalize_optional_text(runtime_requested)
    if requested == RuntimeBackend.legacy.value:
        return None
    resilience = runtime_resilience or {}
    if not (
        fallback_used
        or bool(resilience.get("fallback_count"))
        or bool(resilience.get("runtime_error_count"))
        or bool(resilience.get("retry_budget_exhausted"))
        or bool(resilience.get("immediate_fallback"))
    ):
        return None
    return RuntimeBackend.legacy.value if runtime_used != RuntimeBackend.legacy.value else RuntimeBackend.legacy.value


def _build_round_timeline(
    *,
    transcript: list[StrategyMeetingTurn],
    round_phases: list[str],
    round_durations_ms: list[float],
    round_runtime_diagnostics: list[dict[str, Any]],
    final_runtime_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for round_index, phase in enumerate(round_phases, start=1):
        matching_turns = [turn for turn in transcript if turn.round_index == round_index and turn.phase == phase]
        runtime_diag = round_runtime_diagnostics[round_index - 1] if round_index - 1 < len(round_runtime_diagnostics) else {}
        timeline.append(
            {
                "round_index": round_index,
                "phase": phase,
                "duration_ms": round_durations_ms[round_index - 1] if round_index - 1 < len(round_durations_ms) else 0.0,
                "turn_count": len(matching_turns),
                "participants": [turn.speaker for turn in matching_turns],
                "phase_roles": list(dict.fromkeys(turn.phase_role for turn in matching_turns)),
                "fallback_used": bool(runtime_diag.get("fallback_used")),
                "runtime_retry_count": int(runtime_diag.get("runtime_retry_count", 0) or 0),
                "runtime_error_category": runtime_diag.get("runtime_error_category"),
                "report_style": "round_summary",
            }
        )
    if final_runtime_diagnostics:
        timeline.append(
            {
                "round_index": len(round_phases) + 1,
                "phase": "final_synthesis",
                "duration_ms": 0.0,
                "turn_count": len([turn for turn in transcript if turn.role in {"final_synthesis", "cluster_summary"}]),
                "participants": [turn.speaker for turn in transcript if turn.role in {"final_synthesis", "cluster_summary"}],
                "phase_roles": list(
                    dict.fromkeys(turn.phase_role for turn in transcript if turn.role in {"final_synthesis", "cluster_summary"})
                ),
                "fallback_used": bool(final_runtime_diagnostics.get("fallback_used")),
                "runtime_retry_count": int(final_runtime_diagnostics.get("runtime_retry_count", 0) or 0),
                "runtime_error_category": final_runtime_diagnostics.get("runtime_error_category"),
                "report_style": "final_synthesis",
            }
        )
    return timeline


def _coerce_runtime_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_strategy_meeting_comparability_metadata(
    *,
    runtime: Any,
    runtime_requested: str,
    fallback_model_name: str | None,
    fallback_used: bool,
    runtime_resilience: dict[str, Any] | None,
    degraded_runtime_used: str | None,
    meeting_degraded_runtime_used: str | None,
    decision_degraded: bool,
    cluster_runtime_diagnostic_count: int,
    cluster_fallback_count: int,
    cluster_error_categories: list[str],
    hierarchical: bool,
    routing_mode: str,
    topic: str,
    objective: str,
    requested_participants: list[str],
    resolved_participants: list[str],
    requested_max_agents: int,
    requested_rounds: int,
    effective_rounds: int,
    cluster_size: int,
    cluster_count: int,
    phase_count: int,
    analytical_run: bool,
    analytical_rerun_required: bool,
) -> dict[str, Any]:
    runtime_requested_text = _normalize_optional_text(runtime_requested)
    runtime_used_text = _normalize_optional_text(getattr(runtime.runtime_used, "value", runtime.runtime_used))
    runtime_config = getattr(runtime, "_config", None)
    model_name = _normalize_optional_text(getattr(runtime_config, "model_name", None)) or _normalize_optional_text(
        fallback_model_name
    )
    provider_base_url = _normalize_optional_text(getattr(runtime_config, "base_url", None))
    normalized_requested_participants = [_normalize_comparability_text(participant) for participant in requested_participants]
    normalized_resolved_participants = [_normalize_comparability_text(participant) for participant in resolved_participants]
    normalized_topic = _normalize_comparability_text(topic)
    normalized_objective = _normalize_comparability_text(objective)

    return {
        "runtime_requested": runtime_requested_text,
        "runtime_used": runtime_used_text,
        "runtime_match": bool(
            runtime_requested_text is None
            or runtime_used_text is None
            or runtime_requested_text == runtime_used_text
        ),
        "fallback_used": bool(fallback_used),
        "degraded_runtime_used": degraded_runtime_used,
        "meeting_degraded_runtime_used": meeting_degraded_runtime_used,
        "decision_degraded": bool(decision_degraded),
        "runtime_resilience": runtime_resilience,
        "runtime_resilience_status": runtime_resilience.get("status") if runtime_resilience else None,
        "runtime_resilience_score": runtime_resilience.get("score") if runtime_resilience else None,
        "runtime_resilience_degraded_mode": runtime_resilience.get("degraded_mode") if runtime_resilience else None,
        "cluster_runtime_diagnostic_count": int(cluster_runtime_diagnostic_count),
        "cluster_fallback_count": int(cluster_fallback_count),
        "cluster_error_categories": list(cluster_error_categories),
        "model_name": model_name,
        "provider_base_url": provider_base_url,
        "routing_mode": routing_mode,
        "hierarchical": hierarchical,
        "participant_count": len(resolved_participants),
        "cluster_count": cluster_count,
        "phase_count": phase_count,
        "analytical_run": bool(analytical_run),
        "analytical_rerun_required": bool(analytical_rerun_required),
        "requested_rounds": requested_rounds,
        "rounds_completed": effective_rounds,
        "requested_max_agents": requested_max_agents,
        "cluster_size": cluster_size,
        "topic_fingerprint": _sha256_text(normalized_topic),
        "objective_fingerprint": _sha256_text(normalized_objective),
        "participant_fingerprint": _sha256_json(normalized_resolved_participants),
        "input_fingerprint": _sha256_json(
            {
                "topic": normalized_topic,
                "objective": normalized_objective,
                "requested_participants": normalized_requested_participants,
                "resolved_participants": normalized_resolved_participants,
                "requested_max_agents": requested_max_agents,
                "requested_rounds": requested_rounds,
                "rounds_completed": effective_rounds,
                "cluster_size": cluster_size,
                "routing_mode": routing_mode,
                "hierarchical": hierarchical,
            }
        ),
        "execution_fingerprint": _sha256_json(
            {
                "runtime_requested": runtime_requested_text,
                "runtime_used": runtime_used_text,
                "model_name": model_name,
                "provider_base_url": provider_base_url,
                "routing_mode": routing_mode,
                "hierarchical": hierarchical,
                "participant_count": len(resolved_participants),
                "cluster_count": cluster_count,
                "phase_count": phase_count,
                "requested_rounds": requested_rounds,
                "rounds_completed": effective_rounds,
                "requested_max_agents": requested_max_agents,
                "cluster_size": cluster_size,
            }
        ),
    }


def _normalize_comparability_text(value: Any) -> str:
    text = _normalize_optional_text(value) or ""
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _sha256_json(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_text(value: Any) -> bool:
    return _normalize_optional_text(value) is not None


def _collect_unique_text_values(values: Any) -> list[str]:
    seen: set[str] = set()
    collected: list[str] = []
    for value in values:
        text = _normalize_optional_text(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        collected.append(text)
    return collected


def stage_groups_diagnostics(stage_groups: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for _, group in stage_groups:
        diagnostics.extend(group)
    return diagnostics


def _dedupe_meeting_points(items: list[str]) -> list[str]:
    seen_keys: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate:
            continue
        key = _normalize_meeting_point_key(candidate)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(candidate)
    return deduped


def _normalize_meeting_point_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    lowered = stripped.lower().replace("’", "'").strip()
    lowered = re.sub(r"^[\s\-\*\u2022\d\.\)\(\[\]{}:]+", "", lowered)
    lowered = re.sub(r"[^a-z0-9\s']+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    for prefix in _MEETING_POINT_TRIVIAL_PREFIXES:
        if lowered.startswith(f"{prefix} "):
            lowered = lowered[len(prefix) :].strip()
            break
    tokens = [token for token in lowered.split() if token not in _MEETING_POINT_STOPWORDS]
    return " ".join(tokens) if tokens else lowered


def _phase_readiness_score(final_phase: str) -> float:
    if final_phase == ROUND_PHASE_SYNTHESIS:
        return 1.0
    if final_phase == ROUND_PHASE_CRITIQUE:
        return 0.6
    if final_phase == ROUND_PHASE_INDEPENDENT:
        return 0.25
    return 0.4


def _build_round_context(
    *,
    base_context: str,
    round_reports: list[dict[str, Any]],
    current_round: int,
    participant: str | None = None,
) -> str:
    sections = [base_context.strip() or "No meeting context yet."]
    if round_reports:
        sections.append("[Round report carry-forward]")
        for report in round_reports[-2:]:
            round_index = report.get("round_index")
            phase = _normalize_optional_text(report.get("phase")) or "unknown"
            summary = _normalize_optional_text(report.get("summary")) or _normalize_optional_text(report.get("summary_text"))
            sections.append(
                f"- Round {round_index} ({phase}): {summary or 'no summary'}"
            )
            persistent = report.get("persistent")
            if isinstance(persistent, dict):
                options = [item for item in persistent.get("options", []) if isinstance(item, str)][:2]
                risks = [item for item in persistent.get("risks", []) if isinstance(item, str)][:2]
                disagreements = [item for item in persistent.get("disagreements", []) if isinstance(item, str)][:2]
                if options:
                    sections.append(f"  Options: {' | '.join(options)}")
                if risks:
                    sections.append(f"  Risks: {' | '.join(risks)}")
                if disagreements:
                    sections.append(f"  Disagreements: {' | '.join(disagreements)}")
    if participant:
        sections.append(f"[Participant anchor]\n- Keep agent '{participant}' coherent with its prior belief lens.")
    return "\n".join(section for section in sections if section).strip()


def _collect_meeting_points(turns: list[MeetingTurnDraft]) -> dict[str, list[str]]:
    options: list[str] = []
    risks: list[str] = []
    disagreements: list[str] = []
    for turn in turns:
        if turn.thesis:
            options.append(turn.thesis)
        options.extend(turn.recommended_actions)
        risks.extend(turn.key_risks)
        disagreements.extend(turn.disagreements)
    return {
        "options": _dedupe_meeting_points(options),
        "risks": _dedupe_meeting_points(risks),
        "disagreements": _dedupe_meeting_points(disagreements),
    }


def build_round_report(
    *,
    topic: str,
    objective: str,
    round_index: int,
    phase: str,
    prior_summary: str,
    current_points: dict[str, list[str]],
    summary_text: str,
) -> dict[str, Any]:
    prior_points = _extract_memory_points(prior_summary)
    persistent = {
        key: _dedupe_meeting_points([*current_points.get(key, []), *prior_points.get(key, [])])[:4]
        for key in ("options", "risks", "disagreements")
    }
    emerging = {
        key: [
            item
            for item in current_points.get(key, [])
            if _normalize_meeting_point_key(item) not in {_normalize_meeting_point_key(existing) for existing in prior_points.get(key, [])}
        ][:3]
        for key in ("options", "risks", "disagreements")
    }
    carry_forward = {key: prior_points.get(key, [])[:3] for key in ("options", "risks", "disagreements")}
    headline = " ".join((summary_text or "").split()).strip()
    if not headline:
        headline = " | ".join(persistent["options"][:2] or persistent["risks"][:2] or persistent["disagreements"][:2])
    headline = headline[:220] if len(headline) <= 220 else headline[:219].rstrip() + "…"
    if persistent["disagreements"]:
        decision_gate = "Keep the strongest disagreement visible before promotion."
    elif persistent["risks"]:
        decision_gate = "Do not promote until the sharpest risk has a measurable guardrail."
    else:
        decision_gate = "Preserve the current best option and define the next validation gate."
    return {
        "round_index": round_index,
        "phase": phase,
        "topic": topic,
        "objective": objective,
        "headline": headline or f"Round {round_index} produced no durable signal.",
        "decision_gate": decision_gate,
        "carry_forward": carry_forward,
        "emerging": emerging,
        "persistent": persistent,
    }


def _extract_memory_points(memory_snapshot: str) -> dict[str, list[str]]:
    sections = {
        "top options": "options",
        "key risks": "risks",
        "open disagreements": "disagreements",
    }
    extracted: dict[str, list[str]] = {"options": [], "risks": [], "disagreements": []}
    current: str | None = None
    for raw_line in (memory_snapshot or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower().removesuffix(":")
        if lower in sections:
            current = sections[lower]
            continue
        if current is None:
            continue
        if not line.startswith("- "):
            current = None
            continue
        candidate = line[2:].strip()
        if candidate and candidate != "none" and candidate != "none yet":
            extracted[current].append(candidate)
    return {key: _dedupe_meeting_points(value) for key, value in extracted.items()}


def _format_bullet_block(title: str, items: list[str], *, empty_value: str = "none") -> str:
    lines = [f"{title}:"]
    if not items:
        lines.append(f"- {empty_value}")
        return "\n".join(lines)
    lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def _format_memory_snapshot(
    *,
    topic: str,
    objective: str,
    phase: str,
    round_index: int,
    prior_summary: str,
    turn_points: dict[str, list[str]],
) -> str:
    memory_sections = [
        f"Round {round_index} memory",
        f"Topic: {topic}",
        f"Objective: {objective}",
        f"Phase: {phase}",
        _format_bullet_block("Top options", turn_points.get("options", [])[:3]),
        _format_bullet_block("Key risks", turn_points.get("risks", [])[:3]),
        _format_bullet_block("Open disagreements", turn_points.get("disagreements", [])[:3]),
        _format_bullet_block(
            "Carry-forward memory",
            _carry_forward_memory_lines(prior_summary),
            empty_value="none yet",
        ),
        "Decision gate:",
        f"- Keep the next round grounded in the strongest option, the hardest disagreement, and the next gate.",
    ]
    return "\n".join(memory_sections).strip()


def _carry_forward_memory_lines(prior_summary: str) -> list[str]:
    if not prior_summary.strip():
        return []
    points = _extract_memory_points(prior_summary)
    carry_forward: list[str] = []
    if points["options"]:
        carry_forward.append(f"Prior options: {'; '.join(points['options'][:2])}")
    if points["risks"]:
        carry_forward.append(f"Prior risks: {'; '.join(points['risks'][:2])}")
    if points["disagreements"]:
        carry_forward.append(f"Prior disagreements: {'; '.join(points['disagreements'][:2])}")
    if carry_forward:
        return carry_forward[:3]
    compact_summary = " ".join(prior_summary.strip().split())
    return [compact_summary[:220]]


def _format_final_strategy(
    *,
    topic: str,
    objective: str,
    raw_strategy: str,
    consensus_points: list[str],
    dissent_points: list[str],
    next_actions: list[str],
    runtime_resilience: dict[str, Any] | None,
    round_summary: str,
    analytical_run: bool,
    analytical_rerun_required: bool,
) -> str:
    decision_line = raw_strategy.strip() if raw_strategy.strip() else "Adopt a staged rollout with explicit gates."
    resilience_status = (runtime_resilience or {}).get("status", "n/a")
    resilience_cause = ", ".join((runtime_resilience or {}).get("degraded_reasons", [])[:3]) or "none"
    lines = [
        "Decision brief",
        f"- Recommendation: {decision_line}",
        f"- Topic: {topic}",
        f"- Objective: {objective}",
        "Memory snapshot",
        f"- {round_summary.strip() or 'No intermediate memory captured.'}",
        _format_bullet_block("Consensus", consensus_points[:4]),
        _format_bullet_block("Dissent", dissent_points[:4]),
        _format_bullet_block("Next actions", next_actions[:4]),
        "Decision gate",
        f"- Runtime resilience: {resilience_status}",
        f"- Resilience cause: {resilience_cause}",
        f"- Analytical run: {'yes' if analytical_run else 'no'}",
        f"- Analytical rerun required: {'yes' if analytical_rerun_required else 'no'}",
        f"- Exit condition: keep the rollout reversible until the next gate is explicitly passed.",
    ]
    return "\n".join(lines).strip()

def build_meeting_report(
    *,
    topic: str,
    objective: str,
    round_reports: list[dict[str, Any]],
    strategy: str,
    consensus_points: list[str],
    dissent_points: list[str],
    next_actions: list[str],
    runtime_resilience: dict[str, Any] | None = None,
    analytical_run: bool = False,
    analytical_rerun_required: bool = False,
) -> dict[str, Any]:
    latest_round = round_reports[-1] if round_reports else {}
    persistent_options: list[str] = []
    persistent_risks: list[str] = []
    persistent_disagreements: list[str] = []
    for report in round_reports[-3:]:
        persistent = report.get("persistent") if isinstance(report, dict) else {}
        if not isinstance(persistent, dict):
            continue
        persistent_options.extend([item for item in persistent.get("options", []) if isinstance(item, str)])
        persistent_risks.extend([item for item in persistent.get("risks", []) if isinstance(item, str)])
        persistent_disagreements.extend([item for item in persistent.get("disagreements", []) if isinstance(item, str)])
    return {
        "topic": topic,
        "objective": objective,
        "round_count": len(round_reports),
        "strategy": strategy,
        "headline": strategy.splitlines()[1] if "\n" in strategy else strategy,
        "latest_decision_gate": str(latest_round.get("decision_gate") or "n/a"),
        "persistent_options": _dedupe_meeting_points(persistent_options)[:4],
        "persistent_risks": _dedupe_meeting_points(persistent_risks)[:4],
        "persistent_disagreements": _dedupe_meeting_points(persistent_disagreements)[:4],
        "consensus_points": _dedupe_meeting_points(consensus_points)[:4],
        "dissent_points": _dedupe_meeting_points(dissent_points)[:4],
        "next_actions": _dedupe_meeting_points(next_actions)[:4],
        "round_reports": list(round_reports),
        "runtime_status": str((runtime_resilience or {}).get("status") or "n/a"),
        "runtime_summary": str((runtime_resilience or {}).get("summary") or "n/a"),
        "analytical_run": bool(analytical_run),
        "analytical_rerun_required": bool(analytical_rerun_required),
    }


def _enrich_turn_draft(
    draft: MeetingTurnDraft,
    *,
    participant: str,
    round_index: int,
    phase: str,
    topic: str,
    objective: str,
    prior_summary: str,
    critique_focus: str | None = None,
) -> MeetingTurnDraft:
    if draft.recommended_actions or draft.key_risks or draft.disagreements or draft.closing_note:
        return draft
    phase_key = phase.strip().lower()
    thesis = draft.thesis.strip() or f"{participant} keeps the meeting grounded for {topic}."
    if phase_key == ROUND_PHASE_CRITIQUE:
        return MeetingTurnDraft(
            thesis=thesis,
            recommended_actions=[
                f"Challenge the weakest assumption in the current plan for {topic}.",
                f"Require a rollback gate before widening scope for {objective}.",
            ],
            key_risks=[
                critique_focus or "The current plan may hide a material failure mode.",
                "The discussion may drift unless the objection is recorded explicitly.",
            ],
            disagreements=[
                "The strongest counterargument should remain visible in the next round.",
                "Do not advance until the red-team objection is addressed.",
            ],
            closing_note="Critique should force a concrete decision threshold.",
        )
    if phase_key == ROUND_PHASE_SYNTHESIS:
        return MeetingTurnDraft(
            thesis=thesis,
            recommended_actions=[
                f"Commit to the preferred path for {objective}.",
                "Name the owner, the gate, and the rollback trigger.",
            ],
            key_risks=[
                "The synthesis can still be too optimistic if unresolved dissent is hidden.",
                "The decision may be premature without a final verification step.",
            ],
            disagreements=[
                "Keep the strongest unresolved objection in the watchlist.",
            ],
            closing_note="Synthesis should close the loop, not reopen the debate.",
        )
    return MeetingTurnDraft(
        thesis=thesis,
        recommended_actions=[
            f"List the two assumptions that must hold for {topic}.",
            "Define the success metric and the abort criterion before the next round.",
        ],
        key_risks=[
            "The opening position may be too broad without explicit evidence.",
            "The next round should preserve a short memory of the key options.",
        ],
        disagreements=[
            "Record any early uncertainty as a named watchpoint.",
        ],
        closing_note=f"Initial pass for {objective} should stay concrete and bounded.",
    )


def _enrich_round_summary(
    summary: MeetingRoundSummary,
    *,
    topic: str,
    objective: str,
    round_index: int,
    phase: str,
    prior_summary: str,
    turns: list[MeetingTurnDraft],
) -> MeetingRoundSummary:
    point_sets = _collect_meeting_points(turns)
    prior_points = _extract_memory_points(prior_summary)
    top_options = _dedupe_meeting_points(
        [
            *list(getattr(summary, "top_options", []) or []),
            *point_sets["options"],
            *prior_points["options"],
        ]
    )
    risks = _dedupe_meeting_points(
        [
            *list(getattr(summary, "risks", []) or []),
            *point_sets["risks"],
            *prior_points["risks"],
        ]
    )
    unresolved = _dedupe_meeting_points(
        [
            *list(getattr(summary, "unresolved_disagreements", []) or []),
            *point_sets["disagreements"],
            *prior_points["disagreements"],
        ]
    )
    summary_text = _format_memory_snapshot(
        topic=topic,
        objective=objective,
        phase=phase,
        round_index=round_index,
        prior_summary=prior_summary,
        turn_points={"options": top_options, "risks": risks, "disagreements": unresolved},
    )
    return MeetingRoundSummary(
        summary=summary_text,
        top_options=top_options,
        risks=risks,
        unresolved_disagreements=unresolved,
    )


def _enrich_meeting_synthesis(
    synthesis: MeetingSynthesisDraft,
    *,
    topic: str,
    objective: str,
    summary: str,
    turns: list[MeetingTurnDraft],
    runtime_resilience: dict[str, Any] | None,
) -> MeetingSynthesisDraft:
    point_sets = _collect_meeting_points(turns)
    consensus_points = _dedupe_meeting_points(list(getattr(synthesis, "consensus_points", []) or point_sets["options"][:4]))
    dissent_points = _dedupe_meeting_points(list(getattr(synthesis, "dissent_points", []) or point_sets["disagreements"][:4]))
    next_actions = _dedupe_meeting_points(list(getattr(synthesis, "next_actions", []) or []))
    if len(consensus_points) < 2:
        consensus_points = _dedupe_meeting_points(
            [
                *consensus_points,
                *point_sets["options"][:4],
                f"Keep the decision for '{topic}' explicit and stage-gated.",
            ]
        )
    if len(dissent_points) < 1:
        dissent_points = _dedupe_meeting_points(
            [
                *dissent_points,
                *point_sets["disagreements"][:4],
                f"Do not hide the strongest unresolved objection on '{topic}'.",
            ]
        )
    if len(next_actions) < 2:
        flattened_actions: list[str] = []
        for turn in turns:
            flattened_actions.extend(turn.recommended_actions)
        next_actions = _dedupe_meeting_points(
            [
                *next_actions,
                *flattened_actions,
                f"Define the next validation gate for '{objective}'.",
                "Record the rerun condition if runtime quality is degraded.",
            ]
        )
    strategy = _format_final_strategy(
        topic=topic,
        objective=objective,
        raw_strategy=getattr(synthesis, "strategy", ""),
        consensus_points=consensus_points,
        dissent_points=dissent_points,
        next_actions=next_actions,
        runtime_resilience=runtime_resilience,
        round_summary=summary,
        analytical_run=_is_analytical_meeting(topic=topic, objective=objective),
        analytical_rerun_required=bool(_is_analytical_meeting(topic=topic, objective=objective) and (runtime_resilience or {}).get("degraded_mode")),
    )
    return MeetingSynthesisDraft(
        strategy=strategy,
        consensus_points=consensus_points,
        dissent_points=dissent_points,
        next_actions=next_actions,
    )


def _is_analytical_meeting(*, topic: str, objective: str) -> bool:
    corpus = f"{topic} {objective}".lower()
    return any(term in corpus for term in _ANALYTICAL_MEETING_TERMS)


def run_strategy_meeting_sync(
    *,
    topic: str,
    objective: str | None = None,
    participants: list[str] | None = None,
    max_agents: int = 6,
    rounds: int = 2,
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str = "pydanticai",
    allow_fallback: bool = False,
    client: OpenClawClient | Any | None = None,
    model_name: str | None = None,
) -> StrategyMeetingResult:
    coordinator = StrategyMeetingCoordinator(
        config_path=config_path,
        client=client,
        runtime=runtime,
        allow_fallback=allow_fallback,
        model_name=model_name,
    )
    return coordinator.run_meeting(
        topic=topic,
        objective=objective,
        participants=participants,
        max_agents=max_agents,
        rounds=rounds,
        persist=persist,
    )
