from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from .belief_state import BeliefState
from .normalized_social_traces import NormalizedSocialTrace


class InterventionDelta(BaseModel):
    metric: str
    baseline: float = 0.0
    candidate: float = 0.0
    delta: float = 0.0


class InterventionLabReport(BaseModel):
    intervention_count: int = 0
    before_trace_count: int = 0
    after_trace_count: int = 0
    before_support_share: float = 0.0
    after_support_share: float = 0.0
    deltas: list[InterventionDelta] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class InterventionLab:
    def compare(
        self,
        *,
        before_beliefs: Iterable[BeliefState],
        after_beliefs: Iterable[BeliefState],
        before_traces: Iterable[NormalizedSocialTrace],
        after_traces: Iterable[NormalizedSocialTrace],
        interventions: Iterable[str] | None = None,
    ) -> InterventionLabReport:
        before_beliefs = list(before_beliefs)
        after_beliefs = list(after_beliefs)
        before_traces = list(before_traces)
        after_traces = list(after_traces)
        interventions = [str(item).strip() for item in (interventions or []) if str(item).strip()]
        before_support = _support_share(before_beliefs)
        after_support = _support_share(after_beliefs)
        deltas = [
            InterventionDelta(
                metric="support_share",
                baseline=before_support,
                candidate=after_support,
                delta=round(after_support - before_support, 6),
            ),
            InterventionDelta(
                metric="trace_count",
                baseline=float(len(before_traces)),
                candidate=float(len(after_traces)),
                delta=float(len(after_traces) - len(before_traces)),
            ),
        ]
        notes: list[str] = []
        if after_support > before_support:
            notes.append("intervention_improved_support")
        elif after_support < before_support:
            notes.append("intervention_reduced_support")
        else:
            notes.append("intervention_neutral")
        if len(after_traces) > len(before_traces):
            notes.append("intervention_increased_activity")
        return InterventionLabReport(
            intervention_count=len(interventions),
            before_trace_count=len(before_traces),
            after_trace_count=len(after_traces),
            before_support_share=before_support,
            after_support_share=after_support,
            deltas=deltas,
            notes=notes,
            metadata={"interventions": interventions},
        )


def _support_share(states: Iterable[BeliefState]) -> float:
    states = list(states)
    if not states:
        return 0.0
    support_count = sum(1 for state in states if state.stance in {"support", "expansion"})
    return support_count / len(states)
