from __future__ import annotations

from pathlib import Path

from swarm_core.belief_state import BeliefState
from swarm_core.cross_platform_runtime import (
    CrossPlatformActionLog,
    CrossPlatformBeliefSnapshot,
    CrossPlatformMemoryBridge,
    CrossPlatformMarketMediaBridge,
    CrossPlatformOrchestrationPlan,
    CrossPlatformOrchestrator,
    build_cross_platform_orchestration_report_from_simulation,
)
from swarm_core.cross_platform_simulation import CrossPlatformSimulator
from swarm_core.normalized_social_traces import NormalizedSocialTrace, SocialTraceKind


def _trace(
    *,
    platform: str,
    actor_id: str,
    content: str,
    round_index: int,
    sentiment: float,
    score: float,
    kind: SocialTraceKind = SocialTraceKind.post,
) -> NormalizedSocialTrace:
    return NormalizedSocialTrace(
        platform=platform,
        actor_id=actor_id,
        kind=kind,
        content=content,
        round_index=round_index,
        sentiment=sentiment,
        score=score,
        tags=[platform, actor_id],
    )


def test_cross_platform_plan_normalizes_platforms_and_limits() -> None:
    plan = CrossPlatformOrchestrationPlan(
        topic="launch",
        objective="evaluate cross-platform pressure",
        platforms=["Twitter", "reddit", "twitter", "Forum"],
        rounds=0,
        memory_window=0,
        trace_limit_per_platform=0,
        belief_limit_per_agent=0,
        market_keywords=["risk", "risk", "launch"],
        media_keywords=["coverage", "coverage"],
    )

    assert plan.platforms == ["twitter", "reddit", "forum"]
    assert plan.rounds == 1
    assert plan.memory_window == 1
    assert plan.trace_limit_per_platform == 1
    assert plan.belief_limit_per_agent == 1
    assert plan.market_keywords == ["risk", "launch"]
    assert plan.media_keywords == ["coverage"]


def test_cross_platform_action_log_persists_jsonl(tmp_path: Path) -> None:
    log = CrossPlatformActionLog(output_path=tmp_path / "actions.jsonl")
    log.record_action(
        platform="reddit",
        actor_id="agent_1",
        kind="signal",
        stage="running",
        title="Support the rollout",
        summary="Support the rollout with cautious gates.",
        tags=["alpha", "alpha"],
        details={"confidence": 0.7},
    )
    log.record_trace(
        _trace(
            platform="twitter",
            actor_id="agent_2",
            content="Watch the rollout carefully and keep the kill-switch ready.",
            round_index=0,
            sentiment=-0.4,
            score=0.8,
            kind=SocialTraceKind.intervention,
        )
    )

    summary = log.summary()

    assert summary.record_count == 2
    assert summary.platform_counts == {"reddit": 1, "twitter": 1}
    assert summary.kind_counts["signal"] == 1
    assert summary.kind_counts["intervention"] == 1
    assert summary.stage_counts["running"] == 1
    assert summary.stage_counts["intervention"] == 1
    assert log.output_path is not None
    assert log.output_path.exists()

    reloaded = CrossPlatformActionLog(output_path=log.output_path)
    assert reloaded.summary().record_count == 2
    assert len(reloaded.list(platform="reddit")) == 1
    assert len(reloaded.list(actor_id="agent_2")) == 1


def test_cross_platform_memory_bridge_builds_belief_snapshots_and_round_reports() -> None:
    bridge = CrossPlatformMemoryBridge(topic="launch", objective="coordinate a cautious rollout", memory_window=3)
    bridge.ingest_beliefs(
        [
            BeliefState(agent_id="agent_1", stance="support", confidence=0.65, trust=0.55, memory_window=["launch"]),
            BeliefState(agent_id="agent_2", stance="skeptical", confidence=0.45, trust=0.52, memory_window=["risk"]),
        ]
    )
    bridge.ingest_traces(
        [
            _trace(
                platform="reddit",
                actor_id="agent_1",
                content="The rollout looks strong if the gates stay explicit.",
                round_index=0,
                sentiment=0.75,
                score=0.9,
            ),
            _trace(
                platform="twitter",
                actor_id="agent_2",
                content="Keep the rollback criteria tight before scaling.",
                round_index=0,
                sentiment=-0.45,
                score=0.7,
                kind=SocialTraceKind.intervention,
            ),
        ]
    )

    report = bridge.build_report()
    round_snapshot = bridge.build_round_snapshot(0)
    agent_snapshot = bridge.build_agent_snapshot("agent_1")

    assert report.trace_count == 2
    assert report.belief_count == 2
    assert report.platform_counts == {"reddit": 1, "twitter": 1}
    assert report.round_counts == {"0": 2}
    assert "support" in report.belief_summaries["agent_1"]["stance"]
    assert "skeptical" in report.belief_summaries["agent_2"]["stance"]
    assert agent_snapshot["found"] is True
    assert agent_snapshot["recent_trace_ids"]
    assert round_snapshot["trace_count"] == 2
    assert round_snapshot["platform_counts"] == {"reddit": 1, "twitter": 1}

    snapshot = CrossPlatformBeliefSnapshot.from_belief_state(
        BeliefState(agent_id="agent_3", stance="observing", confidence=0.5, trust=0.5, memory_window=["market"]),
        platform="forum",
    )
    snapshot.absorb_trace(
        _trace(
            platform="forum",
            actor_id="agent_3",
            content="The market signal feels constructive.",
            round_index=1,
            sentiment=0.55,
            score=0.6,
        )
    )
    assert snapshot.signal_count == 1
    assert snapshot.recent_platforms == ["forum"]
    assert "constructive" in snapshot.memory_window[0].lower()


