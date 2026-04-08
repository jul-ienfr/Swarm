from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from swarm_core.deliberation_artifacts import DeliberationMode


class DeliberationExpectationOperator(str, Enum):
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    eq = "eq"
    contains = "contains"


class DeliberationBenchmarkExpectation(BaseModel):
    metric: str
    operator: DeliberationExpectationOperator = DeliberationExpectationOperator.gte
    target: float | int | str | bool | None = None
    tolerance: float | None = None
    description: str = ""

    def matches(self, value: Any) -> bool:
        if self.operator == DeliberationExpectationOperator.contains:
            if self.target is None:
                return False
            return str(self.target) in str(value)

        if self.target is None:
            return False
        if value is None:
            return False

        left = value
        right = self.target
        if self.operator == DeliberationExpectationOperator.eq:
            return left == right
        if self.operator == DeliberationExpectationOperator.gt:
            return left > right
        if self.operator == DeliberationExpectationOperator.gte:
            return left >= right
        if self.operator == DeliberationExpectationOperator.lt:
            return left < right
        if self.operator == DeliberationExpectationOperator.lte:
            return left <= right
        return False


class DeliberationBenchmarkCase(BaseModel):
    case_id: str
    topic: str
    description: str = ""
    mode: DeliberationMode = DeliberationMode.committee
    input_payload: dict[str, Any] = Field(default_factory=dict)
    expectations: list[DeliberationBenchmarkExpectation] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationBenchmarkSuite(BaseModel):
    suite_id: str
    suite_version: str = "v1"
    name: str = "deliberation_benchmark_suite"
    cases: list[DeliberationBenchmarkCase] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def case_ids(self) -> list[str]:
        return [case.case_id for case in self.cases]

    def get_case(self, case_id: str) -> DeliberationBenchmarkCase:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "DeliberationBenchmarkSuite":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class DeliberationBenchmarkOutcome(BaseModel):
    case_id: str
    passed: bool
    score: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliberationBenchmarkReport(BaseModel):
    suite_id: str
    run_id: str
    outcomes: list[DeliberationBenchmarkOutcome] = Field(default_factory=list)
    overall_score: float = 0.0
    pass_rate: float = 0.0
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_outcomes(
        cls,
        *,
        suite_id: str,
        run_id: str,
        outcomes: list[DeliberationBenchmarkOutcome],
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "DeliberationBenchmarkReport":
        if outcomes:
            overall_score = sum(outcome.score for outcome in outcomes) / len(outcomes)
            pass_rate = sum(1 for outcome in outcomes if outcome.passed) / len(outcomes)
        else:
            overall_score = 0.0
            pass_rate = 0.0
        return cls(
            suite_id=suite_id,
            run_id=run_id,
            outcomes=outcomes,
            overall_score=overall_score,
            pass_rate=pass_rate,
            notes=notes,
            metadata=metadata or {},
        )
