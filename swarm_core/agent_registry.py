from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


DEFAULT_DYNAMIC_AGENTS_DIR = Path("/home/jul/.openclaw/agents")
DEFAULT_CUSTOM_WORKERS = ["studio-media", "video-assembler", "debate_room", "simulation_runtime"]
DEFAULT_FALLBACK_AGENTS = [
    ("architect", ""),
    ("veille-strategique", ""),
    ("viral-analyzer", ""),
    ("script-writer", ""),
    ("studio-media", ""),
    ("video-assembler", ""),
    ("simulation_runtime", "Bounded simulation runtime through the adapter and AgentSociety."),
]


class SwarmAgentRegistry:
    """Discovers agent capabilities without depending on LangGraph internals."""

    def __init__(
        self,
        *,
        client=None,
        agents_dir: str | Path = DEFAULT_DYNAMIC_AGENTS_DIR,
        custom_workers: list[str] | None = None,
    ) -> None:
        self.client = client
        self.agents_dir = Path(agents_dir)
        self.custom_workers = list(custom_workers or DEFAULT_CUSTOM_WORKERS)

    def get_dynamic_agents(self) -> list[str]:
        if not self.agents_dir.exists():
            return []
        return sorted(
            entry.name
            for entry in self.agents_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    def get_valid_worker_names(self) -> list[str]:
        return list(dict.fromkeys(self.custom_workers + self.get_dynamic_agents()))

    def get_prompt_catalog(self) -> str:
        available = self._discover_gateway_agents()
        if not available:
            available = DEFAULT_FALLBACK_AGENTS + [
                (agent, "") for agent in self.get_dynamic_agents() if agent not in {name for name, _ in DEFAULT_FALLBACK_AGENTS}
            ]
        lines = ["Available agents (Available Right Now):"]
        for name, description in available:
            suffix = f" ({description})" if description else ""
            lines.append(f" - {name}{suffix}")
        lines.append(" - COMPLETE")
        return "\n".join(lines) + "\n"

    def _discover_gateway_agents(self) -> list[tuple[str, str]]:
        if self.client is None:
            return []
        try:
            headers = {
                "Authorization": f"Bearer {self.client.gateway_token}",
                "Accept": "application/json",
            }
            tools_url = self.client.gateway_url.replace("/v1", "") + "/tools"
            response = requests.get(tools_url, headers=headers, timeout=5)
            if response.status_code != 200 or "json" not in response.headers.get("Content-Type", ""):
                response = requests.get(f"{self.client.gateway_url}/tools", headers=headers, timeout=5)
            if response.status_code != 200:
                return []
            payload = response.json()
            tools = payload.get("tools", []) or payload.get("data", [])
            discovered = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                name = tool.get("name") or tool.get("id")
                if not name:
                    continue
                discovered.append((str(name), str(tool.get("description", ""))))
            if discovered:
                for worker in self.custom_workers:
                    if worker not in {name for name, _ in discovered}:
                        discovered.append((worker, ""))
            return discovered
        except Exception:
            return []


def get_dynamic_agents(agents_dir: str | Path = DEFAULT_DYNAMIC_AGENTS_DIR) -> list[str]:
    return SwarmAgentRegistry(agents_dir=agents_dir).get_dynamic_agents()
