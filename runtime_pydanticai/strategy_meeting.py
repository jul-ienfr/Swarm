from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openclaw_client import OpenClawClient

from .factory import RuntimeAvailabilityError, load_runtime_model_config, run_structured_agent
from .models import (
    MeetingRoundSummary,
    MeetingSynthesisDraft,
    MeetingTurnDraft,
    RuntimeBackend,
    RuntimeFallbackPolicy,
)


@dataclass(slots=True)
class _LegacyMeetingTransport:
    config_path: str = "config.yaml"
    client: OpenClawClient | Any | None = None
    injected_client: bool = False

    def __post_init__(self) -> None:
        self.injected_client = self.client is not None
        if self.client is None:
            self.client = OpenClawClient(config_path=self.config_path)

    def generate_turn(
        self,
        *,
        participant: str,
        round_index: int,
        phase: str,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
        critique_focus: str | None = None,
    ) -> MeetingTurnDraft:
        instruction = _build_participant_prompt(
            participant=participant,
            round_index=round_index,
            phase=phase,
            topic=topic,
            objective=objective,
            participants=participants,
            prior_summary=prior_summary,
            critique_focus=critique_focus,
        )
        result = self.client.chat_with_agent(
            worker_name=participant,
            agent_id=participant,
            messages=[{"role": "user", "content": instruction}],
        )
        content = str(result.get("content", "")).strip()
        if not content and self.injected_client:
            # Test/integration clients can still provide a generic chat-completion fallback.
            fallback_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are participating in a structured strategy meeting.\n"
                        f"Adopt the point of view of agent '{participant}'.\n"
                        "Return concise, concrete analysis."
                    ),
                },
                {"role": "user", "content": instruction},
            ]
            fallback_result = self.client.chat_with_escalation(
                worker_name=f"strategy_meeting_{participant}",
                messages=fallback_messages,
                preferred_tier="tier3_paid",
                model_name="claude-sonnet-4-6",
            )
            content = str(fallback_result.get("content", "")).strip()
        if not content:
            return _fallback_turn_draft(
                participant=participant,
                phase=phase,
                topic=topic,
                objective=objective,
                prior_summary=prior_summary,
                critique_focus=critique_focus,
            )
        parsed = _parse_turn_content(content)
        return parsed if parsed.thesis else MeetingTurnDraft(thesis=content, closing_note=None)

    def summarize_round(
        self,
        *,
        topic: str,
        objective: str,
        round_index: int,
        phase: str,
        turns: list[MeetingTurnDraft],
        prior_summary: str,
    ) -> MeetingRoundSummary:
        transcript_block = _format_turns(turns)
        if not self.injected_client:
            top_options = [turn.thesis for turn in turns[:3]]
            risks = [risk for turn in turns for risk in turn.key_risks][:5]
            disagreements = [item for turn in turns for item in turn.disagreements][:5]
            summary = _legacy_round_summary_text(
                topic=topic,
                objective=objective,
                phase=phase,
                prior_summary=prior_summary,
                top_options=top_options,
                risks=risks,
                disagreements=disagreements,
                transcript_block=transcript_block,
            )
            return MeetingRoundSummary(
                summary=summary,
                top_options=top_options,
                risks=risks,
                unresolved_disagreements=disagreements,
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a neutral meeting facilitator. Summarize the discussion into a compact briefing "
                    "that can be fed into the next round. Keep it factual.\n"
                    "If the topic is quantitative or comparative, carry forward explicit probability ranges,\n"
                    "gain-vs-no-trade tradeoffs, and the main invalidation test."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n"
                    f"Objective: {objective}\n"
                    f"Round: {round_index}\n"
                    f"Phase: {phase}\n"
                    f"Prior summary:\n{prior_summary or 'None'}\n\n"
                    f"Round transcript:\n{transcript_block}\n\n"
                    "Produce a concise synthesis with the top options, risks, unresolved disagreements,"
                    " and any explicit probability or expected-value signals."
                ),
            },
        ]
        result = self.client.chat_with_escalation(
            worker_name="meeting_facilitator",
            messages=messages,
            preferred_tier="tier3_paid",
            model_name="claude-sonnet-4-6",
        )
        if not result.get("success"):
            return MeetingRoundSummary(summary=transcript_block[:4000])
        return MeetingRoundSummary(summary=str(result.get("content", "")).strip())

    def synthesize_meeting(
        self,
        *,
        topic: str,
        objective: str,
        participants: list[str],
        phase: str,
        turns: list[MeetingTurnDraft],
        summary: str,
    ) -> MeetingSynthesisDraft:
        transcript_block = _format_turns(turns)
        if not self.injected_client:
            consensus = [turn.thesis for turn in turns[:3]]
            dissent = [item for turn in turns for item in turn.disagreements][:5]
            next_actions = []
            for turn in turns:
                next_actions.extend(turn.recommended_actions)
            next_actions = list(dict.fromkeys(next_actions))[:5]
            profile = _meeting_intent_profile(topic=topic, objective=objective, summary=summary)
            if profile["quantitative"] or profile["comparative"]:
                consensus = _augment_quantitative_consensus(consensus, topic=topic, objective=objective)
                dissent = _augment_quantitative_dissent(dissent, topic=topic, objective=objective)
                next_actions = _augment_quantitative_next_actions(next_actions, topic=topic, objective=objective)
            return MeetingSynthesisDraft(
                strategy=_legacy_synthesis_strategy_text(topic=topic, objective=objective, summary=summary),
                consensus_points=consensus,
                dissent_points=dissent,
                next_actions=next_actions or ["Define rollout gates", "Define rollback criteria"],
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the chair of a strategy meeting. Produce a final synthesis in JSON with keys "
                    "`strategy`, `consensus_points`, `dissent_points`, and `next_actions`.\n"
                    "If the topic is quantitative or comparative, make the decision explicit: separate forecast alpha,\n"
                    "arbitrage alpha, execution alpha, and no-trade. Include the validation gate in next_actions."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n"
                    f"Objective: {objective}\n"
                    f"Participants: {', '.join(participants)}\n"
                    f"Phase: {phase}\n"
                    f"Final round summary:\n{summary}\n\n"
                    f"Full transcript:\n{transcript_block}\n\n"
                    "When relevant, include explicit probability or expected-value signals in the final strategy.\n"
                    "Return only JSON."
                ),
            },
        ]
        result = self.client.chat_with_escalation(
            worker_name="meeting_chair",
            messages=messages,
            preferred_tier="tier3_paid",
            model_name="claude-sonnet-4-6",
        )
        if not result.get("success"):
            return MeetingSynthesisDraft(strategy=summary or "No synthesis available.")

        raw = str(result.get("content", "")).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(raw)
            return MeetingSynthesisDraft.model_validate(parsed)
        except Exception:
            return MeetingSynthesisDraft(strategy=str(result.get("content", "")).strip())


