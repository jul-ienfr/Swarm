from __future__ import annotations

import json
from pathlib import Path

from engines.agentsociety.live_client import AgentSocietyProcessClient, LLMEndpoint
from engines.agentsociety.translator import AgentSocietyRunConfig


def test_live_client_discovers_direct_openclaw_providers(tmp_path, monkeypatch) -> None:
    openclaw_config = {
        "env": {
            "vars": {
                "CEREBRAS_API_KEY": "cerebras-key",
                "MISTRAL_API_KEY": "mistral-key",
                "NVIDIA_API_KEY": "nvidia-key",
            }
        },
        "models": {
            "providers": {
                "cerebras": {"baseUrl": "https://api.cerebras.ai/v1", "apiKey": {"id": "CEREBRAS_API_KEY"}},
                "mistral": {"baseUrl": "https://api.mistral.ai/v1", "apiKey": {"id": "MISTRAL_API_KEY"}},
                "nvidia": {"baseUrl": "https://integrate.api.nvidia.com/v1", "apiKey": {"id": "NVIDIA_API_KEY"}},
            }
        },
    }
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps(openclaw_config))
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(config_path))

    client = AgentSocietyProcessClient.from_environment()

    assert [endpoint.label for endpoint in client._llm_configs] == ["cerebras"]
    assert client._llm_configs[0].model == "llama3.1-8b"


def test_live_client_builds_multiple_llm_entries(tmp_path) -> None:
    client = AgentSocietyProcessClient(
        runs_root=tmp_path / "runs",
        map_path=tmp_path / "map.pb",
        llm_configs=[
            LLMEndpoint(base_url="https://api.mistral.ai/v1", api_key="a", model="mistral-small-latest", label="mistral"),
            LLMEndpoint(base_url="https://api.cerebras.ai/v1", api_key="b", model="llama3.1-8b", label="cerebras"),
        ],
    )

    config = client._build_config_dict(
        config=AgentSocietyRunConfig(
            run_id="run_cfg",
            max_agents=1,
            time_horizon="0.01d",
            extra={"llm_concurrency": 2, "llm_timeout": 45},
        ),
        exp_id="exp_1",
        env_home_dir=tmp_path / "artifacts",
    )

    assert len(config["llm"]) == 2
    assert config["llm"][0]["concurrency"] == 2
    assert config["llm"][1]["timeout"] == 45
