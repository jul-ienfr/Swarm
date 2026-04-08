from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from .factory import RuntimeAvailabilityError, load_runtime_model_config, run_structured_agent
from .models import (
    RuntimeBackend,
    RuntimeFallbackPolicy,
    SupervisorAssignment,
    SupervisorPlan,
    SupervisorPlanDraft,
)


class SupervisorPlanningInput(BaseModel):
    goal: str
    plan: list[str] = Field(default_factory=list)
    recent_outputs: list[dict[str, Any]] = Field(default_factory=list)
    registry_catalog: str = ""
    replan_reason: str | None = None
    current_intent: dict[str, Any] | None = None
    goal_complete_hint: bool = False
    max_assignments: int = 4


class SupervisorPlanWithResilience(SupervisorPlan):
    last_attempt_count: int = 0
    last_retry_count: int = 0
    last_retry_reasons: list[str] = Field(default_factory=list)
    last_backoff_schedule: list[dict[str, Any]] = Field(default_factory=list)
    last_backoff_total_seconds: float = 0.0
    last_retry_budget_exhausted: bool = False
    last_immediate_fallback: bool = False
    last_fallback_mode: str | None = None
    last_error: str | None = None
    last_error_category: str | None = None
    last_error_retryable: bool | None = None
    runtime_resilience: dict[str, Any] | None = None


class _RuleBasedSupervisorPlanner:
    @staticmethod
    def plan(planning_input: SupervisorPlanningInput) -> SupervisorPlan:
        if planning_input.goal_complete_hint or "COMPLETE" in planning_input.goal.upper():
            return SupervisorPlan(
                assignments=[],
                complete=True,
                rationale="Legacy fallback detected completion condition.",
                runtime_used=RuntimeBackend.legacy,
                fallback_used=True,
                model_name=None,
                provider_base_url=None,
                error=None,
            )

        next_speaker = "architect"
        if planning_input.plan:
            next_speaker = "architect"
        if planning_input.replan_reason:
            next_speaker = "architect"

        instruction = (
            f"Goal: {planning_input.goal}\n"
            f"Plan: {planning_input.plan}\n"
            f"Recent outputs: {planning_input.recent_outputs[-3:]}\n"
        )
        if planning_input.replan_reason:
            instruction += f"Replan reason: {planning_input.replan_reason}\n"

        return SupervisorPlan(
            assignments=[
                SupervisorAssignment(
                    speaker=next_speaker,
                    instruction=instruction.strip(),
                    priority=0,
                    rationale="Legacy fallback planner selected the primary architect role.",
                )
            ],
            complete=False,
            rationale="Legacy fallback planner produced a single safe assignment.",
            runtime_used=RuntimeBackend.legacy,
            fallback_used=True,
            model_name=None,
            provider_base_url=None,
            error=None,
        )


