from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime_pydanticai.models import MeetingTurnDraft, RuntimeBackend as StructuredRuntimeBackend
from swarm_core.deliberation import _committee_result_to_deliberation
from swarm_core.strategy_meeting import StrategyMeetingCoordinator, StrategyMeetingStatus, _dedupe_meeting_points


def _extract_phase(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("Phase:"):
            return line.split(":", 1)[1].strip()
    return "independent"


def _extract_critique_focus(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("Critique focus:"):
            return line.split(":", 1)[1].strip()
    return ""


def _agent_content(agent_id: str, phase: str) -> str:
    if phase == "critique":
        return (
            f"Thesis: {agent_id} challenges the current rollout path and asks for stronger rollback criteria.\n"
            "Recommended actions:\n"
            "- Identify the assumptions that could fail first.\n"
            "- Add explicit kill-switches before scaling.\n"
            "Key risks:\n"
            "- The current plan may assume too much stability.\n"
            "- Confidence may be inflated by a narrow sample.\n"
            "Disagreements:\n"
            "- We should not advance without a red-team gate."
        )
    if phase == "synthesis":
        return (
            f"Thesis: {agent_id} converges on a staged rollout with explicit gates and rollback criteria.\n"
            "Recommended actions:\n"
            "- Ship in phases.\n"
            "- Instrument each gate with observable metrics.\n"
            "Key risks:\n"
            "- Skipping synthesis would leave the plan ambiguous.\n"
            "Disagreements:\n"
            "- Earlier objections need to be closed before execution."
        )
    return (
        f"Thesis: {agent_id} recommends a staged rollout that protects reliability and observability.\n"
        "Recommended actions:\n"
        "- Roll out in phases.\n"
        "- Keep rollback criteria explicit.\n"
        "Key risks:\n"
        "- Moving too quickly could hide regressions.\n"
        "Disagreements:\n"
        "- We need evidence before broad rollout."
    )


class RecordingMeetingClient:
    def __init__(self) -> None:
        self.agent_calls: list[dict[str, object]] = []
        self.escalation_calls: list[dict[str, object]] = []

    def chat_with_agent(self, worker_name, agent_id, messages):
        instruction = str(messages[-1]["content"])
        phase = _extract_phase(instruction)
        self.agent_calls.append(
            {
                "worker_name": worker_name,
                "agent_id": agent_id,
                "instruction": instruction,
                "phase": phase,
            }
        )
        return {
            "worker_name": worker_name,
            "content": _agent_content(agent_id, phase),
            "success": True,
            "error": None,
            "tokens_used": 11,
        }

    def chat_with_escalation(self, worker_name, messages, preferred_tier="tier3_paid", model_name="claude-sonnet-4-6"):
        prompt = str(messages[-1]["content"])
        phase = _extract_phase(prompt)
        self.escalation_calls.append(
            {
                "worker_name": worker_name,
                "instruction": prompt,
                "phase": phase,
                "preferred_tier": preferred_tier,
                "model_name": model_name,
            }
        )
        if worker_name == "meeting_facilitator":
            return {
                "success": True,
                "content": "Round summary: the discussion is shifting from first-pass exploration to explicit tradeoff handling.",
                "tokens_used": 17,
            }
        return {
            "success": True,
            "content": json.dumps(
                {
                    "strategy": "Adopt a staged rollout with explicit gates.",
                    "consensus_points": [
                        "Preserve reliability with phased deployment",
                        "Preserve reliability with phased deployment.",
                        "preserve reliability with phased deployment",
                        "Make rollback criteria explicit",
                    ],
                    "dissent_points": [
                        "Some participants want more aggressive expansion",
                        "some participants want more aggressive expansion.",
                        "Red-team concerns remain around hidden assumptions",
                        "Red-team concerns remain around hidden assumptions.",
                    ],
                    "next_actions": [
                        "Define the rollout gates",
                        "define the rollout gates",
                        "Assign owners for reliability monitoring",
                        "Assign owners for reliability monitoring.",
                    ],
                }
            ),
            "tokens_used": 21,
        }


class ResilientFakeRuntime:
    def __init__(self, **kwargs) -> None:
        self.runtime_used = StructuredRuntimeBackend.pydanticai
        self.last_fallback_used = True
        self.last_error = "temporary upstream failure"
        self.last_error_category = "rate_limit"
        self.last_attempt_count = 3
        self.last_retry_count = 2
        self.last_retry_reasons = ["rate_limit", "timeout"]

    def generate_turn(self, **kwargs):
        participant = str(kwargs.get("participant", "agent"))
        return MeetingTurnDraft(thesis=f"{participant} keeps the rollout cautious.")

    def summarize_round(self, **kwargs):
        round_index = kwargs.get("round_index", 0)
        return SimpleNamespace(summary=f"Round {round_index} synthesis.")

    def synthesize_meeting(self, **kwargs):
        return SimpleNamespace(
            strategy="Adopt a phased rollout.",
            consensus_points=["Preserve reliability"],
            dissent_points=["Watch for timeout pressure"],
            next_actions=["Define rollout gates"],
        )


class ComparabilityFakeRuntime:
    def __init__(self, **kwargs) -> None:
        self.runtime_used = StructuredRuntimeBackend.pydanticai
        self.last_fallback_used = False
        self.last_error = None
        self.last_error_category = None
        self.last_attempt_count = 1
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_backoff_schedule = []
        self.last_backoff_total_seconds = 0.0
        self.last_retry_budget_exhausted = False
        self.last_immediate_fallback = False
        self._config = SimpleNamespace(model_name="claude-sonnet-4-6", base_url="https://api.example.test/v1")

    def generate_turn(self, **kwargs):
        participant = str(kwargs.get("participant", "agent"))
        return MeetingTurnDraft(thesis=f"{participant} recommends a phased rollout.")

    def summarize_round(self, **kwargs):
        round_index = kwargs.get("round_index", 0)
        return SimpleNamespace(summary=f"Round {round_index} summary.")

    def synthesize_meeting(self, **kwargs):
        return SimpleNamespace(
            strategy="Adopt a phased rollout.",
            consensus_points=["Preserve reliability"],
            dissent_points=["Watch for timeout pressure"],
            next_actions=["Define rollout gates"],
        )


class MixedFallbackRuntime:
    def __init__(self, **kwargs) -> None:
        self.runtime_used = StructuredRuntimeBackend.pydanticai
        self.last_fallback_used = False
        self.last_error = None
        self.last_error_category = None
        self.last_error_retryable = None
        self.last_attempt_count = 1
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_backoff_schedule = []
        self.last_backoff_total_seconds = 0.0
        self.last_retry_budget_exhausted = False
        self.last_immediate_fallback = False
        self._turn_index = 0
        self._config = SimpleNamespace(model_name="claude-sonnet-4-6", base_url="https://api.example.test/v1")

    def _set_state(self, *, runtime_used: StructuredRuntimeBackend, fallback_used: bool) -> None:
        self.runtime_used = runtime_used
        self.last_fallback_used = fallback_used
        self.last_error = "temporary upstream failure" if fallback_used else None
        self.last_error_category = "connection_error" if fallback_used else None
        self.last_error_retryable = fallback_used
        self.last_attempt_count = 2 if fallback_used else 1
        self.last_retry_count = 1 if fallback_used else 0
        self.last_retry_reasons = ["connection_error"] if fallback_used else []
        self.last_backoff_schedule = (
            [{"attempt": 1, "delay_seconds": 0.15, "error_category": "connection_error", "retryable": True}]
            if fallback_used
            else []
        )
        self.last_backoff_total_seconds = 0.15 if fallback_used else 0.0
        self.last_retry_budget_exhausted = fallback_used
        self.last_immediate_fallback = fallback_used

    def generate_turn(self, **kwargs):
        self._turn_index += 1
        if self._turn_index == 1:
            self._set_state(runtime_used=StructuredRuntimeBackend.legacy, fallback_used=True)
        else:
            self._set_state(runtime_used=StructuredRuntimeBackend.pydanticai, fallback_used=False)
        participant = str(kwargs.get("participant", "agent"))
        return MeetingTurnDraft(thesis=f"{participant} keeps the rollout cautious.")

    def summarize_round(self, **kwargs):
        self._set_state(runtime_used=StructuredRuntimeBackend.pydanticai, fallback_used=False)
        round_index = kwargs.get("round_index", 0)
        return SimpleNamespace(summary=f"Round {round_index} synthesis.")

    def synthesize_meeting(self, **kwargs):
        self._set_state(runtime_used=StructuredRuntimeBackend.pydanticai, fallback_used=False)
        return SimpleNamespace(
            strategy="Adopt a phased rollout.",
            consensus_points=["Preserve reliability"],
            dissent_points=["Watch for timeout pressure"],
            next_actions=["Define rollout gates"],
        )


def test_strategy_meeting_deduplication_is_order_stable() -> None:
    assert _dedupe_meeting_points(
        [
            "We should define the rollout gates.",
            "define rollout gates",
            "Define the rollout gates!",
            "Assign owners for reliability monitoring",
            "assign owners for reliability monitoring.",
        ]
    ) == [
        "We should define the rollout gates.",
        "Assign owners for reliability monitoring",
    ]


def test_strategy_meeting_score_is_zero_without_units() -> None:
    assert StrategyMeetingCoordinator._score_meeting(
        success_count=0,
        total_units=0,
        dissent_count=0,
        cluster_count=0,
        round_phases=[],
        requested_rounds=0,
        rounds_completed=0,
    ) == (0.0, 0.0)


def test_strategy_meeting_score_prefers_synthesis_over_critique_and_independent() -> None:
    synth_quality, synth_confidence = StrategyMeetingCoordinator._score_meeting(
        success_count=9,
        total_units=9,
        dissent_count=1,
        cluster_count=0,
        round_phases=["independent", "critique", "synthesis"],
        requested_rounds=3,
        rounds_completed=3,
    )
    critique_quality, critique_confidence = StrategyMeetingCoordinator._score_meeting(
        success_count=6,
        total_units=6,
        dissent_count=1,
        cluster_count=0,
        round_phases=["independent", "critique"],
        requested_rounds=3,
        rounds_completed=2,
    )
    independent_quality, independent_confidence = StrategyMeetingCoordinator._score_meeting(
        success_count=3,
        total_units=3,
        dissent_count=0,
        cluster_count=0,
        round_phases=["independent"],
        requested_rounds=3,
        rounds_completed=1,
    )

    assert synth_quality > critique_quality > independent_quality
    assert synth_confidence > critique_confidence > independent_confidence
    assert critique_quality >= 0.55
    assert independent_quality < critique_quality
    assert independent_confidence < critique_confidence


def test_strategy_meeting_score_dissent_bonus_is_capped() -> None:
    baseline_quality, baseline_confidence = StrategyMeetingCoordinator._score_meeting(
        success_count=9,
        total_units=9,
        dissent_count=0,
        cluster_count=0,
        round_phases=["independent", "critique", "synthesis"],
        requested_rounds=3,
        rounds_completed=3,
    )
    noisy_quality, noisy_confidence = StrategyMeetingCoordinator._score_meeting(
        success_count=9,
        total_units=9,
        dissent_count=9,
        cluster_count=0,
        round_phases=["independent", "critique", "synthesis"],
        requested_rounds=3,
        rounds_completed=3,
    )

    assert noisy_quality >= baseline_quality
    assert noisy_confidence >= baseline_confidence
    assert noisy_quality - baseline_quality <= 0.031
    assert noisy_confidence - baseline_confidence <= 0.02


def test_strategy_meeting_runs_and_persists_artifact(tmp_path: Path) -> None:
    client = RecordingMeetingClient()
    coordinator = StrategyMeetingCoordinator(
        client=client,
        output_dir=tmp_path,
        max_participants=8,
        parallelism_limit=2,
    )

    result = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        participants=["architect", "veille-strategique", "studio-dev"],
        max_agents=3,
        rounds=3,
        persist=True,
    )

    assert result.status == StrategyMeetingStatus.completed
    assert result.rounds_completed == 3
    assert result.round_phases == ["independent", "critique", "synthesis"]
    assert len(result.round_durations_ms) == 3
    assert len(result.transcript) == 9
    assert result.transcript[0].phase == "independent"
    assert result.transcript[3].phase == "critique"
    assert result.transcript[6].phase == "synthesis"
    assert result.strategy == "Adopt a staged rollout with explicit gates."
    assert result.consensus_points == [
        "Preserve reliability with phased deployment",
        "Make rollback criteria explicit",
    ]
    assert result.dissent_points == [
        "Some participants want more aggressive expansion",
        "Red-team concerns remain around hidden assumptions",
    ]
    assert result.next_actions == [
        "Define the rollout gates",
        "Assign owners for reliability monitoring",
    ]
    assert result.dissent_turn_count == 3
    assert result.metadata["phase_counts"]["critique"] == 3
    assert result.metadata["role_counts"]["critic"] == 3
    assert result.metadata["duration_ms"] >= 0.0
    assert result.metadata["quality_score"] >= 0.0
    assert result.metadata["confidence_score"] >= 0.0
    assert len(result.metadata["round_runtime_diagnostics"]) == 3
    assert result.metadata["final_runtime_diagnostics"]["stage"] == "final_synthesis"
    assert result.transcript[0].metadata["runtime_diagnostics"]["runtime_attempt_count"] >= 1
    resilience = result.metadata["runtime_resilience"]
    assert resilience["stage_count"] == 3
    assert resilience["stages_present"] == ["turn", "round", "final"]
    assert resilience["source_stage"] == "turn"
    assert resilience["stage_counts"]["turn"] == len(result.transcript)
    assert resilience["stage_counts"]["round"] == 3
    assert resilience["stage_counts"]["final"] == 1
    assert resilience["diagnostic_count"] == len(result.transcript)
    assert resilience["status"] == "degraded"
    assert resilience["meeting_status"] == StrategyMeetingStatus.completed.value
    assert resilience["fallback_count"] == len(result.transcript)
    assert resilience["fallback_modes"] == ["policy_always"]
    assert resilience["summary"].startswith("degraded")
    assert resilience["degraded_mode"] is True
    assert resilience["runtime_match"] is True
    assert result.persisted_path is not None
    assert Path(result.persisted_path).exists()
    assert any("Phase: independent" in call["instruction"] for call in client.agent_calls)
    assert any("Phase: critique" in call["instruction"] for call in client.agent_calls)
    assert any("Phase: synthesis" in call["instruction"] for call in client.agent_calls)
    assert any(call["phase"] == "critique" for call in client.escalation_calls)
    critique_foci = {
        _extract_critique_focus(call["instruction"])
        for call in client.agent_calls
        if call["phase"] == "critique"
    }
    assert all(focus for focus in critique_foci)
    assert len(critique_foci) >= 2


def test_strategy_meeting_comparability_is_canonical_and_additive(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.strategy_meeting.PydanticAIStrategyMeetingRuntime", ComparabilityFakeRuntime)

    coordinator = StrategyMeetingCoordinator(
        client=RecordingMeetingClient(),
        output_dir=tmp_path,
        max_participants=12,
        cluster_size=4,
        forced_dissent_per_cluster=1,
        parallelism_limit=4,
    )

    flat_result = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        objective="Pick the safest launch plan.",
        participants=["architect", "ops", "qa"],
        max_agents=3,
        rounds=3,
        persist=True,
    )
    flat_repeat = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        objective="Pick the safest launch plan.",
        participants=["architect", "ops", "qa"],
        max_agents=3,
        rounds=3,
        persist=False,
    )

    comparability = flat_result.metadata["comparability"]
    assert comparability == flat_repeat.metadata["comparability"]
    assert comparability["runtime_requested"] == "pydanticai"
    assert comparability["runtime_used"] == "pydanticai"
    assert comparability["runtime_match"] is True
    assert comparability["model_name"] == "claude-sonnet-4-6"
    assert comparability["provider_base_url"] == "https://api.example.test/v1"
    assert comparability["participant_count"] == 3
    assert comparability["cluster_count"] == 0
    assert comparability["phase_count"] == 3
    assert comparability["routing_mode"] == "committee"
    assert len(comparability["topic_fingerprint"]) == 64
    assert len(comparability["objective_fingerprint"]) == 64
    assert len(comparability["participant_fingerprint"]) == 64
    assert len(comparability["input_fingerprint"]) == 64
    assert len(comparability["execution_fingerprint"]) == 64

    persisted = json.loads(Path(flat_result.persisted_path).read_text(encoding="utf-8"))
    assert persisted["metadata"]["comparability"] == comparability

    hierarchical_result = coordinator.run_meeting(
        topic="Design the rollout for the social deliberation program",
        objective="Keep the rollout auditable and reversible.",
        participants=[
            "architect",
            "product",
            "safety",
            "ops",
            "research",
            "qa",
            "infra",
            "governance",
            "red-team",
        ],
        max_agents=9,
        rounds=3,
        persist=False,
    )
    hierarchical_comparability = hierarchical_result.metadata["comparability"]
    assert hierarchical_comparability["routing_mode"] == "hierarchical"
    assert hierarchical_comparability["hierarchical"] is True
    assert hierarchical_comparability["participant_count"] == 9
    assert hierarchical_comparability["cluster_count"] == 3
    assert hierarchical_comparability["phase_count"] == 4


