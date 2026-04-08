from __future__ import annotations

from enum import Enum
from statistics import mean
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .persona_chat_helpers_v0 import PersonaChatHelper
from .profile_generation_pipeline_v0 import (
    PersonaProfile,
    ProfileGenerationPipeline,
    ProfileGenerationRequest,
    ProfileStance,
)
from .scenario_judge_v0 import ScenarioCandidate, ScenarioJudge, ScenarioJudgementReport, ScenarioVerdict


class SignalDirection(str, Enum):
    up = "up"
    down = "down"
    flat = "flat"


class MarketSignal(BaseModel):
    name: str
    value: float = 0.0
    unit: str = ""
    direction: SignalDirection = SignalDirection.flat
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("weight")
    @classmethod
    def _clamp_weight(cls, value: float) -> float:
        return max(0.0, float(value))


class SocialSentiment(str, Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class SocialSignal(BaseModel):
    name: str
    value: float = 0.0
    unit: str = ""
    sentiment: SocialSentiment = SocialSentiment.neutral
    reach: float = 0.0
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reach", "weight")
    @classmethod
    def _clamp_non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class BridgeScenario(ScenarioCandidate):
    bridge_type: str = "market_social"
    market_implications: list[str] = Field(default_factory=list)
    social_implications: list[str] = Field(default_factory=list)


class MarketSocialBridgeRequest(BaseModel):
    topic: str
    objective: str = ""
    participants: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    market_signals: list[MarketSignal] = Field(default_factory=list)
    social_signals: list[SocialSignal] = Field(default_factory=list)
    target_profiles: int = 8
    max_scenarios: int = 4
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_profiles", "max_scenarios")
    @classmethod
    def _validate_positive(cls, value: int) -> int:
        return max(1, int(value))


class MarketSocialBridgeReport(BaseModel):
    bridge_id: str = Field(default_factory=lambda: f"bridge_{uuid4().hex[:12]}")
    topic: str
    objective: str = ""
    profiles: list[PersonaProfile] = Field(default_factory=list)
    scenarios: list[BridgeScenario] = Field(default_factory=list)
    judge_report: ScenarioJudgementReport
    best_scenario_id: str | None = None
    bridge_score: float = 0.0
    coordination_brief: str = ""
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeepMarketSocialBridge:
    """
    Bounded market/social bridge for deliberation planning.

    It turns market + social signals into a small scenario set, then reuses the
    profile pipeline and scenario judge to produce a compact decision report.
    """

    def __init__(
        self,
        *,
        profile_pipeline: ProfileGenerationPipeline | None = None,
        scenario_judge: ScenarioJudge | None = None,
    ) -> None:
        self.profile_pipeline = profile_pipeline or ProfileGenerationPipeline()
        self.scenario_judge = scenario_judge or ScenarioJudge()
        self.persona_helper = PersonaChatHelper()

    def run(self, request: MarketSocialBridgeRequest) -> MarketSocialBridgeReport:
        profile_report = self.profile_pipeline.run(
            ProfileGenerationRequest(
                topic=request.topic,
                objective=request.objective,
                participants=request.participants,
                documents=request.documents,
                entities=request.entities,
                interventions=request.interventions,
                target_profiles=request.target_profiles,
                max_profiles=max(request.max_scenarios * 4, request.target_profiles, 8),
                metadata=request.metadata,
            )
        )
        scenarios = self._build_scenarios(request, profile_report.profiles)
        judge_report = self.scenario_judge.judge(scenarios, topic=request.topic)
        best = next((scenario for scenario in scenarios if scenario.scenario_id == judge_report.top_scenario_id), None)
        bridge_score = self._score_bridge(profile_report.profiles, judge_report)
        coordination_brief = self._build_coordination_brief(request, profile_report.profiles, best, judge_report)
        recommendations = self._build_recommendations(best, judge_report)
        return MarketSocialBridgeReport(
            topic=request.topic,
            objective=request.objective,
            profiles=profile_report.profiles,
            scenarios=scenarios,
            judge_report=judge_report,
            best_scenario_id=judge_report.top_scenario_id,
            bridge_score=bridge_score,
            coordination_brief=coordination_brief,
            recommendations=recommendations,
            metadata={
                "profile_report_id": profile_report.request_id,
                "profile_count": profile_report.profile_count,
                "scenario_count": len(scenarios),
                "signal_balance": self._signal_balance(request.market_signals, request.social_signals),
            },
        )

    def _build_scenarios(self, request: MarketSocialBridgeRequest, profiles: list[PersonaProfile]) -> list[BridgeScenario]:
        candidates: list[BridgeScenario] = []
        signal_balance = self._signal_balance(request.market_signals, request.social_signals)
        keyword_pool = self._keyword_pool(request, profiles)

        if request.market_signals:
            candidates.append(
                self._market_shock_scenario(request, signal_balance, keyword_pool)
            )
        if request.social_signals:
            candidates.append(
                self._social_contagion_scenario(request, signal_balance, keyword_pool)
            )
        if self._has_negative_trust_signal(request.social_signals):
            candidates.append(
                self._trust_repair_scenario(request, signal_balance, keyword_pool)
            )
        if self._has_positive_growth_signal(request.market_signals, request.social_signals):
            candidates.append(
                self._adoption_cascade_scenario(request, signal_balance, keyword_pool)
            )
        if not candidates:
            candidates.append(
                self._baseline_scenario(request, keyword_pool)
            )

        return candidates[: request.max_scenarios]

    def _market_shock_scenario(
        self,
        request: MarketSocialBridgeRequest,
        signal_balance: float,
        keyword_pool: list[str],
    ) -> BridgeScenario:
        title = f"Market shock response for {request.topic}"
        thesis = (
            "Prepare for a market shock by protecting the most fragile assumptions, "
            "while preserving the ability to scale back quickly."
        )
        return BridgeScenario(
            title=title,
            topic=request.topic,
            thesis=thesis,
            evidence=self._signal_names(request.market_signals),
            risks=["price volatility", "execution slippage"],
            actions=[
                "Set a defensive threshold for the core market metric.",
                "Create a rollback path for the most exposed steps.",
            ],
            confidence=self._scenario_confidence(signal_balance, request.market_signals, request.social_signals),
            impact=0.8,
            horizon="14d",
            market_implications=[
                "Expect pressure on near-term price discovery.",
                "Monitor leading indicators for a rebound or further deterioration.",
            ],
            social_implications=[
                "Expect cautious messaging and slower adoption if trust is low.",
            ],
            metadata={"keywords": keyword_pool[:5], "scenario_type": "market_shock"},
        )

    def _social_contagion_scenario(
        self,
        request: MarketSocialBridgeRequest,
        signal_balance: float,
        keyword_pool: list[str],
    ) -> BridgeScenario:
        title = f"Social contagion response for {request.topic}"
        thesis = (
            "Optimize for message spread and retention by anchoring the narrative in a small set of credible signals."
        )
        return BridgeScenario(
            title=title,
            topic=request.topic,
            thesis=thesis,
            evidence=self._signal_names(request.social_signals),
            risks=["narrative fragmentation", "audience fatigue"],
            actions=[
                "Concentrate the message around one repeatable storyline.",
                "Use a small number of high-trust personas to reinforce the signal.",
            ],
            confidence=self._scenario_confidence(signal_balance, request.market_signals, request.social_signals),
            impact=0.7,
            horizon="7d",
            market_implications=[
                "The market outcome will be driven by message velocity rather than hard fundamentals alone.",
            ],
            social_implications=[
                "High-reach channels can amplify the preferred narrative if the framing stays consistent.",
            ],
            metadata={"keywords": keyword_pool[:5], "scenario_type": "social_contagion"},
        )

    def _trust_repair_scenario(
        self,
        request: MarketSocialBridgeRequest,
        signal_balance: float,
        keyword_pool: list[str],
    ) -> BridgeScenario:
        title = f"Trust repair plan for {request.topic}"
        thesis = (
            "When sentiment is negative, the best response is to repair trust before attempting aggressive expansion."
        )
        return BridgeScenario(
            title=title,
            topic=request.topic,
            thesis=thesis,
            evidence=self._signal_names(request.social_signals),
            risks=["trust deficit", "backlash risk"],
            actions=[
                "Publish a transparent mitigation plan.",
                "Make a single trusted spokesperson the main interface.",
            ],
            confidence=self._scenario_confidence(signal_balance, request.market_signals, request.social_signals),
            impact=0.75,
            horizon="21d",
            market_implications=[
                "Short-term growth may soften while the trust base is rebuilt.",
            ],
            social_implications=[
                "A credible repair sequence can reset the conversation and lower hostility.",
            ],
            metadata={"keywords": keyword_pool[:5], "scenario_type": "trust_repair"},
        )

    def _adoption_cascade_scenario(
        self,
        request: MarketSocialBridgeRequest,
        signal_balance: float,
        keyword_pool: list[str],
    ) -> BridgeScenario:
        title = f"Adoption cascade plan for {request.topic}"
        thesis = (
            "If both market and social signals are positive, scale the strongest path and keep the feedback loop short."
        )
        return BridgeScenario(
            title=title,
            topic=request.topic,
            thesis=thesis,
            evidence=self._signal_names(request.market_signals) + self._signal_names(request.social_signals),
            risks=["overextension", "coordination lag"],
            actions=[
                "Increase rollout only where the signal remains strongest.",
                "Keep a short review cadence so the system can stop if adoption weakens.",
            ],
            confidence=self._scenario_confidence(signal_balance, request.market_signals, request.social_signals),
            impact=0.85,
            horizon="10d",
            market_implications=[
                "A positive market signal can compound quickly if adoption remains stable.",
            ],
            social_implications=[
                "The best personas should reinforce the same message to reduce drift.",
            ],
            metadata={"keywords": keyword_pool[:5], "scenario_type": "adoption_cascade"},
        )

    def _baseline_scenario(self, request: MarketSocialBridgeRequest, keyword_pool: list[str]) -> BridgeScenario:
        title = f"Baseline coordination for {request.topic}"
        thesis = "Maintain a stable baseline and keep the decision loop short until stronger signals appear."
        return BridgeScenario(
            title=title,
            topic=request.topic,
            thesis=thesis,
            evidence=keyword_pool[:3],
            risks=["insufficient signal", "analysis paralysis"],
            actions=["Collect one more round of evidence.", "Hold the line on the least reversible choice."],
            confidence=0.55,
            impact=0.5,
            horizon="7d",
            market_implications=["No strong market bias yet."],
            social_implications=["No strong social bias yet."],
            metadata={"scenario_type": "baseline"},
        )

    def _score_bridge(self, profiles: list[PersonaProfile], judge_report: ScenarioJudgementReport) -> float:
        profile_signal = mean(profile.confidence for profile in profiles) if profiles else 0.0
        trust_signal = mean(profile.trust for profile in profiles) if profiles else 0.0
        scenario_signal = judge_report.average_score
        return round((profile_signal * 0.3) + (trust_signal * 0.2) + (scenario_signal * 0.5), 3)

    def _build_coordination_brief(
        self,
        request: MarketSocialBridgeRequest,
        profiles: list[PersonaProfile],
        best: BridgeScenario | None,
        judge_report: ScenarioJudgementReport,
    ) -> str:
        lead_profile = profiles[0] if profiles else None
        persona_brief = self.persona_helper.render_brief(
            lead_profile,
            topic=request.topic,
            objective=request.objective,
        ) if lead_profile else "No profiles available."
        best_text = best.thesis if best else "No scenario was selected."
        return (
            f"Bridge topic: {request.topic}\n"
            f"Selected verdict: {judge_report.verdict.value}\n"
            f"Best scenario: {best_text}\n"
            f"Lead profile:\n{persona_brief}"
        )

    def _build_recommendations(self, best: BridgeScenario | None, judge_report: ScenarioJudgementReport) -> list[str]:
        if not best:
            return ["Collect more signals before making a decision."]
        recommendations = list(best.actions)
        if judge_report.verdict != ScenarioVerdict.approve:
            recommendations.append("Review the scenario before full deployment.")
        return _dedupe(recommendations)[:6]

    def _signal_balance(self, market_signals: list[MarketSignal], social_signals: list[SocialSignal]) -> float:
        market_weight = sum(signal.weight for signal in market_signals)
        social_weight = sum(signal.weight for signal in social_signals)
        total = market_weight + social_weight
        if total <= 0:
            return 0.0
        return round((market_weight - social_weight) / total, 3)

    def _scenario_confidence(
        self,
        signal_balance: float,
        market_signals: list[MarketSignal],
        social_signals: list[SocialSignal],
    ) -> float:
        balance_penalty = 1.0 - min(1.0, abs(signal_balance))
        signal_density = min(1.0, (len(market_signals) + len(social_signals)) / 8.0)
        return round(max(0.25, min(0.95, 0.4 + (0.35 * signal_density) + (0.2 * balance_penalty))), 3)

    def _has_negative_trust_signal(self, social_signals: list[SocialSignal]) -> bool:
        return any(signal.sentiment == SocialSentiment.negative or signal.value < 0 for signal in social_signals)

    def _has_positive_growth_signal(
        self,
        market_signals: list[MarketSignal],
        social_signals: list[SocialSignal],
    ) -> bool:
        return any(signal.direction == SignalDirection.up or signal.value > 0 for signal in market_signals) and any(
            signal.sentiment == SocialSentiment.positive or signal.reach > 0.5 for signal in social_signals
        )

    def _keyword_pool(self, request: MarketSocialBridgeRequest, profiles: list[PersonaProfile]) -> list[str]:
        words: list[str] = []
        words.extend(_tokenize(request.topic))
        words.extend(_tokenize(request.objective))
        for signal in request.market_signals:
            words.extend(_tokenize(signal.name))
        for signal in request.social_signals:
            words.extend(_tokenize(signal.name))
        for profile in profiles:
            words.extend(profile.keywords[:3])
        return _dedupe(words)

    def _signal_names(self, signals: list[MarketSignal | SocialSignal]) -> list[str]:
        return [signal.name for signal in signals if signal.name]


def _tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", text.lower())


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
