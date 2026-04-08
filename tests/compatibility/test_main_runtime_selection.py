from __future__ import annotations

import json
import os
import subprocess
import sys
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console
from typer.testing import CliRunner

from improvement_loop.models import ImprovementRoundRecord, ImprovementRuntime, LoopDecision, LoopMode, TargetDescriptor, TargetInspection
import main
from runtime_pydanticai import runtime_health as pydanticai_runtime_health
from swarm_core.deliberation import DeliberationResult, DeliberationStatus
from swarm_core.deliberation_artifacts import DeliberationMode
from swarm_core.benchmark_suite import BenchmarkProfile
from swarm_core.deliberation_stability import DeliberationStabilitySummary
from swarm_core.orchestration import RuntimeBackend
from runtime_contracts.intent import EnginePreference
from swarm_core.strategy_meeting import StrategyMeetingResult, StrategyMeetingStatus


def _entrypoint_env() -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{project_root}:{pythonpath}" if pythonpath else str(project_root)
    return env


def test_main_entrypoint_help_smoke() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(project_root / "main.py"), "--help"],
        capture_output=True,
        text=True,
        env=_entrypoint_env(),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Swarm Multi-Agent Research Harness" in result.stdout
    assert "deliberation-campaign" in result.stdout
    assert "deliberation-campaign-index" in result.stdout
    assert "list-deliberation-campaigns" in result.stdout
    assert "compare-deliberation-campaigns" in result.stdout
    assert "deliberation-campaign-dashboard" in result.stdout
    assert "read-deliberation-campaign" in result.stdout
    assert "audit-deliberation-campaign-comparison" in result.stdout
    assert "export-deliberation-campaign-comparison" in result.stdout
    assert "compare-deliberation-campaigns-audit-export" in result.stdout
    assert "benchmark-deliberation-campaigns" in result.stdout
    assert "benchmark-deliberation-campaign-matrix" in result.stdout
    assert "read-deliberation-campaign-benchmark" in result.stdout
    assert "list-deliberation-campaign-benchmarks" in result.stdout
    assert "read-deliberation-campaign-benchmark-matrix" in result.stdout
    assert "compare-deliberation-campaign-benchmark-matrices" in result.stdout
    assert "compare-deliberation-campaign-benchmark-matrices-audit-export" in result.stdout
    assert "audit-deliberation-campaign-benchmark-matrix" in result.stdout
    assert "export-deliberation-campaign-benchmark-matrix" in result.stdout
    assert "read-deliberation-campaign-benchmark-matrix-export" in result.stdout
    assert "list-deliberation-campaign-benchmark-matrix-exports" in result.stdout
    assert "compare-deliberation-campaign-benchmark-matrix-exports" in result.stdout
    assert "compare-deliberation-campaign-benchmark-matrix-exports-audit-export" in result.stdout
    assert "audit-deliberation-campaign-benchmark-matrix-export-comparison" in result.stdout
    assert "export-deliberation-campaign-benchmark-matrix-export-comparison" in result.stdout
    assert "read-deliberation-campaign-benchmark-matrix-export-comparison-export" in result.stdout
    assert "list-deliberation-campaign-benchmark-matrix-export-comparison-exports" in result.stdout
    assert "audit-deliberation-campaign-benchmark-matrix-comparison" in result.stdout
    assert "export-deliberation-campaign-benchmark-matrix-comparison" in result.stdout
    assert "read-deliberation-campaign-benchmark-matrix-comparison-export" in result.stdout
    assert "list-deliberation-campaign-benchmark-matrix-comparison-exports" in result.stdout
    assert "list-deliberation-campaign-benchmark-matrices" in result.stdout
    assert "OpenClaw" not in result.stdout
    assert "Antigravity" not in result.stdout


def test_main_entrypoint_deliberate_help_smoke() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(project_root / "main.py"), "deliberate", "--help"],
        capture_output=True,
        text=True,
        env=_entrypoint_env(),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Run the unified committee" in result.stdout


def test_main_entrypoint_meeting_help_smoke() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(project_root / "main.py"), "meeting", "--help"],
        capture_output=True,
        text=True,
        env=_entrypoint_env(),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "multi-agent strategy meeting" in result.stdout


