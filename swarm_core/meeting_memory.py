from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _as_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _preview(value: str, *, limit: int = 220) -> str:
    text = _as_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_text_block(text: str, *, limit: int) -> str:
    cleaned = _as_text(text)
    if len(cleaned) <= limit:
        return cleaned
    head_limit = max(0, limit - 160)
    head = cleaned[:head_limit].rstrip()
    tail = cleaned[-120:].lstrip()
    return "\n".join(part for part in (head, "[...compacted...]", tail) if part)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _render_round_report(round_report: dict[str, Any]) -> str:
    if not isinstance(round_report, dict):
        return _preview(round_report, limit=260)
    lines = [
        f"Round {round_report.get('round_index', '?')} ({_as_text(round_report.get('phase')) or 'unknown'})",
    ]
    if round_report.get("summary"):
        lines.append(f"Summary: {_preview(round_report.get('summary'), limit=260)}")
    if round_report.get("strategy"):
        lines.append(f"Strategy: {_preview(round_report.get('strategy'), limit=260)}")
    for label in ("consensus_points", "dissent_points", "next_actions"):
        items = _coerce_list(round_report.get(label))
        if items:
            lines.append(f"{label.replace('_', ' ').title()}: {' | '.join(items[:3])}")
    persistent = round_report.get("persistent")
    if isinstance(persistent, dict):
        for label in ("options", "risks", "disagreements"):
            items = _coerce_list(persistent.get(label))
            if items:
                lines.append(f"Persistent {label}: {' | '.join(items[:2])}")
    return "\n".join(lines)


def _coerce_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def _extract_turn_draft(turn: Any) -> dict[str, Any]:
    metadata = getattr(turn, "metadata", None)
    if isinstance(metadata, dict):
        draft = metadata.get("draft")
        if isinstance(draft, dict):
            return draft

    thesis = _as_text(getattr(turn, "content", None))
    return {
        "thesis": thesis,
        "recommended_actions": [],
        "key_risks": [],
        "disagreements": [],
        "closing_note": None,
    }


@dataclass(slots=True)
class MeetingMemoryTurnView:
    speaker: str
    phase: str
    thesis: str
    recommended_actions: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    closing_note: str | None = None

    @classmethod
    def from_turn(cls, turn: Any) -> "MeetingMemoryTurnView":
        draft = _extract_turn_draft(turn)
        return cls(
            speaker=_as_text(getattr(turn, "speaker", None)) or "agent",
            phase=_as_text(getattr(turn, "phase", None)) or "independent",
            thesis=_as_text(draft.get("thesis")),
            recommended_actions=_coerce_list(draft.get("recommended_actions")),
            key_risks=_coerce_list(draft.get("key_risks")),
            disagreements=_coerce_list(draft.get("disagreements")),
            closing_note=_as_text(draft.get("closing_note")) or None,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "phase": self.phase,
            "thesis": self.thesis,
            "thesis_preview": _preview(self.thesis, limit=240),
            "recommended_actions": list(self.recommended_actions[:3]),
            "key_risks": list(self.key_risks[:3]),
            "disagreements": list(self.disagreements[:3]),
            "closing_note": self.closing_note,
            "action_count": len(self.recommended_actions),
            "risk_count": len(self.key_risks),
            "disagreement_count": len(self.disagreements),
        }


