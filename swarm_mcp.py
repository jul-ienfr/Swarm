from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from improvement_loop import ImprovementRuntime, LoopMode, build_default_controller
from prediction_markets import (
    RunRegistry,
    TradeSide,
    additional_venues_catalog_sync,
    advise_market_sync,
    allocate_market_sync,
    analyze_market_comments_sync,
    assess_market_arbitrage_sync,
    assess_market_risk_sync,
    build_market_graph_sync,
    cross_venue_intelligence_sync,
    guard_market_manipulation_sync,
    ingest_twitter_watcher_sidecar_sync,
    ingest_worldmonitor_sidecar_sync,
    live_execute_market_sync,
    market_events_sync,
    market_execution_sync,
    market_positions_sync,
    market_stream_health_sync,
    market_stream_summary_sync,
    multi_venue_paper_sync,
    monitor_market_spreads_sync,
    open_market_stream_sync,
    paper_trade_market_sync,
    reconcile_market_run_sync,
    research_market_sync,
    replay_market_run_sync,
    simulate_market_slippage_sync,
    shadow_trade_market_sync,
)
from prediction_markets.compat import stream_collect_sync, simulate_microstructure_lab_sync
from prediction_markets.compat import replay_market_postmortem_sync
from runtime_langgraph import build_status_config, compile_graph, json_safe
from swarm_core.deliberation import load_deliberation_result, replay_deliberation_sync
from swarm_core.deliberation_campaign import (
    DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR,
    DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR as CORE_DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
    DeliberationCampaignStatus,
    build_deliberation_campaign_artifact_index,
    build_deliberation_campaign_dashboard,
    DeliberationCampaignBenchmarkBundle,
    DeliberationCampaignMatrixCandidateSpec,
    build_deliberation_campaign_comparison_audit,
    compare_deliberation_campaign_bundle,
    DeliberationCampaignComparisonExport,
    DeliberationCampaignComparisonReport,
    compare_deliberation_campaign_reports,
    compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle as core_compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle,
    compare_deliberation_campaign_matrix_benchmark_exports as core_compare_deliberation_campaign_matrix_benchmark_exports,
    load_deliberation_campaign_benchmark,
    load_deliberation_campaign_matrix_benchmark_export_comparison_report,
    load_deliberation_campaign_matrix_benchmark_comparison_report,
    load_deliberation_campaign_matrix_benchmark,
    load_deliberation_campaign_comparison_report,
    load_deliberation_campaign_comparison_audit,
    load_deliberation_campaign_comparison_export,
    load_deliberation_campaign_report,
    load_deliberation_campaign_matrix_benchmark_export_comparison_audit,
    load_deliberation_campaign_matrix_benchmark_export_comparison_export,
    compare_deliberation_campaign_matrix_benchmarks,
    list_deliberation_campaign_comparison_exports,
    list_deliberation_campaign_comparison_reports,
    list_deliberation_campaign_benchmarks,
    list_deliberation_campaign_matrix_benchmark_export_comparison_reports,
    list_deliberation_campaign_matrix_benchmark_export_comparison_exports,
    list_deliberation_campaign_matrix_benchmark_comparison_reports,
    list_deliberation_campaign_matrix_benchmarks,
    list_deliberation_campaign_reports,
    materialize_deliberation_campaign_comparison_export,
    materialize_deliberation_campaign_matrix_benchmark_export_comparison_export,
    render_deliberation_campaign_comparison_markdown,
    run_deliberation_campaign_benchmark_sync,
    run_deliberation_campaign_matrix_benchmark_sync,
    run_deliberation_campaign_sync,
)
from swarm_core.deliberation_interview import (
    interview_deliberation_sync as run_deliberation_interview_sync,
    list_deliberation_targets as collect_deliberation_targets,
)
from swarm_core.deliberation_persona_chat import DeliberationPersonaChatService
from swarm_core.deep_market_social_bridge import (
    DeepMarketSocialBridge,
    MarketSignal,
    MarketSocialBridgeRequest,
    SignalDirection,
    SocialSentiment,
    SocialSignal,
)
from swarm_core.graph_backend_adapter import Neo4jFriendlyGraphBackendAdapter
from swarm_core.graph_store import GraphStore
from swarm_core.orchestration import (
    RuntimeBackend,
    normalize_runtime_backend,
    run_deliberation_runtime,
    run_strategy_meeting_runtime,
    runtime_capabilities,
    runtime_health as collect_runtime_health,
)
from swarm_core.benchmark_suite import BenchmarkProfile
from swarm_core import (
    DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH,
    DEFAULT_BENCHMARK_SUITE_PATH,
    DEFAULT_DELIBERATION_OUTPUT_DIR,
    DEFAULT_HARNESS_MEMORY_PATH,
    DEFAULT_STRATEGY_MEETING_OUTPUT_DIR,
    inspect_harness,
)


REPO_ROOT = Path(__file__).resolve().parent
MAIN_SCRIPT = REPO_ROOT / "main.py"
PYTHON_BIN = REPO_ROOT / "venv" / "bin" / "python"
DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_COMPARISON_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR = (
    REPO_ROOT / "data" / "deliberation_campaign_matrix_benchmark_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR = (
    CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR = (
    REPO_ROOT / "data" / "deliberation_campaign_matrix_benchmark_comparison_exports"
)
DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR = CORE_DEFAULT_DELIBERATION_CAMPAIGN_MATRIX_BENCHMARK_OUTPUT_DIR
MCP_SERVER_NAME = "Swarm MCP"

mcp = FastMCP(MCP_SERVER_NAME)


def _success(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def _failure(message: str, *, error_code: str = "operation_failed", **payload: Any) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "message": message, **payload}


@lru_cache(maxsize=1)
def _get_graph():
    return compile_graph()


def _as_improvement_runtime(runtime: str | RuntimeBackend) -> ImprovementRuntime:
    return ImprovementRuntime(normalize_runtime_backend(runtime).value)


def _get_improvement_controller(
    *,
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
):
    return build_default_controller(
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
    )


def _improvement_runtime_metadata(
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    *,
    runtime_used: str | None = None,
    fallback_used: bool | None = None,
    allow_fallback: bool = True,
    executed: bool = True,
) -> dict[str, Any]:
    selected = normalize_runtime_backend(runtime)
    execution_runtime = runtime_used if runtime_used is not None else (None if not executed else selected.value)
    return {
        "runtime_requested": selected.value,
        "runtime_used": execution_runtime,
        "fallback_used": bool(fallback_used),
        "allow_fallback": allow_fallback,
        "executed": executed,
    }


def _coerce_loop_mode(mode: str | LoopMode) -> LoopMode:
    if isinstance(mode, LoopMode):
        return mode
    try:
        return LoopMode(str(mode).strip())
    except ValueError as exc:
        allowed = ", ".join(loop_mode.value for loop_mode in LoopMode)
        raise ValueError(f"Unsupported loop mode {mode!r}. Expected one of: {allowed}.") from exc


def _mission_log_path(thread_id: str) -> Path:
    return REPO_ROOT / f"{thread_id}.log"


def _launch_background_command(*, command: list[str], thread_id: str, action: str) -> dict[str, Any]:
    log_file = _mission_log_path(thread_id)
    try:
        with log_file.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                cwd=str(REPO_ROOT),
            )
        time.sleep(0.5)
        return_code = process.poll()
        if return_code is not None:
            tail = ""
            try:
                tail = "\n".join(log_file.read_text(encoding="utf-8").splitlines()[-20:])
            except OSError:
                tail = ""
            return _failure(
                f"Swarm process exited immediately while trying to {action}.",
                error_code="process_exited",
                thread_id=thread_id,
                return_code=return_code,
                log_file=str(log_file),
                log_tail=tail,
            )
        return _success(
            action=action,
            thread_id=thread_id,
            status="launched",
            log_file=str(log_file),
            command=command,
        )
    except Exception as exc:
        return _failure(
            f"Failed to {action}: {exc}",
            error_code="launch_failed",
            thread_id=thread_id,
            log_file=str(log_file),
        )


def _collect_mission_status(thread_id: str) -> dict[str, Any]:
    graph = _get_graph()
    state = graph.get_state(build_status_config(thread_id))
    if not getattr(state, "values", None):
        return _success(
            thread_id=thread_id,
            found=False,
            state=None,
            next_nodes=[],
            message="No mission state found for this thread.",
        )

    values = json_safe(state.values)
    task_ledger = values.get("task_ledger", {}) if isinstance(values, dict) else {}
    progress_ledger = values.get("progress_ledger", {}) if isinstance(values, dict) else {}
    current_intent = task_ledger.get("current_intent", {})
    simulation_result = task_ledger.get("simulation_result") or progress_ledger.get("simulation_result")

    return _success(
        thread_id=thread_id,
        found=True,
        state={
            "goal": task_ledger.get("goal"),
            "current_intent": current_intent,
            "progress": progress_ledger,
            "simulation_result": simulation_result,
            "tokens_used_total": values.get("tokens_used_total", 0),
        },
        next_nodes=list(getattr(state, "next", ()) or []),
    )


def _collect_improvement_targets() -> dict[str, Any]:
    controller = _get_improvement_controller()
    return _success(
        targets=[descriptor.model_dump(mode="json") for descriptor in controller.list_targets()],
        **_improvement_runtime_metadata(executed=False),
    )