def test_cross_platform_market_media_bridge_detects_alignment_and_divergence() -> None:
    traces = [
        _trace(
            platform="reddit",
            actor_id="agent_1",
            content="Momentum looks strong.",
            round_index=0,
            sentiment=0.8,
            score=0.8,
        ),
        _trace(
            platform="twitter",
            actor_id="agent_2",
            content="The position still looks constructive.",
            round_index=0,
            sentiment=0.7,
            score=0.7,
        ),
    ]

    report = CrossPlatformMarketMediaBridge.build_report(
        traces,
        topic="launch",
        objective="bridge market and media signals",
        market_snapshot={"probability": 0.2, "depth": {"midpoint": 0.2}},
        market_keywords=["launch"],
        media_keywords=["momentum"],
    )

    assert report.market_bias == 0.2
    assert report.market_bias_path in {"probability", "depth.midpoint"}
    assert report.social_trace_aggregate.trace_count == 2
    assert report.divergence_score is not None and report.divergence_score > 0.4
    assert report.alignment_score is not None and report.alignment_score < 0.7
    assert report.watchpoints
    assert report.recommendations
    assert "cross-platform view" in report.narrative.lower()


def test_cross_platform_orchestrator_builds_end_to_end_report(tmp_path: Path) -> None:
    simulator = CrossPlatformSimulator()
    beliefs = [
        BeliefState(agent_id="agent_1", stance="support", confidence=0.7, trust=0.6, memory_window=["launch"]),
        BeliefState(agent_id="agent_2", stance="skeptical", confidence=0.5, trust=0.5, memory_window=["risk"]),
    ]
    simulation = simulator.simulate(
        topic="launch",
        summary="Keep the rollout cautious.",
        beliefs=beliefs,
        platforms=["reddit", "twitter"],
        rounds=2,
        interventions=["watch sentiment"],
    )
    plan = CrossPlatformOrchestrationPlan(
        topic="launch",
        objective="evaluate cross-platform narrative",
        platforms=simulation.platforms,
        rounds=simulation.rounds,
        market_keywords=["launch", "risk"],
        media_keywords=["momentum"],
    )
    action_log = CrossPlatformActionLog(output_path=tmp_path / "orchestrator.jsonl")
    orchestrator = CrossPlatformOrchestrator(plan=plan, action_log=action_log)
    orchestrator.ingest_beliefs(beliefs)
    orchestrator.ingest_traces(simulation.traces)
    orchestrator.record_action(
        platform="reddit",
        actor_id="agent_1",
        kind="decision",
        stage="approved",
        title="Approve cautious rollout",
        summary="Approve the cautious rollout after the market check.",
        tags=["decision", "approval"],
    )

    report = orchestrator.build_report(market_snapshot={"probability": 0.65, "price": 0.64})
    from_simulation = build_cross_platform_orchestration_report_from_simulation(
        plan,
        simulation,
        beliefs=beliefs,
        market_snapshot={"probability": 0.65, "price": 0.64},
    )

    assert report.plan.run_id == plan.run_id
    assert report.trace_aggregate.trace_count == simulation.trace_count
    assert report.memory_report.trace_count == simulation.trace_count
    assert report.memory_report.belief_count >= 2
    assert report.action_report.record_count == simulation.trace_count + 1
    assert report.market_media_report.market_bias == 0.65
    assert report.market_media_report.alignment_score is not None
    assert "alignment" in report.summary.lower()
    assert from_simulation.trace_aggregate.trace_count == simulation.trace_count
    assert from_simulation.action_report.record_count == simulation.trace_count
