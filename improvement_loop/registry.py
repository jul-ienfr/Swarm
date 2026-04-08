from __future__ import annotations

from .controller import ImprovementLoopController
from .models import ImprovementRuntime
from .targets import ConfigImprovementTarget, HarnessImprovementTarget


def build_default_controller(
    *,
    runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
    allow_fallback: bool = True,
) -> ImprovementLoopController:
    controller = ImprovementLoopController()
    controller.register_target(
        ConfigImprovementTarget(runtime=runtime, allow_fallback=allow_fallback),
    )
    controller.register_target(
        HarnessImprovementTarget(runtime=runtime, allow_fallback=allow_fallback),
    )
    return controller
