from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from runtime_pydanticai.models import MeetingTurnDraft, RuntimeBackend as StructuredRuntimeBackend
from runtime_pydanticai.strategy_meeting import (
    PydanticAIStrategyMeetingRuntime,
    _LegacyMeetingTransport,
    _build_participant_prompt,
    _build_summary_prompt,
    _build_synthesis_prompt,
    _fallback_turn_draft,
)
from swarm_core.orchestration import run_strategy_meeting_runtime
from swarm_core.orchestration import RuntimeBackend
from swarm_core.strategy_meeting import StrategyMeetingResult, StrategyMeetingStatus


@dataclass
class FakeMeetingClient:
    def chat_with_agent(self, worker_name, agent_id, messages):
        return {
            "worker_name": worker_name,
            "content": f"{agent_id} recommends the cautious rollout.",
            "success": True,
            "error": None,
            "tokens_used": 7,
        }

    def chat_with_escalation(self, worker_name, messages, preferred_tier="tier3_paid", model_name="claude-sonnet-4-6"):
        return {
            "success": True,
            "content": (
                '{"strategy":"Adopt a cautious rollout.",'
                '"consensus_points":["Protect reliability"],'
                '"dissent_points":["Some prefer speed"],'
                '"next_actions":["Define the canary gates"]}'
            ),
            "tokens_used": 13,
        }


class EmptyMeetingClient:
    def __init__(self, *args, **kwargs):
        pass

    def chat_with_agent(self, worker_name, agent_id, messages):
        return {
            "worker_name": worker_name,
            "content": "",
            "success": True,
            "error": None,
            "tokens_used": 0,
        }

    def chat_with_escalation(self, worker_name, messages, preferred_tier="tier3_paid", model_name="claude-sonnet-4-6"):
        return {
            "success": True,
            "content": "",
            "tokens_used": 0,
        }


class RecordingMeetingClient:
    def __init__(self, *args, **kwargs):
        self.calls: list[tuple[str, str]] = []

    def chat_with_agent(self, worker_name, agent_id, messages):
        self.calls.append(("agent", worker_name))
        return {
            "worker_name": worker_name,
            "content": "",
            "success": True,
            "error": None,
            "tokens_used": 0,
        }

    def chat_with_escalation(self, worker_name, messages, preferred_tier="tier3_paid", model_name="claude-sonnet-4-6"):
        self.calls.append(("escalation", worker_name))
        if worker_name == "meeting_facilitator":
            return {
                "success": True,
                "content": "Summary from escalation with explicit probability ranges.",
                "tokens_used": 11,
            }
        if worker_name == "meeting_chair":
            return {
                "success": True,
                "content": (
                    '{"strategy":"Pick the validated path and keep no-trade as the default gate.",'
                    '"consensus_points":["Protect reliability"],'
                    '"dissent_points":["Some prefer speed"],'
                    '"next_actions":["Define the canary gates"]}'
                ),
                "tokens_used": 12,
            }
        return {
            "success": True,
            "content": (
                "Thesis: Use the richer legacy escalation path.\n"
                "Recommended actions:\n"
                "- Quantify the gain probability.\n"
                "Key risks:\n"
                "- Fees may erase the edge.\n"
                "Disagreements:\n"
                "- Need a sharper no-trade comparison."
            ),
            "tokens_used": 9,
        }


def test_quantitative_strategy_meeting_prompts_emphasize_probability_arbitrage_and_no_trade() -> None:
    participant_prompt = _build_participant_prompt(
        participant="architect",
        round_index=1,
        phase="critique",
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect", "research"],
        prior_summary="The current edge is not yet validated.",
        critique_focus="execution drag",
    )
    summary_prompt = _build_summary_prompt(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        round_index=1,
        phase="critique",
        turns=[
            MeetingTurnDraft(
                thesis="Forecast alpha looks modest.",
                recommended_actions=["Measure the expected-value delta"],
                key_risks=["Fees may erase the edge"],
                disagreements=["Need to compare against no-trade"],
            )
        ],
        prior_summary="The current edge is not yet validated.",
    )
    synthesis_prompt = _build_synthesis_prompt(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect", "research"],
        phase="synthesis",
        turns=[
            MeetingTurnDraft(
                thesis="The strongest path is still unproven.",
                recommended_actions=["Check shadow results"],
                key_risks=["Execution drag"],
                disagreements=["Forecast vs arbitrage"],
            )
        ],
        summary="Use the path with the best gain probability only if it survives costs.",
    )

    assert "probability" in participant_prompt.lower()
    assert "no-trade" in participant_prompt.lower()
    assert "arbitrage alpha" in participant_prompt.lower()
    assert "expected-value" in participant_prompt.lower()
    assert "role grounding:" in participant_prompt.lower()
    assert "current meeting memory" in participant_prompt.lower()
    assert "memory discipline:" in participant_prompt.lower()
    assert "coherence, sequencing, and decision gates" in participant_prompt.lower()
    assert "quantitative guidance" in summary_prompt.lower()
    assert "invalidat" in summary_prompt.lower()
    assert "expected-value" in summary_prompt.lower()
    assert "forecast alpha" in synthesis_prompt.lower()
    assert "validation gate" in synthesis_prompt.lower()
    assert "no-trade" in synthesis_prompt.lower()
    assert "return only json" in synthesis_prompt.lower()
    assert "preserve the strongest dissent point" in synthesis_prompt.lower()


