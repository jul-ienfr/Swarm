from __future__ import annotations

import hashlib
import json
from pathlib import Path

from runtime_contracts.adapter_command import AdapterCommand
from runtime_contracts.adapter_result import AdapterResultV1, EngineMeta, NormalizedArtifact, NormalizedMetric, RunStatus
from swarm_core.deliberation import (
    DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH,
    DeliberationCoordinator,
    DeliberationJudgeScores,
    DeliberationMode,
    DeliberationResult,
    DeliberationStatus,
    _build_comparability_metadata,
    _build_quality_warnings,
    load_deliberation_result,
    replay_deliberation_sync,
    run_deliberation_sync,
)
from swarm_core.deliberation_stability import DeliberationStabilitySummary
from swarm_core.strategy_meeting import StrategyMeetingResult, StrategyMeetingStatus


FAKE_RUNTIME_RESILIENCE = {
    "status": "guarded",
    "score": 0.82,
    "summary": "guarded | retries=1 | backoff=0.150s",
    "meeting_status": "completed",
    "runtime_requested": "pydanticai",
    "runtime_used": "pydanticai",
    "runtime_match": True,
    "degraded_mode": False,
    "degraded_reasons": [],
    "stage_count": 3,
    "stages_present": ["turn", "round", "final"],
    "stage_counts": {"turn": 3, "round": 3, "final": 1},
    "source_stage": "turn",
    "diagnostic_count": 3,
    "attempt_count": 3,
    "retry_count": 1,
    "retry_rate": 0.333,
    "fallback_count": 0,
    "fallback_rate": 0.0,
    "fallback_modes": [],
    "backoff_event_count": 1,
    "backoff_total_seconds": 0.15,
    "retry_budget_exhausted": False,
    "immediate_fallback": False,
    "runtime_error_count": 0,
    "error_categories": [],
    "error_category_count": 0,
    "retry_reasons": ["connection_error"],
    "retry_reason_count": 1,
}


def _stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class FakeAdapterService:
    def __init__(self) -> None:
        self.status_calls = 0
        self.commands: list[str] = []

    def dispatch(self, command):
        self.commands.append(command.command.value)
        if command.command == AdapterCommand.create_run:
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_1",
                status=RunStatus.queued,
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        if command.command == AdapterCommand.get_status:
            self.status_calls += 1
            status = RunStatus.completed if self.status_calls >= 1 else RunStatus.running
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_1",
                status=status,
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        if command.command == AdapterCommand.get_result:
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_1",
                status=RunStatus.completed,
                summary="Population reaction stabilizes around a cautious rollout.",
                metrics=[NormalizedMetric(name="engagement_index", value=0.73, unit="index")],
                scenarios=[{"scenario_id": "baseline", "description": "Cautious adoption."}],
                risks=[{"risk": "trust_dip", "detail": "Confidence drops if messaging is inconsistent."}],
                recommendations=[{"action": "sequence_release", "detail": "Roll out in phases."}],
                artifacts=[
                    NormalizedArtifact(
                        name="engine-report",
                        artifact_type="report",
                        uri="engine://agentsociety/demo/report.json",
                        content_type="application/json",
                    )
                ],
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        if command.command == AdapterCommand.cancel_run:
            return AdapterResultV1(
                runtime_run_id=command.runtime_run_id,
                engine_run_id="as_demo_1",
                status=RunStatus.cancelled,
                engine_meta=EngineMeta(engine=command.engine.value),
                correlation_id=command.correlation_id,
            )
        raise AssertionError(f"Unexpected command: {command.command}")


def _fake_meeting_result(**kwargs) -> StrategyMeetingResult:
    participants = list(kwargs.get("participants") or [])
    return StrategyMeetingResult(
        meeting_id="meeting_demo",
        topic=kwargs["topic"],
        objective=kwargs.get("objective") or "Define the best strategy for the topic",
        status=StrategyMeetingStatus.completed,
        participants=participants,
        requested_participants=participants,
        requested_max_agents=kwargs.get("max_agents", 0),
        requested_rounds=kwargs.get("rounds", 0),
        rounds_completed=kwargs.get("rounds", 0),
        strategy="Adopt a staged rollout with clear guardrails.",
        consensus_points=["Roll out in stages", "Protect reliability"],
        dissent_points=["Some want a faster launch"],
        next_actions=["Define the canary gates", "Set rollback thresholds"],
        quality_score=0.84,
        confidence_score=0.77,
        dissent_turn_count=2,
        metadata={
            "runtime_used": kwargs["runtime"],
            "fallback_used": False,
            "runtime_resilience": FAKE_RUNTIME_RESILIENCE,
        },
    )


