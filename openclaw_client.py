import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

from ledger_state import LLMResult

DEFAULT_OPENCLAW_CONFIG_PATH = Path("/home/jul/.openclaw/openclaw.json")
DEFAULT_OPENCLAW_ENV_PATH = Path("/home/jul/.openclaw/.env")


def _read_openclaw_json(path: str | Path = DEFAULT_OPENCLAW_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _read_simple_env_file(path: str | Path = DEFAULT_OPENCLAW_ENV_PATH) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key:
            values[key] = value
    return values


def _resolve_template_string(value: str, lookup: dict[str, Any]) -> str:
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        resolved = lookup.get(key)
        return str(resolved) if resolved is not None else ""

    return pattern.sub(replace, value).strip()


def _resolve_openclaw_config_value(raw: Any, lookup: dict[str, Any]) -> str:
    if isinstance(raw, str):
        return _resolve_template_string(raw, lookup)
    if isinstance(raw, dict):
        env_id = str(raw.get("id", "")).strip()
        if env_id:
            return str(lookup.get(env_id, "")).strip()
        inline_value = raw.get("value")
        if isinstance(inline_value, str):
            return _resolve_template_string(inline_value, lookup)
    return ""


def load_openclaw_runtime_settings(
    *,
    openclaw_path: str | Path = DEFAULT_OPENCLAW_CONFIG_PATH,
    env_path: str | Path = DEFAULT_OPENCLAW_ENV_PATH,
) -> dict[str, Any]:
    openclaw_config = _read_openclaw_json(openclaw_path)
    env_vars = openclaw_config.get("env", {}).get("vars", {}) if isinstance(openclaw_config, dict) else {}
    file_env = _read_simple_env_file(env_path)
    lookup = {
        **file_env,
        **os.environ,
        **env_vars,
    }
    providers = openclaw_config.get("models", {}).get("providers", {}) if isinstance(openclaw_config, dict) else {}
    gateway = openclaw_config.get("gateway", {}) if isinstance(openclaw_config, dict) else {}
    ant_proxy = providers.get("antigravity-proxy", {}) if isinstance(providers, dict) else {}
    gateway_token = _resolve_openclaw_config_value(
        gateway.get("auth", {}).get("token") if isinstance(gateway, dict) else None,
        lookup,
    )
    proxy_api_key = _resolve_openclaw_config_value(
        ant_proxy.get("apiKey") if isinstance(ant_proxy, dict) else None,
        lookup,
    )
    return {
        "config": openclaw_config,
        "lookup": lookup,
        "gateway_token": gateway_token,
        "proxy_api_key": proxy_api_key,
        "providers": providers,
    }

class OpenClawNetworkError(Exception):
    pass

class OpenClawProtocolError(Exception):
    pass

class OpenClawLogicError(Exception):
    pass

class OpenClawClient:
    def __init__(self, config_path: str = "config.yaml", openclaw_path: str = str(DEFAULT_OPENCLAW_CONFIG_PATH)):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # The OpenClaw Gateway (for agents)
        self.gateway_url = self.config.get("api_endpoints", {}).get("openclaw_gateway", "http://127.0.0.1:18789/v1")
        # The Antigravity Proxy (for the orchestrator)
        self.proxy_url = self.config.get("api_endpoints", {}).get("antigravity_proxy", "http://192.168.31.59:8045/v1")
        runtime_settings = load_openclaw_runtime_settings(openclaw_path=openclaw_path)
        self.gateway_token = str(runtime_settings.get("gateway_token", "")).strip()
        self.proxy_api_key = str(runtime_settings.get("proxy_api_key", "")).strip()

        self.timeout = httpx.Timeout(120.0)

    def _execute_completion(self, messages: List[Dict[str, str]], model_name: str, temperature: float = 0.2) -> Dict[str, Any]:
        """Used by the orchestrator to talk to the raw Antigravity proxy models via chat/completions."""
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }

        headers = {
            "Content-Type": "application/json"
        }

        if self.proxy_api_key:
            headers["Authorization"] = f"Bearer {self.proxy_api_key}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.proxy_url}/chat/completions", headers=headers, json=payload)

            if response.status_code != 200:
                raise OpenClawProtocolError(f"HTTP {response.status_code}: {response.text}")

            return response.json()

        except httpx.RequestError as e:
            raise OpenClawNetworkError(f"Network error connecting to Proxy: {str(e)}")
        except json.JSONDecodeError as e:
            raise OpenClawProtocolError(f"Invalid JSON response from Proxy: {str(e)}")

    def _execute_agent_response(self, messages: List[Dict[str, str]], agent_id: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Used by the workers to talk to OpenClaw agents via /responses endpoint."""
        # Convert messages array into a single string input as required by the OpenResponses API
        # Typically we just send the last user message, or join them
        input_text = "\n\n".join([f"{m['role']}: {m['content']}" for m in messages])

        payload = {
            "model": model if model else "openclaw",
            "input": input_text
        }

        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": agent_id
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.gateway_url}/responses", headers=headers, json=payload)

            if response.status_code != 200:
                raise OpenClawProtocolError(f"HTTP {response.status_code}: {response.text}")

            return response.json()

        except httpx.RequestError as e:
            raise OpenClawNetworkError(f"Network error connecting to OpenClaw Gateway: {str(e)}")
        except json.JSONDecodeError as e:
            raise OpenClawProtocolError(f"Invalid JSON response from OpenClaw Gateway: {str(e)}")

    def _execute_gateway_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "openclaw",
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.gateway_token}",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.gateway_url}/chat/completions", headers=headers, json=payload)

            if response.status_code != 200:
                raise OpenClawProtocolError(f"HTTP {response.status_code}: {response.text}")

            return response.json()

        except httpx.RequestError as e:
            raise OpenClawNetworkError(f"Network error connecting to OpenClaw Gateway chat/completions: {str(e)}")
        except json.JSONDecodeError as e:
            raise OpenClawProtocolError(f"Invalid JSON response from OpenClaw Gateway chat/completions: {str(e)}")

    def gateway_chat_completion(
        self,
        worker_name: str,
        messages: List[Dict[str, str]],
        model: str = "openclaw",
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResult:
        try:
            result = self._execute_gateway_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
            )
            content = str(result.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
            if not content:
                raise OpenClawLogicError("OpenClaw gateway chat/completions returned empty content.")
            return {
                "worker_name": worker_name,
                "content": content,
                "metadata": {"model_used": model, "route": "gateway_chat_completions"},
                "success": True,
                "error": None,
                "tokens_used": result.get("usage", {}).get("total_tokens", 0),
            }
        except Exception as e:
            return {
                "worker_name": worker_name,
                "content": "",
                "metadata": {"model_used": model, "route": "gateway_chat_completions"},
                "success": False,
                "error": f"Gateway chat completion error: {str(e)}",
                "tokens_used": 0,
            }

    def chat_with_agent(self, worker_name: str, agent_id: str, messages: List[Dict[str, str]], model: Optional[str] = None) -> LLMResult:
        try:
            result = self._execute_agent_response(messages, agent_id=agent_id, model=model)
            print(f"\n[RAW OPENCLAW RESULT] {json.dumps(result, indent=2)}\n")

            # Extract content from the OpenResponses API format
            # Format: "output": [{"role": "assistant", "content": [{"type": "output_text", "text": "..."}]}]
            content = ""
            for item in result.get("output", []):
                if item.get("role") == "assistant":
                    for c in item.get("content", []):
                        if c.get("type") == "output_text":
                            content += c.get("text", "") + "\n"
            content = content.strip()

            if not content or "No response from OpenClaw" in content:
                raise OpenClawLogicError(f"OpenClaw agent returned empty content or default error: {content}")

            return {
                "worker_name": worker_name,
                "content": content,
                "metadata": {"agent_id": agent_id},
                "success": True,
                "error": None,
                "tokens_used": result.get("usage", {}).get("total_tokens", 0)
            }

        except Exception as e:
            return {
                "worker_name": worker_name,
                "content": "",
                "metadata": {"agent_id": agent_id},
                "success": False,
                "error": f"Agent Error: {str(e)}",
                "tokens_used": 0
            }

    def chat_with_escalation(self, worker_name: str, messages: List[Dict[str, str]], preferred_tier: str = "openclaw_gateway", model_name: str = "claude-sonnet-4-6") -> LLMResult:
                # Dynamically fetch fallback LLMs from Gateway /v1/models
        fallback_models = [model_name]
        try:
            headers = {"Authorization": f"Bearer {self.gateway_token}", "Accept": "application/json"}
            import httpx
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.gateway_url}/models", headers=headers)
                if r.status_code == 200:
                    models_data = r.json().get("data", [])
                    for m in models_data:
                        m_id = m.get("id", "")
                        if m_id and not m_id.startswith("openclaw/") and m_id != "openclaw" and m_id not in fallback_models:
                            fallback_models.append(m_id)
        except Exception:
            pass
        if len(fallback_models) == 1:
            fallback_models.append("claude-sonnet-4-6")

        for current_model in fallback_models:
            try:
                result = self._execute_completion(messages, current_model)
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                if not content or "No response from OpenClaw" in content:
                    raise OpenClawLogicError(f"LLM logic error or empty content with model {current_model}.")

                return {
                    "worker_name": worker_name,
                    "content": content,
                    "metadata": {"model_used": current_model},
                    "success": True,
                    "error": None,
                    "tokens_used": result.get("usage", {}).get("total_tokens", 0)
                }

            except Exception as e:
                if current_model == fallback_models[-1]:
                    return {
                        "worker_name": worker_name,
                        "content": "",
                        "metadata": {"model_failed": current_model},
                        "success": False,
                        "error": f"Escalation failed: {str(e)}",
                        "tokens_used": 0
                    }
                print(f"[Fallback Triggered] Model {current_model} failed, escalating...")
                continue
        return {
            "worker_name": worker_name,
            "content": "",
            "metadata": {},
            "success": False,
            "error": "All fallback models failed",
            "tokens_used": 0
        }
