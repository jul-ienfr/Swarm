from __future__ import annotations

from swarm_core.belief_evolution import BeliefEvolutionEngine, BeliefEvolutionSignal, build_belief_states_from_texts
from swarm_core.belief_state import BeliefState
from swarm_core.normalized_social_traces import NormalizedSocialTrace, SocialTraceKind


def test_belief_evolution_updates_beliefs_and_memory() -> None:
    states = [
        BeliefState(agent_id="agent_1", stance="uncertain", confidence=0.4, trust=0.5, memory_window=["old"]),
        BeliefState(agent_id="agent_2", stance="uncertain", confidence=0.5, trust=0.4, memory_window=["old"]),
    ]
    signals = [
        BeliefEvolutionSignal(
            agent_id="agent_1",
            stance="support",
            confidence_delta=0.25,
            trust_delta=0.1,
            sentiment=0.6,
            memory_items=["positive evidence"],
            platform="twitter",
        ),
        BeliefEvolutionSignal(
            agent_id="agent_2",
            stance="oppose",
            confidence_delta=-0.1,
            trust_delta=-0.05,
            sentiment=-0.4,
            memory_items=["risk evidence"],
            platform="reddit",
        ),
    ]
    traces = [
        NormalizedSocialTrace(
            platform="twitter",
            actor_id="agent_1",
            kind=SocialTraceKind.post,
            content="support the rollout",
            sentiment=0.5,
            score=0.9,
            tags=["rollout"],
        ),
        NormalizedSocialTrace(
            platform="reddit",
            actor_id="agent_2",
            kind=SocialTraceKind.comment,
            content="delay the launch",
            sentiment=-0.5,
            score=0.7,
            tags=["launch"],
        ),
    ]

    engine = BeliefEvolutionEngine(memory_capacity=3)
    snapshot = engine.step(states, signals=signals, traces=traces, round_index=2)

    assert snapshot.round_index == 2
    assert snapshot.metrics["agent_count"] == 2
    assert snapshot.metrics["trace_count"] == 2
    assert snapshot.states[0].stance == "support"
    assert snapshot.states[1].stance == "oppose"
    assert len(snapshot.memory_windows["agent_1"].entries) <= 3
    assert snapshot.group_summaries
    assert "Belief evolution round 2" in snapshot.summary


def test_belief_evolution_runs_multiple_rounds() -> None:
    states = build_belief_states_from_texts(["agent_a", "agent_b"], memory_texts=["initial signal"])
    engine = BeliefEvolutionEngine()
    result = engine.run(
        states,
        rounds=[
            [
                BeliefEvolutionSignal(agent_id="agent_a", stance="support", confidence_delta=0.1, sentiment=0.4),
            ],
            [
                BeliefEvolutionSignal(agent_id="agent_b", stance="oppose", confidence_delta=0.1, sentiment=-0.4),
            ],
        ],
    )

    assert result.rounds_completed == 2
    assert len(result.snapshots) == 2
    assert len(result.final_states) == 2
    assert result.final_group_summaries
    assert result.summary
