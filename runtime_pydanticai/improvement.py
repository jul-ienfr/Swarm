from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from pydantic import BaseModel, Field

from .factory import RuntimeAvailabilityError, load_runtime_model_config, run_structured_agent
from .models import ImprovementCritiqueDraft, RuntimeBackend, RuntimeFallbackPolicy


class ConfigCritiqueDraft(BaseModel):
    summary: str
    rationale: list[str] = Field(default_factory=list)
    orchestrator_updates: dict[str, int] = Field(default_factory=dict)
    studio_dev_updates: dict[str, bool] = Field(default_factory=dict)
    veille_updates: dict[str, int] = Field(default_factory=dict)
    top_level_updates: dict[str, int | bool] = Field(default_factory=dict)
    risk_level: str = "low"
    requires_human_review: bool = False


@dataclass(slots=True)
class _RuleBasedConfigCritic:
    def propose(self, snapshot: dict[str, Any], trajectories: list[dict[str, Any]]) -> ConfigCritiqueDraft:
        return ConfigCritiqueDraft(
            summary="Fallback config critic retained the current bounded config and proposed no risky changes.",
            rationale=[
                "PydanticAI runtime unavailable or failed for this round.",
                "Keeping config changes bounded is safer than forcing an uncertain change.",
            ],
            risk_level="low",
            requires_human_review=False,
        )


@dataclass(slots=True)
class _RuleBasedHarnessCritic:
    def propose(self, snapshot: dict[str, Any], trajectories: list[dict[str, Any]]) -> ImprovementCritiqueDraft:
        return ImprovementCritiqueDraft(
            summary="Fallback harness critic suggested safer fallback handling and calibrated sampling.",
            rationale=[
                "PydanticAI runtime unavailable or failed for this round.",
                "Failures should first be turned into safer workflow rules.",
            ],
            workflow_rules_to_add=[
                "When an engine is unavailable, produce a normalized fallback recommendation instead of retrying blindly."
            ],
            sampling_param_overrides={"temperature": 0.3},
            risk_level="low",
            requires_human_review=False,
        )


class _ResilientStructuredCriticMixin:
    max_structured_attempts: int = 2
    base_backoff_seconds: float = 0.15
    max_backoff_seconds: float = 0.75

    def _reset_resilience_state(self) -> None:
        self.last_runtime_used = RuntimeBackend.pydanticai
        self.last_fallback_used = False
        self.last_fallback_mode: str | None = None
        self.last_error: str | None = None
        self.last_error_category: str | None = None
        self.last_error_retryable: bool | None = None
        self.last_attempt_count: int = 0
        self.last_retry_count: int = 0
        self.last_retry_reasons: list[str] = []
        self.last_backoff_schedule: list[dict[str, Any]] = []
        self.last_backoff_total_seconds: float = 0.0
        self.last_retry_budget_exhausted: bool = False
        self.last_immediate_fallback: bool = False

    @property
    def runtime_resilience(self) -> dict[str, Any]:
        status = "healthy"
        if self.last_fallback_used or self.last_error is not None:
            status = "degraded"
        elif self.last_retry_count > 0 or self.last_backoff_total_seconds > 0:
            status = "guarded"
        summary_parts = [status]
        if self.last_retry_count:
            summary_parts.append(f"retries={self.last_retry_count}")
        if self.last_fallback_mode:
            summary_parts.append(f"fallback={self.last_fallback_mode}")
        if self.last_error_category and status != "healthy":
            summary_parts.append(f"error={self.last_error_category}")
        if self.last_backoff_total_seconds:
            summary_parts.append(f"backoff={self.last_backoff_total_seconds:.3f}s")
        return {
            "status": status,
            "summary": " | ".join(summary_parts),
            "runtime_used": self.last_runtime_used.value,
            "fallback_used": self.last_fallback_used,
            "fallback_mode": self.last_fallback_mode,
            "attempt_count": self.last_attempt_count,
            "retry_count": self.last_retry_count,
            "retry_reasons": list(self.last_retry_reasons),
            "backoff_schedule": list(self.last_backoff_schedule),
            "backoff_total_seconds": self.last_backoff_total_seconds,
            "error_category": self.last_error_category,
            "error_retryable": self.last_error_retryable,
            "retry_budget_exhausted": self.last_retry_budget_exhausted,
            "immediate_fallback": self.last_immediate_fallback,
        }

    def _run_with_resilience(
        self,
        *,
        output_type: type[Any],
        system_prompt: str,
        user_prompt: str,
        agent_name: str,
        fallback,
        fallback_policy: RuntimeFallbackPolicy,
        config: Any,
    ) -> Any:
        self._reset_resilience_state()
        if fallback_policy == RuntimeFallbackPolicy.always:
            self.last_runtime_used = RuntimeBackend.legacy
            self.last_fallback_used = True
            self.last_fallback_mode = "policy_always"
            self.last_attempt_count = 1
            self.last_immediate_fallback = True
            return fallback()

        max_attempts = max(1, int(self.max_structured_attempts))
        for attempt_index in range(1, max_attempts + 1):
            self.last_attempt_count = attempt_index
            try:
                result = run_structured_agent(
                    output_type=output_type,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    agent_name=agent_name,
                    config=config,
                )
                self.last_runtime_used = _coerce_runtime_backend(result.runtime_used)
                self.last_fallback_used = bool(result.fallback_used)
                self.last_error = None
                self.last_error_category = None
                self.last_error_retryable = None
                self.last_fallback_mode = "structured_success"
                return result.output
            except Exception as exc:
                error_category = _classify_runtime_error(exc)
                retryable = _is_retryable_runtime_error(error_category)
                self.last_error = str(exc)
                self.last_error_category = error_category
                self.last_error_retryable = retryable
                if retryable and attempt_index < max_attempts:
                    delay_seconds = _structured_backoff_delay(
                        attempt_index=attempt_index,
                        base_backoff_seconds=self.base_backoff_seconds,
                        max_backoff_seconds=self.max_backoff_seconds,
                    )
                    self.last_retry_count += 1
                    self.last_retry_reasons.append(error_category)
                    self.last_backoff_schedule.append(
                        {
                            "attempt": attempt_index,
                            "delay_seconds": delay_seconds,
                            "error_category": error_category,
                            "retryable": True,
                        }
                    )
                    self.last_backoff_total_seconds += delay_seconds
                    time.sleep(delay_seconds)
                    continue
                self.last_fallback_mode = "retry_budget_exhausted" if retryable else "immediate_non_retryable"
                self.last_retry_budget_exhausted = bool(retryable and attempt_index >= max_attempts)
                self.last_immediate_fallback = not retryable
                if fallback_policy == RuntimeFallbackPolicy.never:
                    raise
                self.last_runtime_used = RuntimeBackend.legacy
                self.last_fallback_used = True
                return fallback()

        if fallback_policy == RuntimeFallbackPolicy.never:
            raise RuntimeAvailabilityError("structured runtime attempts exhausted")
        self.last_runtime_used = RuntimeBackend.legacy
        self.last_fallback_used = True
        self.last_fallback_mode = "retry_budget_exhausted"
        self.last_retry_budget_exhausted = True
        return fallback()