def test_quantitative_strategy_meeting_runtime_uses_specific_legacy_fallbacks_when_structured_runtime_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.OpenClawClient",
        EmptyMeetingClient,
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("temporary connection issue")),
    )
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: None)

    runtime = PydanticAIStrategyMeetingRuntime()

    draft = runtime.generate_turn(
        participant="architect",
        round_index=1,
        phase="independent",
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect", "research"],
        prior_summary="The current edge is not yet validated.",
    )
    summary = runtime.summarize_round(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        round_index=1,
        phase="critique",
        turns=[draft],
        prior_summary="The current edge is not yet validated.",
    )
    synthesis = runtime.synthesize_meeting(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect", "research"],
        phase="synthesis",
        turns=[draft],
        summary=summary.summary,
    )

    assert "no-trade" in draft.thesis.lower()
    assert any("probability" in action.lower() for action in draft.recommended_actions)
    assert any("slippage" in risk.lower() for risk in draft.key_risks)
    assert any("prediction, arbitrage, or filtering" in item.lower() or "no-trade" in item.lower() for item in draft.disagreements)
    assert "forecast alpha" in summary.summary.lower()
    assert "probability ranges" in summary.summary.lower()
    assert "no-trade" in summary.summary.lower()
    assert "structured runtime degraded to legacy" in summary.summary.lower()
    assert "best validated gain probability" in synthesis.strategy.lower()
    assert "structured runtime degraded to legacy" in synthesis.strategy.lower()
    assert any("validation" in action.lower() or "shadow" in action.lower() for action in synthesis.next_actions)
    assert any("prediction, arbitrage, or abstention" in item.lower() or "no-trade" in item.lower() for item in synthesis.dissent_points)


def test_legacy_transport_uses_escalation_for_summary_and_synthesis_even_without_injected_test_client(monkeypatch) -> None:
    recording_client = RecordingMeetingClient()
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.OpenClawClient",
        lambda config_path="config.yaml": recording_client,
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("temporary connection issue")),
    )
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: None)

    runtime = PydanticAIStrategyMeetingRuntime()
    draft = runtime.generate_turn(
        participant="architect",
        round_index=1,
        phase="independent",
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect"],
        prior_summary="",
    )
    summary = runtime.summarize_round(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        round_index=1,
        phase="critique",
        turns=[draft],
        prior_summary="",
    )
    synthesis = runtime.synthesize_meeting(
        topic="Estimate the probability of gain for prediction markets arbitrage",
        objective="Compare forecast alpha, arbitrage alpha, and no-trade",
        participants=["architect"],
        phase="synthesis",
        turns=[draft],
        summary=summary.summary,
    )

    assert ("escalation", "strategy_meeting_architect") in recording_client.calls
    assert ("escalation", "meeting_facilitator") in recording_client.calls
    assert ("escalation", "meeting_chair") in recording_client.calls
    assert "probability ranges" in summary.summary.lower()
    assert "structured runtime degraded to legacy" in summary.summary.lower()
    assert "validated path" in synthesis.strategy.lower()
    assert "structured runtime degraded to legacy" in synthesis.strategy.lower()


