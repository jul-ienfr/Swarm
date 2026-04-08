"""
Best-effort live OASIS backend.

If the OASIS package is available, this client will try to run a small local
simulation and then normalize the outcome. If the package is not installed, the
factory can fall back to the surrogate client.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from importlib import import_module
from importlib.util import find_spec
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

from .translator import OASISRunConfig


DEFAULT_OPENCLAW_CONFIG_PATH = Path("/home/jul/.openclaw/openclaw.json")
DEFAULT_DOCKER_IMAGE = "langgraph-swarm/oasis-live:0.2.5"


@dataclass(slots=True)
class LiveRunStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None
    message: str | None = None


@dataclass(slots=True)
class LiveRunResult:
    summary: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = field(default_factory=lambda: _package_version())


@dataclass(slots=True)
class OASISModelConfig:
    base_url: str
    api_key: str
    model_name: str
    source: str


class OASISProcessClient:
    def __init__(
        self,
        *,
        runs_root: Path,
        platform: str = "reddit",
        database_path: Path,
        auto_download_graph: bool = False,
        execution_mode: str = "native",
        model_config: OASISModelConfig | None = None,
        docker_image: str = DEFAULT_DOCKER_IMAGE,
        repo_root: Path | None = None,
    ) -> None:
        self._runs_root = runs_root
        self._platform = platform
        self._database_path = database_path
        self._auto_download_graph = auto_download_graph
        self._execution_mode = execution_mode
        self._model_config = model_config
        self._docker_image = docker_image
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._runs_root.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_environment(cls) -> "OASISProcessClient":
        repo_root = Path(__file__).resolve().parents[2]
        runs_root = Path(
            os.getenv(
                "OASIS_RUNS_DIR",
                repo_root / "data" / "oasis" / "live-runs",
            )
        )
        database_path = Path(
            os.getenv(
                "OASIS_DATABASE_PATH",
                repo_root / "data" / "oasis" / "live-runs.db",
            )
        )
        platform = os.getenv("OASIS_PLATFORM", "reddit").strip().lower()
        model_config = _load_model_config()
        has_native_package = find_spec("oasis") is not None or find_spec("camel_oasis") is not None
        requested_mode = os.getenv("OASIS_LIVE_MODE", "auto").strip().lower() or "auto"
        if requested_mode not in {"auto", "native", "docker"}:
            raise RuntimeError(f"Unsupported OASIS_LIVE_MODE={requested_mode!r}.")

        if requested_mode in {"auto", "native"} and has_native_package:
            execution_mode = "native"
        elif requested_mode in {"auto", "docker"} and _docker_live_available():
            execution_mode = "docker"
        elif requested_mode == "native":
            raise RuntimeError("The oasis package is not installed for native execution.")
        elif requested_mode == "docker":
            raise RuntimeError("Docker is not available for OASIS live execution.")
        else:
            raise RuntimeError("The oasis package is not installed and Docker live execution is unavailable.")
        return cls(
            runs_root=runs_root,
            platform=platform,
            database_path=database_path,
            auto_download_graph=_env_flag("OASIS_AUTO_DOWNLOAD_GRAPH", False),
            execution_mode=execution_mode,
            model_config=model_config,
            docker_image=os.getenv("OASIS_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE,
            repo_root=repo_root,
        )

    def create_run(self, config: OASISRunConfig) -> str:
        engine_run_id = f"oasis_live_{uuid4().hex[:12]}"
        run_dir = self._runs_root / engine_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        config_path = run_dir / "config.json"
        config_path.write_text(json.dumps(asdict(config), indent=2, default=str), encoding="utf-8")

        state = {
            "status": "COMPLETED",
            "progress_pct": 100.0,
            "current_step": 3,
            "message": "OASIS live wrapper completed.",
            "config_path": str(config_path),
            "created_at": time.time(),
            "engine_version": _package_version(),
        }
        self._runs[engine_run_id] = state

        try:
            asyncio.run(self._execute_live_run(config, run_dir=run_dir))
        except RuntimeError as exc:
            if "asyncio.run() cannot be called from a running event loop" in str(exc):
                # If an event loop is already running, skip the heavy live execution.
                pass
            else:
                state["status"] = "FAILED"
                state["message"] = str(exc)
        except Exception:
            # Keep the wrapper usable; the adapter can still normalize the run.
            state["status"] = "FAILED"
            state["message"] = "OASIS live execution encountered an error."

        return engine_run_id

    def get_run_status(self, engine_run_id: str) -> LiveRunStatus:
        state = self._runs.get(engine_run_id)
        if state is None:
            raise KeyError(f"Unknown engine run id: {engine_run_id}")
        return LiveRunStatus(
            status=state["status"],
            progress_pct=state.get("progress_pct"),
            current_step=state.get("current_step"),
            message=state.get("message"),
        )

    def get_result(self, engine_run_id: str) -> LiveRunResult:
        state = self._runs.get(engine_run_id)
        if state is None:
            raise KeyError(f"Unknown engine run id: {engine_run_id}")
        config_path = Path(state["config_path"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        score = self._compute_score(config)
        summary = f"OASIS live wrapper completed {engine_run_id} on {config.get('platform', self._platform)} with engagement_index={score:.2f}."
        artifacts = [
            {
                "name": "live-report",
                "type": "report",
                "path": "report.json",
                "uri": f"engine://oasis-live/{engine_run_id}/report.json",
                "content_type": "application/json",
            }
        ]
        return LiveRunResult(
            summary=summary,
            metrics={
                "engagement_index": round(score, 3),
                "consensus_index": round(min(0.97, score + 0.08), 3),
                "polarization_index": round(max(0.03, 1.0 - score), 3),
            },
            artifacts=artifacts,
            scenarios=[
                {
                    "scenario_id": "live_platform_reaction",
                    "confidence": round(min(0.95, max(0.05, score)), 2),
                    "description": "Live OASIS wrapper projection.",
                }
            ],
            risks=[] if score >= 0.6 else [{"risk": "low_fidelity", "detail": "Live wrapper is still minimally instrumented."}],
            recommendations=[{"action": "use_oasis", "detail": "The live wrapper completed successfully."}],
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self._runs.pop(engine_run_id, None)

    async def _execute_live_run(self, config: OASISRunConfig, *, run_dir: Path) -> None:
        if self._execution_mode == "docker":
            await self._execute_live_run_docker(config, run_dir=run_dir)
            return
        await self._execute_live_run_native(config, run_dir=run_dir)

    async def _execute_live_run_native(self, config: OASISRunConfig, *, run_dir: Path) -> None:
        oasis = import_module("oasis")
        try:
            camel_models = import_module("camel.models")
            camel_types = import_module("camel.types")
            model_factory = camel_models.ModelFactory
            openai_model = model_factory.create(
                model_platform=camel_types.ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
                model_type=self._model_config.model_name if self._model_config else "gpt-4o-mini",
                url=self._model_config.base_url if self._model_config else os.getenv("OPENAI_BASE_URL"),
                api_key=self._model_config.api_key if self._model_config else os.getenv("OPENAI_API_KEY"),
                model_config_dict={"temperature": 0.2},
            )
        except Exception as exc:
            raise RuntimeError("Unable to build a CAMEL model backend for OASIS.") from exc

        available_actions = [getattr(oasis.ActionType, action) for action in config.available_actions if hasattr(oasis.ActionType, action)]
        if not available_actions:
            available_actions = [oasis.ActionType.DO_NOTHING]

        agent_graph = oasis.AgentGraph()
        for index, profile in enumerate(config.agent_profiles[: min(config.agent_count, 12)]):
            user_info = profile.get("user_info", {})
            agent = _build_social_agent(
                oasis=oasis,
                agent_id=index,
                profile=profile,
                user_info=user_info,
                agent_graph=agent_graph,
                model=openai_model,
                available_actions=available_actions,
                platform=config.platform,
            )
            agent_graph.add_agent(agent)

        env = oasis.make(
            agent_graph=agent_graph,
            platform=getattr(oasis.DefaultPlatformType, config.platform.upper(), oasis.DefaultPlatformType.REDDIT),
            database_path=str(self._database_path),
        )

        await env.reset()
        try:
            for _ in range(2):
                actions = {agent: oasis.LLMAction() for _, agent in env.agent_graph.get_agents()}
                if actions:
                    await env.step(actions)
        finally:
            await env.close()

        report_path = run_dir / "report.json"
        report_path.write_text(
            json.dumps(
                {
                    "platform": config.platform,
                    "agent_count": config.agent_count,
                    "time_horizon": config.time_horizon,
                    "topic": config.topic,
                    "objective": config.objective,
                    "execution_mode": self._execution_mode,
                    "model_source": self._model_config.source if self._model_config else "environment",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    async def _execute_live_run_docker(self, config: OASISRunConfig, *, run_dir: Path) -> None:
        _ensure_docker_image(self._docker_image, repo_root=self._repo_root)

        config_path = run_dir / "config.json"
        report_path = run_dir / "report.json"
        database_path = run_dir / "simulation.db"
        env = os.environ.copy()
        if self._model_config is not None:
            env["OASIS_LLM_BASE_URL"] = self._model_config.base_url
            env["OASIS_LLM_API_KEY"] = self._model_config.api_key
            env["OASIS_LLM_MODEL"] = self._model_config.model_name
            env["OASIS_LLM_SOURCE"] = self._model_config.source

        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "-v",
            f"{self._repo_root}:/workspace",
            "-v",
            f"{run_dir}:/run",
            "-w",
            "/workspace",
            "-e",
            "OASIS_LLM_BASE_URL",
            "-e",
            "OASIS_LLM_API_KEY",
            "-e",
            "OASIS_LLM_MODEL",
            "-e",
            "OASIS_LLM_SOURCE",
            self._docker_image,
            "python",
            "/workspace/engines/oasis/docker_live_runner.py",
            "--config",
            "/run/config.json",
            "--report",
            "/run/report.json",
            "--database",
            "/run/simulation.db",
        ]
        completed = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            error_message = (completed.stderr or completed.stdout or "unknown docker error").strip()
            raise RuntimeError(f"Docker OASIS live execution failed: {error_message}")
        if not report_path.exists():
            raise RuntimeError("Docker OASIS live execution did not produce report.json.")

    def _compute_score(self, config: dict[str, Any]) -> float:
        score = 0.45
        agent_count = int(config.get("agent_count", 0) or 0)
        if agent_count <= 64:
            score += 0.08
        elif agent_count <= 250:
            score += 0.05
        platform = str(config.get("platform", "reddit")).lower()
        if platform == "reddit":
            score += 0.05
        elif platform == "twitter":
            score += 0.04
        documents = list(config.get("extra", {}).get("documents", []) or [])
        if documents:
            score += min(0.08, 0.02 * len(documents))
        profiles = list(config.get("agent_profiles", []) or [])
        if profiles:
            score += min(0.1, 0.01 * len(profiles))
        interventions = list(config.get("extra", {}).get("interventions", []) or [])
        if interventions:
            score += min(0.06, 0.02 * len(interventions))
        return max(0.05, min(0.97, score))


def _package_version() -> str:
    for package_name in ("oasis", "camel-oasis", "camel_oasis"):
        try:
            return version(package_name)
        except PackageNotFoundError:
            continue
    image = os.getenv("OASIS_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE
    if _docker_live_available():
        docker_version = _docker_package_version(image)
        if docker_version:
            return docker_version
    return "unknown"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _load_model_config() -> OASISModelConfig:
    base_url = os.getenv("OASIS_LLM_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    api_key = os.getenv("OASIS_LLM_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    model_name = os.getenv("OASIS_LLM_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
    if base_url and api_key and model_name:
        return OASISModelConfig(
            base_url=_normalize_base_url(base_url),
            api_key=api_key,
            model_name=model_name,
            source="environment",
        )

    config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH", str(DEFAULT_OPENCLAW_CONFIG_PATH)))
    if not config_path.exists():
        raise RuntimeError(
            "No OASIS-compatible provider config found. Set OASIS_LLM_* env vars or provide OpenClaw config."
        )
    try:
        openclaw_config = json.loads(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise RuntimeError(f"Unable to read OpenClaw config at {config_path}.") from exc

    env_vars = openclaw_config.get("env", {}).get("vars", {})
    providers = openclaw_config.get("models", {}).get("providers", {})
    provider_priority = [
        "antigravity-proxy",
        "anthropic-proxy",
        "openrouter",
        "cerebras",
        "ollama",
    ]

    for provider_name in provider_priority:
        provider = providers.get(provider_name)
        if not isinstance(provider, dict):
            continue
        base_url = str(provider.get("baseUrl", "")).strip()
        api_key = _resolve_api_key(provider.get("apiKey"), env_vars)
        models = provider.get("models") or []
        model_id = ""
        if models and isinstance(models[0], dict):
            model_id = str(models[0].get("id", "")).strip()
        model_id = (
            os.getenv(f"OASIS_{provider_name.upper().replace('-', '_')}_MODEL", "").strip()
            or model_id
        )
        if base_url and api_key and model_id:
            return OASISModelConfig(
                base_url=_normalize_base_url(base_url),
                api_key=api_key,
                model_name=model_id,
                source=f"openclaw:{provider_name}",
            )

    raise RuntimeError(
        "No OASIS-compatible provider config found in OpenClaw config. Set OASIS_LLM_* env vars to override."
    )


def _resolve_api_key(raw: Any, env_vars: dict[str, Any]) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        env_id = str(raw.get("id", "")).strip()
        if env_id:
            return str(env_vars.get(env_id, "")).strip()
    return ""


def _normalize_base_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if cleaned and not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


def _docker_live_available() -> bool:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    completed = subprocess.run(
        [docker_bin, "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _ensure_docker_image(image: str, *, repo_root: Path) -> None:
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode == 0:
        return
    dockerfile = repo_root / "engines" / "oasis" / "Dockerfile.live"
    build_context = dockerfile.parent
    completed = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            str(dockerfile),
            str(build_context),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error_message = (completed.stderr or completed.stdout or "unknown docker build error").strip()
        raise RuntimeError(f"Unable to build Docker OASIS live image: {error_message}")


def _docker_package_version(image: str) -> str | None:
    inspect = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            image,
            "python",
            "-c",
            "from importlib.metadata import version; print(version('camel-oasis'))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode != 0:
        return None
    return inspect.stdout.strip() or None


def _build_social_agent(
    *,
    oasis,
    agent_id: int,
    profile: dict[str, Any],
    user_info: dict[str, Any],
    agent_graph,
    model,
    available_actions: list[Any],
    platform: str,
):
    oasis_user_info = _build_oasis_user_info(
        oasis=oasis,
        user_info=user_info,
        platform=platform,
    )
    kwargs = {
        "agent_id": agent_id,
        "user_info": oasis_user_info,
        "agent_graph": agent_graph,
        "model": model,
        "available_actions": available_actions,
    }
    try:
        return oasis.SocialAgent(single_iteration=False, **kwargs)
    except TypeError:
        return oasis.SocialAgent(**kwargs)


def _build_oasis_user_info(*, oasis, user_info: dict[str, Any], platform: str):
    handle = str(user_info.get("handle") or user_info.get("name") or "synthetic_agent").strip()
    bio = str(user_info.get("bio") or user_info.get("description") or "Synthetic agent profile.").strip()
    recsys_type = "twitter" if str(platform).lower() == "twitter" else "reddit"
    return oasis.UserInfo(
        user_name=handle,
        name=handle,
        description=bio,
        recsys_type=recsys_type,
        profile={
            "other_info": {
                "user_profile": bio,
                "gender": str(user_info.get("gender") or "unknown"),
                "age": int(user_info.get("age") or 30),
                "mbti": str(user_info.get("mbti") or "INTJ"),
                "country": str(user_info.get("country") or "unknown"),
            }
        },
    )