def test_committee_deliberation_runs_with_benchmark_and_persists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.deliberation.run_strategy_meeting_sync", _fake_meeting_result)

    result = run_deliberation_sync(
        topic="How should we launch the new workflow?",
        mode=DeliberationMode.committee,
        participants=["architect", "research", "safety"],
        max_agents=3,
        rounds=2,
        persist=True,
        output_dir=tmp_path,
        benchmark_path=str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    )

    assert result.status == DeliberationStatus.completed
    assert result.mode == DeliberationMode.committee
    assert result.final_strategy == "Adopt a staged rollout with clear guardrails."
    assert result.benchmark_report is not None
    assert result.metadata["meeting_quality"]["quality_score"] == 0.84
    assert result.metadata["meeting_quality"]["confidence_score"] == 0.77
    assert result.metadata["meeting_quality"]["dissent_turn_count"] == 2
    assert result.runtime_resilience == FAKE_RUNTIME_RESILIENCE
    assert result.metadata["runtime_resilience"] == FAKE_RUNTIME_RESILIENCE
    assert result.metadata["comparability"]["meeting_quality_score"] == 0.84
    assert result.metadata["comparability"]["meeting_confidence_score"] == 0.77
    assert result.metadata["comparability"]["meeting_dissent_turn_count"] == 2
    assert result.metadata["comparability"]["meeting_runtime_resilience"] == FAKE_RUNTIME_RESILIENCE
    assert result.metadata["comparability"]["meeting_runtime_resilience_status"] == "guarded"
    assert result.metadata["comparability"]["meeting_runtime_resilience_score"] == 0.82
    assert result.metadata["comparability"]["input_hash"] == _stable_hash(
        {
            "topic": "How should we launch the new workflow?",
            "objective": "Define the best strategy for: How should we launch the new workflow?",
            "participants": ["architect", "research", "safety"],
            "documents": [],
            "entities": [],
            "interventions": [],
        }
    )
    assert result.metadata["comparability"]["participants_hash"] == _stable_hash(["architect", "research", "safety"])
    assert result.metadata["comparability"]["documents_hash"] == _stable_hash([])
    runtime_identity = result.metadata["comparability"]["runtime_identity"]
    assert runtime_identity["runtime_requested"] == "pydanticai"
    assert runtime_identity["runtime_used"] == "pydanticai"
    assert runtime_identity["runtime_backend"] == "pydanticai"
    assert result.decision_packet is not None
    assert result.decision_packet.quality_score == 0.84
    assert result.decision_packet.confidence_score == 0.77
    assert result.decision_packet.dissent_turn_count == 2
    assert result.decision_packet.meeting_quality_summary.startswith("quality=0.840")
    assert result.decision_packet.runtime_resilience == FAKE_RUNTIME_RESILIENCE
    assert result.persisted_path is not None
    assert Path(result.persisted_path).exists()
    loaded = load_deliberation_result(result.deliberation_id, output_dir=tmp_path)
    assert loaded.final_strategy == result.final_strategy


def test_simulation_deliberation_runs_via_adapter_and_records_artifacts(tmp_path: Path) -> None:
    coordinator = DeliberationCoordinator(output_dir=tmp_path, adapter_service=FakeAdapterService())

    result = coordinator.run(
        topic="How will the population react to a staged release?",
        objective="Estimate social reaction to a staged release.",
        mode=DeliberationMode.simulation,
        documents=["Doc A", "Doc B"],
        entities=[{"segment": "early-adopters"}],
        interventions=["Inject a surprise outage on day 2."],
        population_size=250,
        rounds=2,
        persist=True,
        benchmark_path=str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    )

    assert result.status == DeliberationStatus.completed
    assert result.mode == DeliberationMode.simulation
    assert result.engine_used == "agentsociety"
    assert result.metrics["engagement_index"] == 0.73
    assert result.artifacts
    assert result.manifest_path is not None
    assert result.replay_path is not None
    assert Path(result.manifest_path).exists()
    assert Path(result.replay_path).exists()
    assert result.benchmark_report is not None
    assert result.belief_states
    assert result.belief_group_summaries
    assert result.graph_path is not None
    assert Path(result.graph_path).exists()
    loaded = load_deliberation_result(result.deliberation_id, output_dir=tmp_path)
    assert loaded.deliberation_id == result.deliberation_id
    replayed = coordinator.replay(result.deliberation_id, persist=False)
    assert replayed.mode == DeliberationMode.simulation
    assert replayed.summary == result.summary
    comparability = result.metadata["comparability"]
    assert comparability["input_hash"] == _stable_hash(
        {
            "topic": "How will the population react to a staged release?",
            "objective": "Estimate social reaction to a staged release.",
            "participants": [],
            "documents": ["Doc A", "Doc B"],
            "entities": [{"segment": "early-adopters"}],
            "interventions": ["Inject a surprise outage on day 2."],
        }
    )
    assert comparability["documents_hash"] == _stable_hash(["Doc A", "Doc B"])
    assert comparability["entities_hash"] == _stable_hash([{"segment": "early-adopters"}])
    assert comparability["interventions_hash"] == _stable_hash(["Inject a surprise outage on day 2."])
    assert comparability["runtime_identity"]["runtime_backend"] == "pydanticai"
    assert comparability["workbench_identity"]["workbench_profile_count"] > 0
    assert any(key.startswith("graph:") for key in comparability["artifact_keys"])


