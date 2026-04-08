from __future__ import annotations

import json
from pathlib import Path

from improvement_loop import LoopMode
from improvement_loop.targets.config import ConfigBenchmarkSuite, ConfigImprovementTarget
from improvement_loop import ImprovementRuntime
from runtime_pydanticai.improvement import ConfigCritiqueDraft


def _build_temp_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "model_escalation_policy: true",
                "orchestrator:",
                "  max_stall_count: 3",
                "  max_replan: 4",
                "  max_steps_total: 50",
                "workers:",
                "  default_max_retries: 5",
                "  studio-dev:",
                "    default_tier: openclaw_gateway",
                "    auto_lint_patch: true",
                "  veille-strategique:",
                "    default_tier: openclaw_gateway",
                "    max_search_depth: 3",
            ]
        ),
        encoding="utf-8",
    )


def _build_suite(path: Path) -> None:
    suite = ConfigBenchmarkSuite.model_validate(
        {
            "suite_version": "v1",
            "name": "config_target_test_suite",
            "cases": [
                {
                    "case_id": "orchestrator_pressure",
                    "description": "Should reward more orchestration headroom.",
                    "signals": {
                        "orchestrator_error_rate": 0.4,
                        "long_horizon_complexity": 0.8,
                    },
                    "expectation": {"min_score": 0.95},
                }
            ],
        }
    )
    path.write_text(json.dumps(suite.model_dump(mode="json"), indent=2), encoding="utf-8")


class ResilientConfigCritic:
    def __init__(self, *args, **kwargs) -> None:
        self.runtime_used = ImprovementRuntime.pydanticai
        self.fallback_used = False
        self.last_attempt_count = 1
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_error = "structured runtime unavailable"
        self.last_error_category = "availability_error"
        self.last_error_retryable = False
        self.last_fallback_mode = "immediate_non_retryable"
        self.runtime_resilience = {
            "status": "degraded",
            "attempt_count": 1,
            "retry_count": 0,
            "retry_reasons": [],
            "fallback_used": False,
            "fallback_mode": "immediate_non_retryable",
            "runtime_error": "structured runtime unavailable",
            "error_category": "availability_error",
            "error_retryable": False,
            "diagnostics": ["runtime_error:availability_error"],
        }

    def propose(self, snapshot, trajectories):
        return ConfigCritiqueDraft(
            summary="Config critic kept bounded updates but noted runtime degradation.",
            rationale=["runtime diagnostics should be preserved for replay"],
            orchestrator_updates={"max_steps_total": 60},
            risk_level="low",
            requires_human_review=False,
        )


class NoopConfigCritic:
    def __init__(self, *args, **kwargs) -> None:
        self.runtime_used = ImprovementRuntime.pydanticai
        self.fallback_used = False
        self.last_attempt_count = 1
        self.last_retry_count = 0
        self.last_retry_reasons = []
        self.last_error = None
        self.last_error_category = None
        self.last_error_retryable = None
        self.last_fallback_mode = None
        self.runtime_resilience = {
            "status": "healthy",
            "attempt_count": 1,
            "retry_count": 0,
            "fallback_used": False,
            "summary": "healthy | attempts=1 | retries=0 | runtime=pydanticai",
        }

    def propose(self, snapshot, trajectories):
        return ConfigCritiqueDraft(
            summary="Structured critic found no bounded config change worth applying.",
            rationale=["No safe config delta was justified."],
            risk_level="low",
            requires_human_review=False,
        )


def test_config_target_inspect_reports_bounded_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    target = ConfigImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
    )

    inspection = target.inspect()
    comparability = inspection.metadata["comparability"]

    assert inspection.descriptor.target_id == "config"
    assert "orchestrator.max_steps_total" in inspection.metadata["modifiable_fields"]
    assert inspection.current_snapshot["orchestrator"]["max_steps_total"] == 50
    assert comparability["target_id"] == "config"
    assert comparability["target_kind"] == "config"
    assert comparability["surface"] == "inspection"
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_match"] is True
    assert comparability["latest_round_index"] == 0
    assert isinstance(comparability["config_fingerprint"], str) and len(comparability["config_fingerprint"]) == 64
    assert isinstance(comparability["benchmark_fingerprint"], str) and len(comparability["benchmark_fingerprint"]) == 64
    assert isinstance(comparability["state_fingerprint"], str) and len(comparability["state_fingerprint"]) == 64