class PydanticAIStrategyMeetingRuntime:
    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        fallback_policy: RuntimeFallbackPolicy = RuntimeFallbackPolicy.on_error,
        model_name: str | None = None,
        legacy_client: OpenClawClient | Any | None = None,
    ) -> None:
        self.config_path = config_path
        self.fallback_policy = fallback_policy
        self._config = load_runtime_model_config(config_path=config_path, model_name=model_name)
        self._legacy = _LegacyMeetingTransport(config_path=config_path, client=legacy_client)
        self.max_structured_attempts = 2
        self.base_backoff_seconds = 0.15
        self.max_backoff_seconds = 0.75
        self.last_runtime_used = RuntimeBackend.pydanticai
        self.last_fallback_used = False
        self.last_fallback_mode: str | None = None
        self.last_error: str | None = None
        self.last_error_category: str | None = None
        self.last_error_retryable: bool | None = None
        self.last_attempt_count: int = 0
        self.last_retry_count: int = 0
        self.last_retry_reasons: list[str] = []
        self.last_backoff_schedule: list[dict[str, Any]] = []
        self.last_backoff_total_seconds: float = 0.0
        self.last_retry_budget_exhausted: bool = False
        self.last_immediate_fallback: bool = False

    @property
    def runtime_used(self) -> RuntimeBackend:
        return self.last_runtime_used

    def available(self) -> bool:
        return self._config.base_url is not None

    def generate_turn(
        self,
        *,
        participant: str,
        round_index: int,
        phase: str,
        topic: str,
        objective: str,
        participants: list[str],
        prior_summary: str,
        critique_focus: str | None = None,
    ) -> MeetingTurnDraft:
        return self._run_structured(
            output_type=MeetingTurnDraft,
            agent_name=f"strategy-turn-{participant}",
            system_prompt=(
                "You are participating in a structured strategy meeting.\n"
                "Return a concise structured analysis with a thesis, recommended actions, risks, disagreements, "
                "and an optional closing note."
            ),
            user_prompt=_build_participant_prompt(
                participant=participant,
                round_index=round_index,
                phase=phase,
                topic=topic,
                objective=objective,
                participants=participants,
                prior_summary=prior_summary,
                critique_focus=critique_focus,
            ),
            fallback=lambda: self._legacy.generate_turn(
                participant=participant,
                round_index=round_index,
                phase=phase,
                topic=topic,
                objective=objective,
                participants=participants,
                prior_summary=prior_summary,
                critique_focus=critique_focus,
            ),
        )

    def summarize_round(
        self,
        *,
        topic: str,
        objective: str,
        round_index: int,
        phase: str,
        turns: list[MeetingTurnDraft],
        prior_summary: str,
    ) -> MeetingRoundSummary:
        return self._run_structured(
            output_type=MeetingRoundSummary,
            agent_name="strategy-summary",
            system_prompt=(
                "You are a neutral meeting facilitator. Summarize the discussion into a compact briefing "
                "that can be fed into the next round. Keep it factual."
            ),
            user_prompt=_build_summary_prompt(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                turns=turns,
                prior_summary=prior_summary,
            ),
            fallback=lambda: self._legacy.summarize_round(
                topic=topic,
                objective=objective,
                round_index=round_index,
                phase=phase,
                turns=turns,
                prior_summary=prior_summary,
            ),
        )

    def synthesize_meeting(
        self,
        *,
        topic: str,
        objective: str,
        participants: list[str],
        phase: str,
        turns: list[MeetingTurnDraft],
        summary: str,
    ) -> MeetingSynthesisDraft:
        return self._run_structured(
            output_type=MeetingSynthesisDraft,
            agent_name="strategy-chair",
            system_prompt=(
                "You are the chair of a strategy meeting. Produce a final synthesis in JSON with keys "
                "`strategy`, `consensus_points`, `dissent_points`, and `next_actions`."
            ),
            user_prompt=_build_synthesis_prompt(
                topic=topic,
                objective=objective,
                participants=participants,
                phase=phase,
                turns=turns,
                summary=summary,
            ),
            fallback=lambda: self._legacy.synthesize_meeting(
                topic=topic,
                objective=objective,
                participants=participants,
                phase=phase,
                turns=turns,
                summary=summary,
            ),
        )

    def _run_structured(self, *, output_type, agent_name: str, system_prompt: str, user_prompt: str, fallback):
        self.last_attempt_count = 0
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_backoff_schedule = []
        self.last_backoff_total_seconds = 0.0
        self.last_retry_budget_exhausted = False
        self.last_immediate_fallback = False
        self.last_fallback_mode = None
        self.last_error_retryable = None
        if self.fallback_policy == RuntimeFallbackPolicy.always:
            self.last_runtime_used = RuntimeBackend.legacy
            self.last_fallback_used = True
            self.last_error = None
            self.last_error_category = None
            self.last_error_retryable = None
            self.last_attempt_count = 1
            self.last_fallback_mode = "policy_always"
            self.last_immediate_fallback = True
            return fallback()

        max_attempts = max(1, int(self.max_structured_attempts))
        for attempt_index in range(1, max_attempts + 1):
            self.last_attempt_count = attempt_index
            try:
                result = run_structured_agent(
                    output_type=output_type,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    agent_name=agent_name,
                    config=self._config,
                )
                self.last_runtime_used = result.runtime_used
                self.last_fallback_used = result.fallback_used
                self.last_error = None
                self.last_error_category = None
                self.last_error_retryable = None
                self.last_fallback_mode = "structured_success"
                return result.output
            except Exception as exc:
                error_category = _classify_runtime_error(exc)
                self.last_error = str(exc)
                self.last_error_category = error_category
                retryable = _is_retryable_runtime_error(error_category)
                self.last_error_retryable = retryable
                if retryable and attempt_index < max_attempts:
                    delay_seconds = _structured_backoff_delay(
                        attempt_index=attempt_index,
                        base_backoff_seconds=self.base_backoff_seconds,
                        max_backoff_seconds=self.max_backoff_seconds,
                    )
                    self.last_retry_count += 1
                    self.last_retry_reasons.append(error_category)
                    self.last_backoff_schedule.append(
                        {
                            "attempt": attempt_index,
                            "delay_seconds": delay_seconds,
                            "error_category": error_category,
                            "retryable": True,
                        }
                    )
                    self.last_backoff_total_seconds += delay_seconds
                    time.sleep(delay_seconds)
                    continue
                if self.fallback_policy == RuntimeFallbackPolicy.never:
                    raise
                self.last_runtime_used = RuntimeBackend.legacy
                self.last_fallback_used = True
                self.last_fallback_mode = "retry_budget_exhausted" if retryable else "immediate_non_retryable"
                self.last_retry_budget_exhausted = bool(retryable and attempt_index >= max_attempts)
                self.last_immediate_fallback = not retryable
                return fallback()
        if self.fallback_policy == RuntimeFallbackPolicy.never:
            raise RuntimeAvailabilityError("structured runtime attempts exhausted")
        self.last_runtime_used = RuntimeBackend.legacy
        self.last_fallback_used = True
        self.last_fallback_mode = "retry_budget_exhausted"
        self.last_retry_budget_exhausted = True
        return fallback()


