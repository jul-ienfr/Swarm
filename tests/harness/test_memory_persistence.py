from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import swarm_memory
from swarm_memory import AdaptiveRateLimiter


def test_adaptive_rate_limiter_persists_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    memory_file = tmp_path / "rate_limits_memory.json"
    limiter = AdaptiveRateLimiter(memory_file=str(memory_file))

    monkeypatch.setattr(swarm_memory.time, "time", lambda: 1000.0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.0)
    limiter.record_429("mini-proxy", "reset after 8s")

    persisted = json.loads(memory_file.read_text())
    assert persisted["providers"]["mini-proxy"]["status"] == "throttled"
    assert persisted["providers"]["mini-proxy"]["consecutive_429s"] == 1

    reloaded = AdaptiveRateLimiter(memory_file=str(memory_file))
    monkeypatch.setattr(swarm_memory.time, "time", lambda: 1002.0)

    assert reloaded.get_delay_for_provider("mini-proxy") > 0.0


def test_adaptive_rate_limiter_releases_after_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    memory_file = tmp_path / "rate_limits_memory.json"
    limiter = AdaptiveRateLimiter(memory_file=str(memory_file))

    monkeypatch.setattr(swarm_memory.time, "time", lambda: 1000.0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.0)
    limiter.record_429("mini-proxy", "reset after 8s")

    reloaded = AdaptiveRateLimiter(memory_file=str(memory_file))
    reloaded.default_ttl = 1
    monkeypatch.setattr(swarm_memory.time, "time", lambda: 2000.0)

    assert reloaded.get_delay_for_provider("mini-proxy") == 0.0
