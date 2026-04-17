from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
import yaml
from observability import log_structured_event
from pydantic import TypeAdapter

from openclaw_client import OpenClawClient, load_openclaw_runtime_settings

from .models import (
    RuntimeBackend,
    RuntimeFallbackPolicy,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeModelConfig,
    StructuredRuntimeResult,
)

try:
    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
except Exception as exc:  # pragma: no cover - exercised only when dependency is missing
    AsyncOpenAI = None  # type: ignore[assignment]
    Agent = None  # type: ignore[assignment]
    OpenAIChatModel = None  # type: ignore[assignment]
    OpenAIProvider = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


DEFAULT_OPENCLAW_CONFIG_PATH = Path("/home/jul/.openclaw/openclaw.json")
DEFAULT_MODEL_NAME = "claude-sonnet-4-6"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 10.0
DEFAULT_HEALTH_TIMEOUT_SECONDS = 3.0
DEFAULT_OPENCLAW_PROVIDER_PRIORITY = (
    "antigravity-proxy",
    "anthropic-proxy",
    "openrouter",
    "cerebras",
    "mistral",
    "nvidia",
    "ollama",
)
T = TypeVar("T")


class RuntimeAvailabilityError(RuntimeError):
    pass


def _normalize_base_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


def _read_yaml_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _read_openclaw_config(path: str | Path = DEFAULT_OPENCLAW_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _resolve_openclaw_value(raw: Any, env_vars: dict[str, Any]) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        env_id = str(raw.get("id", "")).strip()
        if env_id:
            return str(env_vars.get(env_id, "")).strip()
        inline_value = raw.get("value")
        if isinstance(inline_value, str):
            return inline_value.strip()
    return ""


def _provider_model_ids(provider: dict[str, Any]) -> list[str]:
    models = provider.get("models") or []
    if not isinstance(models, list):
        return []
    model_ids: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if model_id:
            model_ids.append(model_id)
    return model_ids


def _provider_default_model(provider: dict[str, Any]) -> str | None:
    model_ids = _provider_model_ids(provider)
    return model_ids[0] if model_ids else None


def _provider_priority_from_env() -> list[str]:
    raw = str(os.environ.get("OPENCLAW_PYDANTICAI_PROVIDER_PRIORITY", "")).strip()
    if not raw:
        return list(DEFAULT_OPENCLAW_PROVIDER_PRIORITY)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _candidate_provider_names(
    providers: dict[str, Any],
    *,
    requested_provider: str | None,
    requested_model: str | None,
) -> list[str]:
    valid_names = [name for name, provider in providers.items() if isinstance(provider, dict)]
    if requested_provider:
        return [requested_provider] if requested_provider in providers else []

    ordered: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen or name not in valid_names:
            return
        seen.add(name)
        ordered.append(name)

    if requested_model:
        for name in valid_names:
            provider = providers.get(name) or {}
            if requested_model in _provider_model_ids(provider):
                add(name)

    for name in _provider_priority_from_env():
        add(name)

    for name in valid_names:
        add(name)

    return ordered


def _runtime_config_from_openclaw_provider(
    provider_name: str,
    provider: dict[str, Any],
    env_vars: dict[str, Any],
    *,
    requested_model: str | None,
    allow_missing_api_key: bool = False,
    config_path: str | None = None,
    openclaw_path: str | None = None,
) -> RuntimeModelConfig | None:
    provider_api = str(provider.get("api", "")).strip()
    if provider_name == "openai-codex" or provider_api == "openai-codex-responses":
        return None
    base_url = _resolve_openclaw_value(provider.get("baseUrl"), env_vars)
    api_key = _resolve_openclaw_value(provider.get("apiKey"), env_vars)
    if provider_name == "ollama" and not api_key:
        api_key = "ollama"
    resolved_model_name = requested_model or _provider_default_model(provider)
    if not base_url or not resolved_model_name:
        return None
    if not api_key and not allow_missing_api_key:
        return None
    return RuntimeModelConfig(
        model_name=resolved_model_name,
        provider_name=provider_name,
        base_url=_normalize_base_url(base_url),
        api_key=api_key or None,
        source=f"openclaw:{provider_name}",
        config_path=config_path,
        openclaw_path=openclaw_path,
    )


def _requested_provider_uses_openclaw_gateway(provider_name: str | None) -> bool:
    normalized = str(provider_name or "").strip().lower()
    return normalized in {"openclaw", "openclaw-gateway", "openai-codex"}


def _requested_model_uses_openclaw_gateway(model_name: str | None) -> bool:
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    return normalized.startswith("openclaw") or normalized in {"gpt-5.4", "openai-codex/gpt-5.4"}


def _coerce_openclaw_gateway_model(model_name: str | None) -> str:
    normalized = str(model_name or "").strip()
    if normalized.startswith("openclaw"):
        return normalized
    return "openclaw"


def _extract_json_payload(content: str) -> str | None:
    raw = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not raw:
        return None
    if raw[0] in "{[" and raw[-1] in "}]":
        return raw
    object_start = raw.find("{")
    array_start = raw.find("[")
    starts = [index for index in (object_start, array_start) if index != -1]
    if not starts:
        return None
    start = min(starts)
    object_end = raw.rfind("}")
    array_end = raw.rfind("]")
    end = max(object_end, array_end)
    if end == -1 or end <= start:
        return None
    return raw[start : end + 1]


def _build_gateway_structured_prompt(user_prompt: str, output_type: type[T]) -> str:
    schema = TypeAdapter(output_type).json_schema()
    schema_json = json.dumps(schema, ensure_ascii=True, indent=2)
    return (
        f"{user_prompt.strip()}\n\n"
        "Return only valid JSON that matches the schema below.\n"
        "Do not add markdown fences or explanatory text.\n"
        f"JSON schema:\n{schema_json}"
    ).strip()


def _validate_structured_output(output_type: type[T], payload: str) -> T:
    adapter = TypeAdapter(output_type)
    return adapter.validate_json(payload)


def _run_openclaw_gateway_structured_agent(
    *,
    output_type: type[T],
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
    config: RuntimeModelConfig,
    retries: int = 1,
) -> StructuredRuntimeResult:
    client = OpenClawClient(
        config_path=config.config_path or "config.yaml",
        openclaw_path=config.openclaw_path or str(DEFAULT_OPENCLAW_CONFIG_PATH),
    )
    base_user_prompt = _build_gateway_structured_prompt(user_prompt, output_type)
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": base_user_prompt},
    ]
    last_error: Exception | None = None
    attempt_count = max(1, retries + 1)
    for _ in range(attempt_count):
        result = client.gateway_chat_completion(
            worker_name=agent_name,
            messages=messages,
            model=config.model_name,
        )
        if not result.get("success"):
            last_error = RuntimeAvailabilityError(
                str(result.get("error") or "OpenClaw gateway structured request failed.")
            )
            continue
        content = str(result.get("content", "")).strip()
        payload = _extract_json_payload(content) or content
        try:
            output = _validate_structured_output(output_type, payload)
            return StructuredRuntimeResult(
                output=output,
                runtime_used=RuntimeBackend.pydanticai,
                fallback_used=False,
                model_name=config.model_name,
                provider_base_url=config.base_url,
                provider_source=config.source,
            )
        except Exception as exc:
            last_error = exc
            messages = [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": base_user_prompt},
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was invalid.\n"
                        "Return only valid JSON that matches the schema.\n"
                        f"Validation error: {exc}"
                    ),
                },
            ]
    message = f"OpenClaw gateway structured call failed for {agent_name}."
    if last_error is not None:
        message = f"{message} {last_error}"
    raise RuntimeAvailabilityError(message) from last_error


