"""PydanticAI-backed runtimes and typed planners for Swarm."""

from .factory import (
    PydanticAIRuntimeFactory,
    RuntimeAvailabilityError,
    build_openai_model,
    build_openai_provider,
    check_pydanticai_runtime_health,
    load_runtime_model_config,
    run_structured_agent,
)
from .improvement import ConfigCritiqueDraft, PydanticAIConfigCritic, PydanticAIHarnessCritic
from .models import (
    MeetingRoundSummary,
    MeetingSynthesisDraft,
    MeetingTurnDraft,
    ImprovementCritiqueDraft,
    RuntimeBackend,
    RuntimeFallbackPolicy,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeMode,
    RuntimeModelConfig,
    StructuredRuntimeResult,
    SupervisorAssignment,
    SupervisorAssignmentDraft,
    SupervisorPlan,
    SupervisorPlanDraft,
)
from .strategy_meeting import PydanticAIStrategyMeetingRuntime
from .supervisor import PydanticAISupervisorPlanner, SupervisorPlanningInput

PHASE = 5
PHASE_2_ONLY = False
STATUS = "active"
RuntimeExecutionResult = StructuredRuntimeResult


def runtime_health(
    config: RuntimeModelConfig | None = None,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Return a JSON-ready health snapshot for the PydanticAI runtime."""
    return check_pydanticai_runtime_health(config=config, timeout_seconds=timeout_seconds).model_dump(mode="json")


def get_runtime_stub() -> dict[str, object]:
    return {
        "phase": PHASE,
        "phase_2_only": PHASE_2_ONLY,
        "status": STATUS,
        "message": "runtime_pydanticai is active and provides PydanticAI-backed planners/runtimes for Swarm.",
    }


__all__ = [
    "MeetingRoundSummary",
    "MeetingSynthesisDraft",
    "MeetingTurnDraft",
    "ImprovementCritiqueDraft",
    "PydanticAIConfigCritic",
    "PydanticAIHarnessCritic",
    "PydanticAIRuntimeFactory",
    "PydanticAIStrategyMeetingRuntime",
    "PydanticAISupervisorPlanner",
    "RuntimeAvailabilityError",
    "RuntimeBackend",
    "RuntimeExecutionResult",
    "StructuredRuntimeResult",
    "RuntimeFallbackPolicy",
    "RuntimeHealthReport",
    "RuntimeHealthStatus",
    "RuntimeMode",
    "RuntimeModelConfig",
    "ConfigCritiqueDraft",
    "SupervisorAssignment",
    "SupervisorAssignmentDraft",
    "SupervisorPlan",
    "SupervisorPlanDraft",
    "SupervisorPlanningInput",
    "build_openai_model",
    "build_openai_provider",
    "check_pydanticai_runtime_health",
    "get_runtime_stub",
    "load_runtime_model_config",
    "runtime_health",
    "run_structured_agent",
]
