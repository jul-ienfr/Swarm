from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SafetyDecision(str, Enum):
    allow = "allow"
    review = "review"
    block = "block"


class SafetySeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


@dataclass(slots=True)
class SafetyFinding:
    code: str
    severity: SafetySeverity
    message: str
    field: str | None = None


@dataclass(slots=True)
class SafetyPolicyLimits:
    max_agents: int = 512
    max_rounds: int = 6
    max_parallelism: int = 16
    require_provenance: bool = True
    block_keywords: tuple[str, ...] = (
        "malware",
        "phishing",
        "weapon",
        "explosive",
        "credential theft",
        "money laundering",
        "extort",
        "ransomware",
    )
    review_keywords: tuple[str, ...] = (
        "fraud",
        "bypass",
        "evasion",
        "manipulation",
        "market manipulation",
        "steal",
    )


@dataclass(slots=True)
class SafetyRequest:
    topic: str
    documents: tuple[str, ...] = ()
    population_size: int | None = None
    rounds: int | None = None
    parallelism: int | None = None
    provenance_count: int = 0


@dataclass(slots=True)
class SafetyPolicyResult:
    decision: SafetyDecision
    allowed: bool
    findings: list[SafetyFinding] = field(default_factory=list)
    checked_at: str = field(default_factory=_utc_now)

    @property
    def is_blocked(self) -> bool:
        return self.decision == SafetyDecision.block

    @property
    def is_review(self) -> bool:
        return self.decision == SafetyDecision.review


class SafetyPolicyEngine:
    """
    Conservative safety policy for deliberation runs.

    This is intentionally bounded: it is not a full moderation system,
    but it is good enough to prevent obviously unsafe or over-bounded runs.
    """

    def evaluate(
        self,
        request: SafetyRequest,
        *,
        limits: SafetyPolicyLimits | None = None,
    ) -> SafetyPolicyResult:
        limits = limits or SafetyPolicyLimits()
        findings: list[SafetyFinding] = []
        decision = SafetyDecision.allow

        text = " ".join((request.topic, *request.documents)).lower()
        for keyword in limits.block_keywords:
            if keyword in text:
                findings.append(
                    SafetyFinding(
                        code="blocked_keyword",
                        severity=SafetySeverity.critical,
                        message=f"found blocked keyword {keyword!r}",
                        field="documents",
                    )
                )
                decision = SafetyDecision.block
                break

        if decision != SafetyDecision.block:
            for keyword in limits.review_keywords:
                if keyword in text:
                    findings.append(
                        SafetyFinding(
                            code="review_keyword",
                            severity=SafetySeverity.medium,
                            message=f"found review keyword {keyword!r}",
                            field="documents",
                        )
                    )
                    decision = SafetyDecision.review
                    break

        if request.population_size is not None and request.population_size > limits.max_agents:
            findings.append(
                SafetyFinding(
                    code="population_limit",
                    severity=SafetySeverity.high,
                    message=f"population {request.population_size} exceeds max_agents {limits.max_agents}",
                    field="population_size",
                )
            )
            decision = SafetyDecision.block

        if request.rounds is not None and request.rounds > limits.max_rounds:
            findings.append(
                SafetyFinding(
                    code="round_limit",
                    severity=SafetySeverity.high,
                    message=f"rounds {request.rounds} exceeds max_rounds {limits.max_rounds}",
                    field="rounds",
                )
            )
            decision = SafetyDecision.block

        if request.parallelism is not None and request.parallelism > limits.max_parallelism:
            findings.append(
                SafetyFinding(
                    code="parallelism_limit",
                    severity=SafetySeverity.high,
                    message=f"parallelism {request.parallelism} exceeds max_parallelism {limits.max_parallelism}",
                    field="parallelism",
                )
            )
            decision = SafetyDecision.block

        if limits.require_provenance and request.provenance_count <= 0:
            findings.append(
                SafetyFinding(
                    code="provenance_missing",
                    severity=SafetySeverity.low,
                    message="no provenance evidence attached to request",
                    field="provenance_count",
                )
            )
            if decision == SafetyDecision.allow:
                decision = SafetyDecision.review

        if request.population_size is not None and request.population_size >= int(limits.max_agents * 0.8) and decision == SafetyDecision.allow:
            findings.append(
                SafetyFinding(
                    code="near_population_cap",
                    severity=SafetySeverity.low,
                    message="population size is close to the configured cap",
                    field="population_size",
                )
            )
            decision = SafetyDecision.review

        if request.rounds is not None and request.rounds >= int(limits.max_rounds * 0.8) and decision == SafetyDecision.allow:
            findings.append(
                SafetyFinding(
                    code="near_round_cap",
                    severity=SafetySeverity.low,
                    message="round count is close to the configured cap",
                    field="rounds",
                )
            )
            decision = SafetyDecision.review

        allowed = decision != SafetyDecision.block
        return SafetyPolicyResult(decision=decision, allowed=allowed, findings=findings)
