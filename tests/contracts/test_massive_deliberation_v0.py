from __future__ import annotations

from swarm_core.deep_market_social_bridge_v0 import (
    DeepMarketSocialBridge,
    MarketSignal,
    MarketSocialBridgeRequest,
    SignalDirection,
    SocialSentiment,
    SocialSignal,
)
from swarm_core.persona_chat_helpers_v0 import PersonaChatHelper, PersonaChatRequest
from swarm_core.profile_generation_pipeline_v0 import (
    PersonaProfile,
    ProfileGenerationPipeline,
    ProfileGenerationRequest,
    ProfileRole,
    ProfileStance,
)
from swarm_core.profile_quality_guard import ProfileQualityGuard, ProfileQualityThresholds
from swarm_core.scenario_judge_v0 import ScenarioCandidate, ScenarioJudge, ScenarioVerdict


def test_profile_generation_pipeline_is_bounded_and_stable():
    pipeline = ProfileGenerationPipeline()
    report = pipeline.run(
        ProfileGenerationRequest(
            topic="launch a new planning product",
            objective="balance growth and trust",
            participants=["architect", "guardian"],
            documents=[
                "Growth depends on trust and clear rollout signals.",
                "Risk controls and cost discipline matter.",
            ],
            interventions=["add rollback guardrails"],
            target_profiles=10,
            max_profiles=3,
        )
    )

    assert report.profile_count == 3
    assert len(report.profiles) == 3
    assert report.profiles[0].label == "architect"
    assert report.profiles[1].label == "guardian"
    assert report.cohort_counts
    assert report.top_keywords


def test_profile_generation_pipeline_uses_semantic_labels_and_fr_en_keywords():
    pipeline = ProfileGenerationPipeline()
    report = pipeline.run(
        ProfileGenerationRequest(
            topic="Revue du rollout strategy",
            objective="Protect trust and improve revenue",
            documents=[
                "Le rollout protege la confiance, le revenu et la qualite.",
                "Trust, rollout, and risk controls should stay clear.",
            ],
            interventions=["Add rollback guardrails"],
            target_profiles=5,
            max_profiles=5,
        )
    )

    labels = [profile.label for profile in report.profiles]
    roles = {profile.role for profile in report.profiles}
    stances = {profile.stance for profile in report.profiles}
    assert len(labels) == 5
    assert len(set(labels)) == 5
    assert all(label not in {"les", "plan", "est", "pas"} for label in labels)
    assert any(label.startswith(("strategy", "analysis", "risk", "ops", "market", "governance", "social")) for label in labels)
    assert "les" not in report.top_keywords
    assert any(keyword in report.top_keywords for keyword in {"rollout", "trust", "revenue", "confiance", "revenu", "risk"})


def test_profile_generation_pipeline_preserves_role_and_stance_diversity_on_risk_heavy_topics():
    pipeline = ProfileGenerationPipeline()
    report = pipeline.run(
        ProfileGenerationRequest(
            topic="Risk review for rollout reliability and rollback policy",
            objective="Increase stability without collapsing the room into one governance voice",
            documents=[
                "Risk, safety, compliance, rollback, and reliability dominate the current draft.",
                "We still need market, execution, and research counterpoints to avoid a monoculture.",
            ],
            target_profiles=6,
            max_profiles=6,
        )
    )

    roles = {profile.role for profile in report.profiles}
    stances = {profile.stance for profile in report.profiles}

    assert len(roles) >= 4
    assert len(stances) >= 3
    assert any(profile.stance == ProfileStance.challenge for profile in report.profiles)
    assert any(profile.stance == ProfileStance.efficiency for profile in report.profiles)
    assert any(profile.role == ProfileRole.guardian for profile in report.profiles)
    assert any(profile.role == ProfileRole.operator for profile in report.profiles)
    assert len(roles) >= 4
    assert ProfileStance.governance in stances
    assert ProfileStance.challenge in stances or ProfileStance.efficiency in stances


def test_persona_chat_helper_drafts_structured_turns():
    profile = PersonaProfile(
        label="guardian",
        role=ProfileRole.guardian,
        stance=ProfileStance.governance,
        confidence=0.82,
        trust=0.71,
        summary="Guardian persona focused on risk containment.",
        keywords=["risk", "policy", "rollback"],
        evidence=["risk controls", "policy guardrails"],
    )
    helper = PersonaChatHelper()
    turn = helper.draft_turn(
        PersonaChatRequest(
            topic="product rollout",
            objective="keep the launch safe",
            profile=profile,
            round_index=1,
            question="What should we do first?",
            prior_summary="The room is worried about reversibility.",
            max_words=120,
        )
    )
    summary = helper.summarize_round([turn], round_index=1)

    assert turn.profile_id == profile.profile_id
    assert "Thesis:" in turn.content
    assert "rollback" in turn.content.lower()
    assert summary.round_index == 1
    assert summary.consensus_points


def test_scenario_judge_prefers_actionable_candidate():
    judge = ScenarioJudge()
    weak = ScenarioCandidate(
        title="Weak idea",
        thesis="Short and vague.",
        evidence=[],
        risks=[],
        actions=[],
        confidence=0.2,
        impact=0.1,
    )
    strong = ScenarioCandidate(
        title="Market recovery plan",
        topic="market recovery",
        thesis="We should stabilize the core channel, improve the messaging loop, and stage the rollout carefully.",
        evidence=["sales trend", "community trust"],
        risks=["execution lag"],
        actions=["hold the line", "publish a clear mitigation plan"],
        confidence=0.88,
        impact=0.82,
    )
    report = judge.judge([weak, strong], topic="market recovery")

    assert report.top_scenario_id == strong.scenario_id
    assert report.verdict in {ScenarioVerdict.approve, ScenarioVerdict.revise}
    assert any(assessment.scenario_id == strong.scenario_id and assessment.verdict == ScenarioVerdict.approve for assessment in report.assessments)


def test_deep_market_social_bridge_returns_profiles_scenarios_and_judgement():
    bridge = DeepMarketSocialBridge()
    report = bridge.run(
        MarketSocialBridgeRequest(
            topic="new market launch",
            objective="balance adoption and trust",
            participants=["architect", "moderator"],
            market_signals=[
                MarketSignal(name="revenue_growth", value=0.8, direction=SignalDirection.up, weight=1.2),
            ],
            social_signals=[
                SocialSignal(name="community_sentiment", value=-0.4, sentiment=SocialSentiment.negative, reach=0.7, weight=1.0),
            ],
            target_profiles=6,
            max_scenarios=4,
        )
    )

    assert report.profiles
    assert report.scenarios
    assert report.judge_report.top_scenario_id is not None
    assert report.bridge_score >= 0.0
    assert "Lead profile" in report.coordination_brief
    assert any("Trust repair" in scenario.title or "Market shock" in scenario.title for scenario in report.scenarios)


def test_profile_quality_guard_flags_generic_labels_and_underpowered_profiles() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {
                "label": "les",
                "summary": "Focuses on rollout details",
                "evidence": ["doc-1"],
                "stance": "support",
                "confidence": 0.81,
            },
            {
                "label": "market_strategy",
                "summary": "Focuses on revenue growth and trust",
                "evidence": ["doc-2"],
                "stance": "challenge",
                "confidence": 0.79,
            },
        ],
        thresholds=ProfileQualityThresholds(
            min_coverage=1.0,
            min_grounding=0.5,
            min_diversity=0.5,
            min_consistency=0.7,
            min_label_quality=0.6,
        ),
    )

    assert report.passed is False
    assert report.label_quality < 0.6
    assert any(issue.code == "generic_label" for issue in report.issues)
