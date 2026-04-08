from __future__ import annotations

from copy import deepcopy

import optimizer_cron


def test_optimizer_cron_keeps_config_when_metrics_are_clean(monkeypatch) -> None:
    original = {
        "workers": {
            "coder": {"model": "gpt-4.1"},
            "default_max_retries": 3,
        },
        "orchestrator": {"max_stall_count": 3},
        "model_escalation_policy": True,
    }
    saved = []

    monkeypatch.setattr(optimizer_cron, "get_dynamic_model_ladder", lambda: ["gpt-4.1", "gpt-4.1-pro"])
    monkeypatch.setattr(optimizer_cron, "load_config", lambda: deepcopy(original))
    monkeypatch.setattr(optimizer_cron, "analyze_telemetry", lambda: {"Coder": {"delegations": 6, "errors": 0, "tokens": 100}})
    monkeypatch.setattr(optimizer_cron, "save_config", lambda config: saved.append(deepcopy(config)))

    optimizer_cron.optimize_system()

    assert saved == []


def test_optimizer_cron_reverts_toward_safer_model_on_failure(monkeypatch) -> None:
    original = {
        "workers": {
            "coder": {"model": "gpt-4.1-pro-high"},
            "default_max_retries": 3,
        },
        "orchestrator": {"max_stall_count": 3},
        "model_escalation_policy": True,
    }
    saved = []

    monkeypatch.setattr(optimizer_cron, "get_dynamic_model_ladder", lambda: ["gpt-4.1", "gpt-4.1-pro", "gpt-4.1-pro-high"])
    monkeypatch.setattr(optimizer_cron, "load_config", lambda: deepcopy(original))
    monkeypatch.setattr(optimizer_cron, "analyze_telemetry", lambda: {"Coder": {"delegations": 6, "errors": 4, "tokens": 100}})
    monkeypatch.setattr(optimizer_cron, "save_config", lambda config: saved.append(deepcopy(config)))

    optimizer_cron.optimize_system()

    assert saved
    assert saved[0]["workers"]["default_max_retries"] == 4
    assert saved[0]["workers"]["coder"]["model"] == "gpt-4.1-pro-high"