@lru_cache(maxsize=1)
def load_runtime_model_config(
    config_path: str = "config.yaml",
    openclaw_path: str = str(DEFAULT_OPENCLAW_CONFIG_PATH),
    model_name: str | None = None,
) -> RuntimeModelConfig:
    yaml_config = _read_yaml_config(config_path)
    runtime_settings = load_openclaw_runtime_settings(openclaw_path=openclaw_path)
    openclaw_config = runtime_settings.get("config", {})
    config_env_vars = openclaw_config.get("env", {}).get("vars", {}) if isinstance(openclaw_config, dict) else {}
    env_lookup = runtime_settings.get("lookup", {})
    providers = runtime_settings.get("providers", {})
    antigravity_provider = providers.get("antigravity-proxy", {})
    requested_provider = str(os.environ.get("OPENCLAW_PYDANTICAI_PROVIDER", "")).strip() or None
    gateway_token = str(runtime_settings.get("gateway_token", "")).strip()
    gateway_url = (
        os.environ.get("OPENCLAW_PYDANTICAI_GATEWAY_URL")
        or yaml_config.get("api_endpoints", {}).get("openclaw_gateway")
        or "http://127.0.0.1:18789/v1"
    )

    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("LLM_PROXY_URL")
        or yaml_config.get("api_endpoints", {}).get("antigravity_proxy")
        or env_lookup.get("LLM_PROXY_URL")
    )
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LLM_PROXY_API_KEY")
        or env_lookup.get("LLM_PROXY_API_KEY")
        or env_lookup.get("OPENAI_API_KEY")
    )

    requested_model = model_name or os.environ.get("OPENCLAW_PYDANTICAI_MODEL")
    explicit_gateway = _requested_provider_uses_openclaw_gateway(
        requested_provider
    ) or _requested_model_uses_openclaw_gateway(requested_model)
    if os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_PROXY_URL"):
        source = "environment"
        provider_name = requested_provider or "openai"
    elif explicit_gateway or (gateway_token and requested_provider is None and requested_model is None):
        return RuntimeModelConfig(
            model_name=_coerce_openclaw_gateway_model(requested_model),
            provider_name="openclaw-gateway",
            base_url=_normalize_base_url(str(gateway_url)),
            api_key=gateway_token or None,
            source="openclaw:gateway",
            config_path=config_path,
            openclaw_path=openclaw_path,
        )
    elif yaml_config.get("api_endpoints", {}).get("antigravity_proxy"):
        yaml_api_key = api_key or _resolve_openclaw_value(antigravity_provider.get("apiKey"), env_lookup)
        yaml_model_name = requested_model or _provider_default_model(antigravity_provider) or DEFAULT_MODEL_NAME
        return RuntimeModelConfig(
            model_name=yaml_model_name,
            provider_name="antigravity-proxy",
            base_url=_normalize_base_url(str(yaml_config.get("api_endpoints", {}).get("antigravity_proxy"))),
            api_key=yaml_api_key or None,
            source="config_yaml",
            config_path=config_path,
            openclaw_path=openclaw_path,
        )
    else:
        for provider_name in _candidate_provider_names(
            providers,
            requested_provider=requested_provider,
            requested_model=requested_model,
        ):
            provider = providers.get(provider_name)
            if not isinstance(provider, dict):
                continue
            candidate = _runtime_config_from_openclaw_provider(
                provider_name,
                provider,
                env_lookup,
                requested_model=requested_model,
                allow_missing_api_key=bool(requested_provider),
                config_path=config_path,
                openclaw_path=openclaw_path,
            )
            if candidate is not None:
                return candidate
        source = "openclaw_env" if config_env_vars else "fallback"
        provider_name = requested_provider or "openai"

    resolved_model_name = requested_model or DEFAULT_MODEL_NAME
    if not base_url:
        base_url = "http://127.0.0.1:18080"
        if source == "fallback":
            provider_name = provider_name or "openai"
    if source == "environment":
        provider_name = provider_name or "openai"
    if source == "openclaw_env" and requested_provider == "ollama" and not api_key:
        api_key = "ollama"
    return RuntimeModelConfig(
        model_name=resolved_model_name,
        provider_name=provider_name,
        base_url=_normalize_base_url(base_url) if base_url else None,
        api_key=api_key or None,
        source=source,
        config_path=config_path,
        openclaw_path=openclaw_path,
    )


