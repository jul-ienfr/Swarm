"""
Translate adapter requests into OASIS-native simulation configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation_adapter.adapter import CreateRunRequest


@dataclass(slots=True)
class OASISRunConfig:
    run_id: str
    platform: str
    database_path: str
    agent_count: int
    time_horizon: str
    topic: str
    objective: str
    agent_profiles: list[dict[str, Any]] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class OASISTranslator:
    def translate(self, request: CreateRunRequest) -> OASISRunConfig:
        params = request.parameters
        seeds = request.seed_materials
        population_size = params.population_size or params.max_agents
        extra = dict(params.extra)
        extra["timeout_seconds"] = request.control.timeout_seconds
        extra["budget_max"] = request.control.budget_max
        extra["progress_granularity"] = request.control.progress_granularity.value
        extra["documents"] = list(seeds.documents)
        extra["environment_seed"] = dict(seeds.environment_seed)
        return OASISRunConfig(
            run_id=request.runtime_run_id,
            platform=self._resolve_platform(request.simulation_type, seeds.environment_seed),
            database_path=self._resolve_database_path(request.runtime_run_id, extra),
            agent_count=max(2, int(population_size or 2)),
            time_horizon=params.time_horizon,
            topic=str(seeds.environment_seed.get("topic") or request.brief or request.simulation_type),
            objective=str(seeds.environment_seed.get("objective") or request.brief or "Simulate the social reaction"),
            agent_profiles=self._build_profiles(seeds, population_size),
            available_actions=self._default_actions(),
            extra=extra,
        )

    @staticmethod
    def _resolve_platform(simulation_type: str, environment_seed: dict[str, Any]) -> str:
        platform = str(environment_seed.get("platform") or simulation_type or "reddit").strip().lower()
        if platform in {"twitter", "x"}:
            return "twitter"
        if platform in {"reddit", "forum"}:
            return "reddit"
        return "reddit"

    @staticmethod
    def _resolve_database_path(runtime_run_id: str, extra: dict[str, Any]) -> str:
        return str(extra.get("database_path") or f"/tmp/oasis/{runtime_run_id}.db")

    @staticmethod
    def _build_profiles(seeds, population_size: int | None) -> list[dict[str, Any]]:
        profiles = []
        entities = list(seeds.entities or [])
        if entities:
            for index, entity in enumerate(entities, start=1):
                profiles.append(
                    {
                        "agent_id": index,
                        "user_info": {
                            "handle": f"agent_{index}",
                            "bio": f"Grounded persona from entity {entity!r}",
                            "seed_entity": entity,
                        },
                        "stance": "neutral",
                        "confidence": 0.55,
                        "trust": 0.5,
                    }
                )
        else:
            count = max(2, min(int(population_size or 8), 32))
            for index in range(1, count + 1):
                profiles.append(
                    {
                        "agent_id": index,
                        "user_info": {
                            "handle": f"agent_{index}",
                            "bio": "Synthetic agent profile for OASIS.",
                        },
                        "stance": "neutral",
                        "confidence": 0.5,
                        "trust": 0.5,
                    }
                )
        return profiles

    @staticmethod
    def _default_actions() -> list[str]:
        return [
            "CREATE_POST",
            "CREATE_COMMENT",
            "LIKE_POST",
            "LIKE_COMMENT",
            "SEARCH_POSTS",
            "TREND",
            "FOLLOW",
            "DO_NOTHING",
        ]
