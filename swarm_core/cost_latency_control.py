from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BudgetDecision(str, Enum):
    allow = "allow"
    trim = "trim"
    block = "block"


@dataclass(slots=True)
class BudgetLimits:
    cost_units: float | None = None
    latency_seconds: float | None = None
    max_agents: int | None = None
    max_rounds: int | None = None
    max_parallelism: int | None = None


@dataclass(slots=True)
class BudgetRequest:
    requested_agents: int
    requested_rounds: int
    requested_parallelism: int
    estimated_cost_units: float
    estimated_latency_seconds: float


@dataclass(slots=True)
class BudgetDecisionReport:
    decision: BudgetDecision
    allowed: bool
    adjusted_agents: int
    adjusted_rounds: int
    adjusted_parallelism: int
    adjusted_cost_units: float
    adjusted_latency_seconds: float
    reasons: list[str] = field(default_factory=list)
    checked_at: str = field(default_factory=_utc_now)


class CostLatencyController:
    """
    Simple budget controller for bounded deliberation runs.

    The controller trims a candidate plan down to the available limits and
    reports whether the trimmed plan is safe to execute.
    """

    def evaluate(self, request: BudgetRequest, limits: BudgetLimits) -> BudgetDecisionReport:
        if request.requested_agents < 1 or request.requested_rounds < 1 or request.requested_parallelism < 1:
            raise ValueError("requested agents/rounds/parallelism must be positive")

        adjusted_agents = self._bounded_value(request.requested_agents, limits.max_agents)
        adjusted_rounds = self._bounded_value(request.requested_rounds, limits.max_rounds)
        adjusted_parallelism = self._bounded_value(request.requested_parallelism, limits.max_parallelism)

        reasons: list[str] = []
        if adjusted_agents != request.requested_agents:
            reasons.append(f"agents trimmed to {adjusted_agents}")
        if adjusted_rounds != request.requested_rounds:
            reasons.append(f"rounds trimmed to {adjusted_rounds}")
        if adjusted_parallelism != request.requested_parallelism:
            reasons.append(f"parallelism trimmed to {adjusted_parallelism}")

        adjusted_cost = self._scale_cost(request, adjusted_agents, adjusted_rounds)
        adjusted_latency = self._scale_latency(request, adjusted_agents, adjusted_rounds, adjusted_parallelism)

        if limits.cost_units is not None and adjusted_cost > limits.cost_units:
            scale = limits.cost_units / max(adjusted_cost, 1e-9)
            adjusted_rounds = max(1, int(adjusted_rounds * scale))
            adjusted_agents = max(1, int(adjusted_agents * scale))
            adjusted_cost = self._scale_cost(request, adjusted_agents, adjusted_rounds)
            adjusted_latency = self._scale_latency(request, adjusted_agents, adjusted_rounds, adjusted_parallelism)
            reasons.append(f"cost capped to {limits.cost_units}")

        if limits.latency_seconds is not None and adjusted_latency > limits.latency_seconds:
            scale = limits.latency_seconds / max(adjusted_latency, 1e-9)
            adjusted_rounds = max(1, int(adjusted_rounds * scale))
            adjusted_agents = max(1, int(adjusted_agents * scale))
            adjusted_latency = self._scale_latency(request, adjusted_agents, adjusted_rounds, adjusted_parallelism)
            adjusted_cost = self._scale_cost(request, adjusted_agents, adjusted_rounds)
            reasons.append(f"latency capped to {limits.latency_seconds}")

        blocked = False
        if limits.max_agents is not None and adjusted_agents > limits.max_agents:
            blocked = True
            reasons.append("agents still above max limit")
        if limits.max_rounds is not None and adjusted_rounds > limits.max_rounds:
            blocked = True
            reasons.append("rounds still above max limit")
        if limits.max_parallelism is not None and adjusted_parallelism > limits.max_parallelism:
            blocked = True
            reasons.append("parallelism still above max limit")
        if limits.cost_units is not None and adjusted_cost > limits.cost_units:
            blocked = True
            reasons.append("cost still above limit")
        if limits.latency_seconds is not None and adjusted_latency > limits.latency_seconds:
            blocked = True
            reasons.append("latency still above limit")

        if blocked:
            decision = BudgetDecision.block
            allowed = False
        elif reasons:
            decision = BudgetDecision.trim
            allowed = True
        else:
            decision = BudgetDecision.allow
            allowed = True

        return BudgetDecisionReport(
            decision=decision,
            allowed=allowed,
            adjusted_agents=adjusted_agents,
            adjusted_rounds=adjusted_rounds,
            adjusted_parallelism=adjusted_parallelism,
            adjusted_cost_units=round(adjusted_cost, 3),
            adjusted_latency_seconds=round(adjusted_latency, 3),
            reasons=reasons,
        )

    def _bounded_value(self, requested: int, upper: int | None) -> int:
        return requested if upper is None else min(requested, max(1, upper))

    def _scale_cost(self, request: BudgetRequest, adjusted_agents: int, adjusted_rounds: int) -> float:
        workload_ratio = (adjusted_agents * adjusted_rounds) / max(1, request.requested_agents * request.requested_rounds)
        return request.estimated_cost_units * workload_ratio

    def _scale_latency(
        self,
        request: BudgetRequest,
        adjusted_agents: int,
        adjusted_rounds: int,
        adjusted_parallelism: int,
    ) -> float:
        workload_ratio = (adjusted_agents * adjusted_rounds) / max(1, request.requested_agents * request.requested_rounds)
        parallelism_ratio = request.requested_parallelism / max(1, adjusted_parallelism)
        return request.estimated_latency_seconds * workload_ratio * parallelism_ratio

