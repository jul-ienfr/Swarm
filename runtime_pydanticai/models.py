from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RuntimeBackend(str, Enum):
    pydanticai = "pydanticai"
    legacy = "legacy"


class RuntimeFallbackPolicy(str, Enum):
    never = "never"
    on_error = "on_error"
    always = "always"


class RuntimeMode(str, Enum):
    pydanticai = "pydanticai"
    legacy = "legacy"


class RuntimeHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unavailable = "unavailable"
    misconfigured = "misconfigured"


class RuntimeModelConfig(BaseModel):
    model_name: str = "claude-sonnet-4-6"
    provider_name: str = "openai"
    base_url: str | None = None
    api_key: str | None = None
    source: str = "openclaw"
    config_path: str | None = None
    openclaw_path: str | None = None


class RuntimeHealthReport(BaseModel):
    runtime: RuntimeBackend
    status: RuntimeHealthStatus
    configured: bool = False
    imports_available: bool = False
    api_key_configured: bool = False
    provider_name: str = "openai"
    model_name: str | None = None
    provider_base_url: str | None = None
    provider_source: str | None = None
    provider_probe_url: str | None = None
    provider_reachable: bool | None = None
    http_status: int | None = None
    latency_ms: float | None = None
    fallback_runtime: RuntimeBackend | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class MeetingTurnDraft(BaseModel):
    thesis: str
    recommended_actions: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    closing_note: str | None = None

    def to_content(self) -> str:
        lines = [f"Thesis: {self.thesis}"]
        if self.recommended_actions:
            lines.append("Recommended actions:")
            lines.extend(f"- {item}" for item in self.recommended_actions)
        if self.key_risks:
            lines.append("Key risks:")
            lines.extend(f"- {item}" for item in self.key_risks)
        if self.disagreements:
            lines.append("Disagreements:")
            lines.extend(f"- {item}" for item in self.disagreements)
        if self.closing_note:
            lines.append(f"Closing note: {self.closing_note}")
        return "\n".join(lines).strip()


class MeetingRoundSummary(BaseModel):
    summary: str
    top_options: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved_disagreements: list[str] = Field(default_factory=list)


class MeetingSynthesisDraft(BaseModel):
    strategy: str
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class SupervisorAssignmentDraft(BaseModel):
    speaker: str
    instruction: str
    priority: int = 0
    rationale: str | None = None


class SupervisorPlanDraft(BaseModel):
    assignments: list[SupervisorAssignmentDraft] = Field(default_factory=list)
    complete: bool = False
    rationale: str | None = None


class SupervisorAssignment(BaseModel):
    speaker: str
    instruction: str
    priority: int = 0
    rationale: str | None = None


class SupervisorPlan(BaseModel):
    assignments: list[SupervisorAssignment] = Field(default_factory=list)
    complete: bool = False
    rationale: str | None = None
    runtime_used: RuntimeBackend = RuntimeBackend.pydanticai
    fallback_used: bool = False
    model_name: str | None = None
    provider_base_url: str | None = None
    error: str | None = None


class ImprovementCritiqueDraft(BaseModel):
    summary: str
    rationale: list[str] = Field(default_factory=list)
    workflow_rules_to_add: list[str] = Field(default_factory=list)
    workflow_rules_to_remove: list[str] = Field(default_factory=list)
    sampling_param_overrides: dict[str, float] = Field(default_factory=dict)
    risk_level: str = "low"
    requires_human_review: bool = False


@dataclass(slots=True)
class StructuredRuntimeResult:
    output: Any
    runtime_used: RuntimeBackend
    fallback_used: bool = False
    model_name: str | None = None
    provider_base_url: str | None = None
    provider_source: str | None = None
    error: str | None = None
