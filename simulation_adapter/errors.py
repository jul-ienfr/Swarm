from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime_contracts.adapter_result import EngineErrorCode, NormalizedError, RunStatus


@dataclass(slots=True)
class AdapterError(Exception):
    code: EngineErrorCode
    message: str
    retryable: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.failed

    def __str__(self) -> str:
        return self.message

    def to_normalized_error(self) -> NormalizedError:
        return NormalizedError.from_code(
            self.code,
            self.message,
            retryable=self.retryable,
            detail=self.detail,
        )


class EngineUnavailableError(AdapterError):
    def __init__(self, engine: str, detail: str | None = None):
        super().__init__(
            code=EngineErrorCode.engine_unavailable,
            message=f"Engine '{engine}' is unavailable.",
            retryable=True,
            detail={"engine": engine, "detail": detail} if detail else {"engine": engine},
            status=RunStatus.engine_unavailable,
        )


class VersionMismatchError(AdapterError):
    def __init__(self, expected: str, received: str):
        super().__init__(
            code=EngineErrorCode.version_mismatch,
            message=f"Adapter version mismatch: expected {expected}, received {received}.",
            retryable=False,
            detail={"expected": expected, "received": received},
            status=RunStatus.failed,
        )


class InvalidConfigError(AdapterError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(
            code=EngineErrorCode.invalid_config,
            message=message,
            retryable=False,
            detail=detail or {},
            status=RunStatus.failed,
        )