def test_strategy_meeting_runtime_resilience_summarizes_degraded_fallbacks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.strategy_meeting.PydanticAIStrategyMeetingRuntime", ResilientFakeRuntime)

    coordinator = StrategyMeetingCoordinator(
        client=RecordingMeetingClient(),
        output_dir=tmp_path,
        max_participants=4,
        parallelism_limit=2,
    )

    result = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=1,
        persist=False,
    )

    resilience = result.metadata["runtime_resilience"]
    assert resilience["stage_count"] == 3
    assert resilience["stages_present"] == ["turn", "round", "final"]
    assert resilience["source_stage"] == "turn"
    assert resilience["diagnostic_count"] == 2
    assert resilience["attempt_count"] == 6
    assert resilience["retry_count"] == 4
    assert resilience["retry_rate"] == pytest.approx(4 / 6, rel=1e-3)
    assert resilience["fallback_count"] == 2
    assert resilience["fallback_rate"] == 1.0
    assert resilience["status"] == "degraded"
    assert resilience["meeting_status"] == StrategyMeetingStatus.completed.value
    assert resilience["score"] < 1.0
    assert resilience["summary"].startswith("degraded")
    assert resilience["runtime_error_count"] == 2
    assert resilience["error_categories"] == ["rate_limit"]
    assert resilience["retry_reasons"] == ["rate_limit", "timeout"]
    assert resilience["degraded_mode"] is True
    assert resilience["degraded_runtime_used"] == "legacy"
    assert "fallback_used" in resilience["degraded_reasons"]
    assert "runtime_error" in resilience["degraded_reasons"]
    assert "runtime_error_category" in resilience["degraded_reasons"]
    assert resilience["runtime_match"] is True
    assert result.fallback_used is True
    assert result.degraded_runtime_used == "legacy"
    assert result.decision_degraded is True


def test_strategy_meeting_records_internal_fallback_even_when_final_stage_recovers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.strategy_meeting.PydanticAIStrategyMeetingRuntime", MixedFallbackRuntime)

    coordinator = StrategyMeetingCoordinator(
        client=RecordingMeetingClient(),
        output_dir=tmp_path,
        max_participants=4,
        parallelism_limit=2,
    )

    result = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=2,
        persist=False,
    )

    resilience = result.metadata["runtime_resilience"]
    comparability = result.metadata["comparability"]

    assert result.runtime_used == StructuredRuntimeBackend.pydanticai.value
    assert result.fallback_used is True
    assert result.degraded_runtime_used == "legacy"
    assert result.decision_degraded is True
    assert result.metadata["fallback_used"] is True
    assert result.metadata["degraded_runtime_used"] == "legacy"
    assert result.metadata["meeting_degraded_runtime_used"] == "legacy"
    assert result.metadata["decision_degraded"] is True
    assert resilience["runtime_used"] == StructuredRuntimeBackend.pydanticai.value
    assert resilience["degraded_runtime_used"] == "legacy"
    assert resilience["degraded_mode"] is True
    assert resilience["fallback_count"] >= 1
    assert comparability["runtime_match"] is True
    assert comparability["fallback_used"] is True
    assert comparability["degraded_runtime_used"] == "legacy"
    assert comparability["meeting_degraded_runtime_used"] == "legacy"
    assert comparability["decision_degraded"] is True


