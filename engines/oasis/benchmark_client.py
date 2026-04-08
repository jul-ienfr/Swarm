"""
Deterministic local surrogate for OASIS-backed runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OasisRunStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None
    message: str | None = None


@dataclass(slots=True)
class OasisRunResult:
    summary: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = "oasis-surrogate-1.0"


class OASISBenchmarkClient:
    def __init__(self, artifact_scheme: str = "engine://oasis-surrogate") -> None:
        self._artifact_scheme = artifact_scheme.rstrip("/")
        self._runs: dict[str, Any] = {}
        self._counter = 0

    def create_run(self, config) -> str:
        self._counter += 1
        engine_run_id = f"oasis_bench_{self._counter}"
        self._runs[engine_run_id] = config
        return engine_run_id

    def get_run_status(self, engine_run_id: str) -> OasisRunStatus:
        if engine_run_id not in self._runs:
            raise KeyError(f"Unknown engine run id: {engine_run_id}")
        return OasisRunStatus(
            status="COMPLETED",
            progress_pct=100.0,
            current_step=3,
            message="OASIS surrogate completed.",
        )

    def get_result(self, engine_run_id: str) -> OasisRunResult:
        config = self._runs[engine_run_id]
        score = self._compute_score(config)
        platform = getattr(config, "platform", "reddit")
        summary = f"OASIS surrogate completed {engine_run_id} on {platform} with engagement_index={score:.2f}."
        artifacts = [
            {
                "name": "surrogate-report",
                "type": "report",
                "path": "report.json",
                "uri": f"{self._artifact_scheme}/{engine_run_id}/report.json",
                "content_type": "application/json",
            }
        ]
        scenarios = [
            {
                "scenario_id": "platform_reaction",
                "confidence": round(min(0.95, max(0.05, score)), 2),
                "description": f"Population response estimated for {platform}.",
            }
        ]
        risks = []
        recommendations = []
        if score < 0.6:
            risks.append({"risk": "polarization", "detail": "The social graph shows weak consensus formation."})
            recommendations.append(
                {
                    "action": "increase_cluster_signal",
                    "detail": "Use hierarchical deliberation or stronger evidence grounding.",
                }
            )
        else:
            recommendations.append(
                {
                    "action": "keep_strategy",
                    "detail": "The current strategy appears stable under the surrogate.",
                }
            )

        return OasisRunResult(
            summary=summary,
            metrics={
                "engagement_index": round(score, 3),
                "consensus_index": round(min(0.95, score + 0.07), 3),
                "polarization_index": round(max(0.05, 1.0 - score), 3),
            },
            artifacts=artifacts,
            scenarios=scenarios,
            risks=risks,
            recommendations=recommendations,
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self._runs.pop(engine_run_id, None)

    def _compute_score(self, config) -> float:
        score = 0.46
        agent_count = getattr(config, "agent_count", 0) or 0
        if agent_count <= 64:
            score += 0.08
        elif agent_count <= 250:
            score += 0.05

        platform = str(getattr(config, "platform", "reddit")).lower()
        if platform == "reddit":
            score += 0.05
        elif platform == "twitter":
            score += 0.04

        documents = getattr(config, "extra", {}).get("documents", []) or []
        if documents:
            score += min(0.08, 0.02 * len(documents))

        agent_profiles = getattr(config, "agent_profiles", []) or []
        if agent_profiles:
            score += min(0.1, 0.01 * len(agent_profiles))

        interventions = getattr(config, "extra", {}).get("interventions", []) or []
        if interventions:
            score += min(0.06, 0.02 * len(interventions))

        return max(0.05, min(0.97, score))
