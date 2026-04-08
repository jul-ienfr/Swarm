from __future__ import annotations

from types import SimpleNamespace

from runtime_pydanticai.models import (
    RuntimeBackend as StructuredRuntimeBackend,
    RuntimeFallbackPolicy,
    SupervisorAssignmentDraft,
    SupervisorPlanDraft,
)
from runtime_pydanticai.supervisor import PydanticAISupervisorPlanner, SupervisorPlanningInput


def _fake_planning_input() -> SupervisorPlanningInput:
    return SupervisorPlanningInput(
        goal="Plan the next safe assignment",
        plan=["audit the current plan"],
        recent_outputs=[{"speaker": "architect", "content": "Need a cautious rollout."}],
        registry_catalog="architect, ops, safety",
        replan_reason="The previous assignment stalled.",
        current_intent={"mode": "supervisor"},
        goal_complete_hint=False,
        max_assignments=3,
    )


def test_supervisor_runtime_retries_retryable_errors_before_succeeding(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.supervisor.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )

    def fake_run_structured_agent(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionError("temporary connection issue")
        return SimpleNamespace(
            runtime_used=StructuredRuntimeBackend.pydanticai,
            fallback_used=False,
            model_name="test-model",
            provider_base_url="http://example.test",
            error=None,
            output=SupervisorPlanDraft(
                assignments=[
                    SupervisorAssignmentDraft(
                        speaker="architect",
                        instruction="Review the plan after the retry.",
                        priority=0,
                        rationale="The second attempt is stable.",
                    )
                ],
                complete=False,
                rationale="Structured plan after retry.",
            ),
        )

    monkeypatch.setattr("runtime_pydanticai.supervisor.run_structured_agent", fake_run_structured_agent)
    monkeypatch.setattr("runtime_pydanticai.supervisor.time.sleep", lambda delay: sleeps.append(delay))

    planner = PydanticAISupervisorPlanner(fallback_policy=RuntimeFallbackPolicy.on_error)
    plan = planner.plan_assignments(_fake_planning_input())

    assert calls["count"] == 2
    assert plan.runtime_used == StructuredRuntimeBackend.pydanticai
    assert plan.fallback_used is False
    assert plan.assignments[0].speaker == "architect"
    assert plan.last_attempt_count == 2
    assert plan.last_retry_count == 1
    assert plan.last_retry_reasons == ["connection_error"]
    assert plan.last_backoff_schedule == [
        {
            "attempt": 1,
            "delay_seconds": 0.15,
            "error_category": "connection_error",
            "retryable": True,
        }
    ]
    assert plan.last_backoff_total_seconds == 0.15
    assert sleeps == [0.15]
    assert plan.last_fallback_mode == "structured_success"
    assert plan.last_retry_budget_exhausted is False
    assert plan.last_immediate_fallback is False
    assert plan.last_error is None
    assert plan.runtime_resilience["status"] == "guarded"
    assert plan.runtime_resilience["retry_count"] == 1
    assert plan.runtime_resilience["backoff_total_seconds"] == 0.15
    assert plan.model_dump()["last_retry_count"] == 1
    assert plan.model_dump()["runtime_resilience"]["runtime_used"] == StructuredRuntimeBackend.pydanticai.value


def test_supervisor_runtime_uses_immediate_fallback_for_non_retryable_error(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.supervisor.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.supervisor.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("schema validation failed")),
    )
    monkeypatch.setattr("runtime_pydanticai.supervisor.time.sleep", lambda delay: sleeps.append(delay))

    planner = PydanticAISupervisorPlanner(fallback_policy=RuntimeFallbackPolicy.on_error)
    plan = planner.plan_assignments(_fake_planning_input())

    assert plan.runtime_used == StructuredRuntimeBackend.legacy
    assert plan.fallback_used is True
    assert plan.last_attempt_count == 1
    assert plan.last_retry_count == 0
    assert plan.last_retry_reasons == []
    assert plan.last_backoff_schedule == []
    assert plan.last_backoff_total_seconds == 0.0
    assert sleeps == []
    assert plan.last_fallback_mode == "immediate_non_retryable"
    assert plan.last_retry_budget_exhausted is False
    assert plan.last_immediate_fallback is True
    assert plan.last_error_category == "schema_error"
    assert plan.last_error_retryable is False
    assert plan.runtime_resilience["status"] == "degraded"
    assert plan.runtime_resilience["immediate_fallback"] is True
    assert plan.model_dump()["runtime_resilience"]["fallback_mode"] == "immediate_non_retryable"


def test_supervisor_runtime_marks_retry_budget_exhausted_before_fallback(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.supervisor.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.supervisor.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("temporary connection issue")),
    )
    monkeypatch.setattr("runtime_pydanticai.supervisor.time.sleep", lambda delay: sleeps.append(delay))

    planner = PydanticAISupervisorPlanner(fallback_policy=RuntimeFallbackPolicy.on_error)
    plan = planner.plan_assignments(_fake_planning_input())

    assert plan.runtime_used == StructuredRuntimeBackend.legacy
    assert plan.fallback_used is True
    assert plan.last_attempt_count == 2
    assert plan.last_retry_count == 1
    assert plan.last_retry_reasons == ["connection_error"]
    assert plan.last_backoff_schedule == [
        {
            "attempt": 1,
            "delay_seconds": 0.15,
            "error_category": "connection_error",
            "retryable": True,
        }
    ]
    assert plan.last_backoff_total_seconds == 0.15
    assert sleeps == [0.15]
    assert plan.last_fallback_mode == "retry_budget_exhausted"
    assert plan.last_retry_budget_exhausted is True
    assert plan.last_immediate_fallback is False
    assert plan.last_error_category == "connection_error"
    assert plan.last_error_retryable is True
    assert plan.runtime_resilience["status"] == "degraded"
    assert plan.runtime_resilience["retry_budget_exhausted"] is True
    assert plan.model_dump()["runtime_resilience"]["retry_budget_exhausted"] is True
