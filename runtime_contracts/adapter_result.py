from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    engine_unavailable = "engine_unavailable"

    @property
    def is_terminal(self) -> bool:
        return self in {
            RunStatus.completed,
            RunStatus.failed,
            RunStatus.cancelled,
            RunStatus.timed_out,
            RunStatus.engine_unavailable,
        }


class EngineErrorCode(str, Enum):
    transient_failure = "transient_failure"
    invalid_config = "invalid_config"
    capacity_exceeded = "capacity_exceeded"
    engine_unavailable = "engine_unavailable"
    timeout = "timeout"
    cancelled = "cancelled"
    version_mismatch = "version_mismatch"
    unknown = "unknown"


class ProgressInfo(BaseModel):
    percent_complete: float | None = None
    current_step: int | None = None
    message: str | None = None


class NormalizedMetric(BaseModel):
    name: str
    value: float
    unit: str
    tags: dict[str, str] = Field(default_factory=dict)


class NormalizedArtifact(BaseModel):
    name: str
    artifact_type: str
    uri: str
    content_type: str | None = None


class NormalizedError(BaseModel):
    error_code: EngineErrorCode
    message: str
    retryable: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_code(
        cls,
        error_code: EngineErrorCode,
        message: str,
        *,
        retryable: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> "NormalizedError":
        return cls(
            error_code=error_code,
            message=message,
            retryable=retryable,
            detail=detail or {},
        )


class EngineMeta(BaseModel):
    engine: str | None = None
    engine_version: str | None = None
    adapter_version: str | None = None


class AdapterResultV1(BaseModel):
    adapter_version: str = "v1"
    runtime_run_id: str
    engine_run_id: str | None = None
    status: RunStatus
    summary: str | None = None
    metrics: list[NormalizedMetric] = Field(default_factory=list)
    scenarios: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    artifacts: list[NormalizedArtifact] = Field(default_factory=list)
    engine_meta: EngineMeta = Field(default_factory=EngineMeta)
    errors: list[NormalizedError] = Field(default_factory=list)
    progress: ProgressInfo | None = None
    correlation_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal
