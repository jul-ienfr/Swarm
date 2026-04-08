from __future__ import annotations

import importlib
import json
from pathlib import Path

from improvement_loop.models import ImprovementLoopRun, ImprovementRoundRecord, ImprovementRuntime, LoopDecision, LoopMode, TargetDescriptor, TargetInspection
from swarm_mcp import (
    _coerce_loop_mode,
    bridge_deliberation_market,
    delegate_to_swarm_supervisor,
    export_deliberation_neo4j,
    get_mission_status,
    inspect_improvement_target,
    list_improvement_targets,
    persona_chat_deliberation,
    project_capabilities,
    prediction_markets_market_execution,
    prediction_markets_venues,
    prediction_markets_stream_collect,
    list_deliberation_campaigns,
    read_deliberation_artifact,
    read_deliberation_campaign_artifact,
    read_deliberation_campaign_benchmark_artifact,
    read_deliberation_campaign_benchmark_matrix_artifact,
    read_deliberation_campaign_benchmark_matrix_export_artifact,
    read_deliberation_campaign_benchmark_matrix_export_comparison_artifact,
    read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact,
    read_deliberation_campaign_benchmark_matrix_comparison_artifact,
    read_deliberation_campaign_benchmark_matrix_comparison_export_artifact,
    read_deliberation_campaign_comparison_artifact,
    read_deliberation_campaign_comparison_export_artifact,
    audit_deliberation_campaign_benchmark_matrix_artifact,
    audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact,
    audit_deliberation_campaign_benchmark_matrix_comparison_artifact,
    export_deliberation_campaign_benchmark_matrix_artifact,
    export_deliberation_campaign_benchmark_matrix_export_comparison_artifact,
    export_deliberation_campaign_benchmark_matrix_comparison_artifact,
    audit_deliberation_campaign_comparison_artifact,
    compare_deliberation_campaigns,
    compare_deliberation_campaign_benchmark_matrix_exports,
    compare_deliberation_campaign_benchmark_matrices,
    compare_audit_export_deliberation_campaign_benchmark_matrix_exports,
    compare_audit_export_deliberation_campaign_benchmark_matrices,
    compare_audit_export_deliberation_campaigns,
    compare_deliberation_campaign_bundle,
    benchmark_deliberation_campaigns,
    benchmark_deliberation_campaign_matrix,
    deliberation_campaign_index,
    deliberation_campaign_dashboard,
    list_deliberation_campaign_benchmarks,
    list_deliberation_campaign_benchmark_matrix_artifacts,
    list_deliberation_campaign_benchmark_matrix_export_artifacts,
    list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts,
    list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts,
    list_deliberation_campaign_benchmark_matrix_comparison_artifacts,
    list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts,
    export_deliberation_campaign_comparison_artifact,
    list_deliberation_campaign_comparison_export_artifacts,
    list_deliberation_campaign_comparison_artifacts,
    read_strategy_meeting_artifact,
    read_mission_log,
    replay_deliberation,
    run_deliberation_campaign,
    run_deliberation,
    run_strategy_meeting,
    runtime_health,
    run_improvement_loop,
    run_improvement_round,
)
from swarm_core.deliberation import DeliberationResult, DeliberationStatus
from swarm_core.deliberation_artifacts import DeliberationMode
from swarm_core.deliberation_interview import DeliberationInterviewTarget, DeliberationInterviewTargetType
from swarm_core.deliberation_stability import DeliberationStabilitySummary
from swarm_core.deliberation_campaign import build_deliberation_campaign_artifact_index
from swarm_core.graph_store import GraphNode, GraphStore
from swarm_core.strategy_meeting import StrategyMeetingResult, StrategyMeetingStatus


def test_legacy_openclaw_mcp_alias_resolves_to_swarm_mcp() -> None:
    legacy = importlib.import_module("openclaw_mcp")
    canonical = importlib.import_module("swarm_mcp")

    assert legacy is canonical
    assert canonical.MCP_SERVER_NAME == "Swarm MCP"


class FakeState:
    def __init__(self, values, next_nodes=()):
        self.values = values
        self.next = next_nodes


class FakeGraph:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    def get_state(self, config):
        return self._state


class FakeController:
    def list_targets(self):
        return [
            TargetDescriptor(
                target_id="harness",
                description="Harness target.",
                default_mode=LoopMode.suggest_only,
            )
        ]

    def inspect_target(self, target: str, **kwargs):
        return TargetInspection(
            descriptor=TargetDescriptor(target_id=target, description=f"{target} target."),
            current_snapshot={"version": "snap_1"},
            benchmark={"suite_version": "v1", "cases": []},
            metadata={"source": "fake"},
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
        return ImprovementLoopRun(
            target_id=target,
            mode=mode,
            max_rounds=max_rounds,
            completed_rounds=1,
            rounds=[self.run_round(target, mode)],
            stopped_reason="bounded",
        )


class CapturingFallbackController(FakeController):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def _fallback_record(self, target: str, mode: LoopMode) -> ImprovementRoundRecord:
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
                "runtime_resilience": {
                    "status": "guarded",
                    "score": 0.86,
                    "runtime_requested": ImprovementRuntime.pydanticai.value,
                    "runtime_used": ImprovementRuntime.legacy.value,
                    "fallback_used": True,
                    "attempt_count": 1,
                    "retry_count": 0,
                    "summary": "preferred runtime fell back to legacy",
                },
                "comparability": {
                    "runtime_resilience_status": "guarded",
                    "runtime_resilience_score": 0.86,
                    "runtime_resilience_attempt_count": 1,
                    "runtime_resilience_retry_count": 0,
                    "runtime_resilience_fallback_used": True,
                },
                "quality_warnings": ["runtime_fallback_used: requested=pydanticai used=legacy"],
            },
        )

    def inspect_target(self, target: str, **kwargs):
        self.calls.append({"method": "inspect", "target": target, **kwargs})
        return TargetInspection(
            descriptor=TargetDescriptor(target_id=target, description=f"{target} target."),
            current_snapshot={"version": "snap_1"},
            benchmark={"suite_version": "v1", "cases": []},
            runtime_used=ImprovementRuntime.legacy,
            fallback_used=True,
            metadata={
                "source": "fake",
                "runtime_error": "pydanticai unavailable",
                "runtime_resilience": {
                    "status": "guarded",
                    "score": 0.86,
                    "runtime_requested": ImprovementRuntime.pydanticai.value,
                    "runtime_used": ImprovementRuntime.legacy.value,
                    "fallback_used": True,
                    "attempt_count": 1,
                    "retry_count": 0,
                    "summary": "preferred runtime fell back to legacy",
                },
                "comparability": {
                    "runtime_resilience_status": "guarded",
                    "runtime_resilience_score": 0.86,
                    "runtime_resilience_attempt_count": 1,
                    "runtime_resilience_retry_count": 0,
                    "runtime_resilience_fallback_used": True,
                },
                "quality_warnings": ["runtime_fallback_used: requested=pydanticai used=legacy"],
            },
        )

    def run_round(self, target: str, mode: LoopMode, **kwargs):
        self.calls.append({"method": "round", "target": target, "mode": mode, **kwargs})
        return self._fallback_record(target, mode)

    def run_loop(self, target: str, mode: LoopMode, max_rounds: int, **kwargs):
        self.calls.append(
            {"method": "loop", "target": target, "mode": mode, "max_rounds": max_rounds, **kwargs}
        )
        return ImprovementLoopRun(
            target_id=target,
            mode=mode,
            max_rounds=max_rounds,
            completed_rounds=1,
            rounds=[self._fallback_record(target, mode)],
            stopped_reason="bounded",
        )


class FakeProcess:
    def __init__(self, return_code=None) -> None:
        self._return_code = return_code

    def poll(self):
        return self._return_code


def test_project_capabilities_reports_tooling(monkeypatch) -> None:
    monkeypatch.setattr("swarm_mcp._get_improvement_controller", lambda *args, **kwargs: FakeController())
    monkeypatch.setattr(
        "swarm_mcp._collect_runtime_health",
        lambda runtime_name="all": {
            "ok": True,
            "runtimes": {
                "langgraph": {"runtime": "langgraph", "status": "healthy"},
                "pydanticai": {"runtime": "pydanticai", "status": "healthy"},
                "legacy": {"runtime": "legacy", "status": "healthy"},
            },
        },
    )

    payload = project_capabilities()

    assert payload["ok"] is True
    assert payload["module"] == "swarm_mcp"
    assert payload["canonical_module"] == "swarm_mcp"
    assert payload["canonical_script"] == "swarm_mcp.py"
    assert payload["legacy_aliases"] == ["openclaw_mcp"]
    assert payload["legacy_scripts"] == ["openclaw_mcp.py"]
    assert payload["server_name"] == "Swarm MCP"
    assert payload["entrypoints"]["cli"] == "main.py"
    assert payload["entrypoints"]["mcp"] == "swarm_mcp.py"
    assert payload["entrypoints"]["legacy_mcp_alias"] == "openclaw_mcp.py"
    assert "delegate_to_swarm_supervisor" in payload["tools"]
    assert "runtime_health" in payload["tools"]
    assert "run_strategy_meeting" in payload["tools"]
    assert "run_deliberation" in payload["tools"]
    assert "run_deliberation_campaign" in payload["tools"]
    assert "read_deliberation_artifact" in payload["tools"]
    assert "read_deliberation_campaign_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_export_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_export_comparison_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_comparison_artifact" in payload["tools"]
    assert "read_deliberation_campaign_benchmark_matrix_comparison_export_artifact" in payload["tools"]
    assert "read_deliberation_campaign_comparison_artifact" in payload["tools"]
    assert "list_deliberation_campaigns" in payload["tools"]
    assert "list_deliberation_campaign_benchmarks" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_export_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_comparison_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts" in payload["tools"]
    assert "list_deliberation_campaign_comparison_artifacts" in payload["tools"]
    assert "read_deliberation_campaign_comparison_export_artifact" in payload["tools"]
    assert "list_deliberation_campaign_comparison_export_artifacts" in payload["tools"]
    assert "audit_deliberation_campaign_comparison_artifact" in payload["tools"]
    assert "export_deliberation_campaign_comparison_artifact" in payload["tools"]
    assert "compare_deliberation_campaigns" in payload["tools"]
    assert "compare_deliberation_campaign_benchmark_matrix_exports" in payload["tools"]
    assert "compare_deliberation_campaign_benchmark_matrices" in payload["tools"]
    assert "audit_deliberation_campaign_benchmark_matrix_artifact" in payload["tools"]
    assert "audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact" in payload["tools"]
    assert "export_deliberation_campaign_benchmark_matrix_artifact" in payload["tools"]
    assert "export_deliberation_campaign_benchmark_matrix_export_comparison_artifact" in payload["tools"]
    assert "audit_deliberation_campaign_benchmark_matrix_comparison_artifact" in payload["tools"]
    assert "export_deliberation_campaign_benchmark_matrix_comparison_artifact" in payload["tools"]
    assert "compare_audit_export_deliberation_campaign_benchmark_matrix_exports" in payload["tools"]
    assert "compare_audit_export_deliberation_campaign_benchmark_matrices" in payload["tools"]
    assert "compare_audit_export_deliberation_campaigns" in payload["tools"]
    assert "benchmark_deliberation_campaigns" in payload["tools"]
    assert "benchmark_deliberation_campaign_matrix" in payload["tools"]
    assert "deliberation_campaign_index" in payload["tools"]
    assert "deliberation_campaign_dashboard" in payload["tools"]
    assert "persona_chat_deliberation" in payload["tools"]
    assert "export_deliberation_neo4j" in payload["tools"]
    assert "bridge_deliberation_market" in payload["tools"]
    assert "prediction_markets_market_execution" in payload["tools"]
    assert "prediction_markets_stream_collect" in payload["tools"]
    assert payload["improvement_targets"] == ["harness"]
    assert "langgraph" in payload["runtimes"]
    assert "pydanticai" in payload["runtimes"]
    assert payload["runtime_defaults"]["strategy_meeting"] == "pydanticai"
    assert payload["runtime_defaults"]["deliberation"] == "pydanticai"
    assert payload["runtime_health"]["pydanticai"]["status"] == "healthy"


