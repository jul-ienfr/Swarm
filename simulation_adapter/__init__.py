"""Stable adapter boundary between runtimes and simulation engines."""

from .adapter import (
    CancelRunRequest,
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    GetResultRequest,
    GetStatusRequest,
    ResultResponse,
    SimulationEngineAdapter,
    StatusResponse,
)
from .mapping_store import RunMapping, RunMappingStore
from .service import AdapterService, SUPPORTED_ADAPTER_VERSION

__all__ = [
    "AdapterService",
    "CancelRunRequest",
    "CancelRunResponse",
    "CreateRunRequest",
    "CreateRunResponse",
    "GetResultRequest",
    "GetStatusRequest",
    "ResultResponse",
    "RunMapping",
    "RunMappingStore",
    "SUPPORTED_ADAPTER_VERSION",
    "SimulationEngineAdapter",
    "StatusResponse",
]
