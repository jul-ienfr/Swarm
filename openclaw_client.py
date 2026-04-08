import json
import httpx
import yaml
from typing import Any, Dict, List, Optional

from ledger_state import LLMResult

class OpenClawNetworkError(Exception):
    pass

class OpenClawProtocolError(Exception):
    pass

class OpenClawLogicError(Exception):
    pass

class OpenClawClient:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # The OpenClaw Gateway (for agents)
        self.gateway_url = self.config.get("api_endpoints", {}).get("openclaw_gateway", "http://127.0.0.1:18789/v1")
        # The Antigravity Proxy (for the orchestrator)
        self.proxy_url = self.config.get("api_endpoints", {}).get("antigravity_proxy", "http://192.168.31.59:8045/v1")

        with open("/home/jul/.openclaw/openclaw.json", "r") as oc_file:
            oc_config = json.load(oc_file)
            self.gateway_token = oc_config.get("gateway", {}).get("auth", {}).get("token", "")

            # Extract Antigravity proxy API key
            providers = oc_config.get("models", {}).get("providers", {})
            ant_proxy = providers.get("antigravity-proxy", {})
            self.proxy_api_key = ant_proxy.get("apiKey", "")

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