def test_simulation_deliberation_can_target_oasis_surrogate(tmp_path: Path) -> None:
    coordinator = DeliberationCoordinator(output_dir=tmp_path, backend_mode="surrogate")

    result = coordinator.run(
        topic="How does the platform react on OASIS?",
        objective="Estimate social dynamics with OASIS.",
        mode=DeliberationMode.simulation,
        documents=["Doc A"],
        entities=[{"segment": "early-adopters"}],
        interventions=["Inject a moderation policy shift."],
        population_size=64,
        rounds=1,
        persist=False,
        engine_preference="oasis",
    )

    assert result.mode == DeliberationMode.simulation
    assert result.engine_used == "oasis"
    assert result.metrics["engagement_index"] >= 0.0
    assert result.benchmark_report is not None


def test_simulation_deliberation_can_compare_multiple_engines(tmp_path: Path) -> None:
    coordinator = DeliberationCoordinator(output_dir=tmp_path, backend_mode="surrogate")

    result = coordinator.run(
        topic="Compare agent engines on the same topic",
        objective="Measure convergence across engines.",
        mode=DeliberationMode.simulation,
        documents=["Doc A", "Doc B"],
        population_size=96,
        rounds=1,
        persist=False,
        engine_preference="agentsociety",
        ensemble_engines=["oasis"],
    )

    assert result.mode == DeliberationMode.simulation
    assert result.engine_used == "agentsociety"
    assert result.ensemble_report is not None
    assert result.ensemble_report.primary_engine == "agentsociety"
    assert set(result.ensemble_report.compared_engines) == {"agentsociety", "oasis"}
    assert len(result.ensemble_report.engine_snapshots) == 2


def test_simulation_deliberation_surfaces_quality_warnings_when_stability_samples_are_insufficient(tmp_path: Path) -> None:
    coordinator = DeliberationCoordinator(output_dir=tmp_path, adapter_service=FakeAdapterService())

    result = coordinator.run(
        topic="How stable is the simulated rollout response?",
        objective="Evaluate stability and quality warnings.",
        mode=DeliberationMode.simulation,
        documents=["Doc A", "Doc B"],
        population_size=64,
        rounds=1,
        persist=False,
        stability_runs=2,
    )

    assert result.stability_summary is not None
    assert result.stability_summary.sample_count == 2
    assert result.stability_summary.sample_sufficient is False
    assert "stability_sample_count_insufficient" in result.sensitivity_factors
    assert any(w.startswith("stability_sample_count_insufficient: 2/3") for w in result.metadata["quality_warnings"])
    assert result.metadata["comparability"]["stability_sample_count"] == 2
    assert result.metadata["comparability"]["stability_minimum_sample_count"] == 3
    assert result.metadata["comparability"]["stability_sample_sufficient"] is False
    assert result.metadata["comparability"]["stability_dispersion_gate_passed"] is True
    assert result.metadata["comparability"]["stability_stable"] is False
    assert "profile_quality_diversity" in result.metadata["comparability"]
    assert "profile_quality_stance_diversity" in result.metadata["comparability"]
    assert "profile_quality_role_diversity" in result.metadata["comparability"]
    assert result.metadata["comparability"]["profile_count"] > 0
    assert result.metadata["comparability"]["belief_group_count"] > 0
    assert isinstance(result.metadata["comparability"]["stability_assessment_flags"], list)
    assert isinstance(result.metadata["comparability"]["stability_notes"], str)


