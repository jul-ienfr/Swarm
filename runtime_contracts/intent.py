from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    scenario_simulation = "scenario_simulation"
    analysis = "analysis"


class EnginePreference(str, Enum):
    agentsociety = "agentsociety"
    oasis = "oasis"
    mesa = "mesa"


class IntentInputs(BaseModel):
    documents: list[str] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    environment_seed: dict[str, Any] = Field(default_factory=dict)


class IntentConstraints(BaseModel):
    max_agents: int = 1000
    time_horizon: str = "7d"
    additional: dict[str, Any] = Field(default_factory=dict)


class IntentPolicy(BaseModel):
    budget_max: float = 10
    timeout_seconds: int = 1800
    engine_preference: EnginePreference = EnginePreference.agentsociety
    priority: int = 5


class IntentContext(BaseModel):
    user_id: str | None = None
    tenant_id: str | None = None
    source: str = "cli"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationIntentV1(BaseModel):
    intent_version: str = "v1"
    swarm_version: str = "v1"
    intent_id: str = Field(default_factory=lambda: f"intent_{uuid4().hex[:12]}")
    task_type: TaskType
    goal: str
    inputs: IntentInputs = Field(default_factory=IntentInputs)
    constraints: IntentConstraints = Field(default_factory=IntentConstraints)
    policy: IntentPolicy = Field(default_factory=IntentPolicy)
    requested_outputs: list[str] = Field(
        default_factory=lambda: ["summary", "metrics", "artifacts"]
    )
    context: IntentContext = Field(default_factory=IntentContext)
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex[:12]}")

