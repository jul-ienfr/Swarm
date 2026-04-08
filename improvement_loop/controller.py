from __future__ import annotations

import inspect as _inspect

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


class ImprovementLoopController:
    def __init__(self, targets: dict[str, ImprovementTarget] | None = None) -> None:
        self._targets = dict(targets or {})

    def register_target(self, target: ImprovementTarget) -> None:
        descriptor = target.describe()
        self._targets[descriptor.target_id] = target

    def list_targets(self) -> list[TargetDescriptor]:
        return [self._targets[target_id].describe() for target_id in sorted(self._targets)]

    def inspect_target(
        self,
        target_id: str,
        *,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
        **target_kwargs,
    ) -> TargetInspection:
        return self._call_target(
            self._get_target(target_id),
            "inspect",
            runtime=runtime,
            allow_fallback=allow_fallback,
            **target_kwargs,
        )

    def run_round(
        self,
        target_id: str,
        *,
        mode: LoopMode = LoopMode.suggest_only,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
        **target_kwargs,
    ) -> ImprovementRoundRecord:
        return self._call_target(
            self._get_target(target_id),
            "run_round",
            mode,
            runtime=runtime,
            allow_fallback=allow_fallback,
            **target_kwargs,
        )

    def run_loop(
        self,
        target_id: str,
        *,
        mode: LoopMode = LoopMode.suggest_only,
        max_rounds: int = 5,
        runtime: ImprovementRuntime = ImprovementRuntime.pydanticai,
        allow_fallback: bool = True,
        **target_kwargs,
    ) -> ImprovementLoopRun:
        if max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")

        rounds: list[ImprovementRoundRecord] = []
        stopped_reason = None
        for _ in range(max_rounds):
            record = self.run_round(
                target_id,
                mode=mode,
                runtime=runtime,
                allow_fallback=allow_fallback,
                **target_kwargs,
            )
            rounds.append(record)
            if record.decision == LoopDecision.halt:
                stopped_reason = record.halted_reason or "Target requested loop halt."
                break

        if stopped_reason is None and rounds and len(rounds) >= max_rounds:
            stopped_reason = f"Reached max_rounds={max_rounds}."

        return ImprovementLoopRun(
            target_id=target_id,
            mode=mode,
            max_rounds=max_rounds,
            completed_rounds=len(rounds),
            rounds=rounds,
            stopped_reason=stopped_reason,
        )

    @staticmethod
    def _call_target(target: ImprovementTarget, method_name: str, *args, **kwargs):
        method = getattr(target, method_name)
        try:
            signature = _inspect.signature(method)
        except (TypeError, ValueError):
            return method(*args, **kwargs)

        if any(param.kind == _inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return method(*args, **kwargs)

        filtered_kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return method(*args, **filtered_kwargs)

    def _get_target(self, target_id: str) -> ImprovementTarget:
        try:
            return self._targets[target_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._targets)) or "none"
            raise KeyError(f"Unknown improvement target '{target_id}'. Available targets: {available}.") from exc
