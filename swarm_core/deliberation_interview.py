from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .belief_state import BeliefGroupSummary, BeliefState
from .deliberation import DeliberationResult, load_deliberation_result
from .graph_store import GraphStore


class DeliberationInterviewTargetType(str, Enum):
    overview = "overview"
    agent = "agent"
    group = "group"


class DeliberationInterviewTarget(BaseModel):
    target_id: str
    target_type: DeliberationInterviewTargetType
    label: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationInterviewResponse(BaseModel):
    deliberation_id: str
    target_id: str
    target_type: DeliberationInterviewTargetType
    question: str
    answer: str
    references: list[str] = Field(default_factory=list)
    stance: str | None = None
    confidence: float | None = None
    trust: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def list_deliberation_targets(
    deliberation_id: str,
    *,
    output_dir: str | Path | None = None,
) -> list[DeliberationInterviewTarget]:
    result = load_deliberation_result(deliberation_id, output_dir=output_dir)
    targets: list[DeliberationInterviewTarget] = [
        DeliberationInterviewTarget(
            target_id="overview",
            target_type=DeliberationInterviewTargetType.overview,
            label="Run overview",
            description="High-level explanation of the deliberation outcome.",
            metadata={"mode": result.mode.value, "status": result.status.value},
        )
    ]
    for summary in result.belief_group_summaries:
        group_id = summary.group_id or "ungrouped"
        targets.append(
            DeliberationInterviewTarget(
                target_id=f"group:{group_id}",
                target_type=DeliberationInterviewTargetType.group,
                label=group_id,
                description=f"Belief group with {summary.agent_count} agents.",
                metadata={
                    "agent_count": summary.agent_count,
                    "dominant_stance": summary.dominant_stance,
                    "average_confidence": summary.average_confidence,
                    "average_trust": summary.average_trust,
                },
            )
        )
    for state in result.belief_states:
        targets.append(
            DeliberationInterviewTarget(
                target_id=state.agent_id,
                target_type=DeliberationInterviewTargetType.agent,
                label=state.agent_id,
                description=f"Belief agent in {state.group_id or 'no_group'}.",
                metadata={
                    "group_id": state.group_id,
                    "stance": state.stance,
                    "confidence": state.confidence,
                    "trust": state.trust,
                },
            )
        )
    return targets


def interview_deliberation_sync(
    deliberation_id: str,
    *,
    question: str,
    target_id: str | None = None,
    output_dir: str | Path | None = None,
) -> DeliberationInterviewResponse:
    result = load_deliberation_result(deliberation_id, output_dir=output_dir)
    resolved_target = _resolve_target(result, target_id)
    if resolved_target["type"] == DeliberationInterviewTargetType.agent:
        state = resolved_target["value"]
        return _answer_agent_question(result, state, question)
    if resolved_target["type"] == DeliberationInterviewTargetType.group:
        summary = resolved_target["value"]
        return _answer_group_question(result, summary, question)
    return _answer_overview_question(result, question)


def _resolve_target(
    result: DeliberationResult,
    target_id: str | None,
) -> dict[str, Any]:
    if not target_id or target_id == "overview":
        return {"type": DeliberationInterviewTargetType.overview, "value": None}
    if target_id.startswith("group:"):
        group_id = target_id.split(":", 1)[1]
        for summary in result.belief_group_summaries:
            if (summary.group_id or "ungrouped") == group_id:
                return {"type": DeliberationInterviewTargetType.group, "value": summary}
    for summary in result.belief_group_summaries:
        if (summary.group_id or "ungrouped") == target_id:
            return {"type": DeliberationInterviewTargetType.group, "value": summary}
    for state in result.belief_states:
        if state.agent_id == target_id:
            return {"type": DeliberationInterviewTargetType.agent, "value": state}
    return {"type": DeliberationInterviewTargetType.overview, "value": None}