def test_quality_metadata_flags_dispersion_and_profile_diversity() -> None:
    result = DeliberationResult(
        deliberation_id="delib_demo",
        topic="Check dispersion",
        objective="Check quality metadata",
        mode=DeliberationMode.simulation,
        status=DeliberationStatus.completed,
        runtime_requested="pydanticai",
        runtime_used="legacy",
        fallback_used=True,
        engine_requested="agentsociety",
        engine_used="oasis",
        requested_max_agents=6,
        population_size=96,
        rounds_requested=2,
        rounds_completed=2,
        participants=["architect", "research", "safety"],
        metadata={"profile_count": 3},
        profile_quality={
            "overall_score": 0.31,
            "passed": False,
            "coverage": 0.9,
            "grounding": 0.8,
            "diversity": 0.22,
            "stance_diversity": 0.18,
            "role_diversity": 0.25,
            "consistency": 0.7,
            "label_quality": 0.5,
            "issues": [
                {"code": "diversity_low", "message": "diversity 0.22 < 0.35"},
                {"code": "stance_diversity_low", "message": "stance diversity 0.18 < 0.35"},
            ],
        },
        judge_scores=DeliberationJudgeScores(overall=0.44),
    )
    stability_summary = DeliberationStabilitySummary.from_scores([0.08, 0.34, 0.92], minimum_sample_count=3)

    comparability = _build_comparability_metadata(
        result=result,
        profile_quality=result.profile_quality,
        stability_summary=stability_summary,
        benchmark_suite_loaded=False,
    )
    warnings = _build_quality_warnings(
        result=result,
        profile_quality=result.profile_quality,
        stability_summary=stability_summary,
        comparability=comparability,
    )

    assert comparability["runtime_match"] is False
    assert comparability["engine_match"] is False
    assert comparability["profile_quality_passed"] is False
    assert comparability["profile_quality_diversity"] == 0.22
    assert comparability["profile_quality_issue_codes"] == ["diversity_low", "stance_diversity_low"]
    assert comparability["stability_sample_count"] == 3
    assert comparability["stability_sample_sufficient"] is True
    assert comparability["stability_dispersion_gate_passed"] is False
    assert comparability["stability_stable"] is False
    assert comparability["stability_assessment_flags"]
    assert any(w.startswith("runtime_fallback_used: requested=pydanticai used=legacy") for w in warnings)
    assert any(w.startswith("engine_mismatch: requested=agentsociety used=oasis") for w in warnings)
    assert any(w.startswith("profile_quality_below_threshold: overall=0.310 passed=False") for w in warnings)
    assert any(w.startswith("profile_diversity_low: diversity=0.220 stance=0.180 role=0.250") for w in warnings)
    assert any(w.startswith("stability_dispersion_gate_failed: std_dev=") for w in warnings)
    assert any(w.startswith("stability_not_confirmed: sample_sufficient=True dispersion_gate_passed=False") for w in warnings)


def test_hybrid_deliberation_combines_simulation_and_committee(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.deliberation.run_strategy_meeting_sync", _fake_meeting_result)
    coordinator = DeliberationCoordinator(output_dir=tmp_path, adapter_service=FakeAdapterService())

    result = coordinator.run(
        topic="What is the best launch strategy after simulation?",
        objective="Simulate first, then define the strategy.",
        mode=DeliberationMode.hybrid,
        participants=["architect", "research", "safety"],
        documents=["Doc A"],
        max_agents=3,
        population_size=500,
        rounds=2,
        persist=False,
    )

    assert result.status == DeliberationStatus.completed
    assert result.mode == DeliberationMode.hybrid
    assert result.final_strategy == "Adopt a staged rollout with clear guardrails."
    assert result.summary == "Population reaction stabilizes around a cautious rollout."
    assert result.engine_used == "agentsociety"
    assert result.runtime_used == "pydanticai"
    assert result.decision_packet is not None
    assert result.metadata["meeting_quality"]["quality_score"] == 0.84
    assert result.metadata["meeting_quality"]["summary"].startswith("quality=0.840")
    assert result.runtime_resilience == FAKE_RUNTIME_RESILIENCE
    assert result.metadata["runtime_resilience"] == FAKE_RUNTIME_RESILIENCE
    assert result.metadata["comparability"]["meeting_quality_score"] == 0.84
    assert result.metadata["comparability"]["meeting_runtime_resilience"] == FAKE_RUNTIME_RESILIENCE
    assert result.decision_packet.quality_score == 0.84
    assert result.decision_packet.confidence_score == 0.77
    assert result.decision_packet.dissent_turn_count == 2
    assert result.decision_packet.runtime_resilience == FAKE_RUNTIME_RESILIENCE


def test_replay_deliberation_reuses_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.deliberation.run_strategy_meeting_sync", _fake_meeting_result)

    initial = run_deliberation_sync(
        topic="Replay this committee run",
        mode=DeliberationMode.committee,
        participants=["architect", "safety"],
        max_agents=2,
        rounds=1,
        persist=True,
        output_dir=tmp_path,
    )

    replay = replay_deliberation_sync(initial.deliberation_id, output_dir=tmp_path, persist=False)

    assert replay.mode == DeliberationMode.committee
    assert replay.final_strategy == initial.final_strategy
    assert replay.deliberation_id != initial.deliberation_id
