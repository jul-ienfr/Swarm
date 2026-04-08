"""Generic improvement-loop framework for benchmark-driven iterative optimization."""

from .controller import ImprovementLoopController
from .models import (
    ImprovementLoopRun,
    ImprovementRoundRecord,
    ImprovementRuntime,
    LoopDecision,
    LoopMode,
    TargetDescriptor,
    TargetInspection,
)
from .protocols import ImprovementTarget
from .registry import build_default_controller
from .targets import (
    DEFAULT_CONFIG_TARGET_BENCHMARK_PATH,
    DEFAULT_CONFIG_TARGET_MEMORY_PATH,
    DEFAULT_HARNESS_TARGET_STATE_PATH,
    ConfigImprovementTarget,
    HarnessImprovementTarget,
)

__all__ = [
    "ConfigImprovementTarget",
    "DEFAULT_CONFIG_TARGET_BENCHMARK_PATH",
    "DEFAULT_CONFIG_TARGET_MEMORY_PATH",
    "DEFAULT_HARNESS_TARGET_STATE_PATH",
    "HarnessImprovementTarget",
    "ImprovementLoopController",
    "ImprovementLoopRun",
    "ImprovementRoundRecord",
    "ImprovementTarget",
    "ImprovementRuntime",
    "LoopDecision",
    "LoopMode",
    "TargetDescriptor",
    "TargetInspection",
    "build_default_controller",
]