def _collect_improvement_inspection(
    target: str,
    *,
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    inspection = controller.inspect_target(
        target,
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    return _enrich_improvement_resilience_payload(
        _success(
            inspection=inspection.model_dump(mode="json"),
            **_improvement_runtime_metadata(
                runtime,
                runtime_used=inspection.runtime_used.value,
                fallback_used=inspection.fallback_used,
                allow_fallback=allow_fallback,
            ),
        )
    )


def _run_improvement_round(
    target: str,
    mode: str | LoopMode,
    *,
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    record = controller.run_round(
        target,
        mode=_coerce_loop_mode(mode),
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    return _enrich_improvement_resilience_payload(
        _success(
            record=record.model_dump(mode="json"),
            **_improvement_runtime_metadata(
                runtime,
                runtime_used=record.runtime_used.value,
                fallback_used=record.fallback_used,
                allow_fallback=allow_fallback,
            ),
        )
    )


def _run_improvement_loop(
    target: str,
    mode: str | LoopMode,
    max_rounds: int,
    *,
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    controller = _get_improvement_controller(runtime=runtime, allow_fallback=allow_fallback)
    run = controller.run_loop(
        target,
        mode=_coerce_loop_mode(mode),
        max_rounds=max_rounds,
        runtime=_as_improvement_runtime(runtime),
        allow_fallback=allow_fallback,
        benchmark_profile=benchmark_profile,
        backend_mode=backend_mode,
    )
    last_round = run.rounds[-1] if run.rounds else None
    return _enrich_improvement_resilience_payload(
        _success(
            run=run.model_dump(mode="json"),
            **_improvement_runtime_metadata(
                runtime,
                runtime_used=last_round.runtime_used.value if last_round is not None else normalize_runtime_backend(runtime).value,
                fallback_used=last_round.fallback_used if last_round is not None else False,
                allow_fallback=allow_fallback,
            ),
        )
    )


def _collect_runtime_health(runtime_name: str = "all") -> dict[str, Any]:
    selected = str(runtime_name).strip().lower()
    if selected == "all":
        return _success(
            runtimes={
                "langgraph": _collect_runtime_health("langgraph")["report"],
                "pydanticai": _collect_runtime_health("pydanticai")["report"],
                "legacy": _collect_runtime_health("legacy")["report"],
            }
        )
    if selected == "langgraph":
        try:
            _get_graph()
            report = {
                "runtime": "langgraph",
                "status": "healthy",
                "configured": True,
                "imports_available": True,
                "message": "LangGraph runtime compiled successfully.",
            }
        except Exception as exc:
            report = {
                "runtime": "langgraph",
                "status": "unavailable",
                "configured": False,
                "imports_available": False,
                "message": str(exc),
            }
        return _success(report=report)
    return _success(report=collect_runtime_health(selected))


def _collect_harness_inspection(
    *,
    config_path: str = "config.yaml",
    benchmark_path: str | None = None,
    benchmark_profile: BenchmarkProfile | str = BenchmarkProfile.full,
    memory_path: str = str(DEFAULT_HARNESS_MEMORY_PATH),
    backend_mode: str | None = None,
) -> dict[str, Any]:
    inspection = inspect_harness(
        config_path=config_path,
        benchmark_path=benchmark_path,
        benchmark_profile=benchmark_profile,
        memory_path=memory_path,
        backend_mode=backend_mode,
    )
    return _success(inspection=inspection.model_dump(mode="json"))


def _run_strategy_meeting_session(
    *,
    topic: str,
    objective: str | None = None,
    participants: list[str] | None = None,
    max_agents: int = 6,
    rounds: int = 2,
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    result = run_strategy_meeting_runtime(
        topic=topic,
        objective=objective,
        participants=participants,
        max_agents=max_agents,
        rounds=rounds,
        persist=persist,
        config_path=config_path,
        runtime=runtime,
        allow_fallback=allow_fallback,
    )
    runtime_requested = normalize_runtime_backend(runtime).value
    runtime_id = _first_text_value(
        result.metadata.get("model_name") if isinstance(result.metadata, dict) else None,
        result.metadata.get("provider_base_url") if isinstance(result.metadata, dict) else None,
        result.metadata.get("provider") if isinstance(result.metadata, dict) else None,
    )
    return _success(
        result=result.model_dump(mode="json"),
        runtime_requested=runtime_requested,
        runtime_used=result.metadata.get("runtime_used", runtime_requested),
        fallback_used=bool(result.metadata.get("fallback_used", False)),
        run_id=result.meeting_id,
        config_path=config_path,
        runtime_id=runtime_id,
    )


def _run_deliberation_session(
    *,
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    engine_preference: str = "agentsociety",
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    result = run_deliberation_runtime(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        persist=persist,
        config_path=config_path,
        runtime=runtime,
        allow_fallback=allow_fallback,
        engine_preference=engine_preference,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        stability_runs=stability_runs,
        backend_mode=backend_mode,
    )
    runtime_id = _first_text_value(
        result.metadata.get("model_name") if isinstance(result.metadata, dict) else None,
        result.metadata.get("provider_base_url") if isinstance(result.metadata, dict) else None,
        result.metadata.get("provider") if isinstance(result.metadata, dict) else None,
    )
    return _success(
        result=result.model_dump(mode="json"),
        runtime_requested=normalize_runtime_backend(runtime).value,
        runtime_used=result.runtime_used,
        fallback_used=result.fallback_used,
        engine_requested=result.engine_requested,
        engine_used=result.engine_used,
        run_id=result.deliberation_id,
        config_path=config_path,
        runtime_id=runtime_id,
    )


def _read_strategy_meeting_artifact(meeting_id: str) -> dict[str, Any]:
    artifact_path = Path(DEFAULT_STRATEGY_MEETING_OUTPUT_DIR) / f"{meeting_id}.json"
    if not artifact_path.exists():
        return _success(meeting_id=meeting_id, exists=False, artifact_path=str(artifact_path), result=None)
    return _success(
        meeting_id=meeting_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=json.loads(artifact_path.read_text(encoding="utf-8")),
    )


def _read_deliberation_artifact(deliberation_id: str) -> dict[str, Any]:
    artifact_path = Path(DEFAULT_DELIBERATION_OUTPUT_DIR) / deliberation_id / "result.json"
    if not artifact_path.exists():
        return _success(deliberation_id=deliberation_id, exists=False, artifact_path=str(artifact_path), result=None)
    result = load_deliberation_result(deliberation_id)
    return _success(
        deliberation_id=deliberation_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=result.model_dump(mode="json"),
    )


def _read_deliberation_campaign_artifact(campaign_id: str) -> dict[str, Any]:
    artifact_path = Path(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR) / campaign_id / "report.json"
    if not artifact_path.exists():
        return _success(campaign_id=campaign_id, exists=False, artifact_path=str(artifact_path), result=None)
    report = load_deliberation_campaign_report(
        campaign_id,
        output_dir=DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
    )
    return _success(
        campaign_id=campaign_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=report.model_dump(mode="json"),
    )


def _read_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    if not artifact_path.exists():
        return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
    report = load_deliberation_campaign_comparison_report(
        comparison_id,
        output_dir=base_dir,
    )
    return _success(
        comparison_id=comparison_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=report.model_dump(mode="json"),
    )


def _comparison_report_overview(report: DeliberationCampaignComparisonReport) -> dict[str, Any]:
    report_payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
    summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    return {
        "comparison_id": report_payload.get("comparison_id"),
        "created_at": report_payload.get("created_at"),
        "output_dir": report_payload.get("output_dir"),
        "requested_campaign_ids": report_payload.get("requested_campaign_ids", []),
        "latest": report_payload.get("latest"),
        "campaign_count": summary.get("campaign_count"),
        "campaign_ids": summary.get("campaign_ids", []),
        "comparable": summary.get("comparable"),
        "mismatch_reasons": summary.get("mismatch_reasons", []),
        "artifact_path": report_payload.get("report_path"),
    }


def _comparison_report_payload(report: DeliberationCampaignComparisonReport | dict[str, Any]) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report)


def _comparison_export_id(comparison_id: str, *, format: str = "markdown") -> str:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    return f"{comparison_id}__{normalized_format}"


def _comparison_report_audit(report: DeliberationCampaignComparisonReport | dict[str, Any]) -> dict[str, Any]:
    audit = build_deliberation_campaign_comparison_audit(report, include_markdown=False)
    return audit.model_dump(mode="json")


def _render_deliberation_campaign_comparison_markdown(audit: dict[str, Any]) -> str:
    return render_deliberation_campaign_comparison_markdown(audit)


def _list_deliberation_campaign_comparison_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, comparisons=[])

    comparisons = list_deliberation_campaign_comparison_reports(output_dir=base_dir, limit=limit)
    return _success(
        output_dir=str(base_dir),
        exists=True,
        count=len(comparisons),
        limit=limit,
        comparisons=[_comparison_report_overview(report) for report in comparisons],
    )


def _read_deliberation_campaign_comparison_export_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    export_id = _comparison_export_id(comparison_id, format=normalized_format)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    manifest_path = base_dir / export_id / "manifest.json"
    if not manifest_path.exists():
        return _success(
            comparison_id=comparison_id,
            export_id=export_id,
            format=normalized_format,
            exists=False,
            artifact_path=str(manifest_path),
            result=None,
        )
    export = load_deliberation_campaign_comparison_export(
        export_id,
        output_dir=base_dir,
        include_content=True,
    )
    payload = export.model_dump(mode="json")
    return _success(
        comparison_id=comparison_id,
        export_id=export_id,
        format=normalized_format,
        exists=True,
        artifact_path=str(manifest_path),
        result=payload,
    )


def _list_deliberation_campaign_comparison_export_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, exports=[])
    exports = [
        export.model_dump(mode="json")
        for export in list_deliberation_campaign_comparison_exports(output_dir=base_dir, limit=limit)
    ]
    return _success(
        output_dir=str(base_dir),
        exists=True,
        count=len(exports),
        limit=limit,
        exports=exports,
    )


def _benchmark_report_dir(benchmark_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    return base_dir / benchmark_id


def _benchmark_report_path(benchmark_id: str, *, output_dir: str | Path | None = None) -> Path:
    return _benchmark_report_dir(benchmark_id, output_dir=output_dir) / "report.json"


def _benchmark_report_overview(report: dict[str, Any]) -> dict[str, Any]:
    comparison = report.get("comparison", {}) if isinstance(report.get("comparison"), dict) else {}
    export = report.get("export", {}) if isinstance(report.get("export"), dict) else {}
    return {
        "benchmark_id": report.get("benchmark_id"),
        "created_at": report.get("created_at"),
        "output_dir": report.get("output_dir"),
        "report_path": report.get("report_path"),
        "baseline_campaign_id": report.get("baseline_campaign_id"),
        "candidate_campaign_id": report.get("candidate_campaign_id"),
        "comparison_id": report.get("comparison_id") or comparison.get("comparison_id"),
        "export_id": report.get("export_id") or export.get("export_id"),
        "format": report.get("format") or export.get("format"),
        "baseline_runtime": report.get("baseline_runtime"),
        "candidate_runtime": report.get("candidate_runtime"),
    }


def _benchmark_matrix_report_dir(matrix_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
    return base_dir / matrix_id


def _benchmark_matrix_report_path(matrix_id: str, *, output_dir: str | Path | None = None) -> Path:
    return _benchmark_matrix_report_dir(matrix_id, output_dir=output_dir) / "report.json"


def _benchmark_matrix_cell_payload(entry: dict[str, Any], *, baseline_campaign_id: str | None) -> dict[str, Any]:
    candidate_spec = (
        entry.get("candidate_spec", {})
        if isinstance(entry.get("candidate_spec", {}), dict)
        else {}
    )
    candidate_campaign = (
        entry.get("candidate_campaign", {})
        if isinstance(entry.get("candidate_campaign", {}), dict)
        else {}
    )
    comparison_bundle = (
        entry.get("comparison_bundle", {})
        if isinstance(entry.get("comparison_bundle", {}), dict)
        else {}
    )
    comparison_report = (
        comparison_bundle.get("comparison_report", {})
        if isinstance(comparison_bundle.get("comparison_report", {}), dict)
        else {}
    )
    export_payload = (
        comparison_bundle.get("export", {})
        if isinstance(comparison_bundle.get("export", {}), dict)
        else {}
    )
    candidate_campaign_id = (
        candidate_campaign.get("campaign_id")
        or entry.get("metadata", {}).get("candidate_campaign_id")
        or candidate_spec.get("campaign_id")
    )
    benchmark_id = (
        f"{baseline_campaign_id}__vs__{candidate_campaign_id}"
        if baseline_campaign_id and candidate_campaign_id
        else None
    )
    return {
        **entry,
        "cell_id": candidate_spec.get("label") or candidate_campaign_id or benchmark_id,
        "benchmark_id": benchmark_id,
        "candidate_campaign_id": candidate_campaign_id,
        "candidate_runtime": candidate_spec.get("runtime"),
        "candidate_engine_preference": candidate_spec.get("engine_preference"),
        "comparison_id": comparison_report.get("comparison_id"),
        "export_id": export_payload.get("export_id"),
        "comparison_report_path": comparison_report.get("report_path"),
        "export_manifest_path": export_payload.get("manifest_path"),
        "export_content_path": export_payload.get("content_path"),
    }


def _benchmark_matrix_report_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = _coerce_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    baseline_campaign = (
        payload.get("baseline_campaign", {})
        if isinstance(payload.get("baseline_campaign", {}), dict)
        else {}
    )
    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    matrix_id = payload.get("matrix_id") or payload.get("benchmark_id")
    baseline_campaign_id = (
        payload.get("baseline_campaign_id")
        or baseline_campaign.get("campaign_id")
        or payload.get("metadata", {}).get("baseline_campaign_id")
    )
    cells = [
        _benchmark_matrix_cell_payload(entry, baseline_campaign_id=baseline_campaign_id)
        for entry in entries
        if isinstance(entry, dict)
    ]
    benchmark_ids = [cell.get("benchmark_id") for cell in cells if cell.get("benchmark_id")]
    return {
        **payload,
        "matrix_id": matrix_id,
        "baseline_campaign_id": baseline_campaign_id,
        "candidate_count": summary.get("candidate_count", len(cells)),
        "candidate_campaign_ids": summary.get("candidate_campaign_ids", []),
        "comparison_ids": summary.get("comparison_ids", []),
        "candidate_labels": summary.get("candidate_labels", []),
        "benchmark_ids": benchmark_ids,
        "cell_count": len(cells),
        "cells": cells,
    }


def _benchmark_matrix_report_overview(report: dict[str, Any]) -> dict[str, Any]:
    payload = _benchmark_matrix_report_payload(report)
    cells = payload.get("cells", []) if isinstance(payload.get("cells"), list) else []
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    return {
        "matrix_id": payload.get("matrix_id"),
        "created_at": payload.get("created_at"),
        "output_dir": payload.get("output_dir"),
        "report_path": payload.get("report_path"),
        "baseline_campaign_id": payload.get("baseline_campaign_id"),
        "baseline_runtime": payload.get("metadata", {}).get("baseline_runtime"),
        "baseline_engine_preference": payload.get("metadata", {}).get("baseline_engine_preference"),
        "candidate_campaign_ids": payload.get("candidate_campaign_ids", []),
        "cell_count": payload.get("cell_count", summary.get("candidate_count", len(cells))),
        "benchmark_ids": payload.get("benchmark_ids", []),
    }


def _matrix_benchmark_comparison_report_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
    if (
        isinstance(payload.get("baseline"), dict)
        and isinstance(payload.get("candidate"), dict)
        and isinstance(payload.get("comparison"), dict)
    ):
        return payload

    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    baseline_entry = entries[0] if len(entries) >= 1 and isinstance(entries[0], dict) else {}
    candidate_entry = entries[1] if len(entries) >= 2 and isinstance(entries[1], dict) else {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}

    def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "matrix_id": entry.get("benchmark_id"),
            "benchmark_id": entry.get("benchmark_id"),
            "created_at": entry.get("created_at"),
            "baseline_campaign_id": entry.get("baseline_campaign_id"),
            "report_path": entry.get("report_path"),
            "summary": {
                "candidate_count": entry.get("candidate_count", 0),
                "candidate_labels": entry.get("candidate_labels", []),
                "comparison_ids": entry.get("comparison_ids", []),
                "comparable_count": entry.get("comparable_count", 0),
                "mismatch_count": entry.get("mismatch_count", 0),
                "quality_score_mean": entry.get("quality_score_mean", 0.0),
                "confidence_level_mean": entry.get("confidence_level_mean", 0.0),
                "runtime_values": sorted(
                    {
                        *(entry.get("candidate_runtimes", []) or []),
                        entry.get("baseline_runtime", ""),
                    }
                ),
                "engine_values": sorted(
                    {
                        *(entry.get("candidate_engines", []) or []),
                        entry.get("baseline_engine", ""),
                    }
                ),
            },
        }

    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    baseline_payload = _entry_payload(baseline_entry)
    candidate_payload = _entry_payload(candidate_entry)
    baseline_summary = (
        baseline_payload.get("summary", {})
        if isinstance(baseline_payload.get("summary", {}), dict)
        else {}
    )
    candidate_summary = (
        candidate_payload.get("summary", {})
        if isinstance(candidate_payload.get("summary", {}), dict)
        else {}
    )
    comparison = {
        "candidate_count": {
            "baseline": baseline_summary.get("candidate_count", 0),
            "candidate": candidate_summary.get("candidate_count", 0),
            "delta": _int(candidate_summary.get("candidate_count", 0))
            - _int(baseline_summary.get("candidate_count", 0)),
            "changed": baseline_summary.get("candidate_count", 0)
            != candidate_summary.get("candidate_count", 0),
        },
        "comparable_count": {
            "baseline": baseline_summary.get("comparable_count", 0),
            "candidate": candidate_summary.get("comparable_count", 0),
            "delta": _int(candidate_summary.get("comparable_count", 0))
            - _int(baseline_summary.get("comparable_count", 0)),
            "changed": baseline_summary.get("comparable_count", 0)
            != candidate_summary.get("comparable_count", 0),
        },
        "mismatch_count": {
            "baseline": baseline_summary.get("mismatch_count", 0),
            "candidate": candidate_summary.get("mismatch_count", 0),
            "delta": _int(candidate_summary.get("mismatch_count", 0))
            - _int(baseline_summary.get("mismatch_count", 0)),
            "changed": baseline_summary.get("mismatch_count", 0)
            != candidate_summary.get("mismatch_count", 0),
        },
        "quality_score_mean": {
            "baseline": baseline_summary.get("quality_score_mean", 0.0),
            "candidate": candidate_summary.get("quality_score_mean", 0.0),
            "delta": round(
                _float(candidate_summary.get("quality_score_mean", 0.0))
                - _float(baseline_summary.get("quality_score_mean", 0.0)),
                6,
            ),
            "changed": baseline_summary.get("quality_score_mean", 0.0)
            != candidate_summary.get("quality_score_mean", 0.0),
        },
        "confidence_level_mean": {
            "baseline": baseline_summary.get("confidence_level_mean", 0.0),
            "candidate": candidate_summary.get("confidence_level_mean", 0.0),
            "delta": round(
                _float(candidate_summary.get("confidence_level_mean", 0.0))
                - _float(baseline_summary.get("confidence_level_mean", 0.0)),
                6,
            ),
            "changed": baseline_summary.get("confidence_level_mean", 0.0)
            != candidate_summary.get("confidence_level_mean", 0.0),
        },
    }
    return {
        **payload,
        "baseline_matrix_id": baseline_payload.get("matrix_id"),
        "candidate_matrix_id": candidate_payload.get("matrix_id"),
        "baseline": baseline_payload,
        "candidate": candidate_payload,
        "comparison": comparison,
        "comparable": summary.get("comparable", False),
        "mismatch_reasons": summary.get("mismatch_reasons", []),
    }


def _matrix_benchmark_comparison_report_overview(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = _matrix_benchmark_comparison_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    return {
        "comparison_id": payload.get("comparison_id"),
        "created_at": payload.get("created_at"),
        "baseline_matrix_id": payload.get("baseline_matrix_id"),
        "candidate_matrix_id": payload.get("candidate_matrix_id"),
        "comparable": summary.get("comparable", payload.get("comparable")),
        "mismatch_reasons": summary.get("mismatch_reasons", payload.get("mismatch_reasons", [])),
        "report_path": payload.get("report_path"),
        "output_dir": payload.get("output_dir"),
    }


def _compare_deliberation_campaign_benchmark_matrix_artifacts(
    baseline_matrix_id: str | None = None,
    candidate_matrix_id: str | None = None,
    *,
    latest: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
    if latest and (baseline_matrix_id or candidate_matrix_id):
        raise ValueError("Use either explicit matrix IDs or latest=True, not both.")

    if latest:
        reports = list_deliberation_campaign_matrix_benchmarks(output_dir=base_dir, limit=2)
        if len(reports) < 2:
            raise ValueError("At least two benchmark matrix reports are required for comparison.")
        candidate_report = reports[0]
        baseline_report = reports[1]
    else:
        if not baseline_matrix_id or not candidate_matrix_id:
            raise ValueError("Provide both baseline_matrix_id and candidate_matrix_id, or use latest=True.")
        baseline_report = load_deliberation_campaign_matrix_benchmark(baseline_matrix_id, output_dir=base_dir)
        candidate_report = load_deliberation_campaign_matrix_benchmark(candidate_matrix_id, output_dir=base_dir)

    baseline_payload = _benchmark_matrix_report_payload(baseline_report)
    candidate_payload = _benchmark_matrix_report_payload(candidate_report)
    baseline_summary = (
        baseline_payload.get("summary", {}) if isinstance(baseline_payload.get("summary"), dict) else {}
    )
    candidate_summary = (
        candidate_payload.get("summary", {}) if isinstance(candidate_payload.get("summary"), dict) else {}
    )

    comparison = {
        "matrix_id": {
            "baseline": baseline_payload.get("matrix_id"),
            "candidate": candidate_payload.get("matrix_id"),
            "changed": baseline_payload.get("matrix_id") != candidate_payload.get("matrix_id"),
        },
        "baseline_campaign_id": {
            "baseline": baseline_payload.get("baseline_campaign_id"),
            "candidate": candidate_payload.get("baseline_campaign_id"),
            "changed": baseline_payload.get("baseline_campaign_id") != candidate_payload.get("baseline_campaign_id"),
        },
        "candidate_count": {
            "baseline": baseline_summary.get("candidate_count", baseline_payload.get("candidate_count")),
            "candidate": candidate_summary.get("candidate_count", candidate_payload.get("candidate_count")),
            "delta": int(candidate_summary.get("candidate_count", candidate_payload.get("candidate_count", 0)))
            - int(baseline_summary.get("candidate_count", baseline_payload.get("candidate_count", 0))),
            "changed": baseline_summary.get("candidate_count", baseline_payload.get("candidate_count"))
            != candidate_summary.get("candidate_count", candidate_payload.get("candidate_count")),
        },
        "comparable_count": {
            "baseline": baseline_summary.get("comparable_count", 0),
            "candidate": candidate_summary.get("comparable_count", 0),
            "delta": int(candidate_summary.get("comparable_count", 0))
            - int(baseline_summary.get("comparable_count", 0)),
            "changed": baseline_summary.get("comparable_count", 0) != candidate_summary.get("comparable_count", 0),
        },
        "mismatch_count": {
            "baseline": baseline_summary.get("mismatch_count", 0),
            "candidate": candidate_summary.get("mismatch_count", 0),
            "delta": int(candidate_summary.get("mismatch_count", 0))
            - int(baseline_summary.get("mismatch_count", 0)),
            "changed": baseline_summary.get("mismatch_count", 0) != candidate_summary.get("mismatch_count", 0),
        },
        "quality_score_mean": {
            "baseline": baseline_summary.get("quality_score_mean", 0.0),
            "candidate": candidate_summary.get("quality_score_mean", 0.0),
            "delta": round(
                float(candidate_summary.get("quality_score_mean", 0.0))
                - float(baseline_summary.get("quality_score_mean", 0.0)),
                6,
            ),
            "changed": baseline_summary.get("quality_score_mean", 0.0)
            != candidate_summary.get("quality_score_mean", 0.0),
        },
        "confidence_level_mean": {
            "baseline": baseline_summary.get("confidence_level_mean", 0.0),
            "candidate": candidate_summary.get("confidence_level_mean", 0.0),
            "delta": round(
                float(candidate_summary.get("confidence_level_mean", 0.0))
                - float(baseline_summary.get("confidence_level_mean", 0.0)),
                6,
            ),
            "changed": baseline_summary.get("confidence_level_mean", 0.0)
            != candidate_summary.get("confidence_level_mean", 0.0),
        },
        "candidate_labels": {
            "baseline": baseline_summary.get("candidate_labels", []),
            "candidate": candidate_summary.get("candidate_labels", []),
            "changed": baseline_summary.get("candidate_labels", []) != candidate_summary.get("candidate_labels", []),
        },
        "candidate_campaign_ids": {
            "baseline": baseline_summary.get("candidate_campaign_ids", []),
            "candidate": candidate_summary.get("candidate_campaign_ids", []),
            "changed": baseline_summary.get("candidate_campaign_ids", []) != candidate_summary.get("candidate_campaign_ids", []),
        },
        "comparison_ids": {
            "baseline": baseline_summary.get("comparison_ids", []),
            "candidate": candidate_summary.get("comparison_ids", []),
            "changed": baseline_summary.get("comparison_ids", []) != candidate_summary.get("comparison_ids", []),
        },
        "runtime_values": {
            "baseline": baseline_summary.get("runtime_values", []),
            "candidate": candidate_summary.get("runtime_values", []),
            "changed": baseline_summary.get("runtime_values", []) != candidate_summary.get("runtime_values", []),
        },
        "engine_values": {
            "baseline": baseline_summary.get("engine_values", []),
            "candidate": candidate_summary.get("engine_values", []),
            "changed": baseline_summary.get("engine_values", []) != candidate_summary.get("engine_values", []),
        },
    }
    mismatch_reasons = [
        key for key, value in comparison.items() if isinstance(value, dict) and value.get("changed") is True
    ]
    comparable = not mismatch_reasons
    return _success(
        baseline_matrix_id=baseline_payload.get("matrix_id"),
        candidate_matrix_id=candidate_payload.get("matrix_id"),
        latest=latest,
        output_dir=str(base_dir),
        comparable=comparable,
        mismatch_reasons=mismatch_reasons,
        comparison=comparison,
        baseline=baseline_payload,
        candidate=candidate_payload,
        result={
            "baseline": baseline_payload,
            "candidate": candidate_payload,
            "comparison": comparison,
            "comparable": comparable,
            "mismatch_reasons": mismatch_reasons,
        },
    )


def _coerce_report_payload(report: Any) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report)


def _read_deliberation_campaign_benchmark_artifact(
    benchmark_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    artifact_path = _benchmark_report_path(benchmark_id, output_dir=base_dir)
    if not artifact_path.exists():
        return _success(benchmark_id=benchmark_id, exists=False, artifact_path=str(artifact_path), result=None)
    helper = getattr(sys.modules[__name__], "load_deliberation_campaign_benchmark", None)
    if not callable(helper):
        helper = load_deliberation_campaign_benchmark
    if callable(helper):
        try:
            benchmark = helper(benchmark_id, output_dir=base_dir)
            payload = _coerce_report_payload(benchmark)
        except Exception:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return _success(benchmark_id=benchmark_id, exists=True, artifact_path=str(artifact_path), result=payload)


def _list_deliberation_campaign_benchmark_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, benchmarks=[])

    helper = getattr(sys.modules[__name__], "list_deliberation_campaign_benchmarks", None)
    if not callable(helper):
        helper = list_deliberation_campaign_benchmarks
    reports: list[dict[str, Any]] = []
    if callable(helper):
        try:
            benchmarks = helper(output_dir=base_dir, limit=limit)
            for benchmark in benchmarks or []:
                reports.append(_benchmark_report_overview(_coerce_report_payload(benchmark)))
        except Exception:
            reports = []
    if not reports:
        for report_path in sorted(
            (path for path in base_dir.glob("*/report.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            reports.append(_benchmark_report_overview(payload))
            if len(reports) >= max(0, int(limit)):
                break
    return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, benchmarks=reports)


def _read_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
    artifact_path = _benchmark_matrix_report_path(matrix_id, output_dir=base_dir)
    if not artifact_path.exists():
        return _success(matrix_id=matrix_id, exists=False, artifact_path=str(artifact_path), result=None)
    helper = getattr(sys.modules[__name__], "load_deliberation_campaign_matrix_benchmark", None)
    if not callable(helper):
        helper = load_deliberation_campaign_matrix_benchmark
    if callable(helper):
        try:
            payload = _benchmark_matrix_report_payload(helper(matrix_id, output_dir=base_dir))
        except Exception:
            payload = _benchmark_matrix_report_payload(json.loads(artifact_path.read_text(encoding="utf-8")))
    else:
        payload = _benchmark_matrix_report_payload(json.loads(artifact_path.read_text(encoding="utf-8")))
    return _success(matrix_id=matrix_id, exists=True, artifact_path=str(artifact_path), result=payload)


def _list_deliberation_campaign_benchmark_matrix_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, matrices=[])

    reports: list[dict[str, Any]] = []
    helper = getattr(sys.modules[__name__], "list_deliberation_campaign_matrix_benchmarks", None)
    if not callable(helper):
        helper = list_deliberation_campaign_matrix_benchmarks
    if callable(helper):
        try:
            matrices = helper(output_dir=base_dir, limit=limit)
            for matrix in matrices or []:
                reports.append(_benchmark_matrix_report_overview(matrix))
        except Exception:
            reports = []
    if not reports:
        for report_path in sorted(
            (path for path in base_dir.glob("*/report.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            reports.append(_benchmark_matrix_report_overview(payload))
            if len(reports) >= max(0, int(limit)):
                break
    return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, matrices=reports)


def _matrix_benchmark_export_id(matrix_id: str, *, format: str = "markdown") -> str:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    return f"{matrix_id}__{normalized_format}"


def _matrix_benchmark_export_dir(export_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _matrix_benchmark_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _matrix_benchmark_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _matrix_benchmark_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _matrix_benchmark_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def _matrix_benchmark_candidate_audit_entry(
    cell: dict[str, Any],
    *,
    baseline_campaign_id: str | None,
) -> dict[str, Any]:
    candidate_spec = cell.get("candidate_spec", {}) if isinstance(cell.get("candidate_spec", {}), dict) else {}
    candidate_campaign = (
        cell.get("candidate_campaign", {}) if isinstance(cell.get("candidate_campaign", {}), dict) else {}
    )
    cell_metadata = cell.get("metadata", {}) if isinstance(cell.get("metadata", {}), dict) else {}
    comparison_bundle = (
        cell.get("comparison_bundle", {}) if isinstance(cell.get("comparison_bundle", {}), dict) else {}
    )
    comparison_report = (
        comparison_bundle.get("comparison_report", {})
        if isinstance(comparison_bundle.get("comparison_report", {}), dict)
        else {}
    )
    comparison_summary = (
        comparison_report.get("summary", {}) if isinstance(comparison_report.get("summary", {}), dict) else {}
    )
    candidate_label = (
        cell.get("candidate_label")
        or candidate_spec.get("label")
        or cell_metadata.get("candidate_label")
        or candidate_campaign.get("campaign_id")
    )
    candidate_campaign_id = (
        candidate_campaign.get("campaign_id")
        or cell_metadata.get("candidate_campaign_id")
        or candidate_spec.get("campaign_id")
    )
    comparable = bool(comparison_summary.get("comparable"))
    quality_score_mean = float(comparison_summary.get("quality_score_mean", 0.0) or 0.0)
    confidence_level_mean = float(comparison_summary.get("confidence_level_mean", 0.0) or 0.0)
    mismatch_reasons = comparison_summary.get("mismatch_reasons", [])
    comparison_key_values = comparison_summary.get("comparison_key_values", [])
    return {
        "candidate_index": cell.get("candidate_index"),
        "candidate_label": candidate_label,
        "candidate_campaign_id": candidate_campaign_id,
        "candidate_runtime": cell.get("candidate_runtime") or candidate_spec.get("runtime"),
        "candidate_engine_preference": cell.get("candidate_engine_preference")
        or candidate_spec.get("engine_preference"),
        "comparison_id": cell.get("comparison_id"),
        "comparison_report_path": cell.get("comparison_report_path"),
        "export_id": cell.get("export_id"),
        "export_manifest_path": cell.get("export_manifest_path"),
        "export_content_path": cell.get("export_content_path"),
        "baseline_campaign_id": baseline_campaign_id,
        "comparable": comparable,
        "status": "comparable" if comparable else "mismatch",
        "quality_score_mean": quality_score_mean,
        "confidence_level_mean": confidence_level_mean,
        "mismatch_reasons": list(mismatch_reasons or []),
        "comparison_key": comparison_key_values[0] if isinstance(comparison_key_values, list) and comparison_key_values else None,
    }


def _matrix_benchmark_audit_ranking_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    comparable_rank = 0 if entry.get("comparable") else 1
    quality_score = float(entry.get("quality_score_mean", 0.0) or 0.0)
    confidence_level = float(entry.get("confidence_level_mean", 0.0) or 0.0)
    candidate_index = entry.get("candidate_index")
    try:
        candidate_index_value = int(candidate_index) if candidate_index is not None else 0
    except (TypeError, ValueError):
        candidate_index_value = 0
    candidate_label = str(entry.get("candidate_label") or entry.get("candidate_campaign_id") or "")
    return (
        comparable_rank,
        -quality_score,
        -confidence_level,
        candidate_index_value,
        candidate_label,
    )


def _render_deliberation_campaign_matrix_benchmark_markdown(audit: dict[str, Any]) -> str:
    summary = audit.get("summary", {}) if isinstance(audit.get("summary", {}), dict) else {}
    best_candidate = audit.get("best_candidate", {}) if isinstance(audit.get("best_candidate", {}), dict) else {}
    worst_candidate = audit.get("worst_candidate", {}) if isinstance(audit.get("worst_candidate", {}), dict) else {}
    lines = [
        "# Deliberation Campaign Matrix Benchmark Audit",
        "",
        f"- Matrix ID: {audit.get('matrix_id') or 'n/a'}",
        f"- Created At: {audit.get('created_at') or 'n/a'}",
        f"- Baseline Campaign: {audit.get('baseline_campaign_id') or 'n/a'}",
        f"- Candidate Count: {summary.get('candidate_count', 'n/a')}",
        f"- Comparable: {summary.get('comparable', 'n/a')}",
        f"- Mismatch Count: {summary.get('mismatch_count', 'n/a')}",
        f"- Best Candidate: {best_candidate.get('candidate_label') or 'n/a'}",
        f"- Worst Candidate: {worst_candidate.get('candidate_label') or 'n/a'}",
    ]
    ranking = audit.get("ranking", [])
    if ranking:
        lines.extend(["", "## Ranking"])
        for entry in ranking:
            if not isinstance(entry, dict):
                continue
            lines.append(
                "- {candidate_label}: comparable={comparable}, quality_score_mean={quality_score_mean}, "
                "confidence_level_mean={confidence_level_mean}".format(
                    candidate_label=entry.get("candidate_label", "n/a"),
                    comparable=entry.get("comparable", "n/a"),
                    quality_score_mean=entry.get("quality_score_mean", "n/a"),
                    confidence_level_mean=entry.get("confidence_level_mean", "n/a"),
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def _matrix_benchmark_report_audit(
    report: dict[str, Any] | Any,
    *,
    include_markdown: bool = False,
) -> dict[str, Any]:
    payload = _benchmark_matrix_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    cells = payload.get("cells", []) if isinstance(payload.get("cells", []), list) else []
    entries = [
        _matrix_benchmark_candidate_audit_entry(cell, baseline_campaign_id=payload.get("baseline_campaign_id"))
        for cell in cells
        if isinstance(cell, dict)
    ]
    ranking = sorted(entries, key=_matrix_benchmark_audit_ranking_key)
    best_candidate = ranking[0] if ranking else {}
    worst_candidate = ranking[-1] if ranking else {}
    metadata = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {}
    metadata.update(
        {
            "matrix_id": payload.get("matrix_id"),
            "report_path": payload.get("report_path"),
            "output_dir": payload.get("output_dir"),
            "content_kind": "markdown" if include_markdown else "json",
        }
    )
    return {
        **payload,
        "candidate_count": summary.get("candidate_count", len(entries)),
        "comparable_count": summary.get("comparable_count", 0),
        "mismatch_count": summary.get("mismatch_count", 0),
        "quality_score_mean": summary.get("quality_score_mean", 0.0),
        "quality_score_min": summary.get("quality_score_min", 0.0),
        "quality_score_max": summary.get("quality_score_max", 0.0),
        "confidence_level_mean": summary.get("confidence_level_mean", 0.0),
        "confidence_level_min": summary.get("confidence_level_min", 0.0),
        "confidence_level_max": summary.get("confidence_level_max", 0.0),
        "candidate_labels": list(summary.get("candidate_labels", payload.get("candidate_labels", []))),
        "candidate_campaign_ids": list(summary.get("candidate_campaign_ids", payload.get("candidate_campaign_ids", []))),
        "comparison_ids": list(summary.get("comparison_ids", payload.get("comparison_ids", []))),
        "runtime_values": list(summary.get("runtime_values", [])),
        "engine_values": list(summary.get("engine_values", [])),
        "best_candidate": best_candidate,
        "worst_candidate": worst_candidate,
        "ranking": ranking,
        "overview": _benchmark_matrix_report_overview(payload),
        "markdown": _render_deliberation_campaign_matrix_benchmark_markdown(payload | {"ranking": ranking, "best_candidate": best_candidate, "worst_candidate": worst_candidate})
        if include_markdown
        else None,
        "metadata": metadata,
    }


def _matrix_benchmark_audit_overview(audit: dict[str, Any] | Any) -> dict[str, Any]:
    payload = audit.model_dump(mode="json") if hasattr(audit, "model_dump") else dict(audit)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    best_candidate = payload.get("best_candidate", {}) if isinstance(payload.get("best_candidate", {}), dict) else {}
    worst_candidate = payload.get("worst_candidate", {}) if isinstance(payload.get("worst_candidate", {}), dict) else {}
    return {
        "matrix_id": payload.get("matrix_id"),
        "created_at": payload.get("created_at"),
        "baseline_campaign_id": payload.get("baseline_campaign_id"),
        "candidate_count": summary.get("candidate_count", payload.get("candidate_count")),
        "comparable_count": summary.get("comparable_count", payload.get("comparable_count")),
        "mismatch_count": summary.get("mismatch_count", payload.get("mismatch_count")),
        "quality_score_mean": summary.get("quality_score_mean", payload.get("quality_score_mean")),
        "confidence_level_mean": summary.get("confidence_level_mean", payload.get("confidence_level_mean")),
        "best_candidate": best_candidate.get("candidate_label"),
        "worst_candidate": worst_candidate.get("candidate_label"),
        "report_path": payload.get("report_path"),
        "output_dir": payload.get("output_dir"),
    }


def _materialize_deliberation_campaign_benchmark_matrix_export(
    audit: dict[str, Any] | Any,
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")
    audit_payload = (
        _matrix_benchmark_report_audit(audit, include_markdown=normalized_format == "markdown")
        if not isinstance(audit, dict) or "overview" not in audit
        else dict(audit)
    )
    matrix_id = str(audit_payload.get("matrix_id") or audit_payload.get("benchmark_id") or "matrix_benchmark_unknown").strip()
    export_identifier = str(export_id or "").strip() or _matrix_benchmark_export_id(matrix_id, format=normalized_format)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR)
    export_dir = _matrix_benchmark_export_dir(export_identifier, output_dir=base_dir)
    manifest_path = _matrix_benchmark_export_manifest_path(export_identifier, output_dir=base_dir)
    content_path = _matrix_benchmark_export_content_path(
        export_identifier,
        output_dir=base_dir,
        format=normalized_format,
    )
    content = (
        audit_payload.get("markdown")
        if normalized_format == "markdown"
        else json.dumps(audit_payload, indent=2, sort_keys=True)
    )
    if normalized_format == "markdown" and not content:
        content = _render_deliberation_campaign_matrix_benchmark_markdown(audit_payload)
    summary = audit_payload.get("summary", {}) if isinstance(audit_payload.get("summary", {}), dict) else {}
    export_payload = {
        "export_id": export_identifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(base_dir),
        "manifest_path": str(manifest_path),
        "content_path": str(content_path),
        "matrix_id": matrix_id,
        "report_path": audit_payload.get("report_path"),
        "format": normalized_format,
        "candidate_count": summary.get("candidate_count", audit_payload.get("candidate_count")),
        "comparable_count": summary.get("comparable_count", audit_payload.get("comparable_count")),
        "mismatch_count": summary.get("mismatch_count", audit_payload.get("mismatch_count")),
        "best_candidate": audit_payload.get("best_candidate"),
        "worst_candidate": audit_payload.get("worst_candidate"),
        "comparable": summary.get("comparable", audit_payload.get("comparable")),
        "candidate_labels": list(summary.get("candidate_labels", audit_payload.get("candidate_labels", []))),
        "candidate_campaign_ids": list(summary.get("candidate_campaign_ids", audit_payload.get("candidate_campaign_ids", []))),
        "comparison_ids": list(summary.get("comparison_ids", audit_payload.get("comparison_ids", []))),
        "mismatch_reasons": list(summary.get("mismatch_reasons", audit_payload.get("mismatch_reasons", []))),
        "content": content,
        "metadata": {
            **audit_payload.get("metadata", {}),
            "persisted": True,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    }
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = dict(export_payload)
    manifest_payload.pop("content", None)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
    if content is not None:
        content_path.write_text(content, encoding="utf-8")
    return export_payload


def _read_deliberation_campaign_benchmark_matrix_export_artifact(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    export_id = _matrix_benchmark_export_id(matrix_id, format=normalized_format)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR)
    manifest_path = _matrix_benchmark_export_manifest_path(export_id, output_dir=base_dir)
    if not manifest_path.exists():
        return _success(
            matrix_id=matrix_id,
            export_id=export_id,
            format=normalized_format,
            exists=False,
            artifact_path=str(manifest_path),
            result=None,
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    content_path = Path(
        payload.get("content_path")
        or _matrix_benchmark_export_content_path(export_id, output_dir=base_dir, format=normalized_format)
    )
    if content_path.is_file():
        payload["content"] = content_path.read_text(encoding="utf-8")
    return _success(
        matrix_id=matrix_id,
        export_id=export_id,
        format=payload.get("format", normalized_format),
        exists=True,
        artifact_path=str(manifest_path),
        result=payload,
    )


def _list_deliberation_campaign_benchmark_matrix_export_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, exports=[])

    exports: list[dict[str, Any]] = []
    for manifest_path in sorted(
        (path for path in base_dir.glob("*/manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        content_path = Path(
            payload.get("content_path")
            or _matrix_benchmark_export_content_path(
                payload.get("export_id", manifest_path.parent.name),
                output_dir=base_dir,
                format=payload.get("format", "markdown"),
            )
        )
        if content_path.is_file():
            payload["content"] = content_path.read_text(encoding="utf-8")
        exports.append(payload)
        if len(exports) >= max(0, int(limit)):
            break
    return _success(output_dir=str(base_dir), exists=True, count=len(exports), limit=limit, exports=exports)


def _matrix_benchmark_export_comparison_report_payload(report: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        payload = report.model_dump(mode="json")
    elif isinstance(report, dict):
        payload = dict(report)
    else:
        payload = dict(report)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    return payload


def _matrix_benchmark_export_comparison_report_overview(report: dict[str, Any] | Any) -> dict[str, Any]:
    payload = _matrix_benchmark_export_comparison_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    return {
        "comparison_id": payload.get("comparison_id"),
        "created_at": payload.get("created_at"),
        "export_count": summary.get("export_count", len(summary.get("export_ids", []))),
        "export_ids": summary.get("export_ids", []),
        "benchmark_ids": summary.get("benchmark_ids", []),
        "comparable": summary.get("comparable", payload.get("comparable")),
        "mismatch_reasons": summary.get("mismatch_reasons", payload.get("mismatch_reasons", [])),
        "report_path": payload.get("report_path"),
        "output_dir": payload.get("output_dir"),
    }


def _matrix_benchmark_export_comparison_export_payload(export: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(export, "model_dump"):
        payload = export.model_dump(mode="json")
    elif isinstance(export, dict):
        payload = dict(export)
    else:
        payload = dict(export)
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    return payload


def _read_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    try:
        payload = _matrix_benchmark_export_comparison_report_payload(
            load_deliberation_campaign_matrix_benchmark_export_comparison_report(
                comparison_id,
                output_dir=base_dir,
            )
        )
        return _success(
            comparison_id=comparison_id,
            exists=True,
            artifact_path=str(artifact_path),
            result=payload,
        )
    except Exception:
        if not artifact_path.exists():
            return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
        payload = _matrix_benchmark_export_comparison_report_payload(
            json.loads(artifact_path.read_text(encoding="utf-8"))
        )
        return _success(
            comparison_id=comparison_id,
            exists=True,
            artifact_path=str(artifact_path),
            result=payload,
        )


def _list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR)
    reports: list[dict[str, Any]] = []
    try:
        comparisons = list_deliberation_campaign_matrix_benchmark_export_comparison_reports(
            output_dir=base_dir,
            limit=limit,
        )
        reports = [_matrix_benchmark_export_comparison_report_overview(comparison) for comparison in comparisons or []]
    except Exception:
        reports = []
    if reports:
        return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, comparisons=reports)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, comparisons=[])
    for report_path in sorted(
        (path for path in base_dir.glob("*/report.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append(_matrix_benchmark_export_comparison_report_overview(payload))
        if len(reports) >= max(0, int(limit)):
            break
    return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, comparisons=reports)


def _audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    try:
        audit = load_deliberation_campaign_matrix_benchmark_export_comparison_audit(
            comparison_id,
            output_dir=base_dir,
            include_markdown=True,
        )
        payload = audit.model_dump(mode="json") if hasattr(audit, "model_dump") else dict(audit)
        return _success(
            comparison_id=comparison_id,
            exists=True,
            artifact_path=str(artifact_path),
            result=payload,
        )
    except Exception:
        if not artifact_path.exists():
            return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
        raise


def _export_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    *,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="benchmark_matrix_export_comparison_export_format_unsupported",
            comparison_id=comparison_id,
            format=format,
        )
    audit_payload = _audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
        comparison_id,
        output_dir=comparison_output_dir,
    )
    if not audit_payload.get("ok"):
        return audit_payload
    export = materialize_deliberation_campaign_matrix_benchmark_export_comparison_export(
        audit_payload.get("result", {}),
        format=normalized_format,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR,
        export_id=f"{comparison_id}__{normalized_format}",
    )
    export_payload = _matrix_benchmark_export_comparison_export_payload(export)
    return _success(
        comparison_id=comparison_id,
        export_id=export_payload.get("export_id"),
        artifact_path=export_payload.get("content_path"),
        manifest_path=export_payload.get("manifest_path"),
        report_path=audit_payload.get("artifact_path"),
        format=normalized_format,
        result=export_payload,
    )


def _read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
    artifact_path = base_dir / export_id / "manifest.json"
    try:
        payload = _matrix_benchmark_export_comparison_export_payload(
            load_deliberation_campaign_matrix_benchmark_export_comparison_export(
                export_id,
                output_dir=base_dir,
                include_content=True,
            )
        )
        return _success(export_id=export_id, exists=True, artifact_path=str(artifact_path), result=payload)
    except Exception:
        if not artifact_path.exists():
            return _success(export_id=export_id, exists=False, artifact_path=str(artifact_path), result=None)
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        content_path = Path(str(payload.get("content_path") or ""))
        if content_path.is_file():
            payload["content"] = content_path.read_text(encoding="utf-8")
        return _success(export_id=export_id, exists=True, artifact_path=str(artifact_path), result=payload)


def _list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR)
    exports: list[dict[str, Any]] = []
    try:
        artifacts = list_deliberation_campaign_matrix_benchmark_export_comparison_exports(
            output_dir=base_dir,
            limit=limit,
        )
        exports = [_matrix_benchmark_export_comparison_export_payload(artifact) for artifact in artifacts or []]
    except Exception:
        exports = []
    if exports:
        return _success(output_dir=str(base_dir), exists=True, count=len(exports), limit=limit, exports=exports)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, exports=[])
    for manifest_path in sorted(
        (path for path in base_dir.glob("*/manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        exports.append(payload)
        if len(exports) >= max(0, int(limit)):
            break
    return _success(output_dir=str(base_dir), exists=True, count=len(exports), limit=limit, exports=exports)


def _audit_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
    artifact_path = _benchmark_matrix_report_path(matrix_id, output_dir=base_dir)
    helper = getattr(sys.modules[__name__], "load_deliberation_campaign_matrix_benchmark", None)
    if not callable(helper):
        helper = load_deliberation_campaign_matrix_benchmark
    try:
        payload = _benchmark_matrix_report_payload(helper(matrix_id, output_dir=base_dir))
    except Exception:
        if not artifact_path.exists():
            return _success(matrix_id=matrix_id, exists=False, artifact_path=str(artifact_path), result=None)
        payload = _benchmark_matrix_report_payload(json.loads(artifact_path.read_text(encoding="utf-8")))
    audit = _matrix_benchmark_report_audit(payload, include_markdown=False)
    return _success(
        matrix_id=matrix_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=audit,
    )


def _export_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="benchmark_matrix_export_format_unsupported",
            matrix_id=matrix_id,
            format=format,
        )
    audit_payload = _audit_deliberation_campaign_benchmark_matrix_artifact(
        matrix_id,
        output_dir=output_dir,
    )
    if not audit_payload.get("ok"):
        return audit_payload
    export = _materialize_deliberation_campaign_benchmark_matrix_export(
        audit_payload.get("result", {}),
        format=normalized_format,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR,
        export_id=_matrix_benchmark_export_id(matrix_id, format=normalized_format),
    )
    return _success(
        matrix_id=matrix_id,
        export_id=export.get("export_id"),
        artifact_path=export.get("content_path"),
        manifest_path=export.get("manifest_path"),
        report_path=audit_payload.get("artifact_path"),
        format=normalized_format,
        audit=export.get("metadata", {}).get("audit") or audit_payload.get("result"),
        export=export.get("content"),
        result=export,
    )


def _read_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    helper = getattr(sys.modules[__name__], "load_deliberation_campaign_matrix_benchmark_comparison_report", None)
    if not callable(helper):
        helper = load_deliberation_campaign_matrix_benchmark_comparison_report
    if callable(helper):
        try:
            payload = _matrix_benchmark_comparison_report_payload(
                helper(comparison_id, output_dir=base_dir)
            )
            return _success(
                comparison_id=comparison_id,
                exists=True,
                artifact_path=str(artifact_path),
                result=payload,
            )
        except Exception:
            pass
    if not artifact_path.exists():
        return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
    payload = _matrix_benchmark_comparison_report_payload(
        json.loads(artifact_path.read_text(encoding="utf-8"))
    )
    return _success(
        comparison_id=comparison_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=payload,
    )


def _list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR)
    reports: list[dict[str, Any]] = []
    helper = getattr(sys.modules[__name__], "list_deliberation_campaign_matrix_benchmark_comparison_reports", None)
    if not callable(helper):
        helper = list_deliberation_campaign_matrix_benchmark_comparison_reports
    if callable(helper):
        try:
            comparisons = helper(output_dir=base_dir, limit=limit)
            for comparison in comparisons or []:
                reports.append(_matrix_benchmark_comparison_report_overview(comparison))
        except Exception:
            reports = []
    if reports:
        return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, comparisons=reports)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, comparisons=[])
    if not reports:
        for report_path in sorted(
            (path for path in base_dir.glob("*/report.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            reports.append(_matrix_benchmark_comparison_report_overview(payload))
            if len(reports) >= max(0, int(limit)):
                break
    return _success(output_dir=str(base_dir), exists=True, count=len(reports), limit=limit, comparisons=reports)


def _matrix_benchmark_comparison_export_id(comparison_id: str, *, format: str = "markdown") -> str:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    return f"{comparison_id}__{normalized_format}"


def _matrix_benchmark_comparison_export_dir(export_id: str, *, output_dir: str | Path | None = None) -> Path:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR)
    return base_dir / export_id


def _matrix_benchmark_comparison_export_manifest_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    return _matrix_benchmark_comparison_export_dir(export_id, output_dir=output_dir) / "manifest.json"


def _matrix_benchmark_comparison_export_content_path(
    export_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> Path:
    extension = ".md" if str(format).strip().lower() == "markdown" else ".json"
    return _matrix_benchmark_comparison_export_dir(export_id, output_dir=output_dir) / f"content{extension}"


def _render_deliberation_campaign_matrix_benchmark_comparison_markdown(audit: dict[str, Any]) -> str:
    summary = audit.get("summary", {}) if isinstance(audit.get("summary", {}), dict) else {}
    lines = [
        "# Deliberation Campaign Matrix Benchmark Comparison",
        "",
        f"- Comparison ID: {audit.get('comparison_id') or 'n/a'}",
        f"- Created At: {audit.get('created_at') or 'n/a'}",
        f"- Requested Benchmarks: {', '.join(audit.get('requested_benchmark_ids', [])) or 'n/a'}",
        f"- Benchmark Count: {summary.get('benchmark_count', 'n/a')}",
        f"- Comparable: {summary.get('comparable', 'n/a')}",
        f"- Mismatch Reasons: {', '.join(summary.get('mismatch_reasons', [])) or 'none'}",
    ]
    benchmark_ids = summary.get("benchmark_ids", [])
    if benchmark_ids:
        lines.extend(["", "## Benchmarks"])
        lines.extend(f"- {benchmark_id}" for benchmark_id in benchmark_ids)
    entries = audit.get("entries", [])
    if entries:
        lines.extend(["", "## Entries"])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            lines.append(
                "- {benchmark_id}: comparable_count={comparable_count}, mismatch_count={mismatch_count}, "
                "quality_score_mean={quality_score_mean}, confidence_level_mean={confidence_level_mean}".format(
                    benchmark_id=entry.get("benchmark_id", "n/a"),
                    comparable_count=entry.get("comparable_count", "n/a"),
                    mismatch_count=entry.get("mismatch_count", "n/a"),
                    quality_score_mean=entry.get("quality_score_mean", "n/a"),
                    confidence_level_mean=entry.get("confidence_level_mean", "n/a"),
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def _matrix_benchmark_comparison_report_audit(
    report: DeliberationCampaignMatrixBenchmarkComparisonReport | dict[str, Any],
    *,
    include_markdown: bool = False,
) -> dict[str, Any]:
    payload = _matrix_benchmark_comparison_report_payload(report)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    metadata = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {}
    metadata.update(
        {
            "comparison_id": payload.get("comparison_id"),
            "report_path": payload.get("report_path"),
            "output_dir": payload.get("output_dir"),
            "content_kind": "markdown" if include_markdown else "json",
        }
    )
    return {
        **payload,
        "benchmark_count": summary.get("benchmark_count"),
        "benchmark_ids": list(summary.get("benchmark_ids", [])),
        "comparable": summary.get("comparable", payload.get("comparable")),
        "mismatch_reasons": list(summary.get("mismatch_reasons", payload.get("mismatch_reasons", []))),
        "overview": _matrix_benchmark_comparison_report_overview(payload),
        "markdown": _render_deliberation_campaign_matrix_benchmark_comparison_markdown(payload)
        if include_markdown
        else None,
        "metadata": metadata,
    }


def _materialize_deliberation_campaign_benchmark_matrix_comparison_export(
    audit: dict[str, Any] | DeliberationCampaignMatrixBenchmarkComparisonReport,
    *,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    export_id: str | None = None,
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        raise ValueError("format must be one of: markdown, json")

    def _clean_text(value: Any, fallback: str = "") -> str:
        text = str(value).strip() if value is not None else ""
        return text or fallback

    audit_payload = (
        _matrix_benchmark_comparison_report_audit(audit, include_markdown=normalized_format == "markdown")
        if not isinstance(audit, dict) or "overview" not in audit
        else dict(audit)
    )
    comparison_id = _clean_text(audit_payload.get("comparison_id"), "campaign_matrix_compare_unknown")
    export_identifier = _clean_text(export_id) or _matrix_benchmark_comparison_export_id(
        comparison_id,
        format=normalized_format,
    )
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR)
    export_dir = _matrix_benchmark_comparison_export_dir(export_identifier, output_dir=base_dir)
    manifest_path = _matrix_benchmark_comparison_export_manifest_path(export_identifier, output_dir=base_dir)
    content_path = _matrix_benchmark_comparison_export_content_path(
        export_identifier,
        output_dir=base_dir,
        format=normalized_format,
    )
    summary = audit_payload.get("summary", {}) if isinstance(audit_payload.get("summary", {}), dict) else {}
    content = (
        audit_payload.get("markdown")
        if normalized_format == "markdown"
        else json.dumps(audit_payload, indent=2, sort_keys=True)
    )
    if normalized_format == "markdown" and not content:
        content = _render_deliberation_campaign_matrix_benchmark_comparison_markdown(audit_payload)
    export_payload = {
        "export_id": export_identifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(base_dir),
        "manifest_path": str(manifest_path),
        "content_path": str(content_path),
        "comparison_id": comparison_id,
        "comparison_report_path": audit_payload.get("report_path"),
        "format": normalized_format,
        "benchmark_count": summary.get("benchmark_count"),
        "benchmark_ids": list(summary.get("benchmark_ids", [])),
        "comparable": summary.get("comparable", audit_payload.get("comparable")),
        "mismatch_reasons": list(summary.get("mismatch_reasons", audit_payload.get("mismatch_reasons", []))),
        "content": content,
        "metadata": {
            **audit_payload.get("metadata", {}),
            "persisted": True,
            "content_kind": "markdown" if normalized_format == "markdown" else "json",
        },
    }
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = dict(export_payload)
    manifest_payload.pop("content", None)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
    if content is not None:
        content_path.write_text(content, encoding="utf-8")
    return export_payload


def _read_deliberation_campaign_benchmark_matrix_comparison_export_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    export_id = _matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format)
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR)
    manifest_path = _matrix_benchmark_comparison_export_manifest_path(export_id, output_dir=base_dir)
    if not manifest_path.exists():
        return _success(
            comparison_id=comparison_id,
            export_id=export_id,
            format=normalized_format,
            exists=False,
            artifact_path=str(manifest_path),
            result=None,
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    content_path = Path(payload.get("content_path") or _matrix_benchmark_comparison_export_content_path(
        export_id,
        output_dir=base_dir,
        format=normalized_format,
    ))
    if content_path.is_file():
        payload["content"] = content_path.read_text(encoding="utf-8")
    return _success(
        comparison_id=comparison_id,
        export_id=export_id,
        format=payload.get("format", normalized_format),
        exists=True,
        artifact_path=str(manifest_path),
        result=payload,
    )


def _list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts(
    *,
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, exports=[])

    exports: list[dict[str, Any]] = []
    for manifest_path in sorted(
        (path for path in base_dir.glob("*/manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        content_path = Path(payload.get("content_path") or _matrix_benchmark_comparison_export_content_path(
            payload.get("export_id", manifest_path.parent.name),
            output_dir=base_dir,
            format=payload.get("format", "markdown"),
        ))
        if content_path.is_file():
            payload["content"] = content_path.read_text(encoding="utf-8")
        exports.append(payload)
        if len(exports) >= max(0, int(limit)):
            break
    return _success(output_dir=str(base_dir), exists=True, count=len(exports), limit=limit, exports=exports)


def _audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    helper = getattr(sys.modules[__name__], "load_deliberation_campaign_matrix_benchmark_comparison_report", None)
    if not callable(helper):
        helper = load_deliberation_campaign_matrix_benchmark_comparison_report
    try:
        payload = _matrix_benchmark_comparison_report_payload(helper(comparison_id, output_dir=base_dir))
    except Exception:
        if not artifact_path.exists():
            return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
        payload = _matrix_benchmark_comparison_report_payload(json.loads(artifact_path.read_text(encoding="utf-8")))
    audit = _matrix_benchmark_comparison_report_audit(payload, include_markdown=False)
    return _success(
        comparison_id=comparison_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=audit,
    )


def _export_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    *,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="benchmark_matrix_comparison_export_format_unsupported",
            comparison_id=comparison_id,
            format=format,
        )
    audit_payload = _audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
        comparison_id,
        output_dir=comparison_output_dir,
    )
    if not audit_payload.get("ok"):
        return audit_payload
    export = _materialize_deliberation_campaign_benchmark_matrix_comparison_export(
        audit_payload.get("result", {}),
        format=normalized_format,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR,
        export_id=_matrix_benchmark_comparison_export_id(comparison_id, format=normalized_format),
    )
    return _success(
        comparison_id=comparison_id,
        export_id=export.get("export_id"),
        artifact_path=export.get("content_path"),
        manifest_path=export.get("manifest_path"),
        report_path=audit_payload.get("artifact_path"),
        format=normalized_format,
        audit=export.get("metadata", {}).get("audit") or audit_payload.get("result"),
        export=export.get("content"),
        result=export,
    )


def _compare_audit_export_deliberation_campaign_benchmark_matrices(
    baseline_matrix_id: str | None = None,
    candidate_matrix_id: str | None = None,
    *,
    latest: bool = False,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="benchmark_matrix_comparison_export_format_unsupported",
            baseline_matrix_id=baseline_matrix_id,
            candidate_matrix_id=candidate_matrix_id,
            latest=latest,
            format=format,
        )
    if latest:
        comparison_report = compare_deliberation_campaign_matrix_benchmarks(
            latest=2,
            persist=True,
            comparison_output_dir=comparison_output_dir,
        )
    else:
        if not baseline_matrix_id or not candidate_matrix_id:
            return _failure(
                "Provide both baseline_matrix_id and candidate_matrix_id, or use latest=True.",
                error_code="benchmark_matrix_comparison_inputs_missing",
                baseline_matrix_id=baseline_matrix_id,
                candidate_matrix_id=candidate_matrix_id,
                latest=latest,
            )
        comparison_report = compare_deliberation_campaign_matrix_benchmarks(
            benchmark_ids=[baseline_matrix_id, candidate_matrix_id],
            persist=True,
            comparison_output_dir=comparison_output_dir,
        )
    comparison_payload = _matrix_benchmark_comparison_report_payload(comparison_report)
    comparison_id = comparison_payload.get("comparison_id")
    audit_payload = _audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
        comparison_id,
        output_dir=comparison_output_dir,
    )
    if not audit_payload.get("ok"):
        return audit_payload
    export_payload = _export_deliberation_campaign_benchmark_matrix_comparison_artifact(
        comparison_id,
        comparison_output_dir=comparison_output_dir,
        output_dir=export_output_dir,
        format=normalized_format,
    )
    if not export_payload.get("ok"):
        return export_payload
    audit = audit_payload.get("result", {})
    export = export_payload.get("result", {})
    return _success(
        comparison_id=comparison_id,
        baseline_matrix_id=comparison_payload.get("baseline_matrix_id"),
        candidate_matrix_id=comparison_payload.get("candidate_matrix_id"),
        latest=latest,
        comparison=comparison_payload,
        audit=audit,
        export=export.get("content"),
        export_payload=export,
        report_path=comparison_payload.get("report_path"),
        artifact_path=comparison_payload.get("report_path"),
        audit_artifact_path=audit_payload.get("artifact_path"),
        export_artifact_path=export_payload.get("artifact_path"),
        export_manifest_path=export_payload.get("manifest_path"),
        format=normalized_format,
    )


def _deliberation_campaign_artifact_index(
    *,
    limit: int = 20,
    campaign_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    campaign_base = Path(campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    benchmark_base = Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)
    matrix_benchmark_base = Path(
        matrix_benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR
    )
    matrix_benchmark_export_base = Path(
        matrix_benchmark_export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR
    )
    comparison_base = Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    export_base = Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)
    helper = getattr(sys.modules[__name__], "build_deliberation_campaign_artifact_index", None)
    if not callable(helper):
        helper = build_deliberation_campaign_artifact_index
    if callable(helper):
        try:
            helper_kwargs: dict[str, Any] = {
                "limit": limit,
                "campaign_output_dir": campaign_base,
                "benchmark_output_dir": benchmark_base,
                "comparison_output_dir": comparison_base,
                "export_output_dir": export_base,
            }
            if matrix_benchmark_output_dir is not None:
                helper_kwargs["matrix_benchmark_output_dir"] = matrix_benchmark_base
            if matrix_benchmark_export_output_dir is not None:
                helper_kwargs["matrix_benchmark_export_output_dir"] = matrix_benchmark_export_base
            if matrix_benchmark_comparison_output_dir is not None:
                helper_kwargs["matrix_benchmark_comparison_output_dir"] = Path(
                    matrix_benchmark_comparison_output_dir
                )
            if matrix_benchmark_comparison_export_output_dir is not None:
                helper_kwargs["matrix_benchmark_comparison_export_output_dir"] = Path(
                    matrix_benchmark_comparison_export_output_dir
                )
            payload = helper(**helper_kwargs)
            payload = _coerce_report_payload(payload)
            matrix_benchmark_exports = _list_deliberation_campaign_benchmark_matrix_export_artifacts(
                limit=limit,
                output_dir=matrix_benchmark_export_base,
            )
            output_dirs = payload.get("output_dirs")
            if not isinstance(output_dirs, dict):
                output_dirs = {
                    "campaigns": str(campaign_base),
                    "benchmarks": str(benchmark_base),
                    "matrix_benchmarks": str(matrix_benchmark_base),
                    "matrix_benchmark_exports": str(matrix_benchmark_export_base),
                    "matrix_benchmark_comparisons": str(
                        Path(
                            matrix_benchmark_comparison_output_dir
                            or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR
                        )
                    ),
                    "matrix_benchmark_comparison_exports": str(
                        Path(
                            matrix_benchmark_comparison_export_output_dir
                            or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR
                        )
                    ),
                    "comparisons": str(comparison_base),
                    "exports": str(export_base),
                }
            else:
                output_dirs["matrix_benchmark_exports"] = str(matrix_benchmark_export_base)
            payload["output_dirs"] = output_dirs

            counts = payload.get("counts")
            if not isinstance(counts, dict):
                counts = {}
            counts["matrix_benchmark_exports"] = matrix_benchmark_exports.get("count", 0)
            payload["counts"] = counts

            recent = payload.get("recent")
            if not isinstance(recent, dict):
                recent = {}
            recent["matrix_benchmark_exports"] = matrix_benchmark_exports.get("exports", [])
            payload["recent"] = recent
            return payload
        except Exception:
            pass
    campaigns = _list_deliberation_campaign_artifacts(limit=limit)
    benchmarks = _list_deliberation_campaign_benchmark_artifacts(limit=limit, output_dir=benchmark_base)
    matrix_benchmarks = _list_deliberation_campaign_benchmark_matrix_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_base,
    )
    matrix_benchmark_exports = _list_deliberation_campaign_benchmark_matrix_export_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_export_base,
    )
    matrix_benchmark_comparisons = _list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_comparison_output_dir,
    )
    comparisons = _list_deliberation_campaign_comparison_artifacts(limit=limit, output_dir=comparison_base)
    exports = _list_deliberation_campaign_comparison_export_artifacts(limit=limit, output_dir=export_base)
    return _success(
        limit=limit,
        campaign_output_dir=str(campaign_base),
        benchmark_output_dir=str(benchmark_base),
        matrix_benchmark_output_dir=str(matrix_benchmark_base),
        matrix_benchmark_export_output_dir=str(matrix_benchmark_export_base),
        matrix_benchmark_comparison_output_dir=str(
            Path(
                matrix_benchmark_comparison_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR
            )
        ),
        matrix_benchmark_comparison_export_output_dir=str(
            Path(
                matrix_benchmark_comparison_export_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR
            )
        ),
        comparison_output_dir=str(comparison_base),
        export_output_dir=str(export_base),
        counts={
            "campaigns": campaigns.get("count", 0),
            "benchmarks": benchmarks.get("count", 0),
            "matrix_benchmarks": matrix_benchmarks.get("count", 0),
            "matrix_benchmark_exports": matrix_benchmark_exports.get("count", 0),
            "matrix_benchmark_comparisons": matrix_benchmark_comparisons.get("count", 0),
            "matrix_benchmark_comparison_exports": 0,
            "comparisons": comparisons.get("count", 0),
            "exports": exports.get("count", 0),
        },
        campaigns=campaigns.get("campaigns", []),
        benchmarks=benchmarks.get("benchmarks", []),
        matrix_benchmarks=matrix_benchmarks.get("matrices", []),
        matrix_benchmark_exports=matrix_benchmark_exports.get("exports", []),
        matrix_benchmark_comparisons=matrix_benchmark_comparisons.get("comparisons", []),
        comparisons=comparisons.get("comparisons", []),
        exports=exports.get("exports", []),
    )


def _list_deliberation_campaign_global_artifact_index(
    *,
    limit: int = 20,
    campaign_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    campaigns = _list_deliberation_campaign_artifacts(limit=limit, status=None)
    benchmarks = _list_deliberation_campaign_benchmark_artifacts(limit=limit, output_dir=benchmark_output_dir)
    matrix_benchmarks = _list_deliberation_campaign_benchmark_matrix_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_output_dir,
    )
    matrix_benchmark_exports = _list_deliberation_campaign_benchmark_matrix_export_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_export_output_dir,
    )
    matrix_benchmark_comparisons = _list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_comparison_output_dir,
    )
    matrix_benchmark_comparison_exports = _list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts(
        limit=limit,
        output_dir=matrix_benchmark_comparison_export_output_dir,
    )
    comparisons = _list_deliberation_campaign_comparison_artifacts(limit=limit, output_dir=comparison_output_dir)
    exports = _list_deliberation_campaign_comparison_export_artifacts(limit=limit, output_dir=export_output_dir)
    return _success(
        limit=limit,
        campaign_output_dir=str(Path(campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)),
        benchmark_output_dir=str(Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)),
        matrix_benchmark_output_dir=str(
            Path(matrix_benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
        ),
        matrix_benchmark_export_output_dir=str(
            Path(matrix_benchmark_export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR)
        ),
        matrix_benchmark_comparison_output_dir=str(
            Path(
                matrix_benchmark_comparison_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR
            )
        ),
        matrix_benchmark_comparison_export_output_dir=str(
            Path(
                matrix_benchmark_comparison_export_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR
            )
        ),
        comparison_output_dir=str(Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)),
        export_output_dir=str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
        campaigns=campaigns.get("campaigns", []),
        benchmarks=benchmarks.get("benchmarks", []),
        matrix_benchmarks=matrix_benchmarks.get("matrices", []),
        matrix_benchmark_exports=matrix_benchmark_exports.get("exports", []),
        matrix_benchmark_comparisons=matrix_benchmark_comparisons.get("comparisons", []),
        matrix_benchmark_comparison_exports=matrix_benchmark_comparison_exports.get("exports", []),
        comparisons=comparisons.get("comparisons", []),
        exports=exports.get("exports", []),
        counts={
            "campaigns": campaigns.get("count", 0),
            "benchmarks": benchmarks.get("count", 0),
            "matrix_benchmarks": matrix_benchmarks.get("count", 0),
            "matrix_benchmark_exports": matrix_benchmark_exports.get("count", 0),
            "matrix_benchmark_comparisons": matrix_benchmark_comparisons.get("count", 0),
            "matrix_benchmark_comparison_exports": matrix_benchmark_comparison_exports.get("count", 0),
            "comparisons": comparisons.get("count", 0),
            "exports": exports.get("count", 0),
        },
    )


def _export_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    *,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="comparison_export_format_unsupported",
            comparison_id=comparison_id,
            format=format,
        )
    audit_payload = _audit_deliberation_campaign_comparison_artifact(
        comparison_id,
        output_dir=comparison_output_dir,
    )
    if not audit_payload.get("ok"):
        return audit_payload
    audit = audit_payload.get("result", {})
    export = materialize_deliberation_campaign_comparison_export(
        audit,
        format=normalized_format,
        output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
        export_id=_comparison_export_id(comparison_id, format=normalized_format),
    )
    export_payload = export.model_dump(mode="json")
    return _success(
        comparison_id=comparison_id,
        export_id=export_payload.get("export_id"),
        artifact_path=export_payload.get("content_path"),
        manifest_path=export_payload.get("manifest_path"),
        report_path=audit_payload.get("artifact_path"),
        format=normalized_format,
        audit=audit,
        export=export_payload.get("content"),
    )


def _compare_audit_export_deliberation_campaign_artifacts(
    baseline_campaign_id: str,
    candidate_campaign_id: str,
    *,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="comparison_export_format_unsupported",
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
            format=format,
        )

    bundle_helper = getattr(sys.modules[__name__], "compare_deliberation_campaign_bundle", None)
    use_bundle_helper = callable(bundle_helper) and getattr(bundle_helper, "__module__", "") != "swarm_core.deliberation_campaign"
    if use_bundle_helper:
        bundle_result = bundle_helper(
            campaign_ids=[baseline_campaign_id, candidate_campaign_id],
            persist=True,
            comparison_output_dir=comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
            export_output_dir=export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
            format=normalized_format,
        )
        bundle_payload = (
            bundle_result.model_dump(mode="json")
            if hasattr(bundle_result, "model_dump")
            else dict(bundle_result)
        )
        comparison_payload = bundle_payload.get("comparison_report", {})
        audit_payload = bundle_payload.get("audit", {})
        export_payload = bundle_payload.get("export", {})
    else:
        comparison_helper = getattr(sys.modules[__name__], "compare_deliberation_campaign_reports", None)
        if not callable(comparison_helper):
            comparison_helper = compare_deliberation_campaign_reports
        comparison_report = comparison_helper(
            campaign_ids=[baseline_campaign_id, candidate_campaign_id],
            persist=True,
            comparison_output_dir=comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
        )
        comparison_payload = comparison_report.model_dump(mode="json")

        audit_helper = getattr(sys.modules[__name__], "load_deliberation_campaign_comparison_audit", None)
        if not callable(audit_helper):
            audit_helper = load_deliberation_campaign_comparison_audit
        audit_report = audit_helper(
            comparison_payload.get("comparison_id"),
            output_dir=comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
            include_markdown=normalized_format == "markdown",
        )
        audit_payload = audit_report.model_dump(mode="json")

        materialize_helper = getattr(sys.modules[__name__], "materialize_deliberation_campaign_comparison_export", None)
        if not callable(materialize_helper):
            materialize_helper = materialize_deliberation_campaign_comparison_export
        export_report = materialize_helper(
            audit_report,
            format=normalized_format,
            output_dir=export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR,
            export_id=_comparison_export_id(comparison_payload.get("comparison_id"), format=normalized_format),
        )
        export_payload = export_report.model_dump(mode="json")

    return _success(
        comparison_id=comparison_payload.get("comparison_id"),
        baseline_campaign_id=baseline_campaign_id,
        candidate_campaign_id=candidate_campaign_id,
        comparison=comparison_payload,
        audit=audit_payload,
        export=export_payload,
        report_path=comparison_payload.get("report_path"),
        artifact_path=comparison_payload.get("report_path"),
        audit_artifact_path=audit_payload.get("report_path"),
        export_artifact_path=export_payload.get("content_path"),
        export_manifest_path=export_payload.get("manifest_path"),
        format=normalized_format,
    )


def _audit_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)
    artifact_path = base_dir / comparison_id / "report.json"
    if not artifact_path.exists():
        return _success(comparison_id=comparison_id, exists=False, artifact_path=str(artifact_path), result=None)
    audit = load_deliberation_campaign_comparison_audit(
        comparison_id,
        output_dir=base_dir,
        include_markdown=False,
    ).model_dump(mode="json")
    return _success(
        comparison_id=comparison_id,
        exists=True,
        artifact_path=str(artifact_path),
        result=audit,
    )


def _campaign_report_overview(report: Any) -> dict[str, Any]:
    report_payload = report.model_dump(mode="json")
    summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    return {
        "campaign_id": report_payload.get("campaign_id"),
        "status": report_payload.get("status"),
        "topic": report_payload.get("topic"),
        "objective": report_payload.get("objective"),
        "created_at": report_payload.get("created_at"),
        "sample_count_requested": report_payload.get("sample_count_requested"),
        "stability_runs": report_payload.get("stability_runs"),
        "report_path": report_payload.get("report_path"),
        "summary": {
            "sample_count_completed": summary.get("sample_count_completed"),
            "sample_count_failed": summary.get("sample_count_failed"),
            "quality_score_mean": summary.get("quality_score_mean"),
            "confidence_level_mean": summary.get("confidence_level_mean"),
            "fallback_count": summary.get("fallback_count"),
        },
    }


def _count_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    keys = sorted(set(before) | set(after))
    deltas: dict[str, int] = {}
    for key in keys:
        delta = int(after.get(key, 0)) - int(before.get(key, 0))
        if delta:
            deltas[key] = delta
    return deltas


def _list_deliberation_campaign_artifacts(
    *,
    limit: int = 20,
    status: DeliberationCampaignStatus | str | None = None,
) -> dict[str, Any]:
    base_dir = Path(DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)
    if not base_dir.exists():
        return _success(output_dir=str(base_dir), exists=False, count=0, limit=limit, status=status, campaigns=[])

    campaigns: list[dict[str, Any]] = []
    for report in list_deliberation_campaign_reports(
        output_dir=base_dir,
        status=status,
        limit=limit,
    ):
        campaigns.append(_campaign_report_overview(report))
    return _success(
        output_dir=str(base_dir),
        exists=True,
        count=len(campaigns),
        limit=limit,
        status=None if status is None else str(getattr(status, "value", status)),
        campaigns=campaigns,
    )


def _compare_deliberation_campaign_artifacts(
    baseline_campaign_id: str,
    candidate_campaign_id: str,
) -> dict[str, Any]:
    comparison_report = compare_deliberation_campaign_reports(
        campaign_ids=[baseline_campaign_id, candidate_campaign_id],
        output_dir=DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
        persist=True,
        comparison_output_dir=DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR,
    )
    comparison_payload = comparison_report.model_dump(mode="json")
    entries = comparison_payload.get("entries", []) if isinstance(comparison_payload.get("entries"), list) else []
    baseline_payload = entries[0] if len(entries) >= 1 and isinstance(entries[0], dict) else {}
    candidate_payload = entries[1] if len(entries) >= 2 and isinstance(entries[1], dict) else {}
    summary = comparison_payload.get("summary") if isinstance(comparison_payload.get("summary"), dict) else {}

    return _success(
        comparison_id=comparison_payload.get("comparison_id"),
        baseline_campaign_id=baseline_campaign_id,
        candidate_campaign_id=candidate_campaign_id,
        artifact_path=comparison_payload.get("report_path"),
        persisted=bool(comparison_payload.get("report_path")),
        persist_error=None,
        result=comparison_payload,
        baseline=baseline_payload,
        candidate=candidate_payload,
        comparison={
            "status": {
                "baseline": baseline_payload.get("status"),
                "candidate": candidate_payload.get("status"),
                "changed": baseline_payload.get("status") != candidate_payload.get("status"),
            },
            "sample_count_requested": {
                "baseline": baseline_payload.get("sample_count_requested"),
                "candidate": candidate_payload.get("sample_count_requested"),
                "delta": int(candidate_payload.get("sample_count_requested", 0)) - int(baseline_payload.get("sample_count_requested", 0)),
            },
            "sample_count_completed": {
                "baseline": baseline_payload.get("sample_count_completed"),
                "candidate": candidate_payload.get("sample_count_completed"),
                "delta": int(candidate_payload.get("sample_count_completed", 0)) - int(baseline_payload.get("sample_count_completed", 0)),
            },
            "sample_count_failed": {
                "baseline": baseline_payload.get("sample_count_failed"),
                "candidate": candidate_payload.get("sample_count_failed"),
                "delta": int(candidate_payload.get("sample_count_failed", 0)) - int(baseline_payload.get("sample_count_failed", 0)),
            },
            "quality_score_mean": {
                "baseline": baseline_payload.get("quality_score_mean"),
                "candidate": candidate_payload.get("quality_score_mean"),
                "delta": round(
                    float(candidate_payload.get("quality_score_mean", 0.0)) - float(baseline_payload.get("quality_score_mean", 0.0)),
                    6,
                ),
            },
            "confidence_level_mean": {
                "baseline": baseline_payload.get("confidence_level_mean"),
                "candidate": candidate_payload.get("confidence_level_mean"),
                "delta": round(
                    float(candidate_payload.get("confidence_level_mean", 0.0)) - float(baseline_payload.get("confidence_level_mean", 0.0)),
                    6,
                ),
            },
            "fallback_count": {
                "baseline": baseline_payload.get("fallback_count"),
                "candidate": candidate_payload.get("fallback_count"),
                "delta": int(candidate_payload.get("fallback_count", 0)) - int(baseline_payload.get("fallback_count", 0)),
            },
            "runtime_count_deltas": _count_deltas(
                baseline_payload.get("runtime_counts") if isinstance(baseline_payload.get("runtime_counts"), dict) else {},
                candidate_payload.get("runtime_counts") if isinstance(candidate_payload.get("runtime_counts"), dict) else {},
            ),
            "engine_count_deltas": _count_deltas(
                baseline_payload.get("engine_counts") if isinstance(baseline_payload.get("engine_counts"), dict) else {},
                candidate_payload.get("engine_counts") if isinstance(candidate_payload.get("engine_counts"), dict) else {},
            ),
            "comparable": summary.get("comparable"),
            "mismatch_reasons": summary.get("mismatch_reasons", []),
        },
    )


def _normalize_prediction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if hasattr(value, "model_dump"):
            normalized[key] = value.model_dump(mode="json")
        elif isinstance(value, list):
            normalized[key] = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
        else:
            normalized[key] = value
    return normalized


def _compact_runtime_resilience_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    summary: dict[str, Any] = {}
    runtime_requested = payload.get("runtime_requested")
    runtime_used = payload.get("runtime_used")
    fallback_used = payload.get("fallback_used")
    if runtime_requested is not None or runtime_used is not None or fallback_used is not None:
        runtime_block: dict[str, Any] = {}
        if runtime_requested is not None:
            runtime_block["requested"] = runtime_requested
        if runtime_used is not None:
            runtime_block["used"] = runtime_used
        if fallback_used is not None:
            runtime_block["fallback_used"] = bool(fallback_used)
        if runtime_requested is not None and runtime_used is not None:
            runtime_block["matched"] = runtime_requested == runtime_used
        runtime_error = payload.get("runtime_error")
        if runtime_error is not None:
            runtime_block["runtime_error"] = runtime_error
        summary["runtime"] = runtime_block

    result = payload.get("result")
    if not isinstance(result, dict):
        runtime_resilience = payload.get("runtime_resilience")
        if isinstance(runtime_resilience, dict) and runtime_resilience:
            summary["runtime_resilience"] = _normalize_runtime_resilience(runtime_resilience)
        return summary or None

    comparability: dict[str, Any] = {}
    result_metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    runtime_resilience = result_metadata.get("runtime_resilience")
    normalized_runtime_resilience = _normalize_runtime_resilience(runtime_resilience) if isinstance(runtime_resilience, dict) else None
    if normalized_runtime_resilience:
        summary["runtime_resilience"] = normalized_runtime_resilience

    stability_summary = result.get("stability_summary")
    if isinstance(stability_summary, dict):
        for source_key, target_key in (
            ("sample_count", "stability_sample_count"),
            ("sample_sufficient", "stability_sample_sufficient"),
            ("stable", "stability_stable"),
            ("dispersion_gate_passed", "stability_dispersion_gate_passed"),
            ("mean_score", "stability_mean_score"),
            ("std_dev", "stability_std_dev"),
            ("score_spread", "stability_score_spread"),
            ("coefficient_of_variation", "stability_coefficient_of_variation"),
        ):
            value = stability_summary.get(source_key)
            if value is not None:
                comparability[target_key] = value

    metadata_comparability = result_metadata.get("comparability")
    if isinstance(metadata_comparability, dict):
        for key in (
            "stability_sample_count",
            "stability_sample_sufficient",
            "stability_stable",
            "profile_quality_diversity",
            "profile_quality_stance_diversity",
            "profile_quality_role_diversity",
        ):
            value = metadata_comparability.get(key)
            if value is not None:
                comparability[key] = value

    quality_warnings = result_metadata.get("quality_warnings")
    if isinstance(quality_warnings, list):
        comparability["quality_warning_count"] = len(quality_warnings)

    phase_counts = result_metadata.get("phase_counts")
    if isinstance(phase_counts, dict) and phase_counts:
        comparability["phase_count"] = len([key for key, value in phase_counts.items() if value])

    role_counts = result_metadata.get("role_counts")
    if isinstance(role_counts, dict) and role_counts:
        comparability["role_count"] = len([key for key, value in role_counts.items() if value])

    dissent_turn_count = result_metadata.get("dissent_turn_count")
    if dissent_turn_count is not None:
        comparability["dissent_turn_count"] = dissent_turn_count

    round_phases = result.get("round_phases")
    if isinstance(round_phases, list) and round_phases:
        comparability["round_phase_count"] = len({str(phase) for phase in round_phases if str(phase).strip()})

    comparability.update(
        _comparability_identity_summary(
            result_metadata,
            metadata_comparability if isinstance(metadata_comparability, dict) else None,
            result,
            payload,
            normalized_runtime_resilience,
        )
    )

    if normalized_runtime_resilience:
        for source_key, target_key in (
            ("status", "runtime_resilience_status"),
            ("score", "runtime_resilience_score"),
            ("attempt_count", "runtime_resilience_attempt_count"),
            ("retry_count", "runtime_resilience_retry_count"),
            ("fallback_used", "runtime_resilience_fallback_used"),
        ):
            value = normalized_runtime_resilience.get(source_key)
            if value is not None:
                comparability[target_key] = value

    if comparability:
        summary["comparability"] = comparability

    return summary or None


def _normalize_runtime_resilience(runtime_resilience: Any) -> dict[str, Any]:
    if not isinstance(runtime_resilience, dict):
        return {}
    normalized: dict[str, Any] = {}
    for source_key, target_key in (
        ("status", "status"),
        ("score", "score"),
        ("runtime_requested", "runtime_requested"),
        ("runtime_used", "runtime_used"),
        ("engine_requested", "engine_requested"),
        ("engine_used", "engine_used"),
        ("fallback_used", "fallback_used"),
        ("attempt_count", "attempt_count"),
        ("retry_count", "retry_count"),
        ("attempts", "attempts"),
        ("retries", "retries"),
        ("summary", "summary"),
        ("message", "message"),
        ("note", "note"),
        ("runtime_error", "runtime_error"),
        ("runtime_error_category", "runtime_error_category"),
        ("metric_name", "metric_name"),
        ("comparison_key", "comparison_key"),
    ):
        value = runtime_resilience.get(source_key)
        if value is not None:
            normalized[target_key] = value
    if "attempt_count" not in normalized and "attempts" in normalized:
        normalized["attempt_count"] = normalized["attempts"]
    if "retry_count" not in normalized and "retries" in normalized:
        normalized["retry_count"] = normalized["retries"]
    if "summary" not in normalized:
        note = normalized.get("message") or normalized.get("note")
        if note is not None:
            normalized["summary"] = note
    if "matched" not in normalized and normalized.get("runtime_requested") is not None and normalized.get("runtime_used") is not None:
        normalized["matched"] = normalized["runtime_requested"] == normalized["runtime_used"]
    return normalized


def _first_text_value(*values: Any) -> str | None:
    for value in values:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        text = " ".join(str(value).split())
        if text:
            return text
    return None


def _comparability_identity_summary(*sources: dict[str, Any] | None) -> dict[str, Any]:
    def pick(*keys: str) -> str | None:
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value is None or isinstance(value, (dict, list, tuple, set)):
                    continue
                text = " ".join(str(value).split())
                if text:
                    return text
        return None

    summary: dict[str, Any] = {}
    run_id = pick("run_id", "meeting_id", "deliberation_id", "thread_id")
    config_id = pick(
        "input_fingerprint",
        "input_hash",
        "workbench_input_hash",
        "topic_fingerprint",
        "objective_fingerprint",
        "participant_fingerprint",
        "config_id",
        "config_path",
    )
    runtime_id = pick(
        "execution_fingerprint",
        "model_name",
        "provider_base_url",
        "provider",
        "runtime_fingerprint",
        "runtime_id",
    )
    if run_id is not None:
        summary["run_id"] = run_id
    if config_id is not None:
        summary["config_id"] = config_id
    if runtime_id is not None:
        summary["runtime_id"] = runtime_id
    return summary


def _compact_improvement_resilience_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    summary: dict[str, Any] = {}
    runtime_requested = payload.get("runtime_requested")
    runtime_used = payload.get("runtime_used")
    fallback_used = payload.get("fallback_used")
    if runtime_requested is not None or runtime_used is not None or fallback_used is not None:
        runtime_block: dict[str, Any] = {}
        if runtime_requested is not None:
            runtime_block["requested"] = runtime_requested
        if runtime_used is not None:
            runtime_block["used"] = runtime_used
        if fallback_used is not None:
            runtime_block["fallback_used"] = bool(fallback_used)
        if runtime_requested is not None and runtime_used is not None:
            runtime_block["matched"] = runtime_requested == runtime_used
        runtime_error = payload.get("runtime_error")
        if runtime_error is not None:
            runtime_block["runtime_error"] = runtime_error
        summary["runtime"] = runtime_block

    context_metadata: dict[str, Any] = {}
    context_kind = None
    if isinstance(payload.get("inspection"), dict):
        context_kind = "inspection"
        inspection = payload["inspection"]
        context_metadata = inspection.get("metadata") if isinstance(inspection.get("metadata"), dict) else {}
    elif isinstance(payload.get("record"), dict):
        context_kind = "record"
        record = payload["record"]
        context_metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    elif isinstance(payload.get("run"), dict):
        context_kind = "run"
        run = payload["run"]
        rounds = run.get("rounds") if isinstance(run.get("rounds"), list) else []
        if rounds:
            comparability = summary.setdefault("comparability", {})
            comparability["round_count"] = len(rounds)
            if run.get("completed_rounds") is not None:
                comparability["completed_rounds"] = run.get("completed_rounds")
            if run.get("max_rounds") is not None:
                comparability["max_rounds"] = run.get("max_rounds")
            last_round = rounds[-1]
            if isinstance(last_round, dict):
                context_metadata = last_round.get("metadata") if isinstance(last_round.get("metadata"), dict) else {}
    else:
        runtime_resilience = payload.get("runtime_resilience")
        if isinstance(runtime_resilience, dict) and runtime_resilience:
            summary["runtime_resilience"] = _normalize_runtime_resilience(runtime_resilience)
            return summary
        return None

    runtime_resilience = context_metadata.get("runtime_resilience")
    normalized_runtime_resilience = _normalize_runtime_resilience(runtime_resilience) if isinstance(runtime_resilience, dict) else None
    comparability: dict[str, Any] = summary.setdefault("comparability", {})
    if normalized_runtime_resilience:
        summary["runtime_resilience"] = normalized_runtime_resilience
        for source_key, target_key in (
            ("status", "runtime_resilience_status"),
            ("score", "runtime_resilience_score"),
            ("attempt_count", "runtime_resilience_attempt_count"),
            ("retry_count", "runtime_resilience_retry_count"),
            ("fallback_used", "runtime_resilience_fallback_used"),
        ):
            value = normalized_runtime_resilience.get(source_key)
            if value is not None:
                comparability[target_key] = value

    metadata_comparability = context_metadata.get("comparability")
    if isinstance(metadata_comparability, dict):
        for key in (
            "runtime_resilience_status",
            "runtime_resilience_score",
            "runtime_resilience_attempt_count",
            "runtime_resilience_retry_count",
            "runtime_resilience_fallback_used",
            "quality_warning_count",
        ):
            value = metadata_comparability.get(key)
            if value is not None:
                comparability[key] = value

    comparability.update(
        _comparability_identity_summary(
            context_metadata,
            metadata_comparability if isinstance(metadata_comparability, dict) else None,
            payload,
        )
    )

    quality_warnings = context_metadata.get("quality_warnings")
    if isinstance(quality_warnings, list):
        comparability.setdefault("quality_warning_count", len(quality_warnings))

    if context_kind == "record":
        round_index = payload.get("record", {}).get("round_index")
        if round_index is not None:
            comparability["round_index"] = round_index

    if summary and not comparability:
        summary.pop("comparability", None)
    return summary or None


def _enrich_improvement_resilience_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _compact_improvement_resilience_summary(payload)
    if summary is None:
        return payload
    enriched = dict(payload)
    enriched["resilience_summary"] = summary
    return enriched


def _enrich_resilience_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _compact_runtime_resilience_summary(payload)
    if summary is None:
        return payload
    enriched = dict(payload)
    enriched["resilience_summary"] = summary
    return enriched


def _resolve_prediction_markets_decision_packet(
    decision_packet: dict[str, Any] | None = None,
    *,
    deliberation_id: str | None = None,
) -> dict[str, Any] | None:
    if decision_packet is not None:
        return decision_packet
    if not deliberation_id:
        return None
    result = load_deliberation_result(deliberation_id)
    packet = result.decision_packet
    if packet is None:
        raise ValueError(f"Deliberation {deliberation_id} has no persisted decision_packet.")
    if hasattr(packet, "model_dump"):
        return packet.model_dump(mode="json")
    if isinstance(packet, dict):
        return dict(packet)
    raise ValueError(f"Unsupported decision_packet payload for deliberation {deliberation_id}.")


def _prediction_markets_advise(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = advise_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_paper(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = paper_trade_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_risk(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = assess_market_risk_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_allocate(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = allocate_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_shadow(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = shadow_trade_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_live(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
    principal: str = "",
    scopes: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = live_execute_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        dry_run=dry_run,
        allow_live_execution=allow_live_execution,
        authorized=authorized,
        compliance_approved=compliance_approved,
        require_human_approval_before_live=require_human_approval_before_live,
        human_approval_passed=human_approval_passed,
        human_approval_actor=human_approval_actor,
        human_approval_reason=human_approval_reason,
        principal=principal,
        scopes=scopes or [],
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_market_execution(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
    principal: str = "",
    scopes: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = market_execution_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        decision_packet=_resolve_prediction_markets_decision_packet(decision_packet, deliberation_id=deliberation_id),
        stake=stake,
        dry_run=dry_run,
        allow_live_execution=allow_live_execution,
        authorized=authorized,
        compliance_approved=compliance_approved,
        require_human_approval_before_live=require_human_approval_before_live,
        human_approval_passed=human_approval_passed,
        human_approval_actor=human_approval_actor,
        human_approval_reason=human_approval_reason,
        principal=principal,
        scopes=scopes or [],
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_research(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = research_market_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_multi_venue_paper(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    target_notional_usd: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = multi_venue_paper_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        target_notional_usd=target_notional_usd,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_slippage(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    position_side: str = "yes",
    execution_side: str = "buy",
    requested_quantity: float | None = None,
    requested_notional: float | None = None,
    limit_price: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = simulate_market_slippage_sync(
        market_id=market_id,
        slug=slug,
        position_side=TradeSide(position_side),
        execution_side=TradeSide(execution_side),
        requested_quantity=requested_quantity,
        requested_notional=requested_notional,
        limit_price=limit_price,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_microstructure(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    position_side: str = "yes",
    execution_side: str = "buy",
    requested_quantity: float = 1.0,
    capital_available_usd: float | None = None,
    capital_locked_usd: float = 0.0,
    queue_ahead_quantity: float = 0.0,
    spread_collapse_threshold_bps: float = 50.0,
    collapse_liquidity_multiplier: float = 0.35,
    limit_price: float | None = None,
    fee_bps: float = 0.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = simulate_microstructure_lab_sync(
        market_id=market_id,
        slug=slug,
        position_side=TradeSide(position_side),
        execution_side=TradeSide(execution_side),
        requested_quantity=requested_quantity,
        capital_available_usd=capital_available_usd,
        capital_locked_usd=capital_locked_usd,
        queue_ahead_quantity=queue_ahead_quantity,
        spread_collapse_threshold_bps=spread_collapse_threshold_bps,
        collapse_liquidity_multiplier=collapse_liquidity_multiplier,
        limit_price=limit_price,
        fee_bps=fee_bps,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_comment_intel(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    comments: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = analyze_market_comments_sync(
        market_id=market_id,
        slug=slug,
        comments=comments or [],
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_manipulation_guard(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    comments: list[str] | None = None,
    poll_count: int = 0,
    stale_after_seconds: float = 3600.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = guard_market_manipulation_sync(
        market_id=market_id,
        slug=slug,
        evidence_inputs=evidence or [],
        comments=comments or [],
        poll_count=poll_count,
        stale_after_seconds=stale_after_seconds,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_graph(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = build_market_graph_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_cross_venue(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = cross_venue_intelligence_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_spread_monitor(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = monitor_market_spreads_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_arbitrage_lab(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = assess_market_arbitrage_sync(
        market_id=market_id,
        slug=slug,
        limit=limit,
        include_additional_venues=include_additional_venues,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_stream_open(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    poll_count: int = 1,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = open_market_stream_sync(
        market_id=market_id,
        slug=slug,
        poll_count=poll_count,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_stream_summary(
    stream_id: str,
    *,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = market_stream_summary_sync(stream_id, backend_mode=backend_mode)
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_stream_health(
    stream_id: str,
    *,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = market_stream_health_sync(
        stream_id,
        stale_after_seconds=stale_after_seconds,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_stream_collect(
    *,
    market_ids: list[str] | None = None,
    slugs: list[str] | None = None,
    stream_ids: list[str] | None = None,
    fanout: int = 4,
    retries: int = 1,
    timeout_seconds: float = 5.0,
    cache_ttl_seconds: float = 60.0,
    prefetch: bool = True,
    backpressure_limit: int = 32,
    priority_strategy: str = "freshness",
    poll_count: int = 1,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = stream_collect_sync(
        market_ids=market_ids,
        slugs=slugs,
        stream_ids=stream_ids,
        fanout=fanout,
        retries=retries,
        timeout_seconds=timeout_seconds,
        cache_ttl_seconds=cache_ttl_seconds,
        prefetch=prefetch,
        backpressure_limit=backpressure_limit,
        priority_strategy=priority_strategy,
        poll_count=poll_count,
        stale_after_seconds=stale_after_seconds,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_replay(run_id: str) -> dict[str, Any]:
    payload = replay_market_run_sync(run_id)
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_replay_postmortem(run_id: str) -> dict[str, Any]:
    payload = replay_market_postmortem_sync(run_id)
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_reconcile(
    run_id: str,
    *,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = reconcile_market_run_sync(
        run_id,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_worldmonitor(
    source: str,
    *,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = ingest_worldmonitor_sidecar_sync(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_twitter_watcher(
    source: str,
    *,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = ingest_twitter_watcher_sidecar_sync(
        source,
        market_id=market_id,
        slug=slug,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_venues(
    *,
    query: str | None = None,
    limit_per_venue: int = 2,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = additional_venues_catalog_sync(
        query=query,
        limit_per_venue=limit_per_venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_events(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    venue: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = market_events_sync(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_positions(
    *,
    market_id: str | None = None,
    slug: str | None = None,
    venue: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    payload = market_positions_sync(
        market_id=market_id,
        slug=slug,
        venue=venue,
        persist=persist,
        backend_mode=backend_mode,
    )
    return _success(result=_normalize_prediction_payload(payload))


def _prediction_markets_runs(limit: int = 20) -> dict[str, Any]:
    registry = RunRegistry()
    runs = [entry.model_dump(mode="json") for entry in registry.recent(limit=limit)]
    return _success(result={"count": len(runs), "limit": limit, "runs": runs})


def _list_deliberation_targets(deliberation_id: str) -> dict[str, Any]:
    targets = collect_deliberation_targets(deliberation_id)
    return _success(
        deliberation_id=deliberation_id,
        targets=[target.model_dump(mode="json") for target in targets],
    )


def _interview_deliberation(deliberation_id: str, *, question: str, target_id: str | None = None) -> dict[str, Any]:
    result = run_deliberation_interview_sync(
        deliberation_id,
        question=question,
        target_id=target_id,
    )
    return _success(
        deliberation_id=deliberation_id,
        result=result.model_dump(mode="json"),
    )


def _persona_chat_deliberation(deliberation_id: str, *, question: str, target_id: str | None = None) -> dict[str, Any]:
    result = load_deliberation_result(deliberation_id)
    targets = collect_deliberation_targets(deliberation_id)
    selected_target = next((target for target in targets if target.target_id == target_id), None)
    if selected_target is None:
        selected_target = next((target for target in targets if target.target_type.value == "agent"), targets[0])
    service = DeliberationPersonaChatService()
    session = service.start_or_continue(
        deliberation_id=deliberation_id,
        topic=result.topic,
        objective=result.objective,
        target=selected_target,
        question=question,
    )
    html_path = service.export_html(session)
    payload = session.model_dump(mode="json")
    payload["html_path"] = str(html_path)
    return _success(deliberation_id=deliberation_id, result=payload)


def _export_deliberation_neo4j(deliberation_id: str) -> dict[str, Any]:
    result = load_deliberation_result(deliberation_id)
    if not result.graph_path:
        return _failure("No persisted graph available for this deliberation.", error_code="graph_missing", deliberation_id=deliberation_id)
    store = GraphStore.load(result.graph_path)
    bundle = Neo4jFriendlyGraphBackendAdapter(store).export()
    return _success(deliberation_id=deliberation_id, result=bundle.model_dump(mode="json"))


def _bridge_deliberation_market(deliberation_id: str) -> dict[str, Any]:
    result = load_deliberation_result(deliberation_id)
    bridge = DeepMarketSocialBridge().run(
        MarketSocialBridgeRequest(
            topic=result.topic,
            objective=result.objective,
            participants=result.participants,
            documents=[item.content for item in result.provenance if item.content][:6],
            interventions=result.next_actions or result.uncertainty_points,
            market_signals=[
                MarketSignal(
                    name=name,
                    value=value,
                    direction=SignalDirection.up if value > 0 else SignalDirection.down if value < 0 else SignalDirection.flat,
                )
                for name, value in result.metrics.items()
            ],
            social_signals=[
                SocialSignal(
                    name=summary.group_id or f"group_{index}",
                    value=summary.average_confidence,
                    sentiment=SocialSentiment.positive if summary.average_confidence >= 0.6 else SocialSentiment.negative if summary.average_confidence <= 0.4 else SocialSentiment.neutral,
                    reach=float(summary.agent_count),
                    weight=max(0.1, summary.average_trust),
                )
                for index, summary in enumerate(result.belief_group_summaries, start=1)
            ],
        )
    )
    return _success(deliberation_id=deliberation_id, result=bridge.model_dump(mode="json"))


def _project_capabilities() -> dict[str, Any]:
    controller = _get_improvement_controller()
    return _success(
        module=__name__,
        canonical_module="swarm_mcp",
        canonical_script="swarm_mcp.py",
        legacy_aliases=["openclaw_mcp"],
        legacy_scripts=["openclaw_mcp.py"],
        server_name=MCP_SERVER_NAME,
        repo_root=str(REPO_ROOT),
        entrypoints={
            "cli": "main.py",
            "mcp": "swarm_mcp.py",
            "legacy_mcp_alias": "openclaw_mcp.py",
        },
        runtimes=[runtime_capabilities()["mission_runtime"], *runtime_capabilities()["supported"]],
        runtime_defaults={
            "mission": "langgraph",
            "strategy_meeting": RuntimeBackend.pydanticai.value,
            "deliberation": RuntimeBackend.pydanticai.value,
            "improvement": RuntimeBackend.pydanticai.value,
        },
        runtime_health=_collect_runtime_health()["runtimes"],
        improvement_targets=[descriptor.target_id for descriptor in controller.list_targets()],
        tools=[
            "project_capabilities",
            "runtime_health",
            "delegate_to_swarm_supervisor",
            "get_mission_status",
            "resume_mission",
            "read_mission_log",
            "run_strategy_meeting",
            "read_strategy_meeting_artifact",
            "run_deliberation",
            "run_deliberation_campaign",
            "read_deliberation_artifact",
            "read_deliberation_campaign_artifact",
            "read_deliberation_campaign_benchmark_artifact",
            "read_deliberation_campaign_benchmark_matrix_artifact",
            "read_deliberation_campaign_benchmark_matrix_export_artifact",
            "read_deliberation_campaign_benchmark_matrix_export_comparison_artifact",
            "read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact",
            "read_deliberation_campaign_benchmark_matrix_comparison_artifact",
            "read_deliberation_campaign_benchmark_matrix_comparison_export_artifact",
            "read_deliberation_campaign_comparison_artifact",
            "list_deliberation_campaigns",
            "list_deliberation_campaign_benchmarks",
            "list_deliberation_campaign_benchmark_matrix_artifacts",
            "list_deliberation_campaign_benchmark_matrix_export_artifacts",
            "list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts",
            "list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts",
            "list_deliberation_campaign_benchmark_matrix_comparison_artifacts",
            "list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts",
            "list_deliberation_campaign_comparison_artifacts",
            "read_deliberation_campaign_comparison_export_artifact",
            "list_deliberation_campaign_comparison_export_artifacts",
            "audit_deliberation_campaign_comparison_artifact",
            "export_deliberation_campaign_comparison_artifact",
            "compare_deliberation_campaigns",
            "compare_deliberation_campaign_benchmark_matrix_exports",
            "compare_deliberation_campaign_benchmark_matrices",
            "audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact",
            "export_deliberation_campaign_benchmark_matrix_export_comparison_artifact",
            "audit_deliberation_campaign_benchmark_matrix_artifact",
            "export_deliberation_campaign_benchmark_matrix_artifact",
            "audit_deliberation_campaign_benchmark_matrix_comparison_artifact",
            "export_deliberation_campaign_benchmark_matrix_comparison_artifact",
            "compare_audit_export_deliberation_campaign_benchmark_matrix_exports",
            "compare_audit_export_deliberation_campaign_benchmark_matrices",
            "compare_audit_export_deliberation_campaigns",
            "benchmark_deliberation_campaigns",
            "benchmark_deliberation_campaign_matrix",
            "deliberation_campaign_index",
            "deliberation_campaign_dashboard",
            "list_deliberation_targets",
            "interview_deliberation",
            "persona_chat_deliberation",
            "export_deliberation_neo4j",
            "bridge_deliberation_market",
            "replay_deliberation",
            "prediction_markets_advise",
            "prediction_markets_paper",
            "prediction_markets_risk",
            "prediction_markets_allocate",
            "prediction_markets_shadow",
            "prediction_markets_live",
            "prediction_markets_market_execution",
            "prediction_markets_research",
            "prediction_markets_slippage",
            "prediction_markets_microstructure",
            "prediction_markets_comment_intel",
            "prediction_markets_manipulation_guard",
            "prediction_markets_graph",
            "prediction_markets_cross_venue",
            "prediction_markets_multi_venue_paper",
            "prediction_markets_spread_monitor",
            "prediction_markets_arbitrage_lab",
            "prediction_markets_stream_open",
            "prediction_markets_stream_summary",
            "prediction_markets_stream_health",
            "prediction_markets_stream_collect",
            "prediction_markets_worldmonitor",
            "prediction_markets_twitter_watcher",
            "prediction_markets_events",
            "prediction_markets_positions",
            "prediction_markets_venues",
            "prediction_markets_reconcile",
            "prediction_markets_replay",
            "prediction_markets_replay_postmortem",
            "prediction_markets_runs",
            "list_improvement_targets",
            "inspect_improvement_target",
            "run_improvement_round",
            "run_improvement_loop",
            "inspect_harness_state",
        ],
    )


@mcp.tool(structured_output=True)
def project_capabilities() -> dict[str, Any]:
    """Describe the project MCP surface exposed to MCP clients and local tooling."""
    return _project_capabilities()


@mcp.tool(structured_output=True)
def runtime_health(runtime_name: str = "all") -> dict[str, Any]:
    """Inspect runtime/provider health for langgraph, pydanticai, or legacy."""
    try:
        return _collect_runtime_health(runtime_name)
    except Exception as exc:
        return _failure(
            f"Failed to inspect runtime health: {exc}",
            error_code="runtime_health_failed",
            runtime=runtime_name,
        )


@mcp.tool(structured_output=True)
def delegate_to_swarm_supervisor(
    task: str,
    thread_id: str | None = None,
    task_type: str = "analysis",
    engine_preference: str = "agentsociety",
    max_agents: int = 1000,
    time_horizon: str = "7d",
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Launch a new mission through the Swarm-facing CLI entrypoint."""
    mission_thread_id = thread_id or f"mission_{uuid.uuid4().hex[:8]}"
    command = [
        str(PYTHON_BIN),
        str(MAIN_SCRIPT),
        "delegate",
        task,
        "--thread-id",
        mission_thread_id,
        "--task-type",
        task_type,
        "--engine-preference",
        engine_preference,
        "--max-agents",
        str(max_agents),
        "--time-horizon",
        time_horizon,
        "--budget-max",
        str(budget_max),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    return _launch_background_command(
        command=command,
        thread_id=mission_thread_id,
        action="launch mission",
    )


@mcp.tool(structured_output=True)
def get_mission_status(thread_id: str) -> dict[str, Any]:
    """Return the latest checkpointed mission state for a thread."""
    try:
        return _collect_mission_status(thread_id)
    except Exception as exc:
        return _failure(
            f"Failed to read mission status: {exc}",
            error_code="status_failed",
            thread_id=thread_id,
        )


@mcp.tool(structured_output=True)
def resume_mission(thread_id: str) -> dict[str, Any]:
    """Resume a paused mission in the background."""
    return _launch_background_command(
        command=[str(PYTHON_BIN), str(MAIN_SCRIPT), "resume", "--thread-id", thread_id],
        thread_id=thread_id,
        action="resume mission",
    )


@mcp.tool(structured_output=True)
def read_mission_log(thread_id: str, lines: int = 50) -> dict[str, Any]:
    """Read the last lines of a mission log file."""
    log_file = _mission_log_path(thread_id)
    if not log_file.exists():
        return _success(
            thread_id=thread_id,
            exists=False,
            log_file=str(log_file),
            tail="",
        )
    safe_lines = max(1, min(lines, 500))
    tail = "\n".join(log_file.read_text(encoding="utf-8").splitlines()[-safe_lines:])
    return _success(
        thread_id=thread_id,
        exists=True,
        log_file=str(log_file),
        lines=safe_lines,
        tail=tail,
    )


@mcp.tool(structured_output=True)
def run_strategy_meeting(
    topic: str,
    objective: str | None = None,
    participants: list[str] | None = None,
    max_agents: int = 6,
    rounds: int = 2,
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    """Run a bounded multi-agent strategy meeting and synthesize a recommended strategy."""
    try:
        return _enrich_resilience_payload(
            _run_strategy_meeting_session(
                topic=topic,
                objective=objective,
                participants=participants,
                max_agents=max_agents,
                rounds=rounds,
                persist=persist,
                config_path=config_path,
                runtime=runtime,
                allow_fallback=allow_fallback,
            )
        )
    except Exception as exc:
        return _failure(
            f"Failed to run strategy meeting: {exc}",
            error_code="strategy_meeting_failed",
            topic=topic,
            requested_participants=participants or [],
            max_agents=max_agents,
            rounds=rounds,
        )


@mcp.tool(structured_output=True)
def read_strategy_meeting_artifact(meeting_id: str) -> dict[str, Any]:
    """Read a persisted strategy-meeting artifact by meeting id."""
    try:
        return _read_strategy_meeting_artifact(meeting_id)
    except Exception as exc:
        return _failure(
            f"Failed to read strategy meeting artifact: {exc}",
            error_code="meeting_artifact_failed",
            meeting_id=meeting_id,
        )


@mcp.tool(structured_output=True)
def run_deliberation(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    engine_preference: str = "agentsociety",
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run a committee, simulation, or hybrid deliberation and persist its artifacts."""
    try:
        return _enrich_resilience_payload(
            _run_deliberation_session(
                topic=topic,
                objective=objective,
                mode=mode,
                participants=participants,
                documents=documents,
                entities=entities,
                interventions=interventions,
                max_agents=max_agents,
                population_size=population_size,
                rounds=rounds,
                time_horizon=time_horizon,
                persist=persist,
                config_path=config_path,
                runtime=runtime,
                allow_fallback=allow_fallback,
                engine_preference=engine_preference,
                ensemble_engines=ensemble_engines,
                budget_max=budget_max,
                timeout_seconds=timeout_seconds,
                benchmark_path=benchmark_path,
                stability_runs=stability_runs,
                backend_mode=backend_mode,
            )
        )
    except Exception as exc:
        return _failure(
            f"Failed to run deliberation: {exc}",
            error_code="deliberation_failed",
            topic=topic,
            mode=mode,
        )


@mcp.tool(structured_output=True)
def run_deliberation_campaign(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    engine_preference: str = "agentsociety",
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    sample_count: int = 3,
    backend_mode: str | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Run repeated deliberation samples and aggregate them into a campaign artifact."""
    try:
        report = run_deliberation_campaign_sync(
            topic=topic,
            objective=objective,
            mode=mode,
            participants=participants,
            documents=documents,
            entities=entities,
            interventions=interventions,
            max_agents=max_agents,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            sample_count=sample_count,
            stability_runs=stability_runs,
            runtime=normalize_runtime_backend(runtime).value,
            allow_fallback=allow_fallback,
            engine_preference=engine_preference,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
            benchmark_path=benchmark_path,
            config_path=config_path,
            backend_mode=backend_mode,
            persist=persist,
            output_dir=DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
            campaign_id=campaign_id,
            runner=run_deliberation_runtime,
        )
        return _success(campaign_id=report.campaign_id, result=report.model_dump(mode="json"))
    except Exception as exc:
        return _failure(
            f"Failed to run deliberation campaign: {exc}",
            error_code="deliberation_campaign_failed",
            topic=topic,
            mode=mode,
            sample_count=sample_count,
        )


@mcp.tool(structured_output=True)
def read_deliberation_artifact(deliberation_id: str) -> dict[str, Any]:
    """Read a persisted deliberation artifact by deliberation id."""
    try:
        return _read_deliberation_artifact(deliberation_id)
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation artifact: {exc}",
            error_code="deliberation_artifact_failed",
            deliberation_id=deliberation_id,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_artifact(campaign_id: str) -> dict[str, Any]:
    """Read a persisted deliberation campaign artifact by campaign id."""
    try:
        return _read_deliberation_campaign_artifact(campaign_id)
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign artifact: {exc}",
            error_code="deliberation_campaign_artifact_failed",
            campaign_id=campaign_id,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_artifact(
    benchmark_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark artifact by benchmark id."""
    try:
        return _read_deliberation_campaign_benchmark_artifact(benchmark_id, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark artifact: {exc}",
            error_code="deliberation_campaign_benchmark_artifact_failed",
            benchmark_id=benchmark_id,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign comparison artifact by comparison id."""
    try:
        return _read_deliberation_campaign_comparison_artifact(comparison_id, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign comparison artifact: {exc}",
            error_code="deliberation_campaign_comparison_artifact_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaigns(
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign artifacts."""
    try:
        return _list_deliberation_campaign_artifacts(limit=limit, status=status)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaigns: {exc}",
            error_code="deliberation_campaign_listing_failed",
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmarks(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_artifacts(limit=limit, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmarks: {exc}",
            error_code="deliberation_campaign_benchmark_listing_failed",
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_artifact(matrix_id, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_artifact_failed",
            matrix_id=matrix_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_artifacts(limit=limit, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_listing_failed",
        )


@mcp.tool(structured_output=True)
def audit_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a persisted deliberation campaign benchmark matrix artifact."""
    try:
        return _audit_deliberation_campaign_benchmark_matrix_artifact(matrix_id, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to audit deliberation campaign benchmark matrix artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_audit_failed",
            matrix_id=matrix_id,
        )


@mcp.tool(structured_output=True)
def export_deliberation_campaign_benchmark_matrix_artifact(
    matrix_id: str,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Export a persisted deliberation campaign benchmark matrix artifact as markdown or JSON."""
    try:
        return _export_deliberation_campaign_benchmark_matrix_artifact(
            matrix_id,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to export deliberation campaign benchmark matrix artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_failed",
            matrix_id=matrix_id,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_export_artifact(
    matrix_id: str,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix export artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_export_artifact(
            matrix_id,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix export artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_artifact_failed",
            matrix_id=matrix_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_export_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix export artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_export_artifacts(limit=limit, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix export artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_listing_failed",
        )


@mcp.tool(structured_output=True)
def compare_deliberation_campaign_benchmark_matrix_exports(
    export_ids: list[str] | None = None,
    latest: int | None = None,
    output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare persisted deliberation campaign benchmark matrix export artifacts."""
    try:
        report = core_compare_deliberation_campaign_matrix_benchmark_exports(
            export_ids=export_ids,
            latest=latest,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR,
            persist=True,
            comparison_output_dir=(
                comparison_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR
            ),
        )
        payload = _matrix_benchmark_export_comparison_report_payload(report)
        return _success(
            comparison_id=payload.get("comparison_id"),
            artifact_path=payload.get("report_path"),
            result=payload,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare deliberation campaign benchmark matrix exports: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_failed",
            export_ids=export_ids or [],
            latest=latest,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix export comparison artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
            comparison_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix export comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_read_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix export comparison artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts(
            limit=limit,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix export comparison artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_list_failed",
            limit=limit,
        )


@mcp.tool(structured_output=True)
def audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a persisted deliberation campaign benchmark matrix export comparison artifact."""
    try:
        return _audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
            comparison_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to audit deliberation campaign benchmark matrix export comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_audit_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def export_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
    comparison_id: str,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Export a persisted deliberation campaign benchmark matrix export comparison artifact."""
    try:
        return _export_deliberation_campaign_benchmark_matrix_export_comparison_artifact(
            comparison_id,
            comparison_output_dir=comparison_output_dir,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to export deliberation campaign benchmark matrix export comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_export_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact(
    export_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix export comparison export artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact(
            export_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix export comparison export artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_export_read_failed",
            export_id=export_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix export comparison export artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts(
            limit=limit,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix export comparison export artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_comparison_export_list_failed",
            limit=limit,
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix comparison artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_comparison_artifact(
            comparison_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_artifact_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix comparison artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_comparison_artifacts(
            limit=limit,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix comparison artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_listing_failed",
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_benchmark_matrix_comparison_export_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Read a persisted deliberation campaign benchmark matrix comparison export artifact."""
    try:
        return _read_deliberation_campaign_benchmark_matrix_comparison_export_artifact(
            comparison_id,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign benchmark matrix comparison export artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_export_artifact_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign benchmark matrix comparison export artifacts."""
    try:
        return _list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts(
            limit=limit,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign benchmark matrix comparison export artifacts: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_export_listing_failed",
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_comparison_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign comparison artifacts."""
    try:
        return _list_deliberation_campaign_comparison_artifacts(limit=limit, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign comparison artifacts: {exc}",
            error_code="deliberation_campaign_comparison_listing_failed",
        )


@mcp.tool(structured_output=True)
def read_deliberation_campaign_comparison_export_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Read a persisted deliberation campaign comparison export artifact."""
    try:
        return _read_deliberation_campaign_comparison_export_artifact(
            comparison_id,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to read deliberation campaign comparison export artifact: {exc}",
            error_code="deliberation_campaign_comparison_export_artifact_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def list_deliberation_campaign_comparison_export_artifacts(
    limit: int = 20,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """List persisted deliberation campaign comparison export artifacts."""
    try:
        return _list_deliberation_campaign_comparison_export_artifacts(limit=limit, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation campaign comparison export artifacts: {exc}",
            error_code="deliberation_campaign_comparison_export_listing_failed",
        )


@mcp.tool(structured_output=True)
def audit_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a persisted deliberation campaign comparison artifact."""
    try:
        return _audit_deliberation_campaign_comparison_artifact(comparison_id, output_dir=output_dir)
    except Exception as exc:
        return _failure(
            f"Failed to audit deliberation campaign comparison artifact: {exc}",
            error_code="deliberation_campaign_comparison_audit_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def export_deliberation_campaign_comparison_artifact(
    comparison_id: str,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Export a persisted deliberation campaign comparison artifact as markdown or JSON."""
    try:
        return _export_deliberation_campaign_comparison_artifact(
            comparison_id,
            comparison_output_dir=comparison_output_dir,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to export deliberation campaign comparison artifact: {exc}",
            error_code="deliberation_campaign_comparison_export_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def compare_deliberation_campaigns(
    baseline_campaign_id: str,
    candidate_campaign_id: str,
) -> dict[str, Any]:
    """Compare two persisted deliberation campaign artifacts."""
    try:
        return _compare_deliberation_campaign_artifacts(
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare deliberation campaigns: {exc}",
            error_code="deliberation_campaign_comparison_failed",
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
        )


@mcp.tool(structured_output=True)
def compare_deliberation_campaign_benchmark_matrices(
    baseline_matrix_id: str | None = None,
    candidate_matrix_id: str | None = None,
    latest: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare two persisted deliberation campaign benchmark matrix artifacts."""
    try:
        return _compare_deliberation_campaign_benchmark_matrix_artifacts(
            baseline_matrix_id=baseline_matrix_id,
            candidate_matrix_id=candidate_matrix_id,
            latest=latest,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare deliberation campaign benchmark matrices: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_failed",
            baseline_matrix_id=baseline_matrix_id,
            candidate_matrix_id=candidate_matrix_id,
            latest=latest,
        )


@mcp.tool(structured_output=True)
def audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a persisted deliberation campaign benchmark matrix comparison artifact."""
    try:
        return _audit_deliberation_campaign_benchmark_matrix_comparison_artifact(
            comparison_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to audit deliberation campaign benchmark matrix comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_audit_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def export_deliberation_campaign_benchmark_matrix_comparison_artifact(
    comparison_id: str,
    comparison_output_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Export a persisted deliberation campaign benchmark matrix comparison artifact."""
    try:
        return _export_deliberation_campaign_benchmark_matrix_comparison_artifact(
            comparison_id,
            comparison_output_dir=comparison_output_dir,
            output_dir=output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to export deliberation campaign benchmark matrix comparison artifact: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_comparison_export_failed",
            comparison_id=comparison_id,
        )


@mcp.tool(structured_output=True)
def compare_audit_export_deliberation_campaign_benchmark_matrix_exports(
    export_ids: list[str] | None = None,
    latest: int | None = None,
    format: str = "markdown",
    output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare matrix benchmark exports, audit the comparison, and materialize an export."""
    try:
        bundle = core_compare_deliberation_campaign_matrix_benchmark_export_comparison_bundle(
            export_ids=export_ids,
            latest=latest,
            output_dir=output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR,
            persist=True,
            comparison_output_dir=(
                comparison_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_OUTPUT_DIR
            ),
            export_output_dir=(
                export_output_dir
                or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_COMPARISON_EXPORT_OUTPUT_DIR
            ),
            format=format,
        )
        payload = bundle.model_dump(mode="json") if hasattr(bundle, "model_dump") else dict(bundle)
        return _success(
            comparison_id=payload.get("comparison_report", {}).get("comparison_id"),
            export_id=payload.get("export", {}).get("export_id"),
            result=payload,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare, audit, and export deliberation campaign benchmark matrix exports: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_export_compare_audit_export_failed",
            export_ids=export_ids or [],
            latest=latest,
        )


@mcp.tool(structured_output=True)
def compare_audit_export_deliberation_campaign_benchmark_matrices(
    baseline_matrix_id: str | None = None,
    candidate_matrix_id: str | None = None,
    latest: bool = False,
    format: str = "markdown",
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare two benchmark matrices, audit the comparison, and materialize an export."""
    try:
        return _compare_audit_export_deliberation_campaign_benchmark_matrices(
            baseline_matrix_id=baseline_matrix_id,
            candidate_matrix_id=candidate_matrix_id,
            latest=latest,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare, audit, and export deliberation campaign benchmark matrices: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_compare_audit_export_failed",
            baseline_matrix_id=baseline_matrix_id,
            candidate_matrix_id=candidate_matrix_id,
            latest=latest,
        )


@mcp.tool(structured_output=True)
def compare_audit_export_deliberation_campaigns(
    baseline_campaign_id: str,
    candidate_campaign_id: str,
    format: str = "markdown",
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare two persisted campaigns, audit the comparison, and materialize an export."""
    try:
        return _compare_audit_export_deliberation_campaign_artifacts(
            baseline_campaign_id,
            candidate_campaign_id,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to compare, audit, and export deliberation campaigns: {exc}",
            error_code="deliberation_campaign_compare_audit_export_failed",
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
        )


@mcp.tool(structured_output=True)
def benchmark_deliberation_campaigns(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    config_path: str = "config.yaml",
    baseline_runtime: str = RuntimeBackend.pydanticai.value,
    candidate_runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    baseline_engine_preference: str = "agentsociety",
    candidate_engine_preference: str = "agentsociety",
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    sample_count: int = 3,
    backend_mode: str | None = None,
    baseline_campaign_id: str | None = None,
    candidate_campaign_id: str | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Run baseline and candidate campaigns, then compare, audit, and export them in one shot."""
    try:
        return _benchmark_deliberation_campaign_artifacts(
            topic=topic,
            objective=objective,
            mode=mode,
            participants=participants,
            documents=documents,
            entities=entities,
            interventions=interventions,
            max_agents=max_agents,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            persist=persist,
            campaign_output_dir=campaign_output_dir,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            config_path=config_path,
            baseline_runtime=baseline_runtime,
            candidate_runtime=candidate_runtime,
            allow_fallback=allow_fallback,
            baseline_engine_preference=baseline_engine_preference,
            candidate_engine_preference=candidate_engine_preference,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
            benchmark_path=benchmark_path,
            stability_runs=stability_runs,
            sample_count=sample_count,
            backend_mode=backend_mode,
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
            benchmark_output_dir=benchmark_output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to benchmark deliberation campaigns: {exc}",
            error_code="deliberation_campaign_benchmark_failed",
            topic=topic,
            mode=mode,
            baseline_runtime=baseline_runtime,
            candidate_runtime=candidate_runtime,
        )


@mcp.tool(structured_output=True)
def benchmark_deliberation_campaign_matrix(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    config_path: str = "config.yaml",
    baseline_runtime: str = RuntimeBackend.pydanticai.value,
    baseline_engine_preference: str = "agentsociety",
    candidate_runtime: str = RuntimeBackend.pydanticai.value,
    candidate_engine_preference: str = "agentsociety",
    candidate_runtimes: list[str] | None = None,
    candidate_engine_preferences: list[str] | None = None,
    allow_fallback: bool = True,
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    sample_count: int = 3,
    backend_mode: str | None = None,
    baseline_campaign_id: str | None = None,
    matrix_id: str | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    """Run a baseline against a matrix of candidate runtimes and engines, then persist the bundle."""
    try:
        return _benchmark_deliberation_campaign_matrix_artifacts(
            topic=topic,
            objective=objective,
            mode=mode,
            participants=participants,
            documents=documents,
            entities=entities,
            interventions=interventions,
            max_agents=max_agents,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            persist=persist,
            campaign_output_dir=campaign_output_dir,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            config_path=config_path,
            baseline_runtime=baseline_runtime,
            baseline_engine_preference=baseline_engine_preference,
            candidate_runtime=candidate_runtime,
            candidate_engine_preference=candidate_engine_preference,
            candidate_runtimes=candidate_runtimes,
            candidate_engine_preferences=candidate_engine_preferences,
            allow_fallback=allow_fallback,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
            benchmark_path=benchmark_path,
            stability_runs=stability_runs,
            sample_count=sample_count,
            backend_mode=backend_mode,
            baseline_campaign_id=baseline_campaign_id,
            matrix_id=matrix_id,
            benchmark_output_dir=benchmark_output_dir,
            format=format,
        )
    except Exception as exc:
        return _failure(
            f"Failed to benchmark deliberation campaign matrix: {exc}",
            error_code="deliberation_campaign_benchmark_matrix_failed",
            topic=topic,
            mode=mode,
            baseline_runtime=baseline_runtime,
            candidate_runtime=candidate_runtime,
        )


def _benchmark_deliberation_campaign_matrix_artifacts(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    config_path: str = "config.yaml",
    baseline_runtime: str = RuntimeBackend.pydanticai.value,
    baseline_engine_preference: str = "agentsociety",
    candidate_runtime: str = RuntimeBackend.pydanticai.value,
    candidate_engine_preference: str = "agentsociety",
    candidate_runtimes: list[str] | None = None,
    candidate_engine_preferences: list[str] | None = None,
    allow_fallback: bool = True,
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    sample_count: int = 3,
    backend_mode: str | None = None,
    baseline_campaign_id: str | None = None,
    matrix_id: str | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="comparison_export_format_unsupported",
            format=format,
        )
    if not persist:
        return _failure(
            "The benchmark matrix workflow requires persist=True so each cell can be revisited later.",
            error_code="deliberation_campaign_benchmark_matrix_requires_persistence",
            topic=topic,
            mode=mode,
            persist=persist,
        )

    baseline_campaign_id = baseline_campaign_id or None
    matrix_id = str(matrix_id).strip() if matrix_id is not None else ""
    if not matrix_id:
        matrix_id = f"campaign_benchmark_matrix_{uuid.uuid4().hex[:12]}"
    resolved_benchmark_output_dir = benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR
    candidate_runtime_values = [str(value).strip() for value in (candidate_runtimes or [candidate_runtime]) if str(value).strip()]
    candidate_engine_values = [
        str(value).strip()
        for value in (candidate_engine_preferences or [candidate_engine_preference])
        if str(value).strip()
    ]
    if not candidate_runtime_values:
        candidate_runtime_values = [str(candidate_runtime).strip() or RuntimeBackend.pydanticai.value]
    if not candidate_engine_values:
        candidate_engine_values = [str(candidate_engine_preference).strip() or "agentsociety"]

    candidate_specs: list[DeliberationCampaignMatrixCandidateSpec] = []
    for runtime_value in candidate_runtime_values:
        for engine_value in candidate_engine_values:
            candidate_specs.append(
                DeliberationCampaignMatrixCandidateSpec(
                    label=f"{runtime_value}__{engine_value}",
                    campaign_id=f"{matrix_id}__candidate__{runtime_value}__{engine_value}",
                    runtime=runtime_value,
                    engine_preference=engine_value,
                )
            )

    matrix_result = run_deliberation_campaign_matrix_benchmark_sync(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        sample_count=sample_count,
        stability_runs=stability_runs,
        baseline_runtime=baseline_runtime,
        baseline_engine_preference=baseline_engine_preference,
        candidate_specs=candidate_specs,
        allow_fallback=allow_fallback,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        config_path=config_path,
        backend_mode=backend_mode,
        persist=persist,
        output_dir=campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR,
        comparison_output_dir=comparison_output_dir,
        export_output_dir=export_output_dir,
        benchmark_output_dir=resolved_benchmark_output_dir,
        format=normalized_format,
        benchmark_id=matrix_id,
        baseline_campaign_id=baseline_campaign_id,
        client=None,
        runner=None,
    )
    matrix_payload = _benchmark_matrix_report_payload(matrix_result)
    return _success(
        matrix_id=matrix_payload.get("matrix_id"),
        created_at=matrix_payload.get("created_at"),
        output_dir=matrix_payload.get("output_dir"),
        report_path=matrix_payload.get("report_path"),
        baseline_campaign_id=matrix_payload.get("baseline_campaign_id"),
        baseline_runtime=str(baseline_runtime).strip(),
        baseline_engine_preference=str(baseline_engine_preference).strip(),
        candidate_runtimes=candidate_runtime_values,
        candidate_engine_preferences=candidate_engine_values,
        cell_count=matrix_payload.get("cell_count", 0),
        benchmark_ids=matrix_payload.get("benchmark_ids", []),
        comparison_ids=matrix_payload.get("comparison_ids", []),
        candidate_campaign_ids=matrix_payload.get("candidate_campaign_ids", []),
        cells=matrix_payload.get("cells", []),
        summary=matrix_payload.get("summary", {}),
        result=matrix_payload,
    )


def _benchmark_deliberation_campaign_artifacts(
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    campaign_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
    config_path: str = "config.yaml",
    baseline_runtime: str = RuntimeBackend.pydanticai.value,
    candidate_runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    baseline_engine_preference: str = "agentsociety",
    candidate_engine_preference: str = "agentsociety",
    ensemble_engines: list[str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str = str(DEFAULT_DELIBERATION_BENCHMARK_SUITE_PATH),
    stability_runs: int = 1,
    sample_count: int = 3,
    backend_mode: str | None = None,
    baseline_campaign_id: str | None = None,
    candidate_campaign_id: str | None = None,
    benchmark_output_dir: str | Path | None = None,
    format: str = "markdown",
) -> dict[str, Any]:
    normalized_format = "markdown" if format is None else str(format).strip().lower() or "markdown"
    if normalized_format not in {"markdown", "json"}:
        return _failure(
            f"Unsupported export format: {format!r}",
            error_code="comparison_export_format_unsupported",
            format=format,
        )
    if not persist:
        return _failure(
            "The benchmark workflow requires persist=True so campaigns can be compared and exported.",
            error_code="deliberation_campaign_benchmark_requires_persistence",
            topic=topic,
            mode=mode,
            persist=persist,
        )

    resolved_output_dir = campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR
    resolved_benchmark_output_dir = benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR
    try:
        benchmark_result = run_deliberation_campaign_benchmark_sync(
            topic=topic,
            objective=objective,
            mode=mode,
            participants=participants,
            documents=documents,
            entities=entities,
            interventions=interventions,
            max_agents=max_agents,
            population_size=population_size,
            rounds=rounds,
            time_horizon=time_horizon,
            sample_count=sample_count,
            stability_runs=stability_runs,
            baseline_runtime=baseline_runtime,
            candidate_runtime=candidate_runtime,
            allow_fallback=allow_fallback,
            baseline_engine_preference=baseline_engine_preference,
            candidate_engine_preference=candidate_engine_preference,
            ensemble_engines=ensemble_engines,
            budget_max=budget_max,
            timeout_seconds=timeout_seconds,
            benchmark_path=benchmark_path,
            config_path=config_path,
            backend_mode=backend_mode,
            persist=persist,
            output_dir=resolved_output_dir,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
            format=normalized_format,
            baseline_campaign_id=baseline_campaign_id,
            candidate_campaign_id=candidate_campaign_id,
            client=None,
            runner=run_deliberation_runtime,
        )
        bundle_payload = (
            benchmark_result.model_dump(mode="json")
            if hasattr(benchmark_result, "model_dump")
            else dict(benchmark_result)
        )
        benchmark_id = str(
            bundle_payload.get("benchmark_id")
            or f"{bundle_payload.get('baseline_campaign_id')}__vs__{bundle_payload.get('candidate_campaign_id')}"
        )
        benchmark_dir = _benchmark_report_dir(benchmark_id, output_dir=resolved_benchmark_output_dir)
        benchmark_dir.mkdir(parents=True, exist_ok=True)
        benchmark_report_path = _benchmark_report_path(benchmark_id, output_dir=resolved_benchmark_output_dir)
        benchmark_payload = {
            **bundle_payload,
            "benchmark_id": benchmark_id,
            "created_at": bundle_payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "output_dir": str(Path(resolved_benchmark_output_dir)),
            "report_path": str(benchmark_report_path),
        }
        benchmark_report_path.write_text(json.dumps(benchmark_payload, indent=2, sort_keys=True), encoding="utf-8")
        comparison_payload = benchmark_payload.get("comparison", {})
        audit_payload = benchmark_payload.get("audit", {})
        export_payload = benchmark_payload.get("export", {})
        return _success(
            benchmark_id=benchmark_id,
            baseline_campaign_id=benchmark_payload.get("baseline_campaign_id"),
            candidate_campaign_id=benchmark_payload.get("candidate_campaign_id"),
            baseline_campaign=benchmark_payload.get("baseline_campaign"),
            candidate_campaign=benchmark_payload.get("candidate_campaign"),
            comparison_id=comparison_payload.get("comparison_id"),
            comparison=comparison_payload,
            audit=audit_payload,
            export=export_payload,
            export_id=export_payload.get("export_id"),
            comparison_report_path=comparison_payload.get("report_path"),
            audit_report_path=audit_payload.get("report_path"),
            export_manifest_path=export_payload.get("manifest_path"),
            export_content_path=export_payload.get("content_path"),
            benchmark_report_path=str(benchmark_report_path),
            benchmark_artifact_path=str(benchmark_report_path),
            result=benchmark_payload,
        )
    except Exception as exc:
        return _failure(
            f"Failed to benchmark deliberation campaigns: {exc}",
            error_code="deliberation_campaign_benchmark_failed",
            topic=topic,
            mode=mode,
            baseline_runtime=baseline_runtime,
            candidate_runtime=candidate_runtime,
        )


@mcp.tool(structured_output=True)
def deliberation_campaign_index(
    limit: int = 20,
    campaign_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize persisted deliberation campaigns, benchmarks, comparisons, and exports."""
    try:
        return _deliberation_campaign_artifact_index(
            limit=limit,
            campaign_output_dir=campaign_output_dir,
            benchmark_output_dir=benchmark_output_dir,
            matrix_benchmark_output_dir=matrix_benchmark_output_dir,
            matrix_benchmark_export_output_dir=matrix_benchmark_export_output_dir,
            matrix_benchmark_comparison_output_dir=matrix_benchmark_comparison_output_dir,
            matrix_benchmark_comparison_export_output_dir=matrix_benchmark_comparison_export_output_dir,
            comparison_output_dir=comparison_output_dir,
            export_output_dir=export_output_dir,
        )
    except Exception as exc:
        return _failure(
            f"Failed to build deliberation campaign index: {exc}",
            error_code="deliberation_campaign_index_failed",
        )


@mcp.tool(structured_output=True)
def deliberation_campaign_dashboard(
    kinds: list[str] | None = None,
    limit: int | None = 20,
    sort_by: str = "created_at",
    campaign_status: str | None = None,
    comparable_only: bool = False,
    campaign_output_dir: str | Path | None = None,
    benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_output_dir: str | Path | None = None,
    matrix_benchmark_export_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_output_dir: str | Path | None = None,
    matrix_benchmark_comparison_export_output_dir: str | Path | None = None,
    comparison_output_dir: str | Path | None = None,
    export_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a filtered dashboard over persisted deliberation campaign artifacts."""
    try:
        helper_kwargs: dict[str, Any] = {
            "campaign_output_dir": campaign_output_dir,
            "comparison_output_dir": comparison_output_dir,
            "export_output_dir": export_output_dir,
            "benchmark_output_dir": benchmark_output_dir,
            "kinds": kinds,
            "limit": limit,
            "sort_by": sort_by,
            "campaign_status": campaign_status,
            "comparable_only": comparable_only,
        }
        if matrix_benchmark_output_dir is not None:
            helper_kwargs["matrix_benchmark_output_dir"] = matrix_benchmark_output_dir
        if matrix_benchmark_export_output_dir is not None:
            helper_kwargs["matrix_benchmark_export_output_dir"] = matrix_benchmark_export_output_dir
        if matrix_benchmark_comparison_output_dir is not None:
            helper_kwargs["matrix_benchmark_comparison_output_dir"] = (
                matrix_benchmark_comparison_output_dir
            )
        if matrix_benchmark_comparison_export_output_dir is not None:
            helper_kwargs["matrix_benchmark_comparison_export_output_dir"] = (
                matrix_benchmark_comparison_export_output_dir
            )
        dashboard = build_deliberation_campaign_dashboard(
            **helper_kwargs,
        )
        payload = dashboard.model_dump(mode="json") if hasattr(dashboard, "model_dump") else dict(dashboard)
        output_dirs = {
            "campaigns": str(Path(campaign_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_OUTPUT_DIR)),
            "benchmarks": str(Path(benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_OUTPUT_DIR)),
            "matrix_benchmarks": str(
                Path(matrix_benchmark_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_OUTPUT_DIR)
            ),
            "matrix_benchmark_exports": str(
                Path(
                    matrix_benchmark_export_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_EXPORT_OUTPUT_DIR
                )
            ),
            "matrix_benchmark_comparisons": str(
                Path(
                    matrix_benchmark_comparison_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_OUTPUT_DIR
                )
            ),
            "matrix_benchmark_comparison_exports": str(
                Path(
                    matrix_benchmark_comparison_export_output_dir
                    or DEFAULT_DELIBERATION_CAMPAIGN_BENCHMARK_MATRIX_COMPARISON_EXPORT_OUTPUT_DIR
                )
            ),
            "comparisons": str(Path(comparison_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_OUTPUT_DIR)),
            "exports": str(Path(export_output_dir or DEFAULT_DELIBERATION_CAMPAIGN_COMPARISON_EXPORT_OUTPUT_DIR)),
        }
        payload["output_dirs"] = output_dirs
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata["output_dirs"] = output_dirs
        else:
            payload["metadata"] = {"output_dirs": output_dirs}
        return _success(**payload)
    except Exception as exc:
        return _failure(
            f"Failed to build deliberation campaign dashboard: {exc}",
            error_code="deliberation_campaign_dashboard_failed",
        )


@mcp.tool(structured_output=True)
def list_deliberation_targets(deliberation_id: str) -> dict[str, Any]:
    """List interviewable targets for a persisted deliberation."""
    try:
        return _list_deliberation_targets(deliberation_id)
    except Exception as exc:
        return _failure(
            f"Failed to list deliberation targets: {exc}",
            error_code="deliberation_targets_failed",
            deliberation_id=deliberation_id,
        )


@mcp.tool(structured_output=True)
def interview_deliberation(
    deliberation_id: str,
    question: str,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Interview a persisted deliberation at overview, group, or agent level."""
    try:
        return _interview_deliberation(deliberation_id, question=question, target_id=target_id)
    except Exception as exc:
        return _failure(
            f"Failed to interview deliberation: {exc}",
            error_code="deliberation_interview_failed",
            deliberation_id=deliberation_id,
            target_id=target_id,
        )


@mcp.tool(structured_output=True)
def persona_chat_deliberation(
    deliberation_id: str,
    question: str,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Start a bounded persona-chat session on a persisted deliberation target."""
    try:
        return _persona_chat_deliberation(deliberation_id, question=question, target_id=target_id)
    except Exception as exc:
        return _failure(
            f"Failed to start persona chat: {exc}",
            error_code="deliberation_persona_chat_failed",
            deliberation_id=deliberation_id,
            target_id=target_id,
        )


@mcp.tool(structured_output=True)
def export_deliberation_neo4j(deliberation_id: str) -> dict[str, Any]:
    """Export a persisted deliberation graph as a Neo4j-friendly query bundle."""
    try:
        return _export_deliberation_neo4j(deliberation_id)
    except Exception as exc:
        return _failure(
            f"Failed to export deliberation graph: {exc}",
            error_code="deliberation_neo4j_export_failed",
            deliberation_id=deliberation_id,
        )


@mcp.tool(structured_output=True)
def bridge_deliberation_market(deliberation_id: str) -> dict[str, Any]:
    """Build a bounded social-to-market bridge report from a persisted deliberation."""
    try:
        return _bridge_deliberation_market(deliberation_id)
    except Exception as exc:
        return _failure(
            f"Failed to bridge deliberation to market view: {exc}",
            error_code="deliberation_market_bridge_failed",
            deliberation_id=deliberation_id,
        )


@mcp.tool(structured_output=True)
def replay_deliberation(
    deliberation_id: str,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Replay a persisted deliberation manifest and optionally persist the replay."""
    try:
        result = replay_deliberation_sync(
            deliberation_id,
            persist=persist,
            backend_mode=backend_mode,
        )
        return _success(
            result=result.model_dump(mode="json"),
            runtime_requested=result.runtime_requested,
            runtime_used=result.runtime_used,
            fallback_used=result.fallback_used,
            engine_requested=result.engine_requested,
            engine_used=result.engine_used,
        )
    except Exception as exc:
        return _failure(
            f"Failed to replay deliberation: {exc}",
            error_code="deliberation_replay_failed",
            deliberation_id=deliberation_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_advise(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run the prediction markets advisor for one market."""
    try:
        return _prediction_markets_advise(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to advise prediction market: {exc}",
            error_code="prediction_markets_advise_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_paper(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run the paper-trading variant of the prediction markets advisor."""
    try:
        return _prediction_markets_paper(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to paper trade prediction market: {exc}",
            error_code="prediction_markets_paper_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_risk(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Evaluate market risk and the derived allocation envelope for one market."""
    try:
        return _prediction_markets_risk(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to score prediction market risk: {exc}",
            error_code="prediction_markets_risk_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_allocate(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run the portfolio allocator on one market using the advisory pipeline."""
    try:
        return _prediction_markets_allocate(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to allocate prediction market position: {exc}",
            error_code="prediction_markets_allocate_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_shadow(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run a bounded shadow execution pass against the paper-trading path."""
    try:
        return _prediction_markets_shadow(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to shadow execute prediction market recommendation: {exc}",
            error_code="prediction_markets_shadow_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_live(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
    principal: str = "",
    scopes: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run a bounded live-execution control path, dry-run by default."""
    try:
        return _prediction_markets_live(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            dry_run=dry_run,
            allow_live_execution=allow_live_execution,
            authorized=authorized,
            compliance_approved=compliance_approved,
            require_human_approval_before_live=require_human_approval_before_live,
            human_approval_passed=human_approval_passed,
            human_approval_actor=human_approval_actor,
            human_approval_reason=human_approval_reason,
            principal=principal,
            scopes=scopes,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to run live prediction market control path: {exc}",
            error_code="prediction_markets_live_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_market_execution(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    decision_packet: dict[str, Any] | None = None,
    deliberation_id: str | None = None,
    stake: float = 10.0,
    dry_run: bool = True,
    allow_live_execution: bool = False,
    authorized: bool = False,
    compliance_approved: bool = False,
    require_human_approval_before_live: bool = False,
    human_approval_passed: bool = False,
    human_approval_actor: str = "",
    human_approval_reason: str = "",
    principal: str = "",
    scopes: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Materialize a bounded market-execution audit path, dry-run by default."""
    try:
        return _prediction_markets_market_execution(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            decision_packet=decision_packet,
            deliberation_id=deliberation_id,
            stake=stake,
            dry_run=dry_run,
            allow_live_execution=allow_live_execution,
            authorized=authorized,
            compliance_approved=compliance_approved,
            require_human_approval_before_live=require_human_approval_before_live,
            human_approval_passed=human_approval_passed,
            human_approval_actor=human_approval_actor,
            human_approval_reason=human_approval_reason,
            principal=principal,
            scopes=scopes,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to materialize prediction market execution audit: {exc}",
            error_code="prediction_markets_market_execution_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_research(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Normalize evidence notes into research findings and a research synthesis for one market."""
    try:
        return _prediction_markets_research(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to synthesize prediction market research: {exc}",
            error_code="prediction_markets_research_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_multi_venue_paper(
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    target_notional_usd: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Simulate multi-venue paper execution legs without touching real capital."""
    try:
        return _prediction_markets_multi_venue_paper(
            market_id=market_id,
            slug=slug,
            limit=limit,
            include_additional_venues=include_additional_venues,
            target_notional_usd=target_notional_usd,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to simulate multi-venue paper execution: {exc}",
            error_code="prediction_markets_multi_venue_paper_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_slippage(
    market_id: str | None = None,
    slug: str | None = None,
    position_side: str = "yes",
    execution_side: str = "buy",
    requested_quantity: float | None = None,
    requested_notional: float | None = None,
    limit_price: float | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Estimate orderbook slippage and liquidity for one market request."""
    try:
        return _prediction_markets_slippage(
            market_id=market_id,
            slug=slug,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            requested_notional=requested_notional,
            limit_price=limit_price,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to estimate prediction market slippage: {exc}",
            error_code="prediction_markets_slippage_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_microstructure(
    market_id: str | None = None,
    slug: str | None = None,
    position_side: str = "yes",
    execution_side: str = "buy",
    requested_quantity: float = 1.0,
    capital_available_usd: float | None = None,
    capital_locked_usd: float = 0.0,
    queue_ahead_quantity: float = 0.0,
    spread_collapse_threshold_bps: float = 50.0,
    collapse_liquidity_multiplier: float = 0.35,
    limit_price: float | None = None,
    fee_bps: float = 0.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Simulate microstructure fills and surface the postmortem summary."""
    try:
        return _prediction_markets_microstructure(
            market_id=market_id,
            slug=slug,
            position_side=position_side,
            execution_side=execution_side,
            requested_quantity=requested_quantity,
            capital_available_usd=capital_available_usd,
            capital_locked_usd=capital_locked_usd,
            queue_ahead_quantity=queue_ahead_quantity,
            spread_collapse_threshold_bps=spread_collapse_threshold_bps,
            collapse_liquidity_multiplier=collapse_liquidity_multiplier,
            limit_price=limit_price,
            fee_bps=fee_bps,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to simulate prediction market microstructure: {exc}",
            error_code="prediction_markets_microstructure_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_comment_intel(
    market_id: str | None = None,
    slug: str | None = None,
    comments: list[str] | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Summarize comment and narrative signals for one market."""
    try:
        return _prediction_markets_comment_intel(
            market_id=market_id,
            slug=slug,
            comments=comments,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to summarize prediction market comments: {exc}",
            error_code="prediction_markets_comment_intel_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_manipulation_guard(
    market_id: str | None = None,
    slug: str | None = None,
    evidence: list[str] | None = None,
    comments: list[str] | None = None,
    poll_count: int = 0,
    stale_after_seconds: float = 3600.0,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Evaluate whether the current market context should remain signal-only or is safe enough to trade."""
    try:
        return _prediction_markets_manipulation_guard(
            market_id=market_id,
            slug=slug,
            evidence=evidence,
            comments=comments,
            poll_count=poll_count,
            stale_after_seconds=stale_after_seconds,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to evaluate prediction market manipulation guard: {exc}",
            error_code="prediction_markets_manipulation_guard_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_graph(
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Build a normalized market graph around one market."""
    try:
        return _prediction_markets_graph(
            market_id=market_id,
            slug=slug,
            limit=limit,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to build prediction market graph: {exc}",
            error_code="prediction_markets_graph_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_cross_venue(
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Build a cross-venue intelligence report from the normalized market pool."""
    try:
        return _prediction_markets_cross_venue(
            market_id=market_id,
            slug=slug,
            limit=limit,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to build cross-venue intelligence: {exc}",
            error_code="prediction_markets_cross_venue_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_spread_monitor(
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Monitor cross-venue spreads and classify them by executability."""
    try:
        return _prediction_markets_spread_monitor(
            market_id=market_id,
            slug=slug,
            limit=limit,
            include_additional_venues=include_additional_venues,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to monitor prediction market spreads: {exc}",
            error_code="prediction_markets_spread_monitor_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_arbitrage_lab(
    market_id: str | None = None,
    slug: str | None = None,
    limit: int = 12,
    include_additional_venues: bool = True,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Assess multi-venue opportunities without placing live orders."""
    try:
        return _prediction_markets_arbitrage_lab(
            market_id=market_id,
            slug=slug,
            limit=limit,
            include_additional_venues=include_additional_venues,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to assess prediction market arbitrage lab: {exc}",
            error_code="prediction_markets_arbitrage_lab_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_stream_open(
    market_id: str | None = None,
    slug: str | None = None,
    poll_count: int = 1,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Open a bounded market stream and immediately return its first summary + health report."""
    try:
        return _prediction_markets_stream_open(
            market_id=market_id,
            slug=slug,
            poll_count=poll_count,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to open prediction market stream: {exc}",
            error_code="prediction_markets_stream_open_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_stream_summary(
    stream_id: str,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Summarize one persisted market stream."""
    try:
        return _prediction_markets_stream_summary(stream_id, backend_mode=backend_mode)
    except Exception as exc:
        return _failure(
            f"Failed to summarize prediction market stream: {exc}",
            error_code="prediction_markets_stream_summary_failed",
            stream_id=stream_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_stream_health(
    stream_id: str,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Inspect the health of one persisted market stream."""
    try:
        return _prediction_markets_stream_health(
            stream_id,
            stale_after_seconds=stale_after_seconds,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to inspect prediction market stream health: {exc}",
            error_code="prediction_markets_stream_health_failed",
            stream_id=stream_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_stream_collect(
    market_ids: list[str] | None = None,
    slugs: list[str] | None = None,
    stream_ids: list[str] | None = None,
    fanout: int = 4,
    retries: int = 1,
    timeout_seconds: float = 5.0,
    cache_ttl_seconds: float = 60.0,
    prefetch: bool = True,
    backpressure_limit: int = 32,
    priority_strategy: str = "freshness",
    poll_count: int = 1,
    stale_after_seconds: float = 3600.0,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Collect multiple market streams with cache, retries, fanout, and prioritization."""
    try:
        return _prediction_markets_stream_collect(
            market_ids=market_ids,
            slugs=slugs,
            stream_ids=stream_ids,
            fanout=fanout,
            retries=retries,
            timeout_seconds=timeout_seconds,
            cache_ttl_seconds=cache_ttl_seconds,
            prefetch=prefetch,
            backpressure_limit=backpressure_limit,
            priority_strategy=priority_strategy,
            poll_count=poll_count,
            stale_after_seconds=stale_after_seconds,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to collect prediction market streams: {exc}",
            error_code="prediction_markets_stream_collect_failed",
            market_ids=market_ids or [],
            slugs=slugs or [],
            stream_ids=stream_ids or [],
        )


@mcp.tool(structured_output=True)
def prediction_markets_worldmonitor(
    source: str,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Ingest a worldmonitor sidecar payload into research/evidence packets."""
    try:
        return _prediction_markets_worldmonitor(
            source,
            market_id=market_id,
            slug=slug,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to ingest worldmonitor sidecar payload: {exc}",
            error_code="prediction_markets_worldmonitor_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_twitter_watcher(
    source: str,
    market_id: str | None = None,
    slug: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Ingest a twitter_watcher sidecar payload into research/evidence packets."""
    try:
        return _prediction_markets_twitter_watcher(
            source,
            market_id=market_id,
            slug=slug,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to ingest twitter_watcher sidecar payload: {exc}",
            error_code="prediction_markets_twitter_watcher_failed",
            market_id=market_id,
            slug=slug,
        )


@mcp.tool(structured_output=True)
def prediction_markets_venues(
    query: str | None = None,
    limit_per_venue: int = 2,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Inspect the bootstrap multi-venue catalog and capability matrix."""
    try:
        return _prediction_markets_venues(
            query=query,
            limit_per_venue=limit_per_venue,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to inspect prediction market venue catalog: {exc}",
            error_code="prediction_markets_venues_failed",
        )


@mcp.tool(structured_output=True)
def prediction_markets_events(
    market_id: str | None = None,
    slug: str | None = None,
    venue: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """List related event descriptors for one market."""
    try:
        return _prediction_markets_events(
            market_id=market_id,
            slug=slug,
            venue=venue,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to list prediction market events: {exc}",
            error_code="prediction_markets_events_failed",
            market_id=market_id,
            slug=slug,
            venue=venue,
        )


@mcp.tool(structured_output=True)
def prediction_markets_positions(
    market_id: str | None = None,
    slug: str | None = None,
    venue: str | None = None,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Inspect persisted or cached positions for one market."""
    try:
        return _prediction_markets_positions(
            market_id=market_id,
            slug=slug,
            venue=venue,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to inspect prediction market positions: {exc}",
            error_code="prediction_markets_positions_failed",
            market_id=market_id,
            slug=slug,
            venue=venue,
        )


@mcp.tool(structured_output=True)
def prediction_markets_replay(run_id: str) -> dict[str, Any]:
    """Replay one persisted prediction markets run."""
    try:
        return _prediction_markets_replay(run_id)
    except Exception as exc:
        return _failure(
            f"Failed to replay prediction market run: {exc}",
            error_code="prediction_markets_replay_failed",
            run_id=run_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_replay_postmortem(run_id: str) -> dict[str, Any]:
    """Summarize one persisted prediction markets replay deterministically."""
    try:
        return _prediction_markets_replay_postmortem(run_id)
    except Exception as exc:
        return _failure(
            f"Failed to summarize prediction market replay postmortem: {exc}",
            error_code="prediction_markets_replay_postmortem_failed",
            run_id=run_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_reconcile(
    run_id: str,
    persist: bool = True,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Reconcile persisted paper, shadow, and ledger artifacts for one run."""
    try:
        return _prediction_markets_reconcile(
            run_id,
            persist=persist,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to reconcile prediction market run: {exc}",
            error_code="prediction_markets_reconcile_failed",
            run_id=run_id,
        )


@mcp.tool(structured_output=True)
def prediction_markets_runs(limit: int = 20) -> dict[str, Any]:
    """List recent persisted prediction markets runs."""
    try:
        return _prediction_markets_runs(limit=limit)
    except Exception as exc:
        return _failure(
            f"Failed to list prediction market runs: {exc}",
            error_code="prediction_markets_runs_failed",
            limit=limit,
        )


@mcp.tool(structured_output=True)
def list_improvement_targets() -> dict[str, Any]:
    """List all registered generic improvement-loop targets."""
    try:
        return _collect_improvement_targets()
    except Exception as exc:
        return _failure(f"Failed to list improvement targets: {exc}", error_code="targets_failed")


@mcp.tool(structured_output=True)
def inspect_improvement_target(
    target: str = "harness",
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    benchmark_profile: str = BenchmarkProfile.full.value,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Inspect the current state of one improvement-loop target."""
    try:
        return _collect_improvement_inspection(
            target,
            runtime=runtime,
            allow_fallback=allow_fallback,
            benchmark_profile=BenchmarkProfile(benchmark_profile),
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to inspect target {target!r}: {exc}",
            error_code="inspect_failed",
            target=target,
        )


@mcp.tool(structured_output=True)
def run_improvement_round(
    target: str = "harness",
    mode: str = "suggest_only",
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    benchmark_profile: str = BenchmarkProfile.full.value,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run a single bounded improvement round for a target."""
    try:
        return _run_improvement_round(
            target,
            mode,
            runtime=runtime,
            allow_fallback=allow_fallback,
            benchmark_profile=BenchmarkProfile(benchmark_profile),
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to run improvement round for {target!r}: {exc}",
            error_code="round_failed",
            target=target,
            mode=mode,
        )


@mcp.tool(structured_output=True)
def run_improvement_loop(
    target: str = "harness",
    mode: str = "suggest_only",
    max_rounds: int = 3,
    runtime: str = RuntimeBackend.pydanticai.value,
    allow_fallback: bool = True,
    benchmark_profile: str = BenchmarkProfile.full.value,
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Run a bounded multi-round improvement loop for a target."""
    try:
        return _run_improvement_loop(
            target,
            mode,
            max_rounds=max_rounds,
            runtime=runtime,
            allow_fallback=allow_fallback,
            benchmark_profile=BenchmarkProfile(benchmark_profile),
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to run improvement loop for {target!r}: {exc}",
            error_code="loop_failed",
            target=target,
            mode=mode,
            max_rounds=max_rounds,
        )


@mcp.tool(structured_output=True)
def inspect_harness_state(
    config_path: str = "config.yaml",
    benchmark_path: str | None = None,
    benchmark_profile: str = BenchmarkProfile.full.value,
    memory_path: str = str(DEFAULT_HARNESS_MEMORY_PATH),
    backend_mode: str | None = None,
) -> dict[str, Any]:
    """Inspect the current harness snapshot, benchmark suite, and registered engine backends."""
    try:
        return _collect_harness_inspection(
            config_path=config_path,
            benchmark_path=benchmark_path,
            benchmark_profile=BenchmarkProfile(benchmark_profile),
            memory_path=memory_path,
            backend_mode=backend_mode,
        )
    except Exception as exc:
        return _failure(
            f"Failed to inspect harness state: {exc}",
            error_code="harness_inspect_failed",
            config_path=config_path,
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
