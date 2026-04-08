from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class SkillDefinition(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    risk_level: RiskLevel = RiskLevel.low
    config: dict[str, Any] = Field(default_factory=dict)


class HarnessSnapshot(BaseModel):
    snapshot_version: str = "v1"
    version: str = Field(default_factory=lambda: f"harness_{uuid4().hex[:12]}")
    skills: dict[str, SkillDefinition] = Field(default_factory=dict)
    workflow_rules: list[str] = Field(default_factory=list)
    sampling_params: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def clone_with(
        self,
        *,
        version: str | None = None,
        skills: dict[str, SkillDefinition] | None = None,
        workflow_rules: list[str] | None = None,
        sampling_params: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "HarnessSnapshot":
        return HarnessSnapshot(
            snapshot_version=self.snapshot_version,
            version=version or f"{self.version}_cand",
            skills=skills if skills is not None else {name: skill.model_copy(deep=True) for name, skill in self.skills.items()},
            workflow_rules=workflow_rules if workflow_rules is not None else list(self.workflow_rules),
            sampling_params=sampling_params if sampling_params is not None else dict(self.sampling_params),
            metadata=metadata if metadata is not None else dict(self.metadata),
        )

    @classmethod
    def baseline(cls) -> "HarnessSnapshot":
        return cls(
            version="harness_baseline_v1",
            workflow_rules=[
                "Never mutate adapter or engine contracts during optimization rounds.",
                "Prefer retries and graceful degradation over aborting immediately.",
                "Escalate to human review for high-risk harness changes.",
            ],
            sampling_params={"temperature": 0.2},
            metadata={"mode": "baseline"},
        )