def test_prediction_markets_market_execution_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp.market_execution_sync",
        lambda **kwargs: {
            "run_id": "pm_exec",
            "descriptor": {"market_id": "pm_demo_election", "question": "Will it happen?"},
            "market_execution": {
                "report_id": "mexec_1",
                "market_id": "pm_demo_election",
                "execution_kind": "execution-equivalent",
                "manual_review_required": True,
                "order_trace_audit": {"trace_id": "trace_1", "events": ["place", "cancel"]},
            },
            "live_execution": {"execution_id": "lexec_1"},
        },
    )

    payload = prediction_markets_market_execution(slug="demo-election-market")

    assert payload["ok"] is True
    assert payload["result"]["market_execution"]["market_id"] == "pm_demo_election"
    assert payload["result"]["market_execution"]["execution_kind"] == "execution-equivalent"
    assert payload["result"]["market_execution"]["manual_review_required"] is True
    assert payload["result"]["market_execution"]["order_trace_audit"]["trace_id"] == "trace_1"


def test_prediction_markets_venues_tool_surfaces_execution_like_and_manual_review(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp.additional_venues_catalog_sync",
        lambda **kwargs: {
            "run_id": "pm_venues",
            "additional_venues_matrix": {
                "profiles": [
                    {
                        "venue": "manifold",
                        "execution_kind": "execution-like",
                        "manual_review_required": True,
                    }
                ]
            },
        },
    )

    payload = prediction_markets_venues(query="btc")

    assert payload["ok"] is True
    profile = payload["result"]["additional_venues_matrix"]["profiles"][0]
    assert profile["execution_kind"] == "execution-like"
    assert profile["manual_review_required"] is True


def test_prediction_markets_stream_collect_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp.stream_collect_sync",
        lambda **kwargs: {
            "stream_collection": {
                "report_id": "streamctl_1",
                "cache_hit_count": 2,
                "batch_count": 2,
                "items": [{"target_ref": "market_id:demo-election-market"}],
            }
        },
    )

    payload = prediction_markets_stream_collect(market_ids=["demo-election-market"])

    assert payload["ok"] is True
    assert payload["result"]["stream_collection"]["cache_hit_count"] == 2


def test_get_mission_status_returns_checkpoint_summary(monkeypatch) -> None:
    fake_state = FakeState(
        values={
            "task_ledger": {
                "goal": "Run a market simulation",
                "current_intent": {"intent_id": "intent_123", "task_type": "scenario_simulation"},
                "simulation_result": {"status": "completed"},
            },
            "progress_ledger": {"step_index": 3, "next_speaker": "worker_a"},
            "tokens_used_total": 77,
        },
        next_nodes=("supervisor",),
    )
    monkeypatch.setattr("swarm_mcp._get_graph", lambda: FakeGraph(fake_state))

    payload = get_mission_status("mission_demo")

    assert payload["ok"] is True
    assert payload["found"] is True
    assert payload["state"]["goal"] == "Run a market simulation"
    assert payload["state"]["tokens_used_total"] == 77
    assert payload["next_nodes"] == ["supervisor"]


def test_read_mission_log_handles_missing_and_existing_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("swarm_mcp.REPO_ROOT", tmp_path)

    missing = read_mission_log("mission_missing")
    assert missing["ok"] is True
    assert missing["exists"] is False

    log_path = tmp_path / "mission_present.log"
    log_path.write_text("line1\nline2\nline3\n", encoding="utf-8")

    present = read_mission_log("mission_present", lines=2)
    assert present["ok"] is True
    assert present["exists"] is True
    assert present["tail"] == "line2\nline3"


def test_improvement_tools_use_registered_controller(monkeypatch) -> None:
    controller = CapturingFallbackController()
    monkeypatch.setattr("swarm_mcp._get_improvement_controller", lambda *args, **kwargs: controller)

    targets = list_improvement_targets()
    inspection = inspect_improvement_target("harness")
    round_payload = run_improvement_round("harness", "suggest_only")
    loop_payload = run_improvement_loop("harness", "safe_auto_apply", max_rounds=2)

    assert targets["ok"] is True
    assert targets["targets"][0]["target_id"] == "harness"
    assert targets["runtime_requested"] == "pydanticai"
    assert targets["runtime_used"] is None
    assert targets["fallback_used"] is False
    assert targets["executed"] is False
    assert inspection["inspection"]["descriptor"]["target_id"] == "harness"
    assert inspection["inspection"]["runtime_used"] == "legacy"
    assert inspection["inspection"]["fallback_used"] is True
    assert inspection["runtime_requested"] == "pydanticai"
    assert inspection["runtime_used"] == "legacy"
    assert inspection["resilience_summary"]["runtime"]["matched"] is False
    assert inspection["resilience_summary"]["runtime_resilience"]["status"] == "guarded"
    assert inspection["resilience_summary"]["comparability"]["runtime_resilience_score"] == 0.86
    assert inspection["resilience_summary"]["comparability"]["quality_warning_count"] == 1
    assert round_payload["record"]["mode"] == "suggest_only"
    assert round_payload["record"]["runtime_used"] == "legacy"
    assert round_payload["record"]["fallback_used"] is True
    assert round_payload["runtime_requested"] == "pydanticai"
    assert round_payload["runtime_used"] == "legacy"
    assert round_payload["resilience_summary"]["runtime"]["matched"] is False
    assert round_payload["resilience_summary"]["runtime_resilience"]["attempt_count"] == 1
    assert round_payload["resilience_summary"]["comparability"]["round_index"] == 1
    assert loop_payload["run"]["mode"] == "safe_auto_apply"
    assert loop_payload["run"]["rounds"][0]["runtime_used"] == "legacy"
    assert loop_payload["run"]["rounds"][0]["fallback_used"] is True
    assert loop_payload["runtime_requested"] == "pydanticai"
    assert loop_payload["runtime_used"] == "legacy"
    assert loop_payload["resilience_summary"]["runtime"]["matched"] is False
    assert loop_payload["resilience_summary"]["comparability"]["round_count"] == 1
    assert loop_payload["resilience_summary"]["comparability"]["quality_warning_count"] == 1
    assert controller.calls[0]["runtime"] == ImprovementRuntime.pydanticai
    assert controller.calls[0]["allow_fallback"] is True
    assert controller.calls[1]["runtime"] == ImprovementRuntime.pydanticai
    assert controller.calls[1]["allow_fallback"] is True
    assert controller.calls[2]["runtime"] == ImprovementRuntime.pydanticai
    assert controller.calls[2]["allow_fallback"] is True


def test_deliberation_tools_return_structured_payloads(monkeypatch, tmp_path: Path) -> None:
    fake_result = DeliberationResult(
        deliberation_id="delib_demo",
        topic="Choose the launch strategy",
        objective="Define the best strategy",
        mode=DeliberationMode.hybrid,
        status=DeliberationStatus.completed,
        runtime_requested="pydanticai",
        runtime_used="pydanticai",
        fallback_used=False,
        engine_requested="agentsociety",
        engine_used="agentsociety",
        summary="Population reaction is cautious but positive.",
        final_strategy="Roll out in stages.",
        confidence_level=0.72,
        stability_summary=DeliberationStabilitySummary.from_scores(
            [0.71, 0.72, 0.715],
            minimum_sample_count=3,
            metadata={"comparison_key": "demo"},
        ),
        metadata={
            "comparability": {
                "stability_sample_count": 3,
                "stability_sample_sufficient": True,
                "stability_stable": True,
                "profile_quality_diversity": 0.5,
                "profile_quality_stance_diversity": 0.4,
                "profile_quality_role_diversity": 0.3,
            },
            "runtime_resilience": {
                "status": "guarded",
                "score": 0.86,
                "runtime_requested": "pydanticai",
                "runtime_used": "pydanticai",
                "engine_requested": "agentsociety",
                "engine_used": "agentsociety",
                "fallback_used": False,
                "attempt_count": 1,
                "retry_count": 0,
                "summary": "preferred runtime stayed healthy",
            },
            "model_name": "claude-sonnet-4-6",
            "provider_base_url": "https://api.anthropic.com",
            "quality_warnings": ["runtime_fallback_used: requested=pydanticai used=legacy"],
        },
    )

    monkeypatch.setattr("swarm_mcp.run_deliberation_runtime", lambda **kwargs: fake_result)
    monkeypatch.setattr("swarm_mcp.load_deliberation_result", lambda deliberation_id: fake_result)
    monkeypatch.setattr("swarm_mcp.replay_deliberation_sync", lambda deliberation_id, **kwargs: fake_result)
    monkeypatch.setattr("swarm_mcp.DEFAULT_DELIBERATION_OUTPUT_DIR", tmp_path)
    run_dir = tmp_path / "delib_demo"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(fake_result.model_dump_json(indent=2), encoding="utf-8")

    run_payload = run_deliberation("Choose the launch strategy", mode="hybrid")
    read_payload = read_deliberation_artifact("delib_demo")
    replay_payload = replay_deliberation("delib_demo")

    assert run_payload["ok"] is True
    assert run_payload["result"]["mode"] == "hybrid"
    assert run_payload["engine_used"] == "agentsociety"
    assert run_payload["run_id"] == "delib_demo"
    assert run_payload["config_path"] == "config.yaml"
    assert run_payload["runtime_id"] == "claude-sonnet-4-6"
    assert run_payload["resilience_summary"]["runtime"]["matched"] is True
    assert run_payload["resilience_summary"]["runtime_resilience"]["status"] == "guarded"
    assert run_payload["resilience_summary"]["runtime_resilience"]["score"] == 0.86
    assert run_payload["resilience_summary"]["runtime_resilience"]["attempt_count"] == 1
    assert run_payload["resilience_summary"]["comparability"]["runtime_resilience_status"] == "guarded"
    assert run_payload["resilience_summary"]["comparability"]["runtime_resilience_score"] == 0.86
    assert run_payload["resilience_summary"]["comparability"]["runtime_resilience_attempt_count"] == 1
    assert run_payload["resilience_summary"]["comparability"]["run_id"] == "delib_demo"
    assert run_payload["resilience_summary"]["comparability"]["config_id"] == "config.yaml"
    assert run_payload["resilience_summary"]["comparability"]["runtime_id"] == "claude-sonnet-4-6"
    assert run_payload["resilience_summary"]["comparability"]["stability_sample_count"] == 3
    assert run_payload["resilience_summary"]["comparability"]["stability_stable"] is True
    assert run_payload["resilience_summary"]["comparability"]["quality_warning_count"] == 1
    assert read_payload["ok"] is True
    assert read_payload["exists"] is True
    assert read_payload["result"]["final_strategy"] == "Roll out in stages."
    assert replay_payload["ok"] is True
    assert replay_payload["result"]["status"] == "completed"


