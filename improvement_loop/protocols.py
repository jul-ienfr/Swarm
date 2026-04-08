from __future__ import annotations

from typing import Protocol

from .models import ImprovementRoundRecord, ImprovementRuntime, LoopMode, TargetDescriptor, TargetInspection


class ImprovementTarget(Protocol):
    def describe(self) -> TargetDescriptor: ...

    def inspect(
        self,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
    ) -> TargetInspection: ...

    def run_round(
        self,
        mode: LoopMode,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
    ) -> ImprovementRoundRecord: ...
