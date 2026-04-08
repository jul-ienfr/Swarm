from __future__ import annotations

import hashlib
import re
from enum import Enum
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ScenarioVerdict(str, Enum):
    approve = "approve"
    revise = "revise"
    reject = "reject"


class ScenarioCandidate(BaseModel):
    scenario_id: str = Field(default_factory=lambda: f"scenario_{uuid4().hex[:12]}")
    title: str
    topic: str = ""
    thesis: str
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    impact: float = 0.5
    horizon: str = "7d"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", "impact")
    @classmethod
    def _clamp_unit_interval(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class ScenarioAssessment(BaseModel):
    scenario_id: str
    verdict: ScenarioVerdict
    score: float
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioJudgementReport(BaseModel):
    judge_id: str = Field(default_factory=lambda: f"judge_{uuid4().hex[:10]}")
    topic: str = ""
    verdict: ScenarioVerdict = ScenarioVerdict.revise
    average_score: float = 0.0
    top_scenario_id: str | None = None
    assessments: list[ScenarioAssessment] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioJudgeConfig(BaseModel):
    min_approve_score: float = 0.7
    min_revise_score: float = 0.45
    max_candidates: int = 16

    @field_validator("min_approve_score", "min_revise_score")
    @classmethod
    def _validate_scores(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("max_candidates")
    @classmethod
    def _validate_max_candidates(cls, value: int) -> int:
        return max(1, int(value))


class ScenarioJudge:
    """
    Bounded, deterministic judge for scenario proposals.

    Intent:
    - keep the judge pure and local
    - score clarity, evidence, risk handling, and actionability
    - produce an explicit verdict that can be wired into deliberation flows
    """

    def __init__(self, *, config: ScenarioJudgeConfig | None = None) -> None:
        self.config = config or ScenarioJudgeConfig()

    def assess(self, candidate: ScenarioCandidate) -> ScenarioAssessment:
        factors = self._score_factors(candidate)
        score = round(sum(factors.values()) / len(factors), 3) if factors else 0.0
        verdict = self._verdict_for_score(score)
        strengths, gaps, recommendations = self._interpret_candidate(candidate, score)
        return ScenarioAssessment(
            scenario_id=candidate.scenario_id,
            verdict=verdict,
            score=score,
            strengths=strengths,
            gaps=gaps,
            recommended_changes=recommendations,
            factors=factors,
            metadata={
                "title": candidate.title,
                "topic": candidate.topic,
                "horizon": candidate.horizon,
                "hash": _stable_hash(candidate.model_dump(mode="json")),
            },
        )

    def judge(self, candidates: Iterable[ScenarioCandidate], *, topic: str = "") -> ScenarioJudgementReport:
        limited = list(candidates)[: self.config.max_candidates]
        assessments = [self.assess(candidate) for candidate in limited]
        if not assessments:
            return ScenarioJudgementReport(
                topic=topic,
                verdict=ScenarioVerdict.reject,
                summary="No scenario candidates were provided to the judge.",
            )

        ranked = sorted(assessments, key=lambda item: item.score, reverse=True)
        top = ranked[0]
        average_score = round(mean(item.score for item in ranked), 3)
        verdict = self._overall_verdict(top.score, average_score)
        summary = self._build_summary(topic=topic, top=top, average_score=average_score, total=len(ranked))
        return ScenarioJudgementReport(
            topic=topic,
            verdict=verdict,
            average_score=average_score,
            top_scenario_id=top.scenario_id,
            assessments=ranked,
            summary=summary,
            metadata={
                "candidate_count": len(ranked),
                "max_candidates": self.config.max_candidates,
            },
        )

    def _score_factors(self, candidate: ScenarioCandidate) -> dict[str, float]:
        title_tokens = _tokenize(candidate.title)
        thesis_tokens = _tokenize(candidate.thesis)
        evidence_count = len([item for item in candidate.evidence if item])
        risk_count = len([item for item in candidate.risks if item])
        action_count = len([item for item in candidate.actions if item])

        clarity = min(1.0, 0.25 + (0.1 if title_tokens else 0.0) + min(0.3, len(thesis_tokens) / 50.0))
        evidence = min(1.0, evidence_count / 4.0)
        risk_handling = 0.0
        if risk_count and action_count:
            risk_handling = min(1.0, 0.3 + min(0.4, action_count / 5.0) + min(0.3, risk_count / 5.0))
        elif action_count:
            risk_handling = 0.5
        actionability = min(1.0, 0.2 + min(0.5, action_count / 4.0) + (0.1 if "should" in thesis_tokens or "must" in thesis_tokens else 0.0))
        confidence = max(0.0, min(1.0, candidate.confidence))
        impact = max(0.0, min(1.0, candidate.impact))

        return {
            "clarity": round(clarity, 3),
            "evidence": round(evidence, 3),
            "risk_handling": round(risk_handling, 3),
            "actionability": round(actionability, 3),
            "confidence": round(confidence, 3),
            "impact": round(impact, 3),
        }

    def _interpret_candidate(self, candidate: ScenarioCandidate, score: float) -> tuple[list[str], list[str], list[str]]:
        strengths: list[str] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if candidate.title.strip():
            strengths.append("Title is explicit.")
        else:
            gaps.append("Missing title.")
            recommendations.append("Add a concise scenario title.")

        if len(candidate.thesis.split()) >= 12:
            strengths.append("Thesis has sufficient substance.")
        else:
            gaps.append("Thesis is too short.")
            recommendations.append("Expand the thesis with concrete causal detail.")

        if candidate.evidence:
            strengths.append("Evidence references are present.")
        else:
            gaps.append("No evidence references.")
            recommendations.append("Attach at least one supporting evidence item.")

        if candidate.actions:
            strengths.append("Action list is present.")
        else:
            gaps.append("No explicit actions.")
            recommendations.append("Add at least one next action.")

        if candidate.risks:
            strengths.append("Risk surface is explicit.")
        else:
            gaps.append("No risk articulation.")
            recommendations.append("Describe the main risks and mitigation path.")

        if score < self.config.min_revise_score:
            recommendations.append("Rework the scenario before deliberation.")

        return strengths, gaps, recommendations

    def _verdict_for_score(self, score: float) -> ScenarioVerdict:
        if score >= self.config.min_approve_score:
            return ScenarioVerdict.approve
        if score >= self.config.min_revise_score:
            return ScenarioVerdict.revise
        return ScenarioVerdict.reject

    @staticmethod
    def _overall_verdict(top_score: float, average_score: float) -> ScenarioVerdict:
        if top_score >= 0.8 and average_score >= 0.7:
            return ScenarioVerdict.approve
        if top_score >= 0.5:
            return ScenarioVerdict.revise
        return ScenarioVerdict.reject

    @staticmethod
    def _build_summary(*, topic: str, top: ScenarioAssessment, average_score: float, total: int) -> str:
        base = f"Judged {total} scenario candidate(s)"
        if topic:
            base = f"{base} for topic '{topic}'"
        return (
            f"{base}. Top scenario {top.scenario_id} scored {top.score:.2f}; "
            f"mean score was {average_score:.2f}; verdict={top.verdict.value}."
        )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _stable_hash(payload: Any) -> str:
    encoded = repr(payload).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]