class PydanticAISupervisorPlanner:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        fallback_policy: RuntimeFallbackPolicy = RuntimeFallbackPolicy.on_error,
    ) -> None:
        self.config_path = config_path
        self.fallback_policy = fallback_policy
        self.max_structured_attempts = 2
        self.base_backoff_seconds = 0.15
        self.max_backoff_seconds = 0.75
        self._config = load_runtime_model_config(config_path=self.config_path)

    def available(self) -> bool:
        return self._config.base_url is not None

    def plan_assignments(self, planning_input: SupervisorPlanningInput) -> SupervisorPlan:
        if self.fallback_policy == RuntimeFallbackPolicy.always:
            return self._enrich_plan(
                _RuleBasedSupervisorPlanner.plan(planning_input),
                last_attempt_count=1,
                last_retry_count=0,
                last_retry_reasons=[],
                last_backoff_schedule=[],
                last_backoff_total_seconds=0.0,
                last_retry_budget_exhausted=False,
                last_immediate_fallback=True,
                last_fallback_mode="policy_always",
                last_error=None,
                last_error_category=None,
                last_error_retryable=None,
            )

        max_attempts = max(1, int(self.max_structured_attempts))
        last_error: str | None = None
        last_error_category: str | None = None
        last_error_retryable: bool | None = None
        last_retry_reasons: list[str] = []
        last_backoff_schedule: list[dict[str, Any]] = []
        last_backoff_total_seconds = 0.0
        last_retry_count = 0

        for attempt_index in range(1, max_attempts + 1):
            try:
                result = run_structured_agent(
                    output_type=SupervisorPlanDraft,
                    system_prompt=(
                        "You are the orchestrator of a multi-agent swarm.\n"
                        "Plan the next assignment(s) from the available workers.\n"
                        "Return a structured plan with assignments ordered by priority.\n"
                        "If the goal is achieved, return complete=true and no assignments.\n"
                        "Never invent unavailable workers."
                    ),
                    user_prompt=self._build_prompt(planning_input),
                    agent_name="swarm_supervisor_planner",
                    config=self._config,
                )
                draft = result.output
                runtime_used = result.runtime_used
                fallback_used = bool(result.fallback_used)
                fallback_mode = "structured_success"
                if fallback_used or runtime_used != RuntimeBackend.pydanticai:
                    fallback_mode = "structured_degraded_success"
                return self._enrich_plan(
                    SupervisorPlan(
                        assignments=[
                            SupervisorAssignment(
                                speaker=assignment.speaker,
                                instruction=assignment.instruction,
                                priority=assignment.priority,
                                rationale=assignment.rationale,
                            )
                            for assignment in draft.assignments
                        ],
                        complete=draft.complete,
                        rationale=draft.rationale,
                        runtime_used=runtime_used,
                        fallback_used=fallback_used,
                        model_name=result.model_name,
                        provider_base_url=result.provider_base_url,
                        error=result.error,
                    ),
                    last_attempt_count=attempt_index,
                    last_retry_count=last_retry_count,
                    last_retry_reasons=last_retry_reasons,
                    last_backoff_schedule=last_backoff_schedule,
                    last_backoff_total_seconds=last_backoff_total_seconds,
                    last_retry_budget_exhausted=False,
                    last_immediate_fallback=False,
                    last_fallback_mode=fallback_mode,
                    last_error=None,
                    last_error_category=None,
                    last_error_retryable=None,
                )
            except Exception as exc:
                last_error = str(exc)
                last_error_category = _classify_runtime_error(exc)
                last_error_retryable = _is_retryable_runtime_error(last_error_category)
                if last_error_retryable and attempt_index < max_attempts:
                    delay_seconds = _structured_backoff_delay(
                        attempt_index=attempt_index,
                        base_backoff_seconds=self.base_backoff_seconds,
                        max_backoff_seconds=self.max_backoff_seconds,
                    )
                    last_retry_count += 1
                    last_retry_reasons.append(last_error_category)
                    last_backoff_schedule.append(
                        {
                            "attempt": attempt_index,
                            "delay_seconds": delay_seconds,
                            "error_category": last_error_category,
                            "retryable": True,
                        }
                    )
                    last_backoff_total_seconds += delay_seconds
                    time.sleep(delay_seconds)
                    continue
                if self.fallback_policy == RuntimeFallbackPolicy.never:
                    raise RuntimeAvailabilityError(str(exc)) from exc
                fallback_plan = _RuleBasedSupervisorPlanner.plan(planning_input)
                return self._enrich_plan(
                    fallback_plan,
                    last_attempt_count=attempt_index,
                    last_retry_count=last_retry_count,
                    last_retry_reasons=last_retry_reasons,
                    last_backoff_schedule=last_backoff_schedule,
                    last_backoff_total_seconds=last_backoff_total_seconds,
                    last_retry_budget_exhausted=bool(last_error_retryable and attempt_index >= max_attempts),
                    last_immediate_fallback=not bool(last_error_retryable),
                    last_fallback_mode="retry_budget_exhausted" if last_error_retryable else "immediate_non_retryable",
                    last_error=last_error,
                    last_error_category=last_error_category,
                    last_error_retryable=last_error_retryable,
                )

        raise RuntimeAvailabilityError("structured runtime attempts exhausted")

    @staticmethod
    def _build_prompt(planning_input: SupervisorPlanningInput) -> str:
        lines = [
            f"Goal: {planning_input.goal}",
            f"Plan: {planning_input.plan}",
            f"Recent outputs: {planning_input.recent_outputs[-3:]}",
            f"Registry catalog: {planning_input.registry_catalog}",
            f"Current intent: {planning_input.current_intent}",
            f"Goal complete hint: {planning_input.goal_complete_hint}",
            f"Max assignments: {planning_input.max_assignments}",
        ]
        if planning_input.replan_reason:
            lines.append(f"Replan reason: {planning_input.replan_reason}")
        return "\n".join(lines)

    @staticmethod
    def _enrich_plan(
        base_plan: SupervisorPlan,
        *,
        last_attempt_count: int,
        last_retry_count: int,
        last_retry_reasons: list[str],
        last_backoff_schedule: list[dict[str, Any]],
        last_backoff_total_seconds: float,
        last_retry_budget_exhausted: bool,
        last_immediate_fallback: bool,
        last_fallback_mode: str | None,
        last_error: str | None,
        last_error_category: str | None,
        last_error_retryable: bool | None,
    ) -> SupervisorPlanWithResilience:
        plan = SupervisorPlanWithResilience.model_validate(base_plan.model_dump(mode="python"))
        plan.last_attempt_count = max(0, int(last_attempt_count))
        plan.last_retry_count = max(0, int(last_retry_count))
        plan.last_retry_reasons = list(last_retry_reasons)
        plan.last_backoff_schedule = list(last_backoff_schedule)
        plan.last_backoff_total_seconds = max(0.0, float(last_backoff_total_seconds))
        plan.last_retry_budget_exhausted = bool(last_retry_budget_exhausted)
        plan.last_immediate_fallback = bool(last_immediate_fallback)
        plan.last_fallback_mode = last_fallback_mode
        plan.last_error = last_error
        plan.last_error_category = last_error_category
        plan.last_error_retryable = last_error_retryable
        plan.runtime_resilience = _build_supervisor_runtime_resilience_summary(plan)
        return plan


