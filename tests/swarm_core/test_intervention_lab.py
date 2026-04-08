from swarm_core.belief_state import BeliefState
from swarm_core.intervention_lab import InterventionLab
from swarm_core.normalized_social_traces import normalize_social_trace


def test_intervention_lab_compares_before_and_after() -> None:
    lab = InterventionLab()
    report = lab.compare(
        before_beliefs=[BeliefState(agent_id="a", stance="support", confidence=0.6, trust=0.6)],
        after_beliefs=[
            BeliefState(agent_id="a", stance="support", confidence=0.7, trust=0.7),
            BeliefState(agent_id="b", stance="support", confidence=0.5, trust=0.6),
        ],
        before_traces=[normalize_social_trace("baseline", platform="reddit", actor_id="a")],
        after_traces=[
            normalize_social_trace("baseline", platform="reddit", actor_id="a"),
            normalize_social_trace("intervention", platform="twitter", actor_id="b"),
        ],
        interventions=["inject message"],
    )

    assert report.intervention_count == 1
    assert any(delta.metric == "support_share" for delta in report.deltas)
    assert report.notes
