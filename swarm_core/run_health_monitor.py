from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    blocked = "blocked"


@dataclass(slots=True)
class HealthIssue:
    code: str
    message: str
    severity: str


@dataclass(slots=True)
class RunHealthReport:
    run_id: str
    status: RunHealthStatus
    score: float
    issues: list[HealthIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    checked_at: str = field(default_factory=_utc_now)

    @property
    def is_healthy(self) -> bool:
        return self.status == RunHealthStatus.healthy

    @property
    def is_blocked(self) -> bool:
        return self.status == RunHealthStatus.blocked


class RunHealthMonitor:
    """
    Evaluates whether a deliberation run is healthy enough to keep going.

    The monitor is intentionally small: it looks for missing artifacts, timeouts,
    budget pressure, retries, and error accumulation.
    """

    def __init__(self, required_artifacts: Iterable[str] | None = None) -> None:
        self.required_artifacts = tuple(required_artifacts or ("manifest", "result", "report"))

    def evaluate(
        self,
        *,
        run_id: str,
        present_artifacts: Iterable[str],
        elapsed_seconds: float | None = None,
        timeout_seconds: float | None = None,
        retries: int = 0,
        errors: int = 0,
        warnings: int = 0,
        budget_exceeded: bool = False,
    ) -> RunHealthReport:
        present = set(present_artifacts)
        issues: list[HealthIssue] = []
        suggestions: list[str] = []
        score = 1.0
        blocked = False

        missing_required = [artifact for artifact in self.required_artifacts if artifact not in present]
        if missing_required:
            blocked = True
            issues.append(
                HealthIssue(
                    code="missing_required_artifacts",
                    message=f"missing required artifacts: {', '.join(missing_required)}",
                    severity="high",
                )
            )
            suggestions.append("re-run or repair the missing artifacts before continuing")
            score -= 0.45

        if timeout_seconds is not None and elapsed_seconds is not None and elapsed_seconds > timeout_seconds:
            blocked = True
            issues.append(
                HealthIssue(
                    code="timeout",
                    message=f"elapsed {elapsed_seconds:.2f}s exceeded timeout {timeout_seconds:.2f}s",
                    severity="high",
                )
            )
            suggestions.append("reduce fidelity or increase the timeout budget")
            score -= 0.25

        if budget_exceeded:
            blocked = True
            issues.append(HealthIssue(code="budget_exceeded", message="run exceeded its budget", severity="high"))
            suggestions.append("trim agents, rounds, or parallelism")
            score -= 0.2

        if errors:
            if errors >= 2:
                blocked = True
            issues.append(HealthIssue(code="errors", message=f"{errors} errors observed", severity="medium"))
            suggestions.append("inspect the error trail and retry only if the run is recoverable")
            score -= min(0.2, errors * 0.08)

        if retries:
            issues.append(HealthIssue(code="retries", message=f"{retries} retries observed", severity="low"))
            suggestions.append("keep the run under observation because retries were needed")
            score -= min(0.1, retries * 0.03)

        if warnings:
            issues.append(HealthIssue(code="warnings", message=f"{warnings} warnings observed", severity="low"))
            suggestions.append("review warnings to improve the next run")
            score -= min(0.08, warnings * 0.02)

        if not blocked and (retries > 0 or warnings > 0 or len(missing_required) == 0 and not present.issuperset(self.required_artifacts)):
            status = RunHealthStatus.degraded
        elif blocked:
            status = RunHealthStatus.blocked
        else:
            status = RunHealthStatus.healthy

        score = max(0.0, round(score, 3))
        if status == RunHealthStatus.healthy:
            score = max(score, 0.9)
        elif status == RunHealthStatus.degraded:
            score = min(score, 0.89)
        else:
            score = min(score, 0.49)

        return RunHealthReport(
            run_id=run_id,
            status=status,
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

