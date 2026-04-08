from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from runtime_contracts.intent import SimulationIntentV1


DEFAULT_BENCHMARK_SUITE_PATH = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "benchmark_suite_v1.json"
)
DEFAULT_INTERACTIVE_BENCHMARK_SUITE_PATH = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "benchmark_suite_interactive_v1.json"
)


class BenchmarkProfile(str, Enum):
    full = "full"
    interactive = "interactive"


def resolve_benchmark_suite_path(
    path: str | Path | None = None,
    *,
    profile: BenchmarkProfile | str = BenchmarkProfile.full,
) -> Path:
    if path:
        return Path(path)
    selected = profile if isinstance(profile, BenchmarkProfile) else BenchmarkProfile(str(profile))
    if selected == BenchmarkProfile.interactive:
        return DEFAULT_INTERACTIVE_BENCHMARK_SUITE_PATH
    return DEFAULT_BENCHMARK_SUITE_PATH


class BenchmarkExpectation(BaseModel):
    min_score: float = 0.60
    metric_thresholds: dict[str, float] = Field(default_factory=dict)
    accepted_statuses: list[str] = Field(default_factory=lambda: ["completed"])


class BenchmarkCase(BaseModel):
    case_id: str
    description: str
    weight: float = 1.0
    intent: SimulationIntentV1
    expectation: BenchmarkExpectation = Field(default_factory=BenchmarkExpectation)


class BenchmarkSuite(BaseModel):
    suite_version: str = "v1"
    name: str = "default_harness_benchmark_suite"
    metadata: dict[str, str] = Field(default_factory=dict)
    cases: list[BenchmarkCase]

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        profile: BenchmarkProfile | str = BenchmarkProfile.full,
    ) -> "BenchmarkSuite":
        suite_path = resolve_benchmark_suite_path(path, profile=profile)
        return cls.model_validate(json.loads(suite_path.read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))