def test_strategy_meeting_runtime_uses_pydanticai_and_persists_artifact(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_strategy_meeting_sync(**kwargs):
        calls.append(kwargs)
        return StrategyMeetingResult(
            meeting_id="meeting_demo",
            topic=kwargs["topic"],
            objective=kwargs.get("objective") or "Define the best strategy for the topic",
            status=StrategyMeetingStatus.completed,
            participants=list(kwargs.get("participants") or []),
            requested_participants=list(kwargs.get("participants") or []),
            requested_max_agents=kwargs.get("max_agents", 0),
            requested_rounds=kwargs.get("rounds", 0),
            rounds_completed=kwargs.get("rounds", 0),
            strategy="Adopt a cautious rollout.",
            consensus_points=["Protect reliability"],
            dissent_points=["Some prefer speed"],
            next_actions=["Define the canary gates"],
            metadata={"runtime_used": RuntimeBackend.pydanticai.value, "fallback_used": False},
            persisted_path=str(tmp_path / "meeting_demo.json") if kwargs.get("persist") else None,
        )

    monkeypatch.setattr("swarm_core.strategy_meeting.run_strategy_meeting_sync", fake_run_strategy_meeting_sync)

    result = run_strategy_meeting_runtime(
        topic="Choose the product launch approach",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=1,
        persist=True,
        output_dir=tmp_path,
        client=FakeMeetingClient(),
        runtime=RuntimeBackend.pydanticai,
        allow_fallback=False,
    )

    assert result.status == StrategyMeetingStatus.completed
    assert result.metadata["runtime_used"] == RuntimeBackend.pydanticai.value
    assert result.metadata["fallback_used"] is False
    assert result.strategy == "Adopt a cautious rollout."
    assert result.persisted_path is not None
    assert len(calls) == 1
    assert calls[0]["runtime"] == RuntimeBackend.pydanticai.value
    assert Path(result.persisted_path).exists()


def test_strategy_meeting_runtime_falls_back_to_legacy_when_requested(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_strategy_meeting_sync(**kwargs):
        calls.append(kwargs)
        if kwargs["runtime"] == RuntimeBackend.pydanticai.value:
            raise RuntimeError("pydanticai unavailable")
        return StrategyMeetingResult(
            meeting_id="meeting_demo",
            topic=kwargs["topic"],
            objective=kwargs.get("objective") or "Define the best strategy for the topic",
            status=StrategyMeetingStatus.completed,
            participants=list(kwargs.get("participants") or []),
            requested_participants=list(kwargs.get("participants") or []),
            requested_max_agents=kwargs.get("max_agents", 0),
            requested_rounds=kwargs.get("rounds", 0),
            rounds_completed=kwargs.get("rounds", 0),
            strategy="Adopt a cautious rollout.",
            consensus_points=["Protect reliability"],
            dissent_points=["Some prefer speed"],
            next_actions=["Define the canary gates"],
            metadata={"runtime_used": RuntimeBackend.legacy.value, "fallback_used": True},
        )

    monkeypatch.setattr("swarm_core.strategy_meeting.run_strategy_meeting_sync", fake_run_strategy_meeting_sync)

    result = run_strategy_meeting_runtime(
        topic="Choose the product launch approach",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=1,
        persist=False,
        output_dir=tmp_path,
        client=FakeMeetingClient(),
        runtime=RuntimeBackend.pydanticai,
        allow_fallback=True,
    )

    assert result.status == StrategyMeetingStatus.completed
    assert len(calls) == 2
    assert calls[0]["runtime"] == RuntimeBackend.pydanticai.value
    assert calls[1]["runtime"] == RuntimeBackend.legacy.value
    assert result.metadata["runtime_requested"] == RuntimeBackend.pydanticai.value
    assert result.metadata["runtime_used"] == RuntimeBackend.legacy.value
    assert result.metadata["fallback_used"] is True


def test_structured_runtime_retries_retryable_errors_before_succeeding(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )

    def fake_run_structured_agent(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionError("temporary connection issue")
        return SimpleNamespace(
            runtime_used=StructuredRuntimeBackend.pydanticai,
            fallback_used=False,
            output=MeetingTurnDraft(thesis="Use the structured runtime after a retry."),
        )

    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.run_structured_agent", fake_run_structured_agent)
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: sleeps.append(delay))

    runtime = PydanticAIStrategyMeetingRuntime(legacy_client=FakeMeetingClient())
    draft = runtime.generate_turn(
        participant="architect",
        round_index=1,
        phase="independent",
        topic="retry the meeting runtime",
        objective="verify retry handling",
        participants=["architect"],
        prior_summary="",
    )

    assert draft.thesis == "Use the structured runtime after a retry."
    assert calls["count"] == 2
    assert runtime.last_fallback_used is False
    assert runtime.last_attempt_count == 2
    assert runtime.last_retry_count == 1
    assert runtime.last_retry_reasons == ["connection_error"]
    assert runtime.last_backoff_schedule == [
        {
            "attempt": 1,
            "delay_seconds": 0.15,
            "error_category": "connection_error",
            "retryable": True,
        }
    ]
    assert runtime.last_backoff_total_seconds == 0.15
    assert sleeps == [0.15]
    assert runtime.last_fallback_mode == "structured_success_after_retry"
    assert runtime.last_retry_budget_exhausted is False
    assert runtime.last_immediate_fallback is False
    assert runtime.last_error_retryable is None


def test_structured_runtime_falls_back_after_retry_budget_is_exhausted(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("temporary connection issue")),
    )
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: sleeps.append(delay))

    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting._LegacyMeetingTransport.generate_turn",
        lambda self, **kwargs: MeetingTurnDraft(thesis="Fallback draft"),
    )

    runtime = PydanticAIStrategyMeetingRuntime(legacy_client=FakeMeetingClient())

    draft = runtime.generate_turn(
        participant="architect",
        round_index=1,
        phase="independent",
        topic="fallback the meeting runtime",
        objective="verify fallback after retries",
        participants=["architect"],
        prior_summary="",
    )

    assert draft.thesis == "Fallback draft"
    assert runtime.last_fallback_used is True
    assert runtime.runtime_used == StructuredRuntimeBackend.legacy
    assert runtime.last_attempt_count == 2
    assert runtime.last_retry_count == 1
    assert runtime.last_error_category == "connection_error"
    assert runtime.last_retry_reasons == ["connection_error"]
    assert runtime.last_backoff_schedule == [
        {
            "attempt": 1,
            "delay_seconds": 0.15,
            "error_category": "connection_error",
            "retryable": True,
        }
    ]
    assert runtime.last_backoff_total_seconds == 0.15
    assert sleeps == [0.15]
    assert runtime.last_fallback_mode == "retry_budget_exhausted"
    assert runtime.last_retry_budget_exhausted is True
    assert runtime.last_immediate_fallback is False
    assert runtime.last_error_retryable is True


