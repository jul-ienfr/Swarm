"""
Translates adapter requests into AgentSociety-native run configuration.
All engine-specific mapping logic stays inside this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation_adapter.adapter import CreateRunRequest


@dataclass
class AgentSocietyRunConfig:
    run_id: str
    max_agents: int
    time_horizon: str
    environment: dict[str, Any] = field(default_factory=dict)
    agent_profiles: list[dict[str, Any]] = field(default_factory=list)
    ray_config: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class AgentSocietyTranslator:
    def translate(self, request: CreateRunRequest) -> AgentSocietyRunConfig:
        params = request.parameters
        seeds = request.seed_materials
        extra = dict(params.extra)
        extra["timeout_seconds"] = request.control.timeout_seconds
        extra["budget_max"] = request.control.budget_max
        extra["progress_granularity"] = request.control.progress_granularity.value
        return AgentSocietyRunConfig(
            run_id=request.runtime_run_id,
            max_agents=params.max_agents,
            time_horizon=params.time_horizon,
            environment=self._build_environment(seeds),
            agent_profiles=self._build_profiles(seeds),
            ray_config=self._default_ray_config(params.max_agents),
            extra=extra,
        )

    def _build_environment(self, seeds) -> dict[str, Any]:
        return {
            "type": "urban",
            "seed": seeds.environment_seed,
            "documents": seeds.documents,
        }

    def _build_profiles(self, seeds) -> list[dict[str, Any]]:
        return [{"entity": entity} for entity in seeds.entities]

    def _default_ray_config(self, max_agents: int) -> dict[str, Any]:
        return {
            "num_cpus": min(8, max(2, max_agents // 500)),
            "num_gpus": 0,
        }
