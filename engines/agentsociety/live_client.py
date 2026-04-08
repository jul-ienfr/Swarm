"""
Live AgentSociety backend powered by the official package and local process execution.

This client is the production path for harness and adapter runs. It provisions the
official map asset when needed, prefers stable OpenAI-compatible providers discovered
from OpenClaw, and stores per-run metadata so status/result polling remains stable.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

from huggingface_hub import hf_hub_download

from .translator import AgentSocietyRunConfig


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
    engine_version: str = field(default_factory=lambda: version("agentsociety"))


@dataclass(slots=True)
class LLMEndpoint:
    base_url: str
    api_key: str
    model: str
    provider: str = "vllm"
    concurrency: int = 1
    timeout: int = 60
    label: str | None = None

    def to_config_dict(
        self,
        *,
        concurrency: int | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url.rstrip("/"),
            "api_key": self.api_key,
            "model": self.model,
            "concurrency": int(concurrency or self.concurrency),
            "timeout": int(timeout or self.timeout),
        }

    @property
    def backend_label(self) -> str:
        raw_label = self.label or self.model
        return f"{raw_label}@{self.base_url.rstrip('/')}"


@dataclass(slots=True)
class _RunMetadata:
    engine_run_id: str
    exp_id: str
    tenant_id: str
    runtime_run_id: str
    run_dir: str
    env_home_dir: str
    map_path: str
    status_file: str
    log_file: str
    sqlite_path: str
    config_path: str
    estimated_total_steps: int
    timeout_seconds: int
    created_at: float
    llm_backends: list[str] = field(default_factory=list)
    cancelled: bool = False
    timed_out: bool = False
    failure_reason: str | None = None
    failure_code: str | None = None
    cleaned_up: bool = False


class AgentSocietyProcessClient:
    """
    Launches real AgentSociety experiments via the official process executor.
    """

    _DEFAULT_MAP_REPO = "tsinghua-fib-lab/daily-mobility-generation-benchmark"
    _DEFAULT_MAP_FILE = "beijing.pb"
    _STEP_LOG_PATTERN = re.compile(r"step (?P<step>\d+)")
    _LLM_COUNT_PATTERN = re.compile(r"LLM request count:\s*(?P<count>\d+)")

    def __init__(
        self,
        *,
        runs_root: Path,
        map_path: Path,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        llm_configs: list[LLMEndpoint | dict[str, Any]] | None = None,
        tenant_id: str = "langgraph-swarm",
        auto_download_map: bool = True,
    ) -> None:
        self._runs_root = runs_root
        self._map_path = map_path
        self._llm_configs = self._normalize_llm_configs(
            llm_configs=llm_configs,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )
        self._tenant_id = tenant_id
        self._auto_download_map = auto_download_map
        self._runs_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_environment(cls) -> "AgentSocietyProcessClient":
        repo_root = Path(__file__).resolve().parents[2]
        runs_root = Path(
            os.getenv(
                "AGENTSOCIETY_RUNS_DIR",
                repo_root / "data" / "agentsociety" / "live-runs",
            )
        )
        map_path = Path(
            os.getenv(
                "AGENTSOCIETY_MAP_PATH",
                repo_root / "data" / "agentsociety" / cls._DEFAULT_MAP_FILE,
            )
        )
        tenant_id = os.getenv("AGENTSOCIETY_TENANT_ID", "langgraph-swarm")
        openclaw_config_path = Path(
            os.getenv("OPENCLAW_CONFIG_PATH", "/home/jul/.openclaw/openclaw.json")
        )
        llm_configs_json = os.getenv("AGENTSOCIETY_LLM_CONFIGS_JSON", "").strip()
        llm_base_url = os.getenv("AGENTSOCIETY_LLM_BASE_URL", "").strip()
        llm_api_key = os.getenv("AGENTSOCIETY_LLM_API_KEY", "").strip()
        llm_model = os.getenv("AGENTSOCIETY_LLM_MODEL", "").strip()
        llm_configs: list[LLMEndpoint | dict[str, Any]] | None = None

        if llm_configs_json:
            payload = json.loads(llm_configs_json)
            if not isinstance(payload, list) or not payload:
                raise RuntimeError("AGENTSOCIETY_LLM_CONFIGS_JSON must be a non-empty JSON array.")
            llm_configs = payload
        elif llm_base_url or llm_api_key or llm_model:
            if not (llm_base_url and llm_api_key and llm_model):
                raise RuntimeError(
                    "AGENTSOCIETY_LLM_BASE_URL, AGENTSOCIETY_LLM_API_KEY, and AGENTSOCIETY_LLM_MODEL must all be set together."
                )
            llm_configs = [
                {
                    "base_url": llm_base_url,
                    "api_key": llm_api_key,
                    "model": llm_model,
                    "label": "env-override",
                }
            ]
        else:
            if not openclaw_config_path.exists():
                raise RuntimeError(
                    f"OpenClaw config not found at {openclaw_config_path}; cannot discover AgentSociety LLM backends."
                )
            openclaw_config = json.loads(openclaw_config_path.read_text())
            llm_configs = _discover_llm_configs(openclaw_config)
            if not llm_configs:
                raise RuntimeError(
                    "No usable AgentSociety LLM backends could be discovered from OpenClaw config."
                )

        return cls(
            runs_root=runs_root,
            map_path=map_path,
            llm_configs=llm_configs,
            tenant_id=tenant_id,
            auto_download_map=_env_flag("AGENTSOCIETY_AUTO_DOWNLOAD_MAP", True),
        )

    def create_run(self, config: AgentSocietyRunConfig) -> str:
        self._ensure_map_path()

        engine_run_id = f"as_live_{uuid4().hex[:12]}"
        exp_id = str(uuid4())
        run_dir = self._runs_root / engine_run_id
        env_home_dir = run_dir / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=True)
        env_home_dir.mkdir(parents=True, exist_ok=True)

        config_dict = self._build_config_dict(
            config=config,
            exp_id=exp_id,
            env_home_dir=env_home_dir,
        )
        config_path = run_dir / "config.json"
        config_path.write_text(json.dumps(config_dict, indent=2))

        status_file = run_dir / "webui" / "executor" / self._tenant_id / exp_id / "status.json"
        log_file = run_dir / "webui" / "executor" / self._tenant_id / exp_id / "log.txt"
        sqlite_path = env_home_dir / "sqlite.db"

        metadata = _RunMetadata(
            engine_run_id=engine_run_id,
            exp_id=exp_id,
            tenant_id=self._tenant_id,
            runtime_run_id=config.run_id,
            run_dir=str(run_dir),
            env_home_dir=str(env_home_dir),
            map_path=str(self._map_path),
            status_file=str(status_file),
            log_file=str(log_file),
            sqlite_path=str(sqlite_path),
            config_path=str(config_path),
            estimated_total_steps=_estimate_total_steps(
                time_horizon=config.time_horizon,
                step_seconds=_extract_step_seconds(config.extra),
            ),
            timeout_seconds=int(config.extra.get("timeout_seconds", 1800) or 1800),
            created_at=time.time(),
            llm_backends=[endpoint.backend_label for endpoint in self._llm_configs],
        )
        self._write_metadata(metadata)

        executor = self._build_executor(run_dir)
        config_base64 = base64.b64encode(json.dumps(config_dict).encode("utf-8")).decode("utf-8")
        self._run_async(
            executor.create(
                config_base64=config_base64,
                tenant_id=self._tenant_id,
            )
        )
        return engine_run_id

    def get_run_status(self, engine_run_id: str) -> LiveRunStatus:
        metadata = self._read_metadata(engine_run_id)
        logs = self._safe_read_text(Path(metadata.log_file))
        current_step = _extract_current_step(logs)
        progress_pct = _estimate_progress(current_step, metadata.estimated_total_steps)

        if metadata.timed_out:
            self._cleanup_terminal_run(metadata)
            return LiveRunStatus(
                status="TIMED_OUT",
                progress_pct=progress_pct or 100.0,
                current_step=current_step,
                message=metadata.failure_reason or "Run timed out.",
            )

        if metadata.cancelled:
            self._cleanup_terminal_run(metadata)
            return LiveRunStatus(
                status="CANCELLED",
                progress_pct=progress_pct or 100.0,
                current_step=current_step,
                message=metadata.failure_reason or "Run was cancelled.",
            )

        if metadata.failure_reason:
            self._cleanup_terminal_run(metadata)
            return LiveRunStatus(
                status="FAILED",
                progress_pct=progress_pct,
                current_step=current_step,
                message=metadata.failure_reason,
            )

        status_payload = _read_status_payload(Path(metadata.status_file))
        if status_payload is None:
            if _has_resource_exhaustion(logs):
                return self._fail_run(
                    metadata,
                    progress_pct=progress_pct,
                    current_step=current_step,
                    reason="LLM backend returned repeated resource exhaustion errors before the run became healthy.",
                    code="capacity_exceeded",
                )
            if self._deadline_exceeded(metadata):
                return self._timeout_run(
                    metadata,
                    progress_pct=progress_pct,
                    current_step=current_step,
                )
            return LiveRunStatus(status="PENDING", progress_pct=0.0, current_step=0)

        status_value = str(status_payload.get("status", "PENDING"))
        pid = status_payload.get("pid")
        process_state = _read_process_state(pid) if pid else None
        if status_value == "Running" and process_state in {None, "Z"}:
            status_value = "Terminated"

        if status_value == "Running":
            if _has_resource_exhaustion(logs):
                return self._fail_run(
                    metadata,
                    progress_pct=progress_pct,
                    current_step=current_step,
                    reason="LLM backend returned repeated resource exhaustion errors while the run was active.",
                    code="capacity_exceeded",
                )
            if self._deadline_exceeded(metadata):
                return self._timeout_run(
                    metadata,
                    progress_pct=progress_pct,
                    current_step=current_step,
                )
            return LiveRunStatus(
                status="RUNNING",
                progress_pct=progress_pct,
                current_step=current_step,
                message="AgentSociety run is active.",
            )

        sqlite_path = Path(metadata.sqlite_path)
        experiment = _read_experiment_summary(sqlite_path)
        if experiment and experiment["status"] == 2:
            self._cleanup_terminal_run(metadata)
            return LiveRunStatus(
                status="COMPLETED",
                progress_pct=100.0,
                current_step=current_step,
                message="Run completed.",
            )
        if experiment and (experiment["status"] == 3 or experiment["error"]):
            self._cleanup_terminal_run(metadata)
            return LiveRunStatus(
                status="FAILED",
                progress_pct=progress_pct,
                current_step=current_step,
                message="Run terminated with an AgentSociety experiment error.",
            )

        self._cleanup_terminal_run(metadata)
        return LiveRunStatus(
            status="FAILED",
            progress_pct=progress_pct,
            current_step=current_step,
            message="Run terminated without a successful artifact set.",
        )

    def get_result(self, engine_run_id: str) -> LiveRunResult:
        metadata = self._read_metadata(engine_run_id)
        status = self.get_run_status(engine_run_id)
        if status.status != "COMPLETED":
            raise RuntimeError(f"AgentSociety run {engine_run_id} is not completed: {status.status}")

        sqlite_path = Path(metadata.sqlite_path)
        logs = self._safe_read_text(Path(metadata.log_file))
        table_counts = _collect_table_counts(sqlite_path)
        experiment = _read_experiment_summary(sqlite_path) or {
            "input_tokens": 0,
            "output_tokens": 0,
            "error": "",
        }
        llm_request_count = _extract_llm_request_count(logs)
        metrics = {
            "engagement_index": _compute_engagement_index(
                llm_request_count=llm_request_count,
                table_counts=table_counts,
            ),
            "llm_request_count": float(llm_request_count),
            "table_count": float(len(table_counts)),
            "database_size_mb": round(sqlite_path.stat().st_size / (1024 * 1024), 3),
            "input_tokens": float(experiment["input_tokens"]),
            "output_tokens": float(experiment["output_tokens"]),
        }

        artifacts = [
            _artifact_dict("config", "config", Path(metadata.config_path), "application/json"),
            _artifact_dict("logs", "log", Path(metadata.log_file), "text/plain"),
            _artifact_dict("sqlite", "database", sqlite_path, "application/x-sqlite3"),
        ]
        sim_binary = Path(metadata.env_home_dir) / "agentsociety-sim-oss"
        if sim_binary.exists():
            artifacts.append(
                _artifact_dict(
                    "sim-binary",
                    "binary",
                    sim_binary,
                    "application/octet-stream",
                )
            )

        summary = (
            f"AgentSociety live run {engine_run_id} completed with "
            f"{llm_request_count} LLM requests and {len(table_counts)} populated tables."
        )
        return LiveRunResult(
            summary=summary,
            metrics=metrics,
            artifacts=artifacts,
            scenarios=[
                {
                    "scenario_id": engine_run_id,
                    "description": "Observed AgentSociety live run completed successfully.",
                    "llm_request_count": llm_request_count,
                    "tables_recorded": sorted(table_counts.keys()),
                }
            ],
            risks=[],
            recommendations=[
                {
                    "action": "inspect_sqlite_artifacts",
                    "detail": "Use the normalized sqlite artifact for downstream analysis and replay.",
                }
            ],
        )

    def cancel_run(self, engine_run_id: str) -> None:
        metadata = self._read_metadata(engine_run_id)
        self._delete_run(metadata)
        metadata.cancelled = True
        metadata.failure_reason = "Run was cancelled by the adapter."
        self._write_metadata(metadata)

    def _build_config_dict(
        self,
        *,
        config: AgentSocietyRunConfig,
        exp_id: str,
        env_home_dir: Path,
    ) -> dict[str, Any]:
        requested_agents = max(1, int(config.max_agents))
        effective_agents = int(config.extra.get("effective_max_agents", requested_agents))
        ticks_per_step = _extract_step_seconds(config.extra)
        llm_concurrency = int(config.extra.get("llm_concurrency", 4))
        llm_timeout = int(config.extra.get("llm_timeout", 60))

        return {
            "llm": [
                endpoint.to_config_dict(
                    concurrency=llm_concurrency,
                    timeout=llm_timeout,
                )
                for endpoint in self._llm_configs
            ],
            "env": {
                "db": {
                    "enabled": True,
                    "db_type": "sqlite",
                },
                "home_dir": str(env_home_dir),
            },
            "map": {
                "file_path": str(self._map_path),
            },
            "agents": {
                "citizens": [
                    {
                        "agent_class": "citizen",
                        "number": effective_agents,
                    }
                ]
            },
            "exp": {
                "id": exp_id,
                "name": config.run_id,
                "workflow": [
                    {
                        "type": "run",
                        "days": _parse_days(config.time_horizon),
                        "ticks_per_step": ticks_per_step,
                    }
                ],
                "environment": {
                    "start_tick": int(config.environment.get("start_tick", 8 * 60 * 60)),
                    "metric_interval": int(config.environment.get("metric_interval", 3600)),
                    "weather": config.environment.get("weather", "The weather is sunny"),
                    "temperature": config.environment.get("temperature", "The temperature is 23C"),
                    "workday": bool(config.environment.get("workday", True)),
                    "other_information": _stringify_other_information(
                        config.environment.get("seed", {})
                    ),
                },
            },
            "logging_level": "INFO",
        }

    def _ensure_map_path(self) -> None:
        if self._map_path.exists():
            return
        if not self._auto_download_map:
            raise RuntimeError(
                f"AgentSociety map file is missing at {self._map_path} and auto-download is disabled."
            )
        self._map_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=self._DEFAULT_MAP_REPO,
            filename=self._DEFAULT_MAP_FILE,
            repo_type="dataset",
            local_dir=str(self._map_path.parent),
        )
        if Path(downloaded) != self._map_path and not self._map_path.exists():
            Path(downloaded).replace(self._map_path)

    @staticmethod
    def _normalize_llm_configs(
        *,
        llm_configs: list[LLMEndpoint | dict[str, Any]] | None,
        llm_base_url: str | None,
        llm_api_key: str | None,
        llm_model: str | None,
    ) -> list[LLMEndpoint]:
        configs: list[LLMEndpoint] = []
        if llm_configs:
            for config in llm_configs:
                if isinstance(config, LLMEndpoint):
                    configs.append(config)
                else:
                    configs.append(LLMEndpoint(**config))
        elif llm_base_url and llm_api_key and llm_model:
            configs.append(
                LLMEndpoint(
                    base_url=llm_base_url,
                    api_key=llm_api_key,
                    model=llm_model,
                )
            )

        if not configs:
            raise ValueError("At least one AgentSociety LLM backend must be configured.")
        return configs

    @staticmethod
    def _build_executor(run_dir: Path):
        from agentsociety.executor.process import ProcessExecutor

        return ProcessExecutor(str(run_dir))

    @staticmethod
    def _run_async(awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("AgentSocietyProcessClient cannot be called from an active asyncio loop.")

    def _metadata_path(self, engine_run_id: str) -> Path:
        return self._runs_root / engine_run_id / "metadata.json"

    def _write_metadata(self, metadata: _RunMetadata) -> None:
        payload = asdict(metadata)
        path = self._metadata_path(metadata.engine_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def _read_metadata(self, engine_run_id: str) -> _RunMetadata:
        path = self._metadata_path(engine_run_id)
        if not path.exists():
            raise KeyError(f"Unknown engine run id: {engine_run_id}")
        payload = json.loads(path.read_text())
        return _RunMetadata(**payload)

    @staticmethod
    def _safe_read_text(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(errors="replace")

    @staticmethod
    def _deadline_exceeded(metadata: _RunMetadata) -> bool:
        return (time.time() - metadata.created_at) >= max(1, metadata.timeout_seconds)

    def _delete_run(self, metadata: _RunMetadata) -> None:
        executor = self._build_executor(Path(metadata.run_dir))
        try:
            self._run_async(executor.delete(metadata.tenant_id, metadata.exp_id))
        except Exception:
            # Deletion is best-effort; status/result normalization still matters more.
            pass

    def _cleanup_terminal_run(self, metadata: _RunMetadata) -> None:
        if metadata.cleaned_up:
            return
        self._delete_run(metadata)
        metadata.cleaned_up = True
        self._write_metadata(metadata)

    def _timeout_run(
        self,
        metadata: _RunMetadata,
        *,
        progress_pct: float | None,
        current_step: int | None,
    ) -> LiveRunStatus:
        metadata.timed_out = True
        metadata.failure_reason = (
            f"Run exceeded timeout_seconds={metadata.timeout_seconds} and was cancelled."
        )
        metadata.failure_code = "timeout"
        self._cleanup_terminal_run(metadata)
        self._write_metadata(metadata)
        return LiveRunStatus(
            status="TIMED_OUT",
            progress_pct=progress_pct or 100.0,
            current_step=current_step,
            message=metadata.failure_reason,
        )

    def _fail_run(
        self,
        metadata: _RunMetadata,
        *,
        progress_pct: float | None,
        current_step: int | None,
        reason: str,
        code: str,
    ) -> LiveRunStatus:
        metadata.failure_reason = reason
        metadata.failure_code = code
        self._cleanup_terminal_run(metadata)
        self._write_metadata(metadata)
        return LiveRunStatus(
            status="FAILED",
            progress_pct=progress_pct,
            current_step=current_step,
            message=reason,
        )


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _parse_days(time_horizon: str) -> float:
    horizon = str(time_horizon).strip().lower()
    if horizon.endswith("d"):
        return max(0.005, float(horizon[:-1]))
    if horizon.endswith("h"):
        return max(0.005, float(horizon[:-1]) / 24.0)
    return max(0.005, float(horizon))


def _extract_step_seconds(extra: dict[str, Any]) -> int:
    return int(extra.get("ticks_per_step", extra.get("step_seconds", 300)) or 300)


def _estimate_total_steps(time_horizon: str, step_seconds: int) -> int:
    days = _parse_days(time_horizon)
    total_seconds = max(step_seconds, int(days * 24 * 60 * 60))
    return max(1, int(total_seconds / max(1, step_seconds)))


def _extract_current_step(logs: str) -> int | None:
    matches = list(AgentSocietyProcessClient._STEP_LOG_PATTERN.finditer(logs))
    if not matches:
        return None
    return int(matches[-1].group("step"))


def _extract_llm_request_count(logs: str) -> int:
    matches = list(AgentSocietyProcessClient._LLM_COUNT_PATTERN.finditer(logs))
    if not matches:
        return 0
    return int(matches[-1].group("count"))


def _estimate_progress(current_step: int | None, estimated_total_steps: int) -> float | None:
    if current_step is None:
        return None
    return round(min(99.0, 100.0 * float(current_step + 1) / float(max(1, estimated_total_steps))), 2)


def _collect_table_counts(sqlite_path: Path) -> dict[str, int]:
    if not sqlite_path.exists():
        return {}

    conn = sqlite3.connect(sqlite_path)
    try:
        cursor = conn.cursor()
        tables = [
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        for table in tables:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                continue
            counts[table] = int(count)
        return counts
    finally:
        conn.close()


def _compute_engagement_index(*, llm_request_count: int, table_counts: dict[str, int]) -> float:
    base = 0.55
    if llm_request_count > 0:
        base += min(0.25, 0.03 * llm_request_count)
    non_empty_tables = sum(1 for count in table_counts.values() if count > 0)
    if non_empty_tables > 0:
        base += min(0.20, 0.02 * non_empty_tables)
    return round(min(0.95, max(0.05, base)), 3)


def _artifact_dict(name: str, artifact_type: str, path: Path, content_type: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": artifact_type,
        "path": path.name,
        "uri": str(path.resolve()),
        "content_type": content_type,
    }


def _read_experiment_summary(sqlite_path: Path) -> dict[str, Any] | None:
    if not sqlite_path.exists():
        return None

    conn = sqlite3.connect(sqlite_path)
    try:
        cursor = conn.cursor()
        tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "as_experiment" not in tables:
            return None
        row = cursor.execute(
            "SELECT status, input_tokens, output_tokens, error FROM as_experiment LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "status": int(row[0]),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "error": str(row[3] or ""),
        }
    finally:
        conn.close()


def _stringify_other_information(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _read_status_payload(status_path: Path) -> dict[str, Any] | None:
    if not status_path.exists():
        return None
    return json.loads(status_path.read_text())


def _read_process_state(pid: Any) -> str | None:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None

    stat_path = Path(f"/proc/{pid_int}/stat")
    if not stat_path.exists():
        return None
    parts = stat_path.read_text().split()
    if len(parts) < 3:
        return None
    return parts[2]


def _has_resource_exhaustion(logs: str) -> bool:
    lowered = logs.lower()
    exhausted_hits = lowered.count("resource has been exhausted")
    quota_hits = lowered.count("error code: 429")
    return exhausted_hits >= 2 or quota_hits >= 2


def _discover_llm_configs(openclaw_config: dict[str, Any]) -> list[LLMEndpoint]:
    env_vars = openclaw_config.get("env", {}).get("vars", {})
    providers = openclaw_config.get("models", {}).get("providers", {})
    configs: list[LLMEndpoint] = []

    def add_endpoint(
        *,
        provider_name: str,
        env_var_name: str | None,
        default_model: str,
        label: str,
    ) -> None:
        provider = providers.get(provider_name) or {}
        base_url = str(provider.get("baseUrl", "")).strip()
        api_key = ""
        if isinstance(provider.get("apiKey"), str):
            api_key = str(provider.get("apiKey", "")).strip()
        if not api_key and env_var_name:
            api_key = str(env_vars.get(env_var_name, "")).strip()
        if not base_url or not api_key:
            return
        model = os.getenv(f"AGENTSOCIETY_{label.upper()}_MODEL", default_model).strip() or default_model
        configs.append(
            LLMEndpoint(
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=model,
                label=label,
            )
        )

    add_endpoint(
        provider_name="cerebras",
        env_var_name="CEREBRAS_API_KEY",
        default_model="llama3.1-8b",
        label="cerebras",
    )

    if _env_flag("AGENTSOCIETY_INCLUDE_NVIDIA", False):
        add_endpoint(
            provider_name="nvidia",
            env_var_name="NVIDIA_API_KEY",
            default_model="meta/llama-3.3-70b-instruct",
            label="nvidia",
        )

    if _env_flag("AGENTSOCIETY_INCLUDE_MISTRAL", False):
        add_endpoint(
            provider_name="mistral",
            env_var_name="MISTRAL_API_KEY",
            default_model="mistral-small-latest",
            label="mistral",
        )

    if _env_flag("AGENTSOCIETY_INCLUDE_PROXY_FALLBACK", False):
        provider = providers.get("antigravity-proxy") or {}
        base_url = str(provider.get("baseUrl", "")).rstrip("/")
        api_key = str(provider.get("apiKey", "")).strip()
        if base_url and api_key:
            configs.append(
                LLMEndpoint(
                    base_url=f"{base_url}/v1",
                    api_key=api_key,
                    model=os.getenv("AGENTSOCIETY_PROXY_MODEL", "claude-haiku-4-5").strip() or "claude-haiku-4-5",
                    label="antigravity-proxy",
                )
            )

    if _env_flag("AGENTSOCIETY_INCLUDE_OLLAMA", False):
        ollama_provider = providers.get("ollama") or {}
        base_url = str(ollama_provider.get("baseUrl", "")).strip()
        if base_url:
            configs.append(
                LLMEndpoint(
                    base_url=base_url.rstrip("/"),
                    api_key=str(ollama_provider.get("apiKey") or "ollama"),
                    model=os.getenv("AGENTSOCIETY_OLLAMA_MODEL", "qwen2.5:14b").strip() or "qwen2.5:14b",
                    label="ollama",
                    timeout=int(os.getenv("AGENTSOCIETY_OLLAMA_TIMEOUT", "180")),
                )
            )

    return configs