def test_structured_runtime_uses_extra_retry_budget_for_round_and_synthesis_outputs(monkeypatch) -> None:
    sleeps: list[float] = []
    calls = {"count": 0}

    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )

    def fake_run_structured_agent(**kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("temporary connection issue")
        return SimpleNamespace(
            runtime_used=StructuredRuntimeBackend.pydanticai,
            fallback_used=False,
            output=SimpleNamespace(
                summary="Recovered summary",
                top_options=[],
                risks=[],
                unresolved_disagreements=[],
            ),
        )

    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.run_structured_agent", fake_run_structured_agent)
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: sleeps.append(delay))

    runtime = PydanticAIStrategyMeetingRuntime(legacy_client=FakeMeetingClient())
    summary = runtime.summarize_round(
        topic="retry the meeting runtime",
        objective="verify retry handling",
        round_index=1,
        phase="critique",
        turns=[MeetingTurnDraft(thesis="Candidate edge", recommended_actions=[], key_risks=[], disagreements=[])],
        prior_summary="",
    )

    assert summary.summary == "Recovered summary"
    assert calls["count"] == 3
    assert runtime.last_fallback_used is False
    assert runtime.last_attempt_count == 3
    assert runtime.last_retry_count == 2
    assert runtime.last_retry_reasons == ["connection_error", "connection_error"]
    assert sleeps == [0.15, 0.3]


def test_structured_runtime_uses_immediate_fallback_for_non_retryable_error(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("schema validation failed")),
    )
    monkeypatch.setattr("runtime_pydanticai.strategy_meeting.time.sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr(
        "runtime_pydanticai.strategy_meeting._LegacyMeetingTransport.generate_turn",
        lambda self, **kwargs: MeetingTurnDraft(thesis="Immediate fallback draft"),
    )

    runtime = PydanticAIStrategyMeetingRuntime(legacy_client=FakeMeetingClient())

    draft = runtime.generate_turn(
        participant="architect",
        round_index=1,
        phase="independent",
        topic="immediate fallback for meeting runtime",
        objective="verify immediate fallback handling",
        participants=["architect"],
        prior_summary="",
    )

    assert draft.thesis == "Immediate fallback draft"
    assert runtime.last_fallback_used is True
    assert runtime.runtime_used == StructuredRuntimeBackend.legacy
    assert runtime.last_attempt_count == 1
    assert runtime.last_retry_count == 0
    assert runtime.last_retry_reasons == []
    assert runtime.last_backoff_schedule == []
    assert runtime.last_backoff_total_seconds == 0.0
    assert sleeps == []
    assert runtime.last_fallback_mode == "immediate_non_retryable"
    assert runtime.last_retry_budget_exhausted is False
    assert runtime.last_immediate_fallback is True
    assert runtime.last_error_category == "schema_error"
    assert runtime.last_error_retryable is False