def test_deliberation_campaign_tool_aggregates_and_persists(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    scores = [0.6, 0.7, 0.8]

    def build_result(index: int) -> DeliberationResult:
        score = scores[index]
        return DeliberationResult(
            deliberation_id=f"delib_{index + 1}",
            topic="Choose the launch strategy",
            objective="Define the best strategy",
            mode=DeliberationMode.hybrid,
            status=DeliberationStatus.completed,
            runtime_requested="pydanticai",
            runtime_used="pydanticai",
            fallback_used=False,
            engine_requested="agentsociety",
            engine_used="agentsociety",
            summary="Population reaction is cautious but positive.",
            final_strategy="Roll out in stages.",
            confidence_level=score,
            metadata={
                "model_name": "claude-sonnet-4-6",
                "provider_base_url": "https://api.anthropic.com",
                "comparability": {"sample_index": index + 1},
            },
        )

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return build_result(len(calls) - 1)

    monkeypatch.setattr("swarm_mcp.run_deliberation_runtime", fake_runner)
    monkeypatch.setattr("swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR", tmp_path / "campaigns")

    payload = run_deliberation_campaign(
        topic="Choose the launch strategy",
        sample_count=3,
        stability_runs=2,
        allow_fallback=True,
        persist=True,
        campaign_id="campaign_demo",
    )

    assert payload["ok"] is True
    campaign_id = payload["campaign_id"]
    result = payload["result"]
    assert campaign_id == "campaign_demo"
    assert result["sample_count_requested"] == 3
    assert result["stability_runs"] == 2
    assert result["fallback_guard_applied"] is True
    assert result["allow_fallback_effective"] is False
    assert result["fallback_guard_reason"] == "fallback_disabled_for_repeated_campaign_comparison"
    assert result["summary"]["sample_count_completed"] == 3
    assert result["summary"]["campaign_stability_summary"]["sample_count"] == 3
    assert result["summary"]["campaign_stability_summary"]["comparison_key"].startswith("topic=")
    assert abs(result["summary"]["quality_score_mean"] - 0.7) < 1e-9
    assert result["summary"]["runtime_counts"]["pydanticai"] == 3
    assert len(result["samples"]) == 3
    assert all(call["allow_fallback"] is False for call in calls)
    assert all(call["stability_runs"] == 2 for call in calls)
    assert all(str(call["output_dir"]).startswith(str(tmp_path / "campaigns" / campaign_id / "samples")) for call in calls)
    report_path = Path(result["report_path"])
    assert report_path.exists()

    read_payload = read_deliberation_campaign_artifact(campaign_id)
    assert read_payload["ok"] is True
    assert read_payload["exists"] is True
    assert read_payload["result"]["campaign_id"] == campaign_id
    assert abs(read_payload["result"]["summary"]["quality_score_mean"] - 0.7) < 1e-9


def test_deliberation_campaign_tool_lists_persisted_reports(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def build_result(index: int) -> DeliberationResult:
        score = 0.6 + (0.1 * index)
        return DeliberationResult(
            deliberation_id=f"delib_{index + 1}",
            topic="Choose the launch strategy",
            objective="Define the best strategy",
            mode=DeliberationMode.hybrid,
            status=DeliberationStatus.completed,
            runtime_requested="pydanticai",
            runtime_used="pydanticai",
            fallback_used=False,
            engine_requested="agentsociety",
            engine_used="agentsociety",
            summary="Population reaction is cautious but positive.",
            final_strategy="Roll out in stages.",
            confidence_level=score,
            metadata={
                "model_name": "claude-sonnet-4-6",
                "provider_base_url": "https://api.anthropic.com",
                "comparability": {"sample_index": index + 1},
            },
        )

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return build_result(len(calls) - 1)

    monkeypatch.setattr("swarm_mcp.run_deliberation_runtime", fake_runner)
    monkeypatch.setattr("swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR", tmp_path / "campaigns")

    run_deliberation_campaign(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        allow_fallback=True,
        persist=True,
        campaign_id="campaign_alpha",
    )
    run_deliberation_campaign(
        topic="Choose the launch strategy",
        sample_count=1,
        stability_runs=1,
        allow_fallback=True,
        persist=True,
        campaign_id="campaign_beta",
    )

    payload = list_deliberation_campaigns(limit=1, status="completed")

    assert payload["ok"] is True
    assert payload["exists"] is True
    assert payload["count"] == 1
    assert payload["limit"] == 1
    assert payload["status"] == "completed"
    assert [item["campaign_id"] for item in payload["campaigns"]] == ["campaign_beta"]
    assert all(item["report_path"].endswith("/report.json") for item in payload["campaigns"])
    assert all(str(call["output_dir"]).startswith(str(tmp_path / "campaigns")) for call in calls)


def test_deliberation_campaign_tool_compares_persisted_reports(monkeypatch, tmp_path: Path) -> None:
    class FakeCampaignReport:
        def __init__(
            self,
            *,
            campaign_id: str,
            status: str,
            sample_count_requested: int,
            stability_runs: int,
            sample_count_completed: int,
            sample_count_failed: int,
            quality_score_mean: float,
            confidence_level_mean: float,
            fallback_count: int,
            runtime_counts: dict[str, int],
            engine_counts: dict[str, int],
        ) -> None:
            self.campaign_id = campaign_id
            self.status = status
            self.topic = "Choose the launch strategy"
            self.objective = "Define the best strategy"
            self.created_at = "2026-04-08T12:00:00Z"
            self.sample_count_requested = sample_count_requested
            self.stability_runs = stability_runs
            self.report_path = f"/tmp/{campaign_id}/report.json"
            self.sample_count_completed = sample_count_completed
            self.sample_count_failed = sample_count_failed
            self.quality_score_mean = quality_score_mean
            self.confidence_level_mean = confidence_level_mean
            self.fallback_count = fallback_count
            self.runtime_counts = runtime_counts
            self.engine_counts = engine_counts

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {
                "campaign_id": self.campaign_id,
                "status": self.status,
                "topic": self.topic,
                "objective": self.objective,
                "created_at": self.created_at,
                "sample_count_requested": self.sample_count_requested,
                "stability_runs": self.stability_runs,
                "report_path": self.report_path,
                "summary": {
                    "sample_count_completed": self.sample_count_completed,
                    "sample_count_failed": self.sample_count_failed,
                    "quality_score_mean": self.quality_score_mean,
                    "confidence_level_mean": self.confidence_level_mean,
                    "fallback_count": self.fallback_count,
                    "runtime_counts": self.runtime_counts,
                    "engine_counts": self.engine_counts,
                },
            }

    reports = {
        "campaign_baseline": FakeCampaignReport(
            campaign_id="campaign_baseline",
            status="completed",
            sample_count_requested=2,
            stability_runs=1,
            sample_count_completed=2,
            sample_count_failed=0,
            quality_score_mean=0.6,
            confidence_level_mean=0.55,
            fallback_count=0,
            runtime_counts={"pydanticai": 2},
            engine_counts={"agentsociety": 2},
        ),
        "campaign_candidate": FakeCampaignReport(
            campaign_id="campaign_candidate",
            status="partial",
            sample_count_requested=3,
            stability_runs=2,
            sample_count_completed=2,
            sample_count_failed=1,
            quality_score_mean=0.75,
            confidence_level_mean=0.7,
            fallback_count=1,
            runtime_counts={"legacy": 1, "pydanticai": 2},
            engine_counts={"agentsociety": 1, "oasis": 2},
        ),
    }

    comparison_report = {
        "comparison_id": "campaign_compare_demo",
        "output_dir": "/tmp/campaigns",
        "requested_campaign_ids": ["campaign_baseline", "campaign_candidate"],
        "latest": None,
        "entries": [
            {
                "campaign_id": "campaign_baseline",
                "created_at": "2026-04-08T10:00:00+00:00",
                "status": "completed",
                "topic": "Choose the launch strategy",
                "mode": "committee",
                "runtime_requested": "pydanticai",
                "engine_requested": "agentsociety",
                "sample_count_requested": 2,
                "stability_runs": 1,
                "comparison_key": "key_baseline",
                "sample_count_completed": 2,
                "sample_count_failed": 0,
                "fallback_count": 0,
                "runtime_counts": {"pydanticai": 2},
                "engine_counts": {"agentsociety": 2},
                "quality_score_mean": 0.6,
                "quality_score_min": 0.6,
                "quality_score_max": 0.6,
                "confidence_level_mean": 0.55,
                "confidence_level_min": 0.55,
                "confidence_level_max": 0.55,
                "fallback_guard_applied": False,
                "fallback_guard_reason": None,
                "report_path": "/tmp/campaigns/campaign_baseline/report.json",
            },
            {
                "campaign_id": "campaign_candidate",
                "created_at": "2026-04-08T11:00:00+00:00",
                "status": "partial",
                "topic": "Choose the launch strategy",
                "mode": "committee",
                "runtime_requested": "pydanticai",
                "engine_requested": "agentsociety",
                "sample_count_requested": 3,
                "stability_runs": 2,
                "comparison_key": "key_candidate",
                "sample_count_completed": 2,
                "sample_count_failed": 1,
                "fallback_count": 1,
                "runtime_counts": {"legacy": 1, "pydanticai": 2},
                "engine_counts": {"agentsociety": 1, "oasis": 2},
                "quality_score_mean": 0.75,
                "quality_score_min": 0.75,
                "quality_score_max": 0.75,
                "confidence_level_mean": 0.7,
                "confidence_level_min": 0.7,
                "confidence_level_max": 0.7,
                "fallback_guard_applied": False,
                "fallback_guard_reason": None,
                "report_path": "/tmp/campaigns/campaign_candidate/report.json",
            },
        ],
        "summary": {
            "campaign_count": 2,
            "campaign_ids": ["campaign_baseline", "campaign_candidate"],
            "status_counts": {"completed": 1, "partial": 1},
            "topic_values": ["Choose the launch strategy"],
            "mode_values": ["committee"],
            "runtime_values": ["pydanticai"],
            "engine_values": ["agentsociety"],
            "sample_count_values": [2, 3],
            "stability_runs_values": [1, 2],
            "comparison_key_values": ["key_baseline", "key_candidate"],
            "comparable": False,
            "mismatch_reasons": ["sample_count_mismatch", "stability_runs_mismatch", "comparison_key_mismatch"],
            "quality_score_mean": 0.675,
            "quality_score_min": 0.6,
            "quality_score_max": 0.75,
            "confidence_level_mean": 0.625,
            "confidence_level_min": 0.55,
            "confidence_level_max": 0.7,
            "sample_count_requested_total": 5,
            "sample_count_completed_total": 4,
            "sample_count_failed_total": 1,
        },
    }

    monkeypatch.setattr("swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(
        "swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR",
        tmp_path / "campaign_comparisons",
    )
    monkeypatch.setattr(
        "swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR",
        tmp_path / "campaign_comparison_exports",
    )

    def fake_compare_deliberation_campaign_reports(**kwargs):
        report_path = tmp_path / "campaign_comparisons" / "campaign_compare_demo" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        persisted_report = dict(comparison_report, report_path=str(report_path))
        report_path.write_text(json.dumps(persisted_report, indent=2), encoding="utf-8")
        return type("Report", (), {"model_dump": lambda self, mode="json": persisted_report})()

    monkeypatch.setattr(
        "swarm_mcp.compare_deliberation_campaign_reports",
        fake_compare_deliberation_campaign_reports,
    )

    payload = compare_deliberation_campaigns("campaign_baseline", "campaign_candidate")

    assert payload["ok"] is True
    assert payload["comparison_id"] == "campaign_compare_demo"
    assert payload["persisted"] is True
    assert payload["artifact_path"] == str(
        tmp_path / "campaign_comparisons" / "campaign_compare_demo" / "report.json"
    )
    assert payload["baseline_campaign_id"] == "campaign_baseline"
    assert payload["candidate_campaign_id"] == "campaign_candidate"
    assert payload["result"]["comparison_id"] == "campaign_compare_demo"
    assert payload["comparison"]["status"] == {
        "baseline": "completed",
        "candidate": "partial",
        "changed": True,
    }
    assert payload["comparison"]["sample_count_requested"]["delta"] == 1
    assert payload["comparison"]["sample_count_completed"]["delta"] == 0
    assert payload["comparison"]["sample_count_failed"]["delta"] == 1
    assert abs(payload["comparison"]["quality_score_mean"]["delta"] - 0.15) < 1e-9
    assert abs(payload["comparison"]["confidence_level_mean"]["delta"] - 0.15) < 1e-9
    assert payload["comparison"]["fallback_count"]["delta"] == 1
    assert payload["comparison"]["runtime_count_deltas"] == {"legacy": 1}
    assert payload["comparison"]["engine_count_deltas"] == {"oasis": 2, "agentsociety": -1}

    artifact_payload = read_deliberation_campaign_comparison_artifact("campaign_compare_demo")
    list_payload = list_deliberation_campaign_comparison_artifacts(limit=10)
    audit_payload = audit_deliberation_campaign_comparison_artifact("campaign_compare_demo")
    export_payload = export_deliberation_campaign_comparison_artifact("campaign_compare_demo")

    assert artifact_payload["ok"] is True
    assert artifact_payload["exists"] is True
    assert artifact_payload["result"]["comparison_id"] == "campaign_compare_demo"
    assert list_payload["ok"] is True
    assert list_payload["exists"] is True
    assert list_payload["count"] == 1
    assert list_payload["comparisons"][0]["comparison_id"] == "campaign_compare_demo"
    assert audit_payload["ok"] is True
    assert audit_payload["result"]["comparison_id"] == "campaign_compare_demo"
    assert audit_payload["result"]["comparable"] is False
    assert export_payload["ok"] is True
    assert export_payload["export_id"] == "campaign_compare_demo__markdown"
    assert export_payload["format"] == "markdown"
    assert export_payload["comparison_id"] == "campaign_compare_demo"
    assert export_payload["artifact_path"].endswith("/campaign_compare_demo__markdown/content.md")
    assert export_payload["manifest_path"].endswith("/campaign_compare_demo__markdown/manifest.json")
    assert export_payload["report_path"].endswith("/report.json")
    assert "# Deliberation Campaign Comparison" in export_payload["export"]
    assert "- Comparison ID: campaign_compare_demo" in export_payload["export"]
    assert "sample_count_mismatch, stability_runs_mismatch, comparison_key_mismatch" in export_payload["export"]

    export_artifact_payload = read_deliberation_campaign_comparison_export_artifact(
        "campaign_compare_demo",
        output_dir=tmp_path / "campaign_comparison_exports",
    )
    export_list_payload = list_deliberation_campaign_comparison_export_artifacts(
        limit=10,
        output_dir=tmp_path / "campaign_comparison_exports",
    )

    assert export_artifact_payload["ok"] is True
    assert export_artifact_payload["exists"] is True
    assert export_artifact_payload["export_id"] == "campaign_compare_demo__markdown"
    assert export_artifact_payload["format"] == "markdown"
    assert export_artifact_payload["result"]["content"].startswith("# Deliberation Campaign Comparison")
    assert export_list_payload["ok"] is True
    assert export_list_payload["exists"] is True
    assert export_list_payload["count"] == 1
    assert export_list_payload["exports"][0]["comparison_id"] == "campaign_compare_demo"
    assert export_list_payload["exports"][0]["export_id"] == "campaign_compare_demo__markdown"


def test_deliberation_campaign_tool_compare_audit_export_workflow(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    bundle_payload = {
        "comparison_id": "campaign_compare_workflow",
        "comparison_report": {
            "comparison_id": "campaign_compare_workflow",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": str(tmp_path / "comparison_reports"),
            "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
            "latest": None,
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "campaign_ids": ["campaign_alpha", "campaign_beta"],
                "comparable": True,
                "mismatch_reasons": [],
                "comparison_key_values": ["key_alpha"],
                "status_counts": {"completed": 2},
                "runtime_values": ["pydanticai"],
                "engine_values": ["agentsociety"],
                "sample_count_requested_total": 4,
                "sample_count_completed_total": 4,
                "sample_count_failed_total": 0,
                "quality_score_mean": 0.8,
                "confidence_level_mean": 0.77,
            },
            "metadata": {
                "comparison_key": "key_alpha",
                "report_path": str(tmp_path / "comparison_reports" / "campaign_compare_workflow" / "report.json"),
            },
            "report_path": str(tmp_path / "comparison_reports" / "campaign_compare_workflow" / "report.json"),
        },
        "audit": {
            "comparison_id": "campaign_compare_workflow",
            "created_at": "2026-04-08T12:00:00+00:00",
            "output_dir": str(tmp_path / "comparison_reports"),
            "report_path": str(tmp_path / "comparison_reports" / "campaign_compare_workflow" / "report.json"),
            "requested_campaign_ids": ["campaign_alpha", "campaign_beta"],
            "latest": None,
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "comparable": True,
            "mismatch_reasons": [],
            "entries": [],
            "summary": {
                "campaign_count": 2,
                "campaign_ids": ["campaign_alpha", "campaign_beta"],
                "comparable": True,
                "mismatch_reasons": [],
                "comparison_key_values": ["key_alpha"],
                "status_counts": {"completed": 2},
                "runtime_values": ["pydanticai"],
                "engine_values": ["agentsociety"],
                "sample_count_requested_total": 4,
                "sample_count_completed_total": 4,
                "sample_count_failed_total": 0,
                "quality_score_mean": 0.8,
                "confidence_level_mean": 0.77,
            },
            "markdown": "# Deliberation Campaign Comparison\n\n- Comparison ID: campaign_compare_workflow\n",
            "metadata": {"comparison_key": "key_alpha"},
        },
        "export": {
            "export_id": "campaign_compare_workflow__json",
            "created_at": "2026-04-08T12:00:01+00:00",
            "output_dir": str(tmp_path / "comparison_exports"),
            "manifest_path": str(tmp_path / "comparison_exports" / "campaign_compare_workflow__json" / "manifest.json"),
            "content_path": str(tmp_path / "comparison_exports" / "campaign_compare_workflow__json" / "content.json"),
            "comparison_id": "campaign_compare_workflow",
            "comparison_report_path": str(tmp_path / "comparison_reports" / "campaign_compare_workflow" / "report.json"),
            "format": "json",
            "campaign_count": 2,
            "campaign_ids": ["campaign_alpha", "campaign_beta"],
            "comparable": True,
            "mismatch_reasons": [],
            "content": json.dumps(
                {
                    "comparison_id": "campaign_compare_workflow",
                    "audit": True,
                },
                indent=2,
                sort_keys=True,
            ),
            "metadata": {"persisted": True},
        },
    }

    monkeypatch.setattr("swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR", tmp_path / "comparison_reports")
    monkeypatch.setattr(
        "swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR",
        tmp_path / "comparison_exports",
    )

    def fake_compare_deliberation_campaign_bundle(**kwargs):
        calls.append(kwargs)
        return type("Bundle", (), {"model_dump": lambda self, mode="json": bundle_payload})()

    monkeypatch.setattr("swarm_mcp.compare_deliberation_campaign_bundle", fake_compare_deliberation_campaign_bundle)

    payload = compare_audit_export_deliberation_campaigns(
        "campaign_alpha",
        "campaign_beta",
        format="json",
        comparison_output_dir=tmp_path / "comparison_reports",
        export_output_dir=tmp_path / "comparison_exports",
    )

    assert payload["ok"] is True
    assert payload["comparison_id"] == "campaign_compare_workflow"
    assert payload["baseline_campaign_id"] == "campaign_alpha"
    assert payload["candidate_campaign_id"] == "campaign_beta"
    assert payload["format"] == "json"
    assert payload["comparison"]["comparison_id"] == "campaign_compare_workflow"
    assert payload["audit"]["comparison_id"] == "campaign_compare_workflow"
    assert payload["export"]["export_id"] == "campaign_compare_workflow__json"
    assert payload["export_artifact_path"].endswith("/campaign_compare_workflow__json/content.json")
    assert payload["export_manifest_path"].endswith("/campaign_compare_workflow__json/manifest.json")
    assert calls[0]["campaign_ids"] == ["campaign_alpha", "campaign_beta"]
    assert calls[0]["persist"] is True
    assert str(calls[0]["comparison_output_dir"]).endswith("comparison_reports")
    assert str(calls[0]["export_output_dir"]).endswith("comparison_exports")
    assert calls[0]["format"] == "json"


def test_deliberation_campaign_tool_benchmark_runs_then_persists(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    benchmark_payload = {
        "benchmark_id": "campaign_baseline__vs__campaign_candidate",
        "created_at": "2026-04-08T12:00:00+00:00",
        "output_dir": str(tmp_path / "benchmarks"),
        "report_path": str(tmp_path / "benchmarks" / "campaign_baseline__vs__campaign_candidate" / "report.json"),
        "baseline_campaign_id": "campaign_baseline",
        "candidate_campaign_id": "campaign_candidate",
        "baseline_runtime": "pydanticai",
        "candidate_runtime": "legacy",
        "baseline_campaign": {"campaign_id": "campaign_baseline", "runtime_requested": "pydanticai"},
        "candidate_campaign": {"campaign_id": "campaign_candidate", "runtime_requested": "legacy"},
        "comparison_id": "campaign_compare_benchmark",
        "comparison": {
            "comparison_id": "campaign_compare_benchmark",
            "report_path": str(tmp_path / "comparisons" / "campaign_compare_benchmark" / "report.json"),
        },
        "audit": {
            "comparison_id": "campaign_compare_benchmark",
            "report_path": str(tmp_path / "comparisons" / "campaign_compare_benchmark" / "report.json"),
        },
        "export": {
            "export_id": "campaign_compare_benchmark__json",
            "manifest_path": str(tmp_path / "exports" / "campaign_compare_benchmark__json" / "manifest.json"),
            "content_path": str(tmp_path / "exports" / "campaign_compare_benchmark__json" / "content.json"),
            "format": "json",
        },
        "export_id": "campaign_compare_benchmark__json",
        "comparison_report_path": str(tmp_path / "comparisons" / "campaign_compare_benchmark" / "report.json"),
        "audit_report_path": str(tmp_path / "comparisons" / "campaign_compare_benchmark" / "report.json"),
        "export_manifest_path": str(tmp_path / "exports" / "campaign_compare_benchmark__json" / "manifest.json"),
        "export_content_path": str(tmp_path / "exports" / "campaign_compare_benchmark__json" / "content.json"),
    }

    def fake_run_deliberation_campaign_benchmark_sync(**kwargs):
        calls.append(kwargs)
        assert kwargs["baseline_runtime"] == "pydanticai"
        assert kwargs["candidate_runtime"] == "legacy"
        assert kwargs["baseline_engine_preference"] == "agentsociety"
        assert kwargs["candidate_engine_preference"] == "oasis"
        assert kwargs["comparison_output_dir"] == tmp_path / "comparisons"
        assert kwargs["export_output_dir"] == tmp_path / "exports"
        assert kwargs["format"] == "json"
        return type("Bundle", (), {"model_dump": lambda self, mode="json": benchmark_payload})()

    monkeypatch.setattr("swarm_mcp.run_deliberation_campaign_benchmark_sync", fake_run_deliberation_campaign_benchmark_sync)

    payload = benchmark_deliberation_campaigns(
        topic="Choose the launch strategy",
        baseline_runtime="pydanticai",
        candidate_runtime="legacy",
        baseline_engine_preference="agentsociety",
        candidate_engine_preference="oasis",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        campaign_output_dir=tmp_path / "campaigns",
        benchmark_output_dir=tmp_path / "benchmarks",
        baseline_campaign_id="campaign_baseline",
        candidate_campaign_id="campaign_candidate",
        format="json",
    )

    assert payload["ok"] is True
    assert payload["benchmark_id"] == "campaign_baseline__vs__campaign_candidate"
    assert payload["baseline_campaign_id"] == "campaign_baseline"
    assert payload["candidate_campaign_id"] == "campaign_candidate"
    assert payload["comparison_id"] == "campaign_compare_benchmark"
    assert payload["export_id"] == "campaign_compare_benchmark__json"
    assert payload["comparison"]["comparison_id"] == "campaign_compare_benchmark"
    assert payload["export"]["export_id"] == "campaign_compare_benchmark__json"
    assert payload["benchmark_report_path"].endswith("/campaign_baseline__vs__campaign_candidate/report.json")
    assert Path(payload["benchmark_report_path"]).exists()
    assert len(calls) == 1

    benchmark_calls: list[dict[str, object]] = []

    def fake_load_deliberation_campaign_benchmark(benchmark_id, **kwargs):
        benchmark_calls.append({"method": "load", "benchmark_id": benchmark_id, **kwargs})
        return type("Benchmark", (), {"model_dump": lambda self, mode="json": benchmark_payload})()

    def fake_list_deliberation_campaign_benchmarks(**kwargs):
        benchmark_calls.append({"method": "list", **kwargs})
        return [type("Benchmark", (), {"model_dump": lambda self, mode="json": benchmark_payload})()]

    monkeypatch.setattr("swarm_mcp.load_deliberation_campaign_benchmark", fake_load_deliberation_campaign_benchmark)
    monkeypatch.setattr("swarm_mcp.list_deliberation_campaign_benchmarks", fake_list_deliberation_campaign_benchmarks)

    read_payload = read_deliberation_campaign_benchmark_artifact(
        "campaign_baseline__vs__campaign_candidate",
        output_dir=tmp_path / "benchmarks",
    )
    assert read_payload["ok"] is True
    assert read_payload["exists"] is True
    assert read_payload["result"]["benchmark_id"] == "campaign_baseline__vs__campaign_candidate"

    list_payload = list_deliberation_campaign_benchmarks(output_dir=tmp_path / "benchmarks")
    assert list_payload["ok"] is True
    assert list_payload["exists"] is True
    assert list_payload["count"] == 1
    assert list_payload["benchmarks"][0]["benchmark_id"] == "campaign_baseline__vs__campaign_candidate"
    assert benchmark_calls[0]["method"] == "load"
    assert benchmark_calls[1]["method"] == "list"


def test_deliberation_campaign_benchmark_matrix_runs_grid_and_persists(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def build_payload(matrix_id: str, output_dir: Path, candidate_specs: list[object]) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        candidate_campaign_ids: list[str] = []
        comparison_ids: list[str] = []
        candidate_labels: list[str] = []

        for index, spec in enumerate(candidate_specs, start=1):
            candidate_campaign_id = str(getattr(spec, "campaign_id", f"matrix_candidate_{index:02d}"))
            candidate_label = str(getattr(spec, "label", candidate_campaign_id))
            runtime_value = str(getattr(spec, "runtime", "legacy"))
            engine_value = str(
                getattr(getattr(spec, "engine_preference", None), "value", getattr(spec, "engine_preference", "oasis"))
            )
            comparison_id = f"{matrix_id}__comparison__{index:02d}"
            candidate_campaign_ids.append(candidate_campaign_id)
            comparison_ids.append(comparison_id)
            candidate_labels.append(candidate_label)
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
                            "report_path": str(tmp_path / "comparisons" / comparison_id / "report.json"),
                            "summary": {"comparable": True},
                        },
                        "export": {
                            "export_id": f"{comparison_id}__json",
                            "manifest_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "manifest.json"),
                            "content_path": str(tmp_path / "exports" / f"{comparison_id}__json" / "content.json"),
                            "format": "json",
                        },
                    },
                }
            )

        payload = {
            "benchmark_id": matrix_id,
            "created_at": "2026-04-08T12:30:00+00:00",
            "output_dir": str(output_dir),
            "report_path": str(output_dir / matrix_id / "report.json"),
            "baseline_campaign": {
                "campaign_id": "matrix_baseline",
                "status": "completed",
            },
            "summary": {
                "candidate_count": len(entries),
                "candidate_campaign_ids": candidate_campaign_ids,
                "comparison_ids": comparison_ids,
                "candidate_labels": candidate_labels,
                "comparable_count": len(entries),
                "mismatch_count": 0,
            },
            "candidate_specs": [
                {
                    "label": str(getattr(spec, "label", "candidate")),
                    "campaign_id": str(getattr(spec, "campaign_id", "candidate")),
                    "runtime": str(getattr(spec, "runtime", "legacy")),
                    "engine_preference": str(
                        getattr(getattr(spec, "engine_preference", None), "value", getattr(spec, "engine_preference", "oasis"))
                    ),
                }
                for spec in candidate_specs
            ],
            "entries": entries,
        }
        (output_dir / matrix_id).mkdir(parents=True, exist_ok=True)
        (output_dir / matrix_id / "report.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def fake_run_deliberation_campaign_matrix_benchmark_sync(**kwargs):
        calls.append(kwargs)
        payload = build_payload(
            str(kwargs["benchmark_id"]),
            Path(kwargs["benchmark_output_dir"]),
            list(kwargs["candidate_specs"]),
        )
        return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()

    def fake_load_deliberation_campaign_matrix_benchmark(matrix_id, **kwargs):
        output_dir = Path(kwargs["output_dir"])
        payload = json.loads((output_dir / matrix_id / "report.json").read_text(encoding="utf-8"))
        return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()

    def fake_list_deliberation_campaign_matrix_benchmarks(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        payload = json.loads((output_dir / "matrix_demo" / "report.json").read_text(encoding="utf-8"))
        return [type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json": payload})()]

    monkeypatch.setattr(
        "swarm_mcp.run_deliberation_campaign_matrix_benchmark_sync",
        fake_run_deliberation_campaign_matrix_benchmark_sync,
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark",
        fake_load_deliberation_campaign_matrix_benchmark,
    )
    monkeypatch.setattr(
        "swarm_mcp.list_deliberation_campaign_matrix_benchmarks",
        fake_list_deliberation_campaign_matrix_benchmarks,
    )

    payload = benchmark_deliberation_campaign_matrix(
        topic="Choose the launch strategy",
        baseline_runtime="pydanticai",
        baseline_engine_preference="agentsociety",
        candidate_runtimes=["pydanticai", "legacy"],
        candidate_engine_preferences=["agentsociety", "oasis"],
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        campaign_output_dir=tmp_path / "campaigns",
        benchmark_output_dir=tmp_path / "benchmark-matrices",
        baseline_campaign_id="matrix_baseline",
        matrix_id="matrix_demo",
        format="json",
    )

    assert payload["ok"] is True
    assert payload["matrix_id"] == "matrix_demo"
    assert payload["cell_count"] == 4
    assert payload["candidate_runtimes"] == ["pydanticai", "legacy"]
    assert payload["candidate_engine_preferences"] == ["agentsociety", "oasis"]
    assert payload["benchmark_ids"] == [
        "matrix_baseline__vs__matrix_demo__candidate__pydanticai__agentsociety",
        "matrix_baseline__vs__matrix_demo__candidate__pydanticai__oasis",
        "matrix_baseline__vs__matrix_demo__candidate__legacy__agentsociety",
        "matrix_baseline__vs__matrix_demo__candidate__legacy__oasis",
    ]
    assert len(calls) == 1
    assert calls[0]["benchmark_id"] == "matrix_demo"
    assert len(calls[0]["candidate_specs"]) == 4
    assert {spec.runtime for spec in calls[0]["candidate_specs"]} == {"pydanticai", "legacy"}
    assert {getattr(spec.engine_preference, "value", spec.engine_preference) for spec in calls[0]["candidate_specs"]} == {"agentsociety", "oasis"}
    assert all(str(spec.campaign_id).startswith("matrix_demo__candidate__") for spec in calls[0]["candidate_specs"])
    assert Path(payload["report_path"]).exists()

    read_payload = read_deliberation_campaign_benchmark_matrix_artifact(
        "matrix_demo",
        output_dir=tmp_path / "benchmark-matrices",
    )
    assert read_payload["ok"] is True
    assert read_payload["exists"] is True
    assert read_payload["result"]["matrix_id"] == "matrix_demo"
    assert read_payload["result"]["cell_count"] == 4
    assert read_payload["result"]["cells"][0]["benchmark_id"].startswith("matrix_baseline__vs__matrix_demo__candidate__")

    list_payload = list_deliberation_campaign_benchmark_matrix_artifacts(
        output_dir=tmp_path / "benchmark-matrices",
    )
    assert list_payload["ok"] is True
    assert list_payload["exists"] is True
    assert list_payload["count"] == 1
    assert list_payload["matrices"][0]["matrix_id"] == "matrix_demo"
    assert list_payload["matrices"][0]["cell_count"] == 4


def test_compare_deliberation_campaign_benchmark_matrices_tool(monkeypatch, tmp_path: Path) -> None:
    baseline_payload = {
        "benchmark_id": "matrix_baseline",
        "matrix_id": "matrix_baseline",
        "created_at": "2026-04-08T00:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-benchmarks"),
        "report_path": str(tmp_path / "matrix-benchmarks" / "matrix_baseline" / "report.json"),
        "baseline_campaign_id": "campaign_shared",
        "summary": {
            "candidate_count": 2,
            "comparable_count": 2,
            "mismatch_count": 0,
            "quality_score_mean": 0.85,
            "confidence_level_mean": 0.78,
            "candidate_labels": ["pydanticai__agentsociety", "legacy__agentsociety"],
            "candidate_campaign_ids": ["baseline_cell_1", "baseline_cell_2"],
            "comparison_ids": ["cmp_1", "cmp_2"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety"],
        },
    }
    candidate_payload = {
        "benchmark_id": "matrix_candidate",
        "matrix_id": "matrix_candidate",
        "created_at": "2026-04-08T00:00:01+00:00",
        "output_dir": str(tmp_path / "matrix-benchmarks"),
        "report_path": str(tmp_path / "matrix-benchmarks" / "matrix_candidate" / "report.json"),
        "baseline_campaign_id": "campaign_shared",
        "summary": {
            "candidate_count": 3,
            "comparable_count": 3,
            "mismatch_count": 0,
            "quality_score_mean": 0.9,
            "confidence_level_mean": 0.8,
            "candidate_labels": ["pydanticai__agentsociety", "legacy__agentsociety", "legacy__oasis"],
            "candidate_campaign_ids": ["candidate_cell_1", "candidate_cell_2", "candidate_cell_3"],
            "comparison_ids": ["cmp_3", "cmp_4", "cmp_5"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
    }

    def _report(payload):
        return type("MatrixBenchmark", (), {"model_dump": lambda self, mode="json", payload=payload: payload})()

    def fake_load_deliberation_campaign_matrix_benchmark(matrix_id, **kwargs):
        return _report(baseline_payload if matrix_id == "matrix_baseline" else candidate_payload)

    def fake_list_deliberation_campaign_matrix_benchmarks(**kwargs):
        return [_report(candidate_payload), _report(baseline_payload)]

    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark",
        fake_load_deliberation_campaign_matrix_benchmark,
    )
    monkeypatch.setattr(
        "swarm_mcp.list_deliberation_campaign_matrix_benchmarks",
        fake_list_deliberation_campaign_matrix_benchmarks,
    )

    explicit_payload = compare_deliberation_campaign_benchmark_matrices(
        "matrix_baseline",
        "matrix_candidate",
        output_dir=tmp_path / "matrix-benchmarks",
    )

    assert explicit_payload["ok"] is True
    assert explicit_payload["baseline_matrix_id"] == "matrix_baseline"
    assert explicit_payload["candidate_matrix_id"] == "matrix_candidate"
    assert explicit_payload["comparable"] is False
    assert set(explicit_payload["mismatch_reasons"]) >= {
        "candidate_count",
        "candidate_labels",
        "candidate_campaign_ids",
        "comparison_ids",
    }
    assert explicit_payload["comparison"]["candidate_count"]["delta"] == 1
    assert explicit_payload["comparison"]["quality_score_mean"]["delta"] == 0.05
    assert explicit_payload["comparison"]["confidence_level_mean"]["delta"] == 0.02
    assert explicit_payload["result"]["candidate"]["matrix_id"] == "matrix_candidate"

    latest_payload = compare_deliberation_campaign_benchmark_matrices(
        latest=True,
        output_dir=tmp_path / "matrix-benchmarks",
    )
    assert latest_payload["ok"] is True
    assert latest_payload["latest"] is True
    assert latest_payload["baseline_matrix_id"] == "matrix_baseline"
    assert latest_payload["candidate_matrix_id"] == "matrix_candidate"
    assert latest_payload["comparison"]["matrix_id"]["changed"] is True


def test_matrix_benchmark_export_comparison_tools(monkeypatch, tmp_path: Path) -> None:
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
    }

    def payload_object(payload: dict[str, object]) -> object:
        return type("Payload", (), {"model_dump": lambda self, mode="json", payload=payload: payload})()

    monkeypatch.setattr(
        "swarm_mcp.core_compare_deliberation_campaign_matrix_benchmark_exports",
        lambda **kwargs: payload_object(comparison_payload),
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_export_comparison_report",
        lambda comparison_id, **kwargs: payload_object(comparison_payload),
    )
    monkeypatch.setattr(
        "swarm_mcp.list_deliberation_campaign_matrix_benchmark_export_comparison_reports",
        lambda **kwargs: [payload_object(comparison_payload)],
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_export_comparison_audit",
        lambda comparison_id, **kwargs: payload_object(audit_payload),
    )
    monkeypatch.setattr(
        "swarm_mcp.materialize_deliberation_campaign_matrix_benchmark_export_comparison_export",
        lambda audit, **kwargs: payload_object(export_payload),
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_export_comparison_export",
        lambda export_id, **kwargs: payload_object(export_payload),
    )
    monkeypatch.setattr(
        "swarm_mcp.list_deliberation_campaign_matrix_benchmark_export_comparison_exports",
        lambda **kwargs: [payload_object(export_payload)],
    )
    monkeypatch.setattr(
        "swarm_mcp.core_compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle",
        lambda **kwargs: payload_object(bundle_payload),
    )

    compare_payload = compare_deliberation_campaign_benchmark_matrix_exports(
        export_ids=["matrix_alpha__markdown", "matrix_beta__json"],
        output_dir=tmp_path / "matrix-exports",
        comparison_output_dir=tmp_path / "matrix-export-comparisons",
    )
    assert compare_payload["ok"] is True
    assert compare_payload["comparison_id"] == "campaign_matrix_export_compare_demo"

    read_payload = read_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
        "campaign_matrix_export_compare_demo",
        output_dir=tmp_path / "matrix-export-comparisons",
    )
    assert read_payload["ok"] is True
    assert read_payload["result"]["comparison_id"] == "campaign_matrix_export_compare_demo"

    list_payload = list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts(
        output_dir=tmp_path / "matrix-export-comparisons",
    )
    assert list_payload["ok"] is True
    assert list_payload["count"] == 1

    audit_tool_payload = audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
        "campaign_matrix_export_compare_demo",
        output_dir=tmp_path / "matrix-export-comparisons",
    )
    assert audit_tool_payload["ok"] is True
    assert audit_tool_payload["result"]["comparison_id"] == "campaign_matrix_export_compare_demo"

    export_tool_payload = export_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
        "campaign_matrix_export_compare_demo",
        comparison_output_dir=tmp_path / "matrix-export-comparisons",
        output_dir=tmp_path / "matrix-export-comparison-exports",
    )
    assert export_tool_payload["ok"] is True
    assert export_tool_payload["export_id"] == "campaign_matrix_export_compare_demo__markdown"

    read_export_payload = read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact(
        "campaign_matrix_export_compare_demo__markdown",
        output_dir=tmp_path / "matrix-export-comparison-exports",
    )
    assert read_export_payload["ok"] is True
    assert read_export_payload["result"]["export_id"] == "campaign_matrix_export_compare_demo__markdown"

    list_export_payload = list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts(
        output_dir=tmp_path / "matrix-export-comparison-exports",
    )
    assert list_export_payload["ok"] is True
    assert list_export_payload["count"] == 1

    bundle_tool_payload = compare_audit_export_deliberation_campaign_benchmark_matrix_exports(
        export_ids=["matrix_alpha__markdown", "matrix_beta__json"],
        output_dir=tmp_path / "matrix-exports",
        comparison_output_dir=tmp_path / "matrix-export-comparisons",
        export_output_dir=tmp_path / "matrix-export-comparison-exports",
    )
    assert bundle_tool_payload["ok"] is True
    assert bundle_tool_payload["comparison_id"] == "campaign_matrix_export_compare_demo"
    assert bundle_tool_payload["export_id"] == "campaign_matrix_export_compare_demo__markdown"


