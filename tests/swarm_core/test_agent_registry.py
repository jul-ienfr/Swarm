from __future__ import annotations

from swarm_core.agent_registry import SwarmAgentRegistry
from runtime_pydanticai import get_runtime_stub


def test_prompt_catalog_uses_neutral_heading(monkeypatch) -> None:
    registry = SwarmAgentRegistry(client=None, agents_dir="/tmp/does-not-exist", custom_workers=[])
    monkeypatch.setattr(registry, "_discover_gateway_agents", lambda: [])
    monkeypatch.setattr(registry, "get_dynamic_agents", lambda: [])

    catalog = registry.get_prompt_catalog()

    assert catalog.startswith("Available agents (Available Right Now):")
    assert "OpenClaw Agents" not in catalog


def test_runtime_stub_mentions_swarm() -> None:
    stub = get_runtime_stub()

    assert "Swarm" in stub["message"]