@dataclass(slots=True)
class MeetingRoundRecord:
    round_index: int
    phase: str
    turns: list[MeetingMemoryTurnView] = field(default_factory=list)
    round_summary: str = ""
    compacted_summary: str | None = None
    structured_report: dict[str, Any] = field(default_factory=dict)

    def compact(self) -> str:
        options = _dedupe([turn.thesis for turn in self.turns], limit=2)
        risks = _dedupe([risk for turn in self.turns for risk in turn.key_risks], limit=2)
        disagreements = _dedupe([item for turn in self.turns for item in turn.disagreements], limit=2)
        lines = [f"Round {self.round_index} ({self.phase})"]
        if options:
            lines.append(f"- options: {' | '.join(options)}")
        if risks:
            lines.append(f"- risks: {' | '.join(risks)}")
        if disagreements:
            lines.append(f"- disagreements: {' | '.join(disagreements)}")
        if not options and not risks and not disagreements:
            lines.append(f"- summary: {_preview(self.round_summary, limit=180) or 'no notable change'}")
        self.compacted_summary = "\n".join(lines)
        return self.compacted_summary

    def participant_names(self) -> list[str]:
        return _dedupe([turn.speaker for turn in self.turns])

    def snapshot(self) -> dict[str, Any]:
        turn_snapshots = [turn.snapshot() for turn in self.turns]
        phase_counts = dict(Counter(turn.phase for turn in self.turns if turn.phase))
        return {
            "round_index": self.round_index,
            "phase": self.phase,
            "turn_count": len(self.turns),
            "participants": self.participant_names(),
            "participant_count": len(self.participant_names()),
            "phase_counts": phase_counts,
            "round_summary": self.round_summary,
            "round_summary_preview": _preview(self.round_summary, limit=240),
            "compacted_summary": self.compacted_summary or self.compact(),
            "structured_report": _json_safe(dict(self.structured_report)),
            "turns": turn_snapshots,
        }

    def preflight_text(self, *, max_chars: int = 1800) -> str:
        lines = [
            f"Round {self.round_index} ({self.phase})",
            f"Participants: {', '.join(self.participant_names()) or 'none'}",
            f"Summary: {_preview(self.round_summary, limit=360) or 'no notable change'}",
        ]
        if self.structured_report:
            lines.append(_render_round_report(self.structured_report))
        for turn in self.turns[:6]:
            lines.append(f"- {turn.speaker}: {turn.thesis or 'no thesis'}")
            if turn.recommended_actions:
                lines.append(f"  Actions: {' | '.join(turn.recommended_actions[:2])}")
            if turn.key_risks:
                lines.append(f"  Risks: {' | '.join(turn.key_risks[:2])}")
            if turn.disagreements:
                lines.append(f"  Disagreements: {' | '.join(turn.disagreements[:2])}")
        return _compact_text_block("\n".join(lines), limit=max_chars)

    def full_text(self) -> str:
        lines = [f"Round {self.round_index} ({self.phase})"]
        lines.append(f"Participants: {', '.join(self.participant_names()) or 'none'}")
        if self.round_summary:
            lines.append(f"Summary: {_preview(self.round_summary, limit=320)}")
        for turn in self.turns:
            lines.append(f"- {turn.speaker}: {turn.thesis or 'no thesis'}")
            if turn.recommended_actions:
                lines.append(f"  Actions: {' | '.join(turn.recommended_actions[:3])}")
            if turn.key_risks:
                lines.append(f"  Risks: {' | '.join(turn.key_risks[:3])}")
            if turn.disagreements:
                lines.append(f"  Disagreements: {' | '.join(turn.disagreements[:3])}")
        return "\n".join(lines)


@dataclass(slots=True)
class MeetingParticipantBelief:
    participant: str
    thesis_history: list[str] = field(default_factory=list)
    action_watchlist: list[str] = field(default_factory=list)
    risk_watchlist: list[str] = field(default_factory=list)
    disagreement_watchlist: list[str] = field(default_factory=list)

    def update(self, turn: MeetingMemoryTurnView) -> None:
        if turn.thesis:
            self.thesis_history = _dedupe([turn.thesis, *self.thesis_history], limit=6)
        self.action_watchlist = _dedupe([*turn.recommended_actions, *self.action_watchlist], limit=6)
        self.risk_watchlist = _dedupe([*turn.key_risks, *self.risk_watchlist], limit=6)
        self.disagreement_watchlist = _dedupe([*turn.disagreements, *self.disagreement_watchlist], limit=6)

    def to_prompt_block(self, *, phase: str) -> str:
        phase_role = "critic" if phase == "critique" else "participant"
        lines = [
            "[Participant belief lens]",
            f"Agent: {self.participant}",
            f"Role in this phase: {phase_role}",
            f"- Recent thesis: {self.thesis_history[0] if self.thesis_history else 'none yet'}",
            f"- Persistent actions: {' | '.join(self.action_watchlist[:3]) if self.action_watchlist else 'none yet'}",
            f"- Persistent risks: {' | '.join(self.risk_watchlist[:3]) if self.risk_watchlist else 'none yet'}",
            f"- Open disagreements: {' | '.join(self.disagreement_watchlist[:3]) if self.disagreement_watchlist else 'none yet'}",
        ]
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        return {
            "participant": self.participant,
            "thesis_history": list(self.thesis_history[:6]),
            "action_watchlist": list(self.action_watchlist[:6]),
            "risk_watchlist": list(self.risk_watchlist[:6]),
            "disagreement_watchlist": list(self.disagreement_watchlist[:6]),
        }


