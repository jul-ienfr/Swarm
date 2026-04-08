"""
Explicit surrogate backend for AgentSociety adapter runs.

This client is useful for unit tests and deliberate offline development mode,
but it is no longer the default production path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BenchmarkRunStatus:
    status: str
    progress_pct: float | None = None
    current_step: int | None = None
    message: str | None = None


@dataclass(slots=True)
class BenchmarkRunResult:
    summary: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = "surrogate-1.0"


class AgentSocietyBenchmarkClient:
    """
    Deterministic local simulation surrogate for harness and adapter tests.

    The goal is not to impersonate full AgentSociety semantics; it provides
    completed normalized runs so orchestration, benchmarks, and keep/revert
    logic can operate without a live engine deployment.
    """

    def __init__(self, artifact_scheme: str = "engine://agentsociety-surrogate") -> None:
        self._artifact_scheme = artifact_scheme.rstrip("/")
        self._runs: dict[str, Any] = {}
        self._counter = 0

    def create_run(self, config) -> str:
        self._counter += 1
        engine_run_id = f"as_bench_{self._counter}"
        self._runs[engine_run_id] = config
        return engine_run_id

    def get_run_status(self, engine_run_id: str) -> BenchmarkRunStatus:
        if engine_run_id not in self._runs:
            raise KeyError(f"Unknown engine run id: {engine_run_id}")
        return BenchmarkRunStatus(
            status="COMPLETED",
            progress_pct=100.0,
            current_step=5,
            message="Local surrogate completed.",
        )

    def get_result(self, engine_run_id: str) -> BenchmarkRunResult:
        config = self._runs[engine_run_id]
        score = self._compute_score(config)
        summary = (
            f"Local surrogate completed run {engine_run_id} with engagement_index={score:.2f}."
        )
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
                "scenario_id": "baseline_response",
                "confidence": round(min(0.95, max(0.05, score)), 2),
                "description": "Population-level response estimated by local surrogate.",
            }
        ]
        risks = []
        recommendations = []
        if score < 0.6:
            risks.append({"risk": "low_fidelity", "detail": "Harness controls appear under-tuned."})
            recommendations.append(
                {
                    "action": "strengthen_workflow_rules",
                    "detail": "Consider tightening fallback and loop-detection rules.",
                }
            )
        else:
            recommendations.append(
                {
                    "action": "keep_current_harness",
                    "detail": "Current harness controls look stable under the local surrogate.",
                }
            )

        return BenchmarkRunResult(
            summary=summary,
            metrics={"engagement_index": round(score, 3)},
            artifacts=artifacts,
            scenarios=scenarios,
            risks=risks,
            recommendations=recommendations,
        )

    def cancel_run(self, engine_run_id: str) -> None:
        self._runs.pop(engine_run_id, None)

    def _compute_score(self, config) -> float:
        score = 0.48

        max_agents = getattr(config, "max_agents", 0) or 0
        if max_agents <= 1000:
            score += 0.08
        elif max_agents <= 5000:
            score += 0.04

        time_horizon = str(getattr(config, "time_horizon", ""))
        if time_horizon.endswith("d"):
            score += 0.04

        environment = getattr(config, "environment", {}) or {}
        if environment.get("type") == "urban":
            score += 0.04
        if environment.get("documents"):
            score += 0.03

        profiles = getattr(config, "agent_profiles", []) or []
        if profiles:
            score += 0.03

        extra = getattr(config, "extra", {}) or {}
        harness_snapshot = extra.get("harness_snapshot", {})
        workflow_rules = harness_snapshot.get("workflow_rules", []) or []
        sampling_params = harness_snapshot.get("sampling_params", {}) or {}

        if workflow_rules:
            score += min(0.10, 0.02 * len(workflow_rules))
        if any("fallback recommendation" in rule for rule in workflow_rules):
            score += 0.06
        if any("loop" in rule.lower() for rule in workflow_rules):
            score += 0.04

        temperature = float(sampling_params.get("temperature", 0.2) or 0.2)
        if 0.15 <= temperature <= 0.35:
            score += 0.06
        elif 0.35 < temperature <= 0.6:
            score += 0.03

        return max(0.05, min(0.95, score))
