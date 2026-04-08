from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


class FidelityMode(str, Enum):
    low = "low"
    balanced = "balanced"
    high = "high"
    exhaustive = "exhaustive"


@dataclass(slots=True)
class FidelityRequest:
    goal: str
    requested_population: int | None = None
    requested_rounds: int | None = None
    requested_parallelism: int | None = None
    time_budget_seconds: float | None = None
    cost_budget_units: float | None = None
    quality_priority: float = 0.5
    max_population: int = 1000
    max_rounds: int = 8
    max_parallelism: int = 16


@dataclass(slots=True)
class FidelityPlan:
    mode: FidelityMode
    population_size: int
    rounds: int
    parallelism: int
    estimated_cost_units: float
    estimated_latency_seconds: float
    engine_preference: str
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "population_size": self.population_size,
            "rounds": self.rounds,
            "parallelism": self.parallelism,
            "estimated_cost_units": self.estimated_cost_units,
            "estimated_latency_seconds": self.estimated_latency_seconds,
            "engine_preference": self.engine_preference,
            "rationale": self.rationale,
        }


class AdaptiveFidelityPlanner:
    """
    Chooses a bounded fidelity level for massive deliberation runs.

    The planner intentionally stays simple so it can guide deliberation without
    forcing the runtime to depend on a heavy policy layer.
    """

    DEFAULTS = {
        FidelityMode.low: (8, 1, 2, "committee"),
        FidelityMode.balanced: (32, 2, 4, "committee"),
        FidelityMode.high: (128, 3, 8, "simulation"),
        FidelityMode.exhaustive: (500, 4, 12, "simulation"),
    }

    def plan(self, request: FidelityRequest) -> FidelityPlan:
        tier = self._choose_tier(request)
        default_population, default_rounds, default_parallelism, engine = self.DEFAULTS[tier]
        population = _clamp(
            request.requested_population or default_population,
            1,
            request.max_population,
        )
        rounds = _clamp(request.requested_rounds or default_rounds, 1, request.max_rounds)
        parallelism = _clamp(
            request.requested_parallelism or default_parallelism,
            1,
            request.max_parallelism,
        )
        estimated_cost_units = round(population * rounds * 0.02 + parallelism * 0.08, 3)
        estimated_latency_seconds = round(rounds * max(1.0, population / max(1, parallelism)) * 0.05 + 1.0, 3)
        rationale = self._build_rationale(request, tier, population, rounds, parallelism)
        return FidelityPlan(
            mode=tier,
            population_size=population,
            rounds=rounds,
            parallelism=parallelism,
            estimated_cost_units=estimated_cost_units,
            estimated_latency_seconds=estimated_latency_seconds,
            engine_preference=engine,
            rationale=rationale,
        )

    def _choose_tier(self, request: FidelityRequest) -> FidelityMode:
        objective = request.goal.lower()
        quality = _clamp(int(request.quality_priority * 100), 0, 100)

        if any(token in objective for token in ("smoke", "preview", "inspect", "quick", "dry run")):
            tier = FidelityMode.low
        elif any(token in objective for token in ("decision", "strategy", "hybrid", "final", "production")):
            tier = FidelityMode.high if quality < 90 else FidelityMode.exhaustive
        else:
            tier = FidelityMode.balanced if quality < 70 else FidelityMode.high

        if request.time_budget_seconds is not None:
            if request.time_budget_seconds <= 15:
                tier = FidelityMode.low
            elif request.time_budget_seconds <= 45 and tier in (FidelityMode.high, FidelityMode.exhaustive):
                tier = FidelityMode.balanced

        if request.cost_budget_units is not None:
            if request.cost_budget_units <= 5:
                tier = FidelityMode.low
            elif request.cost_budget_units <= 15 and tier == FidelityMode.exhaustive:
                tier = FidelityMode.high

        return tier

    def _build_rationale(
        self,
        request: FidelityRequest,
        tier: FidelityMode,
        population: int,
        rounds: int,
        parallelism: int,
    ) -> str:
        reason_bits = [
            f"goal={request.goal!r}",
            f"tier={tier.value}",
            f"population={population}",
            f"rounds={rounds}",
            f"parallelism={parallelism}",
        ]
        if request.time_budget_seconds is not None:
            reason_bits.append(f"time_budget={request.time_budget_seconds}")
        if request.cost_budget_units is not None:
            reason_bits.append(f"cost_budget={request.cost_budget_units}")
        return "; ".join(reason_bits)