class MeetingMemory:
    """Sliding-window meeting memory inspired by MiroShark round memory and belief tracking."""

    def __init__(self, *, topic: str, objective: str) -> None:
        self.topic = _as_text(topic)
        self.objective = _as_text(objective)
        self._rounds: list[MeetingRoundRecord] = []
        self._beliefs: dict[str, MeetingParticipantBelief] = {}
        self._ancient_summary: list[str] = []

    def record_round(
        self,
        *,
        round_index: int,
        phase: str,
        turns: list[Any],
        round_summary: str,
        round_report: dict[str, Any] | None = None,
    ) -> None:
        views = [MeetingMemoryTurnView.from_turn(turn) for turn in turns]
        record = MeetingRoundRecord(
            round_index=round_index,
            phase=phase,
            turns=views,
            round_summary=_as_text(round_summary),
            structured_report=_json_safe(dict(round_report or {})),
        )
        self._rounds.append(record)
        for view in views:
            belief = self._beliefs.setdefault(view.speaker, MeetingParticipantBelief(participant=view.speaker))
            belief.update(view)
        self._compact_ancient_history()

    def build_global_context(self, *, current_round: int) -> str:
        sections = [
            "[Meeting objective]",
            f"Topic: {self.topic}",
            f"Objective: {self.objective}",
        ]
        if self._ancient_summary:
            sections.append("[Ancient memory]")
            sections.extend(self._ancient_summary)

        previous_rounds = [record for record in self._rounds if record.round_index < current_round]
        if previous_rounds:
            recent = previous_rounds[-2:]
            sections.append("[Recent history]")
            for record in recent[:-1]:
                sections.append(record.compacted_summary or record.compact())
            sections.append("[Previous round - full detail]")
            sections.append(recent[-1].full_text())
        else:
            sections.append("[Recent history]")
            sections.append("No prior round memory yet.")

        return "\n".join(section for section in sections if section).strip()

    def build_participant_context(
        self,
        *,
        participant: str,
        phase: str,
        current_round: int,
    ) -> str:
        sections = [self.build_global_context(current_round=current_round)]
        belief = self._beliefs.get(participant)
        if belief is not None:
            sections.append(belief.to_prompt_block(phase=phase))
        return "\n\n".join(section for section in sections if section).strip()

    def build_preflight_text(
        self,
        *,
        current_round: int,
        max_chars: int = 1800,
        include_belief_lenses: bool = True,
    ) -> str:
        sections = [
            "[Preflight brief]",
            f"Topic: {self.topic}",
            f"Objective: {self.objective}",
            f"Current round: {current_round}",
        ]
        if self._ancient_summary:
            sections.append("[Compressed older rounds]")
            sections.extend(self._ancient_summary[:4])
        previous_rounds = [record for record in self._rounds if record.round_index < current_round]
        if previous_rounds:
            sections.append("[Recent round memory]")
            for record in previous_rounds[-2:]:
                sections.append(record.preflight_text(max_chars=650))
                sections.append(record.compacted_summary or record.compact())
        else:
            sections.append("[Recent round memory]")
            sections.append("No prior round memory yet.")
        if include_belief_lenses and self._beliefs:
            sections.append("[Participant belief lenses]")
            for participant, belief in list(self._beliefs.items())[:5]:
                sections.append(
                    "\n".join(
                        [
                            f"Agent: {participant}",
                            f"- Recent thesis: {belief.thesis_history[0] if belief.thesis_history else 'none yet'}",
                            f"- Persistent actions: {' | '.join(belief.action_watchlist[:2]) if belief.action_watchlist else 'none yet'}",
                            f"- Persistent risks: {' | '.join(belief.risk_watchlist[:2]) if belief.risk_watchlist else 'none yet'}",
                            f"- Open disagreements: {' | '.join(belief.disagreement_watchlist[:2]) if belief.disagreement_watchlist else 'none yet'}",
                        ]
                    )
                )
        return _compact_text_block("\n\n".join(section for section in sections if section).strip(), limit=max_chars)

    def build_round_snapshot(self, *, round_index: int) -> dict[str, Any]:
        record = next((item for item in self._rounds if item.round_index == round_index), None)
        if record is None:
            return {
                "topic": self.topic,
                "objective": self.objective,
                "round_index": round_index,
                "found": False,
                "participant_count": len(self._beliefs),
                "ancient_summary": list(self._ancient_summary),
            }
        snapshot = record.snapshot()
        snapshot.update(
            {
                "topic": self.topic,
                "objective": self.objective,
                "found": True,
                "participant_count": len(snapshot.get("participants", [])),
                "preflight_text": record.preflight_text(max_chars=1600),
                "belief_lens": {
                    participant: belief.snapshot() for participant, belief in self._beliefs.items()
                },
            }
        )
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "objective": self.objective,
            "round_count": len(self._rounds),
            "participant_count": len(self._beliefs),
            "ancient_summary": list(self._ancient_summary),
            "preflight_text": self.build_preflight_text(current_round=len(self._rounds) + 1),
            "recent_rounds": [
                {
                    "round_index": record.round_index,
                    "phase": record.phase,
                    "summary": record.round_summary,
                    "compacted_summary": record.compacted_summary,
                    "participant_count": len(record.participant_names()),
                    "participant_trace": [turn.snapshot() for turn in record.turns],
                }
                for record in self._rounds[-3:]
            ],
            "round_snapshots": [
                self.build_round_snapshot(round_index=record.round_index)
                for record in self._rounds[-3:]
            ],
            "beliefs": {
                participant: {
                    "recent_thesis": belief.thesis_history[0] if belief.thesis_history else None,
                    "actions": belief.action_watchlist[:3],
                    "risks": belief.risk_watchlist[:3],
                    "disagreements": belief.disagreement_watchlist[:3],
                }
                for participant, belief in self._beliefs.items()
            },
        }

    def round_snapshot(self, *, round_index: int) -> dict[str, Any]:
        return self.build_round_snapshot(round_index=round_index)

    def preflight_text(self, *, current_round: int, max_chars: int = 1800) -> str:
        return self.build_preflight_text(current_round=current_round, max_chars=max_chars)

    def _compact_ancient_history(self) -> None:
        if len(self._rounds) <= 3:
            return
        eligible = self._rounds[:-2]
        if not eligible:
            return
        self._ancient_summary = [record.compacted_summary or record.compact() for record in eligible[-6:]]


