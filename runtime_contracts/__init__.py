"""Shared v1 contracts between Swarm Core, runtimes, and simulation adapters."""

from .adapter_command import (
    AdapterCommand,
    AdapterCommandV1,
    ControlParams,
    EngineTarget,
    ProgressGranularity,
    SeedMaterials,
    SimulationParameters,
)
from .adapter_result import (
    AdapterResultV1,
    EngineErrorCode,
    EngineMeta,
    NormalizedArtifact,
    NormalizedError,
    NormalizedMetric,
    ProgressInfo,
    RunStatus,
)
from .intent import (
    EnginePreference,
    IntentConstraints,
    IntentContext,
    IntentInputs,
    IntentPolicy,
    SimulationIntentV1,
    TaskType,
)

__all__ = [
    "AdapterCommand",
    "AdapterCommandV1",
    "AdapterResultV1",
    "ControlParams",
    "EngineErrorCode",
    "EngineMeta",
    "EnginePreference",
    "EngineTarget",
    "IntentConstraints",
    "IntentContext",
    "IntentInputs",
    "IntentPolicy",
    "NormalizedArtifact",
    "NormalizedError",
    "NormalizedMetric",
    "ProgressGranularity",
    "ProgressInfo",
    "RunStatus",
    "SeedMaterials",
    "SimulationIntentV1",
    "SimulationParameters",
    "TaskType",
]