def test_read_and_list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    comparison_payload = {
        "comparison_id": "campaign_matrix_compare_demo",
        "created_at": "2026-04-08T12:30:00+00:00",
        "output_dir": str(tmp_path / "matrix-comparisons"),
        "report_path": str(tmp_path / "matrix-comparisons" / "campaign_matrix_compare_demo" / "report.json"),
        "requested_benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "latest": None,
        "entries": [
            {
                "benchmark_id": "matrix_alpha",
                "created_at": "2026-04-08T12:00:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.81,
                "report_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
            },
            {
                "benchmark_id": "matrix_beta",
                "created_at": "2026-04-08T12:01:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.88,
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

    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_comparison_report",
        lambda comparison_id, **kwargs: comparison_payload,
    )
    monkeypatch.setattr(
        "swarm_mcp.list_deliberation_campaign_matrix_benchmark_comparison_reports",
        lambda **kwargs: [comparison_payload],
    )

    read_payload = read_deliberation_campaign_benchmark_matrix_comparison_artifact(
        "campaign_matrix_compare_demo",
        output_dir=tmp_path / "matrix-comparisons",
    )
    assert read_payload["ok"] is True
    assert read_payload["exists"] is True
    assert read_payload["result"]["comparison_id"] == "campaign_matrix_compare_demo"
    assert read_payload["result"]["baseline_matrix_id"] == "matrix_alpha"
    assert read_payload["result"]["candidate_matrix_id"] == "matrix_beta"

    list_payload = list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
        output_dir=tmp_path / "matrix-comparisons",
    )
    assert list_payload["ok"] is True
    assert list_payload["exists"] is True
    assert list_payload["count"] == 1
    assert list_payload["comparisons"][0]["comparison_id"] == "campaign_matrix_compare_demo"
    assert list_payload["comparisons"][0]["baseline_matrix_id"] == "matrix_alpha"


def test_matrix_benchmark_audit_export_workflow(monkeypatch, tmp_path: Path) -> None:
    matrix_output_dir = tmp_path / "matrix-benchmarks"
    export_output_dir = tmp_path / "matrix-exports"
    matrix_id = "matrix_alpha"
    report_path = matrix_output_dir / matrix_id / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "matrix_id": matrix_id,
        "benchmark_id": matrix_id,
        "created_at": "2026-04-08T12:00:00+00:00",
        "output_dir": str(matrix_output_dir),
        "report_path": str(report_path),
        "baseline_campaign_id": "campaign_baseline",
        "baseline_runtime": "pydanticai",
        "baseline_engine_preference": "agentsociety",
        "candidate_count": 2,
        "candidate_campaign_ids": ["campaign_candidate_1", "campaign_candidate_2"],
        "candidate_labels": ["candidate_1", "candidate_2"],
        "comparison_ids": ["comparison_alpha_1", "comparison_alpha_2"],
        "summary": {
            "candidate_count": 2,
            "candidate_campaign_ids": ["campaign_candidate_1", "campaign_candidate_2"],
            "candidate_labels": ["candidate_1", "candidate_2"],
            "comparison_ids": ["comparison_alpha_1", "comparison_alpha_2"],
            "comparable_count": 1,
            "mismatch_count": 1,
            "quality_score_mean": 0.82,
            "quality_score_min": 0.78,
            "quality_score_max": 0.86,
            "confidence_level_mean": 0.79,
            "confidence_level_min": 0.75,
            "confidence_level_max": 0.83,
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
        "entries": [
            {
                "candidate_index": 1,
                "candidate_label": "candidate_1",
                "candidate_spec": {
                    "label": "candidate_1",
                    "campaign_id": "campaign_candidate_1",
                    "runtime": "legacy",
                    "engine_preference": "oasis",
                },
                "candidate_campaign": {"campaign_id": "campaign_candidate_1"},
                "comparison_bundle": {
                    "comparison_report": {
                        "comparison_id": "comparison_alpha_1",
                        "report_path": str(tmp_path / "comparisons" / "comparison_alpha_1" / "report.json"),
                        "summary": {
                            "comparable": True,
                            "mismatch_reasons": [],
                            "quality_score_mean": 0.78,
                            "confidence_level_mean": 0.75,
                            "comparison_key_values": ["legacy|oasis"],
                        },
                    },
                    "export": {"export_id": "comparison_alpha_1__markdown"},
                },
            },
            {
                "candidate_index": 2,
                "candidate_label": "candidate_2",
                "candidate_spec": {
                    "label": "candidate_2",
                    "campaign_id": "campaign_candidate_2",
                    "runtime": "pydanticai",
                    "engine_preference": "agentsociety",
                },
                "candidate_campaign": {"campaign_id": "campaign_candidate_2"},
                "comparison_bundle": {
                    "comparison_report": {
                        "comparison_id": "comparison_alpha_2",
                        "report_path": str(tmp_path / "comparisons" / "comparison_alpha_2" / "report.json"),
                        "summary": {
                            "comparable": False,
                            "mismatch_reasons": ["runtime_mismatch"],
                            "quality_score_mean": 0.86,
                            "confidence_level_mean": 0.83,
                            "comparison_key_values": ["pydanticai|agentsociety"],
                        },
                    },
                    "export": {"export_id": "comparison_alpha_2__markdown"},
                },
            },
        ],
        "metadata": {"baseline_runtime": "pydanticai", "baseline_engine_preference": "agentsociety"},
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark",
        lambda matrix_id, **kwargs: report_payload,
    )

    audit_payload = audit_deliberation_campaign_benchmark_matrix_artifact(
        matrix_id,
        output_dir=matrix_output_dir,
    )
    assert audit_payload["ok"] is True
    assert audit_payload["exists"] is True
    assert audit_payload["result"]["matrix_id"] == matrix_id
    assert audit_payload["result"]["candidate_count"] == 2
    assert audit_payload["result"]["best_candidate"]["candidate_label"] == "candidate_1"
    assert audit_payload["result"]["worst_candidate"]["candidate_label"] == "candidate_2"
    assert [entry["candidate_label"] for entry in audit_payload["result"]["ranking"]] == [
        "candidate_1",
        "candidate_2",
    ]

    export_payload = export_deliberation_campaign_benchmark_matrix_artifact(
        matrix_id,
        output_dir=export_output_dir,
        format="markdown",
    )
    assert export_payload["ok"] is True
    assert export_payload["export_id"] == "matrix_alpha__markdown"
    assert export_payload["format"] == "markdown"
    assert export_payload["result"]["matrix_id"] == matrix_id
    assert export_payload["result"]["content"].startswith("# Deliberation Campaign Matrix Benchmark Audit")
    assert export_payload["export"].startswith("# Deliberation Campaign Matrix Benchmark Audit")
    assert export_payload["artifact_path"].endswith("/matrix_alpha__markdown/content.md")
    assert export_payload["manifest_path"].endswith("/matrix_alpha__markdown/manifest.json")

    read_export_payload = read_deliberation_campaign_benchmark_matrix_export_artifact(
        matrix_id,
        output_dir=export_output_dir,
        format="markdown",
    )
    assert read_export_payload["ok"] is True
    assert read_export_payload["exists"] is True
    assert read_export_payload["result"]["matrix_id"] == matrix_id
    assert read_export_payload["result"]["content"].startswith("# Deliberation Campaign Matrix Benchmark Audit")

    list_export_payload = list_deliberation_campaign_benchmark_matrix_export_artifacts(
        limit=10,
        output_dir=export_output_dir,
    )
    assert list_export_payload["ok"] is True
    assert list_export_payload["exists"] is True
    assert list_export_payload["count"] == 1
    assert list_export_payload["exports"][0]["matrix_id"] == matrix_id
    assert list_export_payload["exports"][0]["export_id"] == "matrix_alpha__markdown"


def test_matrix_benchmark_comparison_audit_export_workflow(monkeypatch, tmp_path: Path) -> None:
    comparison_output_dir = tmp_path / "matrix-comparison-reports"
    export_output_dir = tmp_path / "matrix-comparison-exports"
    comparison_id = "campaign_matrix_compare_demo"
    report_path = comparison_output_dir / comparison_id / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "comparison_id": comparison_id,
        "created_at": "2026-04-08T12:30:00+00:00",
        "output_dir": str(comparison_output_dir),
        "report_path": str(report_path),
        "requested_benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "latest": None,
        "entries": [
            {
                "benchmark_id": "matrix_alpha",
                "created_at": "2026-04-08T12:00:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.81,
                "report_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
            },
            {
                "benchmark_id": "matrix_beta",
                "created_at": "2026-04-08T12:01:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.88,
                "report_path": str(tmp_path / "benchmarks" / "matrix_beta" / "report.json"),
            },
        ],
        "summary": {
            "benchmark_count": 2,
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "candidate_structure_key_values": ["legacy_oasis|pydanticai_agentsociety", "legacy_agentsociety|legacy_oasis|pydanticai_agentsociety"],
            "comparable": False,
            "mismatch_reasons": ["candidate_count_mismatch", "candidate_structure_mismatch"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
        "metadata": {"comparison_key": "key_alpha"},
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(
        "swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR",
        comparison_output_dir,
    )
    monkeypatch.setattr(
        "swarm_mcp.DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR",
        export_output_dir,
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_comparison_report",
        lambda comparison_id, **kwargs: report_payload,
    )

    audit_payload = audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
        comparison_id,
        output_dir=comparison_output_dir,
    )
    assert audit_payload["ok"] is True
    assert audit_payload["exists"] is True
    assert audit_payload["result"]["comparison_id"] == comparison_id
    assert audit_payload["result"]["benchmark_count"] == 2
    assert audit_payload["result"]["benchmark_ids"] == ["matrix_alpha", "matrix_beta"]
    assert audit_payload["result"]["overview"]["comparable"] is False
    assert audit_payload["result"]["overview"]["report_path"] == str(report_path)

    export_payload = export_deliberation_campaign_benchmark_matrix_comparison_artifact(
        comparison_id,
        comparison_output_dir=comparison_output_dir,
        output_dir=export_output_dir,
        format="json",
    )
    assert export_payload["ok"] is True
    assert export_payload["export_id"] == "campaign_matrix_compare_demo__json"
    assert export_payload["format"] == "json"
    assert export_payload["result"]["comparison_id"] == comparison_id
    assert export_payload["result"]["content"].startswith("{")
    assert export_payload["export"].startswith("{")
    assert export_payload["artifact_path"].endswith("/campaign_matrix_compare_demo__json/content.json")
    assert export_payload["manifest_path"].endswith("/campaign_matrix_compare_demo__json/manifest.json")

    read_export_payload = read_deliberation_campaign_benchmark_matrix_comparison_export_artifact(
        comparison_id,
        output_dir=export_output_dir,
        format="json",
    )
    assert read_export_payload["ok"] is True
    assert read_export_payload["exists"] is True
    assert read_export_payload["result"]["comparison_id"] == comparison_id
    assert read_export_payload["result"]["content"].startswith("{")

    list_export_payload = list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts(
        limit=10,
        output_dir=export_output_dir,
    )
    assert list_export_payload["ok"] is True
    assert list_export_payload["exists"] is True
    assert list_export_payload["count"] == 1
    assert list_export_payload["exports"][0]["comparison_id"] == comparison_id
    assert list_export_payload["exports"][0]["format"] == "json"


def test_compare_audit_export_deliberation_campaign_benchmark_matrices_tool(
    monkeypatch,
    tmp_path: Path,
) -> None:
    comparison_output_dir = tmp_path / "matrix-comparison-reports"
    export_output_dir = tmp_path / "matrix-comparison-exports"
    comparison_id = "campaign_matrix_compare_demo"
    report_path = comparison_output_dir / comparison_id / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "comparison_id": comparison_id,
        "created_at": "2026-04-08T12:30:00+00:00",
        "output_dir": str(comparison_output_dir),
        "report_path": str(report_path),
        "requested_benchmark_ids": ["matrix_alpha", "matrix_beta"],
        "latest": None,
        "entries": [
            {
                "benchmark_id": "matrix_alpha",
                "created_at": "2026-04-08T12:00:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.81,
                "report_path": str(tmp_path / "benchmarks" / "matrix_alpha" / "report.json"),
            },
            {
                "benchmark_id": "matrix_beta",
                "created_at": "2026-04-08T12:01:00+00:00",
                "baseline_campaign_id": "campaign_shared",
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
                "confidence_level_mean": 0.88,
                "report_path": str(tmp_path / "benchmarks" / "matrix_beta" / "report.json"),
            },
        ],
        "summary": {
            "benchmark_count": 2,
            "benchmark_ids": ["matrix_alpha", "matrix_beta"],
            "candidate_structure_key_values": ["legacy_oasis|pydanticai_agentsociety", "legacy_agentsociety|legacy_oasis|pydanticai_agentsociety"],
            "comparable": False,
            "mismatch_reasons": ["candidate_count_mismatch", "candidate_structure_mismatch"],
            "runtime_values": ["legacy", "pydanticai"],
            "engine_values": ["agentsociety", "oasis"],
        },
        "metadata": {"comparison_key": "key_alpha"},
    }

    def fake_compare_deliberation_campaign_matrix_benchmarks(**kwargs):
        assert kwargs["benchmark_ids"] == ["matrix_alpha", "matrix_beta"]
        assert kwargs["persist"] is True
        assert kwargs["comparison_output_dir"] == comparison_output_dir
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
        return type("MatrixComparisonReport", (), {"model_dump": lambda self, mode="json": report_payload})()

    monkeypatch.setattr(
        "swarm_mcp.compare_deliberation_campaign_matrix_benchmarks",
        fake_compare_deliberation_campaign_matrix_benchmarks,
    )
    monkeypatch.setattr(
        "swarm_mcp.load_deliberation_campaign_matrix_benchmark_comparison_report",
        lambda comparison_id, **kwargs: report_payload,
    )

    payload = compare_audit_export_deliberation_campaign_benchmark_matrices(
        "matrix_alpha",
        "matrix_beta",
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        format="json",
    )

    assert payload["ok"] is True
    assert payload["comparison_id"] == comparison_id
    assert payload["baseline_matrix_id"] == "matrix_alpha"
    assert payload["candidate_matrix_id"] == "matrix_beta"
    assert payload["comparison"]["comparison_id"] == comparison_id
    assert payload["audit"]["comparison_id"] == comparison_id
    assert payload["export"].startswith("{")
    assert payload["export_payload"]["format"] == "json"
    assert payload["export_artifact_path"].endswith("/campaign_matrix_compare_demo__json/content.json")
    assert payload["export_manifest_path"].endswith("/campaign_matrix_compare_demo__json/manifest.json")


def test_deliberation_campaign_index_aggregates_recent_artifacts(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_build_deliberation_campaign_artifact_index(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "limit": kwargs["limit"],
            "campaign_output_dir": str(kwargs["campaign_output_dir"]),
            "benchmark_output_dir": str(kwargs["benchmark_output_dir"]),
            "matrix_benchmark_output_dir": str(kwargs["matrix_benchmark_output_dir"]),
            "matrix_benchmark_export_output_dir": str(kwargs["matrix_benchmark_export_output_dir"]),
            "comparison_output_dir": str(kwargs["comparison_output_dir"]),
            "export_output_dir": str(kwargs["export_output_dir"]),
            "counts": {
                "campaigns": 2,
                "benchmarks": 1,
                "matrix_benchmarks": 1,
                "matrix_benchmark_exports": 1,
                "comparisons": 1,
                "exports": 1,
            },
            "campaigns": [{"campaign_id": "campaign_alpha"}, {"campaign_id": "campaign_beta"}],
            "benchmarks": [{"benchmark_id": "benchmark_alpha"}],
            "matrix_benchmarks": [{"benchmark_id": "matrix_alpha"}],
            "matrix_benchmark_exports": [{"export_id": "matrix_export_alpha"}],
            "comparisons": [{"comparison_id": "comparison_alpha"}],
            "exports": [{"export_id": "export_alpha"}],
            "metadata": {"limit": kwargs["limit"], "artifact_count": 7},
        }

    monkeypatch.setattr("swarm_mcp.build_deliberation_campaign_artifact_index", fake_build_deliberation_campaign_artifact_index)
    monkeypatch.setattr(
        "swarm_mcp._list_deliberation_campaign_benchmark_matrix_export_artifacts",
        lambda **kwargs: {"count": 1, "exports": [{"export_id": "matrix_export_alpha"}]},
    )

    payload = deliberation_campaign_index(
        limit=5,
        campaign_output_dir=tmp_path / "campaigns",
        benchmark_output_dir=tmp_path / "benchmarks",
        matrix_benchmark_output_dir=tmp_path / "matrix-benchmarks",
        matrix_benchmark_export_output_dir=tmp_path / "matrix-benchmark-exports",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
    )

    assert payload["ok"] is True
    assert payload["counts"] == {
        "campaigns": 2,
        "benchmarks": 1,
        "matrix_benchmarks": 1,
        "matrix_benchmark_exports": 1,
        "comparisons": 1,
        "exports": 1,
    }
    assert payload["benchmarks"][0]["benchmark_id"] == "benchmark_alpha"
    assert payload["matrix_benchmarks"][0]["benchmark_id"] == "matrix_alpha"
    assert payload["matrix_benchmark_exports"][0]["export_id"] == "matrix_export_alpha"
    assert payload["comparisons"][0]["comparison_id"] == "comparison_alpha"
    assert payload["exports"][0]["export_id"] == "export_alpha"
    assert captured == {
        "limit": 5,
        "campaign_output_dir": tmp_path / "campaigns",
        "benchmark_output_dir": tmp_path / "benchmarks",
        "matrix_benchmark_output_dir": tmp_path / "matrix-benchmarks",
        "matrix_benchmark_export_output_dir": tmp_path / "matrix-benchmark-exports",
        "comparison_output_dir": tmp_path / "comparisons",
        "export_output_dir": tmp_path / "exports",
    }


def test_deliberation_campaign_artifact_index_includes_matrix_benchmarks(monkeypatch, tmp_path: Path) -> None:
    campaign = {"campaign_id": "campaign_alpha"}
    benchmark = {"benchmark_id": "benchmark_alpha"}
    comparison = {"comparison_id": "comparison_alpha"}
    export = {"export_id": "export_alpha"}
    matrix_benchmark = {
        "benchmark_id": "matrix_alpha",
        "created_at": "2026-04-08T00:00:00+00:00",
        "output_dir": str(tmp_path / "matrix-benchmarks"),
        "report_path": str(tmp_path / "matrix-benchmarks" / "matrix_alpha" / "report.json"),
        "baseline_campaign_id": "campaign_baseline",
        "candidate_count": 2,
        "candidate_campaign_ids": ["campaign_candidate_1", "campaign_candidate_2"],
        "candidate_labels": ["candidate_1", "candidate_2"],
        "comparison_ids": ["matrix_alpha__comparison__01", "matrix_alpha__comparison__02"],
        "comparable_count": 2,
        "mismatch_count": 0,
        "quality_score_mean": 0.88,
        "confidence_level_mean": 0.81,
    }

    monkeypatch.setattr("swarm_core.deliberation_campaign._campaign_report_overview", lambda report: report)
    monkeypatch.setattr("swarm_core.deliberation_campaign._comparison_report_overview", lambda report: report)
    monkeypatch.setattr("swarm_core.deliberation_campaign._comparison_export_overview", lambda report: report)
    monkeypatch.setattr("swarm_core.deliberation_campaign._benchmark_report_overview", lambda report: report)
    monkeypatch.setattr("swarm_core.deliberation_campaign._matrix_benchmark_report_overview", lambda report: report)
    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_reports", lambda **kwargs: [campaign])
    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_benchmarks", lambda **kwargs: [benchmark])
    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_reports", lambda **kwargs: [comparison])
    monkeypatch.setattr("swarm_core.deliberation_campaign.list_deliberation_campaign_comparison_exports", lambda **kwargs: [export])
    monkeypatch.setattr(
        "swarm_core.deliberation_campaign.list_deliberation_campaign_matrix_benchmarks",
        lambda **kwargs: [matrix_benchmark],
    )
    monkeypatch.setattr(
        "swarm_mcp._list_deliberation_campaign_benchmark_matrix_export_artifacts",
        lambda **kwargs: {
            "count": 1,
            "exports": [{"export_id": "matrix_export_alpha"}],
        },
    )

    index = build_deliberation_campaign_artifact_index(
        campaign_output_dir=tmp_path / "campaigns",
        benchmark_output_dir=tmp_path / "benchmarks",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
        matrix_benchmark_output_dir=tmp_path / "matrix-benchmarks",
        limit=1,
    )

    assert index.output_dirs == {
        "campaigns": str(tmp_path / "campaigns"),
        "comparisons": str(tmp_path / "comparisons"),
        "exports": str(tmp_path / "exports"),
        "benchmarks": str(tmp_path / "benchmarks"),
        "matrix_benchmarks": str(tmp_path / "matrix-benchmarks"),
        "matrix_benchmark_exports": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_exports")
        ),
        "matrix_benchmark_export_comparisons": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_export_comparisons")
        ),
        "matrix_benchmark_export_comparison_exports": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_export_comparison_exports")
        ),
        "matrix_benchmark_comparisons": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_comparisons")
        ),
        "matrix_benchmark_comparison_exports": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_comparison_exports")
        ),
    }
    assert index.counts == {
        "campaigns": 1,
        "comparisons": 1,
        "exports": 1,
        "benchmarks": 1,
        "matrix_benchmarks": 1,
        "matrix_benchmark_exports": 0,
        "matrix_benchmark_export_comparisons": 0,
        "matrix_benchmark_export_comparison_exports": 0,
        "matrix_benchmark_comparisons": 0,
        "matrix_benchmark_comparison_exports": 0,
    }
    assert index.campaigns == [campaign]
    assert index.benchmarks == [benchmark]
    assert index.comparisons == [comparison]
    assert index.exports == [export]
    assert index.matrix_benchmarks == [matrix_benchmark]
    assert index.metadata["artifact_count"] == 5
    assert index.metadata["limit"] == 1