class PydanticAIConfigCritic(_ResilientStructuredCriticMixin):
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        fallback_policy: RuntimeFallbackPolicy = RuntimeFallbackPolicy.on_error,
        model_name: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.fallback_policy = fallback_policy
        self._config = load_runtime_model_config(config_path=config_path, model_name=model_name)
        self._fallback = _RuleBasedConfigCritic()
        self._reset_resilience_state()

    @property
    def runtime_used(self) -> RuntimeBackend:
        return self.last_runtime_used

    @property
    def fallback_used(self) -> bool:
        return self.last_fallback_used

    def analyze(self, *, snapshot: dict[str, Any], trajectories: list[dict[str, Any]]) -> ConfigCritiqueDraft:
        prompt = (
            f"Snapshot: {snapshot}\n"
            f"Trajectories: {trajectories}\n"
            "Propose a conservative config improvement with bounded changes only."
        )
        return self._run_with_resilience(
            output_type=ConfigCritiqueDraft,
            system_prompt=(
                "You are a configuration critic for a multi-agent runtime.\n"
                "Return a safe, bounded proposal only."
            ),
            user_prompt=prompt,
            agent_name="config_critic",
            fallback=lambda: self._fallback.propose(snapshot, trajectories),
            fallback_policy=self.fallback_policy,
            config=self._config,
        )

    def propose(self, snapshot: dict[str, Any], trajectories: list[dict[str, Any]]) -> ConfigCritiqueDraft:
        return self.analyze(snapshot=snapshot, trajectories=trajectories)


class PydanticAIHarnessCritic(_ResilientStructuredCriticMixin):
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        fallback_policy: RuntimeFallbackPolicy = RuntimeFallbackPolicy.on_error,
        model_name: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.fallback_policy = fallback_policy
        self._config = load_runtime_model_config(config_path=config_path, model_name=model_name)
        self._fallback = _RuleBasedHarnessCritic()
        self._reset_resilience_state()

    @property
    def runtime_used(self) -> RuntimeBackend:
        return self.last_runtime_used

    @property
    def fallback_used(self) -> bool:
        return self.last_fallback_used

    def analyze_failures(
        self,
        *,
        current_snapshot: dict[str, Any],
        trajectories: list[dict[str, Any]],
    ) -> ImprovementCritiqueDraft:
        prompt = (
            f"Snapshot: {current_snapshot}\n"
            f"Trajectories: {trajectories}\n"
            "Propose a conservative harness improvement with bounded changes only."
        )
        return self._run_with_resilience(
            output_type=ImprovementCritiqueDraft,
            system_prompt=(
                "You are a harness critic for a multi-agent runtime.\n"
                "Return safe workflow rule changes and calibrated sampling only."
            ),
            user_prompt=prompt,
            agent_name="harness_critic",
            fallback=lambda: self._fallback.propose(current_snapshot, trajectories),
            fallback_policy=self.fallback_policy,
            config=self._config,
        )

    def propose(self, snapshot: dict[str, Any], trajectories: list[dict[str, Any]]) -> ImprovementCritiqueDraft:
        return self.analyze_failures(current_snapshot=snapshot, trajectories=trajectories)


def _coerce_runtime_backend(value: Any) -> RuntimeBackend:
    if isinstance(value, RuntimeBackend):
        return value
    try:
        return RuntimeBackend(str(value))
    except ValueError:
        return RuntimeBackend.legacy


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
    if "schema" in message or "json" in message or "validation" in message:
        return "schema_error"
    if "unavailable" in message or "not configured" in message:
        return "availability_error"
    return "unexpected_error"


def _is_retryable_runtime_error(category: str) -> bool:
    return category in {"timeout_error", "connection_error", "availability_error"}


def _structured_backoff_delay(
    *,
    attempt_index: int,
    base_backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    delay_seconds = max(0.0, float(base_backoff_seconds) * max(1, int(attempt_index)))
    return min(delay_seconds, max_backoff_seconds)
