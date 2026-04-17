from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from runtime_pydanticai.factory import RuntimeModelConfig, load_runtime_model_config, run_structured_agent


@pytest.fixture(autouse=True)
def clear_runtime_model_config_cache() -> None:
    load_runtime_model_config.cache_clear()
    yield
    load_runtime_model_config.cache_clear()


def test_load_runtime_model_config_prefers_openclaw_gateway_when_token_is_available(tmp_path, monkeypatch) -> None:
    openclaw_config = {
        "env": {"vars": {}},
        "gateway": {"auth": {"token": "${OPENCLAW_REMOTE_TOKEN}"}},
        "models": {
            "providers": {
                "openrouter": {
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "apiKey": {"id": "OPENROUTER_API_KEY"},
                    "models": [{"id": "openai/gpt-4o-mini"}],
                }
            }
        },
    }
    openclaw_path = tmp_path / "openclaw.json"
    config_path = tmp_path / "config.yaml"
    openclaw_path.write_text(json.dumps(openclaw_config), encoding="utf-8")
    config_path.write_text("api_endpoints:\n  openclaw_gateway: http://127.0.0.1:18789/v1\n", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_REMOTE_TOKEN", "gateway-token")

    config = load_runtime_model_config(
        config_path=str(config_path),
        openclaw_path=str(openclaw_path),
    )

    assert config.provider_name == "openclaw-gateway"
    assert config.model_name == "openclaw"
    assert config.base_url == "http://127.0.0.1:18789/v1"
    assert config.api_key == "gateway-token"
    assert config.source == "openclaw:gateway"


def test_load_runtime_model_config_honors_explicit_openclaw_provider(tmp_path, monkeypatch) -> None:
    openclaw_config = {
        "env": {
            "vars": {
                "OPENROUTER_API_KEY": "openrouter-key",
                "CEREBRAS_API_KEY": "cerebras-key",
            }
        },
        "models": {
            "providers": {
                "openrouter": {
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "apiKey": {"id": "OPENROUTER_API_KEY"},
                    "models": [{"id": "openai/gpt-4o-mini"}],
                },
                "cerebras": {
                    "baseUrl": "https://api.cerebras.ai/v1",
                    "apiKey": {"id": "CEREBRAS_API_KEY"},
                    "models": [{"id": "gpt-oss-120b"}],
                },
            }
        },
    }
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps(openclaw_config), encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_PYDANTICAI_PROVIDER", "cerebras")

    config = load_runtime_model_config(
        config_path=str(tmp_path / "missing.yaml"),
        openclaw_path=str(config_path),
    )

    assert config.provider_name == "cerebras"
    assert config.model_name == "gpt-oss-120b"
    assert config.base_url == "https://api.cerebras.ai/v1"
    assert config.api_key == "cerebras-key"
    assert config.source == "openclaw:cerebras"


def test_load_runtime_model_config_matches_provider_from_requested_model(tmp_path) -> None:
    openclaw_config = {
        "env": {
            "vars": {
                "OPENROUTER_API_KEY": "openrouter-key",
                "CEREBRAS_API_KEY": "cerebras-key",
            }
        },
        "models": {
            "providers": {
                "openrouter": {
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "apiKey": {"id": "OPENROUTER_API_KEY"},
                    "models": [{"id": "openai/gpt-4o-mini"}],
                },
                "cerebras": {
                    "baseUrl": "https://api.cerebras.ai/v1",
                    "apiKey": {"id": "CEREBRAS_API_KEY"},
                    "models": [{"id": "gpt-oss-120b"}],
                },
            }
        },
    }
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps(openclaw_config), encoding="utf-8")

    config = load_runtime_model_config(
        config_path=str(tmp_path / "missing.yaml"),
        openclaw_path=str(config_path),
        model_name="gpt-oss-120b",
    )

    assert config.provider_name == "cerebras"
    assert config.model_name == "gpt-oss-120b"
    assert config.api_key == "cerebras-key"
    assert config.source == "openclaw:cerebras"


def test_load_runtime_model_config_uses_dummy_key_for_ollama_provider(tmp_path) -> None:
    openclaw_config = {
        "env": {"vars": {}},
        "models": {
            "providers": {
                "ollama": {
                    "baseUrl": "http://127.0.0.1:11434/v1",
                    "apiKey": {"id": "OPENAI_API_KEY"},
                    "models": [{"id": "qwen2.5:14b"}],
                }
            }
        },
    }
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps(openclaw_config), encoding="utf-8")

    config = load_runtime_model_config(
        config_path=str(tmp_path / "missing.yaml"),
        openclaw_path=str(config_path),
    )

    assert config.provider_name == "ollama"
    assert config.model_name == "qwen2.5:14b"
    assert config.base_url == "http://127.0.0.1:11434/v1"
    assert config.api_key == "ollama"
    assert config.source == "openclaw:ollama"