def test_committee_deliberation_marks_internal_fallback_as_degraded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_core.strategy_meeting.PydanticAIStrategyMeetingRuntime", MixedFallbackRuntime)

    coordinator = StrategyMeetingCoordinator(
        client=RecordingMeetingClient(),
        output_dir=tmp_path,
        max_participants=4,
        parallelism_limit=2,
    )

    meeting = coordinator.run_meeting(
        topic="How should we launch the new workflow?",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=2,
        persist=False,
    )
    deliberation = _committee_result_to_deliberation(
        run_id="delib_demo",
        topic=meeting.topic,
        objective=meeting.objective,
        meeting=meeting,
        runtime_requested="pydanticai",
        runtime_used=meeting.runtime_used or "pydanticai",
        fallback_used=False,
        runtime_error=None,
    )

    assert deliberation.runtime_used == "pydanticai"
    assert deliberation.fallback_used is True
    assert deliberation.metadata["fallback_used"] is True
    assert deliberation.metadata["degraded_runtime_used"] == "legacy"
    assert deliberation.metadata["meeting_degraded_runtime_used"] == "legacy"
    assert deliberation.metadata["decision_degraded"] is True
    assert deliberation.metadata["comparability"]["fallback_used"] is True
    assert deliberation.metadata["comparability"]["meeting_degraded_runtime_used"] == "legacy"
    assert deliberation.metadata["comparability"]["decision_degraded"] is True


