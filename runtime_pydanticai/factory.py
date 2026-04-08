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


@lru_cache(maxsize=1)
def load_runtime_model_config(
    config_path: str = "config.yaml",
    openclaw_path: str = str(DEFAULT_OPENCLAW_CONFIG_PATH),
    model_name: str | None = None,
) -> RuntimeModelConfig:
    yaml_config = _read_yaml_config(config_path)
    openclaw_config = _read_openclaw_config(openclaw_path)
    env_vars = openclaw_config.get("env", {}).get("vars", {})
    providers = openclaw_config.get("models", {}).get("providers", {})
    antigravity_provider = providers.get("antigravity-proxy", {})

    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("LLM_PROXY_URL")
        or yaml_config.get("api_endpoints", {}).get("antigravity_proxy")
        or antigravity_provider.get("baseUrl")
        or env_vars.get("LLM_PROXY_URL")
        or "http://127.0.0.1:18080"
    )
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LLM_PROXY_API_KEY")
        or antigravity_provider.get("apiKey")
        or env_vars.get("LLM_PROXY_API_KEY")
        or env_vars.get("OPENAI_API_KEY")
        or env_vars.get("CEREBRAS_API_KEY")
        or env_vars.get("OPENROUTER_API_KEY")
    )

    resolved_model_name = model_name or os.environ.get("OPENCLAW_PYDANTICAI_MODEL") or DEFAULT_MODEL_NAME
    if os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_PROXY_URL"):
        source = "environment"
    elif yaml_config.get("api_endpoints", {}).get("antigravity_proxy"):
        source = "config_yaml"
    elif antigravity_provider.get("baseUrl"):
        source = "openclaw_provider"
    elif env_vars:
        source = "openclaw_env"
    else:
        source = "fallback"
    return RuntimeModelConfig(
        model_name=resolved_model_name,
        base_url=_normalize_base_url(base_url) if base_url else None,
        api_key=api_key,
        source=source,
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
    base_report = RuntimeHealthReport(
        runtime=RuntimeBackend.pydanticai,
        status=RuntimeHealthStatus.unavailable,
        configured=bool(runtime_config.base_url),
        imports_available=all(
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
            return self.config().base_url is not None and Agent is not None
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