def _classify_runtime_error(exc: Exception) -> str:
    if isinstance(exc, RuntimeAvailabilityError):
        return "availability_error"
    message = str(exc).strip().lower()
    if not message:
        return "unexpected_error"
    if "timeout" in message or "timed out" in message:
        return "timeout_error"
    if "connection" in message or "connect" in message or "refused" in message or "reset" in message:
        return "connection_error"
    if "rate limit" in message or "429" in message:
        return "rate_limit_error"
    if "schema" in message or "json" in message or "validation" in message:
        return "schema_error"
    if "unavailable" in message or "not configured" in message:
        return "availability_error"
    return "unexpected_error"


def _is_retryable_runtime_error(category: str) -> bool:
    return category in {"timeout_error", "connection_error", "availability_error", "rate_limit_error"}


def _structured_backoff_delay(
    *,
    attempt_index: int,
    base_backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    delay_seconds = max(0.0, float(base_backoff_seconds) * max(1, int(attempt_index)))
    return min(delay_seconds, max_backoff_seconds)


def _build_supervisor_runtime_resilience_summary(plan: SupervisorPlanWithResilience) -> dict[str, Any]:
    runtime_requested = RuntimeBackend.pydanticai.value
    runtime_used = getattr(plan.runtime_used, "value", plan.runtime_used)
    runtime_match = runtime_used == runtime_requested
    retry_rate = (plan.last_retry_count / plan.last_attempt_count) if plan.last_attempt_count else 0.0
    status = "healthy"
    score = 1.0
    degraded_reasons: list[str] = []

    if plan.last_retry_count:
        status = "guarded"
        score -= min(0.12, 0.04 * plan.last_retry_count)
        degraded_reasons.append("retries")
    if plan.fallback_used or not runtime_match:
        status = "degraded"
        score -= 0.14
        degraded_reasons.append("fallback_used" if plan.fallback_used else "runtime_mismatch")
    if plan.last_retry_budget_exhausted:
        status = "degraded"
        score -= 0.08
        degraded_reasons.append("retry_budget_exhausted")
    if plan.last_immediate_fallback:
        status = "degraded"
        score -= 0.05
        degraded_reasons.append("immediate_fallback")
    if plan.last_error_retryable is False:
        score -= 0.03

    score = max(0.0, min(1.0, score))
    summary = f"{status}; attempts={plan.last_attempt_count}; retries={plan.last_retry_count}; runtime={runtime_used}"
    if plan.last_fallback_mode:
        summary += f"; fallback={plan.last_fallback_mode}"

    return {
        "status": status,
        "score": score,
        "summary": summary,
        "runtime_requested": runtime_requested,
        "runtime_used": runtime_used,
        "runtime_match": runtime_match,
        "fallback_used": plan.fallback_used,
        "fallback_mode": plan.last_fallback_mode,
        "attempt_count": plan.last_attempt_count,
        "retry_count": plan.last_retry_count,
        "retry_rate": retry_rate,
        "retry_reasons": list(plan.last_retry_reasons),
        "backoff_schedule": list(plan.last_backoff_schedule),
        "backoff_total_seconds": plan.last_backoff_total_seconds,
        "retry_budget_exhausted": plan.last_retry_budget_exhausted,
        "immediate_fallback": plan.last_immediate_fallback,
        "error": plan.last_error,
        "error_category": plan.last_error_category,
        "error_retryable": plan.last_error_retryable,
        "degraded_reasons": degraded_reasons,
    }
