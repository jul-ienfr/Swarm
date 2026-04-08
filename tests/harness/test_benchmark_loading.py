from __future__ import annotations

from pathlib import Path

from swarm_core.benchmark_suite import BenchmarkProfile, BenchmarkSuite


def test_default_benchmark_suite_loads_from_repo() -> None:
    suite = BenchmarkSuite.load()

    assert suite.suite_version == "v1"
    assert suite.name == "default_harness_benchmark_suite"
    assert suite.cases
    first_case = suite.cases[0]
    assert first_case.intent.task_type.value == "scenario_simulation"
    assert first_case.intent.constraints.max_agents > 0
    assert "completed" in first_case.expectation.accepted_statuses


def test_fixture_benchmark_suite_matches_model_shape() -> None:
    fixture = Path(__file__).parent / "fixtures" / "benchmark_suite_v1.json"
    suite = BenchmarkSuite.load(fixture)

    assert suite.suite_version == "v1"
    assert suite.name == "harness-self-improvement-v1"
    assert len(suite.cases) == 1


def test_interactive_benchmark_suite_loads_from_repo() -> None:
    suite = BenchmarkSuite.load(profile=BenchmarkProfile.interactive)

    assert suite.suite_version == "v1-interactive"
    assert suite.name == "interactive_harness_benchmark_suite"
    assert len(suite.cases) == 1
    assert suite.metadata["backend_mode"] == "surrogate"