def _answer_agent_question(
    result: DeliberationResult,
    state: BeliefState,
    question: str,
) -> DeliberationInterviewResponse:
    graph_context = _graph_neighbors(result, state.agent_id)
    memory_lines = state.memory_window[:5]
    answer = (
        f"Agent {state.agent_id} currently leans '{state.stance}' with confidence {state.confidence:.2f} "
        f"and trust {state.trust:.2f}. "
        f"It belongs to group {state.group_id or 'ungrouped'}. "
        f"The most salient memories are: {', '.join(memory_lines) if memory_lines else 'no retained memories'}. "
        f"For the question '{question}', this suggests the agent would emphasize continuity with those retained signals."
    )
    references = [result.summary] if result.summary else []
    references.extend(memory_lines)
    references.extend(graph_context)
    return DeliberationInterviewResponse(
        deliberation_id=result.deliberation_id,
        target_id=state.agent_id,
        target_type=DeliberationInterviewTargetType.agent,
        question=question,
        answer=answer,
        references=[item for item in references if item],
        stance=state.stance,
        confidence=state.confidence,
        trust=state.trust,
        metadata={"group_id": state.group_id, "graph_neighbors": graph_context},
    )


def _answer_group_question(
    result: DeliberationResult,
    summary: BeliefGroupSummary,
    question: str,
) -> DeliberationInterviewResponse:
    group_id = summary.group_id or "ungrouped"
    answer = (
        f"Group {group_id} contains {summary.agent_count} agents and is dominated by the stance "
        f"'{summary.dominant_stance or 'unknown'}'. "
        f"Average confidence is {summary.average_confidence:.2f} and average trust is {summary.average_trust:.2f}. "
        f"For the question '{question}', the most likely group-level answer is shaped by these stance counts: "
        f"{_render_stance_counts(summary)}."
    )
    return DeliberationInterviewResponse(
        deliberation_id=result.deliberation_id,
        target_id=f"group:{group_id}",
        target_type=DeliberationInterviewTargetType.group,
        question=question,
        answer=answer,
        references=[result.summary] if result.summary else [],
        metadata={
            "dominant_stance": summary.dominant_stance,
            "agent_count": summary.agent_count,
            "stance_counts": summary.stance_counts,
        },
    )


def _answer_overview_question(
    result: DeliberationResult,
    question: str,
) -> DeliberationInterviewResponse:
    group_ids = [summary.group_id or "ungrouped" for summary in result.belief_group_summaries]
    answer = (
        f"For the question '{question}', the run-level answer is: {result.final_strategy or result.summary or 'no summary available'}. "
        f"The deliberation finished in mode {result.mode.value} with status {result.status.value}. "
        f"Confidence is {result.confidence_level:.2f}. "
        f"Observed groups: {', '.join(group_ids) if group_ids else 'none'}. "
        f"Top recommendations: {_render_items(result.next_actions or result.recommendations)}."
    )
    references = [result.summary, result.final_strategy]
    references.extend(result.consensus_points[:3])
    references.extend(result.dissent_points[:3])
    return DeliberationInterviewResponse(
        deliberation_id=result.deliberation_id,
        target_id="overview",
        target_type=DeliberationInterviewTargetType.overview,
        question=question,
        answer=answer,
        references=[item for item in references if item],
        metadata={
            "mode": result.mode.value,
            "status": result.status.value,
            "engine_used": result.engine_used,
            "runtime_used": result.runtime_used,
            "group_count": len(result.belief_group_summaries),
        },
    )


def _graph_neighbors(result: DeliberationResult, node_id: str) -> list[str]:
    if not result.graph_path:
        return []
    graph_path = Path(result.graph_path)
    if not graph_path.exists():
        return []
    store = GraphStore.load(graph_path)
    return [node.label for node in store.neighbors(node_id)[:5]]


def _render_stance_counts(summary: BeliefGroupSummary) -> str:
    if not summary.stance_counts:
        return "no stance distribution"
    return ", ".join(f"{stance}={count}" for stance, count in sorted(summary.stance_counts.items()))


def _render_items(items: list[Any], limit: int = 3) -> str:
    rendered: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            rendered.append(item.get("action") or item.get("detail") or str(item))
        else:
            rendered.append(str(item))
    return ", ".join(rendered) if rendered else "none"
