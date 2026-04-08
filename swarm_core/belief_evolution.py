from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import log2
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field

from .belief_state import BeliefGroupSummary, BeliefState, dominant_stance, summarise_belief_group
from .normalized_social_traces import NormalizedSocialTrace, SocialTraceKind, score_social_sentiment
from .sliding_memory import SlidingMemoryEngine, SlidingMemoryWindow, compact_memory_texts


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _clone_state(state: BeliefState) -> BeliefState:
    return BeliefState.model_validate(state.model_dump(mode="python"))


def _stance_from_sentiment(sentiment: float, current: str) -> str:
    if sentiment > 0.15:
        return "support"
    if sentiment < -0.15:
        return "oppose"
    return current or "uncertain"


def _stance_entropy(states: Iterable[BeliefState]) -> float:
    counts: dict[str, int] = defaultdict(int)
    states = list(states)
    if not states:
        return 0.0
    for state in states:
        counts[state.stance] += 1
    total = float(len(states))
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * log2(p)
    return entropy


class BeliefEvolutionSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: f"signal_{uuid4().hex[:12]}")
    agent_id: str
    round_index: int = 0
    stance: str | None = None
    confidence_delta: float = 0.0
    trust_delta: float = 0.0
    sentiment: float = 0.0
    score: float = 0.5
    platform: str = ""
    memory_items: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BeliefEvolutionRoundSnapshot(BaseModel):
    run_id: str
    round_index: int
    states: list[BeliefState] = Field(default_factory=list)
    group_summaries: list[BeliefGroupSummary] = Field(default_factory=list)
    memory_windows: dict[str, SlidingMemoryWindow] = Field(default_factory=dict)
    traces: list[NormalizedSocialTrace] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BeliefEvolutionResult(BaseModel):
    run_id: str = Field(default_factory=lambda: f"belief_run_{uuid4().hex[:12]}")
    rounds_completed: int = 0
    snapshots: list[BeliefEvolutionRoundSnapshot] = Field(default_factory=list)
    final_states: list[BeliefState] = Field(default_factory=list)
    final_group_summaries: list[BeliefGroupSummary] = Field(default_factory=list)
    traces: list[NormalizedSocialTrace] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BeliefEvolutionEngine:
    def __init__(
        self,
        *,
        memory_capacity: int = 12,
        confidence_decay: float = 0.02,
        trust_decay: float = 0.01,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.memory_capacity = max(1, int(memory_capacity))
        self.confidence_decay = max(0.0, float(confidence_decay))
        self.trust_decay = max(0.0, float(trust_decay))
        self.run_id = run_id or f"belief_run_{uuid4().hex[:12]}"
        self.metadata = dict(metadata or {})

    def step(
        self,
        states: Iterable[BeliefState],
        *,
        signals: Iterable[BeliefEvolutionSignal] | None = None,
        traces: Iterable[NormalizedSocialTrace] | None = None,
        round_index: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> BeliefEvolutionRoundSnapshot:
        current_states = [_clone_state(state) for state in states]
        signal_map: dict[str, list[BeliefEvolutionSignal]] = defaultdict(list)
        for signal in signals or []:
            signal_map[signal.agent_id].append(signal)
        trace_map: dict[str, list[NormalizedSocialTrace]] = defaultdict(list)
        broadcast_traces: list[NormalizedSocialTrace] = []
        for trace in traces or []:
            if trace.actor_id:
                trace_map[trace.actor_id].append(trace)
            else:
                broadcast_traces.append(trace)

        memory_windows: dict[str, SlidingMemoryWindow] = {}
        all_traces = list(traces or [])
        for state in current_states:
            window_engine = SlidingMemoryEngine(owner_id=state.agent_id, capacity=self.memory_capacity)
            window_engine.extend(state.memory_window)
            agent_signals = sorted(signal_map.get(state.agent_id, []), key=lambda item: (item.round_index, item.created_at.timestamp()))
            agent_traces = [*trace_map.get(state.agent_id, []), *broadcast_traces]
            if not agent_signals and not agent_traces:
                state.decay(confidence_delta=self.confidence_decay, trust_delta=self.trust_decay)
                window_engine.record(
                    f"Round {round_index}: no new social evidence.",
                    score=0.1,
                    topic="belief_decay",
                    metadata={"round_index": round_index, "kind": "decay"},
                )
            for signal in agent_signals:
                if signal.stance:
                    state.stance = signal.stance
                sentiment_adjustment = signal.sentiment * 0.02
                score_adjustment = max(0.0, float(signal.score)) * 0.01
                state.confidence = _clamp(state.confidence + signal.confidence_delta + sentiment_adjustment + score_adjustment)
                state.trust = _clamp(state.trust + signal.trust_delta + sentiment_adjustment * 0.5)
                for item in signal.memory_items:
                    window_engine.record(
                        item,
                        score=max(0.0, min(1.0, 0.4 + abs(signal.sentiment) * 0.3)),
                        topic="signal_memory",
                        tags=[signal.platform, "signal"],
                        metadata={"signal_id": signal.signal_id, "round_index": signal.round_index},
                    )
                if signal.trace_ids:
                    state.metadata.setdefault("trace_ids", [])
                    state.metadata["trace_ids"] = sorted(set([*state.metadata["trace_ids"], *signal.trace_ids]))
                state.metadata.setdefault("signal_ids", [])
                state.metadata["signal_ids"] = sorted(set([*state.metadata["signal_ids"], signal.signal_id]))
                state.metadata.setdefault("platforms", [])
                if signal.platform and signal.platform not in state.metadata["platforms"]:
                    state.metadata["platforms"].append(signal.platform)
            for trace in agent_traces:
                inferred_stance = _stance_from_sentiment(trace.sentiment, state.stance)
                if trace.kind in {SocialTraceKind.belief_shift, SocialTraceKind.intervention}:
                    state.stance = inferred_stance
                state.confidence = _clamp(state.confidence + trace.sentiment * 0.04 + trace.score * 0.01)
                state.trust = _clamp(state.trust + trace.sentiment * 0.02)
                window_engine.record(
                    f"{trace.platform}:{trace.kind.value}:{trace.content}",
                    score=trace.score,
                    topic=trace.platform,
                    tags=[trace.platform, trace.kind.value, *trace.tags],
                    metadata={"trace_id": trace.trace_id, "round_index": trace.round_index},
                )
            window_engine.compact()
            state.memory_window = [entry.text for entry in window_engine.window.entries]
            state.touch()
            memory_windows[state.agent_id] = window_engine.snapshot()

        group_map: dict[str | None, list[BeliefState]] = defaultdict(list)
        for state in current_states:
            group_map[state.group_id].append(state)
        group_summaries = [
            summarise_belief_group(members, group_id=group_id)
            for group_id, members in sorted(group_map.items(), key=lambda item: item[0] or "")
        ]
        metrics = self._metrics(current_states, signals=list(signals or []), traces=all_traces)
        summary = self._render_summary(round_index, current_states, group_summaries, metrics)
        return BeliefEvolutionRoundSnapshot(
            run_id=self.run_id,
            round_index=round_index,
            states=current_states,
            group_summaries=group_summaries,
            memory_windows=memory_windows,
            traces=all_traces,
            metrics=metrics,
            summary=summary,
            metadata={**self.metadata, **(metadata or {})},
        )

    def run(
        self,
        states: Iterable[BeliefState],
        *,
        rounds: list[Iterable[BeliefEvolutionSignal]] | None = None,
        trace_rounds: list[Iterable[NormalizedSocialTrace]] | None = None,
        round_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BeliefEvolutionResult:
        current_states = [_clone_state(state) for state in states]
        snapshots: list[BeliefEvolutionRoundSnapshot] = []
        resolved_rounds = [list(signal_round) for signal_round in (rounds or [])]
        if not resolved_rounds:
            resolved_rounds = [()]
        if round_count is not None and round_count > len(resolved_rounds):
            resolved_rounds.extend([()] * (round_count - len(resolved_rounds)))
        for round_index, signal_round in enumerate(resolved_rounds):
            trace_round = list(trace_rounds[round_index]) if trace_rounds and round_index < len(trace_rounds) else []
            snapshot = self.step(
                current_states,
                signals=list(signal_round),
                traces=trace_round,
                round_index=round_index,
                metadata=metadata,
            )
            snapshots.append(snapshot)
            current_states = snapshot.states
        final_group_summaries = snapshots[-1].group_summaries if snapshots else []
        all_traces = [trace for snapshot in snapshots for trace in snapshot.traces]
        metrics = self._metrics(current_states, signals=[signal for round_items in resolved_rounds for signal in round_items], traces=all_traces)
        summary = self._render_result_summary(snapshots, current_states, final_group_summaries, metrics)
        return BeliefEvolutionResult(
            run_id=self.run_id,
            rounds_completed=len(snapshots),
            snapshots=snapshots,
            final_states=current_states,
            final_group_summaries=final_group_summaries,
            traces=all_traces,
            metrics=metrics,
            summary=summary,
            metadata={**self.metadata, **(metadata or {})},
        )

    def _metrics(
        self,
        states: Iterable[BeliefState],
        *,
        signals: list[BeliefEvolutionSignal],
        traces: list[NormalizedSocialTrace],
    ) -> dict[str, float]:
        states = list(states)
        if not states:
            return {
                "agent_count": 0.0,
                "signal_count": float(len(signals)),
                "trace_count": float(len(traces)),
                "average_confidence": 0.0,
                "average_trust": 0.0,
                "average_memory_depth": 0.0,
                "stance_diversity": 0.0,
                "stance_entropy": 0.0,
            }
        return {
            "agent_count": float(len(states)),
            "signal_count": float(len(signals)),
            "trace_count": float(len(traces)),
            "average_confidence": mean(state.confidence for state in states),
            "average_trust": mean(state.trust for state in states),
            "average_memory_depth": mean(len(state.memory_window) for state in states),
            "stance_diversity": float(len({state.stance for state in states})),
            "stance_entropy": _stance_entropy(states),
            "dominant_stance_share": self._dominant_share(states),
        }

    @staticmethod
    def _dominant_share(states: list[BeliefState]) -> float:
        if not states:
            return 0.0
        counts: dict[str, int] = defaultdict(int)
        for state in states:
            counts[state.stance] += 1
        return max(counts.values()) / len(states)

    @staticmethod
    def _render_summary(
        round_index: int,
        states: list[BeliefState],
        group_summaries: list[BeliefGroupSummary],
        metrics: dict[str, float],
    ) -> str:
        dominant = dominant_stance(states) or "unknown"
        group_count = len(group_summaries)
        return (
            f"Belief evolution round {round_index} updated {len(states)} agents across {group_count} groups. "
            f"Dominant stance={dominant}. "
            f"Average confidence={metrics.get('average_confidence', 0.0):.2f}, "
            f"average trust={metrics.get('average_trust', 0.0):.2f}."
        )

    @staticmethod
    def _render_result_summary(
        snapshots: list[BeliefEvolutionRoundSnapshot],
        states: list[BeliefState],
        group_summaries: list[BeliefGroupSummary],
        metrics: dict[str, float],
    ) -> str:
        if not snapshots:
            return "No belief evolution rounds were executed."
        return (
            f"Belief evolution completed {len(snapshots)} rounds. "
            f"Final dominant stance={dominant_stance(states) or 'unknown'}. "
            f"Groups={len(group_summaries)}. "
            f"Mean confidence={metrics.get('average_confidence', 0.0):.2f}."
        )


def evolve_belief_states(
    states: Iterable[BeliefState],
    *,
    signals: Iterable[BeliefEvolutionSignal] | None = None,
    traces: Iterable[NormalizedSocialTrace] | None = None,
    round_index: int = 0,
    memory_capacity: int = 12,
) -> BeliefEvolutionRoundSnapshot:
    engine = BeliefEvolutionEngine(memory_capacity=memory_capacity)
    return engine.step(states, signals=signals, traces=traces, round_index=round_index)


def build_belief_states_from_texts(
    agent_ids: Iterable[str],
    *,
    stance: str = "uncertain",
    confidence: float = 0.5,
    trust: float = 0.5,
    memory_capacity: int = 12,
    memory_texts: Iterable[str] | None = None,
) -> list[BeliefState]:
    memory = compact_memory_texts(memory_texts or [], capacity=memory_capacity)
    return [
        BeliefState(
            agent_id=agent_id,
            stance=stance,
            confidence=confidence,
            trust=trust,
            memory_window=list(memory),
        )
        for agent_id in agent_ids
    ]