def test_deliberation_campaign_dashboard_delegates_to_core_helper(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    dashboard_payload = {
        "generated_at": "2026-04-08T00:00:00+00:00",
        "kinds": ["campaign", "comparison", "matrix_benchmark"],
        "limit": 5,
        "sort_by": "quality_score_mean",
        "campaign_status": "completed",
        "comparable_only": True,
        "rows": [
            {
                "artifact_kind": "comparison",
                "artifact_id": "comparison_alpha",
                "created_at": "2026-04-08T00:00:00+00:00",
                "status": "comparable",
                "comparable": True,
                "quality_score_mean": 0.91,
                "confidence_level_mean": 0.73,
                "runtime_summary": "pydanticai, legacy",
                "engine_summary": "agentsociety, oasis",
                "artifact_path": str(tmp_path / "comparisons" / "comparison_alpha" / "report.json"),
                "metadata": {"comparison_id": "comparison_alpha"},
            },
            {
                "artifact_kind": "matrix_benchmark_export",
                "artifact_id": "matrix_export_alpha",
                "created_at": "2026-04-08T00:30:00+00:00",
                "status": "comparable",
                "comparable": True,
                "quality_score_mean": 0.85,
                "confidence_level_mean": 0.77,
                "runtime_summary": "",
                "engine_summary": "",
                "artifact_path": str(tmp_path / "matrix_benchmark_exports" / "matrix_export_alpha" / "manifest.json"),
                "metadata": {
                    "benchmark_id": "benchmark_baseline_alpha",
                    "mismatch_count": 0,
                },
            },
            {
                "artifact_kind": "matrix_benchmark",
                "artifact_id": "matrix_alpha",
                "created_at": "2026-04-08T00:00:00+00:00",
                "status": "comparable",
                "comparable": True,
                "quality_score_mean": 0.88,
                "confidence_level_mean": 0.81,
                "runtime_summary": "pydanticai, legacy",
                "engine_summary": "agentsociety, oasis",
                "artifact_path": str(tmp_path / "matrix-benchmarks" / "matrix_alpha" / "report.json"),
                "metadata": {
                    "baseline_campaign_id": "campaign_baseline",
                    "candidate_count": 2,
                    "comparison_ids": ["matrix_alpha__comparison__01", "matrix_alpha__comparison__02"],
                },
            }
        ],
        "counts": {"comparison": 1, "matrix_benchmark": 1, "matrix_benchmark_export": 1},
        "metadata": {
            "row_count": 3,
            "matrix_benchmark_count": 1,
            "matrix_benchmark_export_count": 1,
            "source_counts": {
                "campaigns": 0,
                "comparisons": 1,
                "exports": 0,
                "benchmarks": 0,
                "matrix_benchmarks": 1,
                "matrix_benchmark_exports": 1,
            },
        },
    }

    class FakeDashboard:
        def model_dump(self, mode="json"):
            return dashboard_payload

    def fake_build_deliberation_campaign_dashboard(**kwargs):
        captured.update(kwargs)
        return FakeDashboard()

    monkeypatch.setattr("swarm_mcp.build_deliberation_campaign_dashboard", fake_build_deliberation_campaign_dashboard)

    payload = deliberation_campaign_dashboard(
        kinds=["campaigns", "comparisons", "matrix_benchmarks"],
        limit=5,
        sort_by="quality_score_mean",
        campaign_status="completed",
        comparable_only=True,
        campaign_output_dir=tmp_path / "campaigns",
        benchmark_output_dir=tmp_path / "benchmarks",
        matrix_benchmark_output_dir=tmp_path / "matrix-benchmarks",
        matrix_benchmark_export_output_dir=tmp_path / "matrix-benchmark-exports",
        comparison_output_dir=tmp_path / "comparisons",
        export_output_dir=tmp_path / "exports",
    )

    assert payload["ok"] is True
    assert captured == {
        "campaign_output_dir": tmp_path / "campaigns",
        "comparison_output_dir": tmp_path / "comparisons",
        "export_output_dir": tmp_path / "exports",
        "benchmark_output_dir": tmp_path / "benchmarks",
        "matrix_benchmark_output_dir": tmp_path / "matrix-benchmarks",
        "matrix_benchmark_export_output_dir": tmp_path / "matrix-benchmark-exports",
        "kinds": ["campaigns", "comparisons", "matrix_benchmarks"],
        "limit": 5,
        "sort_by": "quality_score_mean",
        "campaign_status": "completed",
        "comparable_only": True,
    }
    assert payload["output_dirs"] == {
        "campaigns": str(tmp_path / "campaigns"),
        "benchmarks": str(tmp_path / "benchmarks"),
        "matrix_benchmarks": str(tmp_path / "matrix-benchmarks"),
        "matrix_benchmark_exports": str(tmp_path / "matrix-benchmark-exports"),
        "matrix_benchmark_comparisons": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_comparisons")
        ),
        "matrix_benchmark_comparison_exports": str(
            Path("/home/jul/swarm/data/deliberation_campaign_matrix_benchmark_comparison_exports")
        ),
        "comparisons": str(tmp_path / "comparisons"),
        "exports": str(tmp_path / "exports"),
    }
    assert payload["rows"][0]["artifact_id"] == "comparison_alpha"
    assert payload["rows"][1]["artifact_kind"] == "matrix_benchmark_export"
    assert payload["rows"][2]["artifact_kind"] == "matrix_benchmark"
    assert payload["counts"] == {
        "comparison": 1,
        "matrix_benchmark_export": 1,
        "matrix_benchmark": 1,
    }
    assert payload["metadata"]["matrix_benchmark_count"] == 1
    assert payload["metadata"]["matrix_benchmark_export_count"] == 1
    assert payload["metadata"]["source_counts"]["matrix_benchmarks"] == 1
    assert payload["metadata"]["source_counts"]["matrix_benchmark_exports"] == 1
    assert payload["metadata"]["output_dirs"] == payload["output_dirs"]


