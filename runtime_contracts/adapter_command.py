from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AdapterCommand(str, Enum):
    create_run = "create_run"
    get_status = "get_status"
    get_result = "get_result"
    cancel_run = "cancel_run"


class EngineTarget(str, Enum):
    agentsociety = "agentsociety"
    oasis = "oasis"
    mesa = "mesa"


class ProgressGranularity(str, Enum):
    coarse = "coarse"
    fine = "fine"


class SeedMaterials(BaseModel):
    documents: list[str] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    environment_seed: dict[str, Any] = Field(default_factory=dict)


class SimulationParameters(BaseModel):
    max_agents: int = 1000
    time_horizon: str = "7d"
    rounds: int | None = None
    population_size: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ControlParams(BaseModel):
    timeout_seconds: int = 1800
    budget_max: float = 10
    progress_granularity: ProgressGranularity = ProgressGranularity.coarse


class AdapterCommandV1(BaseModel):
    adapter_version: str = "v1"
    command: AdapterCommand
    runtime_run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    engine: EngineTarget = EngineTarget.agentsociety
    simulation_type: str = "society"
    brief: str | None = None
    seed_materials: SeedMaterials = Field(default_factory=SeedMaterials)
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    control: ControlParams = Field(default_factory=ControlParams)
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex[:12]}")
    swarm_intent_id: str | None = None