def build_openai_provider(config: RuntimeModelConfig) -> Any:
    if OpenAIProvider is None:  # pragma: no cover
        raise RuntimeAvailabilityError(f"PydanticAI provider import failed: {_IMPORT_ERROR}")
    if not config.base_url:
        raise RuntimeAvailabilityError("Missing base_url for PydanticAI OpenAI-compatible provider.")
    timeout_seconds = float(os.environ.get("OPENCLAW_PYDANTICAI_TIMEOUT_SECONDS", DEFAULT_PROVIDER_TIMEOUT_SECONDS))
    if AsyncOpenAI is None:  # pragma: no cover
        raise RuntimeAvailabilityError("OpenAI Async client import unavailable for PydanticAI provider.")
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
    openai_client = AsyncOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=httpx.Timeout(timeout_seconds),
        max_retries=0,
        http_client=http_client,
    )
    return OpenAIProvider(openai_client=openai_client)


def build_openai_model(config: RuntimeModelConfig) -> Any:
    if OpenAIChatModel is None:  # pragma: no cover
        raise RuntimeAvailabilityError(f"PydanticAI model import failed: {_IMPORT_ERROR}")
    provider = build_openai_provider(config)
    return OpenAIChatModel(config.model_name, provider=provider)


def check_pydanticai_runtime_health(
    config: RuntimeModelConfig | None = None,
    *,
    timeout_seconds: float | None = None,
) -> RuntimeHealthReport:
    runtime_config = config or load_runtime_model_config()
    probe_url = f"{runtime_config.base_url.rstrip('/')}/models" if runtime_config.base_url else None
    gateway_provider = runtime_config.provider_name == "openclaw-gateway"
    base_report = RuntimeHealthReport(
        runtime=RuntimeBackend.pydanticai,
        status=RuntimeHealthStatus.unavailable,
        configured=bool(runtime_config.base_url),
        imports_available=gateway_provider
        or all(
            dependency is not None
            for dependency in (Agent, AsyncOpenAI, OpenAIProvider, OpenAIChatModel)
        ),
        api_key_configured=bool(runtime_config.api_key),
        provider_name=runtime_config.provider_name,
        model_name=runtime_config.model_name,
        provider_base_url=runtime_config.base_url,
        provider_source=runtime_config.source,
        provider_probe_url=probe_url,
        fallback_runtime=RuntimeBackend.legacy,
    )
    if not base_report.imports_available:
        report = base_report.model_copy(
            update={
                "status": RuntimeHealthStatus.unavailable,
                "message": f"PydanticAI runtime imports unavailable: {_IMPORT_ERROR}",
                "details": {
                    "bootstrap_hint": "python -m pip install -r requirements.txt",
                    "missing_dependency": "pydantic-ai",
                },
            }
        )
        log_structured_event(
            "runtime_pydanticai.factory",
            "warning",
            "runtime_health_check",
            runtime=report.runtime.value,
            status=report.status.value,
            configured=report.configured,
            imports_available=report.imports_available,
            provider_base_url=report.provider_base_url,
            message=report.message,
        )
        return report
    if not runtime_config.base_url:
        report = base_report.model_copy(
            update={
                "status": RuntimeHealthStatus.misconfigured,
                "message": "Missing base_url for the PydanticAI runtime provider.",
                "details": {
                    "bootstrap_hint": "Set OPENAI_BASE_URL or LLM_PROXY_URL and provide an API key.",
                },
            }
        )
        log_structured_event(
            "runtime_pydanticai.factory",
            "warning",
            "runtime_health_check",
            runtime=report.runtime.value,
            status=report.status.value,
            configured=report.configured,
            imports_available=report.imports_available,
            provider_base_url=report.provider_base_url,
            message=report.message,
        )
        return report

    client_timeout = timeout_seconds or float(
        os.environ.get("OPENCLAW_PYDANTICAI_HEALTH_TIMEOUT_SECONDS", DEFAULT_HEALTH_TIMEOUT_SECONDS)
    )
    headers = {}
    if runtime_config.api_key:
        headers["Authorization"] = f"Bearer {runtime_config.api_key}"
    started_at = time.perf_counter()
    try:
        with httpx.Client(timeout=httpx.Timeout(client_timeout), follow_redirects=True) as client:
            response = client.get(probe_url, headers=headers)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        report = base_report.model_copy(
            update={
                "status": RuntimeHealthStatus.healthy,
                "provider_reachable": True,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
                "message": f"Provider probe responded with HTTP {response.status_code}.",
            }
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        report = base_report.model_copy(
            update={
                "status": RuntimeHealthStatus.degraded,
                "provider_reachable": False,
                "latency_ms": latency_ms,
                "message": str(exc),
                "details": {"error_type": type(exc).__name__},
            }
        )
    log_structured_event(
        "runtime_pydanticai.factory",
        "info" if report.status == RuntimeHealthStatus.healthy else "warning",
        "runtime_health_check",
        runtime=report.runtime.value,
        status=report.status.value,
        configured=report.configured,
        imports_available=report.imports_available,
        provider_base_url=report.provider_base_url,
        provider_probe_url=report.provider_probe_url,
        provider_reachable=report.provider_reachable,
        http_status=report.http_status,
        latency_ms=report.latency_ms,
        message=report.message,
    )
    return report


def check_pydanticai_runtime_health_payload(
    config: RuntimeModelConfig | None = None,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Return a JSON-ready health payload for callers that need plain data."""
    return check_pydanticai_runtime_health(
        config=config,
        timeout_seconds=timeout_seconds,
    ).model_dump(mode="json")


def _ensure_sync_event_loop() -> asyncio.AbstractEventLoop | None:
    """Install a loop only when sync entrypoints are called without one."""
    try:
        asyncio.get_running_loop()
        return None
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def build_agent(
    *,
    output_type: type[T],
    system_prompt: str,
    name: str,
    config: RuntimeModelConfig | None = None,
    retries: int = 1,
) -> Any:
    if Agent is None:  # pragma: no cover
        raise RuntimeAvailabilityError(f"PydanticAI import failed: {_IMPORT_ERROR}")
    runtime_config = config or load_runtime_model_config()
    if runtime_config.provider_name == "openclaw-gateway":
        raise RuntimeAvailabilityError("OpenClaw gateway models are dispatched through run_structured_agent().")
    model = build_openai_model(runtime_config)
    return Agent(
        model=model,
        output_type=output_type,
        system_prompt=system_prompt,
        retries=retries,
        name=name,
    )


def run_structured_agent(
    *,
    output_type: type[T],
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
    config: RuntimeModelConfig | None = None,
    retries: int = 1,
) -> StructuredRuntimeResult:
    runtime_config = config or load_runtime_model_config()
    if runtime_config.provider_name == "openclaw-gateway":
        return _run_openclaw_gateway_structured_agent(
            output_type=output_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            agent_name=agent_name,
            config=runtime_config,
            retries=retries,
        )
    agent = build_agent(
        output_type=output_type,
        system_prompt=system_prompt,
        name=agent_name,
        config=runtime_config,
        retries=retries,
    )
    created_loop = _ensure_sync_event_loop()
    try:
        result = agent.run_sync(user_prompt)
    finally:
        if created_loop is not None:
            created_loop.close()
            asyncio.set_event_loop(None)
    return StructuredRuntimeResult(
        output=result.output,
        runtime_used=RuntimeBackend.pydanticai,
        fallback_used=False,
        model_name=runtime_config.model_name,
        provider_base_url=runtime_config.base_url,
        provider_source=runtime_config.source,
    )


class PydanticAIRuntimeFactory:
    def __init__(self, *, config_path: str = "config.yaml", openclaw_path: str = str(DEFAULT_OPENCLAW_CONFIG_PATH)) -> None:
        self.config_path = config_path
        self.openclaw_path = openclaw_path

    def config(self, model_name: str | None = None) -> RuntimeModelConfig:
        return load_runtime_model_config(self.config_path, self.openclaw_path, model_name)

    def available(self) -> bool:
        try:
            config = self.config()
            return config.base_url is not None and (
                config.provider_name == "openclaw-gateway" or Agent is not None
            )
        except Exception:
            return False

    def health_check(self, *, timeout_seconds: float | None = None) -> RuntimeHealthReport:
        return check_pydanticai_runtime_health(
            self.config(),
            timeout_seconds=timeout_seconds,
        )

    def create_result(self, *, output_type: type[T], system_prompt: str, user_prompt: str, agent_name: str) -> StructuredRuntimeResult:
        return run_structured_agent(
            output_type=output_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            agent_name=agent_name,
            config=self.config(),
        )
