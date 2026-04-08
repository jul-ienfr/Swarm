from __future__ import annotations

from types import SimpleNamespace

import pytest

from runtime_pydanticai.improvement import ConfigCritiqueDraft, PydanticAIConfigCritic, PydanticAIHarnessCritic
from runtime_pydanticai.models import ImprovementCritiqueDraft, RuntimeBackend, RuntimeFallbackPolicy


@pytest.mark.parametrize(
    "critic_cls, output_type",
    [
        (PydanticAIConfigCritic, ConfigCritiqueDraft),
        (PydanticAIHarnessCritic, ImprovementCritiqueDraft),
    ],
)
def test_improvement_critics_retry_once_before_succeeding(monkeypatch, critic_cls, output_type) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.improvement.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )

    def fake_run_structured_agent(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionError("temporary connection issue")
        return SimpleNamespace(
            runtime_used=RuntimeBackend.pydanticai,
            fallback_used=False,
            output=output_type(summary="Structured critic succeeded after a retry."),
        )

    monkeypatch.setattr("runtime_pydanticai.improvement.run_structured_agent", fake_run_structured_agent)
    monkeypatch.setattr("runtime_pydanticai.improvement.time.sleep", lambda delay: sleeps.append(delay))

    critic = critic_cls(config_path="config.yaml")
    result = critic.propose(snapshot={"version": "snap_1"}, trajectories=[{"step": 1}])

    assert result.summary == "Structured critic succeeded after a retry."
    assert calls["count"] == 2
    assert sleeps == [0.15]
    assert critic.runtime_used == RuntimeBackend.pydanticai
    assert critic.fallback_used is False
    assert critic.last_attempt_count == 2
    assert critic.last_retry_count == 1
    assert critic.last_retry_reasons == ["connection_error"]
    assert critic.last_backoff_schedule == [
        {
            "attempt": 1,
            "delay_seconds": 0.15,
            "error_category": "connection_error",
            "retryable": True,
        }
    ]
    assert critic.last_backoff_total_seconds == 0.15
    assert critic.last_fallback_mode == "structured_success"
    assert critic.last_error is None
    assert critic.last_error_category is None
    assert critic.last_error_retryable is None

    resilience = critic.runtime_resilience
    assert resilience["status"] == "guarded"
    assert resilience["retry_count"] == 1
    assert resilience["fallback_used"] is False
    assert resilience["runtime_used"] == RuntimeBackend.pydanticai.value


@pytest.mark.parametrize(
    "critic_cls, output_type",
    [
        (PydanticAIConfigCritic, ConfigCritiqueDraft),
        (PydanticAIHarnessCritic, ImprovementCritiqueDraft),
    ],
)
def test_improvement_critics_fall_back_with_compact_resilience_diagnostics(
    monkeypatch,
    critic_cls,
    output_type,
) -> None:
    monkeypatch.setattr(
        "runtime_pydanticai.improvement.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )
    monkeypatch.setattr(
        "runtime_pydanticai.improvement.run_structured_agent",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("schema validation failed")),
    )

    critic = critic_cls(config_path="config.yaml")
    result = critic.propose(snapshot={"version": "snap_1"}, trajectories=[{"step": 1}])

    assert result.summary.startswith("Fallback")
    assert critic.runtime_used == RuntimeBackend.legacy
    assert critic.fallback_used is True
    assert critic.last_attempt_count == 1
    assert critic.last_retry_count == 0
    assert critic.last_retry_reasons == []
    assert critic.last_backoff_schedule == []
    assert critic.last_fallback_mode == "immediate_non_retryable"
    assert critic.last_error_category == "schema_error"
    assert critic.last_error_retryable is False

    resilience = critic.runtime_resilience
    assert resilience["status"] == "degraded"
    assert resilience["fallback_used"] is True
    assert resilience["immediate_fallback"] is True
    assert resilience["error_category"] == "schema_error"
    assert resilience["error_retryable"] is False


@pytest.mark.parametrize(
    "critic_cls",
    [
        PydanticAIConfigCritic,
        PydanticAIHarnessCritic,
    ],
)
def test_improvement_critics_honor_never_policy_after_bounded_retry(monkeypatch, critic_cls) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    monkeypatch.setattr(
        "runtime_pydanticai.improvement.load_runtime_model_config",
        lambda **kwargs: SimpleNamespace(base_url="http://example.test"),
    )

    def fake_run_structured_agent(**kwargs):
        calls["count"] += 1
        raise ConnectionError("temporary connection issue")

    monkeypatch.setattr("runtime_pydanticai.improvement.run_structured_agent", fake_run_structured_agent)
    monkeypatch.setattr("runtime_pydanticai.improvement.time.sleep", lambda delay: sleeps.append(delay))

    critic = critic_cls(config_path="config.yaml", fallback_policy=RuntimeFallbackPolicy.never)

    with pytest.raises(ConnectionError, match="temporary connection issue"):
        critic.propose(snapshot={"version": "snap_1"}, trajectories=[{"step": 1}])

    assert calls["count"] == 2
    assert sleeps == [0.15]
    assert critic.last_attempt_count == 2
    assert critic.last_retry_count == 1
    assert critic.last_retry_reasons == ["connection_error"]
    assert critic.last_retry_budget_exhausted is True
    assert critic.last_fallback_used is False
    assert critic.last_fallback_mode == "retry_budget_exhausted"
    assert critic.last_error_category == "connection_error"
    assert critic.last_error_retryable is True
