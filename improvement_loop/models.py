from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LoopMode(str, Enum):
    suggest_only = "suggest_only"
    safe_auto_apply = "safe_auto_apply"


class LoopDecision(str, Enum):
    keep = "keep"
    revert = "revert"
    propose = "propose"
    halt = "halt"


class ImprovementRuntime(str, Enum):
    pydanticai = "pydanticai"
    legacy = "legacy"


class TargetDescriptor(BaseModel):
    target_id: str
    description: str
    default_mode: LoopMode = LoopMode.suggest_only
    default_runtime: ImprovementRuntime = ImprovementRuntime.pydanticai
    metadata: dict[str, Any] = Field(default_factory=dict)


class TargetInspection(BaseModel):
    descriptor: TargetDescriptor
    current_snapshot: dict[str, Any]
    benchmark: dict[str, Any] | None = None
    memory_entries: list[dict[str, Any]] = Field(default_factory=list)
    runtime_used: ImprovementRuntime = ImprovementRuntime.pydanticai
    fallback_used: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImprovementRoundRecord(BaseModel):
    target_id: str
    round_index: int
    mode: LoopMode
    decision: LoopDecision
    baseline_score: float
    candidate_score: float
    score_delta: float
    improvement_ratio: float
    current_snapshot: dict[str, Any]
    candidate_snapshot: dict[str, Any]
    applied_snapshot: dict[str, Any]
    proposal: dict[str, Any]
    baseline_report: dict[str, Any]
    candidate_report: dict[str, Any]
    requires_human_review: bool = False
    halted_reason: str | None = None
    runtime_used: ImprovementRuntime = ImprovementRuntime.pydanticai
    fallback_used: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImprovementLoopRun(BaseModel):
    target_id: str
    mode: LoopMode
    max_rounds: int
    completed_rounds: int
    rounds: list[ImprovementRoundRecord] = Field(default_factory=list)
    stopped_reason: str | None = None