def test_load_runtime_model_config_environment_override_still_wins(tmp_path, monkeypatch) -> None:
    openclaw_config = {
        "env": {"vars": {"OPENROUTER_API_KEY": "openrouter-key"}},
        "models": {
            "providers": {
                "openrouter": {
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "apiKey": {"id": "OPENROUTER_API_KEY"},
                    "models": [{"id": "openai/gpt-4o-mini"}],
                }
            }
        },
    }
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps(openclaw_config), encoding="utf-8")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://example.test/runtime")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENCLAW_PYDANTICAI_MODEL", "env-model")

    config = load_runtime_model_config(
        config_path=str(tmp_path / "missing.yaml"),
        openclaw_path=str(config_path),
    )

    assert config.provider_name == "openai"
    assert config.model_name == "env-model"
    assert config.base_url == "http://example.test/runtime/v1"
    assert config.api_key == "env-key"
    assert config.source == "environment"


class _StructuredReply(BaseModel):
    verdict: str
    confidence: int


def test_run_structured_agent_uses_openclaw_gateway_transport_and_parses_json(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    openclaw_path = tmp_path / "openclaw.json"
    config_path.write_text("api_endpoints:\n  openclaw_gateway: http://127.0.0.1:18789/v1\n", encoding="utf-8")
    openclaw_path.write_text("{}", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class FakeOpenClawClient:
        def __init__(self, config_path: str, openclaw_path: str):
            calls.append({"config_path": config_path, "openclaw_path": openclaw_path})

        def gateway_chat_completion(self, worker_name, messages, model, temperature=0.2, tools=None, tool_choice=None):
            calls.append(
                {
                    "worker_name": worker_name,
                    "messages": messages,
                    "model": model,
                }
            )
            return {
                "success": True,
                "content": '```json\n{"verdict":"reliable enough for paper testing","confidence":62}\n```',
                "tokens_used": 21,
            }

    monkeypatch.setattr("runtime_pydanticai.factory.OpenClawClient", FakeOpenClawClient)

    result = run_structured_agent(
        output_type=_StructuredReply,
        system_prompt="Reply with a compact reliability assessment.",
        user_prompt="Evaluate whether prediction markets are reliable.",
        agent_name="strategy-chair",
        config=RuntimeModelConfig(
            model_name="openclaw",
            provider_name="openclaw-gateway",
            base_url="http://127.0.0.1:18789/v1",
            api_key="gateway-token",
            source="openclaw:gateway",
            config_path=str(config_path),
            openclaw_path=str(openclaw_path),
        ),
    )

    assert result.output.verdict == "reliable enough for paper testing"
    assert result.output.confidence == 62
    assert result.model_name == "openclaw"
    assert result.provider_source == "openclaw:gateway"
    assert calls[0] == {"config_path": str(config_path), "openclaw_path": str(openclaw_path)}
    assert calls[1]["worker_name"] == "strategy-chair"
    assert calls[1]["model"] == "openclaw"
    assert "Return only valid JSON" in calls[1]["messages"][1]["content"]


def test_run_structured_agent_retries_invalid_gateway_json(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    openclaw_path = tmp_path / "openclaw.json"
    config_path.write_text("api_endpoints:\n  openclaw_gateway: http://127.0.0.1:18789/v1\n", encoding="utf-8")
    openclaw_path.write_text("{}", encoding="utf-8")
    attempts: list[list[dict[str, str]]] = []

    class FakeOpenClawClient:
        def __init__(self, config_path: str, openclaw_path: str):
            self._responses = iter(
                [
                    {"success": True, "content": '{"verdict":"missing confidence"}', "tokens_used": 7},
                    {"success": True, "content": '{"verdict":"salvaged","confidence":48}', "tokens_used": 8},
                ]
            )

        def gateway_chat_completion(self, worker_name, messages, model, temperature=0.2, tools=None, tool_choice=None):
            attempts.append(messages)
            return next(self._responses)

    monkeypatch.setattr("runtime_pydanticai.factory.OpenClawClient", FakeOpenClawClient)

    result = run_structured_agent(
        output_type=_StructuredReply,
        system_prompt="Reply with JSON only.",
        user_prompt="Assess the edge.",
        agent_name="repair-test",
        retries=1,
        config=RuntimeModelConfig(
            model_name="openclaw",
            provider_name="openclaw-gateway",
            base_url="http://127.0.0.1:18789/v1",
            api_key="gateway-token",
            source="openclaw:gateway",
            config_path=str(config_path),
            openclaw_path=str(openclaw_path),
        ),
    )

    assert result.output.verdict == "salvaged"
    assert result.output.confidence == 48
    assert len(attempts) == 2
    assert attempts[1][-1]["role"] == "user"
    assert "Validation error" in attempts[1][-1]["content"]
