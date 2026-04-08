from swarm_core.belief_state import BeliefState
from swarm_core.cross_platform_simulation import CrossPlatformSimulator


def test_cross_platform_simulator_emits_multiple_platforms_and_rounds() -> None:
    simulator = CrossPlatformSimulator()
    report = simulator.simulate(
        topic="launch plan",
        summary="A cautious rollout is favored.",
        beliefs=[
            BeliefState(agent_id="agent_1", stance="support", confidence=0.7, trust=0.6, memory_window=["launch"]),
            BeliefState(agent_id="agent_2", stance="skeptical", confidence=0.5, trust=0.5, memory_window=["risk"]),
        ],
        platforms=["reddit", "twitter", "forum"],
        rounds=2,
        interventions=["inject outage"],
    )

    assert report.rounds == 2
    assert set(report.platforms) == {"reddit", "twitter", "forum"}
    assert report.trace_count == len(report.traces)
    assert any(trace.kind.value == "intervention" for trace in report.traces)