def _classify_runtime_error(exc: Exception) -> str:
    if isinstance(exc, RuntimeAvailabilityError):
        return "availability_error"
    message = str(exc).strip().lower()
    if not message:
        return "unexpected_error"
    if "timeout" in message or "timed out" in message:
        return "timeout_error"
    if "connection" in message or "connect" in message or "refused" in message or "reset" in message:
        return "connection_error"
    if "schema" in message or "json" in message or "validation" in message:
        return "schema_error"
    if "unavailable" in message or "not configured" in message:
        return "availability_error"
    return "unexpected_error"


def _is_retryable_runtime_error(category: str) -> bool:
    return category in {"timeout_error", "connection_error", "availability_error"}


def _structured_backoff_delay(
    *,
    attempt_index: int,
    base_backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    delay_seconds = max(0.0, float(base_backoff_seconds) * max(1, int(attempt_index)))
    return min(delay_seconds, max_backoff_seconds)


def _build_participant_prompt(
    *,
    participant: str,
    round_index: int,
    phase: str,
    topic: str,
    objective: str,
    participants: list[str],
    prior_summary: str,
    critique_focus: str | None = None,
) -> str:
    summary_block = prior_summary or "No prior summary yet. Give an independent first-pass strategy."
    phase_block = _phase_guidance(phase)
    critique_focus_block = f"Critique focus: {critique_focus}\n" if critique_focus and phase.strip().lower() == "critique" else ""
    quantitative_block = _quantitative_guidance_block(
        topic=topic,
        objective=objective,
        phase=phase,
        prior_summary=prior_summary,
        critique_focus=critique_focus,
    )
    return (
        f"You are participating in a structured strategy meeting as agent '{participant}'.\n"
        f"Topic: {topic}\n"
        f"Objective: {objective}\n"
        f"Participants: {', '.join(participants)}\n"
        f"Round: {round_index}\n"
        f"Phase: {phase}\n"
        f"{critique_focus_block}"
        f"Current discussion summary:\n{summary_block}\n\n"
        f"{phase_block}\n"
        f"{quantitative_block}"
        "Respond with concise, concrete analysis.\n"
        "If the topic is a gain, probability, arbitrage, or comparison question, separate no-trade,"
        " forecast alpha, arbitrage alpha, and execution alpha."
    )


def _build_summary_prompt(
    *,
    topic: str,
    objective: str,
    round_index: int,
    phase: str,
    turns: list[MeetingTurnDraft],
    prior_summary: str,
) -> str:
    transcript_block = _format_turns(turns)
    phase_block = _phase_guidance(phase)
    quantitative_block = _quantitative_guidance_block(
        topic=topic,
        objective=objective,
        phase=phase,
        prior_summary=prior_summary,
        transcript=transcript_block,
    )
    return (
        f"Topic: {topic}\n"
        f"Objective: {objective}\n"
        f"Round: {round_index}\n"
        f"Phase: {phase}\n"
        f"Prior summary:\n{prior_summary or 'None'}\n\n"
        f"Round transcript:\n{transcript_block}\n\n"
        f"{phase_block}\n"
        f"{quantitative_block}"
        "Produce a concise synthesis with the top options, risks, unresolved disagreements,"
        " and any explicit probability or expected-value signals."
    )


def _build_synthesis_prompt(
    *,
    topic: str,
    objective: str,
    participants: list[str],
    phase: str,
    turns: list[MeetingTurnDraft],
    summary: str,
) -> str:
    transcript_block = _format_turns(turns)
    phase_block = _phase_guidance(phase)
    quantitative_block = _quantitative_guidance_block(
        topic=topic,
        objective=objective,
        phase=phase,
        summary=summary,
        transcript=transcript_block,
    )
    return (
        f"Topic: {topic}\n"
        f"Objective: {objective}\n"
        f"Participants: {', '.join(participants)}\n"
        f"Phase: {phase}\n"
        f"Final round summary:\n{summary}\n\n"
        f"Full transcript:\n{transcript_block}\n\n"
        f"{phase_block}\n"
        f"{quantitative_block}"
        "Return only JSON."
    )


def _phase_guidance(phase: str) -> str:
    phase_key = phase.strip().lower()
    if phase_key == "critique":
        return (
            "Phase guidance: challenge the current line. Name at least one concrete disagreement, failure mode, "
            "or missing assumption."
        )
    if phase_key == "synthesis":
        return (
            "Phase guidance: converge to a decision. State the tradeoffs, the recommended path, and the rollout gates."
        )
    return (
        "Phase guidance: give an independent first pass. Focus on your own judgment, evidence, and initial risks."
    )


def _meeting_intent_profile(
    *,
    topic: str,
    objective: str,
    prior_summary: str = "",
    critique_focus: str | None = None,
    summary: str = "",
    transcript: str = "",
) -> dict[str, Any]:
    corpus = " ".join(
        part
        for part in (
            topic,
            objective,
            prior_summary,
            critique_focus or "",
            summary,
            transcript,
        )
        if part
    ).lower()
    quantitative_terms = (
        "probability",
        "gain",
        "profit",
        "expected value",
        "edge",
        "confidence",
        "calibration",
        "percentage",
        "percent",
        "%",
        "win rate",
        "arbitrage",
        "spread",
        "prediction market",
        "market",
    )
    comparative_terms = (
        "compare",
        "comparison",
        "versus",
        " vs ",
        "better",
        "best",
        "ranking",
        "tradeoff",
        "baseline",
        "no-trade",
        "no trade",
    )
    quantitative = any(term in corpus for term in quantitative_terms)
    comparative = any(term in corpus for term in comparative_terms)
    terms = []
    for term in (*quantitative_terms, *comparative_terms):
        if term.strip() and term in corpus and term not in terms:
            terms.append(term)
    return {
        "quantitative": quantitative,
        "comparative": comparative,
        "keywords": terms[:8],
    }


def _quantitative_guidance_block(
    *,
    topic: str,
    objective: str,
    phase: str,
    prior_summary: str = "",
    critique_focus: str | None = None,
    summary: str = "",
    transcript: str = "",
) -> str:
    profile = _meeting_intent_profile(
        topic=topic,
        objective=objective,
        prior_summary=prior_summary,
        critique_focus=critique_focus,
        summary=summary,
        transcript=transcript,
    )
    if not profile["quantitative"] and not profile["comparative"]:
        return ""
    phase_key = phase.strip().lower()
    lines = [
        "Quantitative guidance: treat this as a gain/probability/comparison problem, not just a qualitative discussion.",
        "Separate forecast alpha from arbitrage alpha, execution alpha, and no-trade.",
        "State a probability range or expected-value view whenever you mention an edge or a candidate path.",
        "Compare at least two candidate paths directly and say which one wins on evidence, executable gain, or risk control.",
    ]
    if phase_key == "critique":
        lines.append("Critique the weakest assumption and name the metric that would invalidate the edge.")
    elif phase_key == "synthesis":
        lines.append("Close with the preferred path, the rejection condition, and the next validation gate.")
    else:
        lines.append("Name the current best path, the strongest alternative, and the condition under which no-trade wins.")
    if profile["keywords"]:
        lines.append(f"Detected focus terms: {', '.join(profile['keywords'])}.")
    if critique_focus:
        lines.append(f"Critique focus: {critique_focus}.")
    return "\n".join(lines) + "\n"


def _fallback_turn_draft(
    *,
    participant: str,
    phase: str,
    topic: str,
    objective: str,
    prior_summary: str,
    critique_focus: str | None = None,
) -> MeetingTurnDraft:
    phase_key = phase.strip().lower()
    closing_note = (
        f"Objective reminder: {objective}. "
        f"Prior context: {prior_summary or 'first pass, no prior summary'}."
    )
    profile = _meeting_intent_profile(
        topic=topic,
        objective=objective,
        prior_summary=prior_summary,
        critique_focus=critique_focus,
    )
    if profile["quantitative"] or profile["comparative"]:
        if phase_key == "critique":
            return MeetingTurnDraft(
                thesis=(
                    f"As {participant}, challenge '{topic}' by asking whether the edge survives costs, slippage, "
                    "and calibration drift."
                ),
                recommended_actions=[
                    "Estimate the gain probability for each candidate path.",
                    "Identify the single metric that would falsify the edge.",
                    "Compare prediction alpha, arbitrage alpha, and no-trade explicitly.",
                ],
                key_risks=[
                    "Overfitting can create a false positive edge.",
                    "Execution friction can erase a paper gain.",
                    "A spread or forecast signal may not generalize out of sample.",
                ],
                disagreements=[
                    (
                        f"Need a sharper comparison between the candidate paths for '{topic}', especially around {critique_focus}."
                        if critique_focus
                        else "Need a sharper comparison between prediction, arbitrage, and no-trade."
                    )
                ],
                closing_note=closing_note,
            )
        if phase_key == "synthesis":
            return MeetingTurnDraft(
                thesis=(
                    f"As {participant}, converge on the path with the best validated gain probability for '{topic}', "
                    "and default to no-trade until the edge is executable after fees and slippage."
                ),
                recommended_actions=[
                    "Lock the validation gate for forecast and arbitrage claims.",
                    "Require a paper or shadow proof before any live commitment.",
                    "Record the expected-value delta against the no-trade baseline.",
                ],
                key_risks=[
                    "A promising alpha can disappear once execution and compliance are included.",
                    "Premature live deployment can turn a weak edge into a loss.",
                ],
                disagreements=[
                    "The remaining disagreement is whether the main value comes from prediction, arbitrage, or abstention.",
                ],
                closing_note=closing_note,
            )
        return MeetingTurnDraft(
            thesis=(
                f"As {participant}, treat '{topic}' as a three-way choice between no-trade, prediction alpha, and "
                "execution or arbitrage capture until one path proves a real edge."
            ),
            recommended_actions=[
                "Estimate probability and expected value for each candidate path.",
                "Separate signal quality from execution quality.",
                "Use the no-trade baseline as the default comparator.",
            ],
            key_risks=[
                "The apparent edge may be too small to survive fees or slippage.",
                "A forecast win rate does not guarantee executable gain.",
            ],
            disagreements=[
                "The open question is whether the dominant gain comes from prediction, arbitrage, or filtering.",
            ],
            closing_note=closing_note,
        )
    if phase_key == "critique":
        return MeetingTurnDraft(
            thesis=(
                f"As {participant}, challenge the current strategy for '{topic}' and surface the weak assumptions."
            ),
            recommended_actions=[
                "List the strongest counterargument.",
                "Define what would invalidate the current plan.",
            ],
            key_risks=[
                "Hidden assumptions are likely to slip through.",
                "The current approach may be too optimistic on reversibility.",
            ],
            disagreements=[
                (
                    f"Need a stronger critique of the current rollout path with focus on {critique_focus}."
                    if critique_focus
                    else "Need a stronger critique of the current rollout path."
                )
            ],
            closing_note=closing_note,
        )
    if phase_key == "synthesis":
        return MeetingTurnDraft(
            thesis=(
                f"As {participant}, converge on a decision for '{topic}' with explicit gates, rollback criteria, "
                "and a clear no-trade fallback if the edge is not proven."
            ),
            recommended_actions=[
                "Pick the staged path with explicit gates.",
                "Assign owners for reliability, adoption, and rollback monitoring.",
                "Record what would prove the edge real versus illusory.",
            ],
            key_risks=[
                "Skipping the final decision gate would reintroduce ambiguity.",
                "Treating an unproven edge as executable can create false confidence.",
            ],
            disagreements=["Earlier objections should be resolved before execution."],
            closing_note=closing_note,
        )
    return MeetingTurnDraft(
        thesis=(
            f"As {participant}, prefer a staged strategy for '{topic}' that protects reliability, keeps observability strong, "
            "and limits irreversible changes while checking whether there is any real gain edge."
        ),
        recommended_actions=[
            "Roll out in stages with explicit gates.",
            "Track reliability and adoption separately.",
            "Compare the proposed path against a no-trade or wait-and-measure baseline.",
        ],
        key_risks=[
            "Moving too quickly without rollback criteria.",
            "Under-instrumenting the rollout.",
            "A paper edge can vanish if the validation gate is too weak.",
        ],
        disagreements=[
            "Need a clear answer on whether the value is in prediction, arbitrage, or filtering.",
        ],
        closing_note=closing_note,
    )


def _legacy_round_summary_text(
    *,
    topic: str,
    objective: str,
    phase: str,
    prior_summary: str,
    top_options: list[str],
    risks: list[str],
    disagreements: list[str],
    transcript_block: str,
) -> str:
    profile = _meeting_intent_profile(topic=topic, objective=objective, prior_summary=prior_summary, transcript=transcript_block)
    if profile["quantitative"] or profile["comparative"]:
        lens = (
            f"Decision lens: compare forecast alpha, arbitrage alpha, execution alpha, and no-trade for '{topic}'. "
            "Carry forward explicit probability ranges and the main invalidation test."
        )
    else:
        lens = f"Decision lens: keep the discussion grounded on the objective for '{topic}' and preserve the best supported path."
    phase_line = f"Phase focus: {phase.strip().lower()}."
    summary_lines = [lens, phase_line]
    if prior_summary:
        summary_lines.append(f"Prior summary: {prior_summary}")
    if top_options:
        summary_lines.append("Top options:")
        summary_lines.extend(f"- {item}" for item in top_options[:3])
    if risks:
        summary_lines.append("Key risks:")
        summary_lines.extend(f"- {item}" for item in risks[:3])
    if disagreements:
        summary_lines.append("Open disagreements:")
        summary_lines.extend(f"- {item}" for item in disagreements[:3])
    return "\n".join(summary_lines).strip() or transcript_block[:4000]


def _legacy_synthesis_strategy_text(*, topic: str, objective: str, summary: str) -> str:
    profile = _meeting_intent_profile(topic=topic, objective=objective, summary=summary)
    if profile["quantitative"] or profile["comparative"]:
        return (
            f"Choose the path with the best validated gain probability for '{topic}', and default to no-trade "
            "until the edge is executable after costs, slippage, and calibration checks."
        )
    return summary or "Adopt a staged, observable strategy with explicit rollback gates."


def _augment_quantitative_next_actions(next_actions: list[str], *, topic: str, objective: str) -> list[str]:
    defaults = [
        "Validate the edge in paper or shadow before any live commitment.",
        f"Quantify the gain probability for each candidate path on '{topic}'.",
        "Compare the forecast alpha, arbitrage alpha, and execution alpha separately.",
        "Stress-test the result for fees, slippage, stale data, and fill risk.",
    ]
    combined = list(dict.fromkeys([*next_actions, *defaults]))
    return combined[:5]


def _augment_quantitative_consensus(consensus: list[str], *, topic: str, objective: str) -> list[str]:
    defaults = [
        f"The system should not chase an unvalidated edge on '{topic}'.",
        "The best path must survive out-of-sample checks and execution costs.",
    ]
    combined = list(dict.fromkeys([*consensus, *defaults]))
    return combined[:5]


def _augment_quantitative_dissent(dissent: list[str], *, topic: str, objective: str) -> list[str]:
    defaults = [
        "The main open question is whether prediction, arbitrage, or abstention has the best expected value.",
        "A paper edge may disappear once execution friction is included.",
    ]
    combined = list(dict.fromkeys([*dissent, *defaults]))
    return combined[:5]


def _parse_turn_content(content: str) -> MeetingTurnDraft:
    text = content.strip()
    if not text:
        return MeetingTurnDraft(thesis="")

    section_order = ("thesis", "recommended_actions", "key_risks", "disagreements", "closing_note")
    sections: dict[str, list[str]] = {name: [] for name in section_order}
    current_section: str | None = None
    saw_section = False

    def append_line(section: str, line: str) -> None:
        if line:
            sections[section].append(line)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        matched_section = None
        for candidate in section_order:
            label = candidate.replace("_", " ")
            if lower.startswith(f"{label}:"):
                matched_section = candidate
                remainder = line[len(label) + 1 :].strip()
                saw_section = True
                current_section = matched_section
                if remainder:
                    append_line(matched_section, remainder)
                break
        if matched_section is not None:
            continue

        if line.startswith(("- ", "* ", "• ")):
            target = current_section or "thesis"
            append_line(target, line[2:].strip())
            continue

        target = current_section or "thesis"
        append_line(target, line)

    thesis = " ".join(sections["thesis"]).strip()
    recommended_actions = sections["recommended_actions"]
    key_risks = sections["key_risks"]
    disagreements = sections["disagreements"]
    closing_note = " ".join(sections["closing_note"]).strip() or None

    if not saw_section and not any([recommended_actions, key_risks, disagreements, closing_note]):
        return MeetingTurnDraft(thesis=text, closing_note=None)

    return MeetingTurnDraft(
        thesis=thesis or text,
        recommended_actions=recommended_actions,
        key_risks=key_risks,
        disagreements=disagreements,
        closing_note=closing_note,
    )


def _format_turns(turns: list[MeetingTurnDraft]) -> str:
    lines: list[str] = []
    for turn in turns:
        lines.append(f"{turn.thesis}")
        if turn.recommended_actions:
            lines.extend(f"- {action}" for action in turn.recommended_actions)
        if turn.key_risks:
            lines.extend(f"- risk: {risk}" for risk in turn.key_risks)
        if turn.disagreements:
            lines.extend(f"- disagreement: {item}" for item in turn.disagreements)
        if turn.closing_note:
            lines.append(f"- note: {turn.closing_note}")
    return "\n".join(lines).strip()