def test_advanced_deliberation_tools_return_structured_payloads(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    store = GraphStore(graph_path, name="demo_graph")
    store.add_node(GraphNode(node_id="agent_1", label="Agent One", node_type="persona"))
    store.save(graph_path)
    fake_result = DeliberationResult(
        deliberation_id="delib_demo",
        topic="Choose the launch strategy",
        objective="Define the best strategy",
        mode=DeliberationMode.hybrid,
        status=DeliberationStatus.completed,
        runtime_requested="pydanticai",
        runtime_used="pydanticai",
        fallback_used=False,
        engine_requested="agentsociety",
        engine_used="agentsociety",
        summary="Population reaction is cautious but positive.",
        final_strategy="Roll out in stages.",
        confidence_level=0.72,
        graph_path=str(graph_path),
    )

    monkeypatch.setattr("swarm_mcp.load_deliberation_result", lambda deliberation_id: fake_result)
    monkeypatch.setattr(
        "swarm_mcp.collect_deliberation_targets",
        lambda deliberation_id: [
            DeliberationInterviewTarget(
                target_id="agent_guardian",
                target_type=DeliberationInterviewTargetType.agent,
                label="guardian",
                description="Risk-focused participant",
            )
        ],
    )

    chat_payload = persona_chat_deliberation("delib_demo", question="What worries you most?")
    neo4j_payload = export_deliberation_neo4j("delib_demo")
    bridge_payload = bridge_deliberation_market("delib_demo")

    assert chat_payload["ok"] is True
    assert chat_payload["result"]["deliberation_id"] == "delib_demo"
    assert neo4j_payload["ok"] is True
    assert neo4j_payload["result"]["backend"] == "neo4j"
    assert bridge_payload["ok"] is True
    assert bridge_payload["result"]["topic"] == "Choose the launch strategy"


def test_delegate_to_swarm_supervisor_launches_background_process(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_popen(command, stdout, stderr, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess(return_code=None)

    monkeypatch.setattr("swarm_mcp.REPO_ROOT", tmp_path)
    monkeypatch.setattr("swarm_mcp.MAIN_SCRIPT", tmp_path / "main.py")
    monkeypatch.setattr("swarm_mcp.PYTHON_BIN", tmp_path / "venv" / "bin" / "python")
    monkeypatch.setattr("swarm_mcp.subprocess.Popen", fake_popen)
    monkeypatch.setattr("swarm_mcp.time.sleep", lambda _: None)

    payload = delegate_to_swarm_supervisor("Do the thing", thread_id="mission_abc123")

    assert payload["ok"] is True
    assert payload["thread_id"] == "mission_abc123"
    assert payload["status"] == "launched"
    assert payload["log_file"].endswith("mission_abc123.log")
    assert captured["command"][2] == "delegate"


def test_coerce_loop_mode_rejects_invalid_values() -> None:
    try:
        _coerce_loop_mode("not_a_mode")
    except ValueError as exc:
        assert "Unsupported loop mode" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid loop mode")


def test_strategy_meeting_tools_round_trip(monkeypatch, tmp_path: Path) -> None:
    meeting_artifact = tmp_path / "meeting_demo.json"
    meeting_artifact.write_text(
        json.dumps({"meeting_id": "meeting_demo", "strategy": "Ship the safe option."}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "swarm_mcp._run_strategy_meeting_session",
        lambda **kwargs: {
            "ok": True,
            "result": {
                "meeting_id": "meeting_demo",
                "status": "completed",
                "participants": ["architect", "veille-strategique"],
                "strategy": "Ship the safe option.",
                "metadata": {
                    "runtime_used": "pydanticai",
                    "fallback_used": False,
                    "model_name": "claude-sonnet-4-6",
                    "provider_base_url": "https://api.anthropic.com",
                    "phase_counts": {"independent": 1, "critique": 1, "synthesis": 1},
                    "role_counts": {"participant": 2, "critic": 1},
                    "dissent_turn_count": 1,
                },
            },
            "runtime_requested": "pydanticai",
            "runtime_used": "pydanticai",
            "fallback_used": False,
            "run_id": "meeting_demo",
            "config_path": "config.yaml",
            "runtime_id": "claude-sonnet-4-6",
        },
    )
    monkeypatch.setattr("swarm_mcp.DEFAULT_STRATEGY_MEETING_OUTPUT_DIR", tmp_path)

    run_payload = run_strategy_meeting(
        topic="Choose the next product strategy",
        participants=["architect", "veille-strategique"],
        max_agents=2,
    )
    artifact_payload = read_strategy_meeting_artifact("meeting_demo")

    assert run_payload["ok"] is True
    assert run_payload["result"]["meeting_id"] == "meeting_demo"
    assert run_payload["runtime_requested"] == "pydanticai"
    assert run_payload["runtime_used"] == "pydanticai"
    assert run_payload["fallback_used"] is False
    assert run_payload["run_id"] == "meeting_demo"
    assert run_payload["config_path"] == "config.yaml"
    assert run_payload["runtime_id"] == "claude-sonnet-4-6"
    assert run_payload["resilience_summary"]["runtime"]["matched"] is True
    assert run_payload["resilience_summary"]["comparability"]["run_id"] == "meeting_demo"
    assert run_payload["resilience_summary"]["comparability"]["config_id"] == "config.yaml"
    assert run_payload["resilience_summary"]["comparability"]["runtime_id"] == "claude-sonnet-4-6"
    assert run_payload["resilience_summary"]["comparability"]["phase_count"] == 3
    assert run_payload["resilience_summary"]["comparability"]["role_count"] == 2
    assert run_payload["resilience_summary"]["comparability"]["dissent_turn_count"] == 1
    assert artifact_payload["ok"] is True
    assert artifact_payload["exists"] is True
    assert artifact_payload["result"]["strategy"] == "Ship the safe option."


def test_run_strategy_meeting_tool_falls_back_to_legacy_when_pydanticai_runtime_is_unavailable(monkeypatch) -> None:
    calls = []

    def fake_run_strategy_meeting_sync(**kwargs):
        calls.append(kwargs)
        if kwargs["runtime"] == "pydanticai":
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
            strategy="Ship the safe option.",
            consensus_points=["Protect reliability"],
            dissent_points=["Some prefer speed"],
            next_actions=["Define the canary gates"],
            metadata={"runtime_used": "legacy", "fallback_used": True},
        )

    monkeypatch.setattr("swarm_core.strategy_meeting.run_strategy_meeting_sync", fake_run_strategy_meeting_sync)

    payload = run_strategy_meeting(
        topic="Choose the next product strategy",
        participants=["architect", "veille-strategique"],
        max_agents=2,
        rounds=1,
        persist=False,
    )

    assert payload["ok"] is True
    assert len(calls) == 2
    assert calls[0]["runtime"] == "pydanticai"
    assert calls[1]["runtime"] == "legacy"
    assert payload["runtime_requested"] == "pydanticai"
    assert payload["runtime_used"] == "legacy"
    assert payload["fallback_used"] is True
    assert payload["result"]["metadata"]["runtime_error"] == "pydanticai unavailable"


def test_runtime_health_tool_returns_report(monkeypatch) -> None:
    monkeypatch.setattr(
        "swarm_mcp._collect_runtime_health",
        lambda runtime_name="all": {
            "ok": True,
            "report": {"runtime": runtime_name, "status": "healthy"},
        },
    )

    payload = runtime_health("pydanticai")

    assert payload["ok"] is True
    assert payload["report"]["runtime"] == "pydanticai"
    assert payload["report"]["status"] == "healthy"