def test_config_target_suggest_only_does_not_mutate_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    original = config_path.read_text(encoding="utf-8")
    target = ConfigImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
    )

    record = target.run_round(LoopMode.suggest_only)
    comparability = record.metadata["comparability"]

    assert record.target_id == "config"
    assert record.decision == "propose"
    assert config_path.read_text(encoding="utf-8") == original
    assert record.candidate_snapshot["orchestrator"]["max_steps_total"] == 60
    assert comparability["target_id"] == "config"
    assert comparability["surface"] == "round"
    assert comparability["round_index"] == record.round_index
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] in {
        ImprovementRuntime.pydanticai.value,
        ImprovementRuntime.legacy.value,
    }
    assert comparability["runtime_match"] == (
        comparability["runtime_requested"] == comparability["runtime_used"]
    )
    assert comparability["fallback_used"] is record.fallback_used
    assert isinstance(comparability["target_fingerprint"], str) and len(comparability["target_fingerprint"]) == 64


def test_config_target_safe_auto_apply_updates_temp_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    target = ConfigImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
    )

    record = target.run_round(LoopMode.safe_auto_apply)
    updated = config_path.read_text(encoding="utf-8")
    comparability = record.metadata["comparability"]

    assert record.decision == "keep"
    assert "max_steps_total: 60" in updated
    assert "max_stall_count: 4" in updated
    assert comparability["round_index"] == record.round_index
    assert comparability["latest_round_index"] == record.round_index - 1


def test_config_target_propagates_runtime_resilience_metadata(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    monkeypatch.setattr("improvement_loop.targets.config.PydanticAIConfigCritic", ResilientConfigCritic)

    target = ConfigImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
    )

    record = target.run_round(LoopMode.suggest_only, runtime=ImprovementRuntime.pydanticai)
    resilience = record.metadata["runtime_resilience"]
    comparability = record.metadata["comparability"]

    assert resilience["critic"] == "config"
    assert resilience["status"] == "degraded"
    assert resilience["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert resilience["runtime_used"] == ImprovementRuntime.pydanticai.value
    assert resilience["runtime_match"] is True
    assert resilience["attempt_count"] == 1
    assert resilience["runtime_error_category"] == "availability_error"
    assert resilience["runtime_error_retryable"] is False
    assert resilience["diagnostics"] == ["runtime_error:availability_error"]
    assert "degraded" in resilience["summary"]
    assert "error=availability_error" in resilience["summary"]
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_match"] is True
    assert comparability["fallback_used"] is False


def test_config_target_marks_post_validation_fallback_as_degraded(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    benchmark_path = tmp_path / "benchmark.json"
    _build_temp_config(config_path)
    _build_suite(benchmark_path)

    monkeypatch.setattr("improvement_loop.targets.config.PydanticAIConfigCritic", NoopConfigCritic)

    target = ConfigImprovementTarget(
        config_path=str(config_path),
        benchmark_path=str(benchmark_path),
        memory_path=str(tmp_path / "memory.db"),
    )

    record = target.run_round(LoopMode.suggest_only, runtime=ImprovementRuntime.pydanticai)
    resilience = record.metadata["runtime_resilience"]
    comparability = record.metadata["comparability"]

    assert record.runtime_used == ImprovementRuntime.legacy
    assert record.fallback_used is True
    assert resilience["status"] == "degraded"
    assert resilience["score"] == 0.8
    assert resilience["runtime_match"] is False
    assert resilience["fallback_mode"] == "post_validation_fallback"
    assert "requested=pydanticai" in resilience["summary"]
    assert "runtime=legacy" in resilience["summary"]
    assert comparability["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert comparability["runtime_used"] == ImprovementRuntime.legacy.value
    assert comparability["runtime_match"] is False
    assert comparability["fallback_used"] is True
