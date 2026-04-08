from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .profile_generation_pipeline_v0 import PersonaProfile, ProfileStance


class PersonaChatRequest(BaseModel):
    topic: str
    objective: str = ""
    profile: PersonaProfile
    round_index: int = 0
    question: str = ""
    prior_summary: str = ""
    max_words: int = 180
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_words")
    @classmethod
    def _validate_max_words(cls, value: int) -> int:
        return max(40, int(value))


class PersonaChatTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: f"turn_{uuid4().hex[:12]}")
    round_index: int = 0
    profile_id: str
    label: str
    content: str
    thesis: str
    recommended_actions: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    closing_note: str = ""
    confidence: float = 0.0
    trust: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PersonaChatRoundSummary(BaseModel):
    round_index: int
    summary: str
    consensus_points: list[str] = Field(default_factory=list)
    dissent_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersonaChatHelper:
    """
    Bounded persona-chat helper.

    Intent:
    - format a persona brief
    - draft a structured turn without calling an external model
    - produce a lightweight round summary for deliberation wiring
    """

    def render_brief(self, profile: PersonaProfile, *, topic: str = "", objective: str = "") -> str:
        parts = [
            f"Persona: {profile.label}",
            f"Role: {profile.role.value}",
            f"Stance: {profile.stance.value}",
            f"Confidence: {profile.confidence:.2f}",
            f"Trust: {profile.trust:.2f}",
        ]
        if topic:
            parts.append(f"Topic: {topic}")
        if objective:
            parts.append(f"Objective: {objective}")
        if profile.summary:
            parts.append(f"Summary: {profile.summary}")
        if profile.keywords:
            parts.append(f"Keywords: {', '.join(profile.keywords[:6])}")
        return "\n".join(parts)

    def build_prompt(self, request: PersonaChatRequest) -> str:
        brief = self.render_brief(request.profile, topic=request.topic, objective=request.objective)
        return (
            f"{brief}\n"
            f"Round: {request.round_index}\n"
            f"Question: {request.question or request.topic}\n"
            f"Prior summary: {request.prior_summary or 'none'}\n\n"
            "Answer in four sections:\n"
            "1. Thesis\n"
            "2. Recommended actions\n"
            "3. Key risks\n"
            "4. Closing note"
        )

    def draft_turn(self, request: PersonaChatRequest) -> PersonaChatTurn:
        stance = request.profile.stance
        thesis = self._build_thesis(request.profile, request.topic, request.objective, request.question)
        recommended_actions = self._build_actions(request.profile, request.topic)
        key_risks = self._build_risks(request.profile, request.topic, request.prior_summary)
        disagreements = self._build_disagreements(request.profile, request.question)
        closing_note = self._build_closing_note(request.profile)
        content = self._compose_turn_content(thesis, recommended_actions, key_risks, disagreements, closing_note)
        content = _trim_words(content, request.max_words)
        return PersonaChatTurn(
            round_index=request.round_index,
            profile_id=request.profile.profile_id,
            label=request.profile.label,
            content=content,
            thesis=thesis,
            recommended_actions=recommended_actions,
            key_risks=key_risks,
            disagreements=disagreements,
            closing_note=closing_note,
            confidence=request.profile.confidence,
            trust=request.profile.trust,
            metadata={
                "topic": request.topic,
                "objective": request.objective,
                "stance": stance.value,
                "question": request.question,
            },
        )

    def summarize_round(self, turns: Iterable[PersonaChatTurn], *, round_index: int) -> PersonaChatRoundSummary:
        turn_list = list(turns)
        if not turn_list:
            return PersonaChatRoundSummary(
                round_index=round_index,
                summary="No persona turns were provided for this round.",
            )

        action_counter = Counter(action for turn in turn_list for action in turn.recommended_actions if action)
        risk_counter = Counter(risk for turn in turn_list for risk in turn.key_risks if risk)
        disagreement_counter = Counter(disagreement for turn in turn_list for disagreement in turn.disagreements if disagreement)

        consensus_points = [item for item, _count in action_counter.most_common(4)]
        dissent_points = [item for item, _count in disagreement_counter.most_common(4)]
        open_questions = [item for item, _count in risk_counter.most_common(4)]
        summary = (
            f"Round {round_index} gathered {len(turn_list)} persona turn(s). "
            f"Consensus centered on: {', '.join(consensus_points) if consensus_points else 'no shared actions'}. "
            f"Open questions: {', '.join(open_questions) if open_questions else 'none'}."
        )
        return PersonaChatRoundSummary(
            round_index=round_index,
            summary=summary,
            consensus_points=consensus_points,
            dissent_points=dissent_points,
            open_questions=open_questions,
            metadata={
                "turn_count": len(turn_list),
                "unique_actions": len(action_counter),
                "unique_risks": len(risk_counter),
            },
        )

    def _build_thesis(
        self,
        profile: PersonaProfile,
        topic: str,
        objective: str,
        question: str,
    ) -> str:
        focus = question or objective or topic
        if profile.stance == ProfileStance.cautious:
            return f"I recommend a careful path for {focus}, because the downside risks could compound quickly."
        if profile.stance == ProfileStance.challenge:
            return f"I would challenge the current assumption set around {focus} and test the weak points first."
        if profile.stance == ProfileStance.expansion:
            return f"We should expand on {focus} decisively, while sequencing the rollout to capture upside."
        if profile.stance == ProfileStance.governance:
            return f"{focus} needs stronger guardrails, decision rights, and explicit escalation rules."
        if profile.stance == ProfileStance.efficiency:
            return f"We should optimize {focus} for throughput, cost control, and operational simplicity."
        return f"The best path for {focus} is to proceed with the strongest evidence and stay close to the signals."

    def _build_actions(self, profile: PersonaProfile, topic: str) -> list[str]:
        actions: list[str] = []
        keywords = profile.keywords[:3] or [topic]
        for keyword in keywords:
            if keyword:
                actions.append(f"Validate the signal around {keyword}.")
        if profile.stance in {ProfileStance.governance, ProfileStance.cautious}:
            actions.append("Add a rollback gate before broad rollout.")
        if profile.stance == ProfileStance.expansion:
            actions.append("Stage a controlled expansion with a fast feedback loop.")
        if profile.stance == ProfileStance.efficiency:
            actions.append("Remove one redundant step from the workflow.")
        return _dedupe(actions)[:4]

    def _build_risks(self, profile: PersonaProfile, topic: str, prior_summary: str) -> list[str]:
        risks = list(profile.evidence[:2])
        if prior_summary:
            risks.append(f"Prior summary may understate uncertainty around {topic}.")
        if profile.stance == ProfileStance.challenge:
            risks.append("Consensus may be masking a structural weakness.")
        return _dedupe(risks)[:4]

    def _build_disagreements(self, profile: PersonaProfile, question: str) -> list[str]:
        if profile.stance in {ProfileStance.challenge, ProfileStance.cautious}:
            return [f"Question whether '{question or 'the proposal'}' is assuming too much."]
        return []

    def _build_closing_note(self, profile: PersonaProfile) -> str:
        return f"Confidence {profile.confidence:.2f}; trust {profile.trust:.2f}; {profile.label} is ready for the next round."

    @staticmethod
    def _compose_turn_content(
        thesis: str,
        recommended_actions: list[str],
        key_risks: list[str],
        disagreements: list[str],
        closing_note: str,
    ) -> str:
        lines = [
            f"Thesis: {thesis}",
            "Recommended actions:",
            *(f"- {action}" for action in recommended_actions or ["No direct action yet."]),
            "Key risks:",
            *(f"- {risk}" for risk in key_risks or ["No new risk identified."]),
        ]
        if disagreements:
            lines.extend(["Disagreements:", *(f"- {item}" for item in disagreements)])
        lines.append(f"Closing note: {closing_note}")
        return "\n".join(lines)


def _trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip() + " ..."


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
