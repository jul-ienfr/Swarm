from __future__ import annotations

from swarm_core.belief_state import BeliefState
from swarm_core.deliberation_artifacts import DeliberationArtifact, DeliberationArtifactKind, DeliberationMode, DeliberationRunManifest
from swarm_core.deliberation_contracts import (
    DeliberationReport,
    DeliberationRequest,
    belief_state_snapshot_from_state,
    participant_profile_from_source,
    social_trace_bundles_from_traces,
)
from swarm_core.normalized_social_traces import NormalizedSocialTrace, SocialTraceKind
from swarm_core.profile_generation_pipeline import PersonaProfile


def test_deliberation_request_matches_plan_shape() -> None:
    request = DeliberationRequest(
        topic="market rollout",
        objective="find the best launch strategy",
        mode=DeliberationMode.hybrid,
        documents=["signal a"],
        participants=["architect", "guardian"],
        population_size=128,
        rounds=3,
        time_horizon="14d",
        engine_preference="agentsociety",
    )

    assert request.schema_version == "v1"
    assert request.mode == DeliberationMode.hybrid
    assert request.population_size == 128
    assert request.engine_preference == "agentsociety"


def test_deliberation_manifest_exposes_plan_fields_and_tracks_refs() -> None:
    manifest = DeliberationRunManifest(
        run_id="delib_1",
        mode=DeliberationMode.simulation,
        engine_used="agentsociety",
        seed={"input_hash": "abc"},
        profile_version="profile_generation_pipeline_v1",
        graph_version="graph_store_v1",
        status="completed",
    )
    manifest.add_input_ref("/tmp/request.json")
    manifest.add_artifact(
        DeliberationArtifact(
            artifact_id="artifact_1",
            kind=DeliberationArtifactKind.report,
            title="report",
            uri="/tmp/report.json",
        )
    )

    assert manifest.schema_version == "v1"
    assert manifest.engine_used == "agentsociety"
    assert manifest.seed["input_hash"] == "abc"
    assert manifest.profile_version == "profile_generation_pipeline_v1"
    assert manifest.graph_version == "graph_store_v1"
    assert manifest.input_refs == ["/tmp/request.json"]
    assert manifest.artifact_refs == ["/tmp/report.json"]
    assert manifest.status == "completed"


def test_participant_profile_and_belief_snapshot_match_plan_shape() -> None:
    persona = PersonaProfile(
        label="guardian",
        summary="Risk-focused guardian persona.",
        evidence=["doc:1", "doc:2"],
        confidence=0.72,
        trust=0.61,
        metadata={"group_id": "cluster_1"},
    )
    participant = participant_profile_from_source(persona)
    state = BeliefState(
        agent_id="guardian",
        stance="cautious",
        confidence=0.73,
        trust=0.62,
        memory_window=["remember uncertainty"],
        group_id="cluster_1",
    )
    snapshot = belief_state_snapshot_from_state(run_id="delib_1", state=state, tick=2)

    assert participant.profile_id == persona.profile_id
    assert participant.persona_summary == "Risk-focused guardian persona."
    assert participant.belief_seed["confidence"] == 0.72
    assert participant.group_id == "cluster_1"
    assert participant.grounding_refs == ["doc:1", "doc:2"]
    assert participant.confidence_prior == 0.72

    assert snapshot.run_id == "delib_1"
    assert snapshot.agent_id == "guardian"
    assert snapshot.tick == 2
    assert snapshot.stance == "cautious"
    assert snapshot.trust_map["cluster_1"] == 0.62
    assert snapshot.memory_window == ["remember uncertainty"]


def test_social_trace_bundle_and_report_match_plan_shape() -> None:
    traces = [
        NormalizedSocialTrace(platform="reddit", actor_id="a1", kind=SocialTraceKind.post, content="Post body"),
        NormalizedSocialTrace(platform="reddit", actor_id="a2", kind=SocialTraceKind.comment, content="Comment body"),
        NormalizedSocialTrace(platform="reddit", actor_id="a3", kind=SocialTraceKind.belief_shift, content="Belief changed"),
        NormalizedSocialTrace(platform="reddit", actor_id="a4", kind=SocialTraceKind.intervention, content="Intervention injected"),
    ]
    bundles = social_trace_bundles_from_traces(run_id="delib_1", traces=traces)
    report = DeliberationReport(
        summary="A concise strategic summary.",
        scenarios=[{"id": "s1"}],
        risks=[{"id": "r1"}],
        recommendations=[{"id": "rec1"}],
        metrics={"confidence_index": 0.8},
        cluster_summaries=[{"group_id": "cluster_1"}],
        confidence_level=0.81,
        uncertainty_points=["timing uncertainty"],
        dissent_points=["guardian objects"],
    )

    assert len(bundles) == 1
    assert bundles[0].run_id == "delib_1"
    assert bundles[0].platform == "reddit"
    assert len(bundles[0].posts) == 1
    assert len(bundles[0].comments) == 1
    assert len(bundles[0].reactions) == 1
    assert len(bundles[0].follow_events) == 1

    assert report.summary == "A concise strategic summary."
    assert report.cluster_summaries == [{"group_id": "cluster_1"}]
    assert report.confidence_level == 0.81
    assert report.dissent_points == ["guardian objects"]
