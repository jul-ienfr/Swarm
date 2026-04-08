from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel, Field

from .belief_state import BeliefState
from .normalized_social_traces import NormalizedSocialTrace, SocialTraceKind, normalize_social_trace


class CrossPlatformPlan(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    rounds: int = 1
    traces_per_platform: int = 3
    metadata: dict[str, str] = Field(default_factory=dict)


class CrossPlatformSimulationReport(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    rounds: int = 0
    trace_count: int = 0
    traces: list[NormalizedSocialTrace] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


@dataclass(slots=True)
class CrossPlatformSimulator:
    default_platforms: tuple[str, ...] = ("reddit", "twitter")
    traces_per_platform: int = 3

    def build_plan(
        self,
        *,
        platforms: Iterable[str] | None = None,
        rounds: int = 1,
        traces_per_platform: int | None = None,
    ) -> CrossPlatformPlan:
        resolved_platforms = [str(item).strip().lower() for item in (platforms or self.default_platforms) if str(item).strip()]
        if not resolved_platforms:
            resolved_platforms = list(self.default_platforms)
        return CrossPlatformPlan(
            platforms=list(dict.fromkeys(resolved_platforms)),
            rounds=max(1, int(rounds)),
            traces_per_platform=max(1, int(traces_per_platform or self.traces_per_platform)),
        )

    def simulate(
        self,
        *,
        topic: str,
        summary: str,
        beliefs: Iterable[BeliefState],
        platforms: Iterable[str] | None = None,
        rounds: int = 1,
        interventions: Iterable[str] | None = None,
    ) -> CrossPlatformSimulationReport:
        plan = self.build_plan(platforms=platforms, rounds=rounds)
        belief_list = list(beliefs)
        interventions = [str(item).strip() for item in (interventions or []) if str(item).strip()]
        traces: list[NormalizedSocialTrace] = []
        seeds = belief_list or [
            BeliefState(agent_id="observer_1", stance="support", confidence=0.5, trust=0.5, memory_window=[topic])
        ]
        for round_index in range(plan.rounds):
            for platform in plan.platforms:
                for trace_index in range(plan.traces_per_platform):
                    state = seeds[(round_index * plan.traces_per_platform + trace_index) % len(seeds)]
                    content = self._render_content(
                        topic=topic,
                        summary=summary,
                        platform=platform,
                        state=state,
                        round_index=round_index,
                        interventions=interventions,
                    )
                    kind = SocialTraceKind.post if trace_index == 0 else SocialTraceKind.comment
                    if interventions and trace_index == plan.traces_per_platform - 1:
                        kind = SocialTraceKind.intervention
                    traces.append(
                        normalize_social_trace(
                            content,
                            platform=platform,
                            actor_id=state.agent_id,
                            kind=kind,
                            group_id=state.group_id,
                            round_index=round_index,
                            metadata={
                                "stance": state.stance,
                                "confidence": state.confidence,
                                "trust": state.trust,
                            },
                        )
                    )
        return CrossPlatformSimulationReport(
            platforms=plan.platforms,
            rounds=plan.rounds,
            trace_count=len(traces),
            traces=traces,
            metadata={
                "topic": topic,
                "intervention_count": len(interventions),
                "belief_count": len(belief_list),
            },
        )

    @staticmethod
    def _render_content(
        *,
        topic: str,
        summary: str,
        platform: str,
        state: BeliefState,
        round_index: int,
        interventions: list[str],
    ) -> str:
        prefix = {
            "twitter": "Short-form reaction",
            "reddit": "Thread summary",
            "forum": "Forum response",
            "news": "Editorial signal",
        }.get(platform, "Platform signal")
        intervention_note = f" Intervention: {interventions[round_index % len(interventions)]}." if interventions else ""
        return (
            f"{prefix} on {platform} about {topic}. "
            f"Agent {state.agent_id} is {state.stance} with confidence {state.confidence:.2f}. "
            f"Summary signal: {summary[:140] or topic}.{intervention_note}"
        )