def test_deliberation_campaign_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["deliberation-campaign", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persist a comparable report" in result.stdout
    assert "--sample-count" in result.stdout
    assert "--stability-runs" in result.stdout


def test_read_deliberation_campaign_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign report" in result.stdout


def test_compare_deliberation_campaigns_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["compare-deliberation-campaigns", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Compare two persisted deliberation campaign reports" in result.stdout
    assert "--latest" in result.stdout


def test_read_deliberation_campaign_comparison_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign-comparison", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign comparison report" in result.stdout


def test_list_deliberation_campaign_comparisons_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["list-deliberation-campaign-comparisons", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "list-deliberation-campaign-comparisons" in result.stdout


def test_audit_deliberation_campaign_comparison_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["audit-deliberation-campaign-comparison", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Audit a persisted deliberation campaign comparison report" in result.stdout


def test_export_deliberation_campaign_comparison_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["export-deliberation-campaign-comparison", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Export a persisted deliberation campaign comparison audit" in result.stdout


def test_compare_deliberation_campaigns_audit_export_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["compare-deliberation-campaigns-audit-export", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Compare two persisted campaigns" in result.stdout
    assert "build the audit" in result.stdout


def test_benchmark_deliberation_campaigns_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["benchmark-deliberation-campaigns", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Run baseline and candidate campaigns" in result.stdout
    assert "benchmark-deliberation-campaigns" in result.stdout


def test_benchmark_deliberation_campaign_matrix_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["benchmark-deliberation-campaign-matrix", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "shared baseline campaign against multiple candidates" in result.stdout
    assert "benchmark-deliberation-campaign-matrix" in result.stdout


def test_read_deliberation_campaign_benchmark_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign-benchmark", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign benchmark report" in result.stdout


def test_read_deliberation_campaign_benchmark_matrix_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign-benchmark-matrix", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign benchmark matrix report" in result.stdout


def test_compare_deliberation_campaign_benchmark_matrices_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["compare-deliberation-campaign-benchmark-matrices", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Compare two persisted deliberation campaign benchmark matrices" in result.stdout
    assert "--latest" in result.stdout


def test_read_deliberation_campaign_benchmark_matrix_comparison_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign-benchmark-matrix-comparison", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign benchmark matrix comparison report" in result.stdout


def test_list_deliberation_campaign_benchmark_matrix_comparisons_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["list-deliberation-campaign-benchmark-matrix-comparisons", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "list-deliberation-campaign-benchmark-matrix-comparisons" in result.stdout


def test_list_deliberation_campaign_benchmarks_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["list-deliberation-campaign-benchmarks", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "list-deliberation-campaign-benchmarks" in result.stdout


def test_list_deliberation_campaign_benchmark_matrices_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["list-deliberation-campaign-benchmark-matrices", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "list-deliberation-campaign-benchmark-matrices" in result.stdout


def test_read_deliberation_campaign_comparison_export_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["read-deliberation-campaign-comparison-export", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "persisted deliberation campaign comparison export" in result.stdout


def test_list_deliberation_campaign_comparison_exports_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["list-deliberation-campaign-comparison-exports", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "list-deliberation-campaign-comparison-exports" in result.stdout


def test_deliberation_campaign_index_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["deliberation-campaign-index", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "compact index of campaign" in result.stdout


def test_deliberation_campaign_dashboard_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(main.app, ["deliberation-campaign-dashboard", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "synthetic dashboard across persisted deliberation artifacts" in result.stdout
    assert "--kind" in result.stdout
    assert "--comparable-only" in result.stdout


class FakeController:
    def inspect_target(self, target: str, **kwargs):
        return TargetInspection(
            descriptor=TargetDescriptor(target_id=target, description=f"{target} target."),
            current_snapshot={"version": "snap_1"},
            benchmark={"suite_version": "v1", "cases": []},
        )

    def run_round(self, target: str, mode: LoopMode, **kwargs):
        return ImprovementRoundRecord(
            target_id=target,
            round_index=1,
            mode=mode,
            decision=LoopDecision.propose,
            baseline_score=0.5,
            candidate_score=0.7,
            score_delta=0.2,
            improvement_ratio=0.4,
            current_snapshot={"version": "current_1"},
            candidate_snapshot={"version": "candidate_1"},
            applied_snapshot={"version": "applied_1"},
            proposal={"summary": "test proposal"},
            baseline_report={"score": 0.5},
            candidate_report={"score": 0.7},
        )

    def run_loop(self, target: str, mode: LoopMode, max_rounds: int, **kwargs):
        return SimpleNamespace(
            target_id=target,
            mode=mode,
            max_rounds=max_rounds,
            completed_rounds=1,
            rounds=[self.run_round(target, mode)],
            stopped_reason="bounded",
            model_dump=lambda mode="json": {
                "target_id": target,
                "mode": mode.value if hasattr(mode, "value") else mode,
                "max_rounds": max_rounds,
                "completed_rounds": 1,
                "stopped_reason": "bounded",
            },
        )


class FakeMeetingResult:
    def __init__(self) -> None:
        self.metadata = {
            "runtime_used": RuntimeBackend.pydanticai.value,
            "fallback_used": False,
            "model_name": "claude-sonnet-4-6",
            "provider_base_url": "https://api.anthropic.com",
        }

    def model_dump(self, mode="json"):
        return {
            "meeting_id": "meeting_demo",
            "status": "completed",
            "participants": ["architect", "veille-strategique"],
            "strategy": "Adopt the cautious rollout.",
            "metadata": self.metadata,
        }


class FakeDeliberationResult:
    def __init__(self) -> None:
        self.runtime_requested = RuntimeBackend.pydanticai.value
        self.runtime_used = RuntimeBackend.pydanticai.value
        self.fallback_used = False
        self.engine_requested = "agentsociety"
        self.engine_used = "agentsociety"
        self.metadata = {
            "model_name": "claude-sonnet-4-6",
            "provider_base_url": "https://api.anthropic.com",
        }

    def model_dump(self, mode="json"):
        return {
            "deliberation_id": "delib_demo",
            "topic": "Choose the launch strategy",
            "objective": "Define the best strategy",
            "mode": "hybrid",
            "status": "completed",
            "runtime_requested": self.runtime_requested,
            "runtime_used": self.runtime_used,
            "fallback_used": self.fallback_used,
            "engine_requested": self.engine_requested,
            "engine_used": self.engine_used,
            "summary": "Population reaction is cautious but positive.",
            "final_strategy": "Roll out in stages.",
            "confidence_level": 0.72,
            "participants": ["architect", "research"],
            "artifacts": [],
            "provenance": [],
            "metadata": self.metadata,
        }


class FakeCampaignResult:
    def __init__(self, sample_index: int) -> None:
        self.deliberation_id = f"delib_{sample_index}"
        self.topic = "Choose the launch strategy"
        self.objective = "Define the best strategy"
        self.status = DeliberationStatus.completed
        self.runtime_requested = RuntimeBackend.pydanticai.value
        self.runtime_used = RuntimeBackend.pydanticai.value if sample_index != 2 else RuntimeBackend.legacy.value
        self.fallback_used = sample_index == 2
        self.engine_requested = "agentsociety"
        self.engine_used = "agentsociety" if sample_index != 3 else "oasis"
        self.judge_scores = SimpleNamespace(overall=0.6 + (sample_index * 0.05))
        self.confidence_level = 0.7 + (sample_index * 0.01)
        self.summary = f"Sample {sample_index} summary"
        self.final_strategy = f"Strategy {sample_index}"
        self.persisted_path = f"/tmp/delib_{sample_index}.json"
        self.metadata = {
            "quality_warnings": ["runtime_fallback_used"] if sample_index == 2 else [],
            "comparability": {
                "runtime_used": self.runtime_used,
                "engine_used": self.engine_used,
            },
        }


def _install_buffered_console(monkeypatch) -> StringIO:
    buffer = StringIO()
    monkeypatch.setattr(
        "main.console",
        Console(file=buffer, force_terminal=False, color_system=None, width=120),
    )
    return buffer


class FallbackImprovementController(FakeController):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_round(self, target: str, mode: LoopMode, **kwargs):
        self.calls.append({"target": target, "mode": mode, **kwargs})
        return ImprovementRoundRecord(
            target_id=target,
            round_index=1,
            mode=mode,
            decision=LoopDecision.propose,
            baseline_score=0.5,
            candidate_score=0.7,
            score_delta=0.2,
            improvement_ratio=0.4,
            current_snapshot={"version": "current_1"},
            candidate_snapshot={"version": "candidate_1"},
            applied_snapshot={"version": "applied_1"},
            proposal={"summary": "test proposal"},
            baseline_report={"score": 0.5},
            candidate_report={"score": 0.7},
            runtime_used=ImprovementRuntime.legacy,
            fallback_used=True,
            metadata={
                "runtime_requested": ImprovementRuntime.pydanticai.value,
                "runtime_error": "pydanticai unavailable",
            },
        )


def test_meeting_cli_defaults_to_pydanticai_runtime(monkeypatch) -> None:
    captured = {}

    def fake_runtime_runner(**kwargs):
        captured.update(kwargs)
        return FakeMeetingResult()

    monkeypatch.setattr("main.run_strategy_meeting_runtime", fake_runtime_runner)

    main.meeting(
        topic="Choose the product launch approach",
        json_output=True,
    )

    assert captured["runtime"] == RuntimeBackend.pydanticai
    assert captured["allow_fallback"] is True


def test_deliberate_cli_defaults_to_pydanticai_runtime(monkeypatch) -> None:
    captured = {}

    def fake_runtime_runner(**kwargs):
        captured.update(kwargs)
        return FakeDeliberationResult()

    monkeypatch.setattr("main.run_deliberation_runtime", fake_runtime_runner)

    main.deliberate(
        topic="Choose the product launch approach",
        json_output=True,
    )

    assert captured["runtime"] == RuntimeBackend.pydanticai
    assert captured["allow_fallback"] is True
    assert captured["mode"] == DeliberationMode.committee.value


def test_meeting_cli_can_disable_fallback(monkeypatch) -> None:
    captured = {}

    def fake_runtime_runner(**kwargs):
        captured.update(kwargs)
        return FakeMeetingResult()

    monkeypatch.setattr("main.run_strategy_meeting_runtime", fake_runtime_runner)

    main.meeting(
        topic="Choose the product launch approach",
        allow_fallback=False,
        json_output=True,
    )

    assert captured["runtime"] == RuntimeBackend.pydanticai
    assert captured["allow_fallback"] is False


def test_deliberate_cli_can_disable_fallback_and_forward_stability_runs(monkeypatch) -> None:
    captured = {}

    def fake_runtime_runner(**kwargs):
        captured.update(kwargs)
        return FakeDeliberationResult()

    monkeypatch.setattr("main.run_deliberation_runtime", fake_runtime_runner)

    main.deliberate(
        topic="Choose the product launch approach",
        allow_fallback=False,
        stability_runs=3,
        json_output=True,
    )

    assert captured["allow_fallback"] is False
    assert captured["stability_runs"] == 3


def test_deliberate_cli_disables_fallback_for_repeated_stability_runs(monkeypatch) -> None:
    captured = {}
    printed = {}

    def fake_runtime_runner(**kwargs):
        captured.update(kwargs)
        return FakeDeliberationResult()

    def fake_print_deliberation_result(result, as_json=False):
        printed["result"] = result
        printed["as_json"] = as_json

    monkeypatch.setattr("main.run_deliberation_runtime", fake_runtime_runner)
    monkeypatch.setattr("main._print_deliberation_result", fake_print_deliberation_result)

    main.deliberate(
        topic="Choose the product launch approach",
        stability_runs=4,
        json_output=False,
    )

    assert captured["allow_fallback"] is False
    assert captured["stability_runs"] == 4
    assert printed["as_json"] is False
    assert printed["result"].metadata["stability_runs"] == 4
    assert printed["result"].metadata["stability_guard_applied"] is True
    assert printed["result"].metadata["stability_guard_reason"] == "fallback_disabled_for_repeated_stability_comparison"


def test_deliberation_campaign_cli_text_summary(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def fake_runtime_runner(**kwargs):
        calls.append(kwargs)
        return FakeCampaignResult(len(calls))

    monkeypatch.setattr("swarm_core.deliberation_campaign.uuid4", lambda: SimpleNamespace(hex="abc12345deadbeef"))
    monkeypatch.setattr("main.run_deliberation_runtime", fake_runtime_runner)
    monkeypatch.setattr("main.DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR", tmp_path)

    result = runner.invoke(
        main.app,
        [
            "deliberation-campaign",
            "Choose the launch strategy",
            "--sample-count",
            "2",
            "--stability-runs",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Campaign ID:" in result.stdout
    assert "guard=yes" in result.stdout
    assert "reason=fallback_disabled_for_repeated_campaign_comparison" in result.stdout
    assert "Sample 1:" in result.stdout
    assert "Sample 2:" in result.stdout
    assert len(calls) == 2
    assert all(call["allow_fallback"] is False for call in calls)
    assert all(call["stability_runs"] == 1 for call in calls)


def test_deliberation_campaign_cli_can_forward_and_read_report(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def fake_runtime_runner(**kwargs):
        calls.append(kwargs)
        return FakeCampaignResult(len(calls))

    monkeypatch.setattr("swarm_core.deliberation_campaign.uuid4", lambda: SimpleNamespace(hex="abc12345deadbeef"))
    monkeypatch.setattr("main.run_deliberation_runtime", fake_runtime_runner)
    monkeypatch.setattr("main.DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR", tmp_path)

    result = runner.invoke(
        main.app,
        [
            "deliberation-campaign",
            "Choose the launch strategy",
            "--sample-count",
            "3",
            "--stability-runs",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["campaign_id"] == "campaign_abc12345dead"
    assert report["sample_count_requested"] == 3
    assert report["fallback_guard_applied"] is True
    assert report["fallback_guard_reason"] == "fallback_disabled_for_repeated_campaign_comparison"
    assert report["summary"]["runtime_counts"]["pydanticai"] == 3
    assert report["summary"]["engine_counts"]
    assert report["max_agents"] == 6
    assert report["rounds"] == 2
    assert report["time_horizon"] == "7d"
    assert len(calls) == 3
    assert all(call["allow_fallback"] is False for call in calls)
    assert all(call["stability_runs"] == 2 for call in calls)
    report_path = tmp_path / "campaign_abc12345dead" / "report.json"
    assert report_path.exists()

    read_result = runner.invoke(main.app, ["read-deliberation-campaign", "campaign_abc12345dead", "--json"])
    assert read_result.exit_code == 0, read_result.stdout
    read_report = json.loads(read_result.stdout)
    assert read_report["campaign_id"] == "campaign_abc12345dead"
    assert read_report["sample_count_requested"] == 3
    assert read_report["fallback_guard_applied"] is True


def test_list_deliberation_campaigns_cli_lists_reports_in_text_and_json(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    campaigns = [
        {
            "campaign_id": "campaign_alpha",
            "status": "completed",
            "created_at": "2026-04-08T10:00:00+00:00",
            "topic": "Choose the launch strategy",
            "objective": "Define the best strategy",
            "mode": "committee",
            "sample_count_requested": 3,
            "summary": {
                "sample_count_completed": 3,
                "sample_count_failed": 0,
            },
            "fallback_guard_applied": True,
            "fallback_guard_reason": "fallback_disabled_for_repeated_campaign_comparison",
            "report_path": "/tmp/campaign_alpha/report.json",
            "output_dir": "/tmp/campaigns",
        },
        {
            "campaign_id": "campaign_beta",
            "status": "partial",
            "created_at": "2026-04-07T10:00:00+00:00",
            "topic": "Plan the rollout",
            "objective": "Reduce launch risk",
            "mode": "hybrid",
            "sample_count_requested": 2,
            "summary": {
                "sample_count_completed": 1,
                "sample_count_failed": 1,
            },
            "fallback_guard_applied": False,
            "fallback_guard_reason": None,
            "report_path": "/tmp/campaign_beta/report.json",
            "output_dir": "/tmp/campaigns",
        },
    ]

    def fake_list_deliberation_campaigns(**kwargs):
        calls.append(kwargs)
        return campaigns[: kwargs["limit"]]

    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_reports",
        fake_list_deliberation_campaigns,
        raising=False,
    )
    monkeypatch.setattr("main.deliberation_campaign_core.list_deliberation_campaigns", fake_list_deliberation_campaigns, raising=False)

    text_result = runner.invoke(main.app, ["list-deliberation-campaigns", "--limit", "1"])
    assert text_result.exit_code == 0, text_result.stdout
    assert "Deliberation Campaigns" in text_result.stdout
    assert "campaign_alpha" in text_result.stdout
    assert "campaign_beta" not in text_result.stdout
    assert "guard" in text_result.stdout.lower()
    assert calls[0]["limit"] == 1

    json_result = runner.invoke(main.app, ["list-deliberation-campaigns", "--limit", "2", "--json"])
    assert json_result.exit_code == 0, json_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["count"] == 2
    assert payload["limit"] == 2
    assert payload["status"] is None
    assert payload["campaigns"][0]["campaign_id"] == "campaign_alpha"
    assert payload["campaigns"][1]["campaign_id"] == "campaign_beta"
    assert calls[1]["limit"] == 2

    filtered_result = runner.invoke(main.app, ["list-deliberation-campaigns", "--status", "completed", "--json"])
    assert filtered_result.exit_code == 0, filtered_result.stdout
    filtered_payload = json.loads(filtered_result.stdout)
    assert filtered_payload["status"] == "completed"
    assert calls[2]["status"] == "completed"


def test_compare_deliberation_campaigns_cli_compares_explicit_reports_in_text_and_json(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    comparison_report = {
        "comparison_id": "campaign_compare_demo",
        "output_dir": "/tmp/campaigns",
        "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
        "latest": None,
        "entries": [
            {
                "campaign_id": "campaign_alpha",
                "status": "completed",
                "created_at": "2026-04-08T10:00:00+00:00",
                "topic": "Choose the launch strategy",
                "mode": "committee",
                "runtime_requested": "pydanticai",
                "engine_requested": "agentsociety",
                "sample_count_requested": 3,
                "stability_runs": 1,
                "comparison_key": "key_alpha",
                "sample_count_completed": 3,
                "sample_count_failed": 0,
                "quality_score_mean": 0.72,
                "quality_score_min": 0.70,
                "quality_score_max": 0.74,
                "confidence_level_mean": 0.74,
                "confidence_level_min": 0.72,
                "confidence_level_max": 0.76,
                "fallback_guard_applied": True,
                "fallback_guard_reason": "fallback_disabled_for_repeated_campaign_comparison",
                "report_path": "/tmp/campaign_alpha/report.json",
            },
            {
                "campaign_id": "campaign_beta",
                "status": "partial",
                "created_at": "2026-04-07T10:00:00+00:00",
                "topic": "Plan the rollout",
                "mode": "hybrid",
                "runtime_requested": "legacy",
                "engine_requested": "oasis",
                "sample_count_requested": 2,
                "stability_runs": 1,
                "comparison_key": "key_beta",
                "sample_count_completed": 1,
                "sample_count_failed": 1,
                "quality_score_mean": 0.61,
                "quality_score_min": 0.58,
                "quality_score_max": 0.63,
                "confidence_level_mean": 0.63,
                "confidence_level_min": 0.60,
                "confidence_level_max": 0.66,
                "fallback_guard_applied": False,
                "fallback_guard_reason": None,
                "report_path": "/tmp/campaign_beta/report.json",
            },
        ],
        "summary": {
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "status_counts": {"completed": 1, "partial": 1},
            "topic_values": ["Choose the launch strategy", "Plan the rollout"],
            "mode_values": ["committee", "hybrid"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
            "sample_count_values": [2, 3],
            "stability_runs_values": [1],
            "comparison_key_values": ["key_alpha", "key_beta"],
            "comparable": False,
            "mismatch_reasons": ["topic_mismatch", "mode_mismatch", "runtime_mismatch", "engine_mismatch", "sample_count_mismatch", "comparison_key_mismatch"],
            "quality_score_mean": 0.665,
            "quality_score_min": 0.61,
            "quality_score_max": 0.72,
            "confidence_level_mean": 0.685,
            "confidence_level_min": 0.63,
            "confidence_level_max": 0.74,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
    }

    def fake_compare_deliberation_campaign_reports(**kwargs):
        calls.append(kwargs)
        return comparison_report

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_reports",
        fake_compare_deliberation_campaign_reports,
        raising=False,
    )

    text_result = runner.invoke(
        main.app,
        ["compare-deliberation-campaigns", "campaign_alpha", "campaign_beta"],
    )
    assert text_result.exit_code == 0, text_result.stdout
    assert "Campaign Comparison" in text_result.stdout
    assert "campaign_alpha" in text_result.stdout
    assert "campaign_beta" in text_result.stdout
    assert "quality_mean" in text_result.stdout
    assert calls[0]["campaign_ids"] == ["campaign_alpha", "campaign_beta"]
    assert calls[0]["persist"] is True
    assert str(calls[0]["comparison_output_dir"]).endswith("data/deliberation_campaign_comparisons")

    json_result = runner.invoke(
        main.app,
        ["compare-deliberation-campaigns", "campaign_alpha", "campaign_beta", "--json"],
    )
    assert json_result.exit_code == 0, json_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["comparison_mode"] == "explicit"
    assert payload["entries"][0]["campaign_id"] == "campaign_alpha"
    assert payload["entries"][1]["campaign_id"] == "campaign_beta"
    assert payload["summary"]["comparable"] is False
    assert "topic_mismatch" in payload["summary"]["mismatch_reasons"]
    assert payload["comparison"]["sample_count_completed_delta"] == 2
    assert round(payload["comparison"]["quality_score_mean_delta"], 3) == 0.11


def test_compare_deliberation_campaigns_cli_latest_uses_core_listing(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    comparison_report = {
        "comparison_id": "campaign_compare_latest",
        "output_dir": "/tmp/campaigns",
        "requested_campaign_ids": [],
        "latest": 2,
        "entries": [
            {
                "campaign_id": "campaign_new",
                "status": "completed",
                "created_at": "2026-04-08T12:00:00+00:00",
                "topic": "Newest",
                "mode": "committee",
                "runtime_requested": "pydanticai",
                "engine_requested": "agentsociety",
                "sample_count_requested": 3,
                "stability_runs": 1,
                "comparison_key": "key_new",
                "sample_count_completed": 3,
                "sample_count_failed": 0,
                "quality_score_mean": 0.8,
                "quality_score_min": 0.78,
                "quality_score_max": 0.82,
                "confidence_level_mean": 0.81,
                "confidence_level_min": 0.8,
                "confidence_level_max": 0.82,
                "fallback_guard_applied": True,
                "fallback_guard_reason": "fallback_disabled_for_repeated_campaign_comparison",
                "report_path": "/tmp/campaign_new/report.json",
            },
            {
                "campaign_id": "campaign_old",
                "status": "partial",
                "created_at": "2026-04-07T12:00:00+00:00",
                "topic": "Older",
                "mode": "committee",
                "runtime_requested": "legacy",
                "engine_requested": "oasis",
                "sample_count_requested": 2,
                "stability_runs": 1,
                "comparison_key": "key_old",
                "sample_count_completed": 1,
                "sample_count_failed": 1,
                "quality_score_mean": 0.65,
                "quality_score_min": 0.63,
                "quality_score_max": 0.66,
                "confidence_level_mean": 0.66,
                "confidence_level_min": 0.65,
                "confidence_level_max": 0.67,
                "fallback_guard_applied": False,
                "fallback_guard_reason": None,
                "report_path": "/tmp/campaign_old/report.json",
            },
        ],
        "summary": {
            "campaign_count": 2,
            "campaign_ids": ["campaign_new", "campaign_old"],
            "status_counts": {"completed": 1, "partial": 1},
            "topic_values": ["Newest", "Older"],
            "mode_values": ["committee"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
            "sample_count_values": [2, 3],
            "stability_runs_values": [1],
            "comparison_key_values": ["key_new", "key_old"],
            "comparable": False,
            "mismatch_reasons": ["topic_mismatch", "runtime_mismatch", "engine_mismatch", "sample_count_mismatch", "comparison_key_mismatch"],
            "quality_score_mean": 0.725,
            "quality_score_min": 0.65,
            "quality_score_max": 0.8,
            "confidence_level_mean": 0.735,
            "confidence_level_min": 0.66,
            "confidence_level_max": 0.81,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
    }

    def fake_compare_deliberation_campaign_reports(**kwargs):
        calls.append(kwargs)
        return comparison_report

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_reports",
        fake_compare_deliberation_campaign_reports,
        raising=False,
    )

    result = runner.invoke(main.app, ["compare-deliberation-campaigns", "--latest", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_mode"] == "latest"
    assert payload["entries"][0]["campaign_id"] == "campaign_new"
    assert payload["entries"][1]["campaign_id"] == "campaign_old"
    assert calls[0]["latest"] == 2
    assert calls[0]["persist"] is True
    assert str(calls[0]["comparison_output_dir"]).endswith("data/deliberation_campaign_comparisons")


def test_read_deliberation_campaign_comparison_cli_uses_core_loader(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    comparison_report = {
        "comparison_id": "campaign_compare_demo",
        "created_at": "2026-04-08T10:00:00+00:00",
        "output_dir": "/tmp/campaigns",
        "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
        "latest": None,
        "entries": [],
        "summary": {
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "comparable": True,
            "mismatch_reasons": [],
            "comparison_key_values": ["key_alpha"],
        },
        "metadata": {"comparison_key": "key_alpha", "report_path": "/tmp/campaigns/comparisons/campaign_compare_demo/report.json"},
    }

    def fake_load_deliberation_campaign_comparison_report(comparison_id, **kwargs):
        calls.append({"comparison_id": comparison_id, **kwargs})
        return comparison_report

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_comparison_report",
        fake_load_deliberation_campaign_comparison_report,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        ["read-deliberation-campaign-comparison", "campaign_compare_demo", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_id"] == "campaign_compare_demo"
    assert payload["summary"]["campaign_count"] == 2
    assert calls[0]["comparison_id"] == "campaign_compare_demo"


def test_list_deliberation_campaign_comparisons_cli_uses_core_listing(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    comparison_reports = [
        {
            "comparison_id": "campaign_compare_new",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": "/tmp/campaigns",
            "requested_campaign_ids": ["campaign_new", "campaign_old"],
            "latest": 2,
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "comparable": True,
                "mismatch_reasons": [],
                "comparison_key_values": ["key_new"],
            },
            "metadata": {"comparison_key": "key_new"},
        }
    ]

    def fake_list_deliberation_campaign_comparison_reports(**kwargs):
        calls.append(kwargs)
        return comparison_reports

    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_comparison_reports",
        fake_list_deliberation_campaign_comparison_reports,
        raising=False,
    )

    result = runner.invoke(main.app, ["list-deliberation-campaign-comparisons", "--limit", "1", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["comparisons"][0]["comparison_id"] == "campaign_compare_new"
    assert calls[0]["limit"] == 1


def test_audit_deliberation_campaign_comparison_cli_uses_core_loader(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    audit_payload = {
        "comparison_id": "campaign_compare_demo",
        "created_at": "2026-04-08T10:00:00+00:00",
        "output_dir": "/tmp/campaigns",
        "report_path": "/tmp/campaigns/comparisons/campaign_compare_demo/report.json",
        "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
        "latest": None,
        "campaign_count": 2,
        "campaign_ids": ["campaign_alpha", "campaign_beta"],
        "comparable": False,
        "mismatch_reasons": ["comparison_key_mismatch"],
        "entries": [],
        "summary": {
            "campaign_count": 2,
            "quality_score_mean": 0.71,
            "confidence_level_mean": 0.69,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
        "metadata": {"comparison_key": None},
    }

    def fake_load_deliberation_campaign_comparison_audit(comparison_id, **kwargs):
        calls.append({"comparison_id": comparison_id, **kwargs})
        return audit_payload

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_comparison_audit",
        fake_load_deliberation_campaign_comparison_audit,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        ["audit-deliberation-campaign-comparison", "campaign_compare_demo", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_id"] == "campaign_compare_demo"
    assert payload["comparable"] is False
    assert calls[0]["comparison_id"] == "campaign_compare_demo"
    assert calls[0]["include_markdown"] is False


def test_export_deliberation_campaign_comparison_cli_writes_markdown(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    audit_payload = {
        "comparison_id": "campaign_compare_demo",
        "created_at": "2026-04-08T10:00:00+00:00",
        "output_dir": str(tmp_path),
        "report_path": str(tmp_path / "campaign_compare_demo" / "report.json"),
        "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
        "latest": None,
        "campaign_count": 2,
        "campaign_ids": ["campaign_alpha", "campaign_beta"],
        "comparable": False,
        "mismatch_reasons": ["comparison_key_mismatch"],
        "entries": [],
        "summary": {
            "campaign_count": 2,
            "quality_score_mean": 0.71,
            "confidence_level_mean": 0.69,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
        "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: campaign_compare_demo\n",
        "metadata": {"comparison_key": None},
    }

    def fake_load_deliberation_campaign_comparison_audit(comparison_id, **kwargs):
        calls.append({"comparison_id": comparison_id, **kwargs})
        return audit_payload

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_comparison_audit",
        fake_load_deliberation_campaign_comparison_audit,
        raising=False,
    )

    target_path = tmp_path / "exports" / "comparison.md"
    result = runner.invoke(
        main.app,
        [
            "export-deliberation-campaign-comparison",
            "campaign_compare_demo",
            "--format",
            "markdown",
            "--output-path",
            str(target_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_id"] == "campaign_compare_demo"
    assert payload["export_id"] == "campaign_compare_demo__markdown"
    assert payload["format"] == "markdown"
    assert payload["output_path"] == str(target_path)
    assert payload["content_path"].endswith("/campaign_compare_demo__markdown/content.md")
    assert payload["manifest_path"].endswith("/campaign_compare_demo__markdown/manifest.json")
    assert target_path.read_text(encoding="utf-8").startswith("# Deliberation Campaign Comparison")
    assert calls[0]["include_markdown"] is True


def test_export_deliberation_campaign_comparison_cli_persists_and_lists_default_export(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    audit_payload = {
        "comparison_id": "campaign_compare_demo",
        "created_at": "2026-04-08T10:00:00+00:00",
        "output_dir": str(tmp_path),
        "report_path": str(tmp_path / "campaign_compare_demo" / "report.json"),
        "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
        "latest": None,
        "campaign_count": 2,
        "campaign_ids": ["campaign_alpha", "campaign_beta"],
        "comparable": False,
        "mismatch_reasons": ["comparison_key_mismatch"],
        "entries": [],
        "summary": {
            "campaign_count": 2,
            "quality_score_mean": 0.71,
            "confidence_level_mean": 0.69,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
        "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: campaign_compare_demo\n",
        "metadata": {"comparison_key": None},
    }

    def fake_load_deliberation_campaign_comparison_audit(comparison_id, **kwargs):
        assert comparison_id == "campaign_compare_demo"
        assert kwargs["include_markdown"] is True
        return audit_payload

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_comparison_audit",
        fake_load_deliberation_campaign_comparison_audit,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "export-deliberation-campaign-comparison",
            "campaign_compare_demo",
            "--comparison-output-dir",
            str(tmp_path / "comparison_reports"),
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    expected_path = tmp_path / "campaign_compare_demo__markdown" / "content.md"
    assert payload["output_path"] == str(expected_path)
    assert expected_path.read_text(encoding="utf-8").startswith("# Deliberation Campaign Comparison")

    read_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-comparison-export",
            "campaign_compare_demo",
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert read_result.exit_code == 0, read_result.stdout
    read_payload = json.loads(read_result.stdout)
    assert read_payload["comparison_id"] == "campaign_compare_demo"
    assert read_payload["export_id"] == "campaign_compare_demo__markdown"
    assert read_payload["format"] == "markdown"
    assert "# Deliberation Campaign Comparison" in read_payload["content"]

    list_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-comparison-exports",
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert list_result.exit_code == 0, list_result.stdout
    list_payload = json.loads(list_result.stdout)
    assert list_payload["count"] == 1
    assert list_payload["exports"][0]["comparison_id"] == "campaign_compare_demo"
    assert list_payload["exports"][0]["export_id"] == "campaign_compare_demo__markdown"
    assert list_payload["exports"][0]["format"] == "markdown"


def test_compare_deliberation_campaigns_audit_export_cli_uses_core_helpers(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []
    bundle_payload = {
        "comparison_report": {
            "comparison_id": "campaign_compare_demo",
            "output_dir": str(tmp_path / "comparisons"),
            "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
            "latest": None,
            "report_path": str(tmp_path / "comparisons" / "campaign_compare_demo" / "report.json"),
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "campaign_ids": ["campaign_alpha", "campaign_beta"],
                "comparable": False,
                "mismatch_reasons": ["stability_runs_mismatch", "comparison_key_mismatch"],
                "comparison_key_values": ["key_alpha", "key_beta"],
                "sample_count_requested_total": 5,
                "sample_count_completed_total": 4,
                "sample_count_failed_total": 1,
                "quality_score_mean": 0.675,
                "confidence_level_mean": 0.625,
            },
        },
        "audit": {
            "comparison_id": "campaign_compare_demo",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": str(tmp_path / "comparisons"),
            "report_path": str(tmp_path / "comparisons" / "campaign_compare_demo" / "report.json"),
            "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
            "latest": None,
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "comparable": False,
            "mismatch_reasons": ["stability_runs_mismatch", "comparison_key_mismatch"],
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "quality_score_mean": 0.675,
                "confidence_level_mean": 0.625,
                "sample_count_requested_total": 5,
                "sample_count_completed_total": 4,
                "sample_count_failed_total": 1,
            },
            "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: campaign_compare_demo\n",
            "metadata": {"comparison_key": None},
        },
        "export": {
            "export_id": "campaign_compare_demo__markdown",
            "created_at": "2026-04-08T12:30:00+00:00",
            "output_dir": str(tmp_path / "exports"),
            "manifest_path": str(tmp_path / "exports" / "campaign_compare_demo__markdown" / "manifest.json"),
            "content_path": str(tmp_path / "exports" / "campaign_compare_demo__markdown" / "content.md"),
            "comparison_id": "campaign_compare_demo",
            "comparison_report_path": str(tmp_path / "comparisons" / "campaign_compare_demo" / "report.json"),
            "format": "markdown",
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "comparable": False,
            "mismatch_reasons": ["stability_runs_mismatch", "comparison_key_mismatch"],
            "content": "# Deliberation Campaign Comparison\n\n- Comparison ID: campaign_compare_demo\n",
            "metadata": {"persisted": True},
        },
    }

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        calls.append(kwargs)
        assert kwargs["persist"] is True
        assert kwargs["comparison_output_dir"] == str(tmp_path / "comparisons")
        assert kwargs["export_output_dir"] == str(tmp_path / "exports")
        assert kwargs["format"] == "markdown"
        return dict(bundle_payload)

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_bundle",
        fake_compare_deliberation_campaign_bundle,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaigns-audit-export",
            "campaign_alpha",
            "campaign_beta",
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
            "--export-output-dir",
            str(tmp_path / "exports"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_id"] == "campaign_compare_demo"
    assert payload["export_id"] == "campaign_compare_demo__markdown"
    assert payload["comparison"]["comparison_id"] == "campaign_compare_demo"
    assert payload["audit"]["comparison_id"] == "campaign_compare_demo"
    assert payload["export"]["export_id"] == "campaign_compare_demo__markdown"
    assert calls[0]["persist"] is True
    assert calls[0]["comparison_output_dir"] == str(tmp_path / "comparisons")
    assert calls[0]["export_output_dir"] == str(tmp_path / "exports")
    assert calls[0]["format"] == "markdown"


def test_benchmark_deliberation_campaigns_cli_persists_and_reads_json(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    benchmark_calls: list[dict[str, object]] = []
    load_calls: list[dict[str, object]] = []
    list_calls: list[dict[str, object]] = []

    def fake_run_deliberation_campaign_benchmark_sync(**kwargs):
        benchmark_calls.append(kwargs)
        payload = {
            "benchmark_id": "campaign_baseline_demo__vs__campaign_candidate_demo",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": str(tmp_path / "benchmarks"),
            "report_path": str(tmp_path / "benchmarks" / "campaign_baseline_demo__vs__campaign_candidate_demo" / "report.json"),
            "benchmark_mode": "comparison",
            "baseline_campaign": {
                "campaign_id": "campaign_baseline_demo",
                "status": "completed",
                "summary": {"sample_count_completed": 2, "sample_count_failed": 0},
            },
            "candidate_campaign": {
                "campaign_id": "campaign_candidate_demo",
                "status": "completed",
                "summary": {"sample_count_completed": 2, "sample_count_failed": 0},
            },
            "comparison": {
                "comparison_id": "campaign_benchmark_compare_demo",
                "report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                "summary": {"comparable": True, "mismatch_reasons": []},
            },
            "audit": {
                "comparison_id": "campaign_benchmark_compare_demo",
                "report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                "comparable": True,
                "mismatch_reasons": [],
            },
            "export": {
                "export_id": "campaign_benchmark_compare_demo__json",
                "manifest_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "manifest.json"),
                "content_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "content.json"),
                "comparison_id": "campaign_benchmark_compare_demo",
                "format": "json",
            },
            "baseline_campaign_id": "campaign_baseline_demo",
            "candidate_campaign_id": "campaign_candidate_demo",
            "comparison_id": "campaign_benchmark_compare_demo",
            "export_id": "campaign_benchmark_compare_demo__json",
            "comparison_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
            "audit_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
            "export_manifest_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "manifest.json"),
            "export_content_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "content.json"),
            "baseline_runtime": "pydanticai",
            "candidate_runtime": "legacy",
            "baseline_engine_preference": "agentsociety",
            "candidate_engine_preference": "oasis",
            "format": "json",
        }
        return type("Benchmark", (), {"model_dump": lambda self, mode="json": payload})()

    def fake_load_deliberation_campaign_benchmark(benchmark_id, **kwargs):
        load_calls.append({"benchmark_id": benchmark_id, **kwargs})
        return type(
            "Benchmark",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "benchmark_id": benchmark_id,
                    "created_at": "2026-04-08T12:00:00+00:00",
                    "output_dir": str(tmp_path / "benchmarks"),
                    "report_path": str(tmp_path / "benchmarks" / benchmark_id / "report.json"),
                    "benchmark_mode": "comparison",
                    "baseline_campaign_id": "campaign_baseline_demo",
                    "candidate_campaign_id": "campaign_candidate_demo",
                    "comparison_id": "campaign_benchmark_compare_demo",
                    "export_id": "campaign_benchmark_compare_demo__json",
                    "comparison_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                    "audit_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                    "export_manifest_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "manifest.json"),
                    "export_content_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "content.json"),
                    "baseline_runtime": "pydanticai",
                    "candidate_runtime": "legacy",
                    "baseline_engine_preference": "agentsociety",
                    "candidate_engine_preference": "oasis",
                    "format": "json",
                },
            },
        )()

    def fake_list_deliberation_campaign_benchmarks(**kwargs):
        list_calls.append(kwargs)
        return [
            type(
                "Benchmark",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "benchmark_id": "campaign_baseline_demo__vs__campaign_candidate_demo",
                        "created_at": "2026-04-08T12:00:00+00:00",
                        "output_dir": str(tmp_path / "benchmarks"),
                        "report_path": str(tmp_path / "benchmarks" / "campaign_baseline_demo__vs__campaign_candidate_demo" / "report.json"),
                        "benchmark_mode": "comparison",
                        "baseline_campaign_id": "campaign_baseline_demo",
                        "candidate_campaign_id": "campaign_candidate_demo",
                        "comparison_id": "campaign_benchmark_compare_demo",
                        "export_id": "campaign_benchmark_compare_demo__json",
                        "comparison_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                        "audit_report_path": str(tmp_path / "comparisons" / "campaign_benchmark_compare_demo" / "report.json"),
                        "export_manifest_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "manifest.json"),
                        "export_content_path": str(tmp_path / "exports" / "campaign_benchmark_compare_demo__json" / "content.json"),
                        "baseline_runtime": "pydanticai",
                        "candidate_runtime": "legacy",
                        "baseline_engine_preference": "agentsociety",
                        "candidate_engine_preference": "oasis",
                        "format": "json",
                    },
                },
            )()
        ]

    monkeypatch.setattr(
        "main.deliberation_campaign_core.run_deliberation_campaign_benchmark_sync",
        fake_run_deliberation_campaign_benchmark_sync,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_benchmark",
        fake_load_deliberation_campaign_benchmark,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_benchmarks",
        fake_list_deliberation_campaign_benchmarks,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "benchmark-deliberation-campaigns",
            "Choose the launch strategy",
            "--sample-count",
            "2",
            "--stability-runs",
            "2",
            "--baseline-runtime",
            "pydanticai",
            "--candidate-runtime",
            "legacy",
            "--baseline-engine-preference",
            "agentsociety",
            "--candidate-engine-preference",
            "oasis",
            "--campaign-output-dir",
            str(tmp_path / "campaigns"),
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
            "--export-output-dir",
            str(tmp_path / "exports"),
            "--benchmark-output-dir",
            str(tmp_path / "benchmarks"),
            "--format",
            "json",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["benchmark_mode"] == "comparison"
    assert payload["benchmark_id"] == "campaign_baseline_demo__vs__campaign_candidate_demo"
    assert payload["baseline_campaign_id"] == "campaign_baseline_demo"
    assert payload["candidate_campaign_id"] == "campaign_candidate_demo"
    assert payload["comparison_id"] == "campaign_benchmark_compare_demo"
    assert payload["export_id"] == "campaign_benchmark_compare_demo__json"
    assert payload["format"] == "json"
    assert payload["baseline_campaign"]["campaign_id"] == "campaign_baseline_demo"
    assert payload["candidate_campaign"]["campaign_id"] == "campaign_candidate_demo"
    assert payload["comparison"]["comparison_id"] == "campaign_benchmark_compare_demo"
    assert payload["audit"]["comparison_id"] == "campaign_benchmark_compare_demo"
    assert payload["export"]["export_id"] == "campaign_benchmark_compare_demo__json"
    assert len(benchmark_calls) == 1
    assert benchmark_calls[0]["baseline_runtime"] == RuntimeBackend.pydanticai
    assert benchmark_calls[0]["candidate_runtime"] == RuntimeBackend.legacy
    assert benchmark_calls[0]["baseline_engine_preference"] == EnginePreference.agentsociety
    assert benchmark_calls[0]["candidate_engine_preference"] == EnginePreference.oasis
    assert str(benchmark_calls[0]["output_dir"]).endswith("campaigns")
    assert str(benchmark_calls[0]["comparison_output_dir"]).endswith("comparisons")
    assert str(benchmark_calls[0]["export_output_dir"]).endswith("exports")

    benchmark_report_path = tmp_path / "benchmarks" / "campaign_baseline_demo__vs__campaign_candidate_demo" / "report.json"
    assert benchmark_report_path.exists()
    assert len(load_calls) == 0
    assert len(list_calls) == 0

    read_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark",
            "campaign_baseline_demo__vs__campaign_candidate_demo",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--json",
        ],
    )
    assert read_result.exit_code == 0, read_result.stdout
    read_payload = json.loads(read_result.stdout)
    assert read_payload["benchmark_id"] == "campaign_baseline_demo__vs__campaign_candidate_demo"
    assert read_payload["comparison_id"] == "campaign_benchmark_compare_demo"
    assert read_payload["export_id"] == "campaign_benchmark_compare_demo__json"
    assert read_payload["report_path"] == str(benchmark_report_path)
    assert len(load_calls) == 1
    assert load_calls[0]["benchmark_id"] == "campaign_baseline_demo__vs__campaign_candidate_demo"
    assert load_calls[0]["output_dir"] == str(tmp_path / "benchmarks")

    list_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmarks",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--json",
        ],
    )
    assert list_result.exit_code == 0, list_result.stdout
    list_payload = json.loads(list_result.stdout)
    assert list_payload["count"] == 1
    assert list_payload["benchmarks"][0]["benchmark_id"] == "campaign_baseline_demo__vs__campaign_candidate_demo"
    assert list_payload["benchmarks"][0]["comparison_id"] == "campaign_benchmark_compare_demo"
    assert list_payload["benchmarks"][0]["export_id"] == "campaign_benchmark_compare_demo__json"
    assert len(list_calls) == 1
    assert list_calls[0]["output_dir"] == str(tmp_path / "benchmarks")


def test_benchmark_deliberation_campaign_matrix_cli_persists_and_reads_json(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    matrix_calls: list[dict[str, object]] = []
    load_calls: list[dict[str, object]] = []
    list_calls: list[dict[str, object]] = []

    def build_payload(matrix_id: str, output_dir: str, candidate_specs: list[object]) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        candidate_labels: list[str] = []
        candidate_campaign_ids: list[str] = []
        comparison_ids: list[str] = []
        runtime_values: list[str] = []
        engine_values: list[str] = []

        for index, spec in enumerate(candidate_specs, start=1):
            candidate_campaign_id = str(getattr(spec, "campaign_id", f"matrix_candidate_{index:02d}"))
            candidate_label = str(getattr(spec, "label", candidate_campaign_id))
            runtime_value = str(getattr(spec, "runtime", "legacy"))
            engine_value = str(getattr(getattr(spec, "engine_preference", None), "value", getattr(spec, "engine_preference", "oasis")))
            comparison_id = f"campaign_matrix_compare_{index}"
            candidate_labels.append(candidate_label)
            candidate_campaign_ids.append(candidate_campaign_id)
            comparison_ids.append(comparison_id)
            runtime_values.append(runtime_value)
            engine_values.append(engine_value)
            entries.append(
                {
                    "candidate_index": index,
                    "candidate_label": candidate_label,
                    "candidate_spec": {
                        "label": candidate_label,
                        "campaign_id": candidate_campaign_id,
                        "runtime": runtime_value,
                        "engine_preference": engine_value,
                    },
                    "candidate_campaign": {
                        "campaign_id": candidate_campaign_id,
                        "status": "completed",
                    },
                    "comparison_bundle": {
                        "comparison_report": {
                            "comparison_id": comparison_id,
                            "summary": {
                                "comparable": True,
                                "quality_score_mean": 0.5 + index / 10.0,
                                "confidence_level_mean": 0.6 + index / 10.0,
                            },
                        },
                        "export": {
                            "export_id": f"{comparison_id}__json",
                            "format": "json",
                        },
                    },
                }
            )

        payload = {
            "matrix_id": matrix_id,
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": output_dir,
            "report_path": str(Path(output_dir) / matrix_id / "report.json"),
            "baseline_campaign": {
                "campaign_id": "campaign_baseline_demo",
                "status": "completed",
            },
            "baseline_campaign_id": "campaign_baseline_demo",
            "summary": {
                "candidate_count": len(entries),
                "candidate_labels": candidate_labels,
                "candidate_campaign_ids": candidate_campaign_ids,
                "comparison_ids": comparison_ids,
                "comparable_count": len(entries),
                "mismatch_count": 0,
                "quality_score_mean": 0.6,
                "confidence_level_mean": 0.7,
                "runtime_values": runtime_values,
                "engine_values": engine_values,
            },
            "candidate_specs": [
                {
                    "label": str(getattr(spec, "label", "candidate")),
                    "campaign_id": str(getattr(spec, "campaign_id", "candidate")),
                    "runtime": str(getattr(spec, "runtime", "legacy")),
                    "engine_preference": str(getattr(getattr(spec, "engine_preference", None), "value", getattr(spec, "engine_preference", "oasis"))),
                }
                for spec in candidate_specs
            ],
            "entries": entries,
            "persisted": True,
        }
        Path(output_dir, matrix_id).mkdir(parents=True, exist_ok=True)
        Path(output_dir, matrix_id, "report.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def fake_run_deliberation_campaign_matrix_benchmark_sync(**kwargs):
        matrix_calls.append(kwargs)
        payload = build_payload(
            str(kwargs["benchmark_id"]),
            str(kwargs["benchmark_output_dir"]),
            list(kwargs["candidate_specs"]),
        )
        return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()

    def fake_load_deliberation_campaign_matrix_benchmark(matrix_id, **kwargs):
        load_calls.append({"matrix_id": matrix_id, **kwargs})
        output_dir = Path(kwargs["output_dir"])
        payload = json.loads((output_dir / matrix_id / "report.json").read_text(encoding="utf-8"))
        return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()

    def fake_list_deliberation_campaign_matrix_benchmarks(**kwargs):
        list_calls.append(kwargs)
        output_dir = Path(kwargs["output_dir"])
        payload = json.loads((output_dir / "campaign_matrix_demo" / "report.json").read_text(encoding="utf-8"))
        return [type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()]

    monkeypatch.setattr(
        "main.deliberation_campaign_core.run_deliberation_campaign_matrix_benchmark_sync",
        fake_run_deliberation_campaign_matrix_benchmark_sync,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark",
        fake_load_deliberation_campaign_matrix_benchmark,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmarks",
        fake_list_deliberation_campaign_matrix_benchmarks,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "benchmark-deliberation-campaign-matrix",
            "Choose the launch strategy",
            "--baseline-runtime",
            "pydanticai",
            "--candidate-runtime",
            "legacy",
            "--candidate-runtime",
            "pydanticai",
            "--baseline-engine-preference",
            "agentsociety",
            "--candidate-engine-preference",
            "oasis",
            "--candidate-engine-preference",
            "agentsociety",
            "--baseline-campaign-id",
            "campaign_baseline_demo",
            "--candidate-campaign-id",
            "campaign_candidate_alpha",
            "--candidate-campaign-id",
            "campaign_candidate_beta",
            "--candidate-campaign-id",
            "campaign_candidate_gamma",
            "--candidate-campaign-id",
            "campaign_candidate_delta",
            "--matrix-id",
            "campaign_matrix_demo",
            "--campaign-output-dir",
            str(tmp_path / "campaigns"),
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
            "--export-output-dir",
            str(tmp_path / "exports"),
            "--benchmark-output-dir",
            str(tmp_path / "benchmarks"),
            "--format",
            "json",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["matrix_id"] == "campaign_matrix_demo"
    assert payload["baseline_campaign_id"] == "campaign_baseline_demo"
    assert payload["summary"]["candidate_count"] == 4
    assert payload["summary"]["candidate_campaign_ids"] == [
        "campaign_candidate_alpha",
        "campaign_candidate_beta",
        "campaign_candidate_gamma",
        "campaign_candidate_delta",
    ]
    assert payload["summary"]["comparison_ids"] == [
        "campaign_matrix_compare_1",
        "campaign_matrix_compare_2",
        "campaign_matrix_compare_3",
        "campaign_matrix_compare_4",
    ]
    assert payload["entries"][0]["candidate_campaign"]["campaign_id"] == "campaign_candidate_alpha"
    assert payload["entries"][1]["candidate_campaign"]["campaign_id"] == "campaign_candidate_beta"
    assert payload["entries"][2]["candidate_campaign"]["campaign_id"] == "campaign_candidate_gamma"
    assert payload["entries"][3]["candidate_campaign"]["campaign_id"] == "campaign_candidate_delta"
    assert len(matrix_calls) == 1
    assert matrix_calls[0]["baseline_runtime"] == RuntimeBackend.pydanticai
    assert matrix_calls[0]["baseline_engine_preference"] == EnginePreference.agentsociety
    assert matrix_calls[0]["benchmark_id"] == "campaign_matrix_demo"
    assert matrix_calls[0]["baseline_campaign_id"] == "campaign_baseline_demo"
    assert str(matrix_calls[0]["benchmark_output_dir"]).endswith("benchmarks")
    assert len(matrix_calls[0]["candidate_specs"]) == 4
    assert matrix_calls[0]["candidate_specs"][0].campaign_id == "campaign_candidate_alpha"
    assert matrix_calls[0]["candidate_specs"][0].runtime == "legacy"
    assert matrix_calls[0]["candidate_specs"][0].engine_preference == EnginePreference.oasis
    assert matrix_calls[0]["candidate_specs"][1].campaign_id == "campaign_candidate_beta"
    assert matrix_calls[0]["candidate_specs"][1].runtime == "legacy"
    assert matrix_calls[0]["candidate_specs"][1].engine_preference == EnginePreference.agentsociety
    assert matrix_calls[0]["candidate_specs"][2].campaign_id == "campaign_candidate_gamma"
    assert matrix_calls[0]["candidate_specs"][2].runtime == "pydanticai"
    assert matrix_calls[0]["candidate_specs"][2].engine_preference == EnginePreference.oasis
    assert matrix_calls[0]["candidate_specs"][3].campaign_id == "campaign_candidate_delta"
    assert matrix_calls[0]["candidate_specs"][3].runtime == "pydanticai"
    assert matrix_calls[0]["candidate_specs"][3].engine_preference == EnginePreference.agentsociety

    matrix_report_path = tmp_path / "benchmarks" / "campaign_matrix_demo" / "report.json"
    assert matrix_report_path.exists()
    assert len(load_calls) == 0
    assert len(list_calls) == 0

    read_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix",
            "campaign_matrix_demo",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--json",
        ],
    )
    assert read_result.exit_code == 0, read_result.stdout
    read_payload = json.loads(read_result.stdout)
    assert read_payload["matrix_id"] == "campaign_matrix_demo"
    assert read_payload["summary"]["candidate_count"] == 4
    assert len(load_calls) == 1
    assert load_calls[0]["matrix_id"] == "campaign_matrix_demo"
    assert load_calls[0]["output_dir"] == str(tmp_path / "benchmarks")

    list_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrices",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--json",
        ],
    )
    assert list_result.exit_code == 0, list_result.stdout
    list_payload = json.loads(list_result.stdout)
    assert list_payload["count"] == 1
    assert list_payload["matrices"][0]["matrix_id"] == "campaign_matrix_demo"
    assert list_payload["matrices"][0]["summary"]["candidate_campaign_ids"] == [
        "campaign_candidate_alpha",
        "campaign_candidate_beta",
        "campaign_candidate_gamma",
        "campaign_candidate_delta",
    ]
    assert len(list_calls) == 1
    assert list_calls[0]["output_dir"] == str(tmp_path / "benchmarks")


def test_compare_deliberation_campaign_benchmark_matrices_cli_compares_explicit_reports(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    load_calls: list[dict[str, object]] = []
    left_report = {
        "benchmark_id": "matrix_alpha",
        "matrix_id": "matrix_alpha",
        "created_at": "2026-04-08T12:00:00+00:00",
        "output_dir": str(tmp_path / "benchmarks"),
        "report_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
        "baseline_campaign": {"campaign_id": "campaign_baseline_demo", "status": "completed"},
        "baseline_campaign_id": "campaign_baseline_demo",
        "summary": {
            "candidate_count": 3,
            "candidate_campaign_ids": ["campaign_candidate_alpha", "campaign_candidate_beta", "campaign_candidate_gamma"],
            "candidate_labels": ["legacy_oasis", "legacy_agentsociety", "pydanticai_oasis"],
            "comparison_ids": ["cmp_a1", "cmp_a2", "cmp_a3"],
            "comparable_count": 2,
            "mismatch_count": 1,
            "quality_score_mean": 0.71,
            "confidence_level_mean": 0.74,
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
        "entries": [],
    }
    right_report = {
        "benchmark_id": "matrix_beta",
        "matrix_id": "matrix_beta",
        "created_at": "2026-04-07T12:00:00+00:00",
        "output_dir": str(tmp_path / "benchmarks"),
        "report_path": str(tmp_path / "benchmarks" / "matrix_beta" / "report.json"),
        "baseline_campaign": {"campaign_id": "campaign_baseline_demo", "status": "completed"},
        "baseline_campaign_id": "campaign_baseline_demo",
        "summary": {
            "candidate_count": 2,
            "candidate_campaign_ids": ["campaign_candidate_alpha", "campaign_candidate_beta"],
            "candidate_labels": ["legacy_oasis", "legacy_agentsociety"],
            "comparison_ids": ["cmp_b1", "cmp_b2"],
            "comparable_count": 1,
            "mismatch_count": 1,
            "quality_score_mean": 0.63,
            "confidence_level_mean": 0.66,
            "runtime_values": ["legacy"],
            "engine_values": ["oasis"],
        },
        "entries": [],
    }

    def fake_load_deliberation_campaign_matrix_benchmark(matrix_id, **kwargs):
        load_calls.append({"matrix_id": matrix_id, **kwargs})
        if matrix_id == "matrix_alpha":
            return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": left_report})()
        if matrix_id == "matrix_beta":
            return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": right_report})()
        raise AssertionError(f"unexpected matrix id: {matrix_id}")

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmarks",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmark_reports",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark",
        fake_load_deliberation_campaign_matrix_benchmark,
        raising=False,
    )

    text_result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrices",
            "matrix_alpha",
            "matrix_beta",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
        ],
    )
    assert text_result.exit_code == 0, text_result.stdout
    assert "Matrix Benchmark Comparison" in text_result.stdout
    assert "matrix_alpha" in text_result.stdout
    assert "matrix_beta" in text_result.stdout
    assert "quality_mean" in text_result.stdout

    json_result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrices",
            "matrix_alpha",
            "matrix_beta",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
            "--json",
        ],
    )
    assert json_result.exit_code == 0, json_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["comparison_mode"] == "explicit"
    assert payload["left"]["matrix_id"] == "matrix_alpha"
    assert payload["right"]["matrix_id"] == "matrix_beta"
    assert payload["summary"]["comparable"] is False
    assert "candidate_count_mismatch" in payload["summary"]["mismatch_reasons"]
    assert "runtime_mismatch" in payload["summary"]["mismatch_reasons"]
    assert payload["comparison"]["candidate_count_delta"] == 1
    assert round(payload["comparison"]["quality_score_mean_delta"], 3) == 0.08
    assert Path(payload["report_path"]).exists()
    assert len(load_calls) == 4
    assert load_calls[0]["matrix_id"] == "matrix_alpha"
    assert load_calls[1]["matrix_id"] == "matrix_beta"
    assert load_calls[0]["output_dir"] == str(tmp_path / "benchmarks")


def test_compare_deliberation_campaign_benchmark_matrices_cli_latest_uses_listing(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    list_calls: list[dict[str, object]] = []
    latest_reports = [
        {
            "benchmark_id": "matrix_new",
            "matrix_id": "matrix_new",
            "created_at": "2026-04-08T14:00:00+00:00",
            "output_dir": str(tmp_path / "benchmarks"),
            "report_path": str(tmp_path / "benchmarks" / "matrix_new" / "report.json"),
            "baseline_campaign": {"campaign_id": "campaign_baseline_demo", "status": "completed"},
            "baseline_campaign_id": "campaign_baseline_demo",
            "summary": {
                "candidate_count": 2,
                "candidate_campaign_ids": ["campaign_candidate_alpha", "campaign_candidate_beta"],
                "candidate_labels": ["legacy_oasis", "pydanticai_agentsociety"],
                "comparison_ids": ["cmp_new_1", "cmp_new_2"],
                "comparable_count": 2,
                "mismatch_count": 0,
                "quality_score_mean": 0.79,
                "confidence_level_mean": 0.81,
                "runtime_values": ["legacy", "pydanticai"],
                "engine_values": ["agentsociety", "oasis"],
            },
            "entries": [],
        },
        {
            "benchmark_id": "matrix_old",
            "matrix_id": "matrix_old",
            "created_at": "2026-04-07T14:00:00+00:00",
            "output_dir": str(tmp_path / "benchmarks"),
            "report_path": str(tmp_path / "benchmarks" / "matrix_old" / "report.json"),
            "baseline_campaign": {"campaign_id": "campaign_baseline_demo", "status": "completed"},
            "baseline_campaign_id": "campaign_baseline_demo",
            "summary": {
                "candidate_count": 2,
                "candidate_campaign_ids": ["campaign_candidate_alpha", "campaign_candidate_beta"],
                "candidate_labels": ["legacy_oasis", "pydanticai_agentsociety"],
                "comparison_ids": ["cmp_old_1", "cmp_old_2"],
                "comparable_count": 1,
                "mismatch_count": 1,
                "quality_score_mean": 0.68,
                "confidence_level_mean": 0.7,
                "runtime_values": ["legacy", "pydanticai"],
                "engine_values": ["agentsociety", "oasis"],
            },
            "entries": [],
        },
    ]

    def fake_list_deliberation_campaign_matrix_benchmarks(**kwargs):
        list_calls.append(kwargs)
        return [type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json", payload=payload: payload})() for payload in latest_reports]

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmarks",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmark_reports",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmarks",
        fake_list_deliberation_campaign_matrix_benchmarks,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrices",
            "--latest",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--comparison-output-dir",
            str(tmp_path / "comparisons"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison_mode"] == "latest"
    assert payload["latest"] == 2
    assert payload["requested_matrix_ids"] == ["matrix_new", "matrix_old"]
    assert payload["summary"]["comparable"] is True
    assert payload["comparison"]["comparable_count_delta"] == 1
    assert round(payload["comparison"]["quality_score_mean_delta"], 3) == 0.11
    assert Path(payload["report_path"]).exists()
    assert len(list_calls) == 1
    assert list_calls[0]["limit"] == 2
    assert list_calls[0]["output_dir"] == str(tmp_path / "benchmarks")


def test_matrix_benchmark_comparison_cli_reads_and_lists_artifacts(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    load_calls: list[dict[str, object]] = []
    list_calls: list[dict[str, object]] = []
    comparison_payload = {
        "comparison_id": "campaign_matrix_compare_demo",
        "created_at": "2026-04-08T15:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-comparisons"),
        "report_path": str(tmp_path / "matrix-comparisons" / "campaign_matrix_compare_demo" / "report.json"),
        "requested_benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "latest": None,
        "entries": [
            {
                "benchmark_id": "matrix_alpha",
                "created_at": "2026-04-08T12:00:00+00:00",
                "baseline_campaign_id": "campaign_baseline_demo",
                "topic": "Choose the launch strategy",
                "mode": "committee",
                "baseline_runtime": "pydanticai",
                "baseline_engine": "agentsociety",
                "sample_count_requested": 3,
                "stability_runs": 1,
                "candidate_count": 2,
                "candidate_labels": ["legacy_oasis", "pydanticai_agentsociety"],
                "candidate_runtimes": ["legacy", "pydanticai"],
                "candidate_engines": ["agentsociety", "oasis"],
                "candidate_structure_key": "legacy_oasis|pydanticai_agentsociety",
                "comparison_ids": ["cmp_1", "cmp_2"],
                "comparable_count": 2,
                "mismatch_count": 0,
                "quality_score_mean": 0.79,
                "quality_score_min": 0.78,
                "quality_score_max": 0.8,
                "confidence_level_mean": 0.81,
                "confidence_level_min": 0.8,
                "confidence_level_max": 0.82,
                "report_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
            },
            {
                "benchmark_id": "matrix_beta",
                "created_at": "2026-04-08T12:01:00+00:00",
                "baseline_campaign_id": "campaign_baseline_demo",
                "topic": "Choose the launch strategy",
                "mode": "committee",
                "baseline_runtime": "pydanticai",
                "baseline_engine": "agentsociety",
                "sample_count_requested": 3,
                "stability_runs": 1,
                "candidate_count": 3,
                "candidate_labels": ["legacy_oasis", "legacy_agentsociety", "pydanticai_agentsociety"],
                "candidate_runtimes": ["legacy", "pydanticai"],
                "candidate_engines": ["agentsociety", "oasis"],
                "candidate_structure_key": "legacy_agentsociety|legacy_oasis|pydanticai_agentsociety",
                "comparison_ids": ["cmp_3", "cmp_4", "cmp_5"],
                "comparable_count": 3,
                "mismatch_count": 0,
                "quality_score_mean": 0.86,
                "quality_score_min": 0.85,
                "quality_score_max": 0.87,
                "confidence_level_mean": 0.88,
                "confidence_level_min": 0.87,
                "confidence_level_max": 0.89,
                "report_path": str(tmp_path / "benchmarks" / "matrix_beta" / "report.json"),
            },
        ],
        "summary": {
            "benchmark_count": 2,
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "comparable": False,
            "mismatch_reasons": ["candidate_count_mismatch", "candidate_structure_mismatch"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
    }

    def fake_load(comparison_id, **kwargs):
        load_calls.append({"comparison_id": comparison_id, **kwargs})
        return comparison_payload

    def fake_list(**kwargs):
        list_calls.append(kwargs)
        return [comparison_payload]

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_comparison_report",
        fake_load,
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_comparison_reports",
        fake_list,
        raising=False,
    )

    read_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix-comparison",
            "campaign_matrix_compare_demo",
            "--output-dir",
            str(tmp_path / "matrix-comparisons"),
            "--json",
        ],
    )
    assert read_result.exit_code == 0, read_result.stdout
    read_payload = json.loads(read_result.stdout)
    assert read_payload["comparison_id"] == "campaign_matrix_compare_demo"
    assert read_payload["left"]["matrix_id"] == "matrix_alpha"
    assert read_payload["right"]["matrix_id"] == "matrix_beta"
    assert load_calls[0]["output_dir"] == str(tmp_path / "matrix-comparisons")

    list_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrix-comparisons",
            "--output-dir",
            str(tmp_path / "matrix-comparisons"),
            "--json",
        ],
    )
    assert list_result.exit_code == 0, list_result.stdout
    list_payload = json.loads(list_result.stdout)
    assert list_payload["count"] == 1
    assert list_payload["comparisons"][0]["comparison_id"] == "campaign_matrix_compare_demo"
    assert list_calls[0]["output_dir"] == str(tmp_path / "matrix-comparisons")


def test_matrix_benchmark_comparison_cli_audit_export_and_bundle(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    audit_payload = {
        "comparison_id": "campaign_matrix_compare_demo",
        "created_at": "2026-04-08T15:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-comparisons"),
        "report_path": str(tmp_path / "matrix-comparisons" / "campaign_matrix_compare_demo" / "report.json"),
        "benchmark_count": 2,
        "benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "comparable": True,
        "mismatch_reasons": [],
        "summary": {
            "benchmark_count": 2,
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "comparable": True,
            "mismatch_reasons": [],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
        "metadata": {"report_path": str(tmp_path / "matrix-comparisons" / "campaign_matrix_compare_demo" / "report.json")},
        "markdown": "# matrix audit",
    }
    export_payload = {
        "export_id": "campaign_matrix_compare_demo__markdown",
        "created_at": "2026-04-08T15:10:00+00:00",
        "output_dir": str(tmp_path / "matrix-exports"),
        "manifest_path": str(tmp_path / "matrix-exports" / "campaign_matrix_compare_demo__markdown" / "manifest.json"),
        "content_path": str(tmp_path / "matrix-exports" / "campaign_matrix_compare_demo__markdown" / "content.md"),
        "comparison_id": "campaign_matrix_compare_demo",
        "comparison_report_path": audit_payload["report_path"],
        "format": "markdown",
        "benchmark_count": 2,
        "benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "comparable": True,
        "mismatch_reasons": [],
        "content": "# matrix audit",
        "metadata": {
            "manifest_path": str(tmp_path / "matrix-exports" / "campaign_matrix_compare_demo__markdown" / "manifest.json"),
            "content_path": str(tmp_path / "matrix-exports" / "campaign_matrix_compare_demo__markdown" / "content.md"),
            "persisted": True,
        },
    }
    comparison_payload = {
        "comparison_id": "campaign_matrix_compare_demo",
        "created_at": "2026-04-08T15:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-comparisons"),
        "report_path": audit_payload["report_path"],
        "requested_benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "latest": None,
        "entries": [],
        "summary": {
            "benchmark_count": 2,
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "comparable": True,
            "mismatch_reasons": [],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
    }
    bundle_payload = {
        "comparison_report": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "metadata": {
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "latest": None,
            "persisted": True,
            "comparison_output_dir": str(tmp_path / "matrix-comparisons"),
            "export_output_dir": str(tmp_path / "matrix-exports"),
            "format": "markdown",
            "comparison_id": "campaign_matrix_compare_demo",
            "export_id": "campaign_matrix_compare_demo__markdown",
        },
    }

    def payload_object(payload: dict[str, object]) -> object:
        return type("Payload", (), {"model_dump": lambda self, mode="json", payload=payload: payload})()

    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_comparison_audit",
        lambda comparison_id, **kwargs: payload_object(audit_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.materialize_deliberation_campaign_matrix_benchmark_comparison_export",
        lambda audit, **kwargs: payload_object(export_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_comparison_export",
        lambda export_id, **kwargs: payload_object(export_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_comparison_exports",
        lambda **kwargs: [payload_object(export_payload)],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmark_comparison_bundle",
        lambda **kwargs: payload_object(bundle_payload),
        raising=False,
    )

    audit_result = runner.invoke(
        main.app,
        [
            "audit-deliberation-campaign-benchmark-matrix-comparison",
            "campaign_matrix_compare_demo",
            "--output-dir",
            str(tmp_path / "matrix-comparisons"),
            "--json",
        ],
    )
    assert audit_result.exit_code == 0, audit_result.stdout
    audit_json = json.loads(audit_result.stdout)
    assert audit_json["comparison_id"] == "campaign_matrix_compare_demo"
    assert audit_json["benchmark_count"] == 2

    export_result = runner.invoke(
        main.app,
        [
            "export-deliberation-campaign-benchmark-matrix-comparison",
            "campaign_matrix_compare_demo",
            "--comparison-output-dir",
            str(tmp_path / "matrix-comparisons"),
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert export_result.exit_code == 0, export_result.stdout
    export_json = json.loads(export_result.stdout)
    assert export_json["export_id"] == "campaign_matrix_compare_demo__markdown"
    assert export_json["comparison_id"] == "campaign_matrix_compare_demo"

    read_export_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix-comparison-export",
            "campaign_matrix_compare_demo__markdown",
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert read_export_result.exit_code == 0, read_export_result.stdout
    read_export_json = json.loads(read_export_result.stdout)
    assert read_export_json["export_id"] == "campaign_matrix_compare_demo__markdown"
    assert read_export_json["comparison_id"] == "campaign_matrix_compare_demo"

    list_export_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrix-comparison-exports",
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert list_export_result.exit_code == 0, list_export_result.stdout
    list_export_json = json.loads(list_export_result.stdout)
    assert list_export_json["count"] == 1
    assert list_export_json["exports"][0]["export_id"] == "campaign_matrix_compare_demo__markdown"

    bundle_result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrices-audit-export",
            "matrix_alpha",
            "matrix_beta",
            "--output-dir",
            str(tmp_path / "benchmarks"),
            "--comparison-output-dir",
            str(tmp_path / "matrix-comparisons"),
            "--export-output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert bundle_result.exit_code == 0, bundle_result.stdout
    bundle_json = json.loads(bundle_result.stdout)
    assert bundle_json["comparison_id"] == "campaign_matrix_compare_demo"
    assert bundle_json["export_id"] == "campaign_matrix_compare_demo__markdown"
    assert bundle_json["comparison_report"]["comparison_id"] == "campaign_matrix_compare_demo"
    assert bundle_json["audit"]["comparison_id"] == "campaign_matrix_compare_demo"
    assert bundle_json["export"]["export_id"] == "campaign_matrix_compare_demo__markdown"


def test_matrix_benchmark_export_comparison_cli_audit_export_and_exports(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    comparison_payload = {
        "comparison_id": "campaign_matrix_export_compare_demo",
        "created_at": "2026-04-08T15:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-export-comparisons"),
        "report_path": str(tmp_path / "matrix-export-comparisons" / "campaign_matrix_export_compare_demo" / "report.json"),
        "requested_export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
        "latest": None,
        "entries": [],
        "summary": {
            "export_count": 2,
            "export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "format_values": ["json", "markdown"],
            "comparable": True,
            "mismatch_reasons": [],
            "quality_score_mean": 0.77,
            "confidence_level_mean": 0.74,
        },
    }
    audit_payload = {
        "comparison_id": "campaign_matrix_export_compare_demo",
        "created_at": "2026-04-08T15:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-export-comparisons"),
        "report_path": comparison_payload["report_path"],
        "requested_export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
        "latest": None,
        "export_count": 2,
        "export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
        "comparable": True,
        "mismatch_reasons": [],
        "entries": [],
        "summary": comparison_payload["summary"],
        "markdown": "# export comparison",
    }
    export_payload = {
        "export_id": "campaign_matrix_export_compare_demo__markdown",
        "created_at": "2026-04-08T15:05:00+00:00",
        "output_dir": str(tmp_path / "matrix-export-comparison-exports"),
        "manifest_path": str(
            tmp_path / "matrix-export-comparison-exports" / "campaign_matrix_export_compare_demo__markdown" / "manifest.json"
        ),
        "content_path": str(
            tmp_path / "matrix-export-comparison-exports" / "campaign_matrix_export_compare_demo__markdown" / "content.md"
        ),
        "comparison_id": "campaign_matrix_export_compare_demo",
        "comparison_report_path": comparison_payload["report_path"],
        "format": "markdown",
        "export_count": 2,
        "export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
        "comparable": True,
        "mismatch_reasons": [],
        "content": "# export comparison",
    }
    bundle_payload = {
        "comparison_report": comparison_payload,
        "audit": audit_payload,
        "export": export_payload,
        "metadata": {
            "export_ids": ["matrix_alpha__markdown", "matrix_beta__json"],
            "latest": None,
            "persisted": True,
            "comparison_output_dir": str(tmp_path / "matrix-export-comparisons"),
            "export_output_dir": str(tmp_path / "matrix-export-comparison-exports"),
            "format": "markdown",
            "comparison_id": "campaign_matrix_export_compare_demo",
            "export_id": "campaign_matrix_export_compare_demo__markdown",
        },
    }

    def payload_object(payload: dict[str, object]) -> object:
        return type("Payload", (), {"model_dump": lambda self, mode="json", payload=payload: payload})()

    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmark_exports",
        lambda **kwargs: payload_object(comparison_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_export_comparison_report",
        lambda comparison_id, **kwargs: payload_object(comparison_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_export_comparison_reports",
        lambda **kwargs: [payload_object(comparison_payload)],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_export_comparison_audit",
        lambda comparison_id, **kwargs: payload_object(audit_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.materialize_deliberation_campaign_matrix_benchmark_export_comparison_export",
        lambda audit, **kwargs: payload_object(export_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.load_deliberation_campaign_matrix_benchmark_export_comparison_export",
        lambda export_id, **kwargs: payload_object(export_payload),
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_export_comparison_exports",
        lambda **kwargs: [payload_object(export_payload)],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle",
        lambda **kwargs: payload_object(bundle_payload),
        raising=False,
    )

    compare_result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrix-exports",
            "matrix_alpha__markdown",
            "matrix_beta__json",
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--comparison-output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--json",
        ],
    )
    assert compare_result.exit_code == 0, compare_result.stdout
    assert json.loads(compare_result.stdout)["comparison_id"] == "campaign_matrix_export_compare_demo"

    audit_result = runner.invoke(
        main.app,
        [
            "audit-deliberation-campaign-benchmark-matrix-export-comparison",
            "campaign_matrix_export_compare_demo",
            "--output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--json",
        ],
    )
    assert audit_result.exit_code == 0, audit_result.stdout
    assert json.loads(audit_result.stdout)["comparison_id"] == "campaign_matrix_export_compare_demo"

    export_result = runner.invoke(
        main.app,
        [
            "export-deliberation-campaign-benchmark-matrix-export-comparison",
            "campaign_matrix_export_compare_demo",
            "--comparison-output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--output-dir",
            str(tmp_path / "matrix-export-comparison-exports"),
            "--json",
        ],
    )
    assert export_result.exit_code == 0, export_result.stdout
    assert json.loads(export_result.stdout)["export_id"] == "campaign_matrix_export_compare_demo__markdown"

    read_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix-export-comparison",
            "campaign_matrix_export_compare_demo",
            "--output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--json",
        ],
    )
    assert read_result.exit_code == 0, read_result.stdout
    assert json.loads(read_result.stdout)["comparison_id"] == "campaign_matrix_export_compare_demo"

    list_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrix-export-comparisons",
            "--output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--json",
        ],
    )
    assert list_result.exit_code == 0, list_result.stdout
    assert json.loads(list_result.stdout)["count"] == 1

    read_export_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix-export-comparison-export",
            "campaign_matrix_export_compare_demo__markdown",
            "--output-dir",
            str(tmp_path / "matrix-export-comparison-exports"),
            "--json",
        ],
    )
    assert read_export_result.exit_code == 0, read_export_result.stdout
    assert json.loads(read_export_result.stdout)["export_id"] == "campaign_matrix_export_compare_demo__markdown"

    list_export_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrix-export-comparison-exports",
            "--output-dir",
            str(tmp_path / "matrix-export-comparison-exports"),
            "--json",
        ],
    )
    assert list_export_result.exit_code == 0, list_export_result.stdout
    assert json.loads(list_export_result.stdout)["count"] == 1

    bundle_result = runner.invoke(
        main.app,
        [
            "compare-deliberation-campaign-benchmark-matrix-exports-audit-export",
            "matrix_alpha__markdown",
            "matrix_beta__json",
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--comparison-output-dir",
            str(tmp_path / "matrix-export-comparisons"),
            "--export-output-dir",
            str(tmp_path / "matrix-export-comparison-exports"),
            "--json",
        ],
    )
    assert bundle_result.exit_code == 0, bundle_result.stdout
    bundle_json = json.loads(bundle_result.stdout)
    assert bundle_json["comparison_id"] == "campaign_matrix_export_compare_demo"
    assert bundle_json["export_id"] == "campaign_matrix_export_compare_demo__markdown"


def test_matrix_benchmark_cli_audit_export_and_exports(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    load_calls: list[dict[str, object]] = []

    fake_report = {
        "matrix_id": "matrix_alpha",
        "benchmark_id": "benchmark_matrix_alpha",
        "created_at": "2026-04-08T12:30:00+00:00",
        "baseline_campaign_id": "campaign_baseline_demo",
        "baseline_campaign": {"campaign_id": "campaign_baseline_demo"},
        "output_dir": str(tmp_path / "matrix-benchmarks"),
        "report_path": str(tmp_path / "matrix-benchmarks" / "matrix_alpha" / "report.json"),
        "entries": [
            {
                "candidate_index": 1,
                "candidate_label": "pydanticai__agentsociety",
                "candidate_spec": {
                    "label": "pydanticai__agentsociety",
                    "campaign_id": "campaign_alpha",
                    "runtime": "pydanticai",
                    "engine_preference": "agentsociety",
                },
                "candidate_campaign": {"campaign_id": "campaign_alpha"},
                "comparison_bundle": {
                    "comparison_report": {
                        "comparison_id": "comparison_alpha",
                        "summary": {
                            "comparable": True,
                            "quality_score_mean": 0.91,
                            "confidence_level_mean": 0.89,
                            "mismatch_reasons": [],
                        },
                    },
                    "export": {"export_id": "comparison_alpha__markdown"},
                },
            },
            {
                "candidate_index": 2,
                "candidate_label": "legacy__agentsociety",
                "candidate_spec": {
                    "label": "legacy__agentsociety",
                    "campaign_id": "campaign_beta",
                    "runtime": "legacy",
                    "engine_preference": "agentsociety",
                },
                "candidate_campaign": {"campaign_id": "campaign_beta"},
                "comparison_bundle": {
                    "comparison_report": {
                        "comparison_id": "comparison_beta",
                        "summary": {
                            "comparable": False,
                            "quality_score_mean": 0.77,
                            "confidence_level_mean": 0.8,
                            "mismatch_reasons": ["runtime_mismatch"],
                        },
                    },
                    "export": {"export_id": "comparison_beta__markdown"},
                },
            },
            {
                "candidate_index": 3,
                "candidate_label": "pydanticai__oasis",
                "candidate_spec": {
                    "label": "pydanticai__oasis",
                    "campaign_id": "campaign_gamma",
                    "runtime": "pydanticai",
                    "engine_preference": "oasis",
                },
                "candidate_campaign": {"campaign_id": "campaign_gamma"},
                "comparison_bundle": {
                    "comparison_report": {
                        "comparison_id": "comparison_gamma",
                        "summary": {
                            "comparable": True,
                            "quality_score_mean": 0.88,
                            "confidence_level_mean": 0.86,
                            "mismatch_reasons": [],
                        },
                    },
                    "export": {"export_id": "comparison_gamma__markdown"},
                },
            },
        ],
        "summary": {
            "candidate_count": 3,
            "candidate_labels": ["pydanticai__agentsociety", "legacy__agentsociety", "pydanticai__oasis"],
            "candidate_campaign_ids": ["campaign_alpha", "campaign_beta", "campaign_gamma"],
            "comparison_ids": ["comparison_alpha", "comparison_beta", "comparison_gamma"],
            "comparable_count": 2,
            "mismatch_count": 1,
            "quality_score_mean": 0.8533333333333334,
            "quality_score_min": 0.77,
            "quality_score_max": 0.91,
            "confidence_level_mean": 0.85,
            "confidence_level_min": 0.8,
            "confidence_level_max": 0.89,
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
    }

    def fake_load(matrix_id, **kwargs):
        load_calls.append({"matrix_id": matrix_id, **kwargs})
        return fake_report

    monkeypatch.setattr("main._load_deliberation_campaign_benchmark_matrix_report", fake_load, raising=False)

    audit_result = runner.invoke(
        main.app,
        [
            "audit-deliberation-campaign-benchmark-matrix",
            "matrix_alpha",
            "--output-dir",
            str(tmp_path / "matrix-benchmarks"),
            "--json",
        ],
    )
    assert audit_result.exit_code == 0, audit_result.stdout
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["matrix_id"] == "matrix_alpha"
    assert audit_payload["summary"]["candidate_count"] == 3
    assert audit_payload["best_candidate"]["candidate_label"] == "pydanticai__agentsociety"
    assert audit_payload["worst_candidate"]["candidate_label"] == "legacy__agentsociety"
    assert [row["candidate_label"] for row in audit_payload["leaderboard"]] == [
        "pydanticai__agentsociety",
        "pydanticai__oasis",
        "legacy__agentsociety",
    ]
    assert load_calls[0]["output_dir"] == str(tmp_path / "matrix-benchmarks")

    export_result = runner.invoke(
        main.app,
        [
            "export-deliberation-campaign-benchmark-matrix",
            "matrix_alpha",
            "--benchmark-output-dir",
            str(tmp_path / "matrix-benchmarks"),
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert export_result.exit_code == 0, export_result.stdout
    export_payload = json.loads(export_result.stdout)
    assert export_payload["export_id"] == "matrix_benchmark_audit__matrix_alpha__markdown"
    assert Path(export_payload["manifest_path"]).is_file()
    assert Path(export_payload["content_path"]).is_file()

    read_export_result = runner.invoke(
        main.app,
        [
            "read-deliberation-campaign-benchmark-matrix-export",
            export_payload["export_id"],
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert read_export_result.exit_code == 0, read_export_result.stdout
    read_export_payload = json.loads(read_export_result.stdout)
    assert read_export_payload["export_id"] == export_payload["export_id"]
    assert read_export_payload["matrix_id"] == "matrix_alpha"
    assert read_export_payload["best_candidate"]["candidate_label"] == "pydanticai__agentsociety"

    list_export_result = runner.invoke(
        main.app,
        [
            "list-deliberation-campaign-benchmark-matrix-exports",
            "--output-dir",
            str(tmp_path / "matrix-exports"),
            "--json",
        ],
    )
    assert list_export_result.exit_code == 0, list_export_result.stdout
    list_export_payload = json.loads(list_export_result.stdout)
    assert list_export_payload["count"] == 1
    assert list_export_payload["exports"][0]["export_id"] == export_payload["export_id"]


def test_deliberation_campaign_index_cli_aggregates_recent_artifacts(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_reports",
        lambda **kwargs: [
            {
                "campaign_id": "campaign_alpha",
                "status": "completed",
                "created_at": "2026-04-08T10:00:00+00:00",
                "topic": "Choose the launch strategy",
                "objective": "Define the best strategy",
                "mode": "committee",
                "sample_count_requested": 3,
                "summary": {
                    "sample_count_completed": 3,
                    "sample_count_failed": 0,
                },
                "fallback_guard_applied": True,
                "fallback_guard_reason": "fallback_disabled_for_repeated_campaign_comparison",
                "report_path": str(tmp_path / "campaigns" / "campaign_alpha" / "report.json"),
                "output_dir": str(tmp_path / "campaigns"),
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_comparison_reports",
        lambda **kwargs: [
            {
                "comparison_id": "comparison_alpha",
                "created_at": "2026-04-08T11:00:00+00:00",
                "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
                "latest": None,
                "summary": {
                    "campaign_count": 2,
                    "comparable": True,
                    "mismatch_reasons": [],
                    "comparison_key_values": ["key_alpha"],
                },
                "metadata": {"comparison_key": "key_alpha", "report_path": str(tmp_path / "comparisons" / "comparison_alpha" / "report.json")},
                "output_dir": str(tmp_path / "comparisons"),
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_comparison_exports",
        lambda **kwargs: [
            {
                "export_id": "comparison_alpha__json",
                "comparison_id": "comparison_alpha",
                "format": "json",
                "created_at": "2026-04-08T11:30:00+00:00",
                "content_path": str(tmp_path / "exports" / "comparison_alpha__json" / "content.json"),
                "manifest_path": str(tmp_path / "exports" / "comparison_alpha__json" / "manifest.json"),
                "output_dir": str(tmp_path / "exports"),
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_benchmarks",
        lambda **kwargs: [
            {
                "benchmark_id": "benchmark_alpha",
                "created_at": "2026-04-08T12:00:00+00:00",
                "baseline_campaign_id": "campaign_alpha",
                "candidate_campaign_id": "campaign_beta",
                "comparison_id": "comparison_alpha",
                "export_id": "comparison_alpha__json",
                "format": "json",
                "summary": {
                    "candidate_count": 1,
                    "candidate_campaign_ids": ["campaign_beta"],
                    "candidate_labels": ["legacy__oasis"],
                    "comparable_count": 1,
                    "mismatch_count": 0,
                },
                "report_path": str(tmp_path / "benchmarks" / "benchmark_alpha" / "report.json"),
                "output_dir": str(tmp_path / "benchmarks"),
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmarks",
        lambda **kwargs: [
                {
                    "benchmark_id": "benchmark_matrix_alpha",
                    "matrix_id": "matrix_alpha",
                    "created_at": "2026-04-08T12:30:00+00:00",
                    "baseline_campaign_id": "campaign_alpha",
                "candidate_count": 2,
                "candidate_campaign_ids": ["campaign_beta", "campaign_gamma"],
                "candidate_labels": ["legacy__oasis", "pydanticai__agentsociety"],
                "comparison_ids": ["comparison_beta", "comparison_gamma"],
                    "benchmark_ids": ["campaign_alpha__vs__campaign_beta", "campaign_alpha__vs__campaign_gamma"],
                    "entries": [
                        {
                            "candidate_campaign": {"campaign_id": "campaign_beta"},
                            "comparison_bundle": {
                                "comparison_report": {"comparison_id": "comparison_beta", "summary": {"comparable": True}},
                                "export": {"export_id": "comparison_beta__json"},
                            },
                        },
                        {
                            "candidate_campaign": {"campaign_id": "campaign_gamma"},
                            "comparison_bundle": {
                                "comparison_report": {"comparison_id": "comparison_gamma", "summary": {"comparable": True}},
                                "export": {"export_id": "comparison_gamma__json"},
                            },
                        },
                    ],
                    "summary": {
                        "candidate_count": 2,
                        "candidate_campaign_ids": ["campaign_beta", "campaign_gamma"],
                        "candidate_labels": ["legacy__oasis", "pydanticai__agentsociety"],
                        "comparable_count": 2,
                    "mismatch_count": 0,
                },
                "report_path": str(tmp_path / "matrix_benchmarks" / "matrix_alpha" / "report.json"),
                "output_dir": str(tmp_path / "matrix_benchmarks"),
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_exports",
        lambda **kwargs: [
            SimpleNamespace(
                export_id="matrix_alpha__markdown",
                benchmark_id="benchmark_matrix_alpha",
                created_at=datetime(2026, 4, 8, 12, 40, tzinfo=timezone.utc),
                format="markdown",
                candidate_count=2,
                candidate_labels=["legacy__oasis", "pydanticai__agentsociety"],
                candidate_campaign_ids=["campaign_beta", "campaign_gamma"],
                comparison_ids=["comparison_beta", "comparison_gamma"],
                comparable=True,
                comparable_count=2,
                mismatch_count=0,
                quality_score_mean=0.79,
                confidence_level_mean=0.76,
                best_candidate_label="pydanticai__agentsociety",
                worst_candidate_label="legacy__oasis",
                content_path=str(tmp_path / "matrix_benchmark_exports" / "matrix_alpha__markdown" / "content.md"),
                manifest_path=str(tmp_path / "matrix_benchmark_exports" / "matrix_alpha__markdown" / "manifest.json"),
                output_dir=str(tmp_path / "matrix_benchmark_exports"),
            )
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_EXPORT_OUTPUT_DIR",
        tmp_path / "matrix_benchmark_comparison_exports",
        raising=False,
    )
    monkeypatch.setattr(
        "main.deliberation_campaign_core.list_deliberation_campaign_matrix_benchmark_comparison_exports",
        lambda **kwargs: [
            {
                "export_id": "matrix_comparison_alpha__markdown",
                "comparison_id": "matrix_comparison_alpha",
                "created_at": "2026-04-08T12:45:00+00:00",
                "format": "markdown",
                "output_dir": str(tmp_path / "matrix_benchmark_comparison_exports"),
                "manifest_path": str(
                    tmp_path
                    / "matrix_benchmark_comparison_exports"
                    / "matrix_comparison_alpha__markdown"
                    / "manifest.json"
                ),
                "content_path": str(
                    tmp_path
                    / "matrix_benchmark_comparison_exports"
                    / "matrix_comparison_alpha__markdown"
                    / "content.md"
                ),
                "comparison_report_path": str(
                    tmp_path / "matrix-comparisons" / "matrix_comparison_alpha" / "report.json"
                ),
            }
        ],
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "deliberation-campaign-index",
            "--limit",
            "1",
            "--matrix-benchmark-export-output-dir",
            str(tmp_path / "matrix_benchmark_exports"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["limit"] == 1
    assert payload["counts"] == {
        "campaigns": 1,
        "comparisons": 1,
        "exports": 1,
        "benchmarks": 1,
        "matrix_benchmarks": 1,
        "matrix_benchmark_exports": 1,
        "matrix_benchmark_comparisons": 0,
        "matrix_benchmark_comparison_exports": 1,
    }
    assert payload["recent"]["campaigns"][0]["campaign_id"] == "campaign_alpha"
    assert payload["recent"]["comparisons"][0]["comparison_id"] == "comparison_alpha"
    assert payload["recent"]["exports"][0]["export_id"] == "comparison_alpha__json"
    assert payload["recent"]["benchmarks"][0]["benchmark_id"] == "benchmark_alpha"
    assert payload["recent"]["benchmarks"][0]["candidate_campaign_id"] == "campaign_beta"
    assert payload["recent"]["matrix_benchmarks"][0]["benchmark_id"] == "benchmark_matrix_alpha"
    assert payload["recent"]["matrix_benchmarks"][0]["matrix_id"] == "matrix_alpha"
    assert payload["recent"]["matrix_benchmarks"][0]["candidate_count"] == 2
    assert payload["recent"]["matrix_benchmarks"][0]["benchmark_ids"] == [
        "campaign_alpha__vs__campaign_beta",
        "campaign_alpha__vs__campaign_gamma",
    ]
    assert payload["recent"]["matrix_benchmark_exports"][0]["export_id"] == "matrix_alpha__markdown"
    assert payload["recent"]["matrix_benchmark_exports"][0]["best_candidate_label"] == "pydanticai__agentsociety"
    assert payload["recent"]["matrix_benchmark_comparison_exports"][0]["export_id"] == "matrix_comparison_alpha__markdown"


def test_deliberation_campaign_dashboard_cli_json(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def fake_build_deliberation_campaign_dashboard(**kwargs):
        calls.append(kwargs)
        assert kwargs["limit"] == 3
        assert kwargs["sort_by"] == "kind"
        assert kwargs["comparable_only"] is True
        assert kwargs["campaign_status"] is main.DeliberationCampaignStatus.completed
        assert kwargs["kinds"] == [
            "campaign",
            "comparison",
            "benchmark",
            "matrix_benchmark_export",
            "matrix_benchmark_comparison_export",
        ]
        assert kwargs["matrix_benchmark_export_output_dir"] == str(tmp_path / "matrix_benchmark_exports")
        return {
            "ok": True,
            "limit": kwargs["limit"],
            "sort_by": kwargs["sort_by"],
            "kinds": kwargs["kinds"],
            "campaign_status": "completed",
            "comparable_only": True,
            "counts": {
                "total": 6,
                "campaigns": 1,
                "comparisons": 1,
                "exports": 0,
                "benchmarks": 1,
                "matrix_benchmarks": 1,
                "matrix_benchmark_exports": 1,
                "matrix_benchmark_comparisons": 0,
                "matrix_benchmark_comparison_exports": 1,
            },
            "rows": [
                {
                    "artifact_kind": "campaign",
                    "artifact_id": "campaign_alpha",
                    "created_at": "2026-04-08T10:00:00+00:00",
                    "status": "completed",
                    "comparable": True,
                    "quality_score_mean": 0.84,
                    "confidence_level_mean": 0.81,
                    "runtime_summary": {"pydanticai": 2},
                    "engine_summary": {"agentsociety": 2},
                    "artifact_path": str(tmp_path / "campaigns" / "campaign_alpha" / "report.json"),
                    "output_dir": str(tmp_path / "campaigns"),
                    "comparison_key": "key_alpha",
                },
                {
                    "artifact_kind": "comparison",
                    "artifact_id": "comparison_alpha",
                    "created_at": "2026-04-08T11:00:00+00:00",
                    "status": "comparison",
                    "comparable": True,
                    "quality_score_mean": 0.73,
                    "confidence_level_mean": 0.69,
                    "runtime_summary": {"completed": 2},
                    "engine_summary": {"agentsociety": 1},
                    "artifact_path": str(tmp_path / "comparisons" / "comparison_alpha" / "report.json"),
                    "output_dir": str(tmp_path / "comparisons"),
                    "comparison_key": "key_alpha",
                },
                {
                    "artifact_kind": "benchmark",
                    "artifact_id": "matrix_alpha",
                    "created_at": "2026-04-08T12:00:00+00:00",
                    "status": "benchmark",
                    "comparable": True,
                    "quality_score_mean": 0.77,
                    "confidence_level_mean": 0.75,
                    "runtime_summary": {"baseline": "pydanticai", "candidate": "legacy"},
                    "engine_summary": {"baseline": "agentsociety", "candidate": "oasis"},
                    "artifact_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
                    "output_dir": str(tmp_path / "benchmarks"),
                    "comparison_key": "key_alpha",
                },
                {
                    "artifact_kind": "matrix_benchmark",
                    "artifact_id": "matrix_alpha",
                    "created_at": "2026-04-08T12:30:00+00:00",
                    "status": "matrix_benchmark",
                    "comparable": True,
                    "quality_score_mean": 0.79,
                    "confidence_level_mean": 0.76,
                    "runtime_summary": {"pydanticai": 1, "legacy": 1},
                    "engine_summary": {"agentsociety": 1, "oasis": 1},
                    "artifact_path": str(tmp_path / "matrix_benchmarks" / "matrix_alpha" / "report.json"),
                    "output_dir": str(tmp_path / "matrix_benchmarks"),
                    "comparison_key": "key_alpha",
                },
                {
                    "artifact_kind": "matrix_benchmark_export",
                    "artifact_id": "matrix_alpha__markdown",
                    "created_at": "2026-04-08T12:40:00+00:00",
                    "status": "markdown",
                    "comparable": True,
                    "quality_score_mean": 0.79,
                    "confidence_level_mean": 0.76,
                    "runtime_summary": None,
                    "engine_summary": None,
                    "artifact_path": str(
                        tmp_path / "matrix_benchmark_exports" / "matrix_alpha__markdown" / "content.md"
                    ),
                    "output_dir": str(tmp_path / "matrix_benchmark_exports"),
                    "comparison_key": None,
                },
                {
                    "artifact_kind": "matrix_benchmark_comparison_export",
                    "artifact_id": "matrix_comparison_alpha__markdown",
                    "created_at": "2026-04-08T12:45:00+00:00",
                    "status": "markdown",
                    "comparable": None,
                    "quality_score_mean": None,
                    "confidence_level_mean": None,
                    "runtime_summary": None,
                    "engine_summary": None,
                    "artifact_path": str(
                        tmp_path
                        / "matrix_benchmark_comparison_exports"
                        / "matrix_comparison_alpha__markdown"
                        / "content.md"
                    ),
                    "output_dir": str(tmp_path / "matrix_benchmark_comparison_exports"),
                    "comparison_key": None,
                },
            ],
            "output_dirs": {
                "campaigns": str(tmp_path / "campaigns"),
                "comparisons": str(tmp_path / "comparisons"),
                "exports": str(tmp_path / "exports"),
                "benchmarks": str(tmp_path / "benchmarks"),
                "matrix_benchmark_exports": str(tmp_path / "matrix_benchmark_exports"),
                "matrix_benchmark_comparison_exports": str(tmp_path / "matrix_benchmark_comparison_exports"),
            },
        }

    monkeypatch.setattr(
        "main.deliberation_campaign_core.build_deliberation_campaign_dashboard",
        fake_build_deliberation_campaign_dashboard,
        raising=False,
    )

    result = runner.invoke(
        main.app,
        [
            "deliberation-campaign-dashboard",
            "--kind",
            "campaign",
            "--kind",
            "comparison",
            "--kind",
            "benchmark",
            "--kind",
            "matrix_benchmark_export",
            "--kind",
            "matrix_benchmark_comparison_export",
            "--limit",
            "3",
            "--sort-by",
            "kind",
            "--campaign-status",
            "completed",
            "--comparable-only",
            "--matrix-benchmark-export-output-dir",
            str(tmp_path / "matrix_benchmark_exports"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["limit"] == 3
    assert payload["sort_by"] == "kind"
    assert payload["kinds"] == [
        "campaign",
        "comparison",
        "benchmark",
        "matrix_benchmark_export",
        "matrix_benchmark_comparison_export",
    ]
    assert payload["campaign_status"] == "completed"
    assert payload["comparable_only"] is True
    assert payload["counts"] == {
        "total": 6,
        "campaigns": 1,
        "comparisons": 1,
        "exports": 0,
        "benchmarks": 1,
        "matrix_benchmarks": 1,
        "matrix_benchmark_exports": 1,
        "matrix_benchmark_comparisons": 0,
        "matrix_benchmark_comparison_exports": 1,
    }
    assert [row["artifact_kind"] for row in payload["rows"]] == [
        "campaign",
        "comparison",
        "benchmark",
        "matrix_benchmark",
        "matrix_benchmark_export",
        "matrix_benchmark_comparison_export",
    ]
    assert payload["rows"][0]["artifact_id"] == "campaign_alpha"
    assert payload["rows"][0]["quality_score_mean"] == 0.84
    assert payload["rows"][1]["artifact_id"] == "comparison_alpha"
    assert payload["rows"][1]["comparable"] is True
    assert payload["rows"][2]["artifact_id"] == "matrix_alpha"
    assert payload["rows"][2]["comparable"] is True
    assert payload["rows"][3]["artifact_id"] == "matrix_alpha"
    assert payload["rows"][3]["comparable"] is True
    assert payload["rows"][4]["artifact_id"] == "matrix_alpha__markdown"
    assert payload["rows"][4]["comparable"] is True
    assert payload["rows"][5]["artifact_id"] == "matrix_comparison_alpha__markdown"
    assert payload["rows"][5]["comparable"] is None
    assert len(calls) == 1


def test_improve_cli_text_summary_includes_resilience_diagnostics(monkeypatch) -> None:
    buffer = _install_buffered_console(monkeypatch)
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)

    inspection_resilience = {
        "status": "guarded",
        "score": 0.91,
        "source_stage": "inspection",
        "stage_count": 1,
        "attempt_count": 1,
        "retry_count": 0,
        "fallback_used": False,
        "summary": "preferred runtime stayed healthy",
    }
    round_resilience = {
        "status": "degraded",
        "score": 0.67,
        "source_stage": "round",
        "stage_count": 2,
        "degraded_reasons": ["fallback_used", "runtime_error"],
        "attempt_count": 2,
        "retry_count": 1,
        "fallback_used": False,
        "summary": "recovered after one retry",
    }

    class ResilienceController(FakeController):
        def inspect_target(self, target: str, **kwargs):
            inspection = super().inspect_target(target, **kwargs)
            inspection.metadata.update(
                {
                    "runtime_resilience": inspection_resilience,
                    "comparability": {
                        "runtime_resilience_status": "guarded",
                        "runtime_resilience_score": 0.91,
                        "runtime_resilience_attempt_count": 1,
                        "runtime_resilience_retry_count": 0,
                        "runtime_resilience_fallback_used": False,
                    },
                    "quality_warnings": ["runtime_fallback_used"],
                }
            )
            return inspection

        def run_round(self, target: str, mode: LoopMode, **kwargs):
            record = super().run_round(target, mode, **kwargs)
            record.metadata.update(
                {
                    "runtime_resilience": round_resilience,
                    "comparability": {
                        "runtime_resilience_status": "degraded",
                        "runtime_resilience_score": 0.67,
                        "runtime_resilience_attempt_count": 2,
                        "runtime_resilience_retry_count": 1,
                        "runtime_resilience_fallback_used": False,
                    },
                    "quality_warnings": ["runtime_fallback_used", "runtime_error"],
                }
            )
            return record

        def run_loop(self, target: str, mode: LoopMode, max_rounds: int, **kwargs):
            record = self.run_round(target, mode, **kwargs)
            return SimpleNamespace(
                target_id=target,
                mode=mode,
                max_rounds=max_rounds,
                completed_rounds=1,
                rounds=[record],
                stopped_reason="bounded",
            )

    monkeypatch.setattr("main._get_improvement_controller", lambda **kwargs: ResilienceController())

    main.improve_inspect(target="harness", json_output=False)
    inspect_output = buffer.getvalue()
    assert "Resilience:" in inspect_output
    assert "status=guarded" in inspect_output
    assert "score=0.910" in inspect_output
    assert "stage=inspection" in inspect_output
    assert "attempts=1" in inspect_output

    buffer.truncate(0)
    buffer.seek(0)
    main.improve_round(target="harness", mode=LoopMode.suggest_only, json_output=False)
    round_output = buffer.getvalue()
    assert "Resilience:" in round_output
    assert "status=degraded" in round_output
    assert "cause=fallback_used,runtime_error" in round_output
    assert "attempts=2" in round_output

    buffer.truncate(0)
    buffer.seek(0)
    main.improve_loop(target="harness", mode=LoopMode.suggest_only, max_rounds=2, json_output=False)
    loop_output = buffer.getvalue()
    assert "Resilience:" in loop_output
    assert "status=degraded" in loop_output
    assert "cause=fallback_used,runtime_error" in loop_output
    assert "Last Decision:" in loop_output


def test_meeting_cli_smoke_falls_back_to_legacy_when_pydanticai_runtime_is_unavailable(monkeypatch) -> None:
    runner = CliRunner()
    calls = []

    def fake_run_strategy_meeting_sync(**kwargs):
        calls.append(kwargs)
        if kwargs["runtime"] == RuntimeBackend.pydanticai.value:
            raise RuntimeError("pydanticai unavailable")
        return StrategyMeetingResult(
            meeting_id="meeting_demo",
            topic=kwargs["topic"],
            objective=kwargs.get("objective") or "Define the best strategy for the topic",
            status=StrategyMeetingStatus.completed,
            participants=list(kwargs.get("participants") or []),
            requested_participants=list(kwargs.get("participants") or []),
            requested_max_agents=kwargs.get("max_agents", 0),
            requested_rounds=kwargs.get("rounds", 0),
            rounds_completed=kwargs.get("rounds", 0),
            strategy="Adopt a cautious rollout.",
            consensus_points=["Protect reliability"],
            dissent_points=["Some prefer speed"],
            next_actions=["Define the canary gates"],
            metadata={"runtime_used": RuntimeBackend.legacy.value, "fallback_used": True},
        )

    monkeypatch.setattr("swarm_core.strategy_meeting.run_strategy_meeting_sync", fake_run_strategy_meeting_sync)

    result = runner.invoke(
        main.app,
        [
            "meeting",
            "Choose the product launch approach",
            "--participant",
            "architect",
            "--participant",
            "veille-strategique",
            "--max-agents",
            "2",
            "--rounds",
            "1",
            "--no-persist",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert len(calls) == 2
    assert calls[0]["runtime"] == RuntimeBackend.pydanticai.value
    assert calls[1]["runtime"] == RuntimeBackend.legacy.value
    assert payload["metadata"]["runtime_requested"] == RuntimeBackend.pydanticai.value
    assert payload["metadata"]["runtime_used"] == RuntimeBackend.legacy.value
    assert payload["metadata"]["fallback_used"] is True
    assert payload["metadata"]["runtime_error"] == "pydanticai unavailable"


def test_meeting_cli_no_fallback_surfaces_runtime_failure(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "main.run_strategy_meeting_runtime",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("pydanticai unavailable")),
    )

    result = runner.invoke(
        main.app,
        [
            "meeting",
            "Choose the product launch approach",
            "--no-allow-fallback",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "pydanticai unavailable" in (result.stdout or str(result.exception))


def test_deliberate_cli_smoke_emits_json_payload(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "main.run_deliberation_runtime",
        lambda **kwargs: DeliberationResult(
            deliberation_id="delib_demo",
            topic=kwargs["topic"],
            objective=kwargs.get("objective") or "Define the best strategy",
            mode=DeliberationMode.hybrid,
            status=DeliberationStatus.completed,
            runtime_requested=RuntimeBackend.pydanticai.value,
            runtime_used=RuntimeBackend.pydanticai.value,
            fallback_used=False,
            engine_requested="agentsociety",
            engine_used="agentsociety",
            summary="Population reaction is cautious but positive.",
            final_strategy="Roll out in stages.",
            confidence_level=0.72,
        ),
    )

    result = runner.invoke(
        main.app,
        [
            "deliberate",
            "Choose the product launch approach",
            "--mode",
            "hybrid",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "hybrid"
    assert payload["status"] == "completed"
    assert payload["runtime_used"] == RuntimeBackend.pydanticai.value
    assert payload["engine_used"] == "agentsociety"


def test_meeting_cli_text_summary_includes_compact_quality_and_comparability(monkeypatch) -> None:
    buffer = _install_buffered_console(monkeypatch)
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "main.run_strategy_meeting_runtime",
        lambda **kwargs: SimpleNamespace(
            meeting_id="meeting_demo",
            status=StrategyMeetingStatus.completed,
            metadata={
                "runtime_requested": RuntimeBackend.pydanticai.value,
                "runtime_used": RuntimeBackend.pydanticai.value,
                "fallback_used": False,
                "model_name": "claude-sonnet-4-6",
                "provider_base_url": "https://api.anthropic.com",
                "quality_warnings": ["runtime_fallback_used", "stability_not_confirmed"],
                "runtime_resilience": {
                    "status": "degraded",
                    "score": 0.67,
                    "source_stage": "round",
                    "stage_count": 2,
                    "degraded_reasons": ["fallback_used", "runtime_error"],
                    "attempt_count": 2,
                    "retry_count": 1,
                    "fallback_used": False,
                    "summary": "recovered after one retry",
                },
                "meeting_quality": {
                    "round_phases": ["independent", "critique", "synthesis"],
                },
                "comparability": {
                    "routing_mode": "hierarchical",
                    "runtime_used": RuntimeBackend.pydanticai.value,
                    "fallback_used": False,
                    "cluster_count": 2,
                    "dissent_turn_count": 3,
                },
            },
            participants=["architect", "research"],
            quality_score=0.82,
            confidence_score=0.76,
            routing_mode="hierarchical",
            requested_rounds=3,
            rounds_completed=3,
            cluster_summaries=[SimpleNamespace(), SimpleNamespace()],
            dissent_turn_count=3,
            round_phases=["independent", "critique", "synthesis"],
            strategy="Adopt a staged rollout.",
        ),
    )

    main.meeting(
        topic="Choose the product launch approach",
        participants=["architect", "research"],
        rounds=3,
        json_output=False,
    )

    output = buffer.getvalue()
    assert "Quality:" in output
    assert "score=0.820" in output
    assert "confidence=0.760" in output
    assert "Comparability:" in output
    assert "run=meeting_demo" in output
    assert "config=config.yaml" in output
    assert "runtime_id=claude-sonnet-4-6" in output
    assert "runtime=pydanticai" in output
    assert "routing=hierarchical" in output
    assert "Resilience:" in output
    assert "status=degraded" in output
    assert "score=0.670" in output
    assert "stage=round" in output
    assert "stages=2" in output
    assert "cause=fallback_used,runtime_error" in output
    assert "attempts=2" in output
    assert output.index("Comparability:") < output.index("Resilience:") < output.index("Flow:")
    assert "rounds=3/3" in output
    assert "Flow:" in output
    assert "independent -> critique -> synthesis" in output
    assert "Warnings:" in output
    assert "runtime_fallback_used" in output
    assert "Strategy:" in output


def test_deliberate_cli_text_summary_includes_stability_and_comparability(monkeypatch) -> None:
    buffer = _install_buffered_console(monkeypatch)
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    stability_summary = DeliberationStabilitySummary.from_scores(
        [0.71, 0.72, 0.70],
        metric_name="judge_overall",
        comparison_key="metric=judge_overall|mode=hybrid",
        metadata={"mode": "hybrid", "runtime_used": RuntimeBackend.pydanticai.value, "engine_used": "agentsociety"},
    )
    monkeypatch.setattr(
        "main.run_deliberation_runtime",
        lambda **kwargs: SimpleNamespace(
            deliberation_id="delib_demo",
            topic="Choose the product launch approach",
            objective="Define the best strategy",
            mode=DeliberationMode.hybrid,
            status=DeliberationStatus.completed,
            runtime_requested=RuntimeBackend.pydanticai.value,
            runtime_used=RuntimeBackend.pydanticai.value,
            fallback_used=False,
            engine_requested="agentsociety",
            engine_used="agentsociety",
            confidence_level=0.72,
            judge_scores=SimpleNamespace(overall=0.74),
            stability_summary=stability_summary,
            ensemble_report=SimpleNamespace(compared_engines=["agentsociety", "oasis"]),
            metadata={
                "stability_runs": 3,
                "stability_guard_applied": True,
                "quality_warnings": ["stability_not_confirmed", "profile_quality_below_threshold"],
                "runtime_resilience": {
                    "status": "guarded",
                    "score": 0.88,
                    "source_stage": "final",
                    "stage_count": 3,
                    "attempt_count": 1,
                    "retry_count": 0,
                    "fallback_used": False,
                    "summary": "runtime stayed on the preferred backend",
                },
                "meeting_quality": {
                    "quality_score": 0.81,
                    "confidence_score": 0.75,
                    "dissent_turn_count": 2,
                    "rounds_completed": 3,
                    "routing_mode": "hierarchical",
                    "summary": "quality=0.810 confidence=0.750 dissent_turns=2 rounds=3 routing=hierarchical",
                },
                "comparability": {
                    "runtime_used": RuntimeBackend.pydanticai.value,
                    "engine_used": "agentsociety",
                    "fallback_used": False,
                    "stability_sample_count": 3,
                    "stability_guard_applied": True,
                    "model_name": "claude-sonnet-4-6",
                    "provider_base_url": "https://api.anthropic.com",
                },
            },
            final_strategy="Roll out in stages.",
            summary="Population reaction is cautious but positive.",
        ),
    )

    main.deliberate(
        topic="Choose the product launch approach",
        mode=DeliberationMode.hybrid,
        stability_runs=3,
        json_output=False,
    )

    output = buffer.getvalue()
    assert "Quality:" in output
    assert "judge=0.740" in output
    assert "confidence=0.720" in output
    assert "Comparability:" in output
    assert "run=delib_demo" in output
    assert "config=config.yaml" in output
    assert "runtime_id=claude-sonnet-4-6" in output
    assert "runtime=pydanticai" in output
    assert "engine=agentsociety" in output
    assert "Stability:" in output
    assert "runs=3" in output
    assert "guard=yes" in output
    assert "metric=judge_overall" in output
    assert "Resilience:" in output
    assert "status=guarded" in output
    assert "score=0.880" in output
    assert "stage=final" in output
    assert "stages=3" in output
    assert "cause=stability_guard" in output
    assert "attempts=1" in output
    assert output.index("Stability:") < output.index("Resilience:") < output.index("Meeting:")
    assert "Meeting:" in output
    assert "score=0.810" in output
    assert "routing=hierarchical" in output
    assert "Warnings:" in output
    assert "stability_not_confirmed" in output
    assert "profile_quality_below_threshold" in output


def test_improve_round_defaults_to_pydanticai_runtime_banner(monkeypatch) -> None:
    banner = {}

    monkeypatch.setattr("main._get_improvement_controller", lambda **kwargs: FakeController())
    monkeypatch.setattr(
        "main._print_runtime_banner",
        lambda runtime, allow_fallback, label: banner.update(
            {"runtime": runtime, "allow_fallback": allow_fallback, "label": label}
        ),
    )
    monkeypatch.setattr("main._print_improvement_round", lambda *args, **kwargs: None)

    main.improve_round(target="harness", mode=LoopMode.suggest_only, json_output=False)

    assert banner["runtime"] == RuntimeBackend.pydanticai
    assert banner["allow_fallback"] is True
    assert banner["label"] == "Improve"


def test_improve_round_cli_smoke_preserves_legacy_fallback_result(monkeypatch) -> None:
    runner = CliRunner()
    controller = FallbackImprovementController()

    monkeypatch.setattr("main._get_improvement_controller", lambda **kwargs: controller)

    result = runner.invoke(
        main.app,
        [
            "improve",
            "round",
            "--target",
            "harness",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert controller.calls
    assert controller.calls[0]["runtime"] == ImprovementRuntime.pydanticai
    assert controller.calls[0]["allow_fallback"] is True
    assert payload["runtime_used"] == ImprovementRuntime.legacy.value
    assert payload["fallback_used"] is True
    assert payload["metadata"]["runtime_requested"] == ImprovementRuntime.pydanticai.value
    assert payload["metadata"]["runtime_error"] == "pydanticai unavailable"


def test_harness_suggest_interactive_preset_forces_interactive_profile(monkeypatch) -> None:
    captured = {}

    def fake_run_harness_optimization(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            round_index=1,
            decision=SimpleNamespace(value="propose"),
            mode=SimpleNamespace(value="suggest_only"),
            baseline_score=1.0,
            candidate_score=1.0,
            candidate_snapshot=SimpleNamespace(version="cand_1"),
            proposal=SimpleNamespace(summary="ok", risk_level=SimpleNamespace(value="low"), workflow_rules_to_add=[], sampling_param_overrides={}),
            requires_human_review=False,
            halted_reason=None,
            model_dump=lambda mode="json": {"ok": True},
        )

    monkeypatch.setattr("main.run_harness_optimization", fake_run_harness_optimization)
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr("main._print_harness_round", lambda *args, **kwargs: None)

    main.harness_suggest(interactive=True, json_output=False)

    assert captured["benchmark_profile"] == BenchmarkProfile.interactive
    assert captured["backend_mode"] == "surrogate"


def test_improve_round_harness_interactive_preset_passes_target_kwargs(monkeypatch) -> None:
    captured = {}

    class CapturingController(FakeController):
        def run_round(self, target: str, mode: LoopMode, **kwargs):
            captured.update(kwargs)
            return super().run_round(target, mode, **kwargs)

    monkeypatch.setattr("main._get_improvement_controller", lambda **kwargs: CapturingController())
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr("main._print_improvement_round", lambda *args, **kwargs: None)

    main.improve_round(target="harness", mode=LoopMode.suggest_only, interactive=True, json_output=False)

    assert captured["benchmark_profile"] == BenchmarkProfile.interactive
    assert captured["backend_mode"] == "surrogate"


def test_harness_suggest_full_preset_forces_full_profile(monkeypatch) -> None:
    captured = {}

    def fake_run_harness_optimization(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            round_index=1,
            decision=SimpleNamespace(value="propose"),
            mode=SimpleNamespace(value="suggest_only"),
            baseline_score=1.0,
            candidate_score=1.0,
            candidate_snapshot=SimpleNamespace(version="cand_1"),
            proposal=SimpleNamespace(summary="ok", risk_level=SimpleNamespace(value="low"), workflow_rules_to_add=[], sampling_param_overrides={}),
            requires_human_review=False,
            halted_reason=None,
            model_dump=lambda mode="json": {"ok": True},
        )

    monkeypatch.setattr("main.run_harness_optimization", fake_run_harness_optimization)
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr("main._print_harness_round", lambda *args, **kwargs: None)

    main.harness_suggest(full=True, json_output=False)

    assert captured["benchmark_profile"] == BenchmarkProfile.full
    assert captured["backend_mode"] is None


def test_improve_round_harness_full_preset_passes_target_kwargs(monkeypatch) -> None:
    captured = {}

    class CapturingController(FakeController):
        def run_round(self, target: str, mode: LoopMode, **kwargs):
            captured.update(kwargs)
            return super().run_round(target, mode, **kwargs)

    monkeypatch.setattr("main._get_improvement_controller", lambda **kwargs: CapturingController())
    monkeypatch.setattr("main._print_runtime_banner", lambda *args, **kwargs: None)
    monkeypatch.setattr("main._print_improvement_round", lambda *args, **kwargs: None)

    main.improve_round(target="harness", mode=LoopMode.suggest_only, full=True, json_output=False)

    assert captured["benchmark_profile"] == BenchmarkProfile.full
    assert captured["backend_mode"] is None


def test_runtime_health_command_uses_health_snapshot(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        "main._collect_runtime_health_snapshot",
        lambda runtime_name: {"runtime": runtime_name, "status": "healthy"},
    )
    monkeypatch.setattr(
        "main._print_runtime_health_report",
        lambda report, as_json=False: captured.update({"report": report, "as_json": as_json}),
    )

    main.runtime_health_command(runtime_name="pydanticai", json_output=True)

    assert captured["report"]["runtime"] == "pydanticai"
    assert captured["report"]["status"] == "healthy"
    assert captured["as_json"] is True


def test_runtime_health_command_prints_fallback_runtime_for_pydanticai(monkeypatch) -> None:
    buffer = _install_buffered_console(monkeypatch)

    monkeypatch.setattr(
        "main._collect_runtime_health_snapshot",
        lambda runtime_name: {
            "runtime": runtime_name,
            "status": "unavailable",
            "configured": True,
            "imports_available": False,
            "fallback_runtime": "legacy",
            "provider_base_url": "http://example.test/v1",
            "provider_reachable": False,
            "message": "pydanticai unavailable",
        },
    )

    main.runtime_health_command(runtime_name="pydanticai", json_output=False)

    output = buffer.getvalue()
    assert "Runtime: pydanticai" in output
    assert "Fallback Runtime:" in output
    assert "legacy" in output
    assert "pydanticai unavailable" in output


def test_runtime_pydanticai_runtime_health_alias_returns_json_ready_payload() -> None:
    payload = pydanticai_runtime_health()

    assert isinstance(payload, dict)
    assert payload["runtime"] == "pydanticai"
    assert payload["status"] in {"unavailable", "degraded", "healthy", "misconfigured"}
    assert "message" in payload
    json.dumps(payload)