class MeetingEventLogger:
    """JSONL event logger inspired by MiroShark report agent logs."""

    def __init__(self, *, output_dir: str | Path, meeting_id: str) -> None:
        self.output_dir = Path(output_dir)
        self.meeting_id = meeting_id
        self.log_path = self.output_dir / f"{meeting_id}.agent_log.jsonl"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._sequence = 0

    def log(
        self,
        *,
        action: str,
        stage: str,
        details: dict[str, Any],
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        self._sequence += 1
        payload = {
            "event_id": f"evt_{uuid4().hex[:12]}",
            "timestamp": _utc_now_iso(),
            "sequence": self._sequence,
            "meeting_id": self.meeting_id,
            "event_type": action,
            "action": action,
            "stage": stage,
            "details": _json_safe(details),
        }
        if snapshot is not None:
            payload["snapshot"] = _json_safe(snapshot)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def log_turn(self, *, participant: str, round_index: int, phase: str, content: str, metadata: dict[str, Any]) -> None:
        snapshot = {
            "participant": participant,
            "round_index": round_index,
            "phase": phase,
            "content_preview": _preview(content, limit=240),
            "metadata_keys": sorted(metadata.keys()),
        }
        self.log(
            action="meeting_turn",
            stage="running",
            details={
                "participant": participant,
                "round_index": round_index,
                "phase": phase,
                "content": content,
                "metadata": metadata,
            },
            snapshot=snapshot,
        )

    def log_round_summary(self, *, round_index: int, phase: str, summary: str) -> None:
        snapshot = {
            "round_index": round_index,
            "phase": phase,
            "summary_preview": _preview(summary, limit=240),
        }
        self.log(
            action="round_summary",
            stage="running",
            details={
                "round_index": round_index,
                "phase": phase,
                "summary": summary,
            },
            snapshot=snapshot,
        )

    def log_round_snapshot(self, *, round_snapshot: dict[str, Any]) -> None:
        self.log(
            action="round_snapshot",
            stage="running",
            details=dict(round_snapshot),
            snapshot={
                "round_index": round_snapshot.get("round_index"),
                "phase": round_snapshot.get("phase"),
                "participant_count": round_snapshot.get("participant_count"),
                "turn_count": round_snapshot.get("turn_count"),
            },
        )

    def log_preflight_context(
        self,
        *,
        current_round: int,
        context: str,
        snapshot: dict[str, Any],
    ) -> None:
        self.log(
            action="preflight_context",
            stage="running",
            details={
                "current_round": current_round,
                "context": context,
            },
            snapshot={
                "current_round": current_round,
                "context_preview": _preview(context, limit=260),
                "snapshot": snapshot,
            },
        )

    def log_final_synthesis(self, *, strategy: str, consensus_points: list[str], dissent_points: list[str], next_actions: list[str]) -> None:
        self.log(
            action="meeting_synthesis",
            stage="completed",
            details={
                "strategy": strategy,
                "consensus_points": consensus_points,
                "dissent_points": dissent_points,
                "next_actions": next_actions,
            },
            snapshot={
                "strategy_preview": _preview(strategy, limit=240),
                "consensus_count": len(consensus_points),
                "dissent_count": len(dissent_points),
                "next_action_count": len(next_actions),
            },
        )

    def log_meeting_report(self, *, report: dict[str, Any]) -> None:
        self.log(
            action="meeting_report",
            stage="completed",
            details=dict(report),
            snapshot={
                "round_count": len(report.get("round_reports", []) or []),
                "strategy_preview": _preview(str(report.get("strategy") or ""), limit=220),
                "consensus_count": len(report.get("consensus_points", []) or []),
                "dissent_count": len(report.get("dissent_points", []) or []),
                "next_action_count": len(report.get("next_actions", []) or []),
            },
        )
