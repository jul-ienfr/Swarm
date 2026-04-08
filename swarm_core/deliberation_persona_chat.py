from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import uuid4

from pydantic import BaseModel, Field

from .deliberation_interview import DeliberationInterviewTarget
from .persona_chat_helpers import PersonaChatHelper, PersonaChatRequest, PersonaChatRoundSummary, PersonaChatTurn
from .profile_generation_pipeline import PersonaProfile, ProfileRole, ProfileStance


DEFAULT_PERSONA_CHAT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "persona_chat"


class PersonaChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: f"chat_{uuid4().hex[:12]}")
    deliberation_id: str
    topic: str
    objective: str = ""
    target_id: str
    turns: list[PersonaChatTurn] = Field(default_factory=list)
    round_summaries: list[PersonaChatRoundSummary] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class DeliberationPersonaChatService:
    def __init__(self, *, output_dir: str | Path | None = None) -> None:
        self.output_dir = Path(output_dir or DEFAULT_PERSONA_CHAT_OUTPUT_DIR)
        self.helper = PersonaChatHelper()

    def start_or_continue(
        self,
        *,
        deliberation_id: str,
        topic: str,
        objective: str,
        target: DeliberationInterviewTarget,
        question: str,
        prior_turns: Iterable[PersonaChatTurn] | None = None,
        output_path: str | Path | None = None,
    ) -> PersonaChatSession:
        prior_turns = list(prior_turns or [])
        profile = _target_to_profile(target)
        request = PersonaChatRequest(
            topic=topic,
            objective=objective,
            profile=profile,
            round_index=len(prior_turns) + 1,
            question=question,
            prior_summary=prior_turns[-1].content if prior_turns else "",
        )
        turn = self.helper.draft_turn(request)
        turns = [*prior_turns, turn]
        summary = self.helper.summarize_round(turns[-3:], round_index=turn.round_index)
        session = PersonaChatSession(
            deliberation_id=deliberation_id,
            topic=topic,
            objective=objective,
            target_id=target.target_id,
            turns=turns,
            round_summaries=[summary],
            metadata={"target_type": target.target_type.value, "label": target.label},
        )
        if output_path is not None:
            self.save(session, output_path)
        return session

    def save(self, session: PersonaChatSession, path: str | Path | None = None) -> Path:
        target = Path(path or (self.output_dir / session.deliberation_id / f"{session.session_id}.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        return target

    def export_html(self, session: PersonaChatSession, path: str | Path | None = None) -> Path:
        target = Path(path or (self.output_dir / session.deliberation_id / f"{session.session_id}.html"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_session_html(session), encoding="utf-8")
        return target


def _target_to_profile(target: DeliberationInterviewTarget) -> PersonaProfile:
    role = ProfileRole.participant
    if "safety" in target.label.lower() or "guardian" in target.label.lower():
        role = ProfileRole.guardian
    stance = ProfileStance.support
    if target.target_type.value == "group":
        stance = ProfileStance.cautious
    elif target.target_type.value == "overview":
        stance = ProfileStance.governance
    return PersonaProfile(
        profile_id=target.target_id,
        label=target.label,
        role=role,
        stance=stance,
        confidence=0.7,
        trust=0.65,
        summary=target.description or target.label,
        evidence=[],
        keywords=[target.target_type.value, target.label],
    )


def _render_session_html(session: PersonaChatSession) -> str:
    turn_blocks = []
    for turn in session.turns:
        turn_blocks.append(
            "<section class='turn'>"
            f"<h2>Round {turn.round_index} · {turn.label}</h2>"
            f"<pre>{turn.content}</pre>"
            "</section>"
        )
    round_blocks = []
    for summary in session.round_summaries:
        round_blocks.append(
            "<section class='round-summary'>"
            f"<h3>Round {summary.round_index} summary</h3>"
            f"<p>{summary.summary}</p>"
            "</section>"
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Persona Chat Session</title>"
        "<style>"
        "body{font-family:system-ui, sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;background:#f8fafc;color:#111827;}"
        ".turn,.round-summary{background:white;border:1px solid #dbe4ee;border-radius:12px;padding:1rem;margin:1rem 0;box-shadow:0 4px 18px rgba(15,23,42,.05);}"
        "pre{white-space:pre-wrap;font:inherit;line-height:1.55;margin:0;}"
        "header{margin-bottom:2rem;}"
        "</style></head><body>"
        "<header>"
        f"<h1>Persona Chat · {session.target_id}</h1>"
        f"<p><strong>Deliberation:</strong> {session.deliberation_id}</p>"
        f"<p><strong>Topic:</strong> {session.topic}</p>"
        f"<p><strong>Objective:</strong> {session.objective}</p>"
        "</header>"
        f"{''.join(round_blocks)}"
        f"{''.join(turn_blocks)}"
        "</body></html>"
    )