def test_strategy_meeting_caps_requested_participants(tmp_path: Path) -> None:
    coordinator = StrategyMeetingCoordinator(
        client=RecordingMeetingClient(),
        output_dir=tmp_path,
        max_participants=4,
        parallelism_limit=4,
    )

    result = coordinator.run_meeting(
        topic="Find the safest scaling plan",
        participants=["a", "b", "c", "d", "e", "f"],
        max_agents=10,
        rounds=1,
        persist=False,
    )

    assert result.participants == ["a", "b", "c", "d"]
    assert result.metadata["cap_applied"] is True


def test_strategy_meeting_uses_hierarchical_clusters_with_dissent(tmp_path: Path) -> None:
    client = RecordingMeetingClient()
    coordinator = StrategyMeetingCoordinator(
        client=client,
        output_dir=tmp_path,
        max_participants=12,
        cluster_size=4,
        forced_dissent_per_cluster=1,
        parallelism_limit=4,
    )

    result = coordinator.run_meeting(
        topic="Design the rollout for the social deliberation program",
        participants=[
            "architect",
            "product",
            "safety",
            "ops",
            "research",
            "qa",
            "infra",
            "governance",
            "red-team",
        ],
        max_agents=9,
        rounds=3,
        persist=False,
    )

    assert result.status == StrategyMeetingStatus.completed
    assert result.hierarchical is True
    assert result.routing_mode == "hierarchical"
    assert result.cluster_size == 4
    assert len(result.cluster_summaries) == 3
    assert result.metadata["cluster_count"] == 3
    assert result.metadata["hierarchical"] is True
    assert result.metadata["quality_score"] >= 0.0
    assert result.metadata["confidence_score"] >= 0.0
    assert result.forced_dissent_participants
    assert len(result.forced_dissent_participants) == 3
    assert any(turn.role == "cluster_summary" for turn in result.transcript)
    assert any(turn.role == "final_synthesis" for turn in result.transcript)
    assert all(summary.round_phases == ["independent", "critique", "synthesis"] for summary in result.cluster_summaries)
    assert all(
        summary.consensus_points == [
            "Preserve reliability with phased deployment",
            "Make rollback criteria explicit",
        ]
        for summary in result.cluster_summaries
    )
    assert all(
        summary.next_actions == [
            "Define the rollout gates",
            "Assign owners for reliability monitoring",
        ]
        for summary in result.cluster_summaries
    )
    assert all(len(summary.round_durations_ms) == 3 for summary in result.cluster_summaries)
    red_team_foci = {
        turn.metadata.get("critique_focus")
        for turn in result.transcript
        if turn.phase_role == "red_team"
    }
    assert all(red_team_foci)
    assert all(summary.metadata["phase_counts"]["critique"] >= 1 for summary in result.cluster_summaries)
    assert all(summary.metadata["dissent_turn_count"] >= 1 for summary in result.cluster_summaries)
    assert all(summary.metadata["round_runtime_diagnostics"] for summary in result.cluster_summaries)
    assert all(summary.metadata["final_runtime_diagnostics"]["stage"].endswith("final_synthesis") for summary in result.cluster_summaries)
    assert all(summary.quality_score > 0.0 for summary in result.cluster_summaries)
    assert all(summary.confidence_score > 0.0 for summary in result.cluster_summaries)
    assert any("Phase: critique" in call["instruction"] for call in client.agent_calls)
